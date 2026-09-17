"""Databricks workspace listing (header filter) — reads workflow/compute/dimension tables.

Kept out of the route per the route→service→pool pattern.
"""

from __future__ import annotations

from typing import Any

from ...auth.scope import AllowedScope, add_scope_filter
from ...auth.scope_model import canonical_workspace_id, canonical_workspace_sql
from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_lz_dimension_table, qualified_table

__all__ = ["fetch_workspaces"]

_CANONICAL_WORKSPACE_SQL = canonical_workspace_sql("workspace_id")


def _within_scope(
    workspaces: dict[str, dict[str, Any]], scope: AllowedScope
) -> dict[str, dict[str, Any]]:
    """Keep the workspaces the caller may see, on canonical ids.

    Last line of defence for the sources that cannot be scoped in SQL (see
    :func:`fetch_workspaces`): a workspace stays only when it is granted itself or
    through its landing zone. A row whose ``source_lz_id`` is unknown is dropped
    unless the workspace id is granted — an unprovable row is not an allowed one.
    """
    if scope.unrestricted:
        return workspaces
    granted_workspaces = {canonical_workspace_id(wid) for wid in scope.workspace_ids}
    granted_lz_ids = set(scope.lz_ids)
    return {
        wid: item
        for wid, item in workspaces.items()
        if wid in granted_workspaces or (item.get("source_lz_id") in granted_lz_ids)
    }


def _soft_fail_workspace_source(exc: BaseException, *, table_hint: str) -> bool:
    """Return True when a missing/stale UC table should not blank the filter.

    Live gold tables may lag the contract (e.g. no ``source_lz_id`` yet). Spark
    then raises ``UNRESOLVED_COLUMN`` without embedding the table name — still
    soft-fail so curated/compute can populate the header filter.
    """
    message = str(exc)
    if "[UNRESOLVED_COLUMN" in message:
        return True
    if table_hint not in message:
        return False
    return (
        "[TABLE_OR_VIEW_NOT_FOUND]" in message
        or "[STREAMING_TABLE_NEEDS_REFRESH]" in message
    )


