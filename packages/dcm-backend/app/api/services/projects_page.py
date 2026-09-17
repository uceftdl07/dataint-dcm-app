"""Self-service project & access-governance queries (feature 015).

Kept out of the route per the route→service→pool pattern. See
``app/api/routes/projects.py`` for the two-tier validation model and the
audit-log guarantee this module upholds on every administrative decision.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from dcm_commons.models.enums import ProjectRole, ProjectStatus, RequestStatus, ScopeType
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
from fastapi import HTTPException, status

from ...auth.audit import log_action
from ...auth.dependencies import AuthenticatedIdentity, CurrentUser, is_platform_admin
from ...auth.scope import is_project_admin
from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.lz_scope import project_lz_scope_query
from ...db.tables import qualified_lz_dimension_table, qualified_table

__all__ = [
    "add_member",
    "create_project",
    "create_scope_request",
    "decide_join_request",
    "decide_scope_request",
    "delete_project",
    "fetch_all_join_requests",
    "fetch_join_requests",
    "fetch_members",
    "fetch_project_detail",
    "fetch_projects",
    "fetch_reference_business_applications",
    "fetch_reference_projects",
    "fetch_scope_requests",
    "join_project",
    "register_project",
    "reject_project",
    "remove_member",
    "submit_join_request",
    "update_member_role",
    "validate_project",
]


def _now() -> datetime:
    return datetime.now(UTC)


def _is_super_admin(user: CurrentUser) -> bool:
    """Platform admin, resolved exactly like ``require_platform_admin`` does."""
    return is_platform_admin(user)


async def _load_project_row(
    db: DatabricksWarehousePool, settings: Settings, project_id: str
) -> dict[str, Any]:
    projects = qualified_table(settings, "dcm_projects")
    row = await db.fetchone(
        f"""
        SELECT id, name, business_app_id, status, created_by, created_at,
               validated_by, validated_at, decision_reason
        FROM {projects}
        WHERE id = ?
        LIMIT 1
        """,
        project_id,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="project_not_found"
        )
    return row


def _parse_collected(value: Any) -> list[str]:
    """Normalize a Databricks ``collect_set`` column into a sorted str list.

    The warehouse hands the array back in one of three shapes depending on the
    fetch path: a native sequence, its JSON encoding, or a ``numpy.ndarray`` —
    which is what the Arrow path actually returns and is *not* a ``list``. Only
    accepting list/tuple/set silently emptied every scope column of the
    administration table while the scope rows were there all along.
    """
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return [value] if value else []
        if isinstance(value, str):
            return [value]
    if isinstance(value, (bytes, bytearray, dict)):
        return []
    try:
        items = list(value)
    except TypeError:  # a scalar the driver did not wrap in an array
        return []
    return sorted(str(item) for item in items if item)


async def _project_scopes(
    db: DatabricksWarehousePool, settings: Settings, project_id: str
) -> tuple[list[str], list[str], list[str]]:
    """``(lz_scope, dbx_scope, effective_lz_scope)`` of one project.

    The first two are the registered rows — the values a scope mutation targets.
    The third is what they resolve to in the monitoring vocabulary.
    """
    lz_table = qualified_table(settings, "dcm_project_lz_scope")
    dbx_table = qualified_table(settings, "dcm_project_dbx_scope")
    lz_rows = await db.fetchall(
        f"SELECT lz_id FROM {lz_table} WHERE project_id = ? ORDER BY lz_id",
        project_id,
    )
    dbx_rows = await db.fetchall(
        f"SELECT workspace_id FROM {dbx_table} WHERE project_id = ? ORDER BY workspace_id",
        project_id,
    )
    effective = await _effective_lz_scopes(db, settings, [project_id])
    return (
        [r["lz_id"] for r in lz_rows],
        [r["workspace_id"] for r in dbx_rows],
        effective.get(project_id, []),
    )


async def _effective_lz_scopes(
    db: DatabricksWarehousePool, settings: Settings, project_ids: list[str]
) -> dict[str, list[str]]:
    """Map each project to the landing-zone ids its grants resolve to.

    One statement for every project asked about, so the administration table and
    the header selector stay free of an N+1 fan-out. Projects that resolve to
    nothing are simply absent from the mapping.
    """
    unique_ids = sorted({pid for pid in project_ids if pid})
    if not unique_ids:
        return {}
    sql, params = project_lz_scope_query(settings, unique_ids)
    rows = await db.fetchall(sql, *params)
    grouped: dict[str, set[str]] = {}
    for row in rows:
        project_id = row.get("project_id")
        lz_id = row.get("lz_id")
        if project_id and lz_id:
            grouped.setdefault(str(project_id), set()).add(str(lz_id))
    return {project_id: sorted(values) for project_id, values in grouped.items()}


async def _member_role(
    db: DatabricksWarehousePool, settings: Settings, *, project_id: str, user_id: str
) -> str | None:
    members = qualified_table(settings, "dcm_project_members")
    row = await db.fetchone(
        f"SELECT role FROM {members} WHERE project_id = ? AND user_id = ? LIMIT 1",
        project_id,
        user_id,
    )
    return row["role"] if row else None


async def _count_admins(
    db: DatabricksWarehousePool, settings: Settings, project_id: str
) -> int:
    members = qualified_table(settings, "dcm_project_members")
    row = await db.fetchone(
        f"""
        SELECT COUNT(*) AS admin_count
        FROM {members}
        WHERE project_id = ? AND role = ?
        """,
        project_id,
        ProjectRole.ADMIN,
    )
    return int(row["admin_count"]) if row else 0


async def _count_members(
    db: DatabricksWarehousePool, settings: Settings, project_id: str
) -> int:
    """Member count for a single project.

    ``fetch_projects`` aggregates this in its own statement; this is the one-project
    path, so ``ProjectDetail.member_count`` is never a silent 0 on the wire.
    """
    members = qualified_table(settings, "dcm_project_members")
    count = await db.fetchscalar(
        f"SELECT COUNT(DISTINCT user_id) FROM {members} WHERE project_id = ?",
        project_id,
    )
    return int(count or 0)


async def _require_member_or_super(
    db: DatabricksWarehousePool,
    settings: Settings,
    user: CurrentUser,
    project_id: str,
) -> None:
    if _is_super_admin(user):
        return
    if await _member_role(db, settings, project_id=project_id, user_id=user.id) is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="not_a_project_member"
        )


async def _business_app_has_project(
    db: DatabricksWarehousePool, settings: Settings, business_app_id: str
) -> bool:
    projects = qualified_table(settings, "dcm_projects")
    existing = await db.fetchone(
        f"""
        SELECT id FROM {projects}
        WHERE (id = ? OR business_app_id = ?) AND status IN (?, ?)
        LIMIT 1
        """,
        business_app_id,
        business_app_id,
        ProjectStatus.PENDING_VALIDATION,
        ProjectStatus.ACTIVE,
    )
    return existing is not None


async def _purge_rejected_project(
    db: DatabricksWarehousePool, settings: Settings, business_app_id: str
) -> None:
    """Drop a previously rejected project on this Business Application.

    ``dcm_projects.id`` IS the Business Application id and Delta enforces no
    primary key, so a leftover ``rejected`` row would become a duplicate the
    moment the BA is registered again — and ``_load_project_row`` (LIMIT 1) could
    then return the stale rejected one. The refusal itself stays auditable in
    ``dcm_audit_log``.
    """
    projects = qualified_table(settings, "dcm_projects")
    stale = await db.fetchone(
        f"SELECT id FROM {projects} WHERE id = ? AND status = ? LIMIT 1",
        business_app_id,
        ProjectStatus.REJECTED,
    )
    if stale is None:
        return
    await _delete_project_children(db, settings, business_app_id)
    await db.execute(
        f"DELETE FROM {projects} WHERE id = ? AND status = ?",
        business_app_id,
        ProjectStatus.REJECTED,
    )


async def _delete_project_children(
    db: DatabricksWarehousePool, settings: Settings, project_id: str
) -> None:
    """Drop everything hanging off a project: scope, members and open requests.

    Delta has no foreign keys, so orphaned rows would survive the project and —
    ``dcm_projects.id`` being the Business Application id — get silently adopted
    by the next project registered on the same BA.
    """
    for table in (
        "dcm_project_lz_scope",
        "dcm_project_dbx_scope",
        "dcm_project_members",
        "dcm_project_join_requests",
        "dcm_project_scope_requests",
    ):
        await db.execute(
            f"DELETE FROM {qualified_table(settings, table)} WHERE project_id = ?",
            project_id,
        )


async def _ensure_app_user(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    email: str,
    display_name: str | None = None,
) -> str:
    """Resolve an email to its ``dcm_app_users.id``, creating a pending stub if
    the person has never signed in.

    The stub stores ``entra_oid = "email:<addr>"``; the real Entra ``oid`` is
    back-filled on first login. Project membership is always keyed by this id —
    consistent with the authenticated project routes and scope resolution.
    """
    users = qualified_table(settings, "dcm_app_users")
    existing = await db.fetchone(
        f"SELECT id FROM {users} WHERE LOWER(email) = LOWER(?) LIMIT 1",
        email,
    )
    if existing is not None:
        return str(existing["id"])
    user_id = str(uuid4())
    await db.execute(
        f"""
        INSERT INTO {users}
            (id, entra_oid, email, display_name, role, is_active, created_at, last_login_at)
        VALUES (?, ?, ?, ?, 'pending', FALSE, current_timestamp(), NULL)
        """,
        user_id,
        f"email:{email}",
        email,
        display_name or email,
    )
    return user_id


async def _activate_app_user(
    db: DatabricksWarehousePool, settings: Settings, *, user_id: str
) -> None:
    """Grant baseline access once a project or join request is approved:
    ``pending`` → ``viewer`` and ``is_active = TRUE``."""
    users = qualified_table(settings, "dcm_app_users")
    await db.execute(
        f"""
        UPDATE {users}
        SET role = CASE WHEN role = 'pending' THEN 'viewer' ELSE role END,
            is_active = TRUE
        WHERE id = ?
        """,
        user_id,
    )


async def _fetch_reference_business_applications_rows(
    db: DatabricksWarehousePool, settings: Settings
) -> list[dict[str, Any]]:
    """Public BA catalog: id + display name only (no LZ / account / workspace).

    Landing-zone and Databricks scopes are resolved server-side at register time
    (:func:`_resolve_business_application_scopes`) so the unauthenticated
    ``GET /reference/business-applications`` route never leaks cloud inventory.
    """
    ba_table = qualified_table(settings, "dim_business_application")
    rows = await db.fetchall(
        f"""
        SELECT
            ba.business_application_id AS ba_id,
            ba.business_application_name AS ba_name
        FROM {ba_table} ba
        ORDER BY ba.business_application_name
        """,
    )
    return [
        {
            "businessApplicationId": row["ba_id"],
            "businessApplicationName": row["ba_name"],
        }
        for row in rows
        if row.get("ba_id") is not None
    ]


async def _resolve_business_application_scopes(
    db: DatabricksWarehousePool,
    settings: Settings,
    business_app_id: str,
) -> tuple[list[str], list[str]]:
    """Return ``(lz_ids, workspace_ids)`` for a BA — used only after auth on register.

    Same join chain as the former public catalog payload, kept private so cloud
    account / subscription identifiers never leave the backend on the login page.
    """
    ba_table = qualified_table(settings, "dim_business_application")
    dbx_ws = qualified_table(settings, "dim_dbx_workspace")
    lz_dim = qualified_lz_dimension_table(settings)
    rows = await db.fetchall(
        f"""
        SELECT
            lzd.lz_id,
            ws.workspace_id AS workspace_id
        FROM {ba_table} ba
        LEFT JOIN {lz_dim} lzd
            ON lzd.business_application_id = ba.business_application_id
        LEFT JOIN {dbx_ws} ws
            ON ws.subscription_or_account_id = lzd.subscription_or_account_id
        WHERE ba.business_application_id = ?
        ORDER BY lz_id, workspace_id
        """,
        business_app_id,
    )
    lz_ids: list[str] = []
    workspace_ids: list[str] = []
    seen_lz: set[str] = set()
    seen_ws: set[str] = set()
    for row in rows:
        lz_id = row.get("lz_id")
        if lz_id is not None and lz_id not in seen_lz:
            seen_lz.add(lz_id)
            lz_ids.append(lz_id)
        workspace_id = row.get("workspace_id")
        if workspace_id is not None and workspace_id not in seen_ws:
            seen_ws.add(workspace_id)
            workspace_ids.append(workspace_id)
    return lz_ids, workspace_ids


async def fetch_projects(
    db: DatabricksWarehousePool,
    settings: Settings,
    current_user: CurrentUser,
) -> list[ProjectSummary]:
    """Projects the caller belongs to (super_admin sees all).

    Each row carries its LZ + workspace scope and member count, aggregated in the
    same statement, so the administration table renders what a project grants
    without one detail request per project.
    """
    projects = qualified_table(settings, "dcm_projects")
    members = qualified_table(settings, "dcm_project_members")
    lz_table = qualified_table(settings, "dcm_project_lz_scope")
    dbx_table = qualified_table(settings, "dcm_project_dbx_scope")

    aggregates = """
        collect_set(lz.lz_id) AS lz_scope,
        collect_set(dbx.workspace_id) AS dbx_scope,
        COUNT(DISTINCT am.user_id) AS member_count
    """
    joins = f"""
        LEFT JOIN {lz_table} lz ON lz.project_id = p.id
        LEFT JOIN {dbx_table} dbx ON dbx.project_id = p.id
        LEFT JOIN {members} am ON am.project_id = p.id
    """
    group_by = "GROUP BY p.id, p.name, p.business_app_id, p.status, m.role"

    if _is_super_admin(current_user):
        rows = await db.fetchall(
            f"""
            SELECT p.id, p.name, p.business_app_id, p.status, m.role AS role,
                   {aggregates}
            FROM {projects} p
            LEFT JOIN {members} m ON m.project_id = p.id AND m.user_id = ?
            {joins}
            {group_by}
            ORDER BY p.name
            """,
            current_user.id,
        )
    else:
        rows = await db.fetchall(
            f"""
            SELECT p.id, p.name, p.business_app_id, p.status, m.role AS role,
                   {aggregates}
            FROM {members} m
            JOIN {projects} p ON p.id = m.project_id
            {joins}
            WHERE m.user_id = ?
            {group_by}
            ORDER BY p.name
            """,
            current_user.id,
        )
    effective = await _effective_lz_scopes(
        db, settings, [str(row["id"]) for row in rows if row.get("id")]
    )
    return [
        ProjectSummary(
            id=row["id"],
            name=row["name"],
            business_app_id=row["business_app_id"],
            status=row["status"],
            role=row["role"],
            lz_scope=_parse_collected(row.get("lz_scope")),
            effective_lz_scope=effective.get(str(row["id"]), []),
            dbx_scope=_parse_collected(row.get("dbx_scope")),
            member_count=int(row.get("member_count") or 0),
        )
        for row in rows
    ]


async def create_project(
    db: DatabricksWarehousePool,
    settings: Settings,
    current_user: CurrentUser,
    body: ProjectCreate,
) -> ProjectDetail:
    """Create a ``pending_validation`` project for a Business Application.

    409 if the BA already has a project (active or pending) — FR-011a. Requested
    scope rows are stored immediately; they become effective once a platform_admin
    activates the project (the creator is auto-added as ``admin`` at activation).
    """
    projects = qualified_table(settings, "dcm_projects")

    existing = await db.fetchone(
        f"""
        SELECT id FROM {projects}
        WHERE (id = ? OR business_app_id = ?) AND status IN (?, ?)
        LIMIT 1
        """,
        body.business_app_id,
        body.business_app_id,
        ProjectStatus.PENDING_VALIDATION,
        ProjectStatus.ACTIVE,
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="project_already_exists_for_business_app",
        )
    await _purge_rejected_project(db, settings, body.business_app_id)

    now = _now()
    await db.execute(
        f"""
        INSERT INTO {projects}
            (id, name, business_app_id, status, entra_group_id,
             created_by, created_at, updated_at, validated_by, validated_at)
        VALUES (?, ?, ?, ?, NULL, ?, ?, ?, NULL, NULL)
        """,
        body.business_app_id,
        body.name,
        body.business_app_id,
        ProjectStatus.PENDING_VALIDATION,
        current_user.id,
        now,
        now,
    )

    lz_table = qualified_table(settings, "dcm_project_lz_scope")
    dbx_table = qualified_table(settings, "dcm_project_dbx_scope")
    for lz_id in body.lz_scope:
        await db.execute(
            f"INSERT INTO {lz_table} (project_id, lz_id, granted_by, granted_at) "
            "VALUES (?, ?, ?, ?)",
            body.business_app_id,
            lz_id,
            current_user.id,
            now,
        )
    for workspace_id in body.dbx_scope:
        await db.execute(
            f"INSERT INTO {dbx_table} (project_id, workspace_id, granted_by, granted_at) "
            "VALUES (?, ?, ?, ?)",
            body.business_app_id,
            workspace_id,
            current_user.id,
            now,
        )

    return ProjectDetail(
        id=body.business_app_id,
        name=body.name,
        business_app_id=body.business_app_id,
        status=ProjectStatus.PENDING_VALIDATION,
        role=None,
        lz_scope=list(body.lz_scope),
        dbx_scope=list(body.dbx_scope),
        created_by=current_user.id,
        created_at=now,
        validated_by=None,
        validated_at=None,
    )


async def fetch_reference_business_applications(
    db: DatabricksWarehousePool,
    settings: Settings,
) -> dict[str, Any]:
    """Public BA name catalog for the login-page register form (FR-002).

    Intentionally minimal: id + name only. Scope inventory is attached later by
    :func:`register_project` after the caller is authenticated.
    """
    items = await _fetch_reference_business_applications_rows(db, settings)
    return {"items": items, "total": len(items)}


async def fetch_reference_projects(
    db: DatabricksWarehousePool,
    settings: Settings,
) -> dict[str, Any]:
    """Public catalog of joinable DCM projects, backing the login-page
    *Join a project* form (FR-004).

    Lists only ``active`` ``dcm_projects`` so a visitor requests to join an
    already-validated project by its id — not by Business Application.
    """
    projects = qualified_table(settings, "dcm_projects")
    rows = await db.fetchall(
        f"""
        SELECT id, name, business_app_id, status
        FROM {projects}
        WHERE status = ?
        ORDER BY name
        """,
        ProjectStatus.ACTIVE,
    )
    items = [
        {
            "id": row["id"],
            "name": row["name"],
            "businessAppId": row["business_app_id"],
            "status": row["status"],
        }
        for row in rows
    ]
    return {"items": items, "total": len(items)}


async def register_project(
    db: DatabricksWarehousePool,
    settings: Settings,
    identity: AuthenticatedIdentity,
    body: ProjectRegisterRequest,
) -> ProjectRegisterResponse:
    """Self-service project registration from the login page (FR-002, FR-003).

    Creates a ``pending_validation`` project for a Business Application with the
    requester as project ``admin`` and the declared members. 409 if the BA
    already owns a project (1:1 BA → project), inviting the visitor to *join*.
    The requester is the caller's verified token identity, never a body field.
    """
    if await _business_app_has_project(db, settings, body.business_app_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "project_already_exists_for_business_app",
                "message": (
                    "This Business Application already has a project. "
                    "Join the existing project instead."
                ),
            },
        )
    await _purge_rejected_project(db, settings, body.business_app_id)

    now = _now()
    requester = identity.email.strip().lower()
    requester_id = await _ensure_app_user(db, settings, email=requester)
    projects = qualified_table(settings, "dcm_projects")
    await db.execute(
        f"""
        INSERT INTO {projects}
            (id, name, business_app_id, status, entra_group_id,
             created_by, created_at, updated_at, validated_by, validated_at)
        VALUES (?, ?, ?, ?, NULL, ?, ?, ?, NULL, NULL)
        """,
        body.business_app_id,
        body.name,
        body.business_app_id,
        ProjectStatus.PENDING_VALIDATION,
        requester_id,
        now,
        now,
    )

    members_table = qualified_table(settings, "dcm_project_members")
    # Requester is auto-added as project admin (FR-002).
    await db.execute(
        f"""
        INSERT INTO {members_table} (project_id, user_id, role, added_by, added_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        body.business_app_id,
        requester_id,
        ProjectRole.ADMIN,
        requester_id,
        now,
    )
    seen = {requester}
    for member in body.members:
        if member.email in seen:
            continue
        seen.add(member.email)
        member_id = await _ensure_app_user(db, settings, email=member.email)
        await db.execute(
            f"""
            INSERT INTO {members_table} (project_id, user_id, role, added_by, added_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            body.business_app_id,
            member_id,
            member.role,
            requester_id,
            now,
        )

    # Scopes come from the BA referential on the server — never from the public
    # catalog or a client-supplied list (avoids inventory leakage + spoofing).
    lz_scope, dbx_scope = await _resolve_business_application_scopes(
        db, settings, body.business_app_id
    )
    lz_table = qualified_table(settings, "dcm_project_lz_scope")
    dbx_table = qualified_table(settings, "dcm_project_dbx_scope")
    for lz_id in lz_scope:
        await db.execute(
            f"INSERT INTO {lz_table} (project_id, lz_id, granted_by, granted_at) "
            "VALUES (?, ?, ?, ?)",
            body.business_app_id,
            lz_id,
            requester_id,
            now,
        )
    for workspace_id in dbx_scope:
        await db.execute(
            f"INSERT INTO {dbx_table} (project_id, workspace_id, granted_by, granted_at) "
            "VALUES (?, ?, ?, ?)",
            body.business_app_id,
            workspace_id,
            requester_id,
            now,
        )

    return ProjectRegisterResponse(
        id=body.business_app_id,
        name=body.name,
        business_app_id=body.business_app_id,
        status=ProjectStatus.PENDING_VALIDATION,
        requester_email=requester,
        member_count=len(seen),
    )


async def join_project(
    db: DatabricksWarehousePool,
    settings: Settings,
    identity: AuthenticatedIdentity,
    body: ProjectJoinRequest,
) -> ProjectJoinResponse:
    """Self-service join request from the login page (FR-004).

    Creates a ``pending`` join request routed to the project admins — or to the
    project *creator* while the project is still ``pending_validation`` (no
    confirmed admin yet). The requester is the caller's verified token identity.
    """
    row = await _load_project_row(db, settings, body.project_id)
    if row["status"] in {ProjectStatus.REJECTED, ProjectStatus.ARCHIVED}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="project_not_joinable",
        )

    routed_to: Literal["admins", "creator"]
    if row["status"] == ProjectStatus.PENDING_VALIDATION:
        routed_to = "creator"
        recipient_ids = [row["created_by"]] if row["created_by"] else []
    else:
        routed_to = "admins"
        members_table = qualified_table(settings, "dcm_project_members")
        admin_rows = await db.fetchall(
            f"SELECT user_id FROM {members_table} WHERE project_id = ? AND role = ?",
            body.project_id,
            ProjectRole.ADMIN,
        )
        recipient_ids = [r["user_id"] for r in admin_rows]

    now = _now()
    requester_id = await _ensure_app_user(
        db, settings, email=identity.email.strip().lower()
    )
    request_id = str(uuid4())
    join_requests = qualified_table(settings, "dcm_project_join_requests")
    await db.execute(
        f"""
        INSERT INTO {join_requests}
            (id, project_id, user_id, requested_role, status, justification,
             requested_at, decided_by, decided_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)
        """,
        request_id,
        body.project_id,
        requester_id,
        ProjectRole.VIEWER,
        RequestStatus.PENDING,
        body.justification,
        now,
    )

    return ProjectJoinResponse(
        request_id=request_id,
        project_id=body.project_id,
        status=RequestStatus.PENDING,
        routed_to=routed_to,
        recipient_ids=recipient_ids,
    )


async def fetch_project_detail(
    db: DatabricksWarehousePool,
    settings: Settings,
    current_user: CurrentUser,
    project_id: str,
) -> ProjectDetail:
    """Project detail with both scope dimensions (members only)."""
    row = await _load_project_row(db, settings, project_id)
    await _require_member_or_super(db, settings, current_user, project_id)
    lz_scope, dbx_scope, effective_lz_scope = await _project_scopes(
        db, settings, project_id
    )
    role = await _member_role(
        db, settings, project_id=project_id, user_id=current_user.id
    )
    return ProjectDetail(
        id=row["id"],
        name=row["name"],
        business_app_id=row["business_app_id"],
        status=row["status"],
        role=role,
        lz_scope=lz_scope,
        effective_lz_scope=effective_lz_scope,
        dbx_scope=dbx_scope,
        member_count=await _count_members(db, settings, project_id),
        created_by=row["created_by"],
        created_at=row["created_at"],
        validated_by=row["validated_by"],
        validated_at=row["validated_at"],
        decision_reason=row.get("decision_reason"),
    )


async def validate_project(
    db: DatabricksWarehousePool,
    settings: Settings,
    current_user: CurrentUser,
    request: Any,
    project_id: str,
) -> ProjectDetail:
    """Activate a pending project and auto-add its creator as ``admin`` (FR-011)."""
    row = await _load_project_row(db, settings, project_id)
    if row["status"] != ProjectStatus.PENDING_VALIDATION:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="project_not_pending_validation",
        )

    now = _now()
    projects = qualified_table(settings, "dcm_projects")
    await db.execute(
        f"""
        UPDATE {projects}
        SET status = ?, validated_by = ?, validated_at = ?, updated_at = ?
        WHERE id = ?
        """,
        ProjectStatus.ACTIVE,
        current_user.id,
        now,
        now,
        project_id,
    )

    creator_id = row["created_by"]
    members = qualified_table(settings, "dcm_project_members")
    if (
        await _member_role(db, settings, project_id=project_id, user_id=creator_id)
        is None
    ):
        await db.execute(
            f"""
            INSERT INTO {members} (project_id, user_id, role, added_by, added_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            project_id,
            creator_id,
            ProjectRole.ADMIN,
            current_user.id,
            now,
        )

    # Approval provisions access: activate every member's account (FR-011).
    member_rows = await db.fetchall(
        f"SELECT user_id FROM {members} WHERE project_id = ?", project_id
    )
    for member in member_rows:
        await _activate_app_user(db, settings, user_id=member["user_id"])

    await log_action(
        db=db,
        settings=settings,
        actor=current_user,
        action="project.validate",
        target_type="project",
        target_id=project_id,
        before_state={"status": row["status"]},
        after_state={"status": ProjectStatus.ACTIVE.value},
        request=request,
    )

    lz_scope, dbx_scope, effective_lz_scope = await _project_scopes(
        db, settings, project_id
    )
    return ProjectDetail(
        id=row["id"],
        name=row["name"],
        business_app_id=row["business_app_id"],
        status=ProjectStatus.ACTIVE,
        role=None,
        lz_scope=lz_scope,
        effective_lz_scope=effective_lz_scope,
        dbx_scope=dbx_scope,
        created_by=row["created_by"],
        created_at=row["created_at"],
        validated_by=current_user.id,
        validated_at=now,
    )


async def reject_project(
    db: DatabricksWarehousePool,
    settings: Settings,
    current_user: CurrentUser,
    request: Any,
    project_id: str,
    body: ProjectRejectRequest,
) -> ProjectDetail:
    """Refuse a pending project, with a mandatory reason.

    Moving it to ``rejected`` frees its Business Application: the BA uniqueness
    check only counts ``pending_validation`` and ``active`` projects, so the right
    team can register one afterwards. Without this, a bad request would hold a BA
    hostage forever.
    """
    row = await _load_project_row(db, settings, project_id)
    if row["status"] != ProjectStatus.PENDING_VALIDATION:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="project_not_pending_validation",
        )

    now = _now()
    projects = qualified_table(settings, "dcm_projects")
    await db.execute(
        f"""
        UPDATE {projects}
        SET status = ?, validated_by = ?, validated_at = ?, updated_at = ?,
            decision_reason = ?
        WHERE id = ?
        """,
        ProjectStatus.REJECTED,
        current_user.id,
        now,
        now,
        body.reason,
        project_id,
    )

    await log_action(
        db=db,
        settings=settings,
        actor=current_user,
        action="project.reject",
        target_type="project",
        target_id=project_id,
        before_state={"status": row["status"]},
        after_state={"status": ProjectStatus.REJECTED.value, "reason": body.reason},
        request=request,
    )

    lz_scope, dbx_scope, effective_lz_scope = await _project_scopes(
        db, settings, project_id
    )
    return ProjectDetail(
        id=row["id"],
        name=row["name"],
        business_app_id=row["business_app_id"],
        status=ProjectStatus.REJECTED,
        role=None,
        lz_scope=lz_scope,
        effective_lz_scope=effective_lz_scope,
        dbx_scope=dbx_scope,
        created_by=row["created_by"],
        created_at=row["created_at"],
        validated_by=current_user.id,
        validated_at=now,
        decision_reason=body.reason,
    )


