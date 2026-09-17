"""Unit tests for the two-dimension project scope (feature 015)."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.auth.scope import AllowedScope, add_scope_filter, get_allowed_scope
from app.auth.scope_model import canonical_workspace_sql
from app.cache.response_cache import build_cache_key, cache_key_ids, cache_key_scope
from app.db.lz_scope import project_lz_scope_query
from app.main import app


def test_add_scope_filter_unrestricted_is_noop() -> None:
    conditions: list[str] = []
    params: list[object] = []
    add_scope_filter(conditions, params, AllowedScope(unrestricted=True))
    assert conditions == []
    assert params == []


def test_add_scope_filter_empty_blocks_all_rows() -> None:
    conditions: list[str] = []
    params: list[object] = []
    add_scope_filter(conditions, params, AllowedScope())
    assert conditions == ["1 = 0"]
    assert params == []


def test_add_scope_filter_builds_or_over_both_dimensions() -> None:
    conditions: list[str] = []
    params: list[object] = []
    scope = AllowedScope(lz_ids=["lz-a", "lz-b"], workspace_ids=["ws-1"])
    add_scope_filter(conditions, params, scope)
    assert conditions == [
        f"(source_lz_id IN (?, ?) OR {canonical_workspace_sql('workspace_id')} IN (?))"
    ]
    assert params == ["lz-a", "lz-b", "ws-1"]


def test_add_scope_filter_compares_workspaces_canonically() -> None:
    """A grant on ``adb-123`` must match a table that stores the bare ``123``."""
    conditions: list[str] = []
    params: list[object] = []
    add_scope_filter(conditions, params, AllowedScope(workspace_ids=["adb-123"]))
    assert conditions == [f"({canonical_workspace_sql('workspace_id')} IN (?))"]
    assert params == ["123"]


def test_add_scope_filter_can_skip_canonicalization() -> None:
    conditions: list[str] = []
    params: list[object] = []
    add_scope_filter(
        conditions,
        params,
        AllowedScope(workspace_ids=["123"]),
        workspace_column="w.canonical_id",
        canonical=False,
    )
    assert conditions == ["(w.canonical_id IN (?))"]


def test_allowed_scope_canonicalizes_and_dedupes_workspace_ids() -> None:
    scope = AllowedScope(workspace_ids=["adb-123", "123", "ADB-456", ""])
    assert scope.workspace_ids == ["123", "456"]


def test_add_scope_filter_single_dimension() -> None:
    conditions: list[str] = []
    params: list[object] = []
    add_scope_filter(conditions, params, AllowedScope(lz_ids=["lz-a"]))
    assert conditions == ["(source_lz_id IN (?))"]
    assert params == ["lz-a"]


def test_add_scope_filter_on_a_table_without_lz_column() -> None:
    """``gold_dbx_workflow_*`` carries a workspace but no ``source_lz_id``."""
    conditions: list[str] = []
    params: list[object] = []
    scope = AllowedScope(lz_ids=["lz-a"], workspace_ids=["111"])
    add_scope_filter(conditions, params, scope, lz_column=None)
    assert conditions == [f"({canonical_workspace_sql('workspace_id')} IN (?))"]
    assert params == ["111"]


def test_add_scope_filter_blocks_rows_when_no_dimension_is_expressible() -> None:
    """An LZ-only grant on an LZ-less table must return nothing, not everything.

    This is the anomaly-1 regression guard: the Lakeflow service used to fall back
    to *no clause at all* here, which handed a project member every workspace of
    the platform.
    """
    conditions: list[str] = []
    params: list[object] = []
    add_scope_filter(conditions, params, AllowedScope(lz_ids=["lz-a"]), lz_column=None)
    assert conditions == ["1 = 0"]
    assert params == []


@pytest.mark.asyncio
async def test_get_allowed_scope_super_admin_is_unrestricted() -> None:
    db = AsyncMock()
    scope = await get_allowed_scope(
        db,
        app.state.settings,
        user_id="u-1",
        platform_role="super_admin",
    )
    assert scope.unrestricted is True
    db.fetchall.assert_not_called()


@pytest.mark.asyncio
async def test_get_allowed_scope_union_of_active_projects() -> None:
    db = AsyncMock()
    db.fetchall = AsyncMock(
        side_effect=[
            [{"lz_id": "lz-a"}, {"lz_id": "lz-b"}],
            [{"workspace_id": "ws-1"}],
            [{"id": "p-1"}],  # active projects to resolve
            [{"project_id": "p-1", "lz_id": "lz-a"}],
        ]
    )
    scope = await get_allowed_scope(
        db,
        app.state.settings,
        user_id="u-1",
        platform_role="user",
    )
    assert scope.unrestricted is False
    assert scope.lz_ids == ["lz-a", "lz-b"]
    assert scope.workspace_ids == ["ws-1"]
    assert scope.is_empty is False


@pytest.mark.asyncio
async def test_get_allowed_scope_no_project_is_empty() -> None:
    db = AsyncMock()
    db.fetchall = AsyncMock(side_effect=[[], []])
    scope = await get_allowed_scope(
        db,
        app.state.settings,
        user_id="u-1",
        platform_role="user",
    )
    assert scope.is_empty is True
    # No scope row means nothing to resolve: the resolution query must be skipped
    # rather than build an ``IN ()`` the warehouse would reject.
    assert db.fetchall.await_count == 2


@pytest.mark.asyncio
async def test_get_allowed_scope_keeps_the_registered_value_and_its_resolution() -> None:
    """A scope registered as a subscription id must still match monitoring rows.

    ``dcm_project_lz_scope`` holds whatever the admin UI was given, and the Azure
    source view names the subscription ``lz_id`` — so a grant can carry a
    subscription where an ``lz_id`` is expected. The resolved value is what
    filters match; the registered one is kept so a grant on a landing zone the
    metrics have not reached yet is never dropped.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(
        side_effect=[
            [{"lz_id": "sub-0001"}],
            [],
            [{"id": "p-1"}],
            [{"project_id": "p-1", "lz_id": "lz-north"}],
        ]
    )
    scope = await get_allowed_scope(
        db,
        app.state.settings,
        user_id="u-1",
        platform_role="user",
    )
    assert scope.lz_ids == ["lz-north", "sub-0001"]


