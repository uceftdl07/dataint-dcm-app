"""Admin bundle endpoint — all administration data in one response."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Query, Request
from fastapi.routing import APIRouter

from ...auth.dependencies import CurrentUser
from ...auth.scope import require_platform_admin
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.admin_bundle import fetch_admin_full

__all__ = ["router"]

router = APIRouter()


@router.get("/admin/full")
async def get_admin_full(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
    access_request_status: Annotated[str | None, Query(alias="accessRequestStatus")] = None,
    access_request_limit: Annotated[int, Query(alias="accessRequestLimit", ge=1, le=500)] = 10,
    access_request_offset: Annotated[int, Query(alias="accessRequestOffset", ge=0)] = 0,
    audit_limit: Annotated[int, Query(alias="auditLimit", ge=1, le=500)] = 100,
    audit_offset: Annotated[int, Query(alias="auditOffset", ge=0)] = 0,
    sections: Annotated[str | None, Query(description="all | core | extended | comma-separated keys")] = None,
) -> dict[str, Any]:
    """Return users, landing zones, alerts, collectors, access requests and audit data in one call."""
    return await fetch_admin_full(
        request,
        db,
        actor,
        access_request_status=access_request_status,
        access_request_limit=access_request_limit,
        access_request_offset=access_request_offset,
        audit_limit=audit_limit,
        audit_offset=audit_offset,
        sections=sections,
    )
