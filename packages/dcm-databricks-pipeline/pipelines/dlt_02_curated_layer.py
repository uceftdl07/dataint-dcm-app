# Databricks notebook source
"""
Delta Live Tables Pipeline - Layer 2: CURATED (Silver)
Architecture :
  - Staging views (_stg_X)       : parse VARIANT body + colonnes DQ
  - Filtered views (_stg_X_valid): enregistrements valides uniquement → apply_changes
  - Tables principales           : apply_changes (MERGE) avec clés de dédup
  - Tables rejects               : captures des échecs DQ

Target: it.ba_data_connect_monitoring__d

MODIFICATIONS vs version précédente — alignement sur les fichiers JSON réels :
  ┌──────────────────┬──────────────────────────┬──────────────────────────────────────────────┐
  │ Domaine          │ Changement                │ Détail                                       │
  ├──────────────────┼──────────────────────────┼──────────────────────────────────────────────┤
  │ GLOBAL           │ Structure body            │ Métriques dans body:metrics[] (array VARIANT)│
  │                  │                           │ et non dans body:payload (objet VARIANT)     │
  │                  │ parse_envelope_and_dq     │ Adapté : EXPLODE body:metrics + envelope     │
  │                  │                           │ lu directement depuis raw (pas du body)      │
  ├──────────────────┼──────────────────────────┼──────────────────────────────────────────────┤
  │ pipeline         │ Champs ajoutés            │ factory_name, resource_group, glue_job_name  │
  │                  │ Champ supprimé            │ pipeline_type (absent du JSON réel)          │
  │                  │ DQ status                 │ Valeurs lowercase : succeeded/failed/running │
  ├──────────────────┼──────────────────────────┼──────────────────────────────────────────────┤
  │ compute          │ Filtre domain             │ 'compute' (était 'cluster')                  │
  │                  │ Renommages                │ cluster_name→resource_name                   │
  │                  │                           │ cluster_type→compute_type                    │
  │                  │                           │ instance_type→node_type                      │
  │                  │                           │ node_count→num_workers                       │
  │                  │ Champs ajoutés            │ autoscale_min, autoscale_max, spark_version  │
  │                  │                           │ start_time, creator, estimated_hourly_cost   │
  │                  │                           │ workspace_id                                 │
  │                  │ Champs supprimés          │ uptime_hours, auto_scaling_enabled           │
  │                  │                           │ (absents du JSON réel)                       │
  │                  │ DQ auto_scaling           │ Remplacé par autoscale_min/max cohérence     │
  ├──────────────────┼──────────────────────────┼──────────────────────────────────────────────┤
  │ cost             │ Renommages                │ cost_period→period_start+period_end (2 cols) │
  │                  │                           │ resource_id→resource_group                   │
  │                  │ Champs ajoutés            │ currency, budget_name, budget_limit_usd      │
  │                  │                           │ budget_consumed_pct, period_end              │
  │                  │ Champs supprimés          │ usage_quantity, usage_unit (absents JSON)    │
  │                  │ Clés dedup                │ (period_start, service_name, source_lz_id)  │
  ├──────────────────┼──────────────────────────┼──────────────────────────────────────────────┤
  │ database         │ Renommages                │ database_id→db_id, database_name→db_name     │
  │                  │                           │ database_type→db_type                        │
  │                  │                           │ current_size_gb→storage_used_gb              │
  │                  │                           │ allocated_storage_gb→storage_limit_gb        │
  │                  │                           │ connection_count→active_connections          │
  │                  │ Champs ajoutés            │ server_name, resource_group, region          │
  │                  │                           │ cpu_percent, memory_percent, dtus_used       │
  │                  │                           │ is_available                                 │
  │                  │ Champs supprimés          │ growth_rate_gb_per_day, available_space_gb   │
  │                  │                           │ query_performance_avg_ms, backup_enabled     │
  │                  │                           │ encryption_enabled (absents JSON)            │
  │                  │ DQ rules                  │ Adaptées aux vrais champs                    │
  ├──────────────────┼──────────────────────────┼──────────────────────────────────────────────┤
  │ security         │ Renommages                │ alert_type→title (champ libre du JSON)       │
  │                  │                           │ remediation_status→status                    │
  │                  │ Champs ajoutés            │ resource_name, resource_type                 │
  │                  │                           │ remediation (texte), compromised_entity      │
  │                  │ Champ supprimé            │ resolved_at (absent JSON réel)               │
  │                  │ DQ severity               │ Lowercase : high/medium/low                  │
  │                  │ DQ status                 │ Valeurs JSON : active/resolved/dismissed     │
  ├──────────────────┼──────────────────────────┼──────────────────────────────────────────────┤
  │ activity_run     │ Renommages                │ input_rows→rows_read, output_rows→rows_written│
  │                  │ Champs ajoutés            │ pipeline_name, data_read_bytes               │
  │                  │                           │ data_written_bytes                           │
  │                  │ activity_run_id           │ Synthétisé : concat(pipeline_run_id,         │
  │                  │                           │   activity_name) — absent du JSON réel       │
  │                  │ DQ status                 │ Lowercase : succeeded/failed/inprogress      │
  ├──────────────────┼──────────────────────────┼──────────────────────────────────────────────┤
  │ user             │ Renommages                │ last_login→last_activity_at                  │
  │                  │ Champs ajoutés            │ display_name, workspace_or_account           │
  │                  │ Champ supprimé            │ created_at (absent JSON réel)                │
  │                  │ DQ user_type              │ Élargi : inclut 'databricks' et autres types │
  │                  │                           │ issus des vrais collecteurs                  │
  ├──────────────────┼──────────────────────────┼──────────────────────────────────────────────┤
  │ standard_check   │ Domaine renommé           │ 'standard_check' (était 'compliance')        │
  │ (ex-compliance)  │ Table renommée            │ curated_standard_checks (était compliance)   │
  │                  │ Renommages champs         │ policy_id→check_id, policy_name→check_name   │
  │                  │                           │ compliance_state→check_state                 │
  │                  │ Champs ajoutés            │ check_effect, non_check_reasons, resource_name│
  │                  │ Champs supprimés          │ rule_id, severity, recommendation            │
  │                  │ DQ check_state            │ non_compliant/compliant (snake_case JSON)    │
  └──────────────────┴──────────────────────────┴──────────────────────────────────────────────┘
"""

import dlt
from pyspark.sql.functions import col, expr, when, concat_ws, lit, explode


# ---------------------------------------------------------------------------
# Schema helper
# ---------------------------------------------------------------------------
def _ddl(*fields):
    """Build a comma-separated DDL schema string from (name, type, comment) tuples."""
    return ", ".join(f"{n} {t} COMMENT '{c}'" for n, t, c in fields)


# Colonnes d'enveloppe communes à toutes les tables curated
_ENVELOPE = [
    ("collection_run_id",        "STRING",    "Unique identifier for the data collection batch run"),
    ("source_lz_id",             "STRING",    "Landing zone identifier where this metric originated"),
    ("cloud_provider",           "STRING",    "Cloud platform: aws or azure"),
    ("subscription_or_account_id","STRING",   "Cloud subscription or account identifier"),
    ("collected_at",             "TIMESTAMP", "Timestamp when the metric was collected at source"),
    ("_ingested_at",             "TIMESTAMP", "Timestamp when the record was ingested into the raw layer"),
]

DQ_COLS = ["_dq_is_valid", "_dq_rejection_reasons"]


# ---------------------------------------------------------------------------
# Helper principal : explode metrics[], parse enveloppe + DQ
# ---------------------------------------------------------------------------
def parse_metrics_and_dq(df, metric_fields, dq_rules=None):
    """
    Adapté à la structure JSON réelle :
      - Les métriques sont dans body:metrics[] (ARRAY<VARIANT>)
      - L'enveloppe (collection_run_id, cloud_provider, etc.) est stockée
        directement dans les colonnes de raw_metrics (pas dans body:payload)

    Étapes :
      1. EXPLODE body:metrics  →  une ligne par métrique
      2. Parse les champs d'enveloppe depuis les colonnes raw
      3. Parse les champs métier depuis chaque élément du tableau
      4. Calcul DQ
    """
    # Explode le tableau metrics[] contenu dans le VARIANT body
    # VARIANT ne peut pas être passé directement à explode() →
    # cast en ARRAY<VARIANT> via from_json(to_json(...)) ou cast explicite
    exploded = df.select(
        col("collection_run_id"),
        col("source_lz_id"),
        col("cloud_provider"),
        col("_ingested_at"),
        expr("body:subscription_or_account_id::STRING").alias("subscription_or_account_id"),
        expr("body:collected_at::TIMESTAMP").alias("collected_at"),
        explode(expr("body:metrics::ARRAY<VARIANT>")).alias("metric"),
    )

    # Construction du SELECT final : enveloppe + champs métier
    parsed = exploded.select(
        expr("uuid()").alias("row_id"),
        col("collection_run_id"),
        col("source_lz_id"),
        col("cloud_provider"),
        col("subscription_or_account_id"),
        col("collected_at"),
        col("_ingested_at"),
        *metric_fields,
    )

    # Ajout des colonnes DQ
    if dq_rules:
        valid_expr = " AND ".join(f"COALESCE(({c}), false)" for c in dq_rules.values())
        reason_cols = [
            when(~expr(f"COALESCE(({c}), false)"), lit(name))
            for name, c in dq_rules.items()
        ]
        parsed = (
            parsed
            .withColumn("_dq_is_valid", expr(valid_expr))
            .withColumn("_dq_rejection_reasons", concat_ws("; ", *reason_cols))
        )
    else:
        parsed = (
            parsed
            .withColumn("_dq_is_valid", lit(True))
            .withColumn("_dq_rejection_reasons", lit(None).cast("string"))
        )

    return parsed


# ===================================================================
# 1. PIPELINE METRICS
# ===================================================================
@dlt.view(name="_stg_pipeline")
def _stg_pipeline():
    raw = dlt.read_stream("raw_metrics").filter(col("domain") == "pipeline")
    return parse_metrics_and_dq(raw, [
        expr("metric:pipeline_id::STRING").alias("pipeline_id"),
        expr("metric:pipeline_name::STRING").alias("pipeline_name"),
        expr("metric:run_id::STRING").alias("run_id"),
        expr("metric:status::STRING").alias("status"),
        expr("metric:trigger_type::STRING").alias("trigger_type"),
        expr("metric:start_time::TIMESTAMP").alias("start_time"),
        expr("metric:end_time::TIMESTAMP").alias("end_time"),
        expr("metric:duration_seconds::DOUBLE").alias("duration_seconds"),
        expr("metric:error_message::STRING").alias("error_message"),
        # Champs spécifiques cloud — NULL si absent (ex : glue_job_name sur Azure)
        expr("metric:factory_name::STRING").alias("factory_name"),
        expr("metric:resource_group::STRING").alias("resource_group"),
        expr("metric:glue_job_name::STRING").alias("glue_job_name"),
        expr("metric:tags::STRING").alias("tags"),
    ], {
        "valid_pipeline_id": "pipeline_id IS NOT NULL",
        "valid_run_id":      "run_id IS NOT NULL",
        # Valeurs lowercase dans les JSON réels
        "valid_status": "status IN ('succeeded','failed','running','cancelled','queued','timed_out')",
    })


@dlt.view(name="_stg_pipeline_valid")
def _stg_pipeline_valid():
    return dlt.read_stream("_stg_pipeline").filter("_dq_is_valid = true").drop(*DQ_COLS)


dlt.create_streaming_table(
    name="curated_pipeline_metrics",
    schema=_ddl(
        ("row_id",            "STRING",    "Surrogate UUID key"),
        *_ENVELOPE,
        ("pipeline_id",       "STRING",    "Unique pipeline identifier (dedup key)"),
        ("pipeline_name",     "STRING",    "Human-readable pipeline name"),
        ("run_id",            "STRING",    "Unique execution run identifier (dedup key)"),
        ("status",            "STRING",    "Execution status: succeeded, failed, running, cancelled, queued, timed_out"),
        ("trigger_type",      "STRING",    "Trigger mode: scheduled, manual, or event"),
        ("start_time",        "TIMESTAMP", "Pipeline run start timestamp"),
        ("end_time",          "TIMESTAMP", "Pipeline run end timestamp; NULL if still running"),
        ("duration_seconds",  "DOUBLE",    "Total execution duration in seconds"),
        ("error_message",     "STRING",    "Error details if run failed; NULL otherwise"),
        ("factory_name",      "STRING",    "ADF factory name (Azure only); NULL on AWS"),
        ("resource_group",    "STRING",    "Azure resource group; NULL on AWS"),
        ("glue_job_name",     "STRING",    "AWS Glue job name (AWS only); NULL on Azure"),
        ("tags",              "STRING",    "Freeform tags associated with the pipeline run"),
    ) + ", CONSTRAINT pk_curated_pipeline PRIMARY KEY (pipeline_id, run_id, source_lz_id)",
    comment="Pipeline execution metrics from multi-cloud landing zones. MERGE dedup on (pipeline_id, run_id, source_lz_id).",
    table_properties={"quality": "silver", "delta.enableChangeDataFeed": "true"},
)
dlt.apply_changes(
    target="curated_pipeline_metrics",
    source="_stg_pipeline_valid",
    keys=["pipeline_id", "run_id", "source_lz_id"],
    sequence_by=col("_ingested_at"),
    stored_as_scd_type=1,
)

@dlt.table(name="curated_pipeline_metrics_rejects",
           comment="DQ rejected records from pipeline domain",
           table_properties={"quality": "bronze"})
def curated_pipeline_metrics_rejects():
    return dlt.read_stream("_stg_pipeline").filter("_dq_is_valid = false")


