"""Internal utilities shared across all AWS collector implementations.

Not part of the public package API — import from ``aws_collector`` submodules,
not directly from this module.

Provides:
    - :func:`run_sync` — run a synchronous boto3 call in the thread pool.
    - :func:`fetch_cloudwatch_metric` — retrieve the most recent average for
      a single CloudWatch metric over a time window.
    - Status mapping functions for normalising boto3 API strings to DCM enums.
"""

from __future__ import annotations

import asyncio
import functools
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]

from dcm_commons.models.enums import (
    ComputeState,
    DatabaseType,
    PipelineRunStatus,
)

_BOTO_CONNECT_TIMEOUT_SECONDS: int = 5
_BOTO_RETRY_MAX_ATTEMPTS: int = 2


def create_aws_client(service_name: str, *, region_name: str) -> Any:
    """Create a boto3 client with bounded connection timeout and retries.

    This keeps collector startup/API failures fast when network connectivity
    to AWS endpoints is unavailable inside a landing zone.
    """
    cfg = Config(
        connect_timeout=_BOTO_CONNECT_TIMEOUT_SECONDS,
        retries={"max_attempts": _BOTO_RETRY_MAX_ATTEMPTS, "mode": "standard"},
    )
    return boto3.client(service_name, region_name=region_name, config=cfg)

# ---------------------------------------------------------------------------
# Async / sync bridge
# ---------------------------------------------------------------------------

# All boto3 clients are synchronous.  run_sync() offloads each call to the
# default ThreadPoolExecutor so the asyncio event loop stays unblocked.


async def run_sync(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a synchronous callable in the default thread-pool executor.

    Use this wrapper for every synchronous boto3 call (listing resources,
    querying CloudWatch, fetching Cost Explorer data) to keep the event loop
    unblocked.

    Args:
        func:     A synchronous callable (boto3 method, built-in, or lambda).
        *args:    Positional arguments forwarded to ``func``.
        **kwargs: Keyword arguments forwarded to ``func``.

    Returns:
        The return value of ``func(*args, **kwargs)``.

    Example::

        jobs = await run_sync(lambda: glue_client.get_jobs())
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))


# ---------------------------------------------------------------------------
# CloudWatch metric helper
# ---------------------------------------------------------------------------

# Default look-back window for CloudWatch metric queries.
_CW_WINDOW_MINUTES: int = 15


async def fetch_cloudwatch_metric(
    cloudwatch_client: Any,
    namespace: str,
    metric_name: str,
    dimensions: list[dict[str, str]],
    *,
    window_minutes: int = _CW_WINDOW_MINUTES,
    period_seconds: int = 300,
) -> float | None:
    """Fetch the most recent Average value of a CloudWatch metric.

    Queries ``GetMetricStatistics`` for the given namespace / metric / dimensions
    and returns the single most recent average data point, or ``None`` when no
    data is available (resource too new, metric not published yet, etc.).

    Args:
        cloudwatch_client: A synchronous boto3 CloudWatch client.
        namespace:         CloudWatch metric namespace
                           (e.g. ``"AWS/RDS"``, ``"AWS/Redshift"``).
        metric_name:       Metric name (e.g. ``"CPUUtilization"``).
        dimensions:        List of ``{"Name": str, "Value": str}`` dicts that
                           identify the specific resource.
        window_minutes:    How far back to look (default: 15 minutes).
        period_seconds:    Aggregation period in seconds (default: 300 = 5 min).

    Returns:
        The most recent average value as a ``float``, or ``None`` if no
        data points were returned or if the SDK call fails.
    """
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=window_minutes)

    try:
        response = await run_sync(
            cloudwatch_client.get_metric_statistics,
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=dimensions,
            StartTime=start_time,
            EndTime=end_time,
            Period=period_seconds,
            Statistics=["Average"],
        )
    except Exception:
        return None

    datapoints: list[dict[str, Any]] = response.get("Datapoints", [])
    if not datapoints:
        return None

    # Datapoints are not guaranteed to be in chronological order.
    latest = max(datapoints, key=lambda d: d["Timestamp"])
    return float(latest.get("Average", 0.0))


# ---------------------------------------------------------------------------
# AWS Glue — job run status mapper
# ---------------------------------------------------------------------------

_GLUE_STATUS_MAP: dict[str, PipelineRunStatus] = {
    "STARTING":  PipelineRunStatus.RUNNING,
    "RUNNING":   PipelineRunStatus.RUNNING,
    "STOPPING":  PipelineRunStatus.RUNNING,   # still active
    "WAITING":   PipelineRunStatus.QUEUED,
    "SUCCEEDED": PipelineRunStatus.SUCCEEDED,
    "FAILED":    PipelineRunStatus.FAILED,
    "TIMEOUT":   PipelineRunStatus.TIMED_OUT,
    "STOPPED":   PipelineRunStatus.CANCELLED,
    "ERROR":     PipelineRunStatus.FAILED,
}

_GLUE_CRAWLER_STATUS_MAP: dict[str, PipelineRunStatus] = {
    "SUCCEEDED": PipelineRunStatus.SUCCEEDED,
    "FAILED":    PipelineRunStatus.FAILED,
    "CANCELLED": PipelineRunStatus.CANCELLED,
}


def map_glue_job_status(raw: str | None) -> PipelineRunStatus:
    """Map an AWS Glue job run state string to :class:`~dcm_commons.models.enums.PipelineRunStatus`.

    Args:
        raw: Glue job run state (e.g. ``"SUCCEEDED"``, ``"FAILED"``).

    Returns:
        The corresponding :class:`PipelineRunStatus`, defaulting to ``RUNNING``.
    """
    return _GLUE_STATUS_MAP.get((raw or "").upper(), PipelineRunStatus.RUNNING)


def map_glue_crawler_status(raw: str | None) -> PipelineRunStatus:
    """Map an AWS Glue crawler last-crawl status to :class:`PipelineRunStatus`.

    Args:
        raw: Glue crawler last-crawl status string (e.g. ``"SUCCEEDED"``).

    Returns:
        The corresponding :class:`PipelineRunStatus`, defaulting to ``SUCCEEDED``.
    """
    return _GLUE_CRAWLER_STATUS_MAP.get((raw or "").upper(), PipelineRunStatus.SUCCEEDED)


# ---------------------------------------------------------------------------
# Amazon EMR — cluster state mapper
# ---------------------------------------------------------------------------

_EMR_STATE_MAP: dict[str, ComputeState] = {
    "STARTING":               ComputeState.STARTING,
    "BOOTSTRAPPING":          ComputeState.STARTING,
    "RUNNING":                ComputeState.RUNNING,
    "WAITING":                ComputeState.RUNNING,     # idle but alive
    "TERMINATING":            ComputeState.TERMINATING,
    "TERMINATED":             ComputeState.TERMINATED,
    "TERMINATED_WITH_ERRORS": ComputeState.ERROR,
}


def map_emr_state(raw: str | None) -> ComputeState:
    """Map an EMR cluster state string to :class:`~dcm_commons.models.enums.ComputeState`.

    Args:
        raw: EMR cluster state (e.g. ``"RUNNING"``, ``"TERMINATED_WITH_ERRORS"``).

    Returns:
        The corresponding :class:`ComputeState`, defaulting to ``UNKNOWN``.
    """
    return _EMR_STATE_MAP.get((raw or "").upper(), ComputeState.UNKNOWN)


# ---------------------------------------------------------------------------
# Amazon RDS — engine type mapper
# ---------------------------------------------------------------------------


def map_rds_engine(engine: str | None) -> DatabaseType:
    """Map an RDS/Aurora engine identifier to :class:`~dcm_commons.models.enums.DatabaseType`.

    RDS engine identifiers include version suffixes (e.g. ``"aurora-mysql"``
    or ``"sqlserver-se"``).  The mapping is prefix/substring based.

    Args:
        engine: RDS engine string from ``describe_db_instances``
                (e.g. ``"mysql"``, ``"aurora-postgresql"``, ``"sqlserver-se"``).

    Returns:
        The corresponding :class:`DatabaseType`, defaulting to ``POSTGRESQL``.
    """
    e = (engine or "").lower()
    if e.startswith("aurora"):
        return DatabaseType.RDS_AURORA
    if "sqlserver" in e:
        return DatabaseType.SQLSERVER
    if "mysql" in e:
        return DatabaseType.MYSQL
    if "mariadb" in e:
        return DatabaseType.MYSQL
    if "postgres" in e:
        return DatabaseType.POSTGRESQL
    return DatabaseType.POSTGRESQL  # safe default
