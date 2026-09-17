"""Snapshot chart contracts, full-scope aggregates and paginated drill-downs."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

HEADERS = {"x-dcm-platform-role": "super_admin"}


async def test_governance_charts_keep_full_scope_and_bound_only_detail(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.return_value = {
        "tracked_tables": 412,
        "unused_tables": 46,
        "schema_count": 31,
        "inactivity_unobserved": 7,
        "owner_present": 300,
        "owner_missing": 112,
        "classification_unknown": 2,
        "scatter_total": 405,
        "as_of": datetime(2026, 9, 12, 9),
    }
    mock_db.fetchall.side_effect = [
        [{"catalog": "main", "schema": "sales", "tracked_tables": 12, "unused_tables": 4}],
        [],
    ]
    response = await client.get(
        "/api/v1/uc-usage/governance/charts",
        headers=HEADERS,
        params={"catalog": "main", "schema": "sales", "tables": "main.sales.orders"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["tracked_tables"] == 412
    assert body["matrix"]["total_rows"] == 31
    assert body["matrix"]["rows"][0]["signals"]["unused"] == 4
    assert body["scatter"] == {"total": 405, "limit": 300, "unobserved_reads": 7, "points": []}
    assert body["tag_coverage"][0]["coverage_pct"] == 72.82
    assert body["tag_coverage"][3]["unknown_count"] == 2
    for call in [mock_db.fetchone.call_args, *mock_db.fetchall.call_args_list]:
        sql, *params = call.args
        assert "period_start" not in sql
        assert "cat.cloud_provider = gov.cloud_provider" in sql
        assert params[:6] == ["main", "sales", "main.sales.orders"] * 2
        assert sql.count("?") == len(params)
        assert "main.sales.orders" not in sql
    assert "LIMIT" not in mock_db.fetchone.call_args.args[0]
    assert mock_db.fetchall.call_args_list[0].args[-1] == 25
    assert mock_db.fetchall.call_args_list[1].args[-1] == 300


async def test_single_schema_matrix_uses_tables_and_keeps_cloud_identity(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.return_value = {"schema_count": 1, "tracked_tables": 4}
    response = await client.get("/api/v1/uc-usage/governance/charts", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["matrix"]["mode"] == "table"
    assert response.json()["matrix"]["total_rows"] == 4
    sql = mock_db.fetchall.call_args_list[0].args[0]
    assert "GROUP BY `catalog`, `schema`, cloud_provider, table_full_name, table_name" in sql


async def test_empty_chart_scope_is_zero_counts_but_unknown_coverage_and_cost(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    governance = await client.get("/api/v1/uc-usage/governance/charts", headers=HEADERS)
    assert governance.status_code == 200
    assert governance.json()["summary"]["tracked_tables"] == 0
    assert governance.json()["tag_coverage"][0]["coverage_pct"] is None
    assert governance.json()["scatter"]["points"] == []
    recommendations = await client.get("/api/v1/uc-usage/recommendations/charts", headers=HEADERS)
    assert recommendations.status_code == 200
    assert recommendations.json()["summary"]["reference_cost_usd"] is None
    assert recommendations.json()["summary"]["open_total"] == 0
    assert recommendations.json()["priorities"] == []


async def test_unavailable_classification_is_not_reported_as_zero_coverage(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.return_value = {"tracked_tables": 3, "classification_unknown": 3}
    response = await client.get("/api/v1/uc-usage/governance/charts", headers=HEADERS)
    classification = response.json()["tag_coverage"][3]
    assert classification["coverage_pct"] is None
    assert classification["missing_count"] == 0


async def test_recommendation_charts_count_episodes_and_unique_affected_tables(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.return_value = {
        "open_total": 5,
        "open_high": 3,
        "open_medium": 1,
        "affected_tables": 2,
        "old_high": 2,
        "reference_cost_usd": Decimal("2.345"),
        "cost_candidates": 2,
        "cost_measured_tables": 1,
    }
    mock_db.fetchall.side_effect = [
        [
            {"dimension": "category", "bucket": "LIFECYCLE", "severity": "HIGH", "count": 3},
            {"dimension": "category", "bucket": "LIFECYCLE", "severity": "MEDIUM", "count": 1},
            {"dimension": "category", "bucket": "GOVERNANCE", "severity": "UNKNOWN", "count": 1},
            {"dimension": "age", "bucket": "unknown", "severity": "UNKNOWN", "count": 1},
        ],
        [
            {
                "cloud_provider": "azure",
                "object_id": "main.sales.orders",
                "open_high": 3,
                "open_total": 4,
                "oldest_high_days": 120,
                "downstream_fanout": None,
            }
        ],
    ]
    response = await client.get(
        "/api/v1/uc-usage/recommendations/charts",
        headers=HEADERS,
        params={"catalog": "main", "schema": "sales", "tables": "main.sales.orders"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["affected_tables"] == 2
    assert body["summary"]["open_total"] == 5
    assert body["summary"]["reference_cost_usd"] == 2.35
    assert body["categories"][0]["total"] == 4
    assert body["ages"][-1]["UNKNOWN"] == 1
    assert body["priorities"][0]["downstream_fanout"] is None
    sql = mock_db.fetchone.call_args.args[0]
    assert "UPPER(status) = 'OPEN'" in sql
    assert "UPPER(object_type) = 'DATA_PRODUCT'" in sql
    assert "COUNT(DISTINCT named_struct('cloud', cloud_provider, 'table', object_id))" in sql
    assert "normalized_severity = 'MEDIUM' THEN estimated_savings_usd" in sql
    assert "period_start" not in sql
    priority_sql = mock_db.fetchall.call_args_list[-1].args[0]
    assert "WHERE open_high > 0" in priority_sql
    assert "ORDER BY open_high DESC, oldest_high_days DESC NULLS LAST" in priority_sql
    assert mock_db.fetchall.call_args_list[-1].args[-1] == 5


async def test_registry_focus_applies_before_count_and_pagination(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    response = await client.get(
        "/api/v1/uc-usage/governance/registry",
        headers=HEADERS,
        params={
            "catalog": "main",
            "signal": "unused_critical",
            "inactivity": "over_90",
            "missing_tag": "classification",
            "page": 2,
        },
    )
    assert response.status_code == 200
    for call in [mock_db.fetchscalar.call_args, mock_db.fetchall.call_args]:
        sql = call.args[0]
        assert "(is_unused AND is_critical)" in sql
        assert "days_since_last_read > 90" in sql
        assert "has_classification_tag = FALSE" in sql
        # The last operation is actually produced in the catalogue, not governance.
        assert "cat.last_operation, cat.last_operation_at, cat.last_operation_by" in sql
        assert sql.count("?") == len(call.args) - 1
    assert mock_db.fetchall.call_args.args[-2:] == (25, 25)


async def test_recommendation_age_and_severity_narrow_the_list_not_its_counters(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    response = await client.get(
        "/api/v1/uc-usage/recommendations",
        headers=HEADERS,
        params={
            "object_type": "DATA_PRODUCT",
            "severity": "HIGH",
            "age_bucket": "31_90",
            "sort": "age",
            "page": 2,
        },
    )
    assert response.status_code == 200
    counts_sql = mock_db.fetchone.call_args.args[0]
    assert "UPPER(severity) = ?" not in counts_sql
    assert "WHEN first_seen_date" not in counts_sql
    listing_sql = mock_db.fetchall.call_args.args[0]
    assert "first_seen_date > current_date()" in listing_sql
    assert "age_days DESC NULLS LAST" in listing_sql
    assert mock_db.fetchall.call_args.args[-5:] == ("DATA_PRODUCT", "HIGH", "31_90", 25, 25)


@pytest.mark.parametrize(
    "path,params",
    [
        ("governance/registry", {"signal": "drop table"}),
        ("governance/registry", {"missing_tag": "table_owner"}),
        ("governance/registry", {"inactivity": "all"}),
        ("recommendations", {"age_bucket": "-1"}),
        ("recommendations", {"sort": "unsafe"}),
    ],
)
async def test_unknown_drilldown_values_are_rejected(
    client: AsyncClient, mock_db: AsyncMock, path: str, params: dict[str, str]
) -> None:
    response = await client.get(f"/api/v1/uc-usage/{path}", headers=HEADERS, params=params)
    assert response.status_code == 422
    mock_db.fetchall.assert_not_called()


@pytest.mark.parametrize("path", ["governance/charts", "recommendations/charts"])
async def test_new_charts_preserve_unrestricted_access_gate(
    client: AsyncClient, mock_db: AsyncMock, path: str
) -> None:
    response = await client.get(f"/api/v1/uc-usage/{path}", headers={"x-dcm-workspace-ids": "123"})
    assert response.status_code == 403
    mock_db.fetchone.assert_not_called()


async def test_missing_gold_is_an_error_not_an_empty_graph(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.side_effect = RuntimeError(
        "[TABLE_OR_VIEW_NOT_FOUND] gold_dbx_usage_table_catalog is missing"
    )
    response = await client.get("/api/v1/uc-usage/governance/charts", headers=HEADERS)
    assert response.status_code == 503
