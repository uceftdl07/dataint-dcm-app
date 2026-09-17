"""Read/write exploration over existing Gold facts; no new data pipeline."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from ...db.connection import DatabricksWarehousePool
from .uc_usage_charts import _days, _deleted, _envelope, _key, _where
from .uc_usage_common import (
    GOLD_TABLE_CATALOG,
    GOLD_TABLE_DAILY,
    GOLD_TABLE_POPULARITY_DAILY,
    guarded,
    integer,
    iso,
    number,
    pct_delta,
    period_dict,
    previous_period,
    table_lifecycle,
)

_METRICS = (
    "request_count",
    "data_read_bytes",
    "data_written_bytes",
    "rows_written",
    "estimated_cost_usd",
)
_SUMS = ", ".join(f"SUM({metric}) AS {metric}" for metric in _METRICS)


async def _daily(
    db: DatabricksWarehousePool, start: date, end: date, where: str, params: list[Any]
) -> list[dict[str, Any]]:
    rows = await guarded(
        db,
        db.fetchall(
            f"SELECT period_start, {_SUMS} FROM {db.table(GOLD_TABLE_DAILY)} {where} "
            "GROUP BY period_start ORDER BY period_start",
            *params,
        ),
        tables=[GOLD_TABLE_DAILY, GOLD_TABLE_CATALOG],
    )
    observed = {iso(row["period_start"])[:10]: row for row in rows}
    return [
        {"date": day, **{metric: number(observed.get(day, {}).get(metric)) for metric in _METRICS}}
        for day in _days(start, end)
    ]


async def fetch_write_charts(
    db: DatabricksWarehousePool, *, start: date, end: date, **scope: Any
) -> dict[str, Any]:
    where, params = _where(start, end, scope, extra=_deleted(db, scope))
    ctes = f"""WITH per_table AS (
        SELECT cloud_provider, table_full_name, {_SUMS}
        FROM {db.table(GOLD_TABLE_DAILY)} {where}
        GROUP BY cloud_provider, table_full_name
    )"""
    positive = "(data_written_bytes > 0 OR rows_written > 0)"
    totals = await guarded(
        db,
        db.fetchall(
            f"""{ctes}
        SELECT SUM(data_written_bytes) AS data_written_bytes, SUM(rows_written) AS rows_written,
            SUM(CASE WHEN {positive} THEN 1 ELSE 0 END) AS tables_with_writes,
            SUM(CASE WHEN {positive} AND request_count = 0
                THEN 1 ELSE 0 END) AS written_without_reads FROM per_table""",
            *params,
        ),
        tables=[GOLD_TABLE_DAILY, GOLD_TABLE_CATALOG],
    )
    ranking = await guarded(
        db,
        db.fetchall(
            f"""{ctes} SELECT * FROM per_table
        WHERE {positive} ORDER BY data_written_bytes DESC NULLS LAST, rows_written DESC NULLS LAST,
        table_full_name, cloud_provider LIMIT 10""",
            *params,
        ),
        tables=[GOLD_TABLE_DAILY, GOLD_TABLE_CATALOG],
    )
    total = totals[0] if totals else {}
    return {
        **_envelope(start, end, scope),
        "summary": {
            "data_written_bytes": number(total.get("data_written_bytes")),
            "rows_written": number(total.get("rows_written")),
            "tables_with_writes": integer(total.get("tables_with_writes")),
            "written_without_reads": integer(total.get("written_without_reads")),
        },
        "daily": await _daily(db, start, end, where, params),
        "ranking": [
            {
                "key": _key(row.get("cloud_provider"), row["table_full_name"]),
                "label": row["table_full_name"],
                "cloud_provider": row.get("cloud_provider"),
                "value": number(row.get("data_written_bytes")),
                "rows_written": number(row.get("rows_written")),
                "request_count": number(row.get("request_count")),
            }
            for row in ranking
        ],
    }


async def fetch_entity_detail(
    db: DatabricksWarehousePool,
    *,
    start: date,
    end: date,
    entity_kind: Literal["table", "consumer"],
    entity_id: str,
    **scope: Any,
) -> dict[str, Any]:
    where, params = _where(start, end, scope, extra=_deleted(db, scope))
    identity = "table_full_name" if entity_kind == "table" else "consumer_id"
    counterpart = "consumer_id" if entity_kind == "table" else "table_full_name"
    name = "MAX(consumer_name)" if entity_kind == "table" else "MAX(table_full_name)"
    where += f" AND {identity} = ?"
    params.append(entity_id)
    daily = db.table(GOLD_TABLE_DAILY)
    totals = await guarded(
        db,
        db.fetchall(
            f"""
        SELECT {_SUMS}, COUNT(*) AS observed_rows,
            COUNT(DISTINCT {counterpart}) AS counterpart_count,
            COUNT(DISTINCT CASE WHEN request_count > 0 OR data_written_bytes > 0
                OR rows_written > 0 THEN period_start END) AS active_days,
            COUNT(DISTINCT CASE WHEN data_written_bytes > 0 OR rows_written > 0
                THEN period_start END) AS write_days
        FROM {daily} {where}""",
            *params,
        ),
        tables=[GOLD_TABLE_DAILY, GOLD_TABLE_CATALOG],
    )
    counterparts = await guarded(
        db,
        db.fetchall(
            f"""
        SELECT {counterpart} AS id, {name} AS label, {_SUMS}
        FROM {daily} {where} AND {counterpart} IS NOT NULL
        GROUP BY {counterpart}
        ORDER BY request_count DESC NULLS LAST, data_written_bytes DESC NULLS LAST, id LIMIT 10
        """,
            *params,
        ),
        tables=[GOLD_TABLE_DAILY, GOLD_TABLE_CATALOG],
    )
    total = totals[0] if totals else {}
    # A consumer has no lifecycle: the three fields describe a table, so the
    # consumer detail keeps them at their neutral value rather than inventing one.
    lifecycle = (
        await table_lifecycle(db, entity_id)
        if entity_kind == "table"
        else {"is_deleted": False, "deleted_at": None, "lifecycle_state": "UNKNOWN"}
    )
    return {
        **_envelope(start, end, scope),
        "entity_kind": entity_kind,
        "entity_id": entity_id,
        **lifecycle,
        "summary": {
            **{metric: number(total.get(metric)) for metric in _METRICS},
            **{
                key: integer(total.get(key))
                for key in ("observed_rows", "counterpart_count", "active_days", "write_days")
            },
        },
        "daily": await _daily(db, start, end, where, params),
        "counterparts": [
            {
                "id": row["id"],
                "label": row.get("label") or row["id"],
                **{metric: number(row.get(metric)) for metric in _METRICS},
            }
            for row in counterparts
        ],
    }


async def fetch_cost_changes(
    db: DatabricksWarehousePool, *, start: date, end: date, **scope: Any
) -> dict[str, Any]:
    previous_start, previous_end = previous_period(start, end)
    where, params = _where(previous_start, end, scope, extra=_deleted(db, scope))
    ctes = f"""WITH costs AS (
        SELECT cloud_provider, table_full_name,
            SUM(CASE WHEN period_start >= ? THEN estimated_cost_usd END) AS current_cost,
            SUM(CASE WHEN period_start < ? THEN estimated_cost_usd END) AS previous_cost
        FROM {db.table(GOLD_TABLE_POPULARITY_DAILY)} {where}
        GROUP BY cloud_provider, table_full_name
    ), changes AS (
        SELECT *, current_cost - previous_cost AS delta_usd FROM costs
    )"""
    values = [start, start, *params]
    totals = await guarded(
        db,
        db.fetchall(
            f"""{ctes}
        SELECT SUM(current_cost) AS current_total, SUM(previous_cost) AS previous_total,
            COUNT(*) AS entity_count FROM changes""",
            *values,
        ),
        tables=[GOLD_TABLE_POPULARITY_DAILY, GOLD_TABLE_CATALOG],
    )
    rows = await guarded(
        db,
        db.fetchall(
            f"""{ctes} SELECT * FROM changes
        WHERE current_cost IS NOT NULL OR previous_cost IS NOT NULL
        ORDER BY ABS(delta_usd) DESC NULLS LAST, table_full_name, cloud_provider LIMIT 10""",
            *values,
        ),
        tables=[GOLD_TABLE_POPULARITY_DAILY, GOLD_TABLE_CATALOG],
    )
    total = totals[0] if totals else {}
    return {
        **_envelope(start, end, scope),
        "previous_period": period_dict(previous_start, previous_end),
        "current_total": number(total.get("current_total")),
        "previous_total": number(total.get("previous_total")),
        "entity_count": integer(total.get("entity_count")),
        "items": [
            {
                "key": _key(row.get("cloud_provider"), row["table_full_name"]),
                "label": row["table_full_name"],
                "cloud_provider": row.get("cloud_provider"),
                "current_cost": number(row.get("current_cost")),
                "previous_cost": number(row.get("previous_cost")),
                "delta_usd": number(row.get("delta_usd")),
                "delta_pct": pct_delta(row.get("current_cost"), row.get("previous_cost")),
            }
            for row in rows
        ],
    }
