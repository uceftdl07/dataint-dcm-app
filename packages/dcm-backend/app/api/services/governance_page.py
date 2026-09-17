"""Governance page queries — standard checks, score, and landing zone catalogs."""

from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Any

from fastapi import HTTPException, status

from ...auth.dependencies import CurrentUser
from ...cache.response_cache import build_cache_key, cache_key_ids, get_cached_response
from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_lz_dimension_table
from ..routes._lz_filter import add_lz_filter, add_scope_lz_filter

__all__ = [
    "fetch_active_landing_zone_rows",
    "fetch_governance_page_bundle",
    "fetch_landing_zone_details",
    "fetch_landing_zones_access_overview",
    "fetch_standard_check_score",
    "fetch_standard_checks_list",
    "row_to_check",
    "row_to_landing_zone",
]

_DEFAULT_PAGE_LIMIT = 100
_CACHE_TTL_SECONDS = 120.0

logger = logging.getLogger(__name__)


def row_to_check(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "check_id": row["check_id"],
        "check_name": row["check_name"],
        "cloud_provider": row["cloud_provider"],
        "source_lz_id": row["source_lz_id"],
        "subscription_or_account_id": row["subscription_or_account_id"],
        "check_state": row["check_state"],
        "resource_id": row["resource_id"],
        "resource_name": row["resource_name"],
        "resource_type": row["resource_type"],
        "check_effect": row["check_effect"],
        "non_check_reasons": row["non_check_reasons"] or [],
        "evaluated_at": row["evaluated_at"].isoformat()
        if hasattr(row["evaluated_at"], "isoformat")
        else str(row["evaluated_at"]),
    }


def _iso_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def row_to_landing_zone(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "lz_id": row["lz_id"],
        "lz_name": row.get("lz_name") or row.get("display_name") or row["lz_id"],
        "cloud_provider": row["cloud_provider"],
        "subscription_or_account_id": row.get("subscription_or_account_id"),
        "region": row.get("region"),
        "environment": row.get("environment"),
        "ba_name": row.get("owner_team") or row.get("ba_name"),
        "onboarded_at": _iso_or_none(row.get("onboarded_at") or row.get("registered_at")),
    }


def _user_has_lz_access(current_user: CurrentUser, lz_id: str) -> bool:
    if current_user.role in {"admin", "super_admin"}:
        return True
    return lz_id in current_user.lz_ids


async def fetch_active_landing_zone_rows(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    allowed_lz_ids: list[str] | None = None,
    cloud_provider: str | None = None,
    environment: str | None = None,
    ba_name: str | None = None,
) -> list[dict[str, Any]]:
    where_clauses: list[str] = [
        "subscription_or_account_id IS NOT NULL",
        "TRIM(subscription_or_account_id) <> ''",
    ]
    params: list[Any] = []
    add_lz_filter(where_clauses, params, allowed_lz_ids, column="lz_id")

    if cloud_provider is not None:
        where_clauses.append("cloud_provider = ?")
        params.append(cloud_provider)

    if environment is not None:
        where_clauses.append("environment = ?")
        params.append(environment)

    if ba_name is not None:
        where_clauses.append("LOWER(owner_team) LIKE LOWER(?)")
        params.append(f"%{ba_name}%")

    where_sql = "WHERE " + " AND ".join(where_clauses)
    lz_dimension_table = qualified_lz_dimension_table(settings)

    try:
        return await db.fetchall(
            f"""
            SELECT
                lz_id,
                lz_name,
                cloud_provider,
                subscription_or_account_id,
                region,
                environment,
                owner_team,
                onboarded_at
            FROM {lz_dimension_table}
            {where_sql}
            ORDER BY cloud_provider, lz_name
            """,
            *params,
        )
    except Exception as exc:
        logger.error("dim_landing_zone query failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Landing zone catalog unavailable (dim_landing_zone)",
        ) from exc


async def fetch_landing_zone_details(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    allowed_lz_ids: list[str] | None,
    cloud_provider: str | None,
    environment: str | None,
    ba_name: str | None,
) -> dict[str, Any]:
    rows = await fetch_active_landing_zone_rows(
        db,
        settings,
        allowed_lz_ids=allowed_lz_ids,
        cloud_provider=cloud_provider,
        environment=environment,
        ba_name=ba_name,
    )
    return {
        "items": [row_to_landing_zone(row) for row in rows],
        "total": len(rows),
    }


async def fetch_landing_zones_access_overview(
    db: DatabricksWarehousePool,
    settings: Settings,
    current_user: CurrentUser,
    *,
    cloud_provider: str | None,
    environment: str | None,
    ba_name: str | None,
) -> dict[str, Any]:
    rows = await fetch_active_landing_zone_rows(
        db,
        settings,
        cloud_provider=cloud_provider,
        environment=environment,
        ba_name=ba_name,
    )

    items: list[dict[str, Any]] = []
    granted_count = 0
    for row in rows:
        lz = row_to_landing_zone(row)
        has_access = _user_has_lz_access(current_user, lz["lz_id"])
        if has_access:
            granted_count += 1

        items.append({
            **lz,
            "has_access": has_access,
        })

    return {
        "items": items,
        "total": len(items),
        "granted_count": granted_count,
        "denied_count": len(items) - granted_count,
        "unrestricted_access": current_user.role in {"admin", "super_admin"},
    }


