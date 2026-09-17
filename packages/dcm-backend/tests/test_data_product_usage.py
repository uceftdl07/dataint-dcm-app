"""Tests for GET /api/v1/data-product-usage endpoints."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock

from httpx import AsyncClient

from app.db.tables import qualified_table
from app.main import app


def _viewer_headers(lz_ids: str = "lz-001,lz-002") -> dict[str, str]:
    return {"x-dcm-role": "viewer", "x-dcm-lz-ids": lz_ids}


def _usage_row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "usage_date": date(2026, 5, 1),
        "data_product_id": "dp-sales",
        "data_product_name": "Sales Data Product",
        "consumer_id": "team-finance",
        "consumer_name": "Finance Team",
        "cloud_provider": "azure",
        "source_lz_id": "lz-azure-prod",
        "subscription_or_account_id": "sub-123",
        "request_count": 42,
        "rows_read": 1000,
        "rows_written": 250,
        "data_read_bytes": 2048,
        "data_written_bytes": 512,
        "duration_seconds": 12.345,
        "cost_usd": 7.891,
        "last_used_at": datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
    }
    base.update(overrides)
    return base


class TestDataProductUsageOverview:
    async def test_empty_overview(self, client: AsyncClient, mock_db: AsyncMock) -> None:
        mock_db.fetchone.return_value = None
        mock_db.fetchall.return_value = []

        resp = await client.get("/api/v1/data-product-usage/overview")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_data_products"] == 0
        assert body["active_consumers"] == 0
        assert body["by_cloud"] == []
        assert "period" in body

    async def test_missing_gold_table_returns_clear_503(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        missing = qualified_table(app.state.settings, "gold_data_product_usage")
        mock_db.fetchone.side_effect = Exception(
            f"[TABLE_OR_VIEW_NOT_FOUND] The table or view {missing} cannot be found."
        )

        resp = await client.get("/api/v1/data-product-usage/overview")

        assert resp.status_code == 503
        body = resp.json()
        assert body["detail"]["code"] == "data_product_usage_table_missing"
        # Names the schema the pool actually reads (``…__d`` in dev, ``…__p`` in prod),
        # so the hint stays actionable in every environment.
        assert body["detail"]["table"] == missing

    async def test_overview_serialises_summary_and_clouds(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        mock_db.fetchone.return_value = {
            "total_data_products": 3,
            "active_consumers": 5,
            "request_count": 120,
            "rows_read": 10000,
            "rows_written": 2000,
            "data_read_bytes": 9999,
            "data_written_bytes": 1111,
            "duration_seconds": 45.678,
            "cost_usd": 12.345,
            "last_used_at": datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
        }
        mock_db.fetchall.return_value = [
            {
                "cloud_provider": "azure",
                "data_product_count": 2,
                "consumer_count": 4,
                "request_count": 100,
                "data_read_bytes": 8000,
                "data_written_bytes": 900,
                "cost_usd": 10.125,
            }
        ]

        resp = await client.get("/api/v1/data-product-usage/overview")

        body = resp.json()
        assert body["total_data_products"] == 3
        assert body["duration_seconds"] == 45.68
        assert body["cost_usd"] == 12.35
        assert body["by_cloud"][0]["cloud_provider"] == "azure"
        assert body["by_cloud"][0]["cost_usd"] == 10.12


class TestDataProductUsageTrends:
    async def test_trends_returns_buckets(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        mock_db.fetchall.return_value = [
            {
                "period_start": date(2026, 5, 1),
                "data_product_count": 2,
                "consumer_count": 3,
                "request_count": 50,
                "rows_read": 1000,
                "rows_written": 100,
                "data_read_bytes": 4096,
                "data_written_bytes": 256,
                "cost_usd": 4.567,
            }
        ]

        resp = await client.get(
            "/api/v1/data-product-usage/trends",
            params={"grain": "week", "cloud_provider": "azure"},
        )

        body = resp.json()
        assert body["grain"] == "week"
        assert body["items"][0]["period_start"] == "2026-05-01"
        assert body["items"][0]["cost_usd"] == 4.57

    async def test_rejects_invalid_grain(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        resp = await client.get("/api/v1/data-product-usage/trends", params={"grain": "hour"})

        assert resp.status_code == 400
        mock_db.fetchall.assert_not_called()


class TestTopDataProductConsumers:
    async def test_top_consumers_metric_whitelist(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        resp = await client.get(
            "/api/v1/data-product-usage/top-consumers",
            params={"metric": "drop table"},
        )

        assert resp.status_code == 400
        mock_db.fetchall.assert_not_called()

    async def test_top_consumers_serialises_rows(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        mock_db.fetchall.return_value = [
            {
                "consumer_id": "team-finance",
                "consumer_name": "Finance Team",
                "cloud_provider": "azure",
                "source_lz_id": "lz-azure-prod",
                "subscription_or_account_id": "sub-123",
                "data_product_count": 4,
                "request_count": 100,
                "rows_read": 5000,
                "rows_written": 500,
                "data_read_bytes": 8192,
                "data_written_bytes": 1024,
                "duration_seconds": 30.555,
                "cost_usd": 2.345,
                "metric_value": 8192,
                "last_used_at": datetime(2026, 5, 1, 12, 30, tzinfo=UTC),
            }
        ]

        resp = await client.get("/api/v1/data-product-usage/top-consumers")

        body = resp.json()
        assert body["metric"] == "data_read_bytes"
        assert body["items"][0]["consumer_id"] == "team-finance"
        assert body["items"][0]["duration_seconds"] == 30.55


class TestListDataProductUsage:
    async def test_empty_list(self, client: AsyncClient, mock_db: AsyncMock) -> None:
        mock_db.fetchscalar.return_value = 0
        mock_db.fetchall.return_value = []

        resp = await client.get("/api/v1/data-product-usage")

        body = resp.json()
        assert resp.status_code == 200
        assert body["items"] == []
        assert body["total"] == 0
        assert body["limit"] == 50
        assert body["offset"] == 0

    async def test_list_serialises_usage_row(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        mock_db.fetchscalar.return_value = 1
        mock_db.fetchall.return_value = [_usage_row()]

        resp = await client.get(
            "/api/v1/data-product-usage",
            params={"limit": 10, "offset": 5, "data_product_id": "dp-sales"},
        )

        body = resp.json()
        assert body["total"] == 1
        assert body["limit"] == 10
        assert body["offset"] == 5
        assert body["items"][0]["data_product_name"] == "Sales Data Product"
        assert body["items"][0]["duration_seconds"] == 12.35
        assert body["items"][0]["cost_usd"] == 7.89

    async def test_list_applies_multi_lz_filter_from_query_params(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        mock_db.fetchscalar.return_value = 0
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/data-product-usage",
            params=[("source_lz_ids", "lz-aws-prod"), ("source_lz_ids", "lz-azure-prod")],
            headers={"x-dcm-role": "admin"},
        )

        assert resp.status_code == 200
        count_query = mock_db.fetchscalar.await_args.args[0]
        list_query = mock_db.fetchall.await_args.args[0]
        count_args = mock_db.fetchscalar.await_args.args[1:]
        list_args = mock_db.fetchall.await_args.args[1:]
        assert "source_lz_id IN (?, ?)" in count_query
        assert "source_lz_id IN (?, ?)" in list_query
        assert "lz-aws-prod" in count_args
        assert "lz-azure-prod" in count_args
        assert "lz-aws-prod" in list_args
        assert "lz-azure-prod" in list_args

    async def test_overview_applies_viewer_lz_rbac(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        mock_db.fetchone.return_value = None
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/data-product-usage/overview",
            headers=_viewer_headers("lz-001"),
        )

        assert resp.status_code == 200
        query = mock_db.fetchone.await_args.args[0]
        args = mock_db.fetchone.await_args.args[1:]
        assert "source_lz_id IN (?)" in query
        assert "lz-001" in args
