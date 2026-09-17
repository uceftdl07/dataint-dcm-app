"""Tests for collectors, KPI, retention, maintenance and audit admin endpoints."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.main import app


@pytest.fixture(autouse=True)
def auth_and_collector_key() -> Iterator[None]:
    settings = app.state.settings
    original_auth = settings.auth_disabled
    original_key = settings.collector_api_key
    settings.auth_disabled = True
    settings.collector_api_key = "collector-secret"
    try:
        yield
    finally:
        settings.auth_disabled = original_auth
        settings.collector_api_key = original_key


def _admin_headers() -> dict[str, str]:
    return {"x-dcm-role": "super_admin", "x-dcm-user-id": "admin-001"}


def _kpi_rows(**overrides: float) -> list[dict[str, Any]]:
    values = {
        "pipeline_failure_rate_warning_pct": 10.0,
        "pipeline_failure_rate_critical_pct": 30.0,
        "cluster_error_rate_warning_pct": 5.0,
        "cluster_error_rate_critical_pct": 20.0,
        "cost_overrun_warning_pct": 80.0,
        "cost_overrun_critical_pct": 100.0,
        "open_alerts_warning_count": 5.0,
        "open_alerts_critical_count": 20.0,
        "compliance_score_warning_pct": 80.0,
        "compliance_score_critical_pct": 60.0,
    }
    values.update(overrides)
    return [
        {
            "config_key": key,
            "config_value": value,
            "description": None,
            "updated_by": None,
            "updated_at": datetime(2026, 5, 27, 10, 0, tzinfo=UTC),
        }
        for key, value in values.items()
    ]


def _retention_rows() -> list[dict[str, Any]]:
    return [
        {
            "metric_table": "pipeline_metrics",
            "retention_days": 90,
            "updated_by": None,
            "updated_at": datetime(2026, 5, 27, 10, 0, tzinfo=UTC),
        }
    ]


async def test_collector_status_requires_collector_key(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/admin/collectors/status",
        json={"lz_id": "lz-001", "collector_name": "azure"},
        headers={"X-Collector-Key": "wrong"},
    )

    assert resp.status_code == 403


async def test_collector_status_upsert_accepts_valid_key(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    resp = await client.post(
        "/api/v1/admin/collectors/status",
        json={
            "lz_id": "lz-001",
            "collector_name": "azure",
            "last_run_status": "success",
            "metrics_collected": 12,
        },
        headers={"X-Collector-Key": "collector-secret"},
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert "MERGE INTO" in mock_db.execute.await_args.args[0]


async def test_kpi_patch_rejects_inconsistent_thresholds(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchall.return_value = _kpi_rows()

    resp = await client.patch(
        "/api/v1/admin/kpi-config",
        headers=_admin_headers(),
        json={"pipeline_failure_rate_warning_pct": 40},
    )

    assert resp.status_code == 400
    assert "Inconsistent KPI thresholds" in resp.json()["detail"]


async def test_retention_patch_rejects_values_below_seven_days(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchall.return_value = _retention_rows()

    resp = await client.patch(
        "/api/v1/admin/retention-policies",
        headers=_admin_headers(),
        json={"pipeline_metrics": 6},
    )

    assert resp.status_code == 400
    assert "at least 7 days" in resp.json()["detail"]["message"]


async def test_retention_stats_maps_legacy_table_names_and_tolerates_missing_tables(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchall.return_value = [
        *_retention_rows(),
        {
            "metric_table": "cluster_metrics",
            "retention_days": 90,
            "updated_by": None,
            "updated_at": datetime(2026, 5, 27, 10, 0, tzinfo=UTC),
        },
    ]
    mock_db.fetchone.side_effect = [
        {"numFiles": 3, "sizeInBytes": 1024},
        Exception("table not found"),
    ]

    resp = await client.get("/api/v1/admin/retention-policies/stats", headers=_admin_headers())

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["items"][0]["num_files"] == 3
    assert body["items"][1]["num_files"] is None
    describe_queries = [call.args[0] for call in mock_db.fetchone.await_args_list]
    assert "curated_pipeline_metrics" in describe_queries[0]
    assert "curated_compute_metrics" in describe_queries[1]


async def test_active_maintenance_windows_available_to_authenticated_users(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    now = datetime.now(UTC)
    mock_db.fetchall.return_value = [
        {
            "id": "window-001",
            "name": "Maintenance",
            "description": None,
            "lz_ids": ["lz-001"],
            "starts_at": now - timedelta(hours=1),
            "ends_at": now + timedelta(hours=1),
            "suppress_alerts": True,
            "created_by": "admin-001",
            "created_at": now - timedelta(hours=2),
        }
    ]

    resp = await client.get("/api/v1/maintenance-windows/active", headers={"x-dcm-role": "viewer"})

    assert resp.status_code == 200
    assert resp.json()["items"][0]["id"] == "window-001"


async def test_audit_log_export_returns_csv(
    client: AsyncClient,
    mock_db: AsyncMock,
) -> None:
    mock_db.fetchall.return_value = [
        {
            "id": "audit-001",
            "actor_user_id": "admin-001",
            "action": "user.role.update",
            "target_type": "user",
            "target_id": "user-001",
            "before_state": "{}",
            "after_state": "{}",
            "ip_address": "127.0.0.1",
            "created_at": datetime(2026, 5, 27, 10, 0, tzinfo=UTC),
        }
    ]

    resp = await client.get("/api/v1/admin/audit-log/export", headers=_admin_headers())

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "user.role.update" in resp.text
