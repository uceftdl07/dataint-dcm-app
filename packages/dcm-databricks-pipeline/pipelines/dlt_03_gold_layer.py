# Databricks notebook source
"""
Delta Live Tables Pipeline - Layer 3: GOLD
Architecture :
  - Dimensions : apply_changes (MERGE)
    - dim_landing_zone_collector : SCD Type 1
    - dim_users                  : SCD Type 2
  - Agrégats : Materialized views (full recompute)

Target: it.ba_data_connect_monitoring__d

MODIFICATIONS vs version précédente — alignement sur les tables curated réelles :
  ┌──────────────────────────────────┬──────────────────────────────────────────────────────────┐
  │ Table Gold                       │ Changements                                              │
  ├──────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ dim_landing_zone_collector       │ Renommée dim_landing_zone (lecture raw_metrics)          │
  ├──────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ dim_users                        │ last_login → last_activity_at                            │
  │                                  │ Ajout display_name, workspace_or_account                 │
  │                                  │ created_at supprimé (absent des JSON réels)              │
  │                                  │ track_history : ajout display_name                       │
  ├──────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ gold_pipeline_summary            │ Inchangée (colonnes status/start_time identiques)        │
  ├──────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ gold_compute_utilization         │ cluster_type → compute_type                              │
  │                                  │ total_uptime_hours supprimé (absent curated)             │
  │                                  │ Ajout : estimated_hourly_cost_usd, num_workers           │
  ├──────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ gold_cost_summary                │ cost_period → period_start                               │
  │                                  │ total_usage_quantity supprimé (absent curated)           │
  │                                  │ Ajout : budget_consumed_pct_avg                          │
  ├──────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ gold_database_capacity_alerts    │ database_id → db_id, database_name → db_name             │
  │                                  │ database_type → db_type                                  │
  │                                  │ current_size_gb → storage_used_gb                        │
  │                                  │ allocated_storage_gb → storage_limit_gb                  │
  │                                  │ growth_rate_gb_per_day supprimé (absent curated)         │
  │                                  │ available_space_gb recalculé dynamiquement               │
  │                                  │ Ajout : cpu_percent, memory_percent, is_available        │
  │                                  │ days_until_full supprimé (growth_rate absent)            │
  │                                  │ Alert level basé sur storage_utilization_pct uniquement  │
  ├──────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ gold_compliance_score →          │ Renommée curated_standard_checks                         │
  │ gold_standard_check_score        │ compliance_state → check_state                           │
  │                                  │ Valeurs snake_case : compliant / non_compliant            │
  │                                  │ severity / recommendation supprimés (absents curated)    │
  ├──────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ gold_security_summary            │ remediation_status → status                              │
  │                                  │ Valeurs : active / resolved / dismissed                  │
  │                                  │ avg_resolution_hours : resolved_at absent → basé sur     │
  │                                  │ status='resolved' uniquement (NULL sinon)                │
  ├──────────────────────────────────┼──────────────────────────────────────────────────────────┤
  │ gold_activity_performance        │ input_rows → rows_read, output_rows → rows_written       │
  │                                  │ avg_row_ratio adapté aux nouveaux noms                   │
  │                                  │ Ajout avg_data_read_bytes, avg_data_written_bytes        │
  └──────────────────────────────────┴──────────────────────────────────────────────────────────┘
"""

import dlt
from pyspark.sql.functions import (
    avg,
    col,
    count,
    current_timestamp,
    expr,
    lit,
    when,
)
from pyspark.sql.functions import (
    max as spark_max,
)
from pyspark.sql.functions import (
    min as spark_min,
)
from pyspark.sql.functions import (
    round as spark_round,
)
from pyspark.sql.functions import (
    sum as spark_sum,
)


# ---------------------------------------------------------------------------
# Schema helper
# ---------------------------------------------------------------------------
def _ddl(*fields):
    """Build a comma-separated DDL schema string from (name, type, comment) tuples."""
    return ", ".join(f"{n} {t} COMMENT '{c}'" for n, t, c in fields)


