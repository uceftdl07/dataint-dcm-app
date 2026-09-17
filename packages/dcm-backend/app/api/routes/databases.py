"""Database health and performance endpoints.

Routes
------
GET /api/v1/databases    Latest health snapshot per database (DISTINCT ON db_id).

Uses the same ``DISTINCT ON (db_id) ORDER BY db_id, collected_at DESC``
pattern as the clusters endpoint so that only the most recent observation
per database is returned, even when multiple historical rows exist.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Query
from fastapi.routing import APIRouter

from ...auth.dependencies import get_allowed_lz_ids
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.databases_page import fetch_databases
from ._lz_filter import SourceLzIdQuery, SourceLzIdsQuery

__all__ = ["router"]

router = APIRouter()


@router.get("")
async def list_databases(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    cloud_provider: str | None = Query(default=None),
    db_type: str | None = Query(
        default=None,
        description=(
            "sqlserver|postgresql|mysql|cosmosdb|redshift|rds_mysql|rds_postgres|rds_oracle|aurora"
        ),
    ),
    is_available: bool | None = Query(default=None),
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
) -> dict[str, Any]:
    """Return the latest health snapshot for each monitored database."""
    items = await fetch_databases(
        db,
        allowed_lz_ids,
        cloud_provider=cloud_provider,
        db_type=db_type,
        is_available=is_available,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )
    return {"items": items}
