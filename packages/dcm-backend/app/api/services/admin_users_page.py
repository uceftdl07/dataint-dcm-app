"""Admin CRUD for DCM users, roles, Landing Zone access and project membership.

Kept out of the route per the route→service→pool pattern.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from ...auth.audit import log_action
from ...auth.dependencies import CurrentUser, invalidate_auth_user_cache
from ...auth.role_permissions import (
    DCM_STORED_ROLES,
    PLATFORM_ADMIN_ROLE,
    resolves_to_platform_admin,
)
from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_table
from .admin_access_requests_page import resolve_pending_access_requests_for_email

__all__ = [
    "add_user_lz_access",
    "approve_user",
    "create_user",
    "deactivate_user",
    "delete_user",
    "fetch_user",
    "fetch_users",
    "remove_user_lz_access",
    "replace_user_lz_access",
    "replace_user_projects",
    "update_user_role",
]

DCM_LISTABLE_ROLES = set(DCM_STORED_ROLES)


def _parse_lz_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value] if value else []
        if isinstance(parsed, list):
            return [str(item) for item in parsed if item]
    return []


def _effective_platform_role(row: dict[str, Any]) -> str:
    """Platform tier as the guards see it, legacy rows included."""
    if resolves_to_platform_admin(
        role=row.get("role"), platform_role=row.get("platform_role")
    ):
        return PLATFORM_ADMIN_ROLE
    return str(row.get("platform_role") or "user")


def _row_to_user(
    row: dict[str, Any],
    projects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": row["id"],
        "entra_oid": row["entra_oid"],
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
        # Platform tier is its own column, so the admin table shows the value the
        # backend guards actually read (see ``resolves_to_platform_admin``).
        "platform_role": _effective_platform_role(row),
        "is_active": bool(row["is_active"]),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "last_login_at": row["last_login_at"].isoformat() if row.get("last_login_at") else None,
        "lz_ids": _parse_lz_ids(row.get("lz_ids")),
        "projects": projects or [],
    }


async def _fetch_memberships(
    db: DatabricksWarehousePool,
    settings: Settings,
    user_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    """Map each user_id to its project memberships (feature 016).

    Project membership is the effective data-access key; the admin "Projects"
    editor reads and writes this, not the vestigial ``dcm_user_lz_access`` table.
    """
    if not user_ids:
        return {}
    members = qualified_table(settings, "dcm_project_members")
    projects = qualified_table(settings, "dcm_projects")
    placeholders = ", ".join("?" for _ in user_ids)
    rows = await db.fetchall(
        f"""
        SELECT m.user_id, p.id AS project_id, p.name AS name, m.role AS role, p.status AS status
        FROM {members} m
        JOIN {projects} p ON p.id = m.project_id
        WHERE m.user_id IN ({placeholders})
        ORDER BY p.name
        """,
        *user_ids,
    )
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        result.setdefault(row["user_id"], []).append(
            {
                "id": row["project_id"],
                "name": row["name"],
                "role": row["role"],
                "status": row["status"],
            }
        )
    return result


async def _get_user_row(
    db: DatabricksWarehousePool,
    settings: Settings,
    user_id: str,
) -> dict[str, Any] | None:
    users_table = qualified_table(settings, "dcm_app_users")
    access_table = qualified_table(settings, "dcm_user_lz_access")
    return await db.fetchone(
        f"""
        SELECT
            u.id, u.entra_oid, u.email, u.display_name, u.role, u.platform_role,
            u.is_active, u.created_at, u.last_login_at,
            collect_set(a.lz_id) AS lz_ids
        FROM {users_table} u
        LEFT JOIN {access_table} a ON a.user_id = u.id
        WHERE u.id = ?
        GROUP BY
            u.id, u.entra_oid, u.email, u.display_name, u.role, u.platform_role,
            u.is_active, u.created_at, u.last_login_at
        LIMIT 1
        """,
        user_id,
    )


async def _require_user_row(
    db: DatabricksWarehousePool,
    settings: Settings,
    user_id: str,
) -> dict[str, Any]:
    user = await _get_user_row(db, settings, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    memberships = await _fetch_memberships(db, settings, [user_id])
    return _row_to_user(user, memberships.get(user_id, []))


async def fetch_user(
    db: DatabricksWarehousePool,
    settings: Settings,
    user_id: str,
) -> dict[str, Any]:
    return await _require_user_row(db, settings, user_id)


async def _validate_project_ids(
    db: DatabricksWarehousePool,
    settings: Settings,
    project_ids: list[str],
) -> None:
    if not project_ids:
        return
    table = qualified_table(settings, "dcm_projects")
    placeholders = ", ".join("?" for _ in project_ids)
    rows = await db.fetchall(
        f"SELECT id FROM {table} WHERE id IN ({placeholders})",
        *project_ids,
    )
    existing = {row["id"] for row in rows}
    missing = sorted(set(project_ids) - existing)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Unknown projects", "project_ids": missing},
        )


async def _validate_lz_ids(
    db: DatabricksWarehousePool,
    settings: Settings,
    lz_ids: list[str],
) -> None:
    if not lz_ids:
        return

    table = qualified_table(settings, "dcm_landing_zones")
    placeholders = ", ".join("?" for _ in lz_ids)
    rows = await db.fetchall(
        f"""
        SELECT lz_id
        FROM {table}
        WHERE is_active = TRUE AND lz_id IN ({placeholders})
        """,
        *lz_ids,
    )
    existing = {row["lz_id"] for row in rows}
    missing = sorted(set(lz_ids) - existing)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Unknown or inactive landing zones", "lz_ids": missing},
        )


async def fetch_users(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    role: str | None,
    is_active: bool | None,
    search: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    users_table = qualified_table(settings, "dcm_app_users")
    access_table = qualified_table(settings, "dcm_user_lz_access")

    where_clauses: list[str] = []
    params: list[Any] = []
    if role is not None:
        if role not in DCM_LISTABLE_ROLES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
        where_clauses.append("u.role = ?")
        params.append(role)
    if is_active is not None:
        where_clauses.append("u.is_active = ?")
        params.append(is_active)
    if search is not None:
        where_clauses.append(
            "(LOWER(u.email) LIKE LOWER(?) OR LOWER(u.display_name) LIKE LOWER(?))"
        )
        params.extend([f"%{search}%", f"%{search}%"])

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    count_params = list(params)
    rows = await db.fetchall(
        f"""
        SELECT
            u.id, u.entra_oid, u.email, u.display_name, u.role, u.platform_role,
            u.is_active, u.created_at, u.last_login_at,
            collect_set(a.lz_id) AS lz_ids
        FROM {users_table} u
        LEFT JOIN {access_table} a ON a.user_id = u.id
        {where_sql}
        GROUP BY
            u.id, u.entra_oid, u.email, u.display_name, u.role, u.platform_role,
            u.is_active, u.created_at, u.last_login_at
        ORDER BY u.email
        LIMIT ? OFFSET ?
        """,
        *params,
        limit,
        offset,
    )
    total = await db.fetchscalar(
        f"SELECT COUNT(*) FROM {users_table} u {where_sql}",
        *count_params,
    )
    memberships = await _fetch_memberships(db, settings, [row["id"] for row in rows])
    return {
        "items": [_row_to_user(row, memberships.get(row["id"], [])) for row in rows],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }


async def create_user(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    payload: Any,
) -> dict[str, Any]:
    await _validate_lz_ids(db, settings, payload.lz_ids)

    users_table = qualified_table(settings, "dcm_app_users")
    access_table = qualified_table(settings, "dcm_user_lz_access")
    generated_entra_oid = payload.entra_oid or f"email:{payload.email}"
    existing = await db.fetchone(
        f"""
        SELECT id
        FROM {users_table}
        WHERE LOWER(email) = LOWER(?) OR entra_oid = ?
        LIMIT 1
        """,
        payload.email,
        generated_entra_oid,
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already exists in DCM",
        )

    user_id = str(uuid4())
    display_name = payload.display_name or payload.email
    await db.execute(
        f"""
        INSERT INTO {users_table}
            (id, entra_oid, email, display_name, role, is_active, created_at, last_login_at)
        VALUES (?, ?, ?, ?, ?, TRUE, current_timestamp(), NULL)
        """,
        user_id,
        generated_entra_oid,
        payload.email,
        display_name,
        payload.role,
    )

    for lz_id in payload.lz_ids:
        await db.execute(
            f"""
            INSERT INTO {access_table} (user_id, lz_id, granted_by, granted_at)
            VALUES (?, ?, ?, current_timestamp())
            """,
            user_id,
            lz_id,
            actor.id,
        )

    after = {
        "id": user_id,
        "entra_oid": generated_entra_oid,
        "email": payload.email,
        "display_name": display_name,
        "role": payload.role,
        "is_active": True,
        "created_at": None,
        "last_login_at": None,
        "lz_ids": payload.lz_ids,
    }
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="user.create",
        target_type="user",
        target_id=user_id,
        before_state=None,
        after_state=after,
        request=request,
    )
    await resolve_pending_access_requests_for_email(db, settings, payload.email, actor.email)
    return after


async def update_user_role(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    user_id: str,
    payload: Any,
) -> dict[str, Any]:
    """Set a user's platform tier.

    ``platform_role`` is the authority every guard reads, so it is written here —
    writing only ``role`` used to grant ``/admin`` while still 403-ing on project
    validation and scope decisions. ``role`` is mirrored for the transition, until
    the legacy fallback in ``resolves_to_platform_admin`` is removed.
    """
    if actor.id == user_id and payload.role != PLATFORM_ADMIN_ROLE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An admin cannot revoke their own platform admin tier",
        )
    before = await _require_user_row(db, settings, user_id)
    platform_role = PLATFORM_ADMIN_ROLE if payload.role == PLATFORM_ADMIN_ROLE else "user"
    users_table = qualified_table(settings, "dcm_app_users")
    await db.execute(
        f"""
        UPDATE {users_table}
        SET role = ?, platform_role = ?
        WHERE id = ?
        """,
        payload.role,
        platform_role,
        user_id,
    )
    after = {**before, "role": payload.role, "platform_role": platform_role}
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="user.role.update",
        target_type="user",
        target_id=user_id,
        before_state=before,
        after_state=after,
        request=request,
    )
    # The auth layer caches CurrentUser for 60s — drop it so the new tier applies
    # on the target's next request instead of a minute later.
    invalidate_auth_user_cache(
        entra_oid=before.get("entra_oid"),
        email=before.get("email"),
    )
    return after


async def approve_user(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    user_id: str,
    payload: Any,
) -> dict[str, Any]:
    """Approve a pending user: assign role, landing zones and activate the account."""
    before = await _require_user_row(db, settings, user_id)
    if before["role"] != "pending" and not before["is_active"]:
        pass  # allow re-approval of inactive users
    elif before["role"] != "pending" and before["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already active — use role/LZ endpoints to update access",
        )

    await _validate_lz_ids(db, settings, payload.lz_ids)

    users_table = qualified_table(settings, "dcm_app_users")
    access_table = qualified_table(settings, "dcm_user_lz_access")
    await db.execute(
        f"""
        UPDATE {users_table}
        SET role = ?, is_active = TRUE
        WHERE id = ?
        """,
        payload.role,
        user_id,
    )
    await db.execute(f"DELETE FROM {access_table} WHERE user_id = ?", user_id)
    for lz_id in payload.lz_ids:
        await db.execute(
            f"""
            INSERT INTO {access_table} (user_id, lz_id, granted_by, granted_at)
            VALUES (?, ?, ?, current_timestamp())
            """,
            user_id,
            lz_id,
            actor.id,
        )

    after = {**before, "role": payload.role, "is_active": True, "lz_ids": payload.lz_ids}
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="user.approve",
        target_type="user",
        target_id=user_id,
        before_state=before,
        after_state=after,
        request=request,
    )
    invalidate_auth_user_cache(
        entra_oid=before.get("entra_oid"),
        email=before.get("email"),
    )
    await resolve_pending_access_requests_for_email(db, settings, before["email"], actor.email)
    return after


async def deactivate_user(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    user_id: str,
) -> dict[str, Any]:
    if actor.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An admin cannot deactivate their own account",
        )

    before = await _require_user_row(db, settings, user_id)
    users_table = qualified_table(settings, "dcm_app_users")
    await db.execute(
        f"""
        UPDATE {users_table}
        SET is_active = FALSE
        WHERE id = ?
        """,
        user_id,
    )
    after = {**before, "is_active": False}
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="user.deactivate",
        target_type="user",
        target_id=user_id,
        before_state=before,
        after_state=after,
        request=request,
    )
    return after


async def delete_user(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    user_id: str,
) -> None:
    """Delete a user and everything that grants them access.

    Memberships, pending requests and the vestigial flat LZ rows go with the
    account: leaving a ``dcm_project_members`` row behind would re-grant scope to
    whoever is later provisioned with the same id. Refuses to delete the last
    remaining platform admin, which would lock the platform out of its own
    administration. The audit row is written before the delete, so the deletion
    stays traceable after the account is gone.
    """
    if actor.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An admin cannot delete their own account",
        )

    before = await _require_user_row(db, settings, user_id)
    users_table = qualified_table(settings, "dcm_app_users")

    if before.get("platform_role") == PLATFORM_ADMIN_ROLE:
        remaining = await db.fetchscalar(
            f"""
            SELECT COUNT(*) FROM {users_table}
            WHERE id <> ? AND (platform_role = ? OR role = ?)
            """,
            user_id,
            PLATFORM_ADMIN_ROLE,
            PLATFORM_ADMIN_ROLE,
        )
        if not remaining:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete the last platform admin",
            )

    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="user.delete",
        target_type="user",
        target_id=user_id,
        before_state=before,
        after_state=None,
        request=request,
    )

    for table, column in (
        ("dcm_project_members", "user_id"),
        ("dcm_project_join_requests", "user_id"),
        ("dcm_user_lz_access", "user_id"),
        ("dcm_user_notification_preferences", "user_id"),
    ):
        await db.execute(
            f"DELETE FROM {qualified_table(settings, table)} WHERE {column} = ?",
            user_id,
        )
    await db.execute(f"DELETE FROM {users_table} WHERE id = ?", user_id)

    invalidate_auth_user_cache(
        entra_oid=before.get("entra_oid"),
        email=before.get("email"),
    )


async def replace_user_lz_access(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    user_id: str,
    payload: Any,
) -> dict[str, Any]:
    before = await _require_user_row(db, settings, user_id)
    await _validate_lz_ids(db, settings, payload.lz_ids)

    access_table = qualified_table(settings, "dcm_user_lz_access")
    await db.execute(f"DELETE FROM {access_table} WHERE user_id = ?", user_id)
    for lz_id in payload.lz_ids:
        await db.execute(
            f"""
            INSERT INTO {access_table} (user_id, lz_id, granted_by, granted_at)
            VALUES (?, ?, ?, current_timestamp())
            """,
            user_id,
            lz_id,
            actor.id,
        )

    after = {**before, "lz_ids": payload.lz_ids}
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="user.lz_access.replace",
        target_type="user",
        target_id=user_id,
        before_state=before,
        after_state=after,
        request=request,
    )
    if before.get("is_active"):
        await resolve_pending_access_requests_for_email(db, settings, before["email"], actor.email)
    return after


async def add_user_lz_access(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    user_id: str,
    lz_id: str,
) -> dict[str, Any]:
    before = await _require_user_row(db, settings, user_id)
    await _validate_lz_ids(db, settings, [lz_id])

    access_table = qualified_table(settings, "dcm_user_lz_access")
    await db.execute(
        f"""
        INSERT INTO {access_table} (user_id, lz_id, granted_by, granted_at)
        SELECT ?, ?, ?, current_timestamp()
        WHERE NOT EXISTS (
            SELECT 1 FROM {access_table}
            WHERE user_id = ? AND lz_id = ?
        )
        """,
        user_id,
        lz_id,
        actor.id,
        user_id,
        lz_id,
    )
    after_lz_ids = sorted(set(before["lz_ids"]) | {lz_id})
    after = {**before, "lz_ids": after_lz_ids}
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="user.lz_access.add",
        target_type="user",
        target_id=user_id,
        before_state=before,
        after_state=after,
        request=request,
    )
    return after


async def remove_user_lz_access(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    user_id: str,
    lz_id: str,
) -> dict[str, Any]:
    before = await _require_user_row(db, settings, user_id)
    access_table = qualified_table(settings, "dcm_user_lz_access")
    await db.execute(
        f"""
        DELETE FROM {access_table}
        WHERE user_id = ? AND lz_id = ?
        """,
        user_id,
        lz_id,
    )
    after_lz_ids = [item for item in before["lz_ids"] if item != lz_id]
    after = {**before, "lz_ids": after_lz_ids}
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="user.lz_access.remove",
        target_type="user",
        target_id=user_id,
        before_state=before,
        after_state=after,
        request=request,
    )
    return after


async def replace_user_projects(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    user_id: str,
    payload: Any,
) -> dict[str, Any]:
    """Set the full project membership of a user (feature 016).

    Project membership is the effective data-access key: the caller's scope is
    the union of the LZ/workspace scopes of their ``active`` projects. Applying
    a new list diffs against the current memberships (upsert role, delete the
    rest) and invalidates the auth cache so the scope recomputes on next request.
    """
    before = await _require_user_row(db, settings, user_id)
    desired = {item.project_id: item.role for item in payload.projects}
    await _validate_project_ids(db, settings, list(desired))

    members = qualified_table(settings, "dcm_project_members")
    current = {row["id"]: row["role"] for row in before["projects"]}

    for project_id in set(current) - set(desired):
        await db.execute(
            f"DELETE FROM {members} WHERE project_id = ? AND user_id = ?",
            project_id,
            user_id,
        )
    for project_id, role in desired.items():
        if project_id in current:
            if current[project_id] != role:
                await db.execute(
                    f"UPDATE {members} SET role = ? WHERE project_id = ? AND user_id = ?",
                    role,
                    project_id,
                    user_id,
                )
        else:
            await db.execute(
                f"""
                INSERT INTO {members} (project_id, user_id, role, added_by, added_at)
                VALUES (?, ?, ?, ?, current_timestamp())
                """,
                project_id,
                user_id,
                role,
                actor.id,
            )

    after = await _require_user_row(db, settings, user_id)
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="user.projects.replace",
        target_type="user",
        target_id=user_id,
        before_state=before,
        after_state=after,
        request=request,
    )
    invalidate_auth_user_cache(
        entra_oid=before.get("entra_oid"),
        email=before.get("email"),
    )
    return after
