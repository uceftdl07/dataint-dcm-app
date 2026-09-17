"""Tests for GET /api/v1/databricks/embedded-dashboards endpoints."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from httpx import AsyncClient

from app.db.tables import qualified_table
from app.main import app


def _viewer_headers(lz_ids: str = "lz-001,lz-002") -> dict[str, str]:
    return {"x-dcm-role": "viewer", "x-dcm-lz-ids": lz_ids}


def _dashboard_row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "dashboard_slug": "genie-obs",
        "title": "Genie Control Tower",
        "description": "Real-time observability for Databricks Genie usage across workspaces.",
        "workspace_host": "https://dbc-e25c222e-27eb.cloud.databricks.com",
        "workspace_id": "2505786830871273",
        "dashboard_id": "01f1666ab90c1d32ba3046df563db745",
        "scope": "global",
        "source_lz_id": None,
        "menu_group": "insights",
        "sort_order": 0,
    }
    base.update(overrides)
    return base


class TestEmbeddedDashboards:
    async def test_list_embedded_dashboards(self, client: AsyncClient, mock_db: AsyncMock) -> None:
        mock_db.fetchall.return_value = [_dashboard_row()]

        resp = await client.get("/api/v1/databricks/embedded-dashboards", headers=_viewer_headers())

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["dashboard_slug"] == "genie-obs"
        assert item["embed_url"].endswith(
            "/embed/dashboardsv3/01f1666ab90c1d32ba3046df563db745?o=2505786830871273"
        )
        assert "dashboardsv3/01f1666ab90c1d32ba3046df563db745/published" in item["direct_url"]

    async def test_get_embedded_dashboard_by_slug(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        mock_db.fetchall.return_value = [_dashboard_row()]

        resp = await client.get(
            "/api/v1/databricks/embedded-dashboards/genie-obs",
            headers=_viewer_headers(),
        )

        assert resp.status_code == 200
        assert resp.json()["title"] == "Genie Control Tower"

    async def test_get_embedded_dashboard_not_found(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        mock_db.fetchall.return_value = [_dashboard_row()]

        resp = await client.get(
            "/api/v1/databricks/embedded-dashboards/unknown",
            headers=_viewer_headers(),
        )

        assert resp.status_code == 404

    async def test_landing_zone_scope_filters_by_allowed_lz(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        mock_db.fetchall.return_value = [
            _dashboard_row(scope="landing_zone", source_lz_id="lz-other", dashboard_slug="lz-only"),
        ]

        resp = await client.get(
            "/api/v1/databricks/embedded-dashboards",
            headers=_viewer_headers("lz-001"),
        )

        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_missing_table_returns_clear_503(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        missing = qualified_table(app.state.settings, "dcm_embedded_dashboards")
        mock_db.fetchall.side_effect = Exception(
            f"[TABLE_OR_VIEW_NOT_FOUND] The table or view {missing} cannot be found."
        )

        resp = await client.get("/api/v1/databricks/embedded-dashboards", headers=_viewer_headers())

        assert resp.status_code == 503
        body = resp.json()
        assert body["detail"]["code"] == "embedded_dashboards_table_missing"
