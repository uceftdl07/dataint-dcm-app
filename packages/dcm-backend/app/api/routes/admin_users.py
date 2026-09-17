"""Administration endpoints for DCM users, roles and Landing Zone access."""

from __future__ import annotations

from typing import Annotated, Any

from dcm_commons.models.enums import ProjectRole
from fastapi import Depends, Query, Request, status
from fastapi.routing import APIRouter
from pydantic import BaseModel, Field, field_validator

from ...auth.dependencies import CurrentUser
from ...auth.role_permissions import DCM_EFFECTIVE_ROLES
from ...auth.scope import require_platform_admin
from ...config import Settings
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.admin_users_page import (
    add_user_lz_access,
    approve_user,
    create_user,
    deactivate_user,
    delete_user,
    fetch_user,
    fetch_users,
    remove_user_lz_access,
    replace_user_lz_access,
    replace_user_projects,
    update_user_role,
)

__all__ = ["router"]

router = APIRouter()
DCM_ROLES = set(DCM_EFFECTIVE_ROLES)
_PROJECT_ROLES = {role.value for role in ProjectRole}


class RolePatch(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in DCM_ROLES:
            raise ValueError(f"role must be one of: {', '.join(sorted(DCM_ROLES))}")
        return value


class UserApprove(BaseModel):
    role: str
    lz_ids: list[str] = Field(default_factory=list)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in DCM_ROLES:
            raise ValueError(f"role must be one of: {', '.join(sorted(DCM_ROLES))}")
        return value

    @field_validator("lz_ids")
    @classmethod
    def validate_unique_lz_ids(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("lz_ids must not contain duplicates")
        return normalized


class LzAccessReplace(BaseModel):
    lz_ids: list[str] = Field(default_factory=list)

    @field_validator("lz_ids")
    @classmethod
    def validate_unique_lz_ids(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("lz_ids must not contain duplicates")
        return normalized


class ProjectMembershipInput(BaseModel):
    project_id: str = Field(min_length=1)
    role: str = ProjectRole.VIEWER.value

    @field_validator("project_id")
    @classmethod
    def normalize_project_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("project_id must not be empty")
        return normalized

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in _PROJECT_ROLES:
            raise ValueError(f"role must be one of: {', '.join(sorted(_PROJECT_ROLES))}")
        return value


class ProjectsReplace(BaseModel):
    """Full membership list to apply to a user (feature 016)."""

    projects: list[ProjectMembershipInput] = Field(default_factory=list)

    @field_validator("projects")
    @classmethod
    def validate_unique_projects(
        cls, value: list[ProjectMembershipInput]
    ) -> list[ProjectMembershipInput]:
        ids = [item.project_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("projects must not contain duplicate project_id")
        return value


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str | None = None
    entra_oid: str | None = None
    role: str = "viewer"
    lz_ids: list[str] = Field(default_factory=list)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("email must be a valid address")
        return normalized

    @field_validator("display_name", "entra_oid")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        if value not in DCM_ROLES:
            raise ValueError(f"role must be one of: {', '.join(sorted(DCM_ROLES))}")
        return value

    @field_validator("lz_ids")
    @classmethod
    def validate_unique_lz_ids(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("lz_ids must not contain duplicates")
        return normalized


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/admin/users")
async def list_admin_users(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_platform_admin)],
    role: Annotated[str | None, Query(description="Filter by DCM role.")] = None,
    is_active: Annotated[bool | None, Query(description="Filter by active flag.")] = None,
    search: Annotated[str | None, Query(description="Search by email or display name.")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return await fetch_users(
        db,
        _settings(request),
        role=role,
        is_active=is_active,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.post("/admin/users", status_code=status.HTTP_201_CREATED)
async def create_admin_user(
    payload: UserCreate,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await create_user(db, _settings(request), actor, request, payload)


@router.get("/admin/users/{user_id}")
async def get_admin_user(
    user_id: str,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await fetch_user(db, _settings(request), user_id)


@router.patch("/admin/users/{user_id}/role")
async def update_admin_user_role(
    user_id: str,
    payload: RolePatch,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await update_user_role(db, _settings(request), actor, request, user_id, payload)


@router.post("/admin/users/{user_id}/approve")
async def approve_admin_user(
    user_id: str,
    payload: UserApprove,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    """Approve a pending user: assign role, landing zones and activate the account."""
    return await approve_user(db, _settings(request), actor, request, user_id, payload)


@router.patch("/admin/users/{user_id}/deactivate")
async def deactivate_admin_user(
    user_id: str,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await deactivate_user(db, _settings(request), actor, request, user_id)


@router.delete("/admin/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_user(
    user_id: str,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> None:
    """Delete a user and everything that grants them access."""
    await delete_user(db, _settings(request), actor, request, user_id)


@router.put("/admin/users/{user_id}/lz-access")
async def replace_admin_user_lz_access(
    user_id: str,
    payload: LzAccessReplace,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await replace_user_lz_access(db, _settings(request), actor, request, user_id, payload)


@router.post("/admin/users/{user_id}/lz-access/{lz_id}", status_code=status.HTTP_201_CREATED)
async def add_admin_user_lz_access(
    user_id: str,
    lz_id: str,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await add_user_lz_access(db, _settings(request), actor, request, user_id, lz_id)


@router.delete("/admin/users/{user_id}/lz-access/{lz_id}")
async def remove_admin_user_lz_access(
    user_id: str,
    lz_id: str,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await remove_user_lz_access(db, _settings(request), actor, request, user_id, lz_id)


@router.put("/admin/users/{user_id}/projects")
async def replace_admin_user_projects(
    user_id: str,
    payload: ProjectsReplace,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    """Set the full project membership of a user (feature 016)."""
    return await replace_user_projects(db, _settings(request), actor, request, user_id, payload)