async def delete_project(
    db: DatabricksWarehousePool,
    settings: Settings,
    current_user: CurrentUser,
    request: Any,
    project_id: str,
) -> None:
    """Delete a project and everything attached to it (platform_admin only).

    Rejecting only refuses a *pending* creation; a project that was activated by
    mistake, or whose team is gone, has no other way out. Members keep their DCM
    account — they simply stop being members, and lose the project scope with it.
    The deletion itself stays auditable in ``dcm_audit_log``.
    """
    row = await _load_project_row(db, settings, project_id)

    await _delete_project_children(db, settings, project_id)
    await db.execute(
        f"DELETE FROM {qualified_table(settings, 'dcm_projects')} WHERE id = ?",
        project_id,
    )

    await log_action(
        db=db,
        settings=settings,
        actor=current_user,
        action="project.delete",
        target_type="project",
        target_id=project_id,
        before_state={"status": row["status"], "name": row["name"]},
        after_state=None,
        request=request,
    )


async def fetch_members(
    db: DatabricksWarehousePool,
    settings: Settings,
    current_user: CurrentUser,
    project_id: str,
) -> list[ProjectMember]:
    """List project members with their readable display name (FR-017)."""
    await _load_project_row(db, settings, project_id)
    await _require_member_or_super(db, settings, current_user, project_id)
    members = qualified_table(settings, "dcm_project_members")
    users = qualified_table(settings, "dcm_app_users")
    rows = await db.fetchall(
        f"""
        SELECT m.user_id, u.display_name, m.role, m.added_at
        FROM {members} m
        LEFT JOIN {users} u ON u.id = m.user_id
        WHERE m.project_id = ?
        ORDER BY u.display_name
        """,
        project_id,
    )
    return [
        ProjectMember(
            user_id=row["user_id"],
            display_name=row["display_name"],
            role=row["role"],
            added_at=row["added_at"],
        )
        for row in rows
    ]


