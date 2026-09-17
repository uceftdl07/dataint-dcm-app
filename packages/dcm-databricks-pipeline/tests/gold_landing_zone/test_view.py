"""Tests du SQL de la vue `dim_landing_zone` (fonction pure, sans JVM)."""

from __future__ import annotations

from pipelines.gold_landing_zone.view import build_dim_landing_zone_view_sql


def test_view_sql_targets_qualified_view_name() -> None:
    sql = build_dim_landing_zone_view_sql("cat", "sch")
    assert "CREATE OR REPLACE VIEW cat.sch.dim_landing_zone AS" in sql


def test_view_sql_references_the_three_source_objects() -> None:
    sql = build_dim_landing_zone_view_sql("cat", "sch")
    assert "cat.sch.dim_dbx_workspace" in sql
    assert "cat.sch.dim_landing_zone_collector" in sql
    assert "cat.sch.dim_reference_landing_zone_business_application" in sql


def test_view_sql_unions_and_inner_joins() -> None:
    sql = build_dim_landing_zone_view_sql("cat", "sch")
    assert "UNION ALL" in sql
    assert "INNER JOIN cat.sch.dim_reference_landing_zone_business_application b" in sql
    assert "ON a.subscription_or_account_id = b.subscription_or_account_id" in sql


def test_view_sql_dedups_with_qualify_row_number() -> None:
    sql = build_dim_landing_zone_view_sql("cat", "sch")
    assert "QUALIFY ROW_NUMBER() OVER (" in sql
    assert "PARTITION BY a.subscription_or_account_id" in sql
    assert "ORDER BY CASE WHEN a.lz_name IS NOT NULL THEN 0 ELSE 1 END" in sql


def test_view_sql_recomputes_lz_id_and_filters_collector_branch() -> None:
    sql = build_dim_landing_zone_view_sql("cat", "sch")
    assert (
        "CONCAT('lz-', a.cloud_provider, '-', a.subscription_or_account_id) AS lz_id"
        in sql
    )
    assert "WHERE subscription_or_account_id IS NOT NULL" in sql


def test_view_sql_is_parameterized_by_catalog_and_schema() -> None:
    # La cible n'est jamais codee en dur : un autre catalog/schema (target
    # prod) doit se refleter integralement dans le DDL genere.
    sql = build_dim_landing_zone_view_sql("it", "ba_data_connect_monitoring__p")
    assert "it.ba_data_connect_monitoring__p.dim_landing_zone" in sql
    assert "it.ba_data_connect_monitoring__p.dim_dbx_workspace" in sql
    assert "it.ba_data_connect_monitoring__p.dim_landing_zone_collector" in sql
    assert (
        "it.ba_data_connect_monitoring__p.dim_reference_landing_zone_business_application"
        in sql
    )
    assert "cat.sch" not in sql
