"""Allowlisted, bound filters on complete period aggregates, before pagination."""

from __future__ import annotations

import math

from fastapi import HTTPException

TABLE_COLUMNS = {
    **dict.fromkeys(
        [
            "table_full_name",
            "table_type",
            "catalog",
            "schema",
            "cost_attribution_method",
            "cost_basis",
        ],
        "text",
    ),
    **dict.fromkeys(
        [
            "request_count",
            "distinct_consumers",
            "data_read_bytes",
            "data_written_bytes",
            "rows_written",
            "estimated_cost_usd",
            "latency_p95_ms",
            "failure_rate_pct",
            "freshness_lag_hours",
        ],
        "number",
    ),
}
# Les six colonnes affichées par « Cost by table », dont les deux dérivées
# (coût par accès, prévision) : filtrables parce que calculées dans la requête,
# donc sur la période entière et avant la pagination.
COST_BY_TABLE_COLUMNS = {
    "table_full_name": "text",
    **dict.fromkeys(
        [
            "estimated_cost_usd",
            "cost_per_request_usd",
            "request_count",
            "data_read_bytes",
            "forecast_cost_usd_7d",
        ],
        "number",
    ),
}
CONSUMER_COLUMNS = {
    **dict.fromkeys(["consumer_id", "consumer_name", "consumer_type"], "text"),
    **dict.fromkeys(
        [
            "distinct_tables",
            "request_count",
            "data_read_bytes",
            "data_written_bytes",
            "rows_written",
            "estimated_cost_usd",
        ],
        "number",
    ),
}


def compile_column_filters(
    filters: list[str] | None, columns: dict[str, str]
) -> tuple[str, list[str | float]]:
    # ``params`` porte des bornes numériques autant que du texte : sans l'annotation,
    # mypy fige son type sur le premier ``append`` et refuse ensuite les nombres.
    conditions: list[str] = []
    params: list[str | float] = []
    seen: set[str] = set()
    if len(filters or []) > 25:
        raise HTTPException(422, "too_many_column_filters")
    for token in filters or []:
        parts = token.split(":", 2)
        if len(token) > 600 or len(parts) != 3:
            raise HTTPException(422, "invalid_column_filter")
        column, operator, raw = parts
        if column not in columns or column in seen:
            raise HTTPException(422, "invalid_filter_column")
        seen.add(column)
        field = f"`{column}`"
        if operator in ("isnull", "notnull") and not raw:
            conditions.append(f"{field} IS {'NOT ' if operator == 'notnull' else ''}NULL")
        elif columns[column] == "text" and operator in ("eq", "contains") and raw.strip():
            conditions.append(
                f"LOWER({field}) = LOWER(?)"
                if operator == "eq"
                else f"INSTR(LOWER({field}), LOWER(?)) > 0"
            )
            params.append(raw.strip())
        elif columns[column] == "number" and operator in ("eq", "gte", "lte", "between"):
            try:
                values = [float(value) for value in raw.split(",")]
            except ValueError as error:
                raise HTTPException(422, "invalid_numeric_filter") from error
            if (
                len(values) != (2 if operator == "between" else 1)
                or any(not math.isfinite(value) for value in values)
                or (operator == "between" and values[0] > values[1])
            ):
                raise HTTPException(422, "invalid_numeric_filter")
            if operator == "between":
                conditions.append(f"{field} BETWEEN ? AND ?")
            else:
                comparison = {"eq": "=", "gte": ">=", "lte": "<="}[operator]
                conditions.append(f"{field} {comparison} ?")
            params.extend(values)
        else:
            raise HTTPException(422, "invalid_filter_operator")
    return ("WHERE " + " AND ".join(conditions) if conditions else ""), params


def sort_sql(sort: str, direction: str, columns: dict[str, str], default: str) -> str:
    if direction not in ("asc", "desc") or sort not in columns:
        raise HTTPException(422, "invalid_sort")
    return f"`{columns.get(sort, columns[default])}` {direction.upper()} NULLS LAST"
