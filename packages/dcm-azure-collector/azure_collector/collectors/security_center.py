"""Azure Defender for Cloud (Security Center) collector — security alerts.

Retrieves active security alerts from Microsoft Defender for Cloud via the
``azure-mgmt-security`` SDK.  Only ``Active`` and ``InProgress`` alerts are
collected by default; resolved and dismissed alerts are skipped to reduce
payload size (they are already stored in Lakebase from previous collections).

Azure SDK used
--------------
``azure-mgmt-security`` (synchronous) — wrapped in :func:`run_sync`.

Key API calls
-------------
``client.alerts.list()``
    Returns all alerts associated with the subscription, regardless of status.

Ported from
-----------
``DatabricksPermissionsService.GetSecurityAlertsAsync()`` and
``DataFactoryGovernanceService.GetSecurityAlertsAsync()`` (POC C# backend)

Lakebase target
---------------
``dcm.monitoring.security_alerts``
"""

from __future__ import annotations

from datetime import timezone
from typing import Any

from azure.identity import DefaultAzureCredential  # type: ignore[import-untyped]
from azure.mgmt.security import SecurityCenter  # type: ignore[import-untyped]

from dcm_commons.collectors.base import BaseCollector
from dcm_commons.exceptions import CollectionError
from dcm_commons.logging_utils import get_logger
from dcm_commons.models.enums import AlertStatus, CloudProvider, MetricDomain
from dcm_commons.models.security import SecurityAlert

from azure_collector._azure_utils import (
    map_defender_severity,
    map_defender_status,
    run_sync,
)

__all__ = ["SecurityCenterCollector"]

_logger = get_logger(__name__)

# Statuses to collect (open / actively investigated).
# Resolved and Dismissed are excluded — they are already persisted.
_ACTIVE_STATUSES = frozenset({"active", "inprogress"})


class SecurityCenterCollector(BaseCollector):
    """Collects active security alerts from Microsoft Defender for Cloud.

    Args:
        source_lz_id:    Landing zone identifier.
        subscription_id: Azure subscription ID.
        credential:      ``azure.identity`` credential.  Defaults to
                         ``DefaultAzureCredential``.
        include_resolved: When ``True``, also collects ``Resolved`` and
                          ``Dismissed`` alerts.  Defaults to ``False``.
        max_retries:     Retry attempts on transient failures.
        retry_base_delay_seconds: Base delay for exponential back-off.
    """

    def __init__(
        self,
        source_lz_id: str,
        subscription_id: str,
        *,
        credential: Any | None = None,
        include_resolved: bool = False,
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
        self._include_resolved = include_resolved
        _credential = credential or DefaultAzureCredential()
        self._security_client = SecurityCenter(
            credential=_credential,
            subscription_id=subscription_id,
        )

    @property
    def domain(self) -> MetricDomain:
        """Return the security metric domain."""
        return MetricDomain.SECURITY

    async def _collect_metrics(self) -> list[dict[str, Any]]:
        """List all Defender for Cloud alerts and map them to :class:`SecurityAlert`.

        Returns:
            List of :class:`~dcm_commons.models.security.SecurityAlert` dicts.

        Raises:
            CollectionError: On SDK or authentication failures.
        """
        try:
            raw_alerts = await run_sync(lambda: list(self._security_client.alerts.list()))
        except Exception as exc:
            raise CollectionError(
                "SecurityCenterCollector",
                f"Failed to list Defender for Cloud alerts: {exc}",
            ) from exc

        _logger.debug("defender_raw_alerts_fetched", count=len(raw_alerts))

        metrics: list[dict[str, Any]] = []
        skipped = 0
        for alert in raw_alerts:
            mapped = _map_alert(alert)
            if mapped is None:
                skipped += 1
                continue

            # Filter by status unless include_resolved is set.
            if not self._include_resolved:
                status_str = str(mapped.status).lower()
                if status_str not in _ACTIVE_STATUSES:
                    skipped += 1
                    continue

            metrics.append(mapped.model_dump())

        _logger.info(
            "security_center_collection_done",
            total_alerts=len(raw_alerts),
            collected=len(metrics),
            skipped=skipped,
        )
        return metrics


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _map_alert(alert: Any) -> SecurityAlert | None:
    """Map a Defender for Cloud SDK alert object to a :class:`SecurityAlert`.

    Args:
        alert: Raw SDK ``Alert`` object from ``SecurityCenter.alerts.list()``.

    Returns:
        A :class:`SecurityAlert`, or ``None`` if the alert lacks a required field.
    """
    alert_id: str = getattr(alert, "name", "") or ""
    props = getattr(alert, "properties", None)
    if not alert_id or props is None:
        return None

    title: str = getattr(props, "alert_display_name", "") or ""
    if not title:
        return None

    # UTC timestamp when the alert was first detected.
    detected_at = getattr(props, "start_time_utc", None)
    if detected_at is None:
        return None
    if hasattr(detected_at, "tzinfo") and detected_at.tzinfo is None:
        detected_at = detected_at.replace(tzinfo=timezone.utc)

    # Remediation steps: Defender returns a list; join into a single string.
    remediation_steps: list[str] = getattr(props, "remediation_steps", []) or []
    remediation: str | None = "\n".join(remediation_steps) if remediation_steps else None

    # Resource information.
    resource_id: str | None = getattr(props, "compromised_entity", None)
    # Extended resource details (ARM resource ID).
    resource_identifiers = getattr(props, "resource_identifiers", []) or []
    arm_resource_id: str | None = None
    for ident in resource_identifiers:
        arm_id = getattr(ident, "azure_resource_id", None)
        if arm_id:
            arm_resource_id = arm_id
            break

    return SecurityAlert(
        alert_id=alert_id,
        title=title,
        description=getattr(props, "description", None),
        severity=map_defender_severity(getattr(props, "severity", None)),
        status=map_defender_status(getattr(props, "status", None)),
        detected_at=detected_at,
        resource_id=arm_resource_id,
        resource_name=resource_id,  # compromised_entity = human-readable name
        resource_type=getattr(props, "intent", None),  # attack intent as type proxy
        remediation=remediation,
        compromised_entity=resource_id,
    )
