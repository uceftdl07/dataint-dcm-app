"""AWS RDS collector — database instance health and CloudWatch metrics.

Enumerates all Amazon RDS and Aurora DB instances in the account/region
and collects a point-in-time health snapshot using CloudWatch metrics.

Key API calls
-------------
``rds.describe_db_instances(Marker=...)``
    Paginated list of all RDS/Aurora database instances.
``cloudwatch.get_metric_statistics(Namespace="AWS/RDS", ...)``
    Per-instance metrics: CPUUtilization, DatabaseConnections,
    FreeStorageSpace, FreeableMemory.

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
from dcm_commons.models.enums import CloudProvider, MetricDomain

from aws_collector._aws_utils import (
    create_aws_client,
    fetch_cloudwatch_metric,
    map_rds_engine,
    run_sync,
)

__all__ = ["RDSCollector"]

_logger = get_logger(__name__)

# GiB → bytes conversion (AllocatedStorage in RDS describe is in GiB).
_GIB_TO_BYTES: float = 1024.0 ** 3


class RDSCollector(BaseCollector):
    """Collects health and performance snapshots for Amazon RDS / Aurora instances.

    For each DB instance discovered via ``describe_db_instances``, queries
    CloudWatch for CPU utilisation, active connections, free storage, and
    free memory.  Storage metrics are converted to GB for consistency with
    the Azure database collector.

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
        self._rds = create_aws_client("rds", region_name=aws_region)
        self._cw = create_aws_client("cloudwatch", region_name=aws_region)

    @property
    def domain(self) -> MetricDomain:
        """Return the database metric domain."""
        return MetricDomain.DATABASE

    async def _collect_metrics(self) -> list[dict[str, Any]]:
        """Enumerate all RDS/Aurora instances and collect CloudWatch metrics.

        Returns:
            List of :class:`~dcm_commons.models.database.DatabaseMetric` dicts.

        Raises:
            CollectionError: If the DB instance listing call fails.
        """
        try:
            instances = await _paginate_db_instances(self._rds)
        except Exception as exc:
            raise CollectionError(
                "RDSCollector",
                f"Failed to list RDS DB instances: {exc}",
            ) from exc

        _logger.debug("rds_instances_found", count=len(instances))

        metrics: list[dict[str, Any]] = []
        for instance in instances:
            metric = await _collect_instance_metric(instance, self._cw)
            if metric is not None:
                metrics.append(metric.model_dump())

        _logger.info("rds_collection_done", metric_count=len(metrics))
        return metrics


# ---------------------------------------------------------------------------
# Pagination helper
# ---------------------------------------------------------------------------


async def _paginate_db_instances(rds: Any) -> list[dict[str, Any]]:
    """Paginate through all RDS/Aurora DB instances using the ``Marker`` cursor.

    Args:
        rds: boto3 RDS client.

    Returns:
        Flat list of DB instance dicts from ``describe_db_instances``.
    """
    instances: list[dict[str, Any]] = []
    marker: str | None = None

    while True:
        kwargs: dict[str, Any] = {}
        if marker:
            kwargs["Marker"] = marker

        response = await run_sync(rds.describe_db_instances, **kwargs)
        instances.extend(response.get("DBInstances", []))

        marker = response.get("Marker")
        if not marker:
            break

    return instances


# ---------------------------------------------------------------------------
# Per-instance collection
# ---------------------------------------------------------------------------


async def _collect_instance_metric(
    instance: dict[str, Any],
    cloudwatch: Any,
) -> DatabaseMetric | None:
    """Collect CloudWatch metrics for a single RDS/Aurora instance.

    Args:
        instance:   Raw DB instance dict from ``describe_db_instances``.
        cloudwatch: boto3 CloudWatch client.

    Returns:
        A :class:`DatabaseMetric`, or ``None`` if the instance lacks an ID.
    """
    instance_id: str = instance.get("DBInstanceIdentifier", "")
    if not instance_id:
        return None

    engine: str = instance.get("Engine", "")
    db_type = map_rds_engine(engine)

    # Server endpoint hostname.
    endpoint: dict[str, Any] = instance.get("Endpoint", {})
    server_name: str = endpoint.get("Address", instance_id)

    # Allocated storage is in GiB — convert to GB (GiB ≈ GB for monitoring purposes).
    allocated_gib: int = instance.get("AllocatedStorage", 0)
    storage_limit_gb: float | None = float(allocated_gib) if allocated_gib else None

    dims = [{"Name": "DBInstanceIdentifier", "Value": instance_id}]

    # CloudWatch metric queries — all run concurrently would require asyncio.gather,
    # but run_sync is already threaded; keep sequential for simplicity.
    cpu = await fetch_cloudwatch_metric(
        cloudwatch, "AWS/RDS", "CPUUtilization", dims
    )
    connections = await fetch_cloudwatch_metric(
        cloudwatch, "AWS/RDS", "DatabaseConnections", dims
    )
    free_storage_bytes = await fetch_cloudwatch_metric(
        cloudwatch, "AWS/RDS", "FreeStorageSpace", dims
    )
    free_memory_bytes = await fetch_cloudwatch_metric(
        cloudwatch, "AWS/RDS", "FreeableMemory", dims
    )

    # Derive storage used from allocated − free.
    storage_used_gb: float | None = None
    if storage_limit_gb is not None and free_storage_bytes is not None:
        free_gb = free_storage_bytes / _GIB_TO_BYTES
        storage_used_gb = max(0.0, round(storage_limit_gb - free_gb, 4))

    # Memory percent: free / total_bytes — RDS doesn't expose total memory via CW,
    # so we leave it as None rather than invent a value.
    _ = free_memory_bytes  # captured but not used (no reliable total for pct calc)

    # Tags: RDS returns a list of {"Key": ..., "Value": ...} dicts.
    tags: dict[str, str] = {
        t["Key"]: t.get("Value", "")
        for t in instance.get("TagList", [])
        if "Key" in t
    }

    return DatabaseMetric(
        db_id=instance.get("DBInstanceArn", instance_id),
        db_name=instance.get("DBName", instance_id) or instance_id,
        db_type=db_type,
        server_name=server_name,
        region=instance.get("AvailabilityZone"),
        cpu_percent=cpu,
        storage_used_gb=storage_used_gb,
        storage_limit_gb=storage_limit_gb,
        active_connections=int(round(connections)) if connections is not None else None,
        is_available=instance.get("DBInstanceStatus", "") == "available",
        tags=tags,
    )
