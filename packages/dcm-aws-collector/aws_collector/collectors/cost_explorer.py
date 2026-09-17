"""AWS Cost Explorer collector — daily costs by service and budget utilisation.

Queries the AWS Cost Explorer API for the last ``lookback_days`` of cost
data grouped by service, then enriches each row with matching budget
information from the AWS Budgets API.

Key API calls
-------------
``ce.get_cost_and_usage(TimePeriod, Granularity="MONTHLY", GroupBy=[SERVICE])``
    Costs aggregated by service for the configured look-back period.
``budgets.describe_budgets(AccountId=...)``
    All budgets defined in the account, with current spend and limit.
``sts.get_caller_identity()``
    Resolve the current AWS account ID (needed by the Budgets API).

Note on region
--------------
The Cost Explorer API endpoint is **global** and must be called against
``us-east-1`` regardless of which region is being monitored.  The boto3
client is explicitly created in ``us-east-1`` for this reason.

Lakebase target
---------------
``dcm.monitoring.cost_daily``
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from dcm_commons.collectors.base import BaseCollector
from dcm_commons.exceptions import CollectionError
from dcm_commons.logging_utils import get_logger
from dcm_commons.models.cost import CostMetric
from dcm_commons.models.enums import CloudProvider, MetricDomain

from aws_collector._aws_utils import create_aws_client, run_sync

__all__ = ["CostExplorerCollector"]

_logger = get_logger(__name__)

# Cost Explorer API must be called from us-east-1 (it is a global service).
_CE_REGION: str = "us-east-1"


class CostExplorerCollector(BaseCollector):
    """Collects AWS costs by service and budget utilisation.

    Retrieves monthly cost aggregations for the configured look-back window
    and enriches each service row with a matching budget when one exists
    (case-insensitive name match).

    Args:
        source_lz_id:      Landing zone identifier.
        aws_region:        AWS region of the monitored account.  Used for the
                           Budgets API and STS; Cost Explorer always goes to
                           ``us-east-1``.
        lookback_days:     Number of days of cost history to retrieve (default 30).
        max_retries:       Retry attempts on transient failures.
        retry_base_delay_seconds: Base delay for exponential back-off.
    """

    def __init__(
        self,
        source_lz_id: str,
        aws_region: str,
        *,
        lookback_days: int = 30,
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
        self._aws_region = aws_region
        self._lookback_days = lookback_days
        # Cost Explorer is a global service — always us-east-1.
        self._ce = create_aws_client("ce", region_name=_CE_REGION)
        self._budgets = create_aws_client("budgets", region_name=aws_region)
        self._sts = create_aws_client("sts", region_name=aws_region)

    @property
    def domain(self) -> MetricDomain:
        """Return the cost metric domain."""
        return MetricDomain.COST

    async def _collect_metrics(self) -> list[dict[str, Any]]:
        """Retrieve costs by service and enrich with budget data.

        Returns:
            List of :class:`~dcm_commons.models.cost.CostMetric` dicts.

        Raises:
            CollectionError: On Cost Explorer API or authentication failures.
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=self._lookback_days)

        # Resolve account ID for the Budgets API.
        account_id = await _get_account_id(self._sts)

        try:
            cost_rows = await _query_costs(self._ce, start_date, end_date)
        except Exception as exc:
            raise CollectionError(
                "CostExplorerCollector",
                f"Failed to query Cost Explorer: {exc}",
            ) from exc

        budgets = await _query_budgets(self._budgets, account_id)

        metrics = _build_cost_metrics(
            cost_rows=cost_rows,
            budgets=budgets,
            account_id=account_id,
            period_start=start_date,
            period_end=end_date,
        )

        _logger.info(
            "cost_explorer_collection_done",
            service_count=len(cost_rows),
            budget_count=len(budgets),
            metric_count=len(metrics),
        )
        return [m.model_dump() for m in metrics]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _get_account_id(sts: Any) -> str:
    """Resolve the current AWS account ID via STS.

    Args:
        sts: boto3 STS client.

    Returns:
        The 12-digit AWS account ID string, or empty string on failure.
    """
    try:
        response = await run_sync(sts.get_caller_identity)
        return response.get("Account", "")
    except Exception as exc:
        _logger.warning("cost_explorer_sts_failed", reason=str(exc))
        return ""


