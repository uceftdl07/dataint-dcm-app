"""Per-column filters and distinct values for the compute and Lakeflow list views.

Three rules hold everywhere in this module, and they are the whole point of it:

1. **SQL text only ever comes from this file.** A client sends a column *key*; the key
   is looked up in :data:`FILTERABLE_COLUMNS` and the predicate that comes back was
   written here. An unknown key raises :class:`ColumnFilterError` — it never reaches a
   query as free text. Same pattern as ``_OVERVIEW_SORT_COLUMNS`` for ``ORDER BY``.
2. **Every client value is bound.** ``?`` placeholders only, for every kind of column.
3. **The allowlist is indexed by (view, column), never by column alone.** Seven keys
   repeat across the ``ComputeClusters`` tabs and five across the
   ``ComputeSqlWarehouses`` tabs with a *different* expression each time: ``cost`` is
   ``c.cost_usd`` on ``clusters-overview`` (a join) and ``cost_usd`` on
   ``clusters-cost`` (a single table). A global index would resolve ``cost`` to
   whichever view was registered last, and the predicate would name a table absent
   from the query — a SQL error at best, the wrong column at worst.

The predicate of every column that aliases a legacy query parameter is transcribed
**verbatim** from the ad-hoc block it replaces, so folding the legacy parameters into
this mechanism cannot change the SQL a request produces. That is why two views that
filter "the same" concept sometimes carry different text — ``failure`` is
``COALESCE(p.failure_rate_pct, 0) >= ?`` on the warehouse overview (outer join, a
missing performance row must not pass the filter) and ``failure_rate_pct >= ?`` on the
query-performance tab (single table). Both are what the code did before.

``sql`` is a *predicate*, not a bare column expression: the comparison lives in the
allowlist too. That is what lets ``lakeflow-jobs`` compare its success rates with
``<=`` — on a success rate the useful threshold is the low one ("show me what fails") —
without the UI having to know, or be able to choose, the operator.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from ...auth.scope_model import AllowedScope, canonical_workspace_sql
from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_table
from .compute_metrics_common import (
    _WAREHOUSE_UTILIZATION_ROLLING,
    _resolve_period,
    _scope_where,
    _window_where,
)
from .lakeflow_overview import _resolve_period as _lakeflow_resolve_period
from .lakeflow_overview import _scope_where as _lakeflow_scope_where

__all__ = [
    "AppliedFilter",
    "ColumnFilterError",
    "ColumnFilterSpec",
    "FILTERABLE_COLUMNS",
    "build_column_filter_sql",
    "cache_key_column_filters",
    "column_filter_predicates",
    "fetch_filter_options",
    "fetch_lakeflow_filter_options",
    "needs_last_run",
    "parse_column_filters",
]

logger = logging.getLogger(__name__)

FilterKind = Literal["enum", "text", "numeric"]
ValueCase = Literal["as_is", "lower", "upper"]

_DEFAULT_OPTIONS_LIMIT = 50
_MAX_OPTIONS_LIMIT = 200

# Gold sources of the option lists. Same strings as the service modules that own the
# views (``compute_metrics_clusters``, ``compute_metrics_warehouses``,
# ``compute_metrics_recommendations``, ``lakeflow_jobs``) — spelled again here rather
# than imported because those modules import *this* one.
# ``_WAREHOUSE_UTILIZATION_ROLLING`` is the exception, and it is imported above instead:
# it is declared in ``compute_metrics_common`` precisely because several modules key the
# same decision off that one table, and this module is now one of them.
_CLUSTER_COST_ROLLING = "gold_dbx_compute_cluster_cost_rolling"
_CLUSTER_EFFICIENCY_ROLLING = "gold_dbx_compute_cluster_efficiency_rolling"
_CLUSTER_GOVERNANCE = "gold_dbx_compute_cluster_governance"
_WAREHOUSE_COST_ROLLING = "gold_dbx_compute_warehouse_cost_rolling"
_WAREHOUSE_QUERY_PERF_ROLLING = "gold_dbx_compute_warehouse_query_performance_rolling"
_WAREHOUSE_SLOW_QUERIES = "warehouse_slow_queries"
_RECOMMENDATIONS = "gold_dbx_compute_recommendations"
_SERVERLESS_COST_ROLLING = "gold_dbx_compute_serverless_cost_rolling"
_SERVERLESS_GOVERNANCE = "gold_dbx_compute_serverless_governance"
_WORKFLOW_RUNS = "gold_dbx_workflow_runs"
_WORKFLOW_SUCCESS = "gold_dbx_workflow_success_rate"
_WORKSPACE_DIM = "dim_dbx_workspace"

# How the option list is scoped, per column. ``window`` = the caller's scope AND the
# asked ``window_days``; ``snapshot`` = scope only (the source carries no window);
# ``dated`` = scope AND the period, for the two statement/run-level sources.
OptionScope = Literal["window", "window_latest", "snapshot", "dated"]


class ColumnFilterError(ValueError):
    """A column filter the server refuses to guess at — always answered with a 422.

    Rejecting is the point: a filter silently dropped, or arbitrated between two
    contradicting parameters, shows a filtered-looking table that is not filtered the
    way the user asked.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class FilterChoice:
    """One value of a derived enum, with the predicate it stands for.

    Used where the displayed column is not a stored value but a test on one —
    ``spill_query_count > 0``, ``autoscale_enabled``, ``has_owner_tag``. The predicate
    carries no placeholder: the *value* selects it, nothing is bound.
    """

    value: str
    label: str
    sql: str


@dataclass(frozen=True)
class ColumnFilterSpec:
    """Everything the server is willing to filter on, for one column of one view."""

    key: str
    kind: FilterKind
    label: str
    #: Predicate applied to the view's own query, with one ``?`` per bound value.
    sql: str = ""
    #: How many times the bound value repeats in :attr:`sql` (``text`` spans columns).
    placeholders: int = 1
    #: ``numeric`` only — the thresholds the server declares. The UI offers these and
    #: nothing else: only the server knows what expression the threshold applies to.
    options: tuple[float, ...] = ()
    #: ``enum`` only, when the value is a test rather than a stored value.
    choices: tuple[FilterChoice, ...] = ()
    #: ``enum`` only — the closed set of stored values, when the server knows it
    #: statically. Left empty for the columns whose values come from the data
    #: (``warehouse_size``, ``billing_origin_product``…): the backend cannot enumerate
    #: those, so a value it does not recognise is not necessarily wrong. Where it *is*
    #: knowable, the check is what stops a misspelling from being answered with a
    #: plausible empty page. Must contain any :attr:`overrides` value, since it is
    #: verified before them.
    allowed: tuple[str, ...] = ()
    #: ``enum`` only — values whose predicate differs from :attr:`sql` (``ZOMBIE`` is
    #: a flag on the efficiency table, not a ``utilization_status`` value).
    overrides: tuple[tuple[str, str], ...] = ()
    #: Case folding applied to the bound value, matching what :attr:`sql` wraps it in.
    case: ValueCase = "as_is"
    #: Legacy query parameter this column also drives, if any.
    alias_param: str | None = None
    #: Value the legacy parameter stands for when it is a bare ``True``.
    alias_true_value: str | None = None
    #: Set when the legacy parameter is a list: its ``IN (…)`` predicate cannot be
    #: folded into a mono-value filter, so the two are only checked for contradiction.
    alias_is_list: bool = False
    #: ``lakeflow-jobs`` only: the ``last_*`` columns are literal NULLs unless the
    #: last-run CTE is built, so filtering on them must force it.
    needs_last_run: bool = False
    #: Option list — source table, expression, and how to label a value.
    option_table: str | None = None
    option_scope: OptionScope = "window"
    value_sql: str | None = None
    label_sql: str | None = None
    #: The option query LEFT JOINs the workspace dimension to name an id.
    needs_workspace_dim: bool = False


@dataclass(frozen=True)
class AppliedFilter:
    """A parsed, validated filter: allowlisted predicate plus its bound values."""

    spec: ColumnFilterSpec
    value: str
    sql: str
    params: tuple[Any, ...] = field(default_factory=tuple)


def _workspace_dim_cte(table: str) -> str:
    """One row per workspace, keyed the way the gold tables spell workspace ids."""
    return (
        f"SELECT {canonical_workspace_sql('workspace_id')} AS workspace_key, "
        "MAX(workspace_name) AS workspace_name "
        f"FROM {table} "
        "WHERE workspace_id IS NOT NULL "
        "GROUP BY 1"
    )


def _workspace_spec(alias: str, *, table: str, option_scope: OptionScope) -> ColumnFilterSpec:
    """The ``workspace`` column, which every list view spells the same way.

    The predicate is on the **id** and the label on the name: a workspace name is a
    display string that the dimension may not carry, while the id is what the gold
    row is keyed by. Both sides go through ``canonical_workspace_sql`` so the Azure
    ``adb-`` variant and the bare id are the same workspace here, as everywhere else.
    """
    return ColumnFilterSpec(
        key="workspace",
        kind="enum",
        label="Workspace",
        sql=f"{canonical_workspace_sql(f'{alias}.workspace_id')} = ?",
        option_table=table,
        option_scope=option_scope,
        value_sql=canonical_workspace_sql("t.workspace_id"),
        label_sql="COALESCE(ws.workspace_name, t.workspace_id)",
        needs_workspace_dim=True,
    )


def _unqualified_workspace_spec(*, table: str, option_scope: OptionScope) -> ColumnFilterSpec:
    """:func:`_workspace_spec` for a view that filters **inside a CTE**.

    Same column, same canonicalization, one difference: the predicate carries no table
    alias. The serverless views apply their filters to a ``WITH p AS (SELECT * FROM …)``
    projection, so a qualified ``c.workspace_id`` would either fail to resolve or, worse,
    tie this registry to the alias a service module happens to use in its SQL text.
    """
    return ColumnFilterSpec(
        key="workspace",
        kind="enum",
        label="Workspace",
        sql=f"{canonical_workspace_sql('workspace_id')} = ?",
        option_table=table,
        option_scope=option_scope,
        value_sql=canonical_workspace_sql("t.workspace_id"),
        label_sql="COALESCE(ws.workspace_name, t.workspace_id)",
        needs_workspace_dim=True,
    )


def _numeric(
    key: str,
    label: str,
    sql: str,
    options: tuple[float, ...],
    *,
    alias_param: str | None = None,
    needs_last_run: bool = False,
) -> ColumnFilterSpec:
    return ColumnFilterSpec(
        key=key,
        kind="numeric",
        label=label,
        sql=sql,
        options=options,
        alias_param=alias_param,
        needs_last_run=needs_last_run,
    )


def _text(
    key: str,
    label: str,
    sql: str,
    placeholders: int,
    *,
    alias_param: str | None = None,
    option_table: str | None = None,
    option_scope: OptionScope = "window",
    value_sql: str | None = None,
) -> ColumnFilterSpec:
    return ColumnFilterSpec(
        key=key,
        kind="text",
        label=label,
        sql=sql,
        placeholders=placeholders,
        alias_param=alias_param,
        option_table=option_table,
        option_scope=option_scope,
        value_sql=value_sql,
    )


def _enum(
    key: str,
    label: str,
    sql: str,
    *,
    case: ValueCase = "as_is",
    allowed: tuple[str, ...] = (),
    overrides: tuple[tuple[str, str], ...] = (),
    alias_param: str | None = None,
    alias_is_list: bool = False,
    needs_last_run: bool = False,
    option_table: str | None = None,
    option_scope: OptionScope = "window",
    value_sql: str | None = None,
) -> ColumnFilterSpec:
    return ColumnFilterSpec(
        key=key,
        kind="enum",
        label=label,
        sql=sql,
        case=case,
        allowed=allowed,
        overrides=overrides,
        alias_param=alias_param,
        alias_is_list=alias_is_list,
        needs_last_run=needs_last_run,
        option_table=option_table,
        option_scope=option_scope,
        value_sql=value_sql,
    )


def _derived_enum(
    key: str,
    label: str,
    choices: tuple[FilterChoice, ...],
    *,
    alias_param: str | None = None,
    alias_true_value: str | None = None,
) -> ColumnFilterSpec:
    return ColumnFilterSpec(
        key=key,
        kind="enum",
        label=label,
        choices=choices,
        alias_param=alias_param,
        alias_true_value=alias_true_value,
    )


_COST_THRESHOLDS = (1.0, 10.0, 100.0, 1000.0)
_QUERY_THRESHOLDS = (1.0, 100.0, 1000.0, 10000.0)
_LATENCY_MS_THRESHOLDS = (1000.0, 5000.0, 30000.0)
_PCT_THRESHOLDS = (10.0, 25.0, 50.0, 75.0, 90.0)
_DURATION_S_THRESHOLDS = (60.0, 600.0, 3600.0)
_RETRY_THRESHOLDS = (1.0, 3.0, 10.0)
_DBU_THRESHOLDS = (1.0, 100.0, 1000.0, 10000.0)
_RUN_THRESHOLDS = (1.0, 100.0, 1000.0, 10000.0)
# A serverless run is cheap, so ``_COST_THRESHOLDS`` would offer four choices that all
# return nearly the same page. Measured in dev on 2026-09-10 over the 30-day window,
# 3 689 objects with at least one run: p50 = **0,156 $** per run, p90 = 1,24 $,
# p99 = 37,83 $, max 672,56 $. These four edges cut that population into usable slices
# (414 objects under a cent, 3 205 under a dollar, 73 at 10 $ or more).
_COST_PER_RUN_THRESHOLDS = (0.01, 0.1, 1.0, 10.0)
# Not ``_RETRY_THRESHOLDS`` reused for its shape: a ``>= 10`` edge would select **1** of
# the 1 316 governance couples. Measured in dev on 2026-09-10, `budget_policy_count`
# maxes out at 11 and the population thins fast — ≥ 1: 145 couples, ≥ 2: 37, ≥ 3: 23,
# ≥ 5: 10. These four edges are the ones that still return a page worth reading.
_POLICY_COUNT_THRESHOLDS = (1.0, 2.0, 3.0, 5.0)


# --------------------------------------------------------------------------------------
# The allowlist. 13 views, 112 filterable columns — the 11 views / 88 columns of the
# inventory in ``specs/023-colonnes-et-filtres-compute/contracts/compute-column-filters.md``
# plus the two serverless views of ``specs/025-serverless-compute-page`` (15 + 9).
# Columns are declared in the order the page shows them, which is also the order the
# predicates are emitted in.
# --------------------------------------------------------------------------------------

_CLUSTERS_OVERVIEW: tuple[ColumnFilterSpec, ...] = (
    _workspace_spec("c", table=_CLUSTER_COST_ROLLING, option_scope="window"),
    _text(
        "cluster",
        "Cluster",
        "(LOWER(c.cluster_name) LIKE ? OR LOWER(c.cluster_id) LIKE ?)",
        2,
        option_table=_CLUSTER_COST_ROLLING,
        value_sql="COALESCE(t.cluster_name, t.cluster_id)",
    ),
    _enum(
        "cluster_type",
        "Type",
        "UPPER(c.cluster_type) = ?",
        case="upper",
        option_table=_CLUSTER_COST_ROLLING,
        value_sql="UPPER(t.cluster_type)",
    ),
    _numeric("cost", "Cost", "c.cost_usd >= ?", _COST_THRESHOLDS),
    # The column renders ``utilization_status`` as a badge, so the filter is on the
    # status and not on a percentage. Alias of the ``utilization_status`` parameter,
    # whose predicate on this view has no ZOMBIE special case — unlike the efficiency
    # tab, where the flag lives.
    _enum(
        "utilization",
        "Utilization",
        "UPPER(e.utilization_status) = ?",
        case="upper",
        alias_param="utilization_status",
        option_table=_CLUSTER_EFFICIENCY_ROLLING,
        value_sql="UPPER(t.utilization_status)",
    ),
    _enum(
        "governance",
        "Governance",
        "UPPER(g.severity) = ?",
        case="upper",
        option_table=_CLUSTER_GOVERNANCE,
        option_scope="snapshot",
        value_sql="UPPER(t.severity)",
    ),
)

_CLUSTERS_COST: tuple[ColumnFilterSpec, ...] = (
    _workspace_spec("c", table=_CLUSTER_COST_ROLLING, option_scope="window"),
    _text(
        "cluster",
        "Cluster",
        "(LOWER(c.cluster_name) LIKE ? OR LOWER(c.cluster_id) LIKE ?)",
        2,
        alias_param="search",
        option_table=_CLUSTER_COST_ROLLING,
        value_sql="COALESCE(t.cluster_name, t.cluster_id)",
    ),
    _enum(
        "cluster_type",
        "Type",
        "UPPER(c.cluster_type) = ?",
        case="upper",
        option_table=_CLUSTER_COST_ROLLING,
        value_sql="UPPER(t.cluster_type)",
    ),
    _enum(
        "sku_group",
        "SKU group",
        "LOWER(c.sku_group) = ?",
        case="lower",
        alias_param="sku_group",
        option_table=_CLUSTER_COST_ROLLING,
        value_sql="LOWER(t.sku_group)",
    ),
    _numeric("cost", "Cost", "c.cost_usd >= ?", _COST_THRESHOLDS),
    _numeric("dbu", "DBU", "c.dbu_quantity >= ?", (10.0, 100.0, 1000.0)),
)

_CLUSTERS_EFFICIENCY: tuple[ColumnFilterSpec, ...] = (
    _workspace_spec("e", table=_CLUSTER_EFFICIENCY_ROLLING, option_scope="window"),
    _text(
        "cluster",
        "Cluster",
        "(LOWER(e.cluster_name) LIKE ? OR LOWER(e.cluster_id) LIKE ?)",
        2,
        option_table=_CLUSTER_EFFICIENCY_ROLLING,
        value_sql="COALESCE(t.cluster_name, t.cluster_id)",
    ),
    _enum(
        "cluster_type",
        "Type",
        "UPPER(e.cluster_type) = ?",
        case="upper",
        option_table=_CLUSTER_EFFICIENCY_ROLLING,
        value_sql="UPPER(t.cluster_type)",
    ),
    _enum(
        "driver_node",
        "Driver node",
        "e.driver_node_type = ?",
        option_table=_CLUSTER_EFFICIENCY_ROLLING,
        value_sql="t.driver_node_type",
    ),
    _enum(
        "worker_node",
        "Worker node",
        "e.worker_node_type = ?",
        option_table=_CLUSTER_EFFICIENCY_ROLLING,
        value_sql="t.worker_node_type",
    ),
    _derived_enum(
        "autoscaling",
        "Autoscaling",
        (
            FilterChoice("enabled", "Enabled", "e.autoscale_enabled = true"),
            FilterChoice("fixed", "Fixed", "COALESCE(e.autoscale_enabled, false) = false"),
        ),
    ),
    # Alias of ``utilization_status``, ZOMBIE included: the legacy parameter answers
    # that value with the efficiency flag, not with a status comparison.
    _enum(
        "status",
        "Status",
        "UPPER(e.utilization_status) = ?",
        case="upper",
        overrides=(("ZOMBIE", "e.is_zombie = true"),),
        alias_param="utilization_status",
        option_table=_CLUSTER_EFFICIENCY_ROLLING,
        value_sql="UPPER(t.utilization_status)",
    ),
    # ``configured_worker_count`` is what the column displays: the sizing asked for,
    # not the observed maximum.
    _numeric("nodes", "Nodes", "e.configured_worker_count >= ?", (1.0, 2.0, 8.0, 32.0)),
    _numeric(
        "cluster_lifetime",
        "Cluster lifetime",
        "e.uptime_hours >= ?",
        (1.0, 8.0, 24.0, 168.0),
    ),
    _numeric("idle", "Idle", "e.idle_pct >= ?", (25.0, 50.0, 75.0, 90.0)),
    _numeric("cpu_avg", "CPU avg", "e.cpu_util_avg_pct >= ?", _PCT_THRESHOLDS),
    _numeric("cpu_p95", "CPU p95", "e.cpu_util_p95_pct >= ?", _PCT_THRESHOLDS),
    _numeric("mem_avg", "Mem avg", "e.mem_util_avg_pct >= ?", _PCT_THRESHOLDS),
    _numeric("mem_p95", "Mem p95", "e.mem_util_p95_pct >= ?", _PCT_THRESHOLDS),
    _enum(
        "recommended_node",
        "Recommended node",
        "e.recommended_node_type = ?",
        option_table=_CLUSTER_EFFICIENCY_ROLLING,
        value_sql="t.recommended_node_type",
    ),
    _numeric(
        "estimated_savings",
        "Estimated savings",
        "e.estimated_savings_usd >= ?",
        (1.0, 10.0, 100.0),
    ),
)

_CLUSTERS_GOVERNANCE: tuple[ColumnFilterSpec, ...] = (
    _text(
        "cluster",
        "Cluster",
        "(LOWER(cluster_name) LIKE ? OR LOWER(cluster_id) LIKE ?)",
        2,
        option_table=_CLUSTER_GOVERNANCE,
        option_scope="snapshot",
        value_sql="COALESCE(t.cluster_name, t.cluster_id)",
    ),
    # The gold column is a boolean, so the option list is Present / Absent rather than
    # the tag values — there are none to list.
    _derived_enum(
        "owner_tag",
        "Owner tag",
        (
            FilterChoice("present", "Present", "has_owner_tag = true"),
            FilterChoice("absent", "Absent", "COALESCE(has_owner_tag, false) = false"),
        ),
    ),
    _derived_enum(
        "cost_center_tag",
        "Cost center tag",
        (
            FilterChoice("present", "Present", "has_cost_center_tag = true"),
            FilterChoice(
                "absent", "Absent", "COALESCE(has_cost_center_tag, false) = false"
            ),
        ),
    ),
    _enum(
        "dbr",
        "DBR",
        "dbr_version = ?",
        option_table=_CLUSTER_GOVERNANCE,
        option_scope="snapshot",
        value_sql="t.dbr_version",
    ),
    _enum(
        "severity",
        "Severity",
        "UPPER(severity) = ?",
        case="upper",
        alias_param="severity",
        option_table=_CLUSTER_GOVERNANCE,
        option_scope="snapshot",
        value_sql="UPPER(t.severity)",
    ),
)

_WAREHOUSES_OVERVIEW: tuple[ColumnFilterSpec, ...] = (
    _workspace_spec("c", table=_WAREHOUSE_COST_ROLLING, option_scope="window_latest"),
    # Not an alias of ``search``: that parameter also looks into the size, the
    # workspace id and the workspace name, so folding it here would narrow it.
    _text(
        "warehouse",
        "Warehouse",
        "(LOWER(c.warehouse_name) LIKE ? OR LOWER(c.warehouse_id) LIKE ?)",
        2,
        option_table=_WAREHOUSE_COST_ROLLING,
        option_scope="window_latest",
        value_sql="COALESCE(t.warehouse_name, t.warehouse_id)",
    ),
    _enum(
        "size",
        "Size",
        "LOWER(c.warehouse_size) = ?",
        case="lower",
        alias_param="warehouse_size",
        option_table=_WAREHOUSE_COST_ROLLING,
        option_scope="window_latest",
        value_sql="LOWER(t.warehouse_size)",
    ),
    # Filters the *folded* type of the ``sw`` CTE, not the raw gold column, so the filter
    # selects exactly what the Type cell shows. Deliberately **no** ``allowed``, unlike
    # ``surface`` below: that column's twelve values are ones *we* assign in gold, whereas
    # ``warehouse_type`` is Databricks' own vocabulary and it is open — SERVERLESS, PRO and
    # CLASSIC carry the estate, and curated dev also holds one ``REAL_TIME`` (measured
    # 2026-09-11). An allowlist here would be a second, staler declaration of a list the
    # option query already reads from the data: the dropdown would offer a value the
    # validator then answers with a 422. Same treatment as ``cluster_type`` and
    # ``severity``, the other Databricks-declared enums on these views.
    _enum(
        "type",
        "Type",
        "UPPER(sw.warehouse_type) = ?",
        case="upper",
        option_table=_WAREHOUSE_UTILIZATION_ROLLING,
        option_scope="window_latest",
        value_sql="UPPER(t.warehouse_type)",
    ),
    _numeric("cost", "Cost", "c.cost_usd >= ?", _COST_THRESHOLDS),
    _numeric("queries", "Queries", "c.query_count >= ?", _QUERY_THRESHOLDS),
    # ``COALESCE`` on purpose: the performance row is LEFT JOINed, and a warehouse
    # without one must not pass a "failure rate at least 1 %" filter.
    _numeric(
        "failure",
        "Failure rate",
        "COALESCE(p.failure_rate_pct, 0) >= ?",
        (1.0, 5.0, 10.0, 25.0),
        alias_param="min_failure_rate_pct",
    ),
    _numeric("latency", "Latency p95", "p.latency_p95_ms >= ?", _LATENCY_MS_THRESHOLDS),
)

_WAREHOUSES_COST: tuple[ColumnFilterSpec, ...] = (
    _text(
        "warehouse",
        "Warehouse",
        "(LOWER(warehouse_name) LIKE ? OR LOWER(warehouse_id) LIKE ?)",
        2,
        alias_param="search",
        option_table=_WAREHOUSE_COST_ROLLING,
        option_scope="window_latest",
        value_sql="COALESCE(t.warehouse_name, t.warehouse_id)",
    ),
    _enum(
        "size",
        "Size",
        "LOWER(warehouse_size) = ?",
        case="lower",
        alias_param="warehouse_size",
        option_table=_WAREHOUSE_COST_ROLLING,
        option_scope="window_latest",
        value_sql="LOWER(t.warehouse_size)",
    ),
    _numeric("dbu", "DBU", "dbu_quantity >= ?", (10.0, 100.0, 1000.0)),
    _numeric("cost", "Cost", "cost_usd >= ?", _COST_THRESHOLDS),
    _numeric("queries", "Queries", "query_count >= ?", _QUERY_THRESHOLDS),
    _numeric(
        "cost_per_query", "Cost / query", "cost_per_query_usd >= ?", (0.01, 0.1, 1.0)
    ),
)

_WAREHOUSES_QUERY_PERFORMANCE: tuple[ColumnFilterSpec, ...] = (
    _text(
        "warehouse",
        "Warehouse",
        "(LOWER(warehouse_name) LIKE ? OR LOWER(warehouse_id) LIKE ?)",
        2,
        option_table=_WAREHOUSE_QUERY_PERF_ROLLING,
        option_scope="window_latest",
        value_sql="COALESCE(t.warehouse_name, t.warehouse_id)",
    ),
    _numeric("queries", "Queries", "query_count >= ?", _QUERY_THRESHOLDS),
    _numeric(
        "failure",
        "Failure rate",
        "failure_rate_pct >= ?",
        (1.0, 5.0, 10.0, 25.0),
        alias_param="min_failure_rate_pct",
    ),
    _numeric("p50", "p50", "latency_p50_ms >= ?", _LATENCY_MS_THRESHOLDS),
    _numeric(
        "p95",
        "p95",
        "latency_p95_ms >= ?",
        _LATENCY_MS_THRESHOLDS,
        alias_param="min_latency_p95_ms",
    ),
    _numeric("p99", "p99", "latency_p99_ms >= ?", _LATENCY_MS_THRESHOLDS),
    _numeric("queue", "Queue p95", "queue_time_p95_ms >= ?", (100.0, 1000.0, 10000.0)),
    _derived_enum(
        "spill",
        "Spill",
        (
            FilterChoice("with", "With spill", "spill_query_count > 0"),
            FilterChoice("without", "Without spill", "COALESCE(spill_query_count, 0) = 0"),
        ),
        alias_param="has_spill",
        alias_true_value="with",
    ),
    _numeric("cache", "Cache hit", "cache_hit_pct >= ?", (25.0, 50.0, 75.0)),
)

_WAREHOUSES_SLOW_QUERIES: tuple[ColumnFilterSpec, ...] = (
    _text(
        "warehouse",
        "Warehouse",
        "(LOWER(warehouse_name) LIKE ? OR LOWER(warehouse_id) LIKE ?)",
        2,
        option_table=_WAREHOUSE_SLOW_QUERIES,
        option_scope="dated",
        value_sql="COALESCE(t.warehouse_name, t.warehouse_id)",
    ),
    _enum(
        "user",
        "User",
        "executed_by = ?",
        option_table=_WAREHOUSE_SLOW_QUERIES,
        option_scope="dated",
        value_sql="t.executed_by",
    ),
    _enum(
        "status",
        "Status",
        "UPPER(status) = ?",
        case="upper",
        option_table=_WAREHOUSE_SLOW_QUERIES,
        option_scope="dated",
        value_sql="UPPER(t.status)",
    ),
    _enum(
        "reason",
        "Reason",
        "UPPER(reason) = ?",
        case="upper",
        alias_param="reason",
        option_table=_WAREHOUSE_SLOW_QUERIES,
        option_scope="dated",
        value_sql="UPPER(t.reason)",
    ),
    _numeric("duration", "Duration", "duration_ms >= ?", (30000.0, 300000.0, 1800000.0)),
)

_RECOMMENDATIONS_COLUMNS: tuple[ColumnFilterSpec, ...] = (
    # Not an alias of ``search``: that parameter also looks into the title.
    _text(
        "object",
        "Object",
        "(LOWER(object_name) LIKE ? OR LOWER(object_id) LIKE ?)",
        2,
        option_table=_RECOMMENDATIONS,
        option_scope="snapshot",
        value_sql="COALESCE(t.object_name, t.object_id)",
    ),
    _enum(
        "category",
        "Category",
        "UPPER(category) = ?",
        case="upper",
        alias_param="category",
        option_table=_RECOMMENDATIONS,
        option_scope="snapshot",
        value_sql="UPPER(t.category)",
    ),
    _text(
        "title",
        "Title",
        "LOWER(title) LIKE ?",
        1,
        option_table=_RECOMMENDATIONS,
        option_scope="snapshot",
        value_sql="t.title",
    ),
    _enum(
        "severity",
        "Severity",
        "UPPER(severity) = ?",
        case="upper",
        alias_param="severity",
        option_table=_RECOMMENDATIONS,
        option_scope="snapshot",
        value_sql="UPPER(t.severity)",
    ),
    _numeric("savings", "Savings", "estimated_savings_usd >= ?", _COST_THRESHOLDS),
    _enum(
        "status",
        "Status",
        "UPPER(status) = ?",
        case="upper",
        alias_param="status",
        option_table=_RECOMMENDATIONS,
        option_scope="snapshot",
        value_sql="UPPER(t.status)",
    ),
)

_LAKEFLOW_JOBS: tuple[ColumnFilterSpec, ...] = (
    _enum(
        "status",
        "Status",
        "LOWER(last_status) = ?",
        case="lower",
        alias_param="status",
        alias_is_list=True,
        needs_last_run=True,
        option_table=_WORKFLOW_RUNS,
        option_scope="dated",
        value_sql="LOWER(t.status)",
    ),
    _text(
        "alpha",
        "Job",
        "(LOWER(workflow_name) LIKE ? OR CAST(workflow_id AS STRING) LIKE ?)",
        2,
        alias_param="search",
        option_table=_WORKFLOW_SUCCESS,
        option_scope="dated",
        value_sql="COALESCE(t.workflow_name, CAST(t.workflow_id AS STRING))",
    ),
    _numeric(
        "success", "Success rate", "success_rate_pct <= ?", (99.0, 95.0, 90.0, 50.0)
    ),
    _numeric(
        "success_24h",
        "Success 24h",
        "success_rate_24h_pct <= ?",
        (99.0, 95.0, 90.0, 50.0),
    ),
    _numeric(
        "success_7d", "Success 7d", "success_rate_7d_pct <= ?", (99.0, 95.0, 90.0, 50.0)
    ),
    _numeric("runs", "Runs", "COALESCE(terminal_runs, 0) >= ?", (1.0, 10.0, 100.0)),
    _numeric("duration", "Avg duration", "avg_duration_seconds >= ?", _DURATION_S_THRESHOLDS),
    _numeric("p50", "p50", "p50 >= ?", _DURATION_S_THRESHOLDS),
    _numeric("p95", "p95", "p95 >= ?", _DURATION_S_THRESHOLDS),
    _numeric("p99", "p99", "p99 >= ?", _DURATION_S_THRESHOLDS),
    # Same expression as the ``wait`` sort: queue time and schedule lag are one wait.
    _numeric(
        "wait",
        "Wait",
        "(COALESCE(avg_queued_duration_seconds, 0) + "
        "COALESCE(avg_schedule_lag_seconds, 0)) >= ?",
        (10.0, 60.0, 600.0),
    ),
    _numeric("retries", "Retries", "COALESCE(avg_retry_count, 0) >= ?", _RETRY_THRESHOLDS),
    _enum(
        "trigger",
        "Trigger",
        "last_trigger_type = ?",
        alias_param="trigger_type",
        alias_is_list=True,
        needs_last_run=True,
        option_table=_WORKFLOW_RUNS,
        option_scope="dated",
        value_sql="t.trigger_type",
    ),
    _enum(
        "run_type",
        "Run type",
        "last_run_type = ?",
        needs_last_run=True,
        option_table=_WORKFLOW_RUNS,
        option_scope="dated",
        value_sql="t.run_type",
    ),
    _numeric(
        "last_duration",
        "Last duration",
        "last_duration_seconds >= ?",
        _DURATION_S_THRESHOLDS,
        needs_last_run=True,
    ),
)

_LAKEFLOW_JOB_RUNS: tuple[ColumnFilterSpec, ...] = (
    _enum(
        "status",
        "Status",
        "LOWER(status) = ?",
        case="lower",
        alias_param="status",
        alias_is_list=True,
        option_table=_WORKFLOW_RUNS,
        option_scope="dated",
        value_sql="LOWER(t.status)",
    ),
    _enum(
        "run_type",
        "Run type",
        "run_type = ?",
        option_table=_WORKFLOW_RUNS,
        option_scope="dated",
        value_sql="t.run_type",
    ),
    _enum(
        "trigger",
        "Trigger",
        "trigger_type = ?",
        alias_param="trigger_type",
        alias_is_list=True,
        option_table=_WORKFLOW_RUNS,
        option_scope="dated",
        value_sql="t.trigger_type",
    ),
    _numeric("duration", "Duration", "duration_seconds >= ?", _DURATION_S_THRESHOLDS),
    _numeric("lag", "Lag", "schedule_lag_seconds >= ?", _DURATION_S_THRESHOLDS),
    _numeric("retries", "Retries", "COALESCE(retry_count, 0) >= ?", _RETRY_THRESHOLDS),
    _numeric("tasks", "Tasks", "tasks_total >= ?", (1.0, 5.0, 20.0)),
)


#: The 12 values ``serverless_surface`` can hold. Spelled here rather than imported:
#: ``compute_metrics_serverless`` imports this module, so reading
#: :class:`~app.api.services.compute_metrics_serverless.ServerlessSurface` from here would
#: close an import cycle. ``test_the_surface_filter_accepts_exactly_the_declared_surfaces``
#: is what keeps the two lists equal.
_SERVERLESS_SURFACE_VALUES: tuple[str, ...] = (
    "JOB",
    "DLT_PIPELINE",
    "MV_ST_REFRESH",
    "SQL_WAREHOUSE",
    "NOTEBOOK",
    "APP",
    "AI_ENDPOINT",
    "LAKEBASE",
    "GENIE",
    "NETWORKING",
    "PLATFORM_AUTO",
    "OTHER",
)


_SERVERLESS_OBJECTS: tuple[ColumnFilterSpec, ...] = (
    _unqualified_workspace_spec(
        table=_SERVERLESS_COST_ROLLING, option_scope="window_latest"
    ),
    # Alias of the ``surface`` query parameter, which FastAPI validates against
    # ``ServerlessSurface``. That validation does **not** reach here, though: a value
    # arriving as ``column_filter=surface:…`` is parsed by this module alone, so without
    # ``allowed`` a misspelling would build ``serverless_surface = 'SQL_WAREHOUSSE'`` and
    # answer an empty page — "no serverless SQL warehouse in your perimeter", the opposite
    # of the truth. ``case="upper"`` for the same reason: ``surface:job`` is a legitimate
    # spelling of a value gold stores uppercase.
    _enum(
        "surface",
        "Surface",
        "serverless_surface = ?",
        case="upper",
        allowed=_SERVERLESS_SURFACE_VALUES,
        alias_param="surface",
        option_table=_SERVERLESS_COST_ROLLING,
        option_scope="window_latest",
        value_sql="t.serverless_surface",
    ),
    # Not an alias of ``search``: that parameter looks into the id as well, and on these
    # views the id is often all there is.
    _text(
        "object",
        "Object",
        "(LOWER(object_name) LIKE ? OR LOWER(object_id) LIKE ?)",
        2,
        option_table=_SERVERLESS_COST_ROLLING,
        option_scope="window_latest",
        value_sql="COALESCE(t.object_name, t.object_id)",
    ),
    _enum(
        "product",
        "Billing product",
        "billing_origin_product = ?",
        option_table=_SERVERLESS_COST_ROLLING,
        option_scope="window_latest",
        value_sql="t.billing_origin_product",
    ),
    # The option list comes from the data and therefore does **not** offer a "standard"
    # choice for the unset value: ``performance_target`` is NULL on a large share of the
    # spend, and naming that NULL would assert a default Databricks can change.
    _enum(
        "performance_target",
        "Performance target",
        "UPPER(performance_target) = ?",
        case="upper",
        option_table=_SERVERLESS_COST_ROLLING,
        option_scope="window_latest",
        value_sql="UPPER(t.performance_target)",
    ),
    _text(
        "identity",
        "Identity",
        "LOWER(identity_principal) LIKE ?",
        1,
        option_table=_SERVERLESS_COST_ROLLING,
        option_scope="window_latest",
        value_sql="t.identity_principal",
    ),
    _enum(
        "identity_source",
        "Identity source",
        "identity_source = ?",
        option_table=_SERVERLESS_COST_ROLLING,
        option_scope="window_latest",
        value_sql="t.identity_source",
    ),
    _numeric("cost", "Cost", "cost_usd >= ?", _COST_THRESHOLDS),
    _numeric("dbu", "DBU", "dbu_quantity >= ?", _DBU_THRESHOLDS),
    _numeric("runs", "Runs", "COALESCE(run_count, 0) >= ?", _RUN_THRESHOLDS),
    _numeric(
        "cost_per_run",
        "Cost per run",
        "cost_per_run_p50_usd >= ?",
        _COST_PER_RUN_THRESHOLDS,
    ),
    _derived_enum(
        "budget_policy",
        "Budget policy",
        (
            FilterChoice("with", "With policy", "budget_policy_id IS NOT NULL"),
            FilterChoice("without", "Without policy", "budget_policy_id IS NULL"),
        ),
    ),
    # The three booleans below are asymmetric on purpose, exactly like ``has_owner_tag``
    # on ``clusters-tags``: the positive half is a bare ``= true`` and the negative half
    # goes through ``COALESCE(…, false)``. A NULL flag is not evidence of tagging, so it
    # belongs on the "absent" side — and the two halves still partition the population,
    # which they would not if both sides were bare (``NOT NULL`` is NULL). Measured in
    # dev on 2026-09-10: the three columns carry **0 NULL on 87 067 rows**, so the
    # COALESCE changes nothing today; it is there so that the day the T001d builder
    # gains a branch that can leave one unset, the rows do not silently vanish from both
    # halves at once.
    _derived_enum(
        "tags",
        "Custom tags",
        (
            FilterChoice("with", "Tagged", "has_custom_tags = true"),
            FilterChoice("without", "Untagged", "COALESCE(has_custom_tags, false) = false"),
        ),
    ),
    # The one filter that exposes the gold sentinel as a *property* rather than as an id:
    # ``without`` selects the rows the API serves with ``object_id: null``.
    _derived_enum(
        "object_key",
        "Object key",
        (
            FilterChoice("with", "Identified object", "has_object_key = true"),
            FilterChoice("without", "No object key", "COALESCE(has_object_key, false) = false"),
        ),
    ),
    # One choice, not two: "not in the top" is the default page, so offering it would be
    # offering a filter that filters nothing anyone asked for.
    _derived_enum(
        "top_cost",
        "Top cost",
        (FilterChoice("yes", "Top cost", "is_top_cost = true"),),
    ),
)

_SERVERLESS_GOVERNANCE_COLUMNS: tuple[ColumnFilterSpec, ...] = (
    # ``snapshot``: this table has no ``window_days``, so a windowed option query would
    # bind a parameter no column can take.
    _unqualified_workspace_spec(
        table=_SERVERLESS_GOVERNANCE, option_scope="snapshot"
    ),
    # No ``alias_param`` here, unlike ``serverless-objects``: the governance route has no
    # ``surface`` query parameter, and declaring an alias for a parameter that does not
    # exist would announce a folding this view can never perform.
    _enum(
        "surface",
        "Surface",
        "serverless_surface = ?",
        case="upper",
        allowed=_SERVERLESS_SURFACE_VALUES,
        option_table=_SERVERLESS_GOVERNANCE,
        option_scope="snapshot",
        value_sql="t.serverless_surface",
    ),
    _numeric("cost", "Cost", "cost_usd >= ?", _COST_THRESHOLDS),
    # Coverage thresholds are ``<=``, not ``>=``: on a governance page the useful
    # question is "show me what is *not* covered", the same way the Lakeflow view
    # filters on ``success_rate_pct <= ?``.
    _numeric(
        "owner_tag", "Owner tag", "owner_tag_coverage_pct <= ?", _PCT_THRESHOLDS
    ),
    _numeric(
        "cost_center_tag",
        "Cost center tag",
        "cost_center_tag_coverage_pct <= ?",
        _PCT_THRESHOLDS,
    ),
    _numeric(
        "budget_policy",
        "Budget policy",
        "budget_policy_coverage_pct <= ?",
        _PCT_THRESHOLDS,
    ),
    _numeric("identity", "Identity", "identity_coverage_pct <= ?", _PCT_THRESHOLDS),
    _numeric(
        "policy_count",
        "Distinct policies",
        "COALESCE(budget_policy_count, 0) >= ?",
        _POLICY_COUNT_THRESHOLDS,
    ),
    # ``cost_usd_without_identity`` carries 0 NULL on the 1 316 snapshot rows, but the
    # COALESCE stays: this is the one filter whose *negative* half is the interesting
    # answer ("fully owned"), and a NULL there would put a couple into neither half.
    # Measured in dev on 2026-09-10: 271 of 1 316 couples carry unowned spend, for
    # 22 464,37 $ of 1 036 222,34 $ — **2,17 %** of the serverless dollars have no
    # identity at all.
    _derived_enum(
        "unowned",
        "Unowned spend",
        (
            FilterChoice(
                "yes", "Has unowned spend", "COALESCE(cost_usd_without_identity, 0) > 0"
            ),
            FilterChoice("no", "Fully owned", "COALESCE(cost_usd_without_identity, 0) = 0"),
        ),
    ),
)


def _by_key(specs: tuple[ColumnFilterSpec, ...]) -> dict[str, ColumnFilterSpec]:
    return {spec.key: spec for spec in specs}


FILTERABLE_COLUMNS: dict[str, dict[str, ColumnFilterSpec]] = {
    "clusters-overview": _by_key(_CLUSTERS_OVERVIEW),
    "clusters-cost": _by_key(_CLUSTERS_COST),
    "clusters-efficiency": _by_key(_CLUSTERS_EFFICIENCY),
    "clusters-governance": _by_key(_CLUSTERS_GOVERNANCE),
    "warehouses-overview": _by_key(_WAREHOUSES_OVERVIEW),
    "warehouses-cost": _by_key(_WAREHOUSES_COST),
    "warehouses-query-performance": _by_key(_WAREHOUSES_QUERY_PERFORMANCE),
    "warehouses-slow-queries": _by_key(_WAREHOUSES_SLOW_QUERIES),
    "recommendations": _by_key(_RECOMMENDATIONS_COLUMNS),
    "lakeflow-jobs": _by_key(_LAKEFLOW_JOBS),
    "lakeflow-job-runs": _by_key(_LAKEFLOW_JOB_RUNS),
    "serverless-objects": _by_key(_SERVERLESS_OBJECTS),
    "serverless-governance": _by_key(_SERVERLESS_GOVERNANCE_COLUMNS),
}

_LAKEFLOW_VIEWS = frozenset({"lakeflow-jobs", "lakeflow-job-runs"})


# --------------------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------------------


def _view_columns(view: str) -> dict[str, ColumnFilterSpec]:
    columns = FILTERABLE_COLUMNS.get(view)
    if columns is None:
        accepted = ", ".join(sorted(FILTERABLE_COLUMNS))
        raise ColumnFilterError(f"Unknown filter view '{view}'. Accepted views: {accepted}")
    return columns


def _spec(view: str, key: str) -> ColumnFilterSpec:
    columns = _view_columns(view)
    spec = columns.get(key)
    if spec is None:
        accepted = ", ".join(sorted(columns))
        raise ColumnFilterError(
            f"Unknown filter column '{key}' for view '{view}'. "
            f"Accepted columns: {accepted}"
        )
    return spec


def _cased(value: str, case: ValueCase) -> str:
    if case == "lower":
        return value.lower()
    if case == "upper":
        return value.upper()
    return value


def _build(spec: ColumnFilterSpec, raw: str) -> AppliedFilter:
    """Turn one allowlisted key and one client value into a bound predicate."""
    value = raw.strip()

    if spec.kind == "numeric":
        try:
            number = float(value)
        except ValueError as exc:
            raise ColumnFilterError(
                f"Filter '{spec.key}' takes a number, got '{value}'."
            ) from exc
        return AppliedFilter(spec=spec, value=value, sql=spec.sql, params=(number,))

    if spec.kind == "text":
        pattern = f"%{value.lower()}%"
        return AppliedFilter(
            spec=spec,
            value=value,
            sql=spec.sql,
            params=tuple([pattern] * spec.placeholders),
        )

    if spec.choices:
        for choice in spec.choices:
            if choice.value.lower() == value.lower():
                # The value selects the predicate; nothing is bound, because the
                # column is a test on a boolean, not a stored value.
                return AppliedFilter(spec=spec, value=choice.value, sql=choice.sql)
        accepted = ", ".join(choice.value for choice in spec.choices)
        raise ColumnFilterError(
            f"Filter '{spec.key}' takes one of: {accepted} — got '{value}'."
        )

    normalized = _cased(value, spec.case)
    if spec.allowed and normalized not in spec.allowed:
        accepted = ", ".join(spec.allowed)
        raise ColumnFilterError(
            f"Filter '{spec.key}' takes one of: {accepted} — got '{value}'."
        )
    for override_value, override_sql in spec.overrides:
        if normalized.upper() == override_value.upper():
            return AppliedFilter(spec=spec, value=normalized, sql=override_sql)
    return AppliedFilter(spec=spec, value=normalized, sql=spec.sql, params=(normalized,))


