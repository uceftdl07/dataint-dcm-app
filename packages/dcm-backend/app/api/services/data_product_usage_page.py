"""Data product usage queries — reads Unity Catalog's ``gold_data_product_usage``.

Kept out of the route per the route→service→pool pattern.
"""

from __future__ import annotations

from collections.abc import Awaitable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import HTTPException

from ...db.connection import DatabricksWarehousePool
from ..routes._lz_filter import add_scope_lz_filter

__all__ = [
    "GOLD_TABLE_NAME",
    "TREND_GRAINS",
    "fetch_top_consumers",
    "fetch_usage_list",
    "fetch_usage_overview",
    "fetch_usage_trends",
    "iso",
    "number",
    "row_to_usage",
    "usage_filters",
    "with_gold_table_error_handled",
]

_DEFAULT_LOOKBACK_DAYS = 30
GOLD_TABLE_NAME = "gold_data_product_usage"

TREND_GRAINS = {
    "day": "CAST(usage_date AS DATE)",
    "week": "DATE_TRUNC('WEEK', usage_date)",
    "month": "DATE_TRUNC('MONTH', usage_date)",
}

_TOP_CONSUMER_METRICS = {
    "request_count": "request_count",
    "rows_read": "rows_read",
    "rows_written": "rows_written",
    "data_read_bytes": "data_read_bytes",
    "data_written_bytes": "data_written_bytes",
    "duration_seconds": "duration_seconds",
    "cost_usd": "cost_usd",
}


def _is_missing_gold_table_error(exc: Exception) -> bool:
    message = str(exc)
    return "[TABLE_OR_VIEW_NOT_FOUND]" in message and "gold_data_product_usage" in message


async def with_gold_table_error_handled(
    db: DatabricksWarehousePool, operation: Awaitable[Any]
) -> Any:
    try:
        return await operation
    except Exception as exc:
        if _is_missing_gold_table_error(exc):
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "degraded",
                    "database": "available",
                    "table": db.table(GOLD_TABLE_NAME),
                    "code": "data_product_usage_table_missing",
                    "error": (
                        "Unity Catalog table is missing. Run the data product usage "
                        "Databricks pipeline to create and populate it before using "
                        "these endpoints."
                    ),
                },
            ) from exc
        raise


def _default_dates() -> tuple[date, date]:
    today = datetime.now(UTC).date()
    return today - timedelta(days=_DEFAULT_LOOKBACK_DAYS), today


def iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def number(value: Any, *, decimals: int | None = None) -> int | float:
    if value is None:
        return 0
    result = float(value)
    if decimals is not None:
        return round(result, decimals)
    if result.is_integer():
        return int(result)
    return result


def usage_filters(
    *,
    allowed_lz_ids: list[str] | None,
    start_date: date | None,
    end_date: date | None,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    subscription_or_account_id: str | None,
    data_product_id: str | None,
    consumer_id: str | None,
) -> tuple[str, list[Any], date, date]:
    start, end = _default_dates()
    if start_date is not None:
        start = start_date
    if end_date is not None:
        end = end_date

    conditions: list[str] = [
        "CAST(usage_date AS DATE) >= ?",
        "CAST(usage_date AS DATE) <= ?",
    ]
    args: list[Any] = [start, end]

    if cloud_provider:
        conditions.append("cloud_provider = ?")
        args.append(cloud_provider)
    add_scope_lz_filter(
        conditions,
        args,
        allowed_lz_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )
    if subscription_or_account_id:
        conditions.append("subscription_or_account_id = ?")
        args.append(subscription_or_account_id)
    if data_product_id:
        conditions.append("data_product_id = ?")
        args.append(data_product_id)
    if consumer_id:
        conditions.append("consumer_id = ?")
        args.append(consumer_id)

    return "WHERE " + " AND ".join(conditions), args, start, end


def row_to_usage(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "usage_date": iso(row["usage_date"]),
        "data_product_id": row["data_product_id"],
        "data_product_name": row["data_product_name"],
        "consumer_id": row["consumer_id"],
        "consumer_name": row["consumer_name"],
        "cloud_provider": row["cloud_provider"],
        "source_lz_id": row["source_lz_id"],
        "subscription_or_account_id": row["subscription_or_account_id"],
        "request_count": number(row["request_count"]),
        "rows_read": number(row["rows_read"]),
        "rows_written": number(row["rows_written"]),
        "data_read_bytes": number(row["data_read_bytes"]),
        "data_written_bytes": number(row["data_written_bytes"]),
        "duration_seconds": number(row["duration_seconds"], decimals=2),
        "cost_usd": number(row["cost_usd"], decimals=2),
        "last_used_at": iso(row["last_used_at"]),
    }


