"""Standard Check metrics — Azure Policy evaluations and AWS Config Rule results.

A ``StandardCheckMetric`` captures the evaluation result of a governance standard
check against a specific cloud resource.  Collecting these metrics enables:

- Computing a **Security Score** (% of COMPLIANT evaluations over a time window).
- Identifying **non-compliant resources** for remediation tracking.
- Monitoring **RGPD / SOX / ISO 27001 compliance** posture over time.

Data sources
------------
- **Azure Policy** (via PolicyInsights API):
  ``POST /subscriptions/{sub}/providers/Microsoft.PolicyInsights/policyStates/latest/queryResults``
  Filter recommended: ``complianceState eq 'NonCompliant'`` to reduce volume.

- **AWS Config Rules** (via Config API):
  ``config.get_compliance_details_by_config_rule(ConfigRuleName=...)``
  Iterate over all active Config Rules in the account.

Deduplication key
-----------------
``(check_id, resource_id, source_lz_id, evaluated_at)`` — same check / resource
pair can be evaluated multiple times (e.g. every 24h), so the timestamp is part
of the key.

Volume management
-----------------
At scale, a subscription may have thousands of evaluations.  Collectors should:
1. Collect **only non-compliant** evaluations in normal operation.
2. Collect **all** evaluations periodically (weekly) for full score computation.
3. Use ``tags`` to mark the collection strategy: ``{"scope": "non_compliant_only"}``.

Gold Layer
----------
Standard Check aggregation (score computation) is performed by a dedicated
Databricks Gold job before reaching the SERVING layer.  Unlike other domains,
records do **not** flow directly from CURATED to SERVING via the Aggregator.

Example::

    from dcm_commons.models.standard_check import StandardCheckMetric
    from dcm_commons.models.enums import StandardCheckState, CheckEffect
    from datetime import datetime, timezone

    metric = StandardCheckMetric(
        check_id="/subscriptions/fa5abbc4/providers/Microsoft.Authorization/policyDefinitions/abc",
        check_name="Require HTTPS on Storage Accounts",
        check_state=StandardCheckState.NON_COMPLIANT,
        resource_id="/subscriptions/fa5abbc4/resourceGroups/rg-data/providers/Microsoft.Storage/storageAccounts/stdata01",
        resource_name="stdata01",
        resource_type="Microsoft.Storage/storageAccounts",
        check_effect=CheckEffect.AUDIT,
        non_check_reasons=["Storage account does not enforce HTTPS-only traffic."],
        evaluated_at=datetime(2026, 3, 26, 0, 0, tzinfo=timezone.utc),
    )
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field, field_validator

from dcm_commons.models.base_metric import BaseMetricModel
from dcm_commons.models.enums import CheckEffect, StandardCheckState

__all__ = ["StandardCheckMetric"]


class StandardCheckMetric(BaseMetricModel):
    """Evaluation result of a standard check against a cloud resource.

    Attributes:
        check_id:           Azure Policy definition ID or AWS Config rule ARN.
        check_name:         Human-readable check / rule name.
        check_state:        Whether the resource satisfies the check.
        resource_id:        Full resource identifier (ARM ID or ARN).
        resource_name:      Short resource name for display.
        resource_type:      Resource type (e.g. ``Microsoft.Storage/storageAccounts``).
        check_effect:       Policy effect when non-compliant (Azure-specific).
                            ``None`` for AWS Config evaluations.
        non_check_reasons:  Free-text reasons explaining the non-compliance.
                            May be empty even for NON_COMPLIANT state.
        evaluated_at:       UTC timestamp of the standard check evaluation.
        tags:               Arbitrary key/value metadata (e.g. collection scope).
    """

    check_id: str = Field(
        ...,
        description="Azure Policy definition ID or AWS Config rule ARN.",
    )
    check_name: str
    check_state: StandardCheckState
    resource_id: str | None = None
    resource_name: str | None = None
    resource_type: str | None = None
    check_effect: CheckEffect | None = None
    non_check_reasons: list[str] = Field(default_factory=list)
    evaluated_at: datetime
    tags: dict[str, Any] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("evaluated_at", mode="before")
    @classmethod
    def _ensure_utc(cls, v: datetime) -> datetime:
        """Coerce naive datetimes to UTC."""
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"StandardCheckMetric("
            f"check={self.check_name!r}, "
            f"state={self.check_state}, "
            f"resource={self.resource_name!r})"
        )
