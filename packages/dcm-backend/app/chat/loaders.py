"""Unity Catalog data loaders for Talk-to-Data chat answers."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ..api.routes._lz_filter import add_cost_period_filter, add_lz_filter
from ..db.connection import DatabricksWarehousePool
from .intent import ChatIntent

_GOLD_DATA_PRODUCT_USAGE = "gold_data_product_usage"
_DEFAULT_LOOKBACK_DAYS = 30


def _default_dates() -> tuple[date, date]:
    today = datetime.now(UTC).date()
    return today - timedelta(days=_DEFAULT_LOOKBACK_DAYS), today


def _iso_period(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


async def load_chat_data(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    intent: ChatIntent,
) -> dict[str, Any]:
    """Load structured data for the given intent."""
    loaders: dict[ChatIntent, Any] = {
        "costs": _load_costs,
        "pipelines": _load_pipelines,
        "security": _load_security,
        "governance": _load_governance,
        "data-product-usage": _load_data_product_usage,
        "compute": _load_compute,
        "databases": _load_databases,
        "overview": _load_overview,
    }
    loader = loaders.get(intent)
    if loader is None:
        return {}
    return await loader(db, allowed_lz_ids)


async def _load_costs(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
) -> dict[str, Any]:
    start, end = _default_dates()
    conditions: list[str] = []
    args: list[Any] = []
    add_cost_period_filter(conditions, args, start, end)
    add_lz_filter(conditions, args, allowed_lz_ids)
    where = "WHERE " + " AND ".join(conditions)

    total_usd, cloud_rows, svc_rows = await asyncio.gather(
        db.fetchscalar(
            "SELECT COALESCE(SUM(cost_usd), 0) "
            f"FROM {db.table('curated_cost_metrics')} "
            f"{where}",
            *args,
        ),
        db.fetchall(
            f"""
            SELECT cloud_provider, COALESCE(SUM(cost_usd), 0) AS total
            FROM {db.table('curated_cost_metrics')} {where}
            GROUP BY cloud_provider
            ORDER BY total DESC
            """,
            *args,
        ),
        db.fetchall(
            f"""
            SELECT service_name, cloud_provider, COALESCE(SUM(cost_usd), 0) AS total
            FROM {db.table('curated_cost_metrics')} {where}
            GROUP BY service_name, cloud_provider
            ORDER BY total DESC
            LIMIT 10
            """,
            *args,
        ),
    )

    return {
        "summary": {
            "total_usd": round(float(total_usd or 0), 2),
            "by_cloud": {
                row["cloud_provider"]: round(float(row["total"]), 2) for row in cloud_rows
            },
            "period": {"start": start.isoformat(), "end": end.isoformat()},
        },
        "by_service": {
            "items": [
                {
                    "service_name": row["service_name"],
                    "cloud_provider": row["cloud_provider"],
                    "total_cost_usd": round(float(row["total"]), 2),
                }
                for row in svc_rows
            ],
        },
    }


async def _load_pipelines(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
) -> dict[str, Any]:
    conditions = ["status = ?"]
    args: list[Any] = ["failed"]
    add_lz_filter(conditions, args, allowed_lz_ids)
    where = "WHERE " + " AND ".join(conditions)
    limit = 5

    total, rows = await asyncio.gather(
        db.fetchscalar(
            "SELECT COUNT(*) "
            f"FROM {db.table('curated_pipeline_metrics')} "
            f"{where}",
            *args,
        ),
        db.fetchall(
            f"""
            SELECT pipeline_name, cloud_provider, start_time, error_message
            FROM {db.table('curated_pipeline_metrics')}
            {where}
            ORDER BY start_time DESC
            LIMIT ?
            """,
            *args,
            limit,
        ),
    )

    items = [
        {
            "pipeline_name": row["pipeline_name"],
            "cloud_provider": row["cloud_provider"],
            "start_time": _iso_period(row.get("start_time")),
            "error_message": row.get("error_message"),
        }
        for row in rows
    ]
    return {"pipelines": {"items": items, "total": int(total or 0)}}


async def _load_security(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
) -> dict[str, Any]:
    conditions = ["status = ?"]
    args: list[Any] = ["active"]
    add_lz_filter(conditions, args, allowed_lz_ids)
    where = "WHERE " + " AND ".join(conditions)
    limit = 5

    total, rows = await asyncio.gather(
        db.fetchscalar(
            "SELECT COUNT(*) "
            f"FROM {db.table('curated_security_alerts')} "
            f"{where}",
            *args,
        ),
        db.fetchall(
            f"""
            SELECT title, severity, cloud_provider, resource_type, detected_at
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
        ),
    )

    items = [
        {
            "title": row["title"],
            "severity": row["severity"],
            "cloud_provider": row["cloud_provider"],
            "resource_type": row.get("resource_type"),
            "detected_at": _iso_period(row.get("detected_at")),
        }
        for row in rows
    ]
    return {"security": {"items": items, "total": int(total or 0)}}


async def _load_governance(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
) -> dict[str, Any]:
    where_clauses: list[str] = []
    params: list[Any] = []
    add_lz_filter(where_clauses, params, allowed_lz_ids)
    where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    check_where = f"{where_sql} AND check_state = ?" if where_sql else "WHERE check_state = ?"
    check_params = [*params, "non_compliant", 5]

    score_row, check_rows = await asyncio.gather(
        db.fetchone(
            f"""
            SELECT
                SUM(compliant_count) AS compliant_count,
                SUM(non_compliant_count) AS non_compliant_count,
                SUM(total_checks) AS total_evaluated
            FROM {db.table('gold_standard_check_score')}
            {where_sql}
            """,
            *params,
        ),
        db.fetchall(
            f"""
            SELECT check_name, cloud_provider, resource_name, resource_id, resource_type
            FROM {db.table('curated_standard_checks')}
            {check_where}
            ORDER BY evaluated_at DESC
            LIMIT ?
            """,
            *check_params,
        ),
    )

    score = score_row or {}
    compliant = int(score.get("compliant_count") or 0)
    non_compliant = int(score.get("non_compliant_count") or 0)
    total_evaluated = int(score.get("total_evaluated") or 0)
    global_score = round(compliant / total_evaluated * 100, 1) if total_evaluated > 0 else None

    return {
        "score": {
            "global_score_pct": global_score,
            "compliant_count": compliant,
            "no_compliant_count": non_compliant,
            "total_evaluated": total_evaluated,
        },
        "checks": {
            "items": [
                {
                    "check_name": row["check_name"],
                    "cloud_provider": row["cloud_provider"],
                    "resource_name": row.get("resource_name"),
                    "resource_id": row.get("resource_id"),
                    "resource_type": row.get("resource_type"),
                }
                for row in check_rows
            ],
        },
    }


async def _load_data_product_usage(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
) -> dict[str, Any]:
    start, end = _default_dates()
    conditions = [
        "CAST(usage_date AS DATE) >= ?",
        "CAST(usage_date AS DATE) <= ?",
    ]
    args: list[Any] = [start, end]
    if allowed_lz_ids:
        placeholders = ", ".join("?" for _ in allowed_lz_ids)
        conditions.append(f"source_lz_id IN ({placeholders})")
        args.extend(allowed_lz_ids)
    where = "WHERE " + " AND ".join(conditions)

    overview_row, consumer_rows = await asyncio.gather(
        db.fetchone(
            f"""
            SELECT
                COUNT(DISTINCT data_product_id) AS total_data_products,
                COUNT(DISTINCT consumer_id) AS active_consumers,
                COALESCE(SUM(request_count), 0) AS request_count,
                COALESCE(SUM(cost_usd), 0) AS cost_usd
            FROM {db.table(_GOLD_DATA_PRODUCT_USAGE)}
            {where}
            """,
            *args,
        ),
        db.fetchall(
            f"""
            SELECT consumer_name, consumer_id, cloud_provider,
                   COALESCE(SUM(request_count), 0) AS request_count
            FROM {db.table(_GOLD_DATA_PRODUCT_USAGE)}
            {where}
            GROUP BY consumer_name, consumer_id, cloud_provider
            ORDER BY request_count DESC
            LIMIT ?
            """,
            *args,
            5,
        ),
    )

    overview = overview_row or {}
    return {
        "overview": {
            "total_data_products": int(overview.get("total_data_products") or 0),
            "active_consumers": int(overview.get("active_consumers") or 0),
            "request_count": int(overview.get("request_count") or 0),
            "cost_usd": round(float(overview.get("cost_usd") or 0), 2),
            "period": {"start": start.isoformat(), "end": end.isoformat()},
        },
        "consumers": {
            "items": [
                {
                    "consumer_name": row.get("consumer_name"),
                    "consumer_id": row["consumer_id"],
                    "cloud_provider": row["cloud_provider"],
                    "request_count": int(row["request_count"]),
                }
                for row in consumer_rows
            ],
        },
    }


async def _load_compute(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
) -> dict[str, Any]:
    inner_conditions: list[str] = []
    inner_args: list[Any] = []
    add_lz_filter(inner_conditions, inner_args, allowed_lz_ids)
    inner_where = ("WHERE " + " AND ".join(inner_conditions)) if inner_conditions else ""

    rows = await db.fetchall(
        f"""
        SELECT resource_name, cloud_provider, state, compute_type, num_workers,
               avg_cpu_utilization_pct, avg_mem_utilization_pct
        FROM (
            SELECT resource_name, cloud_provider, state, compute_type, num_workers,
                   avg_cpu_utilization_pct, avg_mem_utilization_pct,
                   ROW_NUMBER() OVER (
                       PARTITION BY compute_resource_id
                       ORDER BY collected_at DESC
                   ) AS rn
            FROM {db.table('curated_compute_metrics')}
            {inner_where}
        ) latest
        WHERE rn = 1
        ORDER BY resource_name
        """,
        *inner_args,
    )

    items = [
        {
            "resource_name": row["resource_name"],
            "cloud_provider": row["cloud_provider"],
            "state": row["state"],
            "compute_type": row.get("compute_type"),
            "num_workers": row.get("num_workers"),
            "avg_cpu_utilization_pct": row.get("avg_cpu_utilization_pct"),
            "avg_mem_utilization_pct": row.get("avg_mem_utilization_pct"),
        }
        for row in rows
    ]
    return {"compute": {"items": items}}


async def _load_databases(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
) -> dict[str, Any]:
    inner_conditions: list[str] = []
    inner_args: list[Any] = []
    add_lz_filter(inner_conditions, inner_args, allowed_lz_ids)
    inner_where = ("WHERE " + " AND ".join(inner_conditions)) if inner_conditions else ""

    rows = await db.fetchall(
        f"""
        SELECT db_name, db_id, db_type, cloud_provider, is_available,
               active_connections, storage_used_gb, storage_limit_gb
        FROM (
            SELECT db_name, db_id, db_type, cloud_provider, is_available,
                   NULL AS active_connections,
                   storage_used_gb,
                   NULL AS storage_limit_gb,
                   ROW_NUMBER() OVER (PARTITION BY db_id ORDER BY collected_at DESC) AS rn
            FROM {db.table('curated_database_metrics')}
            {inner_where}
        ) latest
        WHERE rn = 1
        ORDER BY db_name
        """,
        *inner_args,
    )

    items = [
        {
            "db_name": row.get("db_name"),
            "db_id": row["db_id"],
            "db_type": row["db_type"],
            "cloud_provider": row["cloud_provider"],
            "is_available": row["is_available"],
            "active_connections": row.get("active_connections"),
            "storage_used_gb": row.get("storage_used_gb"),
            "storage_limit_gb": row.get("storage_limit_gb"),
        }
        for row in rows
    ]
    return {"databases": {"items": items}}


