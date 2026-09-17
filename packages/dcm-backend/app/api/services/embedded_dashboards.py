"""Read embedded Databricks AI/BI dashboards configured in Unity Catalog."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_table

__all__ = ["fetch_embedded_dashboards", "fetch_embedded_dashboard_by_slug"]

_EMBEDDED_DASHBOARDS_TABLE = "dcm_embedded_dashboards"


def _normalize_host(workspace_host: str) -> str:
    return workspace_host.rstrip("/")


def _build_embed_url(workspace_host: str, dashboard_id: str, workspace_id: str) -> str:
    host = _normalize_host(workspace_host)
    return f"{host}/embed/dashboardsv3/{dashboard_id}?o={workspace_id}"


def _build_direct_url(workspace_host: str, dashboard_id: str, workspace_id: str) -> str:
    host = _normalize_host(workspace_host)
    return f"{host}/dashboardsv3/{dashboard_id}/published?o={workspace_id}"


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    workspace_host = str(row["workspace_host"])
    workspace_id = str(row["workspace_id"])
    dashboard_id = str(row["dashboard_id"])
    return {
        "dashboard_slug": row["dashboard_slug"],
        "title": row["title"],
        "description": row.get("description"),
        "workspace_host": workspace_host,
        "workspace_id": workspace_id,
        "dashboard_id": dashboard_id,
        "scope": row["scope"],
        "source_lz_id": row.get("source_lz_id"),
        "menu_group": row["menu_group"],
        "sort_order": row["sort_order"],
        "embed_url": _build_embed_url(workspace_host, dashboard_id, workspace_id),
        "direct_url": _build_direct_url(workspace_host, dashboard_id, workspace_id),
    }


def _is_table_missing_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return _EMBEDDED_DASHBOARDS_TABLE in message and (
        "table_or_view_not_found" in message or "cannot be found" in message
    )


def _lz_scope_allowed(row: dict[str, Any], allowed_lz_ids: list[str] | None) -> bool:
    scope = str(row.get("scope") or "global")
    if scope != "landing_zone":
        return True
    if allowed_lz_ids is None:
        return True
    source_lz_id = row.get("source_lz_id")
    return bool(source_lz_id and source_lz_id in allowed_lz_ids)


async def fetch_embedded_dashboards(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    allowed_lz_ids: list[str] | None,
    menu_group: str | None = None,
) -> list[dict[str, Any]]:
    table = qualified_table(settings, _EMBEDDED_DASHBOARDS_TABLE)
    conditions = ["enabled = true"]
    args: list[Any] = []

    if menu_group:
        conditions.append("menu_group = ?")
        args.append(menu_group)

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
            sort_order
        FROM {table}
        WHERE {" AND ".join(conditions)}
        ORDER BY sort_order ASC, title ASC
    """

    try:
        rows = await db.fetchall(query, *args)
    except Exception as exc:
        if _is_table_missing_error(exc):
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "embedded_dashboards_table_missing",
                    "table": f"{settings.databricks_catalog}.{settings.databricks_schema}.{_EMBEDDED_DASHBOARDS_TABLE}",
                    "message": "Run python our_catalogs_spn.py to create dcm_embedded_dashboards.",
                },
            ) from exc
        raise

    return [
        _serialize_row(row)
        for row in rows
        if _lz_scope_allowed(row, allowed_lz_ids)
    ]


async def fetch_embedded_dashboard_by_slug(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    slug: str,
    allowed_lz_ids: list[str] | None,
) -> dict[str, Any]:
    items = await fetch_embedded_dashboards(db, settings, allowed_lz_ids=allowed_lz_ids)
    for item in items:
        if item["dashboard_slug"] == slug:
            return item
    raise HTTPException(status_code=404, detail=f"Embedded dashboard '{slug}' not found.")
