"""Tests for GET /api/v1/clusters."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient


def _cluster_row(**overrides: Any) -> dict:
    base: dict[str, Any] = {
        "compute_resource_id": "compute-001",
        "resource_name": "prod-shared",
        "compute_type": "databricks_cluster",
        "cloud_provider": "azure",
        "source_lz_id": "lz-azure-01",
        "subscription_or_account_id": "sub-abc",
        "workspace_id": "1234567890123456",
        "region": "westeurope",
        "state": "running",
        "num_workers": 4,
        "node_type": "Standard_DS3_v2",
        "spark_version": "14.3.x-scala2.12",
        "autoscale_min": 2,
        "autoscale_max": 8,
        "collected_at": datetime(2026, 3, 19, 8, 0, 0, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return base


class TestListClusters:
    async def test_empty_response(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = []

        resp = await client.get("/api/v1/clusters")

        assert resp.status_code == 200
        assert resp.json() == {"items": []}

    async def test_single_cluster_serialised(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = [_cluster_row()]

        resp = await client.get("/api/v1/clusters")

        items = resp.json()["items"]
        assert len(items) == 1
        item = items[0]
        assert item["compute_resource_id"] == "compute-001"
        assert item["state"] == "running"
        assert item["num_workers"] == 4
        assert item["workspace_id"] == "1234567890123456"
        assert item["autoscale_min"] == 2
        assert item["autoscale_max"] == 8
        assert item["collected_at"].startswith("2026-03-19")

    async def test_cloud_provider_filter_accepted(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = []

        resp = await client.get("/api/v1/clusters", params={"cloud_provider": "aws"})

        assert resp.status_code == 200

    async def test_state_filter_accepted(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = [_cluster_row(state="terminated")]

        resp = await client.get("/api/v1/clusters", params={"state": "terminated"})

        assert resp.status_code == 200
        assert resp.json()["items"][0]["state"] == "terminated"

    async def test_workspace_id_filter_accepted(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = [_cluster_row(workspace_id="999")]

        resp = await client.get("/api/v1/clusters", params={"workspace_id": "999"})

        assert resp.status_code == 200
        assert resp.json()["items"][0]["workspace_id"] == "999"
        query = mock_db.fetchall.await_args.args[0]
        assert "workspace_id = ?" in query
        assert "999" in mock_db.fetchall.await_args.args

    async def test_workspace_ids_filter_applies_in_clause(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/clusters",
            params=[("workspace_ids", "adb-1"), ("workspace_ids", "adb-2")],
        )

        assert resp.status_code == 200
        query = mock_db.fetchall.await_args.args[0]
        args = mock_db.fetchall.await_args.args[1:]
        assert "workspace_id IN (?, ?)" in query
        assert "adb-1" in args
        assert "adb-2" in args

    async def test_multiple_clusters(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = [
            _cluster_row(compute_resource_id="c1", resource_name="alpha"),
            _cluster_row(compute_resource_id="c2", resource_name="beta", state="terminated"),
        ]

        resp = await client.get("/api/v1/clusters")

        items = resp.json()["items"]
        assert len(items) == 2
        assert items[0]["resource_name"] == "alpha"
        assert items[1]["state"] == "terminated"
