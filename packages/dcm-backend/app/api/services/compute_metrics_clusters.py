"""Compute Metrics — cluster gold tables.

The three list views read the ``*_rolling`` tables, which hold one pre-aggregated
row per cluster and per window (1/7/30/90 days) anchored on ``as_of_date`` — the
last day actually present in the daily table, not ``today``. The ``*_daily``
tables are left to the per-cluster trends, a rolling row being a single point.
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
from .compute_metrics_filters import (
    AppliedFilter,
    column_filter_predicates,
    parse_column_filters,
)

__all__ = [
    "ClusterWindowDays",
    "fetch_cluster_cost_trend",
    "fetch_cluster_detail",
    "fetch_cluster_lifetime_trend",
    "fetch_clusters_cost",
    "fetch_clusters_efficiency",
    "fetch_clusters_governance",
    "fetch_clusters_overview",
]

logger = logging.getLogger(__name__)

# Series read by the per-cluster trends only.
_COST_DAILY = "gold_dbx_compute_cluster_cost_daily"
_EFFICIENCY_DAILY = "gold_dbx_compute_cluster_efficiency_daily"
# Snapshots read by the list views and the cluster detail.
_COST_ROLLING = "gold_dbx_compute_cluster_cost_rolling"
_EFFICIENCY_ROLLING = "gold_dbx_compute_cluster_efficiency_rolling"
_GOVERNANCE = "gold_dbx_compute_cluster_governance"
_RECOMMENDATIONS = "gold_dbx_compute_recommendations"
_WORKSPACE_DIM = "dim_dbx_workspace"

# Per-cluster endpoints all narrow their scope the same way.
_CLUSTER_FILTER = "cluster_id = ?"

# The list views expose ALL_PURPOSE clusters only. A hard predicate, not the optional
# ``cluster_type`` column filter: unset, that filter let JOB and PIPELINE rows leak into
# the cluster pages (the root pollution). JOB and PIPELINE compute have their own grain
# endpoints. Defense in depth above the gold purge (024 T001a) — bare column name, applied
# inside each ``SELECT * FROM <rolling> WHERE …`` CTE.
_ALL_PURPOSE_ONLY = "UPPER(cluster_type) = 'ALL_PURPOSE'"


# The enum moved to `compute_metrics_common` when the warehouse views gained the
# same four windows (023 T002): it describes the pipeline's `ROLLING_WINDOWS`, not
# the cluster pages. Kept as an alias rather than renamed at the call sites — it is
# exported and read by the routes and the tests (P11).
ClusterWindowDays = RollingWindowDays


def _sort_clause(sort: str) -> str:
    if sort == "name":
        return "c.cluster_name ASC NULLS LAST, c.cluster_id ASC"
    if sort == "rank":
        return "c.cost_rank ASC NULLS LAST, c.cost_usd DESC NULLS LAST"
    return "c.cost_usd DESC NULLS LAST, c.cluster_name ASC NULLS LAST"


# Overview sorts on columns coming from three different tables, so the allowlist maps
# the front's sort keys onto the aliases of the overview query, not onto bare columns.
_OVERVIEW_SORT_COLUMNS: dict[str, str] = {
    "cluster": "COALESCE(c.cluster_name, c.cluster_id)",
    "workspace": "COALESCE(ws.workspace_name, c.workspace_id)",
    "cluster_type": "c.cluster_type",
    "cluster_lifetime": "e.uptime_hours",
    "cluster_lifetime_prev": "e.uptime_hours_prev_window",
    "cost": "c.cost_usd",
    "cost_prev": "c.cost_usd_prev_window",
    "utilization": "e.utilization_status",
    "governance": "g.severity",
}


def _overview_sort_clause(sort: str | None, direction: str | None) -> str:
    """ORDER BY for the overview page, built from an allowlisted key.

    The result is interpolated into the SQL, so the key must never reach the query as
    free text: an unknown key falls back to cost, which is what the table shows on load.

    ``NULLS LAST`` in both directions. The client-side sort this replaces ranked a
    missing value as ``-Infinity``, which put un-measured clusters *first* when sorting
    ascending — "the 25 clusters we know least about" is not a useful first page.

    ``cluster_id`` breaks ties, and that is not cosmetic: without a unique final key,
    two rows sharing a cost may swap between two `LIMIT/OFFSET` queries, so the same
    cluster can appear on page 2 and page 3 while another is never shown at all.
    """
    column = _OVERVIEW_SORT_COLUMNS.get(sort or "", _OVERVIEW_SORT_COLUMNS["cost"])
    order = "ASC" if direction == "asc" else "DESC"
    return f"{column} {order} NULLS LAST, c.cluster_id ASC"


# What a free-text overview search looks into. Every column belongs to the joined
# result, so a search matches a workspace name the row does not even display in full.
_OVERVIEW_SEARCH_COLUMNS = (
    "c.cluster_name",
    "c.cluster_id",
    "c.cluster_type",
    "c.owner",
    "ws.workspace_name",
    "c.workspace_id",
)


def _overview_filters(
    search: str | None, column_filters: list[AppliedFilter]
) -> tuple[str, list[Any]]:
    """Extra ``AND`` clauses for the overview page, as SQL plus its parameters.

    Search and the utilization chip filter the *whole* window, not the visible page.
    They used to be applied in the browser over the 50 rows the server returned, so a
    cluster ranked 51st by cost could not be found by name at all.

    ``search`` stays here: it looks into six columns, including the owner and the
    workspace name, where the ``cluster`` column filter looks into the name and the id
    only. The utilization chip *has* moved into the allowlist as the ``utilization``
    column — same predicate, same position.
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