# Catalog/schema reference pour les FK
_CATALOG_SCHEMA = "`it`.`ba_data_connect_monitoring__d`"


# ===================================================================
# DIMENSION TABLES
# ===================================================================

# -------------------------------------------------------------------
# dim_landing_zone_collector  — SCD Type 1
# -------------------------------------------------------------------
@dlt.view(name="_stg_dim_landing_zone")
def _stg_dim_landing_zone():
    """Métadonnées des landing zones extraites depuis l'enveloppe raw_metrics."""
    raw = dlt.read_stream("raw_metrics")
    return raw.select(
        col("source_lz_id").alias("lz_id"),
        col("cloud_provider"),
        # subscription_or_account_id lu depuis le VARIANT body (pas de colonne directe dans raw_metrics)
        expr("body:subscription_or_account_id::STRING").alias("subscription_or_account_id"),
        col("_ingested_at"),
    ).dropDuplicates(["lz_id"]).withColumn(
        "lz_name", expr("regexp_replace(lz_id, '-[0-9]+$', '')")
    ).withColumn(
        "environment",
        when(col("lz_id").contains("prod"), lit("prod"))
        .when(col("lz_id").contains("staging"), lit("staging"))
        .when(col("lz_id").contains("dev"), lit("dev"))
        .when(col("lz_id").contains("sandbox"), lit("sandbox"))
        .when(col("lz_id").contains("qa"), lit("qa"))
        .otherwise(lit("unknown"))
    ).withColumn(
        "region",
        when(col("cloud_provider") == "aws",
             when(col("lz_id").contains("001"), lit("us-east-1"))
             .when(col("lz_id").contains("002"), lit("us-west-2"))
             .when(col("lz_id").contains("003"), lit("eu-west-1"))
             .otherwise(lit("us-east-1")))
        .when(col("cloud_provider") == "azure",
             when(col("lz_id").contains("001"), lit("eastus"))
             .when(col("lz_id").contains("002"), lit("westeurope"))
             .when(col("lz_id").contains("003"), lit("northeurope"))
             .otherwise(lit("westeurope")))
    ).withColumn(
        "owner_team",
        when(col("lz_id").contains("prod"), lit("data-platform"))
        .when(col("lz_id").contains("staging"), lit("analytics"))
        .when(col("lz_id").contains("dev"), lit("data-science"))
        .otherwise(lit("unassigned"))
    ).withColumn(
        "onboarded_at", current_timestamp().cast("date")
    ).withColumn(
        "is_active", lit(True)
    )

dlt.create_streaming_table(
    name="dim_landing_zone_collector",
    schema=_ddl(
        ("lz_id",                    "STRING",    "Unique landing zone identifier; natural key for SCD1 MERGE"),
        ("cloud_provider",           "STRING",    "Cloud platform: aws or azure"),
        ("subscription_or_account_id","STRING",   "Cloud subscription or account identifier"),
        ("_ingested_at",             "TIMESTAMP", "Source ingestion timestamp"),
        ("lz_name",                  "STRING",    "Derived LZ name (lz_id without numeric suffix)"),
        ("environment",              "STRING",    "Deployment environment: prod, staging, dev, sandbox, qa"),
        ("region",                   "STRING",    "Cloud region derived from lz_id pattern"),
        ("owner_team",               "STRING",    "Team responsible for the landing zone"),
        ("onboarded_at",             "DATE",      "Date the LZ record was first created"),
        ("is_active",                "BOOLEAN",   "Whether the landing zone is currently active"),
    ) + ", CONSTRAINT pk_dim_landing_zone_collector PRIMARY KEY (lz_id)",
    comment="Landing zone dimension (SCD Type 1). One row per LZ with latest state.",
    table_properties={"quality": "gold", "delta.enableChangeDataFeed": "true"},
)
dlt.apply_changes(
    target="dim_landing_zone_collector",
    source="_stg_dim_landing_zone",
    keys=["lz_id"],
    sequence_by=col("_ingested_at"),
    stored_as_scd_type=1,
)


