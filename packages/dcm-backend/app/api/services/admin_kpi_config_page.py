"""KPI visual threshold configuration — reads/writes ``dcm_kpi_config``.

Kept out of the route per the route→service→pool pattern.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_table

__all__ = ["load_config", "update_config", "validate_thresholds"]

_THRESHOLD_PAIRS = (
    ("pipeline_failure_rate_warning_pct", "pipeline_failure_rate_critical_pct", False),
    ("cluster_error_rate_warning_pct", "cluster_error_rate_critical_pct", False),
    ("cost_overrun_warning_pct", "cost_overrun_critical_pct", False),
    ("open_alerts_warning_count", "open_alerts_critical_count", False),
    ("compliance_score_warning_pct", "compliance_score_critical_pct", True),
)


def _row_to_config(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "config_key": row["config_key"],
        "config_value": float(row["config_value"]),
        "description": row["description"],
        "updated_by": row["updated_by"],
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


async def load_config(
    db: DatabricksWarehousePool,
    settings: Settings,
) -> tuple[list[dict[str, Any]], dict[str, float]]:
    table = qualified_table(settings, "dcm_kpi_config")
    rows = await db.fetchall(
        f"""
        SELECT config_key, config_value, description, updated_by, updated_at
        FROM {table}
        ORDER BY config_key
        """
    )
    items = [_row_to_config(row) for row in rows]
    values = {item["config_key"]: item["config_value"] for item in items}
    return items, values


def validate_thresholds(values: dict[str, float]) -> None:
    for warning_key, critical_key, inverted in _THRESHOLD_PAIRS:
        if warning_key not in values or critical_key not in values:
            continue
        warning = values[warning_key]
        critical = values[critical_key]
        invalid = warning <= critical if inverted else warning >= critical
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Inconsistent KPI thresholds for {warning_key}/{critical_key}",
            )


async def update_config(
    db: DatabricksWarehousePool,
    settings: Settings,
    values: dict[str, float],
    updated_by: str,
) -> None:
    table = qualified_table(settings, "dcm_kpi_config")
    for key, value in values.items():
        await db.execute(
            f"""
            UPDATE {table}
            SET config_value = ?, updated_by = ?, updated_at = current_timestamp()
            WHERE config_key = ?
            """,
            value,
            updated_by,
            key,
        )
