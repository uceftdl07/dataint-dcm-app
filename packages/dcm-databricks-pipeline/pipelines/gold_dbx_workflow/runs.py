"""gold_dbx_workflow_runs — detail par RUN (drill-down, epic 009 addendum).

Grain : 1 ligne = 1 run (run_id). Projection run-grain de `_wf_runs_bridge`,
exposee en GOLD pour le drill-down UI vers un run precis. Portage fidele de
`dlt_03_gold_layer.gold_dbx_workflow_runs`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyspark.sql.functions import col, current_timestamp, expr

from pipelines.gold_dbx_workflow.bridges import build_wf_runs_bridge, build_wf_task_runs_bridge

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

__all__ = ["build_runs"]


def build_runs(
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
    ).filter(col("start_time").isNotNull())

    return runs.select(
        col("cloud_provider"),
        col("account_id"),
        col("workspace_id"),
        col("workspace_name"),
        col("workflow_id"),
        col("workflow_name"),
        col("run_id"),
        expr("date(start_time)").alias("execution_date"),
        col("status"),
        col("trigger_type"),
        col("run_type"),
        col("start_time"),
        col("end_time"),
        col("duration_seconds"),
        col("queued_duration_seconds"),
        col("execution_duration_seconds"),
        col("schedule_lag_seconds"),
        col("retry_count"),
        col("tasks_total"),
        col("tasks_failed"),
        col("task_failure_rate"),
        col("creator_user_name"),
        col("cluster_instance_id"),
        col("run_page_url"),
        col("error_message"),
        current_timestamp().alias("_generated_at"),
    )