@pytest.mark.asyncio
async def test_get_allowed_scope_derives_lz_from_a_workspace_only_project() -> None:
    """Anomaly 2: a workspace always belongs to a landing zone.

    Without the derivation a project granted only Databricks workspaces had an
    empty LZ dimension, so every LZ-keyed page blocked all of its rows and the
    landing-zone selector had nothing to offer.
    """
    db = AsyncMock()
    db.fetchall = AsyncMock(
        side_effect=[
            [],
            [{"workspace_id": "adb-111"}],
            [{"id": "p-1"}],
            [{"project_id": "p-1", "lz_id": "lz-north"}],
        ]
    )
    scope = await get_allowed_scope(
        db,
        app.state.settings,
        user_id="u-1",
        platform_role="user",
    )
    assert scope.lz_ids == ["lz-north"]
    assert scope.workspace_ids == ["111"]


@pytest.mark.asyncio
async def test_get_allowed_scope_never_widens_when_nothing_resolves() -> None:
    """An unresolvable grant stays scoped, it does not become unrestricted."""
    db = AsyncMock()
    db.fetchall = AsyncMock(
        side_effect=[
            [{"lz_id": "lz-unknown"}],
            [],
            [{"id": "p-1"}],
            [],
        ]
    )
    scope = await get_allowed_scope(
        db,
        app.state.settings,
        user_id="u-1",
        platform_role="user",
    )
    assert scope.unrestricted is False
    assert scope.lz_ids == ["lz-unknown"]


