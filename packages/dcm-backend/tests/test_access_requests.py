"""Route tests for the unauthenticated access-request flow (dcm_access).

Guards FR-005: removing the ``lz_registration`` path must NOT break the
``dcm_access`` self-registration flow.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from httpx import AsyncClient

_NEW_ACCOUNT = {
    "email": "newcomer@example.com",
    "display_name": "New Comer",
    "justification": "I need DCM access to monitor my landing zone pipelines.",
    "requested_lz_ids": ["lz-a"],
}


async def test_dcm_access_request_still_works(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    # No existing user, no pending request → request accepted (201).
    mock_db.fetchone.side_effect = [None, None]
    resp = await client.post("/api/v1/access-requests", json=_NEW_ACCOUNT)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert body["email"] == "newcomer@example.com"


async def test_dcm_access_request_conflicts_when_already_registered(
    client: AsyncClient, mock_db: AsyncMock
) -> None:
    mock_db.fetchone.side_effect = [{"id": "u-1", "is_active": True}]
    resp = await client.post("/api/v1/access-requests", json=_NEW_ACCOUNT)
    assert resp.status_code == 409
