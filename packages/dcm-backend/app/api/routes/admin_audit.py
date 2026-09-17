"""Administration audit log list and CSV export endpoints."""

from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO
from typing import Annotated, Any

from fastapi import Depends, Query, Request, Response
from fastapi.routing import APIRouter

from ...auth.dependencies import CurrentUser
from ...auth.scope import require_platform_admin
from ...config import Settings
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.admin_audit_page import fetch_audit_log, fetch_audit_log_rows

__all__ = ["router"]

router = APIRouter()


@router.get("/admin/audit-log")
async def list_audit_log(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_platform_admin)],
    actor_user_id: Annotated[str | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    target_type: Annotated[str | None, Query()] = None,
    start_date: Annotated[datetime | None, Query()] = None,
    end_date: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    return await fetch_audit_log(
        db,
        settings,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


@router.get("/admin/audit-log/export")
async def export_audit_log(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_platform_admin)],
    actor_user_id: Annotated[str | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    target_type: Annotated[str | None, Query()] = None,
    start_date: Annotated[datetime | None, Query()] = None,
    end_date: Annotated[datetime | None, Query()] = None,
) -> Response:
    settings: Settings = request.app.state.settings
    rows = await fetch_audit_log_rows(
        db,
        settings,
        actor_user_id=actor_user_id,
        action=action,
        target_type=target_type,
        start_date=start_date,
        end_date=end_date,
    )
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id",
            "actor_user_id",
            "action",
            "target_type",
            "target_id",
            "before_state",
            "after_state",
            "ip_address",
            "created_at",
        ],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="dcm-audit-log.csv"'},
    )
