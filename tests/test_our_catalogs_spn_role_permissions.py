"""Unit tests for the dcm_role_permissions convergence in our_catalogs_spn.py.

our_catalogs_spn.py is a root standalone script (no package) that exits at import
time without DCM_DATABRICKS_SPN_CLIENT_SECRET, so the env vars are set BEFORE the
import — same guard as test_our_catalogs_spn_migration.py.
"""

import os

os.environ.setdefault("DCM_DATABRICKS_SPN_CLIENT_SECRET", "test-secret")
os.environ.setdefault("DCM_DATABRICKS_SPN_CLIENT_ID", "test-client-id")

import our_catalogs_spn as spn
from app.auth.role_permissions import DEFAULT_ROLE_PERMISSIONS


class FakeCursor:
    """Records executed SQL strings; apply_role_permission_sync_plan never reads."""

    def __init__(self):
        self.executed: list[str] = []

    def execute(self, statement: str) -> None:
        self.executed.append(" ".join(statement.split()))

    def fetchall(self):
        return []


def _rows(*keys, is_allowed: bool = True) -> list[dict]:
    return [
        {
            "role": role,
            "resource_type": resource_type,
            "resource_key": resource_key,
            "is_allowed": is_allowed,
        }
        for role, resource_type, resource_key in keys
    ]


def _defaults_for(role: str) -> set[tuple[str, str, str]]:
    return {row for row in spn.ROLE_PERMISSION_DEFAULTS if row[0] == role}


# --- (a) the seeded defaults must match what the API falls back to -----------


def test_seeded_defaults_match_the_api_defaults_for_every_effective_role():
    """The two sets are the same grant expressed twice — drift silently hides pages.

    ``get_role_permissions`` lets a non-empty table win over
    ``DEFAULT_ROLE_PERMISSIONS``, so a seed set narrower than the in-code one is
    not a cosmetic difference: it removes interfaces from project members.
    """
    for role in spn.SYNCED_PERMISSION_ROLES:
        seeded = {(resource_type, key) for _role, resource_type, key in _defaults_for(role)}
        expected = {
            (resource_type, key)
            for resource_type, keys in DEFAULT_ROLE_PERMISSIONS[role].items()
            for key in keys
        }
        assert seeded == expected, role


def test_viewer_reads_every_data_interface_except_the_unscopeable_explorer():
    viewer_pages = {key for _r, resource_type, key in _defaults_for("viewer") if resource_type == "page"}

    assert "page:unity-catalog" not in viewer_pages
    for page in ("page:dashboard", "page:databricks", "page:databases", "page:costs"):
        assert page in viewer_pages


# --- (b) convergence plan ----------------------------------------------------


def test_stale_table_is_converged_in_both_directions():
    """A table seeded by an older revision is missing grants AND holds dead ones."""
    plan = spn.build_role_permission_sync_plan(
        existing_rows=_rows(
            ("viewer", "page", "page:dashboard"),
            # Dead key: no route has mapped page:my-access since feature 015.
            ("viewer", "page", "page:my-access"),
            ("admin", "page", "page:my-access"),
        )
    )

    assert plan.has_changes is True
    assert plan.rows_to_delete == [
        ("admin", "page", "page:my-access"),
        ("viewer", "page", "page:my-access"),
    ]
    assert ("viewer", "page", "page:databricks") in plan.rows_to_insert
    assert ("admin", "page", "page:unity-catalog") in plan.rows_to_insert
    assert ("viewer", "page", "page:dashboard") not in plan.rows_to_insert


def test_legacy_roles_are_left_untouched_during_the_transition():
    plan = spn.build_role_permission_sync_plan(
        existing_rows=_rows(
            ("data_architect", "page", "page:my-access"),
            ("manager", "page", "page:my-access"),
            ("pending", "page", "page:dashboard"),
        )
    )

    touched = {row[0] for row in plan.rows_to_insert + plan.rows_to_allow + plan.rows_to_delete}
    assert touched <= set(spn.SYNCED_PERMISSION_ROLES)
    assert not any(row[0] == "data_architect" for row in plan.rows_to_delete)


def test_revoked_row_is_re_allowed_rather_than_re_inserted():
    """is_allowed = FALSE is what the API filters on, so the row existing is not enough."""
    plan = spn.build_role_permission_sync_plan(
        existing_rows=_rows(("viewer", "page", "page:dashboard"), is_allowed=False)
    )

    assert plan.rows_to_allow == [("viewer", "page", "page:dashboard")]
    assert ("viewer", "page", "page:dashboard") not in plan.rows_to_insert


def test_duplicate_pair_with_one_allowed_row_needs_no_re_grant():
    key = ("viewer", "page", "page:dashboard")
    plan = spn.build_role_permission_sync_plan(
        existing_rows=_rows(key, is_allowed=False) + _rows(key, is_allowed=True)
    )

    assert plan.rows_to_allow == []
    assert key not in plan.rows_to_insert


def test_plan_is_empty_once_the_table_matches_the_defaults():
    plan = spn.build_role_permission_sync_plan(
        existing_rows=_rows(
            *(
                row
                for row in spn.ROLE_PERMISSION_DEFAULTS
                if row[0] in spn.SYNCED_PERMISSION_ROLES
            )
        )
    )

    assert plan.rows_to_insert == []
    assert plan.rows_to_allow == []
    assert plan.rows_to_delete == []
    assert plan.has_changes is False


# --- (c) writes --------------------------------------------------------------


def test_apply_issues_one_idempotent_statement_per_row():
    plan = spn.RolePermissionSyncPlan(
        rows_to_insert=[("viewer", "page", "page:databricks")],
        rows_to_allow=[("viewer", "page", "page:dashboard")],
        rows_to_delete=[("admin", "page", "page:my-access")],
    )
    cursor = FakeCursor()

    spn.apply_role_permission_sync_plan(cursor, plan)

    insert, update, delete = cursor.executed
    assert insert.startswith("INSERT INTO")
    assert "WHERE NOT EXISTS" in insert
    assert "'page:databricks'" in insert
    assert update.startswith("UPDATE")
    assert "SET is_allowed = TRUE" in update
    assert "AND is_allowed = FALSE" in update
    assert delete.startswith("DELETE FROM")
    assert "role = 'admin'" in delete
    assert "resource_key = 'page:my-access'" in delete


def test_apply_writes_nothing_for_an_empty_plan():
    cursor = FakeCursor()

    spn.apply_role_permission_sync_plan(cursor, spn.RolePermissionSyncPlan())

    assert cursor.executed == []