async def add_member(
    db: DatabricksWarehousePool,
    settings: Settings,
    current_user: CurrentUser,
    request: Any,
    project_id: str,
    body: MemberAdd,
) -> ProjectMember:
    """Directly add a member by email (project admin); provisions and activates
    the account so access is granted without a join request."""
    await _load_project_row(db, settings, project_id)
    user_id = await _ensure_app_user(db, settings, email=body.email)
    if (
        await _member_role(db, settings, project_id=project_id, user_id=user_id)
        is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="member_already_exists"
        )

    now = _now()
    members = qualified_table(settings, "dcm_project_members")
    await db.execute(
        f"""
        INSERT INTO {members} (project_id, user_id, role, added_by, added_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        project_id,
        user_id,
        body.role,
        current_user.id,
        now,
    )
    await _activate_app_user(db, settings, user_id=user_id)
    await log_action(
        db=db,
        settings=settings,
        actor=current_user,
        action="project.member.add",
        target_type="project_member",
        target_id=f"{project_id}:{user_id}",
        before_state=None,
        after_state={"role": body.role.value, "email": body.email},
        request=request,
    )
    return ProjectMember(user_id=user_id, role=body.role, added_at=now)


async def update_member_role(
    db: DatabricksWarehousePool,
    settings: Settings,
    current_user: CurrentUser,
    request: Any,
    project_id: str,
    user_id: str,
    body: MemberRolePatch,
) -> ProjectMember:
    """Change a member's role; 409 on demotion of the last admin (FR-014)."""
    await _load_project_row(db, settings, project_id)
    current_role = await _member_role(
        db, settings, project_id=project_id, user_id=user_id
    )
    if current_role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="member_not_found"
        )

    demoting_last_admin = (
        current_role == ProjectRole.ADMIN
        and body.role != ProjectRole.ADMIN
        and await _count_admins(db, settings, project_id) <= 1
    )
    if demoting_last_admin and not _is_super_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="cannot_demote_last_admin"
        )

    now = _now()
    members = qualified_table(settings, "dcm_project_members")
    await db.execute(
        f"UPDATE {members} SET role = ? WHERE project_id = ? AND user_id = ?",
        body.role,
        project_id,
        user_id,
    )
    await log_action(
        db=db,
        settings=settings,
        actor=current_user,
        action="project.member.role_change",
        target_type="project_member",
        target_id=f"{project_id}:{user_id}",
        before_state={"role": current_role},
        after_state={"role": body.role.value},
        request=request,
    )
    return ProjectMember(user_id=user_id, role=body.role, added_at=now)


