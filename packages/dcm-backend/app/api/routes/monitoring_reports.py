"""Monitoring reports endpoints — bundled page data for /monitoringreports.

``GET /api/v1/monitoring-reports/full``  All monitoring report sections in one response.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import Depends, Query, Request
from fastapi.routing import APIRouter

from ...auth.dependencies import get_allowed_lz_ids
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.monitoring_reports_bundle import fetch_monitoring_reports_full
from ._lz_filter import SourceLzIdQuery, SourceLzIdsQuery

__all__ = ["router"]

router = APIRouter()


@router.get("/full")
async def get_monitoring_reports_full(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    start_date: date | None = Query(
        default=None, description="Filter start (default: last 30 days)"
    ),
    end_date: date | None = Query(default=None, description="Filter end (default: today)"),
    cloud_provider: str | None = Query(default=None, description='"azure" | "aws" | null (all)'),
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    subscription_or_account_id: str | None = Query(default=None),
    usage_limit: int = Query(default=200, ge=1, le=500),
    list_limit: int = Query(default=200, ge=1, le=500),
    trend_grain: str = Query(default="day", description="day|week|month"),
) -> dict[str, Any]:
    """Return usage, governance, costs, and preview lists in one call."""
    return await fetch_monitoring_reports_full(
        request,
        db,
        allowed_lz_ids,
        start_date=start_date,
        end_date=end_date,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        subscription_or_account_id=subscription_or_account_id,
        usage_limit=usage_limit,
        list_limit=list_limit,
        trend_grain=trend_grain,
    )
