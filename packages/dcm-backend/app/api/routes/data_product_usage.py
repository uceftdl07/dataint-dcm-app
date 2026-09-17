"""Data product usage endpoints backed by Unity Catalog gold tables.

Routes
------
GET /api/v1/data-product-usage/overview        Usage KPIs for the selected period.
GET /api/v1/data-product-usage/trends          Daily/weekly/monthly usage trend.
GET /api/v1/data-product-usage/top-consumers   Consumers ordered by usage volume.
GET /api/v1/data-product-usage                 Paginated detailed usage rows.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import Depends, Query
from fastapi.routing import APIRouter

from ...auth.dependencies import get_allowed_lz_ids
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.data_product_usage_page import (
    fetch_top_consumers,
    fetch_usage_list,
    fetch_usage_overview,
    fetch_usage_trends,
)
from ._lz_filter import SourceLzIdQuery, SourceLzIdsQuery

__all__ = ["router"]

router = APIRouter()


@router.get("/overview")
async def get_data_product_usage_overview(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    cloud_provider: Annotated[str | None, Query()] = None,
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    subscription_or_account_id: Annotated[str | None, Query()] = None,
    data_product_id: Annotated[str | None, Query()] = None,
    consumer_id: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    """Return high-level usage KPIs from ``gold_data_product_usage``."""
    return await fetch_usage_overview(
        db,
        allowed_lz_ids,
        start_date=start_date,
        end_date=end_date,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        subscription_or_account_id=subscription_or_account_id,
        data_product_id=data_product_id,
        consumer_id=consumer_id,
    )


@router.get("/trends")
async def get_data_product_usage_trends(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    cloud_provider: Annotated[str | None, Query()] = None,
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    subscription_or_account_id: Annotated[str | None, Query()] = None,
    data_product_id: Annotated[str | None, Query()] = None,
    consumer_id: Annotated[str | None, Query()] = None,
    grain: Annotated[str, Query(description="day|week|month")] = "day",
) -> dict[str, Any]:
    """Return usage trend buckets for charts."""
    return await fetch_usage_trends(
        db,
        allowed_lz_ids,
        start_date=start_date,
        end_date=end_date,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        subscription_or_account_id=subscription_or_account_id,
        data_product_id=data_product_id,
        consumer_id=consumer_id,
        grain=grain,
    )


@router.get("/top-consumers")
async def get_top_data_product_consumers(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    cloud_provider: Annotated[str | None, Query()] = None,
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    subscription_or_account_id: Annotated[str | None, Query()] = None,
    data_product_id: Annotated[str | None, Query()] = None,
    consumer_id: Annotated[str | None, Query()] = None,
    metric: Annotated[str, Query()] = "data_read_bytes",
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> dict[str, Any]:
    """Return consumers ranked by a whitelisted usage metric."""
    return await fetch_top_consumers(
        db,
        allowed_lz_ids,
        start_date=start_date,
        end_date=end_date,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        subscription_or_account_id=subscription_or_account_id,
        data_product_id=data_product_id,
        consumer_id=consumer_id,
        metric=metric,
        limit=limit,
    )


@router.get("")
async def list_data_product_usage(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
    cloud_provider: Annotated[str | None, Query()] = None,
    source_lz_id: SourceLzIdQuery = None,
    source_lz_ids: SourceLzIdsQuery = None,
    subscription_or_account_id: Annotated[str | None, Query()] = None,
    data_product_id: Annotated[str | None, Query()] = None,
    consumer_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    """List detailed data product usage rows from the gold serving table."""
    return await fetch_usage_list(
        db,
        allowed_lz_ids,
        start_date=start_date,
        end_date=end_date,
        cloud_provider=cloud_provider,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
        subscription_or_account_id=subscription_or_account_id,
        data_product_id=data_product_id,
        consumer_id=consumer_id,
        limit=limit,
        offset=offset,
    )
