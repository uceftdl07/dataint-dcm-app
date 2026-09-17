"""Tests du SQL de la vue `dim_dbx_workspace` (fonction pure, sans JVM)."""

from __future__ import annotations

from pipelines.gold_dbx_workspace.view import build_dim_dbx_workspace_view_sql


def test_view_sql_targets_qualified_view_name() -> None:
    sql = build_dim_dbx_workspace_view_sql("cat", "sch")
    assert "CREATE OR REPLACE VIEW cat.sch.dim_dbx_workspace AS" in sql


def test_view_sql_inner_joins_curated_and_reference_on_workspace_id() -> None:
    sql = build_dim_dbx_workspace_view_sql("cat", "sch")
    assert "FROM cat.sch.curated_dbx_access_workspaces_latest AS w" in sql
    assert "INNER JOIN cat.sch.dim_reference_landing_zone_dbx_workspace AS r" in sql
    assert "ON w.workspace_id = r.workspace_id" in sql


def test_view_sql_filters_running_and_known_landing_zone() -> None:
    sql = build_dim_dbx_workspace_view_sql("cat", "sch")
    assert "r.subscription_or_account_id IS NOT NULL" in sql
    assert "w.status = 'RUNNING'" in sql


def test_view_sql_projects_workspace_url_for_deep_links() -> None:
    sql = build_dim_dbx_workspace_view_sql("cat", "sch")
    assert "AS workspace_id" in sql
    assert "AS workspace_name" in sql
    assert "AS workspace_url" in sql
    assert "AS subscription_or_account_id" in sql
    assert "r.cloud_provider               AS cloud" in sql
    assert "current_timestamp()            AS updated_at" in sql


def test_view_sql_is_parameterized_by_catalog_and_schema() -> None:
    # La cible n'est jamais codee en dur : un autre catalog/schema (target
    # prod) doit se refleter integralement dans le DDL genere.
    sql = build_dim_dbx_workspace_view_sql("it", "ba_data_connect_monitoring__p")
    assert "it.ba_data_connect_monitoring__p.dim_dbx_workspace" in sql
    assert "it.ba_data_connect_monitoring__p.curated_dbx_access_workspaces_latest" in sql
    assert (
        "it.ba_data_connect_monitoring__p.dim_reference_landing_zone_dbx_workspace" in sql
    )
    assert "cat.sch" not in sql
