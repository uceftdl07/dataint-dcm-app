"""Contrat d'agregation : registre des 9 tables gold workflow (epic 009).

Reutilise `GoldAggregationSpec` (dataclass generique definie dans
`pipelines.gold_dbx_compute.specs`) : meme mecanique que le domaine compute,
mais pour le domaine `workflow` (Databricks Workflows/Jobs), migre hors du
pipeline DLT (`dlt_03_gold_layer.py`, migration T002/013-workflow-sys-tables).

Toutes les specs ci-dessous ont `watermark_column=None` : comme les vues DLT
d'origine (`@dlt.table` sans fenetre), chaque table est un SNAPSHOT recalcule
INTEGRALEMENT a chaque run depuis les vues-pont (`pipelines.gold_dbx_workflow.
bridges`), elles-memes lisant la totalite de `curated_dbx_lakeflow_*` — il n'y
a jamais eu de fenetre incrementale sur ce domaine, y compris dans la version
DLT. Le garde-fou `SNAPSHOT_ABSENT_ROW_DELETE_GUARD` (partage avec les
snapshots `governance`/`*_rolling` du domaine compute) est active partout :
sans lui, un run absent d'un workflow supprime cote source (job supprime dans
Databricks) resterait indefiniment en gold.
"""

from __future__ import annotations

# Reutilise le contrat generique (`GoldAggregationSpec`) et le garde-fou snapshot
# partage : pas de redefinition, un seul point de verite pour la mecanique commune
# aux deux domaines gold (compute et workflow).
from pipelines.gold_dbx_compute.specs import (
    SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
    GoldAggregationSpec,
)
from pipelines.system_tables.specs import (
    CURATED_LAKEFLOW_JOB_RUN_TIMELINE,
    CURATED_LAKEFLOW_JOB_TASK_RUN_TIMELINE,
    CURATED_LAKEFLOW_JOBS,
    DEFAULT_CATALOG,
    DEFAULT_SCHEMA,
)

__all__ = [
    "DEFAULT_CATALOG",
    "DEFAULT_SCHEMA",
    "DIM_DBX_WORKSPACE_VIEW",
    "GOLD_SPECS",
    "GOLD_WF_CONCURRENCY_1MIN",
    "GOLD_WF_DURATION_DRIFT",
    "GOLD_WF_DURATION_PERCENTILES",
    "GOLD_WF_NEVER_RUN",
    "GOLD_WF_RUNS",
    "GOLD_WF_SUCCESS_RATE",
    "GOLD_WF_TASKS",
    "GOLD_WF_TASK_FAILURE_RATE",
    "GOLD_WF_TASK_HEALTH",
    "RUN_GRAIN_MERGE_KEYS",
    "SOURCE_TABLES",
    "WF_NEVER_RUN_MERGE_KEYS",
    "WF_RUNS_MERGE_KEYS",
    "WF_TASKS_MERGE_KEYS",
    "WF_TASK_HEALTH_MERGE_KEYS",
]

# Table dim non-DLT (`pipelines.gold_dbx_workspace`, deja standalone) utilisee par
# `_wf_runs_bridge` pour `workspace_name`/`workspace_url` — reimportee ici plutot
# que depuis `pipelines.gold_dbx_workspace.view` pour eviter un import circulaire
# de plugin a plugin (meme convention que `pipelines.system_tables.specs` pour les
# tables curated).
DIM_DBX_WORKSPACE_VIEW = "dim_dbx_workspace"

GOLD_WF_SUCCESS_RATE = "gold_dbx_workflow_success_rate"
GOLD_WF_DURATION_PERCENTILES = "gold_dbx_workflow_duration_percentiles"
GOLD_WF_DURATION_DRIFT = "gold_dbx_workflow_duration_drift"
GOLD_WF_TASK_FAILURE_RATE = "gold_dbx_workflow_task_failure_rate"
GOLD_WF_CONCURRENCY_1MIN = "gold_dbx_workflow_concurrency_1min"
GOLD_WF_TASK_HEALTH = "gold_dbx_workflow_task_health"
GOLD_WF_RUNS = "gold_dbx_workflow_runs"
GOLD_WF_TASKS = "gold_dbx_workflow_tasks"
GOLD_WF_NEVER_RUN = "gold_dbx_workflow_never_run"

