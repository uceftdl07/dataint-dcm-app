"""Authentication introspection endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.routing import APIRouter

from ...auth.dependencies import CurrentUser, get_current_user, is_platform_admin
from ...auth.role_permissions import (
    PLATFORM_ADMIN_ROLE,
    get_role_permissions,
    permissions_payload,
)
from ...config import Settings
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.auth_page import fetch_user_projects

__all__ = ["router"]

router = APIRouter()


@router.get("/auth/me")
async def get_me(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> dict[str, Any]:
    """Return the authenticated DCM user, their platform role and project memberships.

    ``projects`` is the list of projects the user belongs to (any status), each
    with the readable name and the user's project role — feeds the frontend
    project switcher and self-service views (feature 015). Kept snake_case for
    consistency with the pre-existing fields of this endpoint.
    """
    settings: Settings = request.app.state.settings
    membership_rows = await fetch_user_projects(db, settings, current_user.id)
    return {
        "id": current_user.id,
        "entra_oid": current_user.entra_oid,
        "email": current_user.email,
        "display_name": current_user.display_name,
        "role": current_user.role,
        # Effective, not raw: a legacy row whose authority still lives in ``role``
        # is reported as a platform admin so the frontend gate and the backend
        # guards agree on exactly one answer.
        "platform_role": (
            PLATFORM_ADMIN_ROLE if is_platform_admin(current_user) else current_user.platform_role
        ),
        "is_active": current_user.is_active,
        "lz_ids": current_user.lz_ids,
        # The scope actually applied to every read, so "why do I see everything?"
        # is answerable in one request: ``unrestricted`` on an account that is not
        # a platform admin means a legacy ``role`` still grants full access
        # (``LEGACY_UNRESTRICTED_ROLES``, kept for the transition), while empty
        # lists mean the account belongs to no *active* project and sees nothing.
        "scope": {
            "unrestricted": current_user.scope.unrestricted,
            "lz_ids": current_user.scope.lz_ids,
            "workspace_ids": current_user.scope.workspace_ids,
        },
        "projects": membership_rows,
    }


@router.get("/auth/permissions")
async def get_permissions(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> dict[str, Any]:
    """Return portal pages, dashboard widgets and features allowed for the current role."""
    settings: Settings = request.app.state.settings
    permissions = await get_role_permissions(
        db, settings, current_user.role, current_user.platform_role
    )
    return permissions_payload(current_user.role, permissions)
