"""Azure Databricks Pipelines collector — workflow and job execution metrics.

Enumerates all Databricks workspaces in the subscription via the Azure
Management REST API, then calls the Databricks 2.0 REST API per workspace
to retrieve Databricks Workflows execution history.

Authentication flow
-------------------
Same as DatabricksCollector:
1. Acquire a management-plane token to list workspaces (Scope: Azure management).
2. Acquire a Databricks-scoped token (resource ID ``2ff814a6-…``) to call the
   Databricks workspace REST API.

Key API calls
-------------
``GET management.azure.com/.../Microsoft.Databricks/workspaces``
    List all Databricks workspace ARM resources in the subscription.
``GET https://{workspace_url}/api/2.1/jobs/runs/list``
    List all job runs within a single workspace (pagination support).

Lakebase target
---------------
``dcm.monitoring.pipeline_metrics`` (domain=pipeline)

Note
----
Databricks Workflows (formerly called Jobs API) are accessible via the
``/jobs/runs/list`` endpoint. This collector fetches recent job executions
and maps them to :class:`~dcm_commons.models.pipeline.PipelineMetric`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from azure.identity import DefaultAzureCredential  # type: ignore[import-untyped]

from dcm_commons.collectors.base import BaseCollector
from dcm_commons.exceptions import CollectionError
from dcm_commons.logging_utils import get_logger, LogMarker, log_line
from dcm_commons.models.pipeline import PipelineMetric
from dcm_commons.models.enums import (
    CloudProvider,
    MetricDomain,
    PipelineRunStatus,
    TriggerType,
)

from azure_collector._azure_utils import get_databricks_token, get_mgmt_token

__all__ = ["DatabricksPipelineCollector"]

_logger = get_logger(__name__)

_MGMT_BASE = "https://management.azure.com"
_DB_API_VERSION = "2023-02-01"
_REQUEST_TIMEOUT = 30.0

# Databricks job run state → DCM PipelineRunStatus
_DB_RUN_STATE_MAP: dict[str, PipelineRunStatus] = {
    "SUCCESS": PipelineRunStatus.SUCCEEDED,
    "SUCCEEDED": PipelineRunStatus.SUCCEEDED,
    "FAILED": PipelineRunStatus.FAILED,
    "RUNNING": PipelineRunStatus.RUNNING,
    "CANCELLED": PipelineRunStatus.CANCELLED,
    "PENDING": PipelineRunStatus.QUEUED,
    "INTERNAL_ERROR": PipelineRunStatus.FAILED,
    "SKIPPED": PipelineRunStatus.SKIPPED,
    "TERMINATING": PipelineRunStatus.RUNNING,  # Intermediate state
    "TERMINATED": PipelineRunStatus.SUCCEEDED,  # resolved via result_state when present
}


class DatabricksPipelineCollector(BaseCollector):
    """Collects Databricks workflow (job) execution snapshots from all workspaces in the subscription.

    Args:
        source_lz_id:    Landing zone identifier.
        subscription_id: Azure subscription ID.
        credential:      ``azure.identity`` credential. Defaults to ``DefaultAzureCredential``.
        max_retries:     Retry attempts on transient ``CollectionError``.
        retry_base_delay_seconds: Base delay for exponential back-off.
        lookback_hours:  Number of hours to look back for job runs (default 24).
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
        """Return the pipeline metric domain."""
        return MetricDomain.PIPELINE

    async def _collect_metrics(self) -> list[dict[str, Any]]:
        """Enumerate workspaces and collect pipeline (job) run history from each one.

        Returns:
            List of :class:`~dcm_commons.models.pipeline.PipelineMetric` dicts.

        Raises:
            CollectionError: If workspace listing or all workspace job run
                             queries fail.
        """
        _logger.info(
            "databricks_pipelines_collect_starting",
            **log_line(
                LogMarker.START,
                f"DBX jobs — subscription {self._subscription_id}, lookback {self._lookback_hours}h",
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
                    "databricks_pipelines_no_workspaces_found",
                    **log_line(LogMarker.WARN, "DBX jobs — no workspaces in subscription"),
                )
                return []

            _logger.info(
                "databricks_pipelines_workspaces_found",
                **log_line(
                    LogMarker.OK,
                    f"DBX jobs — {len(workspaces)} workspace(s) found",
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
                        "databricks_pipelines_workspace_no_url",
                        **log_line(
                            LogMarker.WARN,
                            f"DBX jobs [{index}/{len(workspaces)}] {workspace_name} — missing workspace URL",
                            workspace_name=workspace_name,
                        ),
                    )
                    continue

                _logger.info(
                    "databricks_pipelines_runs_list_starting",
                    **log_line(
                        LogMarker.START,
                        f"DBX jobs [{index}/{len(workspaces)}] {workspace_name} — jobs/runs/list",
                        workspace=workspace_name,
                        index=index,
                        total=len(workspaces),
                    ),
                )
                try:
                    runs = await _list_job_runs(
                        http,
                        db_token,
                        workspace_url,
                        lookback_hours=self._lookback_hours,
                    )
                except Exception as exc:
                    _logger.warning(
                        "databricks_pipelines_runs_list_failed",
                        **log_line(
                            LogMarker.FAIL,
                            f"DBX jobs {workspace_name} — runs/list denied or failed: {exc}",
                            workspace=workspace_name,
                            reason=str(exc),
                        ),
                    )
                    continue

                _logger.info(
                    "databricks_pipelines_runs_list_done",
                    **log_line(
                        LogMarker.OK if runs else LogMarker.WARN,
                        f"DBX jobs {workspace_name} — {len(runs)} run(s) in lookback window",
                        workspace=workspace_name,
                        run_count=len(runs),
                    ),
                )

                for run in runs:
                    metric = _map_run_to_metric(
                        run,
                        workspace_id=workspace_id,
                        workspace_name=workspace_name,
                    )
                    if metric is not None:
                        metrics.append(metric.model_dump())

            _logger.info(
                "databricks_pipelines_collection_done",
                **log_line(
                    LogMarker.OK if metrics else LogMarker.WARN,
                    f"DBX jobs done — {len(metrics)} run metric(s) from {len(workspaces)} workspace(s)",
                    workspace_count=len(workspaces),
                    metric_count=len(metrics),
                ),
            )
            return metrics


# ---------------------------------------------------------------------------
# Private helpers (shared with DatabricksCollector)
# ---------------------------------------------------------------------------


async def _list_workspaces(
    http: httpx.AsyncClient,
    mgmt_token: str,
    subscription_id: str,
) -> list[dict[str, Any]]:
    """List all Databricks workspace ARM resources in the subscription.

    (Identical to the one in databricks.py; could be refactored to a shared
     location in dcm_commons or _azure_utils if necessary.)

    Args:
        http:            Shared ``httpx.AsyncClient``.
        mgmt_token:      Azure management bearer token.
        subscription_id: Azure subscription ID.

    Returns:
        List of workspace dicts with keys: ``workspace_url``, ``workspace_id``,
        ``name``, ``resource_group``.

    Raises:
        CollectionError: On authentication or API errors.
    """
    url = (
        f"{_MGMT_BASE}/subscriptions/{subscription_id}"
        f"/providers/Microsoft.Databricks/workspaces"
        f"?api-version={_DB_API_VERSION}"
    )
    try:
        response = await http.get(
            url,
            headers={"Authorization": f"Bearer {mgmt_token}"},
        )
    except httpx.RequestError as exc:
        raise CollectionError(
            "DatabricksPipelineCollector",
            f"Network error listing Databricks workspaces: {exc}",
        ) from exc

    if response.status_code == 429:
        raise CollectionError(
            "DatabricksPipelineCollector",
            "Management API rate-limited (HTTP 429) listing workspaces.",
        )
    if not response.is_success:
        raise CollectionError(
            "DatabricksPipelineCollector",
            f"Failed to list workspaces: HTTP {response.status_code} — {response.text[:200]}",
        )

    items = response.json().get("value", [])
    workspaces = []
    for item in items:
        props = item.get("properties", {})
        workspaces.append(
            {
                "name": item.get("name", ""),
                "workspace_url": props.get("workspaceUrl", ""),
                "workspace_id": str(props.get("workspaceId", "")),
                "resource_group": _extract_resource_group(item.get("id", "")),
            }
        )
    return workspaces


async def _list_job_runs(
    http: httpx.AsyncClient,
    db_token: str,
    workspace_url: str,
    lookback_hours: int = 24,
) -> list[dict[str, Any]]:
    """Retrieve recent job runs from a Databricks workspace via REST API 2.1.

    Args:
        http:            Shared ``httpx.AsyncClient``.
        db_token:        Databricks-scoped bearer token.
        workspace_url:   Workspace hostname (e.g., ``adb-1234.19.azuredatabricks.net``).
        lookback_hours:  How many hours back to fetch runs (default 24).

    Returns:
        List of raw job run dicts from the Databricks API.

    Raises:
        CollectionError: On authentication or API errors.
    """
    base = workspace_url if workspace_url.startswith("https://") else f"https://{workspace_url}"
    url = f"{base}/api/2.1/jobs/runs/list"

    # Calculate the start time for filtering job runs.
    now = datetime.now(timezone.utc)
    lookback_ms = int(lookback_hours * 3600 * 1000)
    start_time_ms = int((now.timestamp() * 1000) - lookback_ms)

    params = {
        "start_time_ms": start_time_ms,
        "expand_tasks": "false",
    }

    try:
        response = await http.get(
            url,
            headers={"Authorization": f"Bearer {db_token}"},
            params=params,
        )
    except httpx.RequestError as exc:
        raise CollectionError(
            "DatabricksPipelineCollector",
            f"Network error calling Databricks jobs/runs/list on {workspace_url}: {exc}",
        ) from exc

    if not response.is_success:
        raise CollectionError(
            "DatabricksPipelineCollector",
            f"Databricks jobs/runs/list returned HTTP {response.status_code} "
            f"on {workspace_url}: {response.text[:200]}",
        )

    return response.json().get("runs", [])


def _parse_run_state(run: dict[str, Any]) -> tuple[PipelineRunStatus, str]:
    """Normalize Databricks run state from REST API 2.1 payloads.

    The API may return ``state`` as a legacy string or as an object with
    ``life_cycle_state``, ``result_state``, and ``state_message``.
    """
    raw_state = run.get("state")
    message = str(run.get("state_message", ""))

    if isinstance(raw_state, dict):
        lifecycle = str(raw_state.get("life_cycle_state", "")).upper()
        result = str(raw_state.get("result_state", "")).upper()
        message = str(raw_state.get("state_message", message))

        if lifecycle in ("PENDING",):
            return PipelineRunStatus.QUEUED, message
        if lifecycle in ("RUNNING", "TERMINATING"):
            return PipelineRunStatus.RUNNING, message
        if result:
            return _DB_RUN_STATE_MAP.get(result, PipelineRunStatus.RUNNING), message
        if lifecycle:
            return _DB_RUN_STATE_MAP.get(lifecycle, PipelineRunStatus.RUNNING), message

    if isinstance(raw_state, str) and raw_state:
        return _DB_RUN_STATE_MAP.get(raw_state.upper(), PipelineRunStatus.RUNNING), message

    status = run.get("status")
    if isinstance(status, dict):
        nested = str(status.get("state", "")).upper()
        if nested:
            return _DB_RUN_STATE_MAP.get(nested, PipelineRunStatus.RUNNING), message

    return PipelineRunStatus.RUNNING, message


def _map_run_to_metric(
    run: dict[str, Any],
    workspace_id: str,
    workspace_name: str = "",
) -> PipelineMetric | None:
    """Map a Databricks job run dict to a :class:`PipelineMetric`.

    Args:
        run:            Raw job run dict from the Databricks REST API.
        workspace_id:   Parent workspace identifier.
        workspace_name: Azure ARM resource name of the parent workspace.

    Returns:
        A :class:`PipelineMetric`, or ``None`` if the run lacks essential fields.
    """
    run_id = str(run.get("run_id", ""))
    job_id = str(run.get("job_id", ""))

    if not run_id or not job_id:
        return None

    job_name = run.get("run_name", f"job_{job_id}")

    state, state_message = _parse_run_state(run)

    # Timestamps: Databricks returns epoch milliseconds
    start_time: datetime | None = None
    end_time: datetime | None = None

    start_ms = run.get("start_time")
    if start_ms:
        try:
            start_time = datetime.fromtimestamp(start_ms / 1_000, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            pass

    end_ms = run.get("end_time")
    if end_ms:
        try:
            end_time = datetime.fromtimestamp(end_ms / 1_000, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            pass

    # If start_time is None, use current time as fallback to prevent validation error.
    if start_time is None:
        start_time = datetime.now(timezone.utc)

    error_msg = state_message
    if len(error_msg) > 2000:
        error_msg = error_msg[:2000]

    return PipelineMetric(
        pipeline_id=f"databricks:job:{job_id}",
        pipeline_name=job_name,
        run_id=run_id,
        status=state,
        trigger_type=TriggerType.UNKNOWN,  # Databricks API doesn't expose trigger type easily
        start_time=start_time,
        end_time=end_time,
        error_message=error_msg if error_msg else None,
        databricks_workspace_id=workspace_id or None,
        databricks_workspace_name=workspace_name or None,
        tags=dict(run.get("tags", {})) if run.get("tags") else {},
    )


def _extract_resource_group(resource_id: str) -> str:
    """Extract the resource group name from an ARM resource ID."""
    parts = resource_id.lower().split("/")
    try:
        idx = parts.index("resourcegroups")
        return resource_id.split("/")[idx + 1]
    except (ValueError, IndexError):
        return ""

