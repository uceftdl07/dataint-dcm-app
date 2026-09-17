"""Unit tests for Compute Metrics service helpers."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.services.compute_metrics_clusters import (
    fetch_cluster_detail,
    fetch_cluster_lifetime_trend,
    fetch_clusters_cost,
    fetch_clusters_efficiency,
    fetch_clusters_governance,
    fetch_clusters_overview,
)
from app.api.services.compute_metrics_common import (
    _clamp_page,
    _resolve_period,
    _row_to_dict,
    _scope_where,
)
from app.api.services.compute_metrics_forecast import fetch_forecast
from app.api.services.compute_metrics_recommendations import (
    fetch_recommendations,
    fetch_recommendations_summary,
)
from app.api.services.compute_metrics_warehouses import (
    fetch_warehouse_cost_trend,
    fetch_warehouse_detail,
    fetch_warehouse_slow_queries,
    fetch_warehouses_cost,
    fetch_warehouses_overview,
    fetch_warehouses_query_performance,
)
from app.config import Settings


def _settings() -> Settings:
    return Settings(
        databricks_host="https://example.cloud.databricks.com",
        databricks_warehouse_id="wh-1",
        databricks_catalog="cat",
        databricks_schema="sch",
    )


@pytest.mark.parametrize(
    ("period_start", "period_end", "expected_start"),
    [
        (date(2026, 1, 1), date(2026, 1, 31), date(2026, 1, 1)),
        (date(2026, 2, 1), date(2026, 1, 1), date(2026, 1, 1)),
    ],
)
def test_resolve_period_explicit_dates(
    period_start: date, period_end: date, expected_start: date
) -> None:
    start, end = _resolve_period(period_start, period_end)
    assert start == expected_start
    assert end == max(period_start, period_end)


def test_resolve_period_default_30d_window() -> None:
    start, end = _resolve_period(None, None, window="30d")
    assert (end - start).days == 29


def test_clamp_page_caps_size() -> None:
    page, size = _clamp_page(0, 999)
    assert page == 1
    assert size == 200


def test_scope_where_with_lz_column() -> None:
    """RBAC scope and the client's own LZ selection are two separate conditions."""
    conditions, params = _scope_where(
        ["lz-a", "lz-b"],
        "lz-a",
        None,
        ["ws-1"],
        has_lz_column=True,
        cloud_provider="azure",
    )
    # RBAC first: the caller's two project dimensions, ORed.
    assert conditions[0] == "(source_lz_id IN (?, ?))"
    assert params[:2] == ["lz-a", "lz-b"]
    # then the requested LZ, ANDed — a request can only narrow the scope.
    assert "source_lz_id IN (?)" in conditions[1]
    assert "LOWER(cloud_provider) = ?" in conditions
    assert "workspace_id IN" in " ".join(conditions)


def test_scope_where_ors_both_project_dimensions() -> None:
    """A row is in scope when its LZ *or* its workspace is granted (decision D2)."""
    conditions, params = _scope_where(
        ["lz-a"],
        None,
        None,
        None,
        has_lz_column=True,
        allowed_workspace_ids=["1234"],
    )
    assert conditions == ["(source_lz_id IN (?) OR workspace_id IN (?, ?))"]
    # gold tables store both the bare id and the ``adb-`` form (order unspecified).
    assert params[0] == "lz-a"
    assert set(params[1:]) == {"1234", "adb-1234"}


def test_scope_where_without_lz_column_scopes_on_the_workspace_dimension() -> None:
    """``gold_dbx_compute_*`` has no ``source_lz_id``: the workspace scope is all there is."""
    conditions, params = _scope_where(
        ["lz-a"],
        None,
        None,
        None,
        has_lz_column=False,
        allowed_workspace_ids=["ws-1"],
    )
    assert not any("source_lz_id" in c for c in conditions)
    assert conditions == ["(workspace_id IN (?, ?))"]
    assert set(params) == {"ws-1", "adb-ws-1"}


def test_scope_where_without_lz_column_and_no_workspace_scope_returns_no_rows() -> None:
    """The leak this closes: a scoped caller used to read every workspace here.

    With no ``source_lz_id`` column the LZ dimension cannot be expressed, so a
    project that grants no Databricks workspace must see nothing rather than the
    whole platform's compute metrics.
    """
    conditions, params = _scope_where(
        ["lz-a"],
        None,
        None,
        None,
        has_lz_column=False,
        allowed_workspace_ids=[],
    )
    assert conditions == ["1 = 0"]
    assert params == []


def test_scope_where_unrestricted_caller_has_no_rbac_clause() -> None:
    conditions, params = _scope_where(
        None,
        None,
        None,
        None,
        has_lz_column=False,
        allowed_workspace_ids=None,
    )
    assert conditions == []
    assert params == []


def test_row_to_dict_converts_numpy_array_values() -> None:
    class FakeArray:
        __module__ = "numpy"

        def __init__(self, values: list[str]) -> None:
            self._values = values

        def tolist(self) -> list[str]:
            return self._values

    row = {"personas": FakeArray(["FIN", "GOV"]), "status": "OPEN"}
    result = _row_to_dict(row)
    assert result == {"personas": ["FIN", "GOV"], "status": "OPEN"}


def test_row_to_dict_converts_decimal_to_float() -> None:
    """A DECIMAL column must not reach the front as a JSON string.

    The routes annotate ``-> dict[str, Any]``, so FastAPI treats it as a response
    model and Pydantic v2 renders a ``Decimal`` as ``"7.5"``. The front types these
    fields as `number` and calls ``toFixed`` on them.
    """
    row = {
        "cost_usd": Decimal("215.330931"),
        "cost_usd_prev_window": Decimal("207.627028"),
        "uptime_hours": Decimal("14.733333"),
        "cpu_util_p95_pct": Decimal("7.5"),
        "idle_pct": 37.5,
        "cluster_name": "etl",
        "autoscale_min_workers": 2,
        "autoscale_enabled": True,
        "worker_node_type": None,
    }
    result = _row_to_dict(row)

    for key in ("cost_usd", "cost_usd_prev_window", "uptime_hours", "cpu_util_p95_pct"):
        assert isinstance(result[key], float), f"{key} is {type(result[key]).__name__}"
    assert result["cost_usd"] == pytest.approx(215.330931)
    assert result["cpu_util_p95_pct"] == pytest.approx(7.5)
    # Everything else keeps its type — a bool must not become 1.0.
    assert result["idle_pct"] == pytest.approx(37.5)
    assert result["cluster_name"] == "etl"
    assert result["autoscale_min_workers"] == 2
    assert result["autoscale_enabled"] is True
    assert result["worker_node_type"] is None


def test_row_to_dict_decimals_survive_pydantic_as_numbers() -> None:
    """The end of the chain: what the browser actually receives."""
    from pydantic import TypeAdapter

    payload = _row_to_dict({"cost_usd": Decimal("215.330931"), "idle_pct": None})
    rendered = TypeAdapter(dict[str, Any]).dump_json(payload)

    assert rendered == b'{"cost_usd":215.330931,"idle_pct":null}'


def test_scope_where_empty_workspace_selection_returns_no_rows() -> None:
    conditions, _params = _scope_where(
        None,
        None,
        None,
        [],
        has_lz_column=True,
    )
    assert "1 = 0" in conditions


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fetcher",
    [
        fetch_clusters_overview,
        fetch_clusters_cost,
        fetch_clusters_efficiency,
        fetch_clusters_governance,
    ],
)
async def test_cluster_list_views_only_return_all_purpose(fetcher: Any) -> None:
    """024 T002: the cluster tab is interactive compute only.

    ``ALL_PURPOSE`` is a hard predicate, not an optional column filter — a JOB or
    PIPELINE row must never leak into the cluster list even when no filter is set,
    since those grains now have their own endpoints.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetcher(db, _settings(), allowed_lz_ids=None)

    sql = db.fetchall.await_args.args[0]
    assert "UPPER(cluster_type) = 'ALL_PURPOSE'" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize("fetcher", [fetch_clusters_overview, fetch_clusters_cost])
async def test_clusters_list_only_the_grains_that_cost_something(fetcher: Any) -> None:
    """An all-purpose cluster idle for the whole window is not listed (2026-09-09).

    Same rule as the jobs and pipelines services. Both tabs read the same rolling table
    under the alias ``c``, so the predicate is identical on the two of them.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetcher(db, _settings(), allowed_lz_ids=None, window_days=30)

    sql = db.fetchall.await_args.args[0]
    assert "(COALESCE(c.cost_usd, 0) > 0 OR COALESCE(c.dbu_quantity, 0) > 0)" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fetcher", "extra"),
    # Governance has no rolling window: it reads a snapshot of the current state.
    [(fetch_clusters_efficiency, {"window_days": 30}), (fetch_clusters_governance, {})],
)
async def test_clusters_efficiency_and_governance_are_not_filtered_on_cost(
    fetcher: Any, extra: dict[str, Any]
) -> None:
    """Neither tab is a billing list.

    Efficiency exists to show what a cluster did with the time it was up, and governance
    exists to surface what nobody is watching — a zombie or an unused cluster is *exactly*
    the row a cost filter would hide.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetcher(db, _settings(), allowed_lz_ids=None, **extra)

    sql = db.fetchall.await_args.args[0]
    assert "COALESCE(c.cost_usd, 0) > 0" not in sql
    assert "COALESCE(e.cost_usd, 0) > 0" not in sql


@pytest.mark.asyncio
async def test_clusters_overview_search_narrows_the_billed_population() -> None:
    """Search and the column filters are ANDed to the cost filter, not substituted."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_clusters_overview(
        db, _settings(), allowed_lz_ids=None, window_days=30, search="analytics"
    )

    sql, *params = db.fetchall.await_args.args
    assert "(COALESCE(c.cost_usd, 0) > 0 OR COALESCE(c.dbu_quantity, 0) > 0)" in sql
    assert "LOWER(c.cluster_name) LIKE ?" in sql
    assert "%analytics%" in params


@pytest.mark.asyncio
async def test_forecast_includes_projection_after_selected_period() -> None:
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])

    result = await fetch_forecast(
        db,
        _settings(),
        allowed_lz_ids=None,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        metric_name="cost_usd",
    )

    params = [
        param
        for call in db.fetchall.await_args_list
        for param in call.args[1:]
    ]
    assert date(2026, 9, 7) in params
    assert result["period"]["to"] == "2026-08-31"


@pytest.mark.asyncio
async def test_forecast_actual_curve_covers_the_same_population_as_the_projection() -> None:
    """The two curves share an axis, so they must describe the same spend.

    The projection sums CLUSTER (interactive only), JOB, PIPELINE and WAREHOUSE.
    An actual curve built from the cluster and warehouse tables alone would drop
    every serverless job — which has no cluster row anywhere — while counting the
    ephemeral job clusters the CLUSTER pass deliberately leaves out.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])

    await fetch_forecast(
        db,
        _settings(),
        allowed_lz_ids=None,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        metric_name="cost_usd",
    )

    actual_sql = db.fetchall.await_args_list[1].args[0]
    assert "gold_dbx_compute_cluster_cost_daily" in actual_sql
    assert "gold_dbx_compute_job_cluster_cost_daily" in actual_sql
    assert "gold_dbx_compute_pipeline_cost_daily" in actual_sql
    assert "gold_dbx_compute_warehouse_cost_daily" in actual_sql
    assert actual_sql.count("cluster_type NOT IN ('JOB', 'PIPELINE')") == 1


@pytest.mark.asyncio
async def test_forecast_actual_curve_stops_at_the_last_complete_day() -> None:
    """The projection describes a whole day, so the observed curve must too.

    The pipeline excludes the day in progress from training. Summing that same
    partially loaded day here puts it far below its own projection — by a margin
    that shrinks with every hour of the day — and reads as an over-forecast that
    the very same rows stop showing tomorrow.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    today = datetime.now(UTC).date()

    await fetch_forecast(
        db,
        _settings(),
        allowed_lz_ids=None,
        period_start=today - timedelta(days=30),
        period_end=today,
        metric_name="cost_usd",
    )

    _, *params = db.fetchall.await_args_list[1].args
    assert today - timedelta(days=1) in params
    assert today not in params


@pytest.mark.asyncio
async def test_forecast_actual_curve_is_restricted_to_the_projected_objects() -> None:
    """Only objects with enough history are projected; the observed curve follows.

    Summing every object here raises the actual line by the spend of those the
    projection leaves out, which reads as an under-forecast. The eligibility rule
    is not restated in SQL — it would drift from the pipeline on the next tuning:
    the forecast table itself is the record of what was projected.

    The semi-join reads the same horizon window as the projection query, so the
    two cannot disagree: a table holding only past horizons would otherwise turn
    the restriction on and then match nothing, blanking the observed curve.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(
        side_effect=[
            [{"object_type": "CLUSTER", "object_id": "c-1", "metric_name": "cost_usd"}],
            [],
        ]
    )

    await fetch_forecast(
        db,
        _settings(),
        allowed_lz_ids=None,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        metric_name="cost_usd",
    )

    forecast_sql, *forecast_params = db.fetchall.await_args_list[0].args
    actual_sql, *params = db.fetchall.await_args_list[1].args
    assert (
        actual_sql.count("WHERE object_type = ? AND horizon_date >= ? AND horizon_date <= ?)") == 4
    )
    assert actual_sql.count("gold_dbx_compute_forecast_daily") == 4
    for id_column in ("cluster_id", "job_id", "dlt_pipeline_id", "warehouse_id"):
        assert f"{id_column} IN (SELECT object_id FROM" in actual_sql
    for match_type in ("CLUSTER", "JOB", "PIPELINE", "WAREHOUSE"):
        assert match_type in params
    # Same horizon window on both sides, or the restriction can match nothing
    # while the projection it mirrors returned rows.
    assert [p for p in forecast_params if isinstance(p, date)] == [
        date(2026, 8, 1),
        date(2026, 9, 7),
    ]
    assert params.count(date(2026, 9, 7)) == 4
    assert params.count(date(2026, 8, 1)) == 8  # window start, then semi-join, per branch


@pytest.mark.asyncio
async def test_forecast_actual_curve_is_unfiltered_when_nothing_was_projected() -> None:
    """An empty projection must not empty the observed curve along with it.

    Between a table drop — or a first deployment — and the next pipeline run, the
    observed history is the only thing left to draw. Semi-joining an empty
    forecast table would blank the widget instead.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])

    await fetch_forecast(
        db,
        _settings(),
        allowed_lz_ids=None,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        metric_name="cost_usd",
    )

    actual_sql = db.fetchall.await_args_list[1].args[0]
    assert "SELECT object_id FROM" not in actual_sql
    assert "gold_dbx_compute_cluster_cost_daily" in actual_sql


@pytest.mark.asyncio
async def test_forecast_actual_curve_is_restricted_to_the_selected_object_type() -> None:
    """A JOB detail view must not add cluster or warehouse spend to its own curve."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])

    await fetch_forecast(
        db,
        _settings(),
        allowed_lz_ids=None,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        metric_name="cost_usd",
        object_type="job",
        object_id="123456789",
    )

    actual_sql, *params = db.fetchall.await_args_list[1].args
    assert "gold_dbx_compute_job_cluster_cost_daily" in actual_sql
    assert "gold_dbx_compute_cluster_cost_daily" not in actual_sql
    assert "gold_dbx_compute_warehouse_cost_daily" not in actual_sql
    assert "job_id = ?" in actual_sql
    assert "123456789" in params


@pytest.mark.asyncio
async def test_clusters_cost_builds_search_and_sku_sql() -> None:
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_clusters_cost(
        db,
        _settings(),
        allowed_lz_ids=None,
        window_days=7,
        search="analytics",
        sku_group="photon",
        sort="name",
        page=1,
        page_size=10,
    )

    sql, *params = db.fetchall.await_args.args
    # Qualified: the query joins the workspace dimension, so a bare column name
    # would be ambiguous.
    assert "LOWER(c.cluster_name) LIKE ?" in sql
    assert "LOWER(c.sku_group) = ?" in sql
    assert "%analytics%" in params
    assert "photon" in params
    assert "c.cluster_name ASC" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize("window_days", [1, 7, 30, 90])
async def test_clusters_cost_reads_the_rolling_table_for_the_window(window_days: int) -> None:
    """SC-003: the list views leave ``*_cluster_cost_daily`` to the trend endpoints."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_clusters_cost(db, _settings(), allowed_lz_ids=None, window_days=window_days)

    sql, *params = db.fetchall.await_args.args
    assert "gold_dbx_compute_cluster_cost_rolling" in sql
    assert "gold_dbx_compute_cluster_cost_daily" not in sql
    assert "window_days = ?" in sql
    assert window_days in params
    # No snapshot pivot left to do: the rolling table already carries one row per
    # cluster and per window.
    assert "QUALIFY ROW_NUMBER()" not in sql


@pytest.mark.asyncio
async def test_clusters_cost_guards_dbu_cost_against_a_zero_divisor() -> None:
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_clusters_cost(db, _settings(), allowed_lz_ids=None)

    sql = db.fetchall.await_args.args[0]
    assert "NULLIF(c.dbu_quantity, 0)" in sql


@pytest.mark.asyncio
async def test_clusters_cost_left_joins_the_workspace_dimension() -> None:
    """A workspace missing from the dimension must not drop its clusters."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_clusters_cost(db, _settings(), allowed_lz_ids=None)

    sql = db.fetchall.await_args.args[0]
    assert "dim_dbx_workspace" in sql
    assert "LEFT JOIN ws" in sql
    assert "INNER JOIN ws" not in sql


@pytest.mark.asyncio
async def test_clusters_cost_exposes_the_window_bounds_read_from_gold() -> None:
    """R5: ``from_date``/``to_date`` come from the data, never from ``today``."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(
        return_value={"window_start": date(2026, 8, 29), "as_of_date": date(2026, 9, 4)}
    )

    result = await fetch_clusters_cost(db, _settings(), allowed_lz_ids=None, window_days=7)

    assert result["window"] == {
        "window_days": 7,
        "from_date": "2026-08-29",
        "to_date": "2026-09-04",
    }
    # ``period`` is kept for existing callers and carries the same pair of dates.
    assert result["period"] == {"from": "2026-08-29", "to": "2026-09-04"}


@pytest.mark.asyncio
async def test_clusters_cost_window_bounds_are_null_when_the_scope_is_empty() -> None:
    """No row in scope ⇒ no window to report; inventing dates would be a lie."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value={"window_start": None, "as_of_date": None})

    result = await fetch_clusters_cost(db, _settings(), allowed_lz_ids=None, window_days=30)

    assert result["window"] == {"window_days": 30, "from_date": None, "to_date": None}


@pytest.mark.asyncio
async def test_clusters_efficiency_selects_the_new_gold_columns() -> None:
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_clusters_efficiency(db, _settings(), allowed_lz_ids=None, window_days=30)

    sql, *params = db.fetchall.await_args.args
    assert "gold_dbx_compute_cluster_efficiency_rolling" in sql
    assert "gold_dbx_compute_cluster_efficiency_daily" not in sql
    assert 30 in params
    for column in (
        "e.cluster_name",
        "e.autoscale_enabled",
        "e.autoscale_min_workers",
        "e.autoscale_max_workers",
        "e.configured_worker_count",
        "e.uptime_hours_prev_window",
        "e.idle_pct_prev_window",
    ):
        assert column in sql


@pytest.mark.asyncio
async def test_clusters_efficiency_derives_window_over_window_deltas() -> None:
    db = AsyncMock()
    db.fetchall = AsyncMock(
        return_value=[
            {
                "cluster_id": "c-1",
                "uptime_hours": 100.0,
                "uptime_hours_prev_window": 80.0,
                "idle_pct": 41.2,
                "idle_pct_prev_window": 38.0,
                "_total": 2,
            },
            {
                "cluster_id": "c-2",
                "uptime_hours": 12.0,
                "uptime_hours_prev_window": None,
                "idle_pct": 50.0,
                "idle_pct_prev_window": None,
                "_total": 2,
            },
        ]
    )
    db.fetchone = AsyncMock(return_value=None)

    result = await fetch_clusters_efficiency(db, _settings(), allowed_lz_ids=None)

    compared, no_history = result["items"]
    assert compared["uptime_hours_delta_pct"] == 25.0
    # idle_pct is already a percentage: its variation is in points, not per cent.
    assert compared["idle_pct_delta_pts"] == 3.2
    # No previous window ⇒ no comparison, rather than a fabricated -100 %.
    assert no_history["uptime_hours_delta_pct"] is None
    assert no_history["idle_pct_delta_pts"] is None


@pytest.mark.asyncio
async def test_clusters_cost_reports_a_zero_previous_window_as_no_comparison() -> None:
    """``cost_usd_prev_window`` 0 means "no predecessor", and must read as ``None``.

    ``cluster_cost_rolling`` sums the previous window with ``ELSE 0``, so the column is
    never ``NULL``. Left at 0 the page would show "Prev cost $0" — a fabricated
    comparison (P9) — next to a "Prev lifetime —" on the very same row.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(
        return_value=[
            {
                "cluster_id": "c-1",
                "cost_usd": 120.0,
                "cost_usd_prev_window": Decimal("0.000000"),
                "cost_delta_pct": None,
                "_total": 3,
            },
            {
                "cluster_id": "c-2",
                "cost_usd": 120.0,
                "cost_usd_prev_window": Decimal("100.000000"),
                "cost_delta_pct": Decimal("20.0"),
                "_total": 3,
            },
            {
                "cluster_id": "c-3",
                "cost_usd": 120.0,
                "cost_usd_prev_window": Decimal("-5.000000"),
                "cost_delta_pct": None,
                "_total": 3,
            },
        ]
    )
    db.fetchone = AsyncMock(return_value=None)

    result = await fetch_clusters_cost(db, _settings(), allowed_lz_ids=None)
    no_history, compared, credited = result["items"]

    assert no_history["cost_usd_prev_window"] is None
    # A real previous window is untouched, and arrives as a number, not a string.
    assert compared["cost_usd_prev_window"] == pytest.approx(100.0)
    assert isinstance(compared["cost_usd_prev_window"], float)
    assert compared["cost_delta_pct"] == pytest.approx(20.0)
    # A credit makes the baseline negative: no percentage of it is meaningful.
    assert credited["cost_usd_prev_window"] is None


@pytest.mark.asyncio
async def test_clusters_overview_reports_a_zero_previous_window_as_no_comparison() -> None:
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(
        return_value=[
            {
                "cluster_id": "c-1",
                "cost_usd": 10.0,
                "cost_usd_prev_window": Decimal("0"),
                "_total": 1,
            },
        ]
    )

    result = await fetch_clusters_overview(db, _settings(), allowed_lz_ids=None)

    assert result["items"][0]["cost_usd_prev_window"] is None
    # `_total` drives pagination, it is not an item field.
    assert "_total" not in result["items"][0]


@pytest.mark.asyncio
async def test_clusters_efficiency_keeps_the_zombie_and_status_filters() -> None:
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_clusters_efficiency(
        db, _settings(), allowed_lz_ids=None, utilization_status="ZOMBIE"
    )

    sql = db.fetchall.await_args.args[0]
    assert "is_zombie = true" in sql


@pytest.mark.asyncio
async def test_clusters_overview_kpis_come_from_the_window_sums() -> None:
    db = AsyncMock()
    db.fetchone = AsyncMock(
        side_effect=[
            {
                "total_cost": 38720.0,
                "prev_cost": 35000.0,
                "active_clusters": 204,
                "window_start": date(2026, 8, 29),
                "as_of_date": date(2026, 9, 4),
            },
            {"n": 3},
            {"n": 12},
        ]
    )
    db.fetchall = AsyncMock(return_value=[])

    result = await fetch_clusters_overview(db, _settings(), allowed_lz_ids=None, window_days=7)

    assert result["kpis"]["total_cost_usd"] == 38720.0
    assert result["kpis"]["cost_delta_pct"] == 10.6
    assert result["kpis"]["active_clusters"] == 204
    assert result["kpis"]["zombie_count"] == 3
    assert result["kpis"]["open_recommendations"] == 12
    assert result["window"]["from_date"] == "2026-08-29"

    kpi_sql = db.fetchone.await_args_list[0].args[0]
    reco_sql = db.fetchone.await_args_list[2].args[0]
    # A single scan carries both windows: the rolling table stores the previous one.
    assert "cost_usd_prev_window" in kpi_sql
    assert "COUNT(DISTINCT r.object_id)" in reco_sql
    assert "object_type = 'CLUSTER'" in reco_sql


@pytest.mark.asyncio
async def test_clusters_overview_counts_only_clusters_billed_in_the_window() -> None:
    """The rolling table keeps a cluster billed only in the *previous* window."""
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(return_value=[])

    await fetch_clusters_overview(db, _settings(), allowed_lz_ids=None)

    kpi_sql = db.fetchone.await_args_list[0].args[0]
    assert "CASE WHEN cost_usd > 0 THEN 1 ELSE 0 END" in kpi_sql


@pytest.mark.asyncio
async def test_clusters_overview_pages_on_the_server() -> None:
    """The page is cut in SQL, and ``total`` counts the whole scope, not the page."""
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(
        return_value=[{"cluster_id": "c-1", "cost_usd": 1.0, "_total": 9899}]
    )

    result = await fetch_clusters_overview(
        db, _settings(), allowed_lz_ids=None, page=3, page_size=25
    )

    items_sql = db.fetchall.await_args.args[0]
    assert "LIMIT ? OFFSET ?" in items_sql
    assert "COUNT(*) OVER() AS _total" in items_sql
    assert db.fetchall.await_args.args[-2:] == (25, 50)
    assert result["total"] == 9899
    assert (result["page"], result["page_size"]) == (3, 25)


@pytest.mark.asyncio
async def test_clusters_overview_search_and_status_filter_the_whole_window() -> None:
    """Both used to run in the browser over 50 rows: the 51st was unreachable."""
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(return_value=[])

    await fetch_clusters_overview(
        db,
        _settings(),
        allowed_lz_ids=None,
        search="  ETL_Ingestion  ",
        utilization_status="zombie",
    )

    items_sql = db.fetchall.await_args.args[0]
    params = db.fetchall.await_args.args[1:]
    assert "LOWER(ws.workspace_name) LIKE ?" in items_sql
    assert "UPPER(e.utilization_status) = ?" in items_sql
    # Trimmed and case-folded, and passed as a parameter — never inlined.
    assert "%etl_ingestion%" in params
    assert "ZOMBIE" in params
    assert "etl_ingestion" not in items_sql.lower()


@pytest.mark.asyncio
async def test_clusters_overview_sorts_on_an_allowlisted_column_only() -> None:
    """The sort key is interpolated, so an unknown one must not reach the SQL."""
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(return_value=[])

    await fetch_clusters_overview(
        db,
        _settings(),
        allowed_lz_ids=None,
        sort="cost_usd; DROP TABLE t",
        sort_direction="asc",
    )

    items_sql = db.fetchall.await_args.args[0]
    assert "DROP TABLE" not in items_sql
    # Falls back to what the table shows on load, and keeps a unique tie-breaker.
    assert "ORDER BY c.cost_usd ASC NULLS LAST, c.cluster_id ASC" in items_sql


@pytest.mark.asyncio
async def test_clusters_overview_sorts_lifetime_with_nulls_last_when_ascending() -> None:
    """The client sort ranked a missing value as -Infinity, so page 1 was the
    clusters with no measurement at all."""
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(return_value=[])

    await fetch_clusters_overview(
        db, _settings(), allowed_lz_ids=None, sort="cluster_lifetime", sort_direction="asc"
    )

    items_sql = db.fetchall.await_args.args[0]
    assert "ORDER BY e.uptime_hours ASC NULLS LAST" in items_sql


@pytest.mark.asyncio
async def test_clusters_overview_joins_efficiency_on_window_days() -> None:
    """Omitting ``window_days`` from the join key would multiply every row by 4."""
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(return_value=[])

    await fetch_clusters_overview(db, _settings(), allowed_lz_ids=None, window_days=90)

    items_sql = db.fetchall.await_args.args[0]
    assert "e.window_days = c.window_days" in items_sql


@pytest.mark.asyncio
async def test_clusters_governance_stays_on_the_snapshot_table() -> None:
    """Non-regression: ``cluster_governance`` has no notion of a window."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])

    result = await fetch_clusters_governance(
        db,
        _settings(),
        allowed_lz_ids=None,
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 31),
        severity="HIGH",
    )

    sql = db.fetchall.await_args.args[0]
    assert "gold_dbx_compute_cluster_governance" in sql
    assert "window_days" not in sql
    assert "window" not in result
    assert result["period"] == {"from": "2026-07-01", "to": "2026-07-31"}


@pytest.mark.asyncio
async def test_cluster_detail_reads_the_rolling_tables_for_the_window() -> None:
    db = AsyncMock()
    db.fetchone = AsyncMock(
        side_effect=[
            {
                "cloud_provider": "azure",
                "workspace_id": "1234",
                "cluster_id": "c-1",
                "window_start": date(2026, 6, 7),
                "as_of_date": date(2026, 9, 4),
                "cost_usd": 812.4,
                "dbu_cost": 0.572,
            },
            {
                "cluster_id": "c-1",
                "uptime_hours": 100.0,
                "uptime_hours_prev_window": 80.0,
                "idle_pct": 41.2,
                "idle_pct_prev_window": 38.0,
                "autoscale_enabled": True,
                "autoscale_min_workers": 2,
                "autoscale_max_workers": 8,
            },
            None,
        ]
    )

    result = await fetch_cluster_detail(
        db, _settings(), None, "c-1", window_days=90
    )

    assert result is not None
    cost_sql = db.fetchone.await_args_list[0].args[0]
    eff_sql = db.fetchone.await_args_list[1].args[0]
    assert "gold_dbx_compute_cluster_cost_rolling" in cost_sql
    assert "gold_dbx_compute_cluster_efficiency_rolling" in eff_sql
    assert "window_days = ?" in cost_sql
    assert result["window"] == {
        "window_days": 90,
        "from_date": "2026-06-07",
        "to_date": "2026-09-04",
    }
    # The technical specs the drawer renders, and the deltas derived from them.
    assert result["efficiency"]["autoscale_max_workers"] == 8
    assert result["efficiency"]["uptime_hours_delta_pct"] == 25.0
    assert result["efficiency"]["idle_pct_delta_pts"] == 3.2


@pytest.mark.asyncio
async def test_cluster_lifetime_trend_weights_idle_by_uptime() -> None:
    """R6: the trend stays on the daily table — a rolling row is a single point."""
    db = AsyncMock()
    db.fetchall = AsyncMock(
        return_value=[{"bucket": date(2026, 9, 1), "uptime_hours": 21.4, "idle_pct": 38.2}]
    )

    result = await fetch_cluster_lifetime_trend(
        db,
        _settings(),
        None,
        "c-1",
        period_start=date(2026, 6, 7),
        period_end=date(2026, 9, 4),
        granularity="week",
    )

    sql = db.fetchall.await_args.args[0]
    assert "gold_dbx_compute_cluster_efficiency_daily" in sql
    assert "date_trunc('week', period_start)" in sql
    # A plain AVG would weigh a 20-minute day like a 20-hour one.
    assert "SUM(idle_pct * uptime_hours)" in sql
    assert result["granularity"] == "week"
    assert result["items"] == [
        {"bucket": "2026-09-01", "uptime_hours": 21.4, "idle_pct": 38.2}
    ]


@pytest.mark.asyncio
async def test_cluster_lifetime_trend_falls_back_to_day_on_unknown_granularity() -> None:
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])

    result = await fetch_cluster_lifetime_trend(
        db, _settings(), None, "c-1", granularity="quarter"
    )

    assert result["granularity"] == "day"
    assert "date_trunc('day', period_start)" in db.fetchall.await_args.args[0]


@pytest.mark.asyncio
async def test_warehouses_overview_pages_on_the_server() -> None:
    """1 824 warehouses in dev: the page has to be cut in SQL, not in the browser."""
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(
        return_value=[{"warehouse_id": "wh-1", "cost_usd": 1.0, "_total": 1824}]
    )

    result = await fetch_warehouses_overview(
        db, _settings(), allowed_lz_ids=None, page=2, page_size=25
    )

    items_sql = db.fetchall.await_args.args[0]
    assert "LIMIT ? OFFSET ?" in items_sql
    assert "COUNT(*) OVER() AS _total" in items_sql
    assert db.fetchall.await_args.args[-2:] == (25, 25)
    assert result["total"] == 1824
    assert (result["page"], result["page_size"]) == (2, 25)
    assert "_total" not in result["items"][0]


@pytest.mark.asyncio
async def test_warehouses_overview_filters_the_whole_scope() -> None:
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(return_value=[])

    await fetch_warehouses_overview(
        db,
        _settings(),
        allowed_lz_ids=None,
        search=" Analytics ",
        warehouse_size="Medium",
        min_failure_rate_pct=1,
    )

    items_sql = db.fetchall.await_args.args[0]
    params = db.fetchall.await_args.args[1:]
    # A workspace name is searchable even though the front resolves the label itself.
    assert "LOWER(ws.workspace_name) LIKE ?" in items_sql
    assert "LOWER(c.warehouse_size) = ?" in items_sql
    # An unmeasured failure rate reads as 0, the way the browser filter did.
    assert "COALESCE(p.failure_rate_pct, 0) >= ?" in items_sql
    assert "%analytics%" in params
    assert "medium" in params
    assert 1.0 in params


@pytest.mark.asyncio
async def test_warehouses_overview_sorts_on_an_allowlisted_column_only() -> None:
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(return_value=[])

    await fetch_warehouses_overview(
        db, _settings(), allowed_lz_ids=None, sort="1; DELETE FROM t", sort_direction="asc"
    )

    items_sql = db.fetchall.await_args.args[0]
    assert "DELETE FROM" not in items_sql
    assert "ORDER BY c.cost_usd ASC NULLS LAST, c.warehouse_id ASC" in items_sql


# --------------------------------------------------------------------------------------
# 023 T002 — the three warehouse list views on the rolling tables
# --------------------------------------------------------------------------------------

_WH_COST_ROLLING = "gold_dbx_compute_warehouse_cost_rolling"
_WH_PERF_ROLLING = "gold_dbx_compute_warehouse_query_performance_rolling"
_WH_UTIL_ROLLING = "gold_dbx_compute_warehouse_utilization_rolling"
_WH_COST_DAILY = "gold_dbx_compute_warehouse_cost_daily"
_WH_PERF_DAILY = "gold_dbx_compute_warehouse_query_performance_daily"
_CLUSTER_COST_DAILY = "gold_dbx_compute_cluster_cost_daily"
_RECOMMENDATIONS = "gold_dbx_compute_recommendations"


def _issued(db: AsyncMock) -> list[str]:
    calls = list(db.fetchone.await_args_list) + list(db.fetchall.await_args_list)
    return [str(call.args[0]) for call in calls if call.args]


@pytest.mark.asyncio
@pytest.mark.parametrize("window_days", [1, 7, 30, 90])
async def test_warehouses_cost_reads_the_rolling_table_for_the_window(
    window_days: int,
) -> None:
    """The daily table only moved the anchor; the rolling one aggregates the window."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_warehouses_cost(db, _settings(), allowed_lz_ids=None, window_days=window_days)

    sql, *params = db.fetchall.await_args.args
    assert _WH_COST_ROLLING in sql
    assert _WH_COST_DAILY not in sql
    assert "window_days = ?" in sql
    assert window_days in params
    # The rolling table already holds one row per warehouse and per window.
    assert "QUALIFY ROW_NUMBER()" not in sql


@pytest.mark.asyncio
@pytest.mark.parametrize("window_days", [1, 7, 30, 90])
async def test_warehouses_query_performance_reads_the_rolling_table_for_the_window(
    window_days: int,
) -> None:
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_warehouses_query_performance(
        db, _settings(), allowed_lz_ids=None, window_days=window_days
    )

    sql, *params = db.fetchall.await_args.args
    assert _WH_PERF_ROLLING in sql
    assert _WH_PERF_DAILY not in sql
    assert "window_days = ?" in sql
    assert window_days in params
    assert "QUALIFY ROW_NUMBER()" not in sql


@pytest.mark.asyncio
async def test_warehouses_query_performance_selects_the_warehouse_name() -> None:
    """T001 put the name in gold; without it the front printed a literal ``null``."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_warehouses_query_performance(db, _settings(), allowed_lz_ids=None)

    sql = db.fetchall.await_args.args[0]
    assert "warehouse_name" in sql
    assert "window_start" in sql
    assert "as_of_date" in sql


@pytest.mark.asyncio
async def test_warehouses_overview_reads_the_rolling_tables_and_never_the_daily_ones() -> None:
    """Three rolling tables since 025 T002, not two: cost, query performance and
    utilization — the last one only for ``is_serverless``, which exists nowhere else."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_warehouses_overview(db, _settings(), allowed_lz_ids=None, window_days=30)

    issued = _issued(db)
    assert issued
    assert any(_WH_COST_ROLLING in sql for sql in issued)
    assert any(_WH_PERF_ROLLING in sql for sql in issued)
    assert any(_WH_UTIL_ROLLING in sql for sql in issued)
    assert not any(_WH_COST_DAILY in sql or _WH_PERF_DAILY in sql for sql in issued)


@pytest.mark.asyncio
async def test_warehouses_overview_joins_performance_on_window_days() -> None:
    """Omitting ``window_days`` from the join key would multiply every row by 4."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_warehouses_overview(db, _settings(), allowed_lz_ids=None, window_days=90)

    items_sql = db.fetchall.await_args.args[0]
    assert "p.window_days = c.window_days" in items_sql
    assert "LEFT JOIN p" in items_sql
    assert "INNER JOIN p" not in items_sql


@pytest.mark.asyncio
async def test_warehouses_overview_reads_the_previous_window_from_gold() -> None:
    """P12: the comparison is aggregated in gold — no second dated query to issue."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(
        return_value={
            "total_cost": 120.0,
            "prev_cost": 100.0,
            "active_warehouses": 3,
            "query_count": 42,
            "window_start": date(2026, 8, 9),
            "as_of_date": date(2026, 9, 7),
        }
    )

    result = await fetch_warehouses_overview(
        db, _settings(), allowed_lz_ids=None, window_days=30
    )

    assert result["kpis"]["cost_delta_pct"] == 20.0
    assert "SUM(cost_usd_prev_window)" in db.fetchone.await_args_list[0].args[0]
    # `_previous_period` is gone: nothing bounds a preceding range any more.
    assert not any("period_start >= ?" in sql for sql in _issued(db))


@pytest.mark.asyncio
async def test_warehouses_overview_counts_only_the_billed_warehouses_as_active() -> None:
    """Gold keeps a row at 0 as long as the previous window is not 0 — `COUNT(*)` lies."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_warehouses_overview(db, _settings(), allowed_lz_ids=None)

    kpi_sql = db.fetchone.await_args_list[0].args[0]
    assert "SUM(CASE WHEN cost_usd > 0 THEN 1 ELSE 0 END) AS active_warehouses" in kpi_sql
    assert "COUNT(*) AS active_warehouses" not in kpi_sql


@pytest.mark.asyncio
@pytest.mark.parametrize("previous", [0, 0.0, Decimal("0"), -12.5])
async def test_warehouses_cost_normalizes_a_non_positive_previous_window(
    previous: Any,
) -> None:
    """`SUM(CASE … ELSE 0 END)` cannot say "no predecessor"; the API must."""
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(
        return_value=[
            {
                "warehouse_id": "wh-1",
                "cost_usd": 10.0,
                "cost_usd_prev_window": previous,
                "cost_delta_pct": None,
                "_total": 1,
            }
        ]
    )

    result = await fetch_warehouses_cost(db, _settings(), allowed_lz_ids=None)

    item = result["items"][0]
    assert item["cost_usd_prev_window"] is None
    # Gold already draws that conclusion for the ratio, through NULLIF.
    assert item["cost_delta_pct"] is None


@pytest.mark.asyncio
async def test_warehouses_cost_keeps_a_real_previous_window() -> None:
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(
        return_value=[
            {"warehouse_id": "wh-1", "cost_usd_prev_window": Decimal("8.5"), "_total": 1}
        ]
    )

    result = await fetch_warehouses_cost(db, _settings(), allowed_lz_ids=None)

    assert result["items"][0]["cost_usd_prev_window"] == 8.5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fetcher", [fetch_warehouses_cost, fetch_warehouses_query_performance]
)
async def test_warehouse_list_views_expose_the_bounds_read_from_gold(
    fetcher: Any,
) -> None:
    """R5: ``from_date``/``to_date`` come from the data, never from ``today``."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(
        return_value={"window_start": date(2026, 9, 1), "as_of_date": date(2026, 9, 7)}
    )

    result = await fetcher(db, _settings(), allowed_lz_ids=None, window_days=7)

    assert result["window"] == {
        "window_days": 7,
        "from_date": "2026-09-01",
        "to_date": "2026-09-07",
    }
    # `to_date - from_date + 1 == window_days`, and `period` carries the same pair.
    assert result["period"] == {"from": "2026-09-01", "to": "2026-09-07"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fetcher",
    [fetch_warehouses_overview, fetch_warehouses_cost, fetch_warehouses_query_performance],
)
async def test_warehouse_list_views_report_null_bounds_on_an_empty_window(
    fetcher: Any,
) -> None:
    """P9: no row in scope ⇒ no window to report; inventing dates would be a lie."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value={"window_start": None, "as_of_date": None})

    result = await fetcher(db, _settings(), allowed_lz_ids=None, window_days=90)

    assert result["items"] == []
    assert result["window"] == {"window_days": 90, "from_date": None, "to_date": None}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fetcher", "table"),
    [
        (fetch_warehouses_cost, _WH_COST_ROLLING),
        (fetch_warehouses_query_performance, _WH_PERF_ROLLING),
    ],
)
async def test_warehouse_list_views_guard_on_the_latest_snapshot(
    fetcher: Any, table: str
) -> None:
    """R9a: the MERGE never deletes, so an old ``as_of_date`` survives for ever."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetcher(db, _settings(), allowed_lz_ids=None, window_days=7)

    for sql in _issued(db):
        assert f"as_of_date = (SELECT MAX(as_of_date) FROM `cat`.`sch`.`{table}`)" in sql
        # The MAX is global to the table: a per-window MAX would resurrect the stale
        # rows of any window whose current population is empty.
        guard = sql.split("SELECT MAX(as_of_date) FROM", 1)[1].split(")", 1)[0]
        assert "window_days" not in guard


@pytest.mark.asyncio
async def test_warehouses_overview_guards_each_table_on_its_own_snapshot() -> None:
    """Two pipelines, two ``as_of_date``: a shared MAX would empty one whole table."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_warehouses_overview(db, _settings(), allowed_lz_ids=None)

    items_sql = db.fetchall.await_args.args[0]
    for table in (_WH_COST_ROLLING, _WH_PERF_ROLLING):
        assert f"as_of_date = (SELECT MAX(as_of_date) FROM `cat`.`sch`.`{table}`)" in items_sql


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fetcher", "table", "untouched"),
    [
        (fetch_warehouse_detail, _WH_COST_DAILY, _WH_COST_ROLLING),
        (fetch_warehouse_cost_trend, _WH_COST_DAILY, _WH_COST_ROLLING),
    ],
)
async def test_the_per_warehouse_endpoints_keep_their_daily_contract(
    fetcher: Any, table: str, untouched: str
) -> None:
    """A rolling row is a single point: the detail and the trend still need the series."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value={"cloud_provider": "aws", "cost_usd": 1.0})

    result = await fetcher(db, _settings(), None, "wh-1")

    issued = _issued(db)
    assert any(table in sql for sql in issued)
    assert not any(untouched in sql for sql in issued)
    assert "window" not in (result or {})


@pytest.mark.asyncio
async def test_warehouse_slow_queries_keeps_its_contract() -> None:
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])

    result = await fetch_warehouse_slow_queries(db, _settings(), None)

    assert set(result) == {"enabled", "items", "total", "page", "page_size", "period"}
    assert "window_days = ?" not in db.fetchall.await_args.args[0]


class _BoolAnd:
    """Spark's ``bool_and`` for sqlite: NULLs are skipped, all-NULL yields NULL.

    Reproducing the NULL handling is the point. ``_serverless_warehouse_cte`` folds the
    four rolling windows of one warehouse with ``bool_and``, and the whole neutralisation
    turns on what happens when the flag is unknown — an aggregate that returned ``0`` for
    an all-NULL group would make the tests pass on a rule the service does not implement.
    """

    def __init__(self) -> None:
        self._seen = False
        self._value = True

    def step(self, value: Any) -> None:
        if value is None:
            return
        self._seen = True
        self._value = self._value and bool(value)

    def finalize(self) -> int | None:
        return int(self._value) if self._seen else None


class _SqliteDb:
    """A :class:`DatabricksWarehousePool` stand-in that really runs the SQL.

    The ``as_of_date`` guard is the one thing a substring assertion cannot check: a
    predicate that is *present* and a predicate that *filters* read the same in the
    query text, and a fixture holding a single ``as_of_date`` passes either way (023
    T002). So these tests execute the generated statement, parameters and clause
    order included, against sqlite.

    Three adaptations, all named. One textual: the three-part Unity Catalog reference is
    reduced to its table part, sqlite parsing at most ``schema.table``. One functional:
    ``bool_and`` is registered as a user aggregate with Spark's semantics, sqlite having
    no boolean aggregate at all (see :class:`_BoolAnd`). One of plumbing: ``date`` is
    adapted to its ISO string explicitly — the implicit adapter that used to do it is
    deprecated since Python 3.12, and the services bind real ``date`` objects for the
    period bounds. Everything else — placeholders, parameter order, CTEs, window
    functions — is the service's own. Failures are recorded rather than swallowed: the
    services soft-fail on any exception, so an unseeded table would otherwise show up as
    an empty page.
    """

    _PREFIX = "`cat`.`sch`."

    def __init__(self) -> None:
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._conn.create_aggregate("bool_and", 1, _BoolAnd)
        self.errors: list[str] = []

    @staticmethod
    def _adapt(value: Any) -> Any:
        return value.isoformat() if isinstance(value, date) else value

    def seed(
        self, table: str, rows: list[dict[str, Any]], *, columns: list[str] | None = None
    ) -> None:
        names = columns or list(rows[0])
        self._conn.execute(f"CREATE TABLE `{table}` ({', '.join(names)})")
        self._conn.executemany(
            f"INSERT INTO `{table}` VALUES ({', '.join('?' for _ in names)})",
            [tuple(row[name] for name in names) for row in rows],
        )

    def _run(self, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        bound = tuple(self._adapt(value) for value in params)
        try:
            cursor = self._conn.execute(sql.replace(self._PREFIX, ""), bound)
        except sqlite3.Error as exc:  # pragma: no cover - only on a broken query
            self.errors.append(f"{exc}: {sql}")
            raise
        return [dict(row) for row in cursor.fetchall()]

    async def fetchall(self, sql: str, *params: Any) -> list[dict[str, Any]]:
        return self._run(sql, params)

    async def fetchone(self, sql: str, *params: Any) -> dict[str, Any] | None:
        rows = self._run(sql, params)
        return rows[0] if rows else None


_CURRENT = "2026-09-07"
_STALE = "2026-09-05"


def _cost_rolling_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "cloud_provider": "aws",
        "workspace_id": "1234",
        "warehouse_id": "wh-current",
        "warehouse_name": "current warehouse",
        "warehouse_size": "Medium",
        "window_days": 1,
        "dbu_quantity": 10.0,
        "cost_usd": 12.0,
        "cost_usd_prev_window": 8.0,
        "cost_delta_pct": 50.0,
        "query_count": 4,
        "cost_per_query_usd": 3.0,
        "top_consumer": "alice",
        "window_start": _CURRENT,
        "as_of_date": _CURRENT,
    }
    row.update(overrides)
    return row


def _reco_row(**overrides: Any) -> dict[str, Any]:
    """An open warehouse recommendation, with every column the list route selects.

    ``category`` is not decorative — it is half of the neutralisation predicate, and the
    default is the half that must *survive* it: ``RELIABILITY`` applies to a serverless
    warehouse as much as to a classic one. The other half lives in
    ``gold_dbx_compute_warehouse_utilization_rolling`` (see :func:`_util_row`).
    """
    row: dict[str, Any] = {
        "recommendation_id": "rec-1",
        "cloud_provider": "aws",
        "workspace_id": "1234",
        "object_type": "WAREHOUSE",
        "object_id": "wh-current",
        "object_name": "current warehouse",
        "category": "RELIABILITY",
        "mode": "AUTO",
        "title": "queue saturated",
        "detail": "detail",
        "recommended_action": "action",
        "estimated_savings_usd": 0.0,
        "severity": "HIGH",
        "personas": "finops",
        "status": "OPEN",
        "first_seen_date": _CURRENT,
        "last_seen_date": _CURRENT,
    }
    row.update(overrides)
    return row


def _seed_empty_cost_daily(db: _SqliteDb) -> None:
    """Create the two cost tables the recommendations routes left-join, with no rows.

    Both routes decorate a recommendation with the spend actually billed on its object
    over the period. That is a different question from the one these tests ask — whether
    a row survives the serverless neutralisation — and an empty table answers it the same
    way a seeded one would, the joins being ``LEFT``. What an *absent* table does instead
    is raise, and the service soft-fails on any exception, so the whole page would come
    back empty and every assertion below would read as a rule failure.

    Seeded explicitly here rather than pre-created in :class:`_SqliteDb`: the harness makes
    a point of failing loudly on a table nobody seeded, and that is worth keeping for the
    tests that do care about these two.
    """
    columns = ["cloud_provider", "workspace_id", "cost_usd", "period_start"]
    db.seed(_CLUSTER_COST_DAILY, [], columns=[*columns, "cluster_id"])
    db.seed(_WH_COST_DAILY, [], columns=[*columns, "warehouse_id"])


def _util_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "cloud_provider": "aws",
        "workspace_id": "1234",
        "warehouse_id": "wh-current",
        "window_days": 1,
        "is_serverless": 0,
        # Declared form of the warehouse, the column the Type header reads. Defaults to the
        # non-serverless pair of ``is_serverless: 0`` — a fixture whose two columns
        # contradicted each other would exercise the residual ``NULL`` branch of
        # ``_serverless_warehouse_cte`` in every test that only wants a plain warehouse.
        "warehouse_type": "PRO",
        "as_of_date": _CURRENT,
    }
    row.update(overrides)
    return row


def _perf_rolling_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "cloud_provider": "aws",
        "workspace_id": "1234",
        "warehouse_id": "wh-current",
        "warehouse_name": "current warehouse",
        "window_days": 1,
        "query_count": 4,
        "failed_count": 1,
        "failure_rate_pct": 25.0,
        "latency_p50_ms": 100.0,
        "latency_p95_ms": 900.0,
        "latency_p99_ms": 1200.0,
        "queue_time_avg_ms": 10.0,
        "queue_time_p95_ms": 20.0,
        "spill_query_count": 0,
        "cache_hit_pct": 80.0,
        "bytes_scanned": 1000,
        "rows_scanned": 10,
        "top_slow_statement_id": "st-1",
        "window_start": _CURRENT,
        "as_of_date": _CURRENT,
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_warehouses_cost_returns_the_latest_snapshot_only() -> None:
    """Measured in dev: 358 warehouses instead of 202, 156 of them two days stale."""
    db = _SqliteDb()
    db.seed(
        _WH_COST_ROLLING,
        [
            _cost_rolling_row(),
            _cost_rolling_row(warehouse_id="wh-also-current", cost_usd=5.0),
            _cost_rolling_row(
                warehouse_id="wh-deleted", window_start=_STALE, as_of_date=_STALE
            ),
        ],
    )

    result = await fetch_warehouses_cost(db, _settings(), allowed_lz_ids=None, window_days=1)

    assert db.errors == []
    assert [item["warehouse_id"] for item in result["items"]] == [
        "wh-current",
        "wh-also-current",
    ]
    assert result["total"] == 2
    assert result["window"] == {
        "window_days": 1,
        "from_date": _CURRENT,
        "to_date": _CURRENT,
    }


@pytest.mark.asyncio
async def test_warehouses_cost_keeps_a_window_whose_current_population_is_empty() -> None:
    """The MAX is global: a per-window MAX would revive 90d's stale rows here."""
    db = _SqliteDb()
    db.seed(
        _WH_COST_ROLLING,
        [
            _cost_rolling_row(window_days=1),
            _cost_rolling_row(
                warehouse_id="wh-deleted",
                window_days=90,
                window_start=_STALE,
                as_of_date=_STALE,
            ),
        ],
    )

    result = await fetch_warehouses_cost(db, _settings(), allowed_lz_ids=None, window_days=90)

    assert db.errors == []
    assert result["items"] == []
    assert result["window"] == {"window_days": 90, "from_date": None, "to_date": None}


@pytest.mark.asyncio
async def test_warehouses_query_performance_returns_the_latest_snapshot_only() -> None:
    db = _SqliteDb()
    db.seed(
        _WH_PERF_ROLLING,
        [
            _perf_rolling_row(),
            _perf_rolling_row(
                warehouse_id="wh-deleted",
                failure_rate_pct=99.0,
                window_start=_STALE,
                as_of_date=_STALE,
            ),
        ],
    )

    result = await fetch_warehouses_query_performance(
        db, _settings(), allowed_lz_ids=None, window_days=1
    )

    assert db.errors == []
    # The stale row sorts first on failure rate — it must not be there at all.
    assert [item["warehouse_id"] for item in result["items"]] == ["wh-current"]
    assert result["items"][0]["warehouse_name"] == "current warehouse"
    assert result["total"] == 1


