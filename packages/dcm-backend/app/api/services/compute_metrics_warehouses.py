"""Compute Metrics — SQL warehouse gold tables.

The three list views read the ``*_rolling`` tables, which hold one pre-aggregated
row per warehouse and per window (1/7/30/90 days) anchored on ``as_of_date`` — the
last day actually present in the daily table, not ``today``. They used to read the
``*_daily`` tables through ``QUALIFY ROW_NUMBER() … ORDER BY period_start DESC``,
which only moved the *anchor* to the last day found in the requested range: widening
the period never aggregated it (023 T002). The ``*_daily`` tables are left to the
per-warehouse detail and trend, a rolling row being a single point.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

from ...auth.scope_model import canonical_workspace_sql
from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_table
from .compute_metrics_common import (
    _DEFAULT_PAGE_SIZE,
    _WAREHOUSE_UTILIZATION_ROLLING,
    RollingWindowDays,
    _as_float,
    _bounds_sql,
    _clamp_page,
    _date_where,
    _empty_page,
    _grain,
    _is_table_missing,
    _iso,
    _normalize_prev_cost,
    _pct_delta,
    _period_dict,
    _resolve_period,
    _row_to_dict,
    _scope_where,
    _serverless_void_savings_sql,
    _serverless_warehouse_cte,
    _window_block,
    _window_period,
    _window_where,
)
from .compute_metrics_filters import (
    AppliedFilter,
    column_filter_predicates,
    parse_column_filters,
)

__all__ = [
    "fetch_warehouse_cost_trend",
    "fetch_warehouse_detail",
    "fetch_warehouse_slow_queries",
    "fetch_warehouses_cost",
    "fetch_warehouses_overview",
    "fetch_warehouses_query_performance",
]

logger = logging.getLogger(__name__)

# Series read by the per-warehouse detail and trend only.
_COST = "gold_dbx_compute_warehouse_cost_daily"
_QUERY_PERF = "gold_dbx_compute_warehouse_query_performance_daily"
# Snapshots read by the three list views.
_COST_ROLLING = "gold_dbx_compute_warehouse_cost_rolling"
_QUERY_PERF_ROLLING = "gold_dbx_compute_warehouse_query_performance_rolling"
_RECOMMENDATIONS = "gold_dbx_compute_recommendations"
_SLOW_QUERIES = "warehouse_slow_queries"

_WORKSPACE_DIM = "dim_dbx_workspace"
# Warehouse gold tables migrated to grain without source_lz_id (same as cluster cost).


def _warehouse_sort_clause(sort: str) -> str:
    if sort == "name":
        return "warehouse_name ASC NULLS LAST, warehouse_id ASC"
    return "cost_usd DESC NULLS LAST, warehouse_name ASC NULLS LAST"


# Overview sorts on columns from the cost snapshot, the performance snapshot and the
# workspace dimension, so the allowlist maps the front's keys onto the query aliases.
_OVERVIEW_SORT_COLUMNS: dict[str, str] = {
    "warehouse": "COALESCE(c.warehouse_name, c.warehouse_id)",
    "workspace": "COALESCE(ws.workspace_name, c.workspace_id)",
    "size": "c.warehouse_size",
    # Sorting on the *folded* type and not on the raw gold column: the header sorts what
    # the cell shows, and the two differ for a warehouse whose billing contradicts its
    # declaration. ``NULLS LAST`` in the clause below keeps the unknown ones at the bottom
    # in both directions, so they never crowd out the first page.
    "type": "sw.warehouse_type",
    "cost": "c.cost_usd",
    "queries": "c.query_count",
    "failure": "p.failure_rate_pct",
    "latency": "p.latency_p95_ms",
}


def _overview_sort_clause(sort: str | None, direction: str | None) -> str:
    """ORDER BY for the overview page, built from an allowlisted key.

    The result is interpolated into the SQL, so an unknown key must never reach the
    query as free text: it falls back to cost, which is what the table shows on load.
    ``warehouse_id`` breaks ties — without a unique final key, two warehouses sharing a
    cost can swap between two ``LIMIT/OFFSET`` queries, so one shows up on two pages
    while another is never listed at all.
    """
    column = _OVERVIEW_SORT_COLUMNS.get(sort or "", _OVERVIEW_SORT_COLUMNS["cost"])
    order = "ASC" if direction == "asc" else "DESC"
    return f"{column} {order} NULLS LAST, c.warehouse_id ASC"


# What a free-text overview search looks into. ``ws.workspace_name`` is searchable
# without being selected: the front resolves the label from its own workspace list, but
# a user typing a workspace name still expects its warehouses back.
_OVERVIEW_SEARCH_COLUMNS = (
    "c.warehouse_name",
    "c.warehouse_id",
    "c.warehouse_size",
    "c.workspace_id",
    "ws.workspace_name",
)


def _overview_filters(
    search: str | None,
    column_filters: list[AppliedFilter],
) -> tuple[str, list[Any]]:
    """Extra ``AND`` clauses for the overview page, as SQL plus its parameters.

    These filter the whole scope, not the visible page: they used to run in the browser
    over the 50 rows the server returned, so a warehouse ranked 51st by cost could not
    be found by name at all.

    ``search`` stays here rather than becoming a column filter: it looks into five
    columns at once, including the workspace name, while the ``warehouse`` column filter
    looks into the name and the id of the warehouse only. Folding one into the other
    would silently narrow the search box.

    ``warehouse_size`` and ``min_failure_rate_pct`` *have* moved into the allowlist, as
    the ``size`` and ``failure`` columns — same predicates, transcribed verbatim, and
    emitted here in the same position as before.
    """
    filters: list[str] = []
    params: list[Any] = []
    if search and search.strip():
        pattern = f"%{search.strip().lower()}%"
        matches = " OR ".join(f"LOWER({col}) LIKE ?" for col in _OVERVIEW_SEARCH_COLUMNS)
        filters.append(f"({matches})")
        params.extend([pattern] * len(_OVERVIEW_SEARCH_COLUMNS))
    column_clauses, column_params = column_filter_predicates(column_filters)
    filters.extend(column_clauses)
    params.extend(column_params)
    return ("".join(f" AND {clause}" for clause in filters), params)


def _workspace_dim_cte(table: str) -> str:
    """One row per workspace, keyed the way the gold tables spell workspace ids.

    Same collapsing as the cluster views: ``dim_dbx_workspace`` is a view over an inner
    join, so a second reference row for one workspace would duplicate the warehouse rows
    joined to it. Always LEFT JOINed — a workspace absent from the dimension must keep
    its warehouses listed.
    """
    return (
        f"SELECT {canonical_workspace_sql('workspace_id')} AS workspace_key, "
        "MAX(workspace_name) AS workspace_name "
        f"FROM {table} "
        "WHERE workspace_id IS NOT NULL "
        "GROUP BY 1"
    )


async def fetch_warehouses_overview(
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
    warehouse_size: str | None = None,
    min_failure_rate_pct: float | None = None,
    column_filter: list[str] | None = None,
    sort: str | None = None,
    sort_direction: str | None = None,
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    # Parsed **before** the try block below: everything inside it soft-fails to an empty
    # page, which would turn a rejected filter into a plausible-looking empty table.
    column_filters = parse_column_filters(
        "warehouses-overview",
        column_filter,
        warehouse_size=warehouse_size,
        min_failure_rate_pct=min_failure_rate_pct,
    )
    start, end = _resolve_period(period_start, period_end)
    page, page_size = _clamp_page(page, page_size)
    offset = (page - 1) * page_size
    window = int(window_days)
    cost_t = qualified_table(settings, _COST_ROLLING)
    perf_t = qualified_table(settings, _QUERY_PERF_ROLLING)
    reco_t = qualified_table(settings, _RECOMMENDATIONS)
    # Reads ``is_serverless``, the flag no cost or performance snapshot carries.
    util_t = qualified_table(settings, _WAREHOUSE_UTILIZATION_ROLLING)
    ws_t = qualified_table(settings, _WORKSPACE_DIM)

    empty = {
        "kpis": {
            "total_cost_usd": 0.0,
            "cost_delta_pct": None,
            "active_warehouses": 0,
            "query_count": 0,
            "failed_count": 0,
            "open_recommendations": 0,
        },
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
        # One WHERE per table: each carries its own `as_of_date`, and the guard
        # anchors on the table it filters — a shared `MAX` would drop a whole table's
        # rows the day the two pipelines' snapshots differ by one day.
        cost_where, cost_params = _window_where(
            scope, scope_params, window, latest_snapshot_table=cost_t
        )
        perf_where, perf_params = _window_where(
            list(scope), list(scope_params), window, latest_snapshot_table=perf_t
        )

        filter_sql, filter_params = _overview_filters(search, column_filters)

        cost_row, failed_row, reco_row, items = await asyncio.gather(
            db.fetchone(
                f"""
                SELECT
                    COALESCE(SUM(cost_usd), 0) AS total_cost,
                    COALESCE(SUM(cost_usd_prev_window), 0) AS prev_cost,
                    -- "Active" is billed over the window, not merely listed: the gold
                    -- table keeps a row whose window cost is 0 as long as the previous
                    -- one is not (`WHERE cost_usd <> 0 OR cost_usd_prev_window <> 0`),
                    -- so `COUNT(*)` would count warehouses that stopped being used.
                    SUM(CASE WHEN cost_usd > 0 THEN 1 ELSE 0 END) AS active_warehouses,
                    COALESCE(SUM(query_count), 0) AS query_count,
                    MAX(window_start) AS window_start,
                    MAX(as_of_date) AS as_of_date
                FROM {cost_t}
                {cost_where}
                """,
                *cost_params,
            ),
            db.fetchone(
                f"""
                SELECT COALESCE(SUM(failed_count), 0) AS failed_count
                FROM {perf_t}
                {perf_where}
                """,
                *perf_params,
            ),
            db.fetchone(
                f"""
                WITH sw AS (
                    {_serverless_warehouse_cte(util_t)}
                )
                SELECT COUNT(DISTINCT r.object_id) AS n
                FROM {reco_t} r
                INNER JOIN (
                    SELECT DISTINCT cloud_provider, workspace_id, warehouse_id
                    FROM {cost_t}
                    {cost_where}
                ) active
                    ON r.object_type = 'WAREHOUSE'
                   AND r.cloud_provider = active.cloud_provider
                   AND r.workspace_id = active.workspace_id
                   AND r.object_id = active.warehouse_id
                LEFT JOIN sw
                    ON sw.cloud_provider = r.cloud_provider
                   AND sw.workspace_id = r.workspace_id
                   AND sw.warehouse_id = r.object_id
                -- Same neutralisation as ``compute_metrics_recommendations``, and it has
                -- to be here too: this tile is a *count of the same rows*, so leaving it
                -- alone would have the page announce open recommendations the list refuses
                -- to show. ``UPPER(r.object_type) = 'WAREHOUSE'`` is already true of every
                -- row reaching here through the INNER JOIN.
                --
                -- The tile drops by less than the number of neutralised rows, and that is
                -- the correct arithmetic: it counts *warehouses*, not rows. Measured in dev
                -- on 2026-09-10 over the 30-day window, when the predicate keyed on the
                -- category — 419 warehouses with an open recommendation, of which 350 were
                -- untouched, 38 carried a void RIGHTSIZING row *and* a live RELIABILITY one
                -- (still counted, they do have something open) and 31 lost their only
                -- recommendation. 419 → 388.
                --
                -- Since T001i the predicate keys on the **figure**, and the same
                -- measurement gives **419 → 419**: not one open row is void any more. The
                -- 31 warehouses came back, and they came back carrying **0 $** — a
                -- saturated queue or a spilling query set is a real problem that promises
                -- no saving. That is the arithmetic this tile is supposed to show: a count
                -- of warehouses with something to look at, not of warehouses with money on
                -- the table.
                WHERE r.status = 'OPEN'
                  AND NOT {_serverless_void_savings_sql("r", "sw")}
                """,
                *cost_params,
            ),
            db.fetchall(
                f"""
                WITH c AS (
                    SELECT * FROM {cost_t} {cost_where}
                ),
                p AS (
                    SELECT * FROM {perf_t} {perf_where}
                ),
                ws AS (
                    {_workspace_dim_cte(ws_t)}
                ),
                sw AS (
                    {_serverless_warehouse_cte(util_t)}
                )
                SELECT
                    c.cloud_provider,
                    CAST(NULL AS STRING) AS source_lz_id,
                    c.workspace_id,
                    ws.workspace_name,
                    c.warehouse_id,
                    c.warehouse_name,
                    c.warehouse_size,
                    c.cost_usd,
                    c.query_count,
                    p.failure_rate_pct,
                    p.latency_p95_ms,
                    -- Exposed so the UI can say *why* a warehouse carries no efficiency
                    -- figure and no rightsizing advice, instead of rendering a blank the
                    -- user reads as missing data. Three values, not two: ``true``,
                    -- ``false``, and ``null`` for a warehouse billed over the window but
                    -- absent from the utilization snapshot — the flag is genuinely unknown
                    -- there, and a ``COALESCE`` to ``false`` would claim it is classic.
                    sw.is_serverless,
                    -- The same decision the flag above carries, in the vocabulary the user
                    -- reads: SERVERLESS | PRO | CLASSIC. The flag drives the arithmetic —
                    -- which efficiency figures and which savings are void — while this
                    -- column is what the Type header shows, because "not serverless" is not
                    -- an answer. It is folded so it can never contradict the flag; ``NULL``
                    -- covers both a warehouse absent from the utilization snapshot and one
                    -- whose declaration contradicts its billing. See
                    -- :func:`_serverless_warehouse_cte`.
                    sw.warehouse_type,
                    COUNT(*) OVER() AS _total
                FROM c
                -- window_days IS part of the join key: both tables carry one row per
                -- warehouse and per window, joining without it would multiply every
                -- row by the number of windows.
                LEFT JOIN p
                    ON c.cloud_provider = p.cloud_provider
                   AND c.workspace_id = p.workspace_id
                   AND c.warehouse_id = p.warehouse_id
                   AND p.window_days = c.window_days
                LEFT JOIN ws
                    ON ws.workspace_key = {canonical_workspace_sql("c.workspace_id")}
                -- No ``window_days`` in this join key, unlike ``p`` above: ``sw`` is
                -- already folded to one row per warehouse across every window, precisely
                -- so that a warehouse missing from the 1-day window does not lose its
                -- flag. See :func:`_serverless_warehouse_cte`.
                LEFT JOIN sw
                    ON sw.cloud_provider = c.cloud_provider
                   AND sw.workspace_id = c.workspace_id
                   AND sw.warehouse_id = c.warehouse_id
                WHERE 1 = 1{filter_sql}
                ORDER BY {_overview_sort_clause(sort, sort_direction)}
                LIMIT ? OFFSET ?
                """,
                *cost_params,
                *perf_params,
                *filter_params,
                page_size,
                offset,
            ),
        )

        # The comparison is already aggregated in gold: `cost_usd_prev_window` is the
        # same warehouses over the window before, so no second query is needed — and
        # `_previous_period` could not have produced it here anyway, the rolling table
        # holding a single `as_of_date`.
        total_cost = _as_float((cost_row or {}).get("total_cost")) or 0.0
        prev_cost = _as_float((cost_row or {}).get("prev_cost")) or 0.0
        window_block = _window_block(window, cost_row)
        # Warehouses matching the filters, not those on this page: the window function
        # runs before LIMIT, and `_row_to_dict` drops the `_`-prefixed key.
        total = int(items[0]["_total"]) if items else 0

        return {
            "kpis": {
                "total_cost_usd": total_cost,
                "cost_delta_pct": _pct_delta(total_cost, prev_cost),
                "active_warehouses": int((cost_row or {}).get("active_warehouses") or 0),
                "query_count": int((cost_row or {}).get("query_count") or 0),
                "failed_count": int((failed_row or {}).get("failed_count") or 0),
                "open_recommendations": int((reco_row or {}).get("n") or 0),
            },
            "items": [_row_to_dict(r) for r in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "window": window_block,
            "period": _window_period(window_block, start, end),
        }
    except Exception:
        logger.exception("warehouses overview soft-fail")
        return empty


async def fetch_warehouses_cost(
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
    warehouse_size: str | None = None,
    column_filter: list[str] | None = None,
    sort: str = "cost_desc",
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    # Before the try block: a refused filter must not soft-fail into an empty page.
    # Both legacy parameters fold here — on this view ``search`` looks into the same two
    # columns as the ``warehouse`` filter, unlike on the overview.
    column_filters = parse_column_filters(
        "warehouses-cost",
        column_filter,
        search=search,
        warehouse_size=warehouse_size,
    )
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

        filters, column_params = column_filter_predicates(column_filters)
        row_params.extend(column_params)

        filter_sql = (" AND " + " AND ".join(filters)) if filters else ""

        bounds_row, rows = await asyncio.gather(
            db.fetchone(_bounds_sql(table, where), *params),
            db.fetchall(
                f"""
                WITH latest AS (
                    SELECT * FROM {table} {where}
                )
                SELECT
                    cloud_provider,
                    CAST(NULL AS STRING) AS source_lz_id,
                    workspace_id,
                    warehouse_id,
                    warehouse_name,
                    warehouse_size,
                    dbu_quantity,
                    cost_usd,
                    cost_usd_prev_window,
                    cost_delta_pct,
                    query_count,
                    cost_per_query_usd,
                    top_consumer,
                    window_start,
                    as_of_date,
                    COUNT(*) OVER() AS _total
                FROM latest
                WHERE 1 = 1{filter_sql}
                ORDER BY {_warehouse_sort_clause(sort)}
                LIMIT ? OFFSET ?
                """,
                *row_params,
                page_size,
                offset,
            ),
        )

        total = int(rows[0]["_total"]) if rows else 0
        window_block = _window_block(window, bounds_row)
        cost_items: list[dict[str, Any]] = []
        for row in rows:
            item = _row_to_dict(row)
            _normalize_prev_cost(item)
            cost_items.append(item)
        return {
            "items": cost_items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "window": window_block,
            "period": _window_period(window_block, start, end),
        }
    except Exception:
        logger.exception("warehouses cost soft-fail")
        return empty


async def fetch_warehouses_query_performance(
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
    min_failure_rate_pct: float | None = None,
    has_spill: bool | None = None,
    min_latency_p95_ms: float | None = None,
    column_filter: list[str] | None = None,
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    # Before the try block: a refused filter must not soft-fail into an empty page.
    column_filters = parse_column_filters(
        "warehouses-query-performance",
        column_filter,
        min_failure_rate_pct=min_failure_rate_pct,
        has_spill=has_spill,
        min_latency_p95_ms=min_latency_p95_ms,
    )
    start, end = _resolve_period(period_start, period_end)
    page, page_size = _clamp_page(page, page_size)
    offset = (page - 1) * page_size
    window = int(window_days)
    table = qualified_table(settings, _QUERY_PERF_ROLLING)
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

        # The three legacy parameters are now the ``failure``, ``spill`` and ``p95``
        # columns of the allowlist. Their predicates are unchanged; they are emitted in
        # column order (failure, p95, spill) instead of the former (failure, spill, p95)
        # — the same conjunction, so the same rows.
        filters, column_params = column_filter_predicates(column_filters)
        row_params.extend(column_params)

        filter_sql = (" AND " + " AND ".join(filters)) if filters else ""

        bounds_row, rows = await asyncio.gather(
            db.fetchone(_bounds_sql(table, where), *params),
            db.fetchall(
                f"""
                WITH latest AS (
                    SELECT * FROM {table} {where}
                )
                SELECT
                    cloud_provider,
                    CAST(NULL AS STRING) AS source_lz_id,
                    workspace_id,
                    warehouse_id,
                    warehouse_name,
                    query_count,
                    failed_count,
                    failure_rate_pct,
                    latency_p50_ms,
                    latency_p95_ms,
                    latency_p99_ms,
                    queue_time_avg_ms,
                    queue_time_p95_ms,
                    spill_query_count,
                    cache_hit_pct,
                    bytes_scanned,
                    rows_scanned,
                    top_slow_statement_id,
                    window_start,
                    as_of_date,
                    COUNT(*) OVER() AS _total
                FROM latest
                WHERE 1 = 1{filter_sql}
                ORDER BY failure_rate_pct DESC NULLS LAST, latency_p95_ms DESC NULLS LAST
                LIMIT ? OFFSET ?
                """,
                *row_params,
                page_size,
                offset,
            ),
        )

        total = int(rows[0]["_total"]) if rows else 0
        window_block = _window_block(window, bounds_row)
        return {
            "items": [_row_to_dict(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "window": window_block,
            "period": _window_period(window_block, start, end),
        }
    except Exception:
        logger.exception("warehouses query performance soft-fail")
        return empty


async def fetch_warehouse_detail(
    db: DatabricksWarehousePool,
    settings: Settings,
    allowed_lz_ids: list[str] | None,
    warehouse_id: str,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    workspace_ids: list[str] | None = None,
    allowed_workspace_ids: list[str] | None = None,
    cloud_provider: str | None = None,
) -> dict[str, Any] | None:
    start, end = _resolve_period(period_start, period_end)
    cost_t = qualified_table(settings, _COST)
    perf_t = qualified_table(settings, _QUERY_PERF)

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
        scope.append("warehouse_id = ?")
        scope_params.append(warehouse_id)
        where, params = _date_where(scope, scope_params, start, end)

        cost_row = await db.fetchone(
            f"""
            SELECT *
            FROM {cost_t}
            {where}
            ORDER BY period_start DESC
            LIMIT 1
            """,
            *params,
        )
        perf_row = await db.fetchone(
            f"""
            SELECT *
            FROM {perf_t}
            {where}
            ORDER BY period_start DESC
            LIMIT 1
            """,
            *params,
        )

        if not cost_row and not perf_row:
            return None

        base = cost_row or perf_row or {}
        return {
            "cloud_provider": base.get("cloud_provider"),
            "source_lz_id": None,
            "workspace_id": base.get("workspace_id"),
            "warehouse_id": warehouse_id,
            "cost": _row_to_dict(cost_row) or None,
            "query_performance": _row_to_dict(perf_row) or None,
            "period": _period_dict(start, end),
        }
    except Exception:
        logger.exception("warehouse detail soft-fail for %s", warehouse_id)
        return None


async def fetch_warehouse_cost_trend(
    db: DatabricksWarehousePool,
    settings: Settings,
    allowed_lz_ids: list[str] | None,
    warehouse_id: str,
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
    start, end = _resolve_period(period_start, period_end)
    table = qualified_table(settings, _COST)
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
        scope.append("warehouse_id = ?")
        params.append(warehouse_id)
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
        logger.exception("warehouse cost trend soft-fail for %s", warehouse_id)
        return empty


async def fetch_warehouse_slow_queries(
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
    warehouse_id: str | None = None,
    reason: str | None = None,
    column_filter: list[str] | None = None,
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    # Before the try block: a refused filter must not soft-fail into a disabled response.
    # ``warehouse_id`` does not fold — it is an exact match on the id, while the
    # ``warehouse`` column filter is a substring match on the name or the id.
    column_filters = parse_column_filters(
        "warehouses-slow-queries", column_filter, reason=reason
    )
    start, end = _resolve_period(period_start, period_end)
    page, page_size = _clamp_page(page, page_size)
    offset = (page - 1) * page_size
    table = qualified_table(settings, _SLOW_QUERIES)
    disabled = {
        "enabled": False,
        "items": [],
        "total": 0,
        "page": page,
        "page_size": page_size,
        "period": _period_dict(start, end),
    }

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

        filters: list[str] = []
        if warehouse_id:
            filters.append("warehouse_id = ?")
            params.append(warehouse_id)
        column_clauses, column_params = column_filter_predicates(column_filters)
        filters.extend(column_clauses)
        params.extend(column_params)

        scope.extend(filters)
        scope.append("CAST(start_time AS DATE) >= ?")
        params.append(start)
        scope.append("CAST(start_time AS DATE) <= ?")
        params.append(end)
        where = "WHERE " + " AND ".join(scope)

        rows = await db.fetchall(
            f"""
            SELECT
                cloud_provider,
                CAST(NULL AS STRING) AS source_lz_id,
                workspace_id,
                warehouse_id,
                statement_id,
                warehouse_name,
                executed_by,
                start_time,
                duration_ms,
                status,
                reason,
                error_message,
                query_profile_url,
                COUNT(*) OVER() AS _total
            FROM {table}
            {where}
            ORDER BY start_time DESC NULLS LAST
            LIMIT ? OFFSET ?
            """,
            *params,
            page_size,
            offset,
        )

        total = int(rows[0]["_total"]) if rows else 0
        items = []
        for row in rows:
            item = _row_to_dict(row)
            item["start_time"] = _iso(row.get("start_time"))
            items.append(item)

        return {
            "enabled": True,
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "period": _period_dict(start, end),
        }
    except Exception as exc:
        if _is_table_missing(exc, _SLOW_QUERIES):
            logger.info("slow queries table missing — returning disabled response")
            return disabled
        logger.exception("warehouse slow queries soft-fail")
        return disabled
