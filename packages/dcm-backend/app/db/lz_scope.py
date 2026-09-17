"""Resolve a stored project LZ scope into the ``lz_id`` every filter matches.

Three identifier vocabularies coexist in the monitoring schema, and confusing two
of them is what makes a granted scope match no row at all:

``dim_landing_zone.lz_id``
    The DCM landing-zone id. Monitoring rows carry it as ``source_lz_id`` and
    every LZ filter — header selector included — matches on it.

``subscription_or_account_id``
    The Azure subscription or AWS account. It is the *only* key the reference
    dimensions expose: neither ``dim_reference_landing_zone_dbx_workspace`` nor
    ``dim_reference_landing_zone_business_application`` carries an ``lz_id``. The
    Azure source view ``ref_ba_lz`` even *names* this column ``lz_id`` (the
    ingestion renames it), which is why project scopes registered before that was
    understood hold a subscription id where an ``lz_id`` was expected.

Databricks ``workspace_id``
    Reported bare by the system tables and prefixed ``adb-`` by Azure sources,
    hence the canonical comparison.

One landing zone is one subscription, so a stored value resolves the same either
way round, and a workspace resolves to exactly one landing zone. The converse
does not hold: a landing zone need not have any workspace, so nothing is ever
derived in that direction.

Resolving at *read* time rather than rewriting the stored rows means no migration
has to run, mixed content is tolerated, and no grant is lost — a value that
resolves to nothing simply matches nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..auth.scope_model import canonical_workspace_id, canonical_workspace_sql
from ..config import Settings
from .tables import qualified_lz_dimension_table, qualified_table

if TYPE_CHECKING:
    from .connection import DatabricksWarehousePool

__all__ = [
    "narrow_workspace_ids",
    "project_lz_scope_query",
    "resolve_request_lz_workspace_ids",
]


def _normalize_requested_lz_ids(
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
) -> list[str] | None:
    """``None`` when no LZ filter was requested; deduplicated ids otherwise.

    Mirrors :func:`app.api.routes._lz_filter.normalize_requested_lz_ids` but is
    duplicated here so the ``db`` layer does not import the ``api`` layer.
    """
    if source_lz_ids is not None:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in source_lz_ids:
            item = value.strip()
            if not item or item in seen:
                continue
            seen.add(item)
            normalized.append(item)
        return normalized

    if source_lz_id is not None:
        item = source_lz_id.strip()
        return [item] if item else []

    return None


async def resolve_request_lz_workspace_ids(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    source_lz_id: str | None,
    source_lz_ids: list[str] | None,
) -> list[str] | None:
    """Translate a *request* Landing Zone filter into the workspaces it maps to.

    Workspace-keyed gold tables (``gold_dbx_compute_*``, ``gold_dbx_workflow_*``)
    carry a ``workspace_id`` but no ``source_lz_id``, so the header LZ selector
    cannot be pushed down on them directly. This resolves the requested
    ``lz_id`` (s) to their Databricks workspaces via
    ``dim_dbx_workspace`` ⋈ ``dim_landing_zone`` on ``subscription_or_account_id``
    (one LZ = one subscription/account), returning canonical workspace ids the
    downstream ``workspace_id`` filter can match.

    Returns:
        ``None`` when the client asked for no LZ filter (leave the scope as is).
        ``[]`` when the requested LZs map to no workspace — the caller must then
        return no rows rather than widen back to the whole scope.
        ``[...]`` the canonical workspace ids to narrow on otherwise.
    """
    requested = _normalize_requested_lz_ids(source_lz_id, source_lz_ids)
    if requested is None:
        return None
    if not requested:
        return []

    dbx_ws = qualified_table(settings, "dim_dbx_workspace")
    lz_dim = qualified_lz_dimension_table(settings)
    placeholders = ", ".join("?" for _ in requested)
    rows = await db.fetchall(
        f"""
        SELECT DISTINCT ws.workspace_id
        FROM {dbx_ws} ws
        JOIN {lz_dim} lzd
            ON ws.subscription_or_account_id = lzd.subscription_or_account_id
        WHERE lzd.lz_id IN ({placeholders})
          AND ws.workspace_id IS NOT NULL
        """,
        *requested,
    )
    return [
        canonical_workspace_id(row["workspace_id"])
        for row in rows
        if row["workspace_id"] is not None
    ]


def narrow_workspace_ids(
    request_workspace_ids: list[str] | None,
    lz_workspace_ids: list[str] | None,
) -> list[str] | None:
    """Intersect the request workspace filter with the LZ-derived workspaces.

    A request can only ever *narrow* the scope, never widen it:

    - ``lz_workspace_ids is None`` → no LZ filter, keep the workspace filter as is.
    - ``request_workspace_ids is None`` → only the LZ filter applies.
    - both set → intersection (canonical-aware); an empty result means the two
      filters are disjoint and no row can match.
    """
    if lz_workspace_ids is None:
        return request_workspace_ids
    if request_workspace_ids is None:
        return lz_workspace_ids

    requested = {canonical_workspace_id(wid) for wid in request_workspace_ids}
    return [wid for wid in lz_workspace_ids if canonical_workspace_id(wid) in requested]


def project_lz_scope_query(
    settings: Settings, project_ids: list[str]
) -> tuple[str, list[str]]:
    """``(project_id, lz_id)`` pairs for the given projects, both dimensions unioned.

    The first branch resolves what the project was granted on the LZ dimension,
    accepting either vocabulary. The second applies "a workspace always belongs to
    a landing zone", so a project granted only Databricks workspaces still gets a
    usable LZ scope.

    Raises:
        ValueError: on an empty project list — the caller must skip the query
            rather than build ``IN ()``.
    """
    if not project_ids:
        raise ValueError("project_ids must not be empty")

    lz_scope = qualified_table(settings, "dcm_project_lz_scope")
    dbx_scope = qualified_table(settings, "dcm_project_dbx_scope")
    workspace_ref = qualified_table(settings, "dim_reference_landing_zone_dbx_workspace")
    lz_dim = qualified_lz_dimension_table(settings)
    placeholders = ", ".join("?" for _ in project_ids)
    granted_workspace = canonical_workspace_sql("d.workspace_id")
    reference_workspace = canonical_workspace_sql("w.workspace_id")

    sql = f"""
        SELECT s.project_id, lz.lz_id
        FROM {lz_scope} s
        JOIN {lz_dim} lz
            ON (lz.lz_id = s.lz_id OR lz.subscription_or_account_id = s.lz_id)
        WHERE s.project_id IN ({placeholders})
        UNION
        SELECT d.project_id, lz.lz_id
        FROM {dbx_scope} d
        JOIN {workspace_ref} w
            ON {reference_workspace} = {granted_workspace}
        JOIN {lz_dim} lz
            ON lz.subscription_or_account_id = w.subscription_or_account_id
        WHERE d.project_id IN ({placeholders})
    """
    return sql, [*project_ids, *project_ids]
