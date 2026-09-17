"""Azure Databricks Workflows collector — run observability metrics (epic 009).

Enumerates all Databricks workspaces in the subscription (Azure Management REST
API), then calls the Databricks **Jobs 2.2** REST API per workspace with
``expand_tasks=true`` to retrieve rich per-run facts required by the DCM
observability KPIs.

Difference with :class:`DatabricksPipelineCollector`
----------------------------------------------------
``DatabricksPipelineCollector`` feeds the legacy ``pipeline`` domain with a
minimal :class:`PipelineMetric`. This collector feeds the dedicated
``workflow`` domain with :class:`WorkflowRunMetric`, capturing the extra raw
signals the DLT pipeline needs to compute:

- run_status (incl. ``timed_out``)
- duration_seconds, queued/setup/execution/cleanup durations
- retry_count (``attempt_number``)
- tasks_total / tasks_failed (per-run task failure rate)
- schedule_lag_seconds (actual start − previous cron fire, for periodic runs)
- cluster_instance_id (FinOps cost attribution join key)

The collector performs **no aggregation** — success_rate 24h/7d, duration
percentiles p50/p95/p99, duration_drift_pct (14-day moving average),
concurrent_runs_active (1-min sampling) and FinOps cost are all derived
downstream in the Databricks DLT pipeline.

Key API calls
-------------
``GET management.azure.com/.../Microsoft.Databricks/workspaces``
    List all Databricks workspace ARM resources in the subscription.
``GET https://{workspace_url}/api/2.2/jobs/runs/list?expand_tasks=true``
    List job runs within a single workspace (cursor pagination).

Target domain
-------------
``workflow`` (:class:`~dcm_commons.models.workflow.WorkflowRunMetric`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from azure.identity import DefaultAzureCredential  # type: ignore[import-untyped]
import httpx

try:  # croniter is optional; schedule_lag falls back to None when unavailable.
    from croniter import croniter  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - exercised only when dep missing
    croniter = None  # type: ignore[assignment]

from azure_collector._azure_utils import get_databricks_token, get_mgmt_token
from azure_collector.collectors.databricks_pipelines import _list_workspaces
from dcm_commons.collectors.base import BaseCollector
from dcm_commons.exceptions import CollectionError
from dcm_commons.logging_utils import LogMarker, get_logger, log_line
from dcm_commons.models.enums import (
    CloudProvider,
    MetricDomain,
    WorkflowRunStatus,
    WorkflowTriggerType,
)
from dcm_commons.models.workflow import WorkflowRunMetric, WorkflowTaskRun

__all__ = ["DatabricksWorkflowCollector"]

_logger = get_logger(__name__)

_REQUEST_TIMEOUT = 30.0
_PAGE_LIMIT = 25
_MAX_PAGES = 40  # safety bound: up to 1000 runs / workspace / cycle

# Databricks ``result_state`` → DCM WorkflowRunStatus.
_RESULT_STATE_MAP: dict[str, WorkflowRunStatus] = {
    "SUCCESS": WorkflowRunStatus.SUCCEEDED,
    "SUCCESS_WITH_FAILURES": WorkflowRunStatus.FAILED,
    "FAILED": WorkflowRunStatus.FAILED,
    "INTERNAL_ERROR": WorkflowRunStatus.FAILED,
    "UPSTREAM_FAILED": WorkflowRunStatus.FAILED,
    "TIMEDOUT": WorkflowRunStatus.TIMED_OUT,
    "TIMED_OUT": WorkflowRunStatus.TIMED_OUT,
    "CANCELED": WorkflowRunStatus.CANCELLED,
    "CANCELLED": WorkflowRunStatus.CANCELLED,
    "UPSTREAM_CANCELED": WorkflowRunStatus.CANCELLED,
    "EXCLUDED": WorkflowRunStatus.SKIPPED,
    "MAXIMUM_CONCURRENT_RUNS_REACHED": WorkflowRunStatus.SKIPPED,
}

# Databricks ``life_cycle_state`` → DCM WorkflowRunStatus (used when no result_state yet).
_LIFECYCLE_STATE_MAP: dict[str, WorkflowRunStatus] = {
    "PENDING": WorkflowRunStatus.QUEUED,
    "QUEUED": WorkflowRunStatus.QUEUED,
    "BLOCKED": WorkflowRunStatus.QUEUED,
    "RUNNING": WorkflowRunStatus.RUNNING,
    "TERMINATING": WorkflowRunStatus.RUNNING,
    "WAITING_FOR_RETRY": WorkflowRunStatus.RUNNING,
    "SKIPPED": WorkflowRunStatus.SKIPPED,
}

# Databricks 2.2 ``status.state`` (new lifecycle) → DCM WorkflowRunStatus.
_STATUS_STATE_MAP: dict[str, WorkflowRunStatus] = {
    "BLOCKED": WorkflowRunStatus.QUEUED,
    "PENDING": WorkflowRunStatus.QUEUED,
    "QUEUED": WorkflowRunStatus.QUEUED,
    "RUNNING": WorkflowRunStatus.RUNNING,
    "TERMINATING": WorkflowRunStatus.RUNNING,
}

# Databricks 2.2 ``status.termination_details.code`` → DCM WorkflowRunStatus.
_TERMINATION_CODE_MAP: dict[str, WorkflowRunStatus] = {
    "SUCCESS": WorkflowRunStatus.SUCCEEDED,
    "CANCELED": WorkflowRunStatus.CANCELLED,
    "USER_CANCELED": WorkflowRunStatus.CANCELLED,
    "RUN_EXECUTION_ERROR": WorkflowRunStatus.FAILED,
    "INTERNAL_ERROR": WorkflowRunStatus.FAILED,
    "DRIVER_ERROR": WorkflowRunStatus.FAILED,
    "CLUSTER_ERROR": WorkflowRunStatus.FAILED,
    "MAX_JOB_QUEUE_SIZE_EXCEEDED": WorkflowRunStatus.SKIPPED,
    "SKIPPED": WorkflowRunStatus.SKIPPED,
    "MAX_CONCURRENT_RUNS_EXCEEDED": WorkflowRunStatus.SKIPPED,
    "RUN_TIMEOUT": WorkflowRunStatus.TIMED_OUT,
    "TIMEOUT": WorkflowRunStatus.TIMED_OUT,
}

# Databricks ``trigger`` → DCM WorkflowTriggerType.
_TRIGGER_MAP: dict[str, WorkflowTriggerType] = {
    "PERIODIC": WorkflowTriggerType.PERIODIC,
    "ONE_TIME": WorkflowTriggerType.ONE_TIME,
    "RETRY": WorkflowTriggerType.RETRY,
    "RUN_JOB_TASK": WorkflowTriggerType.RUN_JOB_TASK,
    "FILE_ARRIVAL": WorkflowTriggerType.FILE_ARRIVAL,
    "TABLE": WorkflowTriggerType.TABLE_UPDATE,
    "TABLE_UPDATE": WorkflowTriggerType.TABLE_UPDATE,
    "CONTINUOUS": WorkflowTriggerType.CONTINUOUS,
    "MANUAL": WorkflowTriggerType.MANUAL,
}

# Databricks task ``result_state`` values considered a task failure.
_FAILED_TASK_STATES = frozenset(
    {
        "FAILED",
        "TIMEDOUT",
        "TIMED_OUT",
        "CANCELED",
        "CANCELLED",
        "UPSTREAM_FAILED",
        "INTERNAL_ERROR",
    }
)


class DatabricksWorkflowCollector(BaseCollector):
    """Collect Databricks Workflow run observability metrics (domain ``workflow``).

    Args:
        source_lz_id:    Landing zone identifier.
        subscription_id: Azure subscription ID.
        credential:      ``azure.identity`` credential. Defaults to ``DefaultAzureCredential``.
        max_retries:     Retry attempts on transient ``CollectionError``.
        retry_base_delay_seconds: Base delay for exponential back-off.
        lookback_hours:  Hours of run history to fetch (default 24, per FR-021).
    """

    def __init__(
        self,
        source_lz_id: str,
        subscription_id: str,
        *,
        credential: Any | None = None,
        max_retries: int = 3,
        retry_base_delay_seconds: float = 2.0,
        lookback_hours: int = 24,
    ) -> None:
        super().__init__(
            source_lz_id=source_lz_id,
            cloud_provider=CloudProvider.AZURE,
            subscription_or_account_id=subscription_id,
            max_retries=max_retries,
            retry_base_delay_seconds=retry_base_delay_seconds,
        )
        self._subscription_id = subscription_id
        self._credential = credential or DefaultAzureCredential()
        self._lookback_hours = lookback_hours

    @property
    def domain(self) -> MetricDomain:
        """Return the workflow metric domain."""
        return MetricDomain.WORKFLOW

    async def _collect_metrics(self) -> list[dict[str, Any]]:
        """Enumerate workspaces and collect Workflow run metrics from each one.

        Returns:
            List of :class:`WorkflowRunMetric` dicts (one per run, incl. running).

        Raises:
            CollectionError: If workspace listing fails.
        """
        _logger.info(
            "databricks_workflows_collect_starting",
            **log_line(
                LogMarker.START,
                f"DBX workflows — subscription {self._subscription_id}, "
                f"lookback {self._lookback_hours}h",
                subscription_id=self._subscription_id,
                lookback_hours=self._lookback_hours,
            ),
        )

        mgmt_token = await get_mgmt_token(self._credential)
        db_token = await get_databricks_token(self._credential)

        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as http:
            workspaces = await _list_workspaces(http, mgmt_token, self._subscription_id)

            if not workspaces:
                _logger.info(
                    "databricks_workflows_no_workspaces_found",
                    **log_line(LogMarker.WARN, "DBX workflows — no workspaces in subscription"),
                )
                return []

            _logger.info(
                "databricks_workflows_workspaces_found",
                **log_line(
                    LogMarker.OK,
                    f"DBX workflows — {len(workspaces)} workspace(s) found",
                    count=len(workspaces),
                ),
            )

            metrics: list[dict[str, Any]] = []
            for index, ws in enumerate(workspaces, start=1):
                workspace_url = ws.get("workspace_url", "")
                workspace_id = ws.get("workspace_id", "")
                workspace_name = ws.get("name", "")

                if not workspace_url:
                    _logger.warning(
                        "databricks_workflows_workspace_no_url",
                        **log_line(
                            LogMarker.WARN,
                            f"DBX workflows [{index}/{len(workspaces)}] "
                            f"{workspace_name} — missing workspace URL",
                            workspace_name=workspace_name,
                        ),
                    )
                    continue

                try:
                    runs = await _list_workflow_runs(
                        http,
                        db_token,
                        workspace_url,
                        lookback_hours=self._lookback_hours,
                    )
                except Exception as exc:
                    _logger.warning(
                        "databricks_workflows_runs_list_failed",
                        **log_line(
                            LogMarker.FAIL,
                            f"DBX workflows {workspace_name} — runs/list denied or failed: {exc}",
                            workspace=workspace_name,
                            reason=str(exc),
                        ),
                    )
                    continue

                schedules = await _list_job_schedules(http, db_token, workspace_url)

                _logger.info(
                    "databricks_workflows_runs_list_done",
                    **log_line(
                        LogMarker.OK if runs else LogMarker.WARN,
                        f"DBX workflows {workspace_name} — {len(runs)} run(s) in lookback window",
                        workspace=workspace_name,
                        run_count=len(runs),
                        scheduled_jobs=len(schedules),
                    ),
                )

                for run in runs:
                    metric = _map_run_to_metric(
                        run,
                        workspace_id=workspace_id,
                        workspace_name=workspace_name,
                        schedules=schedules,
                    )
                    if metric is not None:
                        metrics.append(metric.model_dump())

            _logger.info(
                "databricks_workflows_collection_done",
                **log_line(
                    LogMarker.OK if metrics else LogMarker.WARN,
                    f"DBX workflows done — {len(metrics)} run metric(s) "
                    f"from {len(workspaces)} workspace(s)",
                    workspace_count=len(workspaces),
                    metric_count=len(metrics),
                ),
            )
            return metrics


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _list_job_schedules(
    http: httpx.AsyncClient,
    db_token: str,
    workspace_url: str,
) -> dict[str, dict[str, str]]:
    """Return ``{job_id: {"quartz_cron_expression", "timezone_id", "pause_status"}}``.

    Reads the cron schedule of every job in the workspace via Jobs REST API 2.2
    ``jobs/list``. Only jobs that expose a ``schedule`` block are included; the
    map is used to derive ``schedule_lag_seconds`` for periodic runs. Failures
    are swallowed (returns whatever was collected) so a missing scope never
    breaks run collection.
    """
    base = workspace_url if workspace_url.startswith("https://") else f"https://{workspace_url}"
    url = f"{base}/api/2.2/jobs/list"

    schedules: dict[str, dict[str, str]] = {}
    page_token: str | None = None

    for _ in range(_MAX_PAGES):
        params: dict[str, Any] = {"limit": 100, "expand_tasks": "false"}
        if page_token:
            params["page_token"] = page_token

        try:
            response = await http.get(
                url,
                headers={"Authorization": f"Bearer {db_token}"},
                params=params,
            )
        except httpx.RequestError:
            break
        if not response.is_success:
            break

        body = response.json()
        for job in body.get("jobs", []):
            job_id = str(job.get("job_id", ""))
            settings = job.get("settings") if isinstance(job.get("settings"), dict) else {}
            schedule = settings.get("schedule") if isinstance(settings, dict) else None
            if not job_id or not isinstance(schedule, dict):
                continue
            cron = schedule.get("quartz_cron_expression")
            if not cron:
                continue
            schedules[job_id] = {
                "quartz_cron_expression": str(cron),
                "timezone_id": str(schedule.get("timezone_id") or "UTC"),
                "pause_status": str(schedule.get("pause_status") or "UNPAUSED"),
            }

        page_token = body.get("next_page_token")
        if not page_token or not body.get("has_more"):
            break

    return schedules


def _normalize_quartz(expr: str) -> str | None:
    """Adapt a Databricks quartz cron to a croniter-compatible expression.

    Databricks uses ``sec min hour day-of-month month day-of-week [year]`` with
    ``?`` placeholders. croniter wants 6 fields (seconds first) and ``*`` in
    place of ``?``. Returns ``None`` when the expression cannot be adapted.
    """
    parts = expr.split()
    if len(parts) == 7:  # drop the optional trailing year field
        parts = parts[:6]
    if len(parts) != 6:
        return None
    return " ".join("*" if field == "?" else field for field in parts)


def _previous_fire(cron: str, timezone_id: str, at: datetime) -> datetime | None:
    """Compute the most recent scheduled fire time at/before ``at`` (tz-aware).

    Evaluates the cron in its own timezone (DST-aware via ``zoneinfo``) and
    returns a UTC-comparable ``datetime``. Returns ``None`` on any parse error.
    """
    if croniter is None:
        return None
    normalized = _normalize_quartz(cron)
    if normalized is None:
        return None
    try:
        tz = ZoneInfo(timezone_id)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        tz = UTC
    try:
        base = at.astimezone(tz)
        return croniter(normalized, base, second_at_beginning=True).get_prev(datetime)
    except (ValueError, KeyError, TypeError):
        return None


def _compute_schedule_lag(
    run: dict[str, Any],
    start_time: datetime,
    schedules: dict[str, dict[str, str]],
) -> float | None:
    """Derive ``schedule_lag_seconds`` = actual start − scheduled fire time.

    Only meaningful for periodic (cron-scheduled) runs whose job schedule is
    known. Returns ``None`` for ad-hoc/manual runs or when the cron is
    unavailable/unparseable. Negative results (clock skew) collapse to ``0``.
    """
    if _parse_trigger(run) is not WorkflowTriggerType.PERIODIC:
        return None
    schedule = schedules.get(str(run.get("job_id", "")))
    if not schedule:
        return None
    prev = _previous_fire(
        schedule["quartz_cron_expression"],
        schedule.get("timezone_id", "UTC"),
        start_time,
    )
    if prev is None:
        return None
    lag = (start_time - prev).total_seconds()
    return round(max(lag, 0.0), 3)


async def _list_workflow_runs(
    http: httpx.AsyncClient,
    db_token: str,
    workspace_url: str,
    lookback_hours: int = 24,
) -> list[dict[str, Any]]:
    """Retrieve recent Workflow runs from a workspace via Jobs REST API 2.2.

    Uses ``expand_tasks=true`` to include per-task states (needed for
    ``tasks_total`` / ``tasks_failed``) and follows cursor pagination.

    Args:
        http:           Shared ``httpx.AsyncClient``.
        db_token:       Databricks-scoped bearer token.
        workspace_url:  Workspace hostname.
        lookback_hours: How many hours back to fetch runs.

    Returns:
        List of raw run dicts from the Databricks API.

    Raises:
        CollectionError: On network or API errors.
    """
    base = workspace_url if workspace_url.startswith("https://") else f"https://{workspace_url}"
    url = f"{base}/api/2.2/jobs/runs/list"

    now = datetime.now(UTC)
    start_time_from = int((now.timestamp() * 1000) - int(lookback_hours * 3600 * 1000))

    runs: list[dict[str, Any]] = []
    page_token: str | None = None

    for _ in range(_MAX_PAGES):
        params: dict[str, Any] = {
            "expand_tasks": "true",
            "start_time_from": start_time_from,
            "limit": _PAGE_LIMIT,
        }
        if page_token:
            params["page_token"] = page_token

        try:
            response = await http.get(
                url,
                headers={"Authorization": f"Bearer {db_token}"},
                params=params,
            )
        except httpx.RequestError as exc:
            raise CollectionError(
                "DatabricksWorkflowCollector",
                f"Network error calling Databricks jobs/runs/list on {workspace_url}: {exc}",
            ) from exc

        if not response.is_success:
            raise CollectionError(
                "DatabricksWorkflowCollector",
                f"Databricks jobs/runs/list returned HTTP {response.status_code} "
                f"on {workspace_url}: {response.text[:200]}",
            )

        body = response.json()
        runs.extend(body.get("runs", []))

        page_token = body.get("next_page_token")
        if not page_token or not body.get("has_more"):
            break

    return runs


def _parse_run_state(run: dict[str, Any]) -> tuple[WorkflowRunStatus, str]:
    """Normalize a Databricks run state to a :class:`WorkflowRunStatus`.

    Handles three payload shapes:
    - legacy ``state`` object (``life_cycle_state`` + ``result_state``),
    - legacy ``state`` string,
    - new 2.2 ``status`` object (``state`` + ``termination_details.code``).
    """
    raw_state = run.get("state")
    message = str(run.get("state_message", ""))

    if isinstance(raw_state, dict):
        lifecycle = str(raw_state.get("life_cycle_state", "")).upper()
        result = str(raw_state.get("result_state", "")).upper()
        message = str(raw_state.get("state_message", message))

        if lifecycle in ("PENDING", "QUEUED", "BLOCKED"):
            return WorkflowRunStatus.QUEUED, message
        if lifecycle in ("RUNNING", "TERMINATING", "WAITING_FOR_RETRY"):
            return WorkflowRunStatus.RUNNING, message
        if result:
            return _RESULT_STATE_MAP.get(result, WorkflowRunStatus.RUNNING), message
        if lifecycle:
            return _LIFECYCLE_STATE_MAP.get(lifecycle, WorkflowRunStatus.RUNNING), message

    if isinstance(raw_state, str) and raw_state:
        return _RESULT_STATE_MAP.get(raw_state.upper(), WorkflowRunStatus.RUNNING), message

    status = run.get("status")
    if isinstance(status, dict):
        state = str(status.get("state", "")).upper()
        details = status.get("termination_details") or {}
        code = str(details.get("code", "")).upper() if isinstance(details, dict) else ""
        message = str(details.get("message", message)) if isinstance(details, dict) else message

        if state in ("BLOCKED", "PENDING", "QUEUED"):
            return WorkflowRunStatus.QUEUED, message
        if state == "RUNNING":
            return WorkflowRunStatus.RUNNING, message
        if code:
            return _TERMINATION_CODE_MAP.get(code, WorkflowRunStatus.FAILED), message
        if state == "TERMINATING":
            return WorkflowRunStatus.RUNNING, message

    return WorkflowRunStatus.RUNNING, message


def _parse_trigger(run: dict[str, Any]) -> WorkflowTriggerType:
    """Map the Databricks ``trigger`` field to a :class:`WorkflowTriggerType`."""
    trigger = run.get("trigger")
    if not trigger and isinstance(run.get("trigger_info"), dict):
        trigger = run["trigger_info"].get("trigger_type")
    if not isinstance(trigger, str) or not trigger:
        return WorkflowTriggerType.UNKNOWN
    return _TRIGGER_MAP.get(trigger.upper(), WorkflowTriggerType.UNKNOWN)


def _ms_to_seconds(value: object) -> float | None:
    """Convert a Databricks duration in milliseconds to seconds; ``None`` if absent/zero-unknown."""
    if not isinstance(value, (int, float)):
        return None
    if value <= 0:
        return None
    return round(value / 1000.0, 3)


def _epoch_ms_to_dt(value: object) -> datetime | None:
    """Convert a Databricks epoch-millisecond timestamp to a UTC ``datetime``."""
    if not isinstance(value, (int, float)) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value / 1000.0, tz=UTC)
    except (OSError, OverflowError, ValueError):
        return None


def _count_task_failures(run: dict[str, Any]) -> tuple[int | None, int | None]:
    """Return ``(tasks_total, tasks_failed)`` from an expanded run, or ``(None, None)``.

    Only populated when the API returned per-task states (``expand_tasks=true``).
    """
    tasks = run.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return None, None

    failed = 0
    for task in tasks:
        if not isinstance(task, dict):
            continue
        state = task.get("state")
        result = ""
        if isinstance(state, dict):
            result = str(state.get("result_state", "")).upper()
        if not result:
            status = task.get("status")
            if isinstance(status, dict):
                details = status.get("termination_details")
                if isinstance(details, dict):
                    result = str(details.get("code", "")).upper()
        if result in _FAILED_TASK_STATES:
            failed += 1

    return len(tasks), failed


def _map_tasks(run: dict[str, Any]) -> list[WorkflowTaskRun]:
    """Map an expanded run's ``tasks[]`` to a list of :class:`WorkflowTaskRun`.

    Each task exposes a globally-unique task-level ``run_id`` (mapped to
    ``task_id``) and a stable ``task_key``. Tasks lacking a ``run_id`` are
    skipped. Returns an empty list when the API did not expand tasks
    (``expand_tasks`` off) — run-level ``tasks_total`` / ``tasks_failed`` remain
    the source of truth for those runs.
    """
    tasks = run.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return []

    mapped: list[WorkflowTaskRun] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("run_id", ""))
        if not task_id:
            continue

        status, state_message = _parse_run_state(task)

        start_time = _epoch_ms_to_dt(task.get("start_time"))
        end_time = _epoch_ms_to_dt(task.get("end_time"))

        duration_seconds = _ms_to_seconds(task.get("execution_duration"))
        if (
            duration_seconds is None
            and start_time is not None
            and end_time is not None
            and end_time >= start_time
        ):
            duration_seconds = (end_time - start_time).total_seconds()

        cluster_instance = task.get("cluster_instance")
        cluster_instance_id = None
        if isinstance(cluster_instance, dict):
            cluster_instance_id = cluster_instance.get("cluster_id") or None

        attempt_number = task.get("attempt_number")
        attempt = int(attempt_number) if isinstance(attempt_number, (int, float)) else 0

        mapped.append(
            WorkflowTaskRun(
                task_id=task_id,
                task_key=task.get("task_key") or None,
                status=status,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration_seconds,
                attempt_number=max(attempt, 0),
                cluster_instance_id=cluster_instance_id,
                error_message=state_message[:2000] if state_message else None,
            )
        )

    return mapped


def _map_run_to_metric(
    run: dict[str, Any],
    workspace_id: str,
    workspace_name: str = "",
    schedules: dict[str, dict[str, str]] | None = None,
) -> WorkflowRunMetric | None:
    """Map a Databricks run dict to a :class:`WorkflowRunMetric`.

    ``schedules`` maps ``job_id`` to its cron schedule and is used to compute
    ``schedule_lag_seconds`` for periodic runs. Returns ``None`` when the run
    lacks essential identifiers.
    """
    run_id = str(run.get("run_id", ""))
    job_id = str(run.get("job_id", ""))
    if not run_id or not job_id:
        return None

    workflow_name = run.get("run_name") or f"job_{job_id}"
    status, state_message = _parse_run_state(run)

    start_time = _epoch_ms_to_dt(run.get("start_time")) or datetime.now(UTC)
    end_time = _epoch_ms_to_dt(run.get("end_time"))

    schedule_lag_seconds = _compute_schedule_lag(run, start_time, schedules or {})

    duration_seconds = _ms_to_seconds(run.get("run_duration"))
    if duration_seconds is None and end_time is not None and end_time >= start_time:
        duration_seconds = (end_time - start_time).total_seconds()

    tasks_total, tasks_failed = _count_task_failures(run)

    cluster_instance = run.get("cluster_instance")
    cluster_instance_id = None
    if isinstance(cluster_instance, dict):
        cluster_instance_id = cluster_instance.get("cluster_id") or None

    attempt_number = run.get("attempt_number")
    retry_count = int(attempt_number) if isinstance(attempt_number, (int, float)) else 0

    error_msg = state_message[:2000] if state_message else None

    return WorkflowRunMetric(
        workflow_id=job_id,
        workflow_name=workflow_name,
        run_id=run_id,
        workspace_id=workspace_id or None,
        workspace_name=workspace_name or None,
        status=status,
        trigger_type=_parse_trigger(run),
        start_time=start_time,
        end_time=end_time,
        duration_seconds=duration_seconds,
        queued_duration_seconds=_ms_to_seconds(run.get("queue_duration")),
        setup_duration_seconds=_ms_to_seconds(run.get("setup_duration")),
        execution_duration_seconds=_ms_to_seconds(run.get("execution_duration")),
        cleanup_duration_seconds=_ms_to_seconds(run.get("cleanup_duration")),
        schedule_lag_seconds=schedule_lag_seconds,
        retry_count=max(retry_count, 0),
        tasks_total=tasks_total,
        tasks_failed=tasks_failed,
        tasks=_map_tasks(run),
        cluster_instance_id=cluster_instance_id,
        creator_user_name=run.get("creator_user_name") or None,
        run_page_url=run.get("run_page_url") or None,
        run_type=run.get("run_type") or None,
        error_message=error_msg,
        tags=dict(run.get("tags", {})) if run.get("tags") else {},
    )
