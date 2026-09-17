"""Compute Metrics — serverless spend, grain ``serverless_surface`` × object.

Reads the four gold tables written by T001d/T001e:

* ``gold_dbx_compute_serverless_cost_rolling`` — snapshot per (cloud, workspace,
  surface, object) and per window (1/7/30/90 days) anchored on ``as_of_date``;
* ``gold_dbx_compute_serverless_cost_daily`` — the same grain per day, for the trends;
* ``gold_dbx_compute_serverless_governance`` — **snapshot without ``window_days``**
  (it carries its own ``window_start``/``window_end``), so it is scoped but never
  windowed, and its figures are captioned with their own period;
* ``gold_dbx_compute_pipeline_update_stats`` — update grain, for the DLT
  serverless-vs-classic comparison of ``/serverless/levers``.

A family of its own rather than an extension of ``compute_metrics_warehouses``: the
grain is different (surface × object, not warehouse), the tables are different, and a
serverless SQL warehouse is *one row of one surface* here (plan decision D11).

Two traps this module exists to avoid, both measured in dev on 2026-09-10:

1. **The object key is not always an object.** ``object_id`` falls back to the gold
   sentinel ``_NO_OBJECT`` for the four surfaces that have nothing listable (``GENIE``,
   ``NETWORKING``, ``PLATFORM_AUTO``, ``OTHER``) *and* for a residue inside surfaces
   that do have one (21 ``NOTEBOOK`` rows, 10 of the 265 ``AI_ENDPOINT`` rows). The
   sentinel is never served as an id: it becomes ``object_id: null`` next to
   ``has_object_key: false``, so the UI cannot deep-link to a row that has no object.
2. **``workspace_id`` is part of the object key.** ``AI_ENDPOINT`` holds 265 rows for
   **251 distinct ``object_id``** — the same endpoint id exists in several workspaces.
   Counting or keying on ``object_id`` alone folds two objects into one, which is why
   :func:`_object_key_sql` exists and why the detail returns a per-workspace breakdown
   instead of picking the heaviest row.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from enum import StrEnum
from typing import Any

from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_table
from .compute_metrics_common import (
    _DEFAULT_PAGE_SIZE,
    RollingWindowDays,
    _as_float,
    _clamp_page,
    _date_where,
    _empty_page,
    _grain,
    _is_table_missing,
    _iso,
    _normalize_prev_cost,
    _pct_delta,
    _period_dict,
    _resolve_period,
    _row_to_dict,
    _scope_where,
    _window_block,
    _window_period,
    _window_where,
)
from .compute_metrics_filters import build_column_filter_sql, parse_column_filters

__all__ = [
    "SERVERLESS_OBJECT_ID_SENTINEL",
    "ServerlessSurface",
    "fetch_serverless_cost_trend",
    "fetch_serverless_governance",
    "fetch_serverless_levers",
    "fetch_serverless_object_cost_trend",
    "fetch_serverless_object_detail",
    "fetch_serverless_objects",
    "fetch_serverless_overview",
    "fetch_serverless_surfaces",
]

logger = logging.getLogger(__name__)

_COST_ROLLING = "gold_dbx_compute_serverless_cost_rolling"
_COST_DAILY = "gold_dbx_compute_serverless_cost_daily"
_GOVERNANCE = "gold_dbx_compute_serverless_governance"
_UPDATE_STATS = "gold_dbx_compute_pipeline_update_stats"

# Read only to build the denominator of the serverless share — see ``_share_block``.
_CLUSTER_COST_ROLLING = "gold_dbx_compute_cluster_cost_rolling"
_WAREHOUSE_COST_ROLLING = "gold_dbx_compute_warehouse_cost_rolling"
_WAREHOUSE_UTILIZATION_ROLLING = "gold_dbx_compute_warehouse_utilization_rolling"

#: Value ``serverless_object_id_expr`` falls back to when a surface has no listable
#: object (``sql_helpers.SERVERLESS_OBJECT_ID_SENTINEL``). Spelled again here rather
#: than imported: this package does not depend on ``dcm-databricks-pipeline``.
SERVERLESS_OBJECT_ID_SENTINEL = "_NO_OBJECT"


class ServerlessSurface(StrEnum):
    """The 12 surfaces ``serverless_surface_case_expr`` can produce.

    Declared as an enum for the same reason as :class:`RollingWindowDays`: FastAPI
    rejects anything else with a 422, whereas a bare ``str`` parameter would let
    ``surface=SQL_WAREHOUSSE`` through and answer an empty page — which reads as "no
    serverless SQL warehouse in your perimeter", the opposite of the truth.

    Mirrors ``sql_helpers.SERVERLESS_SURFACES``; that builder is the source of truth, and
    a surface added there must be added here or it stays unreachable through the API. The
    duplication is deliberate — the backend cannot import the pipeline package — and the
    test that pins the 12 members is what keeps the two lists honest.
    """

    JOB = "JOB"
    DLT_PIPELINE = "DLT_PIPELINE"
    MV_ST_REFRESH = "MV_ST_REFRESH"
    SQL_WAREHOUSE = "SQL_WAREHOUSE"
    NOTEBOOK = "NOTEBOOK"
    APP = "APP"
    AI_ENDPOINT = "AI_ENDPOINT"
    LAKEBASE = "LAKEBASE"
    GENIE = "GENIE"
    NETWORKING = "NETWORKING"
    PLATFORM_AUTO = "PLATFORM_AUTO"
    OTHER = "OTHER"


#: Bucket the cost trend folds every surface outside its top 5 into. **Not** ``OTHER``,
#: which is one of the 12 real surfaces: the two would add up into a single series and
#: the legend would name a surface whose figure is wrong.
_OTHER_SURFACES_BUCKET = "OTHER_SURFACES"

_TREND_TOP_SURFACES = 5

#: Upper edges of ``cost_per_run_histogram``, doubling from 1 cent
#: (``sql_helpers.HISTOGRAM_COST_PER_RUN_EDGES``). 18 edges → 19 buckets, the last one
#: unbounded. Needed here only to *label* the buckets gold already counted; the counts
#: themselves are never recomputed.
_COST_PER_RUN_EDGES: tuple[float, ...] = (
    0.01,
    0.02,
    0.04,
    0.08,
    0.16,
    0.32,
    0.64,
    1.28,
    2.56,
    5.12,
    10.24,
    20.48,
    40.96,
    81.92,
    163.84,
    327.68,
    655.36,
    1310.72,
)

_COST_PER_RUN_BUCKETS = len(_COST_PER_RUN_EDGES) + 1

#: Below this many DLT requests, the comparison block reports "not comparable" instead of
#: a rate. Measured in dev on 2026-09-10: azure classic DLT weighs **6 requests** over the
#: 30-day window, whose 2 failures render as "33,33 %" next to a serverless rate resting
#: on thousands. Without a floor the page would announce that classic fails 5,6× more on
#: azure, out of two rows.
_MIN_COMPARISON_REQUESTS = 30

_TOP_FAILING_PIPELINES = 10

#: Only the **last attempt** of a request counts. ``RETRY_ON_FAILURE`` is a
#: ``trigger_type`` of its own, so counting every update turns one recovered failure into
#: two: measured on the whole table, ``FAILED`` weighs **1 770 classic updates for 886
#: requests** and 8 329 serverless updates for 6 016 requests — the same population, twice
#: the failures. The denominator is therefore the request, never the update.
_LAST_ATTEMPT_RANK = (
    "ROW_NUMBER() OVER (PARTITION BY cloud_provider, workspace_id, request_id "
    "ORDER BY update_start_time DESC, update_id DESC)"
)

#: The three terminal states this table actually holds — measured, no other value exists.
#: ``CANCELED`` is counted out of both the numerator **and** the denominator and reported
#: on its own: a cancellation is an operator decision, not a compute failure, and folding
#: it into either side would make the two compute forms differ by their operators' habits.
#: It weighs 21 classic and 123 serverless requests, so the choice moves almost nothing —
#: which is exactly why it is worth making explicitly rather than by accident.
_OUTCOME_STATES: tuple[str, ...] = ("COMPLETED", "FAILED")
_FAILED_STATE = "FAILED"
_CANCELED_STATE = "CANCELED"
_COMPLETED_STATE = "COMPLETED"

_SURFACE_FILTER = "serverless_surface = ?"
_OBJECT_ID_FILTER = "object_id = ?"

_ROW_COLUMNS = """
    cloud_provider,
    workspace_id,
    serverless_surface,
    object_id,
    object_name,
    billing_origin_product,
    performance_target,
    budget_policy_id,
    identity_principal,
    identity_source,
    has_custom_tags,
    has_object_key,
    dbu_quantity,
    cost_usd,
    cost_usd_prev_window,
    cost_delta_pct,
    run_count,
    cost_per_run_p50_usd,
    cost_per_run_p95_usd,
    cost_per_run_p99_usd,
    cost_rank,
    is_top_cost
"""

_GOVERNANCE_ROW_COLUMNS = """
    cloud_provider,
    workspace_id,
    serverless_surface,
    cost_usd,
    cost_usd_with_owner_tag,
    owner_tag_coverage_pct,
    cost_usd_with_cost_center_tag,
    cost_center_tag_coverage_pct,
    cost_usd_with_budget_policy,
    budget_policy_coverage_pct,
    cost_usd_without_identity,
    identity_coverage_pct,
    cost_usd_without_object_key,
    identity_source_mix,
    budget_policy_count,
    budget_policy_inventory
"""


def _order(direction: str) -> str:
    """``NULLS LAST`` either way: a missing value sorts last, never first.

    ``performance_target`` and ``cost_per_run_p50_usd`` are ``NULL`` on a large share of
    the rows (39,6 % and every non-``JOB`` surface respectively), so an ascending sort
    without this would open the page on a screenful of dashes.
    """
    return (
        "ASC NULLS LAST"
        if (direction or "").strip().lower() == "asc"
        else "DESC NULLS LAST"
    )


def _object_sort_clause(sort: str, direction: str) -> str:
    """Allowlisted ORDER BY — the only place a client string reaches the SQL text."""
    columns = {
        "name": "COALESCE(object_name, object_id)",
        "cost": "cost_usd",
        "dbu": "dbu_quantity",
        "runs": "run_count",
        "cost_per_run": "cost_per_run_p50_usd",
        "surface": "serverless_surface",
    }
    column = columns.get((sort or "").strip().lower(), "cost_usd")
    # The tie-break must be **total** and on the full gold key: two rows sharing a cost
    # would otherwise be ordered non-deterministically between two queries, which makes
    # one row show up on two pages while another never shows up at all.
    return (
        f"{column} {_order(direction)}, "
        "workspace_id ASC, serverless_surface ASC, object_id ASC"
    )


def _surface_sort_clause(sort: str, direction: str) -> str:
    columns = {
        "surface": "serverless_surface",
        "cost": "cost_usd",
        "dbu": "dbu_quantity",
        "objects": "object_count",
        "runs": "run_count",
    }
    column = columns.get((sort or "").strip().lower(), "cost_usd")
    return f"{column} {_order(direction)}, serverless_surface ASC"


def _governance_sort_clause(sort: str, direction: str) -> str:
    columns = {
        "surface": "serverless_surface",
        "cost": "cost_usd",
        "owner_tag": "owner_tag_coverage_pct",
        "cost_center_tag": "cost_center_tag_coverage_pct",
        "budget_policy": "budget_policy_coverage_pct",
        "identity": "identity_coverage_pct",
    }
    column = columns.get((sort or "").strip().lower(), "cost_usd")
    return f"{column} {_order(direction)}, workspace_id ASC, serverless_surface ASC"


def _search_clause(search: str | None) -> tuple[str, list[Any]]:
    """Free-text search on the object name **and** its id, both lowercased.

    On the id too because several surfaces carry no name at all: an ``AI_ENDPOINT`` row
    is often nothing but its id, and a search restricted to the name would answer "not
    found" for a string the user is reading off the page.
    """
    if not search or not search.strip():
        return "", []
    pattern = f"%{search.strip().lower()}%"
    return " AND (LOWER(object_name) LIKE ? OR LOWER(object_id) LIKE ?)", [
        pattern,
        pattern,
    ]


def _object_key_sql(*columns: str) -> str:
    """A composite key that only counts the rows carrying a real object.

    ``CASE WHEN has_object_key`` rather than a comparison against the sentinel: gold has
    already computed that predicate. A page counting ``COUNT(DISTINCT object_id)`` would
    add **one phantom object per surface** — the sentinel — and fold every workspace of a
    keyless surface into it.
    """
    joined = ", ".join(columns)
    return f"CASE WHEN has_object_key THEN CONCAT_WS('|', {joined}) END"


_OBJECT_KEY = _object_key_sql(
    "cloud_provider", "workspace_id", "serverless_surface", "object_id"
)


def _strip_sentinel(item: dict[str, Any]) -> dict[str, Any]:
    """Never serve ``_NO_OBJECT`` as an id.

    The sentinel exists because ``object_id`` is a **merge key** in gold, and a merge key
    may not be ``NULL`` (``merge_into_table`` merges on null-safe ``<=>``, so a ``NULL``
    fuses rows instead of raising). The API has no such constraint, and ``has_object_key``
    already carries the information — passing the sentinel through would hand the UI a
    deep-link target that 404s.
    """
    if item.get("object_id") == SERVERLESS_OBJECT_ID_SENTINEL:
        item["object_id"] = None
    return item


def _histogram_buckets(counts: dict[int, int]) -> list[dict[str, Any]]:
    """Label the 19 gold buckets with their edges, the last one unbounded.

    Takes a **position → count** mapping, not a list, and rebuilds the dense series
    itself: a ``GROUP BY pos`` skips the empty buckets, so appending rows in arrival order
    would shift every label after the first gap — a 0,64 $ bucket presented as 0,08 $.
    """
    buckets: list[dict[str, Any]] = []
    for index in range(_COST_PER_RUN_BUCKETS):
        low = 0.0 if index == 0 else _COST_PER_RUN_EDGES[index - 1]
        high = _COST_PER_RUN_EDGES[index] if index < len(_COST_PER_RUN_EDGES) else None
        buckets.append(
            {"from_usd": low, "to_usd": high, "run_count": int(counts.get(index, 0))}
        )
    return buckets


def _histogram_sql(table: str, where: str) -> str:
    """Element-wise sum of ``cost_per_run_histogram`` over the rows of ``where``.

    A real **run-level** distribution: gold counted the runs of each object into fixed
    buckets, so summing the vectors position by position gives the distribution of the
    runs themselves. Averaging the per-object ``cost_per_run_p50_usd`` instead would give
    the median of the medians, which is not the median of anything.

    ``posexplode`` and not ``posexplode_outer``: the caller's ``where`` already excludes
    the ``NULL`` arrays, and the outer variant would emit a ``(NULL, NULL)`` row that
    lands in no bucket.
    """
    return f"""
        WITH p AS (
            SELECT cost_per_run_histogram FROM {table} {where}
        )
        SELECT h.pos AS bucket_index, COALESCE(SUM(h.cnt), 0) AS run_count
        FROM p
        LATERAL VIEW posexplode(p.cost_per_run_histogram) h AS pos, cnt
        GROUP BY h.pos
        ORDER BY h.pos
    """


def _share_pct(part: float | None, whole: float | None) -> float | None:
    """``None`` rather than ``0`` when there is nothing to divide by."""
    if part is None or not whole or whole <= 0:
        return None
    return round(part / whole * 100, 1)


def _optional_int(value: Any) -> int | None:
    """``None`` stays ``None`` — for the columns where zero is a different claim.

    Used for every served ``run_count``. Measured in dev on 2026-09-10, on the 30-day
    window: ``run_count`` is NULL on **100 % of the rows of eleven surfaces** (and on
    1 387 of the 5 076 ``JOB`` rows), and **not one row in the whole table carries
    ``run_count = 0``**. Gold therefore never says "this ran zero times" — it says "runs
    are not counted for this kind of object", by leaving the column NULL. Folding that
    into ``0`` with a ``COALESCE`` would have the API assert that 8 590 notebooks
    consumed 24 933 $ while running zero times, and would make any client-side cost per
    run divide by zero. ``SUM()`` already returns NULL over an all-NULL group, so the
    honest answer costs nothing but not writing the ``COALESCE``.
    """
    return None if value is None else int(value)


def _scope_only_where(scope: list[str]) -> str:
    """WHERE built from the scope alone — for the tables with no ``window_days``."""
    return ("WHERE " + " AND ".join(scope)) if scope else ""


def _quoted(values: tuple[str, ...]) -> str:
    """``('COMPLETED', 'FAILED')`` from a module constant — never from client input."""
    return ", ".join(f"'{value}'" for value in values)


# --------------------------------------------------------------------------------------
# Overview
# --------------------------------------------------------------------------------------


async def fetch_serverless_overview(
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
    window_days: int = RollingWindowDays.DAY,
) -> dict[str, Any]:
    """KPIs of the serverless page: cost, delta, share of compute, governance coverage.

    The **share** is served in dollars, never in DBU, and it comes with the three parts of
    its denominator — see :func:`_share_block`.

    The two coverage figures are **global** and weighted by dollars, read from the
    governance snapshot: 13,38 % of budget-policy coverage in dev on 2026-09-10
    (138 597,52 $ of 1 036 222,34 $) and 3,10 % of owner-tag coverage. Publishing a
    surface's own figure here would flatter the page — ``JOB`` alone is at 34,65 %, while
    the heaviest surface, ``SQL_WAREHOUSE``, is at 0,00 %.
    """
    start, end = _resolve_period(period_start, period_end)
    window = int(window_days)
    cost_t = qualified_table(settings, _COST_ROLLING)
    gov_t = qualified_table(settings, _GOVERNANCE)

    empty: dict[str, Any] = {
        "kpis": {
            "cost_usd": 0.0,
            "cost_usd_prev_window": None,
            "cost_delta_pct": None,
            "dbu_quantity": 0.0,
            # ``None``, not ``0``, and not for symmetry with the two lines above: this
            # block is what the route serves when the gold table is **missing**, and a
            # missing table is the one situation where "zero runs" is certainly false —
            # nothing was counted at all. It is also what the real query returns on an
            # empty perimeter (``SUM()`` over no row is NULL), so the fallback and the
            # live path now answer the same thing about the same fact. See
            # :func:`_optional_int`.
            "run_count": None,
            "surface_count": 0,
            "object_count": 0,
            "cost_usd_without_identity": None,
            "cost_usd_without_object_key": None,
            "budget_policy_coverage_pct": None,
            "owner_tag_coverage_pct": None,
            "serverless_share": None,
        },
        "governance_period": None,
        "window": _window_block(window, None),
        "period": _period_dict(start, end),
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
        where, params = _window_where(
            scope, scope_params, window, latest_snapshot_table=cost_t
        )

        cost_row, gov_row, share = await asyncio.gather(
            db.fetchone(
                f"""
                SELECT
                    COALESCE(SUM(cost_usd), 0) AS cost_usd,
                    COALESCE(SUM(cost_usd_prev_window), 0) AS cost_usd_prev_window,
                    COALESCE(SUM(dbu_quantity), 0) AS dbu_quantity,
                    SUM(run_count) AS run_count,
                    COUNT(DISTINCT serverless_surface) AS surface_count,
                    COUNT(DISTINCT {_OBJECT_KEY}) AS object_count,
                    MAX(window_start) AS window_start,
                    MAX(as_of_date) AS as_of_date
                FROM {cost_t}
                {where}
                """,
                *params,
            ),
            # The governance table carries neither ``window_days`` nor ``as_of_date``: it
            # is one snapshot over its own period, so it takes the scope and nothing else.
            # Adding ``window_days = ?`` here would return zero rows, silently.
            db.fetchone(
                f"""
                SELECT
                    COALESCE(SUM(cost_usd), 0) AS cost_usd,
                    COALESCE(SUM(cost_usd_with_budget_policy), 0) AS cost_with_policy,
                    COALESCE(SUM(cost_usd_with_owner_tag), 0) AS cost_with_owner_tag,
                    COALESCE(SUM(cost_usd_without_identity), 0) AS cost_without_identity,
                    COALESCE(SUM(cost_usd_without_object_key), 0) AS cost_without_key,
                    MIN(window_start) AS window_start,
                    MAX(window_end) AS window_end
                FROM {gov_t}
                {_scope_only_where(scope)}
                """,
                *scope_params,
            ),
            _share_block(
                db, settings, scope=scope, scope_params=scope_params, window=window
            ),
        )

        cost = _as_float((cost_row or {}).get("cost_usd")) or 0.0
        previous = _as_float((cost_row or {}).get("cost_usd_prev_window")) or 0.0
        gov_cost = _as_float((gov_row or {}).get("cost_usd")) or 0.0
        window_block = _window_block(window, cost_row)

        return {
            "kpis": {
                "cost_usd": cost,
                # A zero previous window means "no comparison", never "it was free": gold
                # aggregates it with ``SUM(CASE … ELSE 0 END)``, so the column is
                # structurally never NULL. Same rule as ``_normalize_prev_cost``.
                "cost_usd_prev_window": previous if previous > 0 else None,
                "cost_delta_pct": _pct_delta(cost, previous),
                "dbu_quantity": _as_float((cost_row or {}).get("dbu_quantity")) or 0.0,
                "run_count": _optional_int((cost_row or {}).get("run_count")),
                "surface_count": int((cost_row or {}).get("surface_count") or 0),
                "object_count": int((cost_row or {}).get("object_count") or 0),
                "cost_usd_without_identity": _as_float(
                    (gov_row or {}).get("cost_without_identity")
                ),
                "cost_usd_without_object_key": _as_float(
                    (gov_row or {}).get("cost_without_key")
                ),
                "budget_policy_coverage_pct": _share_pct(
                    _as_float((gov_row or {}).get("cost_with_policy")), gov_cost
                ),
                "owner_tag_coverage_pct": _share_pct(
                    _as_float((gov_row or {}).get("cost_with_owner_tag")), gov_cost
                ),
                "serverless_share": share,
            },
            # The governance block covers its own period, wider than the selected window
            # (90 days in dev): captioning it with the window would misstate which days
            # the coverage was measured on.
            "governance_period": {
                "from": _iso((gov_row or {}).get("window_start")),
                "to": _iso((gov_row or {}).get("window_end")),
            },
            "window": window_block,
            "period": _window_period(window_block, start, end),
        }
    except Exception:
        logger.exception("serverless overview soft-fail")
        return empty


async def _share_block(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    scope: list[str],
    scope_params: list[Any],
    window: int,
) -> dict[str, Any] | None:
    """Share of serverless in the compute spend, with the denominator it rests on.

    There is **no gold table holding a compute total**, and the cost rollups overlap: a
    serverless SQL warehouse is billed in ``warehouse_cost_rolling`` *and* in
    ``serverless_cost_rolling``. Summing them double-counts — 156 787 $ of the 30-day
    window in dev. The denominator is therefore a **partition**, each part read on the
    only table that can produce it:

    * serverless — ``serverless_cost_rolling`` (serverless SQL warehouses included);
    * classic clusters — ``cluster_cost_rolling`` (a serverless line has no
      ``cluster_id``, so it cannot appear there);
    * classic SQL warehouses — ``warehouse_cost_rolling`` minus the serverless ones,
      which only ``warehouse_utilization_rolling.is_serverless`` can tell apart.

    Cross-check that the partition holds, dev 2026-09-10, window 30: the serverless
    warehouse cost seen from the warehouse side (156 787,11 $) matches the
    ``SQL_WAREHOUSE`` + ``MV_ST_REFRESH`` surfaces (159 953,70 + 2 275,81 $) to within the
    one-day ``as_of_date`` shift between the two rollups.

    Two facts make the result an estimate, and both are returned rather than hidden:

    1. the utilization snapshot does not cover every billed warehouse — **89 rows /
       6 944,62 $ (3,9 % of the window)** carry no ``is_serverless`` at all. They are
       counted as classic, which *lowers* the serverless share instead of inflating it,
       and they are reported as ``unclassified_warehouse_cost_usd`` so the reader can size
       the uncertainty rather than guess at it;
    2. the two warehouse tables are written by two rollups whose ``as_of_date`` differ by
       a run (2026-09-09 against 2026-09-10 in dev), so each carries its **own** stale-row
       guard. Joining them **on ``as_of_date``** matches almost nothing: measured before
       this comment existed, it left 100 % of the warehouse cost unclassified while
       raising no error at all.

    The share is in **dollars, not DBU**: a serverless DBU and a classic DBU are priced
    differently, so their ratio would not be a share of anything.
    """
    cost_t = qualified_table(settings, _COST_ROLLING)
    cluster_t = qualified_table(settings, _CLUSTER_COST_ROLLING)
    wh_cost_t = qualified_table(settings, _WAREHOUSE_COST_ROLLING)
    wh_util_t = qualified_table(settings, _WAREHOUSE_UTILIZATION_ROLLING)

    try:
        srv_where, srv_params = _window_where(
            scope, scope_params, window, latest_snapshot_table=cost_t
        )
        cluster_where, cluster_params = _window_where(
            scope, scope_params, window, latest_snapshot_table=cluster_t
        )
        wh_where, wh_params = _window_where(
            scope, scope_params, window, latest_snapshot_table=wh_cost_t
        )

        serverless_row, cluster_row, warehouse_row = await asyncio.gather(
            db.fetchone(
                f"SELECT COALESCE(SUM(cost_usd), 0) AS cost_usd "
                f"FROM {cost_t} {srv_where}",
                *srv_params,
            ),
            db.fetchone(
                f"SELECT COALESCE(SUM(cost_usd), 0) AS cost_usd "
                f"FROM {cluster_t} {cluster_where}",
                *cluster_params,
            ),
            db.fetchone(
                f"""
                WITH c AS (
                    SELECT cloud_provider, workspace_id, warehouse_id, window_days,
                           cost_usd
                    FROM {wh_cost_t}
                    {wh_where}
                ),
                u AS (
                    SELECT cloud_provider, workspace_id, warehouse_id, window_days,
                           is_serverless
                    FROM {wh_util_t}
                    WHERE as_of_date = (SELECT MAX(as_of_date) FROM {wh_util_t})
                )
                SELECT
                    COALESCE(
                        SUM(CASE WHEN u.is_serverless = false THEN c.cost_usd END), 0
                    ) AS classic_cost_usd,
                    COALESCE(
                        SUM(CASE WHEN u.is_serverless IS NULL THEN c.cost_usd END), 0
                    ) AS unclassified_cost_usd
                FROM c
                LEFT JOIN u
                    ON u.cloud_provider = c.cloud_provider
                   AND u.workspace_id = c.workspace_id
                   AND u.warehouse_id = c.warehouse_id
                   AND u.window_days = c.window_days
                """,
                *wh_params,
            ),
        )

        serverless = _as_float((serverless_row or {}).get("cost_usd")) or 0.0
        classic_clusters = _as_float((cluster_row or {}).get("cost_usd")) or 0.0
        classic_warehouses = (
            _as_float((warehouse_row or {}).get("classic_cost_usd")) or 0.0
        )
        unclassified = (
            _as_float((warehouse_row or {}).get("unclassified_cost_usd")) or 0.0
        )
        classic = classic_clusters + classic_warehouses + unclassified

        return {
            "pct": _share_pct(serverless, serverless + classic),
            "serverless_cost_usd": serverless,
            "classic_cost_usd": classic,
            "classic_cluster_cost_usd": classic_clusters,
            "classic_warehouse_cost_usd": classic_warehouses,
            "unclassified_warehouse_cost_usd": unclassified,
        }
    except Exception:
        # ``None``, not a share of 100 %: a denominator that could not be built is not an
        # estate that happens to be entirely serverless.
        logger.exception("serverless share soft-fail")
        return None


# --------------------------------------------------------------------------------------
# Surfaces
# --------------------------------------------------------------------------------------


async def fetch_serverless_surfaces(
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
    window_days: int = RollingWindowDays.DAY,
    sort: str = "cost",
    sort_direction: str = "desc",
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """One row per ``serverless_surface``: cost, share, delta, objects, keyed share.

    Deltas and shares are recomputed from the **sums**, never averaged over the rows' own
    ``cost_delta_pct``: the mean of per-object percentages is not the percentage of the
    surface, and on a surface where one cheap object doubled it is not even close.

    ``total`` and ``total_cost_usd`` come from a dedicated aggregate, not from a
    ``COUNT(*) OVER ()`` on the page: that idiom returns **nothing** when the requested
    page is past the end, so the client loses the total exactly when it needs it to
    correct its own pagination.
    """
    start, end = _resolve_period(period_start, period_end)
    page, page_size = _clamp_page(page, page_size)
    offset = (page - 1) * page_size
    window = int(window_days)
    table = qualified_table(settings, _COST_ROLLING)

    empty = _empty_page(page, page_size, start, end)
    empty["window"] = _window_block(window, None)
    empty["total_cost_usd"] = 0.0

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
        where, params = _window_where(
            scope, scope_params, window, latest_snapshot_table=table
        )

        totals_row, rows = await asyncio.gather(
            db.fetchone(
                f"""
                SELECT
                    COALESCE(SUM(cost_usd), 0) AS total_cost_usd,
                    COUNT(DISTINCT serverless_surface) AS surface_count,
                    MAX(window_start) AS window_start,
                    MAX(as_of_date) AS as_of_date
                FROM {table}
                {where}
                """,
                *params,
            ),
            db.fetchall(
                f"""
                SELECT
                    serverless_surface,
                    COALESCE(SUM(cost_usd), 0) AS cost_usd,
                    COALESCE(SUM(cost_usd_prev_window), 0) AS cost_usd_prev_window,
                    COALESCE(SUM(dbu_quantity), 0) AS dbu_quantity,
                    -- No ``COALESCE`` on this one, unlike the three lines above: eleven of
                    -- the twelve surfaces never count runs, and this is the query where
                    -- that shows. See :func:`_optional_int`. ``_order`` already sorts
                    -- ``NULLS LAST`` in both directions, so the not-counted surfaces never
                    -- outrank a real figure when the client sorts on ``runs``.
                    SUM(run_count) AS run_count,
                    COUNT(DISTINCT {_OBJECT_KEY}) AS object_count,
                    COUNT(DISTINCT workspace_id) AS workspace_count,
                    COALESCE(SUM(CASE WHEN has_object_key THEN cost_usd END), 0)
                        AS cost_usd_with_object_key
                FROM {table}
                {where}
                GROUP BY serverless_surface
                ORDER BY {_surface_sort_clause(sort, sort_direction)}
                LIMIT ? OFFSET ?
                """,
                *params,
                page_size,
                offset,
            ),
        )

        total_cost = _as_float((totals_row or {}).get("total_cost_usd")) or 0.0
        total = int((totals_row or {}).get("surface_count") or 0)

        items: list[dict[str, Any]] = []
        for row in rows:
            item = _row_to_dict(row)
            cost = _as_float(item.get("cost_usd")) or 0.0
            previous = _as_float(item.get("cost_usd_prev_window")) or 0.0
            item["cost_delta_pct"] = _pct_delta(cost, previous)
            item["share_pct"] = _share_pct(cost, total_cost)
            item["object_key_coverage_pct"] = _share_pct(
                _as_float(item.get("cost_usd_with_object_key")), cost
            )
            _normalize_prev_cost(item)
            items.append(item)

        window_block = _window_block(window, totals_row)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_cost_usd": total_cost,
            "window": window_block,
            "period": _window_period(window_block, start, end),
        }
    except Exception:
        logger.exception("serverless surfaces soft-fail")
        return empty


# --------------------------------------------------------------------------------------
# Trends
# --------------------------------------------------------------------------------------


async def fetch_serverless_cost_trend(
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
    granularity: str = "day",
    surface: str | None = None,
) -> dict[str, Any]:
    """Daily serverless cost split by surface — the top 5 plus one collapsed bucket.

    No ``window_days``: this reads the **daily** table, where the free date range is the
    filter. A trend built on a ``*_rolling`` table would be a straight line, since a
    rolling row is a single point per window.

    The 12 surfaces are collapsed to the 5 heaviest of the selected period plus
    ``OTHER_SURFACES``: a 12-series stacked chart is unreadable, and the tail is dust. The
    bucket is named ``OTHER_SURFACES`` and **not** ``OTHER`` — ``OTHER`` is one of the 12
    real surfaces, and reusing its name would add the two together under a legend that
    points at the wrong thing.

    Passing ``surface`` narrows to one surface, in which case nothing is collapsed.
    """
    start, end = _resolve_period(period_start, period_end)
    grain = _grain(granularity)
    table = qualified_table(settings, _COST_DAILY)

    empty: dict[str, Any] = {
        "items": [],
        "series": [],
        "period": _period_dict(start, end),
        "granularity": grain,
    }

    try:
        scope, params = _scope_where(
            allowed_lz_ids,
            source_lz_id,
            source_lz_ids,
            workspace_ids,
            has_lz_column=False,
            allowed_workspace_ids=allowed_workspace_ids,
            cloud_provider=cloud_provider,
        )
        if surface:
            scope.append(_SURFACE_FILTER)
            params.append(surface)
        where, where_params = _date_where(scope, params, start, end)

        # ``_TREND_TOP_SURFACES``, ``_OTHER_SURFACES_BUCKET`` and ``grain`` are all
        # server-side values — a module constant and an allowlisted enum — which is what
        # makes interpolating them into the text safe.
        rows = await db.fetchall(
            f"""
            WITH p AS (
                SELECT period_start, serverless_surface, cost_usd, dbu_quantity, run_count
                FROM {table}
                {where}
            ),
            top AS (
                SELECT serverless_surface
                FROM p
                GROUP BY serverless_surface
                ORDER BY COALESCE(SUM(cost_usd), 0) DESC NULLS LAST,
                         serverless_surface ASC
                LIMIT {_TREND_TOP_SURFACES}
            )
            SELECT
                CAST(date_trunc('{grain}', p.period_start) AS DATE) AS bucket,
                CASE
                    WHEN p.serverless_surface IN (SELECT serverless_surface FROM top)
                        THEN p.serverless_surface
                    ELSE '{_OTHER_SURFACES_BUCKET}'
                END AS serverless_surface,
                COALESCE(SUM(p.cost_usd), 0) AS cost_usd,
                COALESCE(SUM(p.dbu_quantity), 0) AS dbu_quantity,
                -- NULL-preserving, see :func:`_optional_int`. The ``OTHER_SURFACES``
                -- bucket folds several surfaces, and ``SUM`` skips NULL: a bucket mixing
                -- ``JOB`` with a not-counted surface reports ``JOB``'s runs, not a total
                -- polluted by zeros.
                SUM(p.run_count) AS run_count
            FROM p
            GROUP BY 1, 2
            ORDER BY 1 ASC, 3 DESC
            """,
            *where_params,
        )

        items = [
            {
                "bucket": _iso(row["bucket"]),
                "serverless_surface": row["serverless_surface"],
                "cost_usd": _as_float(row["cost_usd"]) or 0.0,
                "dbu_quantity": _as_float(row["dbu_quantity"]) or 0.0,
                "run_count": _optional_int(row["run_count"]),
            }
            for row in rows
        ]

        # The series list is the chart's legend, ordered by total cost over the whole
        # period — not by the last bucket, which would reshuffle the legend and the
        # colours on every refresh.
        totals: dict[str, float] = {}
        for item in items:
            name = str(item["serverless_surface"])
            totals[name] = totals.get(name, 0.0) + float(item["cost_usd"])
        series = sorted(totals, key=lambda name: (-totals[name], name))

        return {
            "items": items,
            "series": series,
            "period": _period_dict(start, end),
            "granularity": grain,
        }
    except Exception:
        logger.exception("serverless cost trend soft-fail")
        return empty


async def fetch_serverless_object_cost_trend(
    db: DatabricksWarehousePool,
    settings: Settings,
    allowed_lz_ids: list[str] | None,
    object_id: str,
    *,
    surface: str,
    period_start: date | None = None,
    period_end: date | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    workspace_ids: list[str] | None = None,
    allowed_workspace_ids: list[str] | None = None,
    cloud_provider: str | None = None,
    granularity: str = "day",
) -> dict[str, Any]:
    """Cost / DBU / run series of one serverless object.

    ``surface`` is required, not optional: ``object_id`` is only unique **within** a
    surface, and the same id can exist in several workspaces (``AI_ENDPOINT``: 251 ids for
    265 rows). The series therefore sums the workspaces in scope, and
    ``workspace_count`` says how many were folded in.

    The sentinel id yields an empty series rather than an error, like every other trend of
    this family: the 404 belongs on the detail route, and a raising trend would turn one
    absent tile into a page-wide failure.
    """
    start, end = _resolve_period(period_start, period_end)
    grain = _grain(granularity)
    table = qualified_table(settings, _COST_DAILY)

    empty: dict[str, Any] = {
        "items": [],
        "workspace_count": 0,
        "period": _period_dict(start, end),
        "granularity": grain,
    }
    if object_id == SERVERLESS_OBJECT_ID_SENTINEL:
        return empty

    try:
        scope, params = _scope_where(
            allowed_lz_ids,
            source_lz_id,
            source_lz_ids,
            workspace_ids,
            has_lz_column=False,
            allowed_workspace_ids=allowed_workspace_ids,
            cloud_provider=cloud_provider,
        )
        scope.extend([_SURFACE_FILTER, _OBJECT_ID_FILTER])
        params.extend([surface, object_id])
        where, where_params = _date_where(scope, params, start, end)

        rows = await db.fetchall(
            f"""
            SELECT
                CAST(date_trunc('{grain}', period_start) AS DATE) AS bucket,
                COALESCE(SUM(cost_usd), 0) AS cost_usd,
                COALESCE(SUM(dbu_quantity), 0) AS dbu_quantity,
                -- NULL-preserving, see :func:`_optional_int`. This route is reached with a
                -- ``surface`` in the path, so the whole series is either counted or not
                -- counted — a chart of zeros here would be a chart of a fabricated fact.
                SUM(run_count) AS run_count,
                COUNT(DISTINCT workspace_id) AS workspace_count
            FROM {table}
            {where}
            GROUP BY 1
            ORDER BY 1
            """,
            *where_params,
        )

        items = [
            {
                "bucket": _iso(row["bucket"]),
                "cost_usd": _as_float(row["cost_usd"]) or 0.0,
                "dbu_quantity": _as_float(row["dbu_quantity"]) or 0.0,
                "run_count": _optional_int(row["run_count"]),
            }
            for row in rows
        ]
        # The max over the buckets, not the last one: a workspace that stopped spending
        # mid-period still belongs to the object's history.
        workspace_count = max(
            (int(row["workspace_count"] or 0) for row in rows), default=0
        )
        return {
            "items": items,
            "workspace_count": workspace_count,
            "period": _period_dict(start, end),
            "granularity": grain,
        }
    except Exception:
        logger.exception("serverless object cost trend soft-fail for %s", object_id)
        return empty


# --------------------------------------------------------------------------------------
# Governance
# --------------------------------------------------------------------------------------


async def fetch_serverless_governance(
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
    column_filter: list[str] | None = None,
    sort: str = "cost",
    sort_direction: str = "desc",
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """Tag, budget-policy and identity coverage per (workspace, surface).

    **No ``window_days`` parameter, deliberately**: this table is a snapshot carrying its
    own ``window_start``/``window_end``, and the response reports that period so the
    figures are never captioned with a window they were not measured on. Accepting a
    window here and ignoring it would be worse than refusing it.

    ``identity_source_mix`` is stored as a ``+``-joined string by gold and returned as a
    **list** — the join character is a gold serialisation detail, not something a UI
    should have to know.
    """
    start, end = _resolve_period(period_start, period_end)
    page, page_size = _clamp_page(page, page_size)
    offset = (page - 1) * page_size
    table = qualified_table(settings, _GOVERNANCE)

    # Parsed **before** the try: an unknown column key must surface as a 422, not be
    # swallowed by the soft-fail below and answered as an empty page — which would read as
    # "no serverless spend" instead of "your filter is wrong".
    filters = parse_column_filters("serverless-governance", column_filter)

    empty = _empty_page(page, page_size, start, end)
    empty["totals"] = None
    empty["governance_period"] = None

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
        where = _scope_only_where(scope)
        filter_sql, filter_params = build_column_filter_sql(filters)
        aggregate_params = [*scope_params, *filter_params]

        totals_row, rows = await asyncio.gather(
            db.fetchone(
                f"""
                WITH p AS (
                    SELECT * FROM {table} {where}
                )
                SELECT
                    COUNT(*) AS row_count,
                    COALESCE(SUM(cost_usd), 0) AS cost_usd,
                    COALESCE(SUM(cost_usd_with_owner_tag), 0) AS cost_with_owner_tag,
                    COALESCE(SUM(cost_usd_with_cost_center_tag), 0)
                        AS cost_with_cost_center,
                    COALESCE(SUM(cost_usd_with_budget_policy), 0) AS cost_with_policy,
                    COALESCE(SUM(cost_usd_without_identity), 0) AS cost_without_identity,
                    COALESCE(SUM(cost_usd_without_object_key), 0) AS cost_without_key,
                    MIN(window_start) AS window_start,
                    MAX(window_end) AS window_end
                FROM p
                WHERE 1 = 1{filter_sql}
                """,
                *aggregate_params,
            ),
            db.fetchall(
                f"""
                WITH p AS (
                    SELECT * FROM {table} {where}
                )
                SELECT {_GOVERNANCE_ROW_COLUMNS}
                FROM p
                WHERE 1 = 1{filter_sql}
                ORDER BY {_governance_sort_clause(sort, sort_direction)}
                LIMIT ? OFFSET ?
                """,
                *aggregate_params,
                page_size,
                offset,
            ),
        )

        items = [_split_identity_mix(_row_to_dict(row)) for row in rows]
        total_cost = _as_float((totals_row or {}).get("cost_usd")) or 0.0
        without_identity = (
            _as_float((totals_row or {}).get("cost_without_identity")) or 0.0
        )

        return {
            "items": items,
            "total": int((totals_row or {}).get("row_count") or 0),
            "page": page,
            "page_size": page_size,
            "totals": {
                "cost_usd": total_cost,
                "owner_tag_coverage_pct": _share_pct(
                    _as_float((totals_row or {}).get("cost_with_owner_tag")), total_cost
                ),
                "cost_center_tag_coverage_pct": _share_pct(
                    _as_float((totals_row or {}).get("cost_with_cost_center")),
                    total_cost,
                ),
                "budget_policy_coverage_pct": _share_pct(
                    _as_float((totals_row or {}).get("cost_with_policy")), total_cost
                ),
                # Coverage, so the **complement** of the uncovered cost. Gold stores the
                # "without" side; deriving the percentage from that one column keeps the
                # two from drifting apart when a filter narrows the population.
                "identity_coverage_pct": _share_pct(
                    total_cost - without_identity, total_cost
                ),
                "cost_usd_without_identity": without_identity,
                "cost_usd_without_object_key": _as_float(
                    (totals_row or {}).get("cost_without_key")
                ),
            },
            "governance_period": {
                "from": _iso((totals_row or {}).get("window_start")),
                "to": _iso((totals_row or {}).get("window_end")),
            },
            "period": _period_dict(start, end),
        }
    except Exception:
        logger.exception("serverless governance soft-fail")
        return empty


def _split_identity_mix(item: dict[str, Any]) -> dict[str, Any]:
    """``"RUN_AS+OWNED_BY"`` → ``["RUN_AS", "OWNED_BY"]``, order preserved.

    Gold joins the mix with ``+`` because the column has to stay a merge-safe scalar. The
    order is the identity cascade's (``RUN_AS``, ``OWNED_BY``, ``CREATED_BY``, ``NONE``),
    so it carries information and must not be sorted here.
    """
    raw = item.get("identity_source_mix")
    if isinstance(raw, str):
        item["identity_source_mix"] = [part for part in raw.split("+") if part]
    elif raw is None:
        item["identity_source_mix"] = []
    return item


# --------------------------------------------------------------------------------------
# Objects
# --------------------------------------------------------------------------------------


async def fetch_serverless_objects(
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
    window_days: int = RollingWindowDays.DAY,
    surface: str | None = None,
    search: str | None = None,
    column_filter: list[str] | None = None,
    sort: str = "cost",
    sort_direction: str = "desc",
    page: int = 1,
    page_size: int = _DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """Paginated list of serverless objects for one window.

    Rows whose ``object_id`` is the gold sentinel are **kept** — they carry real cost, and
    they are 100 % of the ``GENIE``, ``NETWORKING``, ``PLATFORM_AUTO`` and ``OTHER``
    surfaces — but they are served with ``object_id: null`` and ``has_object_key: false``.
    Dropping them would make this list's total disagree with the surfaces' total; serving
    the sentinel as an id would offer a deep link that 404s.
    """
    start, end = _resolve_period(period_start, period_end)
    page, page_size = _clamp_page(page, page_size)
    offset = (page - 1) * page_size
    window = int(window_days)
    table = qualified_table(settings, _COST_ROLLING)

    # ``surface`` is passed as the legacy parameter it is: the registry declares it as
    # ``alias_param`` of the ``surface`` column, so ``?surface=JOB`` combined with
    # ``column_filter=surface:APP`` is answered 422 instead of returning the empty page
    # the two predicates would produce together. Called **before** the ``try`` so a
    # refused filter reaches the 422 handler rather than the soft-fail below.
    filters = parse_column_filters("serverless-objects", column_filter, surface=surface)

    empty = _empty_page(page, page_size, start, end)
    empty["window"] = _window_block(window, None)
    empty["total_cost_usd"] = 0.0
    empty["object_count"] = 0

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
        # No manual ``surface`` predicate here: ``parse_column_filters`` already emitted
        # it from the legacy parameter, exactly as it does for ``utilization_status`` on
        # ``clusters-overview``. Appending it again would put the same predicate on both
        # sides of the CTE — harmless in results, but it would make the SQL text lie
        # about where a filter is applied.
        where, params = _window_where(
            scope, scope_params, window, latest_snapshot_table=table
        )
        filter_sql, filter_params = build_column_filter_sql(filters)
        search_sql, search_params = _search_clause(search)
        row_filter = f"{filter_sql}{search_sql}"
        row_params = [*params, *filter_params, *search_params]

        totals_row, rows = await asyncio.gather(
            db.fetchone(
                f"""
                WITH p AS (
                    SELECT * FROM {table} {where}
                )
                SELECT
                    COUNT(*) AS row_count,
                    COALESCE(SUM(cost_usd), 0) AS total_cost_usd,
                    COUNT(DISTINCT {_OBJECT_KEY}) AS object_count,
                    MAX(window_start) AS window_start,
                    MAX(as_of_date) AS as_of_date
                FROM p
                WHERE 1 = 1{row_filter}
                """,
                *row_params,
            ),
            db.fetchall(
                f"""
                WITH p AS (
                    SELECT * FROM {table} {where}
                )
                SELECT {_ROW_COLUMNS}
                FROM p
                WHERE 1 = 1{row_filter}
                ORDER BY {_object_sort_clause(sort, sort_direction)}
                LIMIT ? OFFSET ?
                """,
                *row_params,
                page_size,
                offset,
            ),
        )

        items: list[dict[str, Any]] = []
        for row in rows:
            item = _strip_sentinel(_row_to_dict(row))
            _normalize_prev_cost(item)
            items.append(item)

        window_block = _window_block(window, totals_row)
        return {
            "items": items,
            "total": int((totals_row or {}).get("row_count") or 0),
            "page": page,
            "page_size": page_size,
            "total_cost_usd": _as_float((totals_row or {}).get("total_cost_usd")) or 0.0,
            # Rows, objects: the two differ by the sentinel rows, and a UI that shows
            # "1 234 objects" over a list of 1 259 rows has a bug the API can prevent.
            "object_count": int((totals_row or {}).get("object_count") or 0),
            "window": window_block,
            "period": _window_period(window_block, start, end),
        }
    except Exception:
        logger.exception("serverless objects soft-fail")
        return empty


async def fetch_serverless_object_detail(
    db: DatabricksWarehousePool,
    settings: Settings,
    allowed_lz_ids: list[str] | None,
    object_id: str,
    *,
    surface: str,
    period_start: date | None = None,
    period_end: date | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    workspace_ids: list[str] | None = None,
    allowed_workspace_ids: list[str] | None = None,
    cloud_provider: str | None = None,
    window_days: int = RollingWindowDays.DAY,
) -> dict[str, Any] | None:
    """One serverless object, or ``None`` when out of scope (→ 404).

    **Returns a per-workspace breakdown instead of picking the heaviest row.** The same
    ``object_id`` legitimately exists in several workspaces — 265 ``AI_ENDPOINT`` rows for
    251 distinct ids — so an ``ORDER BY cost_usd DESC LIMIT 1`` would answer with one
    workspace's figures under a title that names the object, and the difference would be
    invisible. The totals are summed over the workspaces in scope and ``workspaces``
    carries the rows that were summed.

    The **percentiles are not summed**: a percentile of a percentile is not a percentile.
    They stay on the per-workspace rows, ``max_object_p99_usd`` is the honest scalar
    (measured non-``NULL`` for ``JOB`` only), and the run-level distribution comes from the
    element-wise sum of the gold histograms.

    The sentinel id is refused outright: it is not an object, and 404 is the truthful
    answer to a request for it.
    """
    if object_id == SERVERLESS_OBJECT_ID_SENTINEL:
        return None

    start, end = _resolve_period(period_start, period_end)
    window = int(window_days)
    table = qualified_table(settings, _COST_ROLLING)

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
        object_scope = [*scope, _SURFACE_FILTER, _OBJECT_ID_FILTER]
        object_params = [*scope_params, surface, object_id]

        where, params = _window_where(
            object_scope, object_params, window, latest_snapshot_table=table
        )
        # ``cost_per_run_histogram`` is NULL on the surfaces that do not count runs;
        # excluding it here rather than around ``posexplode`` keeps the parameter order of
        # the query identical to the one above.
        hist_where, hist_params = _window_where(
            [*object_scope, "cost_per_run_histogram IS NOT NULL"],
            object_params,
            window,
            latest_snapshot_table=table,
        )
        # Every window in one query, so the detail can show 1/7/30/90 side by side. No
        # ``window_days`` predicate, but the stale-row guard stays: without it the older
        # snapshots of a stopped object would come back as current.
        windows_where = " AND ".join(
            [
                *object_scope,
                f"as_of_date = (SELECT MAX(as_of_date) FROM {table})",
            ]
        )

        rows, window_rows, hist_rows = await asyncio.gather(
            db.fetchall(
                f"""
                SELECT {_ROW_COLUMNS}, window_start, as_of_date
                FROM {table}
                {where}
                ORDER BY cost_usd DESC NULLS LAST, workspace_id ASC
                """,
                *params,
            ),
            db.fetchall(
                f"""
                SELECT
                    window_days,
                    COALESCE(SUM(cost_usd), 0) AS cost_usd,
                    COALESCE(SUM(cost_usd_prev_window), 0) AS cost_usd_prev_window,
                    COALESCE(SUM(dbu_quantity), 0) AS dbu_quantity,
                    -- NULL-preserving, see :func:`_optional_int`.
                    SUM(run_count) AS run_count
                FROM {table}
                WHERE {windows_where}
                GROUP BY window_days
                ORDER BY window_days
                """,
                *object_params,
            ),
            db.fetchall(_histogram_sql(table, hist_where), *hist_params),
        )

        if not rows:
            return None

        workspaces = [_strip_sentinel(_row_to_dict(row)) for row in rows]
        for workspace in workspaces:
            _normalize_prev_cost(workspace)

        cost = sum(_as_float(row["cost_usd"]) or 0.0 for row in rows)
        previous = sum(_as_float(row["cost_usd_prev_window"]) or 0.0 for row in rows)
        # Summed over the non-NULL rows only, and ``None`` when there is none: an object
        # whose surface does not count runs must not be credited with zero of them. This
        # also keeps ``cost_per_run_mean_usd`` below silent instead of wrong — ``if runs``
        # is falsy for ``None`` exactly as it is for ``0``. See :func:`_optional_int`.
        counted_runs = [row["run_count"] for row in rows if row["run_count"] is not None]
        runs = sum(int(value) for value in counted_runs) if counted_runs else None
        p99_values = [
            value
            for value in (_as_float(row["cost_per_run_p99_usd"]) for row in rows)
            if value is not None
        ]
        window_block = _window_block(window, rows[0])
        head = workspaces[0]

        windows = [
            {
                "window_days": int(row["window_days"]),
                "cost_usd": _as_float(row["cost_usd"]) or 0.0,
                "cost_usd_prev_window": (
                    _as_float(row["cost_usd_prev_window"])
                    if (_as_float(row["cost_usd_prev_window"]) or 0.0) > 0
                    else None
                ),
                "dbu_quantity": _as_float(row["dbu_quantity"]) or 0.0,
                "run_count": _optional_int(row["run_count"]),
            }
            for row in window_rows
        ]

        return {
            "object": {
                "serverless_surface": head.get("serverless_surface"),
                "object_id": head.get("object_id"),
                # The name can differ between workspaces; the heaviest row's name is the
                # one shown, and ``workspaces`` carries the others rather than hiding the
                # disagreement.
                "object_name": head.get("object_name"),
                "has_object_key": head.get("has_object_key"),
                "billing_origin_product": head.get("billing_origin_product"),
                "workspace_count": len({str(row["workspace_id"]) for row in rows}),
                "cloud_providers": sorted(
                    {str(row["cloud_provider"]) for row in rows if row["cloud_provider"]}
                ),
            },
            "totals": {
                "cost_usd": cost,
                "cost_usd_prev_window": previous if previous > 0 else None,
                "cost_delta_pct": _pct_delta(cost, previous),
                "dbu_quantity": sum(
                    _as_float(row["dbu_quantity"]) or 0.0 for row in rows
                ),
                "run_count": runs,
                # The **mean** cost per run, named as such: the gold percentiles below
                # are per workspace and cannot be averaged into one.
                "cost_per_run_mean_usd": (cost / runs) if runs else None,
                "max_object_p99_usd": max(p99_values) if p99_values else None,
            },
            "workspaces": workspaces,
            "windows": windows,
            "cost_per_run_histogram": _histogram_buckets(
                {
                    int(row["bucket_index"]): int(row["run_count"] or 0)
                    for row in hist_rows
                }
            ),
            "window": window_block,
            "period": _window_period(window_block, start, end),
        }
    except Exception as exc:
        logger.exception("serverless object detail failed for %s", object_id)
        # **Deliberate deviation from the family**: the other ``fetch_*_detail`` soft-fail
        # to ``None``, which the route turns into a 404 — so a warehouse outage or a
        # broken query is presented to the user as "this object does not exist", and the
        # incident is invisible. Only a genuinely absent table gets that treatment here
        # (a fresh environment where the T001d rollup has never run); anything else is
        # re-raised so the route answers 500 and the failure is seen for what it is.
        if _is_table_missing(exc, _COST_ROLLING):
            return None
        raise


# --------------------------------------------------------------------------------------
# Levers
# --------------------------------------------------------------------------------------


async def fetch_serverless_levers(
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
    window_days: int = RollingWindowDays.DAY,
) -> dict[str, Any]:
    """The three serverless levers, each measured rather than estimated.

    **No figured saving anywhere in this response, on purpose.** A serverless lever's
    gain depends on the workload's shape, and gold has no counterfactual to compare
    against — publishing "you would save X" would be inventing a number. What is
    published instead is the *exposure*: how much spend sits on each setting, and how the
    two compute forms actually compare.

    1. ``performance_target`` — population and dollars per value, ``NULL`` kept as
       ``null`` and never relabelled "standard": it is unset on 39,6 % of the serverless
       spend, and a default that Databricks may change is not something to assert here.
    2. ``cost_per_run`` — percentiles **across objects** plus the element-wise sum of the
       gold histograms, which is a genuine run-level distribution.
    3. ``dlt_comparison`` — serverless against classic on the DLT updates, per cloud,
       with a minimum population before any rate is published.
    """
    start, end = _resolve_period(period_start, period_end)
    window = int(window_days)
    table = qualified_table(settings, _COST_ROLLING)

    empty: dict[str, Any] = {
        "performance_target": {"items": [], "total_cost_usd": 0.0, "unset_share_pct": None},
        "cost_per_run": None,
        "dlt_comparison": None,
        "window": _window_block(window, None),
        "period": _period_dict(start, end),
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
        where, params = _window_where(
            scope, scope_params, window, latest_snapshot_table=table
        )
        # ``run_count > 0`` in the scope rather than around the percentile: dividing by a
        # zero ``run_count`` yields NULL in Spark, which ``percentile_approx`` skips — the
        # figure would be right, and the ``object_count`` next to it wrong.
        per_run_where, per_run_params = _window_where(
            [*scope, "run_count > 0"], scope_params, window, latest_snapshot_table=table
        )
        hist_where, hist_params = _window_where(
            [*scope, "cost_per_run_histogram IS NOT NULL"],
            scope_params,
            window,
            latest_snapshot_table=table,
        )

        target_rows, per_run_row, hist_rows, bounds_row = await asyncio.gather(
            db.fetchall(
                f"""
                SELECT
                    performance_target,
                    COALESCE(SUM(cost_usd), 0) AS cost_usd,
                    COALESCE(SUM(dbu_quantity), 0) AS dbu_quantity,
                    -- NULL-preserving, see :func:`_optional_int`. This aggregate runs on
                    -- the plain window scope, **not** on ``per_run_where``: it spans every
                    -- surface, so a ``performance_target`` group made only of not-counted
                    -- surfaces must report no run count rather than zero runs.
                    SUM(run_count) AS run_count,
                    COUNT(DISTINCT {_OBJECT_KEY}) AS object_count,
                    COUNT(*) AS row_count
                FROM {table}
                {where}
                GROUP BY performance_target
                ORDER BY 2 DESC NULLS LAST
                """,
                *params,
            ),
            db.fetchone(
                f"""
                SELECT
                    COUNT(*) AS object_count,
                    -- The one ``COALESCE(SUM(run_count), 0)`` kept in this module, and it
                    -- is kept because it cannot fire: ``per_run_where`` carries
                    -- ``run_count > 0``, so every row of this aggregate has a counted run
                    -- and the sum is never NULL. It stays as the statement that zero
                    -- *would* be true here — the opposite of every other site, where the
                    -- scope admits rows gold never counted. See :func:`_optional_int`.
                    COALESCE(SUM(run_count), 0) AS run_count,
                    percentile_approx(cost_usd / run_count, 0.5) AS p50_usd,
                    percentile_approx(cost_usd / run_count, 0.9) AS p90_usd,
                    percentile_approx(cost_usd / run_count, 0.99) AS p99_usd,
                    MAX(cost_usd / run_count) AS max_usd,
                    MAX(cost_per_run_p99_usd) AS max_object_p99_usd
                FROM {table}
                {per_run_where}
                """,
                *per_run_params,
            ),
            db.fetchall(_histogram_sql(table, hist_where), *hist_params),
            db.fetchone(
                f"""
                SELECT MAX(window_start) AS window_start, MAX(as_of_date) AS as_of_date
                FROM {table}
                {where}
                """,
                *params,
            ),
        )

        target_total = sum(_as_float(row["cost_usd"]) or 0.0 for row in target_rows)
        target_items: list[dict[str, Any]] = []
        unset_cost = 0.0
        for row in target_rows:
            item = _row_to_dict(row)
            cost = _as_float(item.get("cost_usd")) or 0.0
            item["share_pct"] = _share_pct(cost, target_total)
            if item.get("performance_target") is None:
                unset_cost += cost
            target_items.append(item)

        per_run = None
        if per_run_row and int(per_run_row.get("object_count") or 0) > 0:
            per_run = {
                "object_count": int(per_run_row["object_count"]),
                "run_count": int(per_run_row["run_count"] or 0),
                "p50_usd": _as_float(per_run_row["p50_usd"]),
                "p90_usd": _as_float(per_run_row["p90_usd"]),
                "p99_usd": _as_float(per_run_row["p99_usd"]),
                "max_usd": _as_float(per_run_row["max_usd"]),
                # Gold's own per-object p99, non-NULL for ``JOB`` only: a well-defined
                # worst case, unlike a percentile of percentiles.
                "max_object_p99_usd": _as_float(per_run_row["max_object_p99_usd"]),
                "histogram": _histogram_buckets(
                    {
                        int(row["bucket_index"]): int(row["run_count"] or 0)
                        for row in hist_rows
                    }
                ),
            }

        window_block = _window_block(window, bounds_row)
        comparison = await _dlt_comparison_block(
            db,
            settings,
            scope=scope,
            scope_params=scope_params,
            window_start=(bounds_row or {}).get("window_start"),
            as_of_date=(bounds_row or {}).get("as_of_date"),
        )

        return {
            "performance_target": {
                "items": target_items,
                "total_cost_usd": target_total,
                "unset_share_pct": _share_pct(unset_cost, target_total),
            },
            "cost_per_run": per_run,
            "dlt_comparison": comparison,
            "window": window_block,
            "period": _window_period(window_block, start, end),
        }
    except Exception:
        logger.exception("serverless levers soft-fail")
        return empty


async def _dlt_comparison_block(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    scope: list[str],
    scope_params: list[Any],
    window_start: Any,
    as_of_date: Any,
) -> dict[str, Any] | None:
    """Serverless against classic DLT: failure rate, duration, failure concentration.

    Four rules, each one there because its absence produced a wrong figure in dev:

    1. **The denominator is the request, not the update.** ``RETRY_ON_FAILURE`` is a
       trigger type of its own, so a failure that was later recovered counts twice —
       ``FAILED`` weighs 1 770 classic updates for 886 requests. Only the last attempt of
       each ``request_id`` is kept (:data:`_LAST_ATTEMPT_RANK`).
    2. **The window comes from gold, never from ``today``.** The bounds are the caller's
       ``window_start``/``as_of_date`` as read from ``serverless_cost_rolling``: a pipeline
       run late by a day would otherwise have the comparison cover days the cost figures
       above do not (R5). Without bounds there is no comparison — ``None``, not a
       full-history figure silently captioned with the window.
    3. **Split by cloud, with a population floor.** Azure classic DLT is 6 requests over
       30 days; its 2 failures render as 33,33 % next to a serverless rate resting on
       thousands, and the page would announce that classic fails 5,6× more on azure out of
       two rows. Below :data:`_MIN_COMPARISON_REQUESTS` the rate is ``None`` and
       ``comparable`` is ``false`` — the counts are still served, because "6 requests" is
       the useful answer here.
    4. **Durations on completed runs only.** A failed update stops when it fails, so
       including it measures how fast things break, not how long the work takes.

    Plus the concentration, which is what turns a rate into an action: if the top
    :data:`_TOP_FAILING_PIPELINES` pipelines carry most of the failures, the answer is to
    fix those pipelines, not to change compute form.
    """
    if not window_start or not as_of_date:
        return None

    table = qualified_table(settings, _UPDATE_STATS)
    # ``as_of_date`` is a day and ``update_start_time`` a timestamp: an inclusive upper
    # bound on the day would drop everything that ran after midnight of that day, so the
    # comparison is bounded by the **start of the next day**, exclusive.
    upper = as_of_date + timedelta(days=1) if isinstance(as_of_date, date) else as_of_date

    conditions = [*scope, "update_start_time >= ?", "update_start_time < ?"]
    params = [*scope_params, window_start, upper]
    where = "WHERE " + " AND ".join(conditions)
    last_attempt = f"""
        WITH ranked AS (
            SELECT
                cloud_provider, workspace_id, request_id, pipeline_id, compute_type,
                result_state, duration_sec,
                {_LAST_ATTEMPT_RANK} AS attempt_rank
            FROM {table}
            {where}
        ),
        last_try AS (
            SELECT * FROM ranked WHERE attempt_rank = 1
        )
    """

    try:
        outcome_rows, concentration_rows = await asyncio.gather(
            db.fetchall(
                f"""
                {last_attempt}
                SELECT
                    cloud_provider,
                    compute_type,
                    COUNT(*) AS requests,
                    SUM(
                        CASE WHEN UPPER(result_state) IN ({_quoted(_OUTCOME_STATES)})
                             THEN 1 ELSE 0 END
                    ) AS outcome_requests,
                    SUM(
                        CASE WHEN UPPER(result_state) = '{_FAILED_STATE}'
                             THEN 1 ELSE 0 END
                    ) AS failed_requests,
                    SUM(
                        CASE WHEN UPPER(result_state) = '{_CANCELED_STATE}'
                             THEN 1 ELSE 0 END
                    ) AS canceled_requests,
                    percentile_approx(
                        CASE WHEN UPPER(result_state) = '{_COMPLETED_STATE}'
                             THEN duration_sec END,
                        0.5
                    ) AS duration_p50_sec,
                    percentile_approx(
                        CASE WHEN UPPER(result_state) = '{_COMPLETED_STATE}'
                             THEN duration_sec END,
                        0.95
                    ) AS duration_p95_sec,
                    COUNT(DISTINCT pipeline_id) AS pipeline_count
                FROM last_try
                GROUP BY cloud_provider, compute_type
                ORDER BY cloud_provider, compute_type
                """,
                *params,
            ),
            db.fetchall(
                f"""
                {last_attempt},
                failures AS (
                    SELECT cloud_provider, compute_type, pipeline_id,
                           COUNT(*) AS failed_requests
                    FROM last_try
                    WHERE UPPER(result_state) = '{_FAILED_STATE}'
                    GROUP BY cloud_provider, compute_type, pipeline_id
                ),
                ranked_failures AS (
                    SELECT
                        cloud_provider, compute_type, failed_requests,
                        ROW_NUMBER() OVER (
                            PARTITION BY cloud_provider, compute_type
                            ORDER BY failed_requests DESC, pipeline_id ASC
                        ) AS failure_rank,
                        SUM(failed_requests) OVER (
                            PARTITION BY cloud_provider, compute_type
                        ) AS total_failed_requests
                    FROM failures
                )
                SELECT
                    cloud_provider,
                    compute_type,
                    MAX(total_failed_requests) AS failed_requests,
                    COALESCE(
                        SUM(
                            CASE WHEN failure_rank <= {_TOP_FAILING_PIPELINES}
                                 THEN failed_requests END
                        ),
                        0
                    ) AS top_failed_requests,
                    COUNT(*) AS failing_pipeline_count
                FROM ranked_failures
                GROUP BY cloud_provider, compute_type
                """,
                *params,
            ),
        )
    except Exception:
        logger.exception("serverless DLT comparison soft-fail")
        return None

    concentration = {
        (str(row["cloud_provider"]), str(row["compute_type"])): row
        for row in concentration_rows
    }

    items: list[dict[str, Any]] = []
    for row in outcome_rows:
        key = (str(row["cloud_provider"]), str(row["compute_type"]))
        outcome = int(row["outcome_requests"] or 0)
        failed = int(row["failed_requests"] or 0)
        comparable = outcome >= _MIN_COMPARISON_REQUESTS
        conc = concentration.get(key)
        top_failed = int((conc or {}).get("top_failed_requests") or 0)
        items.append(
            {
                "cloud_provider": row["cloud_provider"],
                "compute_type": row["compute_type"],
                "requests": int(row["requests"] or 0),
                "outcome_requests": outcome,
                "failed_requests": failed,
                "canceled_requests": int(row["canceled_requests"] or 0),
                # ``None`` below the floor, never a rate the reader would compare anyway.
                "failure_rate_pct": _share_pct(failed, outcome) if comparable else None,
                "comparable": comparable,
                "duration_p50_sec": _as_float(row["duration_p50_sec"]),
                "duration_p95_sec": _as_float(row["duration_p95_sec"]),
                "pipeline_count": int(row["pipeline_count"] or 0),
                "failing_pipeline_count": int((conc or {}).get("failing_pipeline_count") or 0),
                "failure_concentration_pct": _share_pct(top_failed, failed),
            }
        )

    if not items:
        return None
    return {
        "items": items,
        "min_requests": _MIN_COMPARISON_REQUESTS,
        "top_failing_pipelines": _TOP_FAILING_PIPELINES,
        "window": {"from": _iso(window_start), "to": _iso(as_of_date)},
    }
