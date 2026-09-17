"""AWS EMR collector — cluster state snapshots.

Enumerates all Amazon EMR clusters in the account/region and collects
a point-in-time state snapshot for each one.

Key API calls
-------------
``emr.list_clusters(ClusterStates=[...], Marker=...)``
    Paginated list of EMR clusters filtered by state.
``emr.describe_cluster(ClusterId=id)``
    Detailed cluster information including instance group composition.

Lakebase target
---------------
``dcm.monitoring.compute_metrics``
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dcm_commons.collectors.base import BaseCollector
from dcm_commons.exceptions import CollectionError
from dcm_commons.logging_utils import get_logger
from dcm_commons.models.compute import ComputeMetric
from dcm_commons.models.enums import CloudProvider, ComputeState, ComputeType, MetricDomain

from aws_collector._aws_utils import create_aws_client, map_emr_state, run_sync

__all__ = ["EMRCollector"]

_logger = get_logger(__name__)

# EMR states to enumerate — all non-terminated states plus recently terminated.
_EMR_STATES_TO_LIST = [
    "STARTING",
    "BOOTSTRAPPING",
    "RUNNING",
    "WAITING",
    "TERMINATING",
    "TERMINATED",
    "TERMINATED_WITH_ERRORS",
]


class EMRCollector(BaseCollector):
    """Collects cluster state snapshots for all Amazon EMR clusters.

    Queries the cluster list with ``list_clusters`` (paginated), then calls
    ``describe_cluster`` for each to obtain worker count and start time.

    Args:
        source_lz_id: Landing zone identifier.
        aws_region:   AWS region (e.g. ``"eu-west-1"``).
        max_retries:  Retry attempts on transient failures.
        retry_base_delay_seconds: Base delay for exponential back-off.
    """

    def __init__(
        self,
        source_lz_id: str,
        aws_region: str,
        *,
        subscription_or_account_id: str | None = None,
        max_retries: int = 3,
        retry_base_delay_seconds: float = 2.0,
    ) -> None:
        super().__init__(
            source_lz_id=source_lz_id,
            cloud_provider=CloudProvider.AWS,
            subscription_or_account_id=subscription_or_account_id,
            max_retries=max_retries,
            retry_base_delay_seconds=retry_base_delay_seconds,
        )
        self._emr = create_aws_client("emr", region_name=aws_region)

    @property
    def domain(self) -> MetricDomain:
        """Return the compute metric domain."""
        return MetricDomain.COMPUTE

    async def _collect_metrics(self) -> list[dict[str, Any]]:
        """List all EMR clusters and collect their state details.

        Returns:
            List of :class:`~dcm_commons.models.compute.ComputeMetric` dicts.

        Raises:
            CollectionError: If the cluster listing call fails.
        """
        try:
            cluster_summaries = await _paginate_clusters(self._emr)
        except Exception as exc:
            raise CollectionError(
                "EMRCollector",
                f"Failed to list EMR clusters: {exc}",
            ) from exc

        _logger.debug("emr_clusters_found", count=len(cluster_summaries))

        metrics: list[dict[str, Any]] = []
        for summary in cluster_summaries:
            cluster_id: str = summary.get("Id", "")
            if not cluster_id:
                continue

            try:
                detail = await run_sync(
                    self._emr.describe_cluster,
                    ClusterId=cluster_id,
                )
            except Exception as exc:
                _logger.warning(
                    "emr_describe_cluster_failed",
                    cluster_id=cluster_id,
                    reason=str(exc),
                )
                continue

            metric = _map_cluster(detail.get("Cluster", {}))
            if metric is not None:
                metrics.append(metric.model_dump())

        _logger.info("emr_collection_done", metric_count=len(metrics))
        return metrics


# ---------------------------------------------------------------------------
# Pagination helper
# ---------------------------------------------------------------------------


async def _paginate_clusters(emr: Any) -> list[dict[str, Any]]:
    """Paginate through EMR clusters using the ``Marker`` cursor.

    Args:
        emr: boto3 EMR client.

    Returns:
        Flat list of cluster summary dicts from ``list_clusters``.
    """
    summaries: list[dict[str, Any]] = []
    marker: str | None = None

    while True:
        kwargs: dict[str, Any] = {"ClusterStates": _EMR_STATES_TO_LIST}
        if marker:
            kwargs["Marker"] = marker

        response = await run_sync(emr.list_clusters, **kwargs)
        summaries.extend(response.get("Clusters", []))

        marker = response.get("Marker")
        if not marker:
            break

    return summaries


# ---------------------------------------------------------------------------
# Mapping helper
# ---------------------------------------------------------------------------


def _map_cluster(cluster: dict[str, Any]) -> ComputeMetric | None:
    """Map an EMR ``describe_cluster`` response to a :class:`ComputeMetric`.

    Args:
        cluster: The ``Cluster`` sub-dict from ``describe_cluster``.

    Returns:
        A :class:`ComputeMetric`, or ``None`` if the cluster lacks an ID.
    """
    cluster_id: str = cluster.get("Id", "")
    cluster_name: str = cluster.get("Name", "") or cluster_id
    if not cluster_id:
        return None

    raw_state: str = cluster.get("Status", {}).get("State", "")
    state: ComputeState = map_emr_state(raw_state)

    # Worker count: sum of slave (core + task) instance group counts.
    num_workers: int = 0
    for group in cluster.get("InstanceGroups", []):
        role: str = group.get("InstanceGroupType", "")
        if role.upper() in ("CORE", "TASK"):
            num_workers += group.get("RunningInstanceCount", 0)

    # Start time: EMR returns an epoch timestamp (float/int).
    start_time: datetime | None = None
    status_timeline = cluster.get("Status", {}).get("Timeline", {})
    created_at = status_timeline.get("CreationDateTime")
    if created_at is not None:
        try:
            # boto3 returns timezone-aware datetime objects for EMR timestamps.
            start_time = (
                created_at
                if hasattr(created_at, "tzinfo") and created_at.tzinfo is not None
                else created_at.replace(tzinfo=timezone.utc)
                if hasattr(created_at, "replace")
                else None
            )
        except Exception:
            start_time = None

    # Tags: EMR returns a list of {"Key": ..., "Value": ...} dicts.
    tags: dict[str, str] = {
        t["Key"]: t.get("Value", "")
        for t in cluster.get("Tags", [])
        if "Key" in t
    }

    return ComputeMetric(
        compute_resource_id=cluster_id,
        resource_name=cluster_name,
        compute_type=ComputeType.EMR,
        state=state,
        num_workers=num_workers,
        node_type=cluster.get("Ec2InstanceAttributes", {}).get("Ec2SubnetId"),
        spark_version=cluster.get("ReleaseLabel"),  # e.g. "emr-7.0.0"
        start_time=start_time,
        creator=cluster.get("RequestedAmiVersion"),
        tags=tags,
    )
