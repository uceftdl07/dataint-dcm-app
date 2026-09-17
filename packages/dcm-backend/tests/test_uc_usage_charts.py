"""Execute chart SQL on local fixtures, plus route validation and scope guards.

The queries use the SQL subset shared by SQLite and Databricks; no query string
is rewritten or replaced by canned aggregate results in the calculation tests.
A live SQL Warehouse check remains an integration step at deployment.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.api.services.uc_usage_charts import (
    fetch_consumer_charts,
    fetch_finops_charts,
    fetch_table_charts,
)
from app.api.services.uc_usage_common import (
    GOLD_TABLE_CATALOG,
    GOLD_TABLE_DAILY,
    GOLD_TABLE_POPULARITY_DAILY,
)


class ChartDatabase:
    def __init__(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(f"""
            CREATE TABLE {GOLD_TABLE_DAILY} (
                cloud_provider TEXT NOT NULL, catalog TEXT, schema TEXT, table_full_name TEXT,
                period_start TEXT, consumer_id TEXT, consumer_name TEXT, consumer_type TEXT,
                request_count INTEGER, costed_request_count INTEGER, estimated_cost_usd REAL,
                cost_attribution_method TEXT, cost_basis TEXT
            )
        """)
        self.connection.execute(f"""
            CREATE VIEW {GOLD_TABLE_POPULARITY_DAILY} AS
            SELECT cloud_provider, catalog, schema, table_full_name, period_start,
                SUM(request_count) AS request_count, SUM(estimated_cost_usd) AS estimated_cost_usd
            FROM {GOLD_TABLE_DAILY}
            GROUP BY cloud_provider, catalog, schema, table_full_name, period_start
        """)
        # The deleted flag never reaches the facts (spec 027): the charts exclude
        # deleted tables by anti-join, so the catalogue must exist even empty.
        self.connection.execute(f"""
            CREATE TABLE {GOLD_TABLE_CATALOG} (
                cloud_provider TEXT NOT NULL, table_full_name TEXT,
                is_deleted INTEGER, deleted_at TEXT, lifecycle_state TEXT
            )
        """)
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    @staticmethod
    def table(name: str) -> str:
        return name

    async def fetchall(self, sql: str, *params: Any) -> list[dict[str, Any]]:
        self.calls.append((sql, params))
        parameters = [value.isoformat() if isinstance(value, date) else value for value in params]
        return [dict(row) for row in self.connection.execute(sql, parameters).fetchall()]

    def add(
        self,
        name: str = "invoices",
        *,
        day: str = "2026-09-01",
        requests: int = 10,
        consumer: str = "shared",
        kind: str | None = "JOB",
        cloud: str = "aws",
        catalog: str = "it",
        schema: str = "finance",
        cost: float | None = None,
        costed: int = 0,
    ) -> None:
        self.connection.execute(
            f"INSERT INTO {GOLD_TABLE_DAILY} VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                cloud,
                catalog,
                schema,
                f"{catalog}.{schema}.{name}",
                day,
                consumer,
                consumer,
                kind,
                requests,
                costed,
                cost,
                "equal_parts_fallback" if cost is not None else None,
                "warehouse_prorata" if cost is not None else None,
            ),
        )

    def mark_deleted(
        self,
        name: str = "invoices",
        *,
        cloud: str = "aws",
        catalog: str = "it",
        schema: str = "finance",
        deleted_at: str = "2026-09-02T00:00:00",
    ) -> None:
        self.connection.execute(
            f"INSERT INTO {GOLD_TABLE_CATALOG} VALUES (?, ?, 1, ?, 'DELETED')",
            (cloud, f"{catalog}.{schema}.{name}", deleted_at),
        )


@pytest.fixture
def chart_db() -> Any:
    db = ChartDatabase()
    yield db
    db.connection.close()


async def test_period_ranking_and_remainder_reconcile_beyond_a_table_page(chart_db: Any) -> None:
    for i in range(30):
        chart_db.add(f"table_{i:02}", requests=(i + 1) * 10)
        chart_db.add(f"table_{i:02}", day="2026-09-02", requests=1000 if i == 0 else 1)
    chart_db.add("excluded", catalog="another", requests=99999)
    result = await fetch_table_charts(
        chart_db,
        start=date(2026, 9, 1),
        end=date(2026, 9, 3),
        catalog="it",
        schema="finance",
    )
    expected = sum((i + 1) * 10 for i in range(30)) + 1029
    assert result["summary"]["total"] == expected
    assert result["summary"]["entity_count"] == 30
    assert len(result["ranking"]) == 10
    assert result["ranking"][0]["label"] == "it.finance.table_00"
    assert len(result["series"]) == 6
    assert result["series"][-1]["entity_count"] == 25
    assert sum(p["value"] or 0 for series in result["series"] for p in series["points"]) == expected
    assert result["summary"]["top_5_total"] + result["summary"]["other_total"] == expected
    # An unobserved day breaks every line, including the remainder.
    assert all(series["points"][2]["value"] is None for series in result["series"])
    assert len(result["activity"]["rows"]) == 10


async def test_multi_table_scope_and_cloud_homonyms_do_not_multiply_rows(chart_db: Any) -> None:
    chart_db.add("a", requests=10)
    chart_db.add("a", requests=20, cloud="azure")
    chart_db.add("b", requests=30)
    chart_db.add("ignored", requests=999)
    result = await fetch_table_charts(
        chart_db,
        start=date(2026, 9, 1),
        end=date(2026, 9, 1),
        tables=["it.finance.a", "it.finance.b"],
    )
    assert result["summary"]["total"] == 60
    assert result["summary"]["entity_count"] == 3
    assert len({entry["key"] for entry in result["ranking"]}) == 3
    assert sorted(entry["value"] for entry in result["ranking"]) == [10, 20, 30]
    assert result["filters"]["tables"] == ["it.finance.a", "it.finance.b"]


async def test_single_table_ranks_its_consumers_and_filters_are_bound(chart_db: Any) -> None:
    chart_db.add(consumer="reader-a", requests=1)
    chart_db.add(consumer="reader-b", requests=3)
    chart_db.add("other", consumer="reader-c", requests=999)
    result = await fetch_table_charts(
        chart_db,
        start=date(2026, 9, 1),
        end=date(2026, 9, 1),
        tables=["it.finance.invoices"],
    )
    assert result["ranking_mode"] == "consumers"
    assert [entry["label"] for entry in result["single_table_consumers"]] == [
        "reader-b",
        "reader-a",
    ]
    empty = await fetch_table_charts(
        chart_db,
        start=date(2026, 9, 1),
        end=date(2026, 9, 1),
        catalog="it' OR 1=1 --",
    )
    assert empty["summary"]["entity_count"] == 0
    assert empty["series"] == []
    assert "it' OR 1=1 --" not in chart_db.calls[-1][0]
    assert "it' OR 1=1 --" in chart_db.calls[-1][1]


async def test_daily_distincts_and_previous_dates_are_not_sums_of_table_distincts(
    chart_db: Any,
) -> None:
    chart_db.add("a", day="2026-09-03", consumer="same", kind="FUTURE_TYPE")
    chart_db.add("b", day="2026-09-03", consumer="same", kind="FUTURE_TYPE")
    chart_db.add("b", day="2026-09-03", consumer="same", cloud="azure", kind=None)
    chart_db.add("a", day="2026-09-03", consumer="writer", requests=0)
    chart_db.add("a", day="2026-09-01", consumer="previous")
    chart_db.add("a", day="2026-09-04", consumer="same")
    result = await fetch_consumer_charts(chart_db, start=date(2026, 9, 3), end=date(2026, 9, 4))
    assert result["previous_period"] == {"start": "2026-09-01", "end": "2026-09-02"}
    assert result["active_consumers"] == [
        {"date": "2026-09-03", "value": 2, "previous_date": "2026-09-01", "previous_value": 1},
        {"date": "2026-09-04", "value": 1, "previous_date": "2026-09-02", "previous_value": None},
    ]
    assert result["ranking"][0]["distinct_tables"] == 2
    assert result["ranking"][0]["value"] == 30
    assert all(entry["label"] != "writer" for entry in result["ranking"])
    assert {series["key"] for series in result["by_type"]} == {"FUTURE_TYPE", "UNKNOWN", "JOB"}
    assert result["total_requests"] == 40


async def test_cost_denominator_coverage_and_zero_are_explicit(chart_db: Any) -> None:
    chart_db.add(requests=100, cost=10, costed=2)
    chart_db.add(day="2026-09-02", requests=2, cost=0, costed=2)
    chart_db.add(day="2026-09-03", requests=7)
    result = await fetch_finops_charts(chart_db, start=date(2026, 9, 1), end=date(2026, 9, 4))
    assert [point["value"] for point in result["unit_cost"]] == [5000, 0, None, None]
    assert result["unit_cost"][0]["coverage_pct"] == 2
    assert result["unit_cost"][2]["coverage_pct"] == 0
    assert result["unit_cost"][3]["coverage_pct"] is None
    assert result["cost_coverage_pct"] == round(4 / 109 * 100, 2)
    assert result["cost_attribution_method"] == "equal_parts_fallback"
    assert result["cost_basis"] == "warehouse_prorata"
    assert [p["value"] for p in result["series"][0]["points"]] == [10, 0, None, None]


async def test_unknown_costs_and_weekly_observation_counts(chart_db: Any) -> None:
    chart_db.add(requests=0)
    result = await fetch_finops_charts(chart_db, start=date(2026, 9, 1), end=date(2026, 9, 1))
    assert result["summary"]["total"] is None
    assert result["summary"]["unmeasured_entity_count"] == 1
    assert result["ranking"][0]["value"] is None
    activity = (
        await fetch_table_charts(
            chart_db,
            start=date(2026, 9, 1),
            end=date(2026, 10, 15),
        )
    )["activity"]
    assert activity["grain"] == "week"
    assert activity["columns"][0] == {"start": "2026-09-01", "end": "2026-09-06"}
    assert activity["columns"][-1]["end"] == "2026-10-15"
    assert activity["rows"][0]["cells"][0] == {"value": 0, "observed_days": 1, "expected_days": 6}
    assert activity["rows"][0]["cells"][1]["value"] is None


@pytest.mark.parametrize("view", ["tables", "consumers", "finops"])
async def test_chart_routes_validate_period_and_existing_scope(
    client: AsyncClient,
    mock_db: AsyncMock,
    view: str,
) -> None:
    path = f"/api/v1/uc-usage/charts/{view}"
    headers = {"x-dcm-platform-role": "super_admin"}
    period = {"period_start": "2026-09-01", "period_end": "2026-09-02"}
    assert (await client.get(path, headers=headers)).status_code == 422
    assert (
        await client.get(path, headers=headers, params={**period, "period_end": "2026-08-01"})
    ).status_code == 422
    mock_db.fetchall.assert_not_called()
    assert (await client.get(path, params=period)).status_code == 403
    response = await client.get(
        path,
        headers=headers,
        params={
            **period,
            "catalog": "it",
            "schema": "finance",
            "tables": ["it.finance.a", "it.finance.b"],
        },
    )
    assert response.status_code == 200
    assert response.json()["filters"]["tables"] == ["it.finance.a", "it.finance.b"]
    for call in mock_db.fetchall.call_args_list:
        assert "`catalog` = ?" in call.args[0]
        assert "`schema` = ?" in call.args[0]
        assert "it.finance.a" in call.args and "it.finance.b" in call.args


async def test_chart_missing_gold_remains_an_explicit_degraded_response(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchall.side_effect = RuntimeError(
        f"TABLE_OR_VIEW_NOT_FOUND: {GOLD_TABLE_POPULARITY_DAILY}"
    )
    response = await client.get(
        "/api/v1/uc-usage/charts/tables",
        headers={"x-dcm-platform-role": "super_admin"},
        params={"period_start": "2026-09-01", "period_end": "2026-09-02"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "degraded"
