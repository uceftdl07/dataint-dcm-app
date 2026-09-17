"""Compute Metrics — job cluster gold table.

Grain ``job_id``: one row per job and per window (1/7/30/90 days) anchored on
``as_of_date``, read from ``gold_dbx_compute_job_cluster_cost_rolling``. Job clusters
are ephemeral — a distinct ``cluster_id`` per run — so the useful unit is the stable
``job_id``, never the cluster.

Since T001b the gold grain is one row per job **and per ``compute_kind``**, so the
routes no longer read a pre-aggregated row: ``_cost_rollup_ctes`` collapses the two
kinds back to one row per job and re-derives the ratio and the rank. See its comment
for why the jobs page collapses where the DLT page filters. Modelled on
``compute_metrics_warehouses`` (server pagination, rolling window, ``cost_usd_prev_window``
≤ 0 → ``null``, stale-snapshot guard).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_table
from .compute_metrics_common import (
    _DEFAULT_PAGE_SIZE,
    RollingWindowDays,
    _as_float,
    _bounds_sql,
    _clamp_page,
    _date_where,
    _empty_page,
    _grain,
    _idle_delta_pts,
    _iso,
    _normalize_prev_cost,
    _pct_delta,
    _period_dict,
    _resolve_period,
    _round_pct,
    _row_to_dict,
    _scope_where,
    _uptime_delta_pct,
    _window_block,
    _window_period,
    _window_where,
)

__all__ = [
    "fetch_job_cost_trend",
    "fetch_job_detail",
    "fetch_job_uptime_trend",
    "fetch_jobs_cost",
    "fetch_jobs_efficiency",
    "fetch_jobs_overview",
]

logger = logging.getLogger(__name__)

# Snapshots read by the list views and the job detail.
_COST_ROLLING = "gold_dbx_compute_job_cluster_cost_rolling"
_EFFICIENCY_ROLLING = "gold_dbx_compute_job_efficiency_rolling"
# Series read by the per-job trends only — a rolling row is one point per window.
_COST_DAILY = "gold_dbx_compute_job_cluster_cost_daily"
_EFFICIENCY_DAILY = "gold_dbx_compute_job_efficiency_daily"

# Per-job endpoints all narrow their scope the same way.
_JOB_FILTER = "job_id = ?"

# Threshold behind ``is_top_cost``, mirroring ``TOP_COST_RANK_THRESHOLD`` in the gold
# package. Duplicated rather than imported: the backend does not depend on the pipeline
# package. Kept next to the rank that uses it so a drift is visible in one place.
_TOP_COST_RANK_THRESHOLD = 10


# ``gold_dbx_compute_job_cluster_cost_{daily,rolling}`` carry ``compute_kind`` IN THEIR
# GRAIN since T001b: a job that ran both classic and serverless over the window has
# **two** rows. Measured in dev on 2026-09-10 over 30 days: 926 job-days and 101 jobs
# out of 8 457. Reading the snapshot as-is would put two lines per such job in the list,
# two ``cost_rank = 1`` per window, and count it twice in ``active_jobs`` — with no error
# raised anywhere.
#
# The jobs page collapses ``compute_kind`` instead of exposing it as a row dimension,
# unlike the DLT page which **filters** on ``compute_kind = 'CLASSIC'``. The two choices
# are deliberate and answer different questions: the DLT page is dedicated to the DLT
# *cluster* compute (user decision of 2026-09-09), whereas the jobs page is where a user
# looks for "what does this job cost me" — spec 025 has its population **grow** to
# include serverless, which is the whole point of T001b (85 653 $/30 days that the page
# did not show, i.e. 65 % of the job spend).
#
# ``compute_kind`` therefore survives as a *label* — ``CLASSIC``, ``SERVERLESS`` or
# ``MIXED`` — so the split stays readable without duplicating the row.
#
# ``cost_delta_pct``, ``cost_rank`` and ``is_top_cost`` are RE-DERIVED, never summed:
# gold ranks *within* each ``compute_kind`` (two rows can hold rank 1) and a ratio of
# sums is not the sum of ratios. Formulas mirror ``job_cluster_cost_rolling.py`` exactly.
def _cost_rollup_ctes(table: str, where: str, *, ranked: bool = True) -> str:
    """Render the two CTEs that bring the cost snapshot back to one row per job.

    ``_billed`` is left out on purpose: the caller applies it *after* the rollup, so a
    job billed only on one of its two compute kinds stays listed.

    ``ranked=False`` yields NULL for ``cost_rank``/``is_top_cost`` instead of computing
    them. A rank is a property of a **population**, and the per-job endpoints scope
    ``where`` down to a single job: ranking there would return 1 for every job asked
    about. NULL says "not computed here"; 1 would be a wrong answer, and the field is
    already nullable in the contract. Nothing renders it off the detail route — the
    "Top" badge lives in the list.
    """
    rank_sql = (
        f"""RANK() OVER (
                    PARTITION BY window_days ORDER BY cost_usd DESC
                ) AS cost_rank,
                RANK() OVER (PARTITION BY window_days ORDER BY cost_usd DESC)
                    <= {_TOP_COST_RANK_THRESHOLD} AS is_top_cost"""
        if ranked
        else """CAST(NULL AS INT) AS cost_rank,
                CAST(NULL AS BOOLEAN) AS is_top_cost"""
    )
    return f"""
        _src AS (
            SELECT * FROM {table} {where}
        ),
        _rolled AS (
            SELECT
                cloud_provider,
                workspace_id,
                job_id,
                -- Pinned to a single value by ``where`` already, but kept in the
                -- grain because the overview joins the efficiency snapshot on it.
                window_days,
                -- MAX and not FIRST: the name comes from the same `latest_attrs`
                -- lookup for both rows of a job, so it is already identical. MAX
                -- also prefers a known name over a NULL one, which FIRST would not.
                MAX(job_name) AS job_name,
                CASE
                    WHEN COUNT(DISTINCT compute_kind) > 1 THEN 'MIXED'
                    ELSE MAX(compute_kind)
                END AS compute_kind,
                -- A SERVERLESS row carries 0, not NULL (no cluster is provisioned),
                -- so the sum is the classic cluster count of a mixed job.
                SUM(cluster_count) AS cluster_count,
                SUM(dbu_quantity) AS dbu_quantity,
                SUM(cost_usd) AS cost_usd,
                SUM(cost_usd_prev_window) AS cost_usd_prev_window,
                MAX(window_start) AS window_start,
                MAX(as_of_date) AS as_of_date
            FROM _src
            GROUP BY cloud_provider, workspace_id, job_id, window_days
        ),
        j AS (
            SELECT
                *,
                (cost_usd - cost_usd_prev_window)
                    / NULLIF(cost_usd_prev_window, 0) * 100 AS cost_delta_pct,
                {rank_sql}
            FROM _rolled
        )
    """


# The name may be empty (a run launched from a notebook has no job definition, so no
# name in any source): NULLIF turns that "" into the id fallback, not a blank cell.
_ROW_COLUMNS = """
    cloud_provider,
    workspace_id,
    job_id,
    COALESCE(NULLIF(job_name, ''), job_id) AS job_name,
    compute_kind,
    cluster_count,
    dbu_quantity,
    cost_usd,
    cost_usd_prev_window,
    cost_delta_pct,
    cost_rank,
    is_top_cost,
    window_start,
    as_of_date
"""

# Columns of ``gold_dbx_compute_job_efficiency_rolling``, listed rather than ``*``:
# the table also carries ``_generated_at``, and the name fallback has to be applied
# here exactly as on the cost rows.
#
# No ``is_zombie`` — gold does not produce it at this grain and must not (024 R8): a
# JOB cluster dies with its run, so the flag would be ``false`` on every row and read
# as a control that passes. No ``cluster_name``/``cluster_type`` either: the grain is
# the job, aggregating as many ephemeral clusters as it had runs.
_EFFICIENCY_ROW_COLUMNS = """
    cloud_provider,
    workspace_id,
    job_id,
    COALESCE(NULLIF(job_name, ''), job_id) AS job_name,
    cluster_count,
    cpu_util_avg_pct,
    cpu_util_p95_pct,
    mem_util_avg_pct,
    mem_util_p95_pct,
    cpu_wait_avg_pct,
    idle_pct,
    idle_pct_prev_window,
    uptime_hours,
    uptime_hours_prev_window,
    active_hours,
    worker_count_avg,
    worker_count_max,
    autoscale_oscillation,
    driver_node_type,
    worker_node_type,
    autoscale_enabled,
    autoscale_min_workers,
    autoscale_max_workers,
    configured_worker_count,
    utilization_status,
    recommended_node_type,
    rightsizing_reco,
    estimated_savings_usd,
    window_days,
    window_start,
    as_of_date
"""


# Overview only: the cost row plus the three utilization figures the page shows next
# to the cost (cumulated uptime, its predecessor, sizing verdict). Every column is
# **qualified** — ``job_name``, ``job_id``, ``cluster_count``, ``window_start`` and
# ``as_of_date`` all exist on both snapshots, so an unqualified reference becomes
# ambiguous as soon as the LEFT JOIN is in. ``dbu_quantity`` stays in the payload even
# though the page no longer shows a DBU column: other readers of this route use it.
_OVERVIEW_ROW_COLUMNS = """
    j.cloud_provider,
    j.workspace_id,
    j.job_id,
    COALESCE(NULLIF(j.job_name, ''), j.job_id) AS job_name,
    j.compute_kind,
    j.cluster_count,
    j.dbu_quantity,
    j.cost_usd,
    j.cost_usd_prev_window,
    j.cost_delta_pct,
    j.cost_rank,
    j.is_top_cost,
    j.window_start,
    j.as_of_date,
    e.uptime_hours,
    e.uptime_hours_prev_window,
    e.utilization_status
"""


def _sort_clause(sort: str, prefix: str = "") -> str:
    if sort == "name":
        return f"{prefix}job_name ASC NULLS LAST, {prefix}job_id ASC"
    return f"{prefix}cost_usd DESC NULLS LAST, {prefix}job_id ASC"


def _efficiency_sort_clause(sort: str) -> str:
    """Default sort of the efficiency view: the savings the page exists to surface.

    ``cost_usd`` is not on this table (the cost lives at its own grain), so the
    cost-ordered default of the other views has nothing to sort on here.
    """
    if sort == "name":
        return "job_name ASC NULLS LAST, job_id ASC"
    if sort == "uptime":
        return "uptime_hours DESC NULLS LAST, job_id ASC"
    return "estimated_savings_usd DESC NULLS LAST, job_id ASC"


def _search_clause(search: str | None, prefix: str = "") -> tuple[str, list[Any]]:
    """Free-text filter on the job name and id, over the whole window not the page.

    ``prefix`` qualifies the two columns for the joined overview query, where both
    names also exist on the efficiency side.
    """
    if not search or not search.strip():
        return "", []
    pattern = f"%{search.strip().lower()}%"
    return (
        f"(LOWER({prefix}job_name) LIKE ? OR LOWER({prefix}job_id) LIKE ?)",
        [pattern, pattern],
    )


def _billed_only(prefix: str = "") -> str:
    """Restrict the listed population to grains that cost or consumed something.

    Same rule as the pipelines service, applied for the same reason: the rolling snapshot
    holds one row per known job, billed over the window or not. Measured in dev on
    2026-09-09: of the rows served, **982 of 1 701 are billed at 1 day, 2 375 of 3 309 at
    7 days, 4 896 of 6 759 at 30 days** (at 90 days every row is billed). The unbilled ones
    made the footer count read like a job inventory and left every metric column on "—".

    DBU is part of the test on purpose: a grain that consumed without being charged
    (credits, promo, a free SKU) did run, and dropping it would hide real compute. The
    ``active_jobs`` KPI already counted ``cost_usd > 0`` only, so this brings the served
    total in line with the card rather than changing what the card means.
    """
    return f"(COALESCE({prefix}cost_usd, 0) > 0 OR COALESCE({prefix}dbu_quantity, 0) > 0)"


async def fetch_jobs_cost(
    db: DatabricksWarehousePool,
    settings: Settings,
    allowed_lz_ids: list[str] | None,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    workspace_ids: list[str] | None = None,
    allowed_workspace_ids: list[str] | None = None,
    cloud_provider: str | None = None,
    window_days: int = RollingWindowDays.DAY,
    search: str | None = None,
    sort: str = "cost_desc",
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    start, end = _resolve_period(period_start, period_end)
    page, page_size = _clamp_page(page, page_size)
    offset = (page - 1) * page_size
    window = int(window_days)
    table = qualified_table(settings, _COST_ROLLING)
    empty = _empty_page(page, page_size, start, end)
    empty["window"] = _window_block(window, None)

    try:
        scope, scope_params = _scope_where(
            allowed_lz_ids,
            source_lz_id,
            source_lz_ids,
            workspace_ids,
            has_lz_column=False,
            allowed_workspace_ids=allowed_workspace_ids,
            cloud_provider=cloud_provider,
        )
        where, params = _window_where(
            scope, scope_params, window, latest_snapshot_table=table
        )
        row_params = list(params)

        search_sql, search_params = _search_clause(search)
        row_params.extend(search_params)
        filter_sql = f" AND {_billed_only()}"
        if search_sql:
            filter_sql += f" AND {search_sql}"

        bounds_row, rows = await asyncio.gather(
            db.fetchone(_bounds_sql(table, where), *params),
            db.fetchall(
                f"""
                WITH {_cost_rollup_ctes(table, where)}
                SELECT
                    {_ROW_COLUMNS},
                    COUNT(*) OVER() AS _total
                FROM j
                WHERE 1 = 1{filter_sql}
                ORDER BY {_sort_clause(sort)}
                LIMIT ? OFFSET ?
                """,
                *row_params,
                page_size,
                offset,
            ),
        )

        total = int(rows[0]["_total"]) if rows else 0
        window_block = _window_block(window, bounds_row)
        items: list[dict[str, Any]] = []
        for row in rows:
            item = _row_to_dict(row)
            _normalize_prev_cost(item)
            items.append(item)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "window": window_block,
            "period": _window_period(window_block, start, end),
        }
    except Exception:
        logger.exception("jobs cost soft-fail")
        return empty


async def fetch_jobs_overview(
    db: DatabricksWarehousePool,
    settings: Settings,
    allowed_lz_ids: list[str] | None,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    workspace_ids: list[str] | None = None,
    allowed_workspace_ids: list[str] | None = None,
    cloud_provider: str | None = None,
    window_days: int = RollingWindowDays.DAY,
    search: str | None = None,
    sort: str = "cost_desc",
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    start, end = _resolve_period(period_start, period_end)
    page, page_size = _clamp_page(page, page_size)
    offset = (page - 1) * page_size
    window = int(window_days)
    table = qualified_table(settings, _COST_ROLLING)
    eff_table = qualified_table(settings, _EFFICIENCY_ROLLING)

    empty = {
        "kpis": {"total_cost_usd": 0.0, "cost_delta_pct": None, "active_jobs": 0},
        "items": [],
        "total": 0,
        "page": page,
        "page_size": page_size,
        "window": _window_block(window, None),
        "period": _period_dict(start, end),
    }

    try:
        scope, scope_params = _scope_where(
            allowed_lz_ids,
            source_lz_id,
            source_lz_ids,
            workspace_ids,
            has_lz_column=False,
            allowed_workspace_ids=allowed_workspace_ids,
            cloud_provider=cloud_provider,
        )
        where, params = _window_where(
            scope, scope_params, window, latest_snapshot_table=table
        )
        # The efficiency snapshot gets its own stale-row guard: the two tables are
        # written by two different rollups, so pinning one on the other's MAX
        # ``as_of_date`` would blank the utilization columns the day they diverge.
        eff_where, eff_params = _window_where(
            scope, scope_params, window, latest_snapshot_table=eff_table
        )
        row_params = [*params, *eff_params]

        search_sql, search_params = _search_clause(search, prefix="j.")
        row_params.extend(search_params)
        filter_sql = f" AND {_billed_only(prefix='j.')}"
        if search_sql:
            filter_sql += f" AND {search_sql}"

        kpi_row, rows = await asyncio.gather(
            db.fetchone(
                f"""
                SELECT
                    -- The two sums stay correct on the post-T001b grain: the two
                    -- ``compute_kind`` rows of a job partition its billing lines, so
                    -- summing them is exactly the job total.
                    COALESCE(SUM(cost_usd), 0) AS total_cost,
                    COALESCE(SUM(cost_usd_prev_window), 0) AS prev_cost,
                    -- COUNT DISTINCT on the job grain, and no longer one increment per
                    -- row: since T001b a mixed job holds two rows and the previous
                    -- ``SUM(CASE ...)`` counted it twice (101 jobs over 30 days in dev).
                    -- The card would have read above the number of jobs actually listed.
                    COUNT(DISTINCT
                        CASE
                            WHEN cost_usd > 0
                            THEN concat_ws('|', cloud_provider, workspace_id, job_id)
                        END
                    ) AS active_jobs,
                    MAX(window_start) AS window_start,
                    MAX(as_of_date) AS as_of_date
                FROM {table}
                {where}
                """,
                *params,
            ),
            db.fetchall(
                f"""
                WITH {_cost_rollup_ctes(table, where)},
                e AS (
                    SELECT * FROM {eff_table} {eff_where}
                )
                SELECT
                    {_OVERVIEW_ROW_COLUMNS},
                    COUNT(*) OVER() AS _total
                FROM j
                -- LEFT, and never INNER: a job billed without a single measured
                -- minute stays listed, with "—" on the utilization columns (024
                -- SC-005). ``window_days`` belongs to the join key — both tables
                -- carry one row per job and per window.
                LEFT JOIN e
                    ON j.cloud_provider = e.cloud_provider
                   AND j.workspace_id = e.workspace_id
                   AND j.job_id = e.job_id
                   AND e.window_days = j.window_days
                WHERE 1 = 1{filter_sql}
                ORDER BY {_sort_clause(sort, prefix="j.")}
                LIMIT ? OFFSET ?
                """,
                *row_params,
                page_size,
                offset,
            ),
        )

        total_cost = _as_float((kpi_row or {}).get("total_cost")) or 0.0
        prev_cost = _as_float((kpi_row or {}).get("prev_cost")) or 0.0
        window_block = _window_block(window, kpi_row)
        total = int(rows[0]["_total"]) if rows else 0
        items: list[dict[str, Any]] = []
        for row in rows:
            item = _row_to_dict(row)
            item["uptime_hours_delta_pct"] = _uptime_delta_pct(item)
            _normalize_prev_cost(item)
            items.append(item)

        return {
            "kpis": {
                "total_cost_usd": total_cost,
                "cost_delta_pct": _pct_delta(total_cost, prev_cost),
                "active_jobs": int((kpi_row or {}).get("active_jobs") or 0),
            },
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "window": window_block,
            "period": _window_period(window_block, start, end),
        }
    except Exception:
        logger.exception("jobs overview soft-fail")
        return empty


async def fetch_jobs_efficiency(
    db: DatabricksWarehousePool,
    settings: Settings,
    allowed_lz_ids: list[str] | None,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    workspace_ids: list[str] | None = None,
    allowed_workspace_ids: list[str] | None = None,
    cloud_provider: str | None = None,
    window_days: int = RollingWindowDays.DAY,
    search: str | None = None,
    sort: str = "savings_desc",
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """CPU/memory utilization of each job over the window, grain ``job_id``.

    The population is **smaller** than ``fetch_jobs_cost``': efficiency comes from
    ``node_timeline`` (nothing for a serverless job) while cost comes from billing,
    and the rollup keeps only the grains with ``uptime_hours > 0``. Measured at
    99,0 % coverage in dev on 2026-09-09 (024 SC-005) — a documented residue, not a
    pagination bug, and nothing to backfill with a default value.
    """
    start, end = _resolve_period(period_start, period_end)
    page, page_size = _clamp_page(page, page_size)
    offset = (page - 1) * page_size
    window = int(window_days)
    table = qualified_table(settings, _EFFICIENCY_ROLLING)
    empty = _empty_page(page, page_size, start, end)
    empty["window"] = _window_block(window, None)

    try:
        scope, scope_params = _scope_where(
            allowed_lz_ids,
            source_lz_id,
            source_lz_ids,
            workspace_ids,
            has_lz_column=False,
            allowed_workspace_ids=allowed_workspace_ids,
            cloud_provider=cloud_provider,
        )
        where, params = _window_where(
            scope, scope_params, window, latest_snapshot_table=table
        )
        row_params = list(params)

        search_sql, search_params = _search_clause(search)
        row_params.extend(search_params)
        filter_sql = f" AND {search_sql}" if search_sql else ""

        bounds_row, rows = await asyncio.gather(
            db.fetchone(_bounds_sql(table, where), *params),
            db.fetchall(
                f"""
                WITH j AS (
                    SELECT * FROM {table} {where}
                )
                SELECT
                    {_EFFICIENCY_ROW_COLUMNS},
                    COUNT(*) OVER() AS _total
                FROM j
                WHERE 1 = 1{filter_sql}
                ORDER BY {_efficiency_sort_clause(sort)}
                LIMIT ? OFFSET ?
                """,
                *row_params,
                page_size,
                offset,
            ),
        )

        total = int(rows[0]["_total"]) if rows else 0
        items: list[dict[str, Any]] = []
        for row in rows:
            item = _row_to_dict(row)
            item["uptime_hours_delta_pct"] = _uptime_delta_pct(item)
            item["idle_pct_delta_pts"] = _idle_delta_pts(item)
            items.append(item)

        window_block = _window_block(window, bounds_row)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "window": window_block,
            "period": _window_period(window_block, start, end),
        }
    except Exception:
        logger.exception("jobs efficiency soft-fail")
        return empty


async def fetch_job_detail(
    db: DatabricksWarehousePool,
    settings: Settings,
    allowed_lz_ids: list[str] | None,
    job_id: str,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    workspace_ids: list[str] | None = None,
    allowed_workspace_ids: list[str] | None = None,
    cloud_provider: str | None = None,
    window_days: int = RollingWindowDays.DAY,
) -> dict[str, Any] | None:
    """Cost and efficiency of one job for the window, or ``None`` when out of scope.

    ``None`` becomes a 404 in the route: a job the caller cannot see must not answer
    an empty 200, which reads "this job exists and did nothing".

    **No governance block** — the key is absent from the payload, not ``null`` (024
    C2): ``dbr_version``, owner tags and oversizing describe a long-lived cluster, and
    ``null`` would read "governance measured, and empty".

    ``efficiency: None`` on the other hand is a **normal** outcome: the job ran on
    compute with no ``node_timeline`` row. The detail is still served, with its cost.
    """
    start, end = _resolve_period(period_start, period_end)
    window = int(window_days)
    cost_t = qualified_table(settings, _COST_ROLLING)
    eff_t = qualified_table(settings, _EFFICIENCY_ROLLING)

    try:
        scope, scope_params = _scope_where(
            allowed_lz_ids,
            source_lz_id,
            source_lz_ids,
            workspace_ids,
            has_lz_column=False,
            allowed_workspace_ids=allowed_workspace_ids,
            cloud_provider=cloud_provider,
        )
        job_scope = [*scope, _JOB_FILTER]
        job_params = [*scope_params, job_id]
        # One guard per table: the two rollups are written by two tasks, so their
        # ``MAX(as_of_date)`` can differ by a run. Applied here — unlike the cluster
        # homologue — so the drawer and the list can never disagree: without it a
        # stale snapshot with a higher cost would win the ``LIMIT 1``.
        cost_where, cost_params = _window_where(
            job_scope, job_params, window, latest_snapshot_table=cost_t
        )
        eff_where, eff_params = _window_where(
            job_scope, job_params, window, latest_snapshot_table=eff_t
        )

        cost_row, eff_row = await asyncio.gather(
            db.fetchone(
                f"""
                WITH {_cost_rollup_ctes(cost_t, cost_where, ranked=False)}
                SELECT {_ROW_COLUMNS}
                FROM j
                ORDER BY cost_usd DESC NULLS LAST
                LIMIT 1
                """,
                *cost_params,
            ),
            db.fetchone(
                f"""
                SELECT {_EFFICIENCY_ROW_COLUMNS}
                FROM {eff_t}
                {eff_where}
                ORDER BY uptime_hours DESC NULLS LAST
                LIMIT 1
                """,
                *eff_params,
            ),
        )

        if not cost_row and not eff_row:
            return None

        base = cost_row or eff_row or {}

        efficiency = _row_to_dict(eff_row)
        if efficiency:
            efficiency["uptime_hours_delta_pct"] = _uptime_delta_pct(efficiency)
            efficiency["idle_pct_delta_pts"] = _idle_delta_pts(efficiency)

        cost = _row_to_dict(cost_row)
        if cost:
            _normalize_prev_cost(cost)

        # Both rollings carry the same bounds for a given window; cost is the wider
        # population, so it is the reference when both are present.
        window_block = _window_block(window, cost_row or eff_row)

        return {
            "cloud_provider": base.get("cloud_provider"),
            "workspace_id": base.get("workspace_id"),
            "job_id": job_id,
            "cost": cost or None,
            "efficiency": efficiency or None,
            "window": window_block,
            "period": _window_period(window_block, start, end),
        }
    except Exception:
        logger.exception("job detail soft-fail for %s", job_id)
        return None


async def fetch_job_cost_trend(
    db: DatabricksWarehousePool,
    settings: Settings,
    allowed_lz_ids: list[str] | None,
    job_id: str,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    workspace_ids: list[str] | None = None,
    allowed_workspace_ids: list[str] | None = None,
    cloud_provider: str | None = None,
    granularity: str = "day",
) -> dict[str, Any]:
    """Cost / DBU series of one job, read from the daily table.

    No ``window_days``: a ``*_rolling`` row is a single point per window and cannot
    feed a series.
    """
    start, end = _resolve_period(period_start, period_end)
    table = qualified_table(settings, _COST_DAILY)
    grain = _grain(granularity)

    empty = {"items": [], "period": _period_dict(start, end), "granularity": grain}

    try:
        scope, params = _scope_where(
            allowed_lz_ids,
            source_lz_id,
            source_lz_ids,
            workspace_ids,
            has_lz_column=False,
            allowed_workspace_ids=allowed_workspace_ids,
            cloud_provider=cloud_provider,
        )
        scope.append(_JOB_FILTER)
        params.append(job_id)
        where, params = _date_where(scope, params, start, end)

        rows = await db.fetchall(
            f"""
            SELECT
                CAST(date_trunc('{grain}', period_start) AS DATE) AS bucket,
                COALESCE(SUM(cost_usd), 0) AS cost_usd,
                COALESCE(SUM(dbu_quantity), 0) AS dbu_quantity
            FROM {table}
            {where}
            GROUP BY 1
            ORDER BY 1
            """,
            *params,
        )

        items = [
            {
                "bucket": _iso(r["bucket"]),
                "cost_usd": float(r["cost_usd"] or 0),
                "dbu_quantity": float(r["dbu_quantity"] or 0),
            }
            for r in rows
        ]
        return {"items": items, "period": _period_dict(start, end), "granularity": grain}
    except Exception:
        logger.exception("job cost trend soft-fail for %s", job_id)
        return empty


async def fetch_job_uptime_trend(
    db: DatabricksWarehousePool,
    settings: Settings,
    allowed_lz_ids: list[str] | None,
    job_id: str,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    workspace_ids: list[str] | None = None,
    allowed_workspace_ids: list[str] | None = None,
    cloud_provider: str | None = None,
    granularity: str = "day",
) -> dict[str, Any]:
    """Cumulated uptime and idle share of one job, read from the daily table.

    Named ``uptime`` and not ``lifetime`` like its cluster homologue: "lifetime" has
    no meaning for compute destroyed at the end of every run — what is followed here
    is the uptime **summed over the runs** of the day/week/month.
    """
    start, end = _resolve_period(period_start, period_end)
    table = qualified_table(settings, _EFFICIENCY_DAILY)
    grain = _grain(granularity)

    empty = {"items": [], "period": _period_dict(start, end), "granularity": grain}

    try:
        scope, params = _scope_where(
            allowed_lz_ids,
            source_lz_id,
            source_lz_ids,
            workspace_ids,
            has_lz_column=False,
            allowed_workspace_ids=allowed_workspace_ids,
            cloud_provider=cloud_provider,
        )
        scope.append(_JOB_FILTER)
        params.append(job_id)
        where, params = _date_where(scope, params, start, end)

        rows = await db.fetchall(
            f"""
            SELECT
                CAST(date_trunc('{grain}', period_start) AS DATE) AS bucket,
                COALESCE(SUM(uptime_hours), 0) AS uptime_hours,
                -- Weighted by uptime, the same rule gold applies inside the day: a
                -- plain AVG would weigh a 20-minute run like a 20-hour one.
                SUM(idle_pct * uptime_hours)
                    / NULLIF(SUM(CASE WHEN idle_pct IS NOT NULL THEN uptime_hours END), 0)
                    AS idle_pct
            FROM {table}
            {where}
            GROUP BY 1
            ORDER BY 1
            """,
            *params,
        )

        items = [
            {
                "bucket": _iso(r["bucket"]),
                "uptime_hours": float(r["uptime_hours"] or 0),
                # None, not 0: an unmeasured bucket has no idle share, and 0 % would
                # read as a job that ran flat out.
                "idle_pct": _round_pct(r["idle_pct"]),
            }
            for r in rows
        ]
        return {"items": items, "period": _period_dict(start, end), "granularity": grain}
    except Exception:
        logger.exception("job uptime trend soft-fail for %s", job_id)
        return empty
