"""Compute Metrics — DLT pipeline gold table.

Grain ``dlt_pipeline_id``: one pre-aggregated row per Lakeflow/DLT pipeline and per
window (1/7/30/90 days) anchored on ``as_of_date``, read from
``gold_dbx_compute_pipeline_cost_rolling``. The rollup is billing-direct — it groups
the billing lines carrying ``usage_metadata.dlt_pipeline_id`` (execution *and*
maintenance), so the stable pipeline id is the unit, never the ephemeral PIPELINE
cluster. No ``cluster_count`` column exists on this grain (there is no cluster
resolution step). Modelled on ``compute_metrics_warehouses``.

**Scope: classic DLT compute only** (``_CLASSIC_ONLY``). These endpoints back the
"DLT clusters" page, which is about the DLT *cluster* compute — serverless DLT is
billed without any cluster and is out of scope here, not filtered out by accident.
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
    "fetch_pipeline_cost_trend",
    "fetch_pipeline_detail",
    "fetch_pipeline_uptime_trend",
    "fetch_pipelines_cost",
    "fetch_pipelines_efficiency",
    "fetch_pipelines_overview",
]

logger = logging.getLogger(__name__)

# Snapshots read by the list views and the pipeline detail.
_COST_ROLLING = "gold_dbx_compute_pipeline_cost_rolling"
_EFFICIENCY_ROLLING = "gold_dbx_compute_pipeline_efficiency_rolling"
# Series read by the per-pipeline trends only.
_COST_DAILY = "gold_dbx_compute_pipeline_cost_daily"
_EFFICIENCY_DAILY = "gold_dbx_compute_pipeline_efficiency_daily"

# Per-pipeline endpoints all narrow their scope the same way.
_PIPELINE_FILTER = "dlt_pipeline_id = ?"

# The page is dedicated to the DLT **cluster** compute, not to DLT at large: only the
# pipelines served by a classic PIPELINE / PIPELINE_MAINTENANCE cluster belong here
# (user decision of 2026-09-09). ``compute_kind`` is carried by the two cost tables and
# derived in gold from ``usage_metadata.cluster_id IS NOT NULL`` — verified in dev: the
# 6 375 ephemeral clusters behind DLT billing lines all have ``cluster_source =
# 'PIPELINE'``, none missing from the cluster dimension, so the flag is an exact proxy
# for the cluster type and not a heuristic.
#
# Appended to the **scope** rather than to the row filter so the same predicate reaches
# the rows, the window bounds and the KPI aggregate: leaving the cards on the whole DLT
# population would show $23 588 above a list totalling $1 903.
#
# Never applied to the efficiency tables: they have no ``compute_kind`` column (the
# filter would raise ``UNRESOLVED_COLUMN``) and they are classic-only by construction —
# ``system.compute.node_timeline`` only samples clusters, so a serverless pipeline has
# no row to exclude.
_CLASSIC_ONLY = "compute_kind = 'CLASSIC'"

# The name falls back to the id when no pipeline definition has been ingested yet.
_ROW_COLUMNS = """
    cloud_provider,
    workspace_id,
    dlt_pipeline_id,
    COALESCE(NULLIF(pipeline_name, ''), dlt_pipeline_id) AS pipeline_name,
    compute_kind,
    dbu_quantity,
    cost_usd,
    cost_usd_prev_window,
    cost_delta_pct,
    cost_rank,
    is_top_cost,
    window_start,
    as_of_date
"""

# Columns of ``gold_dbx_compute_pipeline_efficiency_rolling``.
#
# ``cluster_count`` **is** exposed here although ``_ROW_COLUMNS`` above has none: the
# cost rollup is billing-direct (no cluster grain at all), while the efficiency rollup
# goes through the R7 ``cluster_id → dlt_pipeline_id`` mapping and therefore knows how
# many PIPELINE clusters served the pipeline over the window.
#
# No ``is_zombie``/``cluster_name``/``cluster_type``, for the same reason as the job
# grain (024 R8): a PIPELINE cluster is destroyed with its update.
_EFFICIENCY_ROW_COLUMNS = """
    cloud_provider,
    workspace_id,
    dlt_pipeline_id,
    COALESCE(NULLIF(pipeline_name, ''), dlt_pipeline_id) AS pipeline_name,
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
# **qualified** — ``pipeline_name``, ``dlt_pipeline_id``, ``window_start`` and
# ``as_of_date`` all exist on both snapshots, so an unqualified reference becomes
# ambiguous as soon as the LEFT JOIN is in. ``dbu_quantity`` stays in the payload even
# though the page no longer shows a DBU column: other readers of this route use it.
_OVERVIEW_ROW_COLUMNS = """
    p.cloud_provider,
    p.workspace_id,
    p.dlt_pipeline_id,
    COALESCE(NULLIF(p.pipeline_name, ''), p.dlt_pipeline_id) AS pipeline_name,
    p.compute_kind,
    p.dbu_quantity,
    p.cost_usd,
    p.cost_usd_prev_window,
    p.cost_delta_pct,
    p.cost_rank,
    p.is_top_cost,
    p.window_start,
    p.as_of_date,
    e.uptime_hours,
    e.uptime_hours_prev_window,
    e.utilization_status
"""


def _sort_clause(sort: str, prefix: str = "") -> str:
    if sort == "name":
        return f"{prefix}pipeline_name ASC NULLS LAST, {prefix}dlt_pipeline_id ASC"
    return f"{prefix}cost_usd DESC NULLS LAST, {prefix}dlt_pipeline_id ASC"


def _efficiency_sort_clause(sort: str) -> str:
    """``cost_usd`` is not on this table: the default sort is the savings."""
    if sort == "name":
        return "pipeline_name ASC NULLS LAST, dlt_pipeline_id ASC"
    if sort == "uptime":
        return "uptime_hours DESC NULLS LAST, dlt_pipeline_id ASC"
    return "estimated_savings_usd DESC NULLS LAST, dlt_pipeline_id ASC"


def _search_clause(search: str | None, prefix: str = "") -> tuple[str, list[Any]]:
    """Free-text filter on the pipeline name and id, over the whole window.

    ``prefix`` qualifies the two columns for the joined overview query, where both
    names also exist on the efficiency side.
    """
    if not search or not search.strip():
        return "", []
    pattern = f"%{search.strip().lower()}%"
    return (
        f"(LOWER({prefix}pipeline_name) LIKE ? OR LOWER({prefix}dlt_pipeline_id) LIKE ?)",
        [pattern, pattern],
    )


def _billed_only(prefix: str = "") -> str:
    """Restrict the listed population to grains that cost or consumed something.

    The rolling snapshot holds one row per known pipeline, billed over the window or not.
    Measured in dev on 2026-09-09, 30-day window: **3 097 of 6 062 rows cost exactly
    $0.00 and consumed 0 DBU** — almost all of them materialized views (names
    ``MV-<catalog>.<schema>.vw_…``), each owning its own ``dlt_pipeline_id`` and having
    billed a fraction of a cent in an earlier window. Listing them made the footer count
    read like a pipeline inventory and left every metric column on "—".

    DBU is part of the test on purpose: a grain that consumed without being charged
    (credits, promo, a free SKU) did run, and dropping it would hide real compute. The
    ``active_pipelines`` KPI already counted ``cost_usd > 0`` only, so this brings the
    served total in line with the card rather than changing what the card means.
    """
    return f"(COALESCE({prefix}cost_usd, 0) > 0 OR COALESCE({prefix}dbu_quantity, 0) > 0)"


async def fetch_pipelines_cost(
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
            [*scope, _CLASSIC_ONLY], scope_params, window, latest_snapshot_table=table
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
                WITH p AS (
                    SELECT * FROM {table} {where}
                )
                SELECT
                    {_ROW_COLUMNS},
                    COUNT(*) OVER() AS _total
                FROM p
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
        logger.exception("pipelines cost soft-fail")
        return empty


async def fetch_pipelines_overview(
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
        "kpis": {"total_cost_usd": 0.0, "cost_delta_pct": None, "active_pipelines": 0},
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
            [*scope, _CLASSIC_ONLY], scope_params, window, latest_snapshot_table=table
        )
        # The efficiency snapshot gets its own stale-row guard: the two tables are
        # written by two different rollups, so pinning one on the other's MAX
        # ``as_of_date`` would blank the utilization columns the day they diverge.
        eff_where, eff_params = _window_where(
            scope, scope_params, window, latest_snapshot_table=eff_table
        )
        row_params = [*params, *eff_params]

        search_sql, search_params = _search_clause(search, prefix="p.")
        row_params.extend(search_params)
        filter_sql = f" AND {_billed_only(prefix='p.')}"
        if search_sql:
            filter_sql += f" AND {search_sql}"

        kpi_row, rows = await asyncio.gather(
            db.fetchone(
                f"""
                SELECT
                    COALESCE(SUM(cost_usd), 0) AS total_cost,
                    COALESCE(SUM(cost_usd_prev_window), 0) AS prev_cost,
                    SUM(CASE WHEN cost_usd > 0 THEN 1 ELSE 0 END) AS active_pipelines,
                    MAX(window_start) AS window_start,
                    MAX(as_of_date) AS as_of_date
                FROM {table}
                {where}
                """,
                *params,
            ),
            db.fetchall(
                f"""
                WITH p AS (
                    SELECT * FROM {table} {where}
                ),
                e AS (
                    SELECT * FROM {eff_table} {eff_where}
                )
                SELECT
                    {_OVERVIEW_ROW_COLUMNS},
                    COUNT(*) OVER() AS _total
                FROM p
                -- LEFT, and never INNER: a pipeline billed without a single measured
                -- minute — serverless DLT has no cluster to observe — stays listed,
                -- with "—" on the utilization columns (024 SC-005). ``window_days``
                -- belongs to the join key: both tables carry one row per pipeline
                -- and per window.
                LEFT JOIN e
                    ON p.cloud_provider = e.cloud_provider
                   AND p.workspace_id = e.workspace_id
                   AND p.dlt_pipeline_id = e.dlt_pipeline_id
                   AND e.window_days = p.window_days
                WHERE 1 = 1{filter_sql}
                ORDER BY {_sort_clause(sort, prefix="p.")}
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
                "active_pipelines": int((kpi_row or {}).get("active_pipelines") or 0),
            },
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "window": window_block,
            "period": _window_period(window_block, start, end),
        }
    except Exception:
        logger.exception("pipelines overview soft-fail")
        return empty


async def fetch_pipelines_efficiency(
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
    """CPU/memory utilization of each DLT pipeline, grain ``dlt_pipeline_id``.

    **No ``compute_kind`` filter here**, and none is needed: a serverless DLT pipeline
    has no ``node_timeline`` row at all, so this table only ever holds classic compute —
    out of reach of any mapping, not a gap to fill. Measured in dev on 2026-09-09:
    96,1 % of the pipelines running on a classic cluster are covered (174 of 181),
    against 2 784 serverless ones that are not measurable (024 SC-005 / R7).

    Since ``fetch_pipelines_cost`` became classic-only the two populations are of the
    same order (≈ 174 measured against ≈ 178 billed at 30 days); the residual gap is
    the 7 pipelines under $0.55 that no ``node_timeline`` sample covers, plus the grains
    measured just outside the billing window. It is **not** a subset relation: this tab
    is not filtered on cost either.
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
                WITH p AS (
                    SELECT * FROM {table} {where}
                )
                SELECT
                    {_EFFICIENCY_ROW_COLUMNS},
                    COUNT(*) OVER() AS _total
                FROM p
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
        logger.exception("pipelines efficiency soft-fail")
        return empty


async def fetch_pipeline_detail(
    db: DatabricksWarehousePool,
    settings: Settings,
    allowed_lz_ids: list[str] | None,
    dlt_pipeline_id: str,
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
    """Cost and efficiency of one DLT pipeline, or ``None`` when out of scope (→ 404).

    **No governance block** — the key is absent, not ``null`` (024 C2).

    ``efficiency: None`` is the **expected** answer for a serverless pipeline: the
    detail is still served with its cost block, and the UI shows "—" rather than 0.
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
        pipeline_scope = [*scope, _PIPELINE_FILTER]
        pipeline_params = [*scope_params, dlt_pipeline_id]
        # One guard per table: the two rollups are written by two tasks, so their
        # ``MAX(as_of_date)`` can differ by a run.
        # ``_CLASSIC_ONLY`` on the cost side only, and it is not cosmetic here: the
        # rolling grain carries ``compute_kind``, so a pipeline that ran both ways in
        # the window has two rows and the ``ORDER BY cost_usd DESC LIMIT 1`` below
        # would silently return the serverless one.
        cost_where, cost_params = _window_where(
            [*pipeline_scope, _CLASSIC_ONLY],
            pipeline_params,
            window,
            latest_snapshot_table=cost_t,
        )
        eff_where, eff_params = _window_where(
            pipeline_scope, pipeline_params, window, latest_snapshot_table=eff_t
        )

        cost_row, eff_row = await asyncio.gather(
            db.fetchone(
                f"""
                SELECT {_ROW_COLUMNS}
                FROM {cost_t}
                {cost_where}
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

        window_block = _window_block(window, cost_row or eff_row)

        return {
            "cloud_provider": base.get("cloud_provider"),
            "workspace_id": base.get("workspace_id"),
            "dlt_pipeline_id": dlt_pipeline_id,
            "cost": cost or None,
            "efficiency": efficiency or None,
            "window": window_block,
            "period": _window_period(window_block, start, end),
        }
    except Exception:
        logger.exception("pipeline detail soft-fail for %s", dlt_pipeline_id)
        return None


async def fetch_pipeline_cost_trend(
    db: DatabricksWarehousePool,
    settings: Settings,
    allowed_lz_ids: list[str] | None,
    dlt_pipeline_id: str,
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
    """Cost / DBU series of one DLT pipeline (execution **and** maintenance).

    No ``window_days``: a ``*_rolling`` row is a single point per window.
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
        scope.append(_PIPELINE_FILTER)
        params.append(dlt_pipeline_id)
        # Same reason as the detail: the daily grain carries ``compute_kind``, so the
        # ``SUM`` below would add the serverless share back into a classic-only series.
        scope.append(_CLASSIC_ONLY)
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
        logger.exception("pipeline cost trend soft-fail for %s", dlt_pipeline_id)
        return empty


async def fetch_pipeline_uptime_trend(
    db: DatabricksWarehousePool,
    settings: Settings,
    allowed_lz_ids: list[str] | None,
    dlt_pipeline_id: str,
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
    """Cumulated uptime and idle share of one DLT pipeline, from the daily table.

    Empty for a serverless pipeline, which has no ``node_timeline`` row: an empty
    series, never a flat zero line.
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
        scope.append(_PIPELINE_FILTER)
        params.append(dlt_pipeline_id)
        where, params = _date_where(scope, params, start, end)

        rows = await db.fetchall(
            f"""
            SELECT
                CAST(date_trunc('{grain}', period_start) AS DATE) AS bucket,
                COALESCE(SUM(uptime_hours), 0) AS uptime_hours,
                -- Weighted by uptime, the same rule gold applies inside the day.
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
                # None, not 0: an unmeasured bucket has no idle share.
                "idle_pct": _round_pct(r["idle_pct"]),
            }
            for r in rows
        ]
        return {"items": items, "period": _period_dict(start, end), "granularity": grain}
    except Exception:
        logger.exception("pipeline uptime trend soft-fail for %s", dlt_pipeline_id)
        return empty
