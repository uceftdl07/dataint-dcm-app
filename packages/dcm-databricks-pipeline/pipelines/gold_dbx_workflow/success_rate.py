"""gold_dbx_workflow_success_rate — run_status + success_rate 24h & 7j.

Portage fidele de `dlt_03_gold_layer.gold_dbx_workflow_success_rate` (memes
agregations/fenetres) : seule difference, la source n'est plus `dlt.read(
"_wf_runs_bridge")` mais un appel direct a `bridges.build_wf_runs_bridge`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyspark.sql.functions import col, count, current_timestamp, expr, when
from pyspark.sql.functions import round as spark_round
from pyspark.sql.functions import sum as spark_sum
from pyspark.sql.window import Window

from pipelines.gold_dbx_workflow.bridges import build_wf_runs_bridge, build_wf_task_runs_bridge

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

__all__ = ["build_success_rate"]


def build_success_rate(
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
    ).filter(col("status").isin("succeeded", "failed", "cancelled", "timed_out", "skipped"))

    daily = runs.groupBy(
        col("cloud_provider"), col("account_id"), col("workspace_id"),
        col("workflow_id"), col("workflow_name"),
        expr("date(start_time)").alias("execution_date"),
    ).agg(
        count("*").alias("terminal_runs"),
        count(when(col("status") == "succeeded", 1)).alias("succeeded_runs"),
        count(when(col("status").isin("failed", "timed_out"), 1)).alias("failed_runs"),
        count(when(col("status") == "cancelled", 1)).alias("cancelled_runs"),
        count(when(col("status") == "timed_out", 1)).alias("timed_out_runs"),
    )
    w7 = (
        Window.partitionBy("cloud_provider", "account_id", "workspace_id", "workflow_id")
        .orderBy(col("execution_date"))
        .rowsBetween(-6, 0)
    )
    return (
        daily
        .withColumn("succeeded_7d", spark_sum("succeeded_runs").over(w7))
        .withColumn("terminal_7d", spark_sum("terminal_runs").over(w7))
        .withColumn(
            "success_rate_24h_pct",
            spark_round(
                when(
                    col("terminal_runs") > 0,
                    100.0 * col("succeeded_runs") / col("terminal_runs"),
                ),
                2,
            ),
        )
        .withColumn(
            "success_rate_7d_pct",
            spark_round(
                when(col("terminal_7d") > 0, 100.0 * col("succeeded_7d") / col("terminal_7d")),
                2,
            ),
        )
        .withColumn("_generated_at", current_timestamp())
        .select(
            "cloud_provider", "account_id", "workspace_id", "workflow_id",
            "workflow_name", "execution_date", "terminal_runs", "succeeded_runs",
            "failed_runs", "cancelled_runs", "timed_out_runs",
            "success_rate_24h_pct", "success_rate_7d_pct", "_generated_at",
        )
    )
