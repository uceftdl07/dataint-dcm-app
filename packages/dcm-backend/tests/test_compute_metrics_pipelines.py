"""Unit and route tests for the compute **pipeline** endpoints (grain ``dlt_pipeline_id``)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.api.services.compute_metrics_pipelines import (
    fetch_pipeline_cost_trend,
    fetch_pipeline_detail,
    fetch_pipeline_uptime_trend,
    fetch_pipelines_cost,
    fetch_pipelines_efficiency,
    fetch_pipelines_overview,
)
from app.config import Settings

BASE = "/api/v1/databricks/compute"
_PIPELINE_COST_ROLLING = "gold_dbx_compute_pipeline_cost_rolling"
_PIPELINE_COST_DAILY = "gold_dbx_compute_pipeline_cost_daily"
_PIPELINE_EFFICIENCY_ROLLING = "gold_dbx_compute_pipeline_efficiency_rolling"
_PIPELINE_EFFICIENCY_DAILY = "gold_dbx_compute_pipeline_efficiency_daily"


def _settings() -> Settings:
    return Settings(
        databricks_host="https://example.cloud.databricks.com",
        databricks_warehouse_id="wh-1",
        databricks_catalog="cat",
        databricks_schema="sch",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("window_days", [1, 7, 30, 90])
@pytest.mark.parametrize("fetcher", [fetch_pipelines_cost, fetch_pipelines_overview])
async def test_pipelines_read_the_rolling_table_for_the_window(
    fetcher: Any, window_days: int
) -> None:
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetcher(db, _settings(), allowed_lz_ids=None, window_days=window_days)

    sql, *params = db.fetchall.await_args.args
    assert _PIPELINE_COST_ROLLING in sql
    assert "window_days = ?" in sql
    assert window_days in params


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fetcher", "name_fallback"),
    [
        (
            fetch_pipelines_cost,
            "COALESCE(NULLIF(pipeline_name, ''), dlt_pipeline_id) AS pipeline_name",
        ),
        # The overview joins the efficiency snapshot: both sides carry
        # ``pipeline_name`` and ``dlt_pipeline_id``, so the columns must be qualified.
        (
            fetch_pipelines_overview,
            "COALESCE(NULLIF(p.pipeline_name, ''), p.dlt_pipeline_id) AS pipeline_name",
        ),
    ],
)
async def test_pipelines_grain_is_pipeline_id_with_name_fallback(
    fetcher: Any, name_fallback: str
) -> None:
    """Grain ``dlt_pipeline_id``; an unnamed pipeline falls back to the id, not blank."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetcher(db, _settings(), allowed_lz_ids=None)

    sql = db.fetchall.await_args.args[0]
    assert "dlt_pipeline_id" in sql
    assert name_fallback in sql
    # The cost rollup is billing-direct (no cluster grain): the column does not exist
    # there, and the overview does not borrow the efficiency side's one either.
    assert "cluster_count" not in sql


