"""Tests for DatabricksWorkflowCollector — Databricks Workflows observability (epic 009).

Mocks all Azure/Databricks API calls; no network access.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from azure_collector.collectors.databricks_workflows import (
    DatabricksWorkflowCollector,
    _compute_schedule_lag,
    _count_task_failures,
    _map_run_to_metric,
    _map_tasks,
    _normalize_quartz,
    _parse_run_state,
    _parse_trigger,
    _previous_fire,
)
from dcm_commons.models.enums import (
    MetricDomain,
    WorkflowRunStatus,
    WorkflowTriggerType,
)

_MOD = "azure_collector.collectors.databricks_workflows"


def _make_run(
    run_id: int = 111,
    job_id: int = 222,
    run_name: str = "etl_job",
    result_state: str = "SUCCESS",
    life_cycle_state: str = "TERMINATED",
    start_time: int = 1717670400000,  # 2024-06-06 12:00:00 UTC ms
    end_time: int | None = 1717670460000,  # +60s
    **extra: Any,
) -> dict[str, Any]:
    run: dict[str, Any] = {
        "run_id": run_id,
        "job_id": job_id,
        "run_name": run_name,
        "state": {
            "life_cycle_state": life_cycle_state,
            "result_state": result_state,
            "state_message": extra.pop("state_message", ""),
        },
        "start_time": start_time,
    }
    if end_time is not None:
        run["end_time"] = end_time
    run.update(extra)
    return run


def _make_workspace() -> dict[str, str]:
    return {
        "name": "dbw-prod-01",
        "workspace_id": "7405618090331145",
        "workspace_url": "https://adb-123.19.azuredatabricks.net",
        "resource_group": "rg-data",
    }


# ---------------------------------------------------------------------------
# Collector basics
# ---------------------------------------------------------------------------


class TestCollectorBasics:
    def test_domain(self) -> None:
        from azure.identity import DefaultAzureCredential

        with patch.object(DefaultAzureCredential, "__init__", return_value=None):
            c = DatabricksWorkflowCollector(
                source_lz_id="azure-sub-fa5abbc4",
                subscription_id="sub-1",
            )
            assert c.domain == MetricDomain.WORKFLOW
            assert c._lookback_hours == 24


# ---------------------------------------------------------------------------
# State mapping
# ---------------------------------------------------------------------------


class TestStateMapping:
    def test_success(self) -> None:
        status, _ = _parse_run_state(_make_run(result_state="SUCCESS"))
        assert status == WorkflowRunStatus.SUCCEEDED

    def test_failed(self) -> None:
        status, msg = _parse_run_state(
            _make_run(result_state="FAILED", state_message="boom")
        )
        assert status == WorkflowRunStatus.FAILED
        assert msg == "boom"

    def test_timed_out(self) -> None:
        status, _ = _parse_run_state(_make_run(result_state="TIMEDOUT"))
        assert status == WorkflowRunStatus.TIMED_OUT

    def test_cancelled(self) -> None:
        status, _ = _parse_run_state(_make_run(result_state="CANCELED"))
        assert status == WorkflowRunStatus.CANCELLED

    def test_running_lifecycle(self) -> None:
        run = {"state": {"life_cycle_state": "RUNNING"}}
        assert _parse_run_state(run)[0] == WorkflowRunStatus.RUNNING

    def test_queued_lifecycle(self) -> None:
        run = {"state": {"life_cycle_state": "PENDING"}}
        assert _parse_run_state(run)[0] == WorkflowRunStatus.QUEUED

    def test_status_object_new_api(self) -> None:
        run = {
            "status": {
                "state": "TERMINATED",
                "termination_details": {"code": "RUN_TIMEOUT", "message": "too long"},
            }
        }
        status, msg = _parse_run_state(run)
        assert status == WorkflowRunStatus.TIMED_OUT
        assert msg == "too long"

    def test_status_object_running(self) -> None:
        run = {"status": {"state": "RUNNING"}}
        assert _parse_run_state(run)[0] == WorkflowRunStatus.RUNNING


# ---------------------------------------------------------------------------
# Trigger mapping
# ---------------------------------------------------------------------------


class TestTriggerMapping:
    def test_periodic(self) -> None:
        assert _parse_trigger({"trigger": "PERIODIC"}) == WorkflowTriggerType.PERIODIC

    def test_one_time(self) -> None:
        assert _parse_trigger({"trigger": "ONE_TIME"}) == WorkflowTriggerType.ONE_TIME

    def test_file_arrival(self) -> None:
        assert _parse_trigger({"trigger": "FILE_ARRIVAL"}) == WorkflowTriggerType.FILE_ARRIVAL

    def test_unknown(self) -> None:
        assert _parse_trigger({}) == WorkflowTriggerType.UNKNOWN
        assert _parse_trigger({"trigger": "WHATEVER"}) == WorkflowTriggerType.UNKNOWN


# ---------------------------------------------------------------------------
# Task failure counting
# ---------------------------------------------------------------------------


class TestTaskFailures:
    def test_no_tasks(self) -> None:
        assert _count_task_failures({}) == (None, None)

    def test_mixed_tasks(self) -> None:
        run = {
            "tasks": [
                {"state": {"result_state": "SUCCESS"}},
                {"state": {"result_state": "FAILED"}},
                {"state": {"result_state": "TIMEDOUT"}},
            ]
        }
        assert _count_task_failures(run) == (3, 2)

    def test_new_api_task_status(self) -> None:
        run = {
            "tasks": [
                {"status": {"termination_details": {"code": "SUCCESS"}}},
                {"status": {"termination_details": {"code": "INTERNAL_ERROR"}}},
            ]
        }
        assert _count_task_failures(run) == (2, 1)


# ---------------------------------------------------------------------------
# Task grain mapping (epic 009 addendum — task_id)
# ---------------------------------------------------------------------------


class TestMapTasks:
    def test_no_tasks(self) -> None:
        assert _map_tasks({}) == []
        assert _map_tasks({"tasks": []}) == []

    def test_maps_task_fields(self) -> None:
        run = {
            "tasks": [
                {
                    "run_id": 9001,
                    "task_key": "ingest",
                    "state": {"result_state": "SUCCESS"},
                    "start_time": 1717670400000,
                    "end_time": 1717670460000,  # +60s
                    "attempt_number": 0,
                    "cluster_instance": {"cluster_id": "0312-reef"},
                },
                {
                    "run_id": 9002,
                    "task_key": "load",
                    "state": {"result_state": "FAILED", "state_message": "boom"},
                    "start_time": 1717670460000,
                    "end_time": 1717670470000,  # +10s
                },
            ]
        }
        tasks = _map_tasks(run)
        assert len(tasks) == 2
        assert tasks[0].task_id == "9001"
        assert tasks[0].task_key == "ingest"
        assert tasks[0].status == WorkflowRunStatus.SUCCEEDED
        assert tasks[0].duration_seconds == 60.0
        assert tasks[0].cluster_instance_id == "0312-reef"
        assert tasks[1].task_id == "9002"
        assert tasks[1].status == WorkflowRunStatus.FAILED
        assert tasks[1].error_message == "boom"
        assert tasks[1].duration_seconds == 10.0

    def test_skips_task_without_run_id(self) -> None:
        run = {"tasks": [{"task_key": "orphan", "state": {"result_state": "SUCCESS"}}]}
        assert _map_tasks(run) == []

    def test_map_run_populates_nested_tasks(self) -> None:
        run = _make_run(
            tasks=[
                {"run_id": 1, "task_key": "a", "state": {"result_state": "SUCCESS"}},
                {"run_id": 2, "task_key": "b", "state": {"result_state": "FAILED"}},
            ]
        )
        m = _map_run_to_metric(run, workspace_id="ws")
        assert m is not None
        assert len(m.tasks) == 2
        assert {t.task_id for t in m.tasks} == {"1", "2"}
        assert m.tasks_total == 2  # run-level aggregate unchanged
        assert m.tasks_failed == 1


# ---------------------------------------------------------------------------
# Full mapping
# ---------------------------------------------------------------------------


class TestMapRunToMetric:
    def test_full_success(self) -> None:
        run = _make_run(
            result_state="SUCCESS",
            trigger="PERIODIC",
            queue_duration=12000,
            setup_duration=34000,
            execution_duration=402000,
            cleanup_duration=15000,
            run_duration=463000,
            attempt_number=1,
            creator_user_name="svc@example.com",
            run_page_url="https://x/run/1",
            run_type="JOB_RUN",
            cluster_instance={"cluster_id": "0312-reef"},
            tasks=[
                {"state": {"result_state": "SUCCESS"}},
                {"state": {"result_state": "SUCCESS"}},
            ],
        )
        m = _map_run_to_metric(run, workspace_id="ws-1", workspace_name="dbw-prod-01")
        assert m is not None
        assert m.workflow_id == "222"
        assert m.run_id == "111"
        assert m.workflow_name == "etl_job"
        assert m.status == WorkflowRunStatus.SUCCEEDED
        assert m.trigger_type == WorkflowTriggerType.PERIODIC
        assert m.duration_seconds == 463.0
        assert m.queued_duration_seconds == 12.0
        assert m.setup_duration_seconds == 34.0
        assert m.execution_duration_seconds == 402.0
        assert m.cleanup_duration_seconds == 15.0
        assert m.retry_count == 1
        assert m.tasks_total == 2
        assert m.tasks_failed == 0
        assert m.task_failure_rate == 0.0
        assert m.cluster_instance_id == "0312-reef"
        assert m.creator_user_name == "svc@example.com"
        assert m.run_page_url == "https://x/run/1"
        assert m.workspace_id == "ws-1"
        assert m.workspace_name == "dbw-prod-01"
        assert m.schedule_lag_seconds is None

    def test_schedule_lag_computed_for_periodic_run(self) -> None:
        # start_time = 2024-06-06 12:00:30 UTC; cron fires daily at 12:00:00.
        run = _make_run(
            trigger="PERIODIC",
            start_time=1717675230000,  # 12:00:30 UTC
            end_time=1717675290000,
        )
        schedules = {
            "222": {
                "quartz_cron_expression": "0 0 12 * * ?",
                "timezone_id": "UTC",
                "pause_status": "UNPAUSED",
            }
        }
        m = _map_run_to_metric(run, workspace_id="ws", schedules=schedules)
        assert m is not None
        assert m.schedule_lag_seconds == 30.0

    def test_schedule_lag_none_for_non_periodic_run(self) -> None:
        run = _make_run(trigger="ONE_TIME")
        schedules = {
            "222": {"quartz_cron_expression": "0 0 12 * * ?", "timezone_id": "UTC"}
        }
        m = _map_run_to_metric(run, workspace_id="ws", schedules=schedules)
        assert m is not None
        assert m.schedule_lag_seconds is None

    def test_schedule_lag_none_when_schedule_unknown(self) -> None:
        run = _make_run(trigger="PERIODIC")
        m = _map_run_to_metric(run, workspace_id="ws", schedules={})
        assert m is not None
        assert m.schedule_lag_seconds is None


        m = _map_run_to_metric(_make_run(), workspace_id="ws")
        assert m is not None
        assert m.duration_seconds == 60.0

    def test_running_no_end_time(self) -> None:
        run = {
            "run_id": 5,
            "job_id": 6,
            "run_name": "live",
            "state": {"life_cycle_state": "RUNNING"},
            "start_time": 1717670400000,
        }
        m = _map_run_to_metric(run, workspace_id="ws")
        assert m is not None
        assert m.status == WorkflowRunStatus.RUNNING
        assert m.end_time is None
        assert m.duration_seconds is None

    def test_timed_out_task_failure_rate(self) -> None:
        run = _make_run(
            result_state="TIMEDOUT",
            tasks=[
                {"state": {"result_state": "SUCCESS"}},
                {"state": {"result_state": "SUCCESS"}},
                {"state": {"result_state": "SUCCESS"}},
                {"state": {"result_state": "TIMEDOUT"}},
            ],
        )
        m = _map_run_to_metric(run, workspace_id="ws")
        assert m is not None
        assert m.status == WorkflowRunStatus.TIMED_OUT
        assert m.task_failure_rate == 0.25

    def test_error_message_truncated(self) -> None:
        run = _make_run(result_state="FAILED", state_message="x" * 3000)
        m = _map_run_to_metric(run, workspace_id="ws")
        assert m is not None
        assert len(m.error_message or "") == 2000

    def test_missing_run_id(self) -> None:
        run = _make_run()
        run["run_id"] = ""
        assert _map_run_to_metric(run, workspace_id="ws") is None

    def test_missing_job_id(self) -> None:
        run = _make_run()
        run["job_id"] = ""
        assert _map_run_to_metric(run, workspace_id="ws") is None

    def test_default_retry_count(self) -> None:
        m = _map_run_to_metric(_make_run(), workspace_id="ws")
        assert m is not None
        assert m.retry_count == 0


# ---------------------------------------------------------------------------
# _collect_metrics orchestration
# ---------------------------------------------------------------------------


class TestCollectMetrics:
    @pytest.mark.asyncio
    async def test_no_workspaces(self) -> None:
        from azure.identity import DefaultAzureCredential

        with patch.object(DefaultAzureCredential, "__init__", return_value=None), patch(
            f"{_MOD}.get_mgmt_token", new_callable=AsyncMock, return_value="m"
        ), patch(
            f"{_MOD}.get_databricks_token", new_callable=AsyncMock, return_value="d"
        ), patch(
            f"{_MOD}._list_workspaces", new_callable=AsyncMock, return_value=[]
        ):
            c = DatabricksWorkflowCollector(source_lz_id="lz", subscription_id="s")
            assert await c._collect_metrics() == []

    @pytest.mark.asyncio
    async def test_with_runs(self) -> None:
        from azure.identity import DefaultAzureCredential

        runs = [
            _make_run(run_id=1, job_id=10, result_state="SUCCESS"),
            _make_run(run_id=2, job_id=11, result_state="FAILED"),
            _make_run(run_id=3, job_id=12, result_state="TIMEDOUT"),
        ]
        with patch.object(DefaultAzureCredential, "__init__", return_value=None), patch(
            f"{_MOD}.get_mgmt_token", new_callable=AsyncMock, return_value="m"
        ), patch(
            f"{_MOD}.get_databricks_token", new_callable=AsyncMock, return_value="d"
        ), patch(
            f"{_MOD}._list_workspaces",
            new_callable=AsyncMock,
            return_value=[_make_workspace()],
        ), patch(
            f"{_MOD}._list_workflow_runs", new_callable=AsyncMock, return_value=runs
        ), patch(
            f"{_MOD}._list_job_schedules", new_callable=AsyncMock, return_value={}
        ):
            c = DatabricksWorkflowCollector(source_lz_id="lz", subscription_id="s")
            metrics = await c._collect_metrics()

        assert len(metrics) == 3
        assert [m["status"] for m in metrics] == ["succeeded", "failed", "timed_out"]
        assert metrics[0]["workspace_id"] == "7405618090331145"

    @pytest.mark.asyncio
    async def test_workspace_failure_isolated(self) -> None:
        from azure.identity import DefaultAzureCredential

        with patch.object(DefaultAzureCredential, "__init__", return_value=None), patch(
            f"{_MOD}.get_mgmt_token", new_callable=AsyncMock, return_value="m"
        ), patch(
            f"{_MOD}.get_databricks_token", new_callable=AsyncMock, return_value="d"
        ), patch(
            f"{_MOD}._list_workspaces",
            new_callable=AsyncMock,
            return_value=[_make_workspace()],
        ), patch(
            f"{_MOD}._list_workflow_runs",
            new_callable=AsyncMock,
            side_effect=RuntimeError("403 denied"),
        ):
            c = DatabricksWorkflowCollector(source_lz_id="lz", subscription_id="s")
            assert await c._collect_metrics() == []


def test_start_time_fallback_is_utc() -> None:
    run = {"run_id": 9, "job_id": 9, "run_name": "x", "state": {"life_cycle_state": "RUNNING"}}
    m = _map_run_to_metric(run, workspace_id="ws")
    assert m is not None
    assert m.start_time.tzinfo is not None
    # Fallback time is "now" — sanity bound.
    assert m.start_time <= datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Schedule-lag helpers (quartz cron)
# ---------------------------------------------------------------------------


class TestQuartzHelpers:
    def test_normalize_drops_year_and_maps_question_mark(self) -> None:
        assert _normalize_quartz("0 0 12 * * ? *") == "0 0 12 * * *"
        assert _normalize_quartz("0 30 8 ? * MON-FRI") == "0 30 8 * * MON-FRI"

    def test_normalize_rejects_wrong_field_count(self) -> None:
        assert _normalize_quartz("0 12 * *") is None

    def test_previous_fire_daily_noon_utc(self) -> None:
        at = datetime(2024, 6, 6, 12, 0, 30, tzinfo=timezone.utc)
        prev = _previous_fire("0 0 12 * * ?", "UTC", at)
        assert prev is not None
        assert prev.astimezone(timezone.utc) == datetime(2024, 6, 6, 12, 0, 0, tzinfo=timezone.utc)

    def test_previous_fire_bad_cron_returns_none(self) -> None:
        at = datetime(2024, 6, 6, 12, 0, 30, tzinfo=timezone.utc)
        assert _previous_fire("not a cron", "UTC", at) is None

    def test_previous_fire_unknown_timezone_falls_back_to_utc(self) -> None:
        at = datetime(2024, 6, 6, 12, 0, 30, tzinfo=timezone.utc)
        prev = _previous_fire("0 0 12 * * ?", "Mars/Olympus", at)
        assert prev is not None

    def test_compute_schedule_lag_respects_timezone(self) -> None:
        # Cron fires 08:00 America/New_York (EDT = UTC-4) => 12:00 UTC.
        run = _make_run(trigger="PERIODIC", start_time=1717680060000)  # 13:20:30 UTC
        schedules = {
            "222": {
                "quartz_cron_expression": "0 0 8 * * ?",
                "timezone_id": "America/New_York",
            }
        }
        # 13:20:30 UTC - 12:00:00 UTC = 4830 s
        at = datetime(2024, 6, 6, 13, 20, 30, tzinfo=timezone.utc)
        lag = _compute_schedule_lag(run, at, schedules)
        assert lag == 4830.0

