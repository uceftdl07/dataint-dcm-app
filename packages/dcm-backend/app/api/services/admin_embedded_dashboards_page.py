"""Admin CRUD for embedded Databricks AI/BI dashboards.

Kept out of the route per the route→service→pool pattern.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from ...auth.audit import log_action
from ...auth.dependencies import CurrentUser
from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_table
from .embedded_dashboards import _EMBEDDED_DASHBOARDS_TABLE, _is_table_missing_error, _serialize_row

__all__ = [
    "create_dashboard",
    "delete_dashboard",
    "fetch_admin_dashboards",
    "update_dashboard",
]


def _admin_row_to_item(row: dict[str, Any]) -> dict[str, Any]:
    item = _serialize_row(row)
    item["enabled"] = bool(row.get("enabled", True))
    return item


async def _load_admin_rows(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    slug: str | None = None,
) -> list[dict[str, Any]]:
    table = qualified_table(settings, _EMBEDDED_DASHBOARDS_TABLE)
    conditions: list[str] = []
    args: list[Any] = []
    if slug:
        conditions.append("dashboard_slug = ?")
        args.append(slug)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT
            dashboard_slug,
            title,
            description,
            workspace_host,
            workspace_id,
            dashboard_id,
            scope,
            source_lz_id,
            menu_group,
            sort_order,
            enabled
        FROM {table}
        {where_clause}
        ORDER BY sort_order ASC, title ASC
    """
    try:
        return await db.fetchall(query, *args)
    except Exception as exc:
        if _is_table_missing_error(exc):
            qualified = f"{settings.databricks_catalog}.{settings.databricks_schema}"
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "embedded_dashboards_table_missing",
                    "table": f"{qualified}.{_EMBEDDED_DASHBOARDS_TABLE}",
                    "message": "Run python our_catalogs_spn.py to create dcm_embedded_dashboards.",
                },
            ) from exc
        raise


async def fetch_admin_dashboards(
    db: DatabricksWarehousePool,
    settings: Settings,
) -> dict[str, Any]:
    rows = await _load_admin_rows(db, settings)
    return {"items": [_admin_row_to_item(row) for row in rows]}


async def create_dashboard(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    payload: dict[str, Any],
) -> dict[str, Any]:
    slug = payload["dashboard_slug"]
    existing = await _load_admin_rows(db, settings, slug=slug)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Embedded dashboard slug '{slug}' already exists.",
        )

    table = qualified_table(settings, _EMBEDDED_DASHBOARDS_TABLE)
    await db.execute(
        f"""
        INSERT INTO {table} (
            dashboard_slug,
            title,
            description,
            workspace_host,
            workspace_id,
            dashboard_id,
            scope,
            source_lz_id,
            menu_group,
            sort_order,
            enabled,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp())
        """,
        slug,
        payload["title"].strip(),
        payload["description"],
        payload["workspace_host"],
        payload["workspace_id"].strip(),
        payload["dashboard_id"].strip(),
        payload["scope"],
        payload["source_lz_id"],
        payload["menu_group"].strip() or "insights",
        payload["sort_order"],
        payload["enabled"],
    )
    created = await _load_admin_rows(db, settings, slug=slug)
    item = _admin_row_to_item(created[0])
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="embedded_dashboard.create",
        target_type="embedded_dashboard",
        target_id=slug,
        after_state=item,
        request=request,
    )
    return item


async def update_dashboard(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    slug: str,
    patch: dict[str, Any],
) -> dict[str, Any]:
    rows = await _load_admin_rows(db, settings, slug=slug)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Embedded dashboard '{slug}' not found.",
        )

    before = _admin_row_to_item(rows[0])
    if not patch:
        return before

    assignments: list[str] = []
    args: list[Any] = []
    for field, value in patch.items():
        assignments.append(f"{field} = ?")
        args.append(value)
    assignments.append("updated_at = current_timestamp()")
    args.append(slug)

    table = qualified_table(settings, _EMBEDDED_DASHBOARDS_TABLE)
    await db.execute(
        f"""
        UPDATE {table}
        SET {", ".join(assignments)}
        WHERE dashboard_slug = ?
        """,
        *args,
    )
    updated = await _load_admin_rows(db, settings, slug=slug)
    item = _admin_row_to_item(updated[0])
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="embedded_dashboard.update",
        target_type="embedded_dashboard",
        target_id=slug,
        before_state=before,
        after_state=item,
        request=request,
    )
    return item


async def delete_dashboard(
    db: DatabricksWarehousePool,
    settings: Settings,
    actor: CurrentUser,
    request: Any,
    slug: str,
) -> None:
    rows = await _load_admin_rows(db, settings, slug=slug)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Embedded dashboard '{slug}' not found.",
        )

    before = _admin_row_to_item(rows[0])
    table = qualified_table(settings, _EMBEDDED_DASHBOARDS_TABLE)
    await db.execute(
        f"DELETE FROM {table} WHERE dashboard_slug = ?",
        slug,
    )
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="embedded_dashboard.delete",
        target_type="embedded_dashboard",
        target_id=slug,
        before_state=before,
        request=request,
    )