def test_project_lz_scope_query_derives_only_from_workspace_to_lz() -> None:
    """The N:1 direction is safe; the reverse would grant unrelated workspaces.

    A landing zone need not have a workspace, so no workspace may be inferred
    from an LZ grant — that would hand a project compute it was never given.
    """
    sql, params = project_lz_scope_query(app.state.settings, ["p-1"])
    assert params == ["p-1", "p-1"]
    assert "lz.subscription_or_account_id = w.subscription_or_account_id" in sql
    assert "(lz.lz_id = s.lz_id OR lz.subscription_or_account_id = s.lz_id)" in sql
    # dbx_scope is only ever the driving side of the workspace → LZ branch.
    assert "`dcm_project_dbx_scope` d" in sql
    assert sql.count("dcm_project_dbx_scope") == 1


def test_project_lz_scope_query_refuses_an_empty_project_list() -> None:
    """``IN ()`` is invalid SQL: the caller must skip the query instead."""
    with pytest.raises(ValueError, match="project_ids"):
        project_lz_scope_query(app.state.settings, [])


def test_cache_key_ids_separates_empty_scope_from_unrestricted() -> None:
    """An empty scope must not read an unrestricted caller's cached payload.

    The response cache is process-wide, so a key that hashes ``[]`` (no row)
    like ``None`` (every row) serves platform-wide data to a project member.
    """
    empty = build_cache_key("page", allowed_lz_ids=cache_key_ids([]))
    unrestricted = build_cache_key("page", allowed_lz_ids=cache_key_ids(None))
    scoped = build_cache_key("page", allowed_lz_ids=cache_key_ids(["lz-a"]))
    assert empty != unrestricted
    assert empty != scoped
    assert scoped != unrestricted


def test_cache_key_scope_separates_projects_sharing_one_dimension() -> None:
    """Both dimensions must reach the key, or a cache hit crosses projects.

    Two projects granted the same landing zone but different Databricks
    workspaces produce different rows; keying on the LZ list alone made them
    share one process-wide entry.
    """
    lz_only_a = build_cache_key(
        "page", scope=cache_key_scope(AllowedScope(lz_ids=["lz-x"], workspace_ids=["111"]))
    )
    lz_only_b = build_cache_key(
        "page", scope=cache_key_scope(AllowedScope(lz_ids=["lz-x"], workspace_ids=["222"]))
    )
    assert lz_only_a != lz_only_b


def test_cache_key_scope_is_stable_and_order_insensitive() -> None:
    scope = AllowedScope(lz_ids=["lz-b", "lz-a"], workspace_ids=["222", "111"])
    reordered = AllowedScope(lz_ids=["lz-a", "lz-b"], workspace_ids=["111", "222"])
    assert cache_key_scope(scope) == cache_key_scope(reordered)


def test_cache_key_scope_separates_unrestricted_from_empty() -> None:
    unrestricted = cache_key_scope(AllowedScope(unrestricted=True))
    empty = cache_key_scope(AllowedScope())
    assert build_cache_key("page", scope=unrestricted) != build_cache_key("page", scope=empty)


def test_cache_key_ids_ignores_order() -> None:
    assert cache_key_ids(["lz-b", "lz-a"]) == ["lz-a", "lz-b"]
    assert build_cache_key("page", ids=cache_key_ids(["lz-b", "lz-a"])) == build_cache_key(
        "page", ids=cache_key_ids(["lz-a", "lz-b"])
    )


def test_no_cache_key_collapses_an_empty_id_scope() -> None:
    """Guard the whole API against the truthiness form coming back.

    ``sorted(x) if x else None`` reads as harmless normalization but silently
    merges the empty scope into the unrestricted one, so it must not reappear
    in any cache key. :func:`cache_key_ids` is the one allowed spelling.
    """
    api_root = Path(__file__).resolve().parents[1] / "app" / "api"
    collapsing = re.compile(
        r"if (allowed_lz_ids|allowed_workspace_ids|source_lz_ids|workspace_ids) else None"
    )
    offenders = [
        f"{path.relative_to(api_root)}:{number}"
        for path in api_root.rglob("*.py")
        for number, line in enumerate(path.read_text().splitlines(), start=1)
        if "sorted(" in line and collapsing.search(line)
    ]
    assert offenders == []
