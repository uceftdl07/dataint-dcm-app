"""Maintenance window CRUD — reads/writes ``dcm_maintenance_windows``.

Kept out of the route per the route→service→pool pattern.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from ...auth.audit import log_action
from ...auth.dependencies import CurrentUser
from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_table

__all__ = [
    "MAX_WINDOW_DURATION",
    "create_window",
    "delete_window",
    "fetch_active_windows",
    "fetch_windows",
    "get_window",
    "require_window",
    "update_window",
    "validate_candidate_window",
]

MAX_WINDOW_DURATION = timedelta(days=7)


def validate_candidate_window(candidate: dict[str, Any]) -> None:
    if candidate["ends_at"] <= candidate["starts_at"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ends_at must be after starts_at",
        )
    if candidate["ends_at"] - candidate["starts_at"] > MAX_WINDOW_DURATION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="maintenance window cannot exceed 7 days",
        )


def _row_to_window(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "lz_ids": row["lz_ids"] or [],
        "starts_at": row["starts_at"].isoformat() if row.get("starts_at") else None,
        "ends_at": row["ends_at"].isoformat() if row.get("ends_at") else None,
        "suppress_alerts": bool(row["suppress_alerts"]),
        "created_by": row["created_by"],
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }


async def get_window(
    db: DatabricksWarehousePool,
    settings: Settings,
    window_id: str,
) -> dict[str, Any] | None:
    table = qualified_table(settings, "dcm_maintenance_windows")
    return await db.fetchone(
        f"""
        SELECT id, name, description, lz_ids, starts_at, ends_at, suppress_alerts,
               created_by, created_at
        FROM {table}
        WHERE id = ?
        LIMIT 1
        """,
        window_id,
    )


async def require_window(
    db: DatabricksWarehousePool,
    settings: Settings,
    window_id: str,
) -> dict[str, Any]:
    row = await get_window(db, settings, window_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maintenance window not found",
        )
    return _row_to_window(row)


async def fetch_windows(
    db: DatabricksWarehousePool,
    settings: Settings,
) -> dict[str, Any]:
    table = qualified_table(settings, "dcm_maintenance_windows")
    rows = await db.fetchall(
        f"""
        SELECT id, name, description, lz_ids, starts_at, ends_at, suppress_alerts,
               created_by, created_at
        FROM {table}
        ORDER BY starts_at DESC
        LIMIT 500
        """
    )
    return {"items": [_row_to_window(row) for row in rows], "total": len(rows)}


async def fetch_active_windows(
    db: DatabricksWarehousePool,
    settings: Settings,
) -> dict[str, Any]:
    table = qualified_table(settings, "dcm_maintenance_windows")
    rows = await db.fetchall(
        f"""
        SELECT id, name, description, lz_ids, starts_at, ends_at, suppress_alerts,
               created_by, created_at
        FROM {table}
        WHERE starts_at <= current_timestamp() AND ends_at > current_timestamp()
        ORDER BY starts_at
        """
    )
    return {"items": [_row_to_window(row) for row in rows], "total": len(rows)}


async def create_window(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    payload: dict[str, Any],
) -> dict[str, Any]:
    table = qualified_table(settings, "dcm_maintenance_windows")
    window_id = str(uuid4())
    after = {"id": window_id, **payload, "created_by": actor.id}
    await db.execute(
        f"""
        INSERT INTO {table}
            (id, name, description, lz_ids, starts_at, ends_at,
             suppress_alerts, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, current_timestamp())
        """,
        window_id,
        payload["name"],
        payload["description"],
        payload["lz_ids"],
        payload["starts_at"],
        payload["ends_at"],
        payload["suppress_alerts"],
        actor.id,
    )
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="maintenance_window.create",
        target_type="maintenance_window",
        target_id=window_id,
        after_state=after,
        request=request,
    )
    return after


async def update_window(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    window_id: str,
    changes: dict[str, Any],
) -> dict[str, Any]:
    before_row = await get_window(db, settings, window_id)
    if before_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Maintenance window not found",
        )
    before = _row_to_window(before_row)
    candidate = {**before_row, **changes}
    validate_candidate_window(candidate)
    if not changes:
        return before

    table = qualified_table(settings, "dcm_maintenance_windows")
    assignments = ", ".join(f"{column} = ?" for column in changes)
    await db.execute(
        f"""
        UPDATE {table}
        SET {assignments}
        WHERE id = ?
        """,
        *changes.values(),
        window_id,
    )
    after = {**before, **changes}
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="maintenance_window.update",
        target_type="maintenance_window",
        target_id=window_id,
        before_state=before,
        after_state=after,
        request=request,
    )
    return after


async def delete_window(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    window_id: str,
) -> dict[str, Any]:
    before = await require_window(db, settings, window_id)
    table = qualified_table(settings, "dcm_maintenance_windows")
    await db.execute(f"DELETE FROM {table} WHERE id = ?", window_id)
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="maintenance_window.delete",
        target_type="maintenance_window",
        target_id=window_id,
        before_state=before,
        request=request,
    )
    return {"status": "deleted", "id": window_id}
