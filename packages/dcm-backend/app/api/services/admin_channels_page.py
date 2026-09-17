"""Alert notification channel CRUD — reads/writes ``dcm_notification_channels``.

Kept out of the route per the route→service→pool pattern.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from ...auth.audit import log_action
from ...auth.dependencies import CurrentUser
from ...auth.notifier import test_notification_channel, validate_channel_config
from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_table

__all__ = [
    "create_channel",
    "delete_channel",
    "fetch_channels",
    "require_channel",
    "test_channel_notification",
    "update_channel",
]


def _parse_config(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _row_to_channel(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "channel_type": row["channel_type"],
        "config": _parse_config(row["config"]),
        "is_active": bool(row["is_active"]),
        "created_by": row["created_by"],
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


async def _get_channel(
    db: DatabricksWarehousePool,
    settings: Settings,
    channel_id: str,
) -> dict[str, Any] | None:
    table = qualified_table(settings, "dcm_notification_channels")
    return await db.fetchone(
        f"""
        SELECT id, name, channel_type, config, is_active, created_by, created_at, updated_at
        FROM {table}
        WHERE id = ?
        LIMIT 1
        """,
        channel_id,
    )


async def require_channel(
    db: DatabricksWarehousePool,
    settings: Settings,
    channel_id: str,
) -> dict[str, Any]:
    row = await _get_channel(db, settings, channel_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    return _row_to_channel(row)


async def fetch_channels(
    db: DatabricksWarehousePool,
    settings: Settings,
) -> dict[str, Any]:
    table = qualified_table(settings, "dcm_notification_channels")
    rows = await db.fetchall(
        f"""
        SELECT id, name, channel_type, config, is_active, created_by, created_at, updated_at
        FROM {table}
        ORDER BY name
        """
    )
    return {"items": [_row_to_channel(row) for row in rows], "total": len(rows)}


async def create_channel(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    *,
    name: str,
    channel_type: str,
    config: dict[str, Any],
    is_active: bool,
) -> dict[str, Any]:
    validate_channel_config(channel_type, config)
    table = qualified_table(settings, "dcm_notification_channels")
    channel_id = str(uuid4())
    after = {
        "id": channel_id,
        "name": name,
        "channel_type": channel_type,
        "config": config,
        "is_active": is_active,
        "created_by": actor.id,
    }
    await db.execute(
        f"""
        INSERT INTO {table}
            (id, name, channel_type, config, is_active, created_by, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, current_timestamp(), current_timestamp())
        """,
        channel_id,
        name,
        channel_type,
        json.dumps(config, ensure_ascii=False, sort_keys=True),
        is_active,
        actor.id,
    )
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="notification_channel.create",
        target_type="notification_channel",
        target_id=channel_id,
        after_state=after,
        request=request,
    )
    return after


async def update_channel(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    channel_id: str,
    changes: dict[str, Any],
) -> dict[str, Any]:
    before = await require_channel(db, settings, channel_id)
    db_changes = dict(changes)
    if "config" in db_changes:
        validate_channel_config(before["channel_type"], db_changes["config"])
        db_changes["config"] = json.dumps(db_changes["config"], ensure_ascii=False, sort_keys=True)
    if not db_changes:
        return before

    table = qualified_table(settings, "dcm_notification_channels")
    assignments = ", ".join(f"{column} = ?" for column in db_changes)
    await db.execute(
        f"""
        UPDATE {table}
        SET {assignments}, updated_at = current_timestamp()
        WHERE id = ?
        """,
        *db_changes.values(),
        channel_id,
    )
    after = {**before, **changes}
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="notification_channel.update",
        target_type="notification_channel",
        target_id=channel_id,
        before_state=before,
        after_state=after,
        request=request,
    )
    return after


async def delete_channel(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    channel_id: str,
) -> dict[str, Any]:
    before = await require_channel(db, settings, channel_id)
    table = qualified_table(settings, "dcm_notification_channels")
    await db.execute(
        f"""
        UPDATE {table}
        SET is_active = FALSE, updated_at = current_timestamp()
        WHERE id = ?
        """,
        channel_id,
    )
    after = {**before, "is_active": False}
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="notification_channel.delete",
        target_type="notification_channel",
        target_id=channel_id,
        before_state=before,
        after_state=after,
        request=request,
    )
    return after


async def test_channel_notification(
    db: DatabricksWarehousePool,
    settings: Settings,
    channel_id: str,
) -> dict[str, Any]:
    channel = await require_channel(db, settings, channel_id)
    result = await test_notification_channel(channel["channel_type"], channel["config"])
    return {"channel_id": channel_id, **result}
