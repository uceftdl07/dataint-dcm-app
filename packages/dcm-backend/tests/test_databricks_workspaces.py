"""Tests for GET /api/v1/databricks/workspaces."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from httpx import AsyncClient

#: The dev user defaults to a project ``viewer`` with no scope header, i.e. an
#: *empty* scope that legitimately sees nothing. Name-resolution tests are about
#: merging sources, not about scoping, so they ask for the unrestricted path.
_UNRESTRICTED = {"x-dcm-platform-role": "super_admin"}


def _wire_workspace_queries(
    mock_db: AsyncMock,
    *,
    gold: list[dict[str, Any]] | Exception | None = None,
    curated: list[dict[str, Any]] | Exception | None = None,
    compute: list[dict[str, Any]] | None = None,
) -> None:
    """Route fetchall by SQL source table (gold → curated → compute)."""

    async def fetchall(query: str, *args: Any) -> list[dict[str, Any]]:
        if "gold_dbx_workflow_runs" in query:
            if isinstance(gold, Exception):
                raise gold
            return gold or []
        if "curated_dbx_workflow_runs" in query:
            if isinstance(curated, Exception):
                raise curated
            return curated or []
        if "curated_compute_metrics" in query:
            return compute or []
        return []

    mock_db.fetchall.side_effect = fetchall


class TestDatabricksWorkspaces:
    async def test_prefers_gold_workspace_name(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        _wire_workspace_queries(
            mock_db,
            gold=[
                {
                    "workspace_id": "adb-111",
                    "workspace_name": "dbw-dsde-d-03",
                    "source_lz_id": "lz-001",
                    "run_count": 12,
                }
            ],
            compute=[
                {
                    "workspace_id": "111",
                    "source_lz_id": "lz-001",
                    "cluster_count": 3,
                    "workspace_name": None,
                }
            ],
        )

        resp = await client.get("/api/v1/databricks/workspaces", headers=_UNRESTRICTED)

        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item["workspace_id"] == "111"
        assert item["display_name"] == "dbw-dsde-d-03"
        assert item["cluster_count"] == 3

    async def test_compute_tag_name_when_gold_empty(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        _wire_workspace_queries(
            mock_db,
            gold=[],
            curated=[],
            compute=[
                {
                    "workspace_id": "222",
                    "source_lz_id": "lz-001",
                    "cluster_count": 5,
                    "workspace_name": "dbw-dsde-p-03",
                }
            ],
        )

        resp = await client.get("/api/v1/databricks/workspaces", headers=_UNRESTRICTED)

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["workspace_id"] == "222"
        assert items[0]["display_name"] == "dbw-dsde-p-03"
        assert items[0]["cluster_count"] == 5

    async def test_missing_gold_still_returns_compute(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        _wire_workspace_queries(
            mock_db,
            gold=Exception(
                "[TABLE_OR_VIEW_NOT_FOUND] Table or view not found: gold_dbx_workflow_runs"
            ),
            curated=Exception(
                "[STREAMING_TABLE_NEEDS_REFRESH] curated_dbx_workflow_runs needs refresh"
            ),
            compute=[
                {
                    "workspace_id": "adb-333",
                    "source_lz_id": "lz-002",
                    "cluster_count": 2,
                    "workspace_name": "dbw-novadatahub-d-03",
                }
            ],
        )

        resp = await client.get("/api/v1/databricks/workspaces", headers=_UNRESTRICTED)

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["workspace_id"] == "333"
        assert items[0]["display_name"] == "dbw-novadatahub-d-03"

    async def test_unresolved_source_lz_on_gold_still_returns_compute(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Prod gold_dbx_workflow_runs may lack source_lz_id — must not 500 the filter."""
        _wire_workspace_queries(
            mock_db,
            gold=Exception(
                "[UNRESOLVED_COLUMN.WITH_SUGGESTION] A column with name `source_lz_id` "
                "cannot be resolved. Did you mean [`account_id`, `run_id`]?"
            ),
            curated=[],
            compute=[
                {
                    "workspace_id": "adb-444",
                    "source_lz_id": "lz-003",
                    "cluster_count": 1,
                    "workspace_name": "dbw-compute-only",
                }
            ],
        )

        resp = await client.get("/api/v1/databricks/workspaces", headers=_UNRESTRICTED)

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["workspace_id"] == "444"
        assert items[0]["display_name"] == "dbw-compute-only"

    async def test_unions_gold_only_workspaces(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        _wire_workspace_queries(
            mock_db,
            gold=[
                {
                    "workspace_id": "adb-gold",
                    "workspace_name": "dbw-gold-only",
                    "source_lz_id": "lz-001",
                    "run_count": 4,
                }
            ],
            compute=[],
        )

        resp = await client.get("/api/v1/databricks/workspaces", headers=_UNRESTRICTED)

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["workspace_id"] == "gold"
        assert items[0]["display_name"] == "dbw-gold-only"
        assert items[0]["cluster_count"] == 4

    async def test_falls_back_to_id_without_name(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        _wire_workspace_queries(
            mock_db,
            gold=[],
            curated=[],
            compute=[
                {
                    "workspace_id": "999",
                    "source_lz_id": "lz-001",
                    "cluster_count": 1,
                    "workspace_name": None,
                }
            ],
        )

        resp = await client.get("/api/v1/databricks/workspaces", headers=_UNRESTRICTED)

        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item["display_name"] == "999"

    async def test_gold_null_name_falls_back_to_id(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """Post system.lakeflow migration gold rows carry ``workspace_name=NULL``.

        With no compute tag to borrow, resolution must land on ``workspace_id``
        (never an invented name) — contract §4 repli final.
        """
        _wire_workspace_queries(
            mock_db,
            gold=[
                {
                    "workspace_id": "adb-777",
                    "workspace_name": None,
                    "source_lz_id": None,
                    "run_count": 9,
                }
            ],
            curated=[],
            compute=[
                {
                    "workspace_id": "777",
                    "source_lz_id": "lz-001",
                    "cluster_count": 2,
                    "workspace_name": None,
                }
            ],
        )

        resp = await client.get("/api/v1/databricks/workspaces", headers=_UNRESTRICTED)

        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item["workspace_id"] == "777"
        assert item["display_name"] == "777"


class TestDatabricksWorkspacesScope:
    """The header filter must show a project's scope — and nothing else."""

    async def test_keeps_workspaces_granted_by_lz_or_by_workspace(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        _wire_workspace_queries(
            mock_db,
            gold=[],
            curated=[],
            compute=[
                {
                    "workspace_id": "111",
                    "source_lz_id": "lz-001",
                    "cluster_count": 1,
                    "workspace_name": None,
                },
                {
                    "workspace_id": "555",
                    "source_lz_id": "lz-999",
                    "cluster_count": 2,
                    "workspace_name": None,
                },
                {
                    "workspace_id": "777",
                    "source_lz_id": "lz-999",
                    "cluster_count": 3,
                    "workspace_name": None,
                },
            ],
        )

        resp = await client.get(
            "/api/v1/databricks/workspaces",
            headers={"x-dcm-lz-ids": "lz-001", "x-dcm-workspace-ids": "555"},
        )

        assert resp.status_code == 200
        # 111 through its landing zone, 555 through the workspace grant itself;
        # 777 is in neither dimension.
        assert [item["workspace_id"] for item in resp.json()["items"]] == ["111", "555"]

    async def test_granted_workspace_without_source_lz_is_listed(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        """gold_dbx_workflow_runs has no source_lz_id in prod — scope on the id.

        Regression: scoping this route on the landing zone alone hid every
        workspace granted through ``dcm_project_dbx_scope``, so the header filter
        read "No workspaces" for a project that had two.
        """
        _wire_workspace_queries(
            mock_db,
            gold=[
                {
                    "workspace_id": "adb-555",
                    "workspace_name": "dbw-granted",
                    "run_count": 7,
                },
                {
                    "workspace_id": "adb-666",
                    "workspace_name": "dbw-other-project",
                    "run_count": 4,
                },
            ],
            curated=[],
            compute=[],
        )

        resp = await client.get(
            "/api/v1/databricks/workspaces",
            headers={"x-dcm-workspace-ids": "adb-555"},
        )

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert [item["workspace_id"] for item in items] == ["555"]
        assert items[0]["display_name"] == "dbw-granted"

    async def test_empty_scope_lists_nothing(
        self,
        client: AsyncClient,
        mock_db: AsyncMock,
    ) -> None:
        _wire_workspace_queries(
            mock_db,
            gold=[{"workspace_id": "adb-111", "workspace_name": "dbw-x", "run_count": 1}],
            curated=[],
            compute=[
                {
                    "workspace_id": "222",
                    "source_lz_id": "lz-001",
                    "cluster_count": 1,
                    "workspace_name": "dbw-y",
                }
            ],
        )

        resp = await client.get("/api/v1/databricks/workspaces")

        assert resp.status_code == 200
        assert resp.json()["items"] == []
