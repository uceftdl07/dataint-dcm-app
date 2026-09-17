"""Cost and FinOps metrics — Azure Cost Management and AWS Cost Explorer.

Produced by:
    - ``dcm_azure_collector.collectors.cost_management.CostManagementCollector``
    - ``dcm_aws_collector.collectors.cost_explorer.CostExplorerCollector``

Stored in Lakebase under: ``dcm.monitoring.cost_daily``

Each ``CostMetric`` represents a daily cost aggregation for one cloud service
or resource group.  Budget fields are optional and populated when the source API
exposes them alongside the cost data.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field, ValidationInfo, field_validator

from dcm_commons.models.base_metric import BaseMetricModel

__all__ = ["CostMetric"]


class CostMetric(BaseMetricModel):
    """Daily cost aggregation for a cloud service or resource group.

    Attributes:
        service_name:               Name of the cloud service
                                    (e.g. ``"Azure Data Factory"`` or ``"AWS Glue"``).
        resource_group:             Azure resource group name, or AWS cost allocation
                                    tag value.  ``None`` when cost is subscription-wide.
        subscription_or_account_id: Azure subscription ID or AWS account ID.
        period_start:               Start date (inclusive) of the billing period.
        period_end:                 End date (inclusive) of the billing period.
                                    Must be ≥ ``period_start``.
        cost_usd:                   Actual cost in USD for the period.
                                    Always ≥ 0; credits may reduce cost toward 0.
        currency:                   Original billing currency code (ISO 4217,
                                    e.g. ``"USD"``, ``"EUR"``).
        budget_name:                Name of the associated budget, if any.
        budget_limit_usd:           Total budget limit in USD.
        budget_consumed_pct:        Percentage of budget consumed (0–100).
                                    Values > 100 indicate budget overrun.
        tags:                       Cost allocation tags as key/value strings.
    """

    service_name: str = Field(
        ...,
        description="Cloud service name (e.g. 'Azure Data Factory', 'AWS Glue').",
    )
    resource_group: str | None = Field(
        default=None,
        description="Resource group (Azure) or cost allocation tag value (AWS).",
    )
    subscription_or_account_id: str = Field(
        ...,
        description="Azure subscription ID or AWS account ID.",
    )
    period_start: date = Field(
        ...,
        description="Start date (inclusive) of the billing period.",
    )
    period_end: date = Field(
        ...,
        description="End date (inclusive) of the billing period.",
    )
    cost_usd: float = Field(
        ...,
        ge=0.0,
        description="Actual cost in USD for the period.",
    )
    currency: str = Field(
        default="USD",
        description="Original billing currency code (ISO 4217).",
    )
    budget_name: str | None = Field(
        default=None,
        description="Name of the associated budget, if any.",
    )
    budget_limit_usd: float | None = Field(
        default=None,
        ge=0.0,
        description="Total budget limit in USD.",
    )
    budget_consumed_pct: float | None = Field(
        default=None,
        ge=0.0,
        description="Percentage of budget consumed (0–100; >100 means overrun).",
    )
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Cost allocation tags.",
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("period_end")
    @classmethod
    def _period_end_not_before_start(cls, v: date, info: ValidationInfo) -> date:
        """Reject payloads where ``period_end`` precedes ``period_start``."""
        start: date | None = info.data.get("period_start")
        if start is not None and v < start:
            raise ValueError(
                f"period_end ({v}) must be greater than or equal to period_start ({start})."
            )
        return v
