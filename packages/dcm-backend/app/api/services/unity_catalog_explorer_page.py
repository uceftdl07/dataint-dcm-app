"""Unity Catalog table explorer — metadata, preview and constrained ad-hoc queries.

Kept out of the route per the route→service→pool pattern.

Every function here reads a caller-supplied ``catalog.schema.table``, so none of
them can be narrowed to a project's Landing Zones or Databricks workspaces — the
route restricts access to callers with an unrestricted scope.
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException

from ...db.connection import DatabricksWarehousePool

__all__ = [
    "fetch_table_metadata",
    "fetch_table_preview",
    "run_generic_query",
]

_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")
_FORBIDDEN_SQL_FRAGMENT_RE = re.compile(
    r"(--|/\*|\*/|;|\b(alter|call|copy|create|delete|drop|grant|insert|merge|optimize|refresh|"
    r"revoke|set|truncate|union|update|use|vacuum)\b)",
    re.IGNORECASE,
)
_DEFAULT_TABLE = "curated_activity_runs"
_MAX_QUERY_LIMIT = 50_000
_MAX_PREVIEW_LIMIT = 5_000
_LARGE_TABLE_PREFIXES = ("large_", "fact_")


def _quote_identifier(value: str, label: str = "identifier") -> str:
    normalized = value.strip()
    if not normalized or not _IDENTIFIER_RE.fullmatch(normalized):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {label}. Only letters, numbers and underscores are supported.",
        )
    return f"`{normalized.replace('`', '``')}`"


def _qualified_name(
    catalog_name: str,
    schema_name: str | None = None,
    table_name: str | None = None,
) -> str:
    parts = [_quote_identifier(catalog_name, "catalog_name")]
    if schema_name is not None:
        parts.append(_quote_identifier(schema_name, "schema_name"))
    if table_name is not None:
        parts.append(_quote_identifier(table_name, "table_name"))
    return ".".join(parts)


def _serialise_value(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        number = float(value)
        return int(number) if number.is_integer() else number
    return value


def _serialise_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _serialise_value(value) for key, value in row.items()}


def _normalise_limit(
    table_name: str,
    limit: int | None,
    *,
    max_limit: int,
    cap_large_tables: bool = False,
) -> int:
    requested = limit or max_limit
    if cap_large_tables and (
        table_name == _DEFAULT_TABLE or table_name.startswith(_LARGE_TABLE_PREFIXES)
    ):
        requested = min(requested, 100)
    return min(requested, max_limit)


def _safe_sql_fragment(value: str | None, label: str) -> str:
    fragment = (value or "").strip()
    if not fragment:
        return ""
    if len(fragment) > 1_000 or _FORBIDDEN_SQL_FRAGMENT_RE.search(fragment):
        raise HTTPException(status_code=400, detail=f"Invalid {label}.")
    return fragment


def _select_columns(columns: list[str] | None) -> str:
    if not columns:
        return "*"
    return ", ".join(_quote_identifier(column, "column") for column in columns)


def _table_payload(
    *,
    full_name: str,
    columns: list[str],
    rows: list[dict[str, Any]],
    execution_time: float,
    sql_query: str,
    total_rows: int | None = None,
) -> dict[str, Any]:
    data = [[row.get(column) for column in columns] for row in rows]
    return {
        "Status": "SUCCESS",
        "FullTableName": full_name,
        "RowsRetrieved": len(rows),
        "TotalRows": total_rows,
        "ColumnsCount": len(columns),
        "Columns": columns,
        "Data": data,
        "Rows": rows,
        "SqlQuery": sql_query,
        "ExecutionTime": round(execution_time, 3),
        "data": {
            "columns": columns,
            "rows": rows,
        },
    }


async def fetch_table_metadata(
    db: DatabricksWarehousePool,
    table_name: str,
    catalog_name: str,
    schema_name: str,
) -> dict[str, Any]:
    """Return table metadata and columns."""
    catalog = _qualified_name(catalog_name)
    full_name = f"{catalog_name}.{schema_name}.{table_name}"
    table_rows, column_rows = await asyncio.gather(
        db.fetchall(
            f"""
            SELECT table_type, data_source_format, table_owner, created
            FROM {catalog}.information_schema.tables
            WHERE table_schema = ? AND table_name = ?
            LIMIT 1
            """,
            schema_name,
            table_name,
        ),
        db.fetchall(
            f"""
            SELECT column_name, data_type, is_nullable, comment
            FROM {catalog}.information_schema.columns
            WHERE table_schema = ? AND table_name = ?
            ORDER BY ordinal_position
            """,
            schema_name,
            table_name,
        ),
    )

    table = table_rows[0] if table_rows else {}
    columns = [
        {
            "Name": row["column_name"],
            "Type": row.get("data_type") or "unknown",
            "Nullable": str(row.get("is_nullable", "")).upper() == "YES",
            "Comment": row.get("comment"),
        }
        for row in column_rows
    ]
    payload = {
        "FullName": full_name,
        "Type": table.get("table_type") or "TABLE",
        "Format": table.get("data_source_format") or "-",
        "Owner": table.get("table_owner") or "-",
        "CreatedAt": _serialise_value(table.get("created")),
        "ColumnsCount": len(columns),
        "Columns": columns,
    }
    return {"Status": "SUCCESS", "Table": payload, "table": payload}


async def fetch_table_preview(
    db: DatabricksWarehousePool,
    table_name: str,
    catalog_name: str,
    schema_name: str,
    *,
    limit: int,
    offset: int,
    order_by: str | None,
    include_total: bool,
) -> dict[str, Any]:
    """Return a paginated data preview."""
    requested = _normalise_limit(
        table_name,
        limit,
        max_limit=_MAX_PREVIEW_LIMIT,
        cap_large_tables=True,
    )
    order_fragment = _safe_sql_fragment(order_by, "orderBy")
    qualified = _qualified_name(catalog_name, schema_name, table_name)
    order_clause = f"ORDER BY {order_fragment}" if order_fragment else ""
    query = f"SELECT * FROM {qualified} {order_clause} LIMIT ? OFFSET ?"

    started = time.perf_counter()
    rows = [_serialise_row(row) for row in await db.fetchall(query, requested, offset)]
    execution_time = time.perf_counter() - started
    columns = list(rows[0].keys()) if rows else []

    total: int | None = None
    if include_total:
        total_rows = await db.fetchscalar(f"SELECT COUNT(*) AS total_rows FROM {qualified}")
        total = int(total_rows or 0)

    has_next_page = (
        len(rows) == requested if not include_total else (offset + requested < (total or 0))
    )
    current_page = (offset // requested) + 1 if requested else 1
    total_pages = (
        ((total + requested - 1) // requested if requested else 1) if total is not None else None
    )
    table = _table_payload(
        full_name=f"{catalog_name}.{schema_name}.{table_name}",
        columns=columns,
        rows=rows,
        execution_time=execution_time,
        sql_query=query,
        total_rows=total,
    )
    pagination = {
        "CurrentPage": current_page,
        "PageSize": requested,
        "Offset": offset,
        "TotalRows": total,
        "TotalPages": total_pages,
        "HasNextPage": has_next_page,
        "HasPreviousPage": offset > 0,
        "NextOffset": offset + requested if has_next_page else None,
        "PreviousOffset": max(offset - requested, 0) if offset > 0 else None,
    }
    return {
        "Status": "SUCCESS",
        "Table": table,
        "table": table,
        "Pagination": pagination,
        "pagination": pagination,
    }


async def run_generic_query(
    db: DatabricksWarehousePool,
    *,
    catalog_name: str,
    schema_name: str,
    table_name: str,
    columns: list[str] | None,
    where_clause: str | None,
    order_by: str | None,
    limit: int | None,
    offset: int,
) -> dict[str, Any]:
    """Run a constrained SELECT against a Unity Catalog table."""
    qualified = _qualified_name(catalog_name, schema_name, table_name)
    select_columns = _select_columns(columns)
    where_fragment = _safe_sql_fragment(where_clause, "whereClause")
    order_fragment = _safe_sql_fragment(order_by, "orderBy")
    normalised_limit = _normalise_limit(table_name, limit, max_limit=_MAX_QUERY_LIMIT)
    where_sql = f"WHERE {where_fragment}" if where_fragment else ""
    order_sql = f"ORDER BY {order_fragment}" if order_fragment else ""
    query = (
        f"SELECT {select_columns} FROM {qualified} "
        f"{where_sql} {order_sql} LIMIT ? OFFSET ?"
    )

    started = time.perf_counter()
    rows = [_serialise_row(row) for row in await db.fetchall(query, normalised_limit, offset)]
    execution_time = time.perf_counter() - started
    result_columns = columns or (list(rows[0].keys()) if rows else [])

    return _table_payload(
        full_name=f"{catalog_name}.{schema_name}.{table_name}",
        columns=result_columns,
        rows=rows,
        execution_time=execution_time,
        sql_query=query,
    )
