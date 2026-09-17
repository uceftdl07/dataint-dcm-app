"""Administration and collector callback endpoints for collector freshness."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, Header, Request
from fastapi.routing import APIRouter
from pydantic import BaseModel, Field

from ...auth.dependencies import CurrentUser
from ...auth.scope import require_platform_admin
from ...config import Settings
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.admin_collectors_page import (
    fetch_collector_status,
    fetch_collector_status_for_lz,
    upsert_collector_status,
    verify_collector_key,
)

__all__ = ["router"]

router = APIRouter()


class CollectorStatusUpsert(BaseModel):
    lz_id: str
    collector_name: str = Field(min_length=1, max_length=120)
    last_run_at: datetime | None = None
    last_run_status: str | None = None
    last_run_duration_s: float | None = None
    metrics_collected: int | None = Field(default=None, ge=0)
    last_error: str | None = None


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/admin/collectors/status")
async def list_collector_status(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await fetch_collector_status(db, _settings(request))


@router.get("/admin/collectors/status/{lz_id}")
async def get_collector_status_for_lz(
    lz_id: str,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await fetch_collector_status_for_lz(db, _settings(request), lz_id)


@router.post("/admin/collectors/status")
async def upsert_collector_status_route(
    payload: CollectorStatusUpsert,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    x_collector_key: Annotated[str | None, Header(alias="X-Collector-Key")] = None,
) -> dict[str, Any]:
    settings = _settings(request)
    verify_collector_key(settings, x_collector_key)
    await upsert_collector_status(
        db,
        settings,
        lz_id=payload.lz_id,
        collector_name=payload.collector_name,
        last_run_at=payload.last_run_at,
        last_run_status=payload.last_run_status,
        last_run_duration_s=payload.last_run_duration_s,
        metrics_collected=payload.metrics_collected,
        last_error=payload.last_error,
    )
    return {"status": "ok", "lz_id": payload.lz_id, "collector_name": payload.collector_name}
