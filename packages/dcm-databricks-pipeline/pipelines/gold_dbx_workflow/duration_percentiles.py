"""gold_dbx_workflow_duration_percentiles — duration + p50/p95/p99 + queued.

Portage fidele de `dlt_03_gold_layer.gold_dbx_workflow_duration_percentiles`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyspark.sql.functions import avg, col, count, current_timestamp, expr
from pyspark.sql.functions import max as spark_max

from pipelines.gold_dbx_workflow.bridges import build_wf_runs_bridge, build_wf_task_runs_bridge

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

__all__ = ["build_duration_percentiles"]


def build_duration_percentiles(
    spark: SparkSession,
    *,
    job_run_timeline_table: str,
    job_task_run_timeline_table: str,
    jobs_table: str,
    dim_dbx_workspace_table: str,
) -> DataFrame:
    task_runs_bridge = build_wf_task_runs_bridge(
        spark,
        job_task_run_timeline_table=job_task_run_timeline_table,
        jobs_table=jobs_table,
        job_run_timeline_table=job_run_timeline_table,
    )
    runs = build_wf_runs_bridge(
        spark,
        job_run_timeline_table=job_run_timeline_table,
        jobs_table=jobs_table,
        dim_dbx_workspace_table=dim_dbx_workspace_table,
        task_runs_bridge=task_runs_bridge,
    ).filter(col("duration_seconds").isNotNull())

    return (
        runs.groupBy(
            col("cloud_provider"), col("account_id"), col("workspace_id"),
            col("workflow_id"), col("workflow_name"),
            expr("date(start_time)").alias("execution_date"),
        ).agg(
            count("*").alias("total_runs"),
            avg("duration_seconds").alias("avg_duration_seconds"),
            expr("percentile_approx(duration_seconds, 0.5)").alias("p50_duration_seconds"),
            expr("percentile_approx(duration_seconds, 0.95)").alias("p95_duration_seconds"),
            expr("percentile_approx(duration_seconds, 0.99)").alias("p99_duration_seconds"),
            spark_max("duration_seconds").alias("max_duration_seconds"),
            avg("queued_duration_seconds").alias("avg_queued_duration_seconds"),
            avg("schedule_lag_seconds").alias("avg_schedule_lag_seconds"),
            spark_max("schedule_lag_seconds").alias("max_schedule_lag_seconds"),
            avg("retry_count").alias("avg_retry_count"),
        )
        .withColumn("_generated_at", current_timestamp())
    )
