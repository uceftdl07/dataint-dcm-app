"""Tests for standard-check and landing-zone endpoints.

Routes covered
--------------
GET /api/v1/standard-checks
GET /api/v1/standard-checks/page-bundle
GET /api/v1/standard-checks/score
GET /api/v1/landing-zones/details
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_row(**overrides: Any) -> dict:
    base: dict[str, Any] = {
        "check_id": "policy-001",
        "check_name": "Require-StorageHttps",
        "cloud_provider": "azure",
        "source_lz_id": "lz-azure-prod-fr",
        "subscription_or_account_id": "sub-abc",
        "check_state": "non_compliant",
        "resource_id": "/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/st01",
        "resource_name": "st01",
        "resource_type": "Microsoft.Storage/storageAccounts",
        "check_effect": "audit",
        "non_check_reasons": ["HTTPS traffic is disabled"],
        "evaluated_at": datetime(2026, 3, 20, 10, 0, 0, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return base


def _score_global_row(**overrides: Any) -> dict:
    base: dict[str, Any] = {
        "compliant_count": 80,
        "non_compliant_count": 20,
        "total_evaluated": 100,
    }
    base.update(overrides)
    return base


def _score_breakdown_row(**overrides: Any) -> dict:
    base: dict[str, Any] = {
        "cloud_provider": "azure",
        "source_lz_id": "lz-azure-prod-fr",
        "subscription_or_account_id": "sub-abc",
        "compliant_count": 80,
        "non_compliant_count": 20,
        "total_evaluated": 100,
    }
    base.update(overrides)
    return base


def _lz_row(**overrides: Any) -> dict:
    base: dict[str, Any] = {
        "lz_id": "lz-azure-prod-fr",
        "lz_name": "Azure FR Prod",
        "cloud_provider": "azure",
        "subscription_or_account_id": "sub-abc",
        "region": "westeurope",
        "environment": "prod",
        "owner_team": "Digital Factory",
        "onboarded_at": date(2025, 1, 1),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# GET /api/v1/standard-checks
# ---------------------------------------------------------------------------

class TestListStandardChecks:
    async def test_empty_response(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 0
        mock_db.fetchall.return_value = []

        resp = await client.get("/api/v1/standard-checks")

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["limit"] == 100
        assert body["offset"] == 0

    async def test_single_item_serialised(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 1
        mock_db.fetchall.return_value = [_check_row()]

        resp = await client.get("/api/v1/standard-checks")

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        item = items[0]
        assert item["check_id"] == "policy-001"
        assert item["check_name"] == "Require-StorageHttps"
        assert item["check_state"] == "non_compliant"
        assert item["check_effect"] == "audit"
        assert item["non_check_reasons"] == ["HTTPS traffic is disabled"]
        assert item["evaluated_at"].startswith("2026-03-20")

    async def test_null_non_check_reasons_becomes_empty_list(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 1
        mock_db.fetchall.return_value = [_check_row(non_check_reasons=None)]

        resp = await client.get("/api/v1/standard-checks")

        assert resp.json()["items"][0]["non_check_reasons"] == []

    async def test_check_state_filter_accepted(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 0
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/standard-checks", params={"check_state": "non_compliant"}
        )

        assert resp.status_code == 200

    async def test_cloud_provider_filter_accepted(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 0
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/standard-checks", params={"cloud_provider": "azure"}
        )

        assert resp.status_code == 200

    async def test_check_name_partial_filter_accepted(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 0
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/standard-checks", params={"check_name": "Storage"}
        )

        assert resp.status_code == 200

    async def test_date_range_filter_accepted(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 0
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/standard-checks",
            params={"start_date": "2026-03-01", "end_date": "2026-03-31"},
        )

        assert resp.status_code == 200

    async def test_pagination_fields(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 250
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/standard-checks", params={"limit": 50, "offset": 100}
        )

        body = resp.json()
        assert body["total"] == 250
        assert body["limit"] == 50
        assert body["offset"] == 100

    async def test_limit_upper_bound_enforced(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        resp = await client.get("/api/v1/standard-checks", params={"limit": 9999})

        assert resp.status_code == 422

    async def test_source_lz_id_filter_accepted(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 0
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/standard-checks", params={"source_lz_id": "lz-azure-prod-fr"}
        )

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/v1/standard-checks/page-bundle
# ---------------------------------------------------------------------------

class TestGovernancePageBundle:
    async def test_returns_score_and_checks(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchscalar.return_value = 1
        mock_db.fetchone.return_value = _score_global_row()

        async def fetchall_side_effect(query: str, *args: Any) -> list[dict[str, Any]]:
            if "curated_standard_checks" in query:
                return [_check_row()]
            if "GROUP BY" in query:
                return [_score_breakdown_row()]
            return []

        mock_db.fetchall.side_effect = fetchall_side_effect

        resp = await client.get("/api/v1/standard-checks/page-bundle")

        assert resp.status_code == 200
        body = resp.json()
        assert body["score"]["global_score_pct"] == 80.0
        assert len(body["checks"]["items"]) == 1
        assert body["checks"]["total"] == 1


# ---------------------------------------------------------------------------
# GET /api/v1/standard-checks/score
# ---------------------------------------------------------------------------

class TestStandardCheckScore:
    async def test_global_score_computed(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchone.return_value = _score_global_row()
        mock_db.fetchall.return_value = [_score_breakdown_row()]

        resp = await client.get("/api/v1/standard-checks/score")

        assert resp.status_code == 200
        body = resp.json()
        assert body["global_score_pct"] == 80.0
        assert body["compliant_count"] == 80
        assert body["non_compliant_count"] == 20
        assert body["total_evaluated"] == 100

    async def test_score_is_none_when_no_evaluations(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchone.return_value = _score_global_row(
            compliant_count=0, non_compliant_count=0, total_evaluated=0
        )
        mock_db.fetchall.return_value = []

        resp = await client.get("/api/v1/standard-checks/score")

        body = resp.json()
        assert body["global_score_pct"] is None
        assert body["total_evaluated"] == 0

    async def test_breakdown_per_lz(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchone.return_value = _score_global_row()
        mock_db.fetchall.return_value = [
            _score_breakdown_row(source_lz_id="lz-azure-prod-fr", compliant_count=60, non_compliant_count=10, total_evaluated=70),
            _score_breakdown_row(cloud_provider="aws", source_lz_id="lz-aws-prod", subscription_or_account_id="aws-acct-01", compliant_count=20, non_compliant_count=10, total_evaluated=30),
        ]

        resp = await client.get("/api/v1/standard-checks/score")

        body = resp.json()
        breakdown = body["by_landing_zone"]
        assert len(breakdown) == 2
        lz_azure = breakdown[0]
        assert lz_azure["source_lz_id"] == "lz-azure-prod-fr"
        assert lz_azure["score_pct"] == round(60 / 70 * 100, 1)
        lz_aws = breakdown[1]
        assert lz_aws["cloud_provider"] == "aws"
        assert lz_aws["score_pct"] == round(20 / 30 * 100, 1)

    async def test_lz_score_none_when_lz_has_no_evaluations(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchone.return_value = _score_global_row(
            compliant_count=0, non_compliant_count=0, total_evaluated=0
        )
        mock_db.fetchall.return_value = [
            _score_breakdown_row(compliant_count=0, non_compliant_count=0, total_evaluated=0)
        ]

        resp = await client.get("/api/v1/standard-checks/score")

        lz = resp.json()["by_landing_zone"][0]
        assert lz["score_pct"] is None

    async def test_since_filter_accepted(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchone.return_value = _score_global_row()
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/standard-checks/score", params={"since": "2026-03-01"}
        )

        assert resp.status_code == 200

    async def test_cloud_provider_filter_accepted(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchone.return_value = _score_global_row()
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/standard-checks/score", params={"cloud_provider": "aws"}
        )

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/v1/landing-zones/details
# ---------------------------------------------------------------------------

class TestListLandingZones:
    async def test_empty_response(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = []

        resp = await client.get("/api/v1/landing-zones/details")

        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    async def test_single_lz_serialised(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = [_lz_row()]

        resp = await client.get("/api/v1/landing-zones/details")

        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        item = items[0]
        assert item["lz_id"] == "lz-azure-prod-fr"
        assert item["lz_name"] == "Azure FR Prod"
        assert item["cloud_provider"] == "azure"
        assert item["environment"] == "prod"
        assert item["ba_name"] == "Digital Factory"
        assert item["onboarded_at"] == "2025-01-01"
        query = mock_db.fetchall.await_args.args[0]
        assert "subscription_or_account_id IS NOT NULL" in query

    async def test_null_subscription_rows_excluded_by_query(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = []

        await client.get("/api/v1/landing-zones/details")

        query = mock_db.fetchall.await_args.args[0]
        assert "subscription_or_account_id IS NOT NULL" in query
        assert "TRIM(subscription_or_account_id)" in query

    async def test_returns_503_when_dim_landing_zone_unavailable(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.side_effect = Exception("dim_landing_zone missing")

        resp = await client.get("/api/v1/landing-zones/details")

        assert resp.status_code == 503
        assert "dim_landing_zone" in resp.json()["detail"]

    async def test_null_onboarded_at_is_none(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = [_lz_row(onboarded_at=None)]

        resp = await client.get("/api/v1/landing-zones/details")

        assert resp.json()["items"][0]["onboarded_at"] is None

    async def test_total_equals_items_count(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = [_lz_row(), _lz_row(lz_id="lz-aws-prod", lz_name="AWS Prod")]

        resp = await client.get("/api/v1/landing-zones/details")

        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

    async def test_cloud_provider_filter_accepted(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/landing-zones/details", params={"cloud_provider": "azure"}
        )

        assert resp.status_code == 200

    async def test_environment_filter_accepted(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/landing-zones/details", params={"environment": "prod"}
        )

        assert resp.status_code == 200

    async def test_ba_name_partial_filter_accepted(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = []

        resp = await client.get(
            "/api/v1/landing-zones/details", params={"ba_name": "Digital"}
        )

        assert resp.status_code == 200

    async def test_all_filters_combined(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = [_lz_row()]

        resp = await client.get(
            "/api/v1/landing-zones/details",
            params={"cloud_provider": "azure", "environment": "prod", "ba_name": "Digital"},
        )

        assert resp.status_code == 200
        assert resp.json()["total"] == 1


# ---------------------------------------------------------------------------
# GET /api/v1/landing-zones/access-overview
# ---------------------------------------------------------------------------

def _viewer_headers(lz_ids: str = "lz-azure-prod-fr") -> dict[str, str]:
    return {"x-dcm-role": "viewer", "x-dcm-lz-ids": lz_ids}


class TestLandingZonesAccessOverview:
    async def test_marks_access_for_viewer_scope(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = [
            _lz_row(),
            _lz_row(lz_id="lz-aws-prod", lz_name="AWS Prod", cloud_provider="aws"),
        ]

        resp = await client.get(
            "/api/v1/landing-zones/access-overview",
            headers=_viewer_headers("lz-azure-prod-fr"),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["granted_count"] == 1
        assert body["denied_count"] == 1
        assert body["unrestricted_access"] is False

        by_id = {item["lz_id"]: item for item in body["items"]}
        assert by_id["lz-azure-prod-fr"]["has_access"] is True
        assert by_id["lz-aws-prod"]["has_access"] is False
        assert "collectors_total" not in by_id["lz-azure-prod-fr"]

    async def test_admin_sees_all_landing_zones_as_accessible(
        self, client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        mock_db.fetchall.return_value = [
            _lz_row(),
            _lz_row(lz_id="lz-aws-prod", lz_name="AWS Prod", cloud_provider="aws"),
        ]

        resp = await client.get(
            "/api/v1/landing-zones/access-overview",
            headers={"x-dcm-role": "admin"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["granted_count"] == 2
        assert body["denied_count"] == 0
        assert body["unrestricted_access"] is True
        assert all(item["has_access"] for item in body["items"])
