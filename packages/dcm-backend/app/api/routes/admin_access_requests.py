"""Administration endpoints for portal access request inbox."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import Depends, Query, Request
from fastapi.routing import APIRouter
from pydantic import BaseModel, Field

from ...auth.dependencies import CurrentUser
from ...auth.scope import require_platform_admin
from ...config import Settings
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.admin_access_requests_page import fetch_access_requests, review_access_request

__all__ = ["router"]

router = APIRouter()


class AccessRequestStatusPatch(BaseModel):
    status: Literal["approved", "rejected"] = Field(
        description="Review outcome after manual handling."
    )
    review_note: str | None = Field(default=None, max_length=2000)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/admin/access-requests")
async def list_admin_access_requests(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
    status_filter: Annotated[
        str | None,
        Query(alias="status", description="Filter by request status."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return await fetch_access_requests(
        db,
        _settings(request),
        actor,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )


@router.patch("/admin/access-requests/{request_id}")
async def review_admin_access_request(
    request_id: str,
    payload: AccessRequestStatusPatch,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await review_access_request(
        db,
        _settings(request),
        actor,
        request,
        request_id,
        new_status=payload.status,
        review_note=payload.review_note,
    )
