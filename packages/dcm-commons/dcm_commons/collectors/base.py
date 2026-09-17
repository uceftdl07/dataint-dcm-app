"""Abstract base class for all DCM metric collectors.

Every concrete collector (``DataFactoryCollector``, ``GlueCollector``, etc.)
inherits from ``BaseCollector`` and implements a single method:
``_collect_metrics()``.

The base class provides:

- Structured logging with per-run correlation IDs (``collection_run_id``).
- Configurable retry with exponential back-off for transient failures.
- Consistent ``MetricPayload`` construction from raw metric dicts.
- ``CollectionResult`` — a richer return type that bundles the payload with
  timing information so the agent can log performance without wrapping
  ``collect()`` in its own timer.

Retry policy
------------
``collect()`` retries ``_collect_metrics()`` up to ``max_retries`` times when
it raises ``CollectionError``.  Back-off delay after attempt *n* is::

    delay = retry_base_delay_seconds * 2 ** (n - 1)   # 2 s, 4 s, 8 s, …

Non-``CollectionError`` exceptions propagate immediately without retrying.
Callers that need to retry on broader exception sets should override
``collect()`` or configure the concrete collector with a custom policy.

Example::

    class DataFactoryCollector(BaseCollector):
        @property
        def domain(self) -> MetricDomain:
            return MetricDomain.PIPELINE

        async def _collect_metrics(self) -> list[dict[str, Any]]:
            runs = await self._adf_client.list_pipeline_runs(...)
            return [PipelineMetric(...).model_dump() for run in runs]

    collector = DataFactoryCollector(
        source_lz_id="azure-sub-fa5abbc4",
        cloud_provider=CloudProvider.AZURE,
    )
    result = await collector.collect()
    await apigee_client.send(result.payload)
"""

from __future__ import annotations

import asyncio
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from dcm_commons.exceptions import CollectionError
from dcm_commons.logging_utils import bind_contextvars, clear_contextvars, get_logger
from dcm_commons.models.enums import CloudProvider, MetricDomain
from dcm_commons.models.payload import MetricPayload

__all__ = ["BaseCollector", "CollectionResult"]

_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_BASE_DELAY = 2.0  # seconds; actual delay = base * 2^(attempt-1)


@dataclass(frozen=True, slots=True)
class CollectionResult:
    """Result of a single collector run.

    Attributes:
        payload:        The ``MetricPayload`` ready to send to Apigee.
        duration_ms:    Wall-clock time of the collection in milliseconds.
        collector_name: ``__class__.__name__`` of the collector that produced
                        this result, for structured logging at the agent level.
    """

    payload: MetricPayload
    duration_ms: float
    collector_name: str


