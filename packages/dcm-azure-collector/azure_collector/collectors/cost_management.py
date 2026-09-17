"""Azure Cost Management collector — daily costs by service and budget utilisation.

Queries the Cost Management REST API directly with ``httpx`` (async), mirroring
the approach used in the C# POC ``AzureCostManagementService.cs``.

Key API calls
-------------
``POST .../Microsoft.CostManagement/query``
    Retrieve actual costs grouped by ``ServiceName`` for the last 30 days.
``GET .../Microsoft.Consumption/budgets``
    Retrieve all budgets associated with the subscription.

Rate limiting
-------------
The Cost Management API enforces per-subscription request quotas.  The
collector backs off automatically on HTTP 429 via the ``max_retries`` policy
inherited from :class:`~dcm_commons.collectors.base.BaseCollector`.

Ported from
-----------
``AzureCostManagementService.cs`` (POC C# backend)

Lakebase target
---------------
``dcm.monitoring.cost_daily``
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from azure.identity import DefaultAzureCredential  # type: ignore[import-untyped]

from dcm_commons.collectors.base import BaseCollector
from dcm_commons.exceptions import CollectionError
from dcm_commons.logging_utils import get_logger
from dcm_commons.models.cost import CostMetric
from dcm_commons.models.enums import CloudProvider, MetricDomain

from azure_collector._azure_utils import get_mgmt_token

__all__ = ["CostManagementCollector"]

_logger = get_logger(__name__)

_MGMT_BASE = "https://management.azure.com"
_COST_API_VERSION = "2023-11-01"
_BUDGET_API_VERSION = "2023-11-01"
_COST_LOOKBACK_DAYS = 30
_REQUEST_TIMEOUT = 60.0  # Cost Management API can be slow under load


class CostManagementCollector(BaseCollector):
    """Collects daily cost data and budget utilisation from Azure Cost Management.

    Uses the REST API directly (not the azure-mgmt-costmanagement SDK) for full
    control over the query body and consistent behaviour with the C# POC.

    Args:
        source_lz_id:    Landing zone identifier.
        subscription_id: Azure subscription ID.
        credential:      ``azure.identity`` credential.  Defaults to
                         ``DefaultAzureCredential``.
        lookback_days:   Number of days of cost history to retrieve.
                         Defaults to 30.
    """

    def __init__(
        self,
        source_lz_id: str,
        subscription_id: str,
        *,
        credential: Any | None = None,
        lookback_days: int = _COST_LOOKBACK_DAYS,
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
        self._lookback_days = lookback_days
        self._credential = credential or DefaultAzureCredential()

    @property
    def domain(self) -> MetricDomain:
        """Return the cost metric domain."""
        return MetricDomain.COST

    async def _collect_metrics(self) -> list[dict[str, Any]]:
        """Retrieve costs by service and budget utilisation.

        Returns:
            List of :class:`~dcm_commons.models.cost.CostMetric` dicts.

        Raises:
            CollectionError: On authentication failure or non-retriable API errors.
        """
        _logger.info(
            "cost_management_collect_starting",
            subscription_id=self._subscription_id,
            lookback_days=self._lookback_days,
        )
        token = await get_mgmt_token(self._credential)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        end_date = date.today()
        start_date = end_date - timedelta(days=self._lookback_days)

        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as http:
            _logger.info(
                "cost_management_query_costs_starting",
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
            )
            costs = await _query_costs_by_service(
                http, headers, self._subscription_id, start_date, end_date
            )
            _logger.info(
                "cost_management_query_costs_done",
                service_row_count=len(costs),
            )
            _logger.info("cost_management_query_budgets_starting")
            budgets = await _query_budgets(http, headers, self._subscription_id)
            _logger.info(
                "cost_management_query_budgets_done",
                budget_count=len(budgets),
            )

        metrics = _build_cost_metrics(
            costs=costs,
            budgets=budgets,
            subscription_id=self._subscription_id,
            period_start=start_date,
            period_end=end_date,
        )

        _logger.info(
            "cost_management_collection_done",
            service_count=len(costs),
            budget_count=len(budgets),
            metric_count=len(metrics),
        )
        return [m.model_dump() for m in metrics]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _query_costs_by_service(
    http: httpx.AsyncClient,
    headers: dict[str, str],
    subscription_id: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """POST a Cost Management query to retrieve costs grouped by ServiceName.

    Args:
        http:            Shared ``httpx.AsyncClient``.
        headers:         Request headers including the bearer token.
        subscription_id: Azure subscription ID.
        start_date:      Start of the billing period (inclusive).
        end_date:        End of the billing period (inclusive).

    Returns:
        List of row dicts, each with keys ``service_name`` and ``cost_usd``.

    Raises:
        CollectionError: On HTTP errors or unexpected response shape.
    """
    url = (
        f"{_MGMT_BASE}/subscriptions/{subscription_id}"
        f"/providers/Microsoft.CostManagement/query"
        f"?api-version={_COST_API_VERSION}"
    )
    body = {
        "type": "ActualCost",
        "timeframe": "Custom",
        "timePeriod": {
            "from": start_date.isoformat(),
            "to": end_date.isoformat(),
        },
        "dataset": {
            "granularity": "None",
            "aggregation": {
                "totalCost": {"name": "Cost", "function": "Sum"},
            },
            "grouping": [
                {"type": "Dimension", "name": "ServiceName"},
                {"type": "Dimension", "name": "ResourceGroup"},
            ],
        },
    }

    try:
        response = await http.post(url, json=body, headers=headers)
    except httpx.RequestError as exc:
        raise CollectionError(
            "CostManagementCollector",
            f"Network error querying Cost Management: {exc}",
        ) from exc

    if response.status_code == 429:
        raise CollectionError(
            "CostManagementCollector",
            "Cost Management API rate-limited (HTTP 429) — will retry.",
        )
    if not response.is_success:
        raise CollectionError(
            "CostManagementCollector",
            f"Cost Management query failed: HTTP {response.status_code} — {response.text[:300]}",
        )

    data = response.json()
    return _parse_cost_query_response(data)


def _parse_cost_query_response(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract service-name → cost pairs from a Cost Management query response.

    The API returns a column-based result set::

        {
            "properties": {
                "columns": [{"name": "Cost"}, {"name": "ServiceName"}],
                "rows": [[12.5, "Azure Data Factory"], ...]
            }
        }

    Args:
        data: Parsed JSON response from the Cost Management API.

    Returns:
        List of dicts with ``service_name`` (str) and ``cost_usd`` (float).
    """
    properties = data.get("properties", {})
    columns: list[dict[str, Any]] = properties.get("columns", [])
    rows: list[list[Any]] = properties.get("rows", [])

    col_names = [c.get("name", "").lower() for c in columns]
    cost_idx = next((i for i, n in enumerate(col_names) if n == "cost"), None)
    svc_idx = next((i for i, n in enumerate(col_names) if n == "servicename"), None)
    rg_idx = next(
        (i for i, n in enumerate(col_names) if n in {"resourcegroup", "resourcegroupname"}),
        None,
    )

    if cost_idx is None or svc_idx is None:
        _logger.warning("cost_management_unexpected_columns", columns=col_names)
        return []

    results = []
    for row in rows:
        try:
            resource_group = None
            if rg_idx is not None and row[rg_idx] not in (None, "", "Unassigned"):
                resource_group = str(row[rg_idx])
            results.append(
                {
                    "service_name": str(row[svc_idx]),
                    "resource_group": resource_group,
                    "cost_usd": float(row[cost_idx]),
                }
            )
        except (IndexError, ValueError, TypeError):
            continue
    return results


