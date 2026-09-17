"""Aggregated monitoring reports queries — single HTTP round-trip for /monitoringreports."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from fastapi import Request

from ...db.connection import DatabricksWarehousePool
from ..routes._lz_filter import (
    add_cost_period_filter,
    add_scope_lz_filter,
)
from .cost_utils import default_cost_dates as _cost_default_dates
from .cost_utils import iso_cost_period as _iso_period
from .dashboard_bundle import (
    _fetch_compute_items,
    _fetch_cost_summary,
    _fetch_governance_score,
    _resolve_period,
)
from .data_product_usage_page import GOLD_TABLE_NAME as _GOLD_TABLE_NAME
from .data_product_usage_page import TREND_GRAINS as _TREND_GRAINS
from .data_product_usage_page import iso as _iso
from .data_product_usage_page import number as _number
from .data_product_usage_page import row_to_usage as _row_to_usage
from .data_product_usage_page import usage_filters as _usage_filters
from .data_product_usage_page import with_gold_table_error_handled as _with_gold_table_error_handled
from .governance_page import (
    fetch_active_landing_zone_rows,
    row_to_check,
    row_to_landing_zone,
)
from .pipelines_page import PIPELINE_TYPE_SQL as _PIPELINE_TYPE_SQL
from .pipelines_page import row_to_pipeline as _row_to_pipeline
from .security_serializers import row_to_alert as _row_to_alert

__all__ = ["fetch_monitoring_reports_full"]

_DEFAULT_LIST_LIMIT = 200


async def _fetch_data_product_usage(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start_date: date | None,
    end_date: date | None,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    subscription_or_account_id: str | None,
    limit: int = _DEFAULT_LIST_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    where, args, start, end = _usage_filters(
        allowed_lz_ids=allowed_lz_ids,
        start_date=start_date,
        end_date=end_date,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        subscription_or_account_id=subscription_or_account_id,
        data_product_id=None,
        consumer_id=None,
    )

    total = await _with_gold_table_error_handled(
        db,
        db.fetchscalar(f"SELECT COUNT(*) FROM {db.table(_GOLD_TABLE_NAME)} {where}", *args),
    ) or 0

    rows = await _with_gold_table_error_handled(
        db,
        db.fetchall(
            f"""
            SELECT
                usage_date,
                data_product_id,
                data_product_name,
                consumer_id,
                consumer_name,
                cloud_provider,
                source_lz_id,
                subscription_or_account_id,
                request_count,
                rows_read,
                rows_written,
                data_read_bytes,
                data_written_bytes,
                duration_seconds,
                cost_usd,
                last_used_at
            FROM {db.table(_GOLD_TABLE_NAME)}
            {where}
            ORDER BY last_used_at DESC, usage_date DESC
            LIMIT ? OFFSET ?
            """,
            *args,
            limit,
            offset,
        )
    )

    return {
        "items": [_row_to_usage(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
    }


async def _fetch_usage_trends(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start_date: date | None,
    end_date: date | None,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    subscription_or_account_id: str | None,
    grain: str = "day",
) -> dict[str, Any]:
    period_expr = _TREND_GRAINS.get(grain)
    if period_expr is None:
        msg = "grain must be one of: day, week, month"
        raise ValueError(msg)

    where, args, start, end = _usage_filters(
        allowed_lz_ids=allowed_lz_ids,
        start_date=start_date,
        end_date=end_date,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        subscription_or_account_id=subscription_or_account_id,
        data_product_id=None,
        consumer_id=None,
    )

    rows = await _with_gold_table_error_handled(
        db,
        db.fetchall(
            f"""
            SELECT
                {period_expr} AS period_start,
                COUNT(DISTINCT data_product_id) AS data_product_count,
                COUNT(DISTINCT consumer_id) AS consumer_count,
                COALESCE(SUM(request_count), 0) AS request_count,
                COALESCE(SUM(rows_read), 0) AS rows_read,
                COALESCE(SUM(rows_written), 0) AS rows_written,
                COALESCE(SUM(data_read_bytes), 0) AS data_read_bytes,
                COALESCE(SUM(data_written_bytes), 0) AS data_written_bytes,
                COALESCE(SUM(cost_usd), 0) AS cost_usd
            FROM {db.table(_GOLD_TABLE_NAME)}
            {where}
            GROUP BY 1
            ORDER BY period_start ASC
            """,
            *args,
        )
    )

    return {
        "grain": grain,
        "items": [
            {
                "period_start": _iso(row["period_start"]),
                "data_product_count": _number(row["data_product_count"]),
                "consumer_count": _number(row["consumer_count"]),
                "request_count": _number(row["request_count"]),
                "rows_read": _number(row["rows_read"]),
                "rows_written": _number(row["rows_written"]),
                "data_read_bytes": _number(row["data_read_bytes"]),
                "data_written_bytes": _number(row["data_written_bytes"]),
                "cost_usd": _number(row["cost_usd"], decimals=2),
            }
            for row in rows
        ],
        "period": {"start": start.isoformat(), "end": end.isoformat()},
    }


async def _fetch_standard_checks(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start_date: date | None,
    end_date: date | None,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    subscription_or_account_id: str | None,
    limit: int = _DEFAULT_LIST_LIMIT,
    offset: int = 0,
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
    if start_date is not None:
        where_clauses.append("evaluated_at >= ?")
        params.append(start_date)
    if end_date is not None:
        where_clauses.append("evaluated_at < CAST(? AS TIMESTAMP) + INTERVAL '1 day'")
        params.append(end_date)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    count_params = list(params)
    params.extend([limit, offset])

    rows, total = await asyncio.gather(
        db.fetchall(
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
        ),
        db.fetchscalar(
            "SELECT COUNT(*) "
            f"FROM {db.table('curated_standard_checks')} "
            f"{where_sql}",
            *count_params,
        ),
    )

    return {
        "items": [row_to_check(row) for row in rows],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }


async def _fetch_landing_zones(
    request: Request,
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    cloud_provider: str | None,
) -> dict[str, Any]:
    rows = await fetch_active_landing_zone_rows(
        db,
        request.app.state.settings,
        allowed_lz_ids=allowed_lz_ids,
        cloud_provider=cloud_provider,
    )
    return {
        "items": [row_to_landing_zone(row) for row in rows],
        "total": len(rows),
    }


async def _fetch_security_alerts(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start_date: date | None,
    end_date: date | None,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    subscription_or_account_id: str | None,
    status: str = "active",
    limit: int = _DEFAULT_LIST_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
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
    if cloud_provider:
        conditions.append("cloud_provider = ?")
        args.append(cloud_provider)
    if subscription_or_account_id:
        conditions.append("subscription_or_account_id = ?")
        args.append(subscription_or_account_id)
    if start_date:
        conditions.append("CAST(detected_at AS DATE) >= ?")
        args.append(start_date)
    if end_date:
        conditions.append("CAST(detected_at AS DATE) <= ?")
        args.append(end_date)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    args_with_pagination = args + [limit, offset]

    rows, total = await asyncio.gather(
        db.fetchall(
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
        ),
        db.fetchscalar(
            "SELECT COUNT(*) "
            f"FROM {db.table('curated_security_alerts')} "
            f"{where}",
            *args,
        ),
    )

    return {
        "items": [_row_to_alert(row) for row in rows],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }


async def _fetch_pipelines(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start_date: date | None,
    end_date: date | None,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    subscription_or_account_id: str | None,
    limit: int = _DEFAULT_LIST_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
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
    if subscription_or_account_id:
        conditions.append("subscription_or_account_id = ?")
        args.append(subscription_or_account_id)
    if start_date:
        conditions.append("CAST(start_time AS DATE) >= ?")
        args.append(start_date)
    if end_date:
        conditions.append("CAST(start_time AS DATE) <= ?")
        args.append(end_date)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    total, rows = await asyncio.gather(
        db.fetchscalar(
            "SELECT COUNT(*) "
            f"FROM {db.table('curated_pipeline_metrics')} "
            f"{where}",
            *args,
        ),
        db.fetchall(
            f"""
             SELECT run_id, pipeline_id, pipeline_name, cloud_provider, source_lz_id,
                 {_PIPELINE_TYPE_SQL} AS pipeline_type, trigger_type, status, start_time, end_time,
                 duration_seconds, error_message
            FROM {db.table('curated_pipeline_metrics')}
            {where}
            ORDER BY start_time DESC
            LIMIT ? OFFSET ?
            """,
            *args,
            limit,
            offset,
        ),
    )

    return {
        "items": [_row_to_pipeline(row) for row in rows],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }


async def _fetch_costs_by_service(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start_date: date | None,
    end_date: date | None,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    subscription_or_account_id: str | None,
) -> dict[str, Any]:
    start, end = _cost_default_dates()
    if start_date is not None:
        start = start_date
    if end_date is not None:
        end = end_date

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
    if subscription_or_account_id:
        conditions.append("subscription_or_account_id = ?")
        args.append(subscription_or_account_id)

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
                "start": _iso_period(row["earliest_period"]),
                "end": _iso_period(row["latest_period"]),
            },
        }
        for row in rows
    ]

    return {"items": items}


async def fetch_monitoring_reports_full(
    request: Request,
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    cloud_provider: str | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    subscription_or_account_id: str | None = None,
    usage_limit: int = _DEFAULT_LIST_LIMIT,
    list_limit: int = _DEFAULT_LIST_LIMIT,
    trend_grain: str = "day",
) -> dict[str, Any]:
    """Return all monitoring report sections in one response."""
    start, end = _resolve_period(start_date, end_date)

    (
        data_product_usage,
        usage_trends,
        standard_checks,
        landing_zones,
        security_alerts,
        computes,
        pipelines,
        cost_summary,
        costs_by_service,
        governance,
    ) = await asyncio.gather(
        _fetch_data_product_usage(
            db,
            allowed_lz_ids,
            start_date=start,
            end_date=end,
            cloud_provider=cloud_provider,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            subscription_or_account_id=subscription_or_account_id,
            limit=usage_limit,
        ),
        _fetch_usage_trends(
            db,
            allowed_lz_ids,
            start_date=start,
            end_date=end,
            cloud_provider=cloud_provider,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            subscription_or_account_id=subscription_or_account_id,
            grain=trend_grain,
        ),
        _fetch_standard_checks(
            db,
            allowed_lz_ids,
            start_date=start,
            end_date=end,
            cloud_provider=cloud_provider,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            subscription_or_account_id=subscription_or_account_id,
            limit=list_limit,
        ),
        _fetch_landing_zones(
            request,
            db,
            allowed_lz_ids,
            cloud_provider=cloud_provider,
        ),
        _fetch_security_alerts(
            db,
            allowed_lz_ids,
            start_date=start,
            end_date=end,
            cloud_provider=cloud_provider,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            subscription_or_account_id=subscription_or_account_id,
            limit=list_limit,
        ),
        _fetch_compute_items(
            db,
            allowed_lz_ids,
            cloud_provider=cloud_provider,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_id=None,
            workspace_ids=None,
        ),
        _fetch_pipelines(
            db,
            allowed_lz_ids,
            start_date=start,
            end_date=end,
            cloud_provider=cloud_provider,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            subscription_or_account_id=subscription_or_account_id,
            limit=list_limit,
        ),
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
            start_date=start,
            end_date=end,
            cloud_provider=cloud_provider,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            subscription_or_account_id=subscription_or_account_id,
        ),
        _fetch_governance_score(
            db,
            allowed_lz_ids,
            cloud_provider=cloud_provider,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            since=start,
        ),
    )

    return {
        "data_product_usage": data_product_usage,
        "usage_trends": usage_trends,
        "standard_checks": standard_checks,
        "landing_zones": landing_zones,
        "security_alerts": security_alerts,
        "computes": {"items": computes},
        "pipelines": pipelines,
        "cost_summary": cost_summary,
        "costs_by_service": costs_by_service,
        "governance": governance,
    }
