"""Tests for GET /api/v1/health."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient


class TestHealthCheck:
    async def test_live_returns_200_without_db(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/health/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_returns_200_when_db_ok(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 1

        resp = await client.get("/api/v1/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["database"] == "ok"
        assert body["service"] == "dcm-backend"
        assert "timestamp" in body

    async def test_returns_503_when_db_unreachable(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.side_effect = OSError("Connection refused")

        resp = await client.get("/api/v1/health")

        assert resp.status_code == 503
        body = resp.json()["detail"]
        assert body["status"] == "degraded"
        assert body["database"] == "unreachable"
        assert "Connection refused" in body["error"]

    async def test_returns_503_when_select_returns_unexpected_value(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 0  # SELECT 1 should return 1

        resp = await client.get("/api/v1/health")

        assert resp.status_code == 503

    async def test_db_probe_called_once(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 1

        await client.get("/api/v1/health")

        mock_db.fetchscalar.assert_awaited_once_with("SELECT 1")
