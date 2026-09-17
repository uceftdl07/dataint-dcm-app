"""Cost and FinOps endpoints.

Routes
------
GET /api/v1/costs/summary      Total cost + breakdown by cloud and top services.
GET /api/v1/costs/by-service   Per-service cost aggregation with optional filters.
GET /api/v1/costs/page-bundle  Summary + by-service in one cached response.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import Depends, Query
from fastapi.routing import APIRouter

from ...auth.dependencies import get_allowed_lz_ids
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.finops_page import (
    fetch_cost_summary,
    fetch_costs_by_service,
    fetch_finops_page_bundle,
)
from ._lz_filter import SourceLzIdQuery, SourceLzIdsQuery

__all__ = ["router"]

router = APIRouter()


@router.get("/summary")
async def get_cost_summary(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    cloud_provider: str | None = Query(default=None),
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
) -> dict[str, Any]:
    """Return cost summary KPIs for the requested period."""
    return await fetch_cost_summary(
        db,
        allowed_lz_ids,
        start_date=start_date,
        end_date=end_date,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )


@router.get("/by-service")
async def get_costs_by_service(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    cloud_provider: str | None = Query(default=None),
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
) -> dict[str, Any]:
    """Return cost broken down by service, account, and cloud provider."""
    return await fetch_costs_by_service(
        db,
        allowed_lz_ids,
        start_date=start_date,
        end_date=end_date,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )


@router.get("/page-bundle")
async def costs_page_bundle(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    cloud_provider: str | None = Query(default=None),
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
) -> dict[str, Any]:
    """Return cost summary + by-service breakdown in one cached response."""
    return await fetch_finops_page_bundle(
        db,
        allowed_lz_ids,
        start_date=start_date,
        end_date=end_date,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )
