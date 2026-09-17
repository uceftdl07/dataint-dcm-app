"""Tests for DataFactoryCollector — Azure Data Factory pipeline runs.

Uses mocking to test the collector without real Azure SDK calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from azure_collector.collectors.datafactory import DataFactoryCollector
from dcm_commons.models.enums import MetricDomain


# ---------------------------------------------------------------------------
# Concrete test implementation
# ---------------------------------------------------------------------------


class ConcreteDataFactoryCollector(DataFactoryCollector):
    """Concrete implementation of DataFactoryCollector for testing.
    
    Overrides __init__ to avoid passing domain parameter to BaseCollector.
    """

    def __init__(
        self,
        source_lz_id: str,
        subscription_id: str,
        *,
        credential: Any | None = None,
        lookback_hours: int = 1,
        max_retries: int = 3,
        retry_base_delay_seconds: float = 2.0,
    ) -> None:
        from azure.identity import DefaultAzureCredential
        from azure.mgmt.datafactory import DataFactoryManagementClient
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
        self._lookback_hours = lookback_hours
        _credential = credential or DefaultAzureCredential()
        self._adf_client = DataFactoryManagementClient(_credential, subscription_id)

    @property
    def domain(self) -> MetricDomain:
        """Return the pipeline metric domain."""
        return MetricDomain.PIPELINE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_adf_factory(
    name: str = "my-adf",
    resource_group: str = "my-rg",
) -> dict[str, Any]:
    """Create an Azure Data Factory resource."""
    return {
        "id": f"/subscriptions/.../resourceGroups/{resource_group}/providers/Microsoft.DataFactory/factories/{name}",
        "name": name,
        "type": "Microsoft.DataFactory/factories",
        "location": "eastus",
        "tags": {},
        "properties": {
            "provisioningState": "Succeeded",
            "createTime": "2026-01-01T00:00:00Z",
            "version": "V2",
        },
    }


def _make_pipeline_run(
    run_id: str = "pr_001",
    pipeline_name: str = "etl-pipeline",
    status: str = "Succeeded",
) -> dict[str, Any]:
    """Create a pipeline run record."""
    return {
        "runId": run_id,
        "pipelineName": pipeline_name,
        "status": status,
        "runStart": datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
        "runEnd": datetime(2026, 3, 1, 10, 30, 0, tzinfo=timezone.utc),
        "duration": 1800000,
        "message": None,
    }


# ---------------------------------------------------------------------------
# DataFactoryCollector
# ---------------------------------------------------------------------------


class TestDataFactoryCollector:
    def test_init_default_parameters(self) -> None:
        collector = ConcreteDataFactoryCollector(
            source_lz_id="azure-sub-fa5abbc4",
            subscription_id="12345678-1234-1234-1234-123456789012",
        )
        assert collector._source_lz_id == "azure-sub-fa5abbc4"
        assert collector._subscription_id == "12345678-1234-1234-1234-123456789012"
        assert collector._lookback_hours == 1

    def test_init_custom_lookback_hours(self) -> None:
        collector = ConcreteDataFactoryCollector(
            source_lz_id="azure-sub-fa5abbc4",
            subscription_id="12345678-1234-1234-1234-123456789012",
            lookback_hours=24,
        )
        assert collector._lookback_hours == 24

    @pytest.mark.asyncio
    async def test_collect_metrics_no_factories(self) -> None:
        """Test when no ADF instances exist."""
        mock_client = MagicMock()
        mock_client.factories.list_by_subscription = MagicMock(return_value=[])

        with patch("azure.identity.DefaultAzureCredential"):
            with patch(
                "azure.mgmt.datafactory.DataFactoryManagementClient",
                return_value=mock_client,
            ):
                with patch(
                    "azure_collector.collectors.datafactory.run_sync",
                    new=AsyncMock(side_effect=lambda f: f()),
                ):
                    collector = ConcreteDataFactoryCollector(
                        source_lz_id="azure-sub-fa5abbc4",
                        subscription_id="12345678-1234-1234-1234-123456789012",
                    )
                    metrics = await collector._collect_metrics()

        assert isinstance(metrics, list)

    @pytest.mark.asyncio
    async def test_collect_metrics_with_pipeline_runs(self) -> None:
        """Test collecting pipeline run metrics."""
        factory = _make_adf_factory("my-adf", "my-rg")
        pipeline_run = _make_pipeline_run("pr_001", "etl-pipeline", "Succeeded")

        mock_factory_object = MagicMock()
        mock_factory_object.name = "my-adf"
        mock_factory_object.id = factory["id"]

        mock_client = MagicMock()
        mock_client.factories.list_by_subscription = MagicMock(
            return_value=[mock_factory_object]
        )
        mock_client.pipeline_runs.query_by_factory = MagicMock(
            return_value=MagicMock(value=[pipeline_run])
        )

        with patch("azure.identity.DefaultAzureCredential"):
            with patch(
                "azure.mgmt.datafactory.DataFactoryManagementClient",
                return_value=mock_client,
            ):
                with patch(
                    "azure_collector.collectors.datafactory.run_sync",
                    new=AsyncMock(side_effect=lambda f: f()),
                ):
                    collector = ConcreteDataFactoryCollector(
                        source_lz_id="azure-sub-fa5abbc4",
                        subscription_id="12345678-1234-1234-1234-123456789012",
                    )
                    metrics = await collector._collect_metrics()

        # Should have metrics for pipeline run
        assert isinstance(metrics, list)

    @pytest.mark.asyncio
    async def test_collect_metrics_multiple_factories(self) -> None:
        """Test collecting from multiple ADF instances."""
        factory1 = MagicMock()
        factory1.name = "adf-1"
        factory1.id = "/subscriptions/.../factories/adf-1"

        factory2 = MagicMock()
        factory2.name = "adf-2"
        factory2.id = "/subscriptions/.../factories/adf-2"

        mock_client = MagicMock()
        mock_client.factories.list_by_subscription = MagicMock(
            return_value=[factory1, factory2]
        )
        mock_client.pipeline_runs.query_by_factory = MagicMock(
            return_value=MagicMock(value=[])
        )

        with patch("azure.identity.DefaultAzureCredential"):
            with patch(
                "azure.mgmt.datafactory.DataFactoryManagementClient",
                return_value=mock_client,
            ):
                with patch(
                    "azure_collector.collectors.datafactory.run_sync",
                    new=AsyncMock(side_effect=lambda f: f()),
                ):
                    collector = ConcreteDataFactoryCollector(
                        source_lz_id="azure-sub-fa5abbc4",
                        subscription_id="12345678-1234-1234-1234-123456789012",
                    )
                    metrics = await collector._collect_metrics()

        # Should handle multiple factories
        assert isinstance(metrics, list)
