"""Vues-pont (ex-`@dlt.view` DLT) reconstruisant le grain run/tache workflow.

Portage FIDELE de `_wf_runs_bridge`/`_wf_task_runs_bridge`
(`pipelines/dlt_03_gold_layer.py`, migration T002/013-workflow-sys-tables) :
memes lectures (`curated_dbx_lakeflow_job_run_timeline`,
`curated_dbx_lakeflow_job_task_run_timeline`, `curated_dbx_lakeflow_jobs`,
`dim_dbx_workspace`), meme logique de calcul (GROUP BY, jamais un
`qualify row_number()` qui fausserait `start_time`), memes noms de colonnes en
sortie.

SEULE difference structurelle avec la version DLT : ce ne sont plus des
`@dlt.view` (jamais materialisees, recalculees par le moteur DLT dans le meme
graphe) mais des fonctions Python pures retournant un `DataFrame` -- chaque
tache `python_wheel_task` qui en a besoin les recalcule a la volee (meme cout
que les tables `*_rolling` de `gold_dbx_compute` qui relisent leur `*_daily`
source a chaque run). `_wf_runs_bridge` appelait `dlt.read("_wf_task_runs_bridge")`
(lecture intra-graphe DLT) : remplace ici par un appel de fonction direct
(`build_wf_task_runs_bridge(...)`), le seul changement non trivial du portage.

RAPPEL SOURCE (cf. `pipelines.gold_dbx_workflow.__init__`) : ces deux fonctions
lisent EXCLUSIVEMENT `curated_dbx_lakeflow_*` (system tables), jamais
`curated_dbx_workflow_runs`/`curated_dbx_workflow_task_runs` (collecteur JSON).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyspark.sql.functions import (
    coalesce,
    col,
    countDistinct,
    expr,
    lit,
)
from pyspark.sql.functions import max as spark_max
from pyspark.sql.functions import min as spark_min
from pyspark.sql.functions import sum as spark_sum
from pyspark.sql.window import Window

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

__all__ = ["build_wf_runs_bridge", "build_wf_task_runs_bridge"]


def _run_page_url_sql() -> str:
    return (
        "concat(regexp_replace(_workspace_url, '/+$', ''), "
        "'/?o=', workspace_id, '#job/', job_id, '/run/', run_id)"
    )


def _latest_jobs(spark: SparkSession, jobs_table: str) -> DataFrame:
    """1 ligne par job (derniere version non supprimee) de `curated_dbx_lakeflow_jobs`.

    Portage fidele de `dlt_03_gold_layer._lakeflow_latest_jobs` -- dedup
    obligatoire (table SCD, sinon fan-out constate en dev jusqu'a x43, cf.
    docstring d'origine).
    """
    jobs = spark.read.table(jobs_table).filter(col("delete_time").isNull())
    latest_window = Window.partitionBy(
        "cloud_provider", "account_id", "workspace_id", "job_id",
    ).orderBy(col("change_time").desc())
    return (
        jobs.withColumn("_rn", expr("row_number()").over(latest_window))
        .filter(col("_rn") == 1)
        .drop("_rn")
    )


def _submit_run_names(spark: SparkSession, job_run_timeline_table: str) -> DataFrame:
    """1 ligne par job portant un nom de RUN (repli pour les runs SOUMIS par API).

    Portage fidele de `dlt_03_gold_layer._lakeflow_submit_run_names`.
    """
    return spark.read.table(job_run_timeline_table).filter(
        col("run_name").isNotNull(),
    ).groupBy(
        col("cloud_provider"), col("account_id"), col("workspace_id"), col("job_id"),
    ).agg(spark_max("run_name").alias("run_name"))


def build_wf_task_runs_bridge(
    spark: SparkSession,
    *,
    job_task_run_timeline_table: str,
    jobs_table: str,
    job_run_timeline_table: str,
) -> DataFrame:
    """Reconstruit 1 ligne par EXECUTION DE TACHE (portage de `_wf_task_runs_bridge`).

    IMPORTANT (schema officiel Databricks) : sur
    `curated_dbx_lakeflow_job_task_run_timeline`, `run_id` designe l'ID
    D'EXECUTION DE LA TACHE (pas le run parent, expose via `job_run_id`).
    """
    tasks_agg = spark.read.table(job_task_run_timeline_table).groupBy(
        col("cloud_provider"), col("account_id"), col("workspace_id"),
        col("job_id"), col("job_run_id"), col("run_id"), col("task_key"),
    ).agg(
        spark_min("period_start_time").alias("start_time"),
        expr(
            "CASE WHEN bool_and(period_end_time IS NOT NULL) "
            "THEN max(period_end_time) END"
        ).alias("end_time"),
        expr("max_by(result_state, period_start_time)").alias("final_result_state"),
        expr("max_by(termination_code, period_start_time)").alias("final_termination_code"),
        expr("max_by(compute_ids, period_start_time)").alias("compute_ids"),
    )

    jobs_names = _latest_jobs(spark, jobs_table).select(
        col("cloud_provider"), col("account_id"), col("workspace_id"),
        col("job_id"), col("name").alias("workflow_name"),
    )

    # `curated_dbx_lakeflow_job_task_run_timeline` NE PORTE PAS `run_name` : le
    # nom des runs soumis vient d'une lecture de `job_run_timeline` au grain job.
    submit_names = _submit_run_names(spark, job_run_timeline_table)

    with_job = tasks_agg.join(
        jobs_names,
        on=["cloud_provider", "account_id", "workspace_id", "job_id"],
        how="left",
    ).join(
        submit_names,
        on=["cloud_provider", "account_id", "workspace_id", "job_id"],
        how="left",
    )

    attempt_window = (
        Window.partitionBy(
            "cloud_provider", "account_id", "workspace_id",
            "job_id", "job_run_id", "task_key",
        ).orderBy(col("start_time"))
    )

    return (
        with_job
        .withColumn("workflow_name", coalesce(col("workflow_name"), col("run_name")))
        .withColumn(
            "status",
            expr(
                "CASE "
                "WHEN final_result_state = 'SUCCEEDED' THEN 'succeeded' "
                "WHEN final_result_state = 'FAILED' THEN 'failed' "
                "WHEN final_result_state IN ('CANCELLED','CANCELED') THEN 'cancelled' "
                "WHEN final_result_state = 'TIMED_OUT' THEN 'timed_out' "
                "WHEN final_result_state IN "
                "('SKIPPED','EXCLUDED','UPSTREAM_FAILED','UPSTREAM_CANCELED') THEN 'skipped' "
                "WHEN final_result_state IS NULL AND end_time IS NULL THEN 'running' "
                "ELSE 'queued' END"
            ),
        )
        .withColumn(
            "duration_seconds",
            expr(
                "CASE WHEN end_time IS NOT NULL "
                "THEN unix_timestamp(end_time) - unix_timestamp(start_time) END"
            ).cast("double"),
        )
        .withColumn("attempt_number", (expr("row_number()").over(attempt_window) - 1))
        # `try_element_at` et non `element_at` (identique en DLT, cf. historique
        # git) : hors DLT, le job serverless applique le mode ANSI, ou
        # `element_at(compute_ids, 1)` leve `INVALID_ARRAY_INDEX` des que
        # `compute_ids` est un tableau VIDE (pas NULL) -- observe en dev sur ce
        # domaine. `try_element_at` retourne NULL dans ce cas, comportement
        # identique a celui que DLT produisait implicitement (ANSI desactive).
        .withColumn("cluster_instance_id", expr("try_element_at(compute_ids, 1)"))
        .withColumn("error_message", col("final_termination_code"))
        .select(
            col("cloud_provider"), col("account_id"), col("workspace_id"),
            col("job_id"), col("job_run_id"), col("workflow_name"),
            col("run_id").alias("task_id"), col("task_key"),
            col("status"), col("start_time"), col("end_time"),
            col("duration_seconds"), col("attempt_number"),
            col("cluster_instance_id"), col("error_message"),
        )
    )


def build_wf_runs_bridge(
    spark: SparkSession,
    *,
    job_run_timeline_table: str,
    jobs_table: str,
    dim_dbx_workspace_table: str,
    task_runs_bridge: DataFrame,
) -> DataFrame:
    """Reconstruit 1 ligne par RUN (portage de `_wf_runs_bridge`).

    `task_runs_bridge` : DataFrame deja calcule par `build_wf_task_runs_bridge`
    (appele UNE fois par l'appelant, transmis ici) -- remplace
    `dlt.read("_wf_task_runs_bridge")` de la version DLT (lecture intra-graphe,
    inexistante hors DLT).
    """
    runs_agg = spark.read.table(job_run_timeline_table).groupBy(
        col("cloud_provider"), col("account_id"), col("workspace_id"),
        col("job_id"), col("run_id"),
    ).agg(
        spark_min("period_start_time").alias("start_time"),
        expr(
            "CASE WHEN bool_and(period_end_time IS NOT NULL) "
            "THEN max(period_end_time) END"
        ).alias("end_time"),
        expr("max_by(result_state, period_start_time)").alias("final_result_state"),
        expr("max_by(termination_code, period_start_time)").alias("final_termination_code"),
        expr("max_by(trigger_type, period_start_time)").alias("trigger_type_raw"),
        expr("max_by(run_type, period_start_time)").alias("run_type"),
        expr("max_by(compute_ids, period_start_time)").alias("compute_ids"),
        spark_max("run_name").alias("run_name"),
    )

    jobs_names = _latest_jobs(spark, jobs_table).select(
        col("cloud_provider"), col("account_id"), col("workspace_id"),
        col("job_id"), col("name").alias("workflow_name"),
        col("tags"), col("creator_user_name"),
    )

    with_job = runs_agg.join(
        jobs_names,
        on=["cloud_provider", "account_id", "workspace_id", "job_id"],
        how="left",
    )

    workspace_metadata = spark.read.table(dim_dbx_workspace_table).select(
        col("cloud").alias("_workspace_cloud_provider"),
        col("workspace_id").alias("_workspace_id"),
        col("workspace_name").alias("_workspace_name"),
        col("workspace_url").alias("_workspace_url"),
    )
    with_workspace = with_job.join(
        workspace_metadata,
        (col("cloud_provider") == col("_workspace_cloud_provider"))
        & (col("workspace_id") == col("_workspace_id")),
        how="left",
    )

    tasks_summary = (
        task_runs_bridge
        .groupBy(
            col("cloud_provider"), col("account_id"), col("workspace_id"),
            col("job_id"), col("job_run_id"),
        )
        .agg(
            countDistinct("task_id").alias("tasks_total"),
            spark_sum(
                expr("CASE WHEN status IN ('failed','timed_out','cancelled') THEN 1 ELSE 0 END")
            ).alias("tasks_failed"),
            spark_max("attempt_number").alias("max_attempt_number"),
        )
        .select(
            col("cloud_provider").alias("_ts_cloud_provider"),
            col("account_id").alias("_ts_account_id"),
            col("workspace_id").alias("_ts_workspace_id"),
            col("job_id").alias("_ts_job_id"),
            col("job_run_id").alias("_ts_job_run_id"),
            col("tasks_total"), col("tasks_failed"), col("max_attempt_number"),
        )
    )

    with_tasks = with_workspace.join(
        tasks_summary,
        (col("cloud_provider") == col("_ts_cloud_provider"))
        & (col("account_id") == col("_ts_account_id"))
        & (col("workspace_id") == col("_ts_workspace_id"))
        & (col("job_id") == col("_ts_job_id"))
        & (col("run_id") == col("_ts_job_run_id")),
        how="left",
    )

    return (
        with_tasks
        .withColumn("workflow_name", coalesce(col("workflow_name"), col("run_name")))
        .withColumn(
            "status",
            expr(
                "CASE "
                "WHEN final_result_state = 'SUCCEEDED' THEN 'succeeded' "
                "WHEN final_result_state = 'FAILED' THEN 'failed' "
                "WHEN final_result_state IN ('CANCELLED','CANCELED') THEN 'cancelled' "
                "WHEN final_result_state = 'TIMED_OUT' THEN 'timed_out' "
                "WHEN final_result_state IN "
                "('SKIPPED','EXCLUDED','UPSTREAM_FAILED','UPSTREAM_CANCELED') THEN 'skipped' "
                "WHEN final_result_state IS NULL AND end_time IS NULL THEN 'running' "
                "ELSE 'queued' END"
            ),
        )
        .withColumn(
            "trigger_type",
            expr(
                "CASE "
                "WHEN trigger_type_raw IN ('PERIODIC','SCHEDULED') THEN 'scheduled' "
                "WHEN trigger_type_raw IN ('ONE_TIME','MANUAL') THEN 'manual' "
                "WHEN trigger_type_raw = 'RETRY' THEN 'retry' "
                "WHEN trigger_type_raw = 'RUN_JOB_TASK' THEN 'run_job_task' "
                "WHEN trigger_type_raw = 'FILE_ARRIVAL' THEN 'file_arrival' "
                "WHEN trigger_type_raw = 'CONTINUOUS' THEN 'continuous' "
                "WHEN trigger_type_raw IN ('TABLE','TABLE_UPDATE') THEN 'table_update' "
                "ELSE 'unknown' END"
            ),
        )
        .withColumn(
            "duration_seconds",
            expr(
                "CASE WHEN end_time IS NOT NULL "
                "THEN unix_timestamp(end_time) - unix_timestamp(start_time) END"
            ).cast("double"),
        )
        .withColumn(
            "cluster_instance_id",
            # cf. `build_wf_task_runs_bridge` : `try_element_at` (pas
            # `element_at`, identique en DLT) evite `INVALID_ARRAY_INDEX` en
            # mode ANSI quand `compute_ids` est un tableau VIDE.
            expr("try_element_at(compute_ids, 1)"),
        )
        .withColumn("run_page_url", expr(_run_page_url_sql()))
        .withColumn("error_message", col("final_termination_code"))
        .withColumn("retry_count", coalesce(col("max_attempt_number"), lit(0)).cast("int"))
        .withColumn("tasks_total", col("tasks_total").cast("int"))
        .withColumn("tasks_failed", coalesce(col("tasks_failed"), lit(0)).cast("int"))
        .withColumn(
            "task_failure_rate",
            expr("CASE WHEN tasks_total > 0 THEN tasks_failed / tasks_total END"),
        )
        .withColumn("workspace_name", col("_workspace_name"))
        .withColumn("queued_duration_seconds", lit(None).cast("double"))
        .withColumn("setup_duration_seconds", lit(None).cast("double"))
        .withColumn("execution_duration_seconds", lit(None).cast("double"))
        .withColumn("cleanup_duration_seconds", lit(None).cast("double"))
        .withColumn("schedule_lag_seconds", lit(None).cast("double"))
        .select(
            col("cloud_provider"), col("account_id"), col("workspace_id"),
            col("workspace_name"),
            col("job_id").alias("workflow_id"), col("workflow_name"),
            col("run_id"),
            col("status"), col("trigger_type"), col("run_type"),
            col("start_time"), col("end_time"), col("duration_seconds"),
            col("queued_duration_seconds"), col("setup_duration_seconds"),
            col("execution_duration_seconds"), col("cleanup_duration_seconds"),
            col("schedule_lag_seconds"),
            col("retry_count"), col("tasks_total"), col("tasks_failed"),
            col("task_failure_rate"),
            col("cluster_instance_id"), col("creator_user_name"),
            col("run_page_url"), col("error_message"), col("tags"),
        )
    )
