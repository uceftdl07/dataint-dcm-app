"""User / identity governance endpoints.

Routes
------
GET /api/v1/users
    List user identity snapshots with filtering.  Returns the latest snapshot
    per (user_id, source_lz_id) — i.e. current state, not history.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Query
from fastapi.routing import APIRouter

from ...auth.dependencies import get_allowed_lz_ids
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.users_page import fetch_users
from ._lz_filter import SourceLzIdQuery, SourceLzIdsQuery

__all__ = ["router"]

router = APIRouter()


@router.get("/users")
async def list_users(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    cloud_provider: Annotated[
        str | None, Query(description="Filter by cloud provider (azure|aws).")
    ] = None,
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    subscription_or_account_id: Annotated[
        str | None, Query(description="Filter by Azure subscription or AWS account ID.")
    ] = None,
    user_type: Annotated[
        str | None, Query(description="Filter by user type (databricks|aws_iam|azure_ad).")
    ] = None,
    is_active: Annotated[bool | None, Query(description="Filter by active status.")] = None,
    search: Annotated[
        str | None,
        Query(description="Search by user_name or display_name (partial match)."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=1000, description="Max rows to return.")] = 100,
    offset: Annotated[int, Query(ge=0, description="Rows to skip.")] = 0,
) -> dict[str, Any]:
    """Return the current user inventory, optionally filtered."""
    return await fetch_users(
        db,
        allowed_lz_ids,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        subscription_or_account_id=subscription_or_account_id,
        user_type=user_type,
        is_active=is_active,
        search=search,
        limit=limit,
        offset=offset,
    )
