"""Collector freshness status — reads/writes ``dcm_collector_status``.

Kept out of the route per the route→service→pool pattern.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status

from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_table

__all__ = [
    "fetch_collector_status",
    "fetch_collector_status_for_lz",
    "upsert_collector_status",
    "verify_collector_key",
]

_STALE_AFTER = timedelta(hours=2)


def _is_stale(last_run_at: datetime | None) -> bool:
    if last_run_at is None:
        return True
    if last_run_at.tzinfo is None:
        last_run_at = last_run_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - last_run_at > _STALE_AFTER


def _row_to_status(row: dict[str, Any]) -> dict[str, Any]:
    last_run_at = row["last_run_at"]
    return {
        "lz_id": row["lz_id"],
        "collector_name": row["collector_name"],
        "last_run_at": last_run_at.isoformat() if last_run_at else None,
        "last_run_status": row["last_run_status"],
        "last_run_duration_s": row["last_run_duration_s"],
        "metrics_collected": row["metrics_collected"],
        "last_error": row["last_error"],
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
        "is_stale": _is_stale(last_run_at),
    }


def verify_collector_key(settings: Settings, collector_key: str | None) -> None:
    if not settings.collector_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DCM_COLLECTOR_API_KEY is not configured",
        )
    if collector_key != settings.collector_api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid collector key")


async def fetch_collector_status(
    db: DatabricksWarehousePool,
    settings: Settings,
) -> dict[str, Any]:
    table = qualified_table(settings, "dcm_collector_status")
    rows = await db.fetchall(
        f"""
        SELECT
            lz_id, collector_name, last_run_at, last_run_status, last_run_duration_s,
            metrics_collected, last_error, updated_at
        FROM {table}
        ORDER BY lz_id, collector_name
        """
    )
    return {"items": [_row_to_status(row) for row in rows], "total": len(rows)}


async def fetch_collector_status_for_lz(
    db: DatabricksWarehousePool,
    settings: Settings,
    lz_id: str,
) -> dict[str, Any]:
    table = qualified_table(settings, "dcm_collector_status")
    rows = await db.fetchall(
        f"""
        SELECT
            lz_id, collector_name, last_run_at, last_run_status, last_run_duration_s,
            metrics_collected, last_error, updated_at
        FROM {table}
        WHERE lz_id = ?
        ORDER BY collector_name
        """,
        lz_id,
    )
    return {"items": [_row_to_status(row) for row in rows], "total": len(rows)}


async def upsert_collector_status(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    lz_id: str,
    collector_name: str,
    last_run_at: datetime | None,
    last_run_status: str | None,
    last_run_duration_s: float | None,
    metrics_collected: int | None,
    last_error: str | None,
) -> None:
    table = qualified_table(settings, "dcm_collector_status")
    await db.execute(
        f"""
        MERGE INTO {table} AS target
        USING (
            SELECT
                ? AS lz_id,
                ? AS collector_name,
                ? AS last_run_at,
                ? AS last_run_status,
                ? AS last_run_duration_s,
                ? AS metrics_collected,
                ? AS last_error
        ) AS source
        ON target.lz_id = source.lz_id AND target.collector_name = source.collector_name
        WHEN MATCHED THEN UPDATE SET
            last_run_at = source.last_run_at,
            last_run_status = source.last_run_status,
            last_run_duration_s = source.last_run_duration_s,
            metrics_collected = source.metrics_collected,
            last_error = source.last_error,
            updated_at = current_timestamp()
        WHEN NOT MATCHED THEN INSERT
            (lz_id, collector_name, last_run_at, last_run_status, last_run_duration_s,
             metrics_collected, last_error, updated_at)
        VALUES
            (source.lz_id, source.collector_name, source.last_run_at, source.last_run_status,
             source.last_run_duration_s, source.metrics_collected, source.last_error,
             current_timestamp())
        """,
        lz_id,
        collector_name,
        last_run_at,
        last_run_status,
        last_run_duration_s,
        metrics_collected,
        last_error,
    )
