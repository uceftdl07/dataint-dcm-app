"""Security alert metrics — Azure Defender for Cloud and AWS GuardDuty.

Produced by:
    - ``dcm_azure_collector.collectors.security.DefenderCollector``
    - ``dcm_aws_collector.collectors.guardduty.GuardDutyCollector``

Stored in Lakebase under: ``dcm.monitoring.security_alerts``

Each ``SecurityAlert`` represents a single security finding.  Collectors poll
the provider's alert APIs on each collection cycle and emit one record per open
or recently-updated alert.

Note on deduplication:
    The Databricks pipeline uses ``alert_id`` as the primary key for UPSERT
    operations.  A repeated collection of the same alert with an updated
    ``status`` will overwrite the previous record rather than create a duplicate.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from dcm_commons.models.base_metric import BaseMetricModel
from dcm_commons.models.enums import AlertSeverity, AlertStatus

__all__ = ["SecurityAlert"]


class SecurityAlert(BaseMetricModel):
    """A security finding from Azure Defender for Cloud or AWS GuardDuty.

    Attributes:
        alert_id:           Provider-assigned unique alert identifier.
                            Defender: ``alert.name`` (GUID).
                            GuardDuty: ``finding.id``.
        title:              Short, human-readable alert title as supplied by the
                            provider (max ~200 characters).
        description:        Extended description of the security finding.
                            May include attack chain context or threat intelligence.
        severity:           Criticality level of the alert.
        status:             Current disposition.  Defaults to ``ACTIVE`` for
                            newly detected alerts; updated by SOC investigation.
        detected_at:        UTC timestamp when the alert was first detected by the
                            provider (not when it was collected by DCM).
        resource_id:        Full cloud resource identifier that triggered the alert.
                            ARM resource ID (Azure) or AWS ARN (AWS).
        resource_name:      Human-readable resource name extracted from the ID.
        resource_type:      Cloud resource type string
                            (e.g. ``"Microsoft.Sql/servers"`` or
                            ``"AWS::S3::Bucket"``).
        remediation:        Provider-suggested remediation steps or documentation
                            link.  ``None`` when not provided by the source API.
        compromised_entity: Entity identified as compromised (IP address, username,
                            resource name).  Sourced from the alert's
                            ``compromisedEntity`` field (Defender) or
                            GuardDuty ``resource`` field.
        tags:               Provider resource tags from the affected resource.
    """

    alert_id: str = Field(..., description="Provider-assigned unique alert identifier.")
    title: str = Field(..., description="Short, human-readable alert title.")
    description: str | None = Field(
        default=None,
        description="Extended description of the security finding.",
    )
    severity: AlertSeverity
    status: AlertStatus = Field(
        default=AlertStatus.ACTIVE,
        description="Current disposition of the alert.",
    )
    detected_at: datetime = Field(
        ...,
        description="UTC timestamp when the alert was first detected by the provider.",
    )
    resource_id: str | None = Field(
        default=None,
        description="Full cloud resource identifier (ARM resource ID or ARN).",
    )
    resource_name: str | None = Field(
        default=None,
        description="Human-readable resource name.",
    )
    resource_type: str | None = Field(
        default=None,
        description="Cloud resource type string.",
    )
    remediation: str | None = Field(
        default=None,
        description="Provider-suggested remediation steps or documentation link.",
    )
    compromised_entity: str | None = Field(
        default=None,
        description="Entity identified as compromised (IP, username, resource name).",
    )
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Provider resource tags from the affected resource.",
    )
