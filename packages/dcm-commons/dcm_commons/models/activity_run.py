"""Activity-level run metrics — ADF activity runs and Glue job steps.

An ``ActivityRunMetric`` represents one activity execution within a pipeline run.
In ADF, a pipeline is composed of activities (Copy, Notebook, Lookup…) that each
produce their own run record.  In AWS Glue, a job may have multiple steps.

Relationship to pipelines
--------------------------
``pipeline_run_id`` is a **logical foreign key** to ``PipelineMetric.run_id``.
There is no physical FK constraint in Lakebase, but the backend uses
``pipeline_run_id`` to join activity details when drillling into a pipeline run.

Data lineage fields
-------------------
``rows_read``, ``rows_written``, ``data_read_bytes``, ``data_written_bytes`` are
populated only for Copy-type activities that move data.  Notebook or Lookup
activities leave these as ``None``.

Example::

    from dcm_commons.models.activity_run import ActivityRunMetric
    from dcm_commons.models.enums import ActivityRunStatus, ActivityType
    from datetime import datetime, timezone

    metric = ActivityRunMetric(
        pipeline_run_id="run-abc123",
        pipeline_name="adf-ingestion-pipeline",
        activity_name="CopyBlobToLake",
        activity_type=ActivityType.COPY,
        status=ActivityRunStatus.SUCCEEDED,
        start_time=datetime(2026, 3, 26, 10, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 3, 26, 10, 5, tzinfo=timezone.utc),
        rows_read=1_500_000,
        rows_written=1_500_000,
        data_read_bytes=524_288_000,
        data_written_bytes=524_288_000,
    )
    assert metric.duration_seconds == 300.0
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field, model_validator

from dcm_commons.models.base_metric import BaseMetricModel
from dcm_commons.models.enums import ActivityRunStatus, ActivityType

__all__ = ["ActivityRunMetric"]


class ActivityRunMetric(BaseMetricModel):
    """Execution metrics for a single activity within a pipeline run.

    Attributes:
        pipeline_run_id:    Logical link to ``PipelineMetric.run_id``.
        pipeline_name:      Name of the parent pipeline.
        activity_name:      Name of this specific activity within the pipeline.
        activity_type:      Classified activity type (Copy, Notebook, …).
        status:             Execution outcome of this activity.
        start_time:         UTC timestamp when the activity started.
        end_time:           UTC timestamp when the activity completed.
        duration_seconds:   Execution duration in seconds.  Auto-computed from
                            ``start_time`` / ``end_time`` when not provided.
        rows_read:          Number of rows read (Copy activities only).
        rows_written:       Number of rows written (Copy activities only).
        data_read_bytes:    Bytes read from the source (Copy activities only).
        data_written_bytes: Bytes written to the sink (Copy activities only).
        error_message:      Error detail when ``status`` is ``failed``.
        tags:               Arbitrary key/value metadata from the source system.
    """

    pipeline_run_id: str = Field(
        ...,
        description="Logical link to PipelineMetric.run_id in pipeline_metrics table.",
    )
    pipeline_name: str
    activity_name: str
    activity_type: ActivityType = ActivityType.UNKNOWN
    status: ActivityRunStatus
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_seconds: float | None = None
    rows_read: int | None = Field(default=None, ge=0)
    rows_written: int | None = Field(default=None, ge=0)
    data_read_bytes: int | None = Field(default=None, ge=0)
    data_written_bytes: int | None = Field(default=None, ge=0)
    error_message: str | None = None
    tags: dict[str, Any] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def _ensure_utc_and_compute_duration(self) -> "ActivityRunMetric":
        """Coerce naive datetimes to UTC and compute duration if not provided."""
        if self.start_time is not None and self.start_time.tzinfo is None:
            object.__setattr__(self, "start_time", self.start_time.replace(tzinfo=timezone.utc))
        if self.end_time is not None and self.end_time.tzinfo is None:
            object.__setattr__(self, "end_time", self.end_time.replace(tzinfo=timezone.utc))
        if self.duration_seconds is None and self.start_time and self.end_time:
            delta = (self.end_time - self.start_time).total_seconds()
            object.__setattr__(self, "duration_seconds", max(0.0, delta))
        return self

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"ActivityRunMetric("
            f"pipeline={self.pipeline_name!r}, "
            f"activity={self.activity_name!r}, "
            f"type={self.activity_type}, "
            f"status={self.status})"
        )
