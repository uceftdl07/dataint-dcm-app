"""Databricks Workflows run observability metrics (epic 009 — domain ``workflow``).

Produced by:
    - ``azure_collector.collectors.databricks_workflows.DatabricksWorkflowCollector``

Stored in Lakebase / Delta under the ``workflow`` domain
(``curated_dbx_workflow_runs`` + GOLD aggregates).

Each ``WorkflowRunMetric`` is a single **raw** snapshot of one Databricks
Workflow (Job/Pipeline) run. The collector emits one record per run — including
runs still in progress — and performs **no aggregation**. Derived KPIs
(success_rate 24h/7d, duration percentiles p50/p95/p99, duration_drift_pct over
a 14-day moving average, task_failure_rate, concurrent_runs_active 1-min
sampling, FinOps cost per cluster/pipeline/job/run) are computed downstream in
the Databricks DLT pipeline from these raw facts.

Design note — why a dedicated model instead of extending ``PipelineMetric``
--------------------------------------------------------------------------
``PipelineMetric`` is shared by ADF, Glue and EMR. Adding Databricks-specific
fields (``tasks_total``, ``tasks_failed``, ``schedule_lag_seconds``,
``retry_count``, ``cluster_instance_id`` …) would pollute it and its aggregates.
The ``workflow`` domain isolates the Databricks run lifecycle end to end.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, computed_field, model_validator

from dcm_commons.models.base_metric import BaseMetricModel
from dcm_commons.models.enums import WorkflowRunStatus, WorkflowTriggerType

__all__ = ["WorkflowRunMetric", "WorkflowTaskRun"]


class WorkflowTaskRun(BaseMetricModel):
    """Raw metrics for a single **task** execution within a Databricks run.

    A Databricks Job/Pipeline run (``run_id``) is composed of one or more tasks.
    Each task exposes its own globally-unique task-level run identifier
    (``task_id``) and a stable name within the job (``task_key``). This nested
    model isolates the **task grain** so the DLT pipeline can materialise a
    dedicated task fact (``curated_dbx_workflow_task_runs``) and per-task health
    aggregates without duplicating run-level measures onto every task row.

    Populated only when the Databricks Jobs API returns per-task states
    (``expand_tasks=true``). Durations are in **seconds**; a value the source
    does not expose is left ``None`` (never defaulted to ``0``).

    Attributes:
        task_id:             Task-level run identifier (``tasks[].run_id``) —
                             globally unique, dedup key at task grain.
        task_key:            Stable task name within the job (``tasks[].task_key``).
        status:              Task outcome / lifecycle at collection time.
        start_time:          UTC timestamp when the task started; ``None`` if unknown.
        end_time:            UTC timestamp when the task finished; ``None`` while running.
        duration_seconds:    Task wall-clock duration in seconds.
        attempt_number:      Task attempt number (0 for the first attempt).
        cluster_instance_id: Cluster used by the task (FinOps join key).
        error_message:       Task state/error message on failure (max 2 000 chars).
    """

    task_id: str = Field(..., description="Task-level run identifier (tasks[].run_id).")
    task_key: str | None = Field(
        default=None,
        description="Stable task name within the job (tasks[].task_key).",
    )
    status: WorkflowRunStatus
    start_time: datetime | None = Field(
        default=None,
        description="UTC timestamp when the task started; None if unknown.",
    )
    end_time: datetime | None = Field(
        default=None,
        description="UTC timestamp when the task finished; None while running.",
    )
    duration_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Task wall-clock duration in seconds.",
    )
    attempt_number: int = Field(
        default=0,
        ge=0,
        description="Task attempt number (0 = first attempt).",
    )
    cluster_instance_id: str | None = Field(
        default=None,
        description="Cluster used by the task; join key for FinOps cost attribution.",
    )
    error_message: str | None = Field(
        default=None,
        description="Task state/error message on failure (max 2 000 characters).",
    )

    @model_validator(mode="before")
    @classmethod
    def _derive_task_duration(cls, data: Any) -> Any:
        """Auto-compute ``duration_seconds`` from ``start_time`` / ``end_time``."""
        if not isinstance(data, dict):
            return data
        if data.get("duration_seconds") is not None:
            return data
        start = data.get("start_time")
        end = data.get("end_time")
        if isinstance(start, datetime) and isinstance(end, datetime) and end >= start:
            data = {**data, "duration_seconds": (end - start).total_seconds()}
        return data


class WorkflowRunMetric(BaseMetricModel):
    """Raw metrics for a single Databricks Workflow (Job/Pipeline) run.

    All duration fields are expressed in **seconds**. When the source API does
    not expose a value it is left ``None`` (never defaulted to ``0``) so the
    downstream pipeline can distinguish "not available" from "zero" — see the
    repository rule *"jamais de donnée fictive"*.

    Attributes:
        workflow_id:            Databricks job identifier (``job_id``).
        workflow_name:          Human-readable job/workflow name (``run_name``).
        run_id:                 Unique Databricks run identifier (``run_id``).
        workspace_id:           Databricks workspace GUID.
        workspace_name:         Azure ARM resource name of the workspace.
        status:                 Run outcome / lifecycle at collection time
                                (incl. ``timed_out``).
        trigger_type:           Databricks-native trigger classification.
        start_time:             UTC timestamp when the run started.
        end_time:               UTC timestamp when the run finished; ``None`` while running.
        duration_seconds:       Wall-clock run duration in seconds. Uses the API
                                ``run_duration`` when present, else derived from
                                ``start_time`` / ``end_time``.
        queued_duration_seconds:   Time spent queued before execution (``queue_duration``).
        setup_duration_seconds:    Cluster setup time (``setup_duration``).
        execution_duration_seconds: Task execution time (``execution_duration``) —
                                used downstream for FinOps cost attribution.
        cleanup_duration_seconds:  Cluster teardown time (``cleanup_duration``).
        retry_count:            Number of retries for this run (``attempt_number``;
                                0 for the first attempt).
        tasks_total:            Number of tasks in the run (requires ``expand_tasks``).
        tasks_failed:           Number of tasks that failed / timed out / errored.
        schedule_lag_seconds:   Delay between the scheduled trigger time and the
                                actual start; ``None`` when the source does not
                                expose a scheduled time.
        cluster_instance_id:    Cluster used by the run (``cluster_instance.cluster_id``).
                                Join key for FinOps cost attribution per cluster/run.
        creator_user_name:      Principal that owns/created the job.
        run_page_url:           Databricks UI URL for the run (troubleshooting/UI).
        run_type:               Databricks run type
                                (``JOB_RUN`` / ``WORKFLOW_RUN`` / ``SUBMIT_RUN``).
        error_message:          Provider error/state message on failure (max 2 000 chars).
        tags:                   Provider-supplied resource tags.
    """

    # --- Identity ---
    workflow_id: str = Field(..., description="Databricks job identifier (job_id).")
    workflow_name: str = Field(..., description="Human-readable workflow/job name.")
    run_id: str = Field(..., description="Unique Databricks run identifier.")
    workspace_id: str | None = Field(
        default=None,
        description="Databricks workspace GUID.",
    )
    workspace_name: str | None = Field(
        default=None,
        description="Azure ARM resource name of the Databricks workspace.",
    )

    # --- Outcome ---
    status: WorkflowRunStatus
    trigger_type: WorkflowTriggerType = Field(
        default=WorkflowTriggerType.UNKNOWN,
        description="Databricks-native trigger classification.",
    )

    # --- Timing ---
    start_time: datetime = Field(..., description="UTC timestamp when the run started.")
    end_time: datetime | None = Field(
        default=None,
        description="UTC timestamp when the run finished; None while running.",
    )
    duration_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Wall-clock run duration in seconds.",
    )
    queued_duration_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Time spent queued before execution, in seconds.",
    )
    setup_duration_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Cluster setup time, in seconds.",
    )
    execution_duration_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Task execution time, in seconds (used for FinOps cost attribution).",
    )
    cleanup_duration_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Cluster teardown time, in seconds.",
    )
    schedule_lag_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Delay between scheduled trigger and actual start; None if unavailable.",
    )

    # --- Reliability ---
    retry_count: int = Field(
        default=0,
        ge=0,
        description="Number of retries for this run (attempt_number; 0 = first attempt).",
    )
    tasks_total: int | None = Field(
        default=None,
        ge=0,
        description="Total number of tasks in the run (requires expand_tasks).",
    )
    tasks_failed: int | None = Field(
        default=None,
        ge=0,
        description="Number of tasks that failed / timed out / errored.",
    )

    # --- FinOps linkage ---
    cluster_instance_id: str | None = Field(
        default=None,
        description="Cluster used by the run; join key for FinOps cost attribution.",
    )
    creator_user_name: str | None = Field(
        default=None,
        description="Principal that owns/created the job.",
    )
    run_page_url: str | None = Field(
        default=None,
        description="Databricks UI URL for the run.",
    )
    run_type: str | None = Field(
        default=None,
        description="Databricks run type (JOB_RUN / WORKFLOW_RUN / SUBMIT_RUN).",
    )

    # --- Diagnostics ---
    error_message: str | None = Field(
        default=None,
        description="Provider error/state message on failure (max 2 000 characters).",
    )
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Provider-supplied resource tags.",
    )

    # --- Task grain (epic 009 addendum) ---
    tasks: list[WorkflowTaskRun] = Field(
        default_factory=list,
        description=(
            "Per-task executions within this run (populated when expand_tasks=true). "
            "Exploded downstream into curated_dbx_workflow_task_runs (task grain)."
        ),
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @model_validator(mode="before")
    @classmethod
    def _derive_duration(cls, data: Any) -> Any:
        """Auto-compute ``duration_seconds`` from ``start_time`` / ``end_time``.

        Only applies when ``duration_seconds`` is absent and both timestamps are
        already parsed ``datetime`` objects (model built from Python objects).
        """
        if not isinstance(data, dict):
            return data
        if data.get("duration_seconds") is not None:
            return data

        start = data.get("start_time")
        end = data.get("end_time")
        if isinstance(start, datetime) and isinstance(end, datetime) and end >= start:
            data = {**data, "duration_seconds": (end - start).total_seconds()}
        return data

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------

    @computed_field  # type: ignore[prop-decorator]
    @property
    def task_failure_rate(self) -> float | None:
        """Per-run task failure ratio in ``[0.0, 1.0]``.

        ``None`` when task counts are unavailable (``expand_tasks`` disabled or
        a run with zero tasks). The DLT pipeline aggregates these per-run ratios
        into ``gold_dbx_workflow_task_failure_rate``.
        """
        if self.tasks_total is None or self.tasks_failed is None or self.tasks_total == 0:
            return None
        return self.tasks_failed / self.tasks_total
