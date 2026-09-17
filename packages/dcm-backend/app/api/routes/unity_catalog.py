"""Unity Catalog explorer endpoints backed by Databricks SQL Warehouse.

Every route here reads a caller-supplied ``catalog.schema.table``, so none of them
can be narrowed to a project's Landing Zones or Databricks workspaces. They are
therefore reserved for callers with an unrestricted scope
(:func:`require_unrestricted_scope`) — a project member browsing raw tables would
bypass the scope the rest of the API enforces.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Query, Request
from fastapi.routing import APIRouter
from pydantic import BaseModel, Field

from ...auth.scope import require_unrestricted_scope
from ...config import Settings
from ...db.connection import DatabricksWarehousePool, get_db
from ..services.unity_catalog_bundle import (
    fetch_catalogs,
    fetch_explorer_full,
    fetch_schemas,
    fetch_tables,
)
from ..services.unity_catalog_explorer_page import (
    fetch_table_metadata,
    fetch_table_preview,
    run_generic_query,
)

__all__ = ["router"]

router = APIRouter(dependencies=[Depends(require_unrestricted_scope)])

_DEFAULT_TABLE = "curated_activity_runs"
_MAX_QUERY_LIMIT = 50_000
_MAX_PREVIEW_LIMIT = 5_000


class GenericUnityCatalogQuery(BaseModel):
    # Catalog and schema default to the configured ones (the schema is
    # environment-specific: ``…__d`` dev, ``…__p`` prod), resolved per request —
    # a literal default here would pin the API to one environment.
    catalogName: str | None = Field(default=None, min_length=1)
    schemaName: str | None = Field(default=None, min_length=1)
    tableName: str = Field(default=_DEFAULT_TABLE, min_length=1)
    columns: list[str] | None = None
    whereClause: str | None = None
    orderBy: str | None = None
    limit: int | None = Field(default=100, ge=1, le=_MAX_QUERY_LIMIT)
    offset: int = Field(default=0, ge=0)


def _get_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


@router.get("/explorer/full")
async def get_unity_catalog_explorer_full(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    catalog_name: Annotated[str | None, Query(alias="catalogName")] = None,
    schema_name: Annotated[str | None, Query(alias="schemaName")] = None,
) -> dict[str, Any]:
    """Return catalogs and optionally schemas/tables in one parallel bundle."""

    settings = _get_settings(request)
    return await fetch_explorer_full(
        db,
        settings,
        catalog_name=catalog_name,
        schema_name=schema_name,
    )


@router.get("/explorer")
async def get_unity_catalog_explorer_data(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> dict[str, Any]:
    """Return available catalogs with POC-compatible flags."""

    settings = _get_settings(request)
    catalogs = await fetch_catalogs(db, settings)
    return {"Status": "SUCCESS", "Catalogs": catalogs, "catalogs": catalogs}


@router.get("/schemas")
async def list_unity_catalog_schemas(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    catalog_name: Annotated[str, Query(alias="catalogName")],
) -> dict[str, Any]:
    """List schemas for a catalog."""

    settings = _get_settings(request)
    schemas = await fetch_schemas(db, settings, catalog_name)
    return {"Status": "SUCCESS", "Schemas": schemas, "schemas": schemas}


@router.get("/tables")
async def list_unity_catalog_tables(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    catalog_name: Annotated[str, Query(alias="catalogName")],
    schema_name: Annotated[str, Query(alias="schemaName")],
) -> dict[str, Any]:
    """List tables and views for a catalog schema."""

    tables = await fetch_tables(db, catalog_name, schema_name)
    return {"Status": "SUCCESS", "Tables": tables, "tables": tables}


@router.get("/tables/{table_name}/metadata")
async def get_unity_catalog_table_metadata(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    table_name: str,
    catalog_name: Annotated[str, Query(alias="catalogName")],
    schema_name: Annotated[str, Query(alias="schemaName")],
) -> dict[str, Any]:
    """Return table metadata and columns."""
    return await fetch_table_metadata(db, table_name, catalog_name, schema_name)


@router.get("/tables/{table_name}/preview")
async def preview_unity_catalog_table(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    table_name: str,
    catalog_name: Annotated[str, Query(alias="catalogName")],
    schema_name: Annotated[str, Query(alias="schemaName")],
    limit: Annotated[int, Query(ge=1, le=_MAX_PREVIEW_LIMIT)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    order_by: Annotated[str | None, Query(alias="orderBy")] = None,
    include_total: Annotated[bool, Query(alias="includeTotal")] = False,
) -> dict[str, Any]:
    """Return a paginated data preview."""
    return await fetch_table_preview(
        db,
        table_name,
        catalog_name,
        schema_name,
        limit=limit,
        offset=offset,
        order_by=order_by,
        include_total=include_total,
    )


@router.post("/query")
async def query_unity_catalog_table(
    request: GenericUnityCatalogQuery,
    http_request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> dict[str, Any]:
    """Run a constrained SELECT against a Unity Catalog table."""

    settings = _get_settings(http_request)
    catalog_name = request.catalogName or settings.databricks_catalog
    schema_name = request.schemaName or settings.databricks_schema
    return await run_generic_query(
        db,
        catalog_name=catalog_name,
        schema_name=schema_name,
        table_name=request.tableName,
        columns=request.columns,
        where_clause=request.whereClause,
        order_by=request.orderBy,
        limit=request.limit,
        offset=request.offset,
    )
