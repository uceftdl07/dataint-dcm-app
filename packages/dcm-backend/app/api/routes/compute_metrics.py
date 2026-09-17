"""Compute Metrics API routes — gold ``gold_dbx_compute_*`` tables.

Routes
------
GET /api/v1/databricks/compute/clusters/overview
GET /api/v1/databricks/compute/clusters/cost
GET /api/v1/databricks/compute/clusters/efficiency
GET /api/v1/databricks/compute/clusters/governance
GET /api/v1/databricks/compute/clusters/{cluster_id}
GET /api/v1/databricks/compute/clusters/{cluster_id}/cost-trend
GET /api/v1/databricks/compute/clusters/{cluster_id}/lifetime-trend
GET /api/v1/databricks/compute/warehouses/overview
GET /api/v1/databricks/compute/warehouses/cost
GET /api/v1/databricks/compute/warehouses/query-performance
GET /api/v1/databricks/compute/warehouses/slow-queries
GET /api/v1/databricks/compute/warehouses/{warehouse_id}
GET /api/v1/databricks/compute/warehouses/{warehouse_id}/cost-trend
GET /api/v1/databricks/compute/jobs/overview
GET /api/v1/databricks/compute/jobs/cost
GET /api/v1/databricks/compute/jobs/efficiency
GET /api/v1/databricks/compute/jobs/{job_id}
GET /api/v1/databricks/compute/jobs/{job_id}/cost-trend
GET /api/v1/databricks/compute/jobs/{job_id}/uptime-trend
GET /api/v1/databricks/compute/pipelines/overview
GET /api/v1/databricks/compute/pipelines/cost
GET /api/v1/databricks/compute/pipelines/efficiency
GET /api/v1/databricks/compute/pipelines/{dlt_pipeline_id}
GET /api/v1/databricks/compute/pipelines/{dlt_pipeline_id}/cost-trend
GET /api/v1/databricks/compute/pipelines/{dlt_pipeline_id}/uptime-trend
GET /api/v1/databricks/compute/recommendations
GET /api/v1/databricks/compute/recommendations/summary
GET /api/v1/databricks/compute/forecast
GET /api/v1/databricks/compute/filter-options
GET /api/v1/databricks/compute/serverless/overview
GET /api/v1/databricks/compute/serverless/surfaces
GET /api/v1/databricks/compute/serverless/cost-trend
GET /api/v1/databricks/compute/serverless/governance
GET /api/v1/databricks/compute/serverless/levers
GET /api/v1/databricks/compute/serverless/objects
GET /api/v1/databricks/compute/serverless/objects/{object_id}
GET /api/v1/databricks/compute/serverless/objects/{object_id}/cost-trend
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.routing import APIRouter

from ...auth.dependencies import get_allowed_lz_ids, get_allowed_workspace_ids
from ...config import Settings
from ...db.connection import DatabricksWarehousePool, get_db
from ...db.lz_scope import narrow_workspace_ids, resolve_request_lz_workspace_ids
from ..services.compute_metrics_clusters import (
    fetch_cluster_cost_trend,
    fetch_cluster_detail,
    fetch_cluster_lifetime_trend,
    fetch_clusters_cost,
    fetch_clusters_efficiency,
    fetch_clusters_governance,
    fetch_clusters_overview,
)
from ..services.compute_metrics_common import RollingWindowDays
from ..services.compute_metrics_filters import FILTERABLE_COLUMNS, fetch_filter_options
from ..services.compute_metrics_forecast import fetch_forecast
from ..services.compute_metrics_jobs import (
    fetch_job_cost_trend,
    fetch_job_detail,
    fetch_job_uptime_trend,
    fetch_jobs_cost,
    fetch_jobs_efficiency,
    fetch_jobs_overview,
)
from ..services.compute_metrics_pipelines import (
    fetch_pipeline_cost_trend,
    fetch_pipeline_detail,
    fetch_pipeline_uptime_trend,
    fetch_pipelines_cost,
    fetch_pipelines_efficiency,
    fetch_pipelines_overview,
)
from ..services.compute_metrics_recommendations import (
    fetch_recommendations,
    fetch_recommendations_summary,
)
from ..services.compute_metrics_serverless import (
    ServerlessSurface,
    fetch_serverless_cost_trend,
    fetch_serverless_governance,
    fetch_serverless_levers,
    fetch_serverless_object_cost_trend,
    fetch_serverless_object_detail,
    fetch_serverless_objects,
    fetch_serverless_overview,
    fetch_serverless_surfaces,
)
from ..services.compute_metrics_warehouses import (
    fetch_warehouse_cost_trend,
    fetch_warehouse_detail,
    fetch_warehouse_slow_queries,
    fetch_warehouses_cost,
    fetch_warehouses_overview,
    fetch_warehouses_query_performance,
)
from ._lz_filter import SourceLzIdQuery, SourceLzIdsQuery

__all__ = ["router"]

router = APIRouter()


def _settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[attr-defined, no-any-return]


WorkspaceIdsQuery = Annotated[
    list[str] | None,
    Query(description="Filter by one or more Databricks workspace IDs."),
]

WorkspaceIdQuery = Annotated[
    str | None,
    Query(description="Filter by a single Databricks workspace ID."),
]

CloudProviderQuery = Annotated[
    str | None,
    Query(description="Filter by cloud provider (azure or aws)."),
]

PeriodStartQuery = Annotated[
    date | None,
    Query(description="Inclusive period start date."),
]

PeriodEndQuery = Annotated[
    date | None,
    Query(description="Inclusive period end date."),
]

PageQuery = Annotated[int, Query(ge=1)]
PageSizeQuery = Annotated[int, Query(ge=1, le=200)]

WindowDaysQuery = Annotated[
    RollingWindowDays,
    Query(
        description=(
            "Rolling window read from gold: 1, 7, 30 or 90 days. "
            "Any other value is rejected — never rounded down to 1."
        )
    ),
]

GranularityQuery = Annotated[
    str,
    Query(description="day|week|month"),
]

SurfaceQuery = Annotated[
    ServerlessSurface | None,
    Query(
        description=(
            "Filter by one of the twelve serverless surfaces. Rejected with 422 when it "
            "is not one of them — the surface set is a closed gold vocabulary, so an "
            "unknown value is a caller mistake and never an empty perimeter."
        )
    ),
]

RequiredSurfaceQuery = Annotated[
    ServerlessSurface,
    Query(
        description=(
            "Required: the gold grain is (cloud, workspace, surface, object_id), so an "
            "object id alone does not identify a row."
        )
    ),
]

ColumnFilterQuery = Annotated[
    list[str] | None,
    Query(
        alias="column_filter",
        description=(
            "Per-column filter, repeatable, as ``key:value`` — e.g. "
            "``column_filter=workspace:adb-123&column_filter=cost:100``. The key must be "
            "declared for the view (see GET /filter-options); an unknown key is a 422, "
            "never a silently empty page. Repeating the same key is refused rather than "
            "guessing between AND and OR."
        ),
    ),
]


def _normalize_workspace_ids(
    workspace_id: str | None = None,
    workspace_ids: list[str] | None = None,
) -> list[str] | None:
    """None = no filter; [] = empty selection; otherwise unique workspace ids."""
    if workspace_ids is not None:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in workspace_ids:
            item = value.strip()
            if not item or item in seen:
                continue
            seen.add(item)
            normalized.append(item)
        return normalized

    if workspace_id is not None:
        item = workspace_id.strip()
        return [item] if item else []

    return None


async def _common_scope_kwargs(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    allowed_lz_ids: list[str] | None,
    allowed_workspace_ids: list[str] | None,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
    workspace_id: str | None,
    workspace_ids: list[str] | None,
    cloud_provider: str | None,
    period_start: date | None,
    period_end: date | None,
) -> dict[str, Any]:
    # ``gold_dbx_compute_*`` tables carry ``workspace_id`` but no ``source_lz_id``,
    # so the header LZ selector is resolved to its workspaces and ANDed with the
    # workspace filter — the request can only ever narrow the RBAC scope.
    lz_workspace_ids = await resolve_request_lz_workspace_ids(
        db, settings, source_lz_id=source_lz_id, source_lz_ids=source_lz_ids
    )
    effective_workspace_ids = narrow_workspace_ids(
        _normalize_workspace_ids(workspace_id, workspace_ids), lz_workspace_ids
    )
    return {
        "allowed_lz_ids": allowed_lz_ids,
        "allowed_workspace_ids": allowed_workspace_ids,
        "source_lz_id": None,
        "source_lz_ids": None,
        "workspace_ids": effective_workspace_ids,
        "cloud_provider": cloud_provider,
        "period_start": period_start,
        "period_end": period_end,
    }


@router.get("/filter-options")
async def get_compute_filter_options(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    view: Annotated[
        str,
        Query(description="One of: " + ", ".join(sorted(FILTERABLE_COLUMNS))),
    ],
    column: Annotated[
        str,
        Query(description="Column key declared for that view; unknown key = 422."),
    ],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    q: str | None = Query(default=None, description="Case-insensitive substring."),
    limit: int | None = Query(default=None, ge=1, le=200),
    window_days: WindowDaysQuery = RollingWindowDays.DAY,
) -> dict[str, Any]:
    """Values offered for one filterable column, in the caller's own perimeter.

    Declared before ``/clusters/{cluster_id}`` and ``/warehouses/{warehouse_id}``: a
    variable segment declared first would swallow ``filter-options`` as a cluster id.
    Answers for the eleven compute views — the two Lakeflow ones are served by
    ``GET /api/v1/lakeflow/filter-options``, which resolves a different perimeter. The
    two serverless views of spec 025 are served **here**, deliberately: they read the
    same landing-zone/workspace perimeter as the other compute views, so a dedicated
    ``/serverless/filter-options`` would only duplicate this handler.
    """
    return await fetch_filter_options(
        db,
        settings,
        view,
        column,
        q=q,
        limit=limit,
        window_days=int(window_days),
        **(await _common_scope_kwargs(
            db,
            settings,
            allowed_lz_ids=allowed_lz_ids,
            allowed_workspace_ids=allowed_workspace_ids,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_id=workspace_id,
            workspace_ids=workspace_ids,
            cloud_provider=cloud_provider,
            period_start=period_start,
            period_end=period_end,
        )),
    )


@router.get("/clusters/overview")
async def get_clusters_overview(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    search: str | None = Query(default=None),
    utilization_status: str | None = Query(default=None),
    column_filter: ColumnFilterQuery = None,
    sort: str | None = Query(
        default=None,
        description=(
            "cluster|workspace|cluster_type|cost|cost_prev|cluster_lifetime|"
            "cluster_lifetime_prev|utilization|governance — anything else sorts by cost"
        ),
    ),
    sort_direction: str | None = Query(default=None, description="asc|desc"),
    page: PageQuery = 1,
    page_size: PageSizeQuery = 25,
    window_days: WindowDaysQuery = RollingWindowDays.DAY,
) -> dict[str, Any]:
    return await fetch_clusters_overview(
        db,
        settings,
        **(await _common_scope_kwargs(
            db,
            settings,
            allowed_lz_ids=allowed_lz_ids,
            allowed_workspace_ids=allowed_workspace_ids,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_id=workspace_id,
            workspace_ids=workspace_ids,
            cloud_provider=cloud_provider,
            period_start=period_start,
            period_end=period_end,
        )),
        search=search,
        utilization_status=utilization_status,
        sort=sort,
        column_filter=column_filter,
        sort_direction=sort_direction,
        page=page,
        page_size=page_size,
        window_days=window_days,
    )


@router.get("/clusters/cost")
async def list_clusters_cost(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    search: str | None = Query(default=None),
    sku_group: str | None = Query(default=None),
    column_filter: ColumnFilterQuery = None,
    sort: str = Query(default="cost_desc", description="cost_desc|name|rank"),
    page: PageQuery = 1,
    page_size: PageSizeQuery = 25,
    window_days: WindowDaysQuery = RollingWindowDays.DAY,
) -> dict[str, Any]:
    return await fetch_clusters_cost(
        db,
        settings,
        **(await _common_scope_kwargs(
            db,
            settings,
            allowed_lz_ids=allowed_lz_ids,
            allowed_workspace_ids=allowed_workspace_ids,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_id=workspace_id,
            workspace_ids=workspace_ids,
            cloud_provider=cloud_provider,
            period_start=period_start,
            period_end=period_end,
        )),
        search=search,
        sku_group=sku_group,
        column_filter=column_filter,
        sort=sort,
        page=page,
        page_size=page_size,
        window_days=window_days,
    )


@router.get("/clusters/efficiency")
async def list_clusters_efficiency(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    utilization_status: str | None = Query(default=None),
    is_zombie: bool | None = Query(default=None),
    column_filter: ColumnFilterQuery = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 25,
    window_days: WindowDaysQuery = RollingWindowDays.DAY,
) -> dict[str, Any]:
    return await fetch_clusters_efficiency(
        db,
        settings,
        **(await _common_scope_kwargs(
            db,
            settings,
            allowed_lz_ids=allowed_lz_ids,
            allowed_workspace_ids=allowed_workspace_ids,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_id=workspace_id,
            workspace_ids=workspace_ids,
            cloud_provider=cloud_provider,
            period_start=period_start,
            period_end=period_end,
        )),
        utilization_status=utilization_status,
        is_zombie=is_zombie,
        column_filter=column_filter,
        page=page,
        page_size=page_size,
        window_days=window_days,
    )


@router.get("/clusters/governance")
async def list_clusters_governance(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    severity: str | None = Query(default=None),
    missing_tags: bool | None = Query(default=None),
    dbr_obsolete: bool | None = Query(default=None),
    column_filter: ColumnFilterQuery = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 25,
) -> dict[str, Any]:
    return await fetch_clusters_governance(
        db,
        settings,
        **(await _common_scope_kwargs(
            db,
            settings,
            allowed_lz_ids=allowed_lz_ids,
            allowed_workspace_ids=allowed_workspace_ids,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_id=workspace_id,
            workspace_ids=workspace_ids,
            cloud_provider=cloud_provider,
            period_start=period_start,
            period_end=period_end,
        )),
        severity=severity,
        missing_tags=missing_tags,
        dbr_obsolete=dbr_obsolete,
        column_filter=column_filter,
        page=page,
        page_size=page_size,
    )


@router.get("/clusters/{cluster_id}")
async def get_cluster_detail(
    cluster_id: str,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    window_days: WindowDaysQuery = RollingWindowDays.DAY,
) -> dict[str, Any]:
    scope = await _common_scope_kwargs(
        db,
        settings,
        allowed_lz_ids=allowed_lz_ids,
        allowed_workspace_ids=allowed_workspace_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        cloud_provider=cloud_provider,
        period_start=period_start,
        period_end=period_end,
    )
    scope.pop("allowed_lz_ids")
    result = await fetch_cluster_detail(
        db, settings, allowed_lz_ids, cluster_id, **scope, window_days=window_days
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cluster not found")
    return result


@router.get("/clusters/{cluster_id}/cost-trend")
async def get_cluster_cost_trend(
    cluster_id: str,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    granularity: GranularityQuery = "day",
) -> dict[str, Any]:
    scope = await _common_scope_kwargs(
        db,
        settings,
        allowed_lz_ids=allowed_lz_ids,
        allowed_workspace_ids=allowed_workspace_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        cloud_provider=cloud_provider,
        period_start=period_start,
        period_end=period_end,
    )
    scope.pop("allowed_lz_ids")
    return await fetch_cluster_cost_trend(
        db, settings, allowed_lz_ids, cluster_id, **scope, granularity=granularity
    )


@router.get("/clusters/{cluster_id}/lifetime-trend")
async def get_cluster_lifetime_trend(
    cluster_id: str,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    granularity: GranularityQuery = "day",
) -> dict[str, Any]:
    """Uptime / idle series of a cluster — no ``window_days`` here.

    A trend is a series over the requested period, which the ``*_rolling`` tables
    cannot serve: they hold one point per window.
    """
    scope = await _common_scope_kwargs(
        db,
        settings,
        allowed_lz_ids=allowed_lz_ids,
        allowed_workspace_ids=allowed_workspace_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        cloud_provider=cloud_provider,
        period_start=period_start,
        period_end=period_end,
    )
    scope.pop("allowed_lz_ids")
    return await fetch_cluster_lifetime_trend(
        db, settings, allowed_lz_ids, cluster_id, **scope, granularity=granularity
    )


@router.get("/warehouses/overview")
async def get_warehouses_overview(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    search: str | None = Query(default=None),
    warehouse_size: str | None = Query(default=None),
    min_failure_rate_pct: float | None = Query(default=None),
    column_filter: ColumnFilterQuery = None,
    sort: str | None = Query(
        default=None,
        description=(
            "warehouse|workspace|size|type|cost|queries|failure|latency — "
            "anything else sorts by cost"
        ),
    ),
    sort_direction: str | None = Query(default=None, description="asc|desc"),
    page: PageQuery = 1,
    page_size: PageSizeQuery = 25,
    window_days: WindowDaysQuery = RollingWindowDays.DAY,
) -> dict[str, Any]:
    return await fetch_warehouses_overview(
        db,
        settings,
        **(await _common_scope_kwargs(
            db,
            settings,
            allowed_lz_ids=allowed_lz_ids,
            allowed_workspace_ids=allowed_workspace_ids,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_id=workspace_id,
            workspace_ids=workspace_ids,
            cloud_provider=cloud_provider,
            period_start=period_start,
            period_end=period_end,
        )),
        search=search,
        warehouse_size=warehouse_size,
        min_failure_rate_pct=min_failure_rate_pct,
        column_filter=column_filter,
        sort=sort,
        sort_direction=sort_direction,
        page=page,
        page_size=page_size,
        window_days=window_days,
    )


@router.get("/warehouses/cost")
async def list_warehouses_cost(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    search: str | None = Query(default=None),
    warehouse_size: str | None = Query(default=None),
    column_filter: ColumnFilterQuery = None,
    sort: str = Query(default="cost_desc"),
    page: PageQuery = 1,
    page_size: PageSizeQuery = 25,
    window_days: WindowDaysQuery = RollingWindowDays.DAY,
) -> dict[str, Any]:
    return await fetch_warehouses_cost(
        db,
        settings,
        **(await _common_scope_kwargs(
            db,
            settings,
            allowed_lz_ids=allowed_lz_ids,
            allowed_workspace_ids=allowed_workspace_ids,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_id=workspace_id,
            workspace_ids=workspace_ids,
            cloud_provider=cloud_provider,
            period_start=period_start,
            period_end=period_end,
        )),
        search=search,
        warehouse_size=warehouse_size,
        sort=sort,
        column_filter=column_filter,
        page=page,
        page_size=page_size,
        window_days=window_days,
    )


@router.get("/warehouses/query-performance")
async def list_warehouses_query_performance(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    min_failure_rate_pct: float | None = Query(default=None),
    has_spill: bool | None = Query(default=None),
    min_latency_p95_ms: float | None = Query(default=None),
    column_filter: ColumnFilterQuery = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 25,
    window_days: WindowDaysQuery = RollingWindowDays.DAY,
) -> dict[str, Any]:
    return await fetch_warehouses_query_performance(
        db,
        settings,
        **(await _common_scope_kwargs(
            db,
            settings,
            allowed_lz_ids=allowed_lz_ids,
            allowed_workspace_ids=allowed_workspace_ids,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_id=workspace_id,
            workspace_ids=workspace_ids,
            cloud_provider=cloud_provider,
            period_start=period_start,
            period_end=period_end,
        )),
        min_failure_rate_pct=min_failure_rate_pct,
        has_spill=has_spill,
        min_latency_p95_ms=min_latency_p95_ms,
        column_filter=column_filter,
        page=page,
        page_size=page_size,
        window_days=window_days,
    )


@router.get("/warehouses/slow-queries")
async def list_warehouse_slow_queries(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    warehouse_id: str | None = Query(default=None),
    reason: str | None = Query(default=None),
    column_filter: ColumnFilterQuery = None,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 25,
) -> dict[str, Any]:
    return await fetch_warehouse_slow_queries(
        db,
        settings,
        **(await _common_scope_kwargs(
            db,
            settings,
            allowed_lz_ids=allowed_lz_ids,
            allowed_workspace_ids=allowed_workspace_ids,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_id=workspace_id,
            workspace_ids=workspace_ids,
            cloud_provider=cloud_provider,
            period_start=period_start,
            period_end=period_end,
        )),
        warehouse_id=warehouse_id,
        reason=reason,
        column_filter=column_filter,
        page=page,
        page_size=page_size,
    )


@router.get("/warehouses/{warehouse_id}")
async def get_warehouse_detail(
    warehouse_id: str,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
) -> dict[str, Any]:
    scope = await _common_scope_kwargs(
        db,
        settings,
        allowed_lz_ids=allowed_lz_ids,
        allowed_workspace_ids=allowed_workspace_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        cloud_provider=cloud_provider,
        period_start=period_start,
        period_end=period_end,
    )
    scope.pop("allowed_lz_ids")
    result = await fetch_warehouse_detail(db, settings, allowed_lz_ids, warehouse_id, **scope)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Warehouse not found")
    return result


@router.get("/warehouses/{warehouse_id}/cost-trend")
async def get_warehouse_cost_trend(
    warehouse_id: str,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    granularity: GranularityQuery = "day",
) -> dict[str, Any]:
    scope = await _common_scope_kwargs(
        db,
        settings,
        allowed_lz_ids=allowed_lz_ids,
        allowed_workspace_ids=allowed_workspace_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        cloud_provider=cloud_provider,
        period_start=period_start,
        period_end=period_end,
    )
    scope.pop("allowed_lz_ids")
    return await fetch_warehouse_cost_trend(
        db, settings, allowed_lz_ids, warehouse_id, **scope, granularity=granularity
    )


@router.get("/jobs/overview")
async def get_jobs_overview(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    search: str | None = Query(default=None),
    sort: str = Query(default="cost_desc", description="cost_desc|name"),
    page: PageQuery = 1,
    page_size: PageSizeQuery = 25,
    window_days: WindowDaysQuery = RollingWindowDays.DAY,
) -> dict[str, Any]:
    return await fetch_jobs_overview(
        db,
        settings,
        **(await _common_scope_kwargs(
            db,
            settings,
            allowed_lz_ids=allowed_lz_ids,
            allowed_workspace_ids=allowed_workspace_ids,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_id=workspace_id,
            workspace_ids=workspace_ids,
            cloud_provider=cloud_provider,
            period_start=period_start,
            period_end=period_end,
        )),
        search=search,
        sort=sort,
        page=page,
        page_size=page_size,
        window_days=window_days,
    )


@router.get("/jobs/cost")
async def list_jobs_cost(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    search: str | None = Query(default=None),
    sort: str = Query(default="cost_desc", description="cost_desc|name"),
    page: PageQuery = 1,
    page_size: PageSizeQuery = 25,
    window_days: WindowDaysQuery = RollingWindowDays.DAY,
) -> dict[str, Any]:
    return await fetch_jobs_cost(
        db,
        settings,
        **(await _common_scope_kwargs(
            db,
            settings,
            allowed_lz_ids=allowed_lz_ids,
            allowed_workspace_ids=allowed_workspace_ids,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_id=workspace_id,
            workspace_ids=workspace_ids,
            cloud_provider=cloud_provider,
            period_start=period_start,
            period_end=period_end,
        )),
        search=search,
        sort=sort,
        page=page,
        page_size=page_size,
        window_days=window_days,
    )


@router.get("/jobs/efficiency")
async def list_jobs_efficiency(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    search: str | None = Query(default=None),
    sort: str = Query(default="savings_desc", description="savings_desc|uptime|name"),
    page: PageQuery = 1,
    page_size: PageSizeQuery = 25,
    window_days: WindowDaysQuery = RollingWindowDays.DAY,
) -> dict[str, Any]:
    """Utilization of each job over the window — declared BEFORE ``/jobs/{job_id}``.

    A variable segment declared first would win, and ``efficiency`` would be read as
    a job id: the list would answer 404. Same trap as ``/filter-options``.

    This population is smaller than ``/jobs/cost``: efficiency comes from
    ``node_timeline``, cost from billing (024 SC-005, 99,0 % measured in dev).
    """
    return await fetch_jobs_efficiency(
        db,
        settings,
        **(await _common_scope_kwargs(
            db,
            settings,
            allowed_lz_ids=allowed_lz_ids,
            allowed_workspace_ids=allowed_workspace_ids,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_id=workspace_id,
            workspace_ids=workspace_ids,
            cloud_provider=cloud_provider,
            period_start=period_start,
            period_end=period_end,
        )),
        search=search,
        sort=sort,
        page=page,
        page_size=page_size,
        window_days=window_days,
    )


@router.get("/jobs/{job_id}")
async def get_job_detail(
    job_id: str,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    window_days: WindowDaysQuery = RollingWindowDays.DAY,
) -> dict[str, Any]:
    """Cost and efficiency of one job — **no** ``governance`` key (024 C2).

    ``efficiency: null`` is a normal answer (the job ran on compute with no
    ``node_timeline`` row); a job outside the caller's perimeter is a 404.
    """
    scope = await _common_scope_kwargs(
        db,
        settings,
        allowed_lz_ids=allowed_lz_ids,
        allowed_workspace_ids=allowed_workspace_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        cloud_provider=cloud_provider,
        period_start=period_start,
        period_end=period_end,
    )
    scope.pop("allowed_lz_ids")
    result = await fetch_job_detail(
        db, settings, allowed_lz_ids, job_id, **scope, window_days=window_days
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return result


@router.get("/jobs/{job_id}/cost-trend")
async def get_job_cost_trend(
    job_id: str,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    granularity: GranularityQuery = "day",
) -> dict[str, Any]:
    scope = await _common_scope_kwargs(
        db,
        settings,
        allowed_lz_ids=allowed_lz_ids,
        allowed_workspace_ids=allowed_workspace_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        cloud_provider=cloud_provider,
        period_start=period_start,
        period_end=period_end,
    )
    scope.pop("allowed_lz_ids")
    return await fetch_job_cost_trend(
        db, settings, allowed_lz_ids, job_id, **scope, granularity=granularity
    )


@router.get("/jobs/{job_id}/uptime-trend")
async def get_job_uptime_trend(
    job_id: str,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    granularity: GranularityQuery = "day",
) -> dict[str, Any]:
    """Cumulated uptime / idle series of a job — no ``window_days`` here.

    Named ``uptime-trend`` and not ``lifetime-trend`` like its cluster homologue:
    "lifetime" has no meaning for a cluster destroyed at the end of every run.
    """
    scope = await _common_scope_kwargs(
        db,
        settings,
        allowed_lz_ids=allowed_lz_ids,
        allowed_workspace_ids=allowed_workspace_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        cloud_provider=cloud_provider,
        period_start=period_start,
        period_end=period_end,
    )
    scope.pop("allowed_lz_ids")
    return await fetch_job_uptime_trend(
        db, settings, allowed_lz_ids, job_id, **scope, granularity=granularity
    )


@router.get("/pipelines/overview")
async def get_pipelines_overview(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    search: str | None = Query(default=None),
    sort: str = Query(default="cost_desc", description="cost_desc|name"),
    page: PageQuery = 1,
    page_size: PageSizeQuery = 25,
    window_days: WindowDaysQuery = RollingWindowDays.DAY,
) -> dict[str, Any]:
    return await fetch_pipelines_overview(
        db,
        settings,
        **(await _common_scope_kwargs(
            db,
            settings,
            allowed_lz_ids=allowed_lz_ids,
            allowed_workspace_ids=allowed_workspace_ids,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_id=workspace_id,
            workspace_ids=workspace_ids,
            cloud_provider=cloud_provider,
            period_start=period_start,
            period_end=period_end,
        )),
        search=search,
        sort=sort,
        page=page,
        page_size=page_size,
        window_days=window_days,
    )


@router.get("/pipelines/cost")
async def list_pipelines_cost(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    search: str | None = Query(default=None),
    sort: str = Query(default="cost_desc", description="cost_desc|name"),
    page: PageQuery = 1,
    page_size: PageSizeQuery = 25,
    window_days: WindowDaysQuery = RollingWindowDays.DAY,
) -> dict[str, Any]:
    return await fetch_pipelines_cost(
        db,
        settings,
        **(await _common_scope_kwargs(
            db,
            settings,
            allowed_lz_ids=allowed_lz_ids,
            allowed_workspace_ids=allowed_workspace_ids,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_id=workspace_id,
            workspace_ids=workspace_ids,
            cloud_provider=cloud_provider,
            period_start=period_start,
            period_end=period_end,
        )),
        search=search,
        sort=sort,
        page=page,
        page_size=page_size,
        window_days=window_days,
    )


@router.get("/pipelines/efficiency")
async def list_pipelines_efficiency(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    search: str | None = Query(default=None),
    sort: str = Query(default="savings_desc", description="savings_desc|uptime|name"),
    page: PageQuery = 1,
    page_size: PageSizeQuery = 25,
    window_days: WindowDaysQuery = RollingWindowDays.DAY,
) -> dict[str, Any]:
    """Utilization of each DLT pipeline — declared BEFORE ``/pipelines/{id}``.

    Narrower than ``/pipelines/cost``: a serverless pipeline has no
    ``node_timeline`` row, so it is billed but not measured (024 SC-005, 96,1 %
    measured in dev).
    """
    return await fetch_pipelines_efficiency(
        db,
        settings,
        **(await _common_scope_kwargs(
            db,
            settings,
            allowed_lz_ids=allowed_lz_ids,
            allowed_workspace_ids=allowed_workspace_ids,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_id=workspace_id,
            workspace_ids=workspace_ids,
            cloud_provider=cloud_provider,
            period_start=period_start,
            period_end=period_end,
        )),
        search=search,
        sort=sort,
        page=page,
        page_size=page_size,
        window_days=window_days,
    )


@router.get("/pipelines/{dlt_pipeline_id}")
async def get_pipeline_detail(
    dlt_pipeline_id: str,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    window_days: WindowDaysQuery = RollingWindowDays.DAY,
) -> dict[str, Any]:
    """Cost and efficiency of one pipeline — **no** ``governance`` key (024 C2)."""
    scope = await _common_scope_kwargs(
        db,
        settings,
        allowed_lz_ids=allowed_lz_ids,
        allowed_workspace_ids=allowed_workspace_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        cloud_provider=cloud_provider,
        period_start=period_start,
        period_end=period_end,
    )
    scope.pop("allowed_lz_ids")
    result = await fetch_pipeline_detail(
        db, settings, allowed_lz_ids, dlt_pipeline_id, **scope, window_days=window_days
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found"
        )
    return result


@router.get("/pipelines/{dlt_pipeline_id}/cost-trend")
async def get_pipeline_cost_trend(
    dlt_pipeline_id: str,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    granularity: GranularityQuery = "day",
) -> dict[str, Any]:
    scope = await _common_scope_kwargs(
        db,
        settings,
        allowed_lz_ids=allowed_lz_ids,
        allowed_workspace_ids=allowed_workspace_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        cloud_provider=cloud_provider,
        period_start=period_start,
        period_end=period_end,
    )
    scope.pop("allowed_lz_ids")
    return await fetch_pipeline_cost_trend(
        db,
        settings,
        allowed_lz_ids,
        dlt_pipeline_id,
        **scope,
        granularity=granularity,
    )


@router.get("/pipelines/{dlt_pipeline_id}/uptime-trend")
async def get_pipeline_uptime_trend(
    dlt_pipeline_id: str,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    granularity: GranularityQuery = "day",
) -> dict[str, Any]:
    """Cumulated uptime / idle series of a pipeline — no ``window_days`` here."""
    scope = await _common_scope_kwargs(
        db,
        settings,
        allowed_lz_ids=allowed_lz_ids,
        allowed_workspace_ids=allowed_workspace_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        cloud_provider=cloud_provider,
        period_start=period_start,
        period_end=period_end,
    )
    scope.pop("allowed_lz_ids")
    return await fetch_pipeline_uptime_trend(
        db,
        settings,
        allowed_lz_ids,
        dlt_pipeline_id,
        **scope,
        granularity=granularity,
    )


@router.get("/recommendations")
async def list_recommendations(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    object_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    column_filter: ColumnFilterQuery = None,
    sort: str | None = Query(default=None),
    order: str | None = Query(default=None),
    page: PageQuery = 1,
    page_size: PageSizeQuery = 25,
) -> dict[str, Any]:
    return await fetch_recommendations(
        db,
        settings,
        **(await _common_scope_kwargs(
            db,
            settings,
            allowed_lz_ids=allowed_lz_ids,
            allowed_workspace_ids=allowed_workspace_ids,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_id=workspace_id,
            workspace_ids=workspace_ids,
            cloud_provider=cloud_provider,
            period_start=period_start,
            period_end=period_end,
        )),
        object_type=object_type,
        category=category,
        severity=severity,
        status=status,
        search=search,
        sort=sort,
        order=order,
        column_filter=column_filter,
        page=page,
        page_size=page_size,
    )


@router.get("/recommendations/summary")
async def get_recommendations_summary(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
) -> dict[str, Any]:
    return await fetch_recommendations_summary(
        db,
        settings,
        **(await _common_scope_kwargs(
            db,
            settings,
            allowed_lz_ids=allowed_lz_ids,
            allowed_workspace_ids=allowed_workspace_ids,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_id=workspace_id,
            workspace_ids=workspace_ids,
            cloud_provider=cloud_provider,
            period_start=period_start,
            period_end=period_end,
        )),
    )


@router.get("/forecast")
async def get_forecast(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    metric_name: str | None = Query(default=None),
    object_type: str | None = Query(default=None),
    object_id: str | None = Query(default=None),
) -> dict[str, Any]:
    return await fetch_forecast(
        db,
        settings,
        **(await _common_scope_kwargs(
            db,
            settings,
            allowed_lz_ids=allowed_lz_ids,
            allowed_workspace_ids=allowed_workspace_ids,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            workspace_id=workspace_id,
            workspace_ids=workspace_ids,
            cloud_provider=cloud_provider,
            period_start=period_start,
            period_end=period_end,
        )),
        metric_name=metric_name,
        object_type=object_type,
        object_id=object_id,
    )


# --------------------------------------------------------------------------------------
# Serverless — spec 025.
#
# The five aggregate routes are declared **before** ``/serverless/objects/{object_id}``
# for the same reason ``/filter-options`` is declared before ``/clusters/{cluster_id}``:
# a variable segment declared first would swallow the static ones. There is deliberately
# **no** ``/serverless/filter-options``: the generic route is driven by
# ``FILTERABLE_COLUMNS``, which now carries ``serverless-objects`` and
# ``serverless-governance``, so a second route would be a second thing to keep in sync.
# --------------------------------------------------------------------------------------


@router.get("/serverless/overview")
async def get_serverless_overview(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    window_days: WindowDaysQuery = RollingWindowDays.DAY,
) -> dict[str, Any]:
    """Serverless KPIs for one window, plus the share of total compute spend.

    ``share_of_compute_pct`` is ``null`` rather than ``100`` when the classic
    denominator cannot be read: a share computed on serverless alone would say
    "serverless is all of your compute", which is the one answer that is never true.
    """
    scope = await _common_scope_kwargs(
        db,
        settings,
        allowed_lz_ids=allowed_lz_ids,
        allowed_workspace_ids=allowed_workspace_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        cloud_provider=cloud_provider,
        period_start=period_start,
        period_end=period_end,
    )
    scope.pop("allowed_lz_ids")
    return await fetch_serverless_overview(
        db, settings, allowed_lz_ids, **scope, window_days=window_days
    )


@router.get("/serverless/surfaces")
async def list_serverless_surfaces(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    sort: str = Query(
        default="cost",
        description="cost|surface|dbu|objects|runs|delta — anything else sorts by cost",
    ),
    sort_direction: str | None = Query(default=None, description="asc|desc"),
    page: PageQuery = 1,
    page_size: PageSizeQuery = 25,
    window_days: WindowDaysQuery = RollingWindowDays.DAY,
) -> dict[str, Any]:
    """One row per serverless surface, with its share of the serverless spend."""
    scope = await _common_scope_kwargs(
        db,
        settings,
        allowed_lz_ids=allowed_lz_ids,
        allowed_workspace_ids=allowed_workspace_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        cloud_provider=cloud_provider,
        period_start=period_start,
        period_end=period_end,
    )
    scope.pop("allowed_lz_ids")
    return await fetch_serverless_surfaces(
        db,
        settings,
        allowed_lz_ids,
        **scope,
        window_days=window_days,
        sort=sort,
        sort_direction=sort_direction or "desc",
        page=page,
        page_size=page_size,
    )


@router.get("/serverless/cost-trend")
async def get_serverless_cost_trend(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    granularity: GranularityQuery = "day",
    surface: SurfaceQuery = None,
) -> dict[str, Any]:
    """Daily serverless cost, read from the **daily** table — no ``window_days``.

    Without ``surface``, the series is split across the top surfaces by spend and the
    rest is folded into ``OTHER_SURFACES`` — spelled with the suffix precisely because
    ``OTHER`` is itself one of the twelve real surfaces, and a bucket named after it
    would be indistinguishable from it.
    """
    scope = await _common_scope_kwargs(
        db,
        settings,
        allowed_lz_ids=allowed_lz_ids,
        allowed_workspace_ids=allowed_workspace_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        cloud_provider=cloud_provider,
        period_start=period_start,
        period_end=period_end,
    )
    scope.pop("allowed_lz_ids")
    return await fetch_serverless_cost_trend(
        db,
        settings,
        allowed_lz_ids,
        **scope,
        granularity=granularity,
        surface=surface.value if surface else None,
    )


@router.get("/serverless/governance")
async def list_serverless_governance(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    column_filter: ColumnFilterQuery = None,
    sort: str = Query(
        default="cost",
        description=(
            "cost|workspace|surface|owner_tag|cost_center_tag|budget_policy|identity "
            "— anything else sorts by cost"
        ),
    ),
    sort_direction: str | None = Query(default=None, description="asc|desc"),
    page: PageQuery = 1,
    page_size: PageSizeQuery = 25,
) -> dict[str, Any]:
    """Tag, budget-policy and identity coverage per (workspace, surface).

    **No ``window_days``**: the gold table is a snapshot carrying its own
    ``window_start``/``window_end``, returned as ``governance_period`` so the numbers
    are never captioned with a window they were not measured on.
    """
    scope = await _common_scope_kwargs(
        db,
        settings,
        allowed_lz_ids=allowed_lz_ids,
        allowed_workspace_ids=allowed_workspace_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        cloud_provider=cloud_provider,
        period_start=period_start,
        period_end=period_end,
    )
    scope.pop("allowed_lz_ids")
    return await fetch_serverless_governance(
        db,
        settings,
        allowed_lz_ids,
        **scope,
        column_filter=column_filter,
        sort=sort,
        sort_direction=sort_direction or "desc",
        page=page,
        page_size=page_size,
    )


@router.get("/serverless/levers")
async def get_serverless_levers(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    window_days: WindowDaysQuery = RollingWindowDays.DAY,
) -> dict[str, Any]:
    """The levers that actually exist on serverless, and what they are worth here.

    ``performance_target`` and the DLT classic-versus-serverless comparison, not the
    classic knobs: there is no auto-stop and no node type to rightsize on a serverless
    surface, so a page offering them would be offering nothing.
    """
    scope = await _common_scope_kwargs(
        db,
        settings,
        allowed_lz_ids=allowed_lz_ids,
        allowed_workspace_ids=allowed_workspace_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        cloud_provider=cloud_provider,
        period_start=period_start,
        period_end=period_end,
    )
    scope.pop("allowed_lz_ids")
    return await fetch_serverless_levers(
        db, settings, allowed_lz_ids, **scope, window_days=window_days
    )


@router.get("/serverless/objects")
async def list_serverless_objects(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    surface: SurfaceQuery = None,
    search: str | None = Query(default=None, description="Object name or id."),
    column_filter: ColumnFilterQuery = None,
    sort: str = Query(
        default="cost",
        description=(
            "cost|object|surface|workspace|dbu|runs|cost_per_run|delta "
            "— anything else sorts by cost"
        ),
    ),
    sort_direction: str | None = Query(default=None, description="asc|desc"),
    page: PageQuery = 1,
    page_size: PageSizeQuery = 25,
    window_days: WindowDaysQuery = RollingWindowDays.DAY,
) -> dict[str, Any]:
    """Paginated serverless objects for one window.

    The keyless surfaces are **kept** and served with ``object_id: null`` and
    ``has_object_key: false``: they carry real cost, and dropping them would make this
    list's total disagree with ``/serverless/surfaces``. They are the rows for which
    ``/serverless/objects/{object_id}`` has nothing to answer, which is why the detail
    route 404s on the gold sentinel rather than accepting it as an id.
    """
    scope = await _common_scope_kwargs(
        db,
        settings,
        allowed_lz_ids=allowed_lz_ids,
        allowed_workspace_ids=allowed_workspace_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        cloud_provider=cloud_provider,
        period_start=period_start,
        period_end=period_end,
    )
    scope.pop("allowed_lz_ids")
    return await fetch_serverless_objects(
        db,
        settings,
        allowed_lz_ids,
        **scope,
        window_days=window_days,
        surface=surface.value if surface else None,
        search=search,
        column_filter=column_filter,
        sort=sort,
        sort_direction=sort_direction or "desc",
        page=page,
        page_size=page_size,
    )


@router.get("/serverless/objects/{object_id}")
async def get_serverless_object_detail(
    object_id: str,
    surface: RequiredSurfaceQuery,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    window_days: WindowDaysQuery = RollingWindowDays.DAY,
) -> dict[str, Any]:
    """One serverless object across the four windows, broken down per workspace.

    ``surface`` is **required**, unlike every other detail route in this module, because
    ``object_id`` alone is not a key here: the gold grain is
    ``(cloud, workspace, surface, object_id)``. Measured in dev on 2026-09-10, 4 of the
    20 583 identified objects appear under two surfaces — a materialized view billed
    both as ``DLT_PIPELINE`` and as ``MV_ST_REFRESH``. Four collisions is few, but the
    answer for them without a surface would be two different things added together, and
    a required parameter says so where a silent sum would not.
    """
    scope = await _common_scope_kwargs(
        db,
        settings,
        allowed_lz_ids=allowed_lz_ids,
        allowed_workspace_ids=allowed_workspace_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        cloud_provider=cloud_provider,
        period_start=period_start,
        period_end=period_end,
    )
    scope.pop("allowed_lz_ids")
    result = await fetch_serverless_object_detail(
        db,
        settings,
        allowed_lz_ids,
        object_id,
        surface=surface.value,
        **scope,
        window_days=window_days,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Serverless object not found"
        )
    return result


@router.get("/serverless/objects/{object_id}/cost-trend")
async def get_serverless_object_cost_trend(
    object_id: str,
    surface: RequiredSurfaceQuery,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    allowed_workspace_ids: Annotated[
        list[str] | None, Depends(get_allowed_workspace_ids)
    ],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    cloud_provider: CloudProviderQuery = None,
    period_start: PeriodStartQuery = None,
    period_end: PeriodEndQuery = None,
    granularity: GranularityQuery = "day",
) -> dict[str, Any]:
    """Daily cost of one serverless object. Empty series on the gold sentinel.

    A list route never 404s and neither does a trend: an object with no billed day in
    the period has an empty series, which is a fact about the period, not a missing
    object.
    """
    scope = await _common_scope_kwargs(
        db,
        settings,
        allowed_lz_ids=allowed_lz_ids,
        allowed_workspace_ids=allowed_workspace_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
        cloud_provider=cloud_provider,
        period_start=period_start,
        period_end=period_end,
    )
    scope.pop("allowed_lz_ids")
    return await fetch_serverless_object_cost_trend(
        db,
        settings,
        allowed_lz_ids,
        object_id,
        surface=surface.value,
        **scope,
        granularity=granularity,
    )
