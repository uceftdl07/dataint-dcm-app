"""Pydantic v2 response models for Compute Metrics gold tables."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ClusterCostItem",
    "ClusterDetailResponse",
    "ClusterEfficiencyItem",
    "ClusterGovernanceItem",
    "ClusterOverviewItem",
    "ClusterOverviewKpis",
    "ClusterOverviewResponse",
    "CostTrendPoint",
    "ForecastPoint",
    "JobCostItem",
    "JobDetailResponse",
    "JobEfficiencyItem",
    "JobOverviewKpis",
    "JobOverviewResponse",
    "PaginatedItems",
    "PeriodRange",
    "PipelineCostItem",
    "PipelineDetailResponse",
    "PipelineEfficiencyItem",
    "PipelineOverviewKpis",
    "PipelineOverviewResponse",
    "RecommendationItem",
    "RecommendationsNotApplicable",
    "RecommendationsSummary",
    "RollingWindowBlock",
    "ServerlessBudgetPolicyEntry",
    "ServerlessCostPerRunBlock",
    "ServerlessCostPerRunBucket",
    "ServerlessDltComparisonBlock",
    "ServerlessDltComparisonItem",
    "ServerlessGovernanceItem",
    "ServerlessLeversResponse",
    "ServerlessObjectDetailResponse",
    "ServerlessObjectDetailRow",
    "ServerlessObjectIdentity",
    "ServerlessObjectItem",
    "ServerlessObjectTotals",
    "ServerlessObjectWindowRow",
    "ServerlessOverviewKpis",
    "ServerlessOverviewResponse",
    "ServerlessPerformanceTargetBlock",
    "ServerlessPerformanceTargetItem",
    "ServerlessShareBlock",
    "ServerlessSurfaceItem",
    "SlowQueriesResponse",
    "SlowQueryItem",
    "UptimeTrendPoint",
    "WarehouseCostItem",
    "WarehouseDetailResponse",
    "WarehouseOverviewItem",
    "WarehouseOverviewKpis",
    "WarehouseOverviewResponse",
    "WarehouseQueryPerformanceItem",
]


class PeriodRange(BaseModel):
    """Inclusive date window for compute metrics queries."""

    model_config = ConfigDict(from_attributes=True)

    from_: date = Field(alias="from")
    to: date


class OptionalPeriodRange(BaseModel):
    """A period whose bounds may be unknown, unlike :class:`PeriodRange`.

    ``PeriodRange`` always has bounds: the caller passed them, or the service defaulted
    them. This one is **read from a snapshot table** — ``governance_period`` — so when the
    snapshot holds nothing for the caller's perimeter there is no date to report, and
    ``null`` is the only truthful answer. A missing caption is better than an invented one:
    today's date under a coverage figure would claim a measurement nobody took.
    """

    model_config = ConfigDict(from_attributes=True)

    from_: date | None = Field(default=None, alias="from")
    to: date | None = None


class PaginatedItems(BaseModel):
    """Generic paginated list envelope."""

    items: list[Any]
    total: int
    page: int
    page_size: int
    period: PeriodRange


class ClusterCostItem(BaseModel):
    """Row from ``gold_dbx_compute_cluster_cost_daily`` (latest per cluster)."""

    model_config = ConfigDict(from_attributes=True)

    cloud_provider: str
    workspace_id: str
    cluster_id: str
    cluster_name: str | None = None
    owner: str | None = None
    ba_name: str | None = None
    cost_center: str | None = None
    sku_group: str | None = None
    cluster_type: str | None = None
    dbu_quantity: float | None = None
    cost_usd: float | None = None
    cost_usd_prev_day: float | None = None
    cost_delta_pct: float | None = None
    cost_rank: int | None = None
    is_top_cost: bool | None = None
    period_start: date | None = None


class ClusterEfficiencyItem(BaseModel):
    """Row from ``gold_dbx_compute_cluster_efficiency_daily``."""

    model_config = ConfigDict(from_attributes=True)

    cloud_provider: str
    workspace_id: str
    cluster_id: str
    cluster_type: str | None = None
    cpu_util_avg_pct: float | None = None
    cpu_util_p95_pct: float | None = None
    mem_util_avg_pct: float | None = None
    mem_util_p95_pct: float | None = None
    cpu_wait_avg_pct: float | None = None
    idle_pct: float | None = None
    uptime_hours: float | None = None
    active_hours: float | None = None
    worker_count_avg: float | None = None
    worker_count_max: float | None = None
    autoscale_oscillation: int | None = None
    driver_node_type: str | None = None
    worker_node_type: str | None = None
    is_zombie: bool | None = None
    utilization_status: str | None = None
    recommended_node_type: str | None = None
    rightsizing_reco: str | None = None
    estimated_savings_usd: float | None = None
    period_start: date | None = None


class ClusterGovernanceItem(BaseModel):
    """Row from ``gold_dbx_compute_cluster_governance`` snapshot."""

    model_config = ConfigDict(from_attributes=True)

    cloud_provider: str
    workspace_id: str
    cluster_id: str
    cluster_name: str | None = None
    cluster_type: str | None = None
    has_owner_tag: bool | None = None
    has_cost_center_tag: bool | None = None
    dbr_version: str | None = None
    dbr_is_lts_current: bool | None = None
    node_oversized: bool | None = None
    is_single_node: bool | None = None
    recommended_action: str | None = None
    severity: str | None = None
    generated_at: datetime | None = Field(default=None, alias="_generated_at")


class WarehouseCostItem(BaseModel):
    """Row from ``gold_dbx_compute_warehouse_cost_daily``."""

    model_config = ConfigDict(from_attributes=True)

    cloud_provider: str
    source_lz_id: str
    workspace_id: str
    warehouse_id: str
    warehouse_name: str | None = None
    warehouse_size: str | None = None
    dbu_quantity: float | None = None
    cost_usd: float | None = None
    cost_usd_prev_day: float | None = None
    cost_delta_pct: float | None = None
    query_count: int | None = None
    cost_per_query_usd: float | None = None
    top_consumer: str | None = None
    period_start: date | None = None


class WarehouseQueryPerformanceItem(BaseModel):
    """Row from ``gold_dbx_compute_warehouse_query_performance_daily``."""

    model_config = ConfigDict(from_attributes=True)

    cloud_provider: str
    source_lz_id: str
    workspace_id: str
    warehouse_id: str
    query_count: int | None = None
    failed_count: int | None = None
    failure_rate_pct: float | None = None
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    latency_p99_ms: float | None = None
    queue_time_avg_ms: float | None = None
    queue_time_p95_ms: float | None = None
    spill_query_count: int | None = None
    cache_hit_pct: float | None = None
    bytes_scanned: int | None = None
    rows_scanned: int | None = None
    top_slow_statement_id: str | None = None
    period_start: date | None = None


class RecommendationItem(BaseModel):
    """Row from ``gold_dbx_compute_recommendations``.

    Rows whose saving is arithmetically void on a serverless SQL warehouse are not served
    at all — the count and the dollars withheld are published by
    :class:`RecommendationsNotApplicable` instead of vanishing.
    """

    model_config = ConfigDict(from_attributes=True)

    recommendation_id: str
    cloud_provider: str
    #: Never served, and typed accordingly: **no** ``gold_dbx_compute_*`` table carries a
    #: ``source_lz_id`` column any more (checked against ``information_schema`` in dev on
    #: 2026-09-10), and this route does not even emit the NULL placeholder the warehouse
    #: overview does. Declaring it required made the model contradict its own payload.
    source_lz_id: str | None = None
    workspace_id: str
    object_type: str
    object_id: str
    object_name: str | None = None
    category: str
    mode: str | None = None
    title: str | None = None
    detail: str | None = None
    recommended_action: str | None = None
    estimated_savings_usd: float | None = None
    severity: str | None = None
    personas: list[str] | None = None
    status: str
    first_seen_date: date | None = None
    last_seen_date: date | None = None
    #: Three values, not two. ``None`` on every non-warehouse row — the flag is a property
    #: of SQL warehouses only, and ``false`` there would assert "this cluster is classic".
    is_serverless: bool | None = None


class ForecastPoint(BaseModel):
    """Row from ``gold_dbx_compute_forecast_daily``."""

    model_config = ConfigDict(from_attributes=True)

    cloud_provider: str | None = None
    source_lz_id: str | None = None
    object_type: str
    object_id: str
    metric_name: str
    horizon_date: date
    predicted_value: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    method: str | None = None


class CostTrendPoint(BaseModel):
    """Aggregated cost/DBU trend bucket."""

    bucket: date
    cost_usd: float | None = None
    dbu_quantity: float | None = None


class UptimeTrendPoint(BaseModel):
    """Aggregated uptime/idle trend bucket of a job or a DLT pipeline.

    ``idle_pct`` is uptime-weighted, and stays ``None`` for a bucket with no
    measured hour: a ``0`` there would read as a fully busy grain.
    """

    bucket: date
    uptime_hours: float | None = None
    idle_pct: float | None = None


class RollingWindowBlock(BaseModel):
    """The window actually covered, read from gold — never derived from today (R5)."""

    window_days: int
    from_date: date | None = None
    to_date: date | None = None


class ClusterOverviewKpis(BaseModel):
    total_cost_usd: float = 0.0
    cost_delta_pct: float | None = None
    active_clusters: int = 0
    zombie_count: int = 0
    open_recommendations: int = 0


class ClusterOverviewItem(BaseModel):
    cloud_provider: str
    workspace_id: str
    cluster_id: str
    cluster_name: str | None = None
    owner: str | None = None
    cluster_type: str | None = None
    cost_usd: float | None = None
    cpu_util_p95_pct: float | None = None
    idle_pct: float | None = None
    uptime_hours: float | None = None
    utilization_status: str | None = None
    severity: str | None = None


class ClusterOverviewResponse(BaseModel):
    kpis: ClusterOverviewKpis
    items: list[ClusterOverviewItem] = Field(default_factory=list)
    period: PeriodRange


class WarehouseOverviewKpis(BaseModel):
    total_cost_usd: float = 0.0
    cost_delta_pct: float | None = None
    active_warehouses: int = 0
    query_count: int = 0
    failed_count: int = 0
    #: Warehouses with at least one **applicable** open recommendation. It drops by less
    #: than the number of neutralised rows because it counts warehouses, not rows: in dev
    #: 38 serverless warehouses keep a live ``RELIABILITY`` recommendation next to a void
    #: ``RIGHTSIZING`` one, and 31 lose their only one (419 → 388).
    open_recommendations: int = 0


class WarehouseOverviewItem(BaseModel):
    cloud_provider: str
    #: Always ``None``: the warehouse gold tables moved to a grain without it and the query
    #: emits ``CAST(NULL AS STRING)`` for API compatibility. Kept in the payload, typed for
    #: what it actually contains.
    source_lz_id: str | None = None
    workspace_id: str
    warehouse_id: str
    warehouse_name: str | None = None
    warehouse_size: str | None = None
    cost_usd: float | None = None
    query_count: int | None = None
    failure_rate_pct: float | None = None
    latency_p95_ms: float | None = None
    #: ``None`` for a warehouse billed over the window but absent from the utilization
    #: snapshot: unknown, not classic. A ``COALESCE`` to ``false`` would claim otherwise.
    is_serverless: bool | None = None


class WarehouseOverviewResponse(BaseModel):
    kpis: WarehouseOverviewKpis
    items: list[WarehouseOverviewItem] = Field(default_factory=list)
    #: The pagination envelope and the window block the route has always served and this
    #: model omitted. Added while typing ``is_serverless``: a contract the frontend reads
    #: (T003) is worth less than nothing if it under-describes the payload.
    total: int = 0
    page: int = 1
    page_size: int = 25
    window: RollingWindowBlock | None = None
    period: PeriodRange


class JobCostItem(BaseModel):
    """Row from ``gold_dbx_compute_job_cluster_cost_rolling`` (grain ``job_id``).

    ``compute_kind`` is part of the gold grain since T001b, but this row is **not**:
    the service collapses the two forms back into one row per job, so the field is a
    *label* — ``CLASSIC``, ``SERVERLESS``, or ``MIXED`` for a job that bills both over
    the window. That differs from :class:`PipelineCostItem`, where the field passes the
    gold grain straight through; the difference is deliberate, see the comment above
    ``_cost_rollup_ctes`` in ``compute_metrics_jobs``.
    """

    model_config = ConfigDict(from_attributes=True)

    cloud_provider: str
    workspace_id: str
    job_id: str
    compute_kind: str | None = None
    job_name: str | None = None
    cluster_count: int | None = None
    dbu_quantity: float | None = None
    cost_usd: float | None = None
    cost_usd_prev_window: float | None = None
    cost_delta_pct: float | None = None
    cost_rank: int | None = None
    is_top_cost: bool | None = None
    window_start: date | None = None
    as_of_date: date | None = None


class JobEfficiencyItem(BaseModel):
    """Row from ``gold_dbx_compute_job_efficiency_rolling`` (grain ``job_id``).

    No ``is_zombie``: a JOB cluster dies with its run, so the flag would be ``false``
    on every row and read as a control that passes (024 R8). No ``cluster_name`` /
    ``cluster_type`` either — the grain aggregates as many ephemeral clusters as the
    job had runs.
    """

    model_config = ConfigDict(from_attributes=True)

    cloud_provider: str
    workspace_id: str
    job_id: str
    job_name: str | None = None
    cluster_count: int | None = None
    cpu_util_avg_pct: float | None = None
    cpu_util_p95_pct: float | None = None
    mem_util_avg_pct: float | None = None
    mem_util_p95_pct: float | None = None
    cpu_wait_avg_pct: float | None = None
    idle_pct: float | None = None
    idle_pct_prev_window: float | None = None
    # Points, not per cent: ``idle_pct`` is already a percentage, so 20 % → 30 %
    # is "+10 pts". ``uptime`` is an amount of hours, so its delta is a per cent.
    idle_pct_delta_pts: float | None = None
    uptime_hours: float | None = None
    uptime_hours_prev_window: float | None = None
    uptime_hours_delta_pct: float | None = None
    active_hours: float | None = None
    worker_count_avg: float | None = None
    worker_count_max: float | None = None
    autoscale_oscillation: int | None = None
    driver_node_type: str | None = None
    worker_node_type: str | None = None
    autoscale_enabled: bool | None = None
    autoscale_min_workers: int | None = None
    autoscale_max_workers: int | None = None
    configured_worker_count: int | None = None
    utilization_status: str | None = None
    recommended_node_type: str | None = None
    rightsizing_reco: str | None = None
    estimated_savings_usd: float | None = None
    window_days: int | None = None
    window_start: date | None = None
    as_of_date: date | None = None


class JobOverviewKpis(BaseModel):
    """Headline cost KPIs for the job compute tab."""

    total_cost_usd: float = 0.0
    cost_delta_pct: float | None = None
    active_jobs: int = 0


class JobOverviewResponse(BaseModel):
    """Paginated job overview: KPIs plus the per-job cost rows."""

    kpis: JobOverviewKpis
    items: list[JobCostItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 25
    period: PeriodRange


class PipelineCostItem(BaseModel):
    """Row from ``gold_dbx_compute_pipeline_cost_rolling`` (grain ``dlt_pipeline_id``).

    No ``cluster_count``: the rollup is billing-direct, with no cluster grain.

    ``compute_kind`` is part of the gold grain, so a pipeline that bills both forms
    has one row per form: a caller listing rows without filtering it gets that
    pipeline twice, and ``cost_rank`` restarts at 1 inside each form. The DLT
    clusters page filters ``CLASSIC``; the field is served so that a reader can
    tell which compute a row is about.
    """

    model_config = ConfigDict(from_attributes=True)

    cloud_provider: str
    workspace_id: str
    dlt_pipeline_id: str
    compute_kind: str | None = None
    pipeline_name: str | None = None
    dbu_quantity: float | None = None
    cost_usd: float | None = None
    cost_usd_prev_window: float | None = None
    cost_delta_pct: float | None = None
    cost_rank: int | None = None
    is_top_cost: bool | None = None
    window_start: date | None = None
    as_of_date: date | None = None


class PipelineEfficiencyItem(BaseModel):
    """Row from ``gold_dbx_compute_pipeline_efficiency_rolling`` (grain pipeline).

    ``cluster_count`` **is** carried here, unlike :class:`PipelineCostItem`: the
    efficiency rollup goes through the ``cluster_id → dlt_pipeline_id`` mapping, so it
    knows how many PIPELINE clusters ran, while the cost rollup is billing-direct.
    """

    model_config = ConfigDict(from_attributes=True)

    cloud_provider: str
    workspace_id: str
    dlt_pipeline_id: str
    pipeline_name: str | None = None
    cluster_count: int | None = None
    cpu_util_avg_pct: float | None = None
    cpu_util_p95_pct: float | None = None
    mem_util_avg_pct: float | None = None
    mem_util_p95_pct: float | None = None
    cpu_wait_avg_pct: float | None = None
    idle_pct: float | None = None
    idle_pct_prev_window: float | None = None
    idle_pct_delta_pts: float | None = None
    uptime_hours: float | None = None
    uptime_hours_prev_window: float | None = None
    uptime_hours_delta_pct: float | None = None
    active_hours: float | None = None
    worker_count_avg: float | None = None
    worker_count_max: float | None = None
    autoscale_oscillation: int | None = None
    driver_node_type: str | None = None
    worker_node_type: str | None = None
    autoscale_enabled: bool | None = None
    autoscale_min_workers: int | None = None
    autoscale_max_workers: int | None = None
    configured_worker_count: int | None = None
    utilization_status: str | None = None
    recommended_node_type: str | None = None
    rightsizing_reco: str | None = None
    estimated_savings_usd: float | None = None
    window_days: int | None = None
    window_start: date | None = None
    as_of_date: date | None = None


class PipelineOverviewKpis(BaseModel):
    """Headline cost KPIs for the pipeline compute tab."""

    total_cost_usd: float = 0.0
    cost_delta_pct: float | None = None
    active_pipelines: int = 0


class PipelineOverviewResponse(BaseModel):
    """Paginated pipeline overview: KPIs plus the per-pipeline cost rows."""

    kpis: PipelineOverviewKpis
    items: list[PipelineCostItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 25
    period: PeriodRange



class RecommendationsNotApplicable(BaseModel):
    """What the serverless neutralisation withheld, published rather than dropped.

    Without this block the page and ``gold_dbx_compute_recommendations`` disagree with no
    way to tell why: in dev, 69 open rows out of 213 930 carry 27 104,73 $ of the
    47 324,89 $ of open savings — 57,3 % of the promised dollars in 0,03 % of the rows. A
    suppression nobody can see is indistinguishable from a bug.

    ``reason`` is a code (``SERVERLESS_WAREHOUSE``), not a sentence: the wording belongs to
    the frontend, the fact belongs to the API.
    """

    count: int = 0
    savings_usd: float = 0.0
    reason: str
    #: The categories neutralised — ``RELIABILITY`` is deliberately **not** among them: a
    #: reliability finding on a serverless warehouse is still actionable.
    categories: list[str] = Field(default_factory=list)


class RecommendationsSummary(BaseModel):
    open_count: int = 0
    open_savings_usd: float = 0.0
    resolved_30d_count: int = 0
    high_severity_open_count: int = 0
    not_applicable: RecommendationsNotApplicable
    period: PeriodRange


class SlowQueryItem(BaseModel):
    cloud_provider: str
    source_lz_id: str
    workspace_id: str
    warehouse_id: str
    statement_id: str
    warehouse_name: str | None = None
    executed_by: str | None = None
    start_time: datetime | None = None
    duration_ms: float | None = None
    status: str | None = None
    reason: str | None = None
    error_message: str | None = None
    query_profile_url: str | None = None


class SlowQueriesResponse(BaseModel):
    enabled: bool
    items: list[SlowQueryItem] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 25
    period: PeriodRange | None = None


class ClusterDetailResponse(BaseModel):
    cloud_provider: str
    workspace_id: str
    cluster_id: str
    cost: ClusterCostItem | None = None
    efficiency: ClusterEfficiencyItem | None = None
    governance: ClusterGovernanceItem | None = None
    period: PeriodRange


class JobDetailResponse(BaseModel):
    """Drawer payload of one job — **no** ``governance`` field, deliberately.

    Governance is a cluster-level snapshot (tags, DBR version, oversizing) and stays on
    the all-purpose grain (024 C2). Declaring it here as ``None`` would read as
    "measured, nothing found" instead of "not applicable at this grain".

    ``efficiency`` is ``None`` for a job billed without a ``node_timeline`` row — a
    normal answer, not an error.
    """

    cloud_provider: str | None = None
    workspace_id: str | None = None
    job_id: str
    cost: JobCostItem | None = None
    efficiency: JobEfficiencyItem | None = None
    window: RollingWindowBlock
    period: PeriodRange


class PipelineDetailResponse(BaseModel):
    """Drawer payload of one DLT pipeline — **no** ``governance`` field (024 C2).

    ``efficiency`` is ``None`` for a serverless pipeline: it has no ``node_timeline``
    row, so it is billed but not measured.
    """

    cloud_provider: str | None = None
    workspace_id: str | None = None
    dlt_pipeline_id: str
    cost: PipelineCostItem | None = None
    efficiency: PipelineEfficiencyItem | None = None
    window: RollingWindowBlock
    period: PeriodRange


class WarehouseDetailResponse(BaseModel):
    cloud_provider: str
    source_lz_id: str
    workspace_id: str
    warehouse_id: str
    cost: WarehouseCostItem | None = None
    query_performance: WarehouseQueryPerformanceItem | None = None
    period: PeriodRange


# --- Serverless surfaces (spec 025) ------------------------------------------------
#
# ``run_count`` is ``int | None`` in every model below, and the ``None`` half is the whole
# point: eleven of the twelve serverless surfaces do not count runs at all, and not one row
# of ``gold_dbx_compute_serverless_cost_rolling`` carries ``run_count = 0``. A ``0`` here
# would claim "measured, nothing ran" for a surface that never reports runs.
#
# (Keep prose off a line starting with ``# type:`` — mypy reads that as a type comment and
# reports the file as a syntax error, which is how this note came to be written.)


class ServerlessBudgetPolicyEntry(BaseModel):
    """One budget policy attached to a surface, ordered by cost descending.

    No policy **name** is available, and that is not an omission: ``system.billing``
    exposes no budget-policy table. The UI must not promise one.
    """

    budget_policy_id: str | None = None
    cost_usd: float | None = None


class ServerlessShareBlock(BaseModel):
    """Serverless share of compute spend, in **dollars** — never in DBUs.

    A serverless DBU and a classic DBU are not the same unit and do not have the same
    price, so a DBU ratio would not be a share of anything. ``unclassified_warehouse_cost_usd``
    is the spend of SQL warehouses absent from the utilization snapshot: it is neither
    proven serverless nor proven classic, and it is published rather than folded into
    either side.
    """

    pct: float | None = None
    serverless_cost_usd: float = 0.0
    classic_cost_usd: float = 0.0
    classic_cluster_cost_usd: float = 0.0
    classic_warehouse_cost_usd: float = 0.0
    unclassified_warehouse_cost_usd: float = 0.0


class ServerlessOverviewKpis(BaseModel):
    """Every optional field here is optional because the API measurably serves ``null``.

    ``cost_usd_prev_window`` is ``null`` and not ``0`` when there is no comparison —
    "it was free last window" is a different statement from "there is nothing to compare
    to". The two ``cost_usd_without_*`` figures and ``serverless_share`` come from the
    governance snapshot and the classic tables respectively: when either cannot be read,
    the block is absent rather than zeroed, because a zero would read as "everything is
    covered" and "serverless is 0 % of your compute" — two claims nobody measured.
    """

    cost_usd: float = 0.0
    cost_usd_prev_window: float | None = None
    cost_delta_pct: float | None = None
    dbu_quantity: float = 0.0
    run_count: int | None = None
    surface_count: int = 0
    object_count: int = 0
    cost_usd_without_identity: float | None = None
    cost_usd_without_object_key: float | None = None
    budget_policy_coverage_pct: float | None = None
    owner_tag_coverage_pct: float | None = None
    serverless_share: ServerlessShareBlock | None = None


class ServerlessOverviewResponse(BaseModel):
    """``governance_period`` is **not** ``period``.

    Governance is a 90-day snapshot rebuilt on its own cadence, while the cost KPIs follow
    the rolling window. Serving one date range for both would make a 90-day coverage figure
    look like it was measured over the selected 30 days.
    """

    kpis: ServerlessOverviewKpis
    governance_period: OptionalPeriodRange | None = None
    window: RollingWindowBlock
    period: PeriodRange


class ServerlessSurfaceItem(BaseModel):
    """One row of ``gold_dbx_compute_serverless_cost_rolling`` folded to the surface."""

    model_config = ConfigDict(from_attributes=True)

    serverless_surface: str
    cost_usd: float | None = None
    cost_usd_prev_window: float | None = None
    dbu_quantity: float | None = None
    run_count: int | None = None
    object_count: int | None = None
    workspace_count: int | None = None
    cost_usd_with_object_key: float | None = None
    cost_delta_pct: float | None = None
    share_pct: float | None = None
    object_key_coverage_pct: float | None = None


class ServerlessGovernanceItem(BaseModel):
    """Row of ``gold_dbx_compute_serverless_governance``, at the (workspace, surface) grain.

    ``identity_source_mix`` is an unweighted **set** — the carrying field changes by
    surface (SQL warehouses are 100 % ``OWNED_BY``, apps 100 % ``CREATED_BY``, jobs and
    notebooks 100 % ``RUN_AS``), and "owner" and "runner" are not the same rechargeability
    semantics. The weight of identity-less spend is in ``identity_coverage_pct``.
    """

    model_config = ConfigDict(from_attributes=True)

    cloud_provider: str
    workspace_id: str
    serverless_surface: str
    cost_usd: float | None = None
    cost_usd_with_owner_tag: float | None = None
    owner_tag_coverage_pct: float | None = None
    cost_usd_with_cost_center_tag: float | None = None
    cost_center_tag_coverage_pct: float | None = None
    cost_usd_with_budget_policy: float | None = None
    budget_policy_coverage_pct: float | None = None
    cost_usd_without_identity: float | None = None
    identity_coverage_pct: float | None = None
    cost_usd_without_object_key: float | None = None
    identity_source_mix: list[str] = Field(default_factory=list)
    #: ``0`` and not ``None`` when nothing is attached — a measured fact, not an unknown.
    budget_policy_count: int = 0
    budget_policy_inventory: list[ServerlessBudgetPolicyEntry] | None = None


class ServerlessGovernanceTotals(BaseModel):
    """The footer row of the governance tab, over the **filtered** population.

    Not a sum of the page: it is computed over every row the filters keep, so it does not
    change when the user pages. The coverage percentages are derived from the dollars in
    the same row rather than recomputed client-side from the items — an average of
    per-workspace percentages is not the percentage of the whole.
    """

    cost_usd: float = 0.0
    owner_tag_coverage_pct: float | None = None
    cost_center_tag_coverage_pct: float | None = None
    budget_policy_coverage_pct: float | None = None
    identity_coverage_pct: float | None = None
    cost_usd_without_identity: float = 0.0
    cost_usd_without_object_key: float | None = None


class ServerlessObjectItem(BaseModel):
    """One serverless object over the window.

    ``serverless_surface`` is part of the identity, not a label: the same ``object_id``
    appears under two surfaces for 4 of the 20 583 objects measured in dev, which is why
    the detail routes require it as a query parameter.
    """

    model_config = ConfigDict(from_attributes=True)

    cloud_provider: str
    workspace_id: str
    serverless_surface: str
    object_id: str
    object_name: str | None = None
    billing_origin_product: str | None = None
    performance_target: str | None = None
    budget_policy_id: str | None = None
    identity_principal: str | None = None
    identity_source: str | None = None
    has_custom_tags: bool | None = None
    has_object_key: bool | None = None
    dbu_quantity: float | None = None
    cost_usd: float | None = None
    cost_usd_prev_window: float | None = None
    cost_delta_pct: float | None = None
    run_count: int | None = None
    cost_per_run_p50_usd: float | None = None
    cost_per_run_p95_usd: float | None = None
    cost_per_run_p99_usd: float | None = None
    cost_rank: int | None = None
    is_top_cost: bool | None = None


class ServerlessObjectDetailRow(ServerlessObjectItem):
    """The list row plus the two snapshot columns only the drawer shows."""

    window_start: date | None = None
    as_of_date: date | None = None


class ServerlessPerformanceTargetItem(BaseModel):
    """``performance_target`` bucket. ``None`` is a **fourth** value, not missing data.

    Gold also emits ``MIXED`` for an object seen under more than one target, so the four
    observed values are ``PERFORMANCE_OPTIMIZED``, ``STANDARD``, ``MIXED`` and ``NULL``.
    ``NULL`` carries 71,5 % of serverless dollars in dev, so hiding it would hide the
    lever.
    """

    performance_target: str | None = None
    cost_usd: float | None = None
    dbu_quantity: float | None = None
    run_count: int | None = None
    object_count: int | None = None
    row_count: int | None = None
    share_pct: float | None = None


class ServerlessPerformanceTargetBlock(BaseModel):
    """The ``performance_target`` buckets and the weight of the unset one."""

    items: list[ServerlessPerformanceTargetItem] = Field(default_factory=list)
    total_cost_usd: float = 0.0
    unset_share_pct: float | None = None


class ServerlessCostPerRunBucket(BaseModel):
    """One histogram bucket, whose ``run_count`` is a real ``0``.

    Unlike everywhere else in this section: an absent bucket means no run was observed in
    that cost band, which is a measurement and not an unknown.
    """

    from_usd: float
    to_usd: float | None = None
    run_count: int = 0


class ServerlessCostPerRunBlock(BaseModel):
    """Cost per run, over the objects that actually count runs (``run_count > 0``)."""

    object_count: int = 0
    run_count: int | None = None
    p50_usd: float | None = None
    p90_usd: float | None = None
    p99_usd: float | None = None
    max_usd: float | None = None
    max_object_p99_usd: float | None = None
    histogram: list[ServerlessCostPerRunBucket] = Field(default_factory=list)


class ServerlessDltComparisonItem(BaseModel):
    """Serverless vs classic DLT, per cloud.

    ``compute_type`` is ``CLASSIC_COMPUTE`` or ``SERVERLESS_COMPUTE``.

    ``comparable`` is ``false`` — and ``failure_rate_pct`` then ``None`` — below
    ``min_requests``: azure classic DLT has 6 requests in dev, from which no failure rate
    can be read. A percentage over 6 requests is noise shaped like a metric.
    """

    cloud_provider: str
    compute_type: str
    requests: int = 0
    outcome_requests: int = 0
    failed_requests: int = 0
    canceled_requests: int = 0
    failure_rate_pct: float | None = None
    comparable: bool = False
    duration_p50_sec: float | None = None
    duration_p95_sec: float | None = None
    pipeline_count: int | None = None
    failing_pipeline_count: int | None = None
    failure_concentration_pct: float | None = None


class ServerlessDltComparisonBlock(BaseModel):
    """The per-cloud comparison rows, plus the two thresholds they were built with."""

    items: list[ServerlessDltComparisonItem] = Field(default_factory=list)
    #: Below this many requests a row is served with ``comparable = false``.
    min_requests: int = 0
    #: How many pipelines ``failure_concentration_pct`` is computed over.
    top_failing_pipelines: int = 0
    window: PeriodRange | None = None


class ServerlessLeversResponse(BaseModel):
    """Two of the three blocks are nullable, and not only on a broken warehouse.

    ``cost_per_run`` needs objects that count runs — eleven of the twelve surfaces never
    do — and ``dlt_comparison`` publishes nothing below its request floor. ``null`` there
    means "not measurable on this perimeter", which the page renders as a stated absence.
    ``performance_target`` always exists: an empty bucket list is itself the answer.
    """

    performance_target: ServerlessPerformanceTargetBlock
    cost_per_run: ServerlessCostPerRunBlock | None = None
    dlt_comparison: ServerlessDltComparisonBlock | None = None
    window: RollingWindowBlock
    period: PeriodRange


class ServerlessObjectIdentity(BaseModel):
    """The object itself, folded across the workspaces that billed it."""

    serverless_surface: str
    object_id: str
    object_name: str | None = None
    has_object_key: bool | None = None
    billing_origin_product: str | None = None
    workspace_count: int = 0
    cloud_providers: list[str] = Field(default_factory=list)


class ServerlessObjectTotals(BaseModel):
    """The object's figures summed over the workspaces in scope.

    ``cost_per_run_mean_usd`` is ``None``, not ``0``, when no run was counted — see the
    note at the top of this section.
    """

    cost_usd: float | None = None
    cost_usd_prev_window: float | None = None
    cost_delta_pct: float | None = None
    dbu_quantity: float | None = None
    run_count: int | None = None
    cost_per_run_mean_usd: float | None = None
    max_object_p99_usd: float | None = None


class ServerlessObjectWindowRow(BaseModel):
    """The same object over each of the four rolling windows (1 / 7 / 30 / 90 days)."""

    window_days: int
    cost_usd: float | None = None
    cost_usd_prev_window: float | None = None
    dbu_quantity: float | None = None
    run_count: int | None = None


class ServerlessObjectDetailResponse(BaseModel):
    """One object: its identity, its totals, and the rows those totals were summed from.

    ``workspaces`` is served rather than folded away because the same ``object_id`` is
    legitimately billed in several workspaces, and a single set of figures under a title
    naming the object would silently be one workspace's.
    """

    object: ServerlessObjectIdentity
    totals: ServerlessObjectTotals
    workspaces: list[ServerlessObjectDetailRow] = Field(default_factory=list)
    cost_per_run_histogram: list[ServerlessCostPerRunBucket] = Field(default_factory=list)
    windows: list[ServerlessObjectWindowRow] = Field(default_factory=list)
    window: RollingWindowBlock
    period: PeriodRange
