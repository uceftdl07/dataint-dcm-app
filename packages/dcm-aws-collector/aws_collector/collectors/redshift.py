"""AWS Redshift collector — cluster health and performance snapshots.

Enumerates all Amazon Redshift clusters in the account/region and collects
point-in-time health and performance metrics via CloudWatch.

Key API calls
-------------
``redshift.describe_clusters(Marker=...)``
    Paginated list of all Redshift clusters with provisioned capacity details.
``cloudwatch.get_metric_statistics(Namespace="AWS/Redshift", ...)``
    Per-cluster metrics: CPUUtilization, PercentageDiskSpaceUsed,
    DatabaseConnections.

Lakebase target
---------------
``dcm.monitoring.database_snapshots``
"""

from __future__ import annotations

from typing import Any

from dcm_commons.collectors.base import BaseCollector
from dcm_commons.exceptions import CollectionError
from dcm_commons.logging_utils import get_logger
from dcm_commons.models.database import DatabaseMetric
from dcm_commons.models.enums import CloudProvider, DatabaseType, MetricDomain

from aws_collector._aws_utils import create_aws_client, fetch_cloudwatch_metric, run_sync

__all__ = ["RedshiftCollector"]

_logger = get_logger(__name__)


class RedshiftCollector(BaseCollector):
    """Collects health and performance snapshots for Amazon Redshift clusters.

    For each cluster discovered via ``describe_clusters``, queries CloudWatch
    for CPU utilisation, disk space usage and active connections.

    ``PercentageDiskSpaceUsed`` is reported directly as a percentage, so no
    bytes conversion is needed.  ``TotalStorageCapacity`` (in MB) is available
    in the describe response and converted to GB for ``storage_limit_gb``.

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
        self._redshift = create_aws_client("redshift", region_name=aws_region)
        self._cw = create_aws_client("cloudwatch", region_name=aws_region)

    @property
    def domain(self) -> MetricDomain:
        """Return the database metric domain."""
        return MetricDomain.DATABASE

    async def _collect_metrics(self) -> list[dict[str, Any]]:
        """Enumerate all Redshift clusters and collect CloudWatch metrics.

        Returns:
            List of :class:`~dcm_commons.models.database.DatabaseMetric` dicts.

        Raises:
            CollectionError: If the cluster listing call fails.
        """
        try:
            clusters = await _paginate_clusters(self._redshift)
        except Exception as exc:
            raise CollectionError(
                "RedshiftCollector",
                f"Failed to list Redshift clusters: {exc}",
            ) from exc

        _logger.debug("redshift_clusters_found", count=len(clusters))

        metrics: list[dict[str, Any]] = []
        for cluster in clusters:
            metric = await _collect_cluster_metric(cluster, self._cw)
            if metric is not None:
                metrics.append(metric.model_dump())

        _logger.info("redshift_collection_done", metric_count=len(metrics))
        return metrics


# ---------------------------------------------------------------------------
# Pagination helper
# ---------------------------------------------------------------------------


async def _paginate_clusters(redshift: Any) -> list[dict[str, Any]]:
    """Paginate through all Redshift clusters using the ``Marker`` cursor.

    Args:
        redshift: boto3 Redshift client.

    Returns:
        Flat list of cluster dicts from ``describe_clusters``.
    """
    clusters: list[dict[str, Any]] = []
    marker: str | None = None

    while True:
        kwargs: dict[str, Any] = {}
        if marker:
            kwargs["Marker"] = marker

        response = await run_sync(redshift.describe_clusters, **kwargs)
        clusters.extend(response.get("Clusters", []))

        marker = response.get("Marker")
        if not marker:
            break

    return clusters


# ---------------------------------------------------------------------------
# Per-cluster collection
# ---------------------------------------------------------------------------

# MB → GB conversion factor for Redshift storage capacity.
_MB_TO_GB: float = 1.0 / 1024.0


async def _collect_cluster_metric(
    cluster: dict[str, Any],
    cloudwatch: Any,
) -> DatabaseMetric | None:
    """Collect CloudWatch metrics for a single Redshift cluster.

    Args:
        cluster:    Raw cluster dict from ``describe_clusters``.
        cloudwatch: boto3 CloudWatch client.

    Returns:
        A :class:`DatabaseMetric`, or ``None`` if the cluster identifier is missing.
    """
    cluster_id: str = cluster.get("ClusterIdentifier", "")
    if not cluster_id:
        return None

    # Endpoint details.
    endpoint: dict[str, Any] = cluster.get("Endpoint", {})
    server_name: str = endpoint.get("Address", cluster_id)

    # Storage capacity: NumberOfNodes × NodeType storage (approximated via
    # TotalStorageCapacityInMegaBytes when available, else None).
    total_storage_mb = cluster.get("TotalStorageCapacityInMegaBytes")
    storage_limit_gb: float | None = (
        round(float(total_storage_mb) * _MB_TO_GB, 2)
        if total_storage_mb is not None
        else None
    )

    dims = [{"Name": "ClusterIdentifier", "Value": cluster_id}]

    cpu = await fetch_cloudwatch_metric(cloudwatch, "AWS/Redshift", "CPUUtilization", dims)
    disk_pct = await fetch_cloudwatch_metric(
        cloudwatch, "AWS/Redshift", "PercentageDiskSpaceUsed", dims
    )
    connections = await fetch_cloudwatch_metric(
        cloudwatch, "AWS/Redshift", "DatabaseConnections", dims
    )

    # Derive storage_used_gb from disk percentage and total capacity.
    storage_used_gb: float | None = None
    if storage_limit_gb is not None and disk_pct is not None:
        storage_used_gb = round(storage_limit_gb * disk_pct / 100.0, 4)

    # Tags: Redshift returns a list of {"TagKey": ..., "TagValue": ...} dicts.
    tags: dict[str, str] = {
        t["TagKey"]: t.get("TagValue", "")
        for t in cluster.get("Tags", [])
        if "TagKey" in t
    }

    # Cluster availability: consider "available" and "available, prep-for-resize".
    cluster_status: str = cluster.get("ClusterStatus", "")
    is_available: bool = cluster_status.startswith("available")

    return DatabaseMetric(
        db_id=f"arn:aws:redshift:{cluster.get('AvailabilityZone', '')}::cluster:{cluster_id}",
        db_name=cluster.get("DBName", cluster_id) or cluster_id,
        db_type=DatabaseType.REDSHIFT,
        server_name=server_name,
        region=cluster.get("AvailabilityZone"),
        cpu_percent=cpu,
        storage_used_gb=storage_used_gb,
        storage_limit_gb=storage_limit_gb,
        active_connections=int(round(connections)) if connections is not None else None,
        is_available=is_available,
        tags=tags,
    )
