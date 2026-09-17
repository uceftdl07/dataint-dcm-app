"""Admin endpoints for embedded Databricks AI/BI dashboards."""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import Body, Depends, Request, status
from fastapi.routing import APIRouter
from pydantic import BaseModel, field_validator

from ...auth.dependencies import CurrentUser
from ...auth.scope import require_platform_admin
from ...config import Settings
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.admin_embedded_dashboards_page import (
    create_dashboard,
    delete_dashboard,
    fetch_admin_dashboards,
    update_dashboard,
)

__all__ = ["router"]

router = APIRouter()
_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$")
_SCOPE_VALUES = {"global", "workspace", "landing_zone"}


def _settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[attr-defined, no-any-return]


class EmbeddedDashboardCreate(BaseModel):
    dashboard_slug: str
    title: str
    description: str | None = None
    workspace_host: str
    workspace_id: str
    dashboard_id: str
    scope: str = "global"
    source_lz_id: str | None = None
    menu_group: str = "insights"
    sort_order: int = 0
    enabled: bool = True

    @field_validator("dashboard_slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _SLUG_PATTERN.match(normalized):
            raise ValueError("dashboard_slug must be lowercase letters, numbers and hyphens")
        return normalized

    @field_validator("workspace_host")
    @classmethod
    def validate_workspace_host(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized.startswith("https://"):
            raise ValueError("workspace_host must start with https://")
        return normalized

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in _SCOPE_VALUES:
            raise ValueError("scope must be global, workspace or landing_zone")
        return normalized


class EmbeddedDashboardUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    workspace_host: str | None = None
    workspace_id: str | None = None
    dashboard_id: str | None = None
    scope: str | None = None
    source_lz_id: str | None = None
    menu_group: str | None = None
    sort_order: int | None = None
    enabled: bool | None = None

    @field_validator("workspace_host")
    @classmethod
    def validate_workspace_host(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().rstrip("/")
        if not normalized.startswith("https://"):
            raise ValueError("workspace_host must start with https://")
        return normalized

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in _SCOPE_VALUES:
            raise ValueError("scope must be global, workspace or landing_zone")
        return normalized


@router.get("/admin/embedded-dashboards")
async def list_admin_embedded_dashboards(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await fetch_admin_dashboards(db, _settings(request))


@router.post("/admin/embedded-dashboards", status_code=status.HTTP_201_CREATED)
async def create_admin_embedded_dashboard(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
    payload: Annotated[EmbeddedDashboardCreate, Body()],
) -> dict[str, Any]:
    return await create_dashboard(db, _settings(request), actor, request, payload.model_dump())


@router.put("/admin/embedded-dashboards/{slug}")
async def update_admin_embedded_dashboard(
    slug: str,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
    payload: Annotated[EmbeddedDashboardUpdate, Body()],
) -> dict[str, Any]:
    return await update_dashboard(
        db,
        _settings(request),
        actor,
        request,
        slug,
        payload.model_dump(exclude_unset=True),
    )


@router.delete("/admin/embedded-dashboards/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_embedded_dashboard(
    slug: str,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> None:
    await delete_dashboard(db, _settings(request), actor, request, slug)
