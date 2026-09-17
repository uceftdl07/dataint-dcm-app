"""Default notification preferences and row mapping."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

__all__ = ["DEFAULT_NOTIFICATION_PREFERENCES", "row_to_preferences"]

MIN_SEVERITIES = frozenset({"info", "warning", "critical"})

DEFAULT_NOTIFICATION_PREFERENCES: dict[str, Any] = {
    "show_pipeline": True,
    "show_cluster": True,
    "show_cost": True,
    "show_security": True,
    "show_governance": True,
    "show_collector_status": True,
    "min_severity": "warning",
    "hide_info": False,
    "email_enabled": False,
    "teams_digest_enabled": False,
    "notification_lz_ids": [],
}


def row_to_preferences(row: dict[str, Any]) -> dict[str, Any]:
    """Map a warehouse row to the API response shape."""
    updated_at = row.get("updated_at")
    return {
        "show_pipeline": bool(row["show_pipeline"]),
        "show_cluster": bool(row["show_cluster"]),
        "show_cost": bool(row["show_cost"]),
        "show_security": bool(row["show_security"]),
        "show_governance": bool(row["show_governance"]),
        "show_collector_status": bool(row["show_collector_status"]),
        "min_severity": str(row["min_severity"]),
        "hide_info": bool(row["hide_info"]),
        "email_enabled": bool(row["email_enabled"]),
        "teams_digest_enabled": bool(row["teams_digest_enabled"]),
        "notification_lz_ids": list(row.get("notification_lz_ids") or []),
        "updated_at": updated_at.isoformat() if updated_at else None,
        "is_default": False,
    }


def preferences_with_timestamp(**fields: Any) -> dict[str, Any]:
    """Build a response dict including ``updated_at``."""
    now = datetime.now(UTC)
    return {
        **fields,
        "updated_at": now.isoformat(),
        "is_default": False,
    }


def default_preferences_response() -> dict[str, Any]:
    """Preferences returned when the user has no stored row yet."""
    return {
        **DEFAULT_NOTIFICATION_PREFERENCES,
        "updated_at": None,
        "is_default": True,
    }
