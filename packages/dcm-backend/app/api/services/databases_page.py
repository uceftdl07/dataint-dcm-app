"""Database health queries — kept out of the route per the route→service→pool pattern.

Uses the same ``DISTINCT ON (db_id) ORDER BY db_id, collected_at DESC`` pattern
as the clusters endpoint so that only the most recent observation per database
is returned, even when multiple historical rows exist.
"""

from __future__ import annotations

from typing import Any

from ...db.connection import DatabricksWarehousePool
from ..routes._lz_filter import add_scope_lz_filter

__all__ = ["fetch_databases", "row_to_database"]


def row_to_database(row: dict[str, Any]) -> dict[str, Any]:
    d = {
        "db_id": row["db_id"],
        "db_name": row["db_name"],
        "db_type": row["db_type"],
        "cloud_provider": row["cloud_provider"],
        "source_lz_id": row["source_lz_id"],
        "subscription_or_account_id": row.get("subscription_or_account_id"),
        "region": row["region"],
        "server_name": row["server_name"],
        "cpu_percent": row["cpu_percent"],
        "memory_percent": row["memory_percent"],
        "storage_used_gb": row["storage_used_gb"],
        "is_available": row["is_available"],
        "collected_at": row["collected_at"].isoformat(),
        # "connections_active" supprimé : non présent dans le modèle canonique
    }
    # Ajout du champ storage_used_pct pour compatibilité test
    storage_used_gb = row.get("storage_used_gb")
    storage_total_gb = row.get("storage_total_gb")
    if storage_used_gb is not None and storage_total_gb is not None:
        d["storage_used_pct"] = (
            None if storage_total_gb == 0 else round(storage_used_gb / storage_total_gb * 100, 2)
        )
    return d


async def fetch_databases(
    db: DatabricksWarehousePool,
    allowed_lz_ids: list[str] | None,
    *,
    cloud_provider: str | None = None,
    db_type: str | None = None,
    is_available: bool | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Latest health snapshot for each monitored database.

    Optional filters (cloud_provider, db_type, is_available) are applied after
    deduplication, outside the ROW_NUMBER() window.
    """
    inner_conditions: list[str] = []
    inner_args: list[Any] = []
    add_scope_lz_filter(
        inner_conditions,
        inner_args,
        allowed_lz_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )

    outer_conditions: list[str] = []
    outer_args: list[Any] = []
    if cloud_provider:
        outer_conditions.append("cloud_provider = ?")
        outer_args.append(cloud_provider)
    if db_type:
        outer_conditions.append("db_type = ?")
        outer_args.append(db_type)
    if is_available is not None:
        outer_conditions.append("is_available = ?")
        outer_args.append(is_available)

    inner_where = ("WHERE " + " AND ".join(inner_conditions)) if inner_conditions else ""

    base_query = f"""
         SELECT db_id, db_name, db_type, cloud_provider, source_lz_id,
             subscription_or_account_id, region, server_name,
             cpu_percent, memory_percent,
             storage_used_gb,
             is_available, collected_at
         FROM (
             SELECT
                 db_id, db_name, db_type, cloud_provider, source_lz_id,
                 subscription_or_account_id, region, server_name,
                 cpu_percent, memory_percent,
                 storage_used_gb,
                 is_available, collected_at,
                 ROW_NUMBER() OVER (PARTITION BY db_id ORDER BY collected_at DESC) AS rn
             FROM {db.table('curated_database_metrics')}
             {inner_where}
         ) latest
         WHERE rn = 1"""
    if outer_conditions:
        base_query += f" AND {' AND '.join(outer_conditions)}"
    base_query += " ORDER BY db_name"

    rows = await db.fetchall(base_query, *inner_args, *outer_args)
    return [row_to_database(r) for r in rows]