class BaseCollector(ABC):
    """Abstract base for all DCM metric collectors.

    Subclasses must implement:

    - :attr:`domain` — the :class:`MetricDomain` this collector produces.
    - :meth:`_collect_metrics` — async method that calls the cloud provider
      API and returns a list of metric dicts (each should be the
      ``model_dump()`` of a domain model such as ``PipelineMetric``).

    Args:
        source_lz_id:           Landing zone identifier.
                                Conventions: ``"azure-sub-{sub_id_prefix}"``
                                or ``"aws-account-{account_id}"``.
        cloud_provider:         The cloud platform monitored by this collector.
        subscription_or_account_id:
                                Azure subscription ID or AWS account ID embedded
                                on the ``MetricPayload`` envelope for multi-account
                                isolation.  Optional but recommended.
        max_retries:            Maximum number of ``_collect_metrics()`` attempts
                                before raising ``CollectionError``.  Defaults to 3.
        retry_base_delay_seconds: Base delay (seconds) for exponential back-off.
                                  Delay after attempt *n* =
                                  ``retry_base_delay_seconds * 2^(n-1)``.
                                  Defaults to 2.0.
    """

    def __init__(
        self,
        source_lz_id: str,
        cloud_provider: CloudProvider,
        *,
        subscription_or_account_id: str | None = None,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        retry_base_delay_seconds: float = _DEFAULT_RETRY_BASE_DELAY,
    ) -> None:
        if not source_lz_id or not str(source_lz_id).strip():
            raise ValueError("source_lz_id is required for MetricPayload")
        self._source_lz_id = str(source_lz_id).strip()
        self._cloud_provider = cloud_provider
        self._subscription_or_account_id = (
            str(subscription_or_account_id).strip() if subscription_or_account_id else None
        )
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay_seconds
        self._logger = get_logger(self.__class__.__module__)

    # ------------------------------------------------------------------
    # Abstract interface — subclasses must implement
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def domain(self) -> MetricDomain:
        """The :class:`MetricDomain` this collector produces."""
        ...

    @abstractmethod
    async def _collect_metrics(self) -> list[dict[str, Any]]:
        """Collect raw metrics from the cloud provider.

        Returns:
            List of metric dicts, each the ``model_dump()`` output of the
            corresponding domain model (e.g. ``PipelineMetric.model_dump()``).

        Raises:
            CollectionError: If the cloud provider API is unavailable or
                             returns unexpected data.  Transient errors
                             should raise ``CollectionError`` to trigger
                             the base class retry policy.
        """
        ...

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def collect(self) -> CollectionResult:
        """Run the collection cycle with retry and return a :class:`CollectionResult`.

        Retries ``_collect_metrics()`` up to ``max_retries`` times when it
        raises :class:`CollectionError`.  Other exceptions propagate immediately.

        Returns:
            A :class:`CollectionResult` containing the ``MetricPayload`` and
            timing information.

        Raises:
            CollectionError: If all retry attempts are exhausted.
        """
        run_id = str(uuid.uuid4())
        collector_name = self.__class__.__name__

        bind_contextvars(
            collection_run_id=run_id,
            collector=collector_name,
            cloud_provider=self._cloud_provider,
            domain=self.domain,
        )
        self._logger.info(
            "collection_started",
            collector_class=collector_name,
            source_lz_id=self._source_lz_id,
            domain=str(self.domain),
            max_retries=self._max_retries,
        )

        start_mono = time.monotonic()
        last_exc: CollectionError | None = None

        try:
            for attempt in range(1, self._max_retries + 1):
                try:
                    metrics = await self._collect_metrics()
                    duration_ms = (time.monotonic() - start_mono) * 1_000

                    self._logger.info(
                        "collection_completed",
                        collector_class=collector_name,
                        domain=str(self.domain),
                        metric_count=len(metrics),
                        duration_ms=round(duration_ms, 1),
                        attempt=attempt,
                    )

                    payload = MetricPayload(
                        collection_run_id=run_id,
                        source_lz_id=self._source_lz_id,
                        subscription_or_account_id=self._subscription_or_account_id,
                        cloud_provider=self._cloud_provider,
                        domain=self.domain,
                        collected_at=datetime.now(timezone.utc),
                        metrics=metrics,
                        metadata={"collector": collector_name},
                    )
                    # Fail fast if envelope would be rejected by Lambda.
                    MetricPayload.model_validate_json(payload.to_ingest_json())
                    return CollectionResult(
                        payload=payload,
                        duration_ms=duration_ms,
                        collector_name=collector_name,
                    )

                except CollectionError as exc:
                    last_exc = exc
                    if attempt == self._max_retries:
                        break

                    delay = self._retry_base_delay * (2.0 ** (attempt - 1))
                    self._logger.warning(
                        "collection_attempt_failed",
                        attempt=attempt,
                        max_retries=self._max_retries,
                        retry_in_seconds=round(delay, 1),
                        reason=str(exc),
                    )
                    await asyncio.sleep(delay)

            # All retries exhausted
            duration_ms = (time.monotonic() - start_mono) * 1_000
            self._logger.error(
                "collection_failed",
                attempts=self._max_retries,
                duration_ms=round(duration_ms, 1),
                reason=str(last_exc),
            )
            raise last_exc  # type: ignore[misc]  # last_exc is set when loop exits here

        finally:
            clear_contextvars()
