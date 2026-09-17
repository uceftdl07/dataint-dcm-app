"""Lakeflow Overview — aggregated KPIs from Unity Catalog gold tables.

Gold sources (never AVG of pre-computed %):
  gold_dbx_workflow_success_rate
  gold_dbx_workflow_duration_percentiles
  gold_dbx_workflow_duration_drift
  gold_dbx_workflow_task_failure_rate
  gold_dbx_workflow_concurrency_1min
  gold_dbx_workflow_runs  (recent failures only)

Window: today | 7d | 30d (default today), or explicit start_date/end_date
from the global header (overrides window). Soft-fail per table.

Perf notes:
  - One success-rate scan covers activity + reliability date buckets
  - Short in-memory response cache (30s)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ...auth.scope_model import (
    AllowedScope,
    add_scope_filter,
    canonical_workspace_id,
    canonical_workspace_sql,
)
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

__all__ = ["fetch_lakeflow_as_of", "fetch_lakeflow_overview"]

logger = logging.getLogger(__name__)

_SUCCESS = "gold_dbx_workflow_success_rate"
_PERCENTILES = "gold_dbx_workflow_duration_percentiles"
_DRIFT = "gold_dbx_workflow_duration_drift"
_TASK_FAIL = "gold_dbx_workflow_task_failure_rate"
_CONCURRENCY = "gold_dbx_workflow_concurrency_1min"
_RUNS = "gold_dbx_workflow_runs"

# Freshness source for the ``as_of`` field: the curated lakeflow run timeline
# feeding every ``gold_dbx_workflow_*`` table. The socle envelope timestamp is
# written by ``enrich_with_envelope`` as ``collected_at`` (the contract calls it
# ``_ingested_at`` — a documentation shorthand; the real column is this one).
_LAKEFLOW_RUN_TIMELINE = "curated_dbx_lakeflow_job_run_timeline"
_FRESHNESS_COLUMN = "collected_at"

_OVERVIEW_CACHE_TTL_SECONDS = 30.0


async def fetch_lakeflow_as_of(
    db: DatabricksWarehousePool,
    settings: Settings,
    scope: AllowedScope,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    workspace_ids: list[str] | None = None,
) -> str | None:
    """Return the real ingestion freshness as an ISO 8601 string, or ``None``.

    Value = ``MAX(collected_at)`` over the curated lakeflow run timeline that
    sources the gold workflow tables. RBAC-scoped like every other lakeflow query
    (a project member must never learn the freshness of workspaces outside their
    grant): the same :func:`_scope_where` clause bounds the rows. Never a
    constant — the caller falls back only when this table is missing/empty.
    """
    conditions, params = _scope_where(
        scope, source_lz_id, source_lz_ids, workspace_ids
    )
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    table = qualified_table(settings, _LAKEFLOW_RUN_TIMELINE)
    row = await db.fetchone(
        f"SELECT MAX({_FRESHNESS_COLUMN}) AS as_of FROM {table} {where}",
        *params,
    )
    value = (row or {}).get("as_of")
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)

_WINDOW_DAYS: dict[str, int | None] = {
    "today": 0,
    "7d": 7,
    "30d": 30,
}


def _resolve_window(window: str) -> tuple[date, date]:
    today = datetime.now(UTC).date()
    days = _WINDOW_DAYS.get(window, 0)
    if days == 0:
        return today, today
    return today - timedelta(days=days - 1), today


def _resolve_period(
    window: str,
    start_date: date | None,
    end_date: date | None,
) -> tuple[str, date, date]:
    """Prefer explicit header dates; otherwise resolve named window presets."""
    if start_date is not None and end_date is not None:
        if end_date < start_date:
            start_date, end_date = end_date, start_date
        return "custom", start_date, end_date
    if window not in _WINDOW_DAYS:
        window = "today"
    start, end = _resolve_window(window)
    return window, start, end


def _previous_window(start: date, end: date) -> tuple[date, date]:
    span = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=span - 1)
    return prev_start, prev_end


def _scope_where(
    scope: AllowedScope,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    workspace_ids: list[str] | None,
) -> tuple[list[str], list[Any]]:
    """RBAC scope ANDed with the workspace filter the client asked for.

    Every ``gold_dbx_workflow_*`` table comes from the ``system.lakeflow`` path:
    its grain is (cloud_provider, account_id, workspace_id) and it carries **no**
    ``source_lz_id``. The workspace is therefore the only dimension that can scope
    these rows, which is why ``lz_column=None`` is passed rather than the LZ
    dimension being ignored — a project that grants no workspace gets ``1 = 0``
    here instead of every workspace of the platform.

    ``source_lz_id`` / ``source_lz_ids`` are the *request* LZ filters coming from
    the global header. They cannot be pushed down on a table without the column;
    narrowing on them would require resolving LZ → workspaces first (see
    ``get_allowed_scope``), so they are deliberately not applied.
    """
    conditions: list[str] = []
    params: list[Any] = []
    add_scope_filter(conditions, params, scope, lz_column=None)
    _ = (source_lz_id, source_lz_ids)
    # None = no workspace filter; [] = explicitly empty selection → no rows.
    # ANDed with the RBAC clause above, so a request can only ever narrow.
    if workspace_ids is not None:
        if not workspace_ids:
            conditions.append("1 = 0")
        else:
            canonical = [canonical_workspace_id(wid) for wid in workspace_ids]
            canonical = [wid for wid in canonical if wid]
            if not canonical:
                conditions.append("1 = 0")
            else:
                placeholders = ", ".join("?" for _ in canonical)
                column = canonical_workspace_sql("workspace_id")
                conditions.append(f"{column} IN ({placeholders})")
                params.extend(canonical)
    return conditions, params


def _date_where(
    conditions: list[str],
    params: list[Any],
    start: date,
    end: date,
    *,
    date_col: str = "execution_date",
) -> tuple[str, list[Any]]:
    c = list(conditions)
    p = list(params)
    c.append(f"{date_col} >= ?")
    p.append(start)
    c.append(f"{date_col} <= ?")
    p.append(end)
    where = ("WHERE " + " AND ".join(c)) if c else ""
    return where, p


def _pct(num: float | int | None, den: float | int | None) -> float | None:
    if den is None or float(den) <= 0 or num is None:
        return None
    return round(float(num) / float(den) * 100, 1)


def _empty_activity() -> dict[str, Any]:
    return {
        "concurrent_runs_active": None,
        "concurrency_as_of": None,
        "concurrency_sparkline": [],
        "runs_total": 0,
        "runs_by_status": {
            "succeeded": 0,
            "failed": 0,
            "timed_out": 0,
            "cancelled": 0,
        },
        "runs_ko": 0,
        "runs_ko_delta": None,
        "distinct_ko_workflows": 0,
    }


def _empty_reliability() -> dict[str, Any]:
    return {
        "success_rate_24h_pct": None,
        "success_rate_24h_n": 0,
        "success_rate_24h_delta": None,
        "success_rate_7d_pct": None,
        "success_rate_7d_n": 0,
        "success_rate_7d_delta": None,
        "task_failure_rate_pct": None,
        "tasks_failed": 0,
        "tasks_total": 0,
    }


def _empty_performance() -> dict[str, Any]:
    return {
        "avg_duration_seconds": None,
        "duration_drift_pct": None,
        "baseline_avg_duration_seconds": None,
        "p50": None,
        "p95": None,
        "p99": None,
        "avg_queued_duration_seconds": None,
        "avg_schedule_lag_seconds": None,
        "max_schedule_lag_seconds": None,
    }


async def _safe(coro: Any, fallback: Any, label: str) -> Any:
    try:
        return await coro
    except Exception:
        logger.exception("lakeflow overview soft-fail: %s", label)
        return fallback


async def _fetch_concurrency(
    db: DatabricksWarehousePool,
    table: str,
    scope: AllowedScope,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    workspace_ids: list[str] | None,
) -> dict[str, Any]:
    conditions, params = _scope_where(
        scope, source_lz_id, source_lz_ids, workspace_ids
    )
    conditions.append("minute_bucket >= current_timestamp() - INTERVAL 24 HOURS")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    rows = await db.fetchall(
        f"""
        SELECT
            minute_bucket,
            SUM(concurrent_runs_active) AS active
        FROM {table}
        {where}
        GROUP BY minute_bucket
        ORDER BY minute_bucket
        """,
        *params,
    )
    if not rows:
        return {
            "concurrent_runs_active": None,
            "concurrency_as_of": None,
            "concurrency_sparkline": [],
        }

    last = rows[-1]
    concurrent = int(last["active"] or 0)
    as_of = last["minute_bucket"]
    as_of_iso = as_of.isoformat() if hasattr(as_of, "isoformat") else str(as_of)

    # Sparkline: 15-min buckets, MAX within each bucket
    sparkline: list[dict[str, Any]] = []
    bucket_max: dict[str, int] = {}
    for r in rows:
        bucket = r["minute_bucket"]
        if hasattr(bucket, "replace"):
            truncated = bucket.replace(
                minute=(bucket.minute // 15) * 15, second=0, microsecond=0
            )
            key = truncated.isoformat()
        else:
            key = str(bucket)
        v = int(r["active"] or 0)
        bucket_max[key] = max(bucket_max.get(key, 0), v)
    sparkline = [{"t": k, "v": v} for k, v in sorted(bucket_max.items())]

    return {
        "concurrent_runs_active": concurrent,
        "concurrency_as_of": as_of_iso,
        "concurrency_sparkline": sparkline,
    }





def _agg_from_sums(row: dict[str, Any] | None) -> dict[str, Any]:
    terminal = int((row or {}).get("terminal") or 0)
    succeeded = int((row or {}).get("succeeded") or 0)
    failed_incl = int((row or {}).get("failed") or 0)  # gold: failed + timed_out
    timed_out = int((row or {}).get("timed_out") or 0)
    cancelled = int((row or {}).get("cancelled") or 0)
    failed_pure = max(failed_incl - timed_out, 0)
    return {
        "terminal": terminal,
        "succeeded": succeeded,
        "failed": failed_pure,
        "timed_out": timed_out,
        "cancelled": cancelled,
        "ko": failed_incl,
        "rate": _pct(succeeded, terminal),
    }


def _empty_success_agg() -> dict[str, Any]:
    return {
        "terminal": 0,
        "succeeded": 0,
        "failed": 0,
        "timed_out": 0,
        "cancelled": 0,
        "ko": 0,
        "rate": None,
    }


async def _fetch_success_buckets(
    db: DatabricksWarehousePool,
    table: str,
    scope: AllowedScope,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    workspace_ids: list[str] | None,
    buckets: dict[str, tuple[date, date]],
) -> dict[str, dict[str, Any]]:
    """One warehouse scan → success aggregates for multiple date windows."""
    if not buckets:
        return {}

    conditions, where_params = _scope_where(
        scope, source_lz_id, source_lz_ids, workspace_ids
    )
    min_d = min(s for s, _ in buckets.values())
    max_d = max(e for _, e in buckets.values())
    conditions.append("execution_date >= ?")
    where_params.append(min_d)
    conditions.append("execution_date <= ?")
    where_params.append(max_d)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # Positional `?` bind in appearance order: SELECT CASE windows first, then WHERE.
    # (Previously WHERE params were prepended → workspace filter zeroed activity KPIs.)
    select_parts: list[str] = []
    select_params: list[Any] = []
    for name, (b_start, b_end) in buckets.items():
        select_parts.append(
            f"""
            COALESCE(SUM(CASE WHEN execution_date >= ? AND execution_date <= ?
                              THEN terminal_runs ELSE 0 END), 0) AS {name}_terminal,
            COALESCE(SUM(CASE WHEN execution_date >= ? AND execution_date <= ?
                              THEN succeeded_runs ELSE 0 END), 0) AS {name}_succeeded,
            COALESCE(SUM(CASE WHEN execution_date >= ? AND execution_date <= ?
                              THEN failed_runs ELSE 0 END), 0) AS {name}_failed,
            COALESCE(SUM(CASE WHEN execution_date >= ? AND execution_date <= ?
                              THEN timed_out_runs ELSE 0 END), 0) AS {name}_timed_out,
            COALESCE(SUM(CASE WHEN execution_date >= ? AND execution_date <= ?
                              THEN cancelled_runs ELSE 0 END), 0) AS {name}_cancelled
            """
        )
        select_params.extend(
            [
                b_start,
                b_end,
                b_start,
                b_end,
                b_start,
                b_end,
                b_start,
                b_end,
                b_start,
                b_end,
            ]
        )

    row = await db.fetchone(
        f"""
        SELECT
            {", ".join(select_parts)}
        FROM {table}
        {where}
        """,
        *select_params,
        *where_params,
    )
    out: dict[str, dict[str, Any]] = {}
    for name in buckets:
        out[name] = _agg_from_sums(
            {
                "terminal": (row or {}).get(f"{name}_terminal"),
                "succeeded": (row or {}).get(f"{name}_succeeded"),
                "failed": (row or {}).get(f"{name}_failed"),
                "timed_out": (row or {}).get(f"{name}_timed_out"),
                "cancelled": (row or {}).get(f"{name}_cancelled"),
            }
        )
    return out


async def _fetch_distinct_ko(
    db: DatabricksWarehousePool,
    table: str,
    scope: AllowedScope,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    workspace_ids: list[str] | None,
    start: date,
    end: date,
) -> int:
    conditions, params = _scope_where(
        scope, source_lz_id, source_lz_ids, workspace_ids
    )
    where, params = _date_where(conditions, params, start, end)
    row = await db.fetchone(
        f"""
        SELECT COUNT(*) AS n FROM (
            SELECT workflow_id
            FROM {table}
            {where}
            GROUP BY workflow_id
            HAVING COALESCE(SUM(failed_runs), 0) > 0
        ) t
        """,
        *params,
    )
    return int((row or {}).get("n") or 0)


async def _fetch_task_failure(
    db: DatabricksWarehousePool,
    table: str,
    scope: AllowedScope,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    workspace_ids: list[str] | None,
    start: date,
    end: date,
) -> dict[str, Any]:
    conditions, params = _scope_where(
        scope, source_lz_id, source_lz_ids, workspace_ids
    )
    where, params = _date_where(conditions, params, start, end)
    row = await db.fetchone(
        f"""
        SELECT
            COALESCE(SUM(tasks_failed), 0) AS tasks_failed,
            COALESCE(SUM(tasks_total), 0)  AS tasks_total
        FROM {table}
        {where}
        """,
        *params,
    )
    failed = int((row or {}).get("tasks_failed") or 0)
    total = int((row or {}).get("tasks_total") or 0)
    return {"tasks_failed": failed, "tasks_total": total, "rate": _pct(failed, total)}


async def _fetch_performance(
    db: DatabricksWarehousePool,
    pct_table: str,
    drift_table: str,
    scope: AllowedScope,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    workspace_ids: list[str] | None,
    start: date,
    end: date,
) -> dict[str, Any]:
    conditions, params = _scope_where(
        scope, source_lz_id, source_lz_ids, workspace_ids
    )
    where, params = _date_where(conditions, params, start, end)

    pct_row, drift_row = await asyncio.gather(
        _safe(
            db.fetchone(
                f"""
                SELECT
                    SUM(avg_duration_seconds * total_runs)
                        / NULLIF(SUM(total_runs), 0)                        AS avg_duration,
                    SUM(avg_queued_duration_seconds * total_runs)
                        / NULLIF(SUM(CASE WHEN avg_queued_duration_seconds IS NOT NULL
                                          THEN total_runs ELSE 0 END), 0)   AS avg_queued,
                    SUM(avg_schedule_lag_seconds * total_runs)
                        / NULLIF(SUM(CASE WHEN avg_schedule_lag_seconds IS NOT NULL
                                          THEN total_runs ELSE 0 END), 0)   AS avg_lag,
                    MAX(max_schedule_lag_seconds)                           AS max_lag,
                    MAX(p50_duration_seconds)                               AS p50,
                    MAX(p95_duration_seconds)                               AS p95,
                    MAX(p99_duration_seconds)                               AS p99,
                    COALESCE(SUM(total_runs), 0)                            AS n
                FROM {pct_table}
                {where}
                """,
                *params,
            ),
            None,
            "percentiles",
        ),
        _safe(
            db.fetchone(
                f"""
                SELECT
                    SUM(avg_duration_seconds * total_runs)
                        / NULLIF(SUM(total_runs), 0) AS avg_duration,
                    SUM(baseline_avg_14d * total_runs)
                        / NULLIF(SUM(CASE WHEN baseline_avg_14d IS NOT NULL
                                          THEN total_runs ELSE 0 END), 0) AS baseline_avg,
                    COALESCE(SUM(CASE WHEN baseline_avg_14d IS NOT NULL
                                      THEN total_runs ELSE 0 END), 0) AS baseline_n
                FROM {drift_table}
                {where}
                """,
                *params,
            ),
            None,
            "drift",
        ),
    )

    avg_dur = (pct_row or {}).get("avg_duration")
    avg_queued = (pct_row or {}).get("avg_queued")
    avg_lag = (pct_row or {}).get("avg_lag")
    max_lag = (pct_row or {}).get("max_lag")
    p50 = (pct_row or {}).get("p50")
    p95 = (pct_row or {}).get("p95")
    p99 = (pct_row or {}).get("p99")

    baseline_avg = (drift_row or {}).get("baseline_avg") if drift_row else None
    baseline_n = int((drift_row or {}).get("baseline_n") or 0) if drift_row else 0
    # Prefer drift-table weighted avg when available
    if drift_row and (drift_row or {}).get("avg_duration") is not None:
        avg_dur = (drift_row or {}).get("avg_duration")

    drift_pct: float | None = None
    if (
        baseline_avg is not None
        and float(baseline_avg) >= 30
        and baseline_n >= 5
        and avg_dur is not None
        and float(baseline_avg) > 0
    ):
        drift_pct = round(
            (float(avg_dur) - float(baseline_avg)) / float(baseline_avg) * 100, 1
        )

    def _round_or_none(v: Any) -> int | None:
        if v is None:
            return None
        return round(float(v))

    return {
        "avg_duration_seconds": _round_or_none(avg_dur),
        "duration_drift_pct": drift_pct,
        "baseline_avg_duration_seconds": _round_or_none(baseline_avg),
        "p50": _round_or_none(p50),
        "p95": _round_or_none(p95),
        "p99": _round_or_none(p99),
        "avg_queued_duration_seconds": _round_or_none(avg_queued),
        "avg_schedule_lag_seconds": _round_or_none(avg_lag),
        "max_schedule_lag_seconds": _round_or_none(max_lag),
    }


async def _fetch_timeline(
    db: DatabricksWarehousePool,
    table: str,
    scope: AllowedScope,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    workspace_ids: list[str] | None,
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    conditions, params = _scope_where(
        scope, source_lz_id, source_lz_ids, workspace_ids
    )
    where, params = _date_where(conditions, params, start, end)
    rows = await db.fetchall(
        f"""
        SELECT
            execution_date AS dt,
            COALESCE(SUM(succeeded_runs), 0)  AS succeeded,
            COALESCE(SUM(failed_runs), 0) - COALESCE(SUM(timed_out_runs), 0) AS failed,
            COALESCE(SUM(timed_out_runs), 0)  AS timed_out,
            COALESCE(SUM(cancelled_runs), 0)  AS cancelled
        FROM {table}
        {where}
        GROUP BY execution_date
        ORDER BY execution_date
        """,
        *params,
    )
    return [
        {
            "date": str(r["dt"]),
            "succeeded": int(r["succeeded"] or 0),
            "failed": max(int(r["failed"] or 0), 0),
            "timed_out": int(r["timed_out"] or 0),
            "cancelled": int(r["cancelled"] or 0),
        }
        for r in rows
    ]


async def _fetch_top_unstable(
    db: DatabricksWarehousePool,
    table: str,
    scope: AllowedScope,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    workspace_ids: list[str] | None,
    start: date,
    end: date,
    limit: int = 5,
) -> list[dict[str, Any]]:
    conditions, params = _scope_where(
        scope, source_lz_id, source_lz_ids, workspace_ids
    )
    where, params = _date_where(conditions, params, start, end)
    rows = await db.fetchall(
        f"""
        SELECT
            workflow_id,
            COALESCE(MAX(workflow_name), CAST(workflow_id AS STRING)) AS workflow_name,
            COALESCE(SUM(failed_runs), 0) AS ko,
            COALESCE(SUM(terminal_runs), 0) AS total
        FROM {table}
        {where}
        GROUP BY workflow_id
        HAVING ko > 0
        ORDER BY ko DESC, total DESC
        LIMIT ?
        """,
        *params,
        limit,
    )
    return [
        {
            "workflow_id": str(r["workflow_id"]),
            "workflow_name": r["workflow_name"],
            "ko": int(r["ko"] or 0),
            "total": int(r["total"] or 0),
        }
        for r in rows
    ]


async def _fetch_recent_errors(
    db: DatabricksWarehousePool,
    table: str,
    scope: AllowedScope,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    workspace_ids: list[str] | None,
    start: date,
    end: date,
    limit: int = 5,
) -> list[dict[str, Any]]:
    conditions, params = _scope_where(
        scope, source_lz_id, source_lz_ids, workspace_ids
    )
    where, params = _date_where(conditions, params, start, end)
    # Append status filter
    if where:
        where = where + " AND status IN ('failed', 'timed_out')"
    else:
        where = "WHERE status IN ('failed', 'timed_out')"
    rows = await db.fetchall(
        f"""
        SELECT
            COALESCE(workflow_name, CAST(workflow_id AS STRING)) AS workflow_name,
            run_id,
            start_time,
            error_message,
            run_page_url
        FROM {table}
        {where}
        ORDER BY start_time DESC
        LIMIT ?
        """,
        *params,
        limit,
    )
    return [
        {
            "workflow_name": r["workflow_name"],
            "run_id": str(r["run_id"] or ""),
            "start_time": str(r["start_time"] or ""),
            "error_message": r["error_message"] or "",
            "run_page_url": r["run_page_url"] or "",
        }
        for r in rows
    ]


def _build_activity(
    conc: dict[str, Any],
    cur: dict[str, Any],
    prev: dict[str, Any],
    distinct_ko: int,
) -> dict[str, Any]:
    ko = int(cur.get("ko") or 0)
    prev_ko = int(prev.get("ko") or 0)
    return {
        "concurrent_runs_active": conc.get("concurrent_runs_active"),
        "concurrency_as_of": conc.get("concurrency_as_of"),
        "concurrency_sparkline": conc.get("concurrency_sparkline") or [],
        "runs_total": int(cur.get("terminal") or 0),
        "runs_by_status": {
            "succeeded": int(cur.get("succeeded") or 0),
            "failed": int(cur.get("failed") or 0),
            "timed_out": int(cur.get("timed_out") or 0),
            "cancelled": int(cur.get("cancelled") or 0),
        },
        "runs_ko": ko,
        "runs_ko_delta": ko - prev_ko,
        "distinct_ko_workflows": int(distinct_ko or 0),
    }


def _build_reliability(
    today_agg: dict[str, Any],
    prev_today_agg: dict[str, Any],
    week_agg: dict[str, Any],
    prev_week_agg: dict[str, Any],
    task_row: dict[str, Any],
) -> dict[str, Any]:
    rate_24h = today_agg.get("rate")
    rate_7d = week_agg.get("rate")
    prev_24h = prev_today_agg.get("rate")
    prev_7d = prev_week_agg.get("rate")

    def _delta(cur: float | None, prev: float | None) -> float | None:
        if cur is None or prev is None:
            return None
        return round(cur - prev, 1)

    return {
        "success_rate_24h_pct": rate_24h,
        "success_rate_24h_n": int(today_agg.get("terminal") or 0),
        "success_rate_24h_delta": _delta(rate_24h, prev_24h),
        "success_rate_7d_pct": rate_7d,
        "success_rate_7d_n": int(week_agg.get("terminal") or 0),
        "success_rate_7d_delta": _delta(rate_7d, prev_7d),
        "task_failure_rate_pct": task_row.get("rate"),
        "tasks_failed": int(task_row.get("tasks_failed") or 0),
        "tasks_total": int(task_row.get("tasks_total") or 0),
    }


async def fetch_lakeflow_overview(
    db: DatabricksWarehousePool,
    settings: Settings,
    scope: AllowedScope,
    *,
    window: str = "today",
    start_date: date | None = None,
    end_date: date | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    workspace_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return aggregated Lakeflow overview metrics for the Overview page."""
    window_key, start, end = _resolve_period(window, start_date, end_date)

    cache_key = build_cache_key(
        "lakeflow-overview",
        scope=cache_key_scope(scope),
        window=window_key,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        source_lz_id=source_lz_id,
        source_lz_ids=cache_key_ids(source_lz_ids),
        workspace_ids=cache_key_ids(workspace_ids),
    )

    async def load() -> dict[str, Any]:
        return await _fetch_lakeflow_overview_uncached(
            db,
            settings,
            scope,
            window_key=window_key,
            start=start,
            end=end,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_ids=workspace_ids,
        )

    return await get_cached_response(
        cache_key, load, ttl_seconds=_OVERVIEW_CACHE_TTL_SECONDS
    )