async def remove_member(
    db: DatabricksWarehousePool,
    settings: Settings,
    current_user: CurrentUser,
    request: Any,
    project_id: str,
    user_id: str,
) -> None:
    """Remove a member; 409 on removal of the last admin (FR-014)."""
    await _load_project_row(db, settings, project_id)
    current_role = await _member_role(
        db, settings, project_id=project_id, user_id=user_id
    )
    if current_role is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="member_not_found"
        )

    removing_last_admin = (
        current_role == ProjectRole.ADMIN
        and await _count_admins(db, settings, project_id) <= 1
    )
    if removing_last_admin and not _is_super_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="cannot_remove_last_admin"
        )

    members = qualified_table(settings, "dcm_project_members")
    await db.execute(
        f"DELETE FROM {members} WHERE project_id = ? AND user_id = ?",
        project_id,
        user_id,
    )
    await log_action(
        db=db,
        settings=settings,
        actor=current_user,
        action="project.member.remove",
        target_type="project_member",
        target_id=f"{project_id}:{user_id}",
        before_state={"role": current_role},
        after_state=None,
        request=request,
    )


async def submit_join_request(
    db: DatabricksWarehousePool,
    settings: Settings,
    current_user: CurrentUser,
    project_id: str,
    body: JoinRequestCreate,
) -> JoinRequestItem:
    """Request to join a project; free resubmission after rejection (FR-020b)."""
    await _load_project_row(db, settings, project_id)

    now = _now()
    request_id = str(uuid4())
    join_requests = qualified_table(settings, "dcm_project_join_requests")
    await db.execute(
        f"""
        INSERT INTO {join_requests}
            (id, project_id, user_id, requested_role, status, justification,
             requested_at, decided_by, decided_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL)
        """,
        request_id,
        project_id,
        current_user.id,
        body.requested_role,
        RequestStatus.PENDING,
        body.justification,
        now,
    )
    return JoinRequestItem(
        id=request_id,
        project_id=project_id,
        user_id=current_user.id,
        display_name=current_user.display_name,
        requested_role=body.requested_role,
        status=RequestStatus.PENDING,
        justification=body.justification,
        requested_at=now,
    )


async def fetch_join_requests(
    db: DatabricksWarehousePool,
    settings: Settings,
    project_id: str,
) -> list[JoinRequestItem]:
    """Pending join requests of a project (in-app queue, FR-020a)."""
    await _load_project_row(db, settings, project_id)
    join_requests = qualified_table(settings, "dcm_project_join_requests")
    users = qualified_table(settings, "dcm_app_users")
    rows = await db.fetchall(
        f"""
        SELECT r.id, r.project_id, r.user_id, u.display_name,
               r.requested_role, r.status, r.justification, r.requested_at
        FROM {join_requests} r
        LEFT JOIN {users} u ON u.id = r.user_id
        WHERE r.project_id = ? AND r.status = ?
        ORDER BY r.requested_at
        """,
        project_id,
        RequestStatus.PENDING,
    )
    return [
        JoinRequestItem(
            id=row["id"],
            project_id=row["project_id"],
            user_id=row["user_id"],
            display_name=row["display_name"],
            requested_role=row["requested_role"],
            status=row["status"],
            justification=row["justification"],
            requested_at=row["requested_at"],
        )
        for row in rows
    ]


async def fetch_all_join_requests(
    db: DatabricksWarehousePool,
    settings: Settings,
) -> list[JoinRequestItem]:
    """Every pending join request across the platform (platform admin).

    Join requests may be decided by a platform admin **or** a project admin. The
    per-project queue only helps the latter; without this global queue a platform
    admin would have to guess which project has something waiting.
    """
    join_requests = qualified_table(settings, "dcm_project_join_requests")
    users = qualified_table(settings, "dcm_app_users")
    rows = await db.fetchall(
        f"""
        SELECT r.id, r.project_id, r.user_id, u.display_name,
               r.requested_role, r.status, r.justification, r.requested_at
        FROM {join_requests} r
        LEFT JOIN {users} u ON u.id = r.user_id
        WHERE r.status = ?
        ORDER BY r.requested_at
        """,
        RequestStatus.PENDING,
    )
    return [
        JoinRequestItem(
            id=row["id"],
            project_id=row["project_id"],
            user_id=row["user_id"],
            display_name=row["display_name"],
            requested_role=row["requested_role"],
            status=row["status"],
            justification=row["justification"],
            requested_at=row["requested_at"],
        )
        for row in rows
    ]


