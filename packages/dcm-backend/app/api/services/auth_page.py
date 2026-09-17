"""Auth introspection queries — kept out of the route per the route→service→pool pattern."""

from __future__ import annotations

from typing import Any

from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_table

__all__ = ["fetch_user_projects"]


async def fetch_user_projects(
    db: DatabricksWarehousePool,
    settings: Settings,
    user_id: str,
) -> list[dict[str, Any]]:
    """Projects the user belongs to (any status), with their readable name and role."""
    members = qualified_table(settings, "dcm_project_members")
    projects = qualified_table(settings, "dcm_projects")
    rows = await db.fetchall(
        f"""
        SELECT p.id AS project_id, p.name AS name, m.role AS role, p.status AS status
        FROM {members} m
        JOIN {projects} p ON p.id = m.project_id
        WHERE m.user_id = ?
        ORDER BY p.name
        """,
        user_id,
    )
    return [
        {
            "project_id": row["project_id"],
            "name": row["name"],
            "role": row["role"],
            "status": row["status"],
        }
        for row in rows
    ]