async def fetch_standard_checks_list(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    subscription_or_account_id: str | None,
    check_state: str | None,
    resource_type: str | None,
    check_name: str | None,
    start_date: date | None,
    end_date: date | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    where_clauses: list[str] = []
    params: list[Any] = []
    add_scope_lz_filter(
        where_clauses,
        params,
        allowed_lz_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )

    if cloud_provider is not None:
        where_clauses.append("cloud_provider = ?")
        params.append(cloud_provider)

    if subscription_or_account_id is not None:
        where_clauses.append("subscription_or_account_id = ?")
        params.append(subscription_or_account_id)

    if check_state is not None:
        where_clauses.append("check_state = ?")
        params.append(check_state)

    if resource_type is not None:
        where_clauses.append("LOWER(resource_type) LIKE LOWER(?)")
        params.append(f"%{resource_type}%")

    if check_name is not None:
        where_clauses.append("LOWER(check_name) LIKE LOWER(?)")
        params.append(f"%{check_name}%")

    if start_date is not None:
        where_clauses.append("evaluated_at >= ?")
        params.append(start_date)

    if end_date is not None:
        where_clauses.append("evaluated_at < CAST(? AS TIMESTAMP) + INTERVAL '1 day'")
        params.append(end_date)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    count_params = list(params)
    params.extend([limit, offset])

    rows = await db.fetchall(
        f"""
        SELECT
            check_id, check_name,
            cloud_provider, source_lz_id, subscription_or_account_id,
            check_state, resource_id, resource_name, resource_type,
            check_effect, non_check_reasons, evaluated_at
        FROM {db.table('curated_standard_checks')}
        {where_sql}
        ORDER BY
            CASE check_state
                WHEN 'non_compliant' THEN 1
                WHEN 'unknown'       THEN 2
                WHEN 'compliant'     THEN 3
                ELSE 4
            END,
            evaluated_at DESC
        LIMIT ? OFFSET ?
        """,
        *params,
    )

    total = await db.fetchscalar(
        "SELECT COUNT(*) "
        f"FROM {db.table('curated_standard_checks')} "
        f"{where_sql}",
        *count_params,
    )

    return {
        "items": [row_to_check(row) for row in rows],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }


async def fetch_standard_check_score(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    subscription_or_account_id: str | None,
    since: date | None,
) -> dict[str, Any]:
    where_clauses: list[str] = []
    params: list[Any] = []

    add_scope_lz_filter(
        where_clauses,
        params,
        allowed_lz_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )

    if cloud_provider is not None:
        where_clauses.append("cloud_provider = ?")
        params.append(cloud_provider)

    if since is not None:
        where_clauses.append("evaluation_date >= ?")
        params.append(since)

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    global_row = await db.fetchone(
        f"""
        SELECT
            SUM(compliant_count) AS compliant_count,
            SUM(non_compliant_count) AS non_compliant_count,
            SUM(total_checks) AS total_evaluated
        FROM {db.table('gold_standard_check_score')}
        {where_sql}
        """,
        *params,
    )

    compliant = int(global_row["compliant_count"] or 0)
    non_compliant = int(global_row["non_compliant_count"] or 0)
    total_evaluated = int(global_row["total_evaluated"] or 0)
    global_score = round(compliant / total_evaluated * 100, 1) if total_evaluated > 0 else None

    breakdown_rows = await db.fetchall(
        f"""
        SELECT
            cloud_provider,
            source_lz_id,
            SUM(compliant_count) AS compliant_count,
            SUM(non_compliant_count) AS non_compliant_count,
            SUM(total_checks) AS total_evaluated
        FROM {db.table('gold_standard_check_score')}
        {where_sql}
        GROUP BY cloud_provider, source_lz_id
        ORDER BY cloud_provider, source_lz_id
        """,
        *params,
    )

    breakdown = []
    for row in breakdown_rows:
        lz_total = int(row["total_evaluated"] or 0)
        lz_compliant = int(row["compliant_count"] or 0)
        breakdown.append(
            {
                "cloud_provider": row["cloud_provider"],
                "source_lz_id": row["source_lz_id"],
                "compliant_count": lz_compliant,
                "non_compliant_count": int(row["non_compliant_count"] or 0),
                "total_evaluated": lz_total,
                "score_pct": round(lz_compliant / lz_total * 100, 1) if lz_total > 0 else None,
            }
        )

    return {
        "global_score_pct": global_score,
        "compliant_count": compliant,
        "non_compliant_count": non_compliant,
        "total_evaluated": total_evaluated,
        "by_landing_zone": breakdown,
    }


async def fetch_governance_page_bundle(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    start_date: date | None,
    end_date: date | None,
    limit: int = _DEFAULT_PAGE_LIMIT,
) -> dict[str, Any]:
    cache_key = build_cache_key(
        "governance-page-bundle",
        allowed_lz_ids=cache_key_ids(allowed_lz_ids),
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=cache_key_ids(source_lz_ids),
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )

    async def load() -> dict[str, Any]:
        score, checks = await asyncio.gather(
            fetch_standard_check_score(
                db,
                allowed_lz_ids,
                cloud_provider=cloud_provider,
                source_lz_id=source_lz_id,
                source_lz_ids=source_lz_ids,
                subscription_or_account_id=None,
                since=start_date,
            ),
            fetch_standard_checks_list(
                db,
                allowed_lz_ids,
                cloud_provider=cloud_provider,
                source_lz_id=source_lz_id,
                source_lz_ids=source_lz_ids,
                subscription_or_account_id=None,
                check_state=None,
                resource_type=None,
                check_name=None,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                offset=0,
            ),
        )
        return {"score": score, "checks": checks}

    return await get_cached_response(cache_key, load, ttl_seconds=_CACHE_TTL_SECONDS)