async def fetch_workspaces(
    db: DatabricksWarehousePool,
    settings: Settings,
    scope: AllowedScope,
) -> dict[str, Any]:
    """List Databricks workspaces with ARM names when available.

    Name resolution order per workspace:
    1. ``gold_dbx_workflow_runs.workspace_name``
    2. ``curated_dbx_workflow_runs.workspace_name``
    3. compute tags ``dcm_workspace_name`` / ``Project`` matching ``dbw-%``
    4. fallback to canonical ``workspace_id``

    Scoped on **both** project dimensions: a workspace is visible when its
    landing zone is granted OR the workspace itself is. Filtering on the landing
    zone alone hid every workspace a project was granted through
    ``dcm_project_dbx_scope`` whenever the rows carried no ``source_lz_id`` —
    which is the norm on the live ``gold_dbx_workflow_runs`` (sys-tables path,
    no such column at all). That table therefore cannot be scoped in SQL, so the
    decision is re-applied on the merged result over canonical workspace ids.
    """
    gold_t = qualified_table(settings, "gold_dbx_workflow_runs")
    curated_runs_t = qualified_table(settings, "curated_dbx_workflow_runs")
    compute_t = qualified_table(settings, "curated_compute_metrics")

    # ``add_scope_filter`` compares the workspace dimension canonically, which
    # matters here: curated_compute_metrics stores Azure workspaces as ``adb-<id>``
    # while the runs tables store the bare id.
    conditions: list[str] = ["workspace_id IS NOT NULL"]
    args: list[Any] = []
    add_scope_filter(conditions, args, scope)
    where_clause = "WHERE " + " AND ".join(conditions)

    names_by_id: dict[str, str] = {}
    runs_meta: dict[str, dict[str, Any]] = {}

    async def _load_run_names(
        table: str,
        *,
        count_col: str,
        table_hint: str,
        include_source_lz: bool = True,
    ) -> None:
        # Live gold_dbx_workflow_runs (sys-tables path) has no source_lz_id — see
        # DESCRIBE — so it carries no scopable column: whatever it contributes is
        # vetted by the scope pass on ``merged`` below.
        if include_source_lz:
            lz_select = "MIN(source_lz_id) AS source_lz_id"
            wc = where_clause
            q_args: list[Any] = list(args)
        else:
            lz_select = "CAST(NULL AS STRING) AS source_lz_id"
            wc = "WHERE workspace_id IS NOT NULL"
            q_args = []
        try:
            rows = await db.fetchall(
                f"""
                SELECT
                    workspace_id,
                    MAX(workspace_name) AS workspace_name,
                    {lz_select},
                    COUNT(DISTINCT {count_col}) AS run_count
                FROM {table}
                {wc}
                GROUP BY workspace_id
                """,
                *q_args,
            )
        except Exception as exc:  # noqa: BLE001 — table may be missing/stale
            if _soft_fail_workspace_source(exc, table_hint=table_hint):
                return
            raise
        for row in rows:
            wid = canonical_workspace_id(row.get("workspace_id"))
            if not wid:
                continue
            name = (row.get("workspace_name") or "").strip()
            if name and wid not in names_by_id:
                names_by_id[wid] = name
            prev = runs_meta.get(wid)
            run_count = int(row.get("run_count") or 0)
            if prev is None:
                runs_meta[wid] = {
                    "source_lz_id": row.get("source_lz_id"),
                    "run_count": run_count,
                }
            else:
                prev["run_count"] = max(int(prev.get("run_count") or 0), run_count)
                if row.get("source_lz_id") and not prev.get("source_lz_id"):
                    prev["source_lz_id"] = row["source_lz_id"]

    await _load_run_names(
        gold_t,
        count_col="run_id",
        table_hint="gold_dbx_workflow",
        include_source_lz=False,
    )
    # DETTE TECHNIQUE (migration T002/013-workflow-sys-tables, epic 009) : ce
    # fallback lit `curated_dbx_workflow_runs` (collecteur JSON Azure,
    # `DatabricksWorkflowCollector`), volontairement laisse hors scope de la
    # migration du domaine workflow vers `pipelines.gold_dbx_workflow`
    # (system tables uniquement). Tant que le collecteur reste actif, cette
    # ligne reste une source valide de complement de nom de workspace ; le
    # jour ou il sera decommissionne, ce fallback devra etre retire (ou
    # remplace par une autre source) sous peine de renvoyer silencieusement
    # zero ligne.
    await _load_run_names(
        curated_runs_t,
        count_col="run_id",
        table_hint="curated_dbx_workflow",
        include_source_lz=True,
    )

    try:
        compute_rows = await db.fetchall(
            f"""
            WITH base AS (
              SELECT
                {_CANONICAL_WORKSPACE_SQL} AS workspace_id,
                source_lz_id,
                COALESCE(
                  get_json_object(tags, '$.dcm_workspace_name'),
                  CASE
                    WHEN lower(get_json_object(tags, '$.Project')) LIKE 'dbw-%'
                    THEN get_json_object(tags, '$.Project')
                    ELSE NULL
                  END
                ) AS name_candidate
              FROM {compute_t}
              {where_clause}
            ),
            agg AS (
              SELECT
                workspace_id,
                MIN(source_lz_id) AS source_lz_id,
                COUNT(*) AS cluster_count
              FROM base
              GROUP BY workspace_id
            ),
            name_votes AS (
              SELECT
                workspace_id,
                name_candidate,
                COUNT(*) AS c,
                ROW_NUMBER() OVER (
                  PARTITION BY workspace_id
                  ORDER BY COUNT(*) DESC, name_candidate
                ) AS rn
              FROM base
              WHERE name_candidate IS NOT NULL AND trim(name_candidate) <> ''
              GROUP BY workspace_id, name_candidate
            )
            SELECT
              a.workspace_id,
              a.source_lz_id,
              a.cluster_count,
              n.name_candidate AS workspace_name
            FROM agg a
            LEFT JOIN name_votes n
              ON a.workspace_id = n.workspace_id AND n.rn = 1
            """,
            *args,
        )
    except Exception:  # noqa: BLE001 — degrade rather than blank the header filter
        compute_rows = []

    merged: dict[str, dict[str, Any]] = {}
    for row in compute_rows:
        wid = canonical_workspace_id(row.get("workspace_id"))
        if not wid:
            continue
        tag_name = (row.get("workspace_name") or "").strip()
        if tag_name and wid not in names_by_id:
            names_by_id[wid] = tag_name
        merged[wid] = {
            "workspace_id": wid,
            "display_name": names_by_id.get(wid) or wid,
            "source_lz_id": row.get("source_lz_id"),
            "cluster_count": int(row.get("cluster_count") or 0),
        }

    for wid, meta in runs_meta.items():
        name = names_by_id.get(wid) or wid
        if wid in merged:
            merged[wid]["display_name"] = name
            if meta.get("source_lz_id") and not merged[wid].get("source_lz_id"):
                merged[wid]["source_lz_id"] = meta["source_lz_id"]
        else:
            merged[wid] = {
                "workspace_id": wid,
                "display_name": name,
                "source_lz_id": meta.get("source_lz_id"),
                "cluster_count": int(meta.get("run_count") or 0),
            }

    # Authoritative names/LZ from the workspace dimension (feature 020):
    # `dim_dbx_workspace` carries the real console workspace name and its
    # subscription/account, joined to the LZ dimension for the `source_lz_id` the
    # header uses to keep the LZ and workspace selectors in sync. Enrich only —
    # never widen the scoped set built above.
    dbx_ws_t = qualified_table(settings, "dim_dbx_workspace")
    lz_dim_t = qualified_lz_dimension_table(settings)
    try:
        dim_rows = await db.fetchall(
            f"""
            SELECT
                ws.workspace_id AS workspace_id,
                ws.workspace_name AS workspace_name,
                lzd.lz_id AS source_lz_id
            FROM {dbx_ws_t} ws
            LEFT JOIN {lz_dim_t} lzd
                ON ws.subscription_or_account_id = lzd.subscription_or_account_id
            WHERE ws.workspace_id IS NOT NULL
            """
        )
    except Exception:  # noqa: BLE001 — view may be missing; degrade to heuristics
        dim_rows = []

    for row in dim_rows:
        wid = canonical_workspace_id(row.get("workspace_id"))
        item = merged.get(wid)
        if item is None:
            continue
        dim_name = (row.get("workspace_name") or "").strip()
        if dim_name:
            item["display_name"] = dim_name
        if row.get("source_lz_id") and not item.get("source_lz_id"):
            item["source_lz_id"] = row["source_lz_id"]

    items = sorted(
        _within_scope(merged, scope).values(),
        key=lambda item: (
            # Named workspaces (dbw-…) first; raw numeric ids last.
            0
            if (item.get("display_name") or "").strip()
            and str(item.get("display_name")).strip() != str(item.get("workspace_id") or "").strip()
            else 1,
            str(item.get("display_name") or "").lower(),
            str(item.get("workspace_id") or ""),
        ),
    )
    return {"items": items}
