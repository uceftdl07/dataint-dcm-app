"""Metric retention policy queries — reads/writes ``dcm_retention_policies``.

Kept out of the route per the route→service→pool pattern.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import HTTPException, status

from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_table

__all__ = [
    "fetch_retention_stats",
    "load_policies",
    "update_policies",
    "validate_policy_update",
]

_TABLE_NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
logger = logging.getLogger(__name__)

_RETENTION_TABLE_ALIASES = {
    "activity_runs": "curated_activity_runs",
    "cluster_metrics": "curated_compute_metrics",
    "compute_metrics": "curated_compute_metrics",
    "cost_metrics": "curated_cost_metrics",
    "database_metrics": "curated_database_metrics",
    "pipeline_metrics": "curated_pipeline_metrics",
    "security_alerts": "curated_security_alerts",
    "standard_check_evaluations": "curated_standard_checks",
    "standard_checks": "curated_standard_checks",
    "user_metrics": "curated_user_metrics",
}


def _row_to_policy(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "metric_table": row["metric_table"],
        "retention_days": int(row["retention_days"]),
        "updated_by": row["updated_by"],
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


def _physical_metric_table(metric_table: str) -> str:
    return _RETENTION_TABLE_ALIASES.get(metric_table, metric_table)


async def load_policies(
    db: DatabricksWarehousePool,
    settings: Settings,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    table = qualified_table(settings, "dcm_retention_policies")
    rows = await db.fetchall(
        f"""
        SELECT metric_table, retention_days, updated_by, updated_at
        FROM {table}
        ORDER BY metric_table
        """
    )
    items = [_row_to_policy(row) for row in rows]
    values = {item["metric_table"]: item["retention_days"] for item in items}
    return items, values


def validate_policy_update(
    values: dict[str, int],
    before_values: dict[str, int],
) -> None:
    unknown = sorted(set(values) - set(before_values))
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Unknown retention policy tables", "tables": unknown},
        )
    too_low = {key: value for key, value in values.items() if value < 7}
    if too_low:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Retention must be at least 7 days", "values": too_low},
        )


async def update_policies(
    db: DatabricksWarehousePool,
    settings: Settings,
    values: dict[str, int],
    updated_by: str,
) -> None:
    table = qualified_table(settings, "dcm_retention_policies")
    for metric_table, days in values.items():
        await db.execute(
            f"""
            UPDATE {table}
            SET retention_days = ?, updated_by = ?, updated_at = current_timestamp()
            WHERE metric_table = ?
            """,
            days,
            updated_by,
            metric_table,
        )


async def fetch_retention_stats(
    db: DatabricksWarehousePool,
    settings: Settings,
) -> dict[str, Any]:
    policies, _ = await load_policies(db, settings)
    items = []
    for policy in policies:
        metric_table = policy["metric_table"]
        physical_table = _physical_metric_table(metric_table)
        if not _TABLE_NAME_PATTERN.match(physical_table):
            continue
        try:
            qualified = qualified_table(settings, physical_table)
            detail = await db.fetchone(f"DESCRIBE DETAIL {qualified}")
        except Exception as exc:  # noqa: BLE001 - stats are best-effort for optional tables
            logger.warning(
                "Retention stats unavailable for metric_table=%s physical_table=%s: %s",
                metric_table,
                physical_table,
                exc,
            )
            detail = None
        items.append(
            {
                **policy,
                "num_files": detail.get("numFiles") if detail else None,
                "size_in_bytes": detail.get("sizeInBytes") if detail else None,
            }
        )
    return {"items": items, "total": len(items)}
