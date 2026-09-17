"""Admin CRUD for alert rules and alert firing history.

Kept out of the route per the route→service→pool pattern.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from ...auth.alert_evaluator import evaluate_alert_rule, validate_alert_condition
from ...auth.audit import log_action
from ...auth.dependencies import CurrentUser
from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_table

__all__ = [
    "create_rule",
    "delete_rule",
    "fetch_rule",
    "fetch_rule_firings",
    "fetch_rules",
    "test_rule",
    "update_rule",
]


def _row_to_rule(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "metric_domain": row["metric_domain"],
        "condition_field": row["condition_field"],
        "condition_operator": row["condition_operator"],
        "condition_threshold": float(row["condition_threshold"]),
        "eval_window_hours": int(row["eval_window_hours"]),
        "severity": row["severity"],
        "applies_to_lz_ids": row["applies_to_lz_ids"] or [],
        "notification_channel_ids": row["notification_channel_ids"] or [],
        "cooldown_minutes": int(row["cooldown_minutes"]),
        "is_active": bool(row["is_active"]),
        "created_by": row["created_by"],
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


def _row_to_firing(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "rule_id": row["rule_id"],
        "lz_id": row["lz_id"],
        "fired_at": row["fired_at"].isoformat() if row.get("fired_at") else None,
        "resolved_at": row["resolved_at"].isoformat() if row.get("resolved_at") else None,
        "measured_value": row["measured_value"],
        "notification_sent": bool(row["notification_sent"]),
        "notification_error": row["notification_error"],
    }


async def _get_rule_row(
    db: DatabricksWarehousePool,
    settings: Settings,
    rule_id: str,
) -> dict[str, Any] | None:
    table = qualified_table(settings, "dcm_alert_rules")
    return await db.fetchone(
        f"""
        SELECT
            id, name, description, metric_domain, condition_field, condition_operator,
            condition_threshold, eval_window_hours, severity, applies_to_lz_ids,
            notification_channel_ids, cooldown_minutes, is_active, created_by,
            created_at, updated_at
        FROM {table}
        WHERE id = ?
        LIMIT 1
        """,
        rule_id,
    )


async def _require_rule_row(
    db: DatabricksWarehousePool,
    settings: Settings,
    rule_id: str,
) -> dict[str, Any]:
    row = await _get_rule_row(db, settings, rule_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert rule not found")
    return _row_to_rule(row)


async def fetch_rule(
    db: DatabricksWarehousePool,
    settings: Settings,
    rule_id: str,
) -> dict[str, Any]:
    return await _require_rule_row(db, settings, rule_id)


async def _validate_channel_ids(
    db: DatabricksWarehousePool,
    settings: Settings,
    channel_ids: list[str],
) -> None:
    if not channel_ids:
        return
    table = qualified_table(settings, "dcm_notification_channels")
    placeholders = ", ".join("?" for _ in channel_ids)
    rows = await db.fetchall(
        f"""
        SELECT id
        FROM {table}
        WHERE is_active = TRUE AND id IN ({placeholders})
        """,
        *channel_ids,
    )
    existing = {row["id"] for row in rows}
    missing = sorted(set(channel_ids) - existing)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Unknown or inactive notification channels", "channel_ids": missing},
        )


async def fetch_rules(
    db: DatabricksWarehousePool,
    settings: Settings,
) -> dict[str, Any]:
    table = qualified_table(settings, "dcm_alert_rules")
    rows = await db.fetchall(
        f"""
        SELECT
            id, name, description, metric_domain, condition_field, condition_operator,
            condition_threshold, eval_window_hours, severity, applies_to_lz_ids,
            notification_channel_ids, cooldown_minutes, is_active, created_by,
            created_at, updated_at
        FROM {table}
        ORDER BY is_active DESC, severity, name
        """
    )
    return {"items": [_row_to_rule(row) for row in rows], "total": len(rows)}


async def create_rule(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    payload: Any,
) -> dict[str, Any]:
    await _validate_channel_ids(db, settings, payload.notification_channel_ids)
    table = qualified_table(settings, "dcm_alert_rules")
    rule_id = str(uuid4())
    after = {"id": rule_id, **payload.model_dump(), "created_by": actor.id}
    await db.execute(
        f"""
        INSERT INTO {table}
            (id, name, description, metric_domain, condition_field, condition_operator,
             condition_threshold, eval_window_hours, severity, applies_to_lz_ids,
             notification_channel_ids, cooldown_minutes, is_active, created_by,
             created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp(), current_timestamp())
        """,
        rule_id,
        payload.name,
        payload.description,
        payload.metric_domain,
        payload.condition_field,
        payload.condition_operator,
        payload.condition_threshold,
        payload.eval_window_hours,
        payload.severity,
        payload.applies_to_lz_ids,
        payload.notification_channel_ids,
        payload.cooldown_minutes,
        payload.is_active,
        actor.id,
    )
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="alert_rule.create",
        target_type="alert_rule",
        target_id=rule_id,
        after_state=after,
        request=request,
    )
    return after


async def update_rule(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    rule_id: str,
    payload: Any,
) -> dict[str, Any]:
    before = await _require_rule_row(db, settings, rule_id)
    changes = payload.model_dump(exclude_unset=True)
    candidate = {**before, **changes}
    validate_alert_condition(
        candidate["metric_domain"],
        candidate["condition_field"],
        candidate["condition_operator"],
    )
    if "notification_channel_ids" in changes:
        await _validate_channel_ids(db, settings, changes["notification_channel_ids"])
    if not changes:
        return before

    table = qualified_table(settings, "dcm_alert_rules")
    assignments = ", ".join(f"{column} = ?" for column in changes)
    await db.execute(
        f"""
        UPDATE {table}
        SET {assignments}, updated_at = current_timestamp()
        WHERE id = ?
        """,
        *changes.values(),
        rule_id,
    )
    after = {**before, **changes}
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="alert_rule.update",
        target_type="alert_rule",
        target_id=rule_id,
        before_state=before,
        after_state=after,
        request=request,
    )
    return after


async def delete_rule(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    rule_id: str,
) -> dict[str, Any]:
    before = await _require_rule_row(db, settings, rule_id)
    table = qualified_table(settings, "dcm_alert_rules")
    await db.execute(
        f"""
        UPDATE {table}
        SET is_active = FALSE, updated_at = current_timestamp()
        WHERE id = ?
        """,
        rule_id,
    )
    after = {**before, "is_active": False}
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="alert_rule.delete",
        target_type="alert_rule",
        target_id=rule_id,
        before_state=before,
        after_state=after,
        request=request,
    )
    return after


async def test_rule(
    db: DatabricksWarehousePool,
    settings: Settings,
    rule_id: str,
) -> dict[str, Any]:
    rule = await _require_rule_row(db, settings, rule_id)
    return await evaluate_alert_rule(db, settings, rule)


async def fetch_rule_firings(
    db: DatabricksWarehousePool,
    settings: Settings,
    rule_id: str,
) -> dict[str, Any]:
    await _require_rule_row(db, settings, rule_id)
    table = qualified_table(settings, "dcm_alert_firings")
    rows = await db.fetchall(
        f"""
        SELECT
            id, rule_id, lz_id, fired_at, resolved_at, measured_value,
            notification_sent, notification_error
        FROM {table}
        WHERE rule_id = ?
        ORDER BY fired_at DESC
        LIMIT 500
        """,
        rule_id,
    )
    return {"items": [_row_to_firing(row) for row in rows], "total": len(rows)}
