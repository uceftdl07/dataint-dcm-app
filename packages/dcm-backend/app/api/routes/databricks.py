"""Databricks-specific endpoints.

Routes
------
GET /api/v1/databricks/workspaces              List Databricks workspaces (names preferred).
GET /api/v1/databricks/full                    Bundled Databricks page data in one call.
GET /api/v1/databricks/embedded-dashboards     List embeddable AI/BI dashboards from Unity Catalog.
GET /api/v1/databricks/embedded-dashboards/{slug}  Return one embeddable dashboard by slug.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import Depends, Query, Request
from fastapi.routing import APIRouter

from ...auth.dependencies import get_allowed_lz_ids, get_allowed_workspace_ids
from ...auth.scope import AllowedScope, get_allowed_scope_dep
from ...config import Settings
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.databricks_bundle import fetch_databricks_full
from ..services.databricks_workspaces_page import fetch_workspaces
from ..services.embedded_dashboards import (
    fetch_embedded_dashboard_by_slug,
    fetch_embedded_dashboards,
)
from ._lz_filter import SourceLzIdQuery, SourceLzIdsQuery

__all__ = ["router"]

router = APIRouter()


def _settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[attr-defined, no-any-return]


WorkspaceIdQuery = Annotated[
    str | None,
    Query(description="Filter by a single Databricks workspace ID."),
]
WorkspaceIdsQuery = Annotated[
    list[str] | None,
    Query(description="Filter by one or more Databricks workspace IDs."),
]


@router.get("/full")
async def get_databricks_full(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[list[str] | None, Depends(get_allowed_workspace_ids)],
    start_date: date | None = Query(default=None, description="Filter start (default: last 30 days)"),
    end_date: date | None = Query(default=None, description="Filter end (default: today)"),
    cloud_provider: str | None = Query(default=None, description='"azure" | "aws" | null (all)'),
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    subscription_or_account_id: str | None = Query(default=None),
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    list_limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """Return computes, governance, pipelines, activities, costs, alerts and checks in one call."""
    return await fetch_databricks_full(
        db,
        allowed_lz_ids,
        allowed_workspace_ids,
        start_date=start_date,
        end_date=end_date,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        subscription_or_account_id=subscription_or_account_id,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        list_limit=list_limit,
    )


@router.get("/workspaces")
async def list_workspaces(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    scope: Annotated[AllowedScope, Depends(get_allowed_scope_dep)],
) -> dict[str, Any]:
    """List Databricks workspaces with ARM names when available."""
    return await fetch_workspaces(db, _settings(request), scope)


@router.get("/embedded-dashboards")
async def list_embedded_dashboards(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    menu_group: str | None = Query(default="insights", description="Menu group for embedded dashboards."),
) -> dict[str, Any]:
    """Return embeddable Databricks AI/BI dashboards configured in Unity Catalog."""
    items = await fetch_embedded_dashboards(
        db,
        _settings(request),
        allowed_lz_ids=allowed_lz_ids,
        menu_group=menu_group,
    )
    return {"items": items}


@router.get("/embedded-dashboards/{slug}")
async def get_embedded_dashboard(
    slug: str,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
) -> dict[str, Any]:
    """Return one embeddable Databricks AI/BI dashboard by slug."""
    return await fetch_embedded_dashboard_by_slug(
        db,
        _settings(request),
        slug=slug,
        allowed_lz_ids=allowed_lz_ids,
    )
