"""Project-scoped authorization — two-dimension access scope (feature 015).

Replaces the flat LZ-only model (``get_allowed_lz_ids`` → list of LZ) with a
scope built from the union of the caller's **active** projects across two
dimensions: Landing Zones and Databricks workspaces. ``super_admin``
(``platform_role``) stays unrestricted.

Ported from the spike ``docs/spike/access-group-governance/project_scope_prototype.py``
(decisions D2/D3). SQL uses ``?`` placeholders via :class:`DatabricksWarehousePool`
and :func:`qualified_table` to address Unity Catalog, matching ``dependencies.py``.
"""

from __future__ import annotations

from typing import Annotated

from dcm_commons.models.enums import PlatformRole, ProjectRole
from fastapi import Depends, HTTPException, Request, status

from ..config import Settings
from ..db.connection import DatabricksWarehousePool, get_db
from ..db.lz_scope import project_lz_scope_query
from ..db.tables import qualified_table
from .dependencies import CurrentUser, get_current_user, is_platform_admin
from .scope_model import AllowedScope, add_scope_filter

__all__ = [
    "AllowedScope",
    "add_scope_filter",
    "get_allowed_scope",
    "get_allowed_scope_dep",
    "is_project_admin",
    "require_platform_admin",
    "require_project_admin",
    "require_unrestricted_scope",
    "resolve_user_lz_scope",
]

# Only ``active`` projects contribute scope; pending/archived do not.
_ACTIVE_PROJECT_STATUS = "active"


async def get_allowed_scope(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    user_id: str,
    platform_role: str,
) -> AllowedScope:
    """Compute the LZ + Databricks-workspace scope of a user.

    Platform admin → unrestricted. Otherwise the union of the scopes of the
    ``active`` projects where the user is a member (project role is irrelevant:
    viewer and admin see the same data, only admins manage the project).

    The LZ dimension is **resolved**, not read raw: a stored value may be either an
    ``lz_id`` or a subscription id, and a granted workspace implies its landing
    zone (see :mod:`app.db.lz_scope`). The raw values are kept alongside the
    resolved ones so a grant on a landing zone the monitoring data has not seen
    yet is never silently dropped — it just matches nothing until it appears.
    """
    if platform_role == PlatformRole.SUPER_ADMIN:
        return AllowedScope(unrestricted=True)

    members = qualified_table(settings, "dcm_project_members")
    projects = qualified_table(settings, "dcm_projects")
    lz_scope = qualified_table(settings, "dcm_project_lz_scope")
    dbx_scope = qualified_table(settings, "dcm_project_dbx_scope")

    lz_rows = await db.fetchall(
        f"""
        SELECT DISTINCT s.lz_id
        FROM {members} m
        JOIN {projects} p ON p.id = m.project_id AND p.status = ?
        JOIN {lz_scope} s ON s.project_id = p.id
        WHERE m.user_id = ?
        ORDER BY s.lz_id
        """,
        _ACTIVE_PROJECT_STATUS,
        user_id,
    )
    dbx_rows = await db.fetchall(
        f"""
        SELECT DISTINCT s.workspace_id
        FROM {members} m
        JOIN {projects} p ON p.id = m.project_id AND p.status = ?
        JOIN {dbx_scope} s ON s.project_id = p.id
        WHERE m.user_id = ?
        ORDER BY s.workspace_id
        """,
        _ACTIVE_PROJECT_STATUS,
        user_id,
    )

    raw_lz_ids = [row["lz_id"] for row in lz_rows]
    workspace_ids = [row["workspace_id"] for row in dbx_rows]
    resolved_lz_ids = await resolve_user_lz_scope(
        db,
        settings,
        user_id=user_id,
        has_scope_rows=bool(raw_lz_ids or workspace_ids),
    )

    return AllowedScope(
        unrestricted=False,
        lz_ids=sorted({*raw_lz_ids, *resolved_lz_ids}),
        workspace_ids=workspace_ids,
    )


async def resolve_user_lz_scope(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    user_id: str,
    has_scope_rows: bool,
) -> list[str]:
    """Landing zones the user's active projects grant, in the ``lz_id`` vocabulary.

    ``has_scope_rows=False`` skips the query: a user with no scope row at all has
    nothing to resolve, and the ``IN ()`` it would build is invalid SQL.
    """
    if not has_scope_rows:
        return []

    members = qualified_table(settings, "dcm_project_members")
    projects = qualified_table(settings, "dcm_projects")
    project_rows = await db.fetchall(
        f"""
        SELECT DISTINCT p.id
        FROM {members} m
        JOIN {projects} p ON p.id = m.project_id AND p.status = ?
        WHERE m.user_id = ?
        """,
        _ACTIVE_PROJECT_STATUS,
        user_id,
    )
    project_ids = [row["id"] for row in project_rows if row.get("id")]
    if not project_ids:
        return []

    sql, params = project_lz_scope_query(settings, project_ids)
    rows = await db.fetchall(sql, *params)
    return sorted({row["lz_id"] for row in rows if row.get("lz_id")})


async def is_project_admin(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    user_id: str,
    project_id: str,
) -> bool:
    """Project-scoped guard: is the user an ``admin`` of THIS project?

    Replaces the global ``require_role`` for per-project management actions
    (members, roles, scope-extension requests). ``super_admin`` bypasses this
    check upstream in the route.
    """
    members = qualified_table(settings, "dcm_project_members")
    row = await db.fetchone(
        f"""
        SELECT 1 AS has_admin
        FROM {members}
        WHERE user_id = ? AND project_id = ? AND role = ?
        LIMIT 1
        """,
        user_id,
        project_id,
        ProjectRole.ADMIN,
    )
    return row is not None


def get_allowed_scope_dep(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> AllowedScope:
    """FastAPI dependency — the caller's two-dimension scope.

    Reads the scope computed **once** at authentication time and carried on
    :class:`CurrentUser`; issues no extra query so metric-route tests keep their
    call-order mocks intact.
    """
    return current_user.scope


async def require_platform_admin(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """Guard: only platform admins pass (403 otherwise).

    The single guard for every administration route. Membership is decided by
    :func:`is_platform_admin`, so promoting someone in the admin UI grants the
    whole administration surface at once — never a subset of it.
    """
    if not is_platform_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="platform_admin role required",
        )
    return current_user


async def require_unrestricted_scope(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """Guard for interfaces that no project scope can be attached to.

    The Unity Catalog explorer reads an arbitrary ``catalog.schema.table`` with a
    caller-supplied ``WHERE``: there is no LZ or workspace predicate to add, so
    exposing it to a project member would hand them every row of every table —
    including the governance tables holding other users' identities. Only callers
    who are unrestricted by design pass (platform admins, plus the legacy
    data-admin roles kept unrestricted during the transition).
    """
    if not current_user.scope.unrestricted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="unrestricted_scope_required",
        )
    return current_user


async def require_project_admin(
    project_id: str,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> CurrentUser:
    """Guard for per-project management routes.

    A platform admin always passes; otherwise the caller must be ``admin`` of the
    ``project_id`` in the path (403 otherwise). Relies on the ``project_id`` path
    parameter being present on the route.
    """
    if is_platform_admin(current_user):
        return current_user
    settings: Settings = request.app.state.settings
    if not await is_project_admin(
        db, settings, user_id=current_user.id, project_id=project_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="project admin role required",
        )
    return current_user
