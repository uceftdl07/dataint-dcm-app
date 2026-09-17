"""Tests for notification channels and alert rules admin endpoints."""

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


def _admin_headers() -> dict[str, str]:
    return {
        "x-dcm-role": "super_admin",
        "x-dcm-user-id": "admin-001",
        "x-dcm-email": "admin@example.com",
    }


def _channel_row(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": "channel-001",
        "name": "Teams DCM",
        "channel_type": "teams",
        "config": '{"webhook_secret_ref": "kv://teams-webhook"}',
        "is_active": True,
        "created_by": "admin-001",
        "created_at": datetime(2026, 5, 27, 10, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 5, 27, 10, 0, tzinfo=UTC),
    }
    base.update(overrides)
    return base


def _rule_row(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": "rule-001",
        "name": "Pipeline failure rate",
        "description": None,
        "metric_domain": "pipeline",
        "condition_field": "failure_rate_pct",
        "condition_operator": "gte",
        "condition_threshold": 30.0,
        "eval_window_hours": 2,
        "severity": "critical",
        "applies_to_lz_ids": ["lz-001"],
        "notification_channel_ids": ["channel-001"],
        "cooldown_minutes": 60,
        "is_active": True,
        "created_by": "admin-001",
        "created_at": datetime(2026, 5, 27, 10, 0, tzinfo=UTC),
        "updated_at": datetime(2026, 5, 27, 10, 0, tzinfo=UTC),
    }
    base.update(overrides)
    return base


async def test_create_notification_channel_writes_audit(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    resp = await client.post(
        "/api/v1/admin/notification-channels",
        headers=_admin_headers(),
        json={
            "name": "Teams DCM",
            "channel_type": "teams",
            "config": {"webhook_secret_ref": "kv://teams-webhook"},
        },
    )

    assert resp.status_code == 201
    assert resp.json()["channel_type"] == "teams"
    assert mock_db.execute.await_count == 2
    assert mock_db.execute.await_args_list[-1].args[3] == "notification_channel.create"


async def test_create_notification_channel_rejects_raw_secret(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/admin/notification-channels",
        headers=_admin_headers(),
        json={
            "name": "Teams DCM",
            "channel_type": "teams",
            "config": {"webhook_url": "https://example.invalid/raw-secret"},
        },
    )

    assert resp.status_code == 400
    assert "secret references" in resp.json()["detail"]


async def test_test_notification_channel_is_dry_run(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchone.return_value = _channel_row()

    resp = await client.post(
        "/api/v1/admin/notification-channels/channel-001/test",
        headers=_admin_headers(),
    )

    assert resp.status_code == 200
    assert resp.json()["dry_run"] is True
    assert resp.json()["status"] == "accepted"


async def test_create_alert_rule_validates_metric_field(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/admin/alert-rules",
        headers=_admin_headers(),
        json={
            "name": "Invalid",
            "metric_domain": "pipeline",
            "condition_field": "open_alert_count",
            "condition_operator": "gte",
            "condition_threshold": 1,
            "eval_window_hours": 2,
            "severity": "critical",
        },
    )

    assert resp.status_code == 400
    assert "Unsupported condition_field" in resp.json()["detail"]


async def test_create_alert_rule_validates_channel_ids(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchall.return_value = [{"id": "channel-001"}]

    resp = await client.post(
        "/api/v1/admin/alert-rules",
        headers=_admin_headers(),
        json={
            "name": "Pipeline failure rate",
            "metric_domain": "pipeline",
            "condition_field": "failure_rate_pct",
            "condition_operator": "gte",
            "condition_threshold": 30,
            "eval_window_hours": 2,
            "severity": "critical",
            "applies_to_lz_ids": ["lz-001"],
            "notification_channel_ids": ["channel-001"],
        },
    )

    assert resp.status_code == 201
    assert resp.json()["notification_channel_ids"] == ["channel-001"]
    assert mock_db.execute.await_args_list[-1].args[3] == "alert_rule.create"


async def test_test_alert_rule_returns_lz_results(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchone.return_value = _rule_row()
    mock_db.fetchall.return_value = [{"source_lz_id": "lz-001", "measured_value": 42.0}]

    resp = await client.post(
        "/api/v1/admin/alert-rules/rule-001/test",
        headers=_admin_headers(),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["would_fire"] is True
    assert body["measured_value"] == 42.0
    assert body["by_landing_zone"][0]["would_fire"] is True
