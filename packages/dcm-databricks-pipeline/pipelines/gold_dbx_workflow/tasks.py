"""gold_dbx_workflow_tasks — detail par TACHE (drill-down, epic 009 addendum).

Grain : 1 ligne = 1 execution de tache (task_id). Projection task-grain de
`_wf_task_runs_bridge`, exposee en GOLD pour le drill-down UI d'un run vers
ses taches. Portage fidele de `dlt_03_gold_layer.gold_dbx_workflow_tasks`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyspark.sql.functions import col, current_timestamp, expr, lit

from pipelines.gold_dbx_workflow.bridges import build_wf_task_runs_bridge

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

__all__ = ["build_tasks"]


def build_tasks(
    spark: SparkSession,
    *,
    job_run_timeline_table: str,
    job_task_run_timeline_table: str,
    jobs_table: str,
) -> DataFrame:
    tasks = build_wf_task_runs_bridge(
        spark,
        job_task_run_timeline_table=job_task_run_timeline_table,
        jobs_table=jobs_table,
        job_run_timeline_table=job_run_timeline_table,
    ).filter(col("start_time").isNotNull())

    return tasks.select(
        col("cloud_provider"),
        col("account_id"),
        col("workspace_id"),
        lit(None).cast("string").alias("workspace_name"),
        col("job_id").alias("workflow_id"),
        col("workflow_name"),
        col("job_run_id").alias("run_id"),
        col("task_id"),
        col("task_key"),
        expr("date(start_time)").alias("execution_date"),
        col("status"),
        col("start_time"),
        col("end_time"),
        col("duration_seconds"),
        col("attempt_number"),
        col("cluster_instance_id"),
        col("error_message"),
        current_timestamp().alias("_generated_at"),
    )