# -------------------------------------------------------------------
# dim_users  — SCD Type 2
# -------------------------------------------------------------------
dlt.create_streaming_table(
    name="dim_users",
    # Pas de schema= déclaré : DLT l'infère depuis curated_user_metrics via apply_changes.
    # Évite tout conflit INFERRED_SCHEMA_NOT_COMPATIBLE lors des évolutions de schéma.
    comment="User dimension (SCD Type 2). Tracks history of groups, roles, is_active, user_type, display_name. Source: curated_user_metrics.",
    table_properties={"quality": "gold", "delta.enableChangeDataFeed": "true"},
)
dlt.apply_changes(
    target="dim_users",
    source="curated_user_metrics",
    keys=["user_id", "source_lz_id", "cloud_provider"],
    sequence_by=col("collected_at"),
    stored_as_scd_type=2,
    # display_name ajouté au suivi historique
    track_history_column_list=["groups", "roles", "is_active", "user_type", "display_name"],
)


# ===================================================================
# AGGREGATE TABLES  (materialized views)
# ===================================================================

# -------------------------------------------------------------------
# gold_pipeline_summary  — inchangée côté agrégat
# -------------------------------------------------------------------
@dlt.table(
    name="gold_pipeline_summary",
    schema=_ddl(
        ("source_lz_id",          "STRING", "Landing zone identifier"),
        ("cloud_provider",        "STRING", "Cloud platform"),
        ("execution_date",        "DATE",   "Date of pipeline execution"),
        ("status",                "STRING", "Pipeline execution status"),
        ("total_runs",            "LONG",   "Total number of pipeline runs"),
        ("avg_duration_seconds",  "DOUBLE", "Average run duration in seconds"),
        ("max_duration_seconds",  "DOUBLE", "Maximum run duration in seconds"),
        ("min_duration_seconds",  "DOUBLE", "Minimum run duration in seconds"),
        ("failed_with_error",     "LONG",   "Count of runs that failed with an error message"),
    ) + f", CONSTRAINT pk_gold_pipeline_summary PRIMARY KEY (source_lz_id, cloud_provider, execution_date, status)",
    comment="Daily pipeline execution summary by LZ, cloud, date, status. Source: curated_pipeline_metrics.",
    table_properties={"quality": "gold"},
)
def gold_pipeline_summary():
    pipelines = dlt.read("curated_pipeline_metrics")
    return pipelines.groupBy(
        col("source_lz_id"),
        col("cloud_provider"),
        expr("date(start_time)").alias("execution_date"),
        col("status"),
    ).agg(
        count("*").alias("total_runs"),
        avg("duration_seconds").alias("avg_duration_seconds"),
        spark_max("duration_seconds").alias("max_duration_seconds"),
        spark_min("duration_seconds").alias("min_duration_seconds"),
        count(when(col("error_message").isNotNull(), 1)).alias("failed_with_error"),
    )


