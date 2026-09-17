"""Unit tests for the T001 project-access-governance migration in our_catalogs_spn.py.

our_catalogs_spn.py is a root standalone script (no package), and it exits at import
time if DCM_DATABRICKS_SPN_CLIENT_SECRET is unset (intentional guard for the smoke-test
script). Set the required env vars BEFORE importing it so the import succeeds without a
real Databricks connection.
"""

import os

os.environ.setdefault("DCM_DATABRICKS_SPN_CLIENT_SECRET", "test-secret")
os.environ.setdefault("DCM_DATABRICKS_SPN_CLIENT_ID", "test-client-id")

from datetime import datetime, timezone

import our_catalogs_spn as spn


def _dim_landing_zone_rows():
    return [
        {"lz_id": "lz-aws-1", "subscription_or_account_id": "sub-1"},
        {"lz_id": "lz-azure-1", "subscription_or_account_id": "sub-1"},
    ]


def _business_application_rows():
    return [
        {
            "subscription_or_account_id": "sub-1",
            "business_application_id": "ba-1",
            "business_application_name": "Business App One",
        }
    ]


def _lz_access_rows():
    return [
        {"user_id": "u1", "lz_id": "lz-aws-1", "granted_at": datetime(2024, 1, 1, tzinfo=timezone.utc)},
        {"user_id": "u2", "lz_id": "lz-azure-1", "granted_at": datetime(2024, 2, 1, tzinfo=timezone.utc)},
        # lz-missing is not in _dim_landing_zone_rows() -> must be reported, not raise.
        {"user_id": "u3", "lz_id": "lz-missing", "granted_at": datetime(2024, 3, 1, tzinfo=timezone.utc)},
    ]


def _first_run_plan(users_needing_platform_role=None):
    return spn.build_project_migration_plan(
        lz_access_rows=_lz_access_rows(),
        dim_landing_zone_rows=_dim_landing_zone_rows(),
        business_application_rows=_business_application_rows(),
        existing_project_ids=[],
        existing_member_keys=[],
        existing_lz_scope_keys=[],
        existing_admin_project_ids=[],
        users_needing_platform_role=users_needing_platform_role or [],
    )


class FakeCursor:
    """Records executed SQL strings; fetchall() unused by apply_project_migration_plan."""

    def __init__(self):
        self.executed: list[str] = []

    def execute(self, statement: str) -> None:
        self.executed.append(" ".join(statement.split()))

    def fetchall(self):
        return []


# --- (a) role mapping -------------------------------------------------------


def test_platform_role_mapping_legacy_super_admin_and_admin_map_to_super_admin():
    plan = _first_run_plan(
        users_needing_platform_role=[
            {"id": "u1", "role": "super_admin"},
            {"id": "u2", "role": "admin"},
        ]
    )
    updates = {u["user_id"]: u["platform_role"] for u in plan.platform_role_updates}
    assert updates == {"u1": "super_admin", "u2": "super_admin"}


def test_platform_role_mapping_data_architect_manager_viewer_map_to_user():
    plan = _first_run_plan(
        users_needing_platform_role=[
            {"id": "u4", "role": "data_architect"},
            {"id": "u5", "role": "manager"},
            {"id": "u6", "role": "viewer"},
        ]
    )
    updates = {u["user_id"]: u["platform_role"] for u in plan.platform_role_updates}
    assert updates == {"u4": "user", "u5": "user", "u6": "user"}


# --- (b) auto-promotion of the oldest member --------------------------------


def test_auto_promote_oldest_member_as_project_admin():
    plan = _first_run_plan()

    assert plan.projects_to_create == [
        {"id": "ba-1", "business_app_id": "ba-1", "name": "Business App One"}
    ]
    # u1 (2024-01-01) is older than u2 (2024-02-01) -> u1 is auto-promoted.
    assert plan.admin_promotions == [{"project_id": "ba-1", "user_id": "u1"}]
    member_roles = {m["user_id"]: m["role"] for m in plan.members_to_add}
    assert member_roles == {"u1": "viewer", "u2": "viewer"}


