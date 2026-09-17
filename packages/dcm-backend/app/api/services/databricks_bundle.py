"""Aggregated Databricks page queries — single HTTP round-trip for /databricks."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from ...cache.response_cache import build_cache_key, cache_key_ids, get_cached_response
from ...db.connection import DatabricksWarehousePool
from ..routes._lz_filter import (
    SourceLzIdQuery,
    SourceLzIdsQuery,
    add_cost_period_filter,
    add_scope_lz_filter,
)
from .activities_page import row_to_activity as _row_to_activity
from .compute_metrics_common import _add_rbac_scope
from .cost_utils import iso_cost_period
from .dashboard_bundle import (
    _fetch_alert_preview,
    _fetch_compute_items,
    _fetch_governance_score,
    _resolve_period,
)
from .governance_page import row_to_check

__all__ = ["fetch_databricks_full"]

_DEFAULT_LIST_LIMIT = 100
_CACHE_TTL_SECONDS = 120.0


async def _fetch_databricks_activities(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start: date,
    end: date,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    subscription_or_account_id: str | None,
    limit: int = _DEFAULT_LIST_LIMIT,
) -> list[dict[str, Any]]:
    where_clauses: list[str] = ["activity_type = ?"]
    params: list[Any] = ["databricks_notebook"]
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
    where_clauses.append("start_time >= ?")
    params.append(start)
    where_clauses.append("start_time < ? + INTERVAL '1 day'")
    params.append(end)

    where_sql = "WHERE " + " AND ".join(where_clauses)
    rows = await db.fetchall(
        f"""
        SELECT
            pipeline_run_id, pipeline_name, activity_name, activity_type,
            cloud_provider, source_lz_id, subscription_or_account_id,
            status, start_time, end_time, duration_seconds,
            rows_read, rows_written, data_read_bytes, data_written_bytes,
            error_message, collected_at
        FROM {db.table('curated_activity_runs')}
        {where_sql}
        ORDER BY start_time DESC
        LIMIT ?
        """,
        *params,
        limit,
    )
    return [_row_to_activity(row) for row in rows]


async def _fetch_costs_by_service(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start: date,
    end: date,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
) -> list[dict[str, Any]]:
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
    return [
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


def _row_to_databricks_pipeline(row: dict[str, Any]) -> dict[str, Any]:
    """Shape a gold_dbx_workflow_runs row like the legacy PipelineRun — minus the
    fields that table doesn't have (source_lz_id), plus workspace_id instead."""
    return {
        "run_id": row["run_id"],
        "pipeline_id": row["pipeline_id"],
        "pipeline_name": row["pipeline_name"],
        "cloud_provider": row["cloud_provider"],
        "workspace_id": row.get("workspace_id"),
        "pipeline_type": "databricks_job",
        "trigger_type": row["trigger_type"],
        "status": row["status"],
        "start_time": row["start_time"].isoformat() if row["start_time"] else None,
        "end_time": row["end_time"].isoformat() if row["end_time"] else None,
        "duration_seconds": row["duration_seconds"],
        "error_message": row["error_message"],
    }