@pytest.mark.asyncio
@pytest.mark.parametrize("fetcher", [fetch_pipelines_cost, fetch_pipelines_overview])
async def test_pipelines_guard_on_the_latest_snapshot(fetcher: Any) -> None:
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetcher(db, _settings(), allowed_lz_ids=None, window_days=7)

    sql = db.fetchall.await_args.args[0]
    assert (
        f"as_of_date = (SELECT MAX(as_of_date) FROM "
        f"`cat`.`sch`.`{_PIPELINE_COST_ROLLING}`)" in sql
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("previous", [0, 0.0, Decimal("0"), -8.0])
@pytest.mark.parametrize("fetcher", [fetch_pipelines_cost, fetch_pipelines_overview])
async def test_pipelines_normalize_a_non_positive_previous_window(
    fetcher: Any, previous: Any
) -> None:
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(
        return_value=[
            {
                "dlt_pipeline_id": "abc-123",
                "cost_usd": 10.0,
                "cost_usd_prev_window": previous,
                "cost_delta_pct": None,
                "_total": 1,
            }
        ]
    )

    result = await fetcher(db, _settings(), allowed_lz_ids=None)

    assert result["items"][0]["cost_usd_prev_window"] is None


@pytest.mark.asyncio
async def test_pipelines_overview_reports_active_pipelines() -> None:
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(
        return_value={
            "total_cost": 80.0,
            "prev_cost": 100.0,
            "active_pipelines": 4,
            "window_start": None,
            "as_of_date": None,
        }
    )

    result = await fetch_pipelines_overview(
        db, _settings(), allowed_lz_ids=None, window_days=30
    )

    assert result["kpis"]["cost_delta_pct"] == -20.0
    assert result["kpis"]["active_pipelines"] == 4
    assert "active_pipelines" in db.fetchone.await_args.args[0]


@pytest.mark.asyncio
async def test_pipelines_overview_left_joins_the_efficiency_snapshot() -> None:
    """The overview shows Lifetime / Prev lifetime / Utilization next to the cost.

    Those three live on the efficiency rollup, joined on the grain **and** on
    ``window_days`` — both tables hold one row per pipeline and per window, so
    omitting it would fan a pipeline out over its four windows.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_pipelines_overview(db, _settings(), allowed_lz_ids=None, window_days=7)

    sql = db.fetchall.await_args.args[0]
    assert _PIPELINE_EFFICIENCY_ROLLING in sql
    assert "LEFT JOIN e" in sql
    # LEFT and never INNER: a serverless pipeline has no cluster to observe, and must
    # keep its billed row.
    assert "INNER JOIN" not in sql
    assert "e.window_days = p.window_days" in sql
    assert "e.uptime_hours," in sql
    assert "e.uptime_hours_prev_window," in sql
    assert "e.utilization_status" in sql
    # Each snapshot is pinned on its own MAX(as_of_date): the two rollups are written
    # separately, and cross-pinning would blank the utilization the day they diverge.
    assert (
        f"as_of_date = (SELECT MAX(as_of_date) FROM "
        f"`cat`.`sch`.`{_PIPELINE_COST_ROLLING}`)" in sql
    )
    assert (
        f"as_of_date = (SELECT MAX(as_of_date) FROM "
        f"`cat`.`sch`.`{_PIPELINE_EFFICIENCY_ROLLING}`)" in sql
    )


@pytest.mark.asyncio
async def test_pipelines_overview_derives_the_uptime_delta() -> None:
    """``Prev lifetime`` carries a per-cent variation, like the all-purpose page."""
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(
        return_value=[
            {
                "dlt_pipeline_id": "abc-123",
                "cost_usd": 10.0,
                "uptime_hours": 46.8,
                "uptime_hours_prev_window": 41.0,
                "utilization_status": "OPTIMAL",
                "_total": 1,
            }
        ]
    )

    result = await fetch_pipelines_overview(db, _settings(), allowed_lz_ids=None)

    assert result["items"][0]["uptime_hours_delta_pct"] == 14.1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fetcher", "prefix"),
    [(fetch_pipelines_cost, ""), (fetch_pipelines_overview, "p.")],
)
async def test_pipelines_list_only_the_grains_that_cost_something(
    fetcher: Any, prefix: str
) -> None:
    """A pipeline that neither cost nor consumed anything over the window is not listed.

    The rolling snapshot holds one row per known pipeline: measured on dev, 3 097 of the
    6 062 rows of the 30-day window are at $0.00 / 0 DBU — materialized views that each
    own a ``dlt_pipeline_id``. They made the footer count read like an inventory and left
    every metric column on "—". DBU is part of the test: a grain that ran without being
    charged still ran.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetcher(db, _settings(), allowed_lz_ids=None, window_days=30)

    sql = db.fetchall.await_args.args[0]
    assert (
        f"(COALESCE({prefix}cost_usd, 0) > 0 OR COALESCE({prefix}dbu_quantity, 0) > 0)" in sql
    )


@pytest.mark.asyncio
async def test_pipelines_efficiency_is_not_filtered_on_cost() -> None:
    """The efficiency snapshot carries no cost column — filtering it there would throw."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_pipelines_efficiency(db, _settings(), allowed_lz_ids=None, window_days=30)

    sql = db.fetchall.await_args.args[0]
    assert "cost_usd" not in sql
    assert "dbu_quantity" not in sql


@pytest.mark.asyncio
async def test_pipelines_search_narrows_the_billed_population() -> None:
    """Search is ANDed to the cost filter, not substituted for it."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_pipelines_overview(
        db, _settings(), allowed_lz_ids=None, window_days=30, search="bronze"
    )

    sql, *params = db.fetchall.await_args.args
    assert "COALESCE(p.cost_usd, 0) > 0" in sql
    assert "LOWER(p.pipeline_name) LIKE ?" in sql
    assert "%bronze%" in params