# Grain (cloud, account, workspace, workflow, jour) — partage par les 4
# premieres tables (success_rate, duration_percentiles, duration_drift,
# task_failure_rate) : memes cles de merge, cf. contrat gold-workflow-contract.md.
RUN_GRAIN_MERGE_KEYS = (
    "cloud_provider", "account_id", "workspace_id", "workflow_id", "execution_date",
)

WF_TASK_HEALTH_MERGE_KEYS = (
    "cloud_provider", "account_id", "workspace_id",
    "workflow_id", "task_key", "execution_date",
)
WF_RUNS_MERGE_KEYS = (
    "cloud_provider", "account_id", "workspace_id", "workflow_id", "run_id",
)
WF_TASKS_MERGE_KEYS = (
    "cloud_provider", "account_id", "workspace_id", "workflow_id", "run_id", "task_id",
)

# Sources curated (system tables, T001) communes aux 8 builders (via les
# vues-pont) : declarees ici pour eviter toute redecouverte au niveau du
# builder — RAPPEL, ce sont les SEULES tables curated lues par ce domaine.
SOURCE_TABLES = (
    CURATED_LAKEFLOW_JOB_RUN_TIMELINE,
    CURATED_LAKEFLOW_JOB_TASK_RUN_TIMELINE,
    CURATED_LAKEFLOW_JOBS,
    DIM_DBX_WORKSPACE_VIEW,
)

_CONCURRENCY_MERGE_KEYS = ("cloud_provider", "account_id", "workspace_id", "minute_bucket")

_SUCCESS_RATE_COLUMN_COMMENTS = {
    "cloud_provider": "Cloud platform",
    "account_id": "Databricks account identifier",
    "workspace_id": "Databricks workspace GUID",
    "workflow_id": "Databricks job identifier",
    "workflow_name": "Workflow/job name; run name if API-submitted",
    "execution_date": "Day of the run (start_time)",
    "terminal_runs": "Runs that reached a terminal state that day",
    "succeeded_runs": "Runs with status = succeeded that day",
    "failed_runs": "Runs with status IN (failed, timed_out) that day",
    "cancelled_runs": "Runs with status = cancelled that day",
    "timed_out_runs": "Runs with status = timed_out that day",
    "success_rate_24h_pct": "Daily success rate = succeeded / terminal * 100",
    "success_rate_7d_pct": "7-day rolling success rate (current + 6 previous days)",
}
_SUCCESS_RATE_TABLE_COMMENT = (
    "Workflow run status & success rate (24h and 7d rolling). "
    "Source: _wf_runs_bridge (system.lakeflow.*)."
)
WF_SUCCESS_RATE_SPEC = GoldAggregationSpec(
    source_tables=SOURCE_TABLES,
    target_table=GOLD_WF_SUCCESS_RATE,
    merge_keys=RUN_GRAIN_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=_SUCCESS_RATE_COLUMN_COMMENTS,
    table_comment=_SUCCESS_RATE_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)

_DURATION_PERCENTILES_COLUMN_COMMENTS = {
    "cloud_provider": "Cloud platform",
    "account_id": "Databricks account identifier",
    "workspace_id": "Databricks workspace GUID",
    "workflow_id": "Databricks job identifier",
    "workflow_name": "Workflow/job name; run name if API-submitted",
    "execution_date": "Day of the run (start_time)",
    "total_runs": "Runs with a known duration that day",
    "avg_duration_seconds": "Mean run duration (s)",
    "p50_duration_seconds": "Median (p50) run duration (s)",
    "p95_duration_seconds": "p95 run duration (s)",
    "p99_duration_seconds": "p99 run duration (s)",
    "max_duration_seconds": "Max run duration (s)",
    "avg_queued_duration_seconds": (
        "Mean queued (wait) time before execution (s); NULL (no exploitable "
        "decomposition in system.lakeflow.job_run_timeline)"
    ),
    "avg_schedule_lag_seconds": "Mean scheduled-to-actual start lag (s); NULL (jobs sans cron)",
    "max_schedule_lag_seconds": "Worst scheduled-to-actual start lag (s); NULL (jobs sans cron)",
    "avg_retry_count": "Mean retry count (attempt_number)",
}
_DURATION_PERCENTILES_TABLE_COMMENT = (
    "Workflow duration percentiles (p50/p95/p99), queued time & retries. "
    "Source: _wf_runs_bridge (system.lakeflow.*)."
)
WF_DURATION_PERCENTILES_SPEC = GoldAggregationSpec(
    source_tables=SOURCE_TABLES,
    target_table=GOLD_WF_DURATION_PERCENTILES,
    merge_keys=RUN_GRAIN_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=_DURATION_PERCENTILES_COLUMN_COMMENTS,
    table_comment=_DURATION_PERCENTILES_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)

_DURATION_DRIFT_COLUMN_COMMENTS = {
    "cloud_provider": "Cloud platform",
    "account_id": "Databricks account identifier",
    "workspace_id": "Databricks workspace GUID",
    "workflow_id": "Databricks job identifier",
    "workflow_name": "Workflow/job name; run name if API-submitted",
    "execution_date": "Day of the run (start_time)",
    "total_runs": "Runs with a known duration that day",
    "avg_duration_seconds": "Mean run duration that day (s)",
    "baseline_avg_14d": (
        "14-day trailing moving average of daily mean duration (excludes current day)"
    ),
    "duration_drift_pct": "(avg_duration - baseline_14d) / baseline_14d * 100",
}
_DURATION_DRIFT_TABLE_COMMENT = (
    "Workflow duration drift vs 14-day moving average. Source: _wf_runs_bridge "
    "(system.lakeflow.*)."
)
WF_DURATION_DRIFT_SPEC = GoldAggregationSpec(
    source_tables=SOURCE_TABLES,
    target_table=GOLD_WF_DURATION_DRIFT,
    merge_keys=RUN_GRAIN_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=_DURATION_DRIFT_COLUMN_COMMENTS,
    table_comment=_DURATION_DRIFT_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)

_TASK_FAILURE_RATE_COLUMN_COMMENTS = {
    "cloud_provider": "Cloud platform",
    "account_id": "Databricks account identifier",
    "workspace_id": "Databricks workspace GUID",
    "workflow_id": "Databricks job identifier",
    "workflow_name": "Workflow/job name; run name if API-submitted",
    "execution_date": "Day of the run (start_time)",
    "runs_with_tasks": "Runs that reported task counts that day",
    "tasks_total": "Sum of tasks across runs that day",
    "tasks_failed": "Sum of failed tasks across runs that day",
    "task_failure_rate_pct": "tasks_failed / tasks_total * 100",
}
_TASK_FAILURE_RATE_TABLE_COMMENT = (
    "Workflow task-level failure rate. Source: _wf_runs_bridge (system.lakeflow.*)."
)
WF_TASK_FAILURE_RATE_SPEC = GoldAggregationSpec(
    source_tables=SOURCE_TABLES,
    target_table=GOLD_WF_TASK_FAILURE_RATE,
    merge_keys=RUN_GRAIN_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=_TASK_FAILURE_RATE_COLUMN_COMMENTS,
    table_comment=_TASK_FAILURE_RATE_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)

_CONCURRENCY_COLUMN_COMMENTS = {
    "cloud_provider": "Cloud platform",
    "account_id": "Databricks account identifier",
    "workspace_id": "Databricks workspace GUID",
    "minute_bucket": "Minute (truncated) time bucket",
    "concurrent_runs_active": "Distinct runs active during that minute",
}
_CONCURRENCY_TABLE_COMMENT = (
    "Active concurrent workflow runs per 1-minute bucket (interval overlap). "
    "Source: _wf_runs_bridge (system.lakeflow.*)."
)
WF_CONCURRENCY_1MIN_SPEC = GoldAggregationSpec(
    source_tables=SOURCE_TABLES,
    target_table=GOLD_WF_CONCURRENCY_1MIN,
    merge_keys=_CONCURRENCY_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=_CONCURRENCY_COLUMN_COMMENTS,
    table_comment=_CONCURRENCY_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)

