"""Access request endpoints — unauthenticated endpoint for requesting DCM access."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Query, Request, status
from fastapi.routing import APIRouter
from pydantic import BaseModel, Field, field_validator

from ...auth.dependencies import CurrentUser, get_current_user
from ...config import Settings
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.access_requests_page import (
    create_lz_scope_extension_request,
    create_request,
    fetch_landing_zones_for_request_form,
    fetch_registration_status,
)

__all__ = ["router"]

router = APIRouter()


class AccessRequestCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=255)
    entra_oid: str | None = None
    justification: str = Field(min_length=10, max_length=2000)
    requested_lz_ids: list[str] = Field(default_factory=list)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("email must be a valid address")
        return normalized

    @field_validator("justification")
    @classmethod
    def validate_justification(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 10:
            raise ValueError("justification must be at least 10 characters")
        return stripped


class LzScopeRequestCreate(BaseModel):
    requested_lz_ids: list[str] = Field(min_length=1)
    justification: str = Field(min_length=10, max_length=2000)

    @field_validator("justification")
    @classmethod
    def validate_justification(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 10:
            raise ValueError("justification must be at least 10 characters")
        return stripped

    @field_validator("requested_lz_ids")
    @classmethod
    def validate_requested_lz_ids(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if not normalized:
            raise ValueError("requested_lz_ids must contain at least one landing zone")
        return normalized


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.post("/access-requests", status_code=status.HTTP_201_CREATED)
async def create_access_request(
    payload: AccessRequestCreate,
    request: Request,
) -> dict[str, Any]:
    """Create a new access request (unauthenticated).

    This endpoint does NOT require authentication - it's for users who are not
    yet registered in DCM. The request is stored in the database and a Teams
    notification is sent to admins.

    Args:
        payload: Access request details
        request: FastAPI request object

    Returns:
        dict: Created request with id and status

    Raises:
        HTTPException: 409 if user already exists or has pending request
    """
    settings = _settings(request)
    db: DatabricksWarehousePool = request.app.state.db_pool
    return await create_request(db, settings, payload)


@router.get("/access-requests/status")
async def get_registration_status(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    email: Annotated[str, Query(min_length=3, max_length=320)],
) -> dict[str, Any]:
    """Check whether an email is registered in DCM (unauthenticated)."""
    return await fetch_registration_status(db, _settings(request), email)


@router.get("/access-requests/landing-zones")
async def list_access_request_landing_zones(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> dict[str, Any]:
    """Public catalog of monitored landing zones for access-request forms."""
    return await fetch_landing_zones_for_request_form(db, _settings(request))


@router.post("/users/me/lz-access-requests", status_code=status.HTTP_201_CREATED)
async def request_lz_scope_extension(
    payload: LzScopeRequestCreate,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    """Allow an active DCM user to request additional landing zone scope."""
    return await create_lz_scope_extension_request(db, _settings(request), current_user, payload)
