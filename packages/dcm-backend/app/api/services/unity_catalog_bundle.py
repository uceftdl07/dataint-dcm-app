"""Aggregated Unity Catalog explorer queries — single HTTP round-trip for navigation."""

from __future__ import annotations

import asyncio
from typing import Any

from ...config import Settings
from ...db.connection import DatabricksWarehousePool

__all__ = [
    "fetch_catalogs",
    "fetch_schemas",
    "fetch_tables",
    "fetch_explorer_full",
]

_DEFAULT_CATALOG = "it"
_DEFAULT_TABLE = "curated_activity_runs"


def _normalise_name(row: dict[str, Any], *candidates: str) -> str:
    lower_map = {key.lower(): value for key, value in row.items()}
    for candidate in candidates:
        if candidate in row and row[candidate] is not None:
            return str(row[candidate])
        value = lower_map.get(candidate.lower())
        if value is not None:
            return str(value)
    first_value = next(iter(row.values()), "")
    return str(first_value)


def _quote_identifier(value: str) -> str:
    normalized = value.strip()
    return f"`{normalized.replace('`', '``')}`"


def _qualified_catalog(catalog_name: str) -> str:
    return _quote_identifier(catalog_name)


def _is_monitoring_catalog(name: str, settings: Settings) -> bool:
    lowered = name.lower()
    return name == settings.databricks_catalog or "monitoring" in lowered


def _is_recommended_catalog(name: str, settings: Settings) -> bool:
    return name in {_DEFAULT_CATALOG, settings.databricks_catalog} or _is_monitoring_catalog(
        name,
        settings,
    )


def _is_target_schema(name: str, settings: Settings) -> bool:
    lowered = name.lower()
    return name == settings.databricks_schema or "monitoring" in lowered


def _is_monitoring_table(name: str) -> bool:
    lowered = name.lower()
    return lowered == _DEFAULT_TABLE or "monitoring" in lowered


async def fetch_catalogs(db: DatabricksWarehousePool, settings: Settings) -> list[dict[str, Any]]:
    rows = await db.fetchall("SHOW CATALOGS")
    catalogs = [
        {
            "Name": name,
            "Type": "CATALOG",
            "IsMonitoringRelevant": _is_monitoring_catalog(name, settings),
            "RecommendedForExploration": _is_recommended_catalog(name, settings),
        }
        for row in rows
        for name in [_normalise_name(row, "catalog", "catalog_name", "namespace")]
        if name
    ]
    catalogs.sort(key=lambda item: (not item["RecommendedForExploration"], item["Name"]))
    return catalogs


async def fetch_schemas(
    db: DatabricksWarehousePool,
    settings: Settings,
    catalog_name: str,
) -> list[dict[str, Any]]:
    catalog = _qualified_catalog(catalog_name)
    rows = await db.fetchall(
        f"""
        SELECT schema_name
        FROM {catalog}.information_schema.schemata
        ORDER BY schema_name
        """,
    )
    schemas = [
        {
            "Name": row["schema_name"],
            "IsTargetSchema": _is_target_schema(str(row["schema_name"]), settings),
        }
        for row in rows
    ]
    schemas.sort(key=lambda item: (not item["IsTargetSchema"], item["Name"]))
    return schemas


async def fetch_tables(
    db: DatabricksWarehousePool,
    catalog_name: str,
    schema_name: str,
) -> list[dict[str, Any]]:
    catalog = _qualified_catalog(catalog_name)
    rows = await db.fetchall(
        f"""
        SELECT table_name, table_type, data_source_format, table_owner
        FROM {catalog}.information_schema.tables
        WHERE table_schema = ?
        ORDER BY table_name
        """,
        schema_name,
    )
    tables = [
        {
            "Name": row["table_name"],
            "Type": row.get("table_type") or "TABLE",
            "Format": row.get("data_source_format") or "-",
            "Owner": row.get("table_owner") or "-",
            "FullName": f"{catalog_name}.{schema_name}.{row['table_name']}",
            "IsMonitoringTable": _is_monitoring_table(str(row["table_name"])),
        }
        for row in rows
    ]
    tables.sort(key=lambda item: (not item["IsMonitoringTable"], item["Name"]))
    return tables


async def fetch_explorer_full(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    catalog_name: str | None = None,
    schema_name: str | None = None,
) -> dict[str, Any]:
    """Load catalogs and optionally schemas/tables in parallel."""

    tasks: list[Any] = [fetch_catalogs(db, settings)]
    if catalog_name:
        tasks.append(fetch_schemas(db, settings, catalog_name))
        if schema_name:
            tasks.append(fetch_tables(db, catalog_name, schema_name))

    results = await asyncio.gather(*tasks)
    catalogs = results[0]
    schemas = results[1] if len(results) > 1 else []
    tables = results[2] if len(results) > 2 else []

    return {
        "Status": "SUCCESS",
        "Catalogs": catalogs,
        "catalogs": catalogs,
        "Schemas": schemas,
        "schemas": schemas,
        "Tables": tables,
        "tables": tables,
    }
