"""Unity Catalog usage tracking endpoints — ``gold_dbx_usage_*`` gold tables.

Routes
------
GET /api/v1/uc-usage/filters/options
GET /api/v1/uc-usage/overview
GET /api/v1/uc-usage/charts/tables
GET /api/v1/uc-usage/charts/consumers
GET /api/v1/uc-usage/charts/finops
GET /api/v1/uc-usage/charts/writes
GET /api/v1/uc-usage/charts/cost-changes
GET /api/v1/uc-usage/details
GET /api/v1/uc-usage/tables
GET /api/v1/uc-usage/tables/{table_full_name}/top-consumers
GET /api/v1/uc-usage/consumers
GET /api/v1/uc-usage/finops/kpis
GET /api/v1/uc-usage/finops/cost-by-table
GET /api/v1/uc-usage/finops/trends
GET /api/v1/uc-usage/attention
GET /api/v1/uc-usage/recommendations
GET /api/v1/uc-usage/recommendations/charts
GET /api/v1/uc-usage/governance/kpis
GET /api/v1/uc-usage/governance/charts
GET /api/v1/uc-usage/governance/registry

None of the eight gold tables carries ``source_lz_id`` or ``workspace_id``, and a
Unity Catalog table does not belong to a workspace: no row-level scope is
expressible, so the whole router is reserved for unrestricted callers (FR-021).
For the same reason no ``cloud_provider`` parameter exists — both clouds are
always aggregated together (FR-019).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from fastapi import Depends, Query
from fastapi.routing import APIRouter

from ...auth.scope import require_unrestricted_scope
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.uc_usage_charts import (
    fetch_consumer_charts,
    fetch_finops_charts,
    fetch_table_charts,
)
from ..services.uc_usage_common import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    resolve_period,
)
from ..services.uc_usage_consumers import fetch_consumers
from ..services.uc_usage_exploration import (
    fetch_cost_changes,
    fetch_entity_detail,
    fetch_write_charts,
)
from ..services.uc_usage_filters import MAX_FILTER_OPTIONS, fetch_filter_options
from ..services.uc_usage_finops import (
    fetch_cost_by_table,
    fetch_finops_kpis,
    fetch_usage_trends,
)
from ..services.uc_usage_governance import (
    fetch_attention,
    fetch_governance_kpis,
    fetch_governance_registry,
    fetch_recommendations,
)
from ..services.uc_usage_governance_charts import (
    fetch_governance_charts,
    fetch_recommendation_charts,
)
from ..services.uc_usage_governance_scope import (
    GovernanceSignal,
    InactivityBucket,
    MissingTag,
    RecommendationAgeBucket,
)
from ..services.uc_usage_tables import fetch_overview, fetch_tables, fetch_top_consumers

__all__ = ["router"]

router = APIRouter(dependencies=[Depends(require_unrestricted_scope)])

Db = Annotated[DatabricksWarehousePool, Depends(get_db)]

# Required, with no default: FR-017 forbids the API from inventing a period.
PeriodStart = Annotated[date, Query(description="Inclusive period start (required).")]
PeriodEnd = Annotated[date, Query(description="Inclusive period end (required).")]

CatalogQuery = Annotated[str | None, Query(description="Filter by Unity Catalog catalog.")]
SchemaQuery = Annotated[str | None, Query(description="Filter by Unity Catalog schema.")]
TablesQuery = Annotated[
    list[str] | None,
    Query(description="Filter by fully qualified table names (repeatable)."),
]
SearchQuery = Annotated[str | None, Query(description="Free-text name search.")]
# Spec 027 froze the name, the type and the default; the two consumer-grain
# endpoints do not declare it at all, since they carry no table key to filter.
IncludeDeletedQuery = Annotated[
    bool,
    Query(
        description=(
            "Include tables deleted from Unity Catalog. Excluded by default: they are "
            "dropped from lists, KPIs, rankings, charts, forecasts and pagination "
            "totals before any aggregation. Every table-grain row carries "
            "is_deleted / deleted_at / lifecycle_state either way."
        )
    ),
]
PageQuery = Annotated[int, Query(ge=1, description="1-based page number.")]
PageSizeQuery = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE, description="Rows per page.")]

# Mirrors ``uc_usage_finops.FORECAST_METRICS`` — spelled out because ``Literal``
# needs literal members, and an unknown metric must be a 422 rather than a
# silently empty series.
ForecastMetric = Literal[
    "request_count", "distinct_consumers", "estimated_cost_usd", "data_read_bytes"
]


@router.get("/filters/options")
async def get_filter_options(
    db: Db,
    catalog: CatalogQuery = None,
    schema: SchemaQuery = None,
    search: SearchQuery = None,
    limit: Annotated[int, Query(ge=1, le=MAX_FILTER_OPTIONS)] = MAX_FILTER_OPTIONS,
    include_deleted: IncludeDeletedQuery = False,
) -> dict[str, Any]:
    """Valeurs proposables par les filtres — un instantané, donc sans période."""
    return await fetch_filter_options(
        db,
        catalog=catalog,
        schema=schema,
        search=search,
        limit=limit,
        include_deleted=include_deleted,
    )


@router.get("/overview")
async def get_usage_overview(
    db: Db,
    period_start: PeriodStart,
    period_end: PeriodEnd,
    catalog: CatalogQuery = None,
    schema: SchemaQuery = None,
    tables: TablesQuery = None,
    include_deleted: IncludeDeletedQuery = False,
) -> dict[str, Any]:
    """Overview KPIs, forecast series and observed written volume."""
    start, end = resolve_period(period_start, period_end)
    return await fetch_overview(
        db,
        start=start,
        end=end,
        catalog=catalog,
        schema=schema,
        tables=tables,
        include_deleted=include_deleted,
    )


@router.get("/tables")
async def get_usage_tables(
    db: Db,
    period_start: PeriodStart,
    period_end: PeriodEnd,
    catalog: CatalogQuery = None,
    schema: SchemaQuery = None,
    tables: TablesQuery = None,
    search: SearchQuery = None,
    sort: Literal[
        "popularity",
        "cost",
        "latency",
        "failure_rate",
        "writes",
        "rows_written",
        "consumers",
        "freshness",
        "table_name",
        "read_bytes",
    ] = "popularity",
    direction: Literal["asc", "desc"] = "desc",
    column_filter: Annotated[
        list[str] | None, Query(description="column:operator:value, repeatable")
    ] = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = DEFAULT_PAGE_SIZE,
    include_deleted: IncludeDeletedQuery = False,
) -> dict[str, Any]:
    """Paginated usage per table, most popular first before any user choice."""
    start, end = resolve_period(period_start, period_end)
    return await fetch_tables(
        db,
        start=start,
        end=end,
        catalog=catalog,
        schema=schema,
        tables=tables,
        search=search,
        sort=sort,
        direction=direction,
        column_filter=column_filter,
        page=page,
        page_size=page_size,
        include_deleted=include_deleted,
    )


@router.get("/charts/tables")
async def get_usage_table_charts(
    db: Db,
    period_start: PeriodStart,
    period_end: PeriodEnd,
    catalog: CatalogQuery = None,
    schema: SchemaQuery = None,
    tables: TablesQuery = None,
    include_deleted: IncludeDeletedQuery = False,
) -> dict[str, Any]:
    """Activity, ranking and regularity across the complete filtered scope."""
    start, end = resolve_period(period_start, period_end)
    return await fetch_table_charts(
        db,
        start=start,
        end=end,
        catalog=catalog,
        schema=schema,
        tables=tables,
        include_deleted=include_deleted,
    )


@router.get("/charts/consumers")
async def get_usage_consumer_charts(
    db: Db,
    period_start: PeriodStart,
    period_end: PeriodEnd,
    catalog: CatalogQuery = None,
    schema: SchemaQuery = None,
    tables: TablesQuery = None,
) -> dict[str, Any]:
    """Consumer composition, ranking and daily distincts with an equal-window comparison."""
    start, end = resolve_period(period_start, period_end)
    return await fetch_consumer_charts(
        db, start=start, end=end, catalog=catalog, schema=schema, tables=tables
    )


@router.get("/charts/finops")
async def get_usage_finops_charts(
    db: Db,
    period_start: PeriodStart,
    period_end: PeriodEnd,
    catalog: CatalogQuery = None,
    schema: SchemaQuery = None,
    tables: TablesQuery = None,
    include_deleted: IncludeDeletedQuery = False,
) -> dict[str, Any]:
    """Observed cost composition, concentration, unit cost and attribution coverage."""
    start, end = resolve_period(period_start, period_end)
    return await fetch_finops_charts(
        db,
        start=start,
        end=end,
        catalog=catalog,
        schema=schema,
        tables=tables,
        include_deleted=include_deleted,
    )


@router.get("/tables/{table_full_name}/top-consumers")
async def get_table_top_consumers(
    db: Db,
    table_full_name: str,
    period_start: PeriodStart,
    period_end: PeriodEnd,
    include_deleted: IncludeDeletedQuery = False,
) -> dict[str, Any]:
    """Top 5 consumers of one table — a drill-down, deliberately not paginated."""
    start, end = resolve_period(period_start, period_end)
    return await fetch_top_consumers(
        db, table_full_name, start=start, end=end, include_deleted=include_deleted
    )


@router.get("/consumers")
async def get_usage_consumers(
    db: Db,
    period_start: PeriodStart,
    period_end: PeriodEnd,
    catalog: CatalogQuery = None,
    schema: SchemaQuery = None,
    tables: TablesQuery = None,
    search: SearchQuery = None,
    consumer_type: Annotated[
        str | None, Query(description="Filter by consumer type (open vocabulary).")
    ] = None,
    sort: Literal[
        "cost", "requests", "distinct_tables", "writes", "rows_written", "name", "read_bytes"
    ] = "cost",
    direction: Literal["asc", "desc"] = "desc",
    column_filter: Annotated[
        list[str] | None, Query(description="column:operator:value, repeatable")
    ] = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """Paginated usage per consumer, ranked on the selected period."""
    start, end = resolve_period(period_start, period_end)
    return await fetch_consumers(
        db,
        start=start,
        end=end,
        catalog=catalog,
        schema=schema,
        tables=tables,
        search=search,
        consumer_type=consumer_type,
        sort=sort,
        direction=direction,
        column_filter=column_filter,
        page=page,
        page_size=page_size,
    )


@router.get("/finops/kpis")
async def get_finops_kpis(
    db: Db,
    period_start: PeriodStart,
    period_end: PeriodEnd,
    catalog: CatalogQuery = None,
    schema: SchemaQuery = None,
    tables: TablesQuery = None,
    include_deleted: IncludeDeletedQuery = False,
) -> dict[str, Any]:
    start, end = resolve_period(period_start, period_end)
    return await fetch_finops_kpis(
        db,
        start=start,
        end=end,
        catalog=catalog,
        schema=schema,
        tables=tables,
        include_deleted=include_deleted,
    )


@router.get("/finops/cost-by-table")
async def get_finops_cost_by_table(
    db: Db,
    period_start: PeriodStart,
    period_end: PeriodEnd,
    catalog: CatalogQuery = None,
    schema: SchemaQuery = None,
    tables: TablesQuery = None,
    search: SearchQuery = None,
    sort: Literal[
        "cost", "cost_per_request", "requests", "read_bytes", "forecast", "table_name"
    ] = "cost",
    direction: Literal["asc", "desc"] = "desc",
    column_filter: Annotated[
        list[str] | None, Query(description="column:operator:value, repeatable")
    ] = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = DEFAULT_PAGE_SIZE,
    include_deleted: IncludeDeletedQuery = False,
) -> dict[str, Any]:
    """Paginated cost per table, sorted and filtered like the two usage tables."""
    start, end = resolve_period(period_start, period_end)
    return await fetch_cost_by_table(
        db,
        start=start,
        end=end,
        catalog=catalog,
        schema=schema,
        tables=tables,
        search=search,
        sort=sort,
        direction=direction,
        column_filter=column_filter,
        page=page,
        page_size=page_size,
        include_deleted=include_deleted,
    )


@router.get("/finops/trends")
async def get_finops_trends(
    db: Db,
    catalog: CatalogQuery = None,
    schema: SchemaQuery = None,
    tables: TablesQuery = None,
    period_start: Annotated[
        date | None, Query(description="Start of the observed period (optional).")
    ] = None,
    period_end: Annotated[
        date | None, Query(description="End of the observed period (optional).")
    ] = None,
    metrics: Annotated[
        list[ForecastMetric] | None,
        Query(description="Forecast metrics to return (repeatable)."),
    ] = None,
    include_deleted: IncludeDeletedQuery = False,
) -> dict[str, Any]:
    """Réalisé puis prévision. Sans période, la prévision seule (FR-017).

    Pas de paramètre d'horizon : la table gold en porte sept jours.
    """
    start, end = (
        resolve_period(period_start, period_end)
        if period_start is not None and period_end is not None
        else (None, None)
    )
    return {
        "series": await fetch_usage_trends(
            db,
            start=start,
            end=end,
            catalog=catalog,
            schema=schema,
            tables=tables,
            metrics=list(metrics) if metrics else None,
            include_deleted=include_deleted,
        )
    }


@router.get("/attention")
async def get_usage_attention(
    db: Db,
    catalog: CatalogQuery = None,
    schema: SchemaQuery = None,
    tables: TablesQuery = None,
    limit: Annotated[int, Query(ge=1, le=10)] = 3,
    include_deleted: IncludeDeletedQuery = False,
) -> dict[str, Any]:
    return {
        "items": await fetch_attention(
            db,
            catalog=catalog,
            schema=schema,
            tables=tables,
            limit=limit,
            include_deleted=include_deleted,
        )
    }


@router.get("/recommendations")
async def get_usage_recommendations(
    db: Db,
    catalog: CatalogQuery = None,
    schema: SchemaQuery = None,
    tables: TablesQuery = None,
    category: Literal["LIFECYCLE", "FRESHNESS", "GOVERNANCE", "RELIABILITY", "FINOPS"]
    | None = None,
    severity: Literal["HIGH", "MEDIUM", "LOW"] | None = None,
    object_type: Literal["DATA_PRODUCT", "CONSUMER"] | None = None,
    age_bucket: RecommendationAgeBucket | None = None,
    sort: Literal["savings", "age"] = "savings",
    page: PageQuery = 1,
    page_size: PageSizeQuery = DEFAULT_PAGE_SIZE,
    include_deleted: IncludeDeletedQuery = False,
) -> dict[str, Any]:
    """Open recommendations — a snapshot, so no period parameter."""
    return await fetch_recommendations(
        db,
        catalog=catalog,
        schema=schema,
        tables=tables,
        category=category,
        severity=severity,
        object_type=object_type,
        age_bucket=age_bucket,
        sort=sort,
        page=page,
        page_size=page_size,
        include_deleted=include_deleted,
    )


@router.get("/governance/kpis")
async def get_governance_kpis(
    db: Db,
    catalog: CatalogQuery = None,
    schema: SchemaQuery = None,
    tables: TablesQuery = None,
    include_deleted: IncludeDeletedQuery = False,
) -> dict[str, Any]:
    return await fetch_governance_kpis(
        db, catalog=catalog, schema=schema, tables=tables, include_deleted=include_deleted
    )


@router.get("/governance/registry")
async def get_governance_registry(
    db: Db,
    catalog: CatalogQuery = None,
    schema: SchemaQuery = None,
    tables: TablesQuery = None,
    search: SearchQuery = None,
    signal: GovernanceSignal | None = None,
    inactivity: InactivityBucket | None = None,
    missing_tag: MissingTag | None = None,
    sort: Literal["severity", "table_name", "fanout"] = "severity",
    page: PageQuery = 1,
    page_size: PageSizeQuery = DEFAULT_PAGE_SIZE,
    include_deleted: IncludeDeletedQuery = False,
) -> dict[str, Any]:
    """Governance registry — a snapshot of the catalogue, so no period parameter."""
    return await fetch_governance_registry(
        db,
        catalog=catalog,
        schema=schema,
        tables=tables,
        search=search,
        signal=signal,
        inactivity=inactivity,
        missing_tag=missing_tag,
        sort=sort,
        page=page,
        page_size=page_size,
        include_deleted=include_deleted,
    )


@router.get("/governance/charts")
async def get_governance_charts(
    db: Db,
    catalog: CatalogQuery = None,
    schema: SchemaQuery = None,
    tables: TablesQuery = None,
    include_deleted: IncludeDeletedQuery = False,
) -> dict[str, Any]:
    """Governance charts over the full snapshot scope, independent of pagination."""
    return await fetch_governance_charts(
        db, catalog=catalog, schema=schema, tables=tables, include_deleted=include_deleted
    )


@router.get("/recommendations/charts")
async def get_recommendation_charts(
    db: Db,
    catalog: CatalogQuery = None,
    schema: SchemaQuery = None,
    tables: TablesQuery = None,
    include_deleted: IncludeDeletedQuery = False,
) -> dict[str, Any]:
    """OPEN table episodes only; global consumer recommendations remain on their list API."""
    return await fetch_recommendation_charts(
        db, catalog=catalog, schema=schema, tables=tables, include_deleted=include_deleted
    )


@router.get("/charts/writes")
async def get_write_charts(
    db: Db,
    period_start: PeriodStart,
    period_end: PeriodEnd,
    catalog: CatalogQuery = None,
    schema: SchemaQuery = None,
    tables: TablesQuery = None,
    include_deleted: IncludeDeletedQuery = False,
) -> dict[str, Any]:
    start, end = resolve_period(period_start, period_end)
    return await fetch_write_charts(
        db,
        start=start,
        end=end,
        catalog=catalog,
        schema=schema,
        tables=tables,
        include_deleted=include_deleted,
    )


@router.get("/charts/cost-changes")
async def get_cost_changes(
    db: Db,
    period_start: PeriodStart,
    period_end: PeriodEnd,
    catalog: CatalogQuery = None,
    schema: SchemaQuery = None,
    tables: TablesQuery = None,
    include_deleted: IncludeDeletedQuery = False,
) -> dict[str, Any]:
    start, end = resolve_period(period_start, period_end)
    return await fetch_cost_changes(
        db,
        start=start,
        end=end,
        catalog=catalog,
        schema=schema,
        tables=tables,
        include_deleted=include_deleted,
    )


@router.get("/details")
async def get_usage_details(
    db: Db,
    period_start: PeriodStart,
    period_end: PeriodEnd,
    entity_kind: Literal["table", "consumer"],
    entity_id: Annotated[str, Query(min_length=1, max_length=1024)],
    catalog: CatalogQuery = None,
    schema: SchemaQuery = None,
    tables: TablesQuery = None,
    include_deleted: IncludeDeletedQuery = False,
) -> dict[str, Any]:
    start, end = resolve_period(period_start, period_end)
    return await fetch_entity_detail(
        db,
        start=start,
        end=end,
        entity_kind=entity_kind,
        entity_id=entity_id,
        catalog=catalog,
        schema=schema,
        tables=tables,
        include_deleted=include_deleted,
    )
