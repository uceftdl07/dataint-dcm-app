"""Security alert serializers — no route imports."""

from __future__ import annotations

from typing import Any


def row_to_alert(row: dict[str, Any]) -> dict[str, Any]:
    alert = {
        "alert_id": row["alert_id"],
        "cloud_provider": row["cloud_provider"],
        "source_lz_id": row["source_lz_id"],
        "subscription_or_account_id": row.get("subscription_or_account_id"),
        "severity": row["severity"],
        "title": row["title"],
        "description": row["description"],
        "status": row["status"],
        "resource_id": row["resource_id"],
        "resource_type": row["resource_type"],
        "detected_at": row["detected_at"].isoformat()
        if hasattr(row["detected_at"], "isoformat")
        else str(row["detected_at"]),
    }
    alert["resolved_at"] = row.get("resolved_at") if "resolved_at" in row else None
    return alert
