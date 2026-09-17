"""Compute metrics endpoints — Databricks and EMR.

Routes
------
GET /api/v1/compute    Latest state per compute resource (using ROW_NUMBER for Databricks).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Query
from fastapi.routing import APIRouter

from ...auth.scope import AllowedScope, get_allowed_scope_dep
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.clusters_page import fetch_compute
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


@router.get("")
async def list_compute(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    scope: Annotated[AllowedScope, Depends(get_allowed_scope_dep)],
    cloud_provider: str | None = Query(default=None),
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    state: str | None = Query(default=None, description="running|terminated|error|unknown"),
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
) -> dict[str, Any]:
    """Return the latest snapshot for each monitored compute resource."""
    return await fetch_compute(
        db,
        scope,
        cloud_provider=cloud_provider,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        state=state,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )
