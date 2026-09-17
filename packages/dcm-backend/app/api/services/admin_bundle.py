"""Aggregated admin page queries — single HTTP round-trip for /admin."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import Request

from ...auth.dependencies import CurrentUser
from ...db.connection import DatabricksWarehousePool
from ..routes.admin_access_requests import list_admin_access_requests
from ..routes.admin_alert_rules import list_alert_rules
from ..routes.admin_audit import list_audit_log
from ..routes.admin_channels import list_notification_channels
from ..routes.admin_collectors import list_collector_status
from ..routes.admin_kpi_config import get_admin_kpi_config
from ..routes.admin_lz import list_admin_landing_zones
from ..routes.admin_maintenance import list_maintenance_windows
from ..routes.admin_retention import get_retention_stats, list_retention_policies
from ..routes.admin_users import list_admin_users

__all__ = ["fetch_admin_full"]

_CORE_SECTIONS = frozenset({"users", "landingZones", "accessRequests", "channels", "alertRules"})
_EXTENDED_SECTIONS = frozenset({
    "collectors",
    "kpiConfig",
    "retentionPolicies",
    "retentionStats",
    "maintenanceWindows",
    "auditLog",
})
_ALL_SECTIONS = _CORE_SECTIONS | _EXTENDED_SECTIONS


def _resolve_sections(sections: str | None) -> frozenset[str]:
    if not sections or sections.strip().lower() == "all":
        return _ALL_SECTIONS

    normalized = sections.strip().lower()
    if normalized == "core":
        return _CORE_SECTIONS
    if normalized == "extended":
        return _EXTENDED_SECTIONS

    requested = {item.strip() for item in sections.split(",") if item.strip()}
    unknown = requested - _ALL_SECTIONS
    if unknown:
        return _ALL_SECTIONS
    return frozenset(requested)


async def _safe_retention_stats(
    request: Request,
    db: DatabricksWarehousePool,
    actor: CurrentUser,
) -> dict[str, Any]:
    try:
        return await get_retention_stats(request, db, actor)
    except Exception:
        return {"items": [], "total": 0}


async def fetch_admin_full(
    request: Request,
    db: DatabricksWarehousePool,
    actor: CurrentUser,
    *,
    access_request_status: str | None,
    access_request_limit: int,
    access_request_offset: int,
    audit_limit: int,
    audit_offset: int,
    sections: str | None = None,
) -> dict[str, Any]:
    """Load admin tab data in parallel (optionally core-only or extended-only)."""
    selected = _resolve_sections(sections)
    tasks: dict[str, Any] = {}

    if "users" in selected:
        tasks["users"] = list_admin_users(request, db, actor, limit=200)
    if "landingZones" in selected:
        tasks["landingZones"] = list_admin_landing_zones(request, db, actor)
    if "alertRules" in selected:
        tasks["alertRules"] = list_alert_rules(request, db, actor)
    if "collectors" in selected:
        tasks["collectors"] = list_collector_status(request, db, actor)
    if "channels" in selected:
        tasks["channels"] = list_notification_channels(request, db, actor)
    if "accessRequests" in selected:
        tasks["accessRequests"] = list_admin_access_requests(
            request,
            db,
            actor,
            status_filter=access_request_status,
            limit=access_request_limit,
            offset=access_request_offset,
        )
    if "kpiConfig" in selected:
        tasks["kpiConfig"] = get_admin_kpi_config(request, db, actor)
    if "retentionPolicies" in selected:
        tasks["retentionPolicies"] = list_retention_policies(request, db, actor)
    if "retentionStats" in selected:
        tasks["retentionStats"] = _safe_retention_stats(request, db, actor)
    if "maintenanceWindows" in selected:
        tasks["maintenanceWindows"] = list_maintenance_windows(request, db, actor)
    if "auditLog" in selected:
        tasks["auditLog"] = list_audit_log(request, db, actor, limit=audit_limit, offset=audit_offset)

    if not tasks:
        return {}

    keys = list(tasks.keys())
    results = await asyncio.gather(*tasks.values())
    return dict(zip(keys, results, strict=True))
