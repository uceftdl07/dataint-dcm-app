"""Tests for the ``/api/v1/uc-usage`` router.

The gold tables carry no scope column, so the whole router is reserved for
unrestricted callers: every request below sends the header that grants it, and
one test checks a project-scoped caller is refused.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from unittest.mock import AsyncMock

from httpx import AsyncClient

_UNRESTRICTED = {"x-dcm-platform-role": "super_admin"}
_PERIOD = {"period_start": "2026-08-11", "period_end": "2026-09-10"}


def _table_row(**overrides: Any) -> dict[str, Any]:
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
    }
    row.update(overrides)
    return row


def _recommendation_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "recommendation_id": "rec-1",
        "cloud_provider": "azure",
        "object_type": "DATA_PRODUCT",
        "object_id": "it.finance.invoices",
        "object_name": "invoices",
        "category": "LIFECYCLE",
        "mode": "REACTIVE",
        "title": "Table inutilisée",
        "detail": "Aucune lecture depuis 120 jours",
        "recommended_action": "archiver",
        "estimated_savings_usd": 4.2,
        "severity": "HIGH",
        "personas": ["OWN", "FIN"],
        "status": "OPEN",
        "first_seen_date": date(2026, 6, 1),
        "last_seen_date": date(2026, 9, 10),
        "age_days": 101,
    }
    row.update(overrides)
    return row


async def test_period_is_required_on_dated_endpoints(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/uc-usage/tables", headers=_UNRESTRICTED)

    assert resp.status_code == 422


async def test_inverted_period_is_refused(client: AsyncClient, mock_db: AsyncMock) -> None:
    resp = await client.get(
        "/api/v1/uc-usage/tables",
        headers=_UNRESTRICTED,
        params={"period_start": "2026-09-10", "period_end": "2026-08-11"},
    )

    assert resp.status_code == 422
    mock_db.fetchall.assert_not_called()


async def test_project_scoped_caller_is_refused(client: AsyncClient, mock_db: AsyncMock) -> None:
    resp = await client.get(
        "/api/v1/uc-usage/governance/kpis",
        headers={"x-dcm-workspace-ids": "1234", "x-dcm-lz-ids": "lz-a"},
    )

    assert resp.status_code == 403
    assert resp.json()["detail"] == "unrestricted_scope_required"
    mock_db.fetchone.assert_not_called()


async def test_missing_gold_table_degrades_to_503(client: AsyncClient, mock_db: AsyncMock) -> None:
    mock_db.fetchone.side_effect = RuntimeError(
        "[TABLE_OR_VIEW_NOT_FOUND] gold_dbx_usage_table_popularity_daily is not found"
    )

    resp = await client.get("/api/v1/uc-usage/overview", headers=_UNRESTRICTED, params=_PERIOD)

    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert detail["code"] == "gold_dbx_usage_table_popularity_daily_missing"
    assert detail["status"] == "degraded"


async def test_overview_keeps_nulls_and_omits_absent_forecast(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.side_effect = [
        {"request_count": 1000, "estimated_cost_usd": None},
        {"request_count": 800, "estimated_cost_usd": None},
        {"tracked_tables": 12, "distinct_consumers": 30},
        {"failed_count": 5, "query_count": 200},
    ]
    mock_db.fetchscalar.return_value = 4
    mock_db.fetchall.side_effect = [
        [
            {
                "metric_name": "request_count",
                "horizon_date": date(2026, 9, 11),
                "predicted_value": 120.0,
                "lower_bound": 100.0,
                "upper_bound": 140.0,
            }
        ],
        [{"period_start": date(2026, 9, 9), "data_written_bytes": None}],
        [_recommendation_row()],
    ]

    resp = await client.get("/api/v1/uc-usage/overview", headers=_UNRESTRICTED, params=_PERIOD)

    assert resp.status_code == 200
    body = resp.json()
    assert body["request_count"] == 1000
    assert body["request_count_delta_pct"] == 25.0
    assert body["distinct_consumers"] == 30
    # NULL cost is a fact about attribution, not a zero (SC-005).
    assert body["estimated_cost_usd"] is None
    assert body["estimated_cost_usd_delta_pct"] is None
    assert body["unused_tables"] == 4
    assert body["access_failure_rate_pct"] == 2.5
    assert body["written_bytes_series"][0]["data_written_bytes"] is None
    # Only the metric with forecast rows is present — no zeroed series.
    assert [series["metric_name"] for series in body["trends"]] == ["request_count"]
    assert body["attention"] == []
    assert mock_db.fetchall.call_count == 2
    assert body["period"] == {"start": "2026-08-11", "end": "2026-09-10"}


async def test_tables_page_exposes_period_p95(client: AsyncClient, mock_db: AsyncMock) -> None:
    mock_db.fetchscalar.return_value = 1
    mock_db.fetchall.return_value = [_table_row()]

    resp = await client.get(
        "/api/v1/uc-usage/tables",
        headers=_UNRESTRICTED,
        params={**_PERIOD, "page_size": 10},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 10
    assert body["period"] == {"start": "2026-08-11", "end": "2026-09-10"}
    item = body["items"][0]
    assert item["request_delta_pct"] == 100.0
    assert item["failure_rate_pct"] == 5.0
    assert item["latency_p95_ms"] == 175.0
    assert item["cost_attribution_method"] == "equal_parts_fallback"

    listing_sql = mock_db.fetchall.call_args.args[0]
    assert "ORDER BY `request_count` DESC NULLS LAST" in listing_sql
    # The P95 is interpolated in SQL over the summed buckets, so the warehouse
    # ranks and slices the page — never Python.
    assert "explode(latency_bucket_counts)" in listing_sql
    assert "LIMIT ? OFFSET ?" in listing_sql


async def test_tables_sorted_by_latency_stays_one_paginated_query(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchscalar.return_value = 1
    mock_db.fetchall.return_value = [_table_row()]

    resp = await client.get(
        "/api/v1/uc-usage/tables",
        headers=_UNRESTRICTED,
        params={**_PERIOD, "sort": "latency"},
    )

    assert resp.status_code == 200
    assert mock_db.fetchall.call_count == 1
    assert "ORDER BY `latency_p95_ms` DESC NULLS LAST" in mock_db.fetchall.call_args.args[0]


async def test_tables_keep_latency_null_when_nothing_was_measured(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchscalar.return_value = 1
    mock_db.fetchall.return_value = [_table_row(latency_p95_ms=None)]

    resp = await client.get("/api/v1/uc-usage/tables", headers=_UNRESTRICTED, params=_PERIOD)

    assert resp.status_code == 200
    assert resp.json()["items"][0]["latency_p95_ms"] is None


async def test_tables_push_the_catalogue_filter_into_the_registry_cte(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """``table_catalog`` is filtered inside its CTE, not scanned whole then joined."""
    mock_db.fetchscalar.return_value = 0
    mock_db.fetchall.return_value = []

    resp = await client.get(
        "/api/v1/uc-usage/tables",
        headers=_UNRESTRICTED,
        params={**_PERIOD, "catalog": "it"},
    )

    assert resp.status_code == 200
    args = mock_db.fetchall.call_args.args
    catalogue_cte = args[0].split("cat AS (")[1].split("),")[0]
    assert "`catalog` = ?" in catalogue_cte
    # pop, prev, cons, perf, cat (snapshot — no dates), latency chain, then LIMIT/OFFSET.
    assert args[1:] == (
        date(2026, 8, 11),
        date(2026, 9, 10),
        "it",
        date(2026, 7, 11),
        date(2026, 8, 10),
        "it",
        date(2026, 8, 11),
        date(2026, 9, 10),
        "it",
        date(2026, 8, 11),
        date(2026, 9, 10),
        "it",
        "it",
        date(2026, 8, 11),
        date(2026, 9, 10),
        "it",
        25,
        0,
    )


async def test_tables_rejects_unknown_sort(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/uc-usage/tables",
        headers=_UNRESTRICTED,
        params={**_PERIOD, "sort": "alphabetical"},
    )

    assert resp.status_code == 422


async def test_page_size_over_the_cap_is_refused(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/uc-usage/consumers",
        headers=_UNRESTRICTED,
        params={**_PERIOD, "page_size": 500},
    )

    assert resp.status_code == 422


async def test_top_consumers_is_capped_at_five(client: AsyncClient, mock_db: AsyncMock) -> None:
    mock_db.fetchall.return_value = [
        {
            "consumer_id": "svc-a",
            "consumer_name": "svc-a",
            "consumer_type": "SOMETHING_NEW",
            "request_count": 10,
            "estimated_cost_usd": None,
            "last_used_at": datetime(2026, 9, 9, 8, 0),
        }
    ]

    resp = await client.get(
        "/api/v1/uc-usage/tables/it.finance.invoices/top-consumers",
        headers=_UNRESTRICTED,
        params=_PERIOD,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["table_full_name"] == "it.finance.invoices"
    assert body["items"][0]["rank"] == 1
    # Open vocabulary: an unseen consumer type is returned, never masked.
    assert body["items"][0]["consumer_type"] == "SOMETHING_NEW"
    assert body["items"][0]["estimated_cost_usd"] is None
    assert mock_db.fetchall.call_args.args[-1] == 5


async def test_consumers_recompute_rank_and_distinct_tables(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchscalar.return_value = 2
    mock_db.fetchall.return_value = [
        {
            "consumer_id": "svc-a",
            "consumer_name": "svc-a",
            "consumer_type": "SERVICE_PRINCIPAL",
            "distinct_tables": 3,
            "request_count": 90,
            "data_read_bytes": 1024,
            "estimated_cost_usd": 9.5,
            "last_used_at": datetime(2026, 9, 9, 8, 0),
            "cost_rank": 1,
        }
    ]

    resp = await client.get("/api/v1/uc-usage/consumers", headers=_UNRESTRICTED, params=_PERIOD)

    assert resp.status_code == 200
    assert resp.json()["items"][0]["rank"] == 1
    sql = mock_db.fetchall.call_args.args[0]
    assert "consumer_rank" not in sql
    assert "COUNT(DISTINCT table_full_name)" in sql


async def test_finops_kpis_flag_the_lower_bound(client: AsyncClient, mock_db: AsyncMock) -> None:
    mock_db.fetchone.side_effect = [
        {"total_cost_usd": 50.0, "request_count": 1000, "costed_tables": 4},
        {"table_full_name": "it.finance.invoices", "estimated_cost_usd": 30.0},
    ]

    resp = await client.get("/api/v1/uc-usage/finops/kpis", headers=_UNRESTRICTED, params=_PERIOD)

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_cost_usd"] == 50.0
    assert body["avg_cost_per_request_usd"] == 0.05
    assert body["is_lower_bound"] is True
    assert body["top_costly_table"]["table_full_name"] == "it.finance.invoices"


def _cost_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "table_full_name": "it.finance.invoices",
        "estimated_cost_usd": 20.0,
        "request_count": 400,
        "data_read_bytes": 2048,
        "cost_per_request_usd": 0.05,
        "forecast_cost_usd_7d": None,
    }
    row.update(overrides)
    return row


async def test_cost_by_table_keeps_missing_forecast_null(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchscalar.return_value = 1
    mock_db.fetchall.return_value = [_cost_row()]

    resp = await client.get(
        "/api/v1/uc-usage/finops/cost-by-table", headers=_UNRESTRICTED, params=_PERIOD
    )

    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["forecast_cost_usd_7d"] is None
    assert item["cost_per_request_usd"] == 0.05
    # Derived in SQL, so the column can be sorted and filtered like any other.
    assert "AS cost_per_request_usd" in mock_db.fetchall.call_args.args[0]


async def test_cost_by_table_sorts_and_filters_on_a_derived_column(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """The two computed columns are first-class: server-side sort and filter, one query."""
    mock_db.fetchscalar.return_value = 1
    mock_db.fetchall.return_value = [_cost_row()]

    resp = await client.get(
        "/api/v1/uc-usage/finops/cost-by-table",
        headers=_UNRESTRICTED,
        params={
            **_PERIOD,
            "sort": "cost_per_request",
            "direction": "asc",
            "column_filter": ["forecast_cost_usd_7d:gte:10"],
        },
    )

    assert resp.status_code == 200
    assert mock_db.fetchall.call_count == 1
    sql, *bound = mock_db.fetchall.call_args.args
    assert "ORDER BY `cost_per_request_usd` ASC NULLS LAST, table_full_name ASC" in sql
    assert "FROM joined WHERE `forecast_cost_usd_7d` >= ?" in sql
    # Period, the forecast metric, then the filter value, then the page window.
    assert tuple(bound) == (date(2026, 8, 11), date(2026, 9, 10), "estimated_cost_usd", 10.0, 25, 0)


async def test_cost_by_table_counts_the_filtered_set_not_every_table(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """Counting the unfiltered fact table would advertise pages that render empty."""
    mock_db.fetchscalar.return_value = 0
    mock_db.fetchall.return_value = []

    resp = await client.get(
        "/api/v1/uc-usage/finops/cost-by-table",
        headers=_UNRESTRICTED,
        params={**_PERIOD, "column_filter": ["estimated_cost_usd:gte:1000"]},
    )

    assert resp.status_code == 200
    count_sql = mock_db.fetchscalar.call_args.args[0]
    assert "SELECT COUNT(*) FROM joined WHERE `estimated_cost_usd` >= ?" in count_sql
    assert 1000.0 in mock_db.fetchscalar.call_args.args[1:]


async def test_cost_by_table_searches_on_the_table_name(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """The page's search box is shared, so this table has to honour it too."""
    mock_db.fetchscalar.return_value = 1
    mock_db.fetchall.return_value = [_cost_row()]

    resp = await client.get(
        "/api/v1/uc-usage/finops/cost-by-table",
        headers=_UNRESTRICTED,
        params={**_PERIOD, "search": "Invoices"},
    )

    assert resp.status_code == 200
    sql, *bound = mock_db.fetchall.call_args.args
    assert "LOWER(table_full_name) LIKE ?" in sql
    assert "%invoices%" in bound