def _legacy_value(spec: ColumnFilterSpec, raw: Any) -> str | None:
    """The value a legacy parameter stands for, in the form a column filter takes."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        # ``has_spill=False`` is "no filter", not "without spill": the parameter has
        # always been opt-in.
        return spec.alias_true_value if raw else None
    if isinstance(raw, list | tuple):
        values = [str(item).strip() for item in raw if str(item).strip()]
        return values[0] if len(values) == 1 else None
    text = str(raw).strip()
    return text or None


def parse_column_filters(
    view: str,
    raw: list[str] | None,
    **legacy: Any,
) -> list[AppliedFilter]:
    """Validate ``column_filter=<key>:<value>`` pairs and fold in the legacy params.

    Returns the filters in the order the view declares its columns, so the predicates
    of the legacy parameters keep the order — and therefore the SQL text — they had
    before this mechanism existed.

    Raises :class:`ColumnFilterError` (answered as a 422) on an unknown view, an
    unknown column, a repeated column, a value the column cannot take, and on a
    legacy parameter contradicting the column filter that drives the same predicate.
    A rejected request is the point: silently dropping one of two contradicting
    filters shows a table the user cannot reason about.
    """
    columns = _view_columns(view)
    requested: dict[str, str] = {}

    for item in raw or []:
        if not item or not item.strip():
            continue
        key, separator, value = item.partition(":")
        if not separator:
            raise ColumnFilterError(
                f"Malformed filter '{item}': expected '<column>:<value>'."
            )
        key = key.strip()
        spec = _spec(view, key)
        if not value.strip():
            # An emptied combo sends ``key:`` — that is "no filter", not "match ''".
            continue
        if key in requested:
            raise ColumnFilterError(
                f"Filter '{key}' given twice for view '{view}'. "
                "This iteration takes one value per column."
            )
        # The value keeps every ``:`` past the first: a job or warehouse name may
        # contain one, a column key never does.
        requested[spec.key] = value

    applied: list[AppliedFilter] = []
    for key, spec in columns.items():
        asked = requested.get(key)
        legacy_raw = legacy.get(spec.alias_param) if spec.alias_param else None
        from_legacy = _legacy_value(spec, legacy_raw) if spec.alias_param else None

        if asked is not None and from_legacy is not None:
            # Compared on the built predicate *and* its values, not on the values
            # alone: two choices of a derived enum bind nothing at all, so
            # ``spill:without`` against ``has_spill=True`` would otherwise read as
            # agreement and apply the wrong one of the two.
            asked_built, legacy_built = _build(spec, asked), _build(spec, from_legacy)
            if (asked_built.sql, asked_built.params) != (
                legacy_built.sql,
                legacy_built.params,
            ):
                raise ColumnFilterError(
                    f"'{spec.alias_param}={from_legacy}' contradicts "
                    f"'column_filter={key}:{asked.strip()}'. Send one or the other."
                )
        if asked is not None and spec.alias_is_list:
            _check_list_alias(spec, asked, legacy_raw)

        # The legacy value wins when both are present and agree: its predicate is the
        # one the view has always produced, and both build to the same SQL anyway.
        chosen = from_legacy if from_legacy is not None else asked
        if chosen is None:
            continue
        if spec.alias_is_list and legacy_raw:
            # The ``IN (…)`` predicate of the list parameter stays where it is; adding
            # the mono-value predicate on top would only narrow what it already covers.
            continue
        applied.append(_build(spec, chosen))

    return applied


def _check_list_alias(spec: ColumnFilterSpec, asked: str, legacy_raw: Any) -> None:
    """A multi-value legacy parameter must at least contain the column filter's value.

    ``status=[SUCCESS]`` with ``column_filter=status:FAILED`` can only return nothing.
    Answering 422 says which two inputs disagree; an empty page would not.
    """
    if not isinstance(legacy_raw, list | tuple) or not legacy_raw:
        return
    values = {str(item).strip().lower() for item in legacy_raw if str(item).strip()}
    if values and asked.strip().lower() not in values:
        raise ColumnFilterError(
            f"'{spec.alias_param}={sorted(values)}' contradicts "
            f"'column_filter={spec.key}:{asked.strip()}'. Send one or the other."
        )


def column_filter_predicates(
    filters: list[AppliedFilter],
) -> tuple[list[str], list[Any]]:
    """The predicates and their bound values, for a caller that builds its own WHERE."""
    predicates = [item.sql for item in filters]
    params: list[Any] = []
    for item in filters:
        params.extend(item.params)
    return predicates, params


def build_column_filter_sql(filters: list[AppliedFilter]) -> tuple[str, list[Any]]:
    """``(" AND …", params)`` — the form the list queries append to ``WHERE 1 = 1``."""
    predicates, params = column_filter_predicates(filters)
    clause = (" AND " + " AND ".join(predicates)) if predicates else ""
    return clause, params


def cache_key_column_filters(filters: list[AppliedFilter]) -> list[str] | None:
    """The filters as a canonical ``key:value`` list, for a response cache key.

    Normalized, not the raw strings: ``size:MEDIUM`` and ``size:medium`` are one filter
    and must share an entry, while two different filters must never read each other's.
    ``None`` when nothing is filtered, so an unfiltered request keeps the key it had.
    """
    if not filters:
        return None
    return [f"{item.spec.key}:{item.value}" for item in filters]


def needs_last_run(filters: list[AppliedFilter]) -> bool:
    """Whether any filter reads a ``last_*`` column of the ``lakeflow-jobs`` view.

    Those columns are ``CAST(NULL AS …)`` literals unless the last-run CTE is built,
    so a filter on one of them would compare against NULL and return nothing at all.
    """
    return any(item.spec.needs_last_run for item in filters)


# --------------------------------------------------------------------------------------
# Distinct values
# --------------------------------------------------------------------------------------


def _clamp_limit(limit: int | None) -> int:
    if limit is None:
        return _DEFAULT_OPTIONS_LIMIT
    return max(1, min(int(limit), _MAX_OPTIONS_LIMIT))


def _declared_options(spec: ColumnFilterSpec) -> dict[str, Any]:
    """The answer for the columns whose values the server declares rather than reads.

    Numeric thresholds and derived booleans have no distinct values to count: only the
    server knows what expression a threshold applies to, and ``Present`` / ``Absent``
    are two halves of a boolean, not two stored strings. Returned without ``count`` so
    the UI cannot present a number it would have had to invent.
    """
    if spec.kind == "numeric":
        options = [
            {"value": _clean_number(value), "label": _threshold_label(spec, value)}
            for value in spec.options
        ]
    else:
        options = [{"value": choice.value, "label": choice.label} for choice in spec.choices]
    return {"kind": spec.kind, "label": spec.label, "options": options, "truncated": False}


def _clean_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _threshold_label(spec: ColumnFilterSpec, value: float) -> str:
    operator = "≤" if "<=" in spec.sql else "≥"
    return f"{operator} {_clean_number(value)}"


async def _fetch_options_rows(
    db: DatabricksWarehousePool,
    spec: ColumnFilterSpec,
    *,
    source: str,
    dim_table: str,
    where: str,
    params: list[Any],
    q: str | None,
    limit: int,
) -> dict[str, Any]:
    """Distinct values of one column over the view's scope, with their row counts."""
    value_sql = spec.value_sql or ""
    label_sql = spec.label_sql or value_sql
    join = ""
    if spec.needs_workspace_dim:
        join = (
            f"LEFT JOIN ({_workspace_dim_cte(dim_table)}) ws "
            f"ON ws.workspace_key = {canonical_workspace_sql('t.workspace_id')}"
        )

    search_params: list[Any] = []
    search_clause = ""
    if q and q.strip():
        pattern = f"%{q.strip().lower()}%"
        search_clause = (
            f" AND (LOWER(CAST({value_sql} AS STRING)) LIKE ? "
            f"OR LOWER(CAST({label_sql} AS STRING)) LIKE ?)"
        )
        search_params = [pattern, pattern]

    if spec.kind == "text" and not (q and q.strip()):
        # A free-text column can carry thousands of distinct values — the dev estate
        # counts 1 824 warehouses. Rather than hand back an arbitrary 50 the user would
        # take for the whole list, say the list is truncated and let them type.
        count_row = await db.fetchone(
            f"SELECT COUNT(DISTINCT {value_sql}) AS n FROM {source} t {join} {where}",
            *params,
        )
        distinct = int((count_row or {}).get("n") or 0)
        if distinct > limit:
            return {
                "kind": spec.kind,
                "label": spec.label,
                "options": [],
                "truncated": True,
            }

    rows = await db.fetchall(
        f"""
        SELECT {value_sql} AS value, {label_sql} AS label, COUNT(*) AS n
        FROM {source} t
        {join}
        {where}{search_clause}
        GROUP BY {value_sql}, {label_sql}
        HAVING {value_sql} IS NOT NULL
        ORDER BY n DESC, 1 ASC
        LIMIT ?
        """,
        *params,
        *search_params,
        limit + 1,
    )

    truncated = len(rows) > limit
    options = [
        {
            "value": str(row.get("value")),
            "label": str(row.get("label") if row.get("label") is not None else row.get("value")),
            "count": int(row.get("n") or 0),
        }
        for row in rows[:limit]
    ]
    return {
        "kind": spec.kind,
        "label": spec.label,
        "options": options,
        "truncated": truncated,
    }


def _empty_options(spec: ColumnFilterSpec, *, enabled: bool = True) -> dict[str, Any]:
    """No value to offer. ``enabled=False`` when the source could not be read at all.

    Mirrors the ``enabled`` flag ``fetch_warehouse_slow_queries`` already sends when its
    table is absent — in dev, ``warehouse_slow_queries`` is not deployed, and without
    this the combo of its four columns would read as "no value in your perimeter"
    instead of "this list cannot be built". Omitted when everything worked, exactly as
    the other list routes omit it.
    """
    answer = {"kind": spec.kind, "label": spec.label, "options": [], "truncated": False}
    return answer if enabled else {**answer, "enabled": False}


async def fetch_filter_options(
    db: DatabricksWarehousePool,
    settings: Settings,
    view: str,
    column: str,
    *,
    q: str | None = None,
    limit: int | None = None,
    window_days: int = 1,
    allowed_lz_ids: list[str] | None = None,
    allowed_workspace_ids: list[str] | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    workspace_ids: list[str] | None = None,
    cloud_provider: str | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> dict[str, Any]:
    """Distinct values offered for one column of one compute view.

    Applies the **scope** of the view — allowed perimeter, ``cloud_provider``,
    ``window_days``, and the period for the sources dated by a timestamp — and
    **no** ``column_filter``: the list describes the perimeter, not the current
    selection. Otherwise setting one filter would empty the lists of every other
    column, and the user could no longer widen what they just narrowed.
    """
    spec = _spec(view, column)
    payload = {"view": view, "column": column}

    if spec.kind == "numeric" or spec.choices:
        return {**payload, **_declared_options(spec)}
    if spec.option_table is None:
        return {**payload, **_empty_options(spec)}

    start, end = _resolve_period(period_start, period_end)
    source = qualified_table(settings, spec.option_table)
    dim_table = qualified_table(settings, _WORKSPACE_DIM)
    scope, scope_params = _scope_where(
        allowed_lz_ids,
        source_lz_id,
        source_lz_ids,
        workspace_ids,
        has_lz_column=False,
        allowed_workspace_ids=allowed_workspace_ids,
        cloud_provider=cloud_provider,
    )

    if spec.option_scope in ("window", "window_latest"):
        where, params = _window_where(
            scope,
            scope_params,
            int(window_days),
            latest_snapshot_table=source if spec.option_scope == "window_latest" else None,
        )
    elif spec.option_scope == "dated":
        conditions = [*scope, "CAST(start_time AS DATE) >= ?", "CAST(start_time AS DATE) <= ?"]
        where = "WHERE " + " AND ".join(conditions)
        params = [*scope_params, start, end]
    else:
        where = ("WHERE " + " AND ".join(scope)) if scope else ""
        params = list(scope_params)

    try:
        return {
            **payload,
            **await _fetch_options_rows(
                db,
                spec,
                source=source,
                dim_table=dim_table,
                where=where,
                params=params,
                q=q,
                limit=_clamp_limit(limit),
            ),
        }
    except Exception:
        # Same soft-fail as the list views: an empty combo, not a broken page.
        logger.exception("filter options soft-fail view=%s column=%s", view, column)
        return {**payload, **_empty_options(spec, enabled=False)}


async def fetch_lakeflow_filter_options(
    db: DatabricksWarehousePool,
    settings: Settings,
    scope: AllowedScope,
    view: str,
    column: str,
    *,
    q: str | None = None,
    limit: int | None = None,
    window: str = "30d",
    start_date: date | None = None,
    end_date: date | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    workspace_ids: list[str] | None = None,
    workflow_id: str | None = None,
) -> dict[str, Any]:
    """Same answer shape for the two Lakeflow views, with their own scope helper.

    A twin route rather than one handler for the eleven compute views: the Lakeflow tables are
    scoped by ``AllowedScope`` on the workspace dimension alone, the compute ones by
    the landing-zone/workspace pair. Merging both into a single dependency chain would
    hide which perimeter a given answer was computed in.
    """
    if view not in _LAKEFLOW_VIEWS:
        accepted = ", ".join(sorted(_LAKEFLOW_VIEWS))
        raise ColumnFilterError(
            f"View '{view}' is not a Lakeflow view. Accepted views: {accepted}"
        )
    spec = _spec(view, column)
    payload = {"view": view, "column": column}

    if spec.kind == "numeric" or spec.choices:
        return {**payload, **_declared_options(spec)}
    if spec.option_table is None:
        return {**payload, **_empty_options(spec)}

    _key, start, end = _lakeflow_resolve_period(window, start_date, end_date)
    source = qualified_table(settings, spec.option_table)
    conditions, params = _lakeflow_scope_where(
        scope, source_lz_id, source_lz_ids, workspace_ids
    )
    # ``gold_dbx_workflow_runs`` is dated by ``start_time``, the success-rate summary
    # by ``execution_date``: the same period, read on each table's own column.
    date_column = (
        "execution_date"
        if spec.option_table == _WORKFLOW_SUCCESS
        else "CAST(start_time AS DATE)"
    )
    conditions = [*conditions, f"{date_column} >= ?", f"{date_column} <= ?"]
    params = [*params, start, end]
    if workflow_id:
        conditions.append("workflow_id = ?")
        params.append(workflow_id)
    where = "WHERE " + " AND ".join(conditions)

    try:
        return {
            **payload,
            **await _fetch_options_rows(
                db,
                spec,
                source=source,
                dim_table=qualified_table(settings, _WORKSPACE_DIM),
                where=where,
                params=params,
                q=q,
                limit=_clamp_limit(limit),
            ),
        }
    except Exception:
        logger.exception("lakeflow filter options soft-fail view=%s column=%s", view, column)
        return {**payload, **_empty_options(spec, enabled=False)}