_TASK_HEALTH_COLUMN_COMMENTS = {
    "cloud_provider": "Cloud platform",
    "account_id": "Databricks account identifier",
    "workspace_id": "Databricks workspace GUID",
    "workflow_id": "Databricks job identifier",
    "workflow_name": "Workflow/job name; run name if API-submitted",
    "task_key": "Stable task name within the job",
    "execution_date": "Day of the task run (start_time)",
    "total_task_runs": "Distinct task runs (task_id) that day",
    "failed_task_runs": "Task runs that failed/timed-out/errored that day",
    "task_failure_rate_pct": "failed_task_runs / total_task_runs * 100",
    "avg_task_duration_seconds": "Mean task duration that day",
    "p95_task_duration_seconds": "95th-percentile task duration that day",
}
_TASK_HEALTH_TABLE_COMMENT = (
    "Per-task workflow health (failure rate & duration). "
    "Source: _wf_task_runs_bridge (system.lakeflow.*)."
)
WF_TASK_HEALTH_SPEC = GoldAggregationSpec(
    source_tables=SOURCE_TABLES,
    target_table=GOLD_WF_TASK_HEALTH,
    merge_keys=WF_TASK_HEALTH_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=_TASK_HEALTH_COLUMN_COMMENTS,
    table_comment=_TASK_HEALTH_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)

_RUNS_COLUMN_COMMENTS = {
    "cloud_provider": "Cloud platform",
    "account_id": "Databricks account identifier",
    "workspace_id": "Databricks workspace GUID",
    "workspace_name": "Databricks workspace ARM resource name; NULL (not exposed by lakeflow)",
    "workflow_id": "Databricks job identifier",
    "workflow_name": "Workflow/job name; run name if API-submitted",
    "run_id": "Unique Databricks run identifier",
    "execution_date": "Day of the run (start_time); filter/join key with aggregates",
    "status": "succeeded, failed, running, cancelled, queued, timed_out, skipped",
    "trigger_type": "Databricks trigger: periodic, one_time, retry, file_arrival, ...",
    "run_type": "JOB_RUN, WORKFLOW_RUN, or SUBMIT_RUN",
    "start_time": "Run start timestamp",
    "end_time": "Run end timestamp; NULL if still running",
    "duration_seconds": "Wall-clock run duration in seconds",
    "queued_duration_seconds": (
        "Time queued before execution; NULL (pas de decomposition exploitable)"
    ),
    "execution_duration_seconds": "Task execution time; NULL (idem)",
    "schedule_lag_seconds": "Scheduled-to-actual start lag; NULL (jobs sans cron)",
    "retry_count": "Retry count (attempt_number; 0 = first attempt)",
    "tasks_total": "Total tasks in the run; NULL if not expanded",
    "tasks_failed": "Failed/timed-out/errored tasks in the run",
    "task_failure_rate": "Per-run tasks_failed / tasks_total; NULL if unavailable",
    "creator_user_name": "Principal that owns/created the job",
    "cluster_instance_id": "Cluster used by the run (FinOps join key)",
    "run_page_url": "Databricks UI URL for the run",
    "error_message": "State/error message on failure; NULL otherwise",
}
_RUNS_TABLE_COMMENT = (
    "Per-run workflow detail for drill-down (grain: run_id). "
    "Source: _wf_runs_bridge (system.lakeflow.*)."
)
WF_RUNS_SPEC = GoldAggregationSpec(
    source_tables=SOURCE_TABLES,
    target_table=GOLD_WF_RUNS,
    merge_keys=WF_RUNS_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=_RUNS_COLUMN_COMMENTS,
    table_comment=_RUNS_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)

