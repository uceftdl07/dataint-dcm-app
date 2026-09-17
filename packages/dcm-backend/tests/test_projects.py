"""Route tests for the project access-governance API (feature 015)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

_SUPER_ADMIN = {"x-dcm-user-id": "admin-1", "x-dcm-platform-role": "super_admin"}
_USER = {"x-dcm-user-id": "user-1", "x-dcm-platform-role": "user"}


def _project_row(status: str = "active") -> dict[str, object]:
    return {
        "id": "ba-42",
        "name": "BA Payments",
        "business_app_id": "ba-42",
        "status": status,
        "created_by": "user-1",
        "created_at": datetime.now(UTC),
        "validated_by": None,
        "validated_at": None,
        "decision_reason": None,
    }


async def test_me_exposes_platform_role_and_projects(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchall.return_value = [
        {"project_id": "ba-42", "name": "BA Payments", "role": "admin", "status": "active"}
    ]
    resp = await client.get("/api/v1/auth/me", headers=_SUPER_ADMIN)
    assert resp.status_code == 200
    body = resp.json()
    assert body["platform_role"] == "super_admin"
    assert body["projects"][0]["project_id"] == "ba-42"
    assert body["projects"][0]["role"] == "admin"
    assert body["scope"]["unrestricted"] is True


async def test_me_reports_the_effective_read_scope(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """A member must be able to see which scope is applied to their reads."""
    mock_db.fetchall.return_value = []
    resp = await client.get(
        "/api/v1/auth/me",
        headers={
            "x-dcm-role": "viewer",
            "x-dcm-lz-ids": "lz-001,lz-002",
            "x-dcm-workspace-ids": "adb-123",
        },
    )
    assert resp.status_code == 200
    scope = resp.json()["scope"]
    assert scope["unrestricted"] is False
    assert scope["lz_ids"] == ["lz-001", "lz-002"]
    # Canonical form: the same workspace is `adb-123` or `123` depending on source.
    assert scope["workspace_ids"] == ["123"]


async def test_create_project_conflict_when_business_app_taken(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.return_value = {"id": "ba-42"}
    resp = await client.post(
        "/api/v1/projects",
        headers=_USER,
        json={"businessAppId": "ba-42", "name": "BA Payments"},
    )
    assert resp.status_code == 409


async def test_create_project_pending_validation(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.return_value = None
    resp = await client.post(
        "/api/v1/projects",
        headers=_USER,
        json={
            "businessAppId": "ba-42",
            "name": "BA Payments",
            "lzScope": ["lz-a"],
            "dbxScope": ["ws-1"],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending_validation"
    assert body["lzScope"] == ["lz-a"]
    assert body["dbxScope"] == ["ws-1"]


async def test_validate_project_activates_and_adds_creator(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    # _load_project_row → pending project ; _member_role(creator) → None
    mock_db.fetchone.side_effect = [_project_row(status="pending_validation"), None]
    # members to activate, then the two scope reads and the LZ resolution
    mock_db.fetchall.side_effect = [[{"user_id": "user-1"}], [], [], []]
    resp = await client.post("/api/v1/projects/ba-42/validate", headers=_SUPER_ADMIN)
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"
    # project update + creator insert + member activation + audit → executes issued
    assert mock_db.execute.await_count >= 4


async def test_validate_project_rejected_for_non_platform_admin(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    resp = await client.post("/api/v1/projects/ba-42/validate", headers=_USER)
    assert resp.status_code == 403


async def test_list_projects_exposes_scope_and_member_count(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """The administration table needs what a project grants, without N+1 calls."""
    mock_db.fetchall.return_value = [
        {
            "id": "ba-42",
            "name": "BA Payments",
            "business_app_id": "ba-42",
            "status": "active",
            "role": "admin",
            "lz_scope": ["lz-b", "lz-a"],
            "dbx_scope": '["ws-1"]',  # driver may hand back the JSON encoding
            "member_count": 3,
        }
    ]
    resp = await client.get("/api/v1/projects", headers=_SUPER_ADMIN)
    assert resp.status_code == 200
    project = resp.json()[0]
    assert project["lzScope"] == ["lz-a", "lz-b"]
    assert project["dbxScope"] == ["ws-1"]
    assert project["memberCount"] == 3


async def test_list_projects_parses_the_numpy_array_the_driver_returns(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """``collect_set`` comes back as a ``numpy.ndarray`` on the Arrow fetch path.

    An ndarray is not a ``list``, so the administration table advertised "No LZ"
    for every project while ``dcm_project_lz_scope`` was fully populated.
    """
    numpy = pytest.importorskip("numpy")
    mock_db.fetchall.return_value = [
        {
            "id": "ba-42",
            "name": "BA Payments",
            "business_app_id": "ba-42",
            "status": "active",
            "role": "admin",
            "lz_scope": numpy.array(["lz-b", "lz-a"], dtype=object),
            "dbx_scope": numpy.array(["ws-1"], dtype=object),
            "member_count": 2,
        }
    ]
    resp = await client.get("/api/v1/projects", headers=_SUPER_ADMIN)
    assert resp.status_code == 200
    project = resp.json()[0]
    assert project["lzScope"] == ["lz-a", "lz-b"]
    assert project["dbxScope"] == ["ws-1"]


async def test_list_projects_exposes_the_resolved_lz_scope(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """The selector needs the landing zones a project *matches*, not what it stores.

    ``dcm_project_lz_scope`` may hold a subscription id, and a workspace-only
    project stores no LZ at all. Intersecting the header's landing-zone list with
    the raw column therefore yielded an empty selector while the project did have
    a scope — anomaly 2.
    """
    mock_db.fetchall.side_effect = [
        [
            {
                "id": "ba-42",
                "name": "BA Payments",
                "business_app_id": "ba-42",
                "status": "active",
                "role": "admin",
                "lz_scope": ["sub-0001"],
                "dbx_scope": ["adb-111"],
                "member_count": 3,
            }
        ],
        [
            {"project_id": "ba-42", "lz_id": "lz-north"},
            {"project_id": "ba-42", "lz_id": "lz-south"},
            {"project_id": "other", "lz_id": "lz-east"},
        ],
    ]
    resp = await client.get("/api/v1/projects", headers=_SUPER_ADMIN)
    assert resp.status_code == 200
    project = resp.json()[0]
    # The registered value stays addressable for scope mutations…
    assert project["lzScope"] == ["sub-0001"]
    # …while the resolved ids are what a monitoring filter can match.
    assert project["effectiveLzScope"] == ["lz-north", "lz-south"]


async def test_list_projects_resolves_scopes_in_one_statement(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """No N+1: one resolution query covers the whole page of projects."""
    mock_db.fetchall.side_effect = [
        [
            {
                "id": f"ba-{index}",
                "name": f"BA {index}",
                "business_app_id": f"ba-{index}",
                "status": "active",
                "role": "viewer",
                "lz_scope": [],
                "dbx_scope": [],
                "member_count": 1,
            }
            for index in range(3)
        ],
        [{"project_id": "ba-1", "lz_id": "lz-north"}],
    ]
    resp = await client.get("/api/v1/projects", headers=_SUPER_ADMIN)
    assert resp.status_code == 200
    assert mock_db.fetchall.await_count == 2
    by_id = {project["id"]: project for project in resp.json()}
    assert by_id["ba-1"]["effectiveLzScope"] == ["lz-north"]
    assert by_id["ba-0"]["effectiveLzScope"] == []


async def test_list_projects_skips_resolution_when_there_is_no_project(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """An empty page must not build ``IN ()`` — the warehouse would reject it."""
    mock_db.fetchall.return_value = []
    resp = await client.get("/api/v1/projects", headers=_SUPER_ADMIN)
    assert resp.status_code == 200
    assert resp.json() == []
    assert mock_db.fetchall.await_count == 1


async def test_get_project_counts_its_members(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """The detail payload carries the same member count as the list payload.

    Without its own count the field fell back to its ``0`` default, so a project
    with members advertised none on the wire.
    """
    # _load_project_row → project ; _member_role(caller) → admin
    mock_db.fetchone.side_effect = [_project_row(), {"role": "admin"}]
    mock_db.fetchall.side_effect = [
        [{"lz_id": "lz-a"}],
        [{"workspace_id": "ws-1"}],
        [{"project_id": "ba-42", "lz_id": "lz-a"}],
    ]
    mock_db.fetchscalar.return_value = 3
    resp = await client.get("/api/v1/projects/ba-42", headers=_SUPER_ADMIN)
    assert resp.status_code == 200
    body = resp.json()
    assert body["memberCount"] == 3
    assert body["lzScope"] == ["lz-a"]
    assert body["dbxScope"] == ["ws-1"]


async def test_reject_project_records_reason(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.side_effect = [_project_row(status="pending_validation")]
    resp = await client.post(
        "/api/v1/projects/ba-42/reject",
        headers=_SUPER_ADMIN,
        json={"reason": "Duplicate of an existing initiative"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["decisionReason"] == "Duplicate of an existing initiative"


async def test_reject_project_requires_a_reason(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    resp = await client.post(
        "/api/v1/projects/ba-42/reject", headers=_SUPER_ADMIN, json={"reason": ""}
    )
    assert resp.status_code == 422


async def test_reject_project_requires_platform_admin(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    resp = await client.post(
        "/api/v1/projects/ba-42/reject", headers=_USER, json={"reason": "nope"}
    )
    assert resp.status_code == 403


async def test_reject_project_only_when_pending(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.side_effect = [_project_row(status="active")]
    resp = await client.post(
        "/api/v1/projects/ba-42/reject", headers=_SUPER_ADMIN, json={"reason": "late"}
    )
    assert resp.status_code == 409


async def test_rejection_frees_the_business_application(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """A rejected project no longer blocks its BA, and its stale row is purged so
    the re-created project is not shadowed by a duplicate ``id``."""
    mock_db.fetchone.side_effect = [
        None,               # BA uniqueness check → free (rejected is not counted)
        {"id": "ba-42"},    # _purge_rejected_project → a rejected row is there
    ]
    resp = await client.post(
        "/api/v1/projects",
        headers=_USER,
        json={"businessAppId": "ba-42", "name": "BA Payments", "lzScope": ["lz-a"]},
    )
    assert resp.status_code == 201
    deletes = [
        call.args[0]
        for call in mock_db.execute.await_args_list
        if call.args and str(call.args[0]).lstrip().startswith("DELETE")
    ]
    assert len(deletes) == 6  # 5 child tables + the project row


async def test_join_a_rejected_project_conflicts(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.side_effect = [_project_row(status="rejected")]
    resp = await client.post(
        "/api/v1/projects/join",
        headers={"x-dcm-email": "newbie@example.com"},
        json={"projectId": "ba-42"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "project_not_joinable"


async def test_global_join_request_queue_requires_platform_admin(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    resp = await client.get("/api/v1/join-requests", headers=_USER)
    assert resp.status_code == 403


async def test_global_join_request_queue_lists_every_pending_request(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchall.return_value = [
        {
            "id": "jr-1",
            "project_id": "ba-42",
            "user_id": "user-9",
            "display_name": "New Joiner",
            "requested_role": "viewer",
            "status": "pending",
            "justification": "Need the Payments scope",
            "requested_at": datetime.now(UTC),
        }
    ]
    resp = await client.get("/api/v1/join-requests", headers=_SUPER_ADMIN)
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["projectId"] == "ba-42"
    assert body[0]["displayName"] == "New Joiner"


async def test_rejecting_a_request_requires_a_reason(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """The requester is told why — a refusal never silently disappears."""
    resp = await client.post(
        "/api/v1/scope-requests/sr-1/decide",
        headers=_SUPER_ADMIN,
        json={"decision": "rejected"},
    )
    assert resp.status_code == 422


async def test_remove_last_admin_conflicts(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.side_effect = [
        {"has_admin": 1},        # require_project_admin.is_project_admin
        _project_row(),          # _load_project_row
        {"role": "admin"},       # _member_role(target)
        {"admin_count": 1},      # _count_admins
    ]
    resp = await client.request(
        "DELETE",
        "/api/v1/projects/ba-42/members/user-1",
        headers=_USER,
    )
    assert resp.status_code == 409


async def test_add_member_provisions_and_activates(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    # _load_project_row ; _ensure_app_user(miss) ; _member_role(not a member)
    mock_db.fetchone.side_effect = [_project_row(), None, None]
    resp = await client.post(
        "/api/v1/projects/ba-42/members",
        headers=_SUPER_ADMIN,  # super_admin bypasses project-admin guard
        json={"email": "New.Member@example.com", "role": "viewer"},
    )
    assert resp.status_code == 201
    assert resp.json()["role"] == "viewer"
    # app-user stub + member insert + activation + audit
    assert mock_db.execute.await_count == 4


async def test_add_member_conflict_when_already_member(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    # _load_project_row ; _ensure_app_user(hit) ; _member_role(already viewer)
    mock_db.fetchone.side_effect = [
        _project_row(),
        {"id": "user-9"},
        {"role": "viewer"},
    ]
    resp = await client.post(
        "/api/v1/projects/ba-42/members",
        headers=_SUPER_ADMIN,
        json={"email": "existing@example.com", "role": "admin"},
    )
    assert resp.status_code == 409


async def test_decide_join_request_approved_adds_member(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.side_effect = [
        {  # the join request row
            "id": "jr-1",
            "project_id": "ba-42",
            "user_id": "user-9",
            "requested_role": "viewer",
            "status": "pending",
            "justification": None,
            "requested_at": datetime.now(UTC),
        },
        None,  # _member_role(user-9) → not yet a member
    ]
    resp = await client.post(
        "/api/v1/join-requests/jr-1/decide",
        headers=_SUPER_ADMIN,  # super_admin bypasses project-admin guard
        json={"decision": "approved"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


async def test_list_scope_requests_requires_platform_admin(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    resp = await client.get("/api/v1/scope-requests", headers=_USER)
    assert resp.status_code == 403


async def test_create_scope_request_accepts_several_items(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """One submission, several landing zones/workspaces — one row each.

    Rows of the same submission share ``requestedAt``, which is how the review
    queue regroups them into a single request.
    """
    mock_db.fetchone.return_value = _project_row()
    resp = await client.post(
        "/api/v1/projects/ba-42/scope-requests",
        headers=_SUPER_ADMIN,  # super_admin bypasses the project-admin guard
        json={
            "items": [
                {"scopeType": "lz", "scopeRef": "lz-a"},
                {"scopeType": "lz", "scopeRef": "lz-a"},  # duplicate → collapsed
                {"scopeType": "dbx_workspace", "scopeRef": "ws-1"},
            ],
            "justification": "New data product",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert [(item["scopeType"], item["scopeRef"]) for item in body] == [
        ("lz", "lz-a"),
        ("dbx_workspace", "ws-1"),
    ]
    assert {item["requestedAt"] for item in body} == {body[0]["requestedAt"]}
    assert {item["justification"] for item in body} == {"New data product"}
    assert len({item["id"] for item in body}) == 2
    assert mock_db.execute.await_count == 2


async def test_create_scope_request_still_accepts_the_single_item_form(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.return_value = _project_row()
    resp = await client.post(
        "/api/v1/projects/ba-42/scope-requests",
        headers=_SUPER_ADMIN,
        json={"scopeType": "lz", "scopeRef": "lz-a"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert len(body) == 1
    assert body[0]["scopeRef"] == "lz-a"


async def test_create_scope_request_rejects_an_empty_request(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.return_value = _project_row()
    resp = await client.post(
        "/api/v1/projects/ba-42/scope-requests",
        headers=_SUPER_ADMIN,
        json={"items": [], "justification": "nothing asked"},
    )
    assert resp.status_code == 422


async def test_delete_project_removes_its_children_and_audits(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """A project activated by mistake has no other way out than deletion.

    Delta has no cascade, so scope/members/requests must be deleted explicitly —
    otherwise the next project on the same Business Application (``id`` IS the BA
    id) would inherit them.
    """
    mock_db.fetchone.return_value = _project_row()
    resp = await client.request(
        "DELETE", "/api/v1/projects/ba-42", headers=_SUPER_ADMIN
    )
    assert resp.status_code == 204
    statements = [
        " ".join(str(call.args[0]).split()) for call in mock_db.execute.await_args_list
    ]

    def deleted(table: str) -> bool:
        return any(
            stmt.startswith("DELETE FROM") and f"`{table}`" in stmt for stmt in statements
        )

    for table in (
        "dcm_project_lz_scope",
        "dcm_project_dbx_scope",
        "dcm_project_members",
        "dcm_project_join_requests",
        "dcm_project_scope_requests",
        "dcm_projects",
    ):
        assert deleted(table), table
    assert any("dcm_audit_log" in stmt for stmt in statements)


async def test_delete_project_requires_platform_admin(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    resp = await client.request("DELETE", "/api/v1/projects/ba-42", headers=_USER)
    assert resp.status_code == 403


async def test_delete_unknown_project_returns_404(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.return_value = None
    resp = await client.request(
        "DELETE", "/api/v1/projects/ba-unknown", headers=_SUPER_ADMIN
    )
    assert resp.status_code == 404


async def test_compute_empty_scope_returns_empty_not_forbidden(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    # user with no active project → empty scope → 200 + empty collection (not 403)
    mock_db.fetchall.return_value = []
    resp = await client.get("/api/v1/clusters", headers=_USER)
    assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Self-service registration / join from the login page (feature 016)
# ─────────────────────────────────────────────────────────────────────────────

_REGISTER_BODY = {
    "businessAppId": "ba-42",
    "name": "BA Payments",
    "members": [
        {"email": "colleague-a@example.com", "role": "viewer"},
        {"email": "colleague-b@example.com", "role": "admin"},
    ],
    "lzScope": ["lz-a"],
    "dbxScope": ["ws-1"],
}


async def test_register_project_creates_pending_with_requester_admin(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.return_value = None  # BA + app-user lookups all miss
    mock_db.fetchall.return_value = [
        {"lz_id": "lz-a", "workspace_id": "ws-1"},
    ]
    resp = await client.post(
        "/api/v1/projects/register",
        headers={"x-dcm-email": "Requester@Example.com"},
        json=_REGISTER_BODY,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending_validation"
    assert body["requesterEmail"] == "requester@example.com"  # from token, normalized
    assert body["memberCount"] == 3  # requester + 2 colleagues
    # 3 app-user stubs + 1 project + 3 members + 1 lz + 1 dbx = 9 inserts
    assert mock_db.execute.await_count == 9


async def test_register_project_conflict_when_business_app_taken(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.return_value = {"id": "ba-42"}
    resp = await client.post(
        "/api/v1/projects/register",
        headers={"x-dcm-email": "requester@example.com"},
        json=_REGISTER_BODY,
    )
    assert resp.status_code == 409
    assert "join" in str(resp.json()["detail"]).lower()


async def test_reference_business_applications_lists_id_and_name_only(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """Public catalog must not leak LZ / account / workspace inventory."""
    mock_db.fetchall.return_value = [
        {"ba_id": "ba-1", "ba_name": "Payments"},
        {"ba_id": "ba-2", "ba_name": "Risk"},
    ]
    resp = await client.get("/api/v1/reference/business-applications")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["items"] == [
        {
            "businessApplicationId": "ba-1",
            "businessApplicationName": "Payments",
        },
        {
            "businessApplicationId": "ba-2",
            "businessApplicationName": "Risk",
        },
    ]
    for item in body["items"]:
        assert "landingZones" not in item
        assert "dbxWorkspaces" not in item
        assert "subscriptionOrAccountId" not in item


async def test_register_project_ignores_client_scope_spoofing(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    """Authenticated register attaches BA scopes from the DB, not the request body."""
    mock_db.fetchone.return_value = None
    mock_db.fetchall.return_value = [
        {"lz_id": "lz-a", "workspace_id": "ws-1"},
        {"lz_id": "lz-b", "workspace_id": None},
    ]
    resp = await client.post(
        "/api/v1/projects/register",
        headers={"x-dcm-email": "jane.doe@totalenergies.com"},
        json={
            "businessAppId": "ba-1",
            "name": "My project",
            "members": [],
            "lzScope": ["spoofed-lz"],
            "dbxScope": ["spoofed-ws"],
        },
    )
    assert resp.status_code == 201, resp.text
    granted_lzs = {
        call.args[2]
        for call in mock_db.execute.await_args_list
        if call.args and "dcm_project_lz_scope" in str(call.args[0])
    }
    granted_ws = {
        call.args[2]
        for call in mock_db.execute.await_args_list
        if call.args and "dcm_project_dbx_scope" in str(call.args[0])
    }
    # INSERT (?, ?, ?, ?) → project_id, lz_id/workspace_id, granted_by, granted_at
    assert granted_lzs == {"lz-a", "lz-b"}
    assert granted_ws == {"ws-1"}
    assert "spoofed-lz" not in granted_lzs
    assert "spoofed-ws" not in granted_ws


async def test_reference_projects_lists_joinable_projects(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchall.return_value = [
        {
            "id": "proj-1",
            "name": "Payments",
            "business_app_id": "ba-1",
            "status": "active",
        },
        {
            "id": "proj-2",
            "name": "Risk",
            "business_app_id": "ba-2",
            "status": "active",
        },
    ]
    resp = await client.get("/api/v1/reference/projects")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["items"][0] == {
        "id": "proj-1",
        "name": "Payments",
        "businessAppId": "ba-1",
        "status": "active",
    }


async def test_join_project_pending_validation_routes_to_creator(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    # _load_project_row → pending ; _ensure_app_user(requester) → miss
    mock_db.fetchone.side_effect = [_project_row(status="pending_validation"), None]
    resp = await client.post(
        "/api/v1/projects/join",
        headers={"x-dcm-email": "newbie@example.com"},
        json={"projectId": "ba-42"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["routedTo"] == "creator"
    assert body["recipientIds"] == ["user-1"]  # _project_row created_by
    assert body["status"] == "pending"


async def test_join_project_active_routes_to_admins(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    # _load_project_row → active ; _ensure_app_user(requester) → miss
    mock_db.fetchone.side_effect = [_project_row(status="active"), None]
    mock_db.fetchall.return_value = [
        {"user_id": "admin-a"},
        {"user_id": "admin-b"},
    ]
    resp = await client.post(
        "/api/v1/projects/join",
        headers={"x-dcm-email": "newbie@example.com"},
        json={"projectId": "ba-42"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["routedTo"] == "admins"
    assert body["recipientIds"] == ["admin-a", "admin-b"]


async def test_join_project_unknown_project_returns_404(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.side_effect = [None]  # _load_project_row → not found
    resp = await client.post(
        "/api/v1/projects/join",
        headers={"x-dcm-email": "newbie@example.com"},
        json={"projectId": "ghost"},
    )
    assert resp.status_code == 404

