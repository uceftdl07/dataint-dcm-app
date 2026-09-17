"""Security alerts page bundle — list + total in one cached response."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from ...cache.response_cache import build_cache_key, cache_key_ids, get_cached_response
from ...db.connection import DatabricksWarehousePool
from ..routes._lz_filter import add_scope_lz_filter
from .security_serializers import row_to_alert

_DEFAULT_PAGE_LIMIT = 200
_CACHE_TTL_SECONDS = 120.0


def _build_alert_filters(
    allowed_lz_ids: list[str] | None,
    *,
    cloud_provider: str | None,
    start_date: date | None,
    end_date: date | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
) -> tuple[str, list[Any]]:
    conditions: list[str] = []
    args: list[Any] = []
    add_scope_lz_filter(
        conditions,
        args,
        allowed_lz_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )

    if cloud_provider:
        conditions.append("cloud_provider = ?")
        args.append(cloud_provider)
    if start_date:
        conditions.append("CAST(detected_at AS DATE) >= ?")
        args.append(start_date)
    if end_date:
        conditions.append("CAST(detected_at AS DATE) <= ?")
        args.append(end_date)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, args


async def _fetch_alerts_list(
    db: DatabricksWarehousePool,
    where: str,
    args: list[Any],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    rows = await db.fetchall(
        f"""
         SELECT alert_id, cloud_provider, source_lz_id, subscription_or_account_id,
             severity, title, description, status,
             resource_id, resource_type,
             detected_at
         FROM {db.table('curated_security_alerts')}
        {where}
        ORDER BY
            CASE severity
                WHEN 'critical' THEN 1
                WHEN 'high'     THEN 2
                WHEN 'medium'   THEN 3
                WHEN 'low'      THEN 4
                ELSE 5
            END,
            detected_at DESC
        LIMIT ?
        """,
        *args,
        limit,
    )
    return [row_to_alert(row) for row in rows]


async def fetch_alerts_page_bundle(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    cloud_provider: str | None,
    start_date: date | None,
    end_date: date | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    limit: int = _DEFAULT_PAGE_LIMIT,
) -> dict[str, Any]:
    cache_key = build_cache_key(
        "alerts-page-bundle",
        allowed_lz_ids=cache_key_ids(allowed_lz_ids),
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=cache_key_ids(source_lz_ids),
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )

    async def load() -> dict[str, Any]:
        where, args = _build_alert_filters(
            allowed_lz_ids,
            cloud_provider=cloud_provider,
            start_date=start_date,
            end_date=end_date,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
        )
        total, items = await asyncio.gather(
            db.fetchscalar(
                "SELECT COUNT(*) "
                f"FROM {db.table('curated_security_alerts')} "
                f"{where}",
                *args,
            ),
            _fetch_alerts_list(db, where, args, limit=limit),
        )
        return {
            "items": items,
            "total": int(total or 0),
            "limit": limit,
            "offset": 0,
        }

    return await get_cached_response(cache_key, load, ttl_seconds=_CACHE_TTL_SECONDS)


async def fetch_security_alerts(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    severity: str | None,
    status: str | None,
    cloud_provider: str | None,
    start_date: date | None,
    end_date: date | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """Security alerts ordered by severity (critical → low) then detection time.

    Default filter is ``status=active`` — pass ``status=None`` to disable.
    Pagination uses limit / offset.
    """
    conditions: list[str] = []
    args: list[Any] = []
    add_scope_lz_filter(
        conditions,
        args,
        allowed_lz_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )

    if status:
        conditions.append("status = ?")
        args.append(status)
    if severity:
        conditions.append("severity = ?")
        args.append(severity)
    if cloud_provider:
        conditions.append("cloud_provider = ?")
        args.append(cloud_provider)
    if start_date:
        conditions.append("CAST(detected_at AS DATE) >= ?")
        args.append(start_date)
    if end_date:
        conditions.append("CAST(detected_at AS DATE) <= ?")
        args.append(end_date)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    args_with_pagination = args + [limit, offset]

    total: int = (
        await db.fetchscalar(
            "SELECT COUNT(*) "
            f"FROM {db.table('curated_security_alerts')} "
            f"{where}",
            *args,
        )
        or 0
    )

    rows = await db.fetchall(
        f"""
         SELECT alert_id, cloud_provider, source_lz_id, subscription_or_account_id,
             severity, title, description, status,
             resource_id, resource_type,
             detected_at
         FROM {db.table('curated_security_alerts')}
        {where}
        ORDER BY
            CASE severity
                WHEN 'critical' THEN 1
                WHEN 'high'     THEN 2
                WHEN 'medium'   THEN 3
                WHEN 'low'      THEN 4
                ELSE 5
            END,
            detected_at DESC
        LIMIT ? OFFSET ?
        """,
        *args_with_pagination,
    )

    return {
        "items": [row_to_alert(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
