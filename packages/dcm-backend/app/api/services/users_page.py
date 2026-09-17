"""User / identity governance queries — kept out of the route per the route→service→pool pattern.

The curated_user_metrics table holds one row per (user_id, source_lz_id),
refreshed via full overwrite on each collection cycle.
"""

from __future__ import annotations

import json
from typing import Any

from ...db.connection import DatabricksWarehousePool
from ..routes._lz_filter import add_scope_lz_filter

__all__ = ["fetch_users"]


def _row_to_user(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": row["user_id"],
        "user_name": row["user_name"],
        "display_name": row["display_name"],
        "cloud_provider": row["cloud_provider"],
        "source_lz_id": row["source_lz_id"],
        "subscription_or_account_id": row["subscription_or_account_id"],
        "user_type": row["user_type"],
        "workspace_or_account": row["workspace_or_account"],
        "is_active": row["is_active"],
        "last_activity_at": (
            row["last_activity_at"].isoformat() if row["last_activity_at"] else None
        ),
        "groups": (
            json.loads(row["groups"]) if isinstance(row["groups"], str) else (row["groups"] or [])
        ),
        "roles": (
            json.loads(row["roles"]) if isinstance(row["roles"], str) else (row["roles"] or [])
        ),
        "collected_at": row["collected_at"].isoformat(),
    }


async def fetch_users(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    subscription_or_account_id: str | None,
    user_type: str | None,
    is_active: bool | None,
    search: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """The current user inventory, optionally filtered, plus summary counts.

    Typical usage:
    - List all inactive Databricks users: ``GET /users?user_type=databricks&is_active=false``
    - List all users in a specific LZ: ``GET /users?source_lz_id=azure-lz-prod-fr``
    - Search for a user by name: ``GET /users?search=yahia``
    """
    where_clauses: list[str] = []
    params: list[Any] = []
    add_scope_lz_filter(
        where_clauses,
        params,
        allowed_lz_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )

    if cloud_provider is not None:
        where_clauses.append("cloud_provider = ?")
        params.append(cloud_provider)

    if subscription_or_account_id is not None:
        where_clauses.append("subscription_or_account_id = ?")
        params.append(subscription_or_account_id)

    if user_type is not None:
        where_clauses.append("user_type = ?")
        params.append(user_type)

    if is_active is not None:
        where_clauses.append("is_active = ?")
        params.append(is_active)

    if search is not None:
        where_clauses.append(
            "(LOWER(user_name) LIKE LOWER(?) OR LOWER(display_name) LIKE LOWER(?))"
        )
        params.append(f"%{search}%")
        params.append(f"%{search}%")

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    params.extend([limit, offset])

    rows = await db.fetchall(
        f"""
        SELECT
            user_id, user_name, display_name,
            cloud_provider, source_lz_id, subscription_or_account_id,
            user_type, workspace_or_account, is_active, last_activity_at,
            groups, roles, collected_at
        FROM {db.table('curated_user_metrics')}
        {where_sql}
        ORDER BY is_active DESC, last_activity_at DESC
        LIMIT ? OFFSET ?
        """,
        *params,
    )

    total = await db.fetchscalar(
        f"SELECT COUNT(*) FROM {db.table('curated_user_metrics')} {where_sql}",
        *params,
    )

    # Summary counts for the frontend governance page
    active_count_table = db.table('curated_user_metrics')
    active_count_query = (
        f"SELECT COUNT(*) FROM {active_count_table} {where_sql} AND is_active = TRUE"
        if where_clauses
        else f"SELECT COUNT(*) FROM {active_count_table} WHERE is_active = TRUE"
    )
    active_count = await db.fetchscalar(
        active_count_query,
        *(params if where_clauses else []),
    )

    return {
        "items": [_row_to_user(row) for row in rows],
        "total": total or 0,
        "active_count": active_count or 0,
        "inactive_count": (total or 0) - (active_count or 0),
        "limit": limit,
        "offset": offset,
    }
