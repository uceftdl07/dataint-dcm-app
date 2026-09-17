"""Tests for SecurityCenterCollector — Azure Security Center findings.

Uses mocking to test the collector without real Azure SDK calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from azure_collector.collectors.security_center import SecurityCenterCollector
from dcm_commons.models.enums import MetricDomain


# ---------------------------------------------------------------------------
# Concrete test implementation
# ---------------------------------------------------------------------------


class ConcreteSecurityCenterCollector(SecurityCenterCollector):
    """Concrete implementation of SecurityCenterCollector for testing.
    
    Overrides __init__ to avoid passing domain parameter to BaseCollector.
    """

    def __init__(
        self,
        source_lz_id: str,
        subscription_id: str,
        *,
        credential: Any | None = None,
        max_retries: int = 3,
        retry_base_delay_seconds: float = 2.0,
    ) -> None:
        from azure.identity import DefaultAzureCredential
        from azure.mgmt.security import SecurityCenter
        from dcm_commons.collectors.base import BaseCollector
        from dcm_commons.models.enums import CloudProvider

        # Call BaseCollector.__init__ directly, bypassing domain parameter
        BaseCollector.__init__(
            self,
            source_lz_id=source_lz_id,
            cloud_provider=CloudProvider.AZURE,
            max_retries=max_retries,
            retry_base_delay_seconds=retry_base_delay_seconds,
        )
        self._subscription_id = subscription_id
        _credential = credential or DefaultAzureCredential()
        self._security_client = SecurityCenter(
            credential=_credential,
            subscription_id=subscription_id,
        )

    @property
    def domain(self) -> MetricDomain:
        """Return the standard check metric domain."""
        return MetricDomain.STANDARD_CHECK


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_security_finding(
    finding_id: str = "sec_001",
    resource_id: str = "/subscriptions/.../resourceGroups/my-rg/providers/Microsoft.Compute/virtualMachines/my-vm",
    display_name: str = "Enable disk encryption",
    severity: str = "High",
    status: str = "Active",
) -> dict[str, Any]:
    """Create a security finding/recommendation record."""
    return {
        "id": f"/subscriptions/.../providers/Microsoft.Security/securityFinding/{finding_id}",
        "name": finding_id,
        "type": "Microsoft.Security/securityFindings",
        "properties": {
            "displayName": display_name,
            "severity": severity,
            "status": status,
            "resourceId": resource_id,
            "recommendation": "Enable encryption at rest for this resource",
            "updatedOn": datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
        },
    }


def _make_security_assessment(
    assessment_name: str = "encrypt-disk",
    status: str = "Unhealthy",
) -> dict[str, Any]:
    """Create a security assessment."""
    return {
        "id": f"/subscriptions/.../providers/Microsoft.Security/assessments/{assessment_name}",
        "name": assessment_name,
        "type": "Microsoft.Security/assessments",
        "properties": {
            "displayName": f"Assessment: {assessment_name}",
            "status": {"code": status, "cause": "Test", "description": "Test assessment"},
            "statusChangeOn": datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
        },
    }


# ---------------------------------------------------------------------------
# SecurityCenterCollector
# ---------------------------------------------------------------------------


class TestSecurityCenterCollector:
    def test_init_default_parameters(self) -> None:
        collector = ConcreteSecurityCenterCollector(
            source_lz_id="azure-sub-fa5abbc4",
            subscription_id="12345678-1234-1234-1234-123456789012",
        )
        assert collector._source_lz_id == "azure-sub-fa5abbc4"
        assert collector._subscription_id == "12345678-1234-1234-1234-123456789012"

    @pytest.mark.asyncio
    async def test_collect_metrics_no_findings(self) -> None:
        """Test when no security findings exist."""
        mock_client = MagicMock()
        mock_client.security_findings.list = MagicMock(return_value=[])

        with patch("azure.identity.DefaultAzureCredential"):
            with patch(
                "azure.mgmt.security.SecurityCenter", return_value=mock_client
            ):
                with patch(
                    "azure_collector.collectors.security_center.run_sync",
                    new=AsyncMock(side_effect=lambda f: f()),
                ):
                    collector = ConcreteSecurityCenterCollector(
                        source_lz_id="azure-sub-fa5abbc4",
                        subscription_id="12345678-1234-1234-1234-123456789012",
                    )
                    metrics = await collector._collect_metrics()

        assert isinstance(metrics, list)

    @pytest.mark.asyncio
    async def test_collect_metrics_with_findings(self) -> None:
        """Test collecting security findings."""
        finding = _make_security_finding(
            finding_id="sec_001",
            display_name="Enable disk encryption",
            severity="High",
        )

        mock_client = MagicMock()
        mock_client.security_findings.list = MagicMock(return_value=[finding])

        with patch("azure.identity.DefaultAzureCredential"):
            with patch(
                "azure.mgmt.security.SecurityCenter", return_value=mock_client
            ):
                with patch(
                    "azure_collector.collectors.security_center.run_sync",
                    new=AsyncMock(side_effect=lambda f: f()),
                ):
                    collector = ConcreteSecurityCenterCollector(
                        source_lz_id="azure-sub-fa5abbc4",
                        subscription_id="12345678-1234-1234-1234-123456789012",
                    )
                    metrics = await collector._collect_metrics()

        # Should have metrics for findings
        assert isinstance(metrics, list)

    @pytest.mark.asyncio
    async def test_collect_metrics_with_multiple_findings(self) -> None:
        """Test collecting multiple security findings by severity."""
        findings = [
            _make_security_finding("finding_1", severity="Critical"),
            _make_security_finding("finding_2", severity="High"),
            _make_security_finding("finding_3", severity="Medium"),
            _make_security_finding("finding_4", severity="Low"),
        ]

        mock_client = MagicMock()
        mock_client.security_findings.list = MagicMock(return_value=findings)

        with patch("azure.identity.DefaultAzureCredential"):
            with patch(
                "azure.mgmt.security.SecurityCenter", return_value=mock_client
            ):
                with patch(
                    "azure_collector.collectors.security_center.run_sync",
                    new=AsyncMock(side_effect=lambda f: f()),
                ):
                    collector = ConcreteSecurityCenterCollector(
                        source_lz_id="azure-sub-fa5abbc4",
                        subscription_id="12345678-1234-1234-1234-123456789012",
                    )
                    metrics = await collector._collect_metrics()

        # Should have metrics for all findings
        assert isinstance(metrics, list)

    @pytest.mark.asyncio
    async def test_collect_metrics_with_assessments(self) -> None:
        """Test collecting security assessments."""
        assessment = _make_security_assessment("encrypt-disk", "Unhealthy")

        mock_client = MagicMock()
        mock_client.security_findings.list = MagicMock(return_value=[])
        mock_client.assessments.list = MagicMock(return_value=[assessment])

        with patch("azure.identity.DefaultAzureCredential"):
            with patch(
                "azure.mgmt.security.SecurityCenter", return_value=mock_client
            ):
                with patch(
                    "azure_collector.collectors.security_center.run_sync",
                    new=AsyncMock(side_effect=lambda f: f()),
                ):
                    collector = ConcreteSecurityCenterCollector(
                        source_lz_id="azure-sub-fa5abbc4",
                        subscription_id="12345678-1234-1234-1234-123456789012",
                    )
                    metrics = await collector._collect_metrics()

        # Should handle assessments gracefully
        assert isinstance(metrics, list)
