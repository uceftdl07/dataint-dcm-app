"""Azure Databricks collector — cluster state and performance snapshots.

Enumerates all Databricks workspaces in the subscription via the Azure
Management REST API, then calls the Databricks 2.0 REST API per workspace
to retrieve cluster state information.

Authentication flow
-------------------
1. Acquire a management-plane token to list workspaces (Scope: Azure management).
2. Acquire a Databricks-scoped token (resource ID ``2ff814a6-…``) to call the
   Databricks workspace REST API.

Both tokens are obtained via the collector's Azure identity credential
(Managed Identity in production, DefaultAzureCredential in dev).

Key API calls
-------------
``GET management.azure.com/.../Microsoft.Databricks/workspaces``
    List all Databricks workspace ARM resources in the subscription.
``GET https://{workspace_url}/api/2.0/clusters/list``
    List job-related clusters only (``cluster_source`` in ``JOB``, ``PIPELINE``).
    Interactive / all-purpose clusters (``UI``, ``API``) are excluded so frontend
    active-cluster KPIs are not inflated.

Ported from
-----------
``AzureDatabricksService.cs`` (POC C# backend)
``DatabricksApiClient.cs``

Lakebase target
---------------
``dcm.monitoring.compute_metrics``
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from azure.identity import DefaultAzureCredential  # type: ignore[import-untyped]

from dcm_commons.collectors.base import BaseCollector
from dcm_commons.exceptions import CollectionError
from dcm_commons.logging_utils import get_logger, LogMarker, log_line
from dcm_commons.models.compute import ComputeMetric
from dcm_commons.models.enums import CloudProvider, ComputeState, ComputeType, MetricDomain

from azure_collector._azure_utils import get_databricks_token, get_mgmt_token

__all__ = ["DatabricksCollector"]

_logger = get_logger(__name__)

_MGMT_BASE = "https://management.azure.com"
_DB_API_VERSION = "2023-02-01"
_REQUEST_TIMEOUT = 30.0

# Databricks cluster state string → DCM ClusterState
# Databricks cluster_source values that represent ephemeral job compute (not interactive).
_JOB_CLUSTER_SOURCES: frozenset[str] = frozenset({"JOB", "PIPELINE"})

_DB_STATE_MAP: dict[str, ComputeState] = {
    "RUNNING": ComputeState.RUNNING,
    "TERMINATED": ComputeState.TERMINATED,
    "TERMINATING": ComputeState.TERMINATING,
    "PENDING": ComputeState.STARTING,
    "RESTARTING": ComputeState.RESTARTING,
    "RESIZING": ComputeState.RUNNING,       # Active — resizing workers
    "ERROR": ComputeState.ERROR,
    "UNKNOWN": ComputeState.UNKNOWN,
}


class DatabricksCollector(BaseCollector):
    """Collects cluster state snapshots from all Databricks workspaces in the subscription.

    Args:
        source_lz_id:    Landing zone identifier.
        subscription_id: Azure subscription ID.
        credential:      ``azure.identity`` credential.  Defaults to
                         ``DefaultAzureCredential``.
        max_retries:     Retry attempts on transient ``CollectionError``.
        retry_base_delay_seconds: Base delay for exponential back-off.
    """

    def __init__(
        self,
        source_lz_id: str,
        subscription_id: str,
        *,
        credential: Any | None = None,
        max_retries: int = 3,
        retry_base_delay_seconds: float = 2.0,
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

    @property
    def domain(self) -> MetricDomain:
        """Return the compute metric domain."""
        return MetricDomain.COMPUTE

    async def _collect_metrics(self) -> list[dict[str, Any]]:
        """Enumerate workspaces and collect cluster state from each one.

        Returns:
            List of :class:`~dcm_commons.models.compute.ComputeMetric` dicts.

        Raises:
            CollectionError: If workspace listing or all workspace cluster
                             queries fail.
        """
        _logger.info(
            "databricks_collect_starting",
            **log_line(
                LogMarker.START,
                f"DBX compute — subscription {self._subscription_id}",
                subscription_id=self._subscription_id,
            ),
        )
        mgmt_token = await get_mgmt_token(self._credential)
        db_token = await get_databricks_token(self._credential)

        _logger.info("databricks_workspaces_list_starting")
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as http:
            workspaces = await _list_workspaces(http, mgmt_token, self._subscription_id)

            if not workspaces:
                _logger.info(
                    "databricks_no_workspaces_found",
                    **log_line(LogMarker.WARN, "DBX compute — no workspaces in subscription"),
                )
                return []

            _logger.info(
                "databricks_workspaces_list_done",
                **log_line(
                    LogMarker.OK,
                    f"DBX compute — {len(workspaces)} workspace(s) found",
                    workspace_count=len(workspaces),
                ),
            )

            metrics: list[dict[str, Any]] = []
            for index, ws in enumerate(workspaces, start=1):
                workspace_url = ws.get("workspace_url", "")
                workspace_id = ws.get("workspace_id", "")
                workspace_name = ws.get("name", "")

                if not workspace_url:
                    _logger.warning(
                        "databricks_workspace_no_url",
                        workspace_name=workspace_name,
                    )
                    continue

                _logger.info(
                    "databricks_workspace_clusters_query_starting",
                    **log_line(
                        LogMarker.START,
                        f"DBX [{index}/{len(workspaces)}] {workspace_name} — clusters/list (job only)",
                        workspace=workspace_name,
                        index=index,
                        total=len(workspaces),
                    ),
                )
                try:
                    clusters = await _list_clusters(http, db_token, workspace_url)
                except Exception as exc:
                    _logger.warning(
                        "databricks_cluster_list_failed",
                        **log_line(
                            LogMarker.FAIL,
                            f"DBX {workspace_name} — clusters/list denied or failed: {exc}",
                            workspace=workspace_name,
                            reason=str(exc),
                        ),
                    )
                    continue

                job_clusters = [c for c in clusters if _is_job_cluster(c)]
                skipped = len(clusters) - len(job_clusters)
                _logger.info(
                    "databricks_workspace_clusters_query_done",
                    **log_line(
                        LogMarker.OK if job_clusters else LogMarker.WARN,
                        (
                            f"DBX {workspace_name} — {len(job_clusters)} job cluster(s)"
                            f"{f', {skipped} interactive skipped' if skipped else ''}"
                        ),
                        workspace=workspace_name,
                        cluster_count=len(job_clusters),
                        skipped_interactive=skipped,
                        total_clusters_seen=len(clusters),
                    ),
                )
                for cluster in job_clusters:
                    metric = _map_cluster_to_metric(
                        cluster,
                        workspace_id=workspace_id,
                        workspace_name=workspace_name,
                    )
                    if metric is not None:
                        metrics.append(metric.model_dump())

            _logger.info(
                "databricks_collection_done",
                **log_line(
                    LogMarker.OK if metrics else LogMarker.WARN,
                    f"DBX compute done — {len(metrics)} metric(s) from {len(workspaces)} workspace(s)",
                    workspace_count=len(workspaces),
                    metric_count=len(metrics),
                ),
            )
            return metrics


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _is_job_cluster(cluster: dict[str, Any]) -> bool:
    """Return True for ephemeral job/pipeline clusters, not interactive all-purpose."""
    source = str(cluster.get("cluster_source", "")).upper()
    return source in _JOB_CLUSTER_SOURCES


async def _list_workspaces(
    http: httpx.AsyncClient,
    mgmt_token: str,
    subscription_id: str,
) -> list[dict[str, Any]]:
    """List all Databricks workspace ARM resources in the subscription.

    Uses the Azure Management REST API directly (not the SDK) to obtain
    ``workspaceUrl`` from resource properties in a single call.

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
            "DatabricksCollector",
            f"Network error listing Databricks workspaces: {exc}",
        ) from exc

    if response.status_code == 429:
        raise CollectionError(
            "DatabricksCollector",
            "Management API rate-limited (HTTP 429) listing workspaces.",
        )
    if not response.is_success:
        raise CollectionError(
            "DatabricksCollector",
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


async def _list_clusters(
    http: httpx.AsyncClient,
    db_token: str,
    workspace_url: str,
) -> list[dict[str, Any]]:
    """Retrieve all clusters from a Databricks workspace via REST API 2.0.

    Args:
        http:          Shared ``httpx.AsyncClient``.
        db_token:      Databricks-scoped bearer token.
        workspace_url: Workspace hostname (e.g. ``adb-1234.19.azuredatabricks.net``).

    Returns:
        List of raw cluster dicts from the Databricks API.

    Raises:
        CollectionError: On authentication or API errors.
    """
    # Ensure the URL has the https:// scheme.
    base = workspace_url if workspace_url.startswith("https://") else f"https://{workspace_url}"
    url = f"{base}/api/2.0/clusters/list"

    try:
        response = await http.get(
            url,
            headers={"Authorization": f"Bearer {db_token}"},
        )
    except httpx.RequestError as exc:
        raise CollectionError(
            "DatabricksCollector",
            f"Network error calling Databricks clusters/list on {workspace_url}: {exc}",
        ) from exc

    if not response.is_success:
        raise CollectionError(
            "DatabricksCollector",
            f"Databricks clusters/list returned HTTP {response.status_code} "
            f"on {workspace_url}: {response.text[:200]}",
        )

    return response.json().get("clusters", [])


def _map_cluster_to_metric(
    cluster: dict[str, Any],
    workspace_id: str,
    workspace_name: str = "",
) -> ComputeMetric | None:
    """Map a Databricks cluster dict to a :class:`ComputeMetric`.

    Args:
        cluster:        Raw cluster dict from the Databricks REST API.
        workspace_id:   Parent workspace identifier.
        workspace_name: Azure ARM workspace name (stamped into tags for the UI).

    Returns:
        A :class:`ComputeMetric`, or ``None`` if the cluster lacks a ``cluster_id``.
    """
    cluster_id = cluster.get("cluster_id", "")
    cluster_name = cluster.get("cluster_name", "")

    if not cluster_id:
        return None

    raw_state = cluster.get("state", "UNKNOWN").upper()
    state = _DB_STATE_MAP.get(raw_state, ComputeState.UNKNOWN)

    # Worker count: prefer effective_spark_version count, fall back to num_workers.
    autoscale = cluster.get("autoscale", {})
    num_workers: int = cluster.get("num_workers", 0)
    autoscale_min: int | None = autoscale.get("min_workers") if autoscale else None
    autoscale_max: int | None = autoscale.get("max_workers") if autoscale else None

    # Start time: Databricks returns epoch milliseconds.
    start_time: datetime | None = None
    start_ms = cluster.get("start_time")
    if start_ms:
        try:
            start_time = datetime.fromtimestamp(start_ms / 1_000, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            pass

    tags = dict(cluster.get("custom_tags", {}))
    cluster_source = str(cluster.get("cluster_source", "")).upper()
    if cluster_source:
        tags["cluster_source"] = cluster_source
    if workspace_name:
        tags["dcm_workspace_name"] = workspace_name

    return ComputeMetric(
        compute_resource_id=cluster_id,
        resource_name=cluster_name or cluster_id,
        compute_type=ComputeType.DATABRICKS,
        state=state,
        num_workers=num_workers,
        autoscale_min=autoscale_min,
        autoscale_max=autoscale_max,
        node_type=cluster.get("node_type_id"),
        spark_version=cluster.get("spark_version"),
        start_time=start_time,
        creator=cluster.get("creator_user_name"),
        workspace_id=workspace_id or None,
        tags=tags,
    )


def _extract_resource_group(resource_id: str) -> str:
    """Extract the resource group name from an ARM resource ID."""
    parts = resource_id.lower().split("/")
    try:
        idx = parts.index("resourcegroups")
        return resource_id.split("/")[idx + 1]
    except (ValueError, IndexError):
        return ""
