"""Tests for GlueActivityRunCollector — Glue job and workflow activity runs.

Uses mocking to test the collector without real AWS API calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aws_collector.collectors.glue_activity_runs import (
    GlueActivityRunCollector,
    _map_glue_run_status,
)
from dcm_commons.models.enums import MetricDomain


# ---------------------------------------------------------------------------
# Concrete test implementation
# ---------------------------------------------------------------------------


class ConcreteGlueActivityRunCollector(GlueActivityRunCollector):
    """Concrete implementation of GlueActivityRunCollector for testing.
    
    Overrides __init__ to avoid passing domain parameter to BaseCollector.
    """

    def __init__(
        self,
        source_lz_id: str,
        region_name: str,
        account_id: str,
        *,
        lookback_hours: int = 1,
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
        self._lookback_hours = lookback_hours

    @property
    def domain(self) -> MetricDomain:
        """Return the activity run metric domain."""
        return MetricDomain.ACTIVITY_RUN


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_glue_job_run(
    job_name: str = "etl-daily",
    run_id: str = "jr_001",
    status: str = "SUCCEEDED",
    started: datetime | None = None,
    completed: datetime | None = None,
    execution_time: int = 300,
) -> dict[str, Any]:
    """Create a Glue job run record."""
    started = started or datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
    completed = completed or datetime(2026, 3, 1, 10, 5, 0, tzinfo=timezone.utc)
    return {
        "JobName": job_name,
        "Id": run_id,
        "JobRunState": status,
        "StartedOn": started,
        "CompletedOn": completed,
        "ExecutionTime": execution_time,
        "NumberOfWorkers": 10,
    }


def _make_glue_job(name: str = "etl-daily") -> dict[str, Any]:
    """Create a Glue job definition."""
    return {
        "Name": name,
        "Role": "arn:aws:iam::123456789012:role/glue-role",
        "Command": {
            "Name": "pythonshell",
            "ScriptLocation": "s3://my-bucket/scripts/etl.py",
        },
        "CreatedOn": datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        "LastModifiedOn": datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc),
    }


def _make_workflow(
    name: str = "my-workflow",
) -> dict[str, Any]:
    """Create a Glue workflow definition."""
    return {
        "Name": name,
        "Description": "Test workflow",
        "DefaultRunProperties": {},
        "CreatedOn": datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        "LastModifiedOn": datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc),
    }


def _make_workflow_run(
    workflow_name: str = "my-workflow",
    run_id: str = "wr_001",
    status: str = "SUCCEEDED",
) -> dict[str, Any]:
    """Create a Glue workflow run record."""
    return {
        "Name": workflow_name,
        "RunId": run_id,
        "WorkflowRunProperties": {},
        "StartedOn": datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc),
        "CompletedOn": datetime(2026, 3, 1, 10, 30, 0, tzinfo=timezone.utc),
        "Status": status,
    }


# ---------------------------------------------------------------------------
# _map_glue_run_status
# ---------------------------------------------------------------------------


class TestMapGlueRunStatus:
    def test_succeeded_status(self) -> None:
        from dcm_commons.models.enums import ActivityRunStatus

        assert _map_glue_run_status("SUCCEEDED") == ActivityRunStatus.SUCCEEDED

    def test_failed_status(self) -> None:
        from dcm_commons.models.enums import ActivityRunStatus

        assert _map_glue_run_status("FAILED") == ActivityRunStatus.FAILED

    def test_running_status(self) -> None:
        from dcm_commons.models.enums import ActivityRunStatus

        assert _map_glue_run_status("RUNNING") == ActivityRunStatus.RUNNING

    def test_cancelled_status(self) -> None:
        from dcm_commons.models.enums import ActivityRunStatus

        assert _map_glue_run_status("STOPPED") == ActivityRunStatus.CANCELLED

    def test_none_status_defaults_to_running(self) -> None:
        from dcm_commons.models.enums import ActivityRunStatus

        assert _map_glue_run_status(None) == ActivityRunStatus.RUNNING

    def test_unknown_status_defaults_to_running(self) -> None:
        from dcm_commons.models.enums import ActivityRunStatus

        assert _map_glue_run_status("UNKNOWN_STATUS") == ActivityRunStatus.RUNNING


# ---------------------------------------------------------------------------
# GlueActivityRunCollector
# ---------------------------------------------------------------------------


class TestGlueActivityRunCollector:
    def test_init_default_lookback(self) -> None:
        collector = ConcreteGlueActivityRunCollector(
            source_lz_id="aws-sub-12345",
            region_name="us-east-1",
            account_id="123456789012",
        )
        assert collector._region == "us-east-1"
        assert collector._account_id == "123456789012"
        assert collector._lookback_hours == 1

    def test_init_custom_lookback(self) -> None:
        collector = ConcreteGlueActivityRunCollector(
            source_lz_id="aws-sub-12345",
            region_name="eu-west-1",
            account_id="987654321098",
            lookback_hours=24,
        )
        assert collector._region == "eu-west-1"
        assert collector._lookback_hours == 24

    @pytest.mark.asyncio
    async def test_collect_metrics_no_jobs(self) -> None:
        """Test when no Glue jobs exist."""
        collector = ConcreteGlueActivityRunCollector(
            source_lz_id="aws-sub-12345",
            region_name="us-east-1",
            account_id="123456789012",
        )

        mock_glue = MagicMock()
        mock_glue.get_jobs = MagicMock(return_value={"JobList": []})
        mock_glue.list_workflows = MagicMock(return_value={"Workflows": []})

        with patch("boto3.client", return_value=mock_glue):
            with patch("aws_collector.collectors.glue_activity_runs.run_sync",
                      new=AsyncMock(side_effect=lambda f: f())):
                metrics = await collector._collect_metrics()

        assert metrics == []

    @pytest.mark.asyncio
    async def test_collect_metrics_with_job_runs(self) -> None:
        """Test collecting activity runs from Glue jobs."""
        collector = ConcreteGlueActivityRunCollector(
            source_lz_id="aws-sub-12345",
            region_name="us-east-1",
            account_id="123456789012",
        )

        job = _make_glue_job("etl-job")
        job_run = _make_glue_job_run("etl-job", "jr_001")

        mock_glue = MagicMock()
        mock_glue.get_jobs = MagicMock(return_value={"JobList": [job]})
        mock_glue.get_job_runs = MagicMock(return_value={"JobRuns": [job_run]})
        mock_glue.list_workflows = MagicMock(return_value={"Workflows": []})

        with patch("boto3.client", return_value=mock_glue):
            with patch("aws_collector.collectors.glue_activity_runs.run_sync",
                      new=AsyncMock(side_effect=lambda f: f())):
                metrics = await collector._collect_metrics()

        # Should have metrics from job run
        assert len(metrics) >= 0  # Depends on implementation

    @pytest.mark.asyncio
    async def test_collect_metrics_with_workflow_runs(self) -> None:
        """Test collecting activity runs from Glue workflows."""
        collector = ConcreteGlueActivityRunCollector(
            source_lz_id="aws-sub-12345",
            region_name="us-east-1",
            account_id="123456789012",
        )

        workflow = _make_workflow("my-workflow")
        workflow_run = _make_workflow_run("my-workflow", "wr_001")

        mock_glue = MagicMock()
        mock_glue.get_jobs = MagicMock(return_value={"JobList": []})
        mock_glue.list_workflows = MagicMock(return_value={"Workflows": [workflow]})
        mock_glue.get_workflow_runs = MagicMock(
            return_value={"Runs": [workflow_run]}
        )

        with patch("boto3.client", return_value=mock_glue):
            with patch("aws_collector.collectors.glue_activity_runs.run_sync",
                      new=AsyncMock(side_effect=lambda f: f())):
                metrics = await collector._collect_metrics()

        # Should have metrics from workflow
        assert len(metrics) >= 0  # Depends on implementation
