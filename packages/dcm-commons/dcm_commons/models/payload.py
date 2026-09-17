"""Core metric payload — transport contract between collectors and the ingestion API.

``MetricPayload`` is the single envelope that every DCM collector agent serialises
and every downstream component deserialises.  It is version-stamped with
``schema_version`` so consumers can safely handle format evolution.

Design decisions
----------------
metrics : list[dict[str, Any]]
    The ingestion layer (Lambda → Databricks pipeline) validates each item against
    the domain model for its ``domain``.  Keeping the envelope domain-agnostic means
    Lambda does not need to import domain models — it only validates the envelope
    before pushing to SQS.

collection_run_id
    Auto-generated as UUIDv4 per collection cycle.  Callers only override it in
    tests or when replaying a failed run.  Appears in every structured log record,
    enabling end-to-end tracing from agent → Lambda → Databricks pipeline.

Example::

    from dcm_commons.models.enums import CloudProvider, MetricDomain
    from dcm_commons.models.payload import MetricPayload

    payload = MetricPayload(
        source_lz_id="azure-sub-fa5abbc4",
        cloud_provider=CloudProvider.AZURE,
        domain=MetricDomain.PIPELINE,
        metrics=[pipeline_metric.model_dump()],
        metadata={"region": "westeurope", "collector_version": "1.0.0"},
    )
    assert not payload.is_empty
    assert payload.metric_count == 1
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import Field, computed_field, field_validator

from dcm_commons.models.base_metric import BaseMetricModel
from dcm_commons.models.enums import CloudProvider, MetricDomain

__all__ = ["MetricPayload"]

_CURRENT_SCHEMA_VERSION = "1.2"  # 1.2: added 'workflow' domain (Databricks Workflows observability, epic 009)


class MetricPayload(BaseMetricModel):
    """Envelope emitted by every DCM collector agent.

    Attributes:
        schema_version:     Payload schema version.  Consumers must check this
                            before deserialising ``metrics`` if they need to
                            handle multiple schema generations.
        collection_run_id:  UUIDv4 auto-assigned per collection cycle.
                            Appears in all structured log records for the run,
                            enabling end-to-end tracing from agent to Lakebase.
        source_lz_id:       Landing zone identifier.
                            Conventions:
                            ``"azure-lz-prod-fr"`` or ``"aws-lz-data-eu"``.
        subscription_or_account_id:
                            Azure Subscription ID or AWS Account ID.
                            Propagated to every SERVING table for multi-account
                            KPI isolation and per-subscription filtering.
                            Required when the agent may manage multiple
                            subscriptions or accounts.
        cloud_provider:     The cloud platform that produced these metrics.
        domain:             Metric category.  Determines which Lakebase table
                            family receives the data and which collector produced
                            the payload.
        collected_at:       UTC timestamp when the agent executed the collection.
                            Always stored with timezone information.
        metrics:            List of domain-specific metric dicts.  Each item
                            should be the ``model_dump()`` output of the
                            corresponding domain model (e.g. ``PipelineMetric``).
        metadata:           Arbitrary string key/value pairs for contextual
                            enrichment (region, environment, collector_version).
    """

    schema_version: str = Field(
        default=_CURRENT_SCHEMA_VERSION,
        description="Payload schema version for forward compatibility.",
    )
    collection_run_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="UUIDv4 correlating all log records for a single collection run.",
    )
    source_lz_id: str = Field(
        ...,
        description=(
            "Landing zone identifier. "
            "Conventions: 'azure-lz-prod-fr' or 'aws-lz-data-eu'."
        ),
    )
    subscription_or_account_id: str | None = Field(
        default=None,
        description=(
            "Azure Subscription ID or AWS Account ID. "
            "Propagated to all SERVING tables for multi-account KPI isolation. "
            "Required when the agent manages multiple subscriptions/accounts."
        ),
    )
    cloud_provider: CloudProvider
    domain: MetricDomain
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp at which the collection was executed.",
    )
    metrics: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Domain-specific metric objects, each serialised via model_dump().",
    )
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Contextual key/value pairs (region, environment, collector_version, …).",
    )

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("collected_at", mode="before")
    @classmethod
    def _ensure_utc(cls, v: datetime) -> datetime:
        """Coerce naive datetimes to UTC; pass through tz-aware datetimes unchanged."""
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------

    @computed_field  # type: ignore[prop-decorator]
    @property
    def metric_count(self) -> int:
        """Number of metric records carried by this payload."""
        return len(self.metrics)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_empty(self) -> bool:
        """``True`` when the payload carries zero metric records."""
        return len(self.metrics) == 0

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def to_ingest_json(self) -> str:
        """Serialize for Apigee → Lambda ingestion.

        Excludes computed fields (``metric_count``, ``is_empty``) so the wire
        body matches the ingest contract and round-trips through
        ``MetricPayload.model_validate_json``.
        """
        return self.model_dump_json(exclude={"metric_count", "is_empty"})

    def __repr__(self) -> str:
        return (
            f"MetricPayload("
            f"run={self.collection_run_id[:8]}…, "
            f"provider={self.cloud_provider}, "
            f"domain={self.domain}, "
            f"count={self.metric_count})"
        )
