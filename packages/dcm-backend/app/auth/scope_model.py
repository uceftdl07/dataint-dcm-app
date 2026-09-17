"""Pure two-dimension scope model — no FastAPI / DB dependencies.

Kept in its own module so :mod:`app.auth.dependencies` can carry an
:class:`AllowedScope` on :class:`CurrentUser` without importing
:mod:`app.auth.scope` (which itself imports ``dependencies``), avoiding a cycle.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "AllowedScope",
    "add_scope_filter",
    "canonical_workspace_id",
    "canonical_workspace_sql",
]


def canonical_workspace_id(workspace_id: Any) -> str:
    """One key per Databricks workspace, whatever spelling a source used.

    Azure sources report ``adb-<id>`` while the Databricks system tables report
    the bare numeric id — the same workspace under two names. Comparing the two
    raw makes a granted workspace match nothing, which silently shows *no* data
    instead of the project's data.
    """
    wid = str(workspace_id or "").strip()
    return wid[4:] if wid.lower().startswith("adb-") else wid


def canonical_workspace_sql(column: str) -> str:
    """SQL counterpart of :func:`canonical_workspace_id` (idempotent)."""
    return (
        f"CASE WHEN lower({column}) LIKE 'adb-%' "
        f"THEN substr({column}, 5) ELSE {column} END"
    )


class AllowedScope(BaseModel):
    """Effective scope of a user, union over their active projects.

    ``unrestricted=True`` short-circuits every filter (platform admin) —
    equivalent to the ``None`` historically returned by ``get_allowed_lz_ids``.
    """

    unrestricted: bool = False
    lz_ids: list[str] = Field(default_factory=list)
    workspace_ids: list[str] = Field(default_factory=list)

    @field_validator("workspace_ids", mode="after")
    @classmethod
    def _canonicalize(cls, workspace_ids: list[str]) -> list[str]:
        """Store one spelling, so a grant matches every source (see above)."""
        seen: dict[str, None] = {}
        for workspace_id in workspace_ids:
            canonical = canonical_workspace_id(workspace_id)
            if canonical:
                seen.setdefault(canonical, None)
        return list(seen)

    @property
    def is_empty(self) -> bool:
        """No scope at all: the user sees nothing (0 active project)."""
        return not self.unrestricted and not self.lz_ids and not self.workspace_ids


def add_scope_filter(
    conditions: list[str],
    params: list[Any],
    scope: AllowedScope,
    *,
    lz_column: str | None = "source_lz_id",
    workspace_column: str | None = "workspace_id",
    canonical: bool = True,
) -> None:
    """Append the two-dimension RBAC scope clause to a parameterized query.

    Mirrors ``WHERE (:unrestricted OR source_lz_id IN (…) OR workspace_id IN (…))``:

    - ``unrestricted`` → no clause added (full access).
    - empty scope (0 active project, not unrestricted) → ``1 = 0`` (no rows).
    - otherwise → ``(lz_column IN (…) OR workspace_column IN (…))`` over the
      dimensions that are non-empty.

    Pass ``lz_column=None`` (resp. ``workspace_column=None``) for a table that
    does not carry that column — every ``gold_dbx_workflow_*`` table has a
    ``workspace_id`` but no ``source_lz_id``. A dimension that cannot be
    expressed is *not* silently dropped: if nothing is left to filter on, the
    clause becomes ``1 = 0``, because returning the whole platform's rows to a
    project member is the one outcome that must never happen.

    The workspace column is compared canonically (:func:`canonical_workspace_sql`)
    because tables disagree on the ``adb-`` prefix; pass ``canonical=False`` when
    the caller already hands a canonical expression.
    """
    if scope.unrestricted:
        return
    if scope.is_empty:
        conditions.append("1 = 0")
        return

    ors: list[str] = []
    scoped_params: list[Any] = []
    if lz_column is not None and scope.lz_ids:
        placeholders = ", ".join("?" for _ in scope.lz_ids)
        ors.append(f"{lz_column} IN ({placeholders})")
        scoped_params.extend(scope.lz_ids)
    if workspace_column is not None and scope.workspace_ids:
        placeholders = ", ".join("?" for _ in scope.workspace_ids)
        column = canonical_workspace_sql(workspace_column) if canonical else workspace_column
        ors.append(f"{column} IN ({placeholders})")
        scoped_params.extend(scope.workspace_ids)

    if not ors:
        conditions.append("1 = 0")
        return
    conditions.append("(" + " OR ".join(ors) + ")")
    params.extend(scoped_params)
