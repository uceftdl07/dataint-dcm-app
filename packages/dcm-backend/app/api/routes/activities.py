"""Activity run endpoints — ADF activity details and Glue job step metrics.

Routes
------
GET /api/v1/activities
    List activity runs with filtering by pipeline_run_id, cloud, status, date range.
    Supports pagination.  Ordered by start_time DESC.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import Depends, Query
from fastapi.routing import APIRouter

from ...auth.dependencies import get_allowed_lz_ids
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.activities_page import fetch_activities
from ._lz_filter import SourceLzIdQuery, SourceLzIdsQuery

__all__ = ["router"]

router = APIRouter()


@router.get("/activities")
async def list_activities(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    # Filters
    pipeline_run_id: Annotated[
        str | None, Query(description="Filter by parent pipeline run ID.")
    ] = None,
    pipeline_name: Annotated[
        str | None, Query(description="Filter by pipeline name (partial match).")
    ] = None,
    cloud_provider: Annotated[
        str | None, Query(description="Filter by cloud provider (azure|aws).")
    ] = None,
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    subscription_or_account_id: Annotated[
        str | None, Query(description="Filter by Azure subscription or AWS account ID.")
    ] = None,
    status: Annotated[
        str | None,
        Query(description="Filter by status (succeeded|failed|running|cancelled|skipped)."),
    ] = None,
    activity_type: Annotated[
        str | None, Query(description="Filter by activity type (copy|databricks_notebook|…).")
    ] = None,
    start_date: Annotated[
        date | None, Query(description="Include activities that started on or after this date.")
    ] = None,
    end_date: Annotated[
        date | None, Query(description="Include activities that started on or before this date.")
    ] = None,
    # Pagination
    limit: Annotated[int, Query(ge=1, le=500, description="Max rows to return.")] = 100,
    offset: Annotated[int, Query(ge=0, description="Rows to skip.")] = 0,
) -> dict[str, Any]:
    """Return activity run details, optionally filtered by parent pipeline run."""
    return await fetch_activities(
        db,
        allowed_lz_ids,
        pipeline_run_id=pipeline_run_id,
        pipeline_name=pipeline_name,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        subscription_or_account_id=subscription_or_account_id,
        status=status,
        activity_type=activity_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