# -------------------------------------------------------------------
# gold_compute_utilization
# -------------------------------------------------------------------
@dlt.table(
    name="gold_compute_utilization",
    schema=_ddl(
        ("source_lz_id",             "STRING", "Landing zone identifier"),
        ("cloud_provider",           "STRING", "Cloud platform"),
        # compute_type remplace cluster_type
        ("compute_type",             "STRING", "Type of compute resource: databricks, emr, etc."),
        ("cpu_utilization_status",   "STRING", "CPU flag: UNDERUTILIZED (<20pct), OPTIMAL (20-80pct), OVERUTILIZED (>80pct)"),
        ("mem_utilization_status",   "STRING", "Memory flag: UNDERUTILIZED (<20pct), OPTIMAL (20-80pct), OVERUTILIZED (>80pct)"),
        ("cluster_count",            "LONG",   "Number of clusters in this bucket"),
        ("avg_cpu_pct",              "DOUBLE", "Average CPU utilization pct"),
        ("avg_mem_pct",              "DOUBLE", "Average memory utilization pct"),
        ("avg_num_workers",          "DOUBLE", "Average number of workers across clusters"),
        ("total_estimated_cost_usd", "DOUBLE", "Sum of estimated hourly costs in USD"),
    ) + f", CONSTRAINT pk_gold_compute_util PRIMARY KEY (source_lz_id, cloud_provider, compute_type, cpu_utilization_status, mem_utilization_status)",
    comment="FinOps compute utilization analysis. Source: curated_compute_metrics.",
    table_properties={"quality": "gold"},
)
def gold_compute_utilization():
    compute = dlt.read("curated_compute_metrics")
    flagged = compute.select(
        "*",
        when(col("avg_cpu_utilization_pct") < 20, lit("UNDERUTILIZED"))
        .when(col("avg_cpu_utilization_pct") > 80, lit("OVERUTILIZED"))
        .otherwise(lit("OPTIMAL")).alias("cpu_utilization_status"),
        when(col("avg_mem_utilization_pct") < 20, lit("UNDERUTILIZED"))
        .when(col("avg_mem_utilization_pct") > 80, lit("OVERUTILIZED"))
        .otherwise(lit("OPTIMAL")).alias("mem_utilization_status"),
    )
    return flagged.groupBy(
        col("source_lz_id"), col("cloud_provider"), col("compute_type"),
        col("cpu_utilization_status"), col("mem_utilization_status"),
    ).agg(
        count("*").alias("cluster_count"),
        avg("avg_cpu_utilization_pct").alias("avg_cpu_pct"),
        avg("avg_mem_utilization_pct").alias("avg_mem_pct"),
        avg("num_workers").alias("avg_num_workers"),
        spark_sum("estimated_hourly_cost_usd").alias("total_estimated_cost_usd"),
    )


# -------------------------------------------------------------------
# gold_cost_summary
# -------------------------------------------------------------------
@dlt.table(
    name="gold_cost_summary",
    schema=_ddl(
        ("period_start",             "STRING", "Billing period start date YYYY-MM-DD"),
        ("source_lz_id",             "STRING", "Landing zone identifier"),
        ("cloud_provider",           "STRING", "Cloud platform"),
        ("environment",              "STRING", "Deployment environment (from dim_landing_zone join)"),
        ("service_name",             "STRING", "Cloud service name"),
        ("total_cost_usd",           "DOUBLE", "Sum of costs in USD"),
        ("resource_count",           "LONG",   "Count of distinct cost records"),
        ("avg_budget_consumed_pct",  "DOUBLE", "Average budget consumption pct across records"),
    ) + f", CONSTRAINT pk_gold_cost_summary PRIMARY KEY (period_start, source_lz_id, cloud_provider, environment, service_name)",
    comment="Monthly cost rollup by service, LZ, environment. Source: curated_cost_metrics.",
    table_properties={"quality": "gold"},
)
def gold_cost_summary():
    costs = dlt.read("curated_cost_metrics")
    lz_dim = dlt.read("dim_landing_zone_collector")
    enriched = costs.join(lz_dim, costs.source_lz_id == lz_dim.lz_id, "left")
    return enriched.groupBy(
        col("period_start"), costs["source_lz_id"], costs["cloud_provider"],
        col("environment"), col("service_name"),
    ).agg(
        spark_sum("cost_usd").alias("total_cost_usd"),
        count("*").alias("resource_count"),
        avg("budget_consumed_pct").alias("avg_budget_consumed_pct"),
    )


# -------------------------------------------------------------------
# gold_database_capacity_alerts
# -------------------------------------------------------------------
@dlt.table(
    name="gold_database_capacity_alerts",
    schema=_ddl(
        ("source_lz_id",            "STRING",  "Landing zone identifier"),
        ("cloud_provider",          "STRING",  "Cloud platform"),
        # db_id remplace database_id
        ("db_id",                   "STRING",  "Database resource identifier"),
        ("db_name",                 "STRING",  "Database name"),
        ("db_type",                 "STRING",  "Database engine type"),
        ("server_name",             "STRING",  "Fully qualified server hostname"),
        ("region",                  "STRING",  "Cloud region"),
        ("cpu_percent",             "DOUBLE",  "Current CPU utilization pct"),
        ("memory_percent",          "DOUBLE",  "Current memory utilization pct"),
        # storage_used_gb remplace current_size_gb
        ("storage_used_gb",         "DOUBLE",  "Current storage used in GB"),
        ("storage_limit_gb",        "DOUBLE",  "Total allocated storage in GB"),
        ("available_space_gb",      "DOUBLE",  "Remaining available storage (limit - used)"),
        ("storage_utilization_pct", "DOUBLE",  "Storage utilization: used / limit * 100"),
        ("is_available",            "BOOLEAN", "Whether the database is currently available"),
        ("alert_level",             "STRING",  "Alert severity: CRITICAL (>90pct), WARNING (>80pct), OK"),
        ("_ingested_at",            "TIMESTAMP","Source ingestion timestamp"),
    ) + f", CONSTRAINT pk_gold_db_capacity PRIMARY KEY (source_lz_id, db_id)",
    comment="Database capacity alerts. Flags CRITICAL (>90pct) and WARNING (>80pct storage). Source: curated_database_metrics.",
    table_properties={"quality": "gold"},
)
def gold_database_capacity_alerts():
    databases = dlt.read("curated_database_metrics")
    with_calcs = databases.select(
        "*",
        # available_space_gb recalculé dynamiquement (absent du JSON réel)
        (col("storage_limit_gb") - col("storage_used_gb")).alias("available_space_gb"),
        spark_round((col("storage_used_gb") / col("storage_limit_gb")) * 100, 2).alias("storage_utilization_pct"),
    )
    return with_calcs.select(
        col("source_lz_id"), col("cloud_provider"),
        col("db_id"), col("db_name"), col("db_type"), col("server_name"), col("region"),
        col("cpu_percent"), col("memory_percent"),
        col("storage_used_gb"), col("storage_limit_gb"),
        col("available_space_gb"), col("storage_utilization_pct"),
        col("is_available"),
        when(col("storage_utilization_pct") > 90, lit("CRITICAL"))
        .when(col("storage_utilization_pct") > 80, lit("WARNING"))
        .otherwise(lit("OK")).alias("alert_level"),
        col("_ingested_at"),
    ).filter(col("storage_utilization_pct") > 80)


# -------------------------------------------------------------------
# gold_standard_check_score  (anciennement gold_compliance_score)
# -------------------------------------------------------------------
@dlt.table(
    name="gold_standard_check_score",
    schema=_ddl(
        ("source_lz_id",          "STRING", "Landing zone identifier"),
        ("cloud_provider",        "STRING", "Cloud platform"),
        ("environment",           "STRING", "Deployment environment"),
        ("owner_team",            "STRING", "Team responsible for the LZ"),
        ("evaluation_date",       "DATE",   "Date of check evaluation"),
        ("total_checks",          "LONG",   "Total number of checks performed"),
        ("compliant_count",       "LONG",   "Number of compliant evaluations"),
        ("non_compliant_count",   "LONG",   "Number of non-compliant evaluations"),
        ("compliance_score_pct",  "DOUBLE", "Score: compliant / total * 100"),
    ) + f", CONSTRAINT pk_gold_standard_check PRIMARY KEY (source_lz_id, cloud_provider, environment, owner_team, evaluation_date)",
    comment="Compliance/standard check scores by LZ, team, date. Source: curated_standard_checks.",
    table_properties={"quality": "gold"},
)
def gold_standard_check_score():
    checks = dlt.read("curated_standard_checks")
    lz_dim = dlt.read("dim_landing_zone_collector")
    enriched = checks.join(lz_dim, checks.source_lz_id == lz_dim.lz_id, "left")
    return enriched.groupBy(
        checks["source_lz_id"], checks["cloud_provider"],
        col("environment"), col("owner_team"),
        expr("date(evaluated_at)").alias("evaluation_date"),
    ).agg(
        count("*").alias("total_checks"),
        # snake_case dans les JSON réels : 'compliant' / 'non_compliant'
        count(when(col("check_state") == "compliant", 1)).alias("compliant_count"),
        count(when(col("check_state") == "non_compliant", 1)).alias("non_compliant_count"),
        spark_round(
            (count(when(col("check_state") == "compliant", 1)) / count("*")) * 100, 2
        ).alias("compliance_score_pct"),
    )


# -------------------------------------------------------------------
# gold_security_summary
# -------------------------------------------------------------------
@dlt.table(
    name="gold_security_summary",
    schema=_ddl(
        ("source_lz_id",         "STRING", "Landing zone identifier"),
        ("cloud_provider",       "STRING", "Cloud platform"),
        ("environment",          "STRING", "Deployment environment"),
        ("severity",             "STRING", "Alert severity level"),
        # status remplace remediation_status
        ("status",               "STRING", "Alert lifecycle status: active, in_progress, resolved, dismissed"),
        ("detection_date",       "DATE",   "Date when alerts were detected"),
        ("alert_count",          "LONG",   "Number of security alerts in this group"),
    ) + f", CONSTRAINT pk_gold_security PRIMARY KEY (source_lz_id, cloud_provider, environment, severity, status, detection_date)",
    comment="Security posture summary by severity, status, environment. Source: curated_security_alerts.",
    table_properties={"quality": "gold"},
)
def gold_security_summary():
    alerts = dlt.read("curated_security_alerts")
    lz_dim = dlt.read("dim_landing_zone_collector")
    enriched = alerts.join(lz_dim, alerts.source_lz_id == lz_dim.lz_id, "left")
    return enriched.groupBy(
        alerts["source_lz_id"], alerts["cloud_provider"],
        col("environment"), col("severity"),
        # status remplace remediation_status (champ JSON réel)
        col("status"),
        expr("date(detected_at)").alias("detection_date"),
    ).agg(
        count("*").alias("alert_count"),
    )


# -------------------------------------------------------------------
# gold_activity_performance
# -------------------------------------------------------------------
@dlt.table(
    name="gold_activity_performance",
    schema=_ddl(
        ("source_lz_id",           "STRING", "Landing zone identifier"),
        ("cloud_provider",         "STRING", "Cloud platform"),
        ("activity_type",          "STRING", "Type of pipeline activity"),
        ("status",                 "STRING", "Activity execution status"),
        ("total_runs",             "LONG",   "Total number of activity runs"),
        ("avg_duration_seconds",   "DOUBLE", "Average execution duration in seconds"),
        ("max_duration_seconds",   "DOUBLE", "Maximum execution duration in seconds"),
        # rows_read remplace input_rows
        ("avg_rows_read",          "DOUBLE", "Average number of rows read"),
        # rows_written remplace output_rows
        ("avg_rows_written",       "DOUBLE", "Average number of rows written"),
        ("avg_row_ratio",          "DOUBLE", "Average rows_written / rows_read ratio"),
        ("avg_data_read_bytes",    "DOUBLE", "Average bytes read per run"),
        ("avg_data_written_bytes", "DOUBLE", "Average bytes written per run"),
    ) + f", CONSTRAINT pk_gold_activity PRIMARY KEY (source_lz_id, cloud_provider, activity_type, status)",
    comment="Pipeline activity performance metrics. Source: curated_activity_runs.",
    table_properties={"quality": "gold"},
)
def gold_activity_performance():
    activities = dlt.read("curated_activity_runs")
    return activities.groupBy(
        col("source_lz_id"), col("cloud_provider"),
        col("activity_type"), col("status"),
    ).agg(
        count("*").alias("total_runs"),
        avg("duration_seconds").alias("avg_duration_seconds"),
        spark_max("duration_seconds").alias("max_duration_seconds"),
        # rows_read / rows_written (JSON réel) au lieu de input_rows / output_rows
        avg("rows_read").alias("avg_rows_read"),
        avg("rows_written").alias("avg_rows_written"),
        avg(when(col("rows_read") > 0, col("rows_written") / col("rows_read"))).alias("avg_row_ratio"),
        # Champs bytes (nouveaux dans le JSON réel)
        avg("data_read_bytes").alias("avg_data_read_bytes"),
        avg("data_written_bytes").alias("avg_data_written_bytes"),
    )


