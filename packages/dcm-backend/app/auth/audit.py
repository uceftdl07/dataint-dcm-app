"""Audit logging for sensitive DCM administration actions."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import Request

from ..config import Settings
from ..db.connection import DatabricksWarehousePool
from ..db.tables import qualified_table
from .dependencies import CurrentUser

__all__ = ["log_action"]


def _json_state(value: dict[str, Any] | list[Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str, ensure_ascii=False, sort_keys=True)


async def log_action(
    *,
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    before_state: dict[str, Any] | list[Any] | None = None,
    after_state: dict[str, Any] | list[Any] | None = None,
    request: Request | None = None,
) -> None:
    """Append an immutable audit event to ``dcm_audit_log``."""
    table = qualified_table(settings, "dcm_audit_log")
    ip_address = request.client.host if request and request.client else None
    await db.execute(
        f"""
        INSERT INTO {table}
            (id, actor_user_id, action, target_type, target_id,
             before_state, after_state, ip_address, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, current_timestamp())
        """,
        str(uuid4()),
        actor.id,
        action,
        target_type,
        target_id,
        _json_state(before_state),
        _json_state(after_state),
        ip_address,
    )
