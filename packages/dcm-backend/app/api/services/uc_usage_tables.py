"""Overview KPIs and the "by table" view of the UC usage page.

Anchor of :func:`fetch_tables`: ``table_popularity_daily``, i.e. the tables that
have observed usage records during the period (including write-only records).
``table_catalog`` is joined only for
registry metadata — anchoring on it would list the whole catalogue and bury the
usage the page exists to show.

Every distinct count is recomputed over the whole period: summing daily distinct
counts would count a consumer once per day.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ...db.connection import DatabricksWarehousePool
from .uc_usage_column_filters import TABLE_COLUMNS, compile_column_filters, sort_sql
from .uc_usage_common import (
    GOLD_QUERY_PERFORMANCE_DAILY,
    GOLD_TABLE_CATALOG,
    GOLD_TABLE_DAILY,
    GOLD_TABLE_POPULARITY_DAILY,
    LIFECYCLE_AGGREGATES,
    date_conditions,
    deleted_table_conditions,
    guarded,
    integer,
    iso,
    lifecycle_fields,
    number,
    object_filters,
    offset_of,
    page_envelope,
    pct_delta,
    period_dict,
    previous_period,
    ratio_pct,
    search_condition,
    table_lifecycle,
    where_clause,
)
from .uc_usage_finops import fetch_forecast_series, fetch_written_bytes_series
from .uc_usage_governance import count_unused_tables
from .uc_usage_latency import latency_p95_ctes

__all__ = ["TABLE_SORTS", "fetch_overview", "fetch_tables", "fetch_top_consumers"]


_SORT_SQL: dict[str, str] = {
    "popularity": "request_count",
    "cost": "estimated_cost_usd",
    "latency": "latency_p95_ms",
    "failure_rate": "failure_rate_pct",
    "writes": "data_written_bytes",
    "rows_written": "rows_written",
    "consumers": "distinct_consumers",
    "freshness": "freshness_lag_hours",
    "table_name": "table_full_name",
    "read_bytes": "data_read_bytes",
}
TABLE_SORTS: tuple[str, ...] = tuple(_SORT_SQL)


_OVERVIEW_FORECAST_METRICS = ["request_count", "distinct_consumers", "estimated_cost_usd"]

_TOP_CONSUMERS_LIMIT = 5


async def fetch_overview(
    db: DatabricksWarehousePool,
    *,
    start: date,
    end: date,
    catalog: str | None = None,
    schema: str | None = None,
    tables: list[str] | None = None,
    include_deleted: bool = False,
) -> dict[str, Any]:
    object_conditions, object_params = object_filters(catalog, schema, tables)
    # Before aggregation, not after: a KPI must never sum a deleted table it does
    # not count (spec 027, contracts/api-include-deleted.md).
    object_conditions.extend(deleted_table_conditions(db, include_deleted))

    def scoped(period: tuple[date, date]) -> tuple[str, list[Any]]:
        conditions, params = date_conditions(*period)
        conditions.extend(object_conditions)
        params.extend(object_params)
        return where_clause(conditions), params

    where, params = scoped((start, end))
    prev_where, prev_params = scoped(previous_period(start, end))
    popularity = db.table(GOLD_TABLE_POPULARITY_DAILY)

    totals = await guarded(
        db,
        db.fetchone(
            f"""
            SELECT
                COALESCE(SUM(request_count), 0) AS request_count,
                SUM(estimated_cost_usd) AS estimated_cost_usd
            FROM {popularity}
            {where}
            """,
            *params,
        ),
        tables=[GOLD_TABLE_POPULARITY_DAILY, GOLD_TABLE_CATALOG],
    )
    previous = await guarded(
        db,
        db.fetchone(
            f"""
            SELECT
                COALESCE(SUM(request_count), 0) AS request_count,
                SUM(estimated_cost_usd) AS estimated_cost_usd
            FROM {popularity}
            {prev_where}
            """,
            *prev_params,
        ),
        tables=[GOLD_TABLE_POPULARITY_DAILY, GOLD_TABLE_CATALOG],
    )

    reach = await guarded(
        db,
        db.fetchone(
            f"""
            SELECT
                COUNT(DISTINCT table_full_name) AS tracked_tables,
                COUNT(DISTINCT consumer_id) AS distinct_consumers
            FROM {db.table(GOLD_TABLE_DAILY)}
            {where}
            """,
            *params,
        ),
        tables=[GOLD_TABLE_DAILY, GOLD_TABLE_CATALOG],
    )

    performance = await guarded(
        db,
        db.fetchone(
            f"""
            SELECT
                SUM(failed_count) AS failed_count,
                SUM(query_count) AS query_count
            FROM {db.table(GOLD_QUERY_PERFORMANCE_DAILY)}
            {where}
            """,
            *params,
        ),
        tables=[GOLD_QUERY_PERFORMANCE_DAILY, GOLD_TABLE_CATALOG],
    )

    unused_tables = await count_unused_tables(
        db, catalog=catalog, schema=schema, tables=tables, include_deleted=include_deleted
    )
    trends = await fetch_forecast_series(
        db,
        catalog=catalog,
        schema=schema,
        tables=tables,
        metrics=_OVERVIEW_FORECAST_METRICS,
        include_deleted=include_deleted,
    )
    written_bytes_series = await fetch_written_bytes_series(
        db,
        start=start,
        end=end,
        catalog=catalog,
        schema=schema,
        tables=tables,
        include_deleted=include_deleted,
    )

    current = totals or {}
    before = previous or {}
    perf = performance or {}

    return {
        "tracked_tables": integer((reach or {}).get("tracked_tables")),
        "request_count": integer(current.get("request_count")),
        "request_count_delta_pct": pct_delta(
            current.get("request_count"), before.get("request_count")
        ),
        "distinct_consumers": integer((reach or {}).get("distinct_consumers")),
        "estimated_cost_usd": number(current.get("estimated_cost_usd"), decimals=2),
        "estimated_cost_usd_delta_pct": pct_delta(
            current.get("estimated_cost_usd"), before.get("estimated_cost_usd")
        ),
        # Snapshot of the catalogue lifecycle: deliberately period-insensitive.
        "unused_tables": unused_tables,
        "access_failure_rate_pct": ratio_pct(perf.get("failed_count"), perf.get("query_count")),
        "trends": trends,
        "written_bytes_series": written_bytes_series,
        "attention": [],  # Response compatibility; alerts are on Governance.
        "period": period_dict(start, end),
    }


def _tables_ctes(
    db: DatabricksWarehousePool,
    where: str,
    prev_where: str,
    cat_where: str,
    *,
    pop_where: str,
) -> str:
    """CTE chain of ``/tables``.

    ``pop_where`` is ``where`` plus the deleted-table exclusion. Only the anchor
    carries it: the other CTEs are ``LEFT JOIN``-ed on ``pop.table_full_name``, so
    excluding a name once removes it from the page, and repeating the anti-join
    five times would only re-read the catalogue.
    """
    popularity = db.table(GOLD_TABLE_POPULARITY_DAILY)
    return f"""
        WITH pop AS (
            SELECT
                table_full_name,
                MAX(`catalog`) AS catalog,
                MAX(`schema`) AS schema,
                MAX(table_name) AS table_name,
                SUM(request_count) AS request_count,
                SUM(data_read_bytes) AS data_read_bytes,
                SUM(estimated_cost_usd) AS estimated_cost_usd
            FROM {popularity}
            {pop_where}
            GROUP BY table_full_name
        ),
        prev AS (
            SELECT table_full_name, SUM(request_count) AS request_count
            FROM {popularity}
            {prev_where}
            GROUP BY table_full_name
        ),
        cons AS (
            SELECT
                table_full_name,
                COUNT(DISTINCT consumer_id) AS distinct_consumers,
                SUM(data_written_bytes) AS data_written_bytes,
                SUM(rows_written) AS rows_written,
                MAX(last_used_at) AS last_used_at,
                CASE
                    WHEN COUNT(DISTINCT cost_attribution_method) > 1 THEN 'mixed'
                    ELSE MAX(cost_attribution_method)
                END AS cost_attribution_method,
                CASE
                    WHEN COUNT(DISTINCT cost_basis) > 1 THEN 'mixed'
                    ELSE MAX(cost_basis)
                END AS cost_basis,
                MIN(catalog_resolution_status) AS catalog_resolution_status
            FROM {db.table(GOLD_TABLE_DAILY)}
            {where}
            GROUP BY table_full_name
        ),
        perf AS (
            SELECT
                table_full_name,
                SUM(query_count) AS query_count,
                SUM(failed_count) AS failed_count
            FROM {db.table(GOLD_QUERY_PERFORMANCE_DAILY)}
            {where}
            GROUP BY table_full_name
        ),
        cat AS (
            SELECT
                table_full_name,
                MAX(table_type) AS table_type,
                MAX(freshness_lag_hours) AS freshness_lag_hours,
                MAX(freshness_basis) AS freshness_basis,
                MAX(last_write_at) AS last_write_at,{LIFECYCLE_AGGREGATES}
            FROM {db.table(GOLD_TABLE_CATALOG)}
            {cat_where}
            GROUP BY table_full_name
        ),
        {latency_p95_ctes(db.table(GOLD_QUERY_PERFORMANCE_DAILY), where)}
    """


_TABLE_SELECT = """
        SELECT
            pop.table_full_name,
            pop.catalog,
            pop.schema,
            pop.table_name,
            cat.table_type,
            pop.request_count,
            prev.request_count AS request_count_prev,
            cons.distinct_consumers,
            cons.data_written_bytes,
            cons.rows_written,
            pop.data_read_bytes,
            pop.estimated_cost_usd,
            cons.cost_attribution_method,
            cons.cost_basis,
            cons.catalog_resolution_status,
            cons.last_used_at,
            perf.query_count,
            perf.failed_count,
            CASE
                WHEN perf.query_count > 0
                THEN perf.failed_count / perf.query_count * 100
            END AS failure_rate_pct,
            lat.latency_p95_ms,
            cat.freshness_lag_hours,
            cat.freshness_basis,
            cat.last_write_at,
            cat.is_deleted,
            cat.deleted_at,
            cat.lifecycle_state
        FROM pop
        LEFT JOIN prev ON prev.table_full_name = pop.table_full_name
        LEFT JOIN cons ON cons.table_full_name = pop.table_full_name
        LEFT JOIN perf ON perf.table_full_name = pop.table_full_name
        LEFT JOIN cat ON cat.table_full_name = pop.table_full_name
        LEFT JOIN lat ON lat.table_full_name = pop.table_full_name
"""

_SOURCE_TABLES = [
    GOLD_TABLE_POPULARITY_DAILY,
    GOLD_TABLE_DAILY,
    GOLD_QUERY_PERFORMANCE_DAILY,
    GOLD_TABLE_CATALOG,
]


def _table_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "table_full_name": row["table_full_name"],
        "catalog": row["catalog"],
        "schema": row["schema"],
        "table_name": row["table_name"],
        "table_type": row["table_type"],
        "request_count": number(row["request_count"]),
        "request_delta_pct": pct_delta(row["request_count"], row["request_count_prev"]),
        "distinct_consumers": number(row["distinct_consumers"]),
        "data_read_bytes": number(row["data_read_bytes"]),
        "data_written_bytes": number(row.get("data_written_bytes")),
        "rows_written": number(row.get("rows_written")),
        "estimated_cost_usd": number(row["estimated_cost_usd"], decimals=2),
        "cost_attribution_method": row["cost_attribution_method"],
        "cost_basis": row["cost_basis"],
        "catalog_resolution_status": row["catalog_resolution_status"],
        "last_used_at": iso(row["last_used_at"]),
        "query_count": number(row["query_count"]),
        "failed_count": number(row["failed_count"]),
        "failure_rate_pct": (
            None if row["failure_rate_pct"] is None else round(float(row["failure_rate_pct"]), 2)
        ),
        # Interpolated over the summed buckets of the period — never an average
        # of daily P95s nor the worst day's maximum (FR-022).
        "latency_p95_ms": number(row["latency_p95_ms"], decimals=1),
        "freshness_lag_hours": number(row["freshness_lag_hours"], decimals=1),
        "freshness_basis": row["freshness_basis"],
        "last_write_at": iso(row["last_write_at"]),
        **lifecycle_fields(row),
    }


async def fetch_tables(
    db: DatabricksWarehousePool,
    *,
    start: date,
    end: date,
    catalog: str | None = None,
    schema: str | None = None,
    tables: list[str] | None = None,
    search: str | None = None,
    sort: str = "popularity",
    direction: str = "desc",
    column_filter: list[str] | None = None,
    page: int = 1,
    page_size: int = 25,
    include_deleted: bool = False,
) -> dict[str, Any]:
    conditions, params = date_conditions(start, end)
    object_conditions, object_params = object_filters(catalog, schema, tables)
    conditions.extend(object_conditions)
    params.extend(object_params)
    search_conditions, search_params = search_condition(search, columns=["table_full_name"])
    conditions.extend(search_conditions)
    params.extend(search_params)

    where = where_clause(conditions)
    prev_conditions, prev_params = date_conditions(*previous_period(start, end))
    prev_conditions.extend(object_conditions)
    prev_params.extend(object_params)
    prev_conditions.extend(search_conditions)
    prev_params.extend(search_params)
    prev_where = where_clause(prev_conditions)

    # ``table_catalog`` is a snapshot: it carries the scope columns but no
    # ``period_start``, so it takes the same filter minus the dates.
    cat_params = [*object_params, *search_params]
    cat_where = where_clause([*object_conditions, *search_conditions])

    # Excludes deleted tables from the page *and* from its pagination total, since
    # the count runs over the same CTE chain. Contributes no parameter, so the
    # positional order below is unchanged.
    pop_where = where_clause([*conditions, *deleted_table_conditions(db, include_deleted)])

    ctes = _tables_ctes(db, where, prev_where, cat_where, pop_where=pop_where)
    # Parameters follow the order the CTEs appear in: pop, prev, cons, perf, cat,
    # then the latency chain, whose first CTE reuses the dated predicate.
    cte_params = [*params, *prev_params, *params, *params, *cat_params, *params]

    filter_where, filter_params = compile_column_filters(column_filter, TABLE_COLUMNS)
    order_by = sort_sql(sort, direction, _SORT_SQL, "popularity")
    ctes += f", usage_rows AS ({_TABLE_SELECT})"
    total = await guarded(
        db,
        db.fetchscalar(
            f"{ctes} SELECT COUNT(*) FROM usage_rows {filter_where}",
            *cte_params,
            *filter_params,
        ),
        tables=_SOURCE_TABLES,
    )
    rows = await guarded(
        db,
        db.fetchall(
            f"""
            {ctes}
            SELECT * FROM usage_rows {filter_where}
            ORDER BY {order_by}, table_full_name ASC
            LIMIT ? OFFSET ?
            """,
            *cte_params,
            *filter_params,
            page_size,
            offset_of(page, page_size),
        ),
        tables=_SOURCE_TABLES,
    )

    return page_envelope(
        [_table_row(row) for row in rows], integer(total), page, page_size, start, end
    )


async def fetch_top_consumers(
    db: DatabricksWarehousePool,
    table_full_name: str,
    *,
    start: date,
    end: date,
    include_deleted: bool = False,
) -> dict[str, Any]:
    """Top 5 consumers of one table, by attributed cost. Not paginated (FR-004)."""
    conditions, params = date_conditions(start, end)
    conditions.append("table_full_name = ?")
    params.append(table_full_name)
    # A deleted table drills down to nothing unless asked for; the lifecycle fields
    # of the envelope say why the list is empty.
    conditions.extend(deleted_table_conditions(db, include_deleted))
    lifecycle = await table_lifecycle(db, table_full_name)

    rows = await guarded(
        db,
        db.fetchall(
            f"""
            SELECT
                consumer_id,
                MAX(consumer_name) AS consumer_name,
                MAX(consumer_type) AS consumer_type,
                SUM(request_count) AS request_count,
                SUM(estimated_cost_usd) AS estimated_cost_usd,
                MAX(last_used_at) AS last_used_at
            FROM {db.table(GOLD_TABLE_DAILY)}
            {where_clause(conditions)}
            GROUP BY consumer_id
            ORDER BY estimated_cost_usd DESC NULLS LAST, request_count DESC NULLS LAST
            LIMIT ?
            """,
            *params,
            _TOP_CONSUMERS_LIMIT,
        ),
        tables=[GOLD_TABLE_DAILY, GOLD_TABLE_CATALOG],
    )

    return {
        "table_full_name": table_full_name,
        **lifecycle,
        "items": [
            {
                "rank": index,
                "consumer_id": row["consumer_id"],
                "consumer_name": row["consumer_name"],
                # Open vocabulary inherited from the lineage: an unknown value is
                # returned as-is rather than folded into UNKNOWN.
                "consumer_type": row["consumer_type"],
                "request_count": number(row["request_count"]),
                "estimated_cost_usd": number(row["estimated_cost_usd"], decimals=2),
                "last_used_at": iso(row["last_used_at"]),
            }
            for index, row in enumerate(rows, start=1)
        ],
        "period": period_dict(start, end),
    }