@pytest.mark.asyncio
@pytest.mark.parametrize("fetcher", [fetch_pipelines_cost, fetch_pipelines_overview])
async def test_pipelines_list_only_the_classic_dlt_compute(fetcher: Any) -> None:
    """The page is about the DLT **cluster** compute, not about DLT at large.

    ``compute_kind`` is carried by the two cost tables (gold derives it from
    ``usage_metadata.cluster_id IS NOT NULL``); ``CLASSIC`` means a PIPELINE /
    PIPELINE_MAINTENANCE cluster served the update. Measured on dev at 30 days: 178
    classic pipelines and 6 216 DBU, against 2 789 serverless ones and 43 375 DBU.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetcher(db, _settings(), allowed_lz_ids=None, window_days=30)

    sql = db.fetchall.await_args.args[0]
    assert "compute_kind = 'CLASSIC'" in sql
    # Served in the payload too, so a reader can tell which compute it is looking at.
    assert "compute_kind," in sql


@pytest.mark.asyncio
async def test_pipelines_overview_kpis_are_scoped_to_the_classic_compute() -> None:
    """Otherwise the cards would total the whole DLT bill above a classic-only list.

    Measured on dev at 30 days: $23 588 of DLT against $1 903 of classic DLT.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_pipelines_overview(
        db, _settings(), allowed_lz_ids=None, window_days=30
    )

    kpi_sql = db.fetchone.await_args.args[0]
    assert "active_pipelines" in kpi_sql
    assert "compute_kind = 'CLASSIC'" in kpi_sql


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fetcher_kwargs",
    [
        (fetch_pipelines_efficiency, {"window_days": 30}),
        (fetch_pipeline_uptime_trend, {}),
    ],
)
async def test_pipelines_efficiency_carries_no_compute_kind_filter(
    fetcher_kwargs: tuple[Any, dict[str, Any]],
) -> None:
    """The efficiency tables have no such column, and need none.

    ``system.compute.node_timeline`` only samples clusters, so a serverless pipeline has
    no row there to exclude. Filtering would raise ``UNRESOLVED_COLUMN``.
    """
    fetcher, kwargs = fetcher_kwargs
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    if fetcher is fetch_pipeline_uptime_trend:
        await fetcher(db, _settings(), None, "abc-123", **kwargs)
    else:
        await fetcher(db, _settings(), allowed_lz_ids=None, **kwargs)

    sql = db.fetchall.await_args.args[0]
    assert "compute_kind" not in sql


@pytest.mark.asyncio
async def test_pipeline_cost_trend_sums_the_classic_compute_only() -> None:
    """The daily grain carries ``compute_kind``: an unfiltered ``SUM`` would add the
    serverless share back into a classic-only series."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])

    await fetch_pipeline_cost_trend(db, _settings(), None, "abc-123")

    sql = db.fetchall.await_args.args[0]
    assert _PIPELINE_COST_DAILY in sql
    assert "compute_kind = 'CLASSIC'" in sql


@pytest.mark.asyncio
async def test_pipeline_detail_filters_the_cost_side_only() -> None:
    """A pipeline that ran both ways has two rolling rows, and the detail keeps one.

    Without the filter the ``ORDER BY cost_usd DESC LIMIT 1`` would silently return the
    serverless row. The efficiency query stays unfiltered — no such column there.
    """
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)

    await fetch_pipeline_detail(db, _settings(), None, "abc-123", window_days=30)

    sqls = [call.args[0] for call in db.fetchone.await_args_list]
    cost_sql = next(s for s in sqls if _PIPELINE_COST_ROLLING in s)
    eff_sql = next(s for s in sqls if _PIPELINE_EFFICIENCY_ROLLING in s)
    assert "compute_kind = 'CLASSIC'" in cost_sql
    assert "compute_kind" not in eff_sql


@pytest.mark.asyncio
async def test_pipelines_overview_keeps_an_unmeasured_pipeline_listed() -> None:
    """Observed on dev: a pipeline billed $941.47 over 30 d with no efficiency row."""
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(
        return_value=[
            {
                "dlt_pipeline_id": "05e63a07-be8b-4500-8c5b-8cc60d25f594",
                "cost_usd": 941.47,
                "uptime_hours": None,
                "uptime_hours_prev_window": None,
                "utilization_status": None,
                "_total": 1,
            }
        ]
    )

    result = await fetch_pipelines_overview(db, _settings(), allowed_lz_ids=None)

    item = result["items"][0]
    assert item["cost_usd"] == 941.47
    assert item["uptime_hours"] is None
    assert item["uptime_hours_delta_pct"] is None
    assert item["utilization_status"] is None


# ---------------------------------------------------------------------------
# Efficiency (024 T005) — grain ``dlt_pipeline_id``, no ``is_zombie`` (R8)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("window_days", [1, 7, 30, 90])
async def test_pipelines_efficiency_reads_the_rolling_table_for_the_window(
    window_days: int,
) -> None:
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_pipelines_efficiency(
        db, _settings(), allowed_lz_ids=None, window_days=window_days
    )

    sql, *params = db.fetchall.await_args.args
    assert _PIPELINE_EFFICIENCY_ROLLING in sql
    assert "window_days = ?" in sql
    assert window_days in params
    assert (
        f"as_of_date = (SELECT MAX(as_of_date) FROM "
        f"`cat`.`sch`.`{_PIPELINE_EFFICIENCY_ROLLING}`)" in sql
    )


@pytest.mark.asyncio
async def test_pipelines_efficiency_grain_and_no_zombie_column() -> None:
    """``dlt_pipeline_id`` + name fallback; ``is_zombie`` absent at this grain (R8).

    ``cluster_count`` **is** exposed here, unlike ``/pipelines/cost``: the efficiency
    rollup goes through the R7 ``cluster_id → dlt_pipeline_id`` mapping, so it knows
    how many PIPELINE clusters ran, while the cost rollup is billing-direct.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_pipelines_efficiency(db, _settings(), allowed_lz_ids=None)

    sql = db.fetchall.await_args.args[0]
    assert "COALESCE(NULLIF(pipeline_name, ''), dlt_pipeline_id) AS pipeline_name" in sql
    assert "cpu_util_p95_pct" in sql
    assert "cluster_count" in sql
    assert "is_zombie" not in sql
    assert "cluster_name" not in sql
    assert "cluster_type" not in sql