@pytest.mark.asyncio
async def test_warehouses_overview_returns_the_latest_snapshot_only() -> None:
    """Both the page and the KPIs: a stale row inflates the cost as much as the count."""
    db = _SqliteDb()
    db.seed(
        _WH_COST_ROLLING,
        [
            _cost_rolling_row(),
            _cost_rolling_row(
                warehouse_id="wh-deleted",
                cost_usd=1000.0,
                cost_usd_prev_window=1000.0,
                query_count=999,
                window_start=_STALE,
                as_of_date=_STALE,
            ),
        ],
    )
    db.seed(
        _WH_PERF_ROLLING,
        [
            _perf_rolling_row(),
            _perf_rolling_row(
                warehouse_id="wh-deleted",
                failed_count=500,
                window_start=_STALE,
                as_of_date=_STALE,
            ),
        ],
    )
    db.seed(
        _RECOMMENDATIONS,
        [
            _reco_row(object_id="wh-current"),
            _reco_row(object_id="wh-deleted"),
        ],
    )
    db.seed(_WH_UTIL_ROLLING, [_util_row()])
    db.seed(
        "dim_dbx_workspace",
        [{"workspace_id": "1234", "workspace_name": "analytics-dev"}],
    )

    result = await fetch_warehouses_overview(
        db, _settings(), allowed_lz_ids=None, window_days=1
    )

    assert db.errors == []
    assert [item["warehouse_id"] for item in result["items"]] == ["wh-current"]
    assert result["items"][0]["workspace_name"] == "analytics-dev"
    assert result["total"] == 1
    assert result["kpis"] == {
        "total_cost_usd": 12.0,
        "cost_delta_pct": 50.0,
        "active_warehouses": 1,
        "query_count": 4,
        "failed_count": 1,
        "open_recommendations": 1,
    }
    assert result["window"] == {
        "window_days": 1,
        "from_date": _CURRENT,
        "to_date": _CURRENT,
    }


@pytest.mark.asyncio
async def test_the_overview_publishes_a_three_valued_type_that_never_denies_the_flag() -> None:
    """``warehouse_type`` next to ``is_serverless``, on the six shapes that can occur.

    Two columns describing one warehouse can contradict each other, and here that would be
    a visible defect: the flag is what voids a saving, so a row reading ``PRO`` beside
    ``is_serverless = true`` would deny, in one cell, the premise of the cell next to it.
    ``_serverless_warehouse_cte`` folds the type so the contradiction is unrepresentable,
    and this test is what fails if someone later reads the raw gold column instead.

    The interesting row is ``wh-billed-classic``: declared ``SERVERLESS`` while billing says
    at least one day was not. There is no honest third value to print, so it is ``NULL`` —
    the same answer as a warehouse missing from the utilization snapshot altogether, and for
    the same reason. Measured 0 occurrences in dev on 2026-09-11; written for the day that
    stops being true.
    """
    db = _SqliteDb()
    shapes = {
        "wh-pro": (0, "PRO"),
        "wh-classic": (0, "CLASSIC"),
        "wh-serverless": (1, "SERVERLESS"),
        # Billing wins over the declaration, which is the whole cascade of the gold column.
        "wh-billed-serverless": (1, "PRO"),
        # ... and it wins in the other direction too, where it leaves nothing to print.
        "wh-billed-classic": (0, "SERVERLESS"),
    }
    db.seed(
        _WH_COST_ROLLING,
        [_cost_rolling_row(warehouse_id=wh) for wh in (*shapes, "wh-unknown")],
    )
    db.seed(_WH_PERF_ROLLING, [_perf_rolling_row(warehouse_id=wh) for wh in shapes])
    db.seed(_RECOMMENDATIONS, [_reco_row(object_id="wh-pro")])
    db.seed(
        _WH_UTIL_ROLLING,
        [
            _util_row(warehouse_id=wh, is_serverless=flag, warehouse_type=declared)
            for wh, (flag, declared) in shapes.items()
        ],
    )
    db.seed("dim_dbx_workspace", [{"workspace_id": "1234", "workspace_name": "analytics-dev"}])

    result = await fetch_warehouses_overview(
        db, _settings(), allowed_lz_ids=None, window_days=1
    )

    assert db.errors == []
    assert {item["warehouse_id"]: item["warehouse_type"] for item in result["items"]} == {
        "wh-pro": "PRO",
        "wh-classic": "CLASSIC",
        "wh-serverless": "SERVERLESS",
        "wh-billed-serverless": "SERVERLESS",
        "wh-billed-classic": None,
        # Absent from the utilization snapshot: unknown, and published as unknown rather
        # than defaulted to a classic form the row does not prove.
        "wh-unknown": None,
    }
    for item in result["items"]:
        if item["is_serverless"]:
            assert item["warehouse_type"] == "SERVERLESS", item["warehouse_id"]
        if item["warehouse_type"] in ("PRO", "CLASSIC"):
            assert not item["is_serverless"], item["warehouse_id"]


# --------------------------------------------------------------------------------------
# The serverless-warehouse neutralisation, executed (spec 025 T002)
#
# Substring assertions cannot check this rule: ``COALESCE(… , false)`` and the naive
# ``NOT (… AND sw.is_serverless = true AND …)`` read almost the same in the query text and
# behave in opposite ways on the one row that matters — the warehouse whose flag is
# unknown. So these run the generated SQL, with the ``bool_and`` semantics of
# :class:`_BoolAnd`.
#
# Measured in dev on 2026-09-10 **after T001i**, the population these fixtures stand for:
# the withheld figures are 487 rows / 93 359,94 $, all ``RESOLVED`` and unreachable by the
# builder's merge; **0** open row is withheld, because the 69 open serverless
# ``RIGHTSIZING`` rows now price 0 $ and stay visible, alongside 337 serverless
# ``RELIABILITY`` ones; 1 warehouse has an unknown flag.
# --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_rightsizing_row_survives_an_unknown_serverless_flag() -> None:
    """The whole reason :func:`_serverless_void_savings_sql` wraps its predicate in a
    ``COALESCE``. ``sw.is_serverless`` is NULL for a warehouse missing from the utilization
    snapshot, and ``NOT (true AND NULL AND true)`` is NULL — which a ``WHERE`` drops. The
    row the guard exists to protect would be the only one it hid.
    """
    db = _SqliteDb()
    db.seed(_RECOMMENDATIONS, [_reco_row(category="RIGHTSIZING", estimated_savings_usd=500.0)])
    db.seed(_WH_UTIL_ROLLING, [_util_row(warehouse_id="wh-other", is_serverless=1)])

    _seed_empty_cost_daily(db)

    result = await fetch_recommendations(db, _settings(), None)

    assert db.errors == []
    assert [item["object_id"] for item in result["items"]] == ["wh-current"]
    assert result["total"] == 1
    # Unknown, not "classic": three-valued all the way to the payload.
    assert result["items"][0]["is_serverless"] is None


@pytest.mark.asyncio
async def test_disagreeing_windows_keep_the_recommendation() -> None:
    """A warehouse migrated mid-window is serverless in the 1-day window and classic in
    the 30-day one. ``bool_and`` folds that to ``false`` — doubt keeps the row, which is
    why it is not ``bool_or``.
    """
    db = _SqliteDb()
    db.seed(_RECOMMENDATIONS, [_reco_row(category="RIGHTSIZING", estimated_savings_usd=500.0)])
    db.seed(
        _WH_UTIL_ROLLING,
        [
            _util_row(window_days=1, is_serverless=1),
            _util_row(window_days=30, is_serverless=0),
        ],
    )

    _seed_empty_cost_daily(db)

    result = await fetch_recommendations(db, _settings(), None)

    assert db.errors == []
    assert [item["object_id"] for item in result["items"]] == ["wh-current"]
    assert not result["items"][0]["is_serverless"]


@pytest.mark.asyncio
async def test_the_serverless_flag_is_read_at_the_utilization_tables_own_snapshot() -> None:
    """The CTE anchors ``as_of_date`` on ``MAX(as_of_date)`` of the utilization table and
    joins on nothing dated. Without that anchor the stale ``false`` would fold with the
    current ``true`` into ``false``, and a warehouse that *became* serverless would keep
    answering for a rightsizing it can no longer act on.
    """
    db = _SqliteDb()
    db.seed(_RECOMMENDATIONS, [_reco_row(category="RIGHTSIZING", estimated_savings_usd=500.0)])
    db.seed(
        _WH_UTIL_ROLLING,
        [
            _util_row(is_serverless=0, as_of_date=_STALE),
            _util_row(is_serverless=1, as_of_date=_CURRENT),
        ],
    )

    _seed_empty_cost_daily(db)

    result = await fetch_recommendations(db, _settings(), None)

    assert db.errors == []
    assert result["items"] == []
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_a_serverless_reliability_row_stays_visible_and_says_it_is_serverless() -> None:
    """The two halves of the rule on one warehouse: ``RIGHTSIZING`` goes, ``RELIABILITY``
    stays. ``is_serverless`` is served with it so the UI can explain the surviving row
    instead of leaving the list looking unfiltered.
    """
    db = _SqliteDb()
    db.seed(
        _RECOMMENDATIONS,
        [
            _reco_row(category="RELIABILITY"),
            _reco_row(
                recommendation_id="rec-2",
                category="RIGHTSIZING",
                estimated_savings_usd=500.0,
            ),
            _reco_row(
                recommendation_id="rec-3", category="FINOPS", estimated_savings_usd=300.0
            ),
        ],
    )
    db.seed(_WH_UTIL_ROLLING, [_util_row(is_serverless=1)])

    _seed_empty_cost_daily(db)

    result = await fetch_recommendations(db, _settings(), None)

    assert db.errors == []
    assert [item["category"] for item in result["items"]] == ["RELIABILITY"]
    # ``COUNT(*) OVER ()`` is computed after the neutralisation: a total of 3 here would
    # page over rows the route refuses to serve, and show an empty page 2.
    assert result["total"] == 1
    assert result["items"][0]["is_serverless"]


