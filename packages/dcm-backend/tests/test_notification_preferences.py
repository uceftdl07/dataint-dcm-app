"""Tests for per-user notification preferences."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.main import app
from app.notification.defaults import DEFAULT_NOTIFICATION_PREFERENCES


@pytest.fixture(autouse=True)
def auth_disabled() -> Iterator[None]:
    settings = app.state.settings
    original = settings.auth_disabled
    settings.auth_disabled = True
    try:
        yield
    finally:
        settings.auth_disabled = original


def _user_headers() -> dict[str, str]:
    return {
        "x-dcm-role": "viewer",
        "x-dcm-user-id": "user-prefs-001",
        "x-dcm-email": "viewer@example.com",
        "x-dcm-display-name": "Prefs User",
    }


def _prefs_row(**overrides: Any) -> dict[str, Any]:
    base = {
        "user_id": "user-prefs-001",
        **DEFAULT_NOTIFICATION_PREFERENCES,
        "updated_at": datetime(2026, 6, 3, 12, 0, tzinfo=UTC),
    }
    base.update(overrides)
    return base


async def test_get_returns_defaults_when_no_row(client: AsyncClient, mock_db: AsyncMock) -> None:
    mock_db.fetchone = AsyncMock(return_value=None)

    resp = await client.get(
        "/api/v1/users/me/notification-preferences",
        headers=_user_headers(),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["is_default"] is True
    assert body["show_security"] is True
    assert body["min_severity"] == "warning"
    assert body["notification_lz_ids"] == []
    assert body["updated_at"] is None


async def test_get_returns_stored_row(client: AsyncClient, mock_db: AsyncMock) -> None:
    mock_db.fetchone = AsyncMock(return_value=_prefs_row(show_governance=False))

    resp = await client.get(
        "/api/v1/users/me/notification-preferences",
        headers=_user_headers(),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["is_default"] is False
    assert body["show_governance"] is False


async def test_put_inserts_preferences(client: AsyncClient, mock_db: AsyncMock) -> None:
    mock_db.fetchone = AsyncMock(side_effect=[None, _prefs_row(hide_info=True)])
    mock_db.execute = AsyncMock(return_value=1)

    resp = await client.put(
        "/api/v1/users/me/notification-preferences",
        headers=_user_headers(),
        json={
            **DEFAULT_NOTIFICATION_PREFERENCES,
            "hide_info": True,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["hide_info"] is True
    assert body["is_default"] is False
    assert mock_db.execute.await_count == 1


async def test_put_updates_existing_row(client: AsyncClient, mock_db: AsyncMock) -> None:
    mock_db.fetchone = AsyncMock(
        side_effect=[_prefs_row(), _prefs_row(show_cost=False, min_severity="critical")],
    )
    mock_db.execute = AsyncMock(return_value=1)

    resp = await client.put(
        "/api/v1/users/me/notification-preferences",
        headers=_user_headers(),
        json={
            **DEFAULT_NOTIFICATION_PREFERENCES,
            "show_cost": False,
            "min_severity": "critical",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["show_cost"] is False
    assert body["min_severity"] == "critical"
    assert mock_db.execute.await_count == 1


async def test_put_persists_notification_lz_ids(client: AsyncClient, mock_db: AsyncMock) -> None:
    mock_db.fetchone = AsyncMock(
        side_effect=[None, _prefs_row(notification_lz_ids=["lz-001"])],
    )
    mock_db.execute = AsyncMock(return_value=1)

    resp = await client.put(
        "/api/v1/users/me/notification-preferences",
        headers={**_user_headers(), "x-dcm-lz-ids": "lz-001,lz-002"},
        json={
            **DEFAULT_NOTIFICATION_PREFERENCES,
            "notification_lz_ids": ["lz-001", "lz-003"],
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["notification_lz_ids"] == ["lz-001"]
    insert_args = mock_db.execute.await_args_list[0].args
    assert insert_args[12] == ["lz-001"]


async def test_put_rejects_invalid_severity(client: AsyncClient) -> None:
    resp = await client.put(
        "/api/v1/users/me/notification-preferences",
        headers=_user_headers(),
        json={**DEFAULT_NOTIFICATION_PREFERENCES, "min_severity": "urgent"},
    )

    assert resp.status_code == 422
