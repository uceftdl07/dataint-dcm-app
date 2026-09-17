"""Unit tests for Lakeflow Overview aggregation helpers."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.api.services.lakeflow_overview import _fetch_success_buckets
from app.auth.scope_model import AllowedScope


@pytest.mark.asyncio
async def test_success_buckets_bind_select_params_before_where() -> None:
    """Positional `?` must follow SQL appearance order (SELECT then WHERE).

    A workspace filter previously prepended WHERE params, so CASE windows
    received workspace_id as dates → activity KPIs stayed at 0 while
    timeline / distinct_ko (WHERE-only queries) stayed correct.
    """
    db = AsyncMock()
    db.fetchone = AsyncMock(
        return_value={
            "activity_cur_terminal": 1,
            "activity_cur_succeeded": 0,
            "activity_cur_failed": 1,
            "activity_cur_timed_out": 0,
            "activity_cur_cancelled": 0,
        }
    )
    start = date(2026, 7, 9)
    end = date(2026, 8, 7)
    buckets = {"activity_cur": (start, end)}

    out = await _fetch_success_buckets(
        db,
        "catalog.schema.gold_dbx_workflow_success_rate",
        AllowedScope(unrestricted=True),
        None,
        None,
        ["1294448047628701"],
        buckets,
    )

    assert out["activity_cur"]["terminal"] == 1
    assert out["activity_cur"]["failed"] == 1
    assert out["activity_cur"]["ko"] == 1

    _sql, *params = db.fetchone.await_args.args
    # 5 metrics × (start, end) for the SELECT CASE windows
    assert params[:10] == [start, end] * 5
    # WHERE: the requested workspace then the outer date range. One canonical id
    # is bound, not both spellings: the ``adb-`` prefix is stripped in SQL on the
    # column side, so a single parameter matches either form stored in gold.
    assert params[10] == "1294448047628701"
    assert "adb-1294448047628701" not in params
    assert "substr(workspace_id, 5)" in _sql
    assert params[-2:] == [start, end]
    assert _sql.index("CASE WHEN") < _sql.index("WHERE")