@pytest.mark.asyncio
async def test_a_serverless_rightsizing_row_that_prices_nothing_stays_visible() -> None:
    """The condition is the **figure**, not the category (spec 025, T001i).

    Since the gold builder stopped letting one rule inherit another's money, the
    ``RIGHTSIZING`` rows left on a serverless warehouse price **0 $**: 34 saturated queues
    and 35 spilling query sets in dev. Their actions — raise ``max_clusters``, upsize or
    tune the query — apply to a serverless warehouse, which still has a size and a scaling
    range. Suppressing those by category removed real advice and no false figure, which is
    the very reason ``RELIABILITY`` is exempt; keying on the figure makes that exemption a
    consequence of the rule rather than a hand-maintained list.

    ``NULL`` and ``0.0`` have to behave alike here — neither promises anything — and the
    priced row in the same category must still go.
    """
    db = _SqliteDb()
    db.seed(
        _RECOMMENDATIONS,
        [
            _reco_row(category="RIGHTSIZING", estimated_savings_usd=None, title="queue"),
            _reco_row(
                recommendation_id="rec-2",
                category="RIGHTSIZING",
                estimated_savings_usd=0.0,
                title="spill",
            ),
            _reco_row(
                recommendation_id="rec-3",
                category="RIGHTSIZING",
                estimated_savings_usd=500.0,
                title="oversized",
            ),
        ],
    )
    db.seed(_WH_UTIL_ROLLING, [_util_row(is_serverless=1)])

    _seed_empty_cost_daily(db)

    result = await fetch_recommendations(db, _settings(), None)

    assert db.errors == []
    assert sorted(item["title"] for item in result["items"]) == ["queue", "spill"]
    assert result["total"] == 2
    assert all(item["is_serverless"] for item in result["items"])


@pytest.mark.asyncio
async def test_the_summary_stops_withholding_a_row_that_promises_nothing() -> None:
    """Same rule seen from the KPIs: an unpriced serverless ``RIGHTSIZING`` row now counts
    in ``open_count`` and is **not** reported as withheld, while the priced one still is.

    This is what makes a ``not_applicable`` block of ``0 / 0,0`` the honest answer rather
    than a broken one — in dev, nothing open is withheld any more.
    """
    db = _SqliteDb()
    db.seed(
        _RECOMMENDATIONS,
        [
            _reco_row(category="RIGHTSIZING", estimated_savings_usd=None),
            _reco_row(
                recommendation_id="rec-2",
                category="RIGHTSIZING",
                estimated_savings_usd=500.0,
            ),
        ],
    )
    db.seed(_WH_UTIL_ROLLING, [_util_row(is_serverless=1)])

    _seed_empty_cost_daily(db)

    summary = await fetch_recommendations_summary(db, _settings(), None)

    assert db.errors == []
    assert summary["open_count"] == 1
    assert summary["open_savings_usd"] == 0.0
    assert summary["not_applicable"]["count"] == 1
    assert summary["not_applicable"]["savings_usd"] == 500.0


@pytest.mark.asyncio
async def test_a_cluster_recommendation_never_borrows_a_warehouse_flag() -> None:
    """``UPPER(r.object_type) = 'WAREHOUSE'`` is in the join, not only in the predicate.
    Warehouse ids and cluster ids are different namespaces and nothing enforces it, so a
    coincidental match would pin a warehouse's flag onto a cluster's rightsizing.
    """
    db = _SqliteDb()
    db.seed(
        _RECOMMENDATIONS,
        [
            _reco_row(
                object_type="CLUSTER", category="RIGHTSIZING", estimated_savings_usd=500.0
            )
        ],
    )
    db.seed(_WH_UTIL_ROLLING, [_util_row(is_serverless=1)])

    _seed_empty_cost_daily(db)

    result = await fetch_recommendations(db, _settings(), None)

    assert db.errors == []
    assert [item["object_type"] for item in result["items"]] == ["CLUSTER"]
    assert result["items"][0]["is_serverless"] is None


@pytest.mark.asyncio
async def test_the_summary_publishes_the_dollars_it_withheld() -> None:
    """A suppression nobody can see is indistinguishable from a bug: the two sides must
    add back up to what ``gold_dbx_compute_recommendations`` holds.

    The fixture keeps a **priced** serverless rightsizing row, because that is what the
    reconciliation has to account for. Since T001i the dev population of such rows is
    entirely ``RESOLVED`` (487 rows / 93 359,94 $) — this test is the reason the block
    keeps working the day one is open again.
    """
    db = _SqliteDb()
    db.seed(
        _RECOMMENDATIONS,
        [
            _reco_row(category="RELIABILITY"),
            _reco_row(
                recommendation_id="rec-2",
                category="RIGHTSIZING",
                estimated_savings_usd=500.0,
            ),
            _reco_row(
                recommendation_id="rec-3",
                object_id="wh-classic",
                category="RIGHTSIZING",
                estimated_savings_usd=100.0,
                severity="MEDIUM",
            ),
        ],
    )
    db.seed(
        _WH_UTIL_ROLLING,
        [
            _util_row(is_serverless=1),
            _util_row(warehouse_id="wh-classic", is_serverless=0),
        ],
    )

    _seed_empty_cost_daily(db)

    summary = await fetch_recommendations_summary(db, _settings(), None)

    assert db.errors == []
    assert summary["open_count"] == 2
    assert summary["open_savings_usd"] == 100.0
    assert summary["high_severity_open_count"] == 1
    assert summary["not_applicable"] == {
        "count": 1,
        "savings_usd": 500.0,
        "reason": "SERVERLESS_WAREHOUSE",
        "categories": ["RIGHTSIZING", "FINOPS"],
    }
    assert summary["open_count"] + summary["not_applicable"]["count"] == 3
    assert (
        summary["open_savings_usd"] + summary["not_applicable"]["savings_usd"] == 600.0
    )


@pytest.mark.asyncio
async def test_the_overview_tile_counts_warehouses_and_not_rows() -> None:
    """Why the tile drops by less than the number of neutralised rows, and why that is the
    right arithmetic: ``wh-keeps`` loses its rightsizing but still has a live reliability
    recommendation, so it is still one warehouse with something open. When the predicate
    keyed on the category, this was the dev 350 untouched + 38 kept + 31 lost that took the
    tile from 419 to 388.

    Both rightsizing rows here are **priced**, which is why the test still measures a drop:
    since T001i only a priced row is withheld, and in dev none of those is open any more
    (the same measurement now gives 419 → 419). The fixture keeps the case the tile must go
    on handling rather than the case dev happens to be in.
    """
    db = _SqliteDb()
    db.seed(
        _WH_COST_ROLLING,
        [
            _cost_rolling_row(warehouse_id="wh-keeps"),
            _cost_rolling_row(warehouse_id="wh-loses"),
        ],
    )
    db.seed(
        _WH_PERF_ROLLING,
        [
            _perf_rolling_row(warehouse_id="wh-keeps"),
            _perf_rolling_row(warehouse_id="wh-loses"),
        ],
    )
    db.seed(
        _RECOMMENDATIONS,
        [
            _reco_row(
                object_id="wh-keeps", category="RIGHTSIZING", estimated_savings_usd=500.0
            ),
            _reco_row(
                recommendation_id="rec-2", object_id="wh-keeps", category="RELIABILITY"
            ),
            _reco_row(
                recommendation_id="rec-3",
                object_id="wh-loses",
                category="RIGHTSIZING",
                estimated_savings_usd=700.0,
            ),
        ],
    )
    db.seed(
        _WH_UTIL_ROLLING,
        [
            _util_row(warehouse_id="wh-keeps", is_serverless=1),
            _util_row(warehouse_id="wh-loses", is_serverless=1),
        ],
    )
    db.seed("dim_dbx_workspace", [{"workspace_id": "1234", "workspace_name": "analytics-dev"}])

    result = await fetch_warehouses_overview(
        db, _settings(), allowed_lz_ids=None, window_days=1
    )

    assert db.errors == []
    # Three OPEN rows over two warehouses, one warehouse left with something open.
    assert result["kpis"]["open_recommendations"] == 1
    # Both warehouses stay on the page: neutralising a recommendation does not hide a
    # warehouse that costs money.
    assert {item["warehouse_id"] for item in result["items"]} == {"wh-keeps", "wh-loses"}
    assert all(item["is_serverless"] for item in result["items"])
