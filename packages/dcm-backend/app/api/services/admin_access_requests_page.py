"""Portal access request inbox — reads/writes ``dcm_access_requests``.

Kept out of the route per the route→service→pool pattern.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status

from ...auth.audit import log_action
from ...auth.dependencies import CurrentUser
from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_table

__all__ = [
    "ACCESS_REQUEST_STATUSES",
    "ACCESS_REQUEST_TYPES",
    "auto_resolve_fulfilled_pending_requests",
    "fetch_access_requests",
    "resolve_pending_access_requests_for_email",
    "review_access_request",
]

ACCESS_REQUEST_STATUSES = {"pending", "approved", "rejected"}
ACCESS_REQUEST_TYPES = {"new_account", "reactivation", "scope_extension"}


def _parse_lz_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []
    return []


def _infer_request_type(user_id: Any, user_is_active: Any) -> str:
    if user_id is None:
        return "new_account"
    if not bool(user_is_active):
        return "reactivation"
    return "scope_extension"


def _row_to_access_request(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "email": row["email"],
        "display_name": row["display_name"],
        "entra_oid": row.get("entra_oid"),
        "justification": row["justification"],
        "requested_lz_ids": _parse_lz_ids(row.get("requested_lz_ids")),
        "status": row["status"],
        "request_type": _infer_request_type(row.get("user_id"), row.get("user_is_active")),
        "requested_at": row["requested_at"].isoformat() if row.get("requested_at") else None,
        "reviewed_by": row.get("reviewed_by"),
        "reviewed_at": row["reviewed_at"].isoformat() if row.get("reviewed_at") else None,
    }


async def resolve_pending_access_requests_for_email(
    db: DatabricksWarehousePool,
    settings: Settings,
    email: str,
    reviewer: str,
) -> None:
    """Mark pending inbox rows as approved after access was granted elsewhere."""
    requests_table = qualified_table(settings, "dcm_access_requests")
    await db.execute(
        f"""
        UPDATE {requests_table}
        SET status = 'approved', reviewed_by = ?, reviewed_at = current_timestamp()
        WHERE status = 'pending' AND LOWER(email) = LOWER(?)
        """,
        reviewer,
        email,
    )


async def auto_resolve_fulfilled_pending_requests(
    db: DatabricksWarehousePool,
    settings: Settings,
    reviewer: str,
) -> None:
    """Close pending requests when the requester already has an active DCM account."""
    requests_table = qualified_table(settings, "dcm_access_requests")
    users_table = qualified_table(settings, "dcm_app_users")
    await db.execute(
        f"""
        UPDATE {requests_table} ar
        SET status = 'approved', reviewed_by = ?, reviewed_at = current_timestamp()
        WHERE ar.status = 'pending'
          AND EXISTS (
              SELECT 1
              FROM {users_table} u
              WHERE LOWER(u.email) = LOWER(ar.email)
                AND u.is_active = TRUE
          )
        """,
        reviewer,
    )


async def _get_access_request_row(
    db: DatabricksWarehousePool,
    settings: Settings,
    request_id: str,
) -> dict[str, Any] | None:
    requests_table = qualified_table(settings, "dcm_access_requests")
    users_table = qualified_table(settings, "dcm_app_users")
    return await db.fetchone(
        f"""
        SELECT
            ar.id,
            ar.email,
            ar.display_name,
            ar.entra_oid,
            ar.justification,
            ar.requested_lz_ids,
            ar.status,
            ar.requested_at,
            ar.reviewed_by,
            ar.reviewed_at,
            u.id AS user_id,
            u.is_active AS user_is_active
        FROM {requests_table} ar
        LEFT JOIN {users_table} u ON LOWER(ar.email) = LOWER(u.email)
        WHERE ar.id = ?
        LIMIT 1
        """,
        request_id,
    )


async def fetch_access_requests(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    *,
    status_filter: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    await auto_resolve_fulfilled_pending_requests(db, settings, actor.email)

    requests_table = qualified_table(settings, "dcm_access_requests")
    users_table = qualified_table(settings, "dcm_app_users")

    where_clauses: list[str] = []
    params: list[Any] = []
    if status_filter is not None:
        normalized_status = status_filter.strip().lower()
        if normalized_status not in ACCESS_REQUEST_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="status must be pending, approved or rejected",
            )
        where_clauses.append("ar.status = ?")
        params.append(normalized_status)

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    count_params = list(params)
    rows = await db.fetchall(
        f"""
        SELECT
            ar.id,
            ar.email,
            ar.display_name,
            ar.entra_oid,
            ar.justification,
            ar.requested_lz_ids,
            ar.status,
            ar.requested_at,
            ar.reviewed_by,
            ar.reviewed_at,
            u.id AS user_id,
            u.is_active AS user_is_active
        FROM {requests_table} ar
        LEFT JOIN {users_table} u ON LOWER(ar.email) = LOWER(u.email)
        {where_sql}
        ORDER BY ar.requested_at DESC
        LIMIT ? OFFSET ?
        """,
        *params,
        limit,
        offset,
    )
    total = await db.fetchscalar(
        f"SELECT COUNT(*) FROM {requests_table} ar {where_sql}",
        *count_params,
    )
    pending_total = await db.fetchscalar(
        f"SELECT COUNT(*) FROM {requests_table} WHERE status = 'pending'",
    )
    return {
        "items": [_row_to_access_request(row) for row in rows],
        "total": total or 0,
        "pending_total": pending_total or 0,
        "limit": limit,
        "offset": offset,
    }


async def review_access_request(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    request_id: str,
    *,
    new_status: str,
    review_note: str | None,
) -> dict[str, Any]:
    row = await _get_access_request_row(db, settings, request_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Access request not found"
        )
    if row["status"] != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Request already {row['status']}",
        )

    requests_table = qualified_table(settings, "dcm_access_requests")
    await db.execute(
        f"""
        UPDATE {requests_table}
        SET status = ?, reviewed_by = ?, reviewed_at = current_timestamp()
        WHERE id = ?
        """,
        new_status,
        actor.email,
        request_id,
    )

    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action=f"access_request.{new_status}",
        target_type="access_request",
        target_id=request_id,
        after_state={
            "email": row["email"],
            "status": new_status,
            "review_note": review_note,
        },
        request=request,
    )

    updated = await _get_access_request_row(db, settings, request_id)
    assert updated is not None
    return _row_to_access_request(updated)