@pytest.mark.asyncio
async def test_pipelines_efficiency_derives_the_previous_window_deltas() -> None:
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(
        return_value=[
            {
                "dlt_pipeline_id": "pipe-abc",
                "uptime_hours": 20.0,
                "uptime_hours_prev_window": 25.0,
                "idle_pct": 12.0,
                "idle_pct_prev_window": 20.0,
                "_total": 1,
            }
        ]
    )

    result = await fetch_pipelines_efficiency(db, _settings(), allowed_lz_ids=None)

    item = result["items"][0]
    assert item["uptime_hours_delta_pct"] == -20.0
    assert item["idle_pct_delta_pts"] == -8.0


# ---------------------------------------------------------------------------
# Detail + trends (024 T005)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_detail_has_no_governance_key_at_all() -> None:
    db = AsyncMock()
    db.fetchone = AsyncMock(
        return_value={
            "cloud_provider": "aws",
            "workspace_id": "1234",
            "dlt_pipeline_id": "pipe-abc",
            "cost_usd": 12.0,
            "window_start": "2026-08-10",
            "as_of_date": "2026-09-08",
        }
    )

    result = await fetch_pipeline_detail(
        db, _settings(), None, "pipe-abc", window_days=30
    )

    assert result is not None
    assert "governance" not in result
    assert result["dlt_pipeline_id"] == "pipe-abc"


@pytest.mark.asyncio
async def test_pipeline_detail_returns_none_when_out_of_scope() -> None:
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)

    result = await fetch_pipeline_detail(db, _settings(), None, "nope", window_days=30)

    assert result is None


@pytest.mark.asyncio
async def test_pipeline_detail_serves_cost_when_serverless_has_no_efficiency() -> None:
    """A serverless DLT pipeline has no ``node_timeline``: cost only, and that is fine."""
    cost_row = {
        "cloud_provider": "aws",
        "workspace_id": "5566",
        "dlt_pipeline_id": "pipe-abc",
        "cost_usd": 12.0,
        "window_start": "2026-08-10",
        "as_of_date": "2026-09-08",
    }
    db = AsyncMock()
    db.fetchone = AsyncMock(side_effect=[cost_row, None])

    result = await fetch_pipeline_detail(
        db, _settings(), None, "pipe-abc", window_days=30
    )

    assert result is not None
    assert result["efficiency"] is None
    assert result["cost"]["cost_usd"] == 12.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("granularity", "expected"),
    [("day", "day"), ("week", "week"), ("month", "month"), ("'; DROP", "day")],
)
async def test_pipeline_cost_trend_reads_the_daily_table(
    granularity: str, expected: str
) -> None:
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])

    result = await fetch_pipeline_cost_trend(
        db, _settings(), None, "pipe-abc", granularity=granularity
    )

    sql, *params = db.fetchall.await_args.args
    assert _PIPELINE_COST_DAILY in sql
    assert f"date_trunc('{expected}', period_start)" in sql
    assert "dlt_pipeline_id = ?" in sql
    assert "pipe-abc" in params
    assert result["granularity"] == expected


@pytest.mark.asyncio
async def test_pipeline_uptime_trend_weights_idle_by_uptime() -> None:
    db = AsyncMock()
    db.fetchall = AsyncMock(
        return_value=[
            {"bucket": "2026-09-01", "uptime_hours": 5.0, "idle_pct": 8.26},
            {"bucket": "2026-09-02", "uptime_hours": 0, "idle_pct": None},
        ]
    )

    result = await fetch_pipeline_uptime_trend(db, _settings(), None, "pipe-abc")

    sql = db.fetchall.await_args.args[0]
    assert _PIPELINE_EFFICIENCY_DAILY in sql
    assert "SUM(idle_pct * uptime_hours)" in sql
    assert result["items"][0]["idle_pct"] == 8.3
    assert result["items"][1]["idle_pct"] is None


class TestPipelinesWindowDays:
    LIST_PATHS = ("/pipelines/overview", "/pipelines/cost", "/pipelines/efficiency")

    @pytest.mark.parametrize("window_days", [1, 7, 30, 90])
    @pytest.mark.parametrize("path", LIST_PATHS)
    async def test_accepts_the_four_materialized_windows(
        self, client: AsyncClient, mock_db: AsyncMock, path: str, window_days: int
    ) -> None:
        resp = await client.get(f"{BASE}{path}", params={"window_days": window_days})

        assert resp.status_code == 200
        assert resp.json()["window"]["window_days"] == window_days

    @pytest.mark.parametrize("window_days", [0, 5, 14, 365, -7])
    @pytest.mark.parametrize("path", LIST_PATHS)
    async def test_rejects_any_other_window(
        self, client: AsyncClient, mock_db: AsyncMock, path: str, window_days: int
    ) -> None:
        resp = await client.get(f"{BASE}{path}", params={"window_days": window_days})

        assert resp.status_code == 422


async def test_pipelines_overview_route_returns_the_pipeline_grain(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.return_value = {
        "total_cost": 12.0,
        "prev_cost": 8.0,
        "active_pipelines": 1,
        "window_start": "2026-09-01",
        "as_of_date": "2026-09-07",
    }
    mock_db.fetchall.return_value = [
        {
            "cloud_provider": "aws",
            "workspace_id": "1234",
            "dlt_pipeline_id": "pipe-abc",
            "pipeline_name": "bronze_to_silver",
            "cost_usd": 12.0,
            "_total": 1,
        }
    ]

    resp = await client.get(f"{BASE}/pipelines/overview")

    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["dlt_pipeline_id"] == "pipe-abc"
    assert item["pipeline_name"] == "bronze_to_silver"
    assert "cluster_count" not in item


async def test_pipelines_cost_empty_200(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchall.return_value = []

    resp = await client.get(f"{BASE}/pipelines/cost")

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["window"]["window_days"] == 1


async def test_pipelines_efficiency_is_not_swallowed_by_the_id_segment(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """Route order: ``/pipelines/efficiency`` is a list, not ``dlt_pipeline_id``."""
    mock_db.fetchall.return_value = []

    resp = await client.get(f"{BASE}/pipelines/efficiency")

    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "cost" not in body
    assert "efficiency" not in body


async def test_pipelines_efficiency_route_returns_the_pipeline_grain(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchall.return_value = [
        {
            "cloud_provider": "aws",
            "workspace_id": "1234",
            "dlt_pipeline_id": "pipe-abc",
            "pipeline_name": "bronze_to_silver",
            "cluster_count": 8,
            "cpu_util_p95_pct": 55.0,
            "idle_pct": 12.0,
            "idle_pct_prev_window": 20.0,
            "uptime_hours": 20.0,
            "uptime_hours_prev_window": 25.0,
            "_total": 1,
        }
    ]

    resp = await client.get(f"{BASE}/pipelines/efficiency", params={"window_days": 7})

    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["dlt_pipeline_id"] == "pipe-abc"
    assert item["uptime_hours_delta_pct"] == -20.0
    assert "is_zombie" not in item


async def test_pipeline_detail_unknown_id_is_404(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.return_value = None

    resp = await client.get(f"{BASE}/pipelines/does-not-exist")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Pipeline not found"


async def test_pipeline_trends_routes_take_no_window_days(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchall.return_value = []

    for suffix in ("cost-trend", "uptime-trend"):
        resp = await client.get(
            f"{BASE}/pipelines/pipe-abc/{suffix}", params={"granularity": "month"}
        )

        assert resp.status_code == 200
        assert resp.json()["granularity"] == "month"
