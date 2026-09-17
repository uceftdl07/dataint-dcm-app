"""Security alerts endpoints.

Routes
------
GET /api/v1/security/alerts              List security alerts with filtering and pagination.
GET /api/v1/security/alerts/page-bundle  Alerts list + total in one cached response.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import Depends, Query
from fastapi.routing import APIRouter

from ...auth.dependencies import get_allowed_lz_ids
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.alerts_page import fetch_alerts_page_bundle, fetch_security_alerts
from ..services.security_serializers import row_to_alert
from ._lz_filter import SourceLzIdQuery, SourceLzIdsQuery

__all__ = ["router"]

router = APIRouter()


def _row_to_alert(row: dict[str, Any]) -> dict[str, Any]:
    return row_to_alert(row)


@router.get("/alerts/page-bundle")
async def security_alerts_page_bundle(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    cloud_provider: str | None = Query(default=None),
    start_date: date | None = Query(default=None, description="Filter by detected_at date"),
    end_date: date | None = Query(default=None, description="Filter by detected_at date"),
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    limit: int = Query(default=200, ge=1, le=200),
) -> dict[str, Any]:
    """Return security alerts list + total in one cached response (all statuses)."""
    return await fetch_alerts_page_bundle(
        db,
        allowed_lz_ids,
        cloud_provider=cloud_provider,
        start_date=start_date,
        end_date=end_date,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        limit=limit,
    )


@router.get("/alerts")
async def list_security_alerts(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    severity: str | None = Query(default=None, description="low|medium|high|critical"),
    status: str | None = Query(default="active", description="active|resolved|dismissed"),
    cloud_provider: str | None = Query(default=None),
    start_date: date | None = Query(default=None, description="Filter by detected_at date"),
    end_date: date | None = Query(default=None, description="Filter by detected_at date"),
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Return security alerts ordered by severity (critical → low) then detection time.

    Default filter is ``status=active`` — pass ``status=null`` to disable.
    Pagination uses limit / offset.
    """
    return await fetch_security_alerts(
        db,
        allowed_lz_ids,
        severity=severity,
        status=status,
        cloud_provider=cloud_provider,
        start_date=start_date,
        end_date=end_date,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        limit=limit,
        offset=offset,
    )