def test_auto_promote_tie_break_by_user_id_ascending():
    same_instant = datetime(2024, 1, 1, tzinfo=timezone.utc)
    plan = spn.build_project_migration_plan(
        lz_access_rows=[
            {"user_id": "zeta", "lz_id": "lz-aws-1", "granted_at": same_instant},
            {"user_id": "alpha", "lz_id": "lz-azure-1", "granted_at": same_instant},
        ],
        dim_landing_zone_rows=_dim_landing_zone_rows(),
        business_application_rows=_business_application_rows(),
        existing_project_ids=[],
        existing_member_keys=[],
        existing_lz_scope_keys=[],
        existing_admin_project_ids=[],
        users_needing_platform_role=[],
    )
    assert plan.admin_promotions == [{"project_id": "ba-1", "user_id": "alpha"}]


# --- (c) idempotence ---------------------------------------------------------


def test_second_run_plan_is_empty_once_everything_is_migrated():
    first_plan = _first_run_plan(
        users_needing_platform_role=[{"id": "u1", "role": "viewer"}]
    )

    second_plan = spn.build_project_migration_plan(
        lz_access_rows=_lz_access_rows(),
        dim_landing_zone_rows=_dim_landing_zone_rows(),
        business_application_rows=_business_application_rows(),
        existing_project_ids=[p["id"] for p in first_plan.projects_to_create],
        existing_member_keys=[
            (m["project_id"], m["user_id"]) for m in first_plan.members_to_add
        ],
        existing_lz_scope_keys=list(first_plan.lz_scope_to_create),
        existing_admin_project_ids=[
            p["project_id"] for p in first_plan.admin_promotions
        ],
        # Real fetch filters WHERE platform_role IS NULL, so a re-run naturally
        # returns nothing once the backfill has been applied.
        users_needing_platform_role=[],
    )

    assert second_plan.projects_to_create == []
    assert second_plan.lz_scope_to_create == []
    assert second_plan.members_to_add == []
    assert second_plan.admin_promotions == []
    assert second_plan.platform_role_updates == []
    assert second_plan.has_changes is False
    # Unresolved LZ report is informational, still surfaced, not a "change".
    assert second_plan.unresolved_lz_ids == ["lz-missing"]


def test_apply_project_migration_plan_issues_idempotent_sql():
    plan = spn.ProjectMigrationPlan(
        projects_to_create=[
            {"id": "ba-1", "business_app_id": "ba-1", "name": "Business App One"}
        ],
        lz_scope_to_create=[("ba-1", "lz-aws-1")],
        members_to_add=[{"project_id": "ba-1", "user_id": "u1", "role": "viewer"}],
        admin_promotions=[{"project_id": "ba-1", "user_id": "u1"}],
        platform_role_updates=[{"user_id": "u1", "platform_role": "user"}],
    )
    cursor = FakeCursor()

    spn.apply_project_migration_plan(cursor, plan)

    assert len(cursor.executed) == 5
    project_insert, lz_scope_insert, member_insert, promotion_update, role_update = (
        cursor.executed
    )
    assert "INSERT INTO" in project_insert
    assert "WHERE NOT EXISTS" in project_insert
    assert "INSERT INTO" in lz_scope_insert
    assert "WHERE NOT EXISTS" in lz_scope_insert
    assert "INSERT INTO" in member_insert
    assert "WHERE NOT EXISTS" in member_insert
    assert "UPDATE" in promotion_update
    assert "NOT EXISTS" in promotion_update
    assert "UPDATE" in role_update
    assert "platform_role IS NULL" in role_update


# --- (d) unresolved lz_id does not abort the migration -----------------------


def test_unresolved_lz_id_reported_and_does_not_abort_other_rows():
    plan = _first_run_plan()

    assert plan.unresolved_lz_ids == ["lz-missing"]
    # lz-aws-1 / lz-azure-1 still resolved into ba-1 despite the unresolved row.
    assert plan.projects_to_create == [
        {"id": "ba-1", "business_app_id": "ba-1", "name": "Business App One"}
    ]


def test_unresolved_when_subscription_has_no_business_application_match():
    plan = spn.build_project_migration_plan(
        lz_access_rows=[
            {"user_id": "u1", "lz_id": "lz-orphan", "granted_at": datetime(2024, 1, 1, tzinfo=timezone.utc)}
        ],
        dim_landing_zone_rows=[
            {"lz_id": "lz-orphan", "subscription_or_account_id": "sub-unknown"}
        ],
        business_application_rows=_business_application_rows(),  # no "sub-unknown"
        existing_project_ids=[],
        existing_member_keys=[],
        existing_lz_scope_keys=[],
        existing_admin_project_ids=[],
        users_needing_platform_role=[],
    )
    assert plan.unresolved_lz_ids == ["lz-orphan"]
    assert plan.projects_to_create == []
    assert plan.has_changes is False
