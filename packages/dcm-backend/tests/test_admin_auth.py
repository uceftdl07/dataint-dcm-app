"""Tests for DCM auth guards and first admin routes."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.main import app


@pytest.fixture(autouse=True)
def auth_disabled() -> Iterator[None]:
    settings = app.state.settings
    original = settings.auth_disabled
    settings.auth_disabled = True
    try:
        yield
    finally:
        settings.auth_disabled = original


def _admin_headers(**overrides: str) -> dict[str, str]:
    headers = {
        "x-dcm-role": "super_admin",
        "x-dcm-user-id": "admin-001",
        "x-dcm-entra-oid": "entra-admin-001",
        "x-dcm-email": "admin@example.com",
        "x-dcm-display-name": "DCM Admin",
    }
    headers.update(overrides)
    return headers


def _user_row(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": "user-001",
        "entra_oid": "entra-user-001",
        "email": "user@example.com",
        "display_name": "DCM User",
        "role": "viewer",
        "is_active": True,
        "created_at": datetime(2026, 5, 27, 10, 0, tzinfo=UTC),
        "last_login_at": None,
        "lz_ids": ["lz-001"],
    }
    base.update(overrides)
    return base


def _lz_row(**overrides: Any) -> dict[str, Any]:
    base = {
        "lz_id": "lz-001",
        "display_name": "Landing Zone 001",
        "cloud_provider": "azure",
        "region": "westeurope",
        "environment": "prod",
        "ba_name": "Data",
        "collector_names": ["azure-collector"],
        "is_active": True,
        "registered_at": datetime(2026, 5, 27, 10, 0, tzinfo=UTC),
        "registered_by": "admin-001",
        "notes": "Managed by DCM",
        "user_count": 2,
    }
    base.update(overrides)
    return base


async def test_auth_me_returns_dev_user(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/auth/me",
        headers=_admin_headers(**{"x-dcm-lz-ids": "lz-001,lz-002"}),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "admin-001"
    assert body["role"] == "super_admin"
    assert body["lz_ids"] == ["lz-001", "lz-002"]


async def test_admin_users_requires_platform_admin(client: AsyncClient) -> None:
    """A legacy data-admin is not a platform admin — the administration API is
    guarded by ``platform_role``, not by the lifecycle ``role`` column."""
    resp = await client.get("/api/v1/admin/users", headers={"x-dcm-role": "admin"})

    assert resp.status_code == 403
    assert resp.json()["detail"] == "platform_admin role required"


async def test_admin_users_blocks_viewer_role(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/admin/users", headers={"x-dcm-role": "viewer"})

    assert resp.status_code == 403
    assert resp.json()["detail"] == "platform_admin role required"


async def test_admin_users_allows_platform_role_header(client: AsyncClient) -> None:
    """``platform_role = super_admin`` alone opens the administration API, even
    when the lifecycle role is a plain viewer."""
    resp = await client.get(
        "/api/v1/admin/users",
        headers={"x-dcm-role": "viewer", "x-dcm-platform-role": "super_admin"},
    )

    assert resp.status_code != 403


async def test_admin_users_list_serializes_lz_access(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchall.side_effect = [
        [_user_row()],
        [
            {
                "user_id": "user-001",
                "project_id": "proj-1",
                "name": "Payments",
                "role": "admin",
                "status": "active",
            }
        ],
    ]
    mock_db.fetchscalar.return_value = 1

    resp = await client.get("/api/v1/admin/users", headers=_admin_headers())

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["email"] == "user@example.com"
    assert body["items"][0]["lz_ids"] == ["lz-001"]
    assert body["items"][0]["projects"] == [
        {"id": "proj-1", "name": "Payments", "role": "admin", "status": "active"}
    ]


async def test_admin_replace_user_projects_sets_membership(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchone.side_effect = [_user_row(), _user_row()]
    mock_db.fetchall.side_effect = [
        [],  # memberships before (none)
        [{"id": "proj-1"}],  # _validate_project_ids
        [
            {
                "user_id": "user-001",
                "project_id": "proj-1",
                "name": "Payments",
                "role": "viewer",
                "status": "active",
            }
        ],  # memberships after
    ]

    resp = await client.put(
        "/api/v1/admin/users/user-001/projects",
        headers=_admin_headers(),
        json={"projects": [{"project_id": "proj-1", "role": "viewer"}]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["projects"] == [
        {"id": "proj-1", "name": "Payments", "role": "viewer", "status": "active"}
    ]
    insert_calls = [
        call.args[0]
        for call in mock_db.execute.await_args_list
        if "INSERT INTO" in call.args[0] and "dcm_project_members" in call.args[0]
    ]
    assert insert_calls, "expected a membership INSERT"


async def test_create_admin_user_by_email_writes_audit_log(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchone.return_value = None

    resp = await client.post(
        "/api/v1/admin/users",
        headers=_admin_headers(),
        json={
            "email": "AL1127809@admin.hubtotal.net",
            "display_name": "AL1127809 Admin",
            "role": "admin",
            "lz_ids": [],
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "al1127809@admin.hubtotal.net"
    assert body["role"] == "admin"
    assert body["entra_oid"] == "email:al1127809@admin.hubtotal.net"
    assert mock_db.execute.await_count == 3
    assert "INSERT INTO" in mock_db.execute.await_args_list[0].args[0]
    assert mock_db.execute.await_args_list[1].args[3] == "user.create"
    assert "dcm_access_requests" in mock_db.execute.await_args_list[2].args[0]


async def test_create_admin_user_rejects_duplicate_email(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchone.return_value = {"id": "existing-user"}

    resp = await client.post(
        "/api/v1/admin/users",
        headers=_admin_headers(),
        json={"email": "user@example.com", "role": "viewer"},
    )

    assert resp.status_code == 409


async def test_update_user_role_writes_audit_log(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchone.return_value = _user_row()

    resp = await client.patch(
        "/api/v1/admin/users/user-001/role",
        headers=_admin_headers(),
        json={"role": "viewer"},
    )

    assert resp.status_code == 200
    assert resp.json()["role"] == "viewer"
    assert mock_db.execute.await_count == 2
    audit_query = mock_db.execute.await_args_list[-1].args[0]
    assert "dcm_audit_log" in audit_query
    assert mock_db.execute.await_args_list[-1].args[2] == "admin-001"
    assert mock_db.execute.await_args_list[-1].args[3] == "user.role.update"


async def test_promoting_to_platform_admin_writes_platform_role(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    """Promotion must set ``platform_role``: it is what every administration guard
    reads. Writing only ``role`` granted ``/admin`` while still 403-ing on project
    validation and scope decisions."""
    mock_db.fetchone.return_value = _user_row()

    resp = await client.patch(
        "/api/v1/admin/users/user-001/role",
        headers=_admin_headers(),
        json={"role": "super_admin"},
    )

    assert resp.status_code == 200
    assert resp.json()["platform_role"] == "super_admin"
    update_query, *update_args = mock_db.execute.await_args_list[0].args
    assert "platform_role = ?" in update_query
    assert update_args == ["super_admin", "super_admin", "user-001"]


async def test_demoting_to_member_clears_platform_role(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchone.return_value = _user_row(role="super_admin", platform_role="super_admin")

    resp = await client.patch(
        "/api/v1/admin/users/user-001/role",
        headers=_admin_headers(),
        json={"role": "viewer"},
    )

    assert resp.status_code == 200
    assert resp.json()["platform_role"] == "user"
    assert mock_db.execute.await_args_list[0].args[2] == "user"


async def test_admin_cannot_demote_themselves(client: AsyncClient) -> None:
    resp = await client.patch(
        "/api/v1/admin/users/admin-001/role",
        headers=_admin_headers(),
        json={"role": "viewer"},
    )

    assert resp.status_code == 400
    assert "own platform admin tier" in resp.json()["detail"]


async def test_legacy_super_admin_row_reports_as_platform_admin(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    """Rows predating the ``platform_role`` backfill keep their authority, so the
    transition never locks an existing super admin out."""
    mock_db.fetchall.side_effect = [
        [_user_row(role="super_admin", platform_role=None)],
        [],  # no project membership
    ]
    mock_db.fetchscalar.return_value = 1

    resp = await client.get("/api/v1/admin/users", headers=_admin_headers())

    assert resp.status_code == 200
    assert resp.json()["items"][0]["platform_role"] == "super_admin"


async def test_delete_user_removes_access_granting_rows(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchone.return_value = _user_row()

    resp = await client.delete(
        "/api/v1/admin/users/user-001",
        headers=_admin_headers(),
    )

    assert resp.status_code == 204
    deleted_from = [
        call.args[0]
        for call in mock_db.execute.await_args_list
        if call.args and str(call.args[0]).startswith("DELETE")
    ]
    assert len(deleted_from) == 5  # memberships, join requests, lz access, prefs, user
    assert any("dcm_project_members" in query for query in deleted_from)
    audit_query = mock_db.execute.await_args_list[0].args[0]
    assert "dcm_audit_log" in audit_query  # written before the row disappears


async def test_delete_user_rejects_self_deletion(client: AsyncClient) -> None:
    resp = await client.delete(
        "/api/v1/admin/users/admin-001",
        headers=_admin_headers(),
    )

    assert resp.status_code == 400
    assert "cannot delete" in resp.json()["detail"]


async def test_delete_last_platform_admin_conflicts(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    """Deleting the only platform admin would lock the platform out of its own
    administration."""
    mock_db.fetchone.return_value = _user_row(role="super_admin", platform_role="super_admin")
    mock_db.fetchscalar.return_value = 0

    resp = await client.delete(
        "/api/v1/admin/users/user-001",
        headers=_admin_headers(),
    )

    assert resp.status_code == 409
    assert "last platform admin" in resp.json()["detail"]


async def test_deactivate_user_rejects_self_deactivation(client: AsyncClient) -> None:
    resp = await client.patch(
        "/api/v1/admin/users/admin-001/deactivate",
        headers=_admin_headers(),
    )

    assert resp.status_code == 400
    assert "cannot deactivate" in resp.json()["detail"]


async def test_list_landing_zones_returns_user_count(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchall.return_value = [_lz_row()]

    resp = await client.get("/api/v1/admin/landing-zones", headers=_admin_headers())

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["lz_id"] == "lz-001"
    assert body["items"][0]["user_count"] == 2


async def test_create_landing_zone_rejects_duplicate(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchone.return_value = _lz_row()

    resp = await client.post(
        "/api/v1/admin/landing-zones",
        headers=_admin_headers(),
        json={
            "lz_id": "lz-001",
            "display_name": "Landing Zone 001",
            "cloud_provider": "azure",
        },
    )

    assert resp.status_code == 409


async def test_create_landing_zone_validates_lz_id(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/admin/landing-zones",
        headers=_admin_headers(),
        json={
            "lz_id": "Invalid LZ",
            "display_name": "Invalid",
            "cloud_provider": "azure",
        },
    )

    assert resp.status_code == 422
