"""gold_dbx_workflow_concurrency_1min — concurrent_runs_active (bucket 1 min).

Portage fidele de `dlt_03_gold_layer.gold_dbx_workflow_concurrency_1min` :
reconstruit la concurrence par recouvrement d'intervalles [start, end]
(deterministe, pas d'echantillonnage). Un run "running" (end_time NULL) est
prolonge jusqu'a l'instant courant.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyspark.sql.functions import coalesce, col, countDistinct, current_timestamp, explode, expr

from pipelines.gold_dbx_workflow.bridges import build_wf_runs_bridge, build_wf_task_runs_bridge

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

__all__ = ["build_concurrency_1min"]


def build_concurrency_1min(
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

    buckets = (
        runs
        .withColumn("_end_ts", coalesce(col("end_time"), current_timestamp()))
        .withColumn(
            "minute_bucket",
            explode(
                expr(
                    "sequence(date_trunc('minute', start_time), "
                    "date_trunc('minute', _end_ts), interval 1 minute)"
                )
            ),
        )
    )
    return (
        buckets.groupBy(
            col("cloud_provider"), col("account_id"), col("workspace_id"),
            col("minute_bucket"),
        ).agg(
            countDistinct("run_id").alias("concurrent_runs_active"),
        )
        .withColumn("_generated_at", current_timestamp())
    )
