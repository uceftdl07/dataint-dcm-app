"""FinOps page bundle — summary + by-service in one cached response."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from ...cache.response_cache import build_cache_key, cache_key_ids, get_cached_response
from ...db.connection import DatabricksWarehousePool
from ..routes._lz_filter import add_cost_period_filter, add_scope_lz_filter
from .cost_utils import default_cost_dates, iso_cost_period

_CACHE_TTL_SECONDS = 120.0


async def _fetch_cost_summary(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start: date,
    end: date,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
) -> dict[str, Any]:
    conditions: list[str] = []
    args: list[Any] = []
    add_cost_period_filter(conditions, args, start, end)
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

    where = "WHERE " + " AND ".join(conditions)

    total_usd: float = (
        await db.fetchscalar(
            "SELECT COALESCE(SUM(cost_usd), 0) "
            f"FROM {db.table('curated_cost_metrics')} "
            f"{where}",
            *args,
        )
        or 0.0
    )

    cloud_rows = await db.fetchall(
        f"""
        SELECT cloud_provider, COALESCE(SUM(cost_usd), 0) AS total
        FROM {db.table('curated_cost_metrics')} {where}
        GROUP BY cloud_provider
        ORDER BY total DESC
        """,
        *args,
    )
    by_cloud = {row["cloud_provider"]: round(float(row["total"]), 2) for row in cloud_rows}

    svc_rows = await db.fetchall(
        f"""
        SELECT service_name, cloud_provider, COALESCE(SUM(cost_usd), 0) AS total
        FROM {db.table('curated_cost_metrics')} {where}
        GROUP BY service_name, cloud_provider
        ORDER BY total DESC
        LIMIT 10
        """,
        *args,
    )
    by_service = [
        {
            "service_name": row["service_name"],
            "cloud_provider": row["cloud_provider"],
            "cost_usd": round(float(row["total"]), 2),
        }
        for row in svc_rows
    ]

    return {
        "total_usd": round(float(total_usd), 2),
        "by_cloud": by_cloud,
        "by_service": by_service,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
    }


async def _fetch_costs_by_service(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start: date,
    end: date,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
) -> dict[str, Any]:
    conditions: list[str] = []
    args: list[Any] = []
    add_cost_period_filter(conditions, args, start, end)
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

    where = "WHERE " + " AND ".join(conditions)
    rows = await db.fetchall(
        f"""
        SELECT
            service_name,
            cloud_provider,
            subscription_or_account_id,
            source_lz_id,
            SUM(cost_usd)               AS total_cost_usd,
            AVG(budget_consumed_pct)    AS avg_budget_pct,
            MIN(period_start)           AS earliest_period,
            MAX(period_end)             AS latest_period
        FROM {db.table('curated_cost_metrics')}
        {where}
        GROUP BY service_name, cloud_provider, subscription_or_account_id, source_lz_id
        ORDER BY total_cost_usd DESC
        """,
        *args,
    )

    items = [
        {
            "service_name": row["service_name"],
            "cloud_provider": row["cloud_provider"],
            "subscription_or_account_id": row["subscription_or_account_id"],
            "source_lz_id": row["source_lz_id"],
            "total_cost_usd": round(float(row["total_cost_usd"]), 2),
            "avg_budget_consumed_pct": (
                round(float(row["avg_budget_pct"]), 1) if row["avg_budget_pct"] is not None else None
            ),
            "period": {
                "start": iso_cost_period(row["earliest_period"]),
                "end": iso_cost_period(row["latest_period"]),
            },
        }
        for row in rows
    ]
    return {"items": items}


async def fetch_cost_summary(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start_date: date | None,
    end_date: date | None,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
) -> dict[str, Any]:
    """Cost summary KPIs for the requested period (``GET /costs/summary``).

    total_usd       Sum of all service costs in the period.
    by_cloud        Mapping cloud_provider → total cost USD.
    by_service      Top 10 services by cost (descending).
    period          Effective date range used.
    """
    start, end = default_cost_dates()
    if start_date is not None:
        start = start_date
    if end_date is not None:
        end = end_date
    return await _fetch_cost_summary(
        db,
        allowed_lz_ids,
        start=start,
        end=end,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )


async def fetch_costs_by_service(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start_date: date | None,
    end_date: date | None,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
) -> dict[str, Any]:
    """Cost broken down by service, account, and cloud provider (``GET /costs/by-service``).

    All cost records within the requested period are aggregated, ordered by
    total cost descending.
    """
    start, end = default_cost_dates()
    if start_date is not None:
        start = start_date
    if end_date is not None:
        end = end_date
    return await _fetch_costs_by_service(
        db,
        allowed_lz_ids,
        start=start,
        end=end,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )


async def fetch_finops_page_bundle(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start_date: date | None,
    end_date: date | None,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
) -> dict[str, Any]:
    start, end = default_cost_dates()
    if start_date is not None:
        start = start_date
    if end_date is not None:
        end = end_date

    cache_key = build_cache_key(
        "finops-page-bundle",
        allowed_lz_ids=cache_key_ids(allowed_lz_ids),
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=cache_key_ids(source_lz_ids),
        start_date=start,
        end_date=end,
    )

    async def load() -> dict[str, Any]:
        summary, by_service = await asyncio.gather(
            _fetch_cost_summary(
                db,
                allowed_lz_ids,
                start=start,
                end=end,
                cloud_provider=cloud_provider,
                source_lz_id=source_lz_id,
                source_lz_ids=source_lz_ids,
            ),
            _fetch_costs_by_service(
                db,
                allowed_lz_ids,
                start=start,
                end=end,
                cloud_provider=cloud_provider,
                source_lz_id=source_lz_id,
                source_lz_ids=source_lz_ids,
            ),
        )
        return {"summary": summary, "by_service": by_service}

    return await get_cached_response(cache_key, load, ttl_seconds=_CACHE_TTL_SECONDS)
