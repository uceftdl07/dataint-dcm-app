"""Route tests for Compute Metrics API."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

BASE = "/api/v1/databricks/compute"
LAKEFLOW = "/api/v1/lakeflow"


class TestComputeMetricsRoutes:
    async def test_clusters_overview_empty_200(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchone.return_value = None
        mock_db.fetchall.return_value = []

        resp = await client.get(f"{BASE}/clusters/overview")

        assert resp.status_code == 200
        body = resp.json()
        assert body["kpis"]["total_cost_usd"] == 0.0
        assert body["items"] == []
        assert "period" in body

    async def test_clusters_cost_empty_200(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = []

        resp = await client.get(f"{BASE}/clusters/cost")

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["page"] == 1
        assert body["page_size"] == 25

    async def test_clusters_cost_pagination_params(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = []

        resp = await client.get(f"{BASE}/clusters/cost", params={"page": 2, "page_size": 50})

        assert resp.status_code == 200
        body = resp.json()
        assert body["page"] == 2
        assert body["page_size"] == 50

    async def test_recommendations_empty_200(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = []

        resp = await client.get(f"{BASE}/recommendations")

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    async def test_recommendations_summary_empty_200(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchone.return_value = None

        resp = await client.get(f"{BASE}/recommendations/summary")

        assert resp.status_code == 200
        body = resp.json()
        assert body["open_count"] == 0
        assert body["open_savings_usd"] == 0.0
        assert body["period_actual_cost_usd"] == 0.0
        assert body["resolved_30d_count"] == 0
        assert body["high_severity_open_count"] == 0

    async def test_forecast_empty_200(self, client: AsyncClient, mock_db: AsyncMock) -> None:
        mock_db.fetchall.return_value = []

        resp = await client.get(f"{BASE}/forecast")

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["actuals"] == []
        assert len(body["metrics"]) == 5

    async def test_soft_fail_on_db_exception(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.side_effect = Exception("warehouse unavailable")

        resp = await client.get(f"{BASE}/clusters/cost")

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    async def test_slow_queries_missing_table_returns_disabled(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.side_effect = Exception(
            "[TABLE_OR_VIEW_NOT_FOUND] warehouse_slow_queries"
        )

        resp = await client.get(f"{BASE}/warehouses/slow-queries")

        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is False
        assert body["items"] == []
        assert body["total"] == 0

    async def test_overview_soft_fail_on_exception(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchone.side_effect = Exception("connection reset")

        resp = await client.get(f"{BASE}/clusters/overview")

        assert resp.status_code == 200
        assert resp.json()["kpis"]["active_clusters"] == 0

    async def test_recommendations_summary_soft_fail(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchone.side_effect = RuntimeError("timeout")

        resp = await client.get(f"{BASE}/recommendations/summary")

        assert resp.status_code == 200
        assert resp.json()["open_count"] == 0


class TestClusterWindowDays:
    """``window_days`` is validated by the API, never rounded down to 1 in silence.

    A silent fallback would show a 1-day figure under a "last 30 days" heading —
    right numbers, wrong caption.
    """

    LIST_PATHS = ("/clusters/overview", "/clusters/cost", "/clusters/efficiency")

    @pytest.mark.parametrize("window_days", [1, 7, 30, 90])
    @pytest.mark.parametrize("path", LIST_PATHS)
    async def test_accepts_the_four_materialized_windows(
        self, client: AsyncClient, mock_db: AsyncMock, path: str, window_days: int
    ) -> None:
        resp = await client.get(f"{BASE}{path}", params={"window_days": window_days})

        assert resp.status_code == 200
        assert resp.json()["window"]["window_days"] == window_days

    @pytest.mark.parametrize("window_days", [0, 5, 14, 365, -7])
    @pytest.mark.parametrize("path", LIST_PATHS)
    async def test_rejects_any_other_window(
        self, client: AsyncClient, mock_db: AsyncMock, path: str, window_days: int
    ) -> None:
        resp = await client.get(f"{BASE}{path}", params={"window_days": window_days})

        assert resp.status_code == 422

    async def test_defaults_to_one_day(self, client: AsyncClient, mock_db: AsyncMock) -> None:
        resp = await client.get(f"{BASE}/clusters/cost")

        assert resp.status_code == 200
        assert resp.json()["window"]["window_days"] == 1

    async def test_cluster_detail_accepts_the_window(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchone.return_value = {"cluster_id": "c-1", "cost_usd": 1.0}

        resp = await client.get(f"{BASE}/clusters/c-1", params={"window_days": 30})

        assert resp.status_code == 200
        assert resp.json()["window"]["window_days"] == 30

    async def test_governance_ignores_the_window(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """The governance tab is a snapshot: same request, same response as before."""
        resp = await client.get(f"{BASE}/clusters/governance", params={"window_days": 5})

        assert resp.status_code == 200
        body = resp.json()
        assert "window" not in body
        assert body["items"] == []
        assert set(body) == {"items", "total", "page", "page_size", "period"}


class TestWarehouseWindowDays:
    """023 T002: the warehouse list views take the same window as the clusters.

    Same rule, same reason as :class:`TestClusterWindowDays` — a silent fallback to 1
    day would caption a one-day figure "last 30 days".
    """

    LIST_PATHS = (
        "/warehouses/overview",
        "/warehouses/cost",
        "/warehouses/query-performance",
    )

    @pytest.mark.parametrize("window_days", [1, 7, 30, 90])
    @pytest.mark.parametrize("path", LIST_PATHS)
    async def test_accepts_the_four_materialized_windows(
        self, client: AsyncClient, mock_db: AsyncMock, path: str, window_days: int
    ) -> None:
        resp = await client.get(f"{BASE}{path}", params={"window_days": window_days})

        assert resp.status_code == 200
        assert resp.json()["window"]["window_days"] == window_days

    @pytest.mark.parametrize("window_days", [0, 5, 14, 365, -7])
    @pytest.mark.parametrize("path", LIST_PATHS)
    async def test_rejects_any_other_window(
        self, client: AsyncClient, mock_db: AsyncMock, path: str, window_days: int
    ) -> None:
        resp = await client.get(f"{BASE}{path}", params={"window_days": window_days})

        assert resp.status_code == 422

    @pytest.mark.parametrize("path", LIST_PATHS)
    async def test_accepts_the_string_a_browser_sends(
        self, client: AsyncClient, mock_db: AsyncMock, path: str
    ) -> None:
        """A query string is always text: a bare ``Literal[7]`` would reject ``"7"``."""
        resp = await client.get(f"{BASE}{path}?window_days=7")

        assert resp.status_code == 200
        assert resp.json()["window"]["window_days"] == 7

    @pytest.mark.parametrize("path", LIST_PATHS)
    async def test_defaults_to_one_day(
        self, client: AsyncClient, mock_db: AsyncMock, path: str
    ) -> None:
        resp = await client.get(f"{BASE}{path}")

        assert resp.status_code == 200
        assert resp.json()["window"]["window_days"] == 1

    async def test_slow_queries_ignores_the_window(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """Statement-level rows, dated by ``start_time``: contract unchanged."""
        resp = await client.get(f"{BASE}/warehouses/slow-queries", params={"window_days": 5})

        assert resp.status_code == 200
        body = resp.json()
        assert "window" not in body
        assert set(body) == {"enabled", "items", "total", "page", "page_size", "period"}

    async def test_no_numeric_field_comes_back_as_a_json_string(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """Pydantic v2 renders a ``Decimal`` as a JSON *string* and ``toFixed`` throws."""
        mock_db.fetchall.return_value = [
            {
                "warehouse_id": "wh-1",
                "dbu_quantity": Decimal("3.5"),
                "cost_usd": Decimal("12.34"),
                "cost_usd_prev_window": Decimal("8.10"),
                "cost_delta_pct": Decimal("52.3"),
                "cost_per_query_usd": Decimal("1.25"),
                "_total": 1,
            }
        ]

        resp = await client.get(f"{BASE}/warehouses/cost", params={"window_days": 7})

        assert resp.status_code == 200
        item = resp.json()["items"][0]
        for field in (
            "dbu_quantity",
            "cost_usd",
            "cost_usd_prev_window",
            "cost_delta_pct",
            "cost_per_query_usd",
        ):
            assert isinstance(item[field], float), f"{field} = {item[field]!r}"


class TestClusterLifetimeTrend:
    async def test_empty_200_with_the_cost_trend_shape(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = []

        resp = await client.get(f"{BASE}/clusters/c-1/lifetime-trend")

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["granularity"] == "day"
        assert "period" in body

    @pytest.mark.parametrize("granularity", ["day", "week", "month"])
    async def test_supported_granularities(
        self, client: AsyncClient, mock_db: AsyncMock, granularity: str
    ) -> None:
        mock_db.fetchall.return_value = [
            {"bucket": "2026-09-01", "uptime_hours": 21.4, "idle_pct": 38.2}
        ]

        resp = await client.get(
            f"{BASE}/clusters/c-1/lifetime-trend", params={"granularity": granularity}
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["granularity"] == granularity
        assert body["items"][0]["uptime_hours"] == 21.4


class TestComputeMetricsProjectScope:
    """The compute pages read the caller's project scope, never the whole platform.

    ``gold_dbx_compute_*`` tables carry a ``workspace_id`` and no ``source_lz_id``,
    so the Databricks-workspace dimension of the project scope is the only thing
    that can restrict them.
    """

    @staticmethod
    def _issued(mock_db: AsyncMock) -> list[tuple[str, list[object]]]:
        calls = list(mock_db.fetchone.await_args_list) + list(mock_db.fetchall.await_args_list)
        return [(str(call.args[0]), list(call.args[1:])) for call in calls if call.args]

    async def test_clusters_overview_filters_on_the_project_workspaces(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        resp = await client.get(
            f"{BASE}/clusters/overview", headers={"x-dcm-workspace-ids": "1234"}
        )

        assert resp.status_code == 200
        issued = self._issued(mock_db)
        assert issued
        for sql, params in issued:
            assert "workspace_id IN" in sql
            assert {"1234", "adb-1234"} <= set(params)

    async def test_warehouses_cost_filters_on_the_project_workspaces(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        resp = await client.get(
            f"{BASE}/warehouses/cost", headers={"x-dcm-workspace-ids": "1234"}
        )

        assert resp.status_code == 200
        issued = self._issued(mock_db)
        assert issued
        for sql, params in issued:
            assert "workspace_id IN" in sql
            assert {"1234", "adb-1234"} <= set(params)

    async def test_clusters_overview_without_workspace_scope_reads_nothing(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """LZ scope alone cannot be expressed here, so it must not open the table."""
        resp = await client.get(f"{BASE}/clusters/overview", headers={"x-dcm-lz-ids": "lz-a"})

        assert resp.status_code == 200
        issued = self._issued(mock_db)
        assert issued
        assert all("1 = 0" in sql for sql, _params in issued)

    async def test_platform_admin_keeps_unrestricted_compute_access(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        resp = await client.get(
            f"{BASE}/clusters/overview", headers={"x-dcm-platform-role": "super_admin"}
        )

        assert resp.status_code == 200
        issued = self._issued(mock_db)
        assert issued
        assert not any("1 = 0" in sql for sql, _params in issued)
        assert not any("workspace_id IN" in sql for sql, _params in issued)


class TestColumnFilterRoutes:
    """023 T004, extended by 025 T002: ``column_filter`` on the thirteen list routes.

    The two Lakeflow routes are asserted here rather than in a Lakeflow module: the
    contract is one — same query-string shape, same 422, same allowlist — and a reader
    checking "is an unknown key refused everywhere?" should not have to find it twice.
    """

    @staticmethod
    def _issued(mock_db: AsyncMock) -> list[tuple[str, list[object]]]:
        calls = list(mock_db.fetchone.await_args_list) + list(mock_db.fetchall.await_args_list)
        return [(str(call.args[0]), list(call.args[1:])) for call in calls if call.args]

    @pytest.mark.parametrize(
        ("path", "params"),
        [
            (f"{BASE}/clusters/overview", {"column_filter": "nope:1"}),
            (f"{BASE}/clusters/cost", {"column_filter": "nope:1"}),
            (f"{BASE}/clusters/efficiency", {"column_filter": "nope:1"}),
            (f"{BASE}/clusters/governance", {"column_filter": "nope:1"}),
            (f"{BASE}/warehouses/overview", {"column_filter": "nope:1"}),
            (f"{BASE}/warehouses/cost", {"column_filter": "nope:1"}),
            (f"{BASE}/warehouses/query-performance", {"column_filter": "nope:1"}),
            (f"{BASE}/warehouses/slow-queries", {"column_filter": "nope:1"}),
            (f"{BASE}/recommendations", {"column_filter": "nope:1"}),
            # 025 T002 — the two serverless list views. ``surface`` is required on the
            # objects route, so it is passed: the 422 must come from the filter key.
            (f"{BASE}/serverless/objects", {"surface": "JOB", "column_filter": "nope:1"}),
            (f"{BASE}/serverless/governance", {"column_filter": "nope:1"}),
            (f"{LAKEFLOW}/jobs", {"column_filter": "nope:1"}),
            (f"{LAKEFLOW}/jobs/42/runs", {"column_filter": "nope:1"}),
        ],
    )
    async def test_unknown_column_is_422_on_every_list_route(
        self, client: AsyncClient, mock_db: AsyncMock, path: str, params: dict[str, str]
    ) -> None:
        """Never a 200 with an empty table: every service soft-fails inside."""
        resp = await client.get(path, params=params)

        assert resp.status_code == 422, path
        assert "nope" in resp.json()["detail"]
        assert self._issued(mock_db) == [], "a refused filter must not reach the warehouse"

    async def test_the_422_lists_the_accepted_keys(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        resp = await client.get(f"{BASE}/clusters/cost", params={"column_filter": "nope:1"})

        detail = resp.json()["detail"]
        assert "cluster_type" in detail and "sku_group" in detail

    @pytest.mark.parametrize(
        "raw",
        ["nocolon", "cost", ":100"],
        ids=["no-separator", "key-alone", "empty-key"],
    )
    async def test_malformed_pair_is_422(
        self, client: AsyncClient, mock_db: AsyncMock, raw: str
    ) -> None:
        resp = await client.get(f"{BASE}/clusters/cost", params={"column_filter": raw})

        assert resp.status_code == 422

    async def test_repeated_key_is_422_rather_than_a_guess(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """AND or OR? Refused instead of picked for the user."""
        resp = await client.get(
            f"{BASE}/clusters/cost?column_filter=cost:1&column_filter=cost:10"
        )

        assert resp.status_code == 422

    async def test_declared_filter_reaches_the_sql_with_a_bound_value(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        resp = await client.get(
            f"{BASE}/clusters/cost", params={"column_filter": "cluster_type:job"}
        )

        assert resp.status_code == 200
        issued = self._issued(mock_db)
        assert issued
        assert any("UPPER(c.cluster_type) = ?" in sql for sql, _params in issued)
        assert any("JOB" in params for _sql, params in issued)

    async def test_injected_fragment_never_reaches_the_sql_text(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """The value is bound; only the allowlist ever contributes SQL text."""
        resp = await client.get(
            f"{BASE}/clusters/cost",
            params={"column_filter": "cluster:x'; DROP TABLE it.gold; --"},
        )

        assert resp.status_code == 200
        issued = self._issued(mock_db)
        assert issued
        for sql, _params in issued:
            assert "DROP" not in sql.upper()
        assert any(
            "%x'; drop table it.gold; --%" in params for _sql, params in issued
        )

    async def test_injected_key_is_refused_not_interpolated(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        resp = await client.get(
            f"{BASE}/clusters/cost",
            params={"column_filter": "cost) OR 1=1 --:1"},
        )

        assert resp.status_code == 422
        assert self._issued(mock_db) == []

    async def test_lakeflow_jobs_filter_reaches_the_sql(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        resp = await client.get(f"{LAKEFLOW}/jobs", params={"column_filter": "retries:3"})

        assert resp.status_code == 200
        issued = self._issued(mock_db)
        assert issued
        assert any("COALESCE(avg_retry_count, 0) >= ?" in sql for sql, _params in issued)
        assert any(3.0 in params for _sql, params in issued)

    async def test_two_different_filters_do_not_share_a_cache_entry(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """``fetch_lakeflow_jobs`` is response-cached — the filter is part of the key."""
        first = await client.get(f"{LAKEFLOW}/jobs", params={"column_filter": "retries:3"})
        issued_after_first = len(self._issued(mock_db))
        second = await client.get(f"{LAKEFLOW}/jobs", params={"column_filter": "retries:10"})

        assert (first.status_code, second.status_code) == (200, 200)
        assert len(self._issued(mock_db)) > issued_after_first

    async def test_numeric_options_are_declared_without_touching_the_warehouse(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        resp = await client.get(
            f"{BASE}/filter-options", params={"view": "clusters-cost", "column": "cost"}
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["kind"] == "numeric"
        assert [option["value"] for option in body["options"]] == ["1", "10", "100", "1000"]
        assert body["truncated"] is False
        assert self._issued(mock_db) == []

    async def test_text_options_stay_in_the_caller_perimeter(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        resp = await client.get(
            f"{BASE}/filter-options",
            params={"view": "clusters-cost", "column": "cluster", "q": "etl"},
            headers={"x-dcm-workspace-ids": "1234"},
        )

        assert resp.status_code == 200
        issued = self._issued(mock_db)
        assert issued
        for sql, params in issued:
            assert "workspace_id IN" in sql
            assert {"1234", "adb-1234"} <= set(params)

    async def test_options_ignore_the_current_selection(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """No ``column_filter`` on this route: narrowing one column must not empty the
        lists of the others, or the user could not widen back."""
        resp = await client.get(
            f"{BASE}/filter-options",
            params={
                "view": "clusters-cost",
                "column": "cluster",
                "column_filter": "cluster_type:job",
            },
        )

        assert resp.status_code == 200
        for sql, _params in self._issued(mock_db):
            assert "cluster_type" not in sql

    async def test_filter_options_is_not_shadowed_by_the_detail_routes(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """Declared before ``/clusters/{cluster_id}``: a 404 here would mean it was
        parsed as a cluster id."""
        resp = await client.get(
            f"{BASE}/filter-options",
            params={"view": "warehouses-overview", "column": "size"},
        )

        assert resp.status_code == 200
        assert resp.json()["column"] == "size"

    async def test_unknown_view_is_422(self, client: AsyncClient, mock_db: AsyncMock) -> None:
        resp = await client.get(
            f"{BASE}/filter-options", params={"view": "nope", "column": "cost"}
        )

        assert resp.status_code == 422
        assert "clusters-cost" in resp.json()["detail"]

    async def test_lakeflow_filter_options_route_answers_its_own_views(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        resp = await client.get(
            f"{LAKEFLOW}/filter-options",
            params={"view": "lakeflow-job-runs", "column": "duration"},
        )

        assert resp.status_code == 200
        assert resp.json()["kind"] == "numeric"

    async def test_a_compute_view_is_refused_by_the_lakeflow_route(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """Two routes because the perimeters differ; the answer says so instead of
        silently resolving a compute view in the Lakeflow scope."""
        resp = await client.get(
            f"{LAKEFLOW}/filter-options",
            params={"view": "clusters-cost", "column": "cost"},
        )

        assert resp.status_code == 422
        assert "lakeflow" in resp.json()["detail"].lower()


class TestServerlessRoutes:
    """025 T002: the eight serverless routes, at the HTTP boundary.

    What this class adds to ``test_compute_metrics_serverless.py`` is everything the
    service functions cannot state about themselves: which path resolves to which
    handler, which missing parameter is a 422, and which absent row is a 404. The
    payload *shapes* are asserted on the empty perimeter because that is what a browser
    gets on a fresh workspace — and an empty page with a missing key is a crash in the
    UI, not an empty page.
    """

    SENTINEL = "_NO_OBJECT"

    @staticmethod
    def _issued(mock_db: AsyncMock) -> list[tuple[str, list[object]]]:
        calls = list(mock_db.fetchone.await_args_list) + list(mock_db.fetchall.await_args_list)
        return [(str(call.args[0]), list(call.args[1:])) for call in calls if call.args]

    # -- the five aggregates, empty perimeter ------------------------------------------

    async def test_overview_empty_200_keeps_run_count_unmeasured(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """``run_count: null`` and not ``0``: nothing was counted, which is not the same
        claim as "there were no runs". The cost is ``0.0`` because a sum over no row is
        genuinely zero dollars."""
        resp = await client.get(f"{BASE}/serverless/overview")

        assert resp.status_code == 200
        body = resp.json()
        assert body["kpis"]["cost_usd"] == 0.0
        assert body["kpis"]["run_count"] is None
        # The block exists and its **share** is null: 0 % would say serverless is none of
        # the compute spend, which is a measurement, and none was taken here.
        assert body["kpis"]["serverless_share"]["pct"] is None
        assert body["kpis"]["cost_usd_prev_window"] is None
        assert body["window"]["window_days"] == 1
        assert set(body) == {"kpis", "governance_period", "window", "period"}

    async def test_surfaces_empty_200_has_the_page_and_the_window(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        resp = await client.get(f"{BASE}/serverless/surfaces", params={"window_days": 30})

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert (body["total"], body["page"], body["page_size"]) == (0, 1, 25)
        assert body["total_cost_usd"] == 0.0
        assert body["window"]["window_days"] == 30

    async def test_cost_trend_empty_200_carries_both_lists(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """``items`` is the flat rows, ``series`` the per-surface split the chart draws:
        a payload with one and not the other renders half a chart."""
        resp = await client.get(f"{BASE}/serverless/cost-trend")

        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {"items", "series", "period", "granularity"}
        assert body["granularity"] == "day"

    async def test_governance_empty_200_states_no_snapshot_rather_than_a_date(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """The snapshot has no bounds here, and says so instead of borrowing ``period``.

        Captioning an empty coverage table with today's date would claim a measurement
        nobody took — hence ``from``/``to`` at ``null`` rather than absent or defaulted.
        """
        resp = await client.get(f"{BASE}/serverless/governance")

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["governance_period"] == {"from": None, "to": None}
        assert body["totals"]["cost_usd"] == 0.0
        # No dollars, so no coverage ratio: 100 % ("all covered") and 0 % ("none covered")
        # are both claims, and the honest answer is neither.
        assert body["totals"]["owner_tag_coverage_pct"] is None
        assert body["totals"]["identity_coverage_pct"] is None
        assert "window" not in body

    async def test_levers_empty_200_keeps_the_three_blocks(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """``cost_per_run`` and ``dlt_comparison`` are ``null`` — the DLT block has a
        30-request floor and publishing a rate below it is worse than publishing none."""
        resp = await client.get(f"{BASE}/serverless/levers")

        assert resp.status_code == 200
        body = resp.json()
        assert body["performance_target"] == {
            "items": [],
            "total_cost_usd": 0.0,
            "unset_share_pct": None,
        }
        assert body["cost_per_run"] is None
        assert body["dlt_comparison"] is None
        assert body["window"]["window_days"] == 1

    async def test_objects_empty_200_counts_objects_and_rows_separately(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """``total`` is rows for the pager, ``object_count`` is distinct objects — the two
        differ as soon as one object is billed in several workspaces."""
        resp = await client.get(f"{BASE}/serverless/objects")

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["object_count"] == 0
        assert body["total_cost_usd"] == 0.0

    # -- path resolution ---------------------------------------------------------------

    @pytest.mark.parametrize(
        "path",
        [
            "/serverless/overview",
            "/serverless/surfaces",
            "/serverless/cost-trend",
            "/serverless/governance",
            "/serverless/levers",
            "/serverless/objects",
        ],
    )
    async def test_a_static_serverless_path_is_not_read_as_an_object_id(
        self, client: AsyncClient, mock_db: AsyncMock, path: str
    ) -> None:
        """The failure this pins has a signature, and it is **not** a 404.

        ``/serverless/objects/{object_id}`` requires ``surface``, so a static path
        swallowed by the variable route would answer **422 — field required** on a
        request that carries no ``surface`` at all. Which is why the assertion is on 200
        and the note is here: a reader seeing a 422 on this test should look at the route
        declaration order, not at the query string.
        """
        resp = await client.get(f"{BASE}{path}")

        assert resp.status_code == 200, resp.text

    async def test_serverless_filter_options_is_404_by_design(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """There is one filter-options route for the whole compute module, driven by
        ``FILTERABLE_COLUMNS``. A second one under ``/serverless/`` would be a second
        allowlist to keep in sync — so the generic route serves the serverless views and
        the namespaced path deliberately does not exist."""
        namespaced = await client.get(f"{BASE}/serverless/filter-options")
        generic = await client.get(
            f"{BASE}/filter-options",
            params={"view": "serverless-objects", "column": "surface"},
        )

        assert namespaced.status_code == 404
        assert generic.status_code == 200
        assert generic.json()["kind"] == "enum"

    # -- the detail route: 404 is a fact, 422 is a missing key ------------------------

    async def test_detail_404s_when_the_object_is_out_of_scope(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """The one route of the family that does **not** soft-fail to an empty payload:
        an empty object page would read as a 0 $ object that exists."""
        mock_db.fetchall.return_value = []

        resp = await client.get(
            f"{BASE}/serverless/objects/114088010544136", params={"surface": "JOB"}
        )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Serverless object not found"

    async def test_detail_404s_on_the_gold_sentinel_without_querying(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """``_NO_OBJECT`` is gold's null-safe merge key, not an object. Refused before the
        warehouse is touched — there is nothing to look up."""
        resp = await client.get(
            f"{BASE}/serverless/objects/{self.SENTINEL}", params={"surface": "APP"}
        )

        assert resp.status_code == 404
        assert self._issued(mock_db) == []

    @pytest.mark.parametrize(
        "suffix", ["", "/cost-trend"], ids=["detail", "object-cost-trend"]
    )
    async def test_a_missing_surface_is_422_and_not_a_silent_sum(
        self, client: AsyncClient, mock_db: AsyncMock, suffix: str
    ) -> None:
        """The gold grain is ``(cloud, workspace, surface, object_id)``: 4 of the 20 583
        identified objects appear under two surfaces, so answering without a surface
        would add two things together under a title naming one."""
        resp = await client.get(f"{BASE}/serverless/objects/mv-1{suffix}")

        assert resp.status_code == 422
        assert self._issued(mock_db) == []

    @pytest.mark.parametrize(
        "suffix", ["", "/cost-trend"], ids=["detail", "object-cost-trend"]
    )
    async def test_an_unknown_surface_is_422_on_the_object_routes(
        self, client: AsyncClient, mock_db: AsyncMock, suffix: str
    ) -> None:
        resp = await client.get(
            f"{BASE}/serverless/objects/mv-1{suffix}", params={"surface": "SQL_WAREHOUSSE"}
        )

        assert resp.status_code == 422
        assert self._issued(mock_db) == []

    @pytest.mark.parametrize("path", ["/serverless/cost-trend", "/serverless/objects"])
    async def test_an_unknown_surface_is_422_on_the_list_routes(
        self, client: AsyncClient, mock_db: AsyncMock, path: str
    ) -> None:
        """``surface`` is optional here, which is not the same as unchecked: an unknown
        value used to come back as a perfectly rendered empty page."""
        resp = await client.get(f"{BASE}{path}", params={"surface": "nope"})

        assert resp.status_code == 422
        assert self._issued(mock_db) == []

    async def test_the_object_trend_answers_an_empty_series_on_the_sentinel(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """A trend never 404s, even where the detail does: the same page asks for both,
        and one absent tile must not fail the page. Nothing is queried either — there is
        no object behind the sentinel to have a series for."""
        resp = await client.get(
            f"{BASE}/serverless/objects/{self.SENTINEL}/cost-trend",
            params={"surface": "NETWORKING"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["workspace_count"] == 0
        assert self._issued(mock_db) == []

    # -- what the daily tables must not be filtered on --------------------------------

    async def test_the_trend_routes_never_bind_a_window(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """Both read the **daily** table, which has no ``window_days`` column. Adding the
        predicate returns zero rows — a flat empty chart, no error."""
        trend = await client.get(f"{BASE}/serverless/cost-trend")
        object_trend = await client.get(
            f"{BASE}/serverless/objects/job-1/cost-trend", params={"surface": "JOB"}
        )

        assert (trend.status_code, object_trend.status_code) == (200, 200)
        issued = self._issued(mock_db)
        assert issued
        for sql, _params in issued:
            assert "window_days" not in sql

    async def test_governance_declares_no_window_and_binds_none(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """Same contract as ``/clusters/governance``: the parameter does not exist here.

        So ``window_days=30`` is an unknown query parameter — accepted and ignored, as
        FastAPI does for any extra — and the assertion that matters is the one on the SQL:
        the snapshot table has no ``window_days`` column, and the response carries no
        ``window`` block that could caption its figures with a window.
        """
        resp = await client.get(f"{BASE}/serverless/governance", params={"window_days": 30})

        assert resp.status_code == 200
        assert "window" not in resp.json()
        issued = self._issued(mock_db)
        assert issued
        for sql, params in issued:
            assert "window_days" not in sql
            assert 30 not in params

    # -- project scope -----------------------------------------------------------------

    @pytest.mark.parametrize(
        "path",
        [
            "/serverless/overview",
            "/serverless/surfaces",
            "/serverless/cost-trend",
            "/serverless/governance",
            "/serverless/levers",
            "/serverless/objects",
        ],
    )
    async def test_every_serverless_route_stays_in_the_project_workspaces(
        self, client: AsyncClient, mock_db: AsyncMock, path: str
    ) -> None:
        """``gold_dbx_serverless_*`` carries a ``workspace_id`` and no ``source_lz_id``,
        so this dimension is the only thing that can restrict the tables."""
        resp = await client.get(f"{BASE}{path}", headers={"x-dcm-workspace-ids": "1234"})

        assert resp.status_code == 200
        issued = self._issued(mock_db)
        assert issued
        for sql, params in issued:
            assert "workspace_id IN" in sql
            assert {"1234", "adb-1234"} <= set(params)

    async def test_the_object_routes_stay_in_the_project_workspaces(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """The detail is scoped too: a deep link is not an authorisation."""
        mock_db.fetchall.return_value = []

        detail = await client.get(
            f"{BASE}/serverless/objects/job-1",
            params={"surface": "JOB"},
            headers={"x-dcm-workspace-ids": "1234"},
        )

        assert detail.status_code == 404
        issued = self._issued(mock_db)
        assert issued
        for sql, params in issued:
            assert "workspace_id IN" in sql
            assert {"1234", "adb-1234"} <= set(params)

    async def test_a_scope_without_workspaces_reads_nothing(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """LZ scope alone cannot be expressed on these tables, so it must not open them."""
        resp = await client.get(
            f"{BASE}/serverless/surfaces", headers={"x-dcm-lz-ids": "lz-a"}
        )

        assert resp.status_code == 200
        issued = self._issued(mock_db)
        assert issued
        assert all("1 = 0" in sql for sql, _params in issued)

    # -- soft-fail -----------------------------------------------------------------------

    @pytest.mark.parametrize(
        "path",
        [
            "/serverless/overview",
            "/serverless/surfaces",
            "/serverless/cost-trend",
            "/serverless/governance",
            "/serverless/levers",
            "/serverless/objects",
        ],
    )
    async def test_a_missing_gold_table_is_an_empty_payload_and_not_a_500(
        self, client: AsyncClient, mock_db: AsyncMock, path: str
    ) -> None:
        """Family convention: a tab whose table is not deployed yet leaves the rest of
        the page working. The trade-off is that an all-zero answer has to be diagnosed
        and never taken at face value."""
        mock_db.fetchall.side_effect = Exception("[TABLE_OR_VIEW_NOT_FOUND] serverless")
        mock_db.fetchone.side_effect = Exception("[TABLE_OR_VIEW_NOT_FOUND] serverless")

        resp = await client.get(f"{BASE}{path}")

        assert resp.status_code == 200, resp.text

    async def test_the_detail_route_lets_a_warehouse_failure_surface(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """The deliberate exception to the convention, and the reason it is one: an empty
        detail is indistinguishable from "this object does not exist", so a broken
        warehouse must not be reported as a missing object."""
        mock_db.fetchall.side_effect = Exception("connection reset")

        with pytest.raises(Exception, match="connection reset"):
            await client.get(
                f"{BASE}/serverless/objects/job-1", params={"surface": "JOB"}
            )

    # -- decimals ----------------------------------------------------------------------

    async def test_no_serverless_number_comes_back_as_a_json_string(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """The warehouse driver hands back ``Decimal`` for a ``SUM``; Pydantic renders it
        as a JSON string and ``toFixed`` throws on it."""
        mock_db.fetchall.return_value = [
            {
                "serverless_surface": "JOB",
                "cost_usd": Decimal("12.34"),
                "cost_usd_prev_window": Decimal("8.10"),
                "cost_delta_pct": Decimal("52.3"),
                "dbu_quantity": Decimal("3.5"),
                "run_count": 7,
                "object_count": 2,
                "_total": 1,
            }
        ]

        resp = await client.get(f"{BASE}/serverless/surfaces")

        assert resp.status_code == 200
        item = resp.json()["items"][0]
        for field in ("cost_usd", "cost_usd_prev_window", "cost_delta_pct", "dbu_quantity"):
            assert isinstance(item[field], float), f"{field} = {item[field]!r}"


class TestServerlessDeclaredContract:
    """The serverless payloads against the ``dcm_commons`` models that document them.

    Nothing enforces this at runtime — the handlers are annotated ``dict[str, Any]`` and
    no route uses ``response_model`` — so the models drift silently, and ``api.ts`` is
    generated from them by hand in T003. Validating the recorded payloads is the only
    thing tying the two together.

    Both "nothing to show" paths are checked, because they are **not** the same code: the
    live query on an empty perimeter returns rows-of-nothing, while a broken or
    undeployed table falls back to a hand-written literal. A field nullable in one and not
    the other is a crash in the UI on the day the table is late.
    """

    AGGREGATES = (
        "/serverless/overview",
        "/serverless/surfaces",
        "/serverless/cost-trend",
        "/serverless/governance",
        "/serverless/levers",
        "/serverless/objects",
    )

    @staticmethod
    def _break(mock_db: AsyncMock) -> None:
        mock_db.fetchall.side_effect = Exception("[TABLE_OR_VIEW_NOT_FOUND] serverless")
        mock_db.fetchone.side_effect = Exception("[TABLE_OR_VIEW_NOT_FOUND] serverless")

    @pytest.mark.parametrize("path", AGGREGATES)
    async def test_the_soft_fail_payload_has_the_same_keys_as_the_live_one(
        self, client: AsyncClient, mock_db: AsyncMock, path: str
    ) -> None:
        """One shape per route, not two. The values may differ — a missing table cannot
        report a governance period — but a key that appears in only one of the two paths
        is a branch the frontend has no way to discover before production."""
        live = await client.get(f"{BASE}{path}")
        self._break(mock_db)
        fallback = await client.get(f"{BASE}{path}")

        assert (live.status_code, fallback.status_code) == (200, 200)
        assert set(live.json()) == set(fallback.json())

    @pytest.mark.parametrize("broken", [False, True], ids=["live-empty", "soft-fail"])
    async def test_the_overview_validates_against_its_declared_model(
        self, client: AsyncClient, mock_db: AsyncMock, broken: bool
    ) -> None:
        from dcm_commons.schemas import ServerlessOverviewResponse

        if broken:
            self._break(mock_db)

        resp = await client.get(f"{BASE}/serverless/overview")

        assert resp.status_code == 200
        ServerlessOverviewResponse.model_validate(resp.json())

    @pytest.mark.parametrize("broken", [False, True], ids=["live-empty", "soft-fail"])
    async def test_the_levers_validate_against_their_declared_model(
        self, client: AsyncClient, mock_db: AsyncMock, broken: bool
    ) -> None:
        from dcm_commons.schemas import ServerlessLeversResponse

        if broken:
            self._break(mock_db)

        resp = await client.get(f"{BASE}/serverless/levers")

        assert resp.status_code == 200
        ServerlessLeversResponse.model_validate(resp.json())

    async def test_the_governance_totals_validate_against_their_declared_model(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        from dcm_commons.schemas import ServerlessGovernanceTotals

        resp = await client.get(f"{BASE}/serverless/governance")

        assert resp.status_code == 200
        totals = resp.json()["totals"]
        ServerlessGovernanceTotals.model_validate(totals)
        undeclared = set(totals) - set(ServerlessGovernanceTotals.model_fields)
        assert undeclared == set(), f"served but not declared: {undeclared}"

    async def test_the_overview_serves_no_undeclared_key(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """``model_validate`` ignores extra keys, so the reverse direction needs its own
        assertion: a column served without being declared reaches the client and diverges
        from the contract in silence."""
        from dcm_commons.schemas import ServerlessOverviewKpis, ServerlessOverviewResponse

        body = (await client.get(f"{BASE}/serverless/overview")).json()

        declared = {
            field.alias or name
            for name, field in ServerlessOverviewResponse.model_fields.items()
        }
        assert set(body) - declared == set()
        assert set(body["kpis"]) - set(ServerlessOverviewKpis.model_fields) == set()
