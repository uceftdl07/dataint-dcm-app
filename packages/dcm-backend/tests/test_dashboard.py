"""Tests for dashboard endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient


def _make_cloud_row(cp: str) -> dict:
    return {"cloud_provider": cp}


def _scalar_from_query(query: str) -> int | float:
    if "COUNT(*)" in query and "curated_pipeline_metrics" in query:
        if "status = 'failed'" in query:
            return 3
        if "NOT LIKE 'databricks:job:%'" in query:
            return 30
        if "pipeline_id LIKE 'databricks:job:%'" in query:
            return 12
        return 42
    if "gold_dbx_workflow_runs" in query:
        return 6
    if "curated_compute_metrics" in query:
        return 7
    if "curated_dbx_compute_warehouse_events" in query:
        return 4
    if "dbx_cost" in query:
        return 1200.0
    if "curated_cost_metrics" in query:
        return 1500.50
    if "curated_security_alerts" in query:
        return 5
    return 0


class TestDashboardOverview:
    async def test_returns_200_with_zero_data(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """All scalar queries return None → response fields default to 0/[]."""
        mock_db.fetchscalar.return_value = None
        mock_db.fetchall.return_value = []

        resp = await client.get("/api/v1/dashboard/overview")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_pipelines"] == 0
        assert body["total_adf_pipelines"] == 0
        assert body["total_databricks_pipelines"] == 0
        assert body["failed_pipelines_24h"] == 0
        assert body["failed_databricks_jobs_24h"] == 0
        assert body["active_compute"] == 0
        assert body["active_sql_warehouses"] == 0
        assert body["cost_ytd_usd"] == 0.0
        assert body["cost_ytd_previous_year_usd"] == 0.0
        assert body["cost_ytd_delta_usd"] == 0.0
        assert body["cost_ytd_delta_pct"] is None
        assert body["cost_ytd_monthly"] == []
        assert body["alert_breakdown"] == {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
        }
        assert body["as_of"].endswith("Z")
        assert body["total_cost_usd"] == 0.0
        assert body["open_alerts"] == 0
        assert body["cloud_coverage"] == []

    async def test_aggregates_scalar_counts(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        async def scalar_side_effect(query: str, *args: object) -> int | float:
            return _scalar_from_query(query)

        mock_db.fetchscalar.side_effect = scalar_side_effect
        mock_db.fetchall.return_value = [_make_cloud_row("azure"), _make_cloud_row("aws")]

        resp = await client.get("/api/v1/dashboard/overview")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_pipelines"] == 42
        assert body["total_adf_pipelines"] == 30
        assert body["total_databricks_pipelines"] == 12
        assert body["failed_pipelines_24h"] == 3
        assert body["failed_databricks_jobs_24h"] == 6
        assert body["active_compute"] == 7
        assert body["active_sql_warehouses"] == 4
        assert body["cost_ytd_usd"] == 1200.0
        assert body["cost_ytd_previous_year_usd"] == 1200.0
        assert body["cost_ytd_delta_usd"] == 0.0
        assert body["cost_ytd_delta_pct"] == 0.0
        assert body["total_cost_usd"] == 1500.5
        assert body["open_alerts"] == 5
        assert set(body["cloud_coverage"]) == {"azure", "aws"}

    async def test_period_in_response(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 0
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/dashboard/overview",
            params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

        body = resp.json()
        assert body["period"]["start"] == "2026-01-01"
        assert body["period"]["end"] == "2026-01-31"

    async def test_cloud_provider_filter_accepted(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 0
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/dashboard/overview", params={"cloud_provider": "azure"}
        )

        assert resp.status_code == 200


class TestDashboardFull:
    async def test_returns_bundled_sections(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 0
        mock_db.fetchone.return_value = {
            "compliant_count": 8,
            "non_compliant_count": 2,
            "total_evaluated": 10,
        }
        mock_db.fetchall.return_value = []

        resp = await client.get("/api/v1/dashboard/full")

        assert resp.status_code == 200
        body = resp.json()
        assert "overview" in body
        assert "governance" in body
        assert "costs" in body
        assert "pipelines" in body
        assert "computes" in body
        assert "databases" in body
        assert "alerts" in body
        assert body["governance"]["global_score_pct"] == 80.0