async def _fetch_lakeflow_overview_uncached(
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
) -> dict[str, Any]:
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
    conc_t = qualified_table(settings, _CONCURRENCY)
    runs_t = qualified_table(settings, _RUNS)

    prev_start, prev_end = _previous_window(start, end)
    today = end
    start_7d = today - timedelta(days=6)
    prev_today = today - timedelta(days=1)
    prev_7d_start = start_7d - timedelta(days=7)
    prev_7d_end = start_7d - timedelta(days=1)

    success_buckets = {
        "activity_cur": (start, end),
        "activity_prev": (prev_start, prev_end),
        "rel_today": (today, today),
        "rel_prev_today": (prev_today, prev_today),
        "rel_7d": (start_7d, today),
        "rel_prev_7d": (prev_7d_start, prev_7d_end),
    }

    (
        buckets,
        conc,
        distinct_ko,
        task_row,
        performance,
        timeline,
        top_unstable,
        recent_errors,
        real_as_of,
    ) = await asyncio.gather(
        _safe(
            _fetch_success_buckets(
                db,
                success_t,
                scope,
                source_lz_id,
                source_lz_ids,
                workspace_ids,
                success_buckets,
            ),
            {},
            "success-buckets",
        ),
        _safe(
            _fetch_concurrency(
                db, conc_t, scope, source_lz_id, source_lz_ids, workspace_ids
            ),
            {
                "concurrent_runs_active": None,
                "concurrency_as_of": None,
                "concurrency_sparkline": [],
            },
            "concurrency",
        ),
        _safe(
            _fetch_distinct_ko(
                db,
                success_t,
                scope,
                source_lz_id,
                source_lz_ids,
                workspace_ids,
                start,
                end,
            ),
            0,
            "distinct-ko",
        ),
        _safe(
            _fetch_task_failure(
                db,
                task_t,
                scope,
                source_lz_id,
                source_lz_ids,
                workspace_ids,
                start,
                end,
            ),
            {"tasks_failed": 0, "tasks_total": 0, "rate": None},
            "task-failure",
        ),
        _safe(
            _fetch_performance(
                db,
                pct_t,
                drift_t,
                scope,
                source_lz_id,
                source_lz_ids,
                workspace_ids,
                start,
                end,
            ),
            _empty_performance(),
            "performance",
        ),
        _safe(
            _fetch_timeline(
                db,
                success_t,
                scope,
                source_lz_id,
                source_lz_ids,
                workspace_ids,
                start,
                end,
            ),
            [],
            "timeline",
        ),
        _safe(
            _fetch_top_unstable(
                db,
                success_t,
                scope,
                source_lz_id,
                source_lz_ids,
                workspace_ids,
                start,
                end,
            ),
            [],
            "top-unstable",
        ),
        _safe(
            _fetch_recent_errors(
                db,
                runs_t,
                scope,
                source_lz_id,
                source_lz_ids,
                workspace_ids,
                start,
                end,
            ),
            [],
            "recent-errors",
        ),
        _safe(
            fetch_lakeflow_as_of(
                db, settings, scope, source_lz_id, source_lz_ids, workspace_ids
            ),
            None,
            "as-of",
        ),
    )

    empty_agg = _empty_success_agg()
    activity = _build_activity(
        conc if isinstance(conc, dict) else {},
        buckets.get("activity_cur", empty_agg) if isinstance(buckets, dict) else empty_agg,
        buckets.get("activity_prev", empty_agg) if isinstance(buckets, dict) else empty_agg,
        int(distinct_ko or 0),
    )
    reliability = _build_reliability(
        buckets.get("rel_today", empty_agg) if isinstance(buckets, dict) else empty_agg,
        buckets.get("rel_prev_today", empty_agg) if isinstance(buckets, dict) else empty_agg,
        buckets.get("rel_7d", empty_agg) if isinstance(buckets, dict) else empty_agg,
        buckets.get("rel_prev_7d", empty_agg) if isinstance(buckets, dict) else empty_agg,
        task_row if isinstance(task_row, dict) else {},
    )

    # Prefer the real ingestion timestamp; degrade to the last run bucket (still
    # real data), and only to now() when both sources are missing.
    as_of = (
        (real_as_of if isinstance(real_as_of, str) else None)
        or activity.get("concurrency_as_of")
        or datetime.now(UTC).isoformat()
    )

    return {
        "as_of": as_of,
        "window": {
            "key": window_key,
            "from": start.isoformat(),
            "to": end.isoformat(),
            "grain": "day",
        },
        "activity": activity,
        "reliability": reliability,
        "performance": performance if isinstance(performance, dict) else _empty_performance(),
        "timeline": timeline if isinstance(timeline, list) else [],
        "top_unstable": top_unstable if isinstance(top_unstable, list) else [],
        "recent_errors": recent_errors if isinstance(recent_errors, list) else [],
    }
