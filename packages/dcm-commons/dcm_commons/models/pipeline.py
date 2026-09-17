"""Pipeline execution metrics — ADF, Databricks, Glue, and EMR.

Produced by:
    - ``dcm_azure_collector.collectors.datafactory.DataFactoryCollector``
    - ``dcm_azure_collector.collectors.databricks_pipelines.DatabricksPipelineCollector``
    - ``dcm_aws_collector.collectors.glue.GlueCollector``
    - ``dcm_aws_collector.collectors.emr.EmrCollector``

Stored in Lakebase under: ``dcm.monitoring.pipeline_runs`` / ``dcm.monitoring.pipeline_metrics``

Each ``PipelineMetric`` instance represents a single pipeline execution snapshot.
Collectors serialise them via ``model_dump()`` and pack the list into a
``MetricPayload.metrics`` before sending to Apigee.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, model_validator

from dcm_commons.models.base_metric import BaseMetricModel
from dcm_commons.models.enums import PipelineRunStatus, TriggerType

__all__ = ["PipelineMetric"]


class PipelineMetric(BaseMetricModel):
    """Metrics for a single pipeline execution run.

    Attributes:
        pipeline_id:            Cloud-native pipeline resource identifier.
                                ADF: ``/subscriptions/{sub}/…/pipelines/{name}``.
                                Glue: job name.  EMR: step ID.
                                Databricks: ``databricks:job:{job_id}``.
        pipeline_name:          Human-readable pipeline or job name.
        run_id:                 Unique identifier for this specific execution run
                                (ADF ``runId``, Glue ``JobRunId``, EMR ``StepId``, Databricks ``run_id``).
        status:                 Execution outcome at collection time.
        trigger_type:           How the execution was initiated.
                                Defaults to ``UNKNOWN`` when the source API does not
                                expose trigger information.
        start_time:             UTC timestamp when the run began.
        end_time:               UTC timestamp when the run completed.
                                ``None`` if the run is still active at collection time.
        duration_seconds:       Elapsed wall-clock time in seconds.
                                Auto-derived from ``start_time`` / ``end_time`` when
                                not supplied by the source API.
        error_message:          Provider error message when ``status`` is a failure.
                                Truncated to 2 000 characters by collectors to avoid
                                oversized payloads.
        factory_name:           Azure Data Factory resource name (ADF only).
        resource_group:         Azure resource group name (ADF only).
        glue_job_name:          AWS Glue job name (Glue only).
        databricks_workspace_id: Databricks workspace identifier (Databricks Workflows only).
        databricks_workspace_name: Azure ARM resource name of the Databricks workspace
                                (Databricks Workflows only).
        tags:                   Provider-supplied resource tags as key/value strings.
    """

    pipeline_id: str = Field(..., description="Cloud-native pipeline resource identifier.")
    pipeline_name: str = Field(..., description="Human-readable pipeline or job name.")
    run_id: str = Field(..., description="Unique identifier for this execution run.")
    status: PipelineRunStatus
    trigger_type: TriggerType = Field(
        default=TriggerType.UNKNOWN,
        description="How the execution was initiated.",
    )
    start_time: datetime = Field(..., description="UTC timestamp when the run began.")
    end_time: datetime | None = Field(
        default=None,
        description="UTC timestamp when the run completed; None if still running.",
    )
    duration_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description=(
            "Elapsed wall-clock time in seconds. "
            "Auto-derived from start_time / end_time when not supplied by the API."
        ),
    )
    error_message: str | None = Field(
        default=None,
        description="Provider error message on failure (max 2 000 characters).",
    )
    # Azure-specific fields
    factory_name: str | None = Field(
        default=None,
        description="Azure Data Factory resource name (ADF only).",
    )
    resource_group: str | None = Field(
        default=None,
        description="Azure resource group name (ADF only).",
    )
    # AWS-specific fields
    glue_job_name: str | None = Field(
        default=None,
        description="AWS Glue job name (Glue only).",
    )
    # Databricks-specific fields
    databricks_workspace_id: str | None = Field(
        default=None,
        description="Databricks workspace identifier (Databricks Workflows only).",
    )
    databricks_workspace_name: str | None = Field(
        default=None,
        description="Azure ARM resource name of the Databricks workspace (Databricks Workflows only).",
    )
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Provider-supplied resource tags.",
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @model_validator(mode="before")
    @classmethod
    def _derive_duration(cls, data: Any) -> Any:
        """Auto-compute ``duration_seconds`` from ``start_time`` / ``end_time``.

        Only applies when ``duration_seconds`` is absent from the raw data and
        both timestamps are already parsed ``datetime`` objects (i.e. the model
        is constructed from Python objects, not from a raw JSON string).
        """
        if not isinstance(data, dict):
            return data
        if data.get("duration_seconds") is not None:
            return data

        start = data.get("start_time")
        end = data.get("end_time")
        if isinstance(start, datetime) and isinstance(end, datetime) and end >= start:
            data = {**data, "duration_seconds": (end - start).total_seconds()}
        return data
