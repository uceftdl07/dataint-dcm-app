"""Unit tests for the reduced 3-role model (feature 016, FR-006/FR-007, SC-003)."""

from __future__ import annotations

from app.auth.role_permissions import (
    DCM_EFFECTIVE_ROLES,
    map_effective_role,
    permissions_for_role,
)


def test_effective_roles_enumerate_to_exactly_three() -> None:
    # SC-003 — the assignable model is exactly {project viewer, project admin,
    # platform admin}.
    assert DCM_EFFECTIVE_ROLES == frozenset({"viewer", "admin", "super_admin"})
    assert len(DCM_EFFECTIVE_ROLES) == 3


def test_effective_roles_are_identity() -> None:
    for role in ("viewer", "admin", "super_admin"):
        assert map_effective_role(role) == role


def test_legacy_roles_map_to_project_viewer() -> None:
    # FR-007 — manager & data_architect become project viewer.
    assert map_effective_role("manager") == "viewer"
    assert map_effective_role("data_architect") == "viewer"


def test_pending_and_unknown_roles_have_no_effective_role() -> None:
    assert map_effective_role("pending") is None
    assert map_effective_role("nope") is None


def test_legacy_role_not_reexposed_as_own_permission_set() -> None:
    # A mapped legacy role resolves to the effective role's permissions, never a
    # distinct legacy permission set.
    assert permissions_for_role("manager") == permissions_for_role("viewer")
    assert permissions_for_role("data_architect") == permissions_for_role("viewer")


def test_projects_page_is_granted_to_every_effective_role() -> None:
    # The Projects page replaces the legacy "my-access" page: every effective
    # role must be able to reach it, otherwise the FE permission intersection
    # strips it and the tab reports "your role does not include projects".
    for role in ("viewer", "admin", "super_admin"):
        assert "page:projects" in permissions_for_role(role)["page"]
