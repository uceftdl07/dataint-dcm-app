"""Compute metrics queries — Databricks and EMR. Kept out of the route per the
route→service→pool pattern.

Uses ROW_NUMBER() OVER (PARTITION BY compute_resource_id ORDER BY collected_at DESC)
to return only the most recent snapshot for each resource, regardless of history
in curated_compute_metrics — the SQL Warehouse (Databricks) compatible replacement
for PostgreSQL's DISTINCT ON.
"""

from __future__ import annotations

from typing import Any

from ...auth.scope import AllowedScope, add_scope_filter
from ...db.connection import DatabricksWarehousePool
from ..routes._lz_filter import add_scope_lz_filter

__all__ = ["add_workspace_filter", "fetch_compute", "row_to_compute"]


def _normalize_requested_workspace_ids(
    workspace_id: str | None = None,
    workspace_ids: list[str] | None = None,
) -> list[str] | None:
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


def add_workspace_filter(
    conditions: list[str],
    args: list[Any],
    *,
    workspace_id: str | None = None,
    workspace_ids: list[str] | None = None,
) -> None:
    requested = _normalize_requested_workspace_ids(workspace_id, workspace_ids)
    if requested is None:
        return
    if not requested:
        conditions.append("1 = 0")
        return
    if len(requested) == 1:
        conditions.append("workspace_id = ?")
        args.append(requested[0])
        return
    placeholders = ", ".join("?" * len(requested))
    conditions.append(f"workspace_id IN ({placeholders})")
    args.extend(requested)


def row_to_compute(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "compute_resource_id": row["compute_resource_id"],
        "resource_name": row["resource_name"],
        "compute_type": row["compute_type"],
        "cloud_provider": row["cloud_provider"],
        "source_lz_id": row["source_lz_id"],
        "subscription_or_account_id": row["subscription_or_account_id"],
        "workspace_id": row.get("workspace_id"),
        "state": row["state"],
        "num_workers": row["num_workers"],
        "autoscale_min": row.get("autoscale_min"),
        "autoscale_max": row.get("autoscale_max"),
        "node_type": row["node_type"],
        "spark_version": row["spark_version"],
        "avg_cpu_utilization_pct": row.get("avg_cpu_utilization_pct"),
        "avg_mem_utilization_pct": row.get("avg_mem_utilization_pct"),
        "tags": row.get("tags", {}),
        "collected_at": row["collected_at"].isoformat()
        if hasattr(row["collected_at"], "isoformat")
        else str(row["collected_at"]),
    }


async def fetch_compute(
    db: DatabricksWarehousePool,
    scope: AllowedScope,
    *,
    cloud_provider: str | None = None,
    workspace_id: str | None = None,
    workspace_ids: list[str] | None = None,
    state: str | None = None,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
) -> dict[str, Any]:
    """The latest snapshot for each monitored compute resource.

    Optional filters are applied after deduplication via a WHERE clause.
    """
    inner_conditions: list[str] = []
    inner_args: list[Any] = []
    # 2-dimension RBAC (feature 015): source_lz_id IN (...) OR workspace_id IN (...).
    # This is the concrete reference enforcement of the workspace dimension; both
    # scope columns are available on the inner (pre-dedup) query.
    add_scope_filter(inner_conditions, inner_args, scope)
    # Request-scoped LZ narrowing only (RBAC already applied above → pass None).
    add_scope_lz_filter(
        inner_conditions,
        inner_args,
        None,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )

    outer_conditions: list[str] = []
    outer_args: list[Any] = []

    if cloud_provider:
        outer_conditions.append("cloud_provider = ?")
        outer_args.append(cloud_provider)
    add_workspace_filter(
        outer_conditions,
        outer_args,
        workspace_id=workspace_id,
        workspace_ids=workspace_ids,
    )
    if state:
        outer_conditions.append("state = ?")
        outer_args.append(state)

    inner_where = ("WHERE " + " AND ".join(inner_conditions)) if inner_conditions else ""

    where_clause = "WHERE rn = 1"
    if outer_conditions:
        where_clause += " AND " + " AND ".join(outer_conditions)

    query = f"""
        SELECT
            compute_resource_id, resource_name, compute_type, cloud_provider, source_lz_id,
            subscription_or_account_id, workspace_id, state, num_workers, node_type,
            spark_version, avg_cpu_utilization_pct, avg_mem_utilization_pct, tags, collected_at
        FROM (
            SELECT
                compute_resource_id, resource_name, compute_type, cloud_provider, source_lz_id,
                subscription_or_account_id, workspace_id, state, num_workers, node_type,
                spark_version, avg_cpu_utilization_pct, avg_mem_utilization_pct, tags, collected_at,
                ROW_NUMBER() OVER (
                    PARTITION BY compute_resource_id
                    ORDER BY collected_at DESC
                ) as rn
            FROM {db.table('curated_compute_metrics')}
            {inner_where}
        ) latest
        {where_clause}
        ORDER BY resource_name
    """

    rows = await db.fetchall(query, *inner_args, *outer_args)
    return {"items": [row_to_compute(r) for r in rows]}
