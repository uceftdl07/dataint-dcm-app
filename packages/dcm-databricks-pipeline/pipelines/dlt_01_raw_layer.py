# Databricks notebook source
"""
Delta Live Tables Pipeline - Layer 1: RAW (Bronze)
Immutable archive of complete JSON payloads stored as VARIANT

Target: it.ba_data_connect_monitoring__d

MODIFICATIONS vs version précédente:
  - Chemin volume mis à jour : it / ba_data_connect_monitoring__d
  - Ajout du domaine 'compute' (renommé depuis 'cluster')
  - Ajout du domaine 'standard_check' (renommé depuis 'compliance')
  - Liste valid_domain mise à jour pour correspondre aux vrais domaines JSON
"""

import dlt
from pyspark.sql.functions import col, current_timestamp, expr, lit, parse_json

# ---------------------------------------------------------------------------
# Configuration — surchargeable via paramètres du job Databricks
# ---------------------------------------------------------------------------
import sys
try:
    INGESTION_VOLUME_PATH = spark.conf.get(
        "pipeline.ingestion_volume_path",
        "/Volumes/it/ba_data_connect_monitoring__d/ingestion_volume/"
    )
except Exception:
    INGESTION_VOLUME_PATH = "/Volumes/it/ba_data_connect_monitoring__d/ingestion_volume/"


# ---------------------------------------------------------------------------
# RAW Layer — archive immuable en VARIANT
# ---------------------------------------------------------------------------
@dlt.table(
    name="raw_metrics",
    comment=(
        "Immutable archive of complete MetricPayload JSON from landing zones. "
        "Body stored as VARIANT for efficient semi-structured querying. "
        "Real JSON structure: envelope fields at root + metrics[] array (no nested body:payload)."
    ),
    table_properties={
        "quality": "bronze",
        "delta.enableChangeDataFeed": "true",
        "delta.autoOptimize.optimizeWrite": "true",
        "delta.autoOptimize.autoCompact": "true",
    },
    partition_cols=["domain", "cloud_provider"],
)
@dlt.expect_all_or_drop({
    "valid_collection_run_id": "collection_run_id IS NOT NULL",
    # Domaines réels issus des fichiers JSON :
    #   - 'compute'        (anciennement 'cluster' dans le modèle DLT)
    #   - 'standard_check' (anciennement 'compliance' dans le modèle DLT)
    "valid_domain": (
        "domain IN ("
        "'pipeline', 'compute', 'cost', 'database', "
        "'security', 'activity_run', 'user', 'standard_check', 'workflow'"
        ")"
    ),
    "valid_cloud_provider": "cloud_provider IN ('aws', 'azure', 'gcp')",
})
def raw_metrics():
    """
    Lit les fichiers JSON depuis le volume d'ingestion et les charge
    dans la couche RAW immuable.

    Structure JSON réelle — un objet unique par fichier :
    {
      "schema_version": "1.1",
      "collection_run_id": "...",
      "source_lz_id": "lz-azure-prod",
      "subscription_or_account_id": "...",
      "cloud_provider": "azure",
      "domain": "pipeline",
      "collected_at": "...",
      "metrics": [ { ...champs domaine... } ],
      "metadata": { ... },
      "metric_count": 1,
      "is_empty": false
    }

    Stratégie de lecture :
      text + wholetext → parse_json(value) → VARIANT directement.
      Chaque fichier est un objet JSON unique (pas un tableau).
      wholetext=true garantit que le fichier entier est lu en un seul string.
    """
    return (
        spark.readStream
            .format("cloudFiles")
            .option("cloudFiles.format", "text")
            .option("wholetext", "true")          # lit chaque fichier en un seul string
            .option("ignoreCorruptFiles", "true")
            .option("ignoreMissingFiles", "true")
            .load(INGESTION_VOLUME_PATH)
            # Chaque fichier est un objet JSON unique (pas un tableau) :
            #   { "collection_run_id": "...", "domain": "...", "metrics": [...], ... }
            # parse_json(value) → VARIANT directement, pas besoin d'exploser un tableau
            .select(parse_json(col("value")).alias("record"))
            .select(
                # body = l'enveloppe complète stockée en VARIANT (inclut metrics[])
                col("record").alias("body"),
                expr("record:collection_run_id::STRING").alias("collection_run_id"),
                expr("record:domain::STRING").alias("domain"),
                expr("record:cloud_provider::STRING").alias("cloud_provider"),
                expr("record:source_lz_id::STRING").alias("source_lz_id"),
                expr("record:schema_version::STRING").alias("schema_version"),
                expr("record:_sqs_message_id::STRING").alias("_sqs_message_id"),
                current_timestamp().alias("_ingested_at"),
            )
    )