"""The "by consumer" view of the UC usage page.

Everything is aggregated from ``table_daily``, the consumer × table × day fact.
``consumer_daily`` is a pre-aggregate that has already collapsed the table
dimension, so it can honour neither the catalogue/table filter nor the two
recomputations the spec requires:

* ``rank`` is recomputed on ``SUM(estimated_cost_usd)`` over the period —
  ``consumer_rank`` is a daily rank, not partitioned the same way (FR-005).
* ``distinct_tables`` is a ``COUNT(DISTINCT table_full_name)`` over the period —
  summing ``distinct_data_products`` would count a table once per day.

With a table filter, a consumer appears when it read at least one selected table
(intersection) and its figures describe that selection only.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ...db.connection import DatabricksWarehousePool
from .uc_usage_column_filters import CONSUMER_COLUMNS, compile_column_filters, sort_sql
from .uc_usage_common import (
    GOLD_TABLE_DAILY,
    date_conditions,
    guarded,
    integer,
    iso,
    number,
    object_filters,
    offset_of,
    page_envelope,
    search_condition,
    where_clause,
)

__all__ = ["CONSUMER_SORTS", "fetch_consumers"]

_SORT_SQL: dict[str, str] = {
    "cost": "estimated_cost_usd",
    "requests": "request_count",
    "distinct_tables": "distinct_tables",
    "writes": "data_written_bytes",
    "rows_written": "rows_written",
    "name": "consumer_name",
    "read_bytes": "data_read_bytes",
}
CONSUMER_SORTS: tuple[str, ...] = tuple(_SORT_SQL)


async def fetch_consumers(
    db: DatabricksWarehousePool,
    *,
    start: date,
    end: date,
    catalog: str | None = None,
    schema: str | None = None,
    tables: list[str] | None = None,
    search: str | None = None,
    consumer_type: str | None = None,
    sort: str = "cost",
    direction: str = "desc",
    column_filter: list[str] | None = None,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    conditions, params = date_conditions(start, end)
    object_conditions, object_params = object_filters(catalog, schema, tables)
    conditions.extend(object_conditions)
    params.extend(object_params)

    if consumer_type:
        # Open vocabulary: compared case-insensitively, never validated against
        # a closed enum the lineage does not guarantee.
        conditions.append("UPPER(consumer_type) = ?")
        params.append(consumer_type.strip().upper())

    search_conditions, search_params = search_condition(
        search, columns=["consumer_name", "consumer_id"]
    )
    conditions.extend(search_conditions)
    params.extend(search_params)

    where = where_clause(conditions)
    daily = db.table(GOLD_TABLE_DAILY)

    ctes = f"""WITH agg AS (
        SELECT consumer_id, MAX(consumer_name) AS consumer_name,
            MAX(consumer_type) AS consumer_type,
            COUNT(DISTINCT table_full_name) AS distinct_tables,
            SUM(request_count) AS request_count, SUM(data_read_bytes) AS data_read_bytes,
            SUM(data_written_bytes) AS data_written_bytes, SUM(rows_written) AS rows_written,
            SUM(estimated_cost_usd) AS estimated_cost_usd, MAX(last_used_at) AS last_used_at
        FROM {daily} {where} GROUP BY consumer_id
    ), ranked AS (
        SELECT agg.*, RANK() OVER (ORDER BY estimated_cost_usd DESC NULLS LAST) AS cost_rank
        FROM agg
    )"""
    filter_where, filter_params = compile_column_filters(column_filter, CONSUMER_COLUMNS)
    order_by = sort_sql(sort, direction, _SORT_SQL, "cost")
    total = await guarded(
        db,
        db.fetchscalar(
            f"{ctes} SELECT COUNT(*) FROM ranked {filter_where}",
            *params,
            *filter_params,
        ),
        tables=[GOLD_TABLE_DAILY],
    )
    rows = await guarded(
        db,
        db.fetchall(
            f"{ctes} SELECT * FROM ranked {filter_where} ORDER BY {order_by}, consumer_id ASC "
            "LIMIT ? OFFSET ?",
            *params,
            *filter_params,
            page_size,
            offset_of(page, page_size),
        ),
        tables=[GOLD_TABLE_DAILY],
    )

    items = [
        {
            "rank": integer(row["cost_rank"]),
            "consumer_id": row["consumer_id"],
            "consumer_name": row["consumer_name"],
            "consumer_type": row["consumer_type"],
            "distinct_tables": number(row["distinct_tables"]),
            "request_count": number(row["request_count"]),
            "data_read_bytes": number(row["data_read_bytes"]),
            "data_written_bytes": number(row.get("data_written_bytes")),
            "rows_written": number(row.get("rows_written")),
            "estimated_cost_usd": number(row["estimated_cost_usd"], decimals=2),
            "last_used_at": iso(row["last_used_at"]),
        }
        for row in rows
    ]

    return page_envelope(items, integer(total), page, page_size, start, end)
