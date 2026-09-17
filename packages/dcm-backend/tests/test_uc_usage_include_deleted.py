"""``include_deleted`` — the six acceptance criteria of spec 027.

Contract: ``specs/027-usage-table-deleted-flag/contracts/api-include-deleted.md``.
The filter applies **before** any aggregation, so the tests below check the SQL
that the aggregate reads, not only the shape of the response. Where SQLite can
run the query it runs it, on fixtures carrying one deleted table.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.api.services.uc_usage_common import (
    GOLD_RECOMMENDATIONS,
    GOLD_TABLE_CATALOG,
    GOLD_TABLE_DAILY,
    GOLD_TABLE_POPULARITY_DAILY,
    deleted_table_conditions,
    deleted_table_join,
    where_clause,
)
from app.api.services.uc_usage_governance import _recommendation_scope
from app.api.services.uc_usage_tables import fetch_tables
from app.main import app

_UNRESTRICTED = {"x-dcm-platform-role": "super_admin"}
_PERIOD = {"period_start": "2026-08-11", "period_end": "2026-09-10"}
_DELETED_AT = "2026-09-05T04:00:00"

# The exclusion is an anti-join on the catalogue, never a column of the facts:
# the daily MERGE would freeze the flag on the three days it rewrites (spec 027).
_ANTI_JOIN = "NOT IN (SELECT table_full_name FROM"
# Join variant, reserved for the recommendations filter, which has to nest the
# exclusion in a disjunction, where no subquery can be planned as an anti-join
# (SC-007): the join goes in the FROM and only a column test stays under the ``OR``.
_DELETED_CTE = "WITH deleted_tables AS (SELECT DISTINCT table_full_name FROM"
_DELETED_JOIN = "LEFT JOIN deleted_tables ON deleted_tables.table_full_name = rec.object_id"
_DELETED_TEST = (
    "(UPPER(rec.object_type) <> 'DATA_PRODUCT' OR deleted_tables.table_full_name IS NULL)"
)
_FLAG = "NOT COALESCE(is_deleted, false)"

# Routes exempt by contract: consumer grain, no table key to filter on.
_EXEMPT_PATHS = ["/api/v1/uc-usage/consumers", "/api/v1/uc-usage/charts/consumers"]
_IN_SCOPE_PATHS = [
    "/api/v1/uc-usage/filters/options",
    "/api/v1/uc-usage/overview",
    "/api/v1/uc-usage/tables",
    "/api/v1/uc-usage/tables/{table_full_name}/top-consumers",
    "/api/v1/uc-usage/details",
    "/api/v1/uc-usage/charts/tables",
    "/api/v1/uc-usage/charts/finops",
    "/api/v1/uc-usage/charts/writes",
    "/api/v1/uc-usage/charts/cost-changes",
    "/api/v1/uc-usage/finops/kpis",
    "/api/v1/uc-usage/finops/cost-by-table",
    "/api/v1/uc-usage/finops/trends",
    "/api/v1/uc-usage/attention",
    "/api/v1/uc-usage/recommendations",
    "/api/v1/uc-usage/recommendations/charts",
    "/api/v1/uc-usage/governance/kpis",
    "/api/v1/uc-usage/governance/charts",
    "/api/v1/uc-usage/governance/registry",
]


class TableDatabase:
    """Popularity/daily facts plus the catalogue, on the SQL subset SQLite shares.

    ``fetch_tables`` itself needs ``explode``/``MIN_BY``, which SQLite has not, so
    the counting queries below are the ones the service builds, executed here to
    check the predicate semantics rather than the string.
    """

    def __init__(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(f"""
            CREATE TABLE {GOLD_TABLE_DAILY} (
                cloud_provider TEXT, catalog TEXT, schema TEXT, table_full_name TEXT,
                period_start TEXT, consumer_id TEXT, request_count INTEGER,
                estimated_cost_usd REAL
            )
        """)
        self.connection.execute(f"""
            CREATE VIEW {GOLD_TABLE_POPULARITY_DAILY} AS
            SELECT cloud_provider, catalog, schema, table_full_name, period_start,
                SUM(request_count) AS request_count,
                SUM(estimated_cost_usd) AS estimated_cost_usd
            FROM {GOLD_TABLE_DAILY}
            GROUP BY cloud_provider, catalog, schema, table_full_name, period_start
        """)
        self.connection.execute(f"""
            CREATE TABLE {GOLD_TABLE_CATALOG} (
                cloud_provider TEXT, table_full_name TEXT,
                is_deleted INTEGER, deleted_at TEXT, lifecycle_state TEXT
            )
        """)
        # Only the three columns the shared recommendation filter reads.
        self.connection.execute(f"""
            CREATE TABLE {GOLD_RECOMMENDATIONS} (
                status TEXT, object_type TEXT, object_id TEXT
            )
        """)

    @staticmethod
    def table(name: str) -> str:
        return name

    def add(self, name: str, *, deleted: bool = False, cloud: str = "aws") -> None:
        full_name = f"it.finance.{name}"
        self.connection.execute(
            f"INSERT INTO {GOLD_TABLE_DAILY} VALUES (?, 'it', 'finance', ?, ?, 'job', 10, 1.5)",
            (cloud, full_name, "2026-09-01"),
        )
        self.connection.execute(
            f"INSERT INTO {GOLD_TABLE_CATALOG} VALUES (?, ?, ?, ?, ?)",
            (
                cloud,
                full_name,
                1 if deleted else 0,
                _DELETED_AT if deleted else None,
                "DELETED" if deleted else "ACTIVE",
            ),
        )

    def count(
        self,
        conditions: list[str],
        *,
        alias: str | None = None,
        cte: str = "",
        join: str = "",
    ) -> int:
        """``COUNT(DISTINCT table_full_name)``, optionally through a joined source.

        ``alias`` qualifies the counted column: joining the deleted-table CTE brings
        a second ``table_full_name`` into scope, which SQLite rejects as ambiguous.
        """
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        column = f"{alias}.table_full_name" if alias else "table_full_name"
        source = GOLD_TABLE_POPULARITY_DAILY + (f" AS {alias}" if alias else "")
        sql = f"{cte} SELECT COUNT(DISTINCT {column}) FROM {source} {join} {where}"
        return int(self.connection.execute(sql).fetchone()[0])

    def add_recommendation(self, object_type: str, object_id: str | None) -> None:
        self.connection.execute(
            f"INSERT INTO {GOLD_RECOMMENDATIONS} VALUES ('OPEN', ?, ?)",
            (object_type, object_id),
        )

    def count_recommendations(self, scope: Any) -> int:
        """Run the SQL :func:`_recommendation_scope` really builds, not a substring."""
        sql = f"{scope.cte} SELECT COUNT(*) FROM {scope.source} {where_clause(scope.conditions)}"
        return int(self.connection.execute(sql, scope.params).fetchone()[0])


def _naming_db() -> Any:
    """Only ``table()`` is reached — the predicate is built here, never executed."""
    return TableDatabase


def _table_row(**overrides: Any) -> dict[str, Any]:
    """One ``/tables`` row, lifecycle columns included as the contract requires."""
    row: dict[str, Any] = {
        "table_full_name": "it.finance.invoices",
        "catalog": "it",
        "schema": "finance",
        "table_name": "invoices",
        "table_type": "MANAGED",
        "request_count": 400,
        "request_count_prev": 200,
        "distinct_consumers": 7,
        "data_read_bytes": 2048,
        "estimated_cost_usd": 12.345,
        "cost_attribution_method": "equal_parts_fallback",
        "cost_basis": "warehouse_prorata",
        "catalog_resolution_status": "RESOLVED",
        "last_used_at": datetime(2026, 9, 9, 12, 0),
        "query_count": 100,
        "failed_count": 5,
        "failure_rate_pct": 5.0,
        "latency_p95_ms": 175.0,
        "freshness_lag_hours": 3.25,
        "freshness_basis": "lineage_write",
        "last_write_at": datetime(2026, 9, 9, 6, 0),
        "is_deleted": False,
        "deleted_at": None,
        "lifecycle_state": "ACTIVE",
    }
    row.update(overrides)
    return row


def _sql_of(mock: AsyncMock) -> str:
    return "\n".join(str(call.args[0]) for call in mock.call_args_list)


def _words(sql: str) -> list[str]:
    """Compare SQL on its tokens: only the indentation differs between callers."""
    return sql.split()


# --------------------------------------------------------------------------- #
# Criterion 3 — the pagination total moves by exactly the deleted table count
# --------------------------------------------------------------------------- #


@pytest.fixture
def table_db() -> Any:
    db = TableDatabase()
    yield db
    db.connection.close()


def test_the_exclusion_removes_exactly_the_deleted_tables(table_db: Any) -> None:
    for index in range(5):
        table_db.add(f"table_{index}", deleted=index in {1, 3})

    assert table_db.count(deleted_table_conditions(table_db, True)) == 5
    assert table_db.count(deleted_table_conditions(table_db, False)) == 3


def test_a_table_deleted_on_one_cloud_only_is_still_excluded(table_db: Any) -> None:
    """The filter reads like the flag the row carries: deleted on any cloud."""
    table_db.add("invoices", cloud="aws", deleted=True)
    table_db.add("invoices", cloud="azure", deleted=False)
    table_db.add("orders", cloud="aws")

    assert table_db.count(deleted_table_conditions(table_db, False)) == 1


async def test_the_pagination_total_and_the_page_read_the_same_filtered_anchor(
    mock_db: AsyncMock,
) -> None:
    """``COUNT(*)`` runs over the CTE chain, so both must carry the exclusion."""
    mock_db.fetchscalar.return_value = 1
    mock_db.fetchall.return_value = [_table_row()]

    await fetch_tables(mock_db, start=date(2026, 9, 1), end=date(2026, 9, 10))

    count_sql = mock_db.fetchscalar.call_args.args[0]
    page_sql = mock_db.fetchall.call_args.args[0]
    assert _ANTI_JOIN in count_sql
    # Same CTE chain word for word: the total cannot count a row the page hides.
    assert _words(count_sql.split("SELECT COUNT(*)")[0]) == _words(
        page_sql.split("SELECT * FROM usage_rows")[0]
    )

    mock_db.reset_mock()
    mock_db.fetchscalar.return_value = 1
    mock_db.fetchall.return_value = [_table_row()]
    await fetch_tables(mock_db, start=date(2026, 9, 1), end=date(2026, 9, 10), include_deleted=True)
    assert _ANTI_JOIN not in mock_db.fetchscalar.call_args.args[0]


# --------------------------------------------------------------------------- #
# Criteria 1 and 2 — hidden by default, returned with their deletion date
# --------------------------------------------------------------------------- #


async def test_tables_rows_always_carry_the_three_lifecycle_fields(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchscalar.return_value = 1
    mock_db.fetchall.return_value = [
        _table_row(
            is_deleted=True,
            deleted_at=datetime(2026, 9, 5, 4, 0),
            lifecycle_state="DELETED",
        )
    ]

    resp = await client.get(
        "/api/v1/uc-usage/tables",
        headers=_UNRESTRICTED,
        params={**_PERIOD, "include_deleted": "true"},
    )

    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["is_deleted"] is True
    assert item["deleted_at"] == _DELETED_AT
    assert item["lifecycle_state"] == "DELETED"
    assert _ANTI_JOIN not in _sql_of(mock_db.fetchall)


async def test_a_live_row_reports_a_non_null_flag_and_no_deletion_date(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchscalar.return_value = 1
    mock_db.fetchall.return_value = [_table_row(is_deleted=None, lifecycle_state=None)]

    resp = await client.get("/api/v1/uc-usage/tables", headers=_UNRESTRICTED, params=_PERIOD)

    assert resp.status_code == 200
    item = resp.json()["items"][0]
    # ``is_deleted`` is never NULL in the response, even from an unresolved row.
    assert item["is_deleted"] is False
    assert item["deleted_at"] is None
    assert item["lifecycle_state"] == "UNKNOWN"
    assert _ANTI_JOIN in _sql_of(mock_db.fetchall)


# --------------------------------------------------------------------------- #
# Criterion 4 — no KPI counts a table its list does not show
# --------------------------------------------------------------------------- #


async def test_overview_kpis_exclude_deleted_tables_before_aggregating(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    resp = await client.get("/api/v1/uc-usage/overview", headers=_UNRESTRICTED, params=_PERIOD)

    assert resp.status_code == 200
    # Totals, reach, failure rate: every aggregate of the page, not just the list.
    assert _sql_of(mock_db.fetchone).count(_ANTI_JOIN) >= 4
    # ``unused_tables`` reads ``table_governance``, which carries the flag itself.
    assert _FLAG in _sql_of(mock_db.fetchscalar)


async def test_governance_kpis_and_registry_share_one_denominator(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    kpis = await client.get("/api/v1/uc-usage/governance/kpis", headers=_UNRESTRICTED)
    assert kpis.status_code == 200
    assert _FLAG in _sql_of(mock_db.fetchone)

    mock_db.reset_mock()
    registry = await client.get("/api/v1/uc-usage/governance/registry", headers=_UNRESTRICTED)
    assert registry.status_code == 200
    assert _FLAG in _sql_of(mock_db.fetchscalar)

    mock_db.reset_mock()
    included = await client.get(
        "/api/v1/uc-usage/governance/kpis",
        headers=_UNRESTRICTED,
        params={"include_deleted": "true"},
    )
    assert included.status_code == 200
    assert _FLAG not in _sql_of(mock_db.fetchone)


# --------------------------------------------------------------------------- #
# Criterion 5 — recommendations drop deleted tables, never their consumer rows
# --------------------------------------------------------------------------- #


async def test_recommendations_narrow_data_products_only(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchscalar.return_value = 0

    resp = await client.get("/api/v1/uc-usage/recommendations", headers=_UNRESTRICTED)

    assert resp.status_code == 200
    sql = _sql_of(mock_db.fetchall)
    # A CONSUMER recommendation carries an identity in ``object_id``, not a table:
    # the exclusion must not reach it.
    assert _DELETED_TEST in sql
    assert _DELETED_JOIN in sql


async def test_the_recommendation_exclusion_never_nests_a_subquery(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """Under the ``DATA_PRODUCT`` disjunction, any subquery is unaffordable.

    A subquery under an ``OR`` cannot be planned as an anti-join — both branches must
    stay evaluable per row — so it is run against every deleted name of the catalogue,
    for every candidate row. A correlated ``NOT EXISTS`` in that position is planned
    the same way. The endpoint issues three of these queries in sequence and the client
    aborts at ``API_REQUEST_TIMEOUT_MS``, so both subquery forms miss the budget of
    SC-007 while the join form holds it.

    Their absence is the whole point of the join form, so it is asserted rather than
    assumed: reverting to either would pass every other test in this file.
    """
    mock_db.fetchscalar.return_value = 0

    resp = await client.get(
        "/api/v1/uc-usage/recommendations", headers=_UNRESTRICTED, params={"catalog": "it"}
    )

    assert resp.status_code == 200
    for mock in (mock_db.fetchall, mock_db.fetchone, mock_db.fetchscalar):
        sql = _sql_of(mock)
        assert _ANTI_JOIN not in sql
        assert "NOT EXISTS" not in sql
        # All three queries, counters included: a total that reads a different
        # source than its page would disagree with it.
        assert _DELETED_CTE in sql
        assert _DELETED_JOIN in sql

    # The attention block shares the filter, so it shared the regression.
    mock_db.reset_mock()
    resp = await client.get(
        "/api/v1/uc-usage/attention", headers=_UNRESTRICTED, params={"catalog": "it"}
    )
    assert resp.status_code == 200
    sql = _sql_of(mock_db.fetchall)
    assert _ANTI_JOIN not in sql
    assert "NOT EXISTS" not in sql
    assert _DELETED_JOIN in sql


def test_the_join_form_refuses_an_unqualified_column() -> None:
    """Unqualified, the outer column would resolve against the CTE itself.

    ``deleted_tables.table_full_name = table_full_name`` is a tautology: the join
    would match every deleted row and the ``IS NULL`` test would then exclude the
    whole table, in silence. Raising is the only safe answer.
    """
    with pytest.raises(ValueError, match="qualified by the outer alias"):
        deleted_table_join(_naming_db(), False, column="object_id")

    # Nothing to splice when the caller asked to keep the deleted tables: the query
    # must come out exactly as it would without the feature.
    kept = deleted_table_join(_naming_db(), True, column="rec.object_id")
    assert (kept.cte, kept.join, kept.conditions) == ("", "", [])


def test_both_forms_of_the_exclusion_keep_the_same_rows(table_db: Any) -> None:
    """The join rewrite is a plan change, not a semantic one.

    Executed on SQLite — which runs both shapes — over the same fixture: one deleted
    table and one live one.
    """
    table_db.add("invoices", deleted=True)
    table_db.add("orders")

    not_in = deleted_table_conditions(table_db, False)
    join = deleted_table_join(table_db, False, column="pop.table_full_name")

    assert (
        table_db.count(not_in)
        == table_db.count(join.conditions, alias="pop", cte=join.cte, join=join.join)
        == 1
    )


def test_the_recommendation_filter_runs_as_generated_on_the_four_shapes_that_matter(
    table_db: Any,
) -> None:
    """The generated SQL, executed — the coverage gap that let T004's regression ship.

    Every other test here matches substrings against an ``AsyncMock``, so nothing
    caught that the shipped predicate was 80 s slow, and nothing would catch a wrong
    join either. This one runs what the service builds, over rows chosen for the four
    behaviours the form has to get right.
    """
    # Deleted on two clouds: the catalogue holds one row per (cloud, table), so the
    # CTE's DISTINCT is what stops the join from duplicating a matching row.
    table_db.add("invoices", cloud="aws", deleted=True)
    table_db.add("invoices", cloud="azure", deleted=True)
    table_db.add("orders")

    table_db.add_recommendation("DATA_PRODUCT", "it.finance.invoices")  # excluded
    table_db.add_recommendation("DATA_PRODUCT", "it.finance.orders")  # kept, live
    # A consumer identity that happens to read like the deleted table: kept by the
    # first branch of the disjunction, and kept **once** — this is the fan-out guard.
    table_db.add_recommendation("CONSUMER", "it.finance.invoices")
    # No name, no deleted table. The null-aware ``NOT IN`` used to drop this row.
    table_db.add_recommendation("DATA_PRODUCT", None)

    scope = _recommendation_scope(
        table_db, catalog=None, schema=None, tables=None, category=None, object_type=None
    )
    assert table_db.count_recommendations(scope) == 3

    included = _recommendation_scope(
        table_db,
        catalog=None,
        schema=None,
        tables=None,
        category=None,
        object_type=None,
        include_deleted=True,
    )
    assert table_db.count_recommendations(included) == 4


async def test_the_two_consumer_grain_routes_ignore_the_flag(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    for path in _EXEMPT_PATHS:
        mock_db.reset_mock()
        mock_db.fetchscalar.return_value = 0
        resp = await client.get(
            path, headers=_UNRESTRICTED, params={**_PERIOD, "include_deleted": "true"}
        )
        assert resp.status_code == 200, path
        assert _ANTI_JOIN not in _sql_of(mock_db.fetchall), path


# --------------------------------------------------------------------------- #
# Criterion 6 — the parameter is documented where it applies, and only there
# --------------------------------------------------------------------------- #


def test_openapi_documents_the_parameter_on_the_in_scope_routes_only() -> None:
    paths = app.openapi()["paths"]

    for path in _IN_SCOPE_PATHS:
        parameters = paths[path]["get"]["parameters"]
        declared = {parameter["name"]: parameter for parameter in parameters}
        assert "include_deleted" in declared, path
        assert declared["include_deleted"]["schema"]["default"] is False, path
        assert declared["include_deleted"]["schema"]["type"] == "boolean", path

    for path in _EXEMPT_PATHS:
        names = {parameter["name"] for parameter in paths[path]["get"]["parameters"]}
        assert "include_deleted" not in names, path
