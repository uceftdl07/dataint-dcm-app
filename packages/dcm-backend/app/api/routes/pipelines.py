"""Pipeline metrics endpoints — ADF (Azure) and Glue/EMR (AWS).

Routes
------
GET /api/v1/pipelines                    List pipeline runs (paginated, filterable).
GET /api/v1/pipelines/{name}/runs        Execution history for one pipeline.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import Depends, Query
from fastapi.routing import APIRouter

from ...auth.dependencies import get_allowed_lz_ids
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.pipelines_page import fetch_pipeline_runs, fetch_pipelines
from ._lz_filter import SourceLzIdQuery, SourceLzIdsQuery

__all__ = ["router"]

router = APIRouter()


@router.get("")
async def list_pipelines(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    cloud_provider: str | None = Query(default=None),
    pipeline_type: str | None = Query(
        default=None, description="adf|glue_job|databricks_job derived from Unity Catalog columns."
    ),
    status: str | None = Query(default=None, description="running|succeeded|failed|cancelled"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List pipeline runs with optional filtering and cursor-style pagination."""
    return await fetch_pipelines(
        db,
        allowed_lz_ids,
        cloud_provider=cloud_provider,
        pipeline_type=pipeline_type,
        status=status,
        start_date=start_date,
        end_date=end_date,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        limit=limit,
        offset=offset,
    )


@router.get("/{pipeline_name}/runs")
async def get_pipeline_runs(
    pipeline_name: str,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """Get chronological execution history for a specific pipeline."""
    return await fetch_pipeline_runs(
        db,
        allowed_lz_ids,
        pipeline_name,
        start_date=start_date,
        end_date=end_date,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        limit=limit,
    )
