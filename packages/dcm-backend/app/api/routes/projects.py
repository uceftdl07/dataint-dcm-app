"""Self-service project & access-governance routes (feature 015).

Two-tier validation:

- **platform_admin** (``platform_role = super_admin``) validates project creation
  and scope-extension requests;
- **project admin** (``dcm_project_members.role = admin``) manages members, roles
  and join requests of their own project.

Every administrative *decision* (project validation, scope extension, join
approval, role change, member removal) writes an immutable ``dcm_audit_log`` row
(FR-020). Responses expose the readable ``displayName`` (FR-017) and use the
frozen camelCase contract from ``contracts/projects-api.md``.
"""

from __future__ import annotations

from typing import Annotated, Any

from dcm_commons.models.projects import (
    JoinRequestCreate,
    JoinRequestItem,
    MemberAdd,
    MemberRolePatch,
    ProjectCreate,
    ProjectDetail,
    ProjectJoinRequest,
    ProjectJoinResponse,
    ProjectMember,
    ProjectRegisterRequest,
    ProjectRegisterResponse,
    ProjectRejectRequest,
    ProjectSummary,
    RequestDecision,
    ScopeRequestCreate,
    ScopeRequestItem,
)
from fastapi import Depends, Request, status
from fastapi.routing import APIRouter

from ...auth.dependencies import (
    AuthenticatedIdentity,
    CurrentUser,
    get_authenticated_identity,
    get_current_user,
)
from ...auth.scope import require_platform_admin, require_project_admin
from ...config import Settings
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.projects_page import (
    add_member,
    create_project,
    create_scope_request,
    decide_join_request,
    decide_scope_request,
    delete_project,
    fetch_all_join_requests,
    fetch_join_requests,
    fetch_members,
    fetch_project_detail,
    fetch_projects,
    fetch_reference_business_applications,
    fetch_reference_projects,
    fetch_scope_requests,
    join_project,
    register_project,
    reject_project,
    remove_member,
    submit_join_request,
    update_member_role,
    validate_project,
)

__all__ = ["router"]

router = APIRouter()


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


# ─────────────────────────────────────────────────────────────────────────────
# Projects
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/projects")
async def list_projects(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> list[ProjectSummary]:
    """Projects the caller belongs to (super_admin sees all)."""
    return await fetch_projects(db, _settings(request), current_user)


@router.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_project_route(
    request: Request,
    body: ProjectCreate,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> ProjectDetail:
    """Create a ``pending_validation`` project for a Business Application."""
    return await create_project(db, _settings(request), current_user, body)


# ─────────────────────────────────────────────────────────────────────────────
# Self-service registration / join from the login page (feature 016)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/reference/business-applications")
async def list_reference_business_applications(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> dict[str, Any]:
    """Public BA id+name catalog for the login-page register form (FR-002).

    Does not expose LZ / cloud-account / workspace inventory — those attach at
    register time on the authenticated path.
    """
    return await fetch_reference_business_applications(db, _settings(request))


@router.get("/reference/projects")
async def list_reference_projects(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> dict[str, Any]:
    """Public catalog of joinable DCM projects, backing the login-page
    *Join a project* form (FR-004)."""
    return await fetch_reference_projects(db, _settings(request))


@router.post("/projects/register", status_code=status.HTTP_201_CREATED)
async def register_project_route(
    body: ProjectRegisterRequest,
    request: Request,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> ProjectRegisterResponse:
    """Self-service project registration from the login page (FR-002, FR-003)."""
    return await register_project(db, _settings(request), identity, body)


@router.post("/projects/join", status_code=status.HTTP_202_ACCEPTED)
async def join_project_route(
    body: ProjectJoinRequest,
    request: Request,
    identity: Annotated[AuthenticatedIdentity, Depends(get_authenticated_identity)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> ProjectJoinResponse:
    """Self-service join request from the login page (FR-004)."""
    return await join_project(db, _settings(request), identity, body)


@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> ProjectDetail:
    """Project detail with both scope dimensions (members only)."""
    return await fetch_project_detail(db, _settings(request), current_user, project_id)


@router.post("/projects/{project_id}/validate")
async def validate_project_route(
    project_id: str,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_platform_admin)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> ProjectDetail:
    """Activate a pending project and auto-add its creator as ``admin`` (FR-011)."""
    return await validate_project(db, _settings(request), current_user, request, project_id)


@router.post("/projects/{project_id}/reject")
async def reject_project_route(
    project_id: str,
    body: ProjectRejectRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_platform_admin)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> ProjectDetail:
    """Refuse a pending project, with a mandatory reason."""
    return await reject_project(db, _settings(request), current_user, request, project_id, body)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_route(
    project_id: str,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_platform_admin)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> None:
    """Delete a project and everything attached to it (platform_admin only)."""
    await delete_project(db, _settings(request), current_user, request, project_id)


# ─────────────────────────────────────────────────────────────────────────────
# Members
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/projects/{project_id}/members")
async def list_members(
    project_id: str,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> list[ProjectMember]:
    """List project members with their readable display name (FR-017)."""
    return await fetch_members(db, _settings(request), current_user, project_id)


@router.post(
    "/projects/{project_id}/members", status_code=status.HTTP_201_CREATED
)
async def add_member_route(
    project_id: str,
    body: MemberAdd,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_project_admin)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> ProjectMember:
    """Directly add a member by email (project admin)."""
    return await add_member(db, _settings(request), current_user, request, project_id, body)


@router.patch("/projects/{project_id}/members/{user_id}")
async def update_member_role_route(
    project_id: str,
    user_id: str,
    body: MemberRolePatch,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_project_admin)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> ProjectMember:
    """Change a member's role; 409 on demotion of the last admin (FR-014)."""
    return await update_member_role(
        db, _settings(request), current_user, request, project_id, user_id, body
    )


@router.delete(
    "/projects/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member_route(
    project_id: str,
    user_id: str,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_project_admin)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> None:
    """Remove a member; 409 on removal of the last admin (FR-014)."""
    await remove_member(db, _settings(request), current_user, request, project_id, user_id)


# ─────────────────────────────────────────────────────────────────────────────
# Join requests
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/projects/{project_id}/join-requests", status_code=status.HTTP_201_CREATED
)
async def create_join_request_route(
    project_id: str,
    body: JoinRequestCreate,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> JoinRequestItem:
    """Request to join a project; free resubmission after rejection (FR-020b)."""
    return await submit_join_request(db, _settings(request), current_user, project_id, body)


@router.get("/projects/{project_id}/join-requests")
async def list_join_requests(
    project_id: str,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_project_admin)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> list[JoinRequestItem]:
    """Pending join requests of a project (in-app queue, FR-020a)."""
    return await fetch_join_requests(db, _settings(request), project_id)


@router.get("/join-requests")
async def list_all_join_requests(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_platform_admin)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> list[JoinRequestItem]:
    """Every pending join request across the platform (platform admin)."""
    return await fetch_all_join_requests(db, _settings(request))


@router.post("/join-requests/{request_id}/decide")
async def decide_join_request_route(
    request_id: str,
    body: RequestDecision,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> JoinRequestItem:
    """Approve/reject a join request (project admin); approval adds the member."""
    return await decide_join_request(
        db, _settings(request), current_user, request, request_id, body
    )


# ─────────────────────────────────────────────────────────────────────────────
# Scope-extension requests
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/projects/{project_id}/scope-requests", status_code=status.HTTP_201_CREATED
)
async def create_scope_request_route(
    project_id: str,
    body: ScopeRequestCreate,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_project_admin)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> list[ScopeRequestItem]:
    """A project admin requests new LZs / workspaces for the project scope."""
    return await create_scope_request(db, _settings(request), current_user, project_id, body)


@router.get("/scope-requests")
async def list_scope_requests(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_platform_admin)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> list[ScopeRequestItem]:
    """Pending scope-extension requests across all projects (platform_admin)."""
    return await fetch_scope_requests(db, _settings(request))


@router.post("/scope-requests/{request_id}/decide")
async def decide_scope_request_route(
    request_id: str,
    body: RequestDecision,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_platform_admin)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> ScopeRequestItem:
    """Approve/reject a scope-extension request; approval adds the scope row."""
    return await decide_scope_request(
        db, _settings(request), current_user, request, request_id, body
    )
