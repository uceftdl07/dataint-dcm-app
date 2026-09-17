"""Compute Metrics — forecast gold table + observed actuals for historical curve."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_table
from .compute_metrics_common import (
    _period_dict,
    _resolve_period,
    _row_to_dict,
    _scope_where,
)

__all__ = ["fetch_forecast"]

logger = logging.getLogger(__name__)

_FORECAST = "gold_dbx_compute_forecast_daily"
_CLUSTER_COST_DAILY = "gold_dbx_compute_cluster_cost_daily"
_JOB_COST_DAILY = "gold_dbx_compute_job_cluster_cost_daily"
_PIPELINE_COST_DAILY = "gold_dbx_compute_pipeline_cost_daily"
_WAREHOUSE_COST_DAILY = "gold_dbx_compute_warehouse_cost_daily"
_FORECAST_HORIZON_DAYS = 7

# The forecast grain CLUSTER covers interactive clusters only: JOB and PIPELINE
# clusters are ephemeral (a new cluster_id per run) and are projected from their
# own rollups instead. The historical curve must read the same population, or
# the actual line sits above a projection that never included those clusters.
_EPHEMERAL_CLUSTER_TYPES = ("JOB", "PIPELINE")

_DEFAULT_METRICS = (
    "cost_usd",
    "dbu_quantity",
    "cpu_util_p95_pct",
    "query_count",
    "queue_time_p95_ms",
)

# Metrics reconstructible from cost daily tables for a true historical curve.
_ACTUAL_COST_METRICS = frozenset({"cost_usd", "dbu_quantity"})


async def _fetch_actual_series(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    metrics: list[str],
    start: date,
    end: date,
    scope: list[str],
    scope_params: list[Any],
    object_type: str | None,
    object_id: str | None,
    restrict_to_projected: bool,
) -> list[dict[str, Any]]:
    """Actual daily spend over the selected period, on the forecast's own population.

    One branch per ``object_type`` the forecast projects (CLUSTER, JOB, PIPELINE,
    WAREHOUSE), each read from the gold ``*_cost_daily`` table that feeds the
    matching forecast pass. The two curves are drawn on the same axis, so they
    must cover the same spend: a branch missing from here — or a cluster type the
    projection excludes and this sums — offsets the actual line against a
    projection that never described the same objects.

    Sharing an axis constrains the population and the time window just as much.

    The projection only covers objects with enough history to be modelled, so
    summing every object here raises the actual line by the spend of those it
    leaves out — which reads as an under-forecast. Rather than restate the
    eligibility rule (it would drift from the pipeline on the next tuning), the
    branches semi-join the forecast table: that table is the record of what was
    actually projected. The semi-join reads the SAME horizon window as the
    projection query, so "the projection returned rows" and "the semi-join
    matches something" cannot disagree — a table holding only past horizons would
    otherwise pass ``restrict_to_projected`` and then match nothing, blanking the
    observed curve. ``restrict_to_projected`` is False when the projection came
    back empty, where the filter would drop the only data left to show.

    The window stops at the last COMPLETE day. The pipeline excludes the day in
    progress from training, so a projection describes a whole day; a partially
    loaded day summed here sits below its own projection by a margin that shrinks
    with every hour, and reads as an over-forecast that the same data will not
    show tomorrow.
    """
    wanted = [m for m in metrics if m in _ACTUAL_COST_METRICS]
    if not wanted:
        return []

    last_complete_day = min(end, datetime.now(UTC).date() - timedelta(days=1))
    if last_complete_day < start:
        return []

    projected = qualified_table(settings, _FORECAST)
    # Must mirror the horizon window of the projection query in `fetch_forecast`:
    # a narrower one here empties the curve, a wider one lets objects back in.
    horizon_end = end + timedelta(days=_FORECAST_HORIZON_DAYS)

    object_type_u = object_type.strip().upper() if object_type else None

    # object_id without type cannot be pinned safely across the source tables.
    if object_id and object_type_u is None:
        return []

    select_exprs: list[str] = []
    if "cost_usd" in wanted:
        select_exprs.append("COALESCE(SUM(cost_usd), 0) AS cost_usd")
    if "dbu_quantity" in wanted:
        select_exprs.append("COALESCE(SUM(dbu_quantity), 0) AS dbu_quantity")
    selects = ", ".join(select_exprs)

    parts: list[str] = []
    params: list[Any] = []

    def add_branch(
        table: str, id_column: str, match_type: str, extra_filters: tuple[str, ...] = ()
    ) -> None:
        if object_type_u not in (None, match_type):
            return
        filters = list(scope) + ["period_start >= ?", "period_start <= ?", *extra_filters]
        branch_params: list[Any] = list(scope_params) + [start, last_complete_day]
        if restrict_to_projected:
            filters.append(
                f"{id_column} IN (SELECT object_id FROM {projected}"
                " WHERE object_type = ? AND horizon_date >= ? AND horizon_date <= ?)"
            )
            branch_params.extend([match_type, start, horizon_end])
        if object_id and object_type_u == match_type:
            filters.append(f"{id_column} = ?")
            branch_params.append(object_id)
        where = "WHERE " + " AND ".join(filters)
        parts.append(
            f"""
            SELECT period_start AS horizon_date, {selects}
            FROM {table}
            {where}
            GROUP BY period_start
            """
        )
        params.extend(branch_params)

    # Jobs and pipelines carry their own rollup: a serverless job has no cluster
    # at all, so its spend exists in no cluster table and only these branches can
    # put it on the actual curve.
    ephemeral = ", ".join(f"'{cluster_type}'" for cluster_type in _EPHEMERAL_CLUSTER_TYPES)
    add_branch(
        qualified_table(settings, _CLUSTER_COST_DAILY),
        "cluster_id",
        "CLUSTER",
        (f"cluster_type NOT IN ({ephemeral})",),
    )
    add_branch(qualified_table(settings, _JOB_COST_DAILY), "job_id", "JOB")
    add_branch(qualified_table(settings, _PIPELINE_COST_DAILY), "dlt_pipeline_id", "PIPELINE")
    add_branch(qualified_table(settings, _WAREHOUSE_COST_DAILY), "warehouse_id", "WAREHOUSE")
    if not parts:
        return []

    re_select: list[str] = []
    if "cost_usd" in wanted:
        re_select.append("COALESCE(SUM(cost_usd), 0) AS cost_usd")
    if "dbu_quantity" in wanted:
        re_select.append("COALESCE(SUM(dbu_quantity), 0) AS dbu_quantity")

    rows = await db.fetchall(
        f"""
        SELECT horizon_date, {", ".join(re_select)}
        FROM (
            {" UNION ALL ".join(parts)}
        ) daily
        GROUP BY horizon_date
        ORDER BY horizon_date
        """,
        *params,
    )

    actuals: list[dict[str, Any]] = []
    for row in rows:
        horizon = row.get("horizon_date")
        date_str = horizon.isoformat() if hasattr(horizon, "isoformat") else str(horizon)
        actuals.extend(
            {
                "horizon_date": date_str,
                "metric_name": metric,
                "actual_value": float(row.get(metric) or 0),
            }
            for metric in wanted
        )
    return actuals


async def fetch_forecast(
    db: DatabricksWarehousePool,
    settings: Settings,
    allowed_lz_ids: list[str] | None,
    *,
    period_start: date | None = None,
    period_end: date | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    workspace_ids: list[str] | None = None,
    allowed_workspace_ids: list[str] | None = None,
    cloud_provider: str | None = None,
    metric_name: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
) -> dict[str, Any]:
    start, end = _resolve_period(period_start, period_end)
    table = qualified_table(settings, _FORECAST)
    metrics = [metric_name] if metric_name else list(_DEFAULT_METRICS)

    empty: dict[str, Any] = {
        "items": [],
        "actuals": [],
        "period": _period_dict(start, end),
        "metrics": metrics,
    }

    try:
        scope, scope_params = _scope_where(
            allowed_lz_ids,
            source_lz_id,
            source_lz_ids,
            workspace_ids,
            has_lz_column=False,
            allowed_workspace_ids=allowed_workspace_ids,
            cloud_provider=cloud_provider,
        )

        filters: list[str] = []
        params: list[Any] = list(scope_params)
        placeholders = ", ".join("?" for _ in metrics)
        filters.append(f"metric_name IN ({placeholders})")
        params.extend(metrics)

        if object_type:
            filters.append("UPPER(object_type) = ?")
            params.append(object_type.strip().upper())
        if object_id:
            filters.append("object_id = ?")
            params.append(object_id)

        filters.append("horizon_date >= ?")
        params.append(start)
        filters.append("horizon_date <= ?")
        params.append(end + timedelta(days=_FORECAST_HORIZON_DAYS))

        where = ("WHERE " + " AND ".join(scope + filters)) if (scope or filters) else ""

        rows = await db.fetchall(
            f"""
            SELECT
                cloud_provider,
                object_type,
                object_id,
                metric_name,
                horizon_date,
                predicted_value,
                lower_bound,
                upper_bound,
                method
            FROM {table}
            {where}
            ORDER BY metric_name, horizon_date, object_id
            """,
            *params,
        )

        actuals = await _fetch_actual_series(
            db,
            settings,
            metrics=metrics,
            start=start,
            end=end,
            scope=scope,
            scope_params=scope_params,
            object_type=object_type,
            object_id=object_id,
            restrict_to_projected=bool(rows),
        )

        return {
            "items": [_row_to_dict(r) for r in rows],
            "actuals": actuals,
            "period": _period_dict(start, end),
            "metrics": metrics,
        }
    except Exception:
        logger.exception("forecast soft-fail")
        return empty
