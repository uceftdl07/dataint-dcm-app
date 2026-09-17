"""Tests for monitoring reports endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient


class TestMonitoringReportsFull:
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

        resp = await client.get("/api/v1/monitoring-reports/full")

        assert resp.status_code == 200
        body = resp.json()
        assert "data_product_usage" in body
        assert "usage_trends" in body
        assert "standard_checks" in body
        assert "landing_zones" in body
        assert "security_alerts" in body
        assert "computes" in body
        assert "pipelines" in body
        assert "cost_summary" in body
        assert "costs_by_service" in body
        assert "governance" in body
        assert body["governance"]["global_score_pct"] == 80.0

    async def test_accepts_date_filters(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 0
        mock_db.fetchone.return_value = {
            "compliant_count": 0,
            "non_compliant_count": 0,
            "total_evaluated": 0,
        }
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/monitoring-reports/full",
            params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["cost_summary"]["period"]["start"] == "2026-01-01"
        assert body["cost_summary"]["period"]["end"] == "2026-01-31"
