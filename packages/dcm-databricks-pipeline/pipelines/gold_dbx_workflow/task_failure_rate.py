"""gold_dbx_workflow_task_failure_rate — taux d'echec des taches.

Portage fidele de `dlt_03_gold_layer.gold_dbx_workflow_task_failure_rate`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyspark.sql.functions import col, count, current_timestamp, expr, when
from pyspark.sql.functions import round as spark_round
from pyspark.sql.functions import sum as spark_sum

from pipelines.gold_dbx_workflow.bridges import build_wf_runs_bridge, build_wf_task_runs_bridge

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

__all__ = ["build_task_failure_rate"]


def build_task_failure_rate(
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
    ).filter(col("tasks_total").isNotNull() & (col("tasks_total") > 0))

    return (
        runs.groupBy(
            col("cloud_provider"), col("account_id"), col("workspace_id"),
            col("workflow_id"), col("workflow_name"),
            expr("date(start_time)").alias("execution_date"),
        ).agg(
            count("*").alias("runs_with_tasks"),
            spark_sum("tasks_total").alias("tasks_total"),
            spark_sum("tasks_failed").alias("tasks_failed"),
        )
        .withColumn(
            "task_failure_rate_pct",
            spark_round(
                when(col("tasks_total") > 0, 100.0 * col("tasks_failed") / col("tasks_total")),
                2,
            ),
        )
        .withColumn("_generated_at", current_timestamp())
    )