async def fetch_usage_overview(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start_date: date | None,
    end_date: date | None,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    subscription_or_account_id: str | None,
    data_product_id: str | None,
    consumer_id: str | None,
) -> dict[str, Any]:
    """Return high-level usage KPIs from ``gold_data_product_usage``."""
    where, args, start, end = usage_filters(
        allowed_lz_ids=allowed_lz_ids,
        start_date=start_date,
        end_date=end_date,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        subscription_or_account_id=subscription_or_account_id,
        data_product_id=data_product_id,
        consumer_id=consumer_id,
    )

    summary = await with_gold_table_error_handled(db, db.fetchone(
        f"""
        SELECT
            COUNT(DISTINCT data_product_id) AS total_data_products,
            COUNT(DISTINCT consumer_id) AS active_consumers,
            COALESCE(SUM(request_count), 0) AS request_count,
            COALESCE(SUM(rows_read), 0) AS rows_read,
            COALESCE(SUM(rows_written), 0) AS rows_written,
            COALESCE(SUM(data_read_bytes), 0) AS data_read_bytes,
            COALESCE(SUM(data_written_bytes), 0) AS data_written_bytes,
            COALESCE(SUM(duration_seconds), 0) AS duration_seconds,
            COALESCE(SUM(cost_usd), 0) AS cost_usd,
            MAX(last_used_at) AS last_used_at
        FROM {db.table(GOLD_TABLE_NAME)}
        {where}
        """,
        *args,
    )) or {}

    by_cloud = await with_gold_table_error_handled(db, db.fetchall(
        f"""
        SELECT
            cloud_provider,
            COUNT(DISTINCT data_product_id) AS data_product_count,
            COUNT(DISTINCT consumer_id) AS consumer_count,
            COALESCE(SUM(request_count), 0) AS request_count,
            COALESCE(SUM(data_read_bytes), 0) AS data_read_bytes,
            COALESCE(SUM(data_written_bytes), 0) AS data_written_bytes,
            COALESCE(SUM(cost_usd), 0) AS cost_usd
        FROM {db.table(GOLD_TABLE_NAME)}
        {where}
        GROUP BY cloud_provider
        ORDER BY data_read_bytes DESC
        """,
        *args,
    ))

    return {
        "total_data_products": number(summary.get("total_data_products")),
        "active_consumers": number(summary.get("active_consumers")),
        "request_count": number(summary.get("request_count")),
        "rows_read": number(summary.get("rows_read")),
        "rows_written": number(summary.get("rows_written")),
        "data_read_bytes": number(summary.get("data_read_bytes")),
        "data_written_bytes": number(summary.get("data_written_bytes")),
        "duration_seconds": number(summary.get("duration_seconds"), decimals=2),
        "cost_usd": number(summary.get("cost_usd"), decimals=2),
        "last_used_at": iso(summary.get("last_used_at")),
        "by_cloud": [
            {
                "cloud_provider": row["cloud_provider"],
                "data_product_count": number(row["data_product_count"]),
                "consumer_count": number(row["consumer_count"]),
                "request_count": number(row["request_count"]),
                "data_read_bytes": number(row["data_read_bytes"]),
                "data_written_bytes": number(row["data_written_bytes"]),
                "cost_usd": number(row["cost_usd"], decimals=2),
            }
            for row in by_cloud
        ],
        "period": {"start": start.isoformat(), "end": end.isoformat()},
    }


async def fetch_usage_trends(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start_date: date | None,
    end_date: date | None,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    subscription_or_account_id: str | None,
    data_product_id: str | None,
    consumer_id: str | None,
    grain: str,
) -> dict[str, Any]:
    """Return usage trend buckets for charts."""
    period_expr = TREND_GRAINS.get(grain)
    if period_expr is None:
        raise HTTPException(status_code=400, detail="grain must be one of: day, week, month")

    where, args, start, end = usage_filters(
        allowed_lz_ids=allowed_lz_ids,
        start_date=start_date,
        end_date=end_date,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        subscription_or_account_id=subscription_or_account_id,
        data_product_id=data_product_id,
        consumer_id=consumer_id,
    )

    rows = await with_gold_table_error_handled(db, db.fetchall(
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
        FROM {db.table(GOLD_TABLE_NAME)}
        {where}
        GROUP BY 1
        ORDER BY period_start ASC
        """,
        *args,
    ))

    return {
        "grain": grain,
        "items": [
            {
                "period_start": iso(row["period_start"]),
                "data_product_count": number(row["data_product_count"]),
                "consumer_count": number(row["consumer_count"]),
                "request_count": number(row["request_count"]),
                "rows_read": number(row["rows_read"]),
                "rows_written": number(row["rows_written"]),
                "data_read_bytes": number(row["data_read_bytes"]),
                "data_written_bytes": number(row["data_written_bytes"]),
                "cost_usd": number(row["cost_usd"], decimals=2),
            }
            for row in rows
        ],
        "period": {"start": start.isoformat(), "end": end.isoformat()},
    }


async def fetch_top_consumers(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start_date: date | None,
    end_date: date | None,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    subscription_or_account_id: str | None,
    data_product_id: str | None,
    consumer_id: str | None,
    metric: str,
    limit: int,
) -> dict[str, Any]:
    """Return consumers ranked by a whitelisted usage metric."""
    metric_column = _TOP_CONSUMER_METRICS.get(metric)
    if metric_column is None:
        raise HTTPException(
            status_code=400,
            detail=f"metric must be one of: {', '.join(sorted(_TOP_CONSUMER_METRICS))}",
        )

    where, args, start, end = usage_filters(
        allowed_lz_ids=allowed_lz_ids,
        start_date=start_date,
        end_date=end_date,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        subscription_or_account_id=subscription_or_account_id,
        data_product_id=data_product_id,
        consumer_id=consumer_id,
    )

    rows = await with_gold_table_error_handled(db, db.fetchall(
        f"""
        SELECT
            consumer_id,
            consumer_name,
            cloud_provider,
            source_lz_id,
            subscription_or_account_id,
            COUNT(DISTINCT data_product_id) AS data_product_count,
            COALESCE(SUM(request_count), 0) AS request_count,
            COALESCE(SUM(rows_read), 0) AS rows_read,
            COALESCE(SUM(rows_written), 0) AS rows_written,
            COALESCE(SUM(data_read_bytes), 0) AS data_read_bytes,
            COALESCE(SUM(data_written_bytes), 0) AS data_written_bytes,
            COALESCE(SUM(duration_seconds), 0) AS duration_seconds,
            COALESCE(SUM(cost_usd), 0) AS cost_usd,
            COALESCE(SUM({metric_column}), 0) AS metric_value,
            MAX(last_used_at) AS last_used_at
        FROM {db.table(GOLD_TABLE_NAME)}
        {where}
        GROUP BY
            consumer_id,
            consumer_name,
            cloud_provider,
            source_lz_id,
            subscription_or_account_id
        ORDER BY metric_value DESC
        LIMIT ?
        """,
        *args,
        limit,
    ))

    return {
        "metric": metric,
        "items": [
            {
                "consumer_id": row["consumer_id"],
                "consumer_name": row["consumer_name"],
                "cloud_provider": row["cloud_provider"],
                "source_lz_id": row["source_lz_id"],
                "subscription_or_account_id": row["subscription_or_account_id"],
                "data_product_count": number(row["data_product_count"]),
                "request_count": number(row["request_count"]),
                "rows_read": number(row["rows_read"]),
                "rows_written": number(row["rows_written"]),
                "data_read_bytes": number(row["data_read_bytes"]),
                "data_written_bytes": number(row["data_written_bytes"]),
                "duration_seconds": number(row["duration_seconds"], decimals=2),
                "cost_usd": number(row["cost_usd"], decimals=2),
                "metric_value": number(row["metric_value"], decimals=2),
                "last_used_at": iso(row["last_used_at"]),
            }
            for row in rows
        ],
        "period": {"start": start.isoformat(), "end": end.isoformat()},
    }


async def fetch_usage_list(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start_date: date | None,
    end_date: date | None,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    subscription_or_account_id: str | None,
    data_product_id: str | None,
    consumer_id: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """List detailed data product usage rows from the gold serving table."""
    where, args, start, end = usage_filters(
        allowed_lz_ids=allowed_lz_ids,
        start_date=start_date,
        end_date=end_date,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        subscription_or_account_id=subscription_or_account_id,
        data_product_id=data_product_id,
        consumer_id=consumer_id,
    )

    total = await with_gold_table_error_handled(
        db,
        db.fetchscalar(f"SELECT COUNT(*) FROM {db.table(GOLD_TABLE_NAME)} {where}", *args)
    ) or 0

    rows = await with_gold_table_error_handled(db, db.fetchall(
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
        FROM {db.table(GOLD_TABLE_NAME)}
        {where}
        ORDER BY last_used_at DESC, usage_date DESC
        LIMIT ? OFFSET ?
        """,
        *args,
        limit,
        offset,
    ))

    return {
        "items": [row_to_usage(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
    }
