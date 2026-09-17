"""Tests for Unity Catalog explorer endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from httpx import AsyncClient

from app.main import app

# The explorer reads an arbitrary table, so no project scope can be attached to
# it: it is reserved for unrestricted callers (see ``require_unrestricted_scope``).
_UNRESTRICTED = {"x-dcm-platform-role": "super_admin"}
# The monitoring schema is environment-specific (``…__d`` dev, ``…__p`` prod):
# name the configured one instead of pinning one environment in the payloads.
_SCHEMA = app.state.settings.databricks_schema


async def test_explorer_lists_catalogs_with_configured_recommendation(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchall.return_value = [
        {"catalog": "it"},
        {"catalog": "catalog_badsdataeng_dev"},
    ]

    resp = await client.get("/api/v1/unity-catalog/explorer", headers=_UNRESTRICTED)

    assert resp.status_code == 200
    body = resp.json()
    assert body["Status"] == "SUCCESS"
    assert body["Catalogs"][0]["Name"] == "it"
    assert body["Catalogs"][0]["RecommendedForExploration"] is True


async def test_query_returns_poc_compatible_shapes(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchall.return_value = [
        {
            "nom_script": "script.py",
            "nom_table": "table_a",
            "date_maj": datetime(2026, 5, 24, 10, tzinfo=UTC),
            "nombre_ligne": 42,
            "statut": "OK",
        }
    ]

    resp = await client.post(
        "/api/v1/unity-catalog/query",
        headers=_UNRESTRICTED,
        json={
            "catalogName": "it",
            "schemaName": _SCHEMA,
            "tableName": "curated_activity_runs",
            "orderBy": "collected_at DESC",
            "limit": 100,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["RowsRetrieved"] == 1
    assert body["Columns"] == ["nom_script", "nom_table", "date_maj", "nombre_ligne", "statut"]
    assert body["Data"][0][0] == "script.py"
    assert body["data"]["rows"][0]["date_maj"] == "2026-05-24T10:00:00+00:00"


async def test_query_without_catalog_and_schema_uses_the_configured_ones(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    """Omitting ``catalogName``/``schemaName`` must land on the configured schema.

    The monitoring schema differs per environment, so a caller that spells it out
    reads the wrong data as soon as it is deployed elsewhere. Leaving both out is
    the supported way to follow the deployment.
    """
    mock_db.fetchall.return_value = [{"nom_script": "script.py"}]

    resp = await client.post(
        "/api/v1/unity-catalog/query",
        headers=_UNRESTRICTED,
        json={"tableName": "curated_activity_runs", "limit": 10},
    )

    assert resp.status_code == 200
    settings = app.state.settings
    expected = f"{settings.databricks_catalog}.{settings.databricks_schema}.curated_activity_runs"
    assert resp.json()["FullTableName"] == expected
    query = mock_db.fetchall.await_args.args[0]
    assert f"`{settings.databricks_schema}`" in query


async def test_query_rejects_unsafe_fragments(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    resp = await client.post(
        "/api/v1/unity-catalog/query",
        headers=_UNRESTRICTED,
        json={
            "catalogName": "it",
            "schemaName": _SCHEMA,
            "tableName": "curated_activity_runs",
            "whereClause": "1=1; DROP TABLE curated_activity_runs",
        },
    )

    assert resp.status_code == 400
    mock_db.fetchall.assert_not_called()


async def test_preview_returns_pagination(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchall.return_value = [{"nom_script": "script.py", "statut": "OK"}]
    mock_db.fetchscalar.return_value = 101

    resp = await client.get(
        "/api/v1/unity-catalog/tables/curated_activity_runs/preview",
        headers=_UNRESTRICTED,
        params={
            "catalogName": "it",
            "schemaName": _SCHEMA,
            "limit": 100,
            "offset": 0,
            "includeTotal": True,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["Table"]["RowsRetrieved"] == 1
    assert body["Pagination"]["TotalRows"] == 101
    assert body["Pagination"]["HasNextPage"] is True
    assert body["Pagination"]["NextOffset"] == 100
    mock_db.fetchscalar.assert_called_once()


async def test_project_scoped_caller_cannot_read_arbitrary_tables(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    """A project member has no business reading raw tables outside their scope.

    ``POST /query`` takes any ``catalog.schema.table`` plus a ``WHERE``, so it can
    reach every row of the platform — including the governance tables. Nothing is
    queried at all: the guard runs before the handler.
    """
    resp = await client.post(
        "/api/v1/unity-catalog/query",
        headers={"x-dcm-workspace-ids": "1234", "x-dcm-lz-ids": "lz-a"},
        json={
            "catalogName": "it",
            "schemaName": _SCHEMA,
            "tableName": "dcm_app_users",
        },
    )

    assert resp.status_code == 403
    assert resp.json()["detail"] == "unrestricted_scope_required"
    mock_db.fetchall.assert_not_called()


async def test_preview_is_refused_to_a_project_scoped_caller(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    resp = await client.get(
        "/api/v1/unity-catalog/tables/curated_activity_runs/preview",
        params={"catalogName": "it", "schemaName": _SCHEMA},
    )

    assert resp.status_code == 403
    mock_db.fetchall.assert_not_called()
