"""Tests for GET /api/v1/costs/summary and GET /api/v1/costs/by-service."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient


def _cloud_row(cp: str, total: float) -> dict:
    return {"cloud_provider": cp, "total": total}


def _svc_row(name: str, cp: str, total: float) -> dict:
    return {"service_name": name, "cloud_provider": cp, "total": total}


def _by_service_row(**overrides: Any) -> dict:
    base: dict[str, Any] = {
        "service_name": "Azure Databricks",
        "cloud_provider": "azure",
        "subscription_or_account_id": "sub-abc",
        "source_lz_id": "lz-azure-prod",
        "total_cost_usd": 1200.50,
        "avg_budget_pct": 60.0,
        "earliest_period": date(2026, 3, 1),
        "latest_period": date(2026, 3, 31),
    }
    base.update(overrides)
    return base


class TestGetCostSummary:
    async def test_zero_data(self, client: AsyncClient, mock_db: AsyncMock) -> None:
        mock_db.fetchscalar.return_value = None
        mock_db.fetchall.return_value = []

        resp = await client.get("/api/v1/costs/summary")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_usd"] == 0.0
        assert body["by_cloud"] == {}
        assert body["by_service"] == []
        assert "period" in body

    async def test_total_rounded(self, client: AsyncClient, mock_db: AsyncMock) -> None:
        mock_db.fetchscalar.return_value = 1234.567891
        mock_db.fetchall.return_value = []

        resp = await client.get("/api/v1/costs/summary")

        assert resp.json()["total_usd"] == 1234.57

    async def test_by_cloud_mapping(self, client: AsyncClient, mock_db: AsyncMock) -> None:
        mock_db.fetchscalar.return_value = 2000.0

        # fetchall called twice: by_cloud then by_service
        call_count = 0

        async def fetchall_side(query: str, *args: Any) -> list:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [_cloud_row("azure", 1500.0), _cloud_row("aws", 500.0)]
            return []

        mock_db.fetchall.side_effect = fetchall_side

        resp = await client.get("/api/v1/costs/summary")

        body = resp.json()
        assert body["by_cloud"]["azure"] == 1500.0
        assert body["by_cloud"]["aws"] == 500.0

    async def test_by_service_list(self, client: AsyncClient, mock_db: AsyncMock) -> None:
        mock_db.fetchscalar.return_value = 100.0
        call_count = 0

        async def fetchall_side(query: str, *args: Any) -> list:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return []  # by_cloud empty
            return [_svc_row("AWS Glue", "aws", 80.0), _svc_row("Azure ADF", "azure", 20.0)]

        mock_db.fetchall.side_effect = fetchall_side

        resp = await client.get("/api/v1/costs/summary")

        svc = resp.json()["by_service"]
        assert len(svc) == 2
        assert svc[0]["service_name"] == "AWS Glue"
        assert svc[0]["cost_usd"] == 80.0

    async def test_period_defaults_present(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 0
        mock_db.fetchall.return_value = []

        resp = await client.get("/api/v1/costs/summary")

        period = resp.json()["period"]
        assert "start" in period
        assert "end" in period

    async def test_cloud_provider_filter(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 0
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/costs/summary", params={"cloud_provider": "aws"}
        )

        assert resp.status_code == 200


class TestGetCostsByService:
    async def test_empty_response(self, client: AsyncClient, mock_db: AsyncMock) -> None:
        mock_db.fetchall.return_value = []

        resp = await client.get("/api/v1/costs/by-service")

        assert resp.status_code == 200
        assert resp.json() == {"items": []}

    async def test_single_service_serialised(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = [_by_service_row()]

        resp = await client.get("/api/v1/costs/by-service")

        items = resp.json()["items"]
        assert len(items) == 1
        item = items[0]
        assert item["service_name"] == "Azure Databricks"
        assert item["total_cost_usd"] == 1200.5
        assert item["avg_budget_consumed_pct"] == 60.0
        assert item["period"]["start"] == "2026-03-01"
        assert item["period"]["end"] == "2026-03-31"

    async def test_null_budget_pct(self, client: AsyncClient, mock_db: AsyncMock) -> None:
        mock_db.fetchall.return_value = [_by_service_row(avg_budget_pct=None)]

        resp = await client.get("/api/v1/costs/by-service")

        assert resp.json()["items"][0]["avg_budget_consumed_pct"] is None

    async def test_string_periods_serialised(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = [
            _by_service_row(earliest_period="2026-03-25", latest_period="2026-05-25")
        ]

        resp = await client.get("/api/v1/costs/by-service")

        item = resp.json()["items"][0]
        assert item["period"]["start"] == "2026-03-25"
        assert item["period"]["end"] == "2026-05-25"


class TestFinOpsPageBundle:
    async def test_page_bundle_shape(self, client: AsyncClient, mock_db: AsyncMock) -> None:
        mock_db.fetchscalar.return_value = 100.0
        call_count = 0

        async def fetchall_side(query: str, *args: Any) -> list:
            nonlocal call_count
            call_count += 1
            if "GROUP BY cloud_provider" in query:
                return [_cloud_row("azure", 100.0)]
            if "LIMIT 10" in query:
                return [_svc_row("Azure Databricks", "azure", 100.0)]
            return [_by_service_row()]

        mock_db.fetchall.side_effect = fetchall_side

        resp = await client.get("/api/v1/costs/page-bundle")

        assert resp.status_code == 200
        body = resp.json()
        assert "summary" in body
        assert "by_service" in body
        assert body["summary"]["total_usd"] == 100.0
        assert len(body["by_service"]["items"]) == 1
