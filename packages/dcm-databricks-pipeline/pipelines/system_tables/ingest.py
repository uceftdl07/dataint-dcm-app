"""Orchestration d'ingestion des system tables : Azure ⊎ AWS -> curated (idempotent).

Cable le socle `pipelines.common` pour une system table Databricks (facturation
ou compute/access) : lecture (native AWS / lots Azure) -> enveloppe -> MERGE
idempotent par cloud. Fidele source (no transform, no join). Aucune I/O de config
ni de secret ici : la connexion Azure et les parametres arrivent deja resolus
depuis l'entrypoint. Le corps est generique : la spec (`IngestionSpec`) porte
toute la difference entre tables.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pipelines.common.incremental import (
    DEFAULT_LOOKBACK_DAYS,
    compute_lower_bound,
    partition_predicate,
)
from pipelines.common.readers import (
    DEFAULT_AZURE_FETCH_BATCH_SIZE,
    read_azure_batches,
    read_native_source,
)
from pipelines.common.transforms import enrich_with_envelope
from pipelines.common.writers import (
    append_to_staging,
    merge_into_table,
    staging_table_name,
)

if TYPE_CHECKING:
    from datetime import datetime

    from pyspark.sql import SparkSession

    from pipelines.common.models import AzureConnectionConfig, IngestionSpec


logger = logging.getLogger(__name__)


def ingest_system_table(
    spark: SparkSession,
    spec: IngestionSpec,
    *,
    collection_run_id: str,
    collected_at: str,
    azure_config: AzureConnectionConfig | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    azure_batch_size: int = DEFAULT_AZURE_FETCH_BATCH_SIZE,
) -> None:
    """Ingere une system table Databricks Azure ⊎ AWS vers curated.

    Fidele source (no transform, no join) ; enveloppe ajoutee ; MERGE idempotent.
    Les MERGE sont SEPARES par cloud : les cles de merge incluent `cloud_provider`,
    donc chaque cloud n'ecrit que ses propres lignes (mutualisation preservee).
    La divergence de schema Azure/AWS est absorbee par l'evolution de schema Delta
    (`spark.databricks.delta.schema.autoMerge.enabled`, activee dans `main`) qui
    remplace l'ancien `unionByName(allowMissingColumns=True)`.

    - AWS : lecture Spark native (distribuee), un seul MERGE.
    - Azure : lecture via SQL connector en lots bornes (`read_azure_batches`) pour
      plafonner la memoire du driver (evite l'OOM sur l'historique complet des
      grosses tables), un staging + un MERGE final.

    En incremental (spec avec `watermark_column`), seules les lignes >= watermark
    - lookback sont lues et le MERGE est borne aux partitions concernees (pruning).
    """
    aws_lower_bound = compute_lower_bound(spark, spec, "aws", lookback_days)
    logger.info(
        "ingest.start table=%s cloud=aws lower_bound=%s", spec.source_table, aws_lower_bound
    )
    aws_enriched = enrich_with_envelope(
        read_native_source(spark, spec, aws_lower_bound),
        cloud_provider="aws",
        collected_at=collected_at,
    )
    merge_into_table(
        spark,
        aws_enriched,
        target_table=spec.curated_table,
        merge_keys=spec.merge_keys,
        partition_columns=spec.partition_columns,
        partition_predicate=partition_predicate(spec, aws_lower_bound),
    )
    logger.info("ingest.done table=%s cloud=aws", spec.source_table)

    if azure_config is None:
        return
    azure_lower_bound = compute_lower_bound(spark, spec, "azure", lookback_days)
    logger.info(
        "ingest.start table=%s cloud=azure lower_bound=%s", spec.source_table, azure_lower_bound
    )
    azure_predicate = partition_predicate(spec, azure_lower_bound)
    # Override par-spec prioritaire sur le reglage global du job : les tables
    # larges (ex. access.audit) imposent un lot plus petit pour eviter l'OOM.
    effective_batch_size = spec.azure_fetch_batch_size or azure_batch_size
    _ingest_azure_via_staging(
        spark,
        spec,
        azure_config,
        collection_run_id=collection_run_id,
        collected_at=collected_at,
        azure_lower_bound=azure_lower_bound,
        azure_predicate=azure_predicate,
        azure_batch_size=effective_batch_size,
    )


def _ingest_azure_via_staging(
    spark: SparkSession,
    spec: IngestionSpec,
    azure_config: AzureConnectionConfig,
    *,
    collection_run_id: str,
    collected_at: str,
    azure_lower_bound: datetime | None,
    azure_predicate: str | None,
    azure_batch_size: int,
) -> None:
    """Ingere Azure via table de staging + 1 unique MERGE final (optimisation).

    Au lieu d'un MERGE par lot (N scans de la cible partitionnee — couteux sur
    les grosses tables), chaque lot est APPEND (insert pur) dans un staging
    ephemere, puis un seul `MERGE INTO` deverse le staging vers curated. On passe
    de N MERGE a N append + 1 MERGE, tout en conservant :
    - la bornage memoire du driver (un lot a la fois cote `createDataFrame`) ;
    - l'idempotence (MERGE final sur les cles metier) ;
    - l'elagage de partitions (meme `partition_predicate`).

    Le staging (nomme par `collection_run_id`) est TOUJOURS supprime en fin
    (succes comme echec) : aucune table orpheline.
    """
    staging_table = staging_table_name(spec.curated_table, collection_run_id)
    staged = False
    batch_num = 0
    try:
        for batch_df in read_azure_batches(
            spark, spec, azure_config, azure_lower_bound, azure_batch_size
        ):
            batch_num += 1
            azure_enriched = enrich_with_envelope(
                batch_df,
                cloud_provider="azure",
                collected_at=collected_at,
            )
            append_to_staging(spark, azure_enriched, staging_table, first_batch=not staged)
            staged = True
            logger.info(
                "ingest.azure.staged table=%s batch=%d staging=%s",
                spec.curated_table, batch_num, staging_table,
            )
        if staged:
            merge_into_table(
                spark,
                spark.read.table(staging_table),
                target_table=spec.curated_table,
                merge_keys=spec.merge_keys,
                partition_columns=spec.partition_columns,
                partition_predicate=azure_predicate,
            )
            logger.info(
                "ingest.done table=%s cloud=azure total_batches=%d",
                spec.curated_table, batch_num,
            )
    finally:
        if staged:
            spark.sql(f"DROP TABLE IF EXISTS {staging_table}")
            logger.info("ingest.staging.dropped staging=%s", staging_table)