async def decide_join_request(
    db: DatabricksWarehousePool,
    settings: Settings,
    current_user: CurrentUser,
    request: Any,
    request_id: str,
    body: RequestDecision,
) -> JoinRequestItem:
    """Approve/reject a join request (project admin); approval adds the member."""
    if body.decision not in {RequestStatus.APPROVED, RequestStatus.REJECTED}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_decision"
        )

    join_requests = qualified_table(settings, "dcm_project_join_requests")
    req = await db.fetchone(
        f"""
        SELECT id, project_id, user_id, requested_role, status, justification, requested_at
        FROM {join_requests}
        WHERE id = ?
        LIMIT 1
        """,
        request_id,
    )
    if req is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="join_request_not_found"
        )

    project_id = req["project_id"]
    if not _is_super_admin(current_user) and not await is_project_admin(
        db, settings, user_id=current_user.id, project_id=project_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="project admin role required"
        )
    if req["status"] != RequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="join_request_not_pending"
        )

    now = _now()
    await db.execute(
        f"""
        UPDATE {join_requests}
        SET status = ?, decided_by = ?, decided_at = ?, decision_reason = ?
        WHERE id = ?
        """,
        body.decision,
        current_user.id,
        now,
        body.reason,
        request_id,
    )

    if body.decision == RequestStatus.APPROVED:
        if (
            await _member_role(
                db, settings, project_id=project_id, user_id=req["user_id"]
            )
            is None
        ):
            members = qualified_table(settings, "dcm_project_members")
            await db.execute(
                f"""
                INSERT INTO {members} (project_id, user_id, role, added_by, added_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                project_id,
                req["user_id"],
                req["requested_role"],
                current_user.id,
                now,
            )
        # Approval provisions access for the joining member (FR-011).
        await _activate_app_user(db, settings, user_id=req["user_id"])

    await log_action(
        db=db,
        settings=settings,
        actor=current_user,
        action="project.join_request.decide",
        target_type="join_request",
        target_id=request_id,
        before_state={"status": req["status"]},
        after_state={"status": body.decision.value},
        request=request,
    )
    return JoinRequestItem(
        id=req["id"],
        project_id=project_id,
        user_id=req["user_id"],
        requested_role=req["requested_role"],
        status=body.decision,
        justification=req["justification"],
        requested_at=req["requested_at"],
    )


async def create_scope_request(
    db: DatabricksWarehousePool,
    settings: Settings,
    current_user: CurrentUser,
    project_id: str,
    body: ScopeRequestCreate,
) -> list[ScopeRequestItem]:
    """A project admin requests new LZs / workspaces for the project scope.

    One submission can carry several items; each becomes its own row so a
    platform admin can still grant part of it, and they share ``requested_at`` +
    ``justification`` so the review queue can present them as one request.
    """
    await _load_project_row(db, settings, project_id)

    now = _now()
    scope_requests = qualified_table(settings, "dcm_project_scope_requests")
    created: list[ScopeRequestItem] = []
    for entry in body.items:
        request_id = str(uuid4())
        await db.execute(
            f"""
            INSERT INTO {scope_requests}
                (id, project_id, scope_type, scope_ref, status, justification,
                 requested_by, requested_at, decided_by, decided_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
            """,
            request_id,
            project_id,
            entry.scope_type,
            entry.scope_ref,
            RequestStatus.PENDING,
            body.justification,
            current_user.id,
            now,
        )
        created.append(
            ScopeRequestItem(
                id=request_id,
                project_id=project_id,
                scope_type=entry.scope_type,
                scope_ref=entry.scope_ref,
                status=RequestStatus.PENDING,
                justification=body.justification,
                requested_by=current_user.id,
                requested_at=now,
            )
        )
    return created


async def fetch_scope_requests(
    db: DatabricksWarehousePool,
    settings: Settings,
) -> list[ScopeRequestItem]:
    """Pending scope-extension requests across all projects (platform_admin)."""
    scope_requests = qualified_table(settings, "dcm_project_scope_requests")
    rows = await db.fetchall(
        f"""
        SELECT id, project_id, scope_type, scope_ref, status, justification,
               requested_by, requested_at
        FROM {scope_requests}
        WHERE status = ?
        ORDER BY requested_at
        """,
        RequestStatus.PENDING,
    )
    return [
        ScopeRequestItem(
            id=row["id"],
            project_id=row["project_id"],
            scope_type=row["scope_type"],
            scope_ref=row["scope_ref"],
            status=row["status"],
            justification=row["justification"],
            requested_by=row["requested_by"],
            requested_at=row["requested_at"],
        )
        for row in rows
    ]


async def decide_scope_request(
    db: DatabricksWarehousePool,
    settings: Settings,
    current_user: CurrentUser,
    request: Any,
    request_id: str,
    body: RequestDecision,
) -> ScopeRequestItem:
    """Approve/reject a scope-extension request; approval adds the scope row."""
    if body.decision not in {RequestStatus.APPROVED, RequestStatus.REJECTED}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_decision"
        )

    scope_requests = qualified_table(settings, "dcm_project_scope_requests")
    req = await db.fetchone(
        f"""
        SELECT id, project_id, scope_type, scope_ref, status, justification,
               requested_by, requested_at
        FROM {scope_requests}
        WHERE id = ?
        LIMIT 1
        """,
        request_id,
    )
    if req is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="scope_request_not_found"
        )
    if req["status"] != RequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="scope_request_not_pending"
        )

    now = _now()
    await db.execute(
        f"""
        UPDATE {scope_requests}
        SET status = ?, decided_by = ?, decided_at = ?, decision_reason = ?
        WHERE id = ?
        """,
        body.decision,
        current_user.id,
        now,
        body.reason,
        request_id,
    )

    if body.decision == RequestStatus.APPROVED:
        project_id = req["project_id"]
        if req["scope_type"] == ScopeType.LZ:
            lz_table = qualified_table(settings, "dcm_project_lz_scope")
            await db.execute(
                f"INSERT INTO {lz_table} (project_id, lz_id, granted_by, granted_at) "
                "VALUES (?, ?, ?, ?)",
                project_id,
                req["scope_ref"],
                current_user.id,
                now,
            )
        else:
            dbx_table = qualified_table(settings, "dcm_project_dbx_scope")
            await db.execute(
                f"INSERT INTO {dbx_table} (project_id, workspace_id, granted_by, granted_at) "
                "VALUES (?, ?, ?, ?)",
                project_id,
                req["scope_ref"],
                current_user.id,
                now,
            )

    await log_action(
        db=db,
        settings=settings,
        actor=current_user,
        action="project.scope_request.decide",
        target_type="scope_request",
        target_id=request_id,
        before_state={"status": req["status"]},
        after_state={"status": body.decision.value, "reason": body.reason},
        request=request,
    )
    return ScopeRequestItem(
        id=req["id"],
        project_id=req["project_id"],
        scope_type=req["scope_type"],
        scope_ref=req["scope_ref"],
        status=body.decision,
        justification=req["justification"],
        requested_by=req["requested_by"],
        requested_at=req["requested_at"],
    )
