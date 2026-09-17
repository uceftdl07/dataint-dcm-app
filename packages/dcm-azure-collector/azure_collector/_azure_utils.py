"""Internal utilities shared across all Azure collector implementations.

Not part of the public package API — import from ``azure_collector`` submodules,
not directly from this module.

Provides:
    - :func:`run_sync` — run a synchronous Azure SDK call in the thread pool.
    - :func:`get_mgmt_token` — acquire a management-plane bearer token.
    - :func:`get_databricks_token` — acquire a Databricks-scoped bearer token.
    - Status and severity mapping functions for normalising Azure API strings.
"""

from __future__ import annotations

import asyncio
import functools
from typing import Any

from dcm_commons.logging_utils import get_logger
from dcm_commons.models.enums import (
    AlertSeverity,
    AlertStatus,
    PipelineRunStatus,
    TriggerType,
)

_logger = get_logger(__name__)

_MGMT_SCOPE = "https://management.azure.com/.default"
_DATABRICKS_SCOPE = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default"

# ---------------------------------------------------------------------------
# Async / sync bridge
# ---------------------------------------------------------------------------

# Azure management SDK packages (azure-mgmt-*) are synchronous. They must not
# be called directly from an async context. run_sync() offloads them to the
# default ThreadPoolExecutor maintained by the running event loop.


async def run_sync(func: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a synchronous callable in the default thread-pool executor.

    Use this wrapper for every synchronous Azure SDK call (e.g. listing
    resources, querying Cost Management, fetching Monitor metrics) to keep
    the event loop unblocked.

    Args:
        func:     A synchronous callable (SDK method, built-in, or lambda).
        *args:    Positional arguments forwarded to ``func``.
        **kwargs: Keyword arguments forwarded to ``func``.

    Returns:
        The return value of ``func(*args, **kwargs)``.

    Example::

        factories = await run_sync(
            lambda: list(adf_client.factories.list(subscription_id))
        )
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))


async def get_mgmt_token(credential: Any) -> str:
    """Acquire an Azure management-plane bearer token (thread-pool safe).

    Args:
        credential: Any ``azure.identity`` credential object that implements
                    ``.get_token(scope)``.

    Returns:
        A valid bearer token string for ``https://management.azure.com/.default``.
    """
    _logger.info("azure_token_acquire_starting", scope=_MGMT_SCOPE, purpose="management")
    token_obj = await run_sync(credential.get_token, _MGMT_SCOPE)
    _logger.info("azure_token_acquire_succeeded", scope=_MGMT_SCOPE, purpose="management")
    return str(token_obj.token)


async def get_databricks_token(credential: Any) -> str:
    """Acquire a bearer token scoped to the Azure Databricks resource.

    The Databricks resource application ID ``2ff814a6-3304-4ab8-85cb-cd0e6f879c1d``
    is a fixed well-known value used by all Azure Databricks tenants.

    Args:
        credential: Any ``azure.identity`` credential object.

    Returns:
        A valid bearer token for the Databricks workspace REST API 2.0.
    """
    _logger.info(
        "azure_token_acquire_starting",
        scope=_DATABRICKS_SCOPE,
        purpose="databricks",
    )
    token_obj = await run_sync(credential.get_token, _DATABRICKS_SCOPE)
    _logger.info(
        "azure_token_acquire_succeeded",
        scope=_DATABRICKS_SCOPE,
        purpose="databricks",
    )
    return str(token_obj.token)


# ---------------------------------------------------------------------------
# ADF pipeline run status / trigger type mappers
# ---------------------------------------------------------------------------

_ADF_STATUS_MAP: dict[str, PipelineRunStatus] = {
    "Succeeded": PipelineRunStatus.SUCCEEDED,
    "Failed": PipelineRunStatus.FAILED,
    "InProgress": PipelineRunStatus.RUNNING,
    "Cancelling": PipelineRunStatus.RUNNING,   # still active during cancellation
    "Queued": PipelineRunStatus.QUEUED,
    "Cancelled": PipelineRunStatus.CANCELLED,
    "TimedOut": PipelineRunStatus.TIMED_OUT,
    "Skipped": PipelineRunStatus.SKIPPED,
}

_ADF_TRIGGER_MAP: dict[str, TriggerType] = {
    "ScheduleTrigger": TriggerType.SCHEDULED,
    "ManualTrigger": TriggerType.MANUAL,
    "BlobEventsTrigger": TriggerType.EVENT,
    "CustomEventsTrigger": TriggerType.EVENT,
    "ChainingTrigger": TriggerType.DEPENDENCY,
    "RerunTrigger": TriggerType.DEPENDENCY,
}


def map_adf_status(raw: str | None) -> PipelineRunStatus:
    """Map an ADF pipeline run status string to :class:`~dcm_commons.models.enums.PipelineRunStatus`.

    Unknown values fall back to ``RUNNING`` (conservative — avoids premature
    terminal classification of an in-flight run).

    Args:
        raw: Status string from the ADF API (e.g. ``"Succeeded"``, ``"Failed"``).

    Returns:
        The corresponding :class:`PipelineRunStatus` value.
    """
    return _ADF_STATUS_MAP.get(raw or "", PipelineRunStatus.RUNNING)


def map_adf_trigger(raw: str | None) -> TriggerType:
    """Map an ADF triggered-by type string to :class:`~dcm_commons.models.enums.TriggerType`.

    Args:
        raw: Trigger type from ``run.triggered_by.trigger_type``
             (e.g. ``"ScheduleTrigger"``).

    Returns:
        The corresponding :class:`TriggerType` value.
    """
    return _ADF_TRIGGER_MAP.get(raw or "", TriggerType.UNKNOWN)


# ---------------------------------------------------------------------------
# Defender for Cloud severity / status mappers
# ---------------------------------------------------------------------------

_DEFENDER_SEVERITY_MAP: dict[str, AlertSeverity] = {
    "High": AlertSeverity.HIGH,
    "Medium": AlertSeverity.MEDIUM,
    "Low": AlertSeverity.LOW,
    "Informational": AlertSeverity.INFORMATIONAL,
}

_DEFENDER_STATUS_MAP: dict[str, AlertStatus] = {
    "Active": AlertStatus.ACTIVE,
    "InProgress": AlertStatus.IN_PROGRESS,
    "Resolved": AlertStatus.RESOLVED,
    "Dismissed": AlertStatus.DISMISSED,
}


def map_defender_severity(raw: str | None) -> AlertSeverity:
    """Map a Defender for Cloud severity string to :class:`~dcm_commons.models.enums.AlertSeverity`.

    Args:
        raw: Severity string (e.g. ``"High"``, ``"Medium"``).

    Returns:
        The corresponding :class:`AlertSeverity`, defaulting to ``INFORMATIONAL``.
    """
    return _DEFENDER_SEVERITY_MAP.get(raw or "", AlertSeverity.INFORMATIONAL)


def map_defender_status(raw: str | None) -> AlertStatus:
    """Map a Defender for Cloud alert status to :class:`~dcm_commons.models.enums.AlertStatus`.

    Args:
        raw: Status string (e.g. ``"Active"``, ``"Resolved"``).

    Returns:
        The corresponding :class:`AlertStatus`, defaulting to ``ACTIVE``.
    """
    return _DEFENDER_STATUS_MAP.get(raw or "", AlertStatus.ACTIVE)
