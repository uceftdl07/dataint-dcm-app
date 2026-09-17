"""Administration endpoints for alert notification channels."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Request, status
from fastapi.routing import APIRouter
from pydantic import BaseModel, Field, field_validator

from ...auth.dependencies import CurrentUser
from ...auth.notifier import SUPPORTED_CHANNEL_TYPES
from ...auth.scope import require_platform_admin
from ...config import Settings
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.admin_channels_page import (
    create_channel,
    delete_channel,
    fetch_channels,
    test_channel_notification,
    update_channel,
)

__all__ = ["router"]

router = APIRouter()


class NotificationChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    channel_type: str
    config: dict[str, Any]
    is_active: bool = True

    @field_validator("channel_type")
    @classmethod
    def validate_channel_type(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in SUPPORTED_CHANNEL_TYPES:
            raise ValueError("channel_type must be teams or email")
        return normalized


class NotificationChannelPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    config: dict[str, Any] | None = None
    is_active: bool | None = None


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/admin/notification-channels")
async def list_notification_channels(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await fetch_channels(db, _settings(request))


@router.post("/admin/notification-channels", status_code=status.HTTP_201_CREATED)
async def create_notification_channel(
    payload: NotificationChannelCreate,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await create_channel(
        db,
        _settings(request),
        actor,
        request,
        name=payload.name,
        channel_type=payload.channel_type,
        config=payload.config,
        is_active=payload.is_active,
    )


@router.patch("/admin/notification-channels/{channel_id}")
async def update_notification_channel(
    channel_id: str,
    payload: NotificationChannelPatch,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await update_channel(
        db,
        _settings(request),
        actor,
        request,
        channel_id,
        payload.model_dump(exclude_unset=True),
    )


@router.delete("/admin/notification-channels/{channel_id}")
async def delete_notification_channel(
    channel_id: str,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await delete_channel(db, _settings(request), actor, request, channel_id)


@router.post("/admin/notification-channels/{channel_id}/test")
async def test_channel(
    channel_id: str,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await test_channel_notification(db, _settings(request), channel_id)
