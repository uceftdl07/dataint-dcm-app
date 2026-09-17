"""gold_dbx_workflow_duration_drift — derive vs moyenne mobile 14j.

Portage fidele de `dlt_03_gold_layer.gold_dbx_workflow_duration_drift`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyspark.sql.functions import avg, col, count, current_timestamp, expr, when
from pyspark.sql.functions import round as spark_round
from pyspark.sql.window import Window

from pipelines.gold_dbx_workflow.bridges import build_wf_runs_bridge, build_wf_task_runs_bridge

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

__all__ = ["build_duration_drift"]


def build_duration_drift(
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

    daily = runs.groupBy(
        col("cloud_provider"), col("account_id"), col("workspace_id"),
        col("workflow_id"), col("workflow_name"),
        expr("date(start_time)").alias("execution_date"),
    ).agg(
        count("*").alias("total_runs"),
        avg("duration_seconds").alias("avg_duration_seconds"),
    )
    w14 = (
        Window.partitionBy("cloud_provider", "account_id", "workspace_id", "workflow_id")
        .orderBy(col("execution_date"))
        .rowsBetween(-14, -1)
    )
    return (
        daily
        .withColumn("baseline_avg_14d", avg("avg_duration_seconds").over(w14))
        .withColumn(
            "duration_drift_pct",
            spark_round(
                when(
                    col("baseline_avg_14d") > 0,
                    100.0 * (col("avg_duration_seconds") - col("baseline_avg_14d"))
                    / col("baseline_avg_14d"),
                ),
                2,
            ),
        )
        .withColumn("_generated_at", current_timestamp())
    )