async def _query_budgets(
    http: httpx.AsyncClient,
    headers: dict[str, str],
    subscription_id: str,
) -> list[dict[str, Any]]:
    """Retrieve all budgets defined for the subscription.

    Args:
        http:            Shared ``httpx.AsyncClient``.
        headers:         Request headers.
        subscription_id: Azure subscription ID.

    Returns:
        List of budget dicts with ``name``, ``limit_usd``, and ``current_spend_usd``.
    """
    url = (
        f"{_MGMT_BASE}/subscriptions/{subscription_id}"
        f"/providers/Microsoft.Consumption/budgets"
        f"?api-version={_BUDGET_API_VERSION}"
    )

    try:
        response = await http.get(url, headers=headers)
    except httpx.RequestError as exc:
        _logger.warning("cost_management_budgets_network_error", reason=str(exc))
        return []

    if not response.is_success:
        _logger.warning(
            "cost_management_budgets_failed",
            status_code=response.status_code,
        )
        return []

    data = response.json()
    budgets = []
    for item in data.get("value", []):
        props = item.get("properties", {})
        filters = _parse_budget_filters(props)
        budgets.append(
            {
                "name": item.get("name", ""),
                "limit_usd": float(props.get("amount", 0.0)),
                "current_spend_usd": float(
                    props.get("currentSpend", {}).get("amount", 0.0)
                ),
                "filters": filters,
            }
        )
    if budgets:
        _logger.info(
            "cost_management_budgets_loaded",
            budget_names=[b["name"] for b in budgets],
            scoped_budgets=sum(
                1
                for b in budgets
                if b["filters"]["service_names"] or b["filters"]["resource_groups"]
            ),
        )
    return budgets


