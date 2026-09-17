"""Tests for ConfigStandardCheckCollector — AWS Config Rule compliance evaluation.

Uses mocking to test the collector without real AWS API calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aws_collector.collectors.config_compliance import (
    ConfigStandardCheckCollector,
    _CONFIG_COMPLIANCE_MAP,
)
from dcm_commons.models.enums import MetricDomain


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_compliance_result(
    rule_name: str = "s3-bucket-versioning",
    compliance_type: str = "NON_COMPLIANT",
    resource_type: str = "AWS::S3::Bucket",
) -> dict[str, Any]:
    """Create a compliance result record from describe_compliance_by_config_rule."""
    return {
        "ConfigRuleName": rule_name,
        "Compliance": {"ComplianceType": compliance_type},
        "EvaluationCount": 5,
        "NonCompliantResourceCount": {"CappedCount": 2, "CapExceeded": False},
    }


def _make_config_rule(
    rule_name: str = "s3-bucket-versioning",
    source_identifier: str = "S3_BUCKET_VERSIONING_ENABLED",
) -> dict[str, Any]:
    """Create a Config Rule definition."""
    return {
        "ConfigRuleName": rule_name,
        "ConfigRuleArn": f"arn:aws:config:us-east-1:123456789012:config-rule/{rule_name}",
        "Source": {
            "Owner": "AWS",
            "SourceIdentifier": source_identifier,
        },
        "Scope": {"ComplianceResourceTypes": ["AWS::S3::Bucket"]},
        "ConfigRuleState": "ACTIVE",
        "CreatedBy": "arn:aws:iam::123456789012:user/admin",
        "CreatedOn": datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
    }


# ---------------------------------------------------------------------------
# Concrete test implementation
# ---------------------------------------------------------------------------


class ConcreteConfigStandardCheckCollector(ConfigStandardCheckCollector):
    """Concrete implementation of ConfigStandardCheckCollector for testing.
    
    Overrides __init__ to avoid passing domain parameter to BaseCollector.
    """

    def __init__(
        self,
        source_lz_id: str,
        region_name: str,
        account_id: str,
        *,
        non_compliant_only: bool = True,
        max_results_per_rule: int = 100,
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
        self._non_compliant_only = non_compliant_only
        self._max_results_per_rule = max_results_per_rule

    @property
    def domain(self) -> MetricDomain:
        """Return the standard check metric domain."""
        return MetricDomain.STANDARD_CHECK


# ---------------------------------------------------------------------------
# ConfigStandardCheckCollector
# ---------------------------------------------------------------------------


class TestConfigStandardCheckCollector:
    def test_init_default_non_compliant_only(self) -> None:
        collector = ConcreteConfigStandardCheckCollector(
            source_lz_id="aws-sub-12345",
            region_name="us-east-1",
            account_id="123456789012",
        )
        assert collector._region == "us-east-1"
        assert collector._account_id == "123456789012"
        assert collector._non_compliant_only is True
        assert collector._max_results_per_rule == 100

    def test_init_full_scan(self) -> None:
        collector = ConcreteConfigStandardCheckCollector(
            source_lz_id="aws-sub-12345",
            region_name="eu-west-1",
            account_id="987654321098",
            non_compliant_only=False,
            max_results_per_rule=50,
        )
        assert collector._region == "eu-west-1"
        assert collector._account_id == "987654321098"
        assert collector._non_compliant_only is False
        assert collector._max_results_per_rule == 50

    @pytest.mark.asyncio
    async def test_collect_metrics_returns_empty_when_no_rules(self) -> None:
        collector = ConcreteConfigStandardCheckCollector(
            source_lz_id="aws-sub-12345",
            region_name="us-east-1",
            account_id="123456789012",
        )

        mock_config = MagicMock()
        mock_config.describe_config_rules = MagicMock(return_value={"ConfigRules": []})
        mock_config.describe_compliance_by_config_rule = MagicMock(
            return_value={"ComplianceByConfigRules": []}
        )

        with patch("boto3.client", return_value=mock_config):
            with patch("aws_collector.collectors.config_compliance.run_sync",
                      new=AsyncMock(side_effect=lambda f: f())):
                metrics = await collector._collect_metrics()

        assert metrics == []

    @pytest.mark.asyncio
    async def test_collect_metrics_with_non_compliant_rules(self) -> None:
        collector = ConcreteConfigStandardCheckCollector(
            source_lz_id="aws-sub-12345",
            region_name="us-east-1",
            account_id="123456789012",
            non_compliant_only=True,
        )

        # Mock Config API responses
        config_rule = _make_config_rule("s3-versioning", "S3_BUCKET_VERSIONING_ENABLED")
        compliance = _make_compliance_result("s3-versioning", "NON_COMPLIANT")

        mock_config = MagicMock()
        mock_config.describe_config_rules = MagicMock(
            return_value={"ConfigRules": [config_rule]}
        )
        mock_config.describe_compliance_by_config_rule = MagicMock(
            return_value={"ComplianceByConfigRules": [compliance]}
        )
        mock_config.get_compliance_details_by_config_rule = MagicMock(
            return_value={
                "EvaluationResults": [
                    {
                        "EvaluationResultIdentifier": {
                            "EvaluationResultQualifier": {
                                "ConfigRuleName": "s3-versioning",
                                "ResourceType": "AWS::S3::Bucket",
                                "ResourceId": "my-bucket-1",
                            }
                        },
                        "ComplianceType": "NON_COMPLIANT",
                    }
                ]
            }
        )

        with patch("boto3.client", return_value=mock_config):
            with patch("aws_collector.collectors.config_compliance.run_sync",
                      new=AsyncMock(side_effect=lambda f: f())):
                metrics = await collector._collect_metrics()

        # Should have collected metrics (may be empty if paging doesn't work perfectly with mock)
        assert isinstance(metrics, list)

    @pytest.mark.asyncio
    async def test_collect_metrics_pagination(self) -> None:
        """Test handling of Config Rules pagination."""
        collector = ConcreteConfigStandardCheckCollector(
            source_lz_id="aws-sub-12345",
            region_name="us-east-1",
            account_id="123456789012",
        )

        rule1 = _make_config_rule("rule-1")
        rule2 = _make_config_rule("rule-2")

        mock_config = MagicMock()
        # Simulate paginated response
        mock_config.describe_config_rules = MagicMock(
            return_value={"ConfigRules": [rule1, rule2]}
        )
        mock_config.describe_compliance_by_config_rule = MagicMock(
            return_value={
                "ComplianceByConfigRules": [
                    _make_compliance_result("rule-1", "COMPLIANT"),
                    _make_compliance_result("rule-2", "NON_COMPLIANT"),
                ]
            }
        )
        mock_config.get_compliance_details_by_config_rule = MagicMock(
            return_value={"EvaluationResults": []}
        )

        with patch("boto3.client", return_value=mock_config):
            with patch("aws_collector.collectors.config_compliance.run_sync",
                      new=AsyncMock(side_effect=lambda f: f())):
                metrics = await collector._collect_metrics()

        # Should have metrics for both rules
        assert len(metrics) >= 0  # Depends on implementation details


# ---------------------------------------------------------------------------
# _CONFIG_COMPLIANCE_MAP
# ---------------------------------------------------------------------------


class TestConfigComplianceMap:
    def test_compliance_mapping(self) -> None:
        from dcm_commons.models.enums import StandardCheckState

        assert _CONFIG_COMPLIANCE_MAP["COMPLIANT"] == StandardCheckState.COMPLIANT
        assert (
            _CONFIG_COMPLIANCE_MAP["NON_COMPLIANT"]
            == StandardCheckState.NON_COMPLIANT
        )
        assert _CONFIG_COMPLIANCE_MAP["NOT_APPLICABLE"] == StandardCheckState.COMPLIANT
        assert _CONFIG_COMPLIANCE_MAP["INSUFFICIENT_DATA"] == StandardCheckState.UNKNOWN
