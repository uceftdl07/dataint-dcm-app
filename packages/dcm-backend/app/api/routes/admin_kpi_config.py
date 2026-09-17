"""Admin and public endpoints for KPI visual threshold configuration."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Body, Depends, HTTPException, Request, status
from fastapi.routing import APIRouter

from ...auth.audit import log_action
from ...auth.dependencies import CurrentUser, get_current_user
from ...auth.scope import require_platform_admin
from ...config import Settings
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.admin_kpi_config_page import load_config, update_config, validate_thresholds

__all__ = ["router"]

router = APIRouter()


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/admin/kpi-config")
async def get_admin_kpi_config(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    items, values = await load_config(db, _settings(request))
    return {"items": items, "values": values}


@router.patch("/admin/kpi-config")
async def patch_kpi_config(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
    values: Annotated[dict[str, float], Body()],
) -> dict[str, Any]:
    settings = _settings(request)
    _, before_values = await load_config(db, settings)
    unknown = sorted(set(values) - set(before_values))
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Unknown KPI config keys", "keys": unknown},
        )
    after_values = {**before_values, **values}
    validate_thresholds(after_values)

    await update_config(db, settings, values, actor.id)
    await log_action(
        db=db,
        settings=settings,
        actor=actor,
        action="kpi_config.update",
        target_type="kpi_config",
        before_state=before_values,
        after_state=after_values,
        request=request,
    )
    return {"values": after_values}


@router.get("/kpi-config")
async def get_public_kpi_config(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, Any]:
    items, values = await load_config(db, _settings(request))
    return {"items": items, "values": values}
