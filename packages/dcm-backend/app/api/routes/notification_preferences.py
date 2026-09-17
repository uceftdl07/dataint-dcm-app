"""Per-user notification display preferences (Settings)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.routing import APIRouter
from pydantic import BaseModel, field_validator

from ...auth.dependencies import CurrentUser, get_current_user
from ...config import Settings
from ...db.connection import DatabricksWarehousePool, get_db
from ...notification.defaults import MIN_SEVERITIES
from ..services.notification_preferences_page import get_preferences, upsert_preferences

__all__ = ["router"]

router = APIRouter()


class NotificationPreferencesPayload(BaseModel):
    show_pipeline: bool = True
    show_cluster: bool = True
    show_cost: bool = True
    show_security: bool = True
    show_governance: bool = True
    show_collector_status: bool = True
    min_severity: str = "warning"
    hide_info: bool = False
    email_enabled: bool = False
    teams_digest_enabled: bool = False
    notification_lz_ids: list[str] = []

    @field_validator("min_severity")
    @classmethod
    def validate_min_severity(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in MIN_SEVERITIES:
            raise ValueError("min_severity must be info, warning or critical")
        return normalized

    @field_validator("notification_lz_ids")
    @classmethod
    def validate_notification_lz_ids(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for lz_id in value:
            cleaned = lz_id.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)
        return normalized


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/users/me/notification-preferences")
async def get_notification_preferences(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    """Return stored preferences or application defaults."""
    return await get_preferences(db, _settings(request), current_user.id)


@router.put("/users/me/notification-preferences")
async def upsert_notification_preferences(
    payload: NotificationPreferencesPayload,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    """Create or replace the authenticated user's notification preferences."""
    return await upsert_preferences(db, _settings(request), current_user, payload.model_dump())