# ===================================================================
# 2. COMPUTE METRICS  (domaine JSON réel : 'compute', anciennement 'cluster')
# ===================================================================
@dlt.view(name="_stg_compute")
def _stg_compute():
    # Filtre sur 'compute' — le JSON réel n'utilise PAS 'cluster'
    raw = dlt.read_stream("raw_metrics").filter(col("domain") == "compute")
    return parse_metrics_and_dq(raw, [
        expr("metric:compute_resource_id::STRING").alias("compute_resource_id"),
        # JSON réel : resource_name (anciennement cluster_name dans le modèle DLT)
        expr("metric:resource_name::STRING").alias("resource_name"),
        # JSON réel : compute_type (anciennement cluster_type)
        expr("metric:compute_type::STRING").alias("compute_type"),
        # JSON réel : node_type (anciennement instance_type)
        expr("metric:node_type::STRING").alias("node_type"),
        # JSON réel : num_workers (anciennement node_count)
        expr("metric:num_workers::INT").alias("num_workers"),
        expr("metric:state::STRING").alias("state"),
        expr("metric:avg_cpu_utilization_pct::DOUBLE").alias("avg_cpu_utilization_pct"),
        expr("metric:avg_mem_utilization_pct::DOUBLE").alias("avg_mem_utilization_pct"),
        # Champs autoscaling (nouveaux dans le JSON réel)
        expr("metric:autoscale_min::INT").alias("autoscale_min"),
        expr("metric:autoscale_max::INT").alias("autoscale_max"),
        # Champs additionnels présents dans le JSON réel
        expr("metric:spark_version::STRING").alias("spark_version"),
        expr("metric:start_time::TIMESTAMP").alias("start_time"),
        expr("metric:creator::STRING").alias("creator"),
        expr("metric:estimated_hourly_cost_usd::DOUBLE").alias("estimated_hourly_cost_usd"),
        expr("metric:workspace_id::STRING").alias("workspace_id"),
        expr("metric:tags::STRING").alias("tags"),
    ], {
        "valid_compute_id":  "compute_resource_id IS NOT NULL",
        "cpu_in_range":      "avg_cpu_utilization_pct IS NULL OR (avg_cpu_utilization_pct >= 0 AND avg_cpu_utilization_pct <= 100)",
        "mem_in_range":      "avg_mem_utilization_pct IS NULL OR (avg_mem_utilization_pct >= 0 AND avg_mem_utilization_pct <= 100)",
        "valid_num_workers": "num_workers IS NULL OR num_workers >= 0",
        # Cohérence autoscaling (si les deux sont renseignés)
        "autoscale_coherent": "autoscale_min IS NULL OR autoscale_max IS NULL OR autoscale_max >= autoscale_min",
    })


@dlt.view(name="_stg_compute_valid")
def _stg_compute_valid():
    return dlt.read_stream("_stg_compute").filter("_dq_is_valid = true").drop(*DQ_COLS)


dlt.create_streaming_table(
    name="curated_compute_metrics",
    schema=_ddl(
        ("row_id",                     "STRING",    "Surrogate UUID key"),
        *_ENVELOPE,
        ("compute_resource_id",        "STRING",    "Unique compute cluster identifier (dedup key)"),
        ("resource_name",              "STRING",    "Human-readable cluster/resource name"),
        ("compute_type",               "STRING",    "Compute type: databricks, emr, synapse, etc."),
        ("node_type",                  "STRING",    "Cloud VM or instance type, e.g. Standard_DS3_v2"),
        ("num_workers",                "INT",       "Current number of worker nodes"),
        ("state",                      "STRING",    "Cluster state: running, terminated, pending, etc."),
        ("avg_cpu_utilization_pct",    "DOUBLE",    "Average CPU utilization pct (0-100); DQ validated"),
        ("avg_mem_utilization_pct",    "DOUBLE",    "Average memory utilization pct (0-100); DQ validated"),
        ("autoscale_min",              "INT",       "Minimum workers for autoscaling; NULL if fixed size"),
        ("autoscale_max",              "INT",       "Maximum workers for autoscaling; NULL if fixed size"),
        ("spark_version",              "STRING",    "Spark/Databricks runtime version; NULL for non-Spark clusters"),
        ("start_time",                 "TIMESTAMP", "Cluster start timestamp"),
        ("creator",                    "STRING",    "IAM role or user that created the cluster"),
        ("estimated_hourly_cost_usd",  "DOUBLE",    "Estimated hourly cost in USD"),
        ("workspace_id",               "STRING",    "Databricks workspace identifier; NULL for non-Databricks"),
        ("tags",                       "STRING",    "Freeform tags associated with the cluster"),
    ) + ", CONSTRAINT pk_curated_compute PRIMARY KEY (compute_resource_id, source_lz_id)",
    comment="Compute cluster metrics. Domain filter: 'compute' (JSON réel). MERGE dedup on (compute_resource_id, source_lz_id).",
    table_properties={"quality": "silver", "delta.enableChangeDataFeed": "true"},
)
dlt.apply_changes(
    target="curated_compute_metrics",
    source="_stg_compute_valid",
    keys=["compute_resource_id", "source_lz_id"],
    sequence_by=col("_ingested_at"),
    stored_as_scd_type=1,
)

@dlt.table(name="curated_compute_metrics_rejects",
           comment="DQ rejected records from compute domain",
           table_properties={"quality": "bronze"})
def curated_compute_metrics_rejects():
    return dlt.read_stream("_stg_compute").filter("_dq_is_valid = false")


# ===================================================================
# 3. COST METRICS
# ===================================================================
@dlt.view(name="_stg_cost")
def _stg_cost():
    raw = dlt.read_stream("raw_metrics").filter(col("domain") == "cost")
    return parse_metrics_and_dq(raw, [
        expr("metric:service_name::STRING").alias("service_name"),
        # JSON réel : resource_group (anciennement resource_id)
        expr("metric:resource_group::STRING").alias("resource_group"),
        # JSON réel : period_start / period_end (anciennement cost_period unique)
        expr("metric:period_start::STRING").alias("period_start"),
        expr("metric:period_end::STRING").alias("period_end"),
        expr("metric:cost_usd::DOUBLE").alias("cost_usd"),
        expr("metric:currency::STRING").alias("currency"),
        # Champs budget — nouveaux dans le JSON réel
        expr("metric:budget_name::STRING").alias("budget_name"),
        expr("metric:budget_limit_usd::DOUBLE").alias("budget_limit_usd"),
        expr("metric:budget_consumed_pct::DOUBLE").alias("budget_consumed_pct"),
        expr("metric:tags::STRING").alias("tags"),
    ], {
        "valid_cost":    "cost_usd >= 0",
        "valid_period":  "period_start IS NOT NULL",
        "valid_service": "service_name IS NOT NULL",
        "valid_budget_pct": "budget_consumed_pct IS NULL OR (budget_consumed_pct >= 0 AND budget_consumed_pct <= 200)",
    })


@dlt.view(name="_stg_cost_valid")
def _stg_cost_valid():
    return dlt.read_stream("_stg_cost").filter("_dq_is_valid = true").drop(*DQ_COLS)


dlt.create_streaming_table(
    name="curated_cost_metrics",
    schema=_ddl(
        ("row_id",               "STRING", "Surrogate UUID key"),
        *_ENVELOPE,
        ("service_name",         "STRING", "Cloud service name: Amazon EMR, Azure Databricks, etc. (dedup key)"),
        ("resource_group",       "STRING", "Azure resource group or AWS resource group tag"),
        ("period_start",         "STRING", "Billing period start date YYYY-MM-DD (dedup key)"),
        ("period_end",           "STRING", "Billing period end date YYYY-MM-DD"),
        ("cost_usd",             "DOUBLE", "Cost amount in USD; DQ validated >= 0"),
        ("currency",             "STRING", "Currency code, e.g. USD"),
        ("budget_name",          "STRING", "Budget name if a budget is configured; NULL otherwise"),
        ("budget_limit_usd",     "DOUBLE", "Budget threshold in USD; NULL if no budget"),
        ("budget_consumed_pct",  "DOUBLE", "Percentage of budget consumed; DQ validated 0-200"),
        ("tags",                 "STRING", "Freeform tags associated with the cost record"),
    ) + ", CONSTRAINT pk_curated_cost PRIMARY KEY (period_start, service_name, source_lz_id)",
    comment="Cloud cost metrics. MERGE dedup on (period_start, service_name, source_lz_id).",
    table_properties={"quality": "silver"},
)
dlt.apply_changes(
    target="curated_cost_metrics",
    source="_stg_cost_valid",
    keys=["period_start", "service_name", "source_lz_id"],
    sequence_by=col("_ingested_at"),
    stored_as_scd_type=1,
)

@dlt.table(name="curated_cost_metrics_rejects",
           comment="DQ rejected records from cost domain",
           table_properties={"quality": "bronze"})
def curated_cost_metrics_rejects():
    return dlt.read_stream("_stg_cost").filter("_dq_is_valid = false")


# ===================================================================
# 4. DATABASE METRICS
# ===================================================================
@dlt.view(name="_stg_database")
def _stg_database():
    raw = dlt.read_stream("raw_metrics").filter(col("domain") == "database")
    return parse_metrics_and_dq(raw, [
        # JSON réel : db_id (anciennement database_id)
        expr("metric:db_id::STRING").alias("db_id"),
        expr("metric:db_name::STRING").alias("db_name"),
        expr("metric:db_type::STRING").alias("db_type"),
        expr("metric:server_name::STRING").alias("server_name"),
        expr("metric:resource_group::STRING").alias("resource_group"),
        expr("metric:region::STRING").alias("region"),
        # Métriques de performance (nouveaux champs dans le JSON réel)
        expr("metric:cpu_percent::DOUBLE").alias("cpu_percent"),
        expr("metric:memory_percent::DOUBLE").alias("memory_percent"),
        # JSON réel : storage_used_gb (anciennement current_size_gb)
        expr("metric:storage_used_gb::DOUBLE").alias("storage_used_gb"),
        # JSON réel : storage_limit_gb (anciennement allocated_storage_gb)
        expr("metric:storage_limit_gb::DOUBLE").alias("storage_limit_gb"),
        # JSON réel : active_connections (anciennement connection_count)
        expr("metric:active_connections::INT").alias("active_connections"),
        expr("metric:dtus_used::DOUBLE").alias("dtus_used"),
        expr("metric:is_available::BOOLEAN").alias("is_available"),
        expr("metric:tags::STRING").alias("tags"),
    ], {
        "valid_db_id":             "db_id IS NOT NULL",
        "valid_storage_used":      "storage_used_gb IS NULL OR storage_used_gb >= 0",
        "valid_storage_limit":     "storage_limit_gb IS NULL OR storage_limit_gb >= 0",
        "storage_within_limit":    "storage_used_gb IS NULL OR storage_limit_gb IS NULL OR storage_used_gb <= storage_limit_gb",
        "cpu_in_range":            "cpu_percent IS NULL OR (cpu_percent >= 0 AND cpu_percent <= 100)",
        "mem_in_range":            "memory_percent IS NULL OR (memory_percent >= 0 AND memory_percent <= 100)",
    })


@dlt.view(name="_stg_database_valid")
def _stg_database_valid():
    return dlt.read_stream("_stg_database").filter("_dq_is_valid = true").drop(*DQ_COLS)


dlt.create_streaming_table(
    name="curated_database_metrics",
    schema=_ddl(
        ("row_id",            "STRING",  "Surrogate UUID key"),
        *_ENVELOPE,
        ("db_id",             "STRING",  "Unique database resource identifier (dedup key)"),
        ("db_name",           "STRING",  "Database name"),
        ("db_type",           "STRING",  "Database engine: sqlserver, postgresql, mysql, etc."),
        ("server_name",       "STRING",  "Fully qualified server hostname"),
        ("resource_group",    "STRING",  "Azure resource group containing this database"),
        ("region",            "STRING",  "Cloud region where the database is deployed"),
        ("cpu_percent",       "DOUBLE",  "Current CPU utilization percentage (0-100)"),
        ("memory_percent",    "DOUBLE",  "Current memory utilization percentage (0-100)"),
        ("storage_used_gb",   "DOUBLE",  "Current storage used in GB; DQ validated >= 0"),
        ("storage_limit_gb",  "DOUBLE",  "Total allocated storage in GB; DQ validated > 0"),
        ("active_connections","INT",     "Number of active database connections"),
        ("dtus_used",         "DOUBLE",  "DTUs consumed (Azure SQL specific); NULL for other engines"),
        ("is_available",      "BOOLEAN", "Whether the database is currently available"),
        ("tags",              "STRING",  "Freeform tags"),
    ) + ", CONSTRAINT pk_curated_database PRIMARY KEY (db_id, source_lz_id)",
    comment="Database health metrics. MERGE dedup on (db_id, source_lz_id).",
    table_properties={"quality": "silver"},
)
dlt.apply_changes(
    target="curated_database_metrics",
    source="_stg_database_valid",
    keys=["db_id", "source_lz_id"],
    sequence_by=col("_ingested_at"),
    stored_as_scd_type=1,
)

@dlt.table(name="curated_database_metrics_rejects",
           comment="DQ rejected records from database domain",
           table_properties={"quality": "bronze"})
def curated_database_metrics_rejects():
    return dlt.read_stream("_stg_database").filter("_dq_is_valid = false")


