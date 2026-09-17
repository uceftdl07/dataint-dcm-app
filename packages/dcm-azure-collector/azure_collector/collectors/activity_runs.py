"""Azure Data Factory activity run collector — activity-level pipeline details.

For each pipeline run collected in the lookback window, retrieves the
individual activity executions (Copy, Notebook, Lookup, etc.) via the ADF
Management API.  This provides row/byte-level data lineage metrics.

Azure SDK used
--------------
``azure-mgmt-datafactory`` (synchronous) — wrapped in :func:`run_sync`.

Key API calls
-------------
``client.factories.list(subscription_id)``
    Enumerate all ADF instances in the subscription.
``client.pipeline_runs.query_by_factory(resource_group, factory, body)``
    Retrieve pipeline runs updated within the lookback window.
``client.activity_runs.query_by_pipeline_run(resource_group, factory, run_id, body)``
    Retrieve activity executions for a single pipeline run.

Volume management
-----------------
A busy pipeline (ForEach with 1 000 iterations) can produce thousands of
activity runs per pipeline run.  To limit cardinality:
- Only failed or long-running activities are collected when ``failed_only=True``.
- ``max_activities_per_run`` caps the number of activities per pipeline run.
- The default is ``failed_only=False`` (collect all) with a cap of 500.

Lakebase target
---------------
``dcm.monitoring.activity_runs``
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from azure.identity import DefaultAzureCredential  # type: ignore[import-untyped]
from azure.mgmt.datafactory import DataFactoryManagementClient  # type: ignore[import-untyped]
from azure.mgmt.datafactory.models import (  # type: ignore[import-untyped]
    RunFilterParameters,
)

from dcm_commons.collectors.base import BaseCollector
from dcm_commons.exceptions import CollectionError
from dcm_commons.logging_utils import get_logger
from dcm_commons.models.activity_run import ActivityRunMetric
from dcm_commons.models.enums import ActivityRunStatus, ActivityType, CloudProvider, MetricDomain

from azure_collector._azure_utils import map_adf_status, run_sync

__all__ = ["ActivityRunCollector"]

_logger = get_logger(__name__)

# Mapping ADF activity status strings → DCM ActivityRunStatus
_ADF_ACTIVITY_STATUS_MAP: dict[str, ActivityRunStatus] = {
    "Succeeded": ActivityRunStatus.SUCCEEDED,
    "Failed": ActivityRunStatus.FAILED,
    "InProgress": ActivityRunStatus.RUNNING,
    "Cancelled": ActivityRunStatus.CANCELLED,
    "Skipped": ActivityRunStatus.SKIPPED,
}

# Mapping ADF activity type strings → DCM ActivityType
_ADF_ACTIVITY_TYPE_MAP: dict[str, ActivityType] = {
    "Copy": ActivityType.COPY,
    "DatabricksNotebook": ActivityType.DATABRICKS_NOTEBOOK,
    "DatabricksPython": ActivityType.DATABRICKS_NOTEBOOK,
    "DatabricksSparkJar": ActivityType.DATABRICKS_NOTEBOOK,
    "Lookup": ActivityType.LOOKUP,
    "ForEach": ActivityType.FOR_EACH,
    "Wait": ActivityType.WAIT,
    "WebActivity": ActivityType.WEB_ACTIVITY,
    "ExecutePipeline": ActivityType.EXECUTE_PIPELINE,
}


def _map_adf_activity_status(raw: str | None) -> ActivityRunStatus:
    if raw is None:
        return ActivityRunStatus.RUNNING
    return _ADF_ACTIVITY_STATUS_MAP.get(raw, ActivityRunStatus.RUNNING)


def _map_adf_activity_type(raw: str | None) -> ActivityType:
    if raw is None:
        return ActivityType.UNKNOWN
    return _ADF_ACTIVITY_TYPE_MAP.get(raw, ActivityType.UNKNOWN)


class ActivityRunCollector(BaseCollector):
    """Collects activity-level run details from all Data Factories.

    Architecture note
    -----------------
    This collector re-enumerates pipeline runs in the lookback window (same as
    :class:`~azure_collector.collectors.datafactory.DataFactoryCollector`) and
    then fetches the activity executions for each run.  Running both collectors
    in the same cycle results in two API passes over pipeline runs; this is
    acceptable because the ``queryActivityRuns`` API is the only way to get
    activity-level metrics — there is no separate streaming endpoint.

    Args:
        source_lz_id:           Landing zone identifier.
        subscription_id:        Azure subscription ID.
        credential:             Azure identity credential.
        lookback_hours:         Pipeline run history window.
        max_activities_per_run: Maximum activity rows to collect per pipeline run.
                                Prevents cardinality explosion for ForEach pipelines.
        failed_only:            When ``True``, collect only failed activities.
        max_retries:            Retry attempts on transient failures.
        retry_base_delay_seconds: Base delay for exponential back-off.
    """

    def __init__(
        self,
        source_lz_id: str,
        subscription_id: str,
        *,
        credential: Any | None = None,
        lookback_hours: int = 1,
        max_activities_per_run: int = 500,
        failed_only: bool = False,
        max_retries: int = 3,
        retry_base_delay_seconds: float = 2.0,
    ) -> None:
        super().__init__(
            source_lz_id=source_lz_id,
            cloud_provider=CloudProvider.AZURE,
            subscription_or_account_id=subscription_id,
            max_retries=max_retries,
            retry_base_delay_seconds=retry_base_delay_seconds,
        )
        self._subscription_id = subscription_id
        self._credential = credential or DefaultAzureCredential()
        self._lookback_hours = lookback_hours
        self._max_activities_per_run = max_activities_per_run
        self._failed_only = failed_only

    @property
    def domain(self) -> MetricDomain:
        """Return the activity-run metric domain."""
        return MetricDomain.ACTIVITY_RUN

    # ------------------------------------------------------------------
    # BaseCollector implementation
    # ------------------------------------------------------------------

    async def _collect_metrics(self) -> list[dict[str, Any]]:
        """Enumerate all ADF instances and collect activity runs per pipeline."""
        metrics = await run_sync(self._collect_sync)
        return [m.model_dump() for m in metrics]

    def _collect_sync(self) -> list[ActivityRunMetric]:
        client = DataFactoryManagementClient(
            credential=self._credential,
            subscription_id=self._subscription_id,
        )
        now = datetime.now(tz=timezone.utc)
        since = now - timedelta(hours=self._lookback_hours)

        all_metrics: list[ActivityRunMetric] = []

        try:
            factories = list(client.factories.list())
        except Exception as exc:
            raise CollectionError(
                "ActivityRunCollector",
                f"Cannot list factories: {exc}",
            ) from exc

        for factory in factories:
            rg = factory.id.split("/")[4]
            factory_name = factory.name
            try:
                all_metrics.extend(
                    self._collect_factory_activities(client, rg, factory_name, since, now)
                )
            except Exception as exc:  # noqa: BLE001
                _logger.warning(
                    "activity_run_factory_skip factory=%s reason=%s",
                    factory_name, exc,
                )

        _logger.info(
            "activity_run_collected subscription=%s total=%d",
            self._subscription_id, len(all_metrics),
        )
        return all_metrics

    def _collect_factory_activities(
        self,
        client: DataFactoryManagementClient,
        resource_group: str,
        factory_name: str,
        since: datetime,
        until: datetime,
    ) -> list[ActivityRunMetric]:
        """Collect activity runs for all pipeline runs in a single factory."""
        filter_params = RunFilterParameters(
            last_updated_after=since,
            last_updated_before=until,
        )
        pipeline_runs = list(
            client.pipeline_runs.query_by_factory(
                resource_group, factory_name, filter_params
            ).value or []
        )

        metrics: list[ActivityRunMetric] = []
        for run in pipeline_runs:
            run_id: str = run.run_id or ""
            pipeline_name: str = run.pipeline_name or ""
            if not run_id:
                continue
            try:
                activities = self._collect_run_activities(
                    client, resource_group, factory_name, run_id, pipeline_name, since, until
                )
                metrics.extend(activities)
            except Exception as exc:  # noqa: BLE001
                _logger.warning(
                    "activity_run_skip factory=%s run_id=%s reason=%s",
                    factory_name, run_id, exc,
                )

        return metrics

    def _collect_run_activities(
        self,
        client: DataFactoryManagementClient,
        resource_group: str,
        factory_name: str,
        run_id: str,
        pipeline_name: str,
        since: datetime,
        until: datetime,
    ) -> list[ActivityRunMetric]:
        """Collect and map activity runs for a single pipeline run."""
        filter_params = RunFilterParameters(
            last_updated_after=since,
            last_updated_before=until,
        )
        result = client.activity_runs.query_by_pipeline_run(
            resource_group, factory_name, run_id, filter_params
        )
        activities = list(result.value or [])

        metrics: list[ActivityRunMetric] = []
        count = 0
        for activity in activities:
            if count >= self._max_activities_per_run:
                _logger.warning(
                    "activity_run_cap_reached factory=%s run_id=%s cap=%d",
                    factory_name, run_id, self._max_activities_per_run,
                )
                break

            status = _map_adf_activity_status(
                getattr(activity, "status", None)
            )

            if self._failed_only and status != ActivityRunStatus.FAILED:
                continue

            # Data movement input/output (only Copy activities have this)
            output: dict[str, Any] = getattr(activity, "output", None) or {}
            rows_read: int | None = output.get("rowsRead")
            rows_written: int | None = output.get("rowsCopied")
            data_read_bytes: int | None = output.get("dataRead")
            data_written_bytes: int | None = output.get("dataWritten")

            error: dict[str, Any] = getattr(activity, "error", None) or {}
            error_message: str | None = error.get("message") if error else None

            metrics.append(
                ActivityRunMetric(
                    pipeline_run_id=run_id,
                    pipeline_name=pipeline_name,
                    activity_name=getattr(activity, "activity_name", "") or "",
                    activity_type=_map_adf_activity_type(
                        getattr(activity, "activity_type", None)
                    ),
                    status=status,
                    start_time=getattr(activity, "activity_run_start", None),
                    end_time=getattr(activity, "activity_run_end", None),
                    duration_seconds=None,  # auto-computed by model validator
                    rows_read=rows_read,
                    rows_written=rows_written,
                    data_read_bytes=data_read_bytes,
                    data_written_bytes=data_written_bytes,
                    error_message=error_message,
                    tags={"factory": factory_name, "resource_group": resource_group},
                )
            )
            count += 1

        return metrics
