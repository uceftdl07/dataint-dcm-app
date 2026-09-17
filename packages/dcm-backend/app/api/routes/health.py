"""Health check endpoint.

``GET /api/v1/health``  — always accessible (no authentication required).

Returns:
    200 OK   — service is up and database is reachable.
    503      — database unreachable (pool initialisation failed or connection lost).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request
from fastapi.routing import APIRouter

from ...db.connection import DatabricksWarehousePool

__all__ = ["router"]

router = APIRouter()


@router.get("/health/live")
async def liveness_check() -> dict[str, Any]:
    """Liveness probe — process is up (no database required).

    Used by the Docker/ECS container health check so tasks are not killed while
    Databricks credentials are being fixed or the warehouse is temporarily down.
    """
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "dcm-backend",
    }


@router.get("/health")
async def health_check(request: Request) -> dict[str, Any]:
    """Readiness probe — database must be reachable.

    The database check executes a trivial ``SELECT 1`` against the SQL Warehouse.
    A failure raises **503 Service Unavailable** so load-balancer health
    checks can remove the task from rotation.
    """
    pool: DatabricksWarehousePool | None = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "degraded",
                "database": "unreachable",
                "error": "Database pool not initialized",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "service": "dcm-backend",
            },
        )

    db_ok = False
    db_error: str | None = None

    try:
        result = await pool.fetchscalar("SELECT 1")
        db_ok = result == 1
    except Exception as exc:  # noqa: BLE001
        db_error = str(exc)

    if not db_ok:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "degraded",
                "database": "unreachable",
                "error": db_error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "service": "dcm-backend",
            },
        )

    return {
        "status": "ok",
        "database": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "dcm-backend",
    }
