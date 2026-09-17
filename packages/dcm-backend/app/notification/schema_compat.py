"""Databricks schema compatibility for notification preference columns."""

from __future__ import annotations

from typing import Any

__all__ = [
    "is_missing_notification_lz_column_error",
    "legacy_preferences_row",
]

_LEGACY_SELECT_COLUMNS = """
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
"""


def is_missing_notification_lz_column_error(exc: BaseException) -> bool:
    message = str(exc)
    return "notification_lz_ids" in message and (
        "UNRESOLVED_COLUMN" in message
        or "cannot be resolved" in message
    )


def legacy_preferences_row(row: dict[str, Any]) -> dict[str, Any]:
    """Attach empty LZ filter when the warehouse table has no LZ column yet."""
    return {**row, "notification_lz_ids": []}


def legacy_select_sql(table: str) -> str:
    return f"""
        SELECT
            {_LEGACY_SELECT_COLUMNS}
        FROM {table}
        WHERE user_id = ?
        LIMIT 1
        """
