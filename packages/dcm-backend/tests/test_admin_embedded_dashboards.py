"""Tests for admin embedded dashboard endpoints."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from httpx import AsyncClient


def _super_admin_headers() -> dict[str, str]:
    return {"x-dcm-role": "super_admin"}


def _dashboard_row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "dashboard_slug": "genie-obs",
        "title": "Genie Control Tower",
        "description": "Observability",
        "workspace_host": "https://dbc-e25c222e-27eb.cloud.databricks.com",
        "workspace_id": "2505786830871273",
        "dashboard_id": "01f1666ab90c1d32ba3046df563db745",
        "scope": "global",
        "source_lz_id": None,
        "menu_group": "insights",
        "sort_order": 0,
        "enabled": True,
    }
    base.update(overrides)
    return base


class TestAdminEmbeddedDashboards:
    async def test_list_admin_embedded_dashboards(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        mock_db.fetchall.return_value = [_dashboard_row()]

        resp = await client.get("/api/v1/admin/embedded-dashboards", headers=_super_admin_headers())

        assert resp.status_code == 200
        assert resp.json()["items"][0]["enabled"] is True

    async def test_create_admin_embedded_dashboard(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        mock_db.fetchall.side_effect = [
            [],
            [_dashboard_row(dashboard_slug="finops-bi", title="FinOps BI")],
        ]

        resp = await client.post(
            "/api/v1/admin/embedded-dashboards",
            headers=_super_admin_headers(),
            json={
                "dashboard_slug": "finops-bi",
                "title": "FinOps BI",
                "workspace_host": "https://dbc-example.cloud.databricks.com",
                "workspace_id": "123",
                "dashboard_id": "01fabc",
            },
        )

        assert resp.status_code == 201
        assert resp.json()["dashboard_slug"] == "finops-bi"
        mock_db.execute.assert_called()

    async def test_update_admin_embedded_dashboard(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        mock_db.fetchall.side_effect = [
            [_dashboard_row()],
            [_dashboard_row(title="Updated title")],
        ]

        resp = await client.put(
            "/api/v1/admin/embedded-dashboards/genie-obs",
            headers=_super_admin_headers(),
            json={"title": "Updated title"},
        )

        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated title"

    async def test_delete_admin_embedded_dashboard(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        mock_db.fetchall.return_value = [_dashboard_row()]

        resp = await client.delete(
            "/api/v1/admin/embedded-dashboards/genie-obs",
            headers=_super_admin_headers(),
        )

        assert resp.status_code == 204
