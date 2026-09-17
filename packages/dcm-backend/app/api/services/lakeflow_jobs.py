"""Lakeflow Jobs — N1 list / N2 workflow detail / N3 run tasks.

Gold sources (no curated fallback):
  gold_dbx_workflow_success_rate
  gold_dbx_workflow_duration_percentiles
  gold_dbx_workflow_duration_drift
  gold_dbx_workflow_task_failure_rate
  gold_dbx_workflow_runs
  gold_dbx_workflow_tasks
  gold_dbx_workflow_task_health (optional soft-fail)

Perf notes (N1):
  - Single warehouse round-trip for list+total via COUNT(*) OVER()
  - Skip last-run CTE unless status/trigger/owner filters need it;
    last_* display fields are filled from the page history query
  - Short in-memory response cache (30s)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

from ...auth.scope_model import AllowedScope
from ...cache.response_cache import (
    build_cache_key,
    cache_key_ids,
    cache_key_scope,
    get_cached_response,
)
from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.lz_scope import narrow_workspace_ids, resolve_request_lz_workspace_ids
from ...db.tables import qualified_table
from .compute_metrics_filters import (
    AppliedFilter,
    cache_key_column_filters,
    column_filter_predicates,
    needs_last_run,
    parse_column_filters,
)
from .lakeflow_overview import (
    _date_where,
    _resolve_period,
    _safe,
    _scope_where,
    fetch_lakeflow_as_of,
)

__all__ = [
    "fetch_lakeflow_jobs",
    "fetch_lakeflow_job_detail",
    "fetch_lakeflow_job_runs",
    "fetch_lakeflow_run_tasks",
]

logger = logging.getLogger(__name__)

_SUCCESS = "gold_dbx_workflow_success_rate"
_PERCENTILES = "gold_dbx_workflow_duration_percentiles"
_DRIFT = "gold_dbx_workflow_duration_drift"
_TASK_FAIL = "gold_dbx_workflow_task_failure_rate"
_RUNS = "gold_dbx_workflow_runs"
_TASKS = "gold_dbx_workflow_tasks"
_TASK_HEALTH = "gold_dbx_workflow_task_health"
# Execution cost per job (DCINT-294). Only covers clusters of type JOB — a job
# that only ever runs on interactive/serverless compute has no row here, so
# execution_cost_usd comes back null rather than 0 (a real "no data" reads
# nothing like a real "billed nothing"). curated_dbx_billing_usage carries a
# finer, per-run job_run_id if a future ticket needs that granularity instead.
_JOB_COST = "gold_dbx_compute_job_cluster_cost_daily"

_DEFAULT_PAGE_SIZE = 25
_MAX_PAGE_SIZE = 200
_HISTORY_N = 10
_MATRIX_RUNS_N = 20
_JOBS_CACHE_TTL_SECONDS = 30.0


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


async def fetch_lakeflow_jobs(
    db: DatabricksWarehousePool,
    settings: Settings,
    scope: AllowedScope,
    *,
    window: str = "30d",
    start_date: date | None = None,
    end_date: date | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    workspace_ids: list[str] | None = None,
    search: str | None = None,
    status: list[str] | None = None,
    trigger_type: list[str] | None = None,
    owner: list[str] | None = None,
    drift_only: bool = False,
    no_runs: bool = False,
    with_retries: bool = False,
    column_filter: list[str] | None = None,
    sort: str = "problems",
    order: str = "desc",
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """N1 — one row per workflow, server-paginated, with last-10 history."""
    # Parsed before the cache is consulted: a refused filter must reach the caller as a
    # 422, not be answered from — or written into — a cache entry.
    column_filters = parse_column_filters(
        "lakeflow-jobs",
        column_filter,
        search=search,
        status=status,
        trigger_type=trigger_type,
    )
    window_key, start, end = _resolve_period(window, start_date, end_date)
    page = max(1, page)
    page_size = min(max(1, page_size), _MAX_PAGE_SIZE)

    cache_key = build_cache_key(
        "lakeflow-jobs",
        scope=cache_key_scope(scope),
        window=window_key,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        source_lz_id=source_lz_id,
        source_lz_ids=cache_key_ids(source_lz_ids),
        workspace_ids=cache_key_ids(workspace_ids),
        search=search or "",
        status=sorted(s.lower() for s in status) if status else None,
        trigger_type=sorted(trigger_type) if trigger_type else None,
        owner=sorted(owner) if owner else None,
        drift_only=drift_only,
        no_runs=no_runs,
        with_retries=with_retries,
        # In the cache key, and not as the raw strings: two requests that filter the
        # same way share an entry, and one that filters differently cannot read it.
        column_filter=cache_key_column_filters(column_filters),
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )

    async def load() -> dict[str, Any]:
        return await _fetch_lakeflow_jobs_uncached(
            db,
            settings,
            scope,
            window_key=window_key,
            start=start,
            end=end,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_ids=workspace_ids,
            status=status,
            trigger_type=trigger_type,
            owner=owner,
            drift_only=drift_only,
            no_runs=no_runs,
            with_retries=with_retries,
            column_filters=column_filters,
            sort=sort,
            order=order,
            page=page,
            page_size=page_size,
        )

    return await get_cached_response(cache_key, load, ttl_seconds=_JOBS_CACHE_TTL_SECONDS)


async def _fetch_lakeflow_jobs_uncached(
    db: DatabricksWarehousePool,
    settings: Settings,
    scope: AllowedScope,
    *,
    window_key: str,
    start: date,
    end: date,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    workspace_ids: list[str] | None,
    status: list[str] | None,
    trigger_type: list[str] | None,
    owner: list[str] | None,
    drift_only: bool,
    no_runs: bool,
    with_retries: bool,
    column_filters: list[AppliedFilter],
    sort: str,
    order: str,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    offset = (page - 1) * page_size
    # gold_dbx_workflow_* tables carry no source_lz_id — resolve the header LZ
    # filter to its workspaces and narrow the workspace filter with it.
    workspace_ids = narrow_workspace_ids(
        workspace_ids,
        await resolve_request_lz_workspace_ids(
            db, settings, source_lz_id=source_lz_id, source_lz_ids=source_lz_ids
        ),
    )
    success_t = qualified_table(settings, _SUCCESS)
    pct_t = qualified_table(settings, _PERCENTILES)
    drift_t = qualified_table(settings, _DRIFT)
    task_t = qualified_table(settings, _TASK_FAIL)
    runs_t = qualified_table(settings, _RUNS)
    cost_t = qualified_table(settings, _JOB_COST)

    as_of = await _safe(
        fetch_lakeflow_as_of(
            db, settings, scope, source_lz_id, source_lz_ids, workspace_ids
        ),
        None,
        "jobs-as-of",
    )

    empty = {
        "items": [],
        "total": 0,
        "page": page,
        "page_size": page_size,
        "total_cost_usd": None,
        "jobs_with_cost": 0,
        "as_of": as_of,
        "window": {"key": window_key, "from": start.isoformat(), "to": end.isoformat()},
    }

    try:
        rows, total, total_cost_usd, jobs_with_cost = await _query_jobs_page(
            db,
            success_t,
            pct_t,
            drift_t,
            task_t,
            runs_t,
            cost_t,
            scope,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_ids=workspace_ids,
            start=start,
            end=end,
            status=status,
            trigger_type=trigger_type,
            owner=owner,
            drift_only=drift_only,
            no_runs=no_runs,
            with_retries=with_retries,
            column_filters=column_filters,
            sort=sort,
            order=order,
            limit=page_size,
            offset=offset,
        )
    except Exception:
        logger.exception("lakeflow jobs list soft-fail")
        return empty

    page_ids = [str(r["workflow_id"]) for r in rows if r.get("workflow_id") is not None]
    history_by_wf: dict[str, list[dict[str, Any]]] = {wid: [] for wid in page_ids}
    if page_ids:
        history_by_wf = await _safe(
            _fetch_history_for_page(
                db,
                runs_t,
                scope,
                source_lz_id=source_lz_id,
                source_lz_ids=source_lz_ids,
                workspace_ids=workspace_ids,
                workflow_ids=page_ids,
                start=start,
                end=end,
            ),
            history_by_wf,
            "jobs-history",
        )

    items = [_row_to_job_list_item(r, history_by_wf.get(str(r["workflow_id"]), [])) for r in rows]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_cost_usd": total_cost_usd,
        "jobs_with_cost": jobs_with_cost,
        "as_of": as_of,
        "window": {"key": window_key, "from": start.isoformat(), "to": end.isoformat()},
    }


async def fetch_lakeflow_job_detail(
    db: DatabricksWarehousePool,
    settings: Settings,
    scope: AllowedScope,
    workflow_id: str,
    *,
    window: str = "30d",
    start_date: date | None = None,
    end_date: date | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    workspace_ids: list[str] | None = None,
) -> dict[str, Any] | None:
    """N2 header + KPI bandeau for one workflow."""
    window_key, start, end = _resolve_period(window, start_date, end_date)
    workspace_ids = narrow_workspace_ids(
        workspace_ids,
        await resolve_request_lz_workspace_ids(
            db, settings, source_lz_id=source_lz_id, source_lz_ids=source_lz_ids
        ),
    )
    success_t = qualified_table(settings, _SUCCESS)
    pct_t = qualified_table(settings, _PERCENTILES)
    drift_t = qualified_table(settings, _DRIFT)
    task_t = qualified_table(settings, _TASK_FAIL)
    runs_t = qualified_table(settings, _RUNS)
    cost_t = qualified_table(settings, _JOB_COST)

    try:
        rows, _, _, _ = await _query_jobs_page(
            db,
            success_t,
            pct_t,
            drift_t,
            task_t,
            runs_t,
            cost_t,
            scope,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_ids=workspace_ids,
            start=start,
            end=end,
            workflow_id=workflow_id,
            sort="alpha",
            order="asc",
            limit=1,
            offset=0,
        )
    except Exception:
        logger.exception("lakeflow job detail soft-fail")
        return None

    if not rows:
        return None

    item = _row_to_job_list_item(rows[0], [])
    as_of = await _safe(
        fetch_lakeflow_as_of(
            db, settings, scope, source_lz_id, source_lz_ids, workspace_ids
        ),
        None,
        "job-detail-as-of",
    )
    return {
        "workflow": item,
        "as_of": as_of,
        "window": {"key": window_key, "from": start.isoformat(), "to": end.isoformat()},
    }


def _runs_sort_clause(sort: str, order: str) -> str:
    order_dir = "ASC" if (order or "").lower() == "asc" else "DESC"
    col_map = {
        "start_time": "start_time",
        "end_time": "end_time",
        "duration": "duration_seconds",
        "lag": "schedule_lag_seconds",
        "status": "status",
        "retries": "retry_count",
        "trigger": "trigger_type",
        "run_type": "run_type",
        "tasks": "tasks_failed",
        "run_id": "run_id",
    }
    col = col_map.get(sort, "start_time")
    return f"ORDER BY {col} {order_dir} NULLS LAST, start_time DESC NULLS LAST, run_id DESC"


async def fetch_lakeflow_job_runs(
    db: DatabricksWarehousePool,
    settings: Settings,
    scope: AllowedScope,
    workflow_id: str,
    *,
    window: str = "30d",
    start_date: date | None = None,
    end_date: date | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    workspace_ids: list[str] | None = None,
    search: str | None = None,
    status: list[str] | None = None,
    trigger_type: list[str] | None = None,
    with_retries: bool = False,
    column_filter: list[str] | None = None,
    sort: str = "start_time",
    order: str = "desc",
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
    matrix_limit: int = _MATRIX_RUNS_N,
) -> dict[str, Any]:
    """N2 — runs table + matrix cells for last N runs."""
    # Parsed first: everything below soft-fails to an empty page, so a refused filter
    # would otherwise be answered as "this job has no run".
    # ``search`` does not fold — here it matches the run id, which no column filters —
    # and neither does ``with_retries``: it is ``> 0``, where the ``retries`` column
    # takes a threshold.
    column_filters = parse_column_filters(
        "lakeflow-job-runs",
        column_filter,
        status=status,
        trigger_type=trigger_type,
    )
    window_key, start, end = _resolve_period(window, start_date, end_date)
    page = max(1, page)
    page_size = min(max(1, page_size), _MAX_PAGE_SIZE)
    offset = (page - 1) * page_size
    workspace_ids = narrow_workspace_ids(
        workspace_ids,
        await resolve_request_lz_workspace_ids(
            db, settings, source_lz_id=source_lz_id, source_lz_ids=source_lz_ids
        ),
    )
    runs_t = qualified_table(settings, _RUNS)
    tasks_t = qualified_table(settings, _TASKS)
    health_t = qualified_table(settings, _TASK_HEALTH)

    conditions, params = _scope_where(
        scope, source_lz_id, source_lz_ids, workspace_ids
    )
    conditions.append("workflow_id = ?")
    params.append(workflow_id)
    where, params = _date_where(conditions, params, start, end, date_col="execution_date")
    if status:
        placeholders = ", ".join("?" for _ in status)
        status_clause = f"LOWER(status) IN ({placeholders})"
        where = f"{where} AND {status_clause}" if where else f"WHERE {status_clause}"
        params.extend([s.lower() for s in status])
    if trigger_type:
        placeholders = ", ".join("?" for _ in trigger_type)
        where = f"{where} AND trigger_type IN ({placeholders})"
        params.extend(trigger_type)
    if search:
        pattern = f"%{search.strip().lower()}%"
        where = f"{where} AND LOWER(CAST(run_id AS STRING)) LIKE ?"
        params.append(pattern)
    if with_retries:
        where = f"{where} AND COALESCE(retry_count, 0) > 0"
    column_clauses, column_params = column_filter_predicates(column_filters)
    for clause in column_clauses:
        where = f"{where} AND {clause}" if where else f"WHERE {clause}"
    params.extend(column_params)

    order_sql = _runs_sort_clause(sort, order)

    as_of = await _safe(
        fetch_lakeflow_as_of(
            db, settings, scope, source_lz_id, source_lz_ids, workspace_ids
        ),
        None,
        "job-runs-as-of",
    )

    try:
        total_row = await db.fetchone(
            f"SELECT COUNT(*) AS n FROM {runs_t} {where}", *params
        )
        total = int((total_row or {}).get("n") or 0)
        run_rows = await db.fetchall(
            f"""
            SELECT
                run_id, workflow_id, workspace_id, cloud_provider, account_id, workspace_name,
                status, trigger_type, run_type, start_time, end_time,
                duration_seconds, queued_duration_seconds, execution_duration_seconds,
                schedule_lag_seconds, retry_count, tasks_total, tasks_failed,
                task_failure_rate, creator_user_name, cluster_instance_id,
                run_page_url, error_message, execution_date
            FROM {runs_t}
            {where}
            {order_sql}
            LIMIT ? OFFSET ?
            """,
            *params,
            page_size,
            offset,
        )
    except Exception:
        logger.exception("lakeflow job runs soft-fail")
        return {
            "items": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "matrix": {"runs": [], "task_keys": [], "cells": []},
            "task_health": [],
            "as_of": as_of,
            "window": {"key": window_key, "from": start.isoformat(), "to": end.isoformat()},
        }

    items = [_row_to_run(r) for r in run_rows]
    matrix_runs = items[: max(1, min(matrix_limit, len(items)))]
    matrix_run_ids = [r["run_id"] for r in matrix_runs if r.get("run_id")]

    matrix = await _safe(
        _fetch_matrix(
            db,
            tasks_t,
            scope,
            source_lz_id,
            source_lz_ids,
            workspace_ids,
            workflow_id,
            matrix_run_ids,
        ),
        {"runs": matrix_runs, "task_keys": [], "cells": []},
        "jobs-matrix",
    )
    if not matrix.get("runs"):
        matrix["runs"] = matrix_runs

    task_health = await _safe(
        _fetch_task_health(
            db,
            health_t,
            scope,
            source_lz_id,
            source_lz_ids,
            workspace_ids,
            workflow_id,
            start,
            end,
        ),
        [],
        "task-health",
    )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "matrix": matrix,
        "task_health": task_health,
        "as_of": as_of,
        "window": {"key": window_key, "from": start.isoformat(), "to": end.isoformat()},
    }


async def fetch_lakeflow_run_tasks(
    db: DatabricksWarehousePool,
    settings: Settings,
    scope: AllowedScope,
    workflow_id: str,
    run_id: str,
    *,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    workspace_ids: list[str] | None = None,
    failed_only: bool = False,
) -> dict[str, Any]:
    """N3 — tasks for one run (+ parent run header if available)."""
    workspace_ids = narrow_workspace_ids(
        workspace_ids,
        await resolve_request_lz_workspace_ids(
            db, settings, source_lz_id=source_lz_id, source_lz_ids=source_lz_ids
        ),
    )
    runs_t = qualified_table(settings, _RUNS)
    tasks_t = qualified_table(settings, _TASKS)

    conditions, params = _scope_where(
        scope, source_lz_id, source_lz_ids, workspace_ids
    )
    conditions.append("workflow_id = ?")
    params.append(workflow_id)
    conditions.append("run_id = ?")
    params.append(run_id)
    where = "WHERE " + " AND ".join(conditions)

    run_row = await _safe(
        db.fetchone(
            f"""
            SELECT
                run_id, workflow_id, workspace_id, cloud_provider, account_id, workspace_name,
                status, trigger_type, run_type, start_time, end_time,
                duration_seconds, queued_duration_seconds, execution_duration_seconds,
                schedule_lag_seconds, retry_count, tasks_total, tasks_failed,
                cluster_instance_id, run_page_url, error_message
            FROM {runs_t}
            {where}
            LIMIT 1
            """,
            *params,
        ),
        None,
        "run-header",
    )

    task_conditions = list(conditions)
    task_params = list(params)
    if failed_only:
        task_conditions.append("LOWER(status) IN ('failed', 'timed_out')")
    task_where = "WHERE " + " AND ".join(task_conditions)

    try:
        task_rows = await db.fetchall(
            f"""
            SELECT
                run_id, task_id, task_key, execution_date, status,
                start_time, end_time, duration_seconds, attempt_number,
                cluster_instance_id, error_message
            FROM {tasks_t}
            {task_where}
            ORDER BY start_time ASC NULLS LAST, task_key ASC
            """,
            *task_params,
        )
    except Exception:
        logger.exception("lakeflow run tasks soft-fail")
        task_rows = []

    return {
        "run": _row_to_run(run_row) if run_row else None,
        "items": [_row_to_task(r) for r in task_rows],
        "total": len(task_rows),
        "as_of": await _safe(
            fetch_lakeflow_as_of(
                db, settings, scope, source_lz_id, source_lz_ids, workspace_ids
            ),
            None,
            "run-tasks-as-of",
        ),
    }


# ── Internals ────────────────────────────────────────────────────────────────


async def _query_jobs_page(
    db: DatabricksWarehousePool,
    success_t: str,
    pct_t: str,
    drift_t: str,
    task_t: str,
    runs_t: str,
    cost_t: str,
    scope: AllowedScope,
    *,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    workspace_ids: list[str] | None,
    start: date,
    end: date,
    status: list[str] | None = None,
    trigger_type: list[str] | None = None,
    owner: list[str] | None = None,
    drift_only: bool = False,
    no_runs: bool = False,
    with_retries: bool = False,
    column_filters: list[AppliedFilter] | None = None,
    workflow_id: str | None = None,
    sort: str = "problems",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int, float | None, int]:
    scope_c, scope_p = _scope_where(
        scope, source_lz_id, source_lz_ids, workspace_ids
    )
    date_c = list(scope_c)
    date_p = list(scope_p)
    date_c.append("execution_date >= ?")
    date_p.append(start)
    date_c.append("execution_date <= ?")
    date_p.append(end)
    if workflow_id:
        date_c.append("workflow_id = ?")
        date_p.append(workflow_id)
    base_where = " AND ".join(date_c) if date_c else "1=1"
    runs_where = base_where.replace("execution_date", "CAST(start_time AS DATE)")
    # gold_dbx_compute_job_cluster_cost_daily has no cloud_provider/account_id
    # columns (only workspace_id + job_id), but the scope/date filters that
    # matter — workspace scope, date range, and workflow_id when set — carry
    # over unchanged: same param count and order as base_where, just aimed at
    # this table's own column names.
    cost_where = base_where.replace("execution_date", "period_start").replace(
        "workflow_id", "job_id"
    )
    # Safe date literals (server-resolved dates, not raw user strings).
    end_lit = end.isoformat()
    start_7d_lit = (end - timedelta(days=6)).isoformat()

    # Last-run scan when filters/sort/detail need it; otherwise history fills display.
    sort_needs_last = sort in {
        "last_run",
        "problems",
        "status",
        "trigger",
        "run_type",
        "last_duration",
    }
    # A column filter on ``status``, ``trigger``, ``run_type`` or ``last_duration``
    # forces the scan too: without the CTE those columns are ``CAST(NULL AS …)``
    # literals, so the predicate would compare against NULL and page over zero rows —
    # a wrong answer rather than an error.
    filters_need_last_run = needs_last_run(column_filters or [])
    need_last_run = bool(
        status
        or trigger_type
        or owner
        or workflow_id
        or sort_needs_last
        or filters_need_last_run
    )
    # Default list sort "problems" can skip last_start_time (fail_score + drift only).
    if sort == "problems" and not (
        status or trigger_type or owner or workflow_id or filters_need_last_run
    ):
        need_last_run = False

    cte_count = 5
    lr_cte = ""
    lr_select = """
        CAST(NULL AS STRING) AS last_status,
        CAST(NULL AS TIMESTAMP) AS last_start_time,
        CAST(NULL AS TIMESTAMP) AS last_end_time,
        CAST(NULL AS STRING) AS last_trigger_type,
        CAST(NULL AS STRING) AS last_run_type,
        CAST(NULL AS DOUBLE) AS last_duration_seconds,
        CAST(NULL AS STRING) AS last_owner,
        CAST(NULL AS STRING) AS workspace_name,
        CAST(NULL AS STRING) AS last_run_page_url,
    """
    lr_join = ""
    if need_last_run:
        cte_count = 6
        # max_by is cheaper than ROW_NUMBER()…WHERE rn = 1 over the full runs window.
        lr_cte = f"""
    , lr AS (
      SELECT cloud_provider, account_id, workspace_id, workflow_id,
             max_by(status, start_time) AS last_status,
             max(start_time) AS last_start_time,
             max_by(end_time, start_time) AS last_end_time,
             max_by(trigger_type, start_time) AS last_trigger_type,
             max_by(run_type, start_time) AS last_run_type,
             max_by(duration_seconds, start_time) AS last_duration_seconds,
             max_by(creator_user_name, start_time) AS last_owner,
             max_by(workspace_name, start_time) AS workspace_name,
             max_by(run_page_url, start_time) AS last_run_page_url
      FROM {runs_t}
      WHERE {runs_where}
      GROUP BY cloud_provider, account_id, workspace_id, workflow_id
    )
        """
        lr_select = """
        lr.last_status, lr.last_start_time, lr.last_end_time, lr.last_trigger_type,
        lr.last_run_type, lr.last_duration_seconds, lr.last_owner,
        lr.workspace_name, lr.last_run_page_url,
        """
        lr_join = "LEFT JOIN lr USING (cloud_provider, account_id, workspace_id, workflow_id)"

    sql = f"""
    WITH sr AS (
      SELECT cloud_provider, account_id, workspace_id, workflow_id,
             ANY_VALUE(workflow_name) AS workflow_name,
             SUM(terminal_runs)  AS terminal_runs,
             SUM(succeeded_runs) AS succeeded_runs,
             SUM(failed_runs)    AS failed_runs,
             SUM(timed_out_runs) AS timed_out_runs,
             SUM(cancelled_runs) AS cancelled_runs,
             SUM(CASE WHEN execution_date = DATE '{end_lit}'
                      THEN succeeded_runs ELSE 0 END) AS succeeded_24h,
             SUM(CASE WHEN execution_date = DATE '{end_lit}'
                      THEN terminal_runs ELSE 0 END) AS terminal_24h,
             SUM(CASE WHEN execution_date >= DATE '{start_7d_lit}'
                      THEN succeeded_runs ELSE 0 END) AS succeeded_7d,
             SUM(CASE WHEN execution_date >= DATE '{start_7d_lit}'
                      THEN terminal_runs ELSE 0 END) AS terminal_7d
      FROM {success_t}
      WHERE {base_where}
      GROUP BY cloud_provider, account_id, workspace_id, workflow_id
    ),
    dp AS (
      SELECT cloud_provider, account_id, workspace_id, workflow_id,
             SUM(avg_duration_seconds * total_runs)
               / NULLIF(SUM(total_runs), 0) AS avg_duration_seconds,
             MAX(p50_duration_seconds) AS p50,
             MAX(p95_duration_seconds) AS p95,
             MAX(p99_duration_seconds) AS p99,
             SUM(avg_queued_duration_seconds * total_runs)
               / NULLIF(
                 SUM(
                   CASE
                     WHEN avg_queued_duration_seconds IS NOT NULL THEN total_runs
                     ELSE 0
                   END
                 ),
                 0
               ) AS avg_queued_duration_seconds,
             SUM(avg_schedule_lag_seconds * total_runs)
               / NULLIF(
                 SUM(
                   CASE
                     WHEN avg_schedule_lag_seconds IS NOT NULL THEN total_runs
                     ELSE 0
                   END
                 ),
                 0
               ) AS avg_schedule_lag_seconds,
             SUM(avg_retry_count * total_runs)
               / NULLIF(SUM(total_runs), 0) AS avg_retry_count
      FROM {pct_t}
      WHERE {base_where}
      GROUP BY cloud_provider, account_id, workspace_id, workflow_id
    ),
    dd AS (
      SELECT cloud_provider, account_id, workspace_id, workflow_id, duration_drift_pct, baseline_avg_14d
      FROM (
        SELECT cloud_provider, account_id, workspace_id, workflow_id, duration_drift_pct, baseline_avg_14d,
               ROW_NUMBER() OVER (
                 PARTITION BY cloud_provider, account_id, workspace_id, workflow_id
                 ORDER BY execution_date DESC
               ) rn
        FROM {drift_t}
        WHERE {base_where}
      ) WHERE rn = 1
    ),
    tf AS (
      SELECT cloud_provider, account_id, workspace_id, workflow_id,
             SUM(tasks_failed) AS tasks_failed, SUM(tasks_total) AS tasks_total
      FROM {task_t}
      WHERE {base_where}
      GROUP BY cloud_provider, account_id, workspace_id, workflow_id
    ),
    cc AS (
      -- job_id only covers clusters of type JOB (DCINT-294): a workflow that
      -- only ever runs on interactive/serverless compute has no row here, so
      -- execution_cost_usd stays NULL rather than defaulting to 0.
      SELECT workspace_id, job_id AS workflow_id,
             SUM(cost_usd) AS execution_cost_usd
      FROM {cost_t}
      WHERE {cost_where}
      GROUP BY workspace_id, job_id
    )
    {lr_cte}
    , joined AS (
      SELECT
        sr.cloud_provider, sr.account_id, sr.workspace_id, sr.workflow_id, sr.workflow_name,
        sr.terminal_runs, sr.succeeded_runs, sr.failed_runs, sr.timed_out_runs, sr.cancelled_runs,
        CASE WHEN sr.terminal_runs > 0
             THEN ROUND(100.0 * sr.succeeded_runs / sr.terminal_runs, 1) END AS success_rate_pct,
        CASE WHEN sr.terminal_24h > 0
             THEN ROUND(100.0 * sr.succeeded_24h / sr.terminal_24h, 1) END AS success_rate_24h_pct,
        CASE WHEN sr.terminal_7d > 0
             THEN ROUND(100.0 * sr.succeeded_7d / sr.terminal_7d, 1) END AS success_rate_7d_pct,
        sr.terminal_24h AS success_rate_24h_n,
        sr.terminal_7d AS success_rate_7d_n,
        dp.avg_duration_seconds, dp.p50, dp.p95, dp.p99, dp.avg_queued_duration_seconds,
        dp.avg_schedule_lag_seconds, dp.avg_retry_count,
        dd.duration_drift_pct, dd.baseline_avg_14d,
        CASE WHEN tf.tasks_total > 0
             THEN ROUND(100.0 * tf.tasks_failed / tf.tasks_total, 1) END AS task_failure_rate_pct,
        tf.tasks_failed, tf.tasks_total,
        cc.execution_cost_usd,
        {lr_select}
        COALESCE(sr.failed_runs, 0) + COALESCE(sr.timed_out_runs, 0) AS fail_score
      FROM sr
      LEFT JOIN dp USING (cloud_provider, account_id, workspace_id, workflow_id)
      LEFT JOIN dd USING (cloud_provider, account_id, workspace_id, workflow_id)
      LEFT JOIN tf USING (cloud_provider, account_id, workspace_id, workflow_id)
      LEFT JOIN cc ON cc.workspace_id = sr.workspace_id AND cc.workflow_id = sr.workflow_id
      {lr_join}
    )
    SELECT * FROM joined WHERE 1=1
    """
    params = list(date_p) * cte_count
    # ``search`` is now the ``alpha`` column of the allowlist — same predicate, and the
    # pattern gains the ``strip()`` every other view already applied.
    filters, column_params = column_filter_predicates(column_filters or [])
    params.extend(column_params)

    if status:
        placeholders = ", ".join("?" for _ in status)
        filters.append(f"LOWER(last_status) IN ({placeholders})")
        params.extend([s.lower() for s in status])
    if trigger_type:
        placeholders = ", ".join("?" for _ in trigger_type)
        filters.append(f"last_trigger_type IN ({placeholders})")
        params.extend(trigger_type)
    if owner:
        placeholders = ", ".join("?" for _ in owner)
        filters.append(f"last_owner IN ({placeholders})")
        params.extend(owner)
    if drift_only:
        filters.append("duration_drift_pct > 20")
    if no_runs:
        filters.append("COALESCE(terminal_runs, 0) = 0")
    if with_retries:
        filters.append("COALESCE(avg_retry_count, 0) > 0")

    if filters:
        sql += " AND " + " AND ".join(filters)

    # Frontend may send "name" — treat as alpha.
    sort_key = "alpha" if sort in {"alpha", "name"} else sort
    order_dir = "DESC" if order.lower() != "asc" else "ASC"
    if sort_key == "alpha":
        order_sql = (
            "ORDER BY LOWER(COALESCE(workflow_name, CAST(workflow_id AS STRING))) "
            f"{order_dir}"
        )
    elif sort_key == "success":
        order_sql = f"ORDER BY success_rate_pct {order_dir} NULLS LAST"
    elif sort_key == "success_24h":
        order_sql = f"ORDER BY success_rate_24h_pct {order_dir} NULLS LAST"
    elif sort_key == "success_7d":
        order_sql = f"ORDER BY success_rate_7d_pct {order_dir} NULLS LAST"
    elif sort_key == "duration":
        order_sql = f"ORDER BY avg_duration_seconds {order_dir} NULLS LAST"
    elif sort_key == "drift":
        order_sql = f"ORDER BY duration_drift_pct {order_dir} NULLS LAST"
    elif sort_key == "p50":
        order_sql = f"ORDER BY p50 {order_dir} NULLS LAST"
    elif sort_key == "p95":
        order_sql = f"ORDER BY p95 {order_dir} NULLS LAST"
    elif sort_key == "p99":
        order_sql = f"ORDER BY p99 {order_dir} NULLS LAST"
    elif sort_key == "runs":
        order_sql = f"ORDER BY terminal_runs {order_dir} NULLS LAST"
    elif sort_key == "retries":
        order_sql = f"ORDER BY avg_retry_count {order_dir} NULLS LAST"
    elif sort_key == "wait":
        order_sql = (
            "ORDER BY (COALESCE(avg_queued_duration_seconds, 0) + "
            f"COALESCE(avg_schedule_lag_seconds, 0)) {order_dir}"
        )
    elif sort_key == "status":
        order_sql = f"ORDER BY LOWER(COALESCE(last_status, '')) {order_dir}"
    elif sort_key == "trigger":
        order_sql = f"ORDER BY LOWER(COALESCE(last_trigger_type, '')) {order_dir}"
    elif sort_key == "run_type":
        order_sql = f"ORDER BY LOWER(COALESCE(last_run_type, '')) {order_dir}"
    elif sort_key == "last_duration":
        order_sql = f"ORDER BY last_duration_seconds {order_dir} NULLS LAST"
    elif sort_key == "last_run":
        order_sql = f"ORDER BY last_start_time {order_dir} NULLS LAST"
    else:
        # problems first — recency only when last_run CTE is present
        if need_last_run:
            order_sql = """
            ORDER BY
              CASE
                WHEN fail_score > 0 THEN 0
                WHEN COALESCE(duration_drift_pct, 0) > 20 THEN 1
                ELSE 2
              END ASC,
              fail_score DESC,
              COALESCE(duration_drift_pct, 0) DESC,
              last_start_time DESC NULLS LAST
            """
        else:
            order_sql = """
            ORDER BY
              CASE
                WHEN fail_score > 0 THEN 0
                WHEN COALESCE(duration_drift_pct, 0) > 20 THEN 1
                ELSE 2
              END ASC,
              fail_score DESC,
              COALESCE(duration_drift_pct, 0) DESC,
              workflow_name ASC NULLS LAST
            """

    # One warehouse round-trip: page rows + total via window count
    page_sql = f"""
    SELECT * FROM (
      SELECT filtered.*, COUNT(*) OVER() AS _total
      FROM (
        {sql}
      ) filtered
      {order_sql}
    ) paged
    LIMIT ? OFFSET ?
    """
    # Total execution cost across every job matching the filter, not just the
    # current page — same filtered set as page_sql (sql + params), reused
    # verbatim so the widget total and the list agree on what "filtered" means.
    cost_summary_sql = f"""
    SELECT SUM(execution_cost_usd) AS total_cost_usd,
           COUNT(execution_cost_usd) AS jobs_with_cost
    FROM ({sql}) t
    """
    rows, cost_row = await asyncio.gather(
        db.fetchall(page_sql, *params, limit, offset),
        db.fetchone(cost_summary_sql, *params),
    )
    total_cost_usd = (cost_row or {}).get("total_cost_usd")
    total_cost_usd = round(float(total_cost_usd), 2) if total_cost_usd is not None else None
    jobs_with_cost = int((cost_row or {}).get("jobs_with_cost") or 0)
    if not rows:
        return [], 0, total_cost_usd, jobs_with_cost
    total = int(rows[0].get("_total") or 0)
    for row in rows:
        row.pop("_total", None)
    return rows, total, total_cost_usd, jobs_with_cost


async def _fetch_history_for_page(
    db: DatabricksWarehousePool,
    runs_t: str,
    scope: AllowedScope,
    *,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    workspace_ids: list[str] | None,
    workflow_ids: list[str],
    start: date,
    end: date,
) -> dict[str, list[dict[str, Any]]]:
    conditions, params = _scope_where(
        scope, source_lz_id, source_lz_ids, workspace_ids
    )
    placeholders = ", ".join("?" for _ in workflow_ids)
    conditions.append(f"workflow_id IN ({placeholders})")
    params.extend(workflow_ids)
    where, params = _date_where(conditions, params, start, end)

    rows = await db.fetchall(
        f"""
        SELECT workflow_id, run_id, status, duration_seconds, start_time, end_time, retry_count,
               trigger_type, run_type, creator_user_name, workspace_name, run_page_url
        FROM (
          SELECT workflow_id, run_id, status, duration_seconds, start_time, end_time, retry_count,
                 trigger_type, run_type, creator_user_name, workspace_name, run_page_url,
                 ROW_NUMBER() OVER (PARTITION BY workflow_id ORDER BY start_time DESC NULLS LAST) rn
          FROM {runs_t}
          {where}
        ) WHERE rn <= {_HISTORY_N}
        ORDER BY workflow_id, start_time DESC NULLS LAST
        """,
        *params,
    )
    out: dict[str, list[dict[str, Any]]] = {wid: [] for wid in workflow_ids}
    for r in rows:
        wid = str(r["workflow_id"])
        out.setdefault(wid, []).append(
            {
                "run_id": str(r["run_id"]),
                "status": (r.get("status") or "").lower() or None,
                "duration_seconds": r.get("duration_seconds"),
                "start_time": _iso(r.get("start_time")),
                "end_time": _iso(r.get("end_time")),
                "retry_count": r.get("retry_count"),
                "trigger_type": r.get("trigger_type"),
                "run_type": r.get("run_type"),
                "creator_user_name": r.get("creator_user_name"),
                "workspace_name": r.get("workspace_name"),
                "run_page_url": r.get("run_page_url"),
            }
        )
    return out


async def _fetch_matrix(
    db: DatabricksWarehousePool,
    tasks_t: str,
    scope: AllowedScope,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    workspace_ids: list[str] | None,
    workflow_id: str,
    run_ids: list[str],
) -> dict[str, Any]:
    if not run_ids:
        return {"runs": [], "task_keys": [], "cells": []}
    conditions, params = _scope_where(
        scope, source_lz_id, source_lz_ids, workspace_ids
    )
    conditions.append("workflow_id = ?")
    params.append(workflow_id)
    placeholders = ", ".join("?" for _ in run_ids)
    conditions.append(f"run_id IN ({placeholders})")
    params.extend(run_ids)
    where = "WHERE " + " AND ".join(conditions)

    rows = await db.fetchall(
        f"""
        SELECT run_id, task_key, status, duration_seconds
        FROM {tasks_t}
        {where}
        """,
        *params,
    )
    task_keys = sorted({str(r["task_key"]) for r in rows if r.get("task_key")})
    cells = [
        {
            "run_id": str(r["run_id"]),
            "task_key": str(r["task_key"]),
            "status": (r.get("status") or "").lower() or None,
            "duration_seconds": r.get("duration_seconds"),
        }
        for r in rows
    ]
    return {"runs": [], "task_keys": task_keys, "cells": cells}


async def _fetch_task_health(
    db: DatabricksWarehousePool,
    health_t: str,
    scope: AllowedScope,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    workspace_ids: list[str] | None,
    workflow_id: str,
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    conditions, params = _scope_where(
        scope, source_lz_id, source_lz_ids, workspace_ids
    )
    conditions.append("workflow_id = ?")
    params.append(workflow_id)
    where, params = _date_where(conditions, params, start, end)
    rows = await db.fetchall(
        f"""
        SELECT task_key,
               AVG(task_failure_rate_pct) AS task_failure_rate_pct,
               MAX(p95_task_duration_seconds) AS p95_task_duration_seconds
        FROM {health_t}
        {where}
        GROUP BY task_key
        ORDER BY task_failure_rate_pct DESC NULLS LAST
        """,
        *params,
    )
    return [
        {
            "task_key": str(r["task_key"]),
            "task_failure_rate_pct": r.get("task_failure_rate_pct"),
            "p95_task_duration_seconds": r.get("p95_task_duration_seconds"),
        }
        for r in rows
    ]


def _row_to_job_list_item(row: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
    terminal = int(row.get("terminal_runs") or 0)
    latest = history[0] if history else None
    last_status = (row.get("last_status") or "").lower() or None
    last_start = _iso(row.get("last_start_time"))
    last_end = _iso(row.get("last_end_time"))
    last_trigger = row.get("last_trigger_type")
    last_run_type = row.get("last_run_type")
    last_duration = row.get("last_duration_seconds")
    owner = row.get("last_owner")
    workspace_name = row.get("workspace_name")
    last_run_page_url = row.get("last_run_page_url")
    if latest:
        last_status = last_status or (latest.get("status") or None)
        last_start = last_start or latest.get("start_time")
        last_end = last_end or latest.get("end_time")
        last_trigger = last_trigger or latest.get("trigger_type")
        last_run_type = last_run_type or latest.get("run_type")
        last_duration = (
            last_duration if last_duration is not None else latest.get("duration_seconds")
        )
        owner = owner or latest.get("creator_user_name")
        workspace_name = workspace_name or latest.get("workspace_name")
        last_run_page_url = last_run_page_url or latest.get("run_page_url")
    # history payload for UI bars (strip enrichment-only fields)
    history_bars = [
        {
            "run_id": h["run_id"],
            "status": h.get("status"),
            "duration_seconds": h.get("duration_seconds"),
            "start_time": h.get("start_time"),
            "retry_count": h.get("retry_count"),
        }
        for h in history
    ]
    return {
        "workflow_id": str(row["workflow_id"]),
        "workflow_name": row.get("workflow_name") or str(row["workflow_id"]),
        "source_lz_id": None,
        "account_id": row.get("account_id"),
        "cloud_provider": row.get("cloud_provider"),
        "workspace_id": str(row["workspace_id"]) if row.get("workspace_id") is not None else None,
        "workspace_name": workspace_name,
        "last_status": last_status,
        "last_start_time": last_start,
        "last_end_time": last_end,
        "last_trigger_type": last_trigger,
        "last_run_type": last_run_type,
        "last_duration_seconds": last_duration,
        "owner": owner,
        "last_run_page_url": last_run_page_url,
        "terminal_runs": terminal,
        "succeeded_runs": int(row.get("succeeded_runs") or 0),
        "failed_runs": int(row.get("failed_runs") or 0),
        "timed_out_runs": int(row.get("timed_out_runs") or 0),
        "cancelled_runs": int(row.get("cancelled_runs") or 0),
        "success_rate_pct": row.get("success_rate_pct"),
        "success_rate_24h_pct": row.get("success_rate_24h_pct"),
        "success_rate_24h_n": int(row.get("success_rate_24h_n") or 0),
        "success_rate_7d_pct": row.get("success_rate_7d_pct"),
        "success_rate_7d_n": int(row.get("success_rate_7d_n") or 0),
        "avg_duration_seconds": row.get("avg_duration_seconds"),
        "duration_drift_pct": row.get("duration_drift_pct"),
        "baseline_avg_14d": row.get("baseline_avg_14d"),
        "p50": row.get("p50"),
        "p95": row.get("p95"),
        "p99": row.get("p99"),
        "avg_queued_duration_seconds": row.get("avg_queued_duration_seconds"),
        "avg_schedule_lag_seconds": row.get("avg_schedule_lag_seconds"),
        "avg_retry_count": row.get("avg_retry_count"),
        "task_failure_rate_pct": row.get("task_failure_rate_pct"),
        "execution_cost_usd": (
            round(float(row["execution_cost_usd"]), 2)
            if row.get("execution_cost_usd") is not None
            else None
        ),
        "history": history_bars,
        "has_runs": terminal > 0 or bool(history),
    }



def _row_to_run(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(row["run_id"]),
        "workflow_id": str(row["workflow_id"]) if row.get("workflow_id") is not None else None,
        "workspace_id": str(row["workspace_id"]) if row.get("workspace_id") is not None else None,
        "source_lz_id": None,
        "account_id": row.get("account_id"),
        "cloud_provider": row.get("cloud_provider"),
        "workspace_name": row.get("workspace_name"),
        "status": (row.get("status") or "").lower() or None,
        "trigger_type": row.get("trigger_type"),
        "run_type": row.get("run_type"),
        "start_time": _iso(row.get("start_time")),
        "end_time": _iso(row.get("end_time")),
        "duration_seconds": row.get("duration_seconds"),
        "queued_duration_seconds": row.get("queued_duration_seconds"),
        "execution_duration_seconds": row.get("execution_duration_seconds"),
        "schedule_lag_seconds": row.get("schedule_lag_seconds"),
        "retry_count": row.get("retry_count"),
        "tasks_total": row.get("tasks_total"),
        "tasks_failed": row.get("tasks_failed"),
        "task_failure_rate": row.get("task_failure_rate"),
        "creator_user_name": row.get("creator_user_name"),
        "cluster_instance_id": row.get("cluster_instance_id"),
        "run_page_url": row.get("run_page_url"),
        "error_message": row.get("error_message"),
        "execution_date": _iso(row.get("execution_date")),
    }


def _row_to_task(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": str(row["run_id"]),
        "task_id": str(row["task_id"]) if row.get("task_id") is not None else None,
        "task_key": row.get("task_key"),
        "status": (row.get("status") or "").lower() or None,
        "start_time": _iso(row.get("start_time")),
        "end_time": _iso(row.get("end_time")),
        "duration_seconds": row.get("duration_seconds"),
        "attempt_number": row.get("attempt_number"),
        "cluster_instance_id": row.get("cluster_instance_id"),
        "error_message": row.get("error_message"),
        "execution_date": _iso(row.get("execution_date")),
    }
