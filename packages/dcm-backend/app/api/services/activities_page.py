"""Activity run queries — ADF activity details and Glue job step metrics.

Kept out of the route per the route→service→pool pattern.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ...db.connection import DatabricksWarehousePool
from ..routes._lz_filter import add_scope_lz_filter

__all__ = ["fetch_activities", "row_to_activity"]


def row_to_activity(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "pipeline_run_id": row["pipeline_run_id"],
        "pipeline_name": row["pipeline_name"],
        "activity_name": row["activity_name"],
        "activity_type": row["activity_type"],
        "cloud_provider": row["cloud_provider"],
        "source_lz_id": row["source_lz_id"],
        "subscription_or_account_id": row["subscription_or_account_id"],
        "status": row["status"],
        "start_time": row["start_time"].isoformat() if row["start_time"] else None,
        "end_time": row["end_time"].isoformat() if row["end_time"] else None,
        "duration_seconds": row["duration_seconds"],
        "rows_read": row["rows_read"],
        "rows_written": row["rows_written"],
        "data_read_bytes": row["data_read_bytes"],
        "data_written_bytes": row["data_written_bytes"],
        "error_message": row["error_message"],
        "collected_at": row["collected_at"].isoformat(),
    }


async def fetch_activities(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    pipeline_run_id: str | None = None,
    pipeline_name: str | None = None,
    cloud_provider: str | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    subscription_or_account_id: str | None = None,
    status: str | None = None,
    activity_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Activity run details, optionally filtered by parent pipeline run.

    Typical usage:
    - Drill down from a pipeline run: ``GET /activities?pipeline_run_id=run-abc123``
    - List all failed activities across clouds: ``GET /activities?status=failed``
    - List all Copy activities in a date range:
      ``GET /activities?activity_type=copy&start_date=2026-03-01``
    """
    where_clauses: list[str] = []
    params: list[Any] = []
    add_scope_lz_filter(
        where_clauses,
        params,
        allowed_lz_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )

    if pipeline_run_id is not None:
        where_clauses.append("pipeline_run_id = ?")
        params.append(pipeline_run_id)

    if pipeline_name is not None:
        where_clauses.append("LOWER(pipeline_name) LIKE LOWER(?)")
        params.append(f"%{pipeline_name}%")

    if cloud_provider is not None:
        where_clauses.append("cloud_provider = ?")
        params.append(cloud_provider)

    if subscription_or_account_id is not None:
        where_clauses.append("subscription_or_account_id = ?")
        params.append(subscription_or_account_id)

    if status is not None:
        where_clauses.append("status = ?")
        params.append(status)

    if activity_type is not None:
        where_clauses.append("activity_type = ?")
        params.append(activity_type)

    if start_date is not None:
        where_clauses.append("start_time >= ?")
        params.append(start_date)

    if end_date is not None:
        where_clauses.append("start_time < ? + INTERVAL '1 day'")
        params.append(end_date)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    count_params = list(params)
    params.extend([limit, offset])

    rows = await db.fetchall(
        f"""
        SELECT
            pipeline_run_id, pipeline_name, activity_name, activity_type,
            cloud_provider, source_lz_id, subscription_or_account_id,
            status, start_time, end_time, duration_seconds,
            rows_read, rows_written, data_read_bytes, data_written_bytes,
            error_message, collected_at
        FROM {db.table('curated_activity_runs')}
        {where_sql}
        ORDER BY start_time DESC
        LIMIT ? OFFSET ?
        """,
        *params,
    )

    total = await db.fetchscalar(
        f"SELECT COUNT(*) FROM {db.table('curated_activity_runs')} {where_sql}",
        *count_params,
    )

    return {
        "items": [row_to_activity(row) for row in rows],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }
