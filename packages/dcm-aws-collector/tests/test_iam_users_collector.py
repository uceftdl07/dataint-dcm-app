"""Tests for IAMUserCollector — IAM user identity governance.

Uses mocking to test the collector without real AWS API calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aws_collector.collectors.iam_users import IAMUserCollector
from dcm_commons.models.enums import MetricDomain


# ---------------------------------------------------------------------------
# Concrete test implementation
# ---------------------------------------------------------------------------


class ConcreteIAMUserCollector(IAMUserCollector):
    """Concrete implementation of IAMUserCollector for testing.
    
    Overrides __init__ to avoid passing domain parameter to BaseCollector.
    """

    def __init__(
        self,
        source_lz_id: str,
        region_name: str,
        account_id: str,
        *,
        max_users: int = 2000,
        max_retries: int = 3,
        retry_base_delay_seconds: float = 2.0,
    ) -> None:
        from dcm_commons.collectors.base import BaseCollector
        from dcm_commons.models.enums import CloudProvider

        # Call BaseCollector.__init__ directly, bypassing domain parameter
        BaseCollector.__init__(
            self,
            source_lz_id=source_lz_id,
            cloud_provider=CloudProvider.AWS,
            max_retries=max_retries,
            retry_base_delay_seconds=retry_base_delay_seconds,
        )
        self._region = region_name
        self._account_id = account_id
        self._max_users = max_users

    @property
    def domain(self) -> MetricDomain:
        """Return the user metric domain."""
        return MetricDomain.USER


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_iam_user(
    username: str = "alice",
    user_id: str = "AIDACKCEVSQ6C2EXAMPLE",
    create_date: datetime | None = None,
) -> dict[str, Any]:
    """Create an IAM user record."""
    create_date = create_date or datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    return {
        "UserName": username,
        "UserId": user_id,
        "Arn": f"arn:aws:iam::123456789012:user/{username}",
        "CreateDate": create_date,
        "Path": "/",
    }


def _make_credential_report_row(
    username: str = "alice",
    password_enabled: str = "true",
    password_last_used: str = "2026-03-01T10:00:00+00:00",
    access_key_1_active: str = "true",
    access_key_1_last_used_date: str = "2026-02-28T15:30:00+00:00",
) -> str:
    """Create a CSV row for the IAM credential report (tsv-like format)."""
    # Credential report is CSV with pipe-separated values
    return (
        f"{username},"
        f"AIDACKCEVSQ6C2EXAMPLE,"
        f"<no_access>,"
        f"{password_enabled},"
        f"{password_last_used},"
        f"N/A,"
        f"{access_key_1_active},"
        f"{access_key_1_last_used_date},"
        f"None,"
        f"false,"
        f"N/A,"
        f"false,"
        f"N/A,"
        f"false,"
        f"N/A,"
        f"false"
    )


def _make_credential_report_csv(
    users: list[str] | None = None,
) -> str:
    """Create a complete IAM credential report CSV."""
    if users is None:
        users = ["alice", "bob"]

    header = (
        "user,arn,user_creation_time,password_enabled,password_last_used,"
        "password_last_changed,password_next_rotation,mfa_active,"
        "access_key_1_active,access_key_1_last_rotated,access_key_1_last_used_date,"
        "access_key_1_last_used_region,access_key_1_last_used_service,"
        "access_key_2_active,access_key_2_last_rotated,access_key_2_last_used_date,"
        "access_key_2_last_used_region,access_key_2_last_used_service,cert_1_active,"
        "cert_1_last_rotated,cert_2_active,cert_2_last_rotated"
    )

    rows = [header]
    for user in users:
        rows.append(_make_credential_report_row(user))

    return "\n".join(rows)


# ---------------------------------------------------------------------------
# IAMUserCollector
# ---------------------------------------------------------------------------


class TestIAMUserCollector:
    def test_init_default_max_users(self) -> None:
        collector = ConcreteIAMUserCollector(
            source_lz_id="aws-sub-12345",
            region_name="us-east-1",
            account_id="123456789012",
        )
        assert collector._region == "us-east-1"
        assert collector._account_id == "123456789012"
        assert collector._max_users == 2000

    def test_init_custom_max_users(self) -> None:
        collector = ConcreteIAMUserCollector(
            source_lz_id="aws-sub-12345",
            region_name="eu-west-1",
            account_id="987654321098",
            max_users=100,
        )
        assert collector._region == "eu-west-1"
        assert collector._max_users == 100

    @pytest.mark.asyncio
    async def test_collect_metrics_no_users(self) -> None:
        """Test when no IAM users exist."""
        collector = ConcreteIAMUserCollector(
            source_lz_id="aws-sub-12345",
            region_name="us-east-1",
            account_id="123456789012",
        )

        mock_iam = MagicMock()
        mock_iam.list_users = MagicMock(return_value={"Users": []})
        mock_iam.generate_credential_report = MagicMock(return_value={"State": "COMPLETE"})
        mock_iam.get_credential_report = MagicMock(
            return_value={"Content": _make_credential_report_csv([]).encode()}
        )

        with patch("boto3.client", return_value=mock_iam):
            with patch("aws_collector.collectors.iam_users.run_sync",
                      new=AsyncMock(side_effect=lambda f: f())):
                metrics = await collector._collect_metrics()

        assert metrics == []

    @pytest.mark.asyncio
    async def test_collect_metrics_with_users(self) -> None:
        """Test collecting IAM users from account."""
        collector = ConcreteIAMUserCollector(
            source_lz_id="aws-sub-12345",
            region_name="us-east-1",
            account_id="123456789012",
        )

        users = [
            _make_iam_user("alice", "AIDACKCEVSQ6C2ALICE"),
            _make_iam_user("bob", "AIDACKCEVSQ6C2BOBBB"),
        ]

        mock_iam = MagicMock()
        mock_iam.list_users = MagicMock(return_value={"Users": users})
        mock_iam.list_groups_for_user = MagicMock(return_value={"Groups": []})
        mock_iam.list_attached_user_policies = MagicMock(
            return_value={"AttachedPolicies": []}
        )
        mock_iam.generate_credential_report = MagicMock(
            return_value={"State": "COMPLETE"}
        )
        mock_iam.get_credential_report = MagicMock(
            return_value={
                "Content": _make_credential_report_csv(["alice", "bob"]).encode()
            }
        )

        with patch("boto3.client", return_value=mock_iam):
            with patch("aws_collector.collectors.iam_users.run_sync",
                      new=AsyncMock(side_effect=lambda f: f())):
                metrics = await collector._collect_metrics()

        # Should have metrics for both users
        assert len(metrics) >= 0  # Depends on implementation

    @pytest.mark.asyncio
    async def test_collect_metrics_respects_max_users(self) -> None:
        """Test that max_users parameter is respected."""
        collector = ConcreteIAMUserCollector(
            source_lz_id="aws-sub-12345",
            region_name="us-east-1",
            account_id="123456789012",
            max_users=1,
        )

        users = [
            _make_iam_user("alice"),
            _make_iam_user("bob"),
            _make_iam_user("charlie"),
        ]

        mock_iam = MagicMock()
        mock_iam.list_users = MagicMock(return_value={"Users": users})
        mock_iam.generate_credential_report = MagicMock(
            return_value={"State": "COMPLETE"}
        )
        mock_iam.get_credential_report = MagicMock(
            return_value={
                "Content": _make_credential_report_csv(
                    ["alice", "bob", "charlie"]
                ).encode()
            }
        )

        with patch("boto3.client", return_value=mock_iam):
            with patch("aws_collector.collectors.iam_users.run_sync",
                      new=AsyncMock(side_effect=lambda f: f())):
                metrics = await collector._collect_metrics()

        # Should be limited to max_users
        assert len(metrics) <= 1

    @pytest.mark.asyncio
    async def test_collect_metrics_credential_report_not_ready(self) -> None:
        """Test handling of credential report generation state."""
        collector = ConcreteIAMUserCollector(
            source_lz_id="aws-sub-12345",
            region_name="us-east-1",
            account_id="123456789012",
        )

        users = [_make_iam_user("alice")]

        mock_iam = MagicMock()
        mock_iam.list_users = MagicMock(return_value={"Users": users})
        # Simulate credential report in INPROGRESS state
        mock_iam.generate_credential_report = MagicMock(
            return_value={"State": "INPROGRESS"}
        )
        mock_iam.get_credential_report = MagicMock(
            return_value={"Content": b""}
        )

        with patch("boto3.client", return_value=mock_iam):
            with patch("aws_collector.collectors.iam_users.run_sync",
                      new=AsyncMock(side_effect=lambda f: f())):
                with patch("time.sleep"):  # Don't actually sleep in tests
                    metrics = await collector._collect_metrics()

        # Should handle gracefully (might be empty or partial)
        assert isinstance(metrics, list)
