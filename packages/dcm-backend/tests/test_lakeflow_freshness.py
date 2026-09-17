"""Tests for the real ``as_of`` freshness field and NULL-tolerant mappers.

Feature 013 (T004): the Lakeflow endpoints expose ``as_of`` = the *real*
``MAX(collected_at)`` of the curated lakeflow run timeline (never a constant),
and every field that became NULL after the ``system.lakeflow.*`` migration must
serialize as ``null`` — never coerced to ``0``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.api.services.lakeflow_jobs import _row_to_run, _row_to_task
from app.api.services.lakeflow_overview import fetch_lakeflow_as_of
from app.auth.scope_model import AllowedScope

_UNRESTRICTED = {"x-dcm-platform-role": "super_admin"}
_AS_OF = datetime(2026, 8, 17, 1, 12, tzinfo=UTC)
_RUN_TIMELINE = "curated_dbx_lakeflow_job_run_timeline"


def _wire_as_of(mock_db: AsyncMock, value: dict[str, Any] | None) -> None:
    """Route ``fetchone`` so only the run-timeline freshness query returns a value."""

    async def fetchone(query: str, *args: Any) -> dict[str, Any] | None:
        if _RUN_TIMELINE in query:
            return value
        return None

    mock_db.fetchone.side_effect = fetchone
    mock_db.fetchall.return_value = []


@pytest.mark.asyncio
async def test_fetch_lakeflow_as_of_returns_real_max() -> None:
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value={"as_of": _AS_OF})
    settings = SimpleNamespace(databricks_catalog="cat", databricks_schema="sch")

    result = await fetch_lakeflow_as_of(
        db,  # type: ignore[arg-type]
        settings,  # type: ignore[arg-type]
        AllowedScope(unrestricted=True),
    )

    assert result == _AS_OF.isoformat()
    query = db.fetchone.await_args.args[0]
    assert _RUN_TIMELINE in query
    assert "MAX(collected_at)" in query


@pytest.mark.asyncio
async def test_fetch_lakeflow_as_of_scopes_to_granted_workspaces() -> None:
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value={"as_of": _AS_OF})
    settings = SimpleNamespace(databricks_catalog="cat", databricks_schema="sch")

    await fetch_lakeflow_as_of(
        db,  # type: ignore[arg-type]
        settings,  # type: ignore[arg-type]
        AllowedScope(workspace_ids=["111"]),
    )

    query, *args = db.fetchone.await_args.args
    assert "workspace_id" in query
    assert "111" in args


@pytest.mark.asyncio
async def test_fetch_lakeflow_as_of_none_when_empty() -> None:
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value={"as_of": None})
    settings = SimpleNamespace(databricks_catalog="cat", databricks_schema="sch")

    result = await fetch_lakeflow_as_of(
        db,  # type: ignore[arg-type]
        settings,  # type: ignore[arg-type]
        AllowedScope(unrestricted=True),
    )
    assert result is None


class TestOverviewAsOf:
    async def test_overview_exposes_real_as_of(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        _wire_as_of(mock_db, {"as_of": _AS_OF})

        resp = await client.get("/api/v1/lakeflow/overview", headers=_UNRESTRICTED)

        assert resp.status_code == 200
        assert resp.json()["as_of"] == _AS_OF.isoformat()

    async def test_overview_as_of_not_a_constant_now(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """Freshness reflects ingestion, not wall-clock: a past ts must survive."""
        _wire_as_of(mock_db, {"as_of": _AS_OF})

        resp = await client.get("/api/v1/lakeflow/overview", headers=_UNRESTRICTED)

        as_of = datetime.fromisoformat(resp.json()["as_of"])
        assert as_of == _AS_OF
        assert as_of < datetime.now(UTC)


class TestJobsAsOf:
    async def test_jobs_list_exposes_as_of(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        _wire_as_of(mock_db, {"as_of": _AS_OF})

        resp = await client.get("/api/v1/lakeflow/jobs", headers=_UNRESTRICTED)

        assert resp.status_code == 200
        assert resp.json()["as_of"] == _AS_OF.isoformat()


class TestNullTolerantMappers:
    def test_run_null_durations_stay_none(self) -> None:
        row = {
            "run_id": 42,
            "workflow_id": 7,
            "workspace_id": None,
            "workspace_name": None,
            "status": "running",
            "queued_duration_seconds": None,
            "execution_duration_seconds": None,
            "schedule_lag_seconds": None,
            "duration_seconds": None,
            "creator_user_name": "creator-123",
        }

        run = _row_to_run(row)

        assert run["queued_duration_seconds"] is None
        assert run["execution_duration_seconds"] is None
        assert run["schedule_lag_seconds"] is None
        assert run["duration_seconds"] is None
        assert run["workspace_name"] is None
        # NULL never coerced to 0, and the whole payload stays JSON-serializable.
        assert json.loads(json.dumps(run))["queued_duration_seconds"] is None

    def test_task_null_fields_stay_none(self) -> None:
        row = {
            "run_id": 1,
            "task_id": None,
            "task_key": "extract",
            "status": None,
            "start_time": None,
            "end_time": None,
            "duration_seconds": None,
            "attempt_number": None,
            "error_message": None,
        }

        task = _row_to_task(row)

        assert task["duration_seconds"] is None
        assert task["status"] is None
        json.dumps(task)