# ===================================================================
# 5. SECURITY ALERTS
# ===================================================================
@dlt.view(name="_stg_security")
def _stg_security():
    raw = dlt.read_stream("raw_metrics").filter(col("domain") == "security")
    return parse_metrics_and_dq(raw, [
        expr("metric:alert_id::STRING").alias("alert_id"),
        # JSON réel : title (anciennement alert_type — champ libre)
        expr("metric:title::STRING").alias("title"),
        expr("metric:description::STRING").alias("description"),
        # Severity en lowercase dans le JSON réel : high, medium, low
        expr("metric:severity::STRING").alias("severity"),
        # JSON réel : status (anciennement remediation_status)
        # Valeurs JSON : active, resolved, dismissed
        expr("metric:status::STRING").alias("status"),
        expr("metric:detected_at::TIMESTAMP").alias("detected_at"),
        expr("metric:resource_id::STRING").alias("resource_id"),
        # Champs additionnels dans le JSON réel
        expr("metric:resource_name::STRING").alias("resource_name"),
        expr("metric:resource_type::STRING").alias("resource_type"),
        expr("metric:remediation::STRING").alias("remediation"),
        expr("metric:compromised_entity::STRING").alias("compromised_entity"),
        expr("metric:tags::STRING").alias("tags"),
    ], {
        "valid_alert_id": "alert_id IS NOT NULL",
        # Lowercase dans les JSON réels
        "valid_severity": "severity IN ('critical','high','medium','low','informational')",
        # Valeurs JSON réelles (pas open/in_progress/resolved/dismissed)
        "valid_status":   "status IN ('active','resolved','dismissed','in_progress')",
    })


@dlt.view(name="_stg_security_valid")
def _stg_security_valid():
    return dlt.read_stream("_stg_security").filter("_dq_is_valid = true").drop(*DQ_COLS)


dlt.create_streaming_table(
    name="curated_security_alerts",
    schema=_ddl(
        ("row_id",              "STRING",    "Surrogate UUID key"),
        *_ENVELOPE,
        ("alert_id",            "STRING",    "Unique security alert identifier (dedup key)"),
        ("title",               "STRING",    "Short alert title (free text from Defender/Security Center)"),
        ("description",         "STRING",    "Detailed alert description"),
        ("severity",            "STRING",    "Alert severity: critical, high, medium, low, informational"),
        ("status",              "STRING",    "Alert lifecycle status: active, in_progress, resolved, dismissed"),
        ("detected_at",         "TIMESTAMP", "Timestamp when the alert was first detected"),
        ("resource_id",         "STRING",    "Full resource identifier of the affected resource"),
        ("resource_name",       "STRING",    "Short resource name"),
        ("resource_type",       "STRING",    "Azure/AWS resource type, e.g. Microsoft.Sql/servers"),
        ("remediation",         "STRING",    "Recommended remediation steps"),
        ("compromised_entity",  "STRING",    "User or entity involved in the alert"),
        ("tags",                "STRING",    "Freeform tags"),
    ) + ", CONSTRAINT pk_curated_security PRIMARY KEY (alert_id, source_lz_id)",
    comment="Security alerts. MERGE dedup on (alert_id, source_lz_id).",
    table_properties={"quality": "silver"},
)
dlt.apply_changes(
    target="curated_security_alerts",
    source="_stg_security_valid",
    keys=["alert_id", "source_lz_id"],
    sequence_by=col("_ingested_at"),
    stored_as_scd_type=1,
)

@dlt.table(name="curated_security_alerts_rejects",
           comment="DQ rejected records from security domain",
           table_properties={"quality": "bronze"})
def curated_security_alerts_rejects():
    return dlt.read_stream("_stg_security").filter("_dq_is_valid = false")


# ===================================================================
# 6. ACTIVITY RUNS
# ===================================================================
@dlt.view(name="_stg_activity")
def _stg_activity():
    raw = dlt.read_stream("raw_metrics").filter(col("domain") == "activity_run")
    return parse_metrics_and_dq(raw, [
        # activity_run_id absent du JSON réel → synthèse à partir de pipeline_run_id + activity_name
        expr("concat(metric:pipeline_run_id::STRING, '|', metric:activity_name::STRING)").alias("activity_run_id"),
        expr("metric:pipeline_run_id::STRING").alias("pipeline_run_id"),
        expr("metric:pipeline_name::STRING").alias("pipeline_name"),
        expr("metric:activity_name::STRING").alias("activity_name"),
        expr("metric:activity_type::STRING").alias("activity_type"),
        # Status lowercase dans le JSON réel : succeeded, failed
        expr("metric:status::STRING").alias("status"),
        expr("metric:start_time::TIMESTAMP").alias("start_time"),
        expr("metric:end_time::TIMESTAMP").alias("end_time"),
        # JSON réel : duration_seconds en DOUBLE (pas INT)
        expr("metric:duration_seconds::DOUBLE").alias("duration_seconds"),
        # JSON réel : rows_read / rows_written (anciennement input_rows / output_rows)
        expr("metric:rows_read::LONG").alias("rows_read"),
        expr("metric:rows_written::LONG").alias("rows_written"),
        # Champs additionnels dans le JSON réel
        expr("metric:data_read_bytes::LONG").alias("data_read_bytes"),
        expr("metric:data_written_bytes::LONG").alias("data_written_bytes"),
        expr("metric:error_message::STRING").alias("error_message"),
        expr("metric:tags::STRING").alias("tags"),
    ], {
        "valid_activity_id":    "activity_run_id IS NOT NULL",
        "valid_pipeline_ref":   "pipeline_run_id IS NOT NULL",
        # Lowercase dans le JSON réel
        "valid_status": "status IN ('succeeded','failed','running','inprogress','cancelled','queued','timed_out')",
        "completed_has_end":    "NOT (status IN ('succeeded','failed','cancelled') AND (end_time IS NULL OR duration_seconds IS NULL))",
    })


@dlt.view(name="_stg_activity_valid")
def _stg_activity_valid():
    return dlt.read_stream("_stg_activity").filter("_dq_is_valid = true").drop(*DQ_COLS)


dlt.create_streaming_table(
    name="curated_activity_runs",
    schema=_ddl(
        ("row_id",              "STRING",    "Surrogate UUID key"),
        *_ENVELOPE,
        ("activity_run_id",     "STRING",    "Synthetic key: concat(pipeline_run_id, activity_name) (dedup key)"),
        ("pipeline_run_id",     "STRING",    "Parent pipeline run identifier (FK to curated_pipeline_metrics)"),
        ("pipeline_name",       "STRING",    "Parent pipeline name"),
        ("activity_name",       "STRING",    "Human-readable activity name"),
        ("activity_type",       "STRING",    "Activity type: copy, databricks_notebook, etc."),
        ("status",              "STRING",    "Execution status: succeeded, failed, inprogress, cancelled"),
        ("start_time",          "TIMESTAMP", "Activity start timestamp"),
        ("end_time",            "TIMESTAMP", "Activity end timestamp; NULL if inprogress"),
        ("duration_seconds",    "DOUBLE",    "Execution duration in seconds"),
        ("rows_read",           "LONG",      "Number of rows read by the activity"),
        ("rows_written",        "LONG",      "Number of rows written by the activity"),
        ("data_read_bytes",     "LONG",      "Bytes read by the activity"),
        ("data_written_bytes",  "LONG",      "Bytes written by the activity"),
        ("error_message",       "STRING",    "Error details if activity failed; NULL otherwise"),
        ("tags",                "STRING",    "Freeform tags"),
    ) + ", CONSTRAINT pk_curated_activity PRIMARY KEY (activity_run_id, source_lz_id)",
    comment="Activity-level execution metrics. activity_run_id is synthetic (no native ID in JSON). MERGE dedup on (activity_run_id, source_lz_id).",
    table_properties={"quality": "silver"},
)
dlt.apply_changes(
    target="curated_activity_runs",
    source="_stg_activity_valid",
    keys=["activity_run_id", "source_lz_id"],
    sequence_by=col("_ingested_at"),
    stored_as_scd_type=1,
)

@dlt.table(name="curated_activity_runs_rejects",
           comment="DQ rejected records from activity_run domain",
           table_properties={"quality": "bronze"})
def curated_activity_runs_rejects():
    return dlt.read_stream("_stg_activity").filter("_dq_is_valid = false")


# ===================================================================
# 7. USER METRICS
# ===================================================================
@dlt.view(name="_stg_user")
def _stg_user():
    raw = dlt.read_stream("raw_metrics").filter(col("domain") == "user")
    return parse_metrics_and_dq(raw, [
        expr("metric:user_id::STRING").alias("user_id"),
        expr("metric:user_name::STRING").alias("user_name"),
        # Valeurs JSON réelles : 'databricks', 'service_principal', etc.
        expr("metric:user_type::STRING").alias("user_type"),
        expr("metric:is_active::BOOLEAN").alias("is_active"),
        # Champs additionnels dans le JSON réel
        expr("metric:display_name::STRING").alias("display_name"),
        expr("metric:workspace_or_account::STRING").alias("workspace_or_account"),
        expr("metric:groups::STRING").alias("groups"),
        expr("metric:roles::STRING").alias("roles"),
        # JSON réel : last_activity_at (anciennement last_login)
        expr("metric:last_activity_at::TIMESTAMP").alias("last_activity_at"),
        expr("metric:tags::STRING").alias("tags"),
    ], {
        "valid_user_id": "user_id IS NOT NULL",
        # Élargi pour couvrir les vrais types collectés : databricks, service_principal, managed_identity, user
        "valid_user_type": "user_type IN ('SERVICE_PRINCIPAL','USER','MANAGED_IDENTITY','databricks','service_principal','managed_identity')",
    })


@dlt.view(name="_stg_user_valid")
def _stg_user_valid():
    return dlt.read_stream("_stg_user").filter("_dq_is_valid = true").drop(*DQ_COLS)


dlt.create_streaming_table(
    name="curated_user_metrics",
    schema=_ddl(
        ("row_id",                "STRING",    "Surrogate UUID key"),
        *_ENVELOPE,
        ("user_id",               "STRING",    "Unique user or service principal identifier (dedup key)"),
        ("user_name",             "STRING",    "User login or email"),
        ("user_type",             "STRING",    "Account type: databricks, USER, SERVICE_PRINCIPAL, MANAGED_IDENTITY"),
        ("is_active",             "BOOLEAN",   "Whether the account is currently active"),
        ("display_name",          "STRING",    "Human-readable display name"),
        ("workspace_or_account",  "STRING",    "Databricks workspace URL or cloud account reference"),
        ("groups",                "STRING",    "Group memberships; tracked for SCD2 in dim_users"),
        ("roles",                 "STRING",    "Assigned roles; tracked for SCD2 in dim_users"),
        ("last_activity_at",      "TIMESTAMP", "Timestamp of the most recent user activity"),
        ("tags",                  "STRING",    "Freeform tags"),
    ) + ", CONSTRAINT pk_curated_user PRIMARY KEY (user_id, source_lz_id, cloud_provider)",
    comment="User snapshots. MERGE dedup on (user_id, source_lz_id, cloud_provider). Feeds dim_users SCD2.",
    table_properties={"quality": "silver"},
)
dlt.apply_changes(
    target="curated_user_metrics",
    source="_stg_user_valid",
    keys=["user_id", "source_lz_id", "cloud_provider"],
    sequence_by=col("_ingested_at"),
    stored_as_scd_type=1,
)

@dlt.table(name="curated_user_metrics_rejects",
           comment="DQ rejected records from user domain",
           table_properties={"quality": "bronze"})
def curated_user_metrics_rejects():
    return dlt.read_stream("_stg_user").filter("_dq_is_valid = false")


# ===================================================================
# 8. STANDARD CHECKS  (domaine JSON réel : 'standard_check', anciennement 'compliance')
# ===================================================================
@dlt.view(name="_stg_standard_check")
def _stg_standard_check():
    # Filtre sur 'standard_check' — le JSON réel n'utilise PAS 'compliance'
    raw = dlt.read_stream("raw_metrics").filter(col("domain") == "standard_check")
    return parse_metrics_and_dq(raw, [
        # JSON réel : check_id (anciennement policy_id)
        expr("metric:check_id::STRING").alias("check_id"),
        # JSON réel : check_name (anciennement policy_name)
        expr("metric:check_name::STRING").alias("check_name"),
        # JSON réel : check_state (anciennement compliance_state)
        # Valeurs JSON : non_compliant, compliant (snake_case)
        expr("metric:check_state::STRING").alias("check_state"),
        expr("metric:resource_id::STRING").alias("resource_id"),
        expr("metric:resource_name::STRING").alias("resource_name"),
        expr("metric:resource_type::STRING").alias("resource_type"),
        # Champs spécifiques au JSON réel (absents du modèle DLT précédent)
        expr("metric:check_effect::STRING").alias("check_effect"),
        expr("metric:non_check_reasons::STRING").alias("non_check_reasons"),
        expr("metric:evaluated_at::TIMESTAMP").alias("evaluated_at"),
        expr("metric:tags::STRING").alias("tags"),
    ], {
        "valid_dedup_key":   "check_id IS NOT NULL AND resource_id IS NOT NULL AND evaluated_at IS NOT NULL",
        # snake_case dans les JSON réels (pas TitleCase)
        "valid_check_state": "check_state IN ('compliant','non_compliant','not_applicable')",
    })


@dlt.view(name="_stg_standard_check_valid")
def _stg_standard_check_valid():
    return dlt.read_stream("_stg_standard_check").filter("_dq_is_valid = true").drop(*DQ_COLS)


