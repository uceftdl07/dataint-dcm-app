"""Per-user notification display preferences (Settings).

Kept out of the route per the route→service→pool pattern.
"""

from __future__ import annotations

from typing import Any

from ...auth.dependencies import CurrentUser
from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_table
from ...notification.defaults import (
    default_preferences_response,
    preferences_with_timestamp,
    row_to_preferences,
)
from ...notification.schema_compat import (
    is_missing_notification_lz_column_error,
    legacy_preferences_row,
    legacy_select_sql,
)

__all__ = [
    "get_preferences",
    "upsert_preferences",
]


def _sanitize_notification_lz_ids(
    requested: list[str],
    current_user: CurrentUser,
) -> list[str]:
    """Keep only LZ IDs the user is allowed to monitor."""
    if current_user.role in {"admin", "super_admin"} and not current_user.lz_ids:
        return requested
    allowed = set(current_user.lz_ids)
    return [lz_id for lz_id in requested if lz_id in allowed]


def _preferences_table(settings: Settings) -> str:
    return qualified_table(settings, "dcm_user_notification_preferences")


async def _fetch_preferences_row(
    db: DatabricksWarehousePool,
    settings: Settings,
    user_id: str,
    *,
    include_lz_column: bool = True,
) -> dict[str, Any] | None:
    table = _preferences_table(settings)
    if include_lz_column:
        try:
            row = await db.fetchone(
                f"""
                SELECT
                    user_id,
                    show_pipeline,
                    show_cluster,
                    show_cost,
                    show_security,
                    show_governance,
                    show_collector_status,
                    min_severity,
                    hide_info,
                    email_enabled,
                    teams_digest_enabled,
                    notification_lz_ids,
                    updated_at
                FROM {table}
                WHERE user_id = ?
                LIMIT 1
                """,
                user_id,
            )
        except Exception as exc:
            if not is_missing_notification_lz_column_error(exc):
                raise
            row = await db.fetchone(legacy_select_sql(table), user_id)
            return legacy_preferences_row(row) if row else None
        return row

    row = await db.fetchone(legacy_select_sql(table), user_id)
    return legacy_preferences_row(row) if row else None


async def _insert_preferences_row(
    db: DatabricksWarehousePool,
    table: str,
    user_id: str,
    values: dict[str, Any],
    *,
    include_lz_column: bool,
) -> None:
    if include_lz_column:
        try:
            await db.execute(
                f"""
                INSERT INTO {table} (
                    user_id,
                    show_pipeline,
                    show_cluster,
                    show_cost,
                    show_security,
                    show_governance,
                    show_collector_status,
                    min_severity,
                    hide_info,
                    email_enabled,
                    teams_digest_enabled,
                    notification_lz_ids,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp())
                """,
                user_id,
                values["show_pipeline"],
                values["show_cluster"],
                values["show_cost"],
                values["show_security"],
                values["show_governance"],
                values["show_collector_status"],
                values["min_severity"],
                values["hide_info"],
                values["email_enabled"],
                values["teams_digest_enabled"],
                values["notification_lz_ids"],
            )
            return
        except Exception as exc:
            if not is_missing_notification_lz_column_error(exc):
                raise

    await db.execute(
        f"""
        INSERT INTO {table} (
            user_id,
            show_pipeline,
            show_cluster,
            show_cost,
            show_security,
            show_governance,
            show_collector_status,
            min_severity,
            hide_info,
            email_enabled,
            teams_digest_enabled,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp())
        """,
        user_id,
        values["show_pipeline"],
        values["show_cluster"],
        values["show_cost"],
        values["show_security"],
        values["show_governance"],
        values["show_collector_status"],
        values["min_severity"],
        values["hide_info"],
        values["email_enabled"],
        values["teams_digest_enabled"],
    )


async def _update_preferences_row(
    db: DatabricksWarehousePool,
    table: str,
    user_id: str,
    values: dict[str, Any],
    *,
    include_lz_column: bool,
) -> None:
    if include_lz_column:
        try:
            await db.execute(
                f"""
                UPDATE {table}
                SET
                    show_pipeline = ?,
                    show_cluster = ?,
                    show_cost = ?,
                    show_security = ?,
                    show_governance = ?,
                    show_collector_status = ?,
                    min_severity = ?,
                    hide_info = ?,
                    email_enabled = ?,
                    teams_digest_enabled = ?,
                    notification_lz_ids = ?,
                    updated_at = current_timestamp()
                WHERE user_id = ?
                """,
                values["show_pipeline"],
                values["show_cluster"],
                values["show_cost"],
                values["show_security"],
                values["show_governance"],
                values["show_collector_status"],
                values["min_severity"],
                values["hide_info"],
                values["email_enabled"],
                values["teams_digest_enabled"],
                values["notification_lz_ids"],
                user_id,
            )
            return
        except Exception as exc:
            if not is_missing_notification_lz_column_error(exc):
                raise

    await db.execute(
        f"""
        UPDATE {table}
        SET
            show_pipeline = ?,
            show_cluster = ?,
            show_cost = ?,
            show_security = ?,
            show_governance = ?,
            show_collector_status = ?,
            min_severity = ?,
            hide_info = ?,
            email_enabled = ?,
            teams_digest_enabled = ?,
            updated_at = current_timestamp()
        WHERE user_id = ?
        """,
        values["show_pipeline"],
        values["show_cluster"],
        values["show_cost"],
        values["show_security"],
        values["show_governance"],
        values["show_collector_status"],
        values["min_severity"],
        values["hide_info"],
        values["email_enabled"],
        values["teams_digest_enabled"],
        user_id,
    )


async def get_preferences(
    db: DatabricksWarehousePool,
    settings: Settings,
    user_id: str,
) -> dict[str, Any]:
    """Return stored preferences or application defaults."""
    row = await _fetch_preferences_row(db, settings, user_id)
    if row is None:
        return default_preferences_response()
    return row_to_preferences(row)


async def upsert_preferences(
    db: DatabricksWarehousePool,
    settings: Settings,
    current_user: CurrentUser,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Create or replace the authenticated user's notification preferences."""
    table = _preferences_table(settings)
    existing = await _fetch_preferences_row(db, settings, current_user.id)

    values = dict(payload)
    values["notification_lz_ids"] = _sanitize_notification_lz_ids(
        values["notification_lz_ids"],
        current_user,
    )
    if existing is None:
        await _insert_preferences_row(
            db,
            table,
            current_user.id,
            values,
            include_lz_column=True,
        )
    else:
        await _update_preferences_row(
            db,
            table,
            current_user.id,
            values,
            include_lz_column=True,
        )

    row = await _fetch_preferences_row(db, settings, current_user.id)
    if row is not None:
        return row_to_preferences(row)
    return preferences_with_timestamp(**values)
