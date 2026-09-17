"""Standard Check endpoints — compliance evaluation results, scores, and landing zone details.

Routes
------
GET /api/v1/standard-checks
    List standard check evaluation results with filtering and pagination.
GET /api/v1/standard-checks/score
    Aggregate compliance score (% of COMPLIANT evaluations) per LZ/cloud.
    Also reads from ``standard_check_scores`` (Gold layer) when available.
GET /api/v1/landing-zones/details
    List active landing zones with metadata from ``dim_landing_zone``.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Annotated, Any

from fastapi import Depends, Query, Request
from fastapi.routing import APIRouter

from ...auth.dependencies import CurrentUser, get_allowed_lz_ids, get_current_user
from ...cache.response_cache import build_cache_key, cache_key_ids, get_cached_response
from ...config import Settings
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.governance_page import (
    fetch_governance_page_bundle,
    fetch_landing_zone_details,
    fetch_landing_zones_access_overview,
    fetch_standard_check_score,
    fetch_standard_checks_list,
)
from ._lz_filter import SourceLzIdQuery, SourceLzIdsQuery

__all__ = ["router"]

router = APIRouter()
logger = logging.getLogger(__name__)

_GOVERNANCE_CACHE_TTL_SECONDS = 120.0


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/standard-checks/page-bundle")
async def standard_checks_page_bundle(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    cloud_provider: Annotated[str | None, Query(description="Filter by cloud provider.")] = None,
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    start_date: Annotated[date | None, Query(description="Filter by evaluation date from.")] = None,
    end_date: Annotated[date | None, Query(description="Filter by evaluation date to.")] = None,
    limit: Annotated[int, Query(ge=1, le=500, description="Max checks returned in bundle.")] = 100,
) -> dict[str, Any]:
    """Return governance score + check list in one cached response (home-page pattern)."""
    return await fetch_governance_page_bundle(
        db,
        allowed_lz_ids,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@router.get("/standard-checks")
async def list_standard_checks(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    cloud_provider: Annotated[str | None, Query(description="Filter by cloud provider.")] = None,
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    subscription_or_account_id: Annotated[
        str | None, Query(description="Filter by Azure subscription or AWS account ID.")
    ] = None,
    check_state: Annotated[
        str | None, Query(description="Filter by state (compliant|non_compliant|unknown).")
    ] = None,
    resource_type: Annotated[str | None, Query(description="Filter by resource type.")] = None,
    check_name: Annotated[
        str | None, Query(description="Filter by check name (partial match).")
    ] = None,
    start_date: Annotated[date | None, Query(description="Filter by evaluation date from.")] = None,
    end_date: Annotated[date | None, Query(description="Filter by evaluation date to.")] = None,
    limit: Annotated[int, Query(ge=1, le=1000, description="Max rows to return.")] = 100,
    offset: Annotated[int, Query(ge=0, description="Rows to skip.")] = 0,
) -> dict[str, Any]:
    """Return standard check evaluation results.

    Typical usage:
    - Non-compliant resources only: ``GET /standard-checks?check_state=non_compliant``
    - For a specific LZ: ``GET /standard-checks?source_lz_id=azure-lz-prod-fr``
    - Recent evaluations: ``GET /standard-checks?start_date=2026-03-01``
    """
    cache_key = build_cache_key(
        "standard-checks-list",
        allowed_lz_ids=cache_key_ids(allowed_lz_ids),
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=cache_key_ids(source_lz_ids),
        subscription_or_account_id=subscription_or_account_id,
        check_state=check_state,
        resource_type=resource_type,
        check_name=check_name,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )

    async def load() -> dict[str, Any]:
        return await fetch_standard_checks_list(
            db,
            allowed_lz_ids,
            cloud_provider=cloud_provider,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            subscription_or_account_id=subscription_or_account_id,
            check_state=check_state,
            resource_type=resource_type,
            check_name=check_name,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

    return await get_cached_response(cache_key, load, ttl_seconds=_GOVERNANCE_CACHE_TTL_SECONDS)


@router.get("/standard-checks/score")
async def standard_check_score(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    cloud_provider: Annotated[str | None, Query(description="Filter by cloud provider.")] = None,
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    subscription_or_account_id: Annotated[
        str | None, Query(description="Filter by Azure subscription or AWS account ID.")
    ] = None,
    since: Annotated[
        date | None, Query(description="Evaluate only results since this date.")
    ] = None,
) -> dict[str, Any]:
    """Return aggregate standard check score per cloud / LZ.

    Score formula: ``compliant_count / (compliant_count + non_compliant_count) * 100``

    A score of 100 means all evaluated resources are compliant.
    ``unknown`` evaluations are excluded from the score calculation.

    Returns:
        Global score + per-(cloud_provider, source_lz_id) breakdown.
    """
    cache_key = build_cache_key(
        "standard-checks-score",
        allowed_lz_ids=cache_key_ids(allowed_lz_ids),
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=cache_key_ids(source_lz_ids),
        subscription_or_account_id=subscription_or_account_id,
        since=since,
    )

    async def load() -> dict[str, Any]:
        return await fetch_standard_check_score(
            db,
            allowed_lz_ids,
            cloud_provider=cloud_provider,
            source_lz_id=source_lz_id,
            source_lz_ids=source_lz_ids,
            subscription_or_account_id=subscription_or_account_id,
            since=since,
        )

    return await get_cached_response(cache_key, load, ttl_seconds=_GOVERNANCE_CACHE_TTL_SECONDS)


@router.get("/landing-zones/details")
async def list_landing_zones(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    cloud_provider: Annotated[
        str | None, Query(description="Filter by cloud provider (azure|aws).")
    ] = None,
    environment: Annotated[
        str | None, Query(description="Filter by environment (prod|preprod|dev…).")
    ] = None,
    ba_name: Annotated[
        str | None, Query(description="Filter by business area name (partial match).")
    ] = None,
) -> dict[str, Any]:
    """Return active landing zones with full metadata from ``dim_landing_zone``.
    Use this endpoint to populate LZ selectors in the frontend and to display
    the ``ba_name`` (business area) alongside the ``lz_id``.

    Returns:
        List of landing zone detail objects ordered by cloud_provider, lz_name.
    """
    return await fetch_landing_zone_details(
        db,
        _settings(request),
        allowed_lz_ids=allowed_lz_ids,
        cloud_provider=cloud_provider,
        environment=environment,
        ba_name=ba_name,
    )


@router.get("/landing-zones/access-overview")
async def landing_zones_access_overview(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    cloud_provider: Annotated[
        str | None, Query(description="Filter by cloud provider (azure|aws).")
    ] = None,
    environment: Annotated[
        str | None, Query(description="Filter by environment (prod|preprod|dev…).")
    ] = None,
    ba_name: Annotated[
        str | None, Query(description="Filter by business area name (partial match).")
    ] = None,
) -> dict[str, Any]:
    """Return all monitored landing zones with per-user access flags.

    Unlike ``/landing-zones/details``, this endpoint lists every active LZ in DCM
    and marks whether the current user can see dashboard metrics for each one.
    """
    return await fetch_landing_zones_access_overview(
        db,
        _settings(request),
        current_user,
        cloud_provider=cloud_provider,
        environment=environment,
        ba_name=ba_name,
    )