_TASKS_COLUMN_COMMENTS = {
    "cloud_provider": "Cloud platform",
    "account_id": "Databricks account identifier",
    "workspace_id": "Databricks workspace GUID",
    "workspace_name": "Databricks workspace ARM resource name; NULL (not exposed by lakeflow)",
    "workflow_id": "Parent Databricks job identifier",
    "workflow_name": "Parent workflow/job name; run name if API-submitted",
    "run_id": "Parent Databricks run identifier (= job_run_id)",
    "task_id": "Task-level run identifier (globally unique)",
    "task_key": "Stable task name within the job",
    "execution_date": "Day of the task run (start_time)",
    "status": "succeeded, failed, running, cancelled, queued, timed_out, skipped",
    "start_time": "Task start timestamp; NULL if unknown",
    "end_time": "Task end timestamp; NULL if still running",
    "duration_seconds": "Task wall-clock duration in seconds",
    "attempt_number": "Task attempt number (0 = first attempt)",
    "cluster_instance_id": "Cluster used by the task (FinOps join key)",
    "error_message": "Task state/error message on failure; NULL otherwise",
}
_TASKS_TABLE_COMMENT = (
    "Per-task workflow detail for drill-down (grain: task_id). "
    "Source: _wf_task_runs_bridge (system.lakeflow.*)."
)
WF_TASKS_SPEC = GoldAggregationSpec(
    source_tables=SOURCE_TABLES,
    target_table=GOLD_WF_TASKS,
    merge_keys=WF_TASKS_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=_TASKS_COLUMN_COMMENTS,
    table_comment=_TASKS_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)

# Cle propre (grain job, pas run/jour) : un job "jamais execute" n'a ni run_id
# ni execution_date a porter dans une cle de merge.
WF_NEVER_RUN_MERGE_KEYS = ("cloud_provider", "account_id", "workspace_id", "workflow_id")

_NEVER_RUN_COLUMN_COMMENTS = {
    "cloud_provider": "Cloud platform",
    "account_id": "Databricks account identifier",
    "workspace_id": "Databricks workspace GUID",
    "workflow_id": "Databricks job identifier",
    "workflow_name": "Job definition name (curated_dbx_lakeflow_jobs.name)",
    "last_definition_change_time": "Last known modification time of the job definition",
    "runs_observed_since": (
        "Earliest period_start_time available in curated_dbx_lakeflow_job_run_timeline "
        "at computation time -- NOT the job creation date. A job whose only run(s) "
        "happened before this date also appears here (see builder docstring)."
    ),
}
_NEVER_RUN_TABLE_COMMENT = (
    "Active (non-deleted) job definitions with zero rows in "
    "curated_dbx_lakeflow_job_run_timeline since runs_observed_since -- i.e. no run "
    "observed in DCM's ingestion window, not necessarily never run since creation. "
    "Source: curated_dbx_lakeflow_jobs anti-joined with curated_dbx_lakeflow_job_run_timeline."
)
WF_NEVER_RUN_SPEC = GoldAggregationSpec(
    source_tables=(CURATED_LAKEFLOW_JOBS, CURATED_LAKEFLOW_JOB_RUN_TIMELINE),
    target_table=GOLD_WF_NEVER_RUN,
    merge_keys=WF_NEVER_RUN_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=_NEVER_RUN_COLUMN_COMMENTS,
    table_comment=_NEVER_RUN_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)

# Registre de dispatch (cle utilisee par `--table` du `python_wheel_task`, cf.
# `pipelines.gold_dbx_workflow.entrypoint`). Ajouter une table = ajouter une
# entree ici, ne jamais modifier les entrees existantes.
GOLD_SPECS: dict[str, GoldAggregationSpec] = {
    "success_rate": WF_SUCCESS_RATE_SPEC,
    "duration_percentiles": WF_DURATION_PERCENTILES_SPEC,
    "duration_drift": WF_DURATION_DRIFT_SPEC,
    "task_failure_rate": WF_TASK_FAILURE_RATE_SPEC,
    "concurrency_1min": WF_CONCURRENCY_1MIN_SPEC,
    "task_health": WF_TASK_HEALTH_SPEC,
    "runs": WF_RUNS_SPEC,
    "tasks": WF_TASKS_SPEC,
    "never_run": WF_NEVER_RUN_SPEC,
}