async def _fetch_databricks_pipeline_preview(
    db: DatabricksWarehousePool,
    allowed_workspace_ids: list[str] | None,
    *,
    start: date,
    end: date,
    cloud_provider: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """The "Jobs" section of the Databricks page — gold_dbx_workflow_runs has no
    source_lz_id (only workspace_id), unlike the legacy curated_pipeline_metrics
    this used to read (see _fetch_pipeline_preview in dashboard_bundle.py)."""
    conditions: list[str] = ["CAST(start_time AS DATE) >= ?", "CAST(start_time AS DATE) <= ?"]
    args: list[Any] = [start, end]
    _add_rbac_scope(
        conditions,
        args,
        allowed_lz_ids=None,
        allowed_workspace_ids=allowed_workspace_ids,
        has_lz_column=False,
    )
    if cloud_provider:
        conditions.append("cloud_provider = ?")
        args.append(cloud_provider)

    where = "WHERE " + " AND ".join(conditions)
    rows = await db.fetchall(
        f"""
        SELECT run_id, workflow_id AS pipeline_id, workflow_name AS pipeline_name,
            cloud_provider, workspace_id, trigger_type, status, start_time, end_time,
            duration_seconds, error_message
        FROM {db.table('gold_dbx_workflow_runs')}
        {where}
        ORDER BY start_time DESC
        LIMIT ?
        """,
        *args,
        limit,
    )
    return [_row_to_databricks_pipeline(row) for row in rows]


async def _fetch_standard_checks_preview(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start: date,
    end: date,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    subscription_or_account_id: str | None,
    limit: int = _DEFAULT_LIST_LIMIT,
) -> list[dict[str, Any]]:
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
    where_clauses.append("evaluated_at >= ?")
    params.append(start)
    where_clauses.append("evaluated_at < CAST(? AS TIMESTAMP) + INTERVAL '1 day'")
    params.append(end)

    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
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
        LIMIT ?
        """,
        *params,
        limit,
    )
    return [row_to_check(row) for row in rows]


async def fetch_databricks_full(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    allowed_workspace_ids: list[str] | None = None,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    cloud_provider: str | None = None,
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    subscription_or_account_id: str | None = None,
    workspace_id: str | None = None,
    workspace_ids: list[str] | None = None,
    list_limit: int = _DEFAULT_LIST_LIMIT,
) -> dict[str, Any]:
    """Return all Databricks page sections in one parallel bundle."""
    cache_key = build_cache_key(
        "databricks-full-bundle",
        allowed_lz_ids=cache_key_ids(allowed_lz_ids),
        allowed_workspace_ids=cache_key_ids(allowed_workspace_ids),
        start_date=start_date,
        end_date=end_date,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=cache_key_ids(source_lz_ids),
        subscription_or_account_id=subscription_or_account_id,
        workspace_id=workspace_id,
        workspace_ids=cache_key_ids(workspace_ids),
        list_limit=list_limit,
    )

    async def load() -> dict[str, Any]:
        start, end = _resolve_period(start_date, end_date)

        (
            computes,
            governance,
            pipelines,
            activities,
            costs,
            alerts,
            checks,
        ) = await asyncio.gather(
            _fetch_compute_items(
                db,
                allowed_lz_ids,
                cloud_provider=cloud_provider,
                source_lz_id=source_lz_id,
                source_lz_ids=source_lz_ids,
                workspace_id=workspace_id,
                workspace_ids=workspace_ids,
            ),
            _fetch_governance_score(
                db,
                allowed_lz_ids,
                cloud_provider=cloud_provider,
                source_lz_id=source_lz_id,
                source_lz_ids=source_lz_ids,
                since=start,
            ),
            _fetch_databricks_pipeline_preview(
                db,
                allowed_workspace_ids,
                start=start,
                end=end,
                cloud_provider=cloud_provider,
                limit=list_limit,
            ),
            _fetch_databricks_activities(
                db,
                allowed_lz_ids,
                start=start,
                end=end,
                cloud_provider=cloud_provider,
                source_lz_id=source_lz_id,
                source_lz_ids=source_lz_ids,
                subscription_or_account_id=subscription_or_account_id,
                limit=list_limit,
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
            _fetch_alert_preview(
                db,
                allowed_lz_ids,
                start=start,
                end=end,
                cloud_provider=cloud_provider,
                source_lz_id=source_lz_id,
                source_lz_ids=source_lz_ids,
                limit=list_limit,
            ),
            _fetch_standard_checks_preview(
                db,
                allowed_lz_ids,
                start=start,
                end=end,
                cloud_provider=cloud_provider,
                source_lz_id=source_lz_id,
                source_lz_ids=source_lz_ids,
                subscription_or_account_id=subscription_or_account_id,
                limit=list_limit,
            ),
        )

        return {
            "computes": {"items": computes},
            "governance": governance,
            "pipelines": {"items": pipelines},
            "activities": {"items": activities},
            "costs": {"items": costs},
            "alerts": {"items": alerts},
            "checks": {"items": checks},
            "period": {"start": start.isoformat(), "end": end.isoformat()},
        }

    return await get_cached_response(cache_key, load, ttl_seconds=_CACHE_TTL_SECONDS)
