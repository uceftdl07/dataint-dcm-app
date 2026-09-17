"""Admin and public endpoints for maintenance windows."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import Depends, Request, status
from fastapi.routing import APIRouter
from pydantic import BaseModel, Field, model_validator

from ...auth.dependencies import CurrentUser, get_current_user
from ...auth.scope import require_platform_admin
from ...config import Settings
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.admin_maintenance_page import (
    MAX_WINDOW_DURATION,
    create_window,
    delete_window,
    fetch_active_windows,
    fetch_windows,
    update_window,
)

__all__ = ["router"]

router = APIRouter()


class MaintenanceWindowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    lz_ids: list[str] | None = None
    starts_at: datetime
    ends_at: datetime
    suppress_alerts: bool = True

    @model_validator(mode="after")
    def validate_window(self) -> MaintenanceWindowCreate:
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        if self.ends_at - self.starts_at > MAX_WINDOW_DURATION:
            raise ValueError("maintenance window cannot exceed 7 days")
        return self


class MaintenanceWindowPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    lz_ids: list[str] | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    suppress_alerts: bool | None = None


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/admin/maintenance-windows")
async def list_maintenance_windows(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await fetch_windows(db, _settings(request))


@router.post("/admin/maintenance-windows", status_code=status.HTTP_201_CREATED)
async def create_maintenance_window(
    payload: MaintenanceWindowCreate,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await create_window(db, _settings(request), actor, request, payload.model_dump())


@router.patch("/admin/maintenance-windows/{window_id}")
async def update_maintenance_window(
    window_id: str,
    payload: MaintenanceWindowPatch,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await update_window(
        db,
        _settings(request),
        actor,
        request,
        window_id,
        payload.model_dump(exclude_unset=True),
    )


@router.delete("/admin/maintenance-windows/{window_id}")
async def delete_maintenance_window(
    window_id: str,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await delete_window(db, _settings(request), actor, request, window_id)


@router.get("/maintenance-windows/active")
async def get_active_maintenance_windows(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    return await fetch_active_windows(db, _settings(request))