def _parse_budget_filters(props: dict[str, Any]) -> dict[str, list[str]]:
    """Extract ServiceName / ResourceGroup filters from an Azure budget payload."""
    service_names: list[str] = []
    resource_groups: list[str] = []

    def _collect(node: Any) -> None:
        if not isinstance(node, dict):
            return
        dimensions = node.get("dimensions")
        if isinstance(dimensions, dict):
            name = str(dimensions.get("name", "")).lower()
            values = dimensions.get("values") or []
            if name == "servicename":
                service_names.extend(str(value) for value in values)
            elif name == "resourcegroup":
                resource_groups.extend(str(value) for value in values)
        for child in node.get("and", []) + node.get("or", []):
            _collect(child)

    filter_obj = props.get("filter")
    if isinstance(filter_obj, dict):
        _collect(filter_obj)

    for legacy_key in ("categoryFilter", "resourceGroupFilter"):
        legacy = props.get(legacy_key)
        if isinstance(legacy, dict):
            _collect(legacy)

    return {
        "service_names": service_names,
        "resource_groups": resource_groups,
    }


def _budget_is_scoped(filters: dict[str, list[str]]) -> bool:
    return bool(filters["service_names"] or filters["resource_groups"])


def _budget_matches_row(
    budget: dict[str, Any],
    *,
    service_name: str,
    resource_group: str | None,
) -> bool:
    filters = budget["filters"]
    service_filters = [value.lower() for value in filters["service_names"]]
    resource_group_filters = [value.lower() for value in filters["resource_groups"]]

    if not service_filters and not resource_group_filters:
        return True

    service_match = not service_filters or service_name.lower() in service_filters
    resource_group_match = (
        not resource_group_filters
        or (
            resource_group is not None
            and resource_group.lower() in resource_group_filters
        )
    )
    return service_match and resource_group_match


def _find_budget_for_row(
    budgets: list[dict[str, Any]],
    *,
    service_name: str,
    resource_group: str | None,
) -> dict[str, Any] | None:
    """Pick the most specific Azure budget for a cost row."""
    scoped_matches = [
        budget
        for budget in budgets
        if _budget_is_scoped(budget["filters"])
        and _budget_matches_row(
            budget,
            service_name=service_name,
            resource_group=resource_group,
        )
    ]
    if scoped_matches:
        return scoped_matches[0]

    subscription_matches = [
        budget for budget in budgets if not _budget_is_scoped(budget["filters"])
    ]
    return subscription_matches[0] if subscription_matches else None


def _budget_fields(
    budget: dict[str, Any] | None,
) -> tuple[str | None, float | None, float | None]:
    if budget is None or budget["limit_usd"] <= 0:
        return None, None, None
    return (
        budget["name"],
        budget["limit_usd"],
        (budget["current_spend_usd"] / budget["limit_usd"]) * 100.0,
    )


def _build_cost_metrics(
    costs: list[dict[str, Any]],
    budgets: list[dict[str, Any]],
    subscription_id: str,
    period_start: date,
    period_end: date,
) -> list[CostMetric]:
    """Build :class:`~dcm_commons.models.cost.CostMetric` instances from raw API data.

    Budget enrichment uses Azure Consumption filter dimensions (ServiceName,
    ResourceGroup) and falls back to subscription-wide budgets when no scoped
    budget matches the row.
    """
    metrics: list[CostMetric] = []
    enriched = 0
    for cost_row in costs:
        service_name = cost_row["service_name"]
        resource_group = cost_row.get("resource_group")
        cost_usd = cost_row["cost_usd"]

        budget = _find_budget_for_row(
            budgets,
            service_name=service_name,
            resource_group=resource_group,
        )
        budget_name, budget_limit, budget_pct = _budget_fields(budget)
        if budget_name is not None:
            enriched += 1

        metrics.append(
            CostMetric(
                service_name=service_name,
                resource_group=resource_group,
                subscription_or_account_id=subscription_id,
                period_start=period_start,
                period_end=period_end,
                cost_usd=max(0.0, cost_usd),
                budget_name=budget_name,
                budget_limit_usd=budget_limit,
                budget_consumed_pct=budget_pct,
            )
        )

    if budgets and enriched == 0:
        _logger.warning(
            "cost_management_budgets_unmatched",
            budget_names=[budget["name"] for budget in budgets],
            service_count=len(costs),
        )
    else:
        _logger.info(
            "cost_management_budgets_enriched",
            enriched_rows=enriched,
            total_rows=len(metrics),
        )
    return metrics
