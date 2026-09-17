"""Administration endpoints for metric retention policies."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Body, Depends, Request
from fastapi.routing import APIRouter

from ...auth.audit import log_action
from ...auth.dependencies import CurrentUser
from ...auth.scope import require_platform_admin
from ...config import Settings
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.admin_retention_page import (
    fetch_retention_stats,
    load_policies,
    update_policies,
    validate_policy_update,
)

__all__ = ["router"]

router = APIRouter()


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/admin/retention-policies")
async def list_retention_policies(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    items, values = await load_policies(db, _settings(request))
    return {"items": items, "values": values}


@router.patch("/admin/retention-policies")
async def patch_retention_policies(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
    values: Annotated[dict[str, int], Body()],
) -> dict[str, Any]:
    settings = _settings(request)
    _, before_values = await load_policies(db, settings)
    validate_policy_update(values, before_values)

    await update_policies(db, settings, values, actor.id)
    after_values = {**before_values, **values}
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="retention_policy.update",
        target_type="retention_policy",
        before_state=before_values,
        after_state=after_values,
        request=request,
    )
    return {"values": after_values}


@router.get("/admin/retention-policies/stats")
async def get_retention_stats(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await fetch_retention_stats(db, _settings(request))