async def _query_costs(
    ce: Any,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Query Cost Explorer for costs grouped by service name.

    Args:
        ce:         boto3 Cost Explorer client.
        start_date: First day of the billing window (inclusive).
        end_date:   Last day of the billing window (exclusive in CE format).

    Returns:
        List of ``{"service_name": str, "cost_usd": float}`` dicts.

    Raises:
        Exception: Propagated from the SDK call (caught in caller).
    """
    response = await run_sync(
        ce.get_cost_and_usage,
        TimePeriod={
            "Start": start_date.isoformat(),
            "End": end_date.isoformat(),
        },
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )

    rows: list[dict[str, Any]] = []
    for result_by_time in response.get("ResultsByTime", []):
        for group in result_by_time.get("Groups", []):
            service_name: str = group["Keys"][0] if group.get("Keys") else ""
            cost_str: str = (
                group.get("Metrics", {}).get("UnblendedCost", {}).get("Amount", "0")
            )
            try:
                cost_usd = float(cost_str)
            except (ValueError, TypeError):
                cost_usd = 0.0

            if service_name:
                rows.append({"service_name": service_name, "cost_usd": cost_usd})

    return rows


async def _query_budgets(
    budgets_client: Any,
    account_id: str,
) -> list[dict[str, Any]]:
    """Retrieve all AWS Budgets for the account.

    Args:
        budgets_client: boto3 Budgets client.
        account_id:     12-digit AWS account ID.

    Returns:
        List of ``{"name": str, "limit_usd": float, "current_spend_usd": float}``
        dicts.  Returns empty list on any error (budget data is best-effort).
    """
    if not account_id:
        return []

    try:
        response = await run_sync(
            budgets_client.describe_budgets,
            AccountId=account_id,
        )
    except Exception as exc:
        _logger.warning("cost_explorer_budgets_failed", reason=str(exc))
        return []

    result: list[dict[str, Any]] = []
    for budget in response.get("Budgets", []):
        name: str = budget.get("BudgetName", "")
        limit: float = float(
            budget.get("BudgetLimit", {}).get("Amount", 0.0) or 0.0
        )
        spend: float = float(
            budget.get("CalculatedSpend", {})
            .get("ActualSpend", {})
            .get("Amount", 0.0)
            or 0.0
        )
        if name:
            result.append({"name": name, "limit_usd": limit, "current_spend_usd": spend})

    return result


def _build_cost_metrics(
    cost_rows: list[dict[str, Any]],
    budgets: list[dict[str, Any]],
    account_id: str,
    period_start: date,
    period_end: date,
) -> list[CostMetric]:
    """Build :class:`~dcm_commons.models.cost.CostMetric` instances.

    Enriches each service cost row with matching budget information when
    a budget name matches the service name (case-insensitive).

    Args:
        cost_rows:    List of ``{"service_name", "cost_usd"}`` dicts.
        budgets:      List of ``{"name", "limit_usd", "current_spend_usd"}`` dicts.
        account_id:   AWS account ID embedded in each metric.
        period_start: Start date of the billing window.
        period_end:   End date of the billing window.

    Returns:
        List of :class:`CostMetric` instances ready for ``model_dump()``.
    """
    subscription_budget = budgets[0] if len(budgets) == 1 else None
    budget_map = {b["name"].lower(): b for b in budgets}
    metrics: list[CostMetric] = []

    for row in cost_rows:
        service_name: str = row["service_name"]
        cost_usd: float = row["cost_usd"]

        budget = budget_map.get(service_name.lower()) or subscription_budget
        budget_name: str | None = None
        budget_limit: float | None = None
        budget_pct: float | None = None

        if budget and budget["limit_usd"] > 0:
            budget_name = budget["name"]
            budget_limit = budget["limit_usd"]
            budget_pct = (budget["current_spend_usd"] / budget["limit_usd"]) * 100.0

        metrics.append(
            CostMetric(
                service_name=service_name,
                subscription_or_account_id=account_id,
                period_start=period_start,
                period_end=period_end,
                cost_usd=max(0.0, cost_usd),
                budget_name=budget_name,
                budget_limit_usd=budget_limit,
                budget_consumed_pct=budget_pct,
            )
        )

    return metrics
