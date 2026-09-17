"""Tests for WorkflowRunMetric — Databricks Workflows observability (epic 009)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from dcm_commons.models.enums import (
    MetricDomain,
    WorkflowRunStatus,
    WorkflowTriggerType,
)
from dcm_commons.models.payload import MetricPayload
from dcm_commons.models.workflow import WorkflowRunMetric, WorkflowTaskRun

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _make(**overrides: object) -> WorkflowRunMetric:
    base: dict[str, object] = {
        "workflow_id": "job-1",
        "workflow_name": "etl",
        "run_id": "run-1",
        "status": WorkflowRunStatus.SUCCEEDED,
        "start_time": datetime(2026, 6, 22, 2, 0, 0, tzinfo=timezone.utc),
        "end_time": datetime(2026, 6, 22, 2, 5, 0, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return WorkflowRunMetric(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestWorkflowEnums:
    def test_metric_domain_workflow(self) -> None:
        assert MetricDomain.WORKFLOW == "workflow"

    def test_run_status_values(self) -> None:
        assert WorkflowRunStatus.TIMED_OUT == "timed_out"
        assert WorkflowRunStatus.SUCCEEDED == "succeeded"
        assert WorkflowRunStatus.CANCELLED == "cancelled"

    def test_run_status_terminal_and_failure(self) -> None:
        assert WorkflowRunStatus.TIMED_OUT.is_terminal
        assert WorkflowRunStatus.TIMED_OUT.is_failure
        assert WorkflowRunStatus.FAILED.is_failure
        assert not WorkflowRunStatus.RUNNING.is_terminal
        assert not WorkflowRunStatus.SUCCEEDED.is_failure

    def test_trigger_type_values(self) -> None:
        assert WorkflowTriggerType.PERIODIC == "periodic"
        assert WorkflowTriggerType.UNKNOWN == "unknown"


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class TestWorkflowRunMetric:
    def test_duration_auto_derived(self) -> None:
        metric = _make()
        assert metric.duration_seconds == 300.0

    def test_duration_explicit_preserved(self) -> None:
        metric = _make(duration_seconds=123.0)
        assert metric.duration_seconds == 123.0

    def test_running_run_has_no_end_time(self) -> None:
        metric = _make(status=WorkflowRunStatus.RUNNING, end_time=None)
        assert metric.end_time is None
        assert metric.duration_seconds is None

    def test_task_failure_rate_computed(self) -> None:
        metric = _make(tasks_total=4, tasks_failed=1)
        assert metric.task_failure_rate == 0.25

    def test_task_failure_rate_none_when_no_tasks(self) -> None:
        assert _make().task_failure_rate is None
        assert _make(tasks_total=0, tasks_failed=0).task_failure_rate is None

    def test_defaults(self) -> None:
        metric = _make()
        assert metric.retry_count == 0
        assert metric.trigger_type == WorkflowTriggerType.UNKNOWN
        assert metric.schedule_lag_seconds is None
        assert metric.tags == {}

    def test_model_dump_includes_computed_field(self) -> None:
        dumped = _make(tasks_total=2, tasks_failed=1).model_dump()
        assert dumped["task_failure_rate"] == 0.5
        assert dumped["status"] == "succeeded"

    def test_frozen(self) -> None:
        metric = _make()
        try:
            metric.run_id = "other"  # type: ignore[misc]
        except Exception:
            return
        raise AssertionError("WorkflowRunMetric should be frozen")


# ---------------------------------------------------------------------------
# Task grain (epic 009 addendum)
# ---------------------------------------------------------------------------


def _make_task(**overrides: object) -> WorkflowTaskRun:
    base: dict[str, object] = {
        "task_id": "task-run-1",
        "task_key": "ingest",
        "status": WorkflowRunStatus.SUCCEEDED,
        "start_time": datetime(2026, 6, 22, 2, 0, 0, tzinfo=timezone.utc),
        "end_time": datetime(2026, 6, 22, 2, 2, 0, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return WorkflowTaskRun(**base)  # type: ignore[arg-type]


class TestWorkflowTaskRun:
    def test_task_duration_auto_derived(self) -> None:
        assert _make_task().duration_seconds == 120.0

    def test_task_duration_explicit_preserved(self) -> None:
        assert _make_task(duration_seconds=55.0).duration_seconds == 55.0

    def test_running_task_has_no_duration(self) -> None:
        task = _make_task(status=WorkflowRunStatus.RUNNING, end_time=None)
        assert task.end_time is None
        assert task.duration_seconds is None

    def test_task_defaults(self) -> None:
        task = _make_task()
        assert task.attempt_number == 0
        assert task.cluster_instance_id is None
        assert task.error_message is None

    def test_task_frozen(self) -> None:
        task = _make_task()
        try:
            task.task_id = "other"  # type: ignore[misc]
        except Exception:
            return
        raise AssertionError("WorkflowTaskRun should be frozen")


class TestWorkflowRunMetricTasks:
    def test_tasks_default_empty(self) -> None:
        assert _make().tasks == []

    def test_nested_tasks_populated(self) -> None:
        metric = _make(
            tasks=[
                {
                    "task_id": "t-1",
                    "task_key": "ingest",
                    "status": "succeeded",
                    "start_time": datetime(2026, 6, 22, 2, 0, 0, tzinfo=timezone.utc),
                    "end_time": datetime(2026, 6, 22, 2, 3, 0, tzinfo=timezone.utc),
                },
                {"task_id": "t-2", "task_key": "load", "status": "failed"},
            ]
        )
        assert len(metric.tasks) == 2
        assert metric.tasks[0].task_id == "t-1"
        assert metric.tasks[0].duration_seconds == 180.0
        assert metric.tasks[1].status == WorkflowRunStatus.FAILED

    def test_tasks_serialized_in_dump(self) -> None:
        dumped = _make(tasks=[_make_task()]).model_dump()
        assert dumped["tasks"][0]["task_id"] == "task-run-1"
        assert dumped["tasks"][0]["status"] == "succeeded"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class TestWorkflowFixtures:
    def test_single_metric_fixture(self) -> None:
        raw = json.loads((FIXTURES_DIR / "workflow_run_metric.json").read_text("utf-8"))
        metric = WorkflowRunMetric.model_validate(raw)
        assert metric.status == WorkflowRunStatus.FAILED
        assert metric.trigger_type == WorkflowTriggerType.PERIODIC
        assert metric.retry_count == 1
        assert metric.tasks_total == 5
        assert metric.tasks_failed == 2
        assert metric.task_failure_rate == 0.4
        assert metric.cluster_instance_id == "0312-151347-reef123"

    def test_payload_fixture(self) -> None:
        raw = (FIXTURES_DIR / "metric_payload_workflow.json").read_text("utf-8")
        payload = MetricPayload.model_validate_json(raw)
        assert payload.schema_version == "1.2"
        assert payload.domain == MetricDomain.WORKFLOW
        assert payload.metric_count == 3
        statuses = {m["status"] for m in payload.metrics}
        assert {"succeeded", "timed_out", "running"} == statuses
