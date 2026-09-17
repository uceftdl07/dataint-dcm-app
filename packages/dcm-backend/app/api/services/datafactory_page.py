"""Data Factory page bundle — ADF pipelines in one cached response."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from ...cache.response_cache import build_cache_key, cache_key_ids, get_cached_response
from ...db.connection import DatabricksWarehousePool
from ..routes._lz_filter import SourceLzIdQuery, SourceLzIdsQuery, add_scope_lz_filter
from .dashboard_bundle import _resolve_period
from .pipelines_page import PIPELINE_TYPE_SQL as _PIPELINE_TYPE_SQL
from .pipelines_page import row_to_pipeline as _row_to_pipeline

__all__ = ["fetch_datafactory_page_bundle"]

_DEFAULT_LIST_LIMIT = 200
_CACHE_TTL_SECONDS = 120.0


def _build_adf_conditions(
    allowed_lz_ids: list[str] | None,
    *,
    start: date,
    end: date,
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
    conditions.append("cloud_provider = ?")
    args.append("azure")
    conditions.append(f"LOWER({_PIPELINE_TYPE_SQL}) = LOWER(?)")
    args.append("adf")
    conditions.append("pipeline_id NOT LIKE 'databricks:job:%'")
    conditions.append("CAST(start_time AS DATE) >= ?")
    args.append(start)
    conditions.append("CAST(start_time AS DATE) <= ?")
    args.append(end)
    where = "WHERE " + " AND ".join(conditions)
    return where, args


async def _fetch_adf_pipeline_total(
    db: DatabricksWarehousePool,
    where: str,
    args: list[Any],
) -> int:
    total = await db.fetchscalar(
        "SELECT COUNT(*) "
        f"FROM {db.table('curated_pipeline_metrics')} "
        f"{where}",
        *args,
    )
    return int(total or 0)


async def _fetch_adf_pipeline_items(
    db: DatabricksWarehousePool,
    where: str,
    args: list[Any],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    rows = await db.fetchall(
        f"""
         SELECT run_id, pipeline_id, pipeline_name, cloud_provider, source_lz_id,
             {_PIPELINE_TYPE_SQL} AS pipeline_type, trigger_type, status, start_time, end_time,
             duration_seconds, error_message
        FROM {db.table('curated_pipeline_metrics')}
        {where}
        ORDER BY start_time DESC
        LIMIT ?
        """,
        *args,
        limit,
    )
    return [_row_to_pipeline(row) for row in rows]


async def fetch_datafactory_page_bundle(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    list_limit: int = _DEFAULT_LIST_LIMIT,
) -> dict[str, Any]:
    """Return ADF pipeline runs + total count in one parallel cached bundle."""
    start, end = _resolve_period(start_date, end_date)
    cache_key = build_cache_key(
        "datafactory-page-bundle",
        allowed_lz_ids=cache_key_ids(allowed_lz_ids),
        source_lz_id=source_lz_id,
        source_lz_ids=cache_key_ids(source_lz_ids),
        start_date=start,
        end_date=end,
        list_limit=list_limit,
    )

    async def load() -> dict[str, Any]:
        where, args = _build_adf_conditions(
            allowed_lz_ids,
            start=start,
            end=end,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
        )
        total, items = await asyncio.gather(
            _fetch_adf_pipeline_total(db, where, args),
            _fetch_adf_pipeline_items(db, where, args, limit=list_limit),
        )
        return {
            "pipelines": {"items": items, "total": total},
            "period": {"start": start.isoformat(), "end": end.isoformat()},
        }

    return await get_cached_response(cache_key, load, ttl_seconds=_CACHE_TTL_SECONDS)
