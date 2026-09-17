#!/usr/bin/env python3
"""Smoke test — SPN access to Unity Catalog via SQL Warehouse.

Load settings from packages/dcm-backend/.env (DCM_* variables).
Run:

    pip install databricks-sql-connector databricks-sdk python-dotenv pydantic-settings
    python our_catalogs_spn.py

Clean dim_landing_zone (keep lz-aws-prod + lz-azure-prod only):

    python our_catalogs_spn.py --clean-dim-landing-zone          # dry-run
    python our_catalogs_spn.py --clean-dim-landing-zone --apply  # execute DELETE

Delete dim_landing_zone rows where subscription_or_account_id IS NULL:

    python our_catalogs_spn.py --delete-dim-lz-null-subscription          # dry-run
    python our_catalogs_spn.py --delete-dim-lz-null-subscription --apply  # execute DELETE

Optional first/super admin bootstrap:

    DCM_BOOTSTRAP_SUPER_ADMIN_ENTRA_OID=<your Entra object id>
    DCM_BOOTSTRAP_SUPER_ADMIN_EMAIL=<your email>
    DCM_BOOTSTRAP_SUPER_ADMIN_DISPLAY_NAME=<your display name>

Multiple bootstrap admins can also be provided:

    DCM_BOOTSTRAP_SUPER_ADMIN_EMAILS=email1@example.com,email2@example.com
    DCM_BOOTSTRAP_SUPER_ADMIN_ENTRA_OIDS=<optional oid1>,<optional oid2>
    DCM_BOOTSTRAP_SUPER_ADMIN_DISPLAY_NAMES=<optional name1>,<optional name2>

Regular full-scope admins can also be bootstrapped without Admin UI access:

    DCM_BOOTSTRAP_ADMIN_EMAILS=email1@example.com,email2@example.com
    DCM_BOOTSTRAP_ADMIN_ENTRA_OIDS=<optional oid1>,<optional oid2>
    DCM_BOOTSTRAP_ADMIN_DISPLAY_NAMES=<optional name1>,<optional name2>

The "admin" role has unrestricted data access. The "super_admin" role has the
same data access plus Admin UI and governance-management access.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from textwrap import dedent
from uuid import uuid4

from dotenv import load_dotenv
from databricks import sql
from databricks.sdk.core import Config, oauth_service_principal

_env_path = Path(__file__).resolve().parent / "packages" / "dcm-backend" / ".env"
load_dotenv(_env_path)

# CI (GitHub Actions) injects a federated Entra bearer as DATABRICKS_TOKEN via
# OIDC/WIF (no SP secret). Local runs fall back to SPN OAuth M2M. Capture the
# token first, then drop DATABRICKS_TOKEN from the env so the SPN-fallback SDK
# Config below never silently picks it up as a competing credential.
access_token = os.environ.get("DCM_DATABRICKS_TOKEN") or os.environ.get(
    "DATABRICKS_TOKEN"
)
os.environ.pop("DATABRICKS_TOKEN", None)

# Local runs can point at a ~/.databrickscfg profile (auth-agnostic: OAuth U2M
# preferred, PAT tolerated). When set it supplies both host and credentials and
# takes precedence over the SPN client_secret fallback.
profile = os.environ.get("DCM_DATABRICKS_PROFILE") or os.environ.get(
    "DATABRICKS_CONFIG_PROFILE"
)
_profile_config = Config(profile=profile) if profile else None

server_hostname = (
    os.environ.get("DCM_DATABRICKS_HOST")
    or (
        _profile_config.host.replace("https://", "").rstrip("/")
        if _profile_config
        else None
    )
    or "dbc-89e8d3b6-20ad.cloud.databricks.com"
)
warehouse_id = os.environ.get("DCM_DATABRICKS_WAREHOUSE_ID", "fcc5098720414937")
http_path = (
    os.environ.get("DCM_DATABRICKS_HTTP_PATH") or f"/sql/1.0/warehouses/{warehouse_id}"
)
client_id = os.environ.get("DCM_DATABRICKS_SPN_CLIENT_ID", "")
client_secret = os.environ.get("DCM_DATABRICKS_SPN_CLIENT_SECRET", "")
catalog = os.environ.get("DCM_DATABRICKS_CATALOG", "it")
schema = os.environ.get("DCM_DATABRICKS_SCHEMA", "ba_data_connect_monitoring__d")

if not access_token and not client_secret and _profile_config is None:
    print(
        "Set DATABRICKS_TOKEN (CI/OIDC), DCM_DATABRICKS_PROFILE "
        "(local ~/.databrickscfg) or DCM_DATABRICKS_SPN_CLIENT_SECRET "
        "in packages/dcm-backend/.env (local)",
        file=sys.stderr,
    )
    sys.exit(1)


def qualified_table(table_name: str) -> str:
    return f"`{catalog}`.`{schema}`.`{table_name}`"


def credential_provider():
    config = Config(
        host=f"https://{server_hostname}",
        client_id=client_id,
        client_secret=client_secret,
    )
    return oauth_service_principal(config)


KEEP_DIM_LANDING_ZONE_IDS = ("lz-aws-prod", "lz-azure-prod")

ADMIN_TABLES = [
    "dcm_app_users",
    "dcm_role_permissions",
    "dcm_user_lz_access",
    "dcm_user_notification_preferences",
    "dcm_access_requests",
    "dcm_landing_zones",
    "dcm_notification_channels",
    "dcm_alert_rules",
    "dcm_alert_firings",
    "dcm_collector_status",
    "dcm_kpi_config",
    "dcm_retention_policies",
    "dcm_maintenance_windows",
    "dcm_audit_log",
    "dcm_embedded_dashboards",
    "dcm_projects",
    "dcm_project_lz_scope",
    "dcm_project_dbx_scope",
    "dcm_project_members",
    "dcm_project_join_requests",
    "dcm_project_scope_requests",
]

# FR-006a compatibility mapping: legacy global `role` -> new `platform_role`.
LEGACY_SUPER_ADMIN_ROLES = frozenset({"super_admin", "admin"})

EMBEDDED_DASHBOARD_DEFAULTS = [
    (
        "genie-obs",
        "Genie Control Tower",
        "Real-time observability for Databricks Genie usage across workspaces.",
        "https://dbc-e25c222e-27eb.cloud.databricks.com",
        "2505786830871273",
        "01f1666ab90c1d32ba3046df563db745",
        "global",
        None,
        "insights",
        0,
    ),
]

KPI_DEFAULTS = [
    (
        "pipeline_failure_rate_warning_pct",
        10,
        "Taux échec pipelines → seuil avertissement (%)",
    ),
    (
        "pipeline_failure_rate_critical_pct",
        30,
        "Taux échec pipelines → seuil critique (%)",
    ),
    (
        "cluster_error_rate_warning_pct",
        5,
        "Taux clusters en erreur → seuil avertissement (%)",
    ),
    (
        "cluster_error_rate_critical_pct",
        20,
        "Taux clusters en erreur → seuil critique (%)",
    ),
    ("cost_overrun_warning_pct", 80, "Budget consommé → seuil avertissement (%)"),
    ("cost_overrun_critical_pct", 100, "Budget consommé → seuil critique (%)"),
    ("open_alerts_warning_count", 5, "Alertes sécurité ouvertes → seuil avertissement"),
    ("open_alerts_critical_count", 20, "Alertes sécurité ouvertes → seuil critique"),
    ("compliance_score_warning_pct", 80, "Score conformité → seuil avertissement (%)"),
    ("compliance_score_critical_pct", 60, "Score conformité → seuil critique (%)"),
]

ROLE_PERMISSION_DEFAULTS: list[tuple[str, str, str]] = [
    # viewer / project member — read-only access to every DCM data interface
    # (data itself is scoped to the project LZ + Databricks workspaces).
    ("viewer", "page", "page:dashboard"),
    ("viewer", "page", "page:datafactory"),
    ("viewer", "page", "page:pipelines"),
    ("viewer", "page", "page:clusters"),
    ("viewer", "page", "page:alerts"),
    ("viewer", "page", "page:security"),
    ("viewer", "page", "page:costs"),
    ("viewer", "page", "page:governance"),
    ("viewer", "page", "page:databricks"),
    ("viewer", "page", "page:databases"),
    ("viewer", "page", "page:talk-to-data"),
    ("viewer", "page", "page:status"),
    ("viewer", "page", "page:projects"),
    ("viewer", "page", "page:settings"),
    ("viewer", "widget", "widget:dashboard:pipelines"),
    ("viewer", "widget", "widget:dashboard:failures"),
    ("viewer", "widget", "widget:dashboard:clusters"),
    ("viewer", "widget", "widget:dashboard:alerts"),
    ("viewer", "widget", "widget:dashboard:cost_total"),
    ("viewer", "widget", "widget:dashboard:governance"),
    ("viewer", "widget", "widget:dashboard:finops_card"),
    ("viewer", "widget", "widget:dashboard:datafactory_card"),
    ("viewer", "widget", "widget:dashboard:databricks_card"),
    ("viewer", "widget", "widget:dashboard:databases_card"),
    # data_architect — viewer + coûts + gouvernance (pas dashboard global)
    ("data_architect", "page", "page:datafactory"),
    ("data_architect", "page", "page:pipelines"),
    ("data_architect", "page", "page:clusters"),
    ("data_architect", "page", "page:alerts"),
    ("data_architect", "page", "page:security"),
    ("data_architect", "page", "page:costs"),
    ("data_architect", "page", "page:governance"),
    ("data_architect", "page", "page:databricks"),
    ("data_architect", "page", "page:databases"),
    ("data_architect", "page", "page:my-access"),
    ("data_architect", "page", "page:settings"),
    ("data_architect", "widget", "widget:dashboard:pipelines"),
    ("data_architect", "widget", "widget:dashboard:failures"),
    ("data_architect", "widget", "widget:dashboard:clusters"),
    ("data_architect", "widget", "widget:dashboard:alerts"),
    ("data_architect", "widget", "widget:dashboard:cost_total"),
    ("data_architect", "widget", "widget:dashboard:governance"),
    ("data_architect", "widget", "widget:dashboard:finops_card"),
    ("data_architect", "widget", "widget:dashboard:datafactory_card"),
    ("data_architect", "widget", "widget:dashboard:databricks_card"),
    ("data_architect", "widget", "widget:dashboard:databases_card"),
    # manager — + global dashboard & users
    ("manager", "page", "page:dashboard"),
    ("manager", "page", "page:datafactory"),
    ("manager", "page", "page:pipelines"),
    ("manager", "page", "page:clusters"),
    ("manager", "page", "page:alerts"),
    ("manager", "page", "page:security"),
    ("manager", "page", "page:costs"),
    ("manager", "page", "page:governance"),
    ("manager", "page", "page:users"),
    ("manager", "page", "page:databricks"),
    ("manager", "page", "page:databases"),
    ("manager", "page", "page:talk-to-data"),
    ("manager", "page", "page:my-access"),
    ("manager", "page", "page:settings"),
    ("manager", "page", "page:status"),
    ("manager", "widget", "widget:dashboard:pipelines"),
    ("manager", "widget", "widget:dashboard:failures"),
    ("manager", "widget", "widget:dashboard:clusters"),
    ("manager", "widget", "widget:dashboard:alerts"),
    ("manager", "widget", "widget:dashboard:cost_total"),
    ("manager", "widget", "widget:dashboard:governance"),
    ("manager", "widget", "widget:dashboard:finops_card"),
    ("manager", "widget", "widget:dashboard:datafactory_card"),
    ("manager", "widget", "widget:dashboard:databricks_card"),
    ("manager", "widget", "widget:dashboard:databases_card"),
    # admin — viewer + user management, no Admin UI page. page:unity-catalog
    # starts here and is withheld from viewer: the raw-table explorer reads an
    # arbitrary catalog.schema.table, so no project scope can be attached to it
    # and the API refuses it to project members (require_unrestricted_scope).
    ("admin", "page", "page:dashboard"),
    ("admin", "page", "page:datafactory"),
    ("admin", "page", "page:pipelines"),
    ("admin", "page", "page:clusters"),
    ("admin", "page", "page:alerts"),
    ("admin", "page", "page:security"),
    ("admin", "page", "page:costs"),
    ("admin", "page", "page:governance"),
    ("admin", "page", "page:users"),
    ("admin", "page", "page:databricks"),
    ("admin", "page", "page:databases"),
    ("admin", "page", "page:unity-catalog"),
    ("admin", "page", "page:talk-to-data"),
    ("admin", "page", "page:projects"),
    ("admin", "page", "page:settings"),
    ("admin", "page", "page:status"),
    ("admin", "widget", "widget:dashboard:pipelines"),
    ("admin", "widget", "widget:dashboard:failures"),
    ("admin", "widget", "widget:dashboard:clusters"),
    ("admin", "widget", "widget:dashboard:alerts"),
    ("admin", "widget", "widget:dashboard:cost_total"),
    ("admin", "widget", "widget:dashboard:governance"),
    ("admin", "widget", "widget:dashboard:finops_card"),
    ("admin", "widget", "widget:dashboard:datafactory_card"),
    ("admin", "widget", "widget:dashboard:databricks_card"),
    ("admin", "widget", "widget:dashboard:databases_card"),
    ("admin", "feature", "feature:admin_ui"),
    # super_admin — everything including Admin UI
    ("super_admin", "page", "page:admin"),
    ("super_admin", "page", "page:dashboard"),
    ("super_admin", "page", "page:datafactory"),
    ("super_admin", "page", "page:pipelines"),
    ("super_admin", "page", "page:clusters"),
    ("super_admin", "page", "page:alerts"),
    ("super_admin", "page", "page:security"),
    ("super_admin", "page", "page:costs"),
    ("super_admin", "page", "page:governance"),
    ("super_admin", "page", "page:users"),
    ("super_admin", "page", "page:databricks"),
    ("super_admin", "page", "page:databases"),
    ("super_admin", "page", "page:unity-catalog"),
    ("super_admin", "page", "page:talk-to-data"),
    ("super_admin", "page", "page:projects"),
    ("super_admin", "page", "page:settings"),
    ("super_admin", "page", "page:status"),
    ("super_admin", "widget", "widget:dashboard:pipelines"),
    ("super_admin", "widget", "widget:dashboard:failures"),
    ("super_admin", "widget", "widget:dashboard:clusters"),
    ("super_admin", "widget", "widget:dashboard:alerts"),
    ("super_admin", "widget", "widget:dashboard:cost_total"),
    ("super_admin", "widget", "widget:dashboard:governance"),
    ("super_admin", "widget", "widget:dashboard:finops_card"),
    ("super_admin", "widget", "widget:dashboard:datafactory_card"),
    ("super_admin", "widget", "widget:dashboard:databricks_card"),
    ("super_admin", "widget", "widget:dashboard:databases_card"),
    ("super_admin", "feature", "feature:admin_ui"),
]

RETENTION_DEFAULTS = [
    ("pipeline_metrics", 90),
    ("cluster_metrics", 90),
    ("cost_metrics", 365),
    ("security_alerts", 180),
    ("user_metrics", 90),
    ("standard_check_evaluations", 180),
]


DEFAULT_BOOTSTRAP_ADMINS = [
    ("email:al0533237@admin.hubtotal.net", "al0533237@admin.hubtotal.net", "Mikael MAUSSE", "admin"),
    ("email:al1010544@admin.hubtotal.net", "al1010544@admin.hubtotal.net", "GIBART Jocelyn", "admin"),
    ("email:al1057721@admin.hubtotal.net", "al1057721@admin.hubtotal.net", "NAKHLA Rochd (A)", "admin"),
    ("email:al1143744@admin.hubtotal.net", "al1143744@admin.hubtotal.net", "BRAHMI Ismail (A)", "admin"),
    ("email:al1146908@admin.hubtotal.net", "al1146908@admin.hubtotal.net", "YENGUI Khouloud (A)", "admin"),
    ("email:al1152754@admin.hubtotal.net", "al1152754@admin.hubtotal.net", "FOUKKAI Anass (A)", "admin"),
    ("email:caj0209162@admin.hubtotal.net", "caj0209162@admin.hubtotal.net", "COLLYN Marie-Hélène", "admin"),
]

DEFAULT_BOOTSTRAP_SUPER_ADMINS = [
    ("email:zahra.maaziz@totalenergies.com", "zahra.maaziz@totalenergies.com", "Zahra Maaziz", "super_admin"),
    ("email:al1036565@admin.hubtotal.net", "al1036565@admin.hubtotal.net", "Yahia ZERDOUMI (A)", "super_admin"),
    ("email:aj0411581@admin.hubtotal.net", "aj0411581@admin.hubtotal.net", "LEZHARI Maher (A)", "super_admin"),
    ("email:aj1087147@tdf.hubtotal.net", "aj1087147@tdf.hubtotal.net", "AJ1087147", "super_admin"),
]


def sql_literal(value: str | None) -> str:
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"


def env_list(name: str) -> list[str]:
    value = os.environ.get(name, "")
    return [item.strip() for item in value.split(",") if item.strip()]


def execute_statement(cursor, statement: str) -> None:
    cursor.execute(dedent(statement).strip())


def table_exists(cursor, table_name: str) -> bool:
    cursor.execute(
        f"SHOW TABLES IN `{catalog}`.`{schema}` LIKE {sql_literal(table_name)}"
    )
    return bool(cursor.fetchall())


def create_admin_tables(cursor) -> None:
    """Create DCM admin Delta tables in Unity Catalog.

    PostgreSQL-only constraints from the original lead spec are enforced by the API layer.
    """

    print(f"\nEnsure DCM admin tables in `{catalog}`.`{schema}`...")

    execute_statement(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table("dcm_app_users")} (
            id STRING NOT NULL,
            entra_oid STRING NOT NULL,
            email STRING NOT NULL,
            display_name STRING,
            role STRING NOT NULL,
            is_active BOOLEAN NOT NULL,
            created_at TIMESTAMP NOT NULL,
            last_login_at TIMESTAMP
        )
        USING DELTA
        """,
    )

    execute_statement(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table("dcm_role_permissions")} (
            role STRING NOT NULL,
            resource_type STRING NOT NULL,
            resource_key STRING NOT NULL,
            is_allowed BOOLEAN NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
        USING DELTA
        """,
    )

    execute_statement(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table("dcm_user_lz_access")} (
            user_id STRING NOT NULL,
            lz_id STRING NOT NULL,
            granted_by STRING,
            granted_at TIMESTAMP NOT NULL
        )
        USING DELTA
        """,
    )

    execute_statement(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table("dcm_user_notification_preferences")} (
            user_id STRING NOT NULL,
            show_pipeline BOOLEAN NOT NULL,
            show_cluster BOOLEAN NOT NULL,
            show_cost BOOLEAN NOT NULL,
            show_security BOOLEAN NOT NULL,
            show_governance BOOLEAN NOT NULL,
            show_collector_status BOOLEAN NOT NULL,
            min_severity STRING NOT NULL,
            hide_info BOOLEAN NOT NULL,
            email_enabled BOOLEAN NOT NULL,
            teams_digest_enabled BOOLEAN NOT NULL,
            notification_lz_ids ARRAY<STRING>,
            updated_at TIMESTAMP NOT NULL
        )
        USING DELTA
        """,
    )

    execute_statement(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table("dcm_access_requests")} (
            id STRING NOT NULL,
            email STRING NOT NULL,
            display_name STRING NOT NULL,
            entra_oid STRING,
            justification STRING NOT NULL,
            requested_lz_ids STRING NOT NULL,
            status STRING NOT NULL,
            requested_at TIMESTAMP NOT NULL,
            reviewed_by STRING,
            reviewed_at TIMESTAMP
        )
        USING DELTA
        """,
    )

    execute_statement(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table("dcm_landing_zones")} (
            lz_id STRING NOT NULL,
            display_name STRING NOT NULL,
            cloud_provider STRING NOT NULL,
            region STRING,
            environment STRING,
            ba_name STRING,
            collector_names ARRAY<STRING> NOT NULL,
            is_active BOOLEAN NOT NULL,
            registered_at TIMESTAMP NOT NULL,
            registered_by STRING,
            notes STRING
        )
        USING DELTA
        """,
    )

    execute_statement(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table("dcm_notification_channels")} (
            id STRING NOT NULL,
            name STRING NOT NULL,
            channel_type STRING NOT NULL,
            config STRING NOT NULL,
            is_active BOOLEAN NOT NULL,
            created_by STRING,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
        USING DELTA
        """,
    )

    execute_statement(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table("dcm_alert_rules")} (
            id STRING NOT NULL,
            name STRING NOT NULL,
            description STRING,
            metric_domain STRING NOT NULL,
            condition_field STRING NOT NULL,
            condition_operator STRING NOT NULL,
            condition_threshold DOUBLE NOT NULL,
            eval_window_hours INT NOT NULL,
            severity STRING NOT NULL,
            applies_to_lz_ids ARRAY<STRING>,
            notification_channel_ids ARRAY<STRING> NOT NULL,
            cooldown_minutes INT NOT NULL,
            is_active BOOLEAN NOT NULL,
            created_by STRING,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
        USING DELTA
        """,
    )

    execute_statement(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table("dcm_alert_firings")} (
            id STRING NOT NULL,
            rule_id STRING NOT NULL,
            lz_id STRING,
            fired_at TIMESTAMP NOT NULL,
            resolved_at TIMESTAMP,
            measured_value DOUBLE,
            notification_sent BOOLEAN NOT NULL,
            notification_error STRING
        )
        USING DELTA
        """,
    )

    execute_statement(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table("dcm_collector_status")} (
            lz_id STRING NOT NULL,
            collector_name STRING NOT NULL,
            last_run_at TIMESTAMP,
            last_run_status STRING,
            last_run_duration_s DOUBLE,
            metrics_collected INT,
            last_error STRING,
            updated_at TIMESTAMP NOT NULL
        )
        USING DELTA
        """,
    )

    execute_statement(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table("dcm_kpi_config")} (
            config_key STRING NOT NULL,
            config_value DOUBLE NOT NULL,
            description STRING,
            updated_by STRING,
            updated_at TIMESTAMP NOT NULL
        )
        USING DELTA
        """,
    )

    execute_statement(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table("dcm_retention_policies")} (
            metric_table STRING NOT NULL,
            retention_days INT NOT NULL,
            updated_by STRING,
            updated_at TIMESTAMP NOT NULL
        )
        USING DELTA
        """,
    )

    execute_statement(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table("dcm_maintenance_windows")} (
            id STRING NOT NULL,
            name STRING NOT NULL,
            description STRING,
            lz_ids ARRAY<STRING>,
            starts_at TIMESTAMP NOT NULL,
            ends_at TIMESTAMP NOT NULL,
            suppress_alerts BOOLEAN NOT NULL,
            created_by STRING,
            created_at TIMESTAMP NOT NULL
        )
        USING DELTA
        """,
    )

    execute_statement(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table("dcm_audit_log")} (
            id STRING NOT NULL,
            actor_user_id STRING,
            action STRING NOT NULL,
            target_type STRING,
            target_id STRING,
            before_state STRING,
            after_state STRING,
            ip_address STRING,
            created_at TIMESTAMP NOT NULL
        )
        USING DELTA
        """,
    )

    execute_statement(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table("dcm_embedded_dashboards")} (
            dashboard_slug STRING NOT NULL,
            title STRING NOT NULL,
            description STRING,
            workspace_host STRING NOT NULL,
            workspace_id STRING NOT NULL,
            dashboard_id STRING NOT NULL,
            scope STRING NOT NULL,
            source_lz_id STRING,
            menu_group STRING NOT NULL,
            sort_order INT NOT NULL,
            enabled BOOLEAN NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
        USING DELTA
        """,
    )

    print("OK — admin tables ensured")


def create_project_tables(cursor) -> None:
    """Create the 6 project-governance Delta tables (feature 015 — T001).

    Ported from docs/spike/access-group-governance/ddl.sql. `dcm_projects.created_by`
    is nullable here (spike DDL had NOT NULL) because the migration creates default
    per-Business-Application projects with no human requester (created_by = NULL).
    """

    print(f"\nEnsure DCM project tables in `{catalog}`.`{schema}`...")

    execute_statement(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table("dcm_projects")} (
            id              STRING    NOT NULL,
            name            STRING    NOT NULL,
            business_app_id STRING    NOT NULL,
            status          STRING    NOT NULL,
            entra_group_id  STRING,
            created_by      STRING,
            created_at      TIMESTAMP NOT NULL,
            updated_at      TIMESTAMP NOT NULL,
            validated_by    STRING,
            validated_at    TIMESTAMP,
            decision_reason STRING
        )
        USING DELTA
        """,
    )

    execute_statement(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table("dcm_project_lz_scope")} (
            project_id STRING    NOT NULL,
            lz_id      STRING    NOT NULL,
            granted_by STRING,
            granted_at TIMESTAMP NOT NULL
        )
        USING DELTA
        """,
    )

    execute_statement(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table("dcm_project_dbx_scope")} (
            project_id   STRING    NOT NULL,
            workspace_id STRING    NOT NULL,
            granted_by   STRING,
            granted_at   TIMESTAMP NOT NULL
        )
        USING DELTA
        """,
    )

    execute_statement(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table("dcm_project_members")} (
            project_id STRING    NOT NULL,
            user_id    STRING    NOT NULL,
            role       STRING    NOT NULL,
            added_by   STRING,
            added_at   TIMESTAMP NOT NULL
        )
        USING DELTA
        """,
    )

    execute_statement(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table("dcm_project_join_requests")} (
            id             STRING    NOT NULL,
            project_id     STRING    NOT NULL,
            user_id        STRING    NOT NULL,
            requested_role STRING    NOT NULL,
            status         STRING    NOT NULL,
            justification  STRING,
            requested_at   TIMESTAMP NOT NULL,
            decided_by     STRING,
            decided_at     TIMESTAMP,
            decision_reason STRING
        )
        USING DELTA
        """,
    )

    execute_statement(
        cursor,
        f"""
        CREATE TABLE IF NOT EXISTS {qualified_table("dcm_project_scope_requests")} (
            id             STRING    NOT NULL,
            project_id     STRING    NOT NULL,
            scope_type     STRING    NOT NULL,
            scope_ref      STRING    NOT NULL,
            status         STRING    NOT NULL,
            justification  STRING,
            requested_by   STRING    NOT NULL,
            requested_at   TIMESTAMP NOT NULL,
            decided_by     STRING,
            decided_at     TIMESTAMP,
            decision_reason STRING
        )
        USING DELTA
        """,
    )

    print("OK — project tables ensured")


def ensure_platform_role_column(cursor) -> None:
    """Additive column on dcm_app_users (P14) — backfilled by migrate_flat_users_to_projects.

    Databricks SQL has no ``ADD COLUMN IF NOT EXISTS``; guard with SHOW COLUMNS
    to stay idempotent.
    """
    cursor.execute(f"SHOW COLUMNS IN {qualified_table('dcm_app_users')}")
    existing = {row[0].lower() for row in cursor.fetchall()}
    if "platform_role" in existing:
        return
    execute_statement(
        cursor,
        f"""
        ALTER TABLE {qualified_table("dcm_app_users")}
        ADD COLUMNS (platform_role STRING)
        """,
    )


def ensure_decision_reason_columns(cursor) -> None:
    """Additive ``decision_reason`` on the three governance decision tables.

    A rejection has to say why: the reason is shown back to the requester and is
    what makes a refused project auditable instead of a silent dead end. Same
    SHOW COLUMNS guard as :func:`ensure_platform_role_column` (Databricks SQL has
    no ``ADD COLUMN IF NOT EXISTS``).
    """
    for table in (
        "dcm_projects",
        "dcm_project_join_requests",
        "dcm_project_scope_requests",
    ):
        qualified = qualified_table(table)
        cursor.execute(f"SHOW COLUMNS IN {qualified}")
        existing = {row[0].lower() for row in cursor.fetchall()}
        if "decision_reason" in existing:
            continue
        execute_statement(
            cursor,
            f"""
            ALTER TABLE {qualified}
            ADD COLUMNS (decision_reason STRING)
            """,
        )


def seed_embedded_dashboard_defaults(cursor) -> None:
    print("\nSeed default embedded Databricks dashboards...")

    dashboards_table = qualified_table("dcm_embedded_dashboards")
    for (
        dashboard_slug,
        title,
        description,
        workspace_host,
        workspace_id,
        dashboard_id,
        scope,
        source_lz_id,
        menu_group,
        sort_order,
    ) in EMBEDDED_DASHBOARD_DEFAULTS:
        execute_statement(
            cursor,
            f"""
            INSERT INTO {dashboards_table} (
                dashboard_slug,
                title,
                description,
                workspace_host,
                workspace_id,
                dashboard_id,
                scope,
                source_lz_id,
                menu_group,
                sort_order,
                enabled,
                updated_at
            )
            SELECT
                {sql_literal(dashboard_slug)},
                {sql_literal(title)},
                {sql_literal(description)},
                {sql_literal(workspace_host)},
                {sql_literal(workspace_id)},
                {sql_literal(dashboard_id)},
                {sql_literal(scope)},
                {sql_literal(source_lz_id)},
                {sql_literal(menu_group)},
                {sort_order},
                TRUE,
                current_timestamp()
            WHERE NOT EXISTS (
                SELECT 1 FROM {dashboards_table}
                WHERE dashboard_slug = {sql_literal(dashboard_slug)}
            )
            """,
        )

    print("OK — default embedded dashboard rows ensured")


def seed_admin_defaults(cursor) -> None:
    print("\nSeed default DCM admin configuration...")

    kpi_table = qualified_table("dcm_kpi_config")
    for config_key, config_value, description in KPI_DEFAULTS:
        execute_statement(
            cursor,
            f"""
            INSERT INTO {kpi_table} (config_key, config_value, description, updated_by, updated_at)
            SELECT
                {sql_literal(config_key)},
                CAST({config_value} AS DOUBLE),
                {sql_literal(description)},
                NULL,
                current_timestamp()
            WHERE NOT EXISTS (
                SELECT 1 FROM {kpi_table}
                WHERE config_key = {sql_literal(config_key)}
            )
            """,
        )

    retention_table = qualified_table("dcm_retention_policies")
    for metric_table, retention_days in RETENTION_DEFAULTS:
        execute_statement(
            cursor,
            f"""
            INSERT INTO {retention_table} (metric_table, retention_days, updated_by, updated_at)
            SELECT
                {sql_literal(metric_table)},
                {retention_days},
                NULL,
                current_timestamp()
            WHERE NOT EXISTS (
                SELECT 1 FROM {retention_table}
                WHERE metric_table = {sql_literal(metric_table)}
            )
            """,
        )

    permissions_table = qualified_table("dcm_role_permissions")
    for role, resource_type, resource_key in ROLE_PERMISSION_DEFAULTS:
        execute_statement(
            cursor,
            f"""
            INSERT INTO {permissions_table}
                (role, resource_type, resource_key, is_allowed, updated_at)
            SELECT
                {sql_literal(role)},
                {sql_literal(resource_type)},
                {sql_literal(resource_key)},
                TRUE,
                current_timestamp()
            WHERE NOT EXISTS (
                SELECT 1 FROM {permissions_table}
                WHERE role = {sql_literal(role)}
                  AND resource_type = {sql_literal(resource_type)}
                  AND resource_key = {sql_literal(resource_key)}
            )
            """,
        )

    print("OK — default KPI, retention and role-permission rows ensured")


# The three effective roles of the reduced model. Legacy ``pending`` /
# ``data_architect`` / ``manager`` rows are deliberately left alone: the API
# resolves those roles to an effective one before reading the table
# (``resolve_permission_role``), so their rows carry no authority and removing
# them is transition churn for nothing.
SYNCED_PERMISSION_ROLES = ("viewer", "admin", "super_admin")


@dataclass
class RolePermissionSyncPlan:
    """Pure convergence plan for dcm_role_permissions — computed with no DB access."""

    rows_to_insert: list[tuple[str, str, str]] = field(default_factory=list)
    rows_to_allow: list[tuple[str, str, str]] = field(default_factory=list)
    rows_to_delete: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.rows_to_insert or self.rows_to_allow or self.rows_to_delete)


def build_role_permission_sync_plan(
    *,
    existing_rows,
    defaults=None,
    roles=SYNCED_PERMISSION_ROLES,
) -> RolePermissionSyncPlan:
    """Align dcm_role_permissions with ROLE_PERMISSION_DEFAULTS for the effective roles.

    :func:`seed_admin_defaults` only ever inserts what is missing, so a table
    seeded by an older revision keeps serving that older permission set forever —
    and the API prefers the table over its in-code defaults as soon as it returns
    a row, so a stale set *hides* interfaces a project member is entitled to. This
    is the missing half: it also revokes what the defaults no longer grant.

    Rows for roles outside ``roles`` are neither read nor deleted, so the legacy
    roles keep whatever they hold for the duration of the transition. Passing the
    post-apply state back in yields an empty plan (idempotence).
    """
    role_filter = set(roles)
    desired = {
        (role, resource_type, resource_key)
        for role, resource_type, resource_key in (defaults or ROLE_PERMISSION_DEFAULTS)
        if role in role_filter
    }

    present: set[tuple[str, str, str]] = set()
    allowed: set[tuple[str, str, str]] = set()
    to_delete: set[tuple[str, str, str]] = set()
    for row in existing_rows:
        key = (row["role"], row["resource_type"], row["resource_key"])
        if key[0] not in role_filter:
            continue
        if key not in desired:
            to_delete.add(key)
            continue
        present.add(key)
        if row.get("is_allowed", True):
            allowed.add(key)

    return RolePermissionSyncPlan(
        rows_to_insert=sorted(desired - present),
        # ``is_allowed = FALSE`` is what the API filters on, so a revoked row keeps
        # hiding the interface even though the row exists. The table has no primary
        # key, so a duplicate pair needs no re-grant as long as one row is TRUE.
        rows_to_allow=sorted(present - allowed),
        rows_to_delete=sorted(to_delete),
    )


def apply_role_permission_sync_plan(cursor, plan: RolePermissionSyncPlan) -> None:
    """Execute the writes for an already-computed RolePermissionSyncPlan (no planning here)."""
    permissions_table = qualified_table("dcm_role_permissions")

    def row_predicate(role: str, resource_type: str, resource_key: str) -> str:
        return (
            f"role = {sql_literal(role)}\n"
            f"  AND resource_type = {sql_literal(resource_type)}\n"
            f"  AND resource_key = {sql_literal(resource_key)}"
        )

    for role, resource_type, resource_key in plan.rows_to_insert:
        execute_statement(
            cursor,
            f"""
            INSERT INTO {permissions_table}
                (role, resource_type, resource_key, is_allowed, updated_at)
            SELECT
                {sql_literal(role)},
                {sql_literal(resource_type)},
                {sql_literal(resource_key)},
                TRUE,
                current_timestamp()
            WHERE NOT EXISTS (
                SELECT 1 FROM {permissions_table}
                WHERE {row_predicate(role, resource_type, resource_key)}
            )
            """,
        )

    for role, resource_type, resource_key in plan.rows_to_allow:
        execute_statement(
            cursor,
            f"""
            UPDATE {permissions_table}
            SET is_allowed = TRUE, updated_at = current_timestamp()
            WHERE {row_predicate(role, resource_type, resource_key)}
              AND is_allowed = FALSE
            """,
        )

    for role, resource_type, resource_key in plan.rows_to_delete:
        execute_statement(
            cursor,
            f"""
            DELETE FROM {permissions_table}
            WHERE {row_predicate(role, resource_type, resource_key)}
            """,
        )


def sync_role_permissions(cursor) -> None:
    """Converge dcm_role_permissions on the in-code defaults for the 3 effective roles."""
    print("\nConverge dcm_role_permissions on the in-code defaults...")
    if not table_exists(cursor, "dcm_role_permissions"):
        print("SKIP — dcm_role_permissions not found")
        return

    plan = build_role_permission_sync_plan(
        existing_rows=_fetch_rows_as_dicts(
            cursor,
            f"""
            SELECT role, resource_type, resource_key, is_allowed
            FROM {qualified_table('dcm_role_permissions')}
            """,
            ["role", "resource_type", "resource_key", "is_allowed"],
        )
    )

    if not plan.has_changes:
        print("OK — role permissions already match the in-code defaults")
        return

    for role, _resource_type, resource_key in plan.rows_to_insert:
        print(f"   + {role}: {resource_key}")
    for role, _resource_type, resource_key in plan.rows_to_allow:
        print(f"   ~ {role}: {resource_key} (was revoked)")
    for role, _resource_type, resource_key in plan.rows_to_delete:
        print(f"   - {role}: {resource_key}")

    apply_role_permission_sync_plan(cursor, plan)
    print(
        f"OK — {len(plan.rows_to_insert)} granted, {len(plan.rows_to_allow)} re-allowed, "
        f"{len(plan.rows_to_delete)} revoked"
    )


def bootstrap_admin_user(cursor) -> None:
    """Optionally create super admins and full-scope admins from bootstrap env vars."""

    def collect_rows(
        prefix: str,
        role: str,
        default_display_name: str,
    ) -> list[tuple[str, str, str, str]]:
        rows: list[tuple[str, str, str, str]] = []
        entra_oid = os.environ.get(f"{prefix}_ENTRA_OID")
        email = os.environ.get(f"{prefix}_EMAIL")
        display_name = os.environ.get(f"{prefix}_DISPLAY_NAME") or default_display_name
        if email:
            rows.append((entra_oid or f"email:{email.lower()}", email, display_name, role))

        emails = env_list(f"{prefix}_EMAILS")
        entra_oids = env_list(f"{prefix}_ENTRA_OIDS")
        display_names = env_list(f"{prefix}_DISPLAY_NAMES")
        for index, admin_email in enumerate(emails):
            rows.append(
                (
                    (
                        entra_oids[index]
                        if index < len(entra_oids)
                        else f"email:{admin_email.lower()}"
                    ),
                    admin_email,
                    display_names[index] if index < len(display_names) else admin_email,
                    role,
                )
            )
        return rows

    bootstrap_rows = [
        *DEFAULT_BOOTSTRAP_ADMINS,
        *DEFAULT_BOOTSTRAP_SUPER_ADMINS,
        *collect_rows("DCM_BOOTSTRAP_ADMIN", "admin", "DCM Admin"),
        *collect_rows("DCM_BOOTSTRAP_SUPER_ADMIN", "super_admin", "DCM Super Admin"),
    ]
    deduped_rows = {
        email.lower(): (entra_oid, email, display_name, role)
        for entra_oid, email, display_name, role in bootstrap_rows
    }

    if not deduped_rows:
        print(
            "\nBootstrap admin skipped — set "
            "DCM_BOOTSTRAP_SUPER_ADMIN_EMAIL(S) or "
            "DCM_BOOTSTRAP_ADMIN_EMAIL(S) to enable"
        )
        return

    users_table = qualified_table("dcm_app_users")
    for admin_entra_oid, admin_email, admin_display_name, role in deduped_rows.values():
        print(f"\nEnsure bootstrap user `{admin_email}` with DCM role `{role}`...")

        execute_statement(
            cursor,
            f"""
            UPDATE {users_table}
            SET
                entra_oid = {sql_literal(admin_entra_oid)},
                email = {sql_literal(admin_email)},
                display_name = {sql_literal(admin_display_name)},
                role = {sql_literal(role)},
                is_active = true
            WHERE entra_oid = {sql_literal(admin_entra_oid)}
               OR LOWER(email) = LOWER({sql_literal(admin_email)})
            """,
        )

        execute_statement(
            cursor,
            f"""
            INSERT INTO {users_table}
                (id, entra_oid, email, display_name, role, is_active, created_at, last_login_at)
            SELECT
                {sql_literal(str(uuid4()))},
                {sql_literal(admin_entra_oid)},
                {sql_literal(admin_email)},
                {sql_literal(admin_display_name)},
                {sql_literal(role)},
                true,
                current_timestamp(),
                NULL
            WHERE NOT EXISTS (
                SELECT 1 FROM {users_table}
                WHERE entra_oid = {sql_literal(admin_entra_oid)}
                   OR LOWER(email) = LOWER({sql_literal(admin_email)})
            )
            """,
        )

    print("OK — bootstrap admin users ensured")


def print_admin_table_status(cursor) -> None:
    print(f"\nDCM admin tables in `{catalog}`.`{schema}`...")
    cursor.execute(f"SHOW TABLES IN `{catalog}`.`{schema}` LIKE 'dcm_*'")
    found = sorted(row[1] for row in cursor.fetchall())
    for table_name in found:
        print(f"   - {table_name}")

    missing = sorted(set(ADMIN_TABLES) - set(found))
    if missing:
        print("Missing admin tables:")
        for table_name in missing:
            print(f"   - {table_name}")
        sys.exit(1)

    print(f"OK — {len(found)} admin tables")


def fetch_dim_landing_zone_rows(cursor) -> list[tuple]:
    table = qualified_table("dim_landing_zone")
    cursor.execute(
        f"""
        SELECT lz_id, cloud_provider, subscription_or_account_id, _ingested_at, lz_name
        FROM {table}
        ORDER BY lz_id
        """
    )
    return cursor.fetchall()


def clean_dim_landing_zone(cursor, *, apply: bool = False) -> None:
    """Remove stray landing zones from dim_landing_zone, keep prod LZ only."""
    table = qualified_table("dim_landing_zone")

    if not table_exists(cursor, "dim_landing_zone"):
        print(f"SKIP — {table} not found")
        return

    keep_literals = ", ".join(sql_literal(lz_id) for lz_id in KEEP_DIM_LANDING_ZONE_IDS)
    rows = fetch_dim_landing_zone_rows(cursor)
    to_remove = [row for row in rows if row[0] not in KEEP_DIM_LANDING_ZONE_IDS]
    to_keep = [row for row in rows if row[0] in KEEP_DIM_LANDING_ZONE_IDS]

    print(f"\nClean {table} — keep {', '.join(KEEP_DIM_LANDING_ZONE_IDS)}")
    print(f"Current rows ({len(rows)}):")
    for lz_id, cloud_provider, sub_id, ingested_at, lz_name in rows:
        marker = "KEEP" if lz_id in KEEP_DIM_LANDING_ZONE_IDS else "DROP"
        print(
            f"  [{marker}] {lz_id} | {cloud_provider} | "
            f"{sub_id or 'NULL'} | {ingested_at} | {lz_name}"
        )

    if not to_remove:
        print("OK — nothing to delete")
        return

    print(f"\nWill delete {len(to_remove)} row(s):")
    for lz_id, *_rest in to_remove:
        print(f"  - {lz_id}")

    missing_keep = sorted(set(KEEP_DIM_LANDING_ZONE_IDS) - {row[0] for row in to_keep})
    if missing_keep:
        print(
            "\nNote — expected LZ not present yet (no delete needed, "
            f"will appear after next DLT run): {', '.join(missing_keep)}"
        )

    if not apply:
        print("\nDRY RUN — pass --apply to execute DELETE")
        return

    execute_statement(
        cursor,
        f"""
        DELETE FROM {table}
        WHERE lz_id NOT IN ({keep_literals})
        """,
    )
    print("\nOK — dim_landing_zone cleaned")
    remaining = fetch_dim_landing_zone_rows(cursor)
    print(f"Remaining rows ({len(remaining)}):")
    for lz_id, cloud_provider, sub_id, ingested_at, lz_name in remaining:
        print(
            f"  - {lz_id} | {cloud_provider} | "
            f"{sub_id or 'NULL'} | {ingested_at} | {lz_name}"
        )


def delete_dim_landing_zone_null_subscription(cursor, *, apply: bool = False) -> None:
    """Delete dim_landing_zone rows where subscription_or_account_id IS NULL."""
    table = qualified_table("dim_landing_zone")

    if not table_exists(cursor, "dim_landing_zone"):
        print(f"SKIP — {table} not found")
        return

    rows = fetch_dim_landing_zone_rows(cursor)
    to_remove = [row for row in rows if row[2] is None]
    to_keep = [row for row in rows if row[2] is not None]

    print(f"\nDelete NULL subscription_or_account_id from {table}")
    print(f"Current rows ({len(rows)}):")
    for lz_id, cloud_provider, sub_id, ingested_at, lz_name in rows:
        marker = "DROP" if sub_id is None else "KEEP"
        print(
            f"  [{marker}] {lz_id} | {cloud_provider} | "
            f"{sub_id or 'NULL'} | {ingested_at} | {lz_name}"
        )

    if not to_remove:
        print("OK — no row with subscription_or_account_id IS NULL")
        return

    print(f"\nWill delete {len(to_remove)} row(s):")
    for lz_id, cloud_provider, *_rest in to_remove:
        print(f"  - {lz_id} ({cloud_provider})")

    print(f"Will keep {len(to_keep)} row(s) with subscription_or_account_id set")

    if not apply:
        print("\nDRY RUN — pass --apply to execute DELETE")
        return

    execute_statement(
        cursor,
        f"""
        DELETE FROM {table}
        WHERE subscription_or_account_id IS NULL
        """,
    )
    print("\nOK — NULL subscription rows deleted")
    remaining = fetch_dim_landing_zone_rows(cursor)
    print(f"Remaining rows ({len(remaining)}):")
    for lz_id, cloud_provider, sub_id, ingested_at, lz_name in remaining:
        print(
            f"  - {lz_id} | {cloud_provider} | "
            f"{sub_id or 'NULL'} | {ingested_at} | {lz_name}"
        )


@dataclass
class ProjectMigrationPlan:
    """Pure-Python migration plan — computed with no DB connection (unit-testable)."""

    projects_to_create: list[dict[str, str]] = field(default_factory=list)
    lz_scope_to_create: list[tuple[str, str]] = field(default_factory=list)
    members_to_add: list[dict[str, str]] = field(default_factory=list)
    admin_promotions: list[dict[str, str]] = field(default_factory=list)
    platform_role_updates: list[dict[str, str]] = field(default_factory=list)
    unresolved_lz_ids: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        """True if applying this plan would write anything (unresolved LZs are report-only)."""
        return bool(
            self.projects_to_create
            or self.lz_scope_to_create
            or self.members_to_add
            or self.admin_promotions
            or self.platform_role_updates
        )


def _resolve_lz_access_by_project(lz_access_rows, dim_landing_zone_rows, business_application_rows):
    """Group dcm_user_lz_access rows by resolved business_app_id (FR-016a: unresolved reported)."""
    lz_to_subscription = {
        row["lz_id"]: row["subscription_or_account_id"] for row in dim_landing_zone_rows
    }
    subscription_to_ba = {
        row["subscription_or_account_id"]: (
            row["business_application_id"],
            row["business_application_name"],
        )
        for row in business_application_rows
    }

    unresolved_lz_ids: set[str] = set()
    project_names: dict[str, str] = {}
    project_lz_ids: dict[str, set[str]] = defaultdict(set)
    project_user_earliest: dict[str, dict[str, object]] = defaultdict(dict)

    for row in lz_access_rows:
        lz_id = row["lz_id"]
        user_id = row["user_id"]
        granted_at = row["granted_at"]

        subscription_id = lz_to_subscription.get(lz_id)
        business_app = subscription_to_ba.get(subscription_id) if subscription_id else None
        if business_app is None:
            unresolved_lz_ids.add(lz_id)
            continue

        business_app_id, business_app_name = business_app
        project_names[business_app_id] = business_app_name
        project_lz_ids[business_app_id].add(lz_id)

        earliest = project_user_earliest[business_app_id].get(user_id)
        if earliest is None or granted_at < earliest:
            project_user_earliest[business_app_id][user_id] = granted_at

    return project_names, project_lz_ids, project_user_earliest, unresolved_lz_ids


def _plan_project_entries(
    *,
    project_names,
    project_lz_ids,
    project_user_earliest,
    existing_project_ids,
    existing_member_keys,
    existing_lz_scope_keys,
    existing_admin_project_ids,
):
    """Per-project diff against existing rows: projects/lz-scope/members/admin promotion."""
    projects_to_create: list[dict[str, str]] = []
    lz_scope_to_create: list[tuple[str, str]] = []
    members_to_add: list[dict[str, str]] = []
    admin_promotions: list[dict[str, str]] = []

    for project_id in sorted(project_names):
        if project_id not in existing_project_ids:
            projects_to_create.append(
                {
                    "id": project_id,
                    "business_app_id": project_id,
                    "name": project_names[project_id],
                }
            )

        for lz_id in sorted(project_lz_ids[project_id]):
            key = (project_id, lz_id)
            if key not in existing_lz_scope_keys:
                lz_scope_to_create.append(key)

        for user_id in sorted(project_user_earliest[project_id]):
            key = (project_id, user_id)
            if key not in existing_member_keys:
                members_to_add.append(
                    {"project_id": project_id, "user_id": user_id, "role": "viewer"}
                )

        if project_id not in existing_admin_project_ids:
            # Oldest granted_at wins; ties broken by user_id ascending (FR-017).
            oldest_user_id, _ = min(
                project_user_earliest[project_id].items(),
                key=lambda item: (item[1], item[0]),
            )
            admin_promotions.append({"project_id": project_id, "user_id": oldest_user_id})

    return projects_to_create, lz_scope_to_create, members_to_add, admin_promotions


def _plan_platform_role_updates(users_needing_platform_role) -> list[dict[str, str]]:
    """FR-006a compatibility mapping — only rows where platform_role IS NULL are passed in."""
    updates: list[dict[str, str]] = []
    for row in users_needing_platform_role:
        legacy_role = row["role"]
        platform_role = "super_admin" if legacy_role in LEGACY_SUPER_ADMIN_ROLES else "user"
        updates.append({"user_id": row["id"], "platform_role": platform_role})
    return updates


def build_project_migration_plan(
    *,
    lz_access_rows,
    dim_landing_zone_rows,
    business_application_rows,
    existing_project_ids,
    existing_member_keys,
    existing_lz_scope_keys,
    existing_admin_project_ids,
    users_needing_platform_role,
) -> ProjectMigrationPlan:
    """Resolve flat dcm_user_lz_access rows into per-BA projects (FR-016/016a/017/006a).

    All rows are plain dicts/tuples (no DB access here). Every ``existing_*``
    collection is what a re-run would already find in the tables, so passing
    the post-apply state back in makes the returned plan empty (idempotence,
    SC-002) except for the informational ``unresolved_lz_ids`` report.
    """
    project_names, project_lz_ids, project_user_earliest, unresolved_lz_ids = (
        _resolve_lz_access_by_project(
            lz_access_rows, dim_landing_zone_rows, business_application_rows
        )
    )

    projects_to_create, lz_scope_to_create, members_to_add, admin_promotions = (
        _plan_project_entries(
            project_names=project_names,
            project_lz_ids=project_lz_ids,
            project_user_earliest=project_user_earliest,
            existing_project_ids=set(existing_project_ids),
            existing_member_keys=set(existing_member_keys),
            existing_lz_scope_keys=set(existing_lz_scope_keys),
            existing_admin_project_ids=set(existing_admin_project_ids),
        )
    )

    return ProjectMigrationPlan(
        projects_to_create=projects_to_create,
        lz_scope_to_create=lz_scope_to_create,
        members_to_add=members_to_add,
        admin_promotions=admin_promotions,
        platform_role_updates=_plan_platform_role_updates(users_needing_platform_role),
        unresolved_lz_ids=sorted(unresolved_lz_ids),
    )


def apply_project_migration_plan(cursor, plan: ProjectMigrationPlan) -> None:
    """Execute the writes for an already-computed ProjectMigrationPlan (no planning here)."""
    projects_table = qualified_table("dcm_projects")
    lz_scope_table = qualified_table("dcm_project_lz_scope")
    members_table = qualified_table("dcm_project_members")
    users_table = qualified_table("dcm_app_users")

    for project in plan.projects_to_create:
        execute_statement(
            cursor,
            f"""
            INSERT INTO {projects_table} (
                id, name, business_app_id, status, entra_group_id,
                created_by, created_at, updated_at, validated_by, validated_at
            )
            SELECT
                {sql_literal(project["id"])},
                {sql_literal(project["name"])},
                {sql_literal(project["business_app_id"])},
                'active',
                NULL,
                NULL,
                current_timestamp(),
                current_timestamp(),
                NULL,
                NULL
            WHERE NOT EXISTS (
                SELECT 1 FROM {projects_table} WHERE id = {sql_literal(project["id"])}
            )
            """,
        )

    for project_id, lz_id in plan.lz_scope_to_create:
        execute_statement(
            cursor,
            f"""
            INSERT INTO {lz_scope_table} (project_id, lz_id, granted_by, granted_at)
            SELECT {sql_literal(project_id)}, {sql_literal(lz_id)}, NULL, current_timestamp()
            WHERE NOT EXISTS (
                SELECT 1 FROM {lz_scope_table}
                WHERE project_id = {sql_literal(project_id)} AND lz_id = {sql_literal(lz_id)}
            )
            """,
        )

    for member in plan.members_to_add:
        execute_statement(
            cursor,
            f"""
            INSERT INTO {members_table} (project_id, user_id, role, added_by, added_at)
            SELECT
                {sql_literal(member["project_id"])},
                {sql_literal(member["user_id"])},
                {sql_literal(member["role"])},
                NULL,
                current_timestamp()
            WHERE NOT EXISTS (
                SELECT 1 FROM {members_table}
                WHERE project_id = {sql_literal(member["project_id"])}
                  AND user_id = {sql_literal(member["user_id"])}
            )
            """,
        )

    for promotion in plan.admin_promotions:
        execute_statement(
            cursor,
            f"""
            UPDATE {members_table}
            SET role = 'admin'
            WHERE project_id = {sql_literal(promotion["project_id"])}
              AND user_id = {sql_literal(promotion["user_id"])}
              AND NOT EXISTS (
                  SELECT 1 FROM {members_table} existing_admin
                  WHERE existing_admin.project_id = {sql_literal(promotion["project_id"])}
                    AND existing_admin.role = 'admin'
              )
            """,
        )

    for update in plan.platform_role_updates:
        execute_statement(
            cursor,
            f"""
            UPDATE {users_table}
            SET platform_role = {sql_literal(update["platform_role"])}
            WHERE id = {sql_literal(update["user_id"])}
              AND platform_role IS NULL
            """,
        )


def _fetch_rows_as_dicts(cursor, query: str, columns: list[str]) -> list[dict]:
    cursor.execute(dedent(query).strip())
    return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]


def _fetch_project_migration_inputs(cursor) -> dict:
    """Read-only fetch of every row build_project_migration_plan needs."""
    ba_table_name = "dim_reference_landing_zone_business_application"
    if not table_exists(cursor, "dim_landing_zone") or not table_exists(cursor, ba_table_name):
        print(
            f"WARNING — dim_landing_zone or {ba_table_name} not found: "
            "every lz_id will be reported as unresolved this run"
        )
        dim_landing_zone_rows: list[dict] = []
        business_application_rows: list[dict] = []
    else:
        dim_landing_zone_rows = _fetch_rows_as_dicts(
            cursor,
            f"SELECT lz_id, subscription_or_account_id FROM {qualified_table('dim_landing_zone')}",
            ["lz_id", "subscription_or_account_id"],
        )
        business_application_rows = _fetch_rows_as_dicts(
            cursor,
            f"""
            SELECT subscription_or_account_id, business_application_id, business_application_name
            FROM {qualified_table(ba_table_name)}
            """,
            ["subscription_or_account_id", "business_application_id", "business_application_name"],
        )

    lz_access_rows = _fetch_rows_as_dicts(
        cursor,
        f"SELECT user_id, lz_id, granted_at FROM {qualified_table('dcm_user_lz_access')}",
        ["user_id", "lz_id", "granted_at"],
    )
    existing_project_ids = [
        row["id"]
        for row in _fetch_rows_as_dicts(
            cursor, f"SELECT id FROM {qualified_table('dcm_projects')}", ["id"]
        )
    ]
    existing_member_rows = _fetch_rows_as_dicts(
        cursor,
        f"SELECT project_id, user_id FROM {qualified_table('dcm_project_members')}",
        ["project_id", "user_id"],
    )
    existing_lz_scope_rows = _fetch_rows_as_dicts(
        cursor,
        f"SELECT project_id, lz_id FROM {qualified_table('dcm_project_lz_scope')}",
        ["project_id", "lz_id"],
    )
    existing_admin_project_ids = [
        row["project_id"]
        for row in _fetch_rows_as_dicts(
            cursor,
            f"""
            SELECT DISTINCT project_id FROM {qualified_table('dcm_project_members')}
            WHERE role = 'admin'
            """,
            ["project_id"],
        )
    ]
    users_needing_platform_role = _fetch_rows_as_dicts(
        cursor,
        f"""
        SELECT id, role FROM {qualified_table('dcm_app_users')}
        WHERE platform_role IS NULL
        """,
        ["id", "role"],
    )

    return {
        "lz_access_rows": lz_access_rows,
        "dim_landing_zone_rows": dim_landing_zone_rows,
        "business_application_rows": business_application_rows,
        "existing_project_ids": existing_project_ids,
        "existing_member_keys": [
            (row["project_id"], row["user_id"]) for row in existing_member_rows
        ],
        "existing_lz_scope_keys": [
            (row["project_id"], row["lz_id"]) for row in existing_lz_scope_rows
        ],
        "existing_admin_project_ids": existing_admin_project_ids,
        "users_needing_platform_role": users_needing_platform_role,
    }


def _print_project_migration_report(plan: ProjectMigrationPlan) -> None:
    """Console report shared by dry-run and --apply (printed before any write)."""
    print(f"Projects to create ({len(plan.projects_to_create)}):")
    for project in plan.projects_to_create:
        print(f"  - {project['id']} ({project['name']})")

    members_by_project: dict[str, list[dict]] = defaultdict(list)
    for member in plan.members_to_add:
        members_by_project[member["project_id"]].append(member)
    promotions_by_project = {p["project_id"]: p["user_id"] for p in plan.admin_promotions}

    print(f"Members to add ({len(plan.members_to_add)}):")
    for project_id, members in members_by_project.items():
        promoted = promotions_by_project.get(project_id)
        for member in members:
            marker = " -> auto-promoted admin" if member["user_id"] == promoted else ""
            print(f"  - project={project_id} user={member['user_id']} role=viewer{marker}")

    print(f"Admin auto-promotions ({len(plan.admin_promotions)}):")
    for promotion in plan.admin_promotions:
        print(f"  - project={promotion['project_id']} user={promotion['user_id']}")

    print(f"platform_role backfill ({len(plan.platform_role_updates)}):")
    for update in plan.platform_role_updates:
        print(f"  - user={update['user_id']} -> platform_role={update['platform_role']}")

    if plan.unresolved_lz_ids:
        print(
            f"Unresolved lz_id (no Business Application match) ({len(plan.unresolved_lz_ids)}):"
        )
        for lz_id in plan.unresolved_lz_ids:
            print(f"  - {lz_id}")


def migrate_flat_users_to_projects(cursor, *, apply: bool = False) -> None:
    """Group flat dcm_user_lz_access rows into default per-BA projects (FR-016/016a/017/006a)."""
    print("\nMigrate flat dcm_user_lz_access into default per-BA projects...")

    plan = build_project_migration_plan(**_fetch_project_migration_inputs(cursor))
    _print_project_migration_report(plan)

    if not apply:
        print("\nDRY RUN — pass --apply to execute")
        return

    if not plan.has_changes:
        print("\nOK — nothing to migrate")
        return

    apply_project_migration_plan(cursor, plan)
    print(
        f"\nOK — migrated {len(plan.projects_to_create)} project(s), "
        f"{len(plan.members_to_add)} member(s), {len(plan.admin_promotions)} promotion(s), "
        f"{len(plan.platform_role_updates)} platform_role backfill(s)"
    )


def ensure_gold_data_product_usage(cursor) -> None:
    """Create the backend serving table if the data product usage gold table is missing."""
    source_table = qualified_table("curated_activity_runs")
    target_table = qualified_table("gold_data_product_usage")

    print(f"\nEnsure `{catalog}`.`{schema}`.`gold_data_product_usage`...")
    if table_exists(cursor, "gold_data_product_usage"):
        print("OK — gold_data_product_usage already exists")
        return
    if not table_exists(cursor, "curated_activity_runs"):
        print(
            "SKIP — curated_activity_runs not found, cannot create gold_data_product_usage"
        )
        return

    print("Creating gold_data_product_usage from curated_activity_runs...")
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {target_table}
        USING DELTA
        AS
        SELECT
            CAST(COALESCE(end_time, start_time, collected_at) AS DATE) AS usage_date,
            COALESCE(pipeline_name, activity_name, 'unknown') AS data_product_id,
            COALESCE(pipeline_name, activity_name, 'Unknown data product') AS data_product_name,
            COALESCE(subscription_or_account_id, source_lz_id, 'unknown') AS consumer_id,
            COALESCE(subscription_or_account_id, source_lz_id, 'Unknown consumer') AS consumer_name,
            cloud_provider,
            source_lz_id,
            subscription_or_account_id,
            COUNT(*) AS request_count,
            SUM(COALESCE(rows_read, 0)) AS rows_read,
            SUM(COALESCE(rows_written, 0)) AS rows_written,
            SUM(COALESCE(data_read_bytes, 0)) AS data_read_bytes,
            SUM(COALESCE(data_written_bytes, 0)) AS data_written_bytes,
            SUM(COALESCE(duration_seconds, 0)) AS duration_seconds,
            CAST(0 AS DOUBLE) AS cost_usd,
            MAX(COALESCE(end_time, start_time, collected_at)) AS last_used_at
        FROM {source_table}
        GROUP BY
            CAST(COALESCE(end_time, start_time, collected_at) AS DATE),
            COALESCE(pipeline_name, activity_name, 'unknown'),
            COALESCE(pipeline_name, activity_name, 'Unknown data product'),
            COALESCE(subscription_or_account_id, source_lz_id, 'unknown'),
            COALESCE(subscription_or_account_id, source_lz_id, 'Unknown consumer'),
            cloud_provider,
            source_lz_id,
            subscription_or_account_id
        """
    )
    print("OK — gold_data_product_usage created")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DCM Unity Catalog utilities (SPN SQL Warehouse access)."
    )
    parser.add_argument(
        "--clean-dim-landing-zone",
        action="store_true",
        help="Delete dim_landing_zone rows except lz-aws-prod and lz-azure-prod.",
    )
    parser.add_argument(
        "--delete-dim-lz-null-subscription",
        action="store_true",
        help="Delete dim_landing_zone rows where subscription_or_account_id IS NULL.",
    )
    parser.add_argument(
        "--migrate-projects",
        action="store_true",
        help=(
            "Migrate dcm_user_lz_access flat access into default per-BA projects "
            "(dry-run by default, pass --apply to execute)."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Execute destructive actions (default is dry-run for cleanup).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    connect_kwargs: dict[str, object] = {
        "server_hostname": server_hostname,
        "http_path": http_path,
        "catalog": catalog,
        "schema": schema,
    }
    if access_token:
        connect_kwargs["access_token"] = access_token
    elif _profile_config is not None:
        connect_kwargs["credentials_provider"] = lambda: _profile_config.authenticate
    else:
        connect_kwargs["credentials_provider"] = credential_provider

    with sql.connect(**connect_kwargs) as connection:
        with connection.cursor() as cursor:
            print(f"\nCatalog '{catalog}'...")
            cursor.execute(f"SHOW CATALOGS LIKE '{catalog}'")
            if not cursor.fetchall():
                print(f"Catalog '{catalog}' not found")
                sys.exit(1)
            print(f"OK — catalog '{catalog}'")

            if args.clean_dim_landing_zone:
                clean_dim_landing_zone(cursor, apply=args.apply)
                return

            if args.delete_dim_lz_null_subscription:
                delete_dim_landing_zone_null_subscription(cursor, apply=args.apply)
                return

            if args.migrate_projects:
                migrate_flat_users_to_projects(cursor, apply=args.apply)
                return

            print(f"\nSchemas in '{catalog}' matching *monitoring*...")
            cursor.execute(f"SHOW SCHEMAS IN {catalog} LIKE '*monitoring*'")
            for row in cursor.fetchall():
                print(f"   - {row[0]}")

            print(f"\nTables in `{catalog}`.`{schema}`...")
            cursor.execute(f"SHOW TABLES IN `{catalog}`.`{schema}`")
            tables = cursor.fetchall()
            if not tables:
                print("No tables found yet — continuing with admin table creation")
            else:
                for t in tables:
                    print(f"   - {t[1]}")
            print(f"\nOK — {len(tables)} tables")

            ensure_gold_data_product_usage(cursor)
            create_admin_tables(cursor)
            create_project_tables(cursor)
            ensure_platform_role_column(cursor)
            ensure_decision_reason_columns(cursor)
            seed_embedded_dashboard_defaults(cursor)
            seed_admin_defaults(cursor)
            sync_role_permissions(cursor)
            bootstrap_admin_user(cursor)
            print_admin_table_status(cursor)

            print(f"\nTables in `{catalog}`.`{schema}` after gold/admin ensure...")
            cursor.execute(f"SHOW TABLES IN `{catalog}`.`{schema}`")
            tables = cursor.fetchall()
            for t in tables:
                print(f"   - {t[1]}")
            print(f"\nOK — {len(tables)} tables")

            # Liste toutes les colonnes de toutes les tables
            print(f"\nColonnes par table dans `{catalog}`.`{schema}` :")
            for t in tables:
                table_name = t[1]
                cursor.execute(f"DESCRIBE TABLE `{catalog}`.`{schema}`.`{table_name}`")
                columns = [row[0] for row in cursor.fetchall()]
                print(f"  - {table_name}: {columns}")

            # Aperçu de la première table
            first_table = tables[0][1]
            print(f"\nPreview `{first_table}` (5 rows)...")
            cursor.execute(
                f"SELECT * FROM `{catalog}`.`{schema}`.`{first_table}` LIMIT 5"
            )
            rows = cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            print("  Columns:", cols)
            for row in rows:
                print(" ", dict(zip(cols, row, strict=False)))


if __name__ == "__main__":
    main()
