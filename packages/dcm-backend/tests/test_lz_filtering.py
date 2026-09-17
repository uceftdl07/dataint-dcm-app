"""Regression tests for admin-managed Landing Zone filtering on data routes."""

from __future__ import annotations

from unittest.mock import AsyncMock

from httpx import AsyncClient


def _viewer_headers(lz_ids: str = "lz-001,lz-002") -> dict[str, str]:
    return {"x-dcm-role": "viewer", "x-dcm-lz-ids": lz_ids}


async def test_viewer_lz_filter_applied_to_pipeline_queries(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchscalar.return_value = 0
    mock_db.fetchall.return_value = []

    resp = await client.get("/api/v1/pipelines", headers=_viewer_headers())

    assert resp.status_code == 200
    count_args = mock_db.fetchscalar.await_args.args
    assert "source_lz_id IN (?, ?)" in count_args[0]
    assert count_args[1:] == ("lz-001", "lz-002")

    list_args = mock_db.fetchall.await_args.args
    assert "source_lz_id IN (?, ?)" in list_args[0]
    assert list_args[1:3] == ("lz-001", "lz-002")


async def test_admin_data_routes_are_not_lz_filtered(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchscalar.return_value = 0
    mock_db.fetchall.return_value = []

    resp = await client.get("/api/v1/costs/summary", headers={"x-dcm-role": "admin"})

    assert resp.status_code == 200
    query = mock_db.fetchscalar.await_args.args[0]
    assert "source_lz_id IN" not in query
    assert "1 = 0" not in query


async def test_viewer_without_lz_access_gets_empty_scope_condition(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchall.return_value = []

    resp = await client.get("/api/v1/clusters", headers=_viewer_headers(""))

    assert resp.status_code == 200
    query = mock_db.fetchall.await_args.args[0]
    assert "1 = 0" in query


async def test_landing_zone_details_filter_uses_lz_id_column(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchall.return_value = []

    resp = await client.get(
        "/api/v1/landing-zones/details",
        headers=_viewer_headers("lz-001"),
    )

    assert resp.status_code == 200
    args = mock_db.fetchall.await_args.args
    assert "lz_id IN (?)" in args[0]
    assert args[1:] == ("lz-001",)


async def test_dashboard_applies_multi_lz_filter_from_query_params(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchscalar.return_value = 0
    mock_db.fetchall.return_value = []

    resp = await client.get(
        "/api/v1/dashboard/overview",
        params=[("source_lz_ids", "lz-aws-prod"), ("source_lz_ids", "lz-azure-prod")],
        headers={"x-dcm-role": "admin"},
    )

    assert resp.status_code == 200
    scalar_queries = [call.args[0] for call in mock_db.fetchscalar.await_args_list]
    # Databricks-specific queries (failed jobs, SQL warehouses, YTD cost current/
    # previous) have no source_lz_id column on their tables — only workspace_id,
    # and admin is RBAC-unrestricted there, so no filter at all on these.
    dbx_scoped_indices = {4, 8, 9, 10}
    other_queries = [q for i, q in enumerate(scalar_queries) if i not in dbx_scoped_indices]
    dbx_queries = [q for i, q in enumerate(scalar_queries) if i in dbx_scoped_indices]
    assert all("source_lz_id IN (?, ?)" in query for query in other_queries)
    assert all("source_lz_id" not in query for query in dbx_queries)
    first_args = mock_db.fetchscalar.await_args_list[0].args
    assert "lz-aws-prod" in first_args
    assert "lz-azure-prod" in first_args


async def test_dashboard_applies_lz_filter_to_all_overview_queries(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchscalar.return_value = 0
    mock_db.fetchall.return_value = []

    resp = await client.get("/api/v1/dashboard/overview", headers=_viewer_headers("lz-001"))

    assert resp.status_code == 200
    scalar_queries = [call.args[0] for call in mock_db.fetchscalar.await_args_list]
    # Existing overview scalars plus Databricks failed jobs, SQL warehouse and
    # current/previous YTD costs.
    assert len(scalar_queries) == 11
    # Databricks-specific queries (failed jobs, SQL warehouses, YTD cost current/
    # previous) have no source_lz_id column on their tables — they're RBAC-scoped
    # by workspace_id instead, and this viewer fixture grants no workspace access,
    # so they get the empty-scope "1 = 0" rather than a filter on a column that
    # doesn't exist (the bug this test guards against).
    dbx_scoped_indices = {4, 8, 9, 10}
    other_queries = [q for i, q in enumerate(scalar_queries) if i not in dbx_scoped_indices]
    dbx_queries = [q for i, q in enumerate(scalar_queries) if i in dbx_scoped_indices]
    assert all("source_lz_id IN (?)" in query for query in other_queries)
    assert all("source_lz_id" not in query for query in dbx_queries)
    assert all("1 = 0" in query for query in dbx_queries)
    pipeline_count_queries = scalar_queries[:3]
    assert all("curated_pipeline_metrics" in query for query in pipeline_count_queries)
    assert any("NOT LIKE 'databricks:job:%'" in query for query in pipeline_count_queries)
    assert any("pipeline_id LIKE 'databricks:job:%'" in query for query in pipeline_count_queries)

    fetchall_calls = mock_db.fetchall.await_args_list
    assert len(fetchall_calls) == 3
    # monthly_cost_rows (index 2) is the same Databricks-only, workspace-scoped
    # UNION query as the YTD scalars above — no source_lz_id on those tables.
    lz_scoped_calls = fetchall_calls[:2]
    monthly_cost_call = fetchall_calls[2]
    assert all("source_lz_id IN (?)" in call.args[0] for call in lz_scoped_calls)
    assert all(call.args[-1] == "lz-001" for call in lz_scoped_calls)
    assert "source_lz_id" not in monthly_cost_call.args[0]
    assert "1 = 0" in monthly_cost_call.args[0]
