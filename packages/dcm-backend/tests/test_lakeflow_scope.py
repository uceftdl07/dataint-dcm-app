"""Project-scope enforcement on the Lakeflow routes (feature 015, anomaly 1).

Every ``gold_dbx_workflow_*`` table has a ``workspace_id`` and **no**
``source_lz_id``, so the workspace is the only dimension that can scope it. The
service used to drop the caller's scope entirely and honour the workspace filter
sent by the client, which meant a project member read every workspace of the
platform as soon as the header sent no filter.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from httpx import AsyncClient

from app.auth.scope_model import canonical_workspace_sql

_WORKSPACE_CLAUSE = f"{canonical_workspace_sql('workspace_id')} IN ("

_ROUTES = (
    "/api/v1/lakeflow/overview",
    "/api/v1/lakeflow/jobs",
    "/api/v1/lakeflow/jobs/42",
    "/api/v1/lakeflow/jobs/42/runs",
    "/api/v1/lakeflow/jobs/42/runs/7/tasks",
)


def _viewer(workspace_ids: str = "", lz_ids: str = "") -> dict[str, str]:
    """A project member: ``viewer`` is the only role outside the legacy bypass."""
    return {
        "x-dcm-role": "viewer",
        "x-dcm-workspace-ids": workspace_ids,
        "x-dcm-lz-ids": lz_ids,
    }


def _queries(mock_db: AsyncMock) -> list[tuple[str, tuple[object, ...]]]:
    """Every SQL statement the route sent, with its bound parameters."""
    calls = [
        *mock_db.fetchall.await_args_list,
        *mock_db.fetchone.await_args_list,
        *mock_db.fetchscalar.await_args_list,
    ]
    return [(call.args[0], call.args[1:]) for call in calls if call.args]


async def test_every_lakeflow_route_scopes_gold_rows_to_granted_workspaces(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    """Two granted workspaces out of a platform of five → only those two."""
    for route in _ROUTES:
        mock_db.reset_mock()
        resp = await client.get(route, headers=_viewer(workspace_ids="111,adb-222"))

        assert resp.status_code in (200, 404), route
        queries = _queries(mock_db)
        assert queries, f"{route} sent no query"
        for sql, params in queries:
            assert _WORKSPACE_CLAUSE in sql, f"{route} left a query unscoped: {sql}"
            # The grant is bound canonically, so ``adb-222`` matches a gold table
            # that stores the bare ``222`` — and nothing else leaks in.
            assert "111" in params, route
            assert "222" in params, route
            assert "adb-222" not in params, route
            for other in ("333", "444", "555"):
                assert other not in params, route


async def test_lakeflow_returns_no_row_when_no_workspace_is_granted(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    """An LZ-only project cannot be expressed on these tables → no rows.

    Falling back to "no clause" here is what leaked the whole platform. The LZ
    grant is real but unusable on a table without ``source_lz_id``; until it is
    resolved into workspaces the honest answer is an empty result, not everything.
    """
    resp = await client.get("/api/v1/lakeflow/overview", headers=_viewer(lz_ids="lz-a"))

    assert resp.status_code == 200
    queries = _queries(mock_db)
    assert queries
    for sql, _params in queries:
        assert "1 = 0" in sql


async def test_lakeflow_scope_is_not_widened_by_a_request_filter(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    """Asking for a workspace outside the grant must not return its rows."""
    resp = await client.get(
        "/api/v1/lakeflow/overview",
        headers=_viewer(workspace_ids="111"),
        params={"workspace_ids": "999"},
    )

    assert resp.status_code == 200
    queries = _queries(mock_db)
    assert queries
    for sql, params in queries:
        # RBAC clause AND request clause: 999 is asked for, 111 still bounds it.
        assert sql.count(_WORKSPACE_CLAUSE) == 2, sql
        assert "111" in params
        assert "999" in params


async def test_projects_sharing_an_lz_scope_do_not_share_a_cached_payload(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    """The response cache is process-wide, so the key must carry both dimensions.

    Keying on the LZ dimension alone was harmless while the workspace dimension
    was unenforced. Now that it filters, two projects granted the same LZ but
    different workspaces would read each other's rows on a cache hit.
    """
    first = await client.get(
        "/api/v1/lakeflow/overview",
        headers=_viewer(workspace_ids="111", lz_ids="lz-shared"),
    )
    assert first.status_code == 200
    calls_after_first = len(_queries(mock_db))
    assert calls_after_first > 0

    second = await client.get(
        "/api/v1/lakeflow/overview",
        headers=_viewer(workspace_ids="222", lz_ids="lz-shared"),
    )
    assert second.status_code == 200

    # A cache hit would leave the query count untouched.
    assert len(_queries(mock_db)) > calls_after_first
    assert any("222" in params for _sql, params in _queries(mock_db))


async def test_identical_scope_still_hits_the_cache(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    """The added key component must not defeat caching for the same caller."""
    headers = _viewer(workspace_ids="111", lz_ids="lz-shared")
    assert (await client.get("/api/v1/lakeflow/overview", headers=headers)).status_code == 200
    calls_after_first = len(_queries(mock_db))

    assert (await client.get("/api/v1/lakeflow/overview", headers=headers)).status_code == 200
    assert len(_queries(mock_db)) == calls_after_first
