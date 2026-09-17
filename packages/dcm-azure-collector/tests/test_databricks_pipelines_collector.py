"""Tests for DatabricksPipelineCollector — Databricks workflow execution metrics.

Uses mocking to test the collector without real Azure/Databricks API calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from azure_collector.collectors.databricks_pipelines import (
    DatabricksPipelineCollector,
    _map_run_to_metric,
)
from dcm_commons.models.enums import MetricDomain, PipelineRunStatus


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


def _make_job_run(
    run_id: int = 12345,
    job_id: int = 67890,
    run_name: str = "my_job",
    state: str = "SUCCESS",
    start_time: int = 1717670400000,  # 2024-06-06 12:00:00 UTC in ms
    end_time: int = 1717670460000,    # 2024-06-06 12:01:00 UTC in ms
    state_message: str = "",
    tags: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create a mock Databricks job run dict."""
    return {
        "run_id": run_id,
        "job_id": job_id,
        "run_name": run_name,
        "state": state,
        "start_time": start_time,
        "end_time": end_time,
        "state_message": state_message,
        "tags": tags or {},
    }


def _make_workspace(
    name: str = "my-workspace",
    workspace_id: str = "1234567890",
    workspace_url: str = "https://eastus.azuredatabricks.net",
    resource_group: str = "my-rg",
) -> dict[str, str]:
    """Create a mock workspace dict."""
    return {
        "name": name,
        "workspace_id": workspace_id,
        "workspace_url": workspace_url,
        "resource_group": resource_group,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDatabricksPipelineCollector:
    """DatabricksPipelineCollector unit tests."""

    def test_init_default_parameters(self) -> None:
        """Test collector initialization with defaults."""
        from azure.identity import DefaultAzureCredential

        with patch.object(DefaultAzureCredential, "__init__", return_value=None):
            collector = DatabricksPipelineCollector(
                source_lz_id="azure-sub-fa5abbc4",
                subscription_id="12345678-1234-1234-1234-123456789012",
            )
            assert collector._source_lz_id == "azure-sub-fa5abbc4"
            assert collector._subscription_id == "12345678-1234-1234-1234-123456789012"
            assert collector._lookback_hours == 24

    def test_init_custom_lookback(self) -> None:
        """Test collector initialization with custom lookback_hours."""
        from azure.identity import DefaultAzureCredential

        with patch.object(DefaultAzureCredential, "__init__", return_value=None):
            collector = DatabricksPipelineCollector(
                source_lz_id="azure-sub-fa5abbc4",
                subscription_id="12345678-1234-1234-1234-123456789012",
                lookback_hours=72,
            )
            assert collector._lookback_hours == 72

    def test_domain_property(self) -> None:
        """Test that domain returns PIPELINE."""
        from azure.identity import DefaultAzureCredential

        with patch.object(DefaultAzureCredential, "__init__", return_value=None):
            collector = DatabricksPipelineCollector(
                source_lz_id="azure-sub-fa5abbc4",
                subscription_id="12345678-1234-1234-1234-123456789012",
            )
            assert collector.domain == MetricDomain.PIPELINE

    def test_map_run_to_metric_success(self) -> None:
        """Test mapping a successful job run to PipelineMetric."""
        run = _make_job_run(
            run_id=111,
            job_id=222,
            run_name="etl_job",
            state="SUCCESS",
            start_time=1717670400000,
            end_time=1717670460000,
        )
        metric = _map_run_to_metric(
            run,
            workspace_id="abc123",
            workspace_name="dbw-novadatahub-d-03",
        )

        assert metric is not None
        assert metric.run_id == "111"
        assert metric.pipeline_id == "databricks:job:222"
        assert metric.pipeline_name == "etl_job"
        assert metric.status == PipelineRunStatus.SUCCEEDED
        assert metric.start_time == datetime.fromtimestamp(1717670400.0, tz=timezone.utc)
        assert metric.end_time == datetime.fromtimestamp(1717670460.0, tz=timezone.utc)
        assert metric.databricks_workspace_id == "abc123"
        assert metric.databricks_workspace_name == "dbw-novadatahub-d-03"

    def test_map_run_to_metric_failed(self) -> None:
        """Test mapping a failed job run."""
        run = _make_job_run(
            run_id=333,
            job_id=444,
            state="FAILED",
            state_message="Task failed with error: data validation failed",
        )
        metric = _map_run_to_metric(run, workspace_id="xyz789")

        assert metric is not None
        assert metric.status == PipelineRunStatus.FAILED
        assert metric.error_message == "Task failed with error: data validation failed"

    def test_map_run_to_metric_running(self) -> None:
        """Test mapping a running job run."""
        run = _make_job_run(
            run_id=555,
            job_id=666,
            state="RUNNING",
            end_time=None,  # No end time for running jobs
        )
        metric = _map_run_to_metric(run, workspace_id="test-ws")

        assert metric is not None
        assert metric.status == PipelineRunStatus.RUNNING
        assert metric.end_time is None

    def test_map_run_to_metric_skipped(self) -> None:
        """Test mapping a skipped job run."""
        run = _make_job_run(state="SKIPPED")
        metric = _map_run_to_metric(run, workspace_id="test-ws")

        assert metric is not None
        assert metric.status == PipelineRunStatus.SKIPPED

    def test_map_run_to_metric_error_message_truncation(self) -> None:
        """Test that long error messages are truncated to 2000 chars."""
        long_message = "x" * 3000
        run = _make_job_run(state="FAILED", state_message=long_message)
        metric = _map_run_to_metric(run, workspace_id="test-ws")

        assert metric is not None
        assert len(metric.error_message or "") <= 2000

    def test_map_run_to_metric_missing_run_id(self) -> None:
        """Test that runs without run_id are skipped."""
        run = _make_job_run(run_id="")  # Empty run_id
        metric = _map_run_to_metric(run, workspace_id="test-ws")

        assert metric is None

    def test_map_run_to_metric_missing_job_id(self) -> None:
        """Test that runs without job_id are skipped."""
        run = _make_job_run()
        run["job_id"] = ""  # Remove job_id
        metric = _map_run_to_metric(run, workspace_id="test-ws")

        assert metric is None

    def test_map_run_to_metric_with_tags(self) -> None:
        """Test that job run tags are preserved."""
        tags = {"env": "prod", "team": "data"}
        run = _make_job_run(tags=tags)
        metric = _map_run_to_metric(run, workspace_id="test-ws")

        assert metric is not None
        assert metric.tags == tags

    def test_map_run_to_metric_cancelled(self) -> None:
        """Test mapping a cancelled job run."""
        run = _make_job_run(state="CANCELLED")
        metric = _map_run_to_metric(run, workspace_id="test-ws")

        assert metric is not None
        assert metric.status == PipelineRunStatus.CANCELLED

    def test_map_run_to_metric_queued(self) -> None:
        """Test mapping a queued (pending) job run."""
        run = _make_job_run(state="PENDING")
        metric = _map_run_to_metric(run, workspace_id="test-ws")

        assert metric is not None
        assert metric.status == PipelineRunStatus.QUEUED

    def test_map_run_to_metric_api21_state_object(self) -> None:
        """Test mapping REST API 2.1 runs where state is an object."""
        run = {
            "run_id": 989038754501220,
            "job_id": 1041221827855698,
            "run_name": "[nova-dev] NOVA Lab — Live Data Refresh",
            "state": {
                "life_cycle_state": "INTERNAL_ERROR",
                "result_state": "FAILED",
                "state_message": "Task refresh_data failed",
            },
            "start_time": 1782857302520,
            "end_time": 1782857305323,
        }
        metric = _map_run_to_metric(run, workspace_id="7405618090331145")

        assert metric is not None
        assert metric.status == PipelineRunStatus.FAILED
        assert metric.error_message == "Task refresh_data failed"
        assert metric.pipeline_name == "[nova-dev] NOVA Lab — Live Data Refresh"

    def test_map_run_to_metric_api21_running_object(self) -> None:
        """Test mapping in-flight runs with life_cycle_state only."""
        run = {
            "run_id": 1,
            "job_id": 2,
            "run_name": "etl",
            "state": {"life_cycle_state": "RUNNING"},
            "start_time": 1717670400000,
        }
        metric = _map_run_to_metric(run, workspace_id="ws")

        assert metric is not None
        assert metric.status == PipelineRunStatus.RUNNING

    @pytest.mark.asyncio
    async def test_collect_metrics_no_workspaces(self) -> None:
        """Test collection when no Databricks workspaces exist."""
        mock_mgmt_token = "mgmt-token"
        mock_db_token = "db-token"

        with patch(
            "azure_collector.collectors.databricks_pipelines.get_mgmt_token",
            new_callable=AsyncMock,
            return_value=mock_mgmt_token,
        ):
            with patch(
                "azure_collector.collectors.databricks_pipelines.get_databricks_token",
                new_callable=AsyncMock,
                return_value=mock_db_token,
            ):
                with patch(
                    "azure_collector.collectors.databricks_pipelines._list_workspaces",
                    new_callable=AsyncMock,
                    return_value=[],
                ):
                    from azure.identity import DefaultAzureCredential

                    with patch.object(
                        DefaultAzureCredential, "__init__", return_value=None
                    ):
                        collector = DatabricksPipelineCollector(
                            source_lz_id="azure-sub-fa5abbc4",
                            subscription_id="12345678-1234-1234-1234-123456789012",
                        )
                        metrics = await collector._collect_metrics()

        assert metrics == []

    @pytest.mark.asyncio
    async def test_collect_metrics_with_job_runs(self) -> None:
        """Test collection when job runs exist."""
        from azure.identity import DefaultAzureCredential

        mock_workspace = _make_workspace()
        mock_runs = [
            _make_job_run(run_id=1, job_id=100, state="SUCCESS"),
            _make_job_run(run_id=2, job_id=101, state="FAILED"),
        ]

        with patch.object(DefaultAzureCredential, "__init__", return_value=None):
            with patch(
                "azure_collector.collectors.databricks_pipelines.get_mgmt_token",
                new_callable=AsyncMock,
                return_value="mgmt-token",
            ):
                with patch(
                    "azure_collector.collectors.databricks_pipelines.get_databricks_token",
                    new_callable=AsyncMock,
                    return_value="db-token",
                ):
                    with patch(
                        "azure_collector.collectors.databricks_pipelines._list_workspaces",
                        new_callable=AsyncMock,
                        return_value=[mock_workspace],
                    ):
                        with patch(
                            "azure_collector.collectors.databricks_pipelines._list_job_runs",
                            new_callable=AsyncMock,
                            return_value=mock_runs,
                        ):
                            collector = DatabricksPipelineCollector(
                                source_lz_id="azure-sub-fa5abbc4",
                                subscription_id="12345678-1234-1234-1234-123456789012",
                            )
                            metrics = await collector._collect_metrics()

        assert len(metrics) == 2
        assert metrics[0]["status"] == "succeeded"
        assert metrics[1]["status"] == "failed"

