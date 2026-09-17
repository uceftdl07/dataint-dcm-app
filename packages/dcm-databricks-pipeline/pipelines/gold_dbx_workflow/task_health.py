"""gold_dbx_workflow_task_health — sante par TACHE (epic 009 addendum).

Grain : (cloud, account, workspace, workflow_id, task_key, jour). Source : le
fait task-grain `_wf_task_runs_bridge` (task_id). Portage fidele de
`dlt_03_gold_layer.gold_dbx_workflow_task_health`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyspark.sql.functions import col, countDistinct, current_timestamp, expr, when
from pyspark.sql.functions import round as spark_round
from pyspark.sql.functions import sum as spark_sum

from pipelines.gold_dbx_workflow.bridges import build_wf_task_runs_bridge

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

__all__ = ["build_task_health"]


def build_task_health(
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
    ).filter(col("task_key").isNotNull() & col("start_time").isNotNull())

    return (
        tasks.groupBy(
            col("cloud_provider"), col("account_id"), col("workspace_id"),
            col("job_id").alias("workflow_id"), col("workflow_name"), col("task_key"),
            expr("date(start_time)").alias("execution_date"),
        ).agg(
            countDistinct("task_id").alias("total_task_runs"),
            spark_sum(
                expr(
                    "CASE WHEN status IN ('failed','timed_out','cancelled') THEN 1 ELSE 0 END"
                )
            ).alias("failed_task_runs"),
            spark_round(expr("avg(duration_seconds)"), 2).alias("avg_task_duration_seconds"),
            spark_round(
                expr("percentile_approx(duration_seconds, 0.95)"), 2
            ).alias("p95_task_duration_seconds"),
        )
        .withColumn(
            "task_failure_rate_pct",
            spark_round(
                when(
                    col("total_task_runs") > 0,
                    100.0 * col("failed_task_runs") / col("total_task_runs"),
                ),
                2,
            ),
        )
        .withColumn("_generated_at", current_timestamp())
    )
