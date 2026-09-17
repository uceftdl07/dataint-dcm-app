"""Orchestration d'ingestion des tables referentiel LZ : AWS ⊎ Azure -> curated.

Cable le socle `pipelines.common` (lecteurs/ecrivains, primitives dedup/filtre)
pour les 2 tables gold referentiel, en orchestration BESPOKE (pas de generique
`ingest_system_table()`, cf. `specs.py` / `research.md` §3) : les sources
`workspace_inventory` (AWS/Azure) divergent sur le nom de colonne d'identifiant
de compte, et `ref_ba_lz` n'a pas d'equivalent AWS.

Full-load (FR-005, pas de watermark) : la source entiere est relue et fusionnee
a chaque run. Avant chaque `MERGE`, les lignes a cle NULL/vide sont exclues
(FR-011) puis le DataFrame est deduplique de facon deterministe (FR-009) --
garde-fous communs factorises dans `_prepare_for_merge`.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pyspark.sql import functions as F

from pipelines.common.readers import read_azure_batches, read_native_source
from pipelines.common.transforms import dedupe_by_key, filter_null_or_empty_key
from pipelines.common.writers import append_to_staging, merge_into_table, staging_table_name
from pipelines.reference_lz.specs import (
    BA_DIM_SPEC,
    BA_LZ_SPEC,
    BUSINESS_APPLICATION_DIM_MERGE_KEYS,
    BUSINESS_APPLICATION_MERGE_KEYS,
    DBX_WORKSPACE_MERGE_KEYS,
    WORKSPACE_ACCOUNT_COLUMN_AWS,
    WORKSPACE_ACCOUNT_COLUMN_AZURE,
    WORKSPACE_ACCOUNT_COLUMN_TARGET,
    WORKSPACE_AWS_SPEC,
    WORKSPACE_AZURE_SPEC,
    WORKSPACE_CLOUD_COLUMN_SOURCE,
    WORKSPACE_CLOUD_COLUMN_TARGET,
)

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

    from pipelines.common.models import AzureConnectionConfig, IngestionSpec

logger = logging.getLogger(__name__)


def _prepare_for_merge(df: DataFrame, key_columns: tuple[str, ...]) -> DataFrame:
    """Garde-fous communs avant MERGE : filtre NULL/vide (FR-011) puis dedup (FR-009).

    L'ordre importe : filtrer d'abord les cles invalides evite qu'une ligne a
    cle NULL/vide soit choisie par `dedupe_by_key` comme representant d'un
    groupe de doublons, avant meme d'etre exclue.
    """
    return dedupe_by_key(filter_null_or_empty_key(df, *key_columns), key_columns)


def ingest_dbx_workspace(
    spark: SparkSession,
    *,
    curated_table: str,
    azure_config: AzureConnectionConfig | None,
    collection_run_id: str,
    collected_at: str,
) -> None:
    """Ingere `dim_reference_landing_zone_dbx_workspace` (union AWS + Azure).

    Full-load a chaque run (FR-005). Les 2 cotes sont MERGE SEPAREMENT (meme
    cle `workspace_id`) : un echec Azure n'affecte pas le MERGE AWS deja ecrit
    (isolation renforcee au niveau job par `for_each_task`, FR-010).
    """
    logger.info("ingest.start table=%s cloud=aws", curated_table)
    aws_rows = (
        read_native_source(spark, WORKSPACE_AWS_SPEC)
        .distinct()
        .withColumnRenamed(WORKSPACE_ACCOUNT_COLUMN_AWS, WORKSPACE_ACCOUNT_COLUMN_TARGET)
        .withColumnRenamed(WORKSPACE_CLOUD_COLUMN_SOURCE, WORKSPACE_CLOUD_COLUMN_TARGET)
        .withColumn("updated_at", F.to_timestamp(F.lit(collected_at)))
    )
    aws_rows = _prepare_for_merge(aws_rows, DBX_WORKSPACE_MERGE_KEYS)
    merge_into_table(
        spark, aws_rows, target_table=curated_table, merge_keys=DBX_WORKSPACE_MERGE_KEYS
    )
    logger.info("ingest.done table=%s cloud=aws", curated_table)

    if azure_config is None:
        logger.info("ingest.skip table=%s cloud=azure reason=no_azure_config", curated_table)
        return

    staging_table = staging_table_name(curated_table, collection_run_id)
    staged = False
    batch_num = 0
    try:
        for batch_df in read_azure_batches(spark, WORKSPACE_AZURE_SPEC, azure_config):
            batch_num += 1
            azure_rows = (
                batch_df.distinct()
                .withColumnRenamed(WORKSPACE_ACCOUNT_COLUMN_AZURE, WORKSPACE_ACCOUNT_COLUMN_TARGET)
                .withColumnRenamed(WORKSPACE_CLOUD_COLUMN_SOURCE, WORKSPACE_CLOUD_COLUMN_TARGET)
                .withColumn("updated_at", F.to_timestamp(F.lit(collected_at)))
            )
            append_to_staging(spark, azure_rows, staging_table, first_batch=not staged)
            staged = True
            logger.info(
                "ingest.azure.staged table=%s batch=%d staging=%s",
                curated_table, batch_num, staging_table,
            )
        if staged:
            staged_df = _prepare_for_merge(
                spark.read.table(staging_table), DBX_WORKSPACE_MERGE_KEYS
            )
            merge_into_table(
                spark, staged_df, target_table=curated_table, merge_keys=DBX_WORKSPACE_MERGE_KEYS
            )
            logger.info(
                "ingest.done table=%s cloud=azure total_batches=%d", curated_table, batch_num
            )
    finally:
        if staged:
            spark.sql(f"DROP TABLE IF EXISTS {staging_table}")
            logger.info("ingest.staging.dropped staging=%s", staging_table)


def ingest_business_application(
    spark: SparkSession,
    *,
    curated_table: str,
    azure_config: AzureConnectionConfig,
    collection_run_id: str,
    collected_at: str,
) -> None:
    """Ingere `dim_reference_landing_zone_business_application` (Azure seul).

    Source unique `ref_ba_lz` (Azure) : `azure_config` est REQUIS (pas de
    valeur par defaut `None`) -- le garde-fou FR-004 (config Azure absente) vit
    dans `entrypoint.main`, pas ici.
    """
    _ingest_azure_full_load(
        spark,
        spec=BA_LZ_SPEC,
        curated_table=curated_table,
        merge_keys=BUSINESS_APPLICATION_MERGE_KEYS,
        rename_pairs=(
            ("name", "business_application_name"),
            ("ba_id", "business_application_id"),
            ("lz_id", WORKSPACE_ACCOUNT_COLUMN_TARGET),
            (WORKSPACE_CLOUD_COLUMN_SOURCE, WORKSPACE_CLOUD_COLUMN_TARGET),
        ),
        azure_config=azure_config,
        collection_run_id=collection_run_id,
        collected_at=collected_at,
    )


def ingest_business_application_dim(
    spark: SparkSession,
    *,
    curated_table: str,
    azure_config: AzureConnectionConfig,
    collection_run_id: str,
    collected_at: str,
) -> None:
    """Ingere `dim_business_application` : catalogue distinct des BA (Azure seul).

    Meme source `ref_ba_lz` que `ingest_business_application`, mais projete sur
    (name, ba_id) et dedupe par `business_application_id` (une BA couvre
    plusieurs subscriptions dans la source). Remplace la materialized view creee
    a la main. `azure_config` REQUIS (garde-fou FR-004 dans `entrypoint.main`).
    """
    _ingest_azure_full_load(
        spark,
        spec=BA_DIM_SPEC,
        curated_table=curated_table,
        merge_keys=BUSINESS_APPLICATION_DIM_MERGE_KEYS,
        rename_pairs=(
            ("name", "business_application_name"),
            ("ba_id", "business_application_id"),
        ),
        azure_config=azure_config,
        collection_run_id=collection_run_id,
        collected_at=collected_at,
    )


def _ingest_azure_full_load(
    spark: SparkSession,
    *,
    spec: IngestionSpec,
    curated_table: str,
    merge_keys: tuple[str, ...],
    rename_pairs: tuple[tuple[str, str], ...],
    azure_config: AzureConnectionConfig,
    collection_run_id: str,
    collected_at: str,
) -> None:
    """Full-load Azure-seul : lecture par lots `ref_ba_lz` -> staging -> MERGE.

    Factorise le pipeline commun aux 2 tables derivees de `ref_ba_lz`
    (`dim_reference_landing_zone_business_application`, `dim_business_application`) :
    seuls le `spec` source, les `rename_pairs` (renommage fidele source) et les
    `merge_keys` different. Le staging ephemere est toujours supprime en fin.
    """
    logger.info("ingest.start table=%s cloud=azure", curated_table)
    staging_table = staging_table_name(curated_table, collection_run_id)
    staged = False
    batch_num = 0
    try:
        for batch_df in read_azure_batches(spark, spec, azure_config):
            batch_num += 1
            azure_rows = batch_df.distinct()
            for source_col, target_col in rename_pairs:
                azure_rows = azure_rows.withColumnRenamed(source_col, target_col)
            azure_rows = azure_rows.withColumn("updated_at", F.to_timestamp(F.lit(collected_at)))
            append_to_staging(spark, azure_rows, staging_table, first_batch=not staged)
            staged = True
            logger.info(
                "ingest.azure.staged table=%s batch=%d staging=%s",
                curated_table, batch_num, staging_table,
            )
        if staged:
            staged_df = _prepare_for_merge(spark.read.table(staging_table), merge_keys)
            merge_into_table(
                spark,
                staged_df,
                target_table=curated_table,
                merge_keys=merge_keys,
            )
            logger.info(
                "ingest.done table=%s cloud=azure total_batches=%d", curated_table, batch_num
            )
    finally:
        if staged:
            spark.sql(f"DROP TABLE IF EXISTS {staging_table}")
            logger.info("ingest.staging.dropped staging=%s", staging_table)
