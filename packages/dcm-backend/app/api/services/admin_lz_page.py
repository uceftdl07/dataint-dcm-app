"""Admin CRUD for the Landing Zone registry.

Kept out of the route per the route→service→pool pattern.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from ...auth.audit import log_action
from ...auth.dependencies import CurrentUser
from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_lz_dimension_table, qualified_table

__all__ = [
    "create_lz",
    "deactivate_lz",
    "fetch_lz",
    "fetch_lzs",
    "update_lz",
]


def _row_to_lz(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "lz_id": row["lz_id"],
        "display_name": row["display_name"],
        "cloud_provider": row["cloud_provider"],
        "region": row["region"],
        "environment": row["environment"],
        "ba_name": row["ba_name"],
        "collector_names": row["collector_names"] or [],
        "is_active": bool(row["is_active"]),
        "registered_at": row["registered_at"].isoformat() if row.get("registered_at") else None,
        "registered_by": row["registered_by"],
        "notes": row["notes"],
        "user_count": int(row.get("user_count") or 0),
    }


def _row_to_lz_from_sync(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "lz_id": row["lz_id"],
        "display_name": row.get("display_name") or row.get("lz_name") or row["lz_id"],
        "cloud_provider": row["cloud_provider"],
        "region": row.get("region"),
        "environment": row.get("environment"),
        "ba_name": row.get("ba_name") or row.get("owner_team"),
        "collector_names": row.get("collector_names") or [],
        "is_active": bool(row.get("is_active", True)),
        "registered_at": (
            row["registered_at"].isoformat()
            if row.get("registered_at") and hasattr(row["registered_at"], "isoformat")
            else (str(row["registered_at"]) if row.get("registered_at") else None)
        ),
        "registered_by": row.get("registered_by"),
        "notes": row.get("notes"),
        "user_count": int(row.get("user_count") or 0),
    }


async def _list_lz_rows_from_sync(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    cloud_provider: str | None = None,
    environment: str | None = None,
    is_active: bool | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    lz_dimension_table = qualified_lz_dimension_table(settings)
    access_table = qualified_table(settings, "dcm_user_lz_access")

    where_clauses: list[str] = []
    params: list[Any] = []
    if cloud_provider is not None:
        where_clauses.append("l.cloud_provider = ?")
        params.append(cloud_provider)
    if environment is not None:
        where_clauses.append("l.environment = ?")
        params.append(environment)
    # dim_landing_zone has no is_active column: every registered LZ is active,
    # so is_active=False can never match while is_active=True/None is a no-op.
    if is_active is False:
        return []
    if search is not None:
        where_clauses.append(
            "(LOWER(l.lz_id) LIKE LOWER(?) OR LOWER(l.lz_name) LIKE LOWER(?))"
        )
        params.extend([f"%{search}%", f"%{search}%"])

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    return await db.fetchall(
        f"""
        SELECT
            l.lz_id,
            l.lz_name,
            l.lz_name AS display_name,
            l.cloud_provider,
            l.region,
            l.environment,
            l.owner_team AS ba_name,
            l.onboarded_at AS registered_at,
            COUNT(a.user_id) AS user_count
        FROM {lz_dimension_table} l
        LEFT JOIN {access_table} a ON a.lz_id = l.lz_id
        {where_sql}
        GROUP BY
            l.lz_id, l.lz_name, l.cloud_provider, l.region, l.environment,
            l.owner_team, l.onboarded_at
        ORDER BY l.cloud_provider, l.lz_id
        """,
        *params,
    )


async def _get_lz_row(
    db: DatabricksWarehousePool,
    settings: Settings,
    lz_id: str,
) -> dict[str, Any] | None:
    lz_table = qualified_table(settings, "dcm_landing_zones")
    access_table = qualified_table(settings, "dcm_user_lz_access")
    return await db.fetchone(
        f"""
        SELECT
            l.lz_id, l.display_name, l.cloud_provider, l.region, l.environment,
            l.ba_name, l.collector_names, l.is_active, l.registered_at,
            l.registered_by, l.notes, COUNT(a.user_id) AS user_count
        FROM {lz_table} l
        LEFT JOIN {access_table} a ON a.lz_id = l.lz_id
        WHERE l.lz_id = ?
        GROUP BY
            l.lz_id, l.display_name, l.cloud_provider, l.region, l.environment,
            l.ba_name, l.collector_names, l.is_active, l.registered_at,
            l.registered_by, l.notes
        LIMIT 1
        """,
        lz_id,
    )


async def _require_lz_row(
    db: DatabricksWarehousePool,
    settings: Settings,
    lz_id: str,
) -> dict[str, Any]:
    row = await _get_lz_row(db, settings, lz_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Landing Zone not found",
        )
    return _row_to_lz(row)


async def fetch_lzs(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    cloud_provider: str | None,
    environment: str | None,
    is_active: bool | None,
    search: str | None,
) -> dict[str, Any]:
    rows = await _list_lz_rows_from_sync(
        db,
        settings,
        cloud_provider=cloud_provider,
        environment=environment,
        is_active=is_active,
        search=search,
    )
    return {
        "items": [_row_to_lz_from_sync(row) for row in rows],
        "total": len(rows),
    }


async def fetch_lz(
    db: DatabricksWarehousePool,
    settings: Settings,
    lz_id: str,
) -> dict[str, Any]:
    return await _require_lz_row(db, settings, lz_id)


async def create_lz(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    payload: Any,
) -> dict[str, Any]:
    if await _get_lz_row(db, settings, payload.lz_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Landing Zone already exists",
        )

    lz_table = qualified_table(settings, "dcm_landing_zones")
    await db.execute(
        f"""
        INSERT INTO {lz_table}
            (lz_id, display_name, cloud_provider, region, environment, ba_name,
             collector_names, is_active, registered_at, registered_by, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, TRUE, current_timestamp(), ?, ?)
        """,
        payload.lz_id,
        payload.display_name,
        payload.cloud_provider,
        payload.region,
        payload.environment,
        payload.ba_name,
        payload.collector_names,
        actor.id,
        payload.notes,
    )
    created = {
        **payload.model_dump(),
        "is_active": True,
        "registered_by": actor.id,
        "user_count": 0,
    }
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="landing_zone.create",
        target_type="landing_zone",
        target_id=payload.lz_id,
        after_state=created,
        request=request,
    )
    return created


async def update_lz(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    lz_id: str,
    payload: Any,
) -> dict[str, Any]:
    before = await _require_lz_row(db, settings, lz_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return before

    lz_table = qualified_table(settings, "dcm_landing_zones")
    assignments = ", ".join(f"{column} = ?" for column in changes)
    await db.execute(
        f"""
        UPDATE {lz_table}
        SET {assignments}
        WHERE lz_id = ?
        """,
        *changes.values(),
        lz_id,
    )
    after = {**before, **changes}
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="landing_zone.update",
        target_type="landing_zone",
        target_id=lz_id,
        before_state=before,
        after_state=after,
        request=request,
    )
    return after


async def deactivate_lz(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    lz_id: str,
) -> dict[str, Any]:
    before = await _require_lz_row(db, settings, lz_id)
    lz_table = qualified_table(settings, "dcm_landing_zones")
    await db.execute(
        f"""
        UPDATE {lz_table}
        SET is_active = FALSE
        WHERE lz_id = ?
        """,
        lz_id,
    )
    after = {**before, "is_active": False}
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="landing_zone.deactivate",
        target_type="landing_zone",
        target_id=lz_id,
        before_state=before,
        after_state=after,
        request=request,
    )
    return after
