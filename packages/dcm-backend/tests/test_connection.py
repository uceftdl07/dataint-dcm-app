"""Unit tests for Databricks warehouse connection handling."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.db import connection as connection_module
from app.db.connection import DatabricksWarehousePool


def test_is_stale_session_error_detects_closed_handle() -> None:
    exc = Exception(
        "Error during request to server: BAD_REQUEST: Invalid SessionHandle: "
        "Session [01f15edc-f195-1497-a2a5-13681e0d56f9] is closed."
    )
    assert connection_module._is_stale_session_error(exc) is True


def test_is_stale_session_error_ignores_other_failures() -> None:
    assert connection_module._is_stale_session_error(Exception("connection refused")) is False


@pytest.mark.asyncio
async def test_run_with_connection_discards_stale_session(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        databricks_host="dbc-example.cloud.databricks.com",
        databricks_warehouse_id="warehouse-id",
        databricks_catalog="it",
        databricks_schema="monitoring",
        databricks_token="pat-token",
    )
    pool = DatabricksWarehousePool(settings)

    stale_connection = MagicMock(name="stale-connection")
    retry_connection = MagicMock(name="retry-connection")

    acquire_calls = {"count": 0}
    release_calls: list[tuple[MagicMock, bool]] = []

    async def fake_acquire() -> MagicMock:
        acquire_calls["count"] += 1
        if acquire_calls["count"] == 1:
            return stale_connection
        return retry_connection

    async def fake_release(connection: MagicMock, *, healthy: bool) -> None:
        release_calls.append((connection, healthy))

    monkeypatch.setattr(pool, "_acquire", fake_acquire)
    monkeypatch.setattr(pool, "_release", fake_release)

    attempts = {"count": 0}

    def fake_operation(connection: MagicMock) -> dict[str, str]:
        attempts["count"] += 1
        if connection is stale_connection:
            raise Exception("Invalid SessionHandle: Session is closed.")
        return {"id": "user-1"}

    async def fake_to_thread(func: Any, /, *args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)

    monkeypatch.setattr(connection_module.asyncio, "to_thread", fake_to_thread)

    result = await pool._run_with_connection(fake_operation)

    assert result == {"id": "user-1"}
    assert attempts["count"] == 2
    assert (stale_connection, False) in release_calls
    assert (retry_connection, True) in release_calls