def _billed_only(prefix: str = "c.") -> str:
    """Restrict the listed population to clusters that cost or consumed something.

    Same rule as the jobs and pipelines services, extended here on request (2026-09-09).
    The rolling snapshot holds one row per known all-purpose cluster, billed over the
    window or not; a cluster stopped for the whole window sat in the list with every
    metric column on "—" and inflated the footer count.

    Two consequences worth knowing:

    * The ``active_clusters`` KPI already counted ``cost_usd > 0`` only, so the served
      total now agrees with the card instead of contradicting it.
    * ``cost_rank`` comes precomputed from gold and is **not** renumbered here. Measured on
      dev at window 1: 185 all-purpose rows in the snapshot, 94 of them billed, ranks
      running 1…95 over 93 distinct values — the rollup ranks the billed rows and already
      carries ties and gaps. The filter therefore drops rows that had no rank to lose, and
      the Cost tab still opens on 1, 2, 3…

    DBU is part of the test on purpose: a cluster that consumed without being charged
    (credits, promo, a free SKU) did run, and dropping it would hide real compute.
    """
    return f"(COALESCE({prefix}cost_usd, 0) > 0 OR COALESCE({prefix}dbu_quantity, 0) > 0)"


def _workspace_dim_cte(table: str) -> str:
    """One row per workspace, keyed the way the gold tables spell workspace ids.

    ``dim_dbx_workspace`` is a view over an inner join: a second reference row for
    one workspace would multiply the cluster rows joined to it, so the name is
    collapsed to a single row per key. Always LEFT JOINed — 47 of the 248
    workspaces billed in dev are absent from the dimension, and they must keep
    their clusters listed with a ``null`` name.
    """
    return (
        f"SELECT {canonical_workspace_sql('workspace_id')} AS workspace_key, "
        "MAX(workspace_name) AS workspace_name "
        f"FROM {table} "
        "WHERE workspace_id IS NOT NULL "
        "GROUP BY 1"
    )


async def fetch_clusters_overview(
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
    window_days: int = ClusterWindowDays.DAY,
    search: str | None = None,
    utilization_status: str | None = None,
    column_filter: list[str] | None = None,
    sort: str | None = None,
    sort_direction: str | None = None,
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    # Parsed **before** the try block below: everything inside it soft-fails to an empty
    # page, which would turn a rejected filter into a plausible-looking empty table.
    column_filters = parse_column_filters(
        "clusters-overview", column_filter, utilization_status=utilization_status
    )
    start, end = _resolve_period(period_start, period_end)
    page, page_size = _clamp_page(page, page_size)
    offset = (page - 1) * page_size
    window = int(window_days)
    cost_t = qualified_table(settings, _COST_ROLLING)
    eff_t = qualified_table(settings, _EFFICIENCY_ROLLING)
    gov_t = qualified_table(settings, _GOVERNANCE)
    reco_t = qualified_table(settings, _RECOMMENDATIONS)
    ws_t = qualified_table(settings, _WORKSPACE_DIM)

    empty = {
        "kpis": {
            "total_cost_usd": 0.0,
            "cost_delta_pct": None,
            "active_clusters": 0,
            "zombie_count": 0,
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
        scope.append(_ALL_PURPOSE_ONLY)
        where, params = _window_where(scope, scope_params, window)
        gov_where = ("WHERE " + " AND ".join(scope)) if scope else ""

        filter_sql, filter_params = _overview_filters(search, column_filters)
        filter_sql = f" AND {_billed_only()}{filter_sql}"

        kpi_row, zombie_row, reco_row, item_rows = await asyncio.gather(
            db.fetchone(
                f"""
                SELECT
                    COALESCE(SUM(cost_usd), 0) AS total_cost,
                    COALESCE(SUM(cost_usd_prev_window), 0) AS prev_cost,
                    SUM(CASE WHEN cost_usd > 0 THEN 1 ELSE 0 END) AS active_clusters,
                    MAX(window_start) AS window_start,
                    MAX(as_of_date) AS as_of_date
                FROM {cost_t}
                {where}
                """,
                *params,
            ),
            db.fetchone(
                f"SELECT COUNT(*) AS n FROM {eff_t} {where} AND is_zombie = true",
                *params,
            ),
            db.fetchone(
                f"""
                SELECT COUNT(DISTINCT r.object_id) AS n
                FROM {reco_t} r
                INNER JOIN (
                    SELECT DISTINCT cloud_provider, workspace_id, cluster_id
                    FROM {cost_t}
                    {where}
                ) active
                    ON r.object_type = 'CLUSTER'
                   AND r.cloud_provider = active.cloud_provider
                   AND r.workspace_id = active.workspace_id
                   AND r.object_id = active.cluster_id
                WHERE r.status = 'OPEN'
                """,
                *params,
            ),
            db.fetchall(
                f"""
                WITH c AS (
                    SELECT * FROM {cost_t} {where}
                ),
                e AS (
                    SELECT * FROM {eff_t} {where}
                ),
                g AS (
                    SELECT * FROM {gov_t} {gov_where}
                ),
                ws AS (
                    {_workspace_dim_cte(ws_t)}
                )
                SELECT
                    c.cloud_provider,
                    c.workspace_id,
                    ws.workspace_name,
                    c.cluster_id,
                    c.cluster_name,
                    c.owner,
                    c.cluster_type,
                    c.cost_usd,
                    c.cost_usd_prev_window,
                    c.cost_delta_pct,
                    e.cpu_util_p95_pct,
                    e.idle_pct,
                    e.uptime_hours,
                    e.uptime_hours_prev_window,
                    e.utilization_status,
                    g.severity,
                    COUNT(*) OVER() AS _total
                FROM c
                -- window_days IS part of the join key: both tables carry one row
                -- per cluster and per window, joining without it would multiply
                -- every row by the number of windows.
                LEFT JOIN e
                    ON c.cloud_provider = e.cloud_provider
                   AND c.workspace_id = e.workspace_id
                   AND c.cluster_id = e.cluster_id
                   AND e.window_days = c.window_days
                LEFT JOIN g
                    ON c.cloud_provider = g.cloud_provider
                   AND c.workspace_id = g.workspace_id
                   AND c.cluster_id = g.cluster_id
                LEFT JOIN ws
                    ON ws.workspace_key = {canonical_workspace_sql("c.workspace_id")}
                WHERE 1 = 1{filter_sql}
                ORDER BY {_overview_sort_clause(sort, sort_direction)}
                LIMIT ? OFFSET ?
                """,
                *params,
                *params,
                *scope_params,
                *filter_params,
                page_size,
                offset,
            ),
        )

        total_cost = _as_float((kpi_row or {}).get("total_cost")) or 0.0
        prev_cost = _as_float((kpi_row or {}).get("prev_cost")) or 0.0
        window_block = _window_block(window, kpi_row)

        items: list[dict[str, Any]] = []
        for row in item_rows:
            item = _row_to_dict(row)
            item["uptime_hours_delta_pct"] = _uptime_delta_pct(item)
            _normalize_prev_cost(item)
            items.append(item)

        # Rows matching the filters, not rows on this page: the window function is
        # evaluated before LIMIT, and `_row_to_dict` drops the `_`-prefixed key.
        total = int(item_rows[0]["_total"]) if item_rows else 0

        return {
            "kpis": {
                "total_cost_usd": total_cost,
                "cost_delta_pct": _pct_delta(total_cost, prev_cost),
                "active_clusters": int((kpi_row or {}).get("active_clusters") or 0),
                "zombie_count": int((zombie_row or {}).get("n") or 0),
                "open_recommendations": int((reco_row or {}).get("n") or 0),
            },
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "window": window_block,
            "period": _window_period(window_block, start, end),
        }
    except Exception:
        logger.exception("clusters overview soft-fail")
        return empty


async def fetch_clusters_cost(
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
    search: str | None = None,
    sku_group: str | None = None,
    column_filter: list[str] | None = None,
    sort: str = "cost_desc",
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
    window_days: int = ClusterWindowDays.DAY,
) -> dict[str, Any]:
    # Before the try block: a refused filter must not soft-fail into an empty page.
    # Both legacy parameters fold here — on this view ``search`` looks into the same two
    # columns as the ``cluster`` filter, unlike on the overview.
    column_filters = parse_column_filters(
        "clusters-cost", column_filter, search=search, sku_group=sku_group
    )
    start, end = _resolve_period(period_start, period_end)
    page, page_size = _clamp_page(page, page_size)
    offset = (page - 1) * page_size
    window = int(window_days)
    table = qualified_table(settings, _COST_ROLLING)
    ws_t = qualified_table(settings, _WORKSPACE_DIM)
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
        scope.append(_ALL_PURPOSE_ONLY)
        where, params = _window_where(scope, scope_params, window)
        row_params = list(params)

        filters, column_params = column_filter_predicates(column_filters)
        row_params.extend(column_params)

        filters.insert(0, _billed_only())
        filter_sql = " AND " + " AND ".join(filters)

        bounds_row, rows = await asyncio.gather(
            db.fetchone(_bounds_sql(table, where), *params),
            db.fetchall(
                f"""
                WITH c AS (
                    SELECT * FROM {table} {where}
                ),
                ws AS (
                    {_workspace_dim_cte(ws_t)}
                )
                SELECT
                    c.cloud_provider,
                    c.workspace_id,
                    ws.workspace_name,
                    c.cluster_id,
                    c.cluster_name,
                    c.owner,
                    c.cost_center,
                    c.sku_group,
                    c.cluster_type,
                    c.dbu_quantity,
                    -- Unit cost of a DBU over the window. NULL, never a division
                    -- error, when no DBU was billed.
                    c.cost_usd / NULLIF(c.dbu_quantity, 0) AS dbu_cost,
                    c.cost_usd,
                    c.cost_usd_prev_window,
                    c.cost_delta_pct,
                    c.cost_rank,
                    c.is_top_cost,
                    COUNT(*) OVER() AS _total
                FROM c
                LEFT JOIN ws
                    ON ws.workspace_key = {canonical_workspace_sql("c.workspace_id")}
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
        logger.exception("clusters cost soft-fail")
        return empty


async def fetch_clusters_efficiency(
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
    utilization_status: str | None = None,
    is_zombie: bool | None = None,
    column_filter: list[str] | None = None,
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
    window_days: int = ClusterWindowDays.DAY,
) -> dict[str, Any]:
    # Before the try block: a refused filter must not soft-fail into an empty page.
    # ``is_zombie`` does not fold: it is a tri-state (true / false / unset) on the flag,
    # while the ``status`` column carries ZOMBIE as one value among the statuses.
    column_filters = parse_column_filters(
        "clusters-efficiency", column_filter, utilization_status=utilization_status
    )
    start, end = _resolve_period(period_start, period_end)
    page, page_size = _clamp_page(page, page_size)
    offset = (page - 1) * page_size
    window = int(window_days)
    table = qualified_table(settings, _EFFICIENCY_ROLLING)
    ws_t = qualified_table(settings, _WORKSPACE_DIM)
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
        scope.append(_ALL_PURPOSE_ONLY)
        where, params = _window_where(scope, scope_params, window)
        row_params = list(params)

        # The ZOMBIE special case moved into the allowlist as an override on the
        # ``status`` column: on this table the value is a flag, not a status.
        filters, column_params = column_filter_predicates(column_filters)
        row_params.extend(column_params)
        if is_zombie is not None:
            filters.append("e.is_zombie = ?")
            row_params.append(is_zombie)

        filter_sql = (" AND " + " AND ".join(filters)) if filters else ""

        bounds_row, rows = await asyncio.gather(
            db.fetchone(_bounds_sql(table, where), *params),
            db.fetchall(
                f"""
                WITH e AS (
                    SELECT * FROM {table} {where}
                ),
                ws AS (
                    {_workspace_dim_cte(ws_t)}
                )
                SELECT
                    e.cloud_provider,
                    e.workspace_id,
                    ws.workspace_name,
                    e.cluster_id,
                    e.cluster_name,
                    e.cluster_type,
                    e.driver_node_type,
                    e.worker_node_type,
                    e.autoscale_enabled,
                    e.autoscale_min_workers,
                    e.autoscale_max_workers,
                    e.configured_worker_count,
                    e.cpu_util_avg_pct,
                    e.cpu_util_p95_pct,
                    e.mem_util_avg_pct,
                    e.mem_util_p95_pct,
                    e.cpu_wait_avg_pct,
                    e.idle_pct,
                    e.idle_pct_prev_window,
                    e.uptime_hours,
                    e.uptime_hours_prev_window,
                    e.worker_count_avg,
                    e.worker_count_max,
                    e.autoscale_oscillation,
                    e.is_zombie,
                    e.utilization_status,
                    e.recommended_node_type,
                    e.rightsizing_reco,
                    e.estimated_savings_usd,
                    COUNT(*) OVER() AS _total
                FROM e
                LEFT JOIN ws
                    ON ws.workspace_key = {canonical_workspace_sql("e.workspace_id")}
                WHERE 1 = 1{filter_sql}
                ORDER BY e.estimated_savings_usd DESC NULLS LAST, e.cluster_id ASC
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
        logger.exception("clusters efficiency soft-fail")
        return empty


async def fetch_clusters_governance(
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
    severity: str | None = None,
    missing_tags: bool | None = None,
    dbr_obsolete: bool | None = None,
    column_filter: list[str] | None = None,
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    # Before the try block: a refused filter must not soft-fail into an empty page.
    # ``missing_tags`` spans both tag columns at once and ``dbr_obsolete`` reads
    # ``dbr_is_lts_current``, which no column displays — neither has a column twin.
    column_filters = parse_column_filters(
        "clusters-governance", column_filter, severity=severity
    )
    start, end = _resolve_period(period_start, period_end)
    page, page_size = _clamp_page(page, page_size)
    offset = (page - 1) * page_size
    table = qualified_table(settings, _GOVERNANCE)
    empty = _empty_page(page, page_size, start, end)

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
        scope.append(_ALL_PURPOSE_ONLY)

        filters, column_params = column_filter_predicates(column_filters)
        params.extend(column_params)
        if missing_tags is True:
            filters.append("(has_owner_tag = false OR has_cost_center_tag = false)")
        if dbr_obsolete is True:
            filters.append("dbr_is_lts_current = false")

        where = ("WHERE " + " AND ".join(scope + filters)) if (scope or filters) else ""

        rows = await db.fetchall(
            f"""
            SELECT
                cloud_provider,
                workspace_id,
                cluster_id,
                cluster_name,
                cluster_type,
                has_owner_tag,
                has_cost_center_tag,
                dbr_version,
                dbr_is_lts_current,
                node_oversized,
                is_single_node,
                recommended_action,
                severity,
                _generated_at,
                COUNT(*) OVER() AS _total
            FROM {table}
            {where}
            ORDER BY
                CASE severity WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
                cluster_name ASC NULLS LAST
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
            if "_generated_at" in row:
                item["generated_at"] = _iso(row["_generated_at"])
            items.append(item)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "period": _period_dict(start, end),
        }
    except Exception:
        logger.exception("clusters governance soft-fail")
        return empty


async def fetch_cluster_detail(
    db: DatabricksWarehousePool,
    settings: Settings,
    allowed_lz_ids: list[str] | None,
    cluster_id: str,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    workspace_ids: list[str] | None = None,
    allowed_workspace_ids: list[str] | None = None,
    cloud_provider: str | None = None,
    window_days: int = ClusterWindowDays.DAY,
) -> dict[str, Any] | None:
    start, end = _resolve_period(period_start, period_end)
    window = int(window_days)
    cost_t = qualified_table(settings, _COST_ROLLING)
    eff_t = qualified_table(settings, _EFFICIENCY_ROLLING)
    gov_t = qualified_table(settings, _GOVERNANCE)

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
        gov_scope = [*scope, _CLUSTER_FILTER]
        gov_params = [*scope_params, cluster_id]
        gov_where = "WHERE " + " AND ".join(gov_scope)
        where, params = _window_where(gov_scope, gov_params, window)

        cost_row, eff_row, gov_row = await asyncio.gather(
            db.fetchone(
                f"""
                SELECT
                    *,
                    cost_usd / NULLIF(dbu_quantity, 0) AS dbu_cost
                FROM {cost_t}
                {where}
                ORDER BY cost_usd DESC NULLS LAST
                LIMIT 1
                """,
                *params,
            ),
            db.fetchone(
                f"""
                SELECT *
                FROM {eff_t}
                {where}
                ORDER BY uptime_hours DESC NULLS LAST
                LIMIT 1
                """,
                *params,
            ),
            db.fetchone(
                f"SELECT * FROM {gov_t} {gov_where} LIMIT 1",
                *gov_params,
            ),
        )

        if not cost_row and not eff_row and not gov_row:
            return None

        base = cost_row or eff_row or gov_row or {}
        gov_item = _row_to_dict(gov_row)
        if gov_row and "_generated_at" in gov_row:
            gov_item["generated_at"] = _iso(gov_row["_generated_at"])

        efficiency = _row_to_dict(eff_row)
        if efficiency:
            efficiency["uptime_hours_delta_pct"] = _uptime_delta_pct(efficiency)
            efficiency["idle_pct_delta_pts"] = _idle_delta_pts(efficiency)

        cost = _row_to_dict(cost_row)
        if cost:
            _normalize_prev_cost(cost)

        # Both rolling rows carry the same bounds for a given window; cost is the
        # wider population (a cluster off over the whole window has no efficiency
        # row at all).
        window_block = _window_block(window, cost_row or eff_row)

        return {
            "cloud_provider": base.get("cloud_provider"),
            "workspace_id": base.get("workspace_id"),
            "cluster_id": cluster_id,
            "cost": cost or None,
            "efficiency": efficiency or None,
            "governance": gov_item or None,
            "window": window_block,
            "period": _window_period(window_block, start, end),
        }
    except Exception:
        logger.exception("cluster detail soft-fail for %s", cluster_id)
        return None


async def fetch_cluster_cost_trend(
    db: DatabricksWarehousePool,
    settings: Settings,
    allowed_lz_ids: list[str] | None,
    cluster_id: str,
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
        scope.append(_CLUSTER_FILTER)
        params.append(cluster_id)
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
        logger.exception("cluster cost trend soft-fail for %s", cluster_id)
        return empty


async def fetch_cluster_lifetime_trend(
    db: DatabricksWarehousePool,
    settings: Settings,
    allowed_lz_ids: list[str] | None,
    cluster_id: str,
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
    """Uptime and idle series of one cluster, read from the daily table (R6).

    A ``*_rolling`` row is a single point per window: it cannot feed a series.
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
        scope.append(_CLUSTER_FILTER)
        params.append(cluster_id)
        where, params = _date_where(scope, params, start, end)

        rows = await db.fetchall(
            f"""
            SELECT
                CAST(date_trunc('{grain}', period_start) AS DATE) AS bucket,
                COALESCE(SUM(uptime_hours), 0) AS uptime_hours,
                -- Weighted by uptime: a plain AVG would weigh a 20-minute day
                -- like a 20-hour one.
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
                # None, not 0: an unmeasured bucket has no idle share, and 0 %
                # would read as a fully busy cluster.
                "idle_pct": _round_pct(r["idle_pct"]),
            }
            for r in rows
        ]
        return {"items": items, "period": _period_dict(start, end), "granularity": grain}
    except Exception:
        logger.exception("cluster lifetime trend soft-fail for %s", cluster_id)
        return empty
