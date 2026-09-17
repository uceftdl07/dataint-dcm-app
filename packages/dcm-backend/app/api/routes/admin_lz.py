"""Administration endpoints for the Landing Zone registry."""

from __future__ import annotations

import logging
import re
from typing import Annotated, Any

from fastapi import Depends, Query, Request, status
from fastapi.routing import APIRouter
from pydantic import BaseModel, Field, field_validator

from ...auth.dependencies import CurrentUser
from ...auth.scope import require_platform_admin
from ...config import Settings
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.admin_lz_page import create_lz, deactivate_lz, fetch_lz, fetch_lzs, update_lz

__all__ = ["router"]

router = APIRouter()
logger = logging.getLogger(__name__)
_LZ_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,98}[a-z0-9]$")


class LandingZoneCreate(BaseModel):
    lz_id: str
    display_name: str
    cloud_provider: str
    region: str | None = None
    environment: str | None = None
    ba_name: str | None = None
    collector_names: list[str] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("lz_id")
    @classmethod
    def validate_lz_id(cls, value: str) -> str:
        if not _LZ_ID_PATTERN.match(value):
            raise ValueError("lz_id must match ^[a-z0-9][a-z0-9-]{2,98}[a-z0-9]$")
        return value

    @field_validator("cloud_provider")
    @classmethod
    def validate_cloud_provider(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"azure", "aws"}:
            raise ValueError("cloud_provider must be azure or aws")
        return normalized


class LandingZonePatch(BaseModel):
    display_name: str | None = None
    cloud_provider: str | None = None
    region: str | None = None
    environment: str | None = None
    ba_name: str | None = None
    collector_names: list[str] | None = None
    is_active: bool | None = None
    notes: str | None = None

    @field_validator("cloud_provider")
    @classmethod
    def validate_optional_cloud_provider(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.lower()
        if normalized not in {"azure", "aws"}:
            raise ValueError("cloud_provider must be azure or aws")
        return normalized


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/admin/landing-zones")
async def list_admin_landing_zones(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_platform_admin)],
    cloud_provider: Annotated[str | None, Query(description="Filter by cloud provider.")] = None,
    environment: Annotated[str | None, Query(description="Filter by environment.")] = None,
    is_active: Annotated[bool | None, Query(description="Filter by active flag.")] = None,
    search: Annotated[str | None, Query(description="Search by lz_id or display name.")] = None,
) -> dict[str, Any]:
    return await fetch_lzs(
        db,
        _settings(request),
        cloud_provider=cloud_provider,
        environment=environment,
        is_active=is_active,
        search=search,
    )


@router.get("/admin/landing-zones/{lz_id}")
async def get_admin_landing_zone(
    lz_id: str,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await fetch_lz(db, _settings(request), lz_id)


@router.post("/admin/landing-zones", status_code=status.HTTP_201_CREATED)
async def create_landing_zone(
    payload: LandingZoneCreate,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await create_lz(db, _settings(request), actor, request, payload)


@router.patch("/admin/landing-zones/{lz_id}")
async def update_landing_zone(
    lz_id: str,
    payload: LandingZonePatch,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await update_lz(db, _settings(request), actor, request, lz_id, payload)


@router.patch("/admin/landing-zones/{lz_id}/deactivate")
async def deactivate_landing_zone(
    lz_id: str,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await deactivate_lz(db, _settings(request), actor, request, lz_id)
