"""Azure Data Factory collector — pipeline run metrics.

Collects the execution history of all pipelines across every Data Factory
instance in the monitored Azure subscription.

Azure SDK used
--------------
``azure-mgmt-datafactory`` (synchronous) — wrapped in :func:`run_sync` to
keep the async event loop unblocked.

Key API calls
-------------
``client.factories.list(subscription_id)``
    Enumerate all ADF instances in the subscription.
``client.pipeline_runs.query_by_factory(resource_group, factory, body)``
    Retrieve pipeline runs updated within the lookback window.

Ported from
-----------
``AzureDataFactoryService.cs`` (POC C# backend)
``DataFactoryApiClient.cs``

Lakebase target
---------------
``dcm.monitoring.pipeline_runs``
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from azure.identity import DefaultAzureCredential  # type: ignore[import-untyped]
from azure.mgmt.datafactory import DataFactoryManagementClient  # type: ignore[import-untyped]
from azure.mgmt.datafactory.models import (  # type: ignore[import-untyped]
    RunFilterParameters,
    RunQueryFilter,
)

from dcm_commons.collectors.base import BaseCollector
from dcm_commons.exceptions import CollectionError
from dcm_commons.logging_utils import get_logger
from dcm_commons.models.enums import CloudProvider, MetricDomain
from dcm_commons.models.pipeline import PipelineMetric

from azure_collector._azure_utils import map_adf_status, map_adf_trigger, run_sync

__all__ = ["DataFactoryCollector"]

_logger = get_logger(__name__)

# ADF Management API version (pinned for stability)
_ADF_API_VERSION = "2018-06-01"


class DataFactoryCollector(BaseCollector):
    """Collects pipeline run metrics from all Data Factories in the subscription.

    For each ADF instance discovered in the subscription, queries the pipeline
    runs updated within the ``lookback_hours`` window and maps each run to a
    :class:`~dcm_commons.models.pipeline.PipelineMetric`.

    Args:
        source_lz_id:     Landing zone identifier.
        subscription_id:  Azure subscription ID.
        credential:       ``azure.identity`` credential.  If ``None``,
                          ``DefaultAzureCredential`` is used.
        lookback_hours:   How many hours back to query pipeline run history.
                          Defaults to 1 hour (aligned with the collection cycle).
        max_retries:      Retry attempts on transient failures.
        retry_base_delay_seconds: Base delay for exponential back-off.
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
        super().__init__(
            source_lz_id=source_lz_id,
            cloud_provider=CloudProvider.AZURE,
            subscription_or_account_id=subscription_id,
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

    async def _collect_metrics(self) -> list[dict[str, Any]]:
        """Collect pipeline runs from all ADF instances in the subscription.

        Returns:
            List of :class:`~dcm_commons.models.pipeline.PipelineMetric`
            dicts serialised via ``model_dump()``.

        Raises:
            CollectionError: On ADF API errors or pagination failures.
        """
        now = datetime.now(timezone.utc)
        lookback_start = now - timedelta(hours=self._lookback_hours)

        _logger.info(
            "datafactory_list_starting",
            subscription_id=self._subscription_id,
            lookback_hours=self._lookback_hours,
        )
        try:
            factories = await run_sync(
                lambda: list(self._adf_client.factories.list()),
            )
        except Exception as exc:
            _logger.error("datafactory_list_failed", exc_info=exc)
            raise CollectionError(
                "DataFactoryCollector",
                f"Failed to list Data Factory instances: {exc}",
            ) from exc

        _logger.info("datafactory_list_done", factory_count=len(factories))

        metrics: list[dict[str, Any]] = []
        for factory in factories:
            # Extract resource group from the ARM resource ID.
            # Format: /subscriptions/{sub}/resourceGroups/{rg}/providers/...
            resource_group = _extract_resource_group(factory.id or "")
            factory_name = factory.name or ""

            if not resource_group or not factory_name:
                _logger.warning(
                    "datafactory_skip_invalid",
                    factory_id=factory.id,
                )
                continue

            _logger.info(
                "datafactory_factory_query_starting",
                factory=factory_name,
                resource_group=resource_group,
            )
            factory_metric_count = 0
            try:
                pipeline_names = await _list_pipeline_names(
                    self._adf_client,
                    resource_group=resource_group,
                    factory_name=factory_name,
                )
            except Exception as exc:
                _logger.warning(
                    "datafactory_pipeline_list_failed",
                    factory=factory_name,
                    resource_group=resource_group,
                    reason=str(exc),
                )
                pipeline_names = []

            _logger.info(
                "datafactory_factory_pipelines_listed",
                factory=factory_name,
                pipeline_count=len(pipeline_names),
            )

            seen_run_ids: set[str] = set()
            for pipeline_name in pipeline_names:
                try:
                    runs = await _query_pipeline_runs(
                        self._adf_client,
                        resource_group=resource_group,
                        factory_name=factory_name,
                        last_updated_after=lookback_start,
                        last_updated_before=now,
                        pipeline_name=pipeline_name,
                    )
                except Exception as exc:
                    _logger.warning(
                        "datafactory_pipeline_query_failed",
                        factory=factory_name,
                        pipeline=pipeline_name,
                        resource_group=resource_group,
                        reason=str(exc),
                    )
                    continue

                for run in runs:
                    run_id = getattr(run, "run_id", None) or ""
                    if run_id and run_id in seen_run_ids:
                        continue
                    if run_id:
                        seen_run_ids.add(run_id)

                    metric = _map_run_to_metric(
                        run,
                        factory_name=factory_name,
                        resource_group=resource_group,
                    )
                    if metric is not None:
                        metrics.append(metric.model_dump())
                        factory_metric_count += 1

            _logger.info(
                "datafactory_factory_query_done",
                factory=factory_name,
                metric_count=factory_metric_count,
            )

        _logger.info(
            "datafactory_collection_done",
            factory_count=len(factories),
            metric_count=len(metrics),
            lookback_hours=self._lookback_hours,
        )
        return metrics


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _list_pipeline_names(
    client: DataFactoryManagementClient,
    resource_group: str,
    factory_name: str,
) -> list[str]:
    """List all pipeline definitions in a Data Factory."""
    pipelines = await run_sync(
        client.pipelines.list_by_factory,
        resource_group,
        factory_name,
    )
    names = [pipeline.name for pipeline in pipelines if getattr(pipeline, "name", None)]
    _logger.info(
        "datafactory_pipelines_listed",
        factory=factory_name,
        pipeline_count=len(names),
    )
    return names


async def _query_pipeline_runs(
    client: DataFactoryManagementClient,
    resource_group: str,
    factory_name: str,
    last_updated_after: datetime,
    last_updated_before: datetime,
    *,
    pipeline_name: str | None = None,
) -> list[Any]:
    """Query all pipeline runs for a single ADF instance with pagination.

    The ADF API returns up to 100 runs per page.  This function follows
    ``continuation_token`` until all runs in the window are retrieved.

    Args:
        client:              Authenticated ADF management client.
        resource_group:      Resource group containing the factory.
        factory_name:        Data Factory resource name.
        last_updated_after:  Lower bound of the query window (UTC).
        last_updated_before: Upper bound of the query window (UTC).

    Returns:
        Flat list of all pipeline run objects from the ADF API.
    """
    runs: list[Any] = []
    continuation_token: str | None = None

    while True:
        filters = None
        if pipeline_name:
            filters = [
                RunQueryFilter(
                    operand="PipelineName",
                    operator="Equals",
                    values=[pipeline_name],
                )
            ]

        filter_params = RunFilterParameters(
            last_updated_after=last_updated_after,
            last_updated_before=last_updated_before,
            filters=filters,
            continuation_token=continuation_token,
        )

        response = await run_sync(
            client.pipeline_runs.query_by_factory,
            resource_group,
            factory_name,
            filter_params,
        )

        page_runs: list[Any] = response.value or []
        runs.extend(page_runs)

        continuation_token = response.continuation_token
        if not continuation_token:
            break

    return runs


def _map_run_to_metric(
    run: Any,
    factory_name: str,
    resource_group: str,
) -> PipelineMetric | None:
    """Map an ADF pipeline run object to a :class:`PipelineMetric`.

    Returns ``None`` if the run lacks the minimum required fields
    (``run_id``, ``pipeline_name``, ``run_start``).

    Args:
        run:            ADF ``PipelineRun`` SDK object.
        factory_name:   Parent Data Factory name.
        resource_group: Parent resource group name.

    Returns:
        A :class:`PipelineMetric` instance, or ``None`` on unmappable runs.
    """
    run_id: str = run.run_id or ""
    pipeline_name: str = run.pipeline_name or ""
    start_time: datetime | None = run.run_start

    if not run_id or not pipeline_name or start_time is None:
        return None

    # Ensure the start_time is tz-aware (ADF returns UTC datetimes).
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)

    end_time: datetime | None = run.run_end
    if end_time is not None and end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    # Duration: ADF returns milliseconds; convert to seconds.
    duration_seconds: float | None = None
    if run.duration_in_ms is not None:
        duration_seconds = run.duration_in_ms / 1_000.0

    # Trigger type: sourced from triggered_by.trigger_type.
    triggered_by = getattr(run, "triggered_by", None)
    raw_trigger = getattr(triggered_by, "trigger_type", None) if triggered_by else None

    # Error message: use the 'message' field when the run failed.
    error_message: str | None = run.message if run.message else None

    # Tags: pipeline runs do not carry tags directly; use empty dict.
    return PipelineMetric(
        pipeline_id=(
            f"/subscriptions/{run.run_group_id or ''}/providers/"
            f"Microsoft.DataFactory/factories/{factory_name}/pipelines/{pipeline_name}"
        ),
        pipeline_name=pipeline_name,
        run_id=run_id,
        status=map_adf_status(run.status),
        trigger_type=map_adf_trigger(raw_trigger),
        start_time=start_time,
        end_time=end_time,
        duration_seconds=duration_seconds,
        error_message=error_message,
        factory_name=factory_name,
        resource_group=resource_group,
    )


def _extract_resource_group(resource_id: str) -> str:
    """Extract the resource group name from an ARM resource ID.

    ARM ID format:
    ``/subscriptions/{sub}/resourceGroups/{rg}/providers/...``

    Args:
        resource_id: Full ARM resource ID string.

    Returns:
        Resource group name, or empty string if the ID is malformed.
    """
    parts = resource_id.lower().split("/")
    try:
        idx = parts.index("resourcegroups")
        # Preserve original casing from the raw string
        return resource_id.split("/")[idx + 1]
    except (ValueError, IndexError):
        return ""
