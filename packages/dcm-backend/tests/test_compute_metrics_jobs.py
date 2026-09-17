"""Unit and route tests for the compute **job** endpoints (grain ``job_id``)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.api.services.compute_metrics_jobs import (
    fetch_job_cost_trend,
    fetch_job_detail,
    fetch_job_uptime_trend,
    fetch_jobs_cost,
    fetch_jobs_efficiency,
    fetch_jobs_overview,
)
from app.config import Settings

BASE = "/api/v1/databricks/compute"
_JOB_COST_ROLLING = "gold_dbx_compute_job_cluster_cost_rolling"
_JOB_COST_DAILY = "gold_dbx_compute_job_cluster_cost_daily"
_JOB_EFFICIENCY_ROLLING = "gold_dbx_compute_job_efficiency_rolling"
_JOB_EFFICIENCY_DAILY = "gold_dbx_compute_job_efficiency_daily"


def _settings() -> Settings:
    return Settings(
        databricks_host="https://example.cloud.databricks.com",
        databricks_warehouse_id="wh-1",
        databricks_catalog="cat",
        databricks_schema="sch",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("window_days", [1, 7, 30, 90])
@pytest.mark.parametrize("fetcher", [fetch_jobs_cost, fetch_jobs_overview])
async def test_jobs_read_the_rolling_table_for_the_window(
    fetcher: Any, window_days: int
) -> None:
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetcher(db, _settings(), allowed_lz_ids=None, window_days=window_days)

    sql, *params = db.fetchall.await_args.args
    assert _JOB_COST_ROLLING in sql
    assert "window_days = ?" in sql
    assert window_days in params
    assert "QUALIFY ROW_NUMBER()" not in sql


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fetcher", "name_fallback"),
    [
        (fetch_jobs_cost, "COALESCE(NULLIF(job_name, ''), job_id) AS job_name"),
        # The overview joins the efficiency snapshot: both sides carry ``job_name``
        # and ``job_id``, so the columns must be qualified or the query is ambiguous.
        (fetch_jobs_overview, "COALESCE(NULLIF(j.job_name, ''), j.job_id) AS job_name"),
    ],
)
async def test_jobs_grain_is_job_id_with_name_fallback(
    fetcher: Any, name_fallback: str
) -> None:
    """Grain ``job_id``; a run with no persisted name falls back to the id, not blank."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetcher(db, _settings(), allowed_lz_ids=None)

    sql = db.fetchall.await_args.args[0]
    assert "job_id" in sql
    assert name_fallback in sql
    assert "cluster_count" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize("fetcher", [fetch_jobs_cost, fetch_jobs_overview])
async def test_jobs_guard_on_the_latest_snapshot(fetcher: Any) -> None:
    """R9a: the MERGE never deletes, so an old ``as_of_date`` survives for ever."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetcher(db, _settings(), allowed_lz_ids=None, window_days=7)

    sql = db.fetchall.await_args.args[0]
    assert f"as_of_date = (SELECT MAX(as_of_date) FROM `cat`.`sch`.`{_JOB_COST_ROLLING}`)" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize("previous", [0, 0.0, Decimal("0"), -12.5])
@pytest.mark.parametrize("fetcher", [fetch_jobs_cost, fetch_jobs_overview])
async def test_jobs_normalize_a_non_positive_previous_window(
    fetcher: Any, previous: Any
) -> None:
    """A ``SUM(CASE … ELSE 0 END)`` cannot say "no predecessor"; the API must."""
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(
        return_value=[
            {
                "job_id": "987",
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
async def test_jobs_cost_pages_on_the_server() -> None:
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(
        return_value=[{"job_id": "987", "cost_usd": 1.0, "_total": 512}]
    )

    result = await fetch_jobs_cost(
        db, _settings(), allowed_lz_ids=None, page=2, page_size=25
    )

    sql = db.fetchall.await_args.args[0]
    assert "LIMIT ? OFFSET ?" in sql
    assert "COUNT(*) OVER() AS _total" in sql
    assert db.fetchall.await_args.args[-2:] == (25, 25)
    assert result["total"] == 512
    assert "_total" not in result["items"][0]


@pytest.mark.asyncio
async def test_jobs_overview_reads_the_previous_window_from_gold() -> None:
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(
        return_value={
            "total_cost": 120.0,
            "prev_cost": 100.0,
            "active_jobs": 3,
            "window_start": None,
            "as_of_date": None,
        }
    )

    result = await fetch_jobs_overview(db, _settings(), allowed_lz_ids=None, window_days=30)

    assert result["kpis"]["cost_delta_pct"] == 20.0
    assert result["kpis"]["active_jobs"] == 3
    assert "SUM(cost_usd_prev_window)" in db.fetchone.await_args.args[0]


@pytest.mark.asyncio
async def test_jobs_overview_left_joins_the_efficiency_snapshot() -> None:
    """The overview shows Lifetime / Prev lifetime / Utilization next to the cost.

    Those three live on the efficiency rollup, joined on the grain **and** on
    ``window_days`` — both tables hold one row per job and per window, so omitting it
    would fan a job out over its four windows.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_jobs_overview(db, _settings(), allowed_lz_ids=None, window_days=7)

    sql = db.fetchall.await_args.args[0]
    assert _JOB_EFFICIENCY_ROLLING in sql
    assert "LEFT JOIN e" in sql
    # LEFT and never INNER: a job billed without a measured minute stays listed.
    assert "INNER JOIN" not in sql
    assert "e.window_days = j.window_days" in sql
    assert "e.uptime_hours," in sql
    assert "e.uptime_hours_prev_window," in sql
    assert "e.utilization_status" in sql
    # Each snapshot is pinned on its own MAX(as_of_date): the two rollups are written
    # separately, and cross-pinning would blank the utilization the day they diverge.
    assert f"as_of_date = (SELECT MAX(as_of_date) FROM `cat`.`sch`.`{_JOB_COST_ROLLING}`)" in sql
    assert (
        f"as_of_date = (SELECT MAX(as_of_date) FROM `cat`.`sch`.`{_JOB_EFFICIENCY_ROLLING}`)"
        in sql
    )


@pytest.mark.asyncio
async def test_jobs_overview_derives_the_uptime_delta() -> None:
    """``Prev lifetime`` carries a per-cent variation, like the all-purpose page."""
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(
        return_value=[
            {
                "job_id": "987",
                "cost_usd": 10.0,
                "uptime_hours": 46.8,
                "uptime_hours_prev_window": 41.0,
                "utilization_status": "OPTIMAL",
                "_total": 1,
            }
        ]
    )

    result = await fetch_jobs_overview(db, _settings(), allowed_lz_ids=None)

    assert result["items"][0]["uptime_hours_delta_pct"] == 14.1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fetcher", "prefix"),
    [(fetch_jobs_cost, ""), (fetch_jobs_overview, "j.")],
)
async def test_jobs_list_only_the_grains_that_cost_something(
    fetcher: Any, prefix: str
) -> None:
    """A job that neither cost nor consumed anything over the window is not listed.

    The rolling snapshot holds one row per known job: measured on dev, only 4 896 of the
    6 759 rows of the 30-day window are billed. The rest made the footer count read like an
    inventory and left every metric column on "—". DBU is part of the test: a grain that ran
    without being charged still ran.
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
async def test_jobs_efficiency_is_not_filtered_on_cost() -> None:
    """The efficiency snapshot carries no cost column — filtering it there would throw."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_jobs_efficiency(db, _settings(), allowed_lz_ids=None, window_days=30)

    sql = db.fetchall.await_args.args[0]
    assert "cost_usd" not in sql
    assert "dbu_quantity" not in sql


@pytest.mark.asyncio
async def test_jobs_search_narrows_the_billed_population() -> None:
    """Search is ANDed to the cost filter, not substituted for it."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_jobs_overview(
        db, _settings(), allowed_lz_ids=None, window_days=30, search="ingest"
    )

    sql, *params = db.fetchall.await_args.args
    assert "COALESCE(j.cost_usd, 0) > 0" in sql
    assert "LOWER(j.job_name) LIKE ?" in sql
    assert "%ingest%" in params


@pytest.mark.asyncio
async def test_jobs_overview_keeps_an_unmeasured_job_listed() -> None:
    """A billed job with no efficiency row keeps its cost, and reads null not zero."""
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(
        return_value=[
            {
                "job_id": "987",
                "cost_usd": 941.47,
                "uptime_hours": None,
                "uptime_hours_prev_window": None,
                "utilization_status": None,
                "_total": 1,
            }
        ]
    )

    result = await fetch_jobs_overview(db, _settings(), allowed_lz_ids=None)

    item = result["items"][0]
    assert item["cost_usd"] == 941.47
    assert item["uptime_hours"] is None
    assert item["uptime_hours_delta_pct"] is None
    assert item["utilization_status"] is None


# ---------------------------------------------------------------------------
# Efficiency (024 T005) — grain ``job_id``, no ``is_zombie`` at this grain (R8)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("window_days", [1, 7, 30, 90])
async def test_jobs_efficiency_reads_the_rolling_table_for_the_window(
    window_days: int,
) -> None:
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_jobs_efficiency(
        db, _settings(), allowed_lz_ids=None, window_days=window_days
    )

    sql, *params = db.fetchall.await_args.args
    assert _JOB_EFFICIENCY_ROLLING in sql
    assert "window_days = ?" in sql
    assert window_days in params
    assert (
        f"as_of_date = (SELECT MAX(as_of_date) FROM `cat`.`sch`.`{_JOB_EFFICIENCY_ROLLING}`)"
        in sql
    )


@pytest.mark.asyncio
async def test_jobs_efficiency_grain_and_no_zombie_column() -> None:
    """``job_id`` + name fallback; ``is_zombie`` is not produced at this grain (R8)."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_jobs_efficiency(db, _settings(), allowed_lz_ids=None)

    sql = db.fetchall.await_args.args[0]
    assert "COALESCE(NULLIF(job_name, ''), job_id) AS job_name" in sql
    assert "cpu_util_p95_pct" in sql
    assert "cluster_count" in sql
    assert "is_zombie" not in sql
    assert "cluster_name" not in sql
    assert "cluster_type" not in sql


@pytest.mark.asyncio
async def test_jobs_efficiency_derives_the_previous_window_deltas() -> None:
    """``uptime`` in per cent, ``idle`` in POINTS — it is already a percentage."""
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(
        return_value=[
            {
                "job_id": "987",
                "uptime_hours": 46.8,
                "uptime_hours_prev_window": 41.0,
                "idle_pct": 21.5,
                "idle_pct_prev_window": 18.0,
                "_total": 1,
            }
        ]
    )

    result = await fetch_jobs_efficiency(db, _settings(), allowed_lz_ids=None)

    item = result["items"][0]
    assert item["uptime_hours_delta_pct"] == 14.1
    assert item["idle_pct_delta_pts"] == 3.5


@pytest.mark.asyncio
@pytest.mark.parametrize("previous", [None, 0, Decimal("0")])
async def test_jobs_efficiency_keeps_an_incomparable_window_null(previous: Any) -> None:
    """No previous window → ``None``, never a 100 % collapse."""
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)
    db.fetchall = AsyncMock(
        return_value=[
            {
                "job_id": "987",
                "uptime_hours": 46.8,
                "uptime_hours_prev_window": previous,
                "idle_pct": 21.5,
                "idle_pct_prev_window": None,
                "_total": 1,
            }
        ]
    )

    result = await fetch_jobs_efficiency(db, _settings(), allowed_lz_ids=None)

    assert result["items"][0]["uptime_hours_delta_pct"] is None
    assert result["items"][0]["idle_pct_delta_pts"] is None


# ---------------------------------------------------------------------------
# Detail + trends (024 T005)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_job_detail_has_no_governance_key_at_all() -> None:
    """C2: the key is ABSENT, not ``null`` — ``null`` reads "measured and empty"."""
    db = AsyncMock()
    db.fetchone = AsyncMock(
        return_value={
            "cloud_provider": "azure",
            "workspace_id": "1234",
            "job_id": "987",
            "cost_usd": 12.0,
            "window_start": "2026-08-10",
            "as_of_date": "2026-09-08",
        }
    )

    result = await fetch_job_detail(db, _settings(), None, "987", window_days=30)

    assert result is not None
    assert "governance" not in result
    assert result["cost"] is not None
    assert result["window"]["window_days"] == 30


@pytest.mark.asyncio
async def test_job_detail_returns_none_when_out_of_scope() -> None:
    """A grain the caller cannot see is a 404 in the route, never an empty 200."""
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)

    assert await fetch_job_detail(db, _settings(), None, "nope", window_days=30) is None


@pytest.mark.asyncio
async def test_job_detail_serves_cost_when_efficiency_is_missing() -> None:
    """``efficiency: null`` is normal (``node_timeline`` coverage), not an error."""
    cost_row = {
        "cloud_provider": "aws",
        "workspace_id": "5566",
        "job_id": "987",
        "cost_usd": 12.0,
        "window_start": "2026-08-10",
        "as_of_date": "2026-09-08",
    }
    db = AsyncMock()
    db.fetchone = AsyncMock(side_effect=[cost_row, None])

    result = await fetch_job_detail(db, _settings(), None, "987", window_days=30)

    assert result is not None
    assert result["efficiency"] is None
    assert result["cost"]["cost_usd"] == 12.0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("granularity", "expected"),
    [("day", "day"), ("week", "week"), ("month", "month"), ("../etc", "day")],
)
async def test_job_cost_trend_reads_the_daily_table(
    granularity: str, expected: str
) -> None:
    """A rolling row is one point per window: a series can only come from daily."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])

    result = await fetch_job_cost_trend(
        db, _settings(), None, "987", granularity=granularity
    )

    sql, *params = db.fetchall.await_args.args
    assert _JOB_COST_DAILY in sql
    assert _JOB_COST_ROLLING not in sql
    assert f"date_trunc('{expected}', period_start)" in sql
    assert "job_id = ?" in sql
    assert "987" in params
    assert result["granularity"] == expected


@pytest.mark.asyncio
async def test_job_uptime_trend_weights_idle_by_uptime() -> None:
    """A plain AVG would weigh a 20-minute day like a 20-hour one."""
    db = AsyncMock()
    db.fetchall = AsyncMock(
        return_value=[
            {"bucket": "2026-09-01", "uptime_hours": 2.4, "idle_pct": 17.34},
            {"bucket": "2026-09-02", "uptime_hours": 0, "idle_pct": None},
        ]
    )

    result = await fetch_job_uptime_trend(db, _settings(), None, "987")

    sql = db.fetchall.await_args.args[0]
    assert _JOB_EFFICIENCY_DAILY in sql
    assert "SUM(idle_pct * uptime_hours)" in sql
    assert result["items"][0]["idle_pct"] == 17.3
    # None, not 0: an unmeasured bucket has no idle share, and 0 % would read as
    # a fully busy job.
    assert result["items"][1]["idle_pct"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("fetcher", [fetch_jobs_cost, fetch_jobs_overview])
async def test_jobs_collapse_compute_kind_back_to_one_row_per_job(fetcher: Any) -> None:
    """T001b put ``compute_kind`` IN the gold grain: a mixed job holds two rows.

    Measured in dev on 2026-09-10 over 30 days: 926 job-days and 101 jobs out of 8 457
    bill both ways. Read as-is, the list would show the job twice and no error would be
    raised anywhere — which is exactly why this is a test and not a comment.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetcher(db, _settings(), allowed_lz_ids=None)

    sql = db.fetchall.await_args.args[0]
    assert "GROUP BY cloud_provider, workspace_id, job_id, window_days" in sql
    assert "SUM(cost_usd) AS cost_usd" in sql
    assert "SUM(dbu_quantity) AS dbu_quantity" in sql
    assert "SUM(cost_usd_prev_window) AS cost_usd_prev_window" in sql
    # The split stays readable as a label rather than duplicating the row.
    assert "THEN 'MIXED'" in sql
    assert "compute_kind" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize("fetcher", [fetch_jobs_cost, fetch_jobs_overview])
async def test_jobs_rederive_the_rank_and_the_ratio_after_the_rollup(
    fetcher: Any,
) -> None:
    """Gold ranks WITHIN each ``compute_kind`` — two rows can both hold rank 1.

    And a ratio of sums is not the sum of ratios, so ``cost_delta_pct`` cannot be
    carried through the ``GROUP BY`` either. Both are recomputed on the collapsed row,
    with the formulas of ``job_cluster_cost_rolling.py``.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetcher(db, _settings(), allowed_lz_ids=None)

    sql = db.fetchall.await_args.args[0]
    # The whole derivation, not just "RANK() OVER (" somewhere in the query: the
    # ``is_top_cost`` expression contains that substring too, so the loose form still
    # passed when ``cost_rank`` was carried straight through the GROUP BY. Verified by
    # sabotage — the loose assertion did not bite.
    assert (
        "RANK() OVER (\n"
        "                    PARTITION BY window_days ORDER BY cost_usd DESC\n"
        "                ) AS cost_rank"
    ) in sql
    assert (
        "RANK() OVER (PARTITION BY window_days ORDER BY cost_usd DESC)\n"
        "                    <= 10 AS is_top_cost"
    ) in sql
    assert (
        "(cost_usd - cost_usd_prev_window)\n"
        "                    / NULLIF(cost_usd_prev_window, 0) * 100 AS cost_delta_pct"
    ) in sql
    # Carrying either through the rollup would be silently wrong, not an error.
    for aggregated in ("cost_rank", "cost_delta_pct", "is_top_cost"):
        for agg in ("SUM", "MAX", "MIN", "AVG", "FIRST"):
            assert f"{agg}({aggregated})" not in sql


@pytest.mark.asyncio
async def test_jobs_overview_kpi_counts_a_mixed_job_once() -> None:
    """``active_jobs`` sat next to a list that collapses the two kinds.

    The former ``SUM(CASE WHEN cost_usd > 0 THEN 1 ELSE 0 END)`` incremented once per
    ROW, so the card read above the number of jobs actually listed as soon as a job
    billed both ways. The cost sums, by contrast, stay correct on the new grain: the
    two rows partition the job's billing lines.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_jobs_overview(db, _settings(), allowed_lz_ids=None)

    kpi_sql = db.fetchone.await_args.args[0]
    assert "COUNT(DISTINCT" in kpi_sql
    assert "concat_ws('|', cloud_provider, workspace_id, job_id)" in kpi_sql
    assert "SUM(CASE WHEN cost_usd > 0 THEN 1 ELSE 0 END)" not in kpi_sql
    assert "COALESCE(SUM(cost_usd), 0) AS total_cost" in kpi_sql


@pytest.mark.asyncio
async def test_jobs_overview_still_joins_the_efficiency_snapshot_on_the_window() -> None:
    """``window_days`` has to survive the rollup or the LEFT JOIN loses its key.

    Dropping it from the ``GROUP BY`` output would leave ``j.window_days`` unresolved —
    a loud failure, but only once someone runs the query.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    await fetch_jobs_overview(db, _settings(), allowed_lz_ids=None, window_days=30)

    sql = db.fetchall.await_args.args[0]
    assert "window_days," in sql
    assert "AND e.window_days = j.window_days" in sql


@pytest.mark.asyncio
async def test_job_detail_rolls_up_but_never_ranks() -> None:
    """A rank is a property of a population; this query holds a single job.

    Ranking here would return 1 for every job the drawer is opened on. NULL says "not
    computed", which the contract already allows, and nothing renders the rank off this
    route. The cost, on the other hand, must be the job's TOTAL: the previous
    ``ORDER BY cost_usd DESC LIMIT 1`` on the raw table would have returned only the
    larger of the two kinds and silently understated a mixed job.
    """
    db = AsyncMock()
    db.fetchone = AsyncMock(return_value=None)

    await fetch_job_detail(db, _settings(), None, "987")

    cost_sql = db.fetchone.await_args_list[0].args[0]
    assert "GROUP BY cloud_provider, workspace_id, job_id, window_days" in cost_sql
    assert "SUM(cost_usd) AS cost_usd" in cost_sql
    assert "CAST(NULL AS INT) AS cost_rank" in cost_sql
    assert "CAST(NULL AS BOOLEAN) AS is_top_cost" in cost_sql
    assert "RANK() OVER" not in cost_sql


@pytest.mark.asyncio
async def test_job_cost_trend_already_aggregates_over_compute_kind() -> None:
    """The series was grain-proof before T001b, and must stay so.

    It reads the daily table with ``SUM ... GROUP BY`` on the bucket, so the two kinds
    of a mixed day already fold into one point. Without the ``SUM`` the chart would draw
    two values at the same date.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])

    await fetch_job_cost_trend(db, _settings(), None, "987")

    sql = db.fetchall.await_args.args[0]
    assert "SUM(cost_usd)" in sql
    assert "SUM(dbu_quantity)" in sql
    assert "GROUP BY 1" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize("fetcher", [fetch_jobs_efficiency, fetch_job_uptime_trend])
async def test_jobs_efficiency_never_mentions_compute_kind(fetcher: Any) -> None:
    """``job_efficiency_*`` has no such column, and cannot have one.

    It descends from ``system.compute.node_timeline``, which only samples CLUSTERS: a
    serverless job has no row to classify. Referencing ``compute_kind`` here would raise
    ``UNRESOLVED_COLUMN``. This is the mirror of the gold-side de-aliasing done in T001b
    on ``JOB_EFFICIENCY_{DAILY,ROLLING}_MERGE_KEYS``.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)

    if fetcher is fetch_job_uptime_trend:
        await fetcher(db, _settings(), None, "987")
    else:
        await fetcher(db, _settings(), allowed_lz_ids=None)

    sql = db.fetchall.await_args.args[0]
    assert "compute_kind" not in sql


def test_job_cost_row_columns_all_exist_on_the_declared_contract() -> None:
    """Every column the job cost rows select must exist on ``JobCostItem``.

    Nothing enforces this at runtime: the routes are annotated ``dict[str, Any]`` and
    ``JobCostItem`` is exported but never used as a ``response_model``, so a column
    served without being declared reaches the client and silently diverges from the
    contract that ``api.ts`` mirrors. This test is the only thing tying the two.
    """
    from dcm_commons.schemas import JobCostItem

    from app.api.services.compute_metrics_jobs import _ROW_COLUMNS

    # Split on the commas that separate select items, i.e. those at paren depth 0:
    # ``COALESCE(NULLIF(job_name, ''), job_id)`` carries two of its own.
    parts: list[str] = [""]
    depth = 0
    for char in _ROW_COLUMNS:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("")
        else:
            parts[-1] += char
    # ``... AS alias`` -> alias, plain column -> itself.
    selected = {part.split(" AS ")[-1].strip() for part in parts if part.strip()}
    assert "compute_kind" in selected, "guard is pointless if the column is gone"
    undeclared = selected - set(JobCostItem.model_fields)
    assert undeclared == set(), f"served but not declared on JobCostItem: {undeclared}"


class TestJobsWindowDays:
    """``window_days`` is validated by the API, never rounded down to 1 in silence."""

    LIST_PATHS = ("/jobs/overview", "/jobs/cost", "/jobs/efficiency")

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


async def test_jobs_overview_route_returns_the_job_grain(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.return_value = {
        "total_cost": 12.0,
        "prev_cost": 8.0,
        "active_jobs": 1,
        "window_start": "2026-09-01",
        "as_of_date": "2026-09-07",
    }
    mock_db.fetchall.return_value = [
        {
            "cloud_provider": "azure",
            "workspace_id": "1234",
            "job_id": "987654321",
            "job_name": "daily_ingestion",
            "cluster_count": 12,
            "cost_usd": 12.0,
            "_total": 1,
        }
    ]

    resp = await client.get(f"{BASE}/jobs/overview")

    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["job_id"] == "987654321"
    assert item["job_name"] == "daily_ingestion"


async def test_jobs_cost_empty_200(client: AsyncClient, mock_db: AsyncMock) -> None:
    mock_db.fetchall.return_value = []

    resp = await client.get(f"{BASE}/jobs/cost")

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["window"]["window_days"] == 1


async def test_jobs_efficiency_is_not_swallowed_by_the_job_id_segment(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """Route order: ``/jobs/efficiency`` must not resolve as ``job_id="efficiency"``.

    A variable segment declared first would win, and the list would answer 404 (or
    a detail payload) instead of a page. Same trap as ``/filter-options``.
    """
    mock_db.fetchall.return_value = []

    resp = await client.get(f"{BASE}/jobs/efficiency")

    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    # A detail payload would carry these instead.
    assert "cost" not in body
    assert "efficiency" not in body


async def test_jobs_efficiency_route_returns_the_job_grain(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchall.return_value = [
        {
            "cloud_provider": "azure",
            "workspace_id": "1234",
            "job_id": "987654321",
            "job_name": "daily_ingestion",
            "cluster_count": 12,
            "cpu_util_p95_pct": 71.2,
            "idle_pct": 21.5,
            "idle_pct_prev_window": 18.0,
            "uptime_hours": 46.8,
            "uptime_hours_prev_window": 41.0,
            "_total": 1,
        }
    ]

    resp = await client.get(f"{BASE}/jobs/efficiency", params={"window_days": 30})

    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["job_id"] == "987654321"
    assert item["idle_pct_delta_pts"] == 3.5
    assert "is_zombie" not in item


async def test_job_detail_unknown_id_is_404(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.return_value = None

    resp = await client.get(f"{BASE}/jobs/does-not-exist")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Job not found"


async def test_job_trends_routes_take_no_window_days(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """A trend is a series over the period: ``window_days`` has nothing to select."""
    mock_db.fetchall.return_value = []

    for suffix in ("cost-trend", "uptime-trend"):
        resp = await client.get(
            f"{BASE}/jobs/987/{suffix}", params={"granularity": "week"}
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["granularity"] == "week"
        assert "window" not in body
