"""Administration audit log queries — kept out of the route per the route→service→pool pattern."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_table

__all__ = ["fetch_audit_log", "fetch_audit_log_rows", "row_to_audit"]

_EXPORT_ROW_LIMIT = 10000


def row_to_audit(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "actor_user_id": row["actor_user_id"],
        "action": row["action"],
        "target_type": row["target_type"],
        "target_id": row["target_id"],
        "before_state": row["before_state"],
        "after_state": row["after_state"],
        "ip_address": row["ip_address"],
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }


def _filters(
    actor_user_id: str | None,
    action: str | None,
    target_type: str | None,
    start_date: datetime | None,
    end_date: datetime | None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if actor_user_id:
        clauses.append("actor_user_id = ?")
        params.append(actor_user_id)
    if action:
        clauses.append("action = ?")
        params.append(action)
    if target_type:
        clauses.append("target_type = ?")
        params.append(target_type)
    if start_date:
        clauses.append("created_at >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("created_at <= ?")
        params.append(end_date)
    where_sql = "WHERE " + " AND ".join(clauses) if clauses else ""
    return where_sql, params


async def fetch_audit_log(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    actor_user_id: str | None,
    action: str | None,
    target_type: str | None,
    start_date: datetime | None,
    end_date: datetime | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    table = qualified_table(settings, "dcm_audit_log")
    where_sql, params = _filters(actor_user_id, action, target_type, start_date, end_date)
    rows = await db.fetchall(
        f"""
        SELECT id, actor_user_id, action, target_type, target_id, before_state,
               after_state, ip_address, created_at
        FROM {table}
        {where_sql}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        *params,
        limit,
        offset,
    )
    total = await db.fetchscalar(f"SELECT COUNT(*) FROM {table} {where_sql}", *params)
    return {
        "items": [row_to_audit(row) for row in rows],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }


async def fetch_audit_log_rows(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    actor_user_id: str | None,
    action: str | None,
    target_type: str | None,
    start_date: datetime | None,
    end_date: datetime | None,
) -> list[dict[str, Any]]:
    """Rows for CSV export — no pagination, capped at ``_EXPORT_ROW_LIMIT``."""
    table = qualified_table(settings, "dcm_audit_log")
    where_sql, params = _filters(actor_user_id, action, target_type, start_date, end_date)
    rows = await db.fetchall(
        f"""
        SELECT id, actor_user_id, action, target_type, target_id, before_state,
               after_state, ip_address, created_at
        FROM {table}
        {where_sql}
        ORDER BY created_at DESC
        LIMIT {_EXPORT_ROW_LIMIT}
        """,
        *params,
    )
    return [row_to_audit(row) for row in rows]
