"""Dashboard endpoints — aggregated KPIs and bundled home page data.

``GET /api/v1/dashboard/overview``  Header KPI cards (parallel SQL).
``GET /api/v1/dashboard/full``      All dashboard sections in one response.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import Depends, Query
from fastapi.routing import APIRouter

from ...auth.dependencies import get_allowed_lz_ids, get_allowed_workspace_ids
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.dashboard_bundle import (
    _resolve_period,
    fetch_dashboard_full,
    fetch_overview_metrics,
)
from ._lz_filter import SourceLzIdQuery, SourceLzIdsQuery

__all__ = ["router"]

router = APIRouter()

WorkspaceIdQuery = Annotated[
    str | None,
    Query(description="Filter by a single Databricks workspace ID."),
]
WorkspaceIdsQuery = Annotated[
    list[str] | None,
    Query(description="Filter by one or more Databricks workspace IDs."),
]


@router.get("/overview")
async def get_dashboard_overview(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[list[str] | None, Depends(get_allowed_workspace_ids)],
    start_date: date | None = Query(
        default=None, description="Filter start (default: last 30 days)"
    ),
    end_date: date | None = Query(default=None, description="Filter end (default: today)"),
    cloud_provider: str | None = Query(default=None, description='"azure" | "aws" | null (all)'),
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
) -> dict[str, Any]:
    """Return aggregated KPIs for the dashboard header cards."""
    start, end = _resolve_period(start_date, end_date)
    return await fetch_overview_metrics(
        db,
        allowed_lz_ids,
        allowed_workspace_ids,
        start=start,
        end=end,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )


@router.get("/full")
async def get_dashboard_full(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[list[str] | None, Depends(get_allowed_workspace_ids)],
    start_date: date | None = Query(
        default=None, description="Filter start (default: last 30 days)"
    ),
    end_date: date | None = Query(default=None, description="Filter end (default: today)"),
    cloud_provider: str | None = Query(default=None, description='"azure" | "aws" | null (all)'),
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
) -> dict[str, Any]:
    """Return overview, governance, costs, and preview lists in one call."""
    return await fetch_dashboard_full(
        db,
        allowed_lz_ids,
        allowed_workspace_ids,
        start_date=start_date,
        end_date=end_date,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
    )
