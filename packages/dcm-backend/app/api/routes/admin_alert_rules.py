"""Administration endpoints for alert rules and alert firing history."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Request, status
from fastapi.routing import APIRouter
from pydantic import BaseModel, Field, field_validator, model_validator

from ...auth.alert_evaluator import validate_alert_condition
from ...auth.dependencies import CurrentUser
from ...auth.scope import require_platform_admin
from ...config import Settings
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.admin_alert_rules_page import (
    create_rule,
    delete_rule,
    fetch_rule,
    fetch_rule_firings,
    fetch_rules,
    test_rule,
    update_rule,
)

__all__ = ["router"]

router = APIRouter()
_SEVERITIES = {"info", "warning", "critical"}


class AlertRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    metric_domain: str
    condition_field: str
    condition_operator: str
    condition_threshold: float
    eval_window_hours: int = Field(ge=1, le=168)
    severity: str
    applies_to_lz_ids: list[str] | None = None
    notification_channel_ids: list[str] = Field(default_factory=list)
    cooldown_minutes: int = Field(default=60, ge=0)
    is_active: bool = True

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in _SEVERITIES:
            raise ValueError("severity must be info, warning or critical")
        return normalized

    @model_validator(mode="after")
    def validate_condition(self) -> AlertRuleCreate:
        validate_alert_condition(
            self.metric_domain,
            self.condition_field,
            self.condition_operator,
        )
        return self


class AlertRulePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    metric_domain: str | None = None
    condition_field: str | None = None
    condition_operator: str | None = None
    condition_threshold: float | None = None
    eval_window_hours: int | None = Field(default=None, ge=1, le=168)
    severity: str | None = None
    applies_to_lz_ids: list[str] | None = None
    notification_channel_ids: list[str] | None = None
    cooldown_minutes: int | None = Field(default=None, ge=0)
    is_active: bool | None = None

    @field_validator("severity")
    @classmethod
    def validate_optional_severity(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.lower()
        if normalized not in _SEVERITIES:
            raise ValueError("severity must be info, warning or critical")
        return normalized


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/admin/alert-rules")
async def list_alert_rules(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await fetch_rules(db, _settings(request))


@router.get("/admin/alert-rules/{rule_id}")
async def get_alert_rule(
    rule_id: str,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await fetch_rule(db, _settings(request), rule_id)


@router.post("/admin/alert-rules", status_code=status.HTTP_201_CREATED)
async def create_alert_rule(
    payload: AlertRuleCreate,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await create_rule(db, _settings(request), actor, request, payload)


@router.patch("/admin/alert-rules/{rule_id}")
async def update_alert_rule(
    rule_id: str,
    payload: AlertRulePatch,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await update_rule(db, _settings(request), actor, request, rule_id, payload)


@router.delete("/admin/alert-rules/{rule_id}")
async def delete_alert_rule(
    rule_id: str,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    actor: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await delete_rule(db, _settings(request), actor, request, rule_id)


@router.post("/admin/alert-rules/{rule_id}/test")
async def test_alert_rule(
    rule_id: str,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await test_rule(db, _settings(request), rule_id)


@router.get("/admin/alert-rules/{rule_id}/firings")
async def list_alert_rule_firings(
    rule_id: str,
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    _: Annotated[CurrentUser, Depends(require_platform_admin)],
) -> dict[str, Any]:
    return await fetch_rule_firings(db, _settings(request), rule_id)