async def test_cost_by_table_rejects_unknown_sort_and_filter_column(client: AsyncClient) -> None:
    unknown_sort = await client.get(
        "/api/v1/uc-usage/finops/cost-by-table",
        headers=_UNRESTRICTED,
        params={**_PERIOD, "sort": "alphabetical"},
    )
    unknown_column = await client.get(
        "/api/v1/uc-usage/finops/cost-by-table",
        headers=_UNRESTRICTED,
        params={**_PERIOD, "column_filter": ["consumer_name:eq:svc-a"]},
    )

    assert unknown_sort.status_code == 422
    assert unknown_column.status_code == 422


async def test_governance_registry_keeps_owner_null(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchscalar.return_value = 1
    mock_db.fetchall.return_value = [
        {
            "table_full_name": "it.finance.invoices",
            "catalog": "it",
            "schema": "finance",
            "table_name": "invoices",
            "table_type": "MANAGED",
            "owner": None,
            "last_operation": "updateTables",
            "last_operation_at": datetime(2026, 9, 1, 9, 0),
            "last_operation_by": "someone@example.com",
            "downstream_fanout": 7,
            "days_since_last_read": 120,
            "is_unused": True,
            "is_orphan": True,
            "is_stale_but_consumed": False,
            "is_critical": True,
            "recommended_action": "archiver",
            "severity": "high",
        }
    ]

    resp = await client.get("/api/v1/uc-usage/governance/registry", headers=_UNRESTRICTED)

    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["owner"] is None
    assert item["severity"] == "high"
    assert item["recommended_action"] == "archiver"


async def test_recommendations_force_open_and_keep_counts_unfiltered(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.return_value = {
        "open_high": 3,
        "open_medium": 2,
        "open_total": 6,
        "estimated_savings_usd": 12.0,
    }
    mock_db.fetchscalar.return_value = 3
    mock_db.fetchall.return_value = [_recommendation_row()]

    resp = await client.get(
        "/api/v1/uc-usage/recommendations",
        headers=_UNRESTRICTED,
        params={"severity": "HIGH", "catalog": "it"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["counts"] == {
        "open_high": 3,
        "open_medium": 2,
        "open_total": 6,
        "estimated_savings_usd": 12.0,
    }
    assert body["items"][0]["personas"] == ["OWN", "FIN"]

    counts_sql = mock_db.fetchone.call_args.args[0]
    # Qualified by ``rec``: the deleted-table exclusion is a LEFT JOIN, so this
    # query's FROM carries an alias to join against (SC-007).
    assert "UPPER(rec.status) = 'OPEN'" in counts_sql
    # The severity filter narrows the list, never the High/Medium counters.
    assert "UPPER(severity) = ?" not in counts_sql
    # A catalogue filter only narrows DATA_PRODUCT rows (FR-011).
    assert "UPPER(rec.object_type) <> 'DATA_PRODUCT'" in counts_sql

    listing_sql = mock_db.fetchall.call_args.args[0]
    assert "UPPER(severity) = ?" in listing_sql


async def test_forecast_trends_reject_an_unknown_metric(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/uc-usage/finops/trends",
        headers=_UNRESTRICTED,
        params={"metrics": "rows_written"},
    )

    assert resp.status_code == 422


async def test_trends_ignore_the_horizons_left_by_previous_runs(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """``forecast_daily`` est écrite en MERGE : les horizons périmés y restent."""
    mock_db.fetchall.return_value = []

    resp = await client.get("/api/v1/uc-usage/finops/trends", headers=_UNRESTRICTED)

    assert resp.status_code == 200
    sql = mock_db.fetchall.call_args.args[0]
    assert "horizon_date >= current_date()" in sql
    # Borné des DEUX côtés : « +7d » annonce sept jours, pas tout le futur présent
    # en table.
    assert "horizon_date < date_add(current_date(), 7)" in sql


async def test_trends_return_the_observed_series_before_the_forecast(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchall.side_effect = [
        [
            {
                "metric_name": "request_count",
                "horizon_date": date(2026, 9, 12),
                "predicted_value": 120.0,
                "lower_bound": 100.0,
                "upper_bound": 140.0,
            }
        ],
        [
            {
                "period_start": date(2026, 9, 10),
                "request_count": 90,
                "distinct_consumers": 4,
                "estimated_cost_usd": 1.5,
                "data_read_bytes": None,
            }
        ],
    ]

    resp = await client.get(
        "/api/v1/uc-usage/finops/trends",
        headers=_UNRESTRICTED,
        params={**_PERIOD, "metrics": "request_count"},
    )

    assert resp.status_code == 200
    series = resp.json()["series"]
    assert len(series) == 1
    observed = series[0]["observed"]
    # Un point par jour de la période (2026-08-11 → 2026-09-10), pas un point par
    # ligne trouvée : refermer les trous ferait lire une activité continue là où
    # la table n'a pas été lue.
    assert len(observed) == 31
    assert observed[0] == {"period_start": "2026-08-11", "value": None}
    assert observed[-1] == {"period_start": "2026-09-10", "value": 90}
    assert series[0]["points"][0]["horizon_date"] == "2026-09-12"

    observed_sql = mock_db.fetchall.call_args_list[1].args[0]
    assert "GROUP BY period_start" in observed_sql
    # Le réalisé est borné par la période, jamais par l'horizon de prévision.
    assert "horizon_date" not in observed_sql
    # Le jour en cours n'est chargé qu'en partie : le tracer donnerait à lire un
    # effondrement là où il n'y a qu'une journée inachevée.
    assert "period_start < current_date()" in observed_sql


async def test_trends_without_a_period_return_the_forecast_only(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchall.return_value = [
        {
            "metric_name": "request_count",
            "horizon_date": date(2026, 9, 12),
            "predicted_value": 120.0,
            "lower_bound": None,
            "upper_bound": None,
        }
    ]

    resp = await client.get("/api/v1/uc-usage/finops/trends", headers=_UNRESTRICTED)

    assert resp.status_code == 200
    assert resp.json()["series"][0]["observed"] == []
    assert mock_db.fetchall.call_count == 1


async def test_filter_options_deduplicate_tables_and_narrow_schemas(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchall.side_effect = [
        [{"value": "it"}, {"value": "sales"}],
        [{"value": "finance"}],
        [
            {
                "table_full_name": "it.finance.invoices",
                "catalog": "it",
                "schema": "finance",
                "is_deleted": False,
                "deleted_at": None,
                "lifecycle_state": "ACTIVE",
            }
        ],
    ]

    resp = await client.get(
        "/api/v1/uc-usage/filters/options",
        headers=_UNRESTRICTED,
        params={"catalog": "it"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["catalogs"] == ["it", "sales"]
    assert body["schemas"] == ["finance"]
    assert body["tables"] == [
        {
            "table_full_name": "it.finance.invoices",
            "catalog": "it",
            "schema": "finance",
            "is_deleted": False,
            "deleted_at": None,
            "lifecycle_state": "ACTIVE",
        }
    ]
    assert body["truncated"] is False

    # Le catalogue choisi resserre schémas et tables, jamais la liste des catalogues.
    catalogs_sql, *catalogs_params = mock_db.fetchall.call_args_list[0].args
    assert "`catalog` = ?" not in catalogs_sql
    assert catalogs_params == [500]
    assert "`catalog` = ?" in mock_db.fetchall.call_args_list[1].args[0]
    tables_sql = mock_db.fetchall.call_args_list[2].args[0]
    assert "GROUP BY table_full_name" in tables_sql
