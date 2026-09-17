"""Pipeline metrics queries — ADF (Azure) and Glue/EMR (AWS).

Kept out of the route per the route→service→pool pattern.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ...db.connection import DatabricksWarehousePool
from ..routes._lz_filter import add_scope_lz_filter

__all__ = ["PIPELINE_TYPE_SQL", "fetch_pipeline_runs", "fetch_pipelines", "row_to_pipeline"]

PIPELINE_TYPE_SQL = """
CASE
    WHEN pipeline_id LIKE 'databricks:job:%' THEN 'databricks_job'
    WHEN factory_name IS NOT NULL THEN 'adf'
    WHEN glue_job_name IS NOT NULL THEN 'glue_job'
    WHEN LOWER(cloud_provider) = 'azure' THEN 'adf'
    WHEN LOWER(cloud_provider) = 'aws' THEN 'glue_job'
    ELSE NULL
END
"""


def row_to_pipeline(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "pipeline_id": row["pipeline_id"],
        "pipeline_name": row["pipeline_name"],
        "cloud_provider": row["cloud_provider"],
        "source_lz_id": row["source_lz_id"],
        "pipeline_type": row.get("pipeline_type"),
        "trigger_type": row["trigger_type"],
        "status": row["status"],
        "start_time": row["start_time"].isoformat() if row["start_time"] else None,
        "end_time": row["end_time"].isoformat() if row["end_time"] else None,
        "duration_seconds": row["duration_seconds"],
        "error_message": row["error_message"],
    }


async def fetch_pipelines(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    cloud_provider: str | None = None,
    pipeline_type: str | None = None,
    status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Pipeline runs with optional filtering and cursor-style pagination.

    Ordered by ``start_time DESC`` (most recent first).
    """
    conditions: list[str] = []
    args: list[Any] = []
    add_scope_lz_filter(
        conditions,
        args,
        allowed_lz_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )

    if cloud_provider:
        conditions.append("cloud_provider = ?")
        args.append(cloud_provider)
    if pipeline_type:
        conditions.append(f"LOWER({PIPELINE_TYPE_SQL}) = LOWER(?)")
        args.append(pipeline_type)
    if status:
        conditions.append("status = ?")
        args.append(status)
    if start_date:
        conditions.append("CAST(start_time AS DATE) >= ?")
        args.append(start_date)
    if end_date:
        conditions.append("CAST(start_time AS DATE) <= ?")
        args.append(end_date)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    total: int = (
        await db.fetchscalar(
            "SELECT COUNT(*) "
            f"FROM {db.table('curated_pipeline_metrics')} "
            f"{where}",
            *args,
        )
        or 0
    )

    rows = await db.fetchall(
        f"""
         SELECT run_id, pipeline_id, pipeline_name, cloud_provider, source_lz_id,
             {PIPELINE_TYPE_SQL} AS pipeline_type, trigger_type, status, start_time, end_time,
             duration_seconds, error_message
        FROM {db.table('curated_pipeline_metrics')}
        {where}
        ORDER BY start_time DESC
        LIMIT ? OFFSET ?
        """,
        *args,
        limit,
        offset,
    )

    return {
        "items": [row_to_pipeline(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


async def fetch_pipeline_runs(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    pipeline_name: str,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Chronological execution history for a specific pipeline.

    Ordered by ``start_time DESC`` (most recent first).
    """
    conditions: list[str] = ["pipeline_name = ?"]
    args: list[Any] = [pipeline_name]
    add_scope_lz_filter(
        conditions,
        args,
        allowed_lz_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )

    if start_date:
        conditions.append("CAST(start_time AS DATE) >= ?")
        args.append(start_date)
    if end_date:
        conditions.append("CAST(start_time AS DATE) <= ?")
        args.append(end_date)

    where = "WHERE " + " AND ".join(conditions)

    rows = await db.fetchall(
        f"""
        SELECT run_id, pipeline_id, pipeline_name, cloud_provider, source_lz_id,
               {PIPELINE_TYPE_SQL} AS pipeline_type, trigger_type, status, start_time, end_time,
               duration_seconds, error_message
        FROM {db.table('curated_pipeline_metrics')}
        {where}
        ORDER BY start_time DESC
        LIMIT ?
        """,
        *args,
        limit,
    )

    return {
        "pipeline_name": pipeline_name,
        "runs": [row_to_pipeline(r) for r in rows],
    }
