"""Lakeflow (Databricks Workflows) API routes.

Routes
------
GET /api/v1/lakeflow/overview
GET /api/v1/lakeflow/jobs
GET /api/v1/lakeflow/jobs/{workflow_id}
GET /api/v1/lakeflow/jobs/{workflow_id}/runs
GET /api/v1/lakeflow/jobs/{workflow_id}/runs/{run_id}/tasks
GET /api/v1/lakeflow/filter-options
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.routing import APIRouter

from ...auth.scope import get_allowed_scope_dep
from ...auth.scope_model import AllowedScope
from ...config import Settings
from ...db.connection import DatabricksWarehousePool, get_db
from ._lz_filter import SourceLzIdQuery, SourceLzIdsQuery
from ..services.compute_metrics_filters import fetch_lakeflow_filter_options
from ..services.lakeflow_jobs import (
    fetch_lakeflow_job_detail,
    fetch_lakeflow_job_runs,
    fetch_lakeflow_jobs,
    fetch_lakeflow_run_tasks,
)
from ..services.lakeflow_overview import fetch_lakeflow_overview

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

StatusListQuery = Annotated[
    list[str] | None,
    Query(description="Filter by last-run / run status values."),
]

ColumnFilterQuery = Annotated[
    list[str] | None,
    Query(
        alias="column_filter",
        description=(
            "Per-column filter, repeatable, as ``key:value`` — e.g. "
            "``column_filter=status:success&column_filter=success_7d:90``. An unknown key "
            "is a 422, never a silently empty page; see GET /lakeflow/filter-options."
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


@router.get("/overview")
async def get_lakeflow_overview(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    scope: Annotated[AllowedScope, Depends(get_allowed_scope_dep)],
    settings: Annotated[Settings, Depends(_settings)],
    window: str = Query(
        default="today",
        description='"today" | "7d" | "30d" — ignored when start_date and end_date are set',
    ),
    start_date: Annotated[
        date | None,
        Query(description="Inclusive start date (header From). Overrides window when set with end_date."),
    ] = None,
    end_date: Annotated[
        date | None,
        Query(description="Inclusive end date (header To). Overrides window when set with start_date."),
    ] = None,
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
) -> dict[str, Any]:
    """Return aggregated Lakeflow workflow metrics for the Overview page."""
    return await fetch_lakeflow_overview(
        db,
        settings,
        scope,
        window=window,
        start_date=start_date,
        end_date=end_date,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_ids=_normalize_workspace_ids(workspace_id, workspace_ids),
    )


@router.get("/jobs")
async def list_lakeflow_jobs(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    scope: Annotated[AllowedScope, Depends(get_allowed_scope_dep)],
    settings: Annotated[Settings, Depends(_settings)],
    window: str = Query(default="30d"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    search: str | None = Query(default=None),
    status: StatusListQuery = None,
    trigger_type: Annotated[list[str] | None, Query()] = None,
    owner: Annotated[list[str] | None, Query()] = None,
    drift_only: bool = Query(default=False),
    no_runs: bool = Query(default=False),
    with_retries: bool = Query(default=False),
    column_filter: ColumnFilterQuery = None,
    sort: str = Query(
        default="problems",
        description=(
            "problems|alpha|success|success_24h|success_7d|duration|drift|"
            "p50|p95|p99|runs|retries|wait|status|trigger|run_type|last_duration|last_run"
        ),
    ),
    order: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> dict[str, Any]:
    """N1 — paginated workflow list with last-10 run history."""
    return await fetch_lakeflow_jobs(
        db,
        settings,
        scope,
        window=window,
        start_date=start_date,
        end_date=end_date,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_ids=_normalize_workspace_ids(workspace_id, workspace_ids),
        search=search,
        status=status,
        trigger_type=trigger_type,
        owner=owner,
        drift_only=drift_only,
        no_runs=no_runs,
        with_retries=with_retries,
        column_filter=column_filter,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )


@router.get("/filter-options")
async def get_lakeflow_filter_options(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    scope: Annotated[AllowedScope, Depends(get_allowed_scope_dep)],
    settings: Annotated[Settings, Depends(_settings)],
    view: Annotated[
        str,
        Query(description="lakeflow-jobs | lakeflow-job-runs"),
    ],
    column: Annotated[
        str,
        Query(description="Column key declared for that view; unknown key = 422."),
    ],
    window: str = Query(default="30d"),
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    workflow_id: Annotated[
        str | None,
        Query(description="Narrows the lakeflow-job-runs view to one workflow."),
    ] = None,
    q: str | None = Query(default=None, description="Case-insensitive substring."),
    limit: int | None = Query(default=None, ge=1, le=200),
) -> dict[str, Any]:
    """Values offered for one filterable column of the two Lakeflow tables.

    Declared before ``/jobs/{workflow_id}`` so the literal segment wins over the
    variable one. The compute views are served by
    ``GET /api/v1/databricks/compute/filter-options`` — a different perimeter.
    """
    return await fetch_lakeflow_filter_options(
        db,
        settings,
        scope,
        view,
        column,
        q=q,
        limit=limit,
        window=window,
        start_date=start_date,
        end_date=end_date,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_ids=_normalize_workspace_ids(workspace_id, workspace_ids),
        workflow_id=workflow_id,
    )


@router.get("/jobs/{workflow_id}/runs/{run_id}/tasks")
async def get_lakeflow_run_tasks(
    workflow_id: str,
    run_id: str,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    scope: Annotated[AllowedScope, Depends(get_allowed_scope_dep)],
    settings: Annotated[Settings, Depends(_settings)],
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    failed_only: bool = Query(default=False),
) -> dict[str, Any]:
    """N3 — task runs for one workflow run."""
    return await fetch_lakeflow_run_tasks(
        db,
        settings,
        scope,
        workflow_id,
        run_id,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_ids=_normalize_workspace_ids(workspace_id, workspace_ids),
        failed_only=failed_only,
    )


@router.get("/jobs/{workflow_id}/runs")
async def list_lakeflow_job_runs(
    workflow_id: str,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    scope: Annotated[AllowedScope, Depends(get_allowed_scope_dep)],
    settings: Annotated[Settings, Depends(_settings)],
    window: str = Query(default="30d"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
    search: str | None = Query(default=None),
    status: StatusListQuery = None,
    trigger_type: Annotated[list[str] | None, Query()] = None,
    with_retries: bool = Query(default=False),
    column_filter: ColumnFilterQuery = None,
    sort: str = Query(default="start_time"),
    order: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
) -> dict[str, Any]:
    """N2 — runs list + matrix for one workflow."""
    return await fetch_lakeflow_job_runs(
        db,
        settings,
        scope,
        workflow_id,
        window=window,
        start_date=start_date,
        end_date=end_date,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_ids=_normalize_workspace_ids(workspace_id, workspace_ids),
        search=search,
        status=status,
        trigger_type=trigger_type,
        with_retries=with_retries,
        column_filter=column_filter,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )


@router.get("/jobs/{workflow_id}")
async def get_lakeflow_job(
    workflow_id: str,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    scope: Annotated[AllowedScope, Depends(get_allowed_scope_dep)],
    settings: Annotated[Settings, Depends(_settings)],
    window: str = Query(default="30d"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    workspace_id: WorkspaceIdQuery = None,
    workspace_ids: WorkspaceIdsQuery = None,
) -> dict[str, Any]:
    """N2 — workflow header + KPIs."""
    detail = await fetch_lakeflow_job_detail(
        db,
        settings,
        scope,
        workflow_id,
        window=window,
        start_date=start_date,
        end_date=end_date,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        workspace_ids=_normalize_workspace_ids(workspace_id, workspace_ids),
    )
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return detail
