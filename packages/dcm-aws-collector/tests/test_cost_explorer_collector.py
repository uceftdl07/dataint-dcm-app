"""Tests for CostExplorerCollector — daily costs by service and budget utilisation.

Stubs boto3 STS, Cost Explorer, and Budgets clients via ``unittest.mock``.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aws_collector.collectors.cost_explorer import (
    CostExplorerCollector,
    _build_cost_metrics,
    _get_account_id,
    _query_budgets,
    _query_costs,
)


# ---------------------------------------------------------------------------
# _get_account_id
# ---------------------------------------------------------------------------


class TestGetAccountId:
    @pytest.mark.asyncio
    async def test_returns_account_id(self) -> None:
        sts = MagicMock()
        sts.get_caller_identity = MagicMock(return_value={"Account": "123456789012"})

        with patch("aws_collector.collectors.cost_explorer.run_sync", new=AsyncMock(side_effect=lambda f, **kw: f(**kw))):
            account_id = await _get_account_id(sts)

        assert account_id == "123456789012"

    @pytest.mark.asyncio
    async def test_sts_failure_returns_empty_string(self) -> None:
        sts = MagicMock()
        sts.get_caller_identity = MagicMock(side_effect=RuntimeError("no credentials"))

        with patch("aws_collector.collectors.cost_explorer.run_sync", new=AsyncMock(side_effect=RuntimeError("no credentials"))):
            account_id = await _get_account_id(sts)

        assert account_id == ""


# ---------------------------------------------------------------------------
# _query_costs
# ---------------------------------------------------------------------------


def _make_ce_response(rows: list[tuple[str, str]]) -> dict[str, Any]:
    """Build a minimal Cost Explorer response for the given (service, amount) pairs."""
    groups = [
        {
            "Keys": [service],
            "Metrics": {"UnblendedCost": {"Amount": amount, "Unit": "USD"}},
        }
        for service, amount in rows
    ]
    return {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": "2026-02-17", "End": "2026-03-19"},
                "Groups": groups,
            }
        ]
    }


class TestQueryCosts:
    @pytest.mark.asyncio
    async def test_parses_service_costs(self) -> None:
        ce = MagicMock()
        ce.get_cost_and_usage = MagicMock(
            return_value=_make_ce_response([("Amazon S3", "12.50"), ("AWS Lambda", "3.00")])
        )

        with patch("aws_collector.collectors.cost_explorer.run_sync", new=AsyncMock(side_effect=lambda f, **kw: f(**kw))):
            rows = await _query_costs(ce, date(2026, 2, 17), date(2026, 3, 19))

        assert len(rows) == 2
        s3 = next(r for r in rows if r["service_name"] == "Amazon S3")
        assert s3["cost_usd"] == pytest.approx(12.50)

    @pytest.mark.asyncio
    async def test_invalid_amount_defaults_to_zero(self) -> None:
        ce = MagicMock()
        ce.get_cost_and_usage = MagicMock(
            return_value=_make_ce_response([("Amazon EC2", "not-a-number")])
        )

        with patch("aws_collector.collectors.cost_explorer.run_sync", new=AsyncMock(side_effect=lambda f, **kw: f(**kw))):
            rows = await _query_costs(ce, date(2026, 2, 17), date(2026, 3, 19))

        assert rows[0]["cost_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_empty_keys_row_skipped(self) -> None:
        ce = MagicMock()
        ce.get_cost_and_usage = MagicMock(
            return_value={
                "ResultsByTime": [
                    {
                        "TimePeriod": {"Start": "2026-03-01", "End": "2026-03-19"},
                        "Groups": [
                            {"Keys": [], "Metrics": {"UnblendedCost": {"Amount": "5.0"}}},
                        ],
                    }
                ]
            }
        )

        with patch("aws_collector.collectors.cost_explorer.run_sync", new=AsyncMock(side_effect=lambda f, **kw: f(**kw))):
            rows = await _query_costs(ce, date(2026, 3, 1), date(2026, 3, 19))

        assert rows == []


# ---------------------------------------------------------------------------
# _query_budgets
# ---------------------------------------------------------------------------


class TestQueryBudgets:
    @pytest.mark.asyncio
    async def test_parses_budgets(self) -> None:
        budgets_client = MagicMock()
        budgets_client.describe_budgets = MagicMock(
            return_value={
                "Budgets": [
                    {
                        "BudgetName": "Amazon S3",
                        "BudgetLimit": {"Amount": "100.00"},
                        "CalculatedSpend": {"ActualSpend": {"Amount": "45.00"}},
                    }
                ]
            }
        )

        with patch("aws_collector.collectors.cost_explorer.run_sync", new=AsyncMock(side_effect=lambda f, **kw: f(**kw))):
            budgets = await _query_budgets(budgets_client, "123456789012")

        assert len(budgets) == 1
        assert budgets[0]["name"] == "Amazon S3"
        assert budgets[0]["limit_usd"] == pytest.approx(100.0)
        assert budgets[0]["current_spend_usd"] == pytest.approx(45.0)

    @pytest.mark.asyncio
    async def test_empty_account_id_returns_empty_list(self) -> None:
        budgets_client = MagicMock()
        budgets = await _query_budgets(budgets_client, "")
        assert budgets == []

    @pytest.mark.asyncio
    async def test_api_failure_returns_empty_list(self) -> None:
        budgets_client = MagicMock()

        with patch(
            "aws_collector.collectors.cost_explorer.run_sync",
            new=AsyncMock(side_effect=RuntimeError("access denied")),
        ):
            budgets = await _query_budgets(budgets_client, "123456789012")

        assert budgets == []

    @pytest.mark.asyncio
    async def test_budget_without_name_skipped(self) -> None:
        budgets_client = MagicMock()
        budgets_client.describe_budgets = MagicMock(
            return_value={
                "Budgets": [
                    {"BudgetName": "", "BudgetLimit": {"Amount": "50"}, "CalculatedSpend": {"ActualSpend": {"Amount": "10"}}}
                ]
            }
        )

        with patch("aws_collector.collectors.cost_explorer.run_sync", new=AsyncMock(side_effect=lambda f, **kw: f(**kw))):
            budgets = await _query_budgets(budgets_client, "123456789012")

        assert budgets == []


# ---------------------------------------------------------------------------
# _build_cost_metrics
# ---------------------------------------------------------------------------


class TestBuildCostMetrics:
    def _rows(self) -> list[dict[str, Any]]:
        return [
            {"service_name": "Amazon S3", "cost_usd": 12.50},
            {"service_name": "AWS Lambda", "cost_usd": 3.00},
            {"service_name": "Amazon EC2", "cost_usd": 200.00},
        ]

    def _budgets(self) -> list[dict[str, Any]]:
        return [
            {"name": "Amazon S3", "limit_usd": 100.0, "current_spend_usd": 45.0},
        ]

    def test_budget_matched_case_insensitive(self) -> None:
        budgets = [{"name": "amazon s3", "limit_usd": 100.0, "current_spend_usd": 45.0}]
        metrics = _build_cost_metrics(
            cost_rows=self._rows(),
            budgets=budgets,
            account_id="123",
            period_start=date(2026, 2, 17),
            period_end=date(2026, 3, 19),
        )
        s3 = next(m for m in metrics if m.service_name == "Amazon S3")
        assert s3.budget_name == "amazon s3"
        assert s3.budget_consumed_pct == pytest.approx(45.0)

    def test_no_matching_budget_gives_none(self) -> None:
        # Two budgets → no subscription-wide fallback; only name matches enrich.
        budgets = [
            {"name": "Amazon S3", "limit_usd": 100.0, "current_spend_usd": 45.0},
            {"name": "AWS Lambda", "limit_usd": 50.0, "current_spend_usd": 3.0},
        ]
        metrics = _build_cost_metrics(
            cost_rows=self._rows(),
            budgets=budgets,
            account_id="123",
            period_start=date(2026, 2, 17),
            period_end=date(2026, 3, 19),
        )
        ec2 = next(m for m in metrics if m.service_name == "Amazon EC2")
        assert ec2.budget_name is None
        assert ec2.budget_limit_usd is None
        assert ec2.budget_consumed_pct is None

    def test_single_budget_fallback_applies_to_all_services(self) -> None:
        metrics = _build_cost_metrics(
            cost_rows=self._rows(),
            budgets=self._budgets(),
            account_id="123",
            period_start=date(2026, 2, 17),
            period_end=date(2026, 3, 19),
        )
        ec2 = next(m for m in metrics if m.service_name == "Amazon EC2")
        assert ec2.budget_name == "Amazon S3"
        assert ec2.budget_limit_usd == pytest.approx(100.0)
        assert ec2.budget_consumed_pct == pytest.approx(45.0)

    def test_budget_with_zero_limit_ignored(self) -> None:
        budgets = [{"name": "AWS Lambda", "limit_usd": 0.0, "current_spend_usd": 3.0}]
        metrics = _build_cost_metrics(
            cost_rows=self._rows(),
            budgets=budgets,
            account_id="123",
            period_start=date(2026, 2, 17),
            period_end=date(2026, 3, 19),
        )
        lam = next(m for m in metrics if m.service_name == "AWS Lambda")
        assert lam.budget_name is None

    def test_negative_cost_clamped_to_zero(self) -> None:
        rows = [{"service_name": "AWS Support", "cost_usd": -5.0}]
        metrics = _build_cost_metrics(
            cost_rows=rows,
            budgets=[],
            account_id="123",
            period_start=date(2026, 2, 17),
            period_end=date(2026, 3, 19),
        )
        assert metrics[0].cost_usd == 0.0

    def test_account_id_embedded(self) -> None:
        metrics = _build_cost_metrics(
            cost_rows=self._rows(),
            budgets=[],
            account_id="999888777666",
            period_start=date(2026, 2, 17),
            period_end=date(2026, 3, 19),
        )
        assert all(m.subscription_or_account_id == "999888777666" for m in metrics)

    def test_budget_pct_calculated_correctly(self) -> None:
        budgets = [{"name": "Amazon S3", "limit_usd": 100.0, "current_spend_usd": 75.0}]
        metrics = _build_cost_metrics(
            cost_rows=self._rows(),
            budgets=budgets,
            account_id="123",
            period_start=date(2026, 2, 17),
            period_end=date(2026, 3, 19),
        )
        s3 = next(m for m in metrics if m.service_name == "Amazon S3")
        assert s3.budget_consumed_pct == pytest.approx(75.0)


# ---------------------------------------------------------------------------
# CostExplorerCollector._collect_metrics (integration)
# ---------------------------------------------------------------------------


class TestCostExplorerCollectorCollectMetrics:
    def _make_collector(self) -> CostExplorerCollector:
        with patch("boto3.client"):
            return CostExplorerCollector(
                source_lz_id="lz-aws-1",
                aws_region="eu-west-1",
                lookback_days=30,
            )

    @pytest.mark.asyncio
    async def test_full_collection_returns_metrics(self) -> None:
        collector = self._make_collector()

        async def fake_get_account_id(sts):  # type: ignore[no-untyped-def]
            return "123456789012"

        async def fake_query_costs(ce, start, end):  # type: ignore[no-untyped-def]
            return [{"service_name": "Amazon S3", "cost_usd": 25.0}]

        async def fake_query_budgets(bc, account_id):  # type: ignore[no-untyped-def]
            return []

        with (
            patch("aws_collector.collectors.cost_explorer._get_account_id", fake_get_account_id),
            patch("aws_collector.collectors.cost_explorer._query_costs", fake_query_costs),
            patch("aws_collector.collectors.cost_explorer._query_budgets", fake_query_budgets),
        ):
            metrics = await collector._collect_metrics()

        assert len(metrics) == 1
        assert metrics[0]["service_name"] == "Amazon S3"
        assert metrics[0]["cost_usd"] == pytest.approx(25.0)

    @pytest.mark.asyncio
    async def test_cost_query_failure_raises_collection_error(self) -> None:
        from dcm_commons.exceptions import CollectionError

        collector = self._make_collector()

        async def fake_get_account_id(sts):  # type: ignore[no-untyped-def]
            return "123"

        async def fake_query_costs(ce, start, end):  # type: ignore[no-untyped-def]
            raise RuntimeError("CE API unavailable")

        async def fake_query_budgets(bc, account_id):  # type: ignore[no-untyped-def]
            return []

        with (
            patch("aws_collector.collectors.cost_explorer._get_account_id", fake_get_account_id),
            patch("aws_collector.collectors.cost_explorer._query_costs", fake_query_costs),
            patch("aws_collector.collectors.cost_explorer._query_budgets", fake_query_budgets),
        ):
            with pytest.raises(CollectionError):
                await collector._collect_metrics()
