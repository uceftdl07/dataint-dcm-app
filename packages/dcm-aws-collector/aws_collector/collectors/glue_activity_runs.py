"""AWS Glue job step collector — activity-level metrics for Glue job runs.

Collects the execution steps of recent Glue job runs to provide activity-level
data lineage (rows read, rows written, duration per step).

Key API calls
-------------
``glue.get_jobs(NextToken=...)``
    Paginated list of all Glue job definitions.
``glue.get_job_runs(JobName, MaxResults=N)``
    Most recent runs for a Glue job.
``glue.get_job_run(JobName=..., RunId=..., PredecessorsIncluded=True)``
    Detailed run info — Glue does not expose step-level breakdown via GetJobRun,
    but it exposes JobRunState, ErrorMessage, ExecutionTime, NumberOfWorkers.
    For Glue workflows, ``glue.get_workflow_run(Name, RunId)`` provides node-level
    execution details (each node is an ``ActivityRunMetric``).

Implementation note
-------------------
AWS Glue does not have a true "activity run" concept like ADF.
This collector uses two strategies:
1. **Glue Workflows**: collect node-level execution from workflow runs.
   Each node (job or crawler) in a workflow is mapped to an ActivityRunMetric.
2. **Standalone Jobs**: map the overall job run as a single ActivityRunMetric
   with activity_name = job_name (no sub-step breakdown available from the API).

Lakebase target
---------------
``dcm.monitoring.activity_runs``
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dcm_commons.collectors.base import BaseCollector
from dcm_commons.exceptions import CollectionError
from dcm_commons.logging_utils import get_logger
from dcm_commons.models.activity_run import ActivityRunMetric
from dcm_commons.models.enums import ActivityRunStatus, ActivityType, CloudProvider, MetricDomain

from aws_collector._aws_utils import create_aws_client, map_glue_job_status, run_sync

__all__ = ["GlueActivityRunCollector"]

_logger = get_logger(__name__)

_MAX_RUNS_PER_JOB: int = 10
_MAX_WORKFLOWS: int = 50


def _map_glue_run_status(raw: str | None) -> ActivityRunStatus:
    _map: dict[str, ActivityRunStatus] = {
        "SUCCEEDED": ActivityRunStatus.SUCCEEDED,
        "FAILED": ActivityRunStatus.FAILED,
        "ERROR": ActivityRunStatus.FAILED,
        "RUNNING": ActivityRunStatus.RUNNING,
        "STOPPED": ActivityRunStatus.CANCELLED,
        "STOPPING": ActivityRunStatus.CANCELLED,
        "TIMEOUT": ActivityRunStatus.FAILED,
        "WAITING": ActivityRunStatus.RUNNING,
    }
    return _map.get(raw or "", ActivityRunStatus.RUNNING)


class GlueActivityRunCollector(BaseCollector):
    """Collects activity-level metrics from Glue job runs and workflow nodes.

    Args:
        source_lz_id:   Landing zone identifier.
        region_name:    AWS region to collect from.
        account_id:     AWS account ID (used for tagging / isolation).
        lookback_hours: How many hours back to include job runs.
        max_retries:    Retry attempts on transient failures.
        retry_base_delay_seconds: Base delay for exponential back-off.
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
        super().__init__(
            source_lz_id=source_lz_id,
            cloud_provider=CloudProvider.AWS,
            subscription_or_account_id=account_id,
            max_retries=max_retries,
            retry_base_delay_seconds=retry_base_delay_seconds,
        )
        self._region = region_name
        self._account_id = account_id
        self._lookback_hours = lookback_hours

    async def _collect_metrics(self) -> list[ActivityRunMetric]:
        return await run_sync(self._collect_sync)

    def _collect_sync(self) -> list[ActivityRunMetric]:
        glue = create_aws_client("glue", region_name=self._region)
        metrics: list[ActivityRunMetric] = []

        # Strategy 1: collect from Glue workflow node runs
        try:
            metrics.extend(self._collect_workflow_nodes(glue))
        except Exception as exc:  # noqa: BLE001
            _logger.warning("glue_activity_workflow_skip reason=%s", exc)

        # Strategy 2: fallback — standalone job runs as single-activity metrics
        try:
            metrics.extend(self._collect_standalone_job_runs(glue, existing=metrics))
        except Exception as exc:  # noqa: BLE001
            _logger.warning("glue_activity_job_skip reason=%s", exc)

        _logger.info(
            "glue_activity_collected region=%s total=%d",
            self._region, len(metrics),
        )
        return metrics

    def _collect_workflow_nodes(self, glue: Any) -> list[ActivityRunMetric]:
        """Collect node-level execution details from recent Glue workflow runs."""
        metrics: list[ActivityRunMetric] = []
        paginator = glue.get_paginator("list_workflows")
        workflow_names: list[str] = []
        for page in paginator.paginate(MaxResults=_MAX_WORKFLOWS):
            workflow_names.extend(page.get("Workflows", []))

        for wf_name in workflow_names:
            try:
                runs_resp = glue.get_workflow_runs(Name=wf_name, MaxResults=5)
                for run in runs_resp.get("Runs", []):
                    run_id = run.get("WorkflowRunId", "")
                    graph = run.get("Graph", {})
                    for node in graph.get("Nodes", []):
                        node_name = node.get("Name", "")
                        node_type = node.get("Type", "JOB")  # JOB | CRAWLER | TRIGGER
                        job_detail = node.get("JobDetails", {})
                        runs = job_detail.get("JobRuns", [{}])
                        latest = runs[0] if runs else {}
                        metrics.append(
                            ActivityRunMetric(
                                pipeline_run_id=run_id,
                                pipeline_name=wf_name,
                                activity_name=node_name,
                                activity_type=(
                                    ActivityType.GLUE_JOB_NODE
                                    if node_type == "JOB"
                                    else ActivityType.UNKNOWN
                                ),
                                status=_map_glue_run_status(latest.get("JobRunState")),
                                start_time=latest.get("StartedOn"),
                                end_time=latest.get("CompletedOn"),
                                duration_seconds=latest.get("ExecutionTime"),
                                error_message=latest.get("ErrorMessage"),
                                tags={
                                    "region": self._region,
                                    "account_id": self._account_id,
                                    "workflow": wf_name,
                                },
                            )
                        )
            except Exception as exc:  # noqa: BLE001
                _logger.warning("glue_activity_wf_skip workflow=%s reason=%s", wf_name, exc)

        return metrics

    def _collect_standalone_job_runs(
        self, glue: Any, existing: list[ActivityRunMetric]
    ) -> list[ActivityRunMetric]:
        """Collect standalone job runs not covered by workflow collection."""
        # Avoid double-counting: skip jobs already captured in workflow nodes
        covered_run_ids = {m.pipeline_run_id for m in existing}

        metrics: list[ActivityRunMetric] = []
        paginator = glue.get_paginator("get_jobs")
        for page in paginator.paginate():
            for job in page.get("Jobs", []):
                job_name = job.get("Name", "")
                try:
                    runs_resp = glue.get_job_runs(
                        JobName=job_name, MaxResults=_MAX_RUNS_PER_JOB
                    )
                    for run in runs_resp.get("JobRuns", []):
                        run_id = run.get("Id", "")
                        if run_id in covered_run_ids:
                            continue
                        metrics.append(
                            ActivityRunMetric(
                                pipeline_run_id=run_id,
                                pipeline_name=job_name,
                                activity_name=job_name,  # single-activity mapping
                                activity_type=ActivityType.GLUE_JOB_NODE,
                                status=_map_glue_run_status(run.get("JobRunState")),
                                start_time=run.get("StartedOn"),
                                end_time=run.get("CompletedOn"),
                                duration_seconds=run.get("ExecutionTime"),
                                rows_read=None,   # not exposed by Glue GetJobRun
                                rows_written=None,
                                error_message=run.get("ErrorMessage"),
                                tags={
                                    "region": self._region,
                                    "account_id": self._account_id,
                                    "glue_worker_type": run.get("WorkerType", ""),
                                },
                            )
                        )
                except Exception as exc:  # noqa: BLE001
                    _logger.warning("glue_activity_job_runs_skip job=%s reason=%s", job_name, exc)

        return metrics
