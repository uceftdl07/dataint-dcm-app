"""Tests for GET /api/v1/databases."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient


def _db_row(**overrides: Any) -> dict:
    base: dict[str, Any] = {
        "db_id": "db-sql-001",
        "db_name": "prod-sql",
        "db_type": "sqlserver",
        "cloud_provider": "azure",
        "source_lz_id": "lz-azure-01",
        "region": "westeurope",
        "server_name": "sql-server-prod.database.windows.net",
        "cpu_percent": 45.5,
        "memory_percent": 60.0,
        "storage_used_gb": 50.0,
        "is_available": True,
        "collected_at": datetime(2026, 3, 19, 8, 0, 0, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return base


class TestListDatabases:
    async def test_empty_response(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = []

        resp = await client.get("/api/v1/databases")

        assert resp.status_code == 200
        assert resp.json() == {"items": []}

    async def test_single_db_serialised(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = [_db_row()]

        resp = await client.get("/api/v1/databases")

        items = resp.json()["items"]
        assert len(items) == 1
        item = items[0]
        assert item["db_id"] == "db-sql-001"
        assert item["db_type"] == "sqlserver"
        assert item["cpu_percent"] == 45.5
        assert item["is_available"] is True
        assert item["collected_at"].startswith("2026-03-19")

    async def test_storage_pct_computed(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """storage_used_pct = storage_used_gb / storage_total_gb * 100."""
        mock_db.fetchall.return_value = [
            _db_row(storage_used_gb=25.0, storage_total_gb=100.0)
        ]

        resp = await client.get("/api/v1/databases")

        assert resp.json()["items"][0]["storage_used_pct"] == 25.0

    async def test_storage_pct_none_when_total_zero(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = [
            _db_row(storage_used_gb=0.0, storage_total_gb=0.0)
        ]

        resp = await client.get("/api/v1/databases")

        assert resp.json()["items"][0]["storage_used_pct"] is None

    async def test_filters_accepted(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/databases",
            params={"cloud_provider": "aws", "db_type": "redshift", "is_available": "true"},
        )

        assert resp.status_code == 200

    async def test_unavailable_db(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = [_db_row(is_available=False)]

        resp = await client.get("/api/v1/databases")

        assert resp.json()["items"][0]["is_available"] is False
