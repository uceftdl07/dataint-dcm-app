"""Filtered UC usage charts, computed on the existing Gold tables.

Rank before reducing the result to ten entities and one remainder. The warehouse
returns at most eleven rows per observed day, not the consumer × table fact.
Table and consumer identities retain their cloud; no join can multiply an AWS
row by an Azure homonym. Missing observations and unattributed costs stay NULL.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from typing import Any, Literal

from ...db.connection import DatabricksWarehousePool
from .uc_usage_common import (
    GOLD_TABLE_CATALOG,
    GOLD_TABLE_DAILY,
    GOLD_TABLE_POPULARITY_DAILY,
    date_conditions,
    deleted_table_conditions,
    guarded,
    integer,
    iso,
    number,
    object_filters,
    period_dict,
    previous_period,
    ratio_pct,
    where_clause,
)

TOP_SERIES = 5
TOP_RANKING = 10


def _sum(values: Iterable[Any]) -> int | float | None:
    measured = [value for value in values if value is not None]
    return number(sum(measured)) if measured else None


def _key(cloud: str | None, name: str) -> str:
    return json.dumps([cloud, name], separators=(",", ":"))


def _where(
    start: date, end: date, scope: dict[str, Any], *, extra: Sequence[str] = ()
) -> tuple[str, list[Any]]:
    """``extra`` carries parameterless predicates — today, the deleted-table one.

    Passed in rather than read from ``scope`` so the consumer-grain charts, exempt
    from ``include_deleted``, cannot pick it up by accident: an endpoint that
    ignores the flag must not start filtering the day the key appears in scope.
    """
    conditions, params = date_conditions(start, end)
    objects, values = object_filters(scope.get("catalog"), scope.get("schema"), scope.get("tables"))
    return where_clause([*conditions, *objects, *extra]), [*params, *values]


def _deleted(db: DatabricksWarehousePool, scope: dict[str, Any]) -> list[str]:
    return deleted_table_conditions(db, bool(scope.get("include_deleted")))


def _envelope(start: date, end: date, scope: dict[str, Any]) -> dict[str, Any]:
    return {
        "period": period_dict(start, end),
        "filters": {
            "catalog": (scope.get("catalog") or "").strip() or None,
            "schema": (scope.get("schema") or "").strip() or None,
            "tables": sorted({t.strip() for t in (scope.get("tables") or []) if t.strip()}),
        },
        "grain": "day",
    }


def _days(start: date, end: date) -> list[str]:
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


def _points(days: list[str], values: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"date": day, "value": number(values.get(day))} for day in days]


async def _table_series(
    db: DatabricksWarehousePool,
    start: date,
    end: date,
    scope: dict[str, Any],
    metric: Literal["request_count", "estimated_cost_usd"],
) -> dict[str, Any]:
    # Filtered inside ``filtered``, i.e. before the ranking window: a deleted table
    # must not consume a top-10 slot nor inflate ``scope_total`` (contract FR-008).
    where, params = _where(start, end, scope, extra=_deleted(db, scope))
    # `metric` and the limits are internal constants, never interpolated user input.
    rows = await guarded(
        db,
        db.fetchall(
            f"""
            WITH filtered AS (
                SELECT cloud_provider, table_full_name, period_start, {metric} AS value
                FROM {db.table(GOLD_TABLE_POPULARITY_DAILY)} {where}
            ), totals AS (
                SELECT cloud_provider, table_full_name, SUM(value) AS entity_total
                FROM filtered GROUP BY cloud_provider, table_full_name
            ), ranked AS (
                SELECT totals.*,
                    ROW_NUMBER() OVER (
                        ORDER BY entity_total DESC NULLS LAST, table_full_name, cloud_provider
                    ) AS position,
                    SUM(entity_total) OVER () AS scope_total,
                    COUNT(*) OVER () AS entity_count,
                    SUM(CASE WHEN entity_total IS NULL THEN 1 ELSE 0 END) OVER ()
                        AS unmeasured_entity_count
                FROM totals
            )
            SELECT f.period_start,
                CASE WHEN r.position <= {TOP_RANKING} THEN r.table_full_name END
                    AS table_full_name,
                CASE WHEN r.position <= {TOP_RANKING} THEN r.cloud_provider END
                    AS cloud_provider,
                CASE WHEN r.position <= {TOP_RANKING} THEN r.position
                    ELSE {TOP_RANKING + 1} END AS position,
                SUM(f.value) AS value,
                MAX(r.scope_total) AS scope_total,
                MAX(r.entity_count) AS entity_count,
                MAX(r.unmeasured_entity_count) AS unmeasured_entity_count
            FROM filtered f JOIN ranked r
              ON r.cloud_provider = f.cloud_provider AND r.table_full_name = f.table_full_name
            GROUP BY f.period_start,
                CASE WHEN r.position <= {TOP_RANKING} THEN r.table_full_name END,
                CASE WHEN r.position <= {TOP_RANKING} THEN r.cloud_provider END,
                CASE WHEN r.position <= {TOP_RANKING} THEN r.position ELSE {TOP_RANKING + 1} END
            ORDER BY position, f.period_start
            """,
            *params,
        ),
        tables=[GOLD_TABLE_POPULARITY_DAILY, GOLD_TABLE_CATALOG],
    )
    days = _days(start, end)
    groups: dict[int, dict[str, Any]] = {}
    for row in rows:
        position = integer(row["position"])
        name = row["table_full_name"]
        group = groups.setdefault(
            position,
            {
                "key": _key(row["cloud_provider"], name) if name else "other-tables",
                "label": name or "Other tables",
                "cloud_provider": row["cloud_provider"],
                "values": {},
            },
        )
        group["values"][iso(row["period_start"])] = number(row["value"])

    scope_total = number(rows[0]["scope_total"]) if rows else None
    entity_count = integer(rows[0]["entity_count"]) if rows else 0
    ranking = [
        {
            "key": group["key"],
            "label": group["label"],
            "cloud_provider": group["cloud_provider"],
            "value": _sum(group["values"].values()),
            "share_pct": ratio_pct(_sum(group["values"].values()), scope_total),
        }
        for position, group in groups.items()
        if position <= TOP_RANKING
    ]
    series = [
        {
            "key": group["key"],
            "label": group["label"],
            "cloud_provider": group["cloud_provider"],
            "entity_count": 1,
            "points": _points(days, group["values"]),
        }
        for position, group in groups.items()
        if position <= TOP_SERIES
    ]
    remainder = [group for position, group in groups.items() if position > TOP_SERIES]
    if remainder:
        series.append(
            {
                "key": "other-tables",
                "label": "Other tables",
                "cloud_provider": None,
                "entity_count": entity_count - TOP_SERIES,
                "points": _points(
                    days, {day: _sum(g["values"].get(day) for g in remainder) for day in days}
                ),
            }
        )
    return {
        "series": series,
        "ranking": ranking,
        "summary": {
            "total": scope_total,
            "entity_count": entity_count,
            "unmeasured_entity_count": integer(rows[0]["unmeasured_entity_count"]) if rows else 0,
            "top_5_total": _sum(item["value"] for item in ranking[:TOP_SERIES]),
            "other_total": _sum(value for group in remainder for value in group["values"].values()),
            "top_5_share_pct": ratio_pct(
                _sum(item["value"] for item in ranking[:TOP_SERIES]), scope_total
            ),
            "top_10_share_pct": ratio_pct(_sum(item["value"] for item in ranking), scope_total),
        },
        "groups": groups,
    }


def _activity(groups: dict[int, dict[str, Any]], start: date, end: date) -> dict[str, Any]:
    weekly = (end - start).days >= 42
    buckets: dict[str, list[str]] = {}
    for day in _days(start, end):
        parsed = date.fromisoformat(day)
        key = (
            max(start, parsed - timedelta(days=parsed.weekday())) if weekly else parsed
        ).isoformat()
        buckets.setdefault(key, []).append(day)
    return {
        "grain": "week" if weekly else "day",
        "columns": [{"start": days[0], "end": days[-1]} for days in buckets.values()],
        "rows": [
            {
                "key": group["key"],
                "label": group["label"],
                "cloud_provider": group["cloud_provider"],
                "cells": [
                    {
                        "value": _sum(group["values"].get(day) for day in days),
                        "observed_days": sum(group["values"].get(day) is not None for day in days),
                        "expected_days": len(days),
                    }
                    for days in buckets.values()
                ],
            }
            for position, group in groups.items()
            if position <= TOP_RANKING
        ],
    }


async def _consumer_ranking(
    db: DatabricksWarehousePool,
    start: date,
    end: date,
    scope: dict[str, Any],
    *,
    extra: Sequence[str] = (),
) -> list[dict[str, Any]]:
    where, params = _where(start, end, scope, extra=extra)
    rows = await guarded(
        db,
        db.fetchall(
            f"""
            WITH per_table AS (
                SELECT cloud_provider, consumer_id, table_full_name,
                    MAX(consumer_name) AS consumer_name, MAX(consumer_type) AS consumer_type,
                    SUM(request_count) AS request_count
                FROM {db.table(GOLD_TABLE_DAILY)} {where} AND request_count > 0
                GROUP BY cloud_provider, consumer_id, table_full_name
            ), consumers AS (
                SELECT cloud_provider, consumer_id, MAX(consumer_name) AS consumer_name,
                    MAX(consumer_type) AS consumer_type, COUNT(*) AS distinct_tables,
                    SUM(request_count) AS request_count
                FROM per_table GROUP BY cloud_provider, consumer_id
            )
            SELECT consumers.*, SUM(request_count) OVER () AS scope_total
            FROM consumers ORDER BY request_count DESC, consumer_id, cloud_provider
            LIMIT {TOP_RANKING}
            """,
            *params,
        ),
        tables=[GOLD_TABLE_DAILY, GOLD_TABLE_CATALOG],
    )
    return [
        {
            "key": _key(row["cloud_provider"], row["consumer_id"]),
            "label": row["consumer_name"] or row["consumer_id"],
            "cloud_provider": row["cloud_provider"],
            "consumer_type": row["consumer_type"],
            "distinct_tables": integer(row["distinct_tables"]),
            "value": number(row["request_count"]),
            "share_pct": ratio_pct(row["request_count"], row["scope_total"]),
        }
        for row in rows
    ]


async def fetch_table_charts(
    db: DatabricksWarehousePool, *, start: date, end: date, **scope: Any
) -> dict[str, Any]:
    result = await _table_series(db, start, end, scope, "request_count")
    activity = _activity(result.pop("groups"), start, end)
    single_table = (
        len(set(scope.get("tables") or [])) == 1 or result["summary"]["entity_count"] == 1
    )
    consumers = (
        await _consumer_ranking(db, start, end, scope, extra=_deleted(db, scope))
        if single_table
        else []
    )
    return {
        **_envelope(start, end, scope),
        **result,
        "activity": activity,
        "single_table_consumers": consumers,
        "ranking_mode": "consumers" if single_table else "tables",
    }


async def fetch_consumer_charts(
    db: DatabricksWarehousePool, *, start: date, end: date, **scope: Any
) -> dict[str, Any]:
    where, params = _where(start, end, scope)
    rows = await guarded(
        db,
        db.fetchall(
            f"""
            SELECT period_start,
                COALESCE(NULLIF(TRIM(consumer_type), ''), 'UNKNOWN') AS consumer_type,
                SUM(request_count) AS request_count
            FROM {db.table(GOLD_TABLE_DAILY)} {where}
            GROUP BY period_start, COALESCE(NULLIF(TRIM(consumer_type), ''), 'UNKNOWN')
            ORDER BY consumer_type, period_start
            """,
            *params,
        ),
        tables=[GOLD_TABLE_DAILY],
    )
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        day = iso(row["period_start"])
        assert day is not None  # The SQL date predicates exclude NULL dates.
        groups.setdefault(row["consumer_type"], {})[day] = number(row["request_count"])
    total = _sum(row["request_count"] for row in rows)
    days = _days(start, end)
    previous_start, previous_end = previous_period(start, end)
    comparison_where, comparison_params = _where(previous_start, end, scope)
    active = await guarded(
        db,
        db.fetchall(
            f"""
            WITH daily AS (
                SELECT period_start, cloud_provider,
                    COUNT(DISTINCT CASE WHEN request_count > 0 THEN consumer_id END)
                        AS active_consumers
                FROM {db.table(GOLD_TABLE_DAILY)} {comparison_where}
                GROUP BY period_start, cloud_provider
            )
            SELECT period_start, SUM(active_consumers) AS active_consumers
            FROM daily GROUP BY period_start ORDER BY period_start
            """,
            *comparison_params,
        ),
        tables=[GOLD_TABLE_DAILY],
    )
    by_date = {iso(row["period_start"]): number(row["active_consumers"]) for row in active}
    span = end - start + timedelta(days=1)
    return {
        **_envelope(start, end, scope),
        "total_requests": number(total),
        "by_type": [
            {
                "key": kind,
                "label": kind,
                "total": _sum(values.values()),
                "share_pct": ratio_pct(_sum(values.values()), total),
                "points": _points(days, values),
            }
            for kind, values in groups.items()
        ],
        "ranking": await _consumer_ranking(db, start, end, scope),
        "previous_period": period_dict(previous_start, previous_end),
        "active_consumers": [
            {
                "date": day,
                "value": by_date.get(day),
                "previous_date": (date.fromisoformat(day) - span).isoformat(),
                "previous_value": by_date.get((date.fromisoformat(day) - span).isoformat()),
            }
            for day in days
        ],
    }


def _method(values: Iterable[str | None]) -> str | None:
    known = {value for value in values if value}
    return next(iter(known)) if len(known) == 1 else "mixed" if known else None


async def fetch_finops_charts(
    db: DatabricksWarehousePool, *, start: date, end: date, **scope: Any
) -> dict[str, Any]:
    result = await _table_series(db, start, end, scope, "estimated_cost_usd")
    result.pop("groups")
    where, params = _where(start, end, scope, extra=_deleted(db, scope))
    rows = await guarded(
        db,
        db.fetchall(
            f"""
            SELECT period_start, SUM(estimated_cost_usd) AS estimated_cost_usd,
                SUM(request_count) AS request_count,
                SUM(costed_request_count) AS costed_request_count,
                CASE WHEN COUNT(DISTINCT cost_attribution_method) > 1 THEN 'mixed'
                    ELSE MAX(cost_attribution_method) END AS cost_attribution_method,
                CASE WHEN COUNT(DISTINCT cost_basis) > 1 THEN 'mixed'
                    ELSE MAX(cost_basis) END AS cost_basis
            FROM {db.table(GOLD_TABLE_DAILY)} {where}
            GROUP BY period_start ORDER BY period_start
            """,
            *params,
        ),
        tables=[GOLD_TABLE_DAILY, GOLD_TABLE_CATALOG],
    )
    by_date = {iso(row["period_start"]): row for row in rows}
    points = []
    for day in _days(start, end):
        row = by_date.get(day, {})
        cost, costed = (
            number(row.get("estimated_cost_usd")),
            number(row.get("costed_request_count")),
        )
        points.append(
            {
                "date": day,
                "value": round(1000 * cost / costed, 6)
                if cost is not None and costed and costed > 0
                else None,
                "request_count": number(row.get("request_count")),
                "costed_request_count": costed,
                "coverage_pct": ratio_pct(costed, row.get("request_count")),
                "cost_attribution_method": row.get("cost_attribution_method"),
                "cost_basis": row.get("cost_basis"),
            }
        )
    return {
        **_envelope(start, end, scope),
        **result,
        "unit_cost": points,
        "cost_coverage_pct": ratio_pct(
            _sum(row["costed_request_count"] for row in rows),
            _sum(row["request_count"] for row in rows),
        ),
        "cost_attribution_method": _method(row["cost_attribution_method"] for row in rows),
        "cost_basis": _method(row["cost_basis"] for row in rows),
    }
