"""Mecanisme generique de purge des tables curated FULL-LOAD (T001, 020-purge-curated-full-load).

Les tables full-load (`watermark_column is None`) ne recoivent aujourd'hui que
des upserts (`MERGE ... WHEN MATCHED/NOT MATCHED`, jamais de `DELETE`) : une
ligne supprimee cote source (ex. un SKU retire de `system.billing.list_prices`)
reste indefiniment en curated, qui derive alors silencieusement de la source
qu'elle est censee refleter fidelement (P12).

`purge_absent_rows` relit la source FRAICHE et COMPLETE (reutilise
`pipelines.common.readers`, jamais `pipelines.system_tables.ingest` — job
separe, cf. story T001), detecte par une requete SQL unique les lignes curated
du cloud traite qui n'ont plus de correspondance sur les cles metier
(`non_cloud_merge_keys`), applique un garde-fou volumetrique (seuil absolu ET
pourcentage, le plus restrictif), puis supprime via
`pipelines.common.writers.purge_rows_not_in_source` si le garde-fou n'est pas
franchi et que le run n'est pas en dry-run. Retourne INCONDITIONNELLEMENT un
`PurgeAuditRecord` (dry-run, garde-fou franchi ou suppression reelle) :
l'appelant (`pipelines.system_tables.purge_entrypoint`) l'ecrit dans
`curated_dbx_purge_audit_log` (traçabilite systematique, aucune exception).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pipelines.common.readers import (
    DEFAULT_AZURE_FETCH_BATCH_SIZE,
    read_azure_batches,
    read_native_source,
)
from pipelines.common.writers import (
    append_to_staging,
    non_cloud_merge_keys,
    purge_rows_not_in_source,
    staging_table_name,
)

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

    from pipelines.common.models import AzureConnectionConfig, IngestionSpec

logger = logging.getLogger(__name__)

RUN_MODE_DRY_RUN = "dry_run"
RUN_MODE_REAL = "real"


@dataclass(frozen=True)
class PurgeAuditRecord:
    """Une ligne d'audit par (table, cloud, run) — colonnes de
    `curated_dbx_purge_audit_log` (ecriture a la charge de l'appelant)."""

    collection_run_id: str
    curated_table: str
    cloud_provider: str
    run_mode: str
    rows_in_source: int
    rows_in_curated_before: int
    rows_to_delete: int
    rows_deleted: int
    guardrail_breached: bool
    threshold_absolute: int
    threshold_percentage: float
    started_at: str
    finished_at: str
    collected_at: str


def _guardrail_breached(
    rows_to_delete: int,
    rows_in_curated_before: int,
    threshold_absolute: int,
    threshold_percentage: float,
) -> bool:
    """True si `rows_to_delete` depasse le PLUS RESTRICTIF des 2 seuils.

    Le seuil pourcentage est une fraction de `rows_in_curated_before` (l'etat
    AVANT purge), pas de la source : une table curated deja fortement derivee
    doit rester purgeable meme si la source a peu de lignes. Le seuil effectif
    retenu est le plus petit des deux (`min`), donc le plus restrictif —
    exactement la regle actee en story T001.
    """
    percentage_limit = rows_in_curated_before * threshold_percentage
    effective_limit = min(threshold_absolute, percentage_limit)
    return rows_to_delete > effective_limit


def _count_rows_in_source_sql(source_view: str) -> str:
    """Compte les lignes de la source fraichement lue (avant tout filtre cloud)."""
    return f"SELECT COUNT(*) AS n FROM {source_view}"


def _count_rows_in_curated_sql(curated_table: str, cloud_provider: str) -> str:
    """Compte les lignes curated existantes pour ce cloud, avant purge."""
    cloud_literal = cloud_provider.replace("'", "''")
    return f"SELECT COUNT(*) AS n FROM {curated_table} WHERE cloud_provider = '{cloud_literal}'"


def _count_rows_to_delete_sql(
    curated_table: str,
    source_view: str,
    merge_keys: tuple[str, ...],
    cloud_provider: str,
) -> str:
    """Anti-join pousse en SQL via `NOT EXISTS` (jamais de join materialise
    cote driver) : compte les lignes curated de ce cloud sans correspondance
    dans la derniere lecture source, sur les cles de merge metier.

    Requete INDEPENDANTE (pas combinee avec `_count_rows_in_source_sql`/
    `_count_rows_in_curated_sql` dans un seul `SELECT (subq1),(subq2),(subq3)`)
    : empaqueter les 3 comptages dans une requete unique referencant
    `curated_table`/`source_view` a la fois avec et sans alias fait
    collisionner les `exprId` Catalyst entre les references repetees a la
    meme relation, et casse la resolution d'attribut du `NOT EXISTS` correle
    (`INTERNAL_ERROR_ATTRIBUTE_NOT_FOUND` sur `BroadcastNestedLoopJoinExec.
    existenceJoin`, constate en execution reelle sur `dcm_curated_purge`).
    Trois requetes independantes cout ent 3 aller-retours driver au lieu d'1,
    mais chacune a son propre espace d'analyse Catalyst : correction plus sure
    qu'un alias coherent, pour un cout negligeable (COUNT sur ces tables).
    """
    business_keys = non_cloud_merge_keys(merge_keys)
    cloud_literal = cloud_provider.replace("'", "''")
    anti_join_condition = " AND ".join(f"t.{key} <=> s.{key}" for key in business_keys)
    return (
        f"SELECT COUNT(*) AS n FROM {curated_table} t "
        f"WHERE t.cloud_provider = '{cloud_literal}' "
        f"AND NOT EXISTS (SELECT 1 FROM {source_view} s WHERE {anti_join_condition})"
    )


def _read_full_source(
    spark: SparkSession,
    spec: IngestionSpec,
    cloud_provider: str,
    *,
    collection_run_id: str,
    azure_config: AzureConnectionConfig | None,
    azure_batch_size: int,
) -> tuple[DataFrame | None, str | None]:
    """Materialise une lecture FRAICHE et COMPLETE de la source pour un cloud.

    AWS : lecture native directe (table de reference legere, aucun staging
    necessaire). Azure : lots bornes (`read_azure_batches`, meme lecture que
    l'ingestion) appendes dans un staging ephemere puis relus en un seul
    DataFrame — meme pattern que
    `pipelines.system_tables.ingest._ingest_azure_via_staging`, duplique ici
    volontairement (job de purge SEPARE, aucune dependance vers `ingest.py`,
    cf. story T001). Retourne `(dataframe, staging_a_supprimer)` : le 2e element
    est None quand aucun staging n'a ete cree (AWS, ou Azure sans lot). Le
    staging n'est PAS supprime ici : il doit rester vivant (DataFrame Spark
    paresseux) jusqu'a la fin du calcul ET de la suppression eventuelle,
    l'appelant le DROP dans un `finally`.
    """
    if cloud_provider == "aws":
        return read_native_source(spark, spec), None
    if azure_config is None:
        return None, None
    staging = staging_table_name(spec.curated_table, f"purge_{collection_run_id}")
    staged = False
    for batch_num, batch_df in enumerate(
        read_azure_batches(spark, spec, azure_config, None, azure_batch_size), start=1
    ):
        append_to_staging(spark, batch_df, staging, first_batch=batch_num == 1)
        staged = True
    if not staged:
        return None, None
    return spark.read.table(staging), staging


def purge_absent_rows(
    spark: SparkSession,
    spec: IngestionSpec,
    cloud_provider: str,
    *,
    collection_run_id: str,
    collected_at: str,
    threshold_absolute: int,
    threshold_percentage: float,
    dry_run: bool = False,
    azure_config: AzureConnectionConfig | None = None,
    azure_batch_size: int = DEFAULT_AZURE_FETCH_BATCH_SIZE,
) -> PurgeAuditRecord:
    """Purge (ou simule) les lignes curated absentes de la source, pour un cloud.

    Ne suppose PAS `watermark_column is None` : c'est le registre appelant
    (`pipelines.system_tables.purge_specs`) qui garantit, des l'import, que
    seules des tables full-load sont routees ici (une purge sur une table
    incrementale produirait des faux positifs — la lecture incrementale ne
    couvre jamais tout l'historique).

    Table curated absente (tout premier run) : retourne un enregistrement a
    zero sans tenter aucune lecture/suppression (rien a purger).

    Source introuvable pour ce cloud (Azure demande sans config, ou 0 lot
    Azure retourne) : le garde-fou est force a `True` (jamais de suppression) —
    sans lecture fraiche fiable, impossible de distinguer une source
    legitimement vide d'un echec de lecture transitoire ; supprimer TOUTE la
    table curated de ce cloud sur cette seule base serait precisement le
    scenario catastrophe que le garde-fou existe pour empecher.
    """
    started_at = datetime.now(UTC).isoformat()
    run_mode = RUN_MODE_DRY_RUN if dry_run else RUN_MODE_REAL

    if not spark.catalog.tableExists(spec.curated_table):
        logger.info(
            "purge.skip table=%s cloud=%s reason=curated_table_absent",
            spec.curated_table, cloud_provider,
        )
        return PurgeAuditRecord(
            collection_run_id=collection_run_id,
            curated_table=spec.curated_table,
            cloud_provider=cloud_provider,
            run_mode=run_mode,
            rows_in_source=0,
            rows_in_curated_before=0,
            rows_to_delete=0,
            rows_deleted=0,
            guardrail_breached=False,
            threshold_absolute=threshold_absolute,
            threshold_percentage=threshold_percentage,
            started_at=started_at,
            finished_at=datetime.now(UTC).isoformat(),
            collected_at=collected_at,
        )

    source_df, staging_to_drop = _read_full_source(
        spark,
        spec,
        cloud_provider,
        collection_run_id=collection_run_id,
        azure_config=azure_config,
        azure_batch_size=azure_batch_size,
    )
    try:
        if source_df is None:
            cloud_literal = cloud_provider.replace("'", "''")
            curated_count = spark.sql(
                f"SELECT COUNT(*) AS n FROM {spec.curated_table} "
                f"WHERE cloud_provider = '{cloud_literal}'"
            ).collect()[0]["n"]
            rows_in_source = 0
            rows_in_curated_before = int(curated_count)
            rows_to_delete = rows_in_curated_before
            guardrail_breached = True
            logger.warning(
                "purge.no_source table=%s cloud=%s rows_in_curated_before=%d "
                "-> guardrail forced breached (no delete)",
                spec.curated_table, cloud_provider, rows_in_curated_before,
            )
        else:
            source_view = f"_stg_purge_source__{cloud_provider}"
            source_df.createOrReplaceTempView(source_view)
            rows_in_source = int(
                spark.sql(_count_rows_in_source_sql(source_view)).collect()[0]["n"]
            )
            rows_in_curated_before = int(
                spark.sql(
                    _count_rows_in_curated_sql(spec.curated_table, cloud_provider)
                ).collect()[0]["n"]
            )
            rows_to_delete = int(
                spark.sql(
                    _count_rows_to_delete_sql(
                        spec.curated_table, source_view, spec.merge_keys, cloud_provider
                    )
                ).collect()[0]["n"]
            )
            guardrail_breached = _guardrail_breached(
                rows_to_delete, rows_in_curated_before, threshold_absolute, threshold_percentage
            )

        rows_deleted = 0
        if source_df is not None and not guardrail_breached and not dry_run and rows_to_delete > 0:
            purge_rows_not_in_source(
                spark,
                source_df,
                target_table=spec.curated_table,
                merge_keys=spec.merge_keys,
                cloud_provider=cloud_provider,
            )
            rows_deleted = rows_to_delete
        logger.info(
            "purge.done table=%s cloud=%s mode=%s rows_in_source=%d "
            "rows_in_curated_before=%d rows_to_delete=%d rows_deleted=%d guardrail_breached=%s",
            spec.curated_table, cloud_provider, run_mode, rows_in_source,
            rows_in_curated_before, rows_to_delete, rows_deleted, guardrail_breached,
        )
    finally:
        if staging_to_drop is not None:
            spark.sql(f"DROP TABLE IF EXISTS {staging_to_drop}")

    return PurgeAuditRecord(
        collection_run_id=collection_run_id,
        curated_table=spec.curated_table,
        cloud_provider=cloud_provider,
        run_mode=run_mode,
        rows_in_source=rows_in_source,
        rows_in_curated_before=rows_in_curated_before,
        rows_to_delete=rows_to_delete,
        rows_deleted=rows_deleted,
        guardrail_breached=guardrail_breached,
        threshold_absolute=threshold_absolute,
        threshold_percentage=threshold_percentage,
        started_at=started_at,
        finished_at=datetime.now(UTC).isoformat(),
        collected_at=collected_at,
    )


def write_purge_audit_record(
    spark: SparkSession, audit_table: str, record: PurgeAuditRecord
) -> None:
    """Append d'une ligne d'audit dans `audit_table` (append-only, 1 ligne/run).

    Insert pur (aucun MERGE : chaque run trace une ligne distincte, jamais
    d'upsert) ; `mergeSchema` absorbe la creation de la table au tout premier
    appel comme les runs suivants.
    """
    from dataclasses import asdict

    df = spark.createDataFrame([asdict(record)])
    df.write.format("delta").option("mergeSchema", "true").mode("append").saveAsTable(audit_table)
