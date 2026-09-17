"""Aggregated dashboard queries — single HTTP round-trip for the home page."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ...db.connection import DatabricksWarehousePool
from ..routes._lz_filter import (
    add_cost_period_filter,
    add_scope_lz_filter,
)
from .clusters_page import add_workspace_filter as _add_workspace_filter
from .clusters_page import row_to_compute as _row_to_compute
from .compute_metrics_common import _add_rbac_scope
from .databases_page import fetch_databases
from .pipelines_page import PIPELINE_TYPE_SQL as _PIPELINE_TYPE_SQL
from .pipelines_page import row_to_pipeline as _row_to_pipeline
from .security_serializers import row_to_alert as _row_to_alert

__all__ = ["fetch_dashboard_full", "fetch_overview_metrics"]

_DEFAULT_LOOKBACK_DAYS = 30
_PIPELINE_LIST_LIMIT = 8
_ALERT_LIST_LIMIT = 8

# Databricks total cost has no single source table — each compute type bills
# separately, and 3 of these 5 gold tables already cover BOTH classic and
# serverless billing for their compute type (confirmed against UC dev:
# job_cluster/pipeline carry compute_kind CLASSIC+SERVERLESS, and
# warehouse_cost_daily's warehouse_id/period_start/workspace_id match 100% of
# serverless_cost_daily's SQL_WAREHOUSE rows). A naive UNION ALL of all 5
# double-counts those rows, since cluster_cost_daily also re-slices JOB/
# PIPELINE cluster types and serverless_cost_daily re-slices JOB/DLT_PIPELINE/
# SQL_WAREHOUSE surfaces of the SAME underlying cost. Each table below is
# filtered to the slice it uniquely owns.
_DBX_COST_DAILY_TABLES: tuple[tuple[str, str | None], ...] = (
    ("gold_dbx_compute_cluster_cost_daily", "cluster_type = 'ALL_PURPOSE'"),
    ("gold_dbx_compute_warehouse_cost_daily", None),
    ("gold_dbx_compute_job_cluster_cost_daily", None),
    ("gold_dbx_compute_pipeline_cost_daily", None),
    (
        "gold_dbx_compute_serverless_cost_daily",
        "serverless_surface NOT IN ('JOB', 'DLT_PIPELINE', 'SQL_WAREHOUSE')",
    ),
)


def _dbx_cost_union_sql(db: DatabricksWarehousePool) -> str:
    parts = (
        f"SELECT period_start, cost_usd, workspace_id FROM {db.table(name)}"
        + (f" WHERE {where}" if where else "")
        for name, where in _DBX_COST_DAILY_TABLES
    )
    return " UNION ALL ".join(parts)


def _default_dates() -> tuple[date, date]:
    today = datetime.now(UTC).date()
    return today - timedelta(days=_DEFAULT_LOOKBACK_DAYS), today


def _resolve_period(
    start_date: date | None,
    end_date: date | None,
) -> tuple[date, date]:
    start, end = _default_dates()
    if start_date is not None:
        start = start_date
    if end_date is not None:
        end = end_date
    return start, end


def _append_scope_filters(
    conditions: list[str],
    args: list[Any],
    allowed_lz_ids: list[str] | None,
    *,
    cloud_provider: str | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
) -> None:
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


def _pipeline_period_where(
    allowed_lz_ids: list[str] | None,
    *,
    start: date,
    end: date,
    cloud_provider: str | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
) -> tuple[str, list[Any]]:
    conditions = ["CAST(start_time AS DATE) BETWEEN ? AND ?"]
    args: list[Any] = [start, end]
    _append_scope_filters(
        conditions,
        args,
        allowed_lz_ids,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )
    return "WHERE " + " AND ".join(conditions), args


async def fetch_overview_metrics(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    allowed_workspace_ids: list[str] | None = None,
    *,
    start: date,
    end: date,
    cloud_provider: str | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    workspace_id: str | None = None,
    workspace_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Load all dashboard overview KPIs in parallel."""
    pipeline_where, pipeline_args = _pipeline_period_where(
        allowed_lz_ids,
        start=start,
        end=end,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )
    adf_suffix = (
        f" AND LOWER({_PIPELINE_TYPE_SQL}) = LOWER(?) AND pipeline_id NOT LIKE 'databricks:job:%'"
    )
    adf_args = [*pipeline_args, "adf"]
    databricks_suffix = (
        f" AND (pipeline_id LIKE 'databricks:job:%' OR LOWER({_PIPELINE_TYPE_SQL}) = LOWER(?))"
    )
    databricks_args = [*pipeline_args, "databricks_job"]

    cutoff_24h = datetime.now(UTC) - timedelta(hours=24)
    failed_conditions = ["status = 'failed'", "start_time >= ?"]
    failed_args: list[Any] = [cutoff_24h]
    _append_scope_filters(
        failed_conditions,
        failed_args,
        allowed_lz_ids,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )
    failed_where = "WHERE " + " AND ".join(failed_conditions)

    # Databricks-only version of the failed-jobs KPI for the home page's
    # "Databricks" section — curated_pipeline_metrics is the legacy multi-cloud
    # collector (kept above for the all-clouds Pipelines page); gold_dbx_workflow_runs
    # is Databricks-specific and scoped by workspace_id, not source_lz_id.
    #
    # Anchored on the table's own freshest row, not wall-clock now(): this table
    # lags collection by ~48h (same lag the "data as of" banner on Jobs &
    # Pipelines already surfaces), so a literal now()-24h window falls entirely
    # after the newest row and silently returns 0 regardless of real failures.
    databricks_failed_conditions = [
        "status = 'failed'",
        f"start_time >= (SELECT MAX(start_time) FROM {db.table('gold_dbx_workflow_runs')}) "
        "- INTERVAL 1 DAY",
    ]
    databricks_failed_args: list[Any] = []
    _add_rbac_scope(
        databricks_failed_conditions,
        databricks_failed_args,
        allowed_lz_ids=None,
        allowed_workspace_ids=allowed_workspace_ids,
        has_lz_column=False,
    )
    _add_workspace_filter(
        databricks_failed_conditions,
        databricks_failed_args,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
    )
    databricks_failed_where = "WHERE " + " AND ".join(databricks_failed_conditions)

    # TODO(home-page legacy->gold_dbx migration): active_clusters/active_compute
    # below still reads curated_compute_metrics (legacy, multi-cloud, source_lz_id
    # scope). Decided replacement: curated_dbx_compute_node_timeline, scoped by
    # workspace_id, COUNT(DISTINCT cluster_id) with activity in [start, end] —
    # NOT "currently running": there's no Databricks-specific table with a live
    # cluster state (unlike warehouses, which have *_warehouse_events). Checked
    # curated_dbx_compute_clusters (create_time/delete_time only, no state) and
    # node_timeline itself (its freshest row is ~24h+ old, every row already has
    # a non-null end_time — no "still open" signal to key off). So "active" here
    # means "had activity in the period", same relaxed semantics as "active
    # pipelines" already implies elsewhere on this page, not a live snapshot.
    compute_conditions: list[str] = []
    compute_args: list[Any] = []
    _append_scope_filters(
        compute_conditions,
        compute_args,
        allowed_lz_ids,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )
    compute_where = ("WHERE " + " AND ".join(compute_conditions)) if compute_conditions else ""

    cost_conditions: list[str] = []
    cost_args: list[Any] = []
    add_cost_period_filter(cost_conditions, cost_args, start, end)
    _append_scope_filters(
        cost_conditions,
        cost_args,
        allowed_lz_ids,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )
    cost_where = "WHERE " + " AND ".join(cost_conditions)

    alert_conditions = ["status = 'active'"]
    alert_args: list[Any] = []
    _append_scope_filters(
        alert_conditions,
        alert_args,
        allowed_lz_ids,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )
    alert_where = "WHERE " + " AND ".join(alert_conditions)

    cloud_conditions: list[str] = []
    cloud_args: list[Any] = []
    _append_scope_filters(
        cloud_conditions,
        cloud_args,
        allowed_lz_ids,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )
    cloud_where = ("WHERE " + " AND ".join(cloud_conditions)) if cloud_conditions else ""

    now = datetime.now(UTC)
    ytd_end = now.date()
    ytd_start = date(ytd_end.year, 1, 1)
    previous_ytd_start = date(ytd_end.year - 1, 1, 1)
    try:
        previous_ytd_end = ytd_end.replace(year=ytd_end.year - 1)
    except ValueError:
        previous_ytd_end = date(ytd_end.year - 1, 2, 28)

    # Databricks compute cost daily facts have no source_lz_id (only
    # workspace_id, like the warehouse events above) and period_start is
    # already a DATE column — no CAST needed, unlike curated_cost_metrics.
    ytd_conditions = [
        "((period_start >= ? AND period_start <= ?) "
        "OR (period_start >= ? AND period_start <= ?))"
    ]
    ytd_args: list[Any] = [
        ytd_start,
        ytd_end,
        previous_ytd_start,
        previous_ytd_end,
    ]
    _add_rbac_scope(
        ytd_conditions,
        ytd_args,
        allowed_lz_ids=None,
        allowed_workspace_ids=allowed_workspace_ids,
        has_lz_column=False,
    )
    _add_workspace_filter(
        ytd_conditions,
        ytd_args,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
    )
    ytd_where = "WHERE " + " AND ".join(ytd_conditions)
    dbx_cost_union = _dbx_cost_union_sql(db)

    # curated_dbx_compute_warehouses has no "running" state at all — it only
    # tracks warehouse existence (delete_time), not activity. The event log
    # (curated_dbx_compute_warehouse_events, STARTING/RUNNING/STOPPING/STOPPED)
    # is what "active" actually means here — same idea as the cluster query
    # above (latest state per resource). Neither table has source_lz_id (only
    # workspace_id), so has_lz_column=False.
    warehouse_conditions: list[str] = []
    warehouse_args: list[Any] = []
    _add_rbac_scope(
        warehouse_conditions,
        warehouse_args,
        allowed_lz_ids=None,
        allowed_workspace_ids=allowed_workspace_ids,
        has_lz_column=False,
    )
    _add_workspace_filter(
        warehouse_conditions,
        warehouse_args,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
    )
    if cloud_provider:
        warehouse_conditions.append("cloud_provider = ?")
        warehouse_args.append(cloud_provider)
    warehouse_where = (
        ("WHERE " + " AND ".join(warehouse_conditions)) if warehouse_conditions else ""
    )

    (
        total_pipelines,
        total_adf_pipelines,
        total_databricks_pipelines,
        failed_pipelines_24h,
        failed_databricks_jobs_24h,
        active_compute,
        total_cost_usd,
        open_alerts,
        cloud_rows,
        active_sql_warehouses,
        cost_ytd_usd,
        cost_ytd_previous_year_usd,
        alert_rows,
        monthly_cost_rows,
    ) = await asyncio.gather(
        db.fetchscalar(
            f"SELECT COUNT(*) FROM {db.table('curated_pipeline_metrics')} "
            f"{pipeline_where}",
            *pipeline_args,
        ),
        db.fetchscalar(
            f"SELECT COUNT(*) FROM {db.table('curated_pipeline_metrics')} "
            f"{pipeline_where}{adf_suffix}",
            *adf_args,
        ),
        db.fetchscalar(
            f"SELECT COUNT(*) FROM {db.table('curated_pipeline_metrics')} "
            f"{pipeline_where}{databricks_suffix}",
            *databricks_args,
        ),
        db.fetchscalar(
            f"SELECT COUNT(*) FROM {db.table('curated_pipeline_metrics')} "
            f"{failed_where}",
            *failed_args,
        ),
        db.fetchscalar(
            f"SELECT COUNT(*) FROM {db.table('gold_dbx_workflow_runs')} "
            f"{databricks_failed_where}",
            *databricks_failed_args,
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
        db.fetchscalar(
            f"""
            SELECT COUNT(*) FROM (
                SELECT warehouse_id, event_type,
                       ROW_NUMBER() OVER (
                           PARTITION BY warehouse_id
                           ORDER BY event_time DESC
                       ) AS rn
                FROM {db.table('curated_dbx_compute_warehouse_events')}
                {warehouse_where}
            ) latest
            WHERE rn = 1 AND event_type = 'RUNNING'
            """,
            *warehouse_args,
        ),
        db.fetchscalar(
            "SELECT COALESCE(SUM(cost_usd), 0) "
            f"FROM ({dbx_cost_union}) dbx_cost "
            f"{ytd_where} AND YEAR(period_start) = ?",
            *ytd_args,
            ytd_end.year,
        ),
        db.fetchscalar(
            "SELECT COALESCE(SUM(cost_usd), 0) "
            f"FROM ({dbx_cost_union}) dbx_cost "
            f"{ytd_where} AND YEAR(period_start) = ?",
            *ytd_args,
            previous_ytd_end.year,
        ),
        db.fetchall(
            f"""
            SELECT LOWER(severity) AS severity, COUNT(*) AS count
            FROM {db.table('curated_security_alerts')}
            {alert_where}
            GROUP BY LOWER(severity)
            """,
            *alert_args,
        ),
        db.fetchall(
            f"""
            SELECT
                MONTH(period_start) AS month_number,
                SUM(CASE WHEN YEAR(period_start) = ? THEN cost_usd ELSE 0 END)
                    AS current_year_usd,
                SUM(CASE WHEN YEAR(period_start) = ? THEN cost_usd ELSE 0 END)
                    AS previous_year_usd,
                SUM(CASE WHEN YEAR(period_start) = ? THEN 1 ELSE 0 END)
                    AS previous_year_count
            FROM ({dbx_cost_union}) dbx_cost
            {ytd_where}
            GROUP BY MONTH(period_start)
            ORDER BY month_number
            """,
            ytd_end.year,
            previous_ytd_end.year,
            previous_ytd_end.year,
            *ytd_args,
        ),
    )

    cloud_coverage = [row["cloud_provider"] for row in cloud_rows]
    active_compute_count = int(active_compute or 0)
    ytd_cost = round(float(cost_ytd_usd or 0.0), 2)
    previous_ytd_cost = round(float(cost_ytd_previous_year_usd or 0.0), 2)
    ytd_delta = round(ytd_cost - previous_ytd_cost, 2)
    ytd_delta_pct = (
        round((ytd_delta / previous_ytd_cost) * 100, 3)
        if previous_ytd_cost
        else None
    )
    alert_breakdown = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for row in alert_rows:
        severity = str(row.get("severity", "")).lower()
        if severity in alert_breakdown:
            alert_breakdown[severity] = int(row.get("count") or 0)

    monthly_cost = [
        {
            "month": f"{ytd_end.year}-{int(row['month_number']):02d}",
            "current_year_usd": round(float(row.get("current_year_usd") or 0.0), 2),
            "previous_year_usd": (
                round(float(row.get("previous_year_usd") or 0.0), 2)
                if int(row.get("previous_year_count") or 0) > 0
                else None
            ),
        }
        for row in monthly_cost_rows
        if row.get("month_number") is not None
    ]

    return {
        "total_pipelines": int(total_pipelines or 0),
        "total_adf_pipelines": int(total_adf_pipelines or 0),
        "total_databricks_pipelines": int(total_databricks_pipelines or 0),
        "failed_pipelines_24h": int(failed_pipelines_24h or 0),
        "failed_databricks_jobs_24h": int(failed_databricks_jobs_24h or 0),
        "active_clusters": active_compute_count,
        "active_compute": active_compute_count,
        "active_sql_warehouses": int(active_sql_warehouses or 0),
        "as_of": now.isoformat().replace("+00:00", "Z"),
        "cost_ytd_usd": ytd_cost,
        "cost_ytd_previous_year_usd": previous_ytd_cost,
        "cost_ytd_delta_usd": ytd_delta,
        "cost_ytd_delta_pct": ytd_delta_pct,
        "cost_ytd_monthly": monthly_cost,
        "alert_breakdown": alert_breakdown,
        "total_cost_usd": round(float(total_cost_usd or 0.0), 2),
        "open_alerts": int(open_alerts or 0),
        "cloud_coverage": cloud_coverage,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
    }


async def _fetch_governance_score(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
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

    global_row, breakdown_rows = await asyncio.gather(
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
        ),
    )

    compliant = int((global_row or {}).get("compliant_count") or 0)
    non_compliant = int((global_row or {}).get("non_compliant_count") or 0)
    total_evaluated = int((global_row or {}).get("total_evaluated") or 0)
    global_score = round(compliant / total_evaluated * 100, 1) if total_evaluated > 0 else None

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

    by_cloud = {row["cloud_provider"]: round(float(row["total"]), 2) for row in cloud_rows}
    by_service = [
        {
            "service_name": row["service_name"],
            "cloud_provider": row["cloud_provider"],
            "cost_usd": round(float(row["total"]), 2),
        }
        for row in svc_rows
    ]

    return {
        "total_usd": round(float(total_usd or 0.0), 2),
        "by_cloud": by_cloud,
        "by_service": by_service,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
    }


async def _fetch_pipeline_preview(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start: date,
    end: date,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    pipeline_type: str | None = None,
    limit: int = _PIPELINE_LIST_LIMIT,
) -> list[dict[str, Any]]:
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
    if pipeline_type:
        conditions.append(f"LOWER({_PIPELINE_TYPE_SQL}) = LOWER(?)")
        args.append(pipeline_type)
    conditions.append("CAST(start_time AS DATE) >= ?")
    args.append(start)
    conditions.append("CAST(start_time AS DATE) <= ?")
    args.append(end)

    where = "WHERE " + " AND ".join(conditions)
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


async def _fetch_compute_items(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    workspace_id: str | None,
    workspace_ids: list[str] | None,
) -> list[dict[str, Any]]:
    inner_conditions: list[str] = []
    inner_args: list[Any] = []
    add_scope_lz_filter(
        inner_conditions,
        inner_args,
        allowed_lz_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )

    outer_conditions: list[str] = []
    outer_args: list[Any] = []
    if cloud_provider:
        outer_conditions.append("cloud_provider = ?")
        outer_args.append(cloud_provider)
    _add_workspace_filter(
        outer_conditions,
        outer_args,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
    )

    inner_where = ("WHERE " + " AND ".join(inner_conditions)) if inner_conditions else ""
    where_clause = "WHERE rn = 1"
    if outer_conditions:
        where_clause += " AND " + " AND ".join(outer_conditions)

    rows = await db.fetchall(
        f"""
        SELECT
            compute_resource_id, resource_name, compute_type, cloud_provider, source_lz_id,
            subscription_or_account_id, workspace_id, state, num_workers, node_type,
            spark_version, avg_cpu_utilization_pct, avg_mem_utilization_pct, tags, collected_at
        FROM (
            SELECT
                compute_resource_id, resource_name, compute_type, cloud_provider, source_lz_id,
                subscription_or_account_id, workspace_id, state, num_workers, node_type,
                spark_version, avg_cpu_utilization_pct, avg_mem_utilization_pct, tags, collected_at,
                ROW_NUMBER() OVER (
                    PARTITION BY compute_resource_id
                    ORDER BY collected_at DESC
                ) as rn
            FROM {db.table('curated_compute_metrics')}
            {inner_where}
        ) latest
        {where_clause}
        ORDER BY resource_name
        """,
        *inner_args,
        *outer_args,
    )
    return [_row_to_compute(row) for row in rows]




async def _fetch_alert_preview(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    start: date,
    end: date,
    cloud_provider: str | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    limit: int = _ALERT_LIST_LIMIT,
) -> list[dict[str, Any]]:
    conditions: list[str] = ["status = 'active'"]
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
    conditions.append("CAST(detected_at AS DATE) >= ?")
    args.append(start)
    conditions.append("CAST(detected_at AS DATE) <= ?")
    args.append(end)

    where = "WHERE " + " AND ".join(conditions)
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
    return [_row_to_alert(row) for row in rows]


async def fetch_dashboard_full(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    allowed_workspace_ids: list[str] | None = None,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    cloud_provider: str | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    workspace_id: str | None = None,
    workspace_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return all dashboard sections in one response."""
    start, end = _resolve_period(start_date, end_date)

    overview, governance, costs, pipelines, computes, databases, alerts = await asyncio.gather(
        fetch_overview_metrics(
            db,
            allowed_lz_ids,
            allowed_workspace_ids,
            start=start,
            end=end,
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
        _fetch_cost_summary(
            db,
            allowed_lz_ids,
            start=start,
            end=end,
            cloud_provider=cloud_provider,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
        ),
        _fetch_pipeline_preview(
            db,
            allowed_lz_ids,
            start=start,
            end=end,
            cloud_provider=cloud_provider,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
        ),
        _fetch_compute_items(
            db,
            allowed_lz_ids,
            cloud_provider=cloud_provider,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_id=workspace_id,
            workspace_ids=workspace_ids,
        ),
        fetch_databases(
            db,
            allowed_lz_ids,
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
        ),
    )

    return {
        "overview": overview,
        "governance": governance,
        "costs": costs,
        "pipelines": pipelines,
        "computes": computes,
        "databases": databases,
        "alerts": alerts,
    }
