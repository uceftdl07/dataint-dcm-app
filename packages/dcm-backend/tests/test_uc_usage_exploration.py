"""Execute exploration/filter SQL with real fixture aggregates and bound values."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from app.api.services.uc_usage_column_filters import TABLE_COLUMNS, compile_column_filters
from app.api.services.uc_usage_common import (
    GOLD_TABLE_CATALOG,
    GOLD_TABLE_DAILY,
    GOLD_TABLE_POPULARITY_DAILY,
)
from app.api.services.uc_usage_consumers import fetch_consumers
from app.api.services.uc_usage_exploration import (
    fetch_cost_changes,
    fetch_entity_detail,
    fetch_write_charts,
)

START, END = date(2026, 9, 1), date(2026, 9, 2)


class BoolOr:
    """SQLite has no ``BOOL_OR``; the lifecycle aggregate of spec 027 needs one."""

    def __init__(self) -> None:
        self.value = False

    def step(self, value: Any) -> None:
        self.value = self.value or bool(value)

    def finalize(self) -> bool:
        return self.value


class Database:
    def __init__(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.db.execute(f"""CREATE TABLE {GOLD_TABLE_DAILY} (
            cloud_provider TEXT, catalog TEXT, schema TEXT, table_full_name TEXT,
            period_start TEXT, consumer_id TEXT, consumer_name TEXT, consumer_type TEXT,
            request_count INTEGER, data_read_bytes REAL, data_written_bytes REAL,
            rows_written REAL, estimated_cost_usd REAL, last_used_at TEXT
        )""")
        self.db.execute(f"""CREATE VIEW {GOLD_TABLE_POPULARITY_DAILY} AS
            SELECT cloud_provider, catalog, schema, table_full_name, period_start,
                SUM(estimated_cost_usd) AS estimated_cost_usd
            FROM {GOLD_TABLE_DAILY}
            GROUP BY cloud_provider, catalog, schema, table_full_name, period_start""")
        # Deleted tables are excluded by anti-join on the catalogue, and the table
        # detail reads its lifecycle there: the fixture needs it even when empty.
        self.db.execute(f"""CREATE TABLE {GOLD_TABLE_CATALOG} (
            cloud_provider TEXT, table_full_name TEXT,
            is_deleted INTEGER, deleted_at TEXT, lifecycle_state TEXT
        )""")
        self.db.create_aggregate("BOOL_OR", 1, BoolOr)

    @staticmethod
    def table(name):
        return name

    def catalogue(
        self,
        *,
        table="main.sales.orders",
        cloud="aws",
        deleted=False,
        deleted_at="2026-09-02T00:00:00",
        lifecycle_state=None,
    ):
        self.db.execute(
            f"INSERT INTO {GOLD_TABLE_CATALOG} VALUES (?, ?, ?, ?, ?)",
            (
                cloud,
                table,
                1 if deleted else 0,
                deleted_at if deleted else None,
                lifecycle_state or ("DELETED" if deleted else "ACTIVE"),
            ),
        )

    def add(
        self,
        *,
        table="main.sales.orders",
        consumer="reader",
        day="2026-09-01",
        cloud="aws",
        reads=0,
        read_bytes=None,
        written=None,
        rows=None,
        cost=None,
    ):
        catalog, schema, _ = table.split(".", 2)
        self.db.execute(
            f"INSERT INTO {GOLD_TABLE_DAILY} VALUES ({','.join(['?'] * 14)})",
            (
                cloud,
                catalog,
                schema,
                table,
                day,
                consumer,
                consumer,
                "JOB",
                reads,
                read_bytes,
                written,
                rows,
                cost,
                day,
            ),
        )

    async def fetchall(self, sql, *params):
        self.calls.append((sql, params))
        values = [p.isoformat() if isinstance(p, date) else p for p in params]
        return [dict(row) for row in self.db.execute(sql, values)]

    async def fetchone(self, sql, *params):
        rows = await self.fetchall(sql, *params)
        return rows[0] if rows else None

    async def fetchscalar(self, sql, *params):
        rows = await self.fetchall(sql, *params)
        return next(iter(rows[0].values())) if rows else None


async def test_writes_include_write_only_tables_and_preserve_unknown_days():
    db = Database()
    db.add(written=200, rows=4, consumer="writer")
    db.add(written=100, rows=2, consumer="writer", cloud="azure")
    db.add(table="main.sales.reads", reads=100, read_bytes=500)
    db.add(table="other.sales.excluded", written=9999, rows=99)
    result = await fetch_write_charts(db, start=START, end=END, catalog="main")
    assert result["summary"] == {
        "data_written_bytes": 300,
        "rows_written": 6,
        "tables_with_writes": 2,
        "written_without_reads": 2,
    }
    assert result["daily"][0]["data_read_bytes"] == 500
    assert result["daily"][1]["data_written_bytes"] is None
    assert len(result["ranking"]) == 2
    assert result["ranking"][0]["key"] != result["ranking"][1]["key"]


async def test_observed_zero_writes_are_distinct_from_unknown_volume():
    db = Database()
    db.add(written=0, rows=0)
    result = await fetch_write_charts(db, start=START, end=END)
    assert result["summary"]["data_written_bytes"] == 0
    assert result["summary"]["tables_with_writes"] == 0
    db = Database()
    db.add(reads=5)
    result = await fetch_write_charts(db, start=START, end=END)
    assert result["summary"]["data_written_bytes"] is None


async def test_entity_detail_keeps_the_exact_id_period_and_table_scope():
    db = Database()
    identity = "reader/o'hara@example.com"
    db.add(consumer=identity, reads=5, written=100, rows=0.5, cost=2)
    db.add(consumer=identity, reads=7, day="2026-09-02", cost=3)
    db.add(consumer=identity, table="main.sales.excluded", reads=999, cost=999)
    db.add(consumer="someone-else", reads=888)
    result = await fetch_entity_detail(
        db,
        start=START,
        end=END,
        entity_kind="consumer",
        entity_id=identity,
        tables=["main.sales.orders"],
    )
    assert result["summary"]["request_count"] == 12
    assert result["summary"]["estimated_cost_usd"] == 5
    assert result["summary"]["counterpart_count"] == 1
    assert result["summary"]["rows_written"] == 0.5
    assert result["summary"]["active_days"] == 2
    assert result["summary"]["write_days"] == 1
    assert identity not in db.calls[0][0]
    assert identity in db.calls[0][1]
    empty = await fetch_entity_detail(
        db,
        start=START,
        end=END,
        entity_kind="table",
        entity_id="main.sales.orders",
        catalog="different",
    )
    assert empty["summary"]["observed_rows"] == 0
    assert empty["summary"]["estimated_cost_usd"] is None


async def test_consumer_filters_apply_after_period_sums_and_before_pagination():
    db = Database()
    for index in range(1, 41):
        for day in ("2026-09-01", "2026-09-02"):
            db.add(consumer=f"consumer-{index:02d}", reads=index, day=day, written=index * 10)
    result = await fetch_consumers(
        db,
        start=START,
        end=END,
        column_filter=["request_count:gte:60"],
        sort="requests",
        direction="asc",
        page=2,
        page_size=5,
    )
    assert result["total"] == 11
    assert [row["request_count"] for row in result["items"]] == [70, 72, 74, 76, 78]
    assert result["items"][0]["data_written_bytes"] == 700
    empty_page = await fetch_consumers(
        db, start=START, end=END, column_filter=["request_count:gte:60"], page=99, page_size=5
    )
    assert empty_page["total"] == 11 and empty_page["items"] == []


async def test_text_contains_is_literal_and_null_filters_do_not_match_zero():
    db = Database()
    db.add(consumer="100%_reader", written=0)
    db.add(consumer="100xyzreader")
    literal = await fetch_consumers(
        db, start=START, end=END, column_filter=["consumer_name:contains:%_"]
    )
    assert [row["consumer_id"] for row in literal["items"]] == ["100%_reader"]
    nulls = await fetch_consumers(
        db, start=START, end=END, column_filter=["data_written_bytes:isnull:"]
    )
    assert [row["consumer_id"] for row in nulls["items"]] == ["100xyzreader"]


@pytest.mark.parametrize(
    "value",
    [
        "unknown:gte:1",
        "request_count:contains:1",
        "request_count:gte:nan",
        "request_count:between:10,2",
        "request_count:eq:Infinity",
        "request_count:eq:1,2",
        "table_full_name:eq:",
        "request_count:isnull:0",
        "request_count;DROP:eq:1",
    ],
)
def test_column_filter_rejects_invalid_operators_values_and_identifiers(value):
    with pytest.raises(HTTPException) as error:
        compile_column_filters([value], TABLE_COLUMNS)
    assert error.value.status_code == 422


async def test_cost_changes_preserve_missing_costs_and_rank_absolute_changes():
    db = Database()
    db.add(table="main.sales.up", cost=20, day="2026-08-30")
    db.add(table="main.sales.up", cost=50)
    db.add(table="main.sales.down", cost=100, day="2026-08-31")
    db.add(table="main.sales.down", cost=20)
    db.add(table="main.sales.new", cost=5)
    db.add(table="main.sales.gap", cost=10, day="2026-08-31")
    result = await fetch_cost_changes(db, start=START, end=END, catalog="main")
    assert result["previous_period"] == {"start": "2026-08-30", "end": "2026-08-31"}
    assert [row["delta_usd"] for row in result["items"][:2]] == [-80, 30]
    by_name = {row["label"]: row for row in result["items"]}
    assert by_name["main.sales.new"]["delta_usd"] is None
    assert by_name["main.sales.gap"]["delta_usd"] is None
    assert result["current_total"] == 75 and result["previous_total"] == 130


@pytest.mark.parametrize("endpoint", ["charts/writes", "charts/cost-changes", "details"])
async def test_new_routes_keep_scope_authorization_and_required_period(
    client: AsyncClient, mock_db: AsyncMock, endpoint: str
) -> None:
    path = f"/api/v1/uc-usage/{endpoint}"
    params = {"entity_kind": "table", "entity_id": "main.sales.orders"}
    response = await client.get(path, headers={"x-dcm-platform-role": "super_admin"}, params=params)
    assert response.status_code == 422
    params.update(period_start="2026-09-01", period_end="2026-09-02")
    response = await client.get(path, headers={"x-dcm-workspace-ids": "1234"}, params=params)
    assert response.status_code == 403
    assert response.json()["detail"] == "unrestricted_scope_required"
    mock_db.fetchall.assert_not_called()