async def _load_overview(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
) -> dict[str, Any]:
    start, end = _default_dates()

    pipeline_conditions = ["CAST(start_time AS DATE) BETWEEN ? AND ?"]
    pipeline_args: list[Any] = [start, end]
    add_lz_filter(pipeline_conditions, pipeline_args, allowed_lz_ids)
    pipeline_where = "WHERE " + " AND ".join(pipeline_conditions)

    cutoff_24h = datetime.now(UTC) - timedelta(hours=24)
    failed_conditions = ["status = 'failed'", "start_time >= ?"]
    failed_args: list[Any] = [cutoff_24h]
    add_lz_filter(failed_conditions, failed_args, allowed_lz_ids)
    failed_where = "WHERE " + " AND ".join(failed_conditions)

    compute_conditions: list[str] = []
    compute_args: list[Any] = []
    add_lz_filter(compute_conditions, compute_args, allowed_lz_ids)
    compute_where = ("WHERE " + " AND ".join(compute_conditions)) if compute_conditions else ""

    cost_conditions: list[str] = []
    cost_args: list[Any] = []
    add_cost_period_filter(cost_conditions, cost_args, start, end)
    add_lz_filter(cost_conditions, cost_args, allowed_lz_ids)
    cost_where = "WHERE " + " AND ".join(cost_conditions)

    alert_conditions = ["status = 'active'"]
    alert_args: list[Any] = []
    add_lz_filter(alert_conditions, alert_args, allowed_lz_ids)
    alert_where = "WHERE " + " AND ".join(alert_conditions)

    cloud_conditions: list[str] = []
    cloud_args: list[Any] = []
    add_lz_filter(cloud_conditions, cloud_args, allowed_lz_ids)
    cloud_where = ("WHERE " + " AND ".join(cloud_conditions)) if cloud_conditions else ""

    (
        total_pipelines,
        failed_pipelines_24h,
        active_compute,
        total_cost_usd,
        open_alerts,
        cloud_rows,
    ) = await asyncio.gather(
        db.fetchscalar(
            f"SELECT COUNT(*) FROM {db.table('curated_pipeline_metrics')} "
            f"{pipeline_where}",
            *pipeline_args,
        ),
        db.fetchscalar(
            f"SELECT COUNT(*) FROM {db.table('curated_pipeline_metrics')} "
            f"{failed_where}",
            *failed_args,
        ),
        db.fetchscalar(
            f"""
            SELECT COUNT(*) FROM (
                SELECT compute_resource_id, state,
                       ROW_NUMBER() OVER (
                           PARTITION BY compute_resource_id
                           ORDER BY collected_at DESC
                       ) AS rn
                FROM {db.table('curated_compute_metrics')}
                {compute_where}
            ) latest
            WHERE rn = 1 AND state = 'running'
            """,
            *compute_args,
        ),
        db.fetchscalar(
            "SELECT COALESCE(SUM(cost_usd), 0) "
            f"FROM {db.table('curated_cost_metrics')} "
            f"{cost_where}",
            *cost_args,
        ),
        db.fetchscalar(
            "SELECT COUNT(*) "
            f"FROM {db.table('curated_security_alerts')} "
            f"{alert_where}",
            *alert_args,
        ),
        db.fetchall(
            f"""
            SELECT DISTINCT cloud_provider
            FROM {db.table('curated_pipeline_metrics')}
            {cloud_where}
            ORDER BY cloud_provider
            """,
            *cloud_args,
        ),
    )

    return {
        "overview": {
            "total_pipelines": int(total_pipelines or 0),
            "failed_pipelines_24h": int(failed_pipelines_24h or 0),
            "active_clusters": int(active_compute or 0),
            "total_cost_usd": round(float(total_cost_usd or 0), 2),
            "open_alerts": int(open_alerts or 0),
            "cloud_coverage": [row["cloud_provider"] for row in cloud_rows],
            "period": {"start": start.isoformat(), "end": end.isoformat()},
        },
    }
