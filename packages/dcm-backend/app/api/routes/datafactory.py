"""Data Factory endpoints.

Routes
------
GET /api/v1/datafactory/full    Bundled ADF page data in one call.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import Depends, Query
from fastapi.routing import APIRouter

from ...auth.dependencies import get_allowed_lz_ids
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.datafactory_page import fetch_datafactory_page_bundle
from ._lz_filter import SourceLzIdQuery, SourceLzIdsQuery

__all__ = ["router"]

router = APIRouter()


@router.get("/full")
async def get_datafactory_full(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    start_date: date | None = Query(default=None, description="Filter start (default: last 30 days)"),
    end_date: date | None = Query(default=None, description="Filter end (default: today)"),
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    list_limit: int = Query(default=200, ge=1, le=500),
) -> dict[str, Any]:
    """Return Azure Data Factory pipeline runs and totals in one cached response."""
    return await fetch_datafactory_page_bundle(
        db,
        allowed_lz_ids,
        start_date=start_date,
        end_date=end_date,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        list_limit=list_limit,
    )