dlt.create_streaming_table(
    name="curated_standard_checks",
    schema=_ddl(
        ("row_id",              "STRING",    "Surrogate UUID key"),
        *_ENVELOPE,
        ("check_id",            "STRING",    "Policy/check definition identifier (dedup key)"),
        ("check_name",          "STRING",    "Human-readable check name"),
        ("check_state",         "STRING",    "Evaluation result: compliant, non_compliant, not_applicable"),
        ("resource_id",         "STRING",    "Full resource identifier evaluated (dedup key)"),
        ("resource_name",       "STRING",    "Short resource name"),
        ("resource_type",       "STRING",    "Azure/AWS resource type"),
        ("check_effect",        "STRING",    "Policy effect: audit, deny, deployifnotexists, etc."),
        ("non_check_reasons",   "STRING",    "Serialized list of non-compliance reasons; NULL if compliant"),
        ("evaluated_at",        "TIMESTAMP", "Timestamp of the compliance evaluation (dedup key)"),
        ("tags",                "STRING",    "Freeform tags including policy_initiative"),
    ) + ", CONSTRAINT pk_curated_standard_check PRIMARY KEY (check_id, resource_id, source_lz_id, evaluated_at)",
    comment="Compliance/standard check results. Domain filter: 'standard_check'. MERGE dedup on (check_id, resource_id, source_lz_id, evaluated_at).",
    table_properties={"quality": "silver"},
)
dlt.apply_changes(
    target="curated_standard_checks",
    source="_stg_standard_check_valid",
    keys=["check_id", "resource_id", "source_lz_id", "evaluated_at"],
    sequence_by=col("_ingested_at"),
    stored_as_scd_type=1,
)

@dlt.table(name="curated_standard_checks_rejects",
           comment="DQ rejected records from standard_check domain",
           table_properties={"quality": "bronze"})
def curated_standard_checks_rejects():
    return dlt.read_stream("_stg_standard_check").filter("_dq_is_valid = false")


# ===================================================================
# 9. WORKFLOW RUNS  (domaine 'workflow' — Databricks Workflows, epic 009)
# ===================================================================
# Observabilité des runs de Workflows Databricks (Jobs & Pipelines).
# Faits bruts par run émis par DatabricksWorkflowCollector ; les agrégats
# (success_rate, percentiles, drift, task_failure_rate, concurrency, coût FinOps)
# sont calculés en GOLD.
@dlt.view(name="_stg_dbx_workflow")
def _stg_dbx_workflow():
    raw = dlt.read_stream("raw_metrics").filter(col("domain") == "workflow")
    return parse_metrics_and_dq(raw, [
        expr("metric:workflow_id::STRING").alias("workflow_id"),
        expr("metric:workflow_name::STRING").alias("workflow_name"),
        expr("metric:run_id::STRING").alias("run_id"),
        expr("metric:workspace_id::STRING").alias("workspace_id"),
        expr("metric:workspace_name::STRING").alias("workspace_name"),
        expr("metric:status::STRING").alias("status"),
        expr("metric:trigger_type::STRING").alias("trigger_type"),
        expr("metric:start_time::TIMESTAMP").alias("start_time"),
        expr("metric:end_time::TIMESTAMP").alias("end_time"),
        expr("metric:duration_seconds::DOUBLE").alias("duration_seconds"),
        expr("metric:queued_duration_seconds::DOUBLE").alias("queued_duration_seconds"),
        expr("metric:setup_duration_seconds::DOUBLE").alias("setup_duration_seconds"),
        expr("metric:execution_duration_seconds::DOUBLE").alias("execution_duration_seconds"),
        expr("metric:cleanup_duration_seconds::DOUBLE").alias("cleanup_duration_seconds"),
        expr("metric:schedule_lag_seconds::DOUBLE").alias("schedule_lag_seconds"),
        expr("metric:retry_count::INT").alias("retry_count"),
        expr("metric:tasks_total::INT").alias("tasks_total"),
        expr("metric:tasks_failed::INT").alias("tasks_failed"),
        expr("metric:task_failure_rate::DOUBLE").alias("task_failure_rate"),
        expr("metric:cluster_instance_id::STRING").alias("cluster_instance_id"),
        expr("metric:creator_user_name::STRING").alias("creator_user_name"),
        expr("metric:run_page_url::STRING").alias("run_page_url"),
        expr("metric:run_type::STRING").alias("run_type"),
        expr("metric:error_message::STRING").alias("error_message"),
        expr("metric:tags::STRING").alias("tags"),
    ], {
        "valid_workflow_id": "workflow_id IS NOT NULL",
        "valid_run_id":      "run_id IS NOT NULL",
        "valid_status": (
            "status IN ('succeeded','failed','running','cancelled','queued','timed_out','skipped')"
        ),
    })


@dlt.view(name="_stg_dbx_workflow_valid")
def _stg_dbx_workflow_valid():
    return dlt.read_stream("_stg_dbx_workflow").filter("_dq_is_valid = true").drop(*DQ_COLS)


dlt.create_streaming_table(
    name="curated_dbx_workflow_runs",
    schema=_ddl(
        ("row_id",                     "STRING",    "Surrogate UUID key"),
        *_ENVELOPE,
        ("workflow_id",                "STRING",    "Databricks job identifier (dedup key)"),
        ("workflow_name",              "STRING",    "Human-readable workflow/job name"),
        ("run_id",                     "STRING",    "Unique Databricks run identifier (dedup key)"),
        ("workspace_id",               "STRING",    "Databricks workspace GUID"),
        ("workspace_name",             "STRING",    "Databricks workspace ARM resource name"),
        ("status",                     "STRING",    "succeeded, failed, running, cancelled, queued, timed_out, skipped"),
        ("trigger_type",               "STRING",    "Databricks trigger: periodic, one_time, retry, file_arrival, ..."),
        ("start_time",                 "TIMESTAMP", "Run start timestamp"),
        ("end_time",                   "TIMESTAMP", "Run end timestamp; NULL if still running"),
        ("duration_seconds",           "DOUBLE",    "Wall-clock run duration in seconds"),
        ("queued_duration_seconds",    "DOUBLE",    "Time queued before execution, in seconds"),
        ("setup_duration_seconds",     "DOUBLE",    "Cluster setup time, in seconds"),
        ("execution_duration_seconds", "DOUBLE",    "Task execution time, in seconds (FinOps attribution)"),
        ("cleanup_duration_seconds",   "DOUBLE",    "Cluster teardown time, in seconds"),
        ("schedule_lag_seconds",       "DOUBLE",    "Scheduled-to-actual start lag; NULL if unavailable"),
        ("retry_count",                "INT",       "Retry count (attempt_number; 0 = first attempt)"),
        ("tasks_total",                "INT",       "Total tasks in the run; NULL if not expanded"),
        ("tasks_failed",               "INT",       "Failed/timed-out/errored tasks in the run"),
        ("task_failure_rate",          "DOUBLE",    "Per-run tasks_failed / tasks_total; NULL if unavailable"),
        ("cluster_instance_id",        "STRING",    "Cluster used by the run (FinOps join key)"),
        ("creator_user_name",          "STRING",    "Principal that owns/created the job"),
        ("run_page_url",               "STRING",    "Databricks UI URL for the run"),
        ("run_type",                   "STRING",    "JOB_RUN, WORKFLOW_RUN, or SUBMIT_RUN"),
        ("error_message",              "STRING",    "State/error message on failure; NULL otherwise"),
        ("tags",                       "STRING",    "Freeform tags associated with the run"),
    ) + ", CONSTRAINT pk_curated_dbx_workflow PRIMARY KEY (workflow_id, run_id, source_lz_id)",
    comment=(
        "Databricks Workflows run observability (epic 009). "
        "MERGE dedup on (workflow_id, run_id, source_lz_id) — a run's latest snapshot wins, "
        "so an in-progress 'running' record is superseded by its terminal outcome."
    ),
    table_properties={"quality": "silver", "delta.enableChangeDataFeed": "true"},
)
dlt.apply_changes(
    target="curated_dbx_workflow_runs",
    source="_stg_dbx_workflow_valid",
    keys=["workflow_id", "run_id", "source_lz_id"],
    sequence_by=col("_ingested_at"),
    stored_as_scd_type=1,
)

@dlt.table(name="curated_dbx_workflow_runs_rejects",
           comment="DQ rejected records from workflow domain",
           table_properties={"quality": "bronze"})
def curated_dbx_workflow_runs_rejects():
    return dlt.read_stream("_stg_dbx_workflow").filter("_dq_is_valid = false")


# ---------------------------------------------------------------------------
# Workflow — grain TÂCHE (epic 009 addendum : task_id)
# ---------------------------------------------------------------------------
# Un run Databricks contient N tâches. On explose metric:tasks[] pour matérialiser
# un fait au grain tâche (task_id unique). Les mesures run-level restent dans
# curated_dbx_workflow_runs (aucune duplication).
@dlt.view(name="_stg_dbx_workflow_task")
def _stg_dbx_workflow_task():
    raw = dlt.read_stream("raw_metrics").filter(col("domain") == "workflow")

    # 1er explode : body:metrics[] → une ligne par run
    runs = raw.select(
        col("collection_run_id"),
        col("source_lz_id"),
        col("cloud_provider"),
        col("_ingested_at"),
        expr("body:subscription_or_account_id::STRING").alias("subscription_or_account_id"),
        expr("body:collected_at::TIMESTAMP").alias("collected_at"),
        explode(expr("body:metrics::ARRAY<VARIANT>")).alias("metric"),
    )

    # 2e explode : metric:tasks[] → une ligne par tâche
    tasks = runs.select(
        col("collection_run_id"),
        col("source_lz_id"),
        col("cloud_provider"),
        col("subscription_or_account_id"),
        col("collected_at"),
        col("_ingested_at"),
        expr("metric:workflow_id::STRING").alias("workflow_id"),
        expr("metric:workflow_name::STRING").alias("workflow_name"),
        expr("metric:run_id::STRING").alias("run_id"),
        expr("metric:workspace_id::STRING").alias("workspace_id"),
        expr("metric:workspace_name::STRING").alias("workspace_name"),
        explode(expr("metric:tasks::ARRAY<VARIANT>")).alias("task"),
    )

    parsed = tasks.select(
        expr("uuid()").alias("row_id"),
        col("collection_run_id"),
        col("source_lz_id"),
        col("cloud_provider"),
        col("subscription_or_account_id"),
        col("collected_at"),
        col("_ingested_at"),
        col("workflow_id"),
        col("workflow_name"),
        col("run_id"),
        col("workspace_id"),
        col("workspace_name"),
        expr("task:task_id::STRING").alias("task_id"),
        expr("task:task_key::STRING").alias("task_key"),
        expr("task:status::STRING").alias("status"),
        expr("task:start_time::TIMESTAMP").alias("start_time"),
        expr("task:end_time::TIMESTAMP").alias("end_time"),
        expr("task:duration_seconds::DOUBLE").alias("duration_seconds"),
        expr("task:attempt_number::INT").alias("attempt_number"),
        expr("task:cluster_instance_id::STRING").alias("cluster_instance_id"),
        expr("task:error_message::STRING").alias("error_message"),
    )

    dq_rules = {
        "valid_workflow_id": "workflow_id IS NOT NULL",
        "valid_run_id":      "run_id IS NOT NULL",
        "valid_task_id":     "task_id IS NOT NULL",
        "valid_status": (
            "status IN ('succeeded','failed','running','cancelled','queued','timed_out','skipped')"
        ),
    }
    valid_expr = " AND ".join(f"COALESCE(({c}), false)" for c in dq_rules.values())
    reason_cols = [
        when(~expr(f"COALESCE(({c}), false)"), lit(name)) for name, c in dq_rules.items()
    ]
    return (
        parsed
        .withColumn("_dq_is_valid", expr(valid_expr))
        .withColumn("_dq_rejection_reasons", concat_ws("; ", *reason_cols))
    )


@dlt.view(name="_stg_dbx_workflow_task_valid")
def _stg_dbx_workflow_task_valid():
    return dlt.read_stream("_stg_dbx_workflow_task").filter("_dq_is_valid = true").drop(*DQ_COLS)


dlt.create_streaming_table(
    name="curated_dbx_workflow_task_runs",
    schema=_ddl(
        ("row_id",              "STRING",    "Surrogate UUID key"),
        *_ENVELOPE,
        ("workflow_id",         "STRING",    "Parent Databricks job identifier"),
        ("workflow_name",       "STRING",    "Parent workflow/job name"),
        ("run_id",              "STRING",    "Parent Databricks run identifier"),
        ("workspace_id",        "STRING",    "Databricks workspace GUID"),
        ("workspace_name",      "STRING",    "Databricks workspace ARM resource name"),
        ("task_id",             "STRING",    "Task-level run identifier (globally unique; dedup key)"),
        ("task_key",            "STRING",    "Stable task name within the job"),
        ("status",              "STRING",    "succeeded, failed, running, cancelled, queued, timed_out, skipped"),
        ("start_time",          "TIMESTAMP", "Task start timestamp; NULL if unknown"),
        ("end_time",            "TIMESTAMP", "Task end timestamp; NULL if still running"),
        ("duration_seconds",    "DOUBLE",    "Task wall-clock duration in seconds"),
        ("attempt_number",      "INT",       "Task attempt number (0 = first attempt)"),
        ("cluster_instance_id", "STRING",    "Cluster used by the task (FinOps join key)"),
        ("error_message",       "STRING",    "Task state/error message on failure; NULL otherwise"),
    ) + ", CONSTRAINT pk_curated_dbx_workflow_task PRIMARY KEY (workflow_id, run_id, task_id, source_lz_id)",
    comment=(
        "Databricks Workflows task-grain observability (epic 009 addendum). "
        "One row per task execution (task_id). MERGE dedup on "
        "(workflow_id, run_id, task_id, source_lz_id) — latest task snapshot wins."
    ),
    table_properties={"quality": "silver", "delta.enableChangeDataFeed": "true"},
)
dlt.apply_changes(
    target="curated_dbx_workflow_task_runs",
    source="_stg_dbx_workflow_task_valid",
    keys=["workflow_id", "run_id", "task_id", "source_lz_id"],
    sequence_by=col("_ingested_at"),
    stored_as_scd_type=1,
)


@dlt.table(name="curated_dbx_workflow_task_runs_rejects",
           comment="DQ rejected records from workflow task grain",
           table_properties={"quality": "bronze"})
def curated_dbx_workflow_task_runs_rejects():
    return dlt.read_stream("_stg_dbx_workflow_task").filter("_dq_is_valid = false")