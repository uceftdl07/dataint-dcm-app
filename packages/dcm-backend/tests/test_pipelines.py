"""Tests for GET /api/v1/pipelines and GET /api/v1/pipelines/{name}/runs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient


def _pipeline_row(**overrides: Any) -> dict:
    base: dict[str, Any] = {
        "run_id": "run-001",
        "pipeline_id": "pl-001",
        "pipeline_name": "ingest_daily",
        "cloud_provider": "azure",
        "source_lz_id": "lz-azure-01",
        "pipeline_type": "adf",
        "account": "sub-abc",
        "region": "westeurope",
        "trigger_type": "scheduled",
        "status": "succeeded",
        "start_time": datetime(2026, 3, 19, 8, 0, 0, tzinfo=timezone.utc),
        "end_time": datetime(2026, 3, 19, 8, 5, 0, tzinfo=timezone.utc),
        "duration_seconds": 300.0,
        "error_message": None,
        "collected_at": datetime(2026, 3, 19, 8, 10, 0, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return base


class TestListPipelines:
    async def test_empty_response(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 0
        mock_db.fetchall.return_value = []

        resp = await client.get("/api/v1/pipelines")

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["limit"] == 50
        assert body["offset"] == 0

    async def test_single_row_serialised(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 1
        mock_db.fetchall.return_value = [_pipeline_row()]

        resp = await client.get("/api/v1/pipelines")

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        item = items[0]
        assert item["run_id"] == "run-001"
        assert item["pipeline_type"] == "adf"
        assert item["status"] == "succeeded"
        assert item["duration_seconds"] == 300.0
        assert item["error_message"] is None
        assert item["start_time"].startswith("2026-03-19")

    async def test_pagination_params_forwarded(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 200
        mock_db.fetchall.return_value = []

        resp = await client.get("/api/v1/pipelines", params={"limit": 10, "offset": 50})

        body = resp.json()
        assert body["limit"] == 10
        assert body["offset"] == 50
        assert body["total"] == 200

    async def test_filters_accepted(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 0
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/pipelines",
            params={
                "cloud_provider": "aws",
                "pipeline_type": "glue_job",
                "status": "failed",
                "start_date": "2026-01-01",
                "end_date": "2026-03-31",
            },
        )

        assert resp.status_code == 200

    async def test_databricks_job_filter_accepted(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 0
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/pipelines",
            params={"pipeline_type": "databricks_job"},
        )

        assert resp.status_code == 200
        query = mock_db.fetchall.await_args.args[0]
        assert "databricks:job:%" in query

    async def test_null_start_time_handled(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 1
        mock_db.fetchall.return_value = [_pipeline_row(start_time=None, end_time=None)]

        resp = await client.get("/api/v1/pipelines")

        item = resp.json()["items"][0]
        assert item["start_time"] is None
        assert item["end_time"] is None


class TestGetPipelineRuns:
    async def test_returns_pipeline_name_and_runs(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = [_pipeline_row(pipeline_name="my_pipeline")]

        resp = await client.get("/api/v1/pipelines/my_pipeline/runs")

        assert resp.status_code == 200
        body = resp.json()
        assert body["pipeline_name"] == "my_pipeline"
        assert len(body["runs"]) == 1

    async def test_empty_run_history(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = []

        resp = await client.get("/api/v1/pipelines/unknown_pipeline/runs")

        assert resp.status_code == 200
        assert resp.json()["runs"] == []

    async def test_date_filters_accepted(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/pipelines/my_pipeline/runs",
            params={"start_date": "2026-01-01", "end_date": "2026-03-31", "limit": 5},
        )

        assert resp.status_code == 200
