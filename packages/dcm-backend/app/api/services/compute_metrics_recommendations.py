"""Compute Metrics — recommendations gold table.

One rule of this module is not in the gold table: on a **serverless** SQL warehouse, a
rightsizing or auto-stop **figure** is money that cannot be saved, because it is priced by
reclaiming idle uptime and serverless does not bill idle capacity. Both the list and the
KPI aggregates neutralise the row that carries such a figure — see
:func:`_serverless_void_savings_sql` for the measurement, for why the condition is the
figure and not the category, and for the three-valued-logic trap the predicate avoids.

Why here and not only in gold: the builder's own merge can never rewrite a ``RESOLVED``
row (``_existing_state_cte`` reads only ``OPEN``/``ACK``), and the list route can be asked
for ``status = 'RESOLVED'``. **93 359,94 $** over **487** already-written rows are
therefore this module's to answer for, and no pipeline run will take them back.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_table
from .compute_metrics_common import (
    _DEFAULT_PAGE_SIZE,
    _SERVERLESS_INAPPLICABLE_CATEGORIES,
    _WAREHOUSE_UTILIZATION_ROLLING,
    _clamp_page,
    _empty_page,
    _period_dict,
    _resolve_period,
    _row_to_dict,
    _scope_where,
    _serverless_void_savings_sql,
    _serverless_warehouse_cte,
)
from .compute_metrics_filters import column_filter_predicates, parse_column_filters

__all__ = ["fetch_recommendations", "fetch_recommendations_summary"]

logger = logging.getLogger(__name__)

_RECOMMENDATIONS = "gold_dbx_compute_recommendations"
_CLUSTER_COST_DAILY = "gold_dbx_compute_cluster_cost_daily"
_WAREHOUSE_COST_DAILY = "gold_dbx_compute_warehouse_cost_daily"

#: Reason code served next to a neutralised figure, so the UI can say *why* rather than
#: show a blank. A code and not a sentence: the wording belongs to the frontend, the fact
#: belongs here.
_NOT_APPLICABLE_REASON = "SERVERLESS_WAREHOUSE"

#: ``r`` is the scoped recommendations CTE, ``sw`` the serverless flag joined onto it.
_VOID_SAVINGS = _serverless_void_savings_sql("r", "sw")

_SORT_SQL: dict[str, str] = {
    "severity": "CASE severity WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END",
    "severity_asc": "CASE severity WHEN 'LOW' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END",
    "savings": "estimated_savings_usd",
    "actual_cost": "actual_cost_usd",
    "since": "first_seen_date",
    "object": "LOWER(COALESCE(object_name, object_id))",
    "status": "status",
    "category": "category",
}


def _not_applicable_block(count: int, savings_usd: float) -> dict[str, Any]:
    """What the neutralisation withheld, published rather than silently dropped.

    The list route removes those rows and the KPIs stop counting their dollars; without
    this block the difference with the gold table would be invisible, and an operator
    reconciling the page against ``gold_dbx_compute_recommendations`` would find rows and
    dollars unaccounted for. A suppression nobody can see is indistinguishable from a bug,
    so the number ships with the reason.

    ``count`` and ``savings_usd`` are **0 on the open KPIs in dev since T001i**, and that
    is the honest answer rather than a broken one: nothing open is being withheld any more,
    because the false figures were removed at the source. The block stays because it is
    what makes the day one comes back readable — and because the resolved rows it also
    covers (**487 rows / 93 359,94 $**) are still withheld.
    """
    return {
        "count": count,
        "savings_usd": savings_usd,
        "reason": _NOT_APPLICABLE_REASON,
        "categories": list(_SERVERLESS_INAPPLICABLE_CATEGORIES),
    }


def _recommendations_order_by(sort: str | None, order: str | None) -> str:
    sort_key = (sort or "severity").strip().lower()
    direction = "ASC" if (order or "desc").strip().lower() == "asc" else "DESC"
    nulls = "NULLS FIRST" if direction == "ASC" else "NULLS LAST"

    if sort_key == "severity":
        expr = _SORT_SQL["severity_asc" if direction == "ASC" else "severity"]
        tie = "ASC" if direction == "ASC" else "DESC"
        return (
            f"{expr} ASC, estimated_savings_usd {tie} NULLS LAST, "
            f"last_seen_date {tie}"
        )

    col = _SORT_SQL.get(sort_key)
    if not col:
        return (
            "CASE severity WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END ASC, "
            "estimated_savings_usd DESC NULLS LAST, last_seen_date DESC"
        )
    return f"{col} {direction} {nulls}, last_seen_date DESC"


async def fetch_recommendations(
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
    object_type: str | None = None,
    category: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    search: str | None = None,
    column_filter: list[str] | None = None,
    sort: str | None = None,
    order: str | None = None,
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    # Before the try block: a refused filter must not soft-fail into an empty page.
    # ``object_type`` and ``search`` do not fold — the first filters a column the table
    # does not display, the second also looks into the title.
    column_filters = parse_column_filters(
        "recommendations",
        column_filter,
        category=category,
        severity=severity,
        status=status,
    )
    # The OPEN-vs-period rule below reads the status whichever way it was asked for:
    # a status set through the column filter must bound the dates the same way.
    effective_status = next(
        (item.value for item in column_filters if item.spec.key == "status"), status
    )
    start, end = _resolve_period(period_start, period_end)
    page, page_size = _clamp_page(page, page_size)
    offset = (page - 1) * page_size
    table = qualified_table(settings, _RECOMMENDATIONS)
    # Safe to join unconditionally: in ``job_dcm_gold_dbx_compute.yml`` the
    # ``gold_recommendations`` task ``depends_on`` ``gold_warehouse_utilization_rolling``,
    # so the recommendations table cannot exist without this one having been written
    # first. "Utilization missing while recommendations present" is not a reachable state,
    # which is why there is no degraded path here.
    util_t = qualified_table(settings, _WAREHOUSE_UTILIZATION_ROLLING)
    empty = _empty_page(page, page_size, start, end)

    try:
        scope, params = _scope_where(
            allowed_lz_ids,
            source_lz_id,
            source_lz_ids,
            workspace_ids,
            # gold_dbx_compute_recommendations has workspace_id but no source_lz_id
            has_lz_column=False,
            allowed_workspace_ids=allowed_workspace_ids,
            cloud_provider=cloud_provider,
        )

        filters: list[str] = []
        if object_type:
            filters.append("UPPER(object_type) = ?")
            params.append(object_type.strip().upper())
        column_clauses, column_params = column_filter_predicates(column_filters)
        filters.extend(column_clauses)
        params.extend(column_params)
        if search:
            filters.append(
                "(LOWER(object_name) LIKE ? OR LOWER(object_id) LIKE ? OR LOWER(title) LIKE ?)"
            )
            pattern = f"%{search.strip().lower()}%"
            params.extend([pattern, pattern, pattern])

        # OPEN recommendations stay visible regardless of header period (aligned with
        # summary KPI + warehouse/cluster overview counts). Resolved/dismissed rows
        # are scoped to last_seen_date within the selected period.
        if effective_status and effective_status.strip().upper() != "OPEN":
            filters.append("last_seen_date >= ?")
            params.append(start)
            filters.append("last_seen_date <= ?")
            params.append(end)
        elif effective_status and effective_status.strip().upper() == "OPEN":
            pass
        else:
            filters.append(
                "(UPPER(status) = 'OPEN' OR (last_seen_date >= ? AND last_seen_date <= ?))"
            )
            params.extend([start, end])

        where = ("WHERE " + " AND ".join(scope + filters)) if (scope or filters) else ""
        order_by = _recommendations_order_by(sort, order)
        cluster_cost = qualified_table(settings, _CLUSTER_COST_DAILY)
        warehouse_cost = qualified_table(settings, _WAREHOUSE_COST_DAILY)

        # Period-scoped actual spend per object (feedback #3/#4). Filter/paginate
        # recommendations first, then left-join aggregated cost.
        rows = await db.fetchall(
            f"""
            WITH sw AS (
                {_serverless_warehouse_cte(util_t)}
            ),
            r AS (
                SELECT * FROM {table} {where}
            )
            SELECT
                base.recommendation_id,
                base.cloud_provider,
                base.workspace_id,
                base.object_type,
                base.object_id,
                base.object_name,
                base.category,
                base.mode,
                base.title,
                base.detail,
                base.recommended_action,
                base.estimated_savings_usd,
                COALESCE(c.actual_cost_usd, w.actual_cost_usd) AS actual_cost_usd,
                base.severity,
                base.personas,
                base.status,
                base.first_seen_date,
                base.last_seen_date,
                base.is_serverless,
                base._total
            FROM (
                -- The neutralisation and the ``_total`` live at this level, not outside:
                -- both have to happen before ``LIMIT``, or a withheld row would occupy a
                -- slot on the page and the count would advertise rows the page cannot
                -- show. The cost joins below are the opposite case — they only decorate
                -- the rows this level already selected.
                SELECT
                    r.recommendation_id,
                    r.cloud_provider,
                    r.workspace_id,
                    r.object_type,
                    r.object_id,
                    r.object_name,
                    r.category,
                    r.mode,
                    r.title,
                    r.detail,
                    r.recommended_action,
                    r.estimated_savings_usd,
                    r.severity,
                    r.personas,
                    r.status,
                    r.first_seen_date,
                    r.last_seen_date,
                    -- Served, and ``NULL`` for every non-warehouse row: that is the honest
                    -- value, since the flag is a property of warehouses only. It is what
                    -- lets the UI explain a *surviving* serverless row — the 337 OPEN
                    -- ``RELIABILITY`` ones — instead of leaving it looking unfiltered.
                    sw.is_serverless,
                    COUNT(*) OVER() AS _total
                FROM r
                -- ``object_type`` is part of the join, not only of the predicate: warehouse
                -- ids and cluster ids are different namespaces, but nothing in either table
                -- enforces that, and a coincidental match would pin a warehouse's flag onto
                -- a cluster's recommendation.
                LEFT JOIN sw
                    ON UPPER(r.object_type) = 'WAREHOUSE'
                   AND sw.cloud_provider = r.cloud_provider
                   AND sw.workspace_id = r.workspace_id
                   AND sw.warehouse_id = r.object_id
                -- The withheld rows are counted by ``fetch_recommendations_summary``, which
                -- is where a KPI belongs; getting the number here too would cost a second
                -- scan of the list route for a figure the summary already publishes.
                -- ``_total`` is computed after this ``WHERE``, so pagination stays
                -- consistent with what the page shows.
                WHERE NOT {_VOID_SAVINGS}
                ORDER BY {order_by}
                LIMIT ? OFFSET ?
            ) base
            LEFT JOIN (
                SELECT
                    cloud_provider,
                    workspace_id,
                    cluster_id AS object_id,
                    COALESCE(SUM(cost_usd), 0) AS actual_cost_usd
                FROM {cluster_cost}
                WHERE period_start >= ? AND period_start <= ?
                GROUP BY cloud_provider, workspace_id, cluster_id
            ) c
              ON UPPER(base.object_type) = 'CLUSTER'
             AND base.cloud_provider = c.cloud_provider
             AND base.workspace_id = c.workspace_id
             AND base.object_id = c.object_id
            LEFT JOIN (
                SELECT
                    cloud_provider,
                    workspace_id,
                    warehouse_id AS object_id,
                    COALESCE(SUM(cost_usd), 0) AS actual_cost_usd
                FROM {warehouse_cost}
                WHERE period_start >= ? AND period_start <= ?
                GROUP BY cloud_provider, workspace_id, warehouse_id
            ) w
              ON UPPER(base.object_type) = 'WAREHOUSE'
             AND base.cloud_provider = w.cloud_provider
             AND base.workspace_id = w.workspace_id
             AND base.object_id = w.object_id
            """,
            *params,
            page_size,
            offset,
            start,
            end,
            start,
            end,
        )

        total = int(rows[0]["_total"]) if rows else 0
        return {
            "items": [_row_to_dict(r) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "period": _period_dict(start, end),
        }
    except Exception:
        logger.exception("recommendations list soft-fail")
        return empty


async def fetch_recommendations_summary(
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
) -> dict[str, Any]:
    start, end = _resolve_period(period_start, period_end)
    table = qualified_table(settings, _RECOMMENDATIONS)
    util_t = qualified_table(settings, _WAREHOUSE_UTILIZATION_ROLLING)
    resolved_30d_start = end - timedelta(days=29)

    empty = {
        "open_count": 0,
        "open_savings_usd": 0.0,
        "period_actual_cost_usd": 0.0,
        "resolved_30d_count": 0,
        "high_severity_open_count": 0,
        "not_applicable": _not_applicable_block(0, 0.0),
        "period": _period_dict(start, end),
    }

    try:
        scope, params = _scope_where(
            allowed_lz_ids,
            source_lz_id,
            source_lz_ids,
            workspace_ids,
            # gold_dbx_compute_recommendations has workspace_id but no source_lz_id
            has_lz_column=False,
            allowed_workspace_ids=allowed_workspace_ids,
            cloud_provider=cloud_provider,
        )
        where = ("WHERE " + " AND ".join(scope)) if scope else ""

        open_where = f"{where} AND status = 'OPEN'" if where else "WHERE status = 'OPEN'"
        open_params = list(params)

        resolved_where = (
            f"{where} AND status = 'RESOLVED' AND last_seen_date >= ? AND last_seen_date <= ?"
            if where
            else "WHERE status = 'RESOLVED' AND last_seen_date >= ? AND last_seen_date <= ?"
        )
        resolved_params = list(params) + [resolved_30d_start, end]

        # Both sides of the neutralisation in one scan and from the same rows: what the
        # page may promise, and what was withheld from it. A second query would let the
        # two disagree the day gold is rebuilt between them.
        open_row = await db.fetchone(
            f"""
            WITH sw AS (
                {_serverless_warehouse_cte(util_t)}
            ),
            r AS (
                SELECT * FROM {table} {open_where}
            )
            SELECT
                COALESCE(SUM(CASE WHEN NOT {_VOID_SAVINGS} THEN 1 ELSE 0 END), 0)
                    AS open_count,
                COALESCE(
                    SUM(CASE WHEN NOT {_VOID_SAVINGS} THEN r.estimated_savings_usd END), 0
                ) AS open_savings_usd,
                COALESCE(
                    SUM(
                        CASE
                            WHEN NOT {_VOID_SAVINGS} AND UPPER(r.severity) = 'HIGH'
                            THEN 1 ELSE 0
                        END
                    ),
                    0
                ) AS high_severity_open_count,
                COALESCE(SUM(CASE WHEN {_VOID_SAVINGS} THEN 1 ELSE 0 END), 0)
                    AS not_applicable_count,
                COALESCE(
                    SUM(CASE WHEN {_VOID_SAVINGS} THEN r.estimated_savings_usd END), 0
                ) AS not_applicable_savings_usd
            FROM r
            LEFT JOIN sw
                ON UPPER(r.object_type) = 'WAREHOUSE'
               AND sw.cloud_provider = r.cloud_provider
               AND sw.workspace_id = r.workspace_id
               AND sw.warehouse_id = r.object_id
            """,
            *open_params,
        )
        resolved_row = await db.fetchone(
            f"""
            SELECT COUNT(*) AS resolved_30d_count
            FROM {table}
            {resolved_where}
            """,
            *resolved_params,
        )

        cluster_cost = qualified_table(settings, _CLUSTER_COST_DAILY)
        warehouse_cost = qualified_table(settings, _WAREHOUSE_COST_DAILY)
        # Same workspace/cloud scope as recommendations, but on cost daily tables.
        cost_scope, cost_params = _scope_where(
            allowed_lz_ids,
            source_lz_id,
            source_lz_ids,
            workspace_ids,
            has_lz_column=False,
            allowed_workspace_ids=allowed_workspace_ids,
            cloud_provider=cloud_provider,
        )
        cost_filters = list(cost_scope) + ["period_start >= ?", "period_start <= ?"]
        cost_args = list(cost_params) + [start, end]
        cost_where = "WHERE " + " AND ".join(cost_filters)
        actual_row = await db.fetchone(
            f"""
            SELECT COALESCE(SUM(cost_usd), 0) AS period_actual_cost_usd
            FROM (
                SELECT cost_usd FROM {cluster_cost} {cost_where}
                UNION ALL
                SELECT cost_usd FROM {warehouse_cost} {cost_where}
            ) spend
            """,
            *cost_args,
            *cost_args,
        )

        return {
            "open_count": int((open_row or {}).get("open_count") or 0),
            "open_savings_usd": float((open_row or {}).get("open_savings_usd") or 0),
            "period_actual_cost_usd": float(
                (actual_row or {}).get("period_actual_cost_usd") or 0
            ),
            "resolved_30d_count": int((resolved_row or {}).get("resolved_30d_count") or 0),
            "high_severity_open_count": int(
                (open_row or {}).get("high_severity_open_count") or 0
            ),
            "not_applicable": _not_applicable_block(
                int((open_row or {}).get("not_applicable_count") or 0),
                float((open_row or {}).get("not_applicable_savings_usd") or 0),
            ),
            "period": _period_dict(start, end),
        }
    except Exception:
        logger.exception("recommendations summary soft-fail")
        return empty
