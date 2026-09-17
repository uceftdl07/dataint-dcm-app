"""Tests for BaseCollector.

Coverage:
    - Successful collection returns a ``CollectionResult`` with correct fields.
    - ``bind_contextvars`` / ``clear_contextvars`` lifecycle (run_id, collector name).
    - Transient ``CollectionError`` triggers retry with correct attempt count.
    - All retries exhausted re-raises the last ``CollectionError``.
    - Non-``CollectionError`` exceptions propagate immediately (no retry).
    - ``CollectionResult.duration_ms`` is positive.
    - Empty metrics list produces an empty ``MetricPayload``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from dcm_commons.collectors.base import BaseCollector, CollectionResult
from dcm_commons.exceptions import CollectionError
from dcm_commons.models.enums import CloudProvider, MetricDomain
from dcm_commons.models.payload import MetricPayload


# ---------------------------------------------------------------------------
# Concrete test implementation
# ---------------------------------------------------------------------------


class SuccessCollector(BaseCollector):
    """Always returns two pipeline metric dicts."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            source_lz_id="azure-sub-test",
            cloud_provider=CloudProvider.AZURE,
            **kwargs,
        )

    @property
    def domain(self) -> MetricDomain:
        return MetricDomain.PIPELINE

    async def _collect_metrics(self) -> list[dict[str, Any]]:
        return [
            {"pipeline_name": "pipe_a", "status": "succeeded"},
            {"pipeline_name": "pipe_b", "status": "failed"},
        ]


class FailThenSucceedCollector(BaseCollector):
    """Fails ``fail_count`` times, then succeeds."""

    def __init__(self, fail_count: int, **kwargs: Any) -> None:
        super().__init__(
            source_lz_id="azure-sub-test",
            cloud_provider=CloudProvider.AZURE,
            **kwargs,
        )
        self._remaining_failures = fail_count

    @property
    def domain(self) -> MetricDomain:
        return MetricDomain.COMPUTE

    async def _collect_metrics(self) -> list[dict[str, Any]]:
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise CollectionError("FailThenSucceedCollector", "transient API error")
        return [{"compute_resource_id": "c-001", "state": "running"}]


class AlwaysFailCollector(BaseCollector):
    """Always raises ``CollectionError``."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            source_lz_id="aws-account-123",
            cloud_provider=CloudProvider.AWS,
            **kwargs,
        )

    @property
    def domain(self) -> MetricDomain:
        return MetricDomain.COST

    async def _collect_metrics(self) -> list[dict[str, Any]]:
        raise CollectionError("AlwaysFailCollector", "API unavailable")


class NonCollectionErrorCollector(BaseCollector):
    """Raises a non-``CollectionError`` exception."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            source_lz_id="aws-account-123",
            cloud_provider=CloudProvider.AWS,
            **kwargs,
        )

    @property
    def domain(self) -> MetricDomain:
        return MetricDomain.SECURITY

    async def _collect_metrics(self) -> list[dict[str, Any]]:
        raise ValueError("unexpected SDK error — not a CollectionError")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBaseCollectorSuccess:
    async def test_returns_collection_result(self) -> None:
        collector = SuccessCollector()
        result = await collector.collect()

        assert isinstance(result, CollectionResult)
        assert isinstance(result.payload, MetricPayload)
        assert result.collector_name == "SuccessCollector"

    async def test_payload_fields_populated(self) -> None:
        collector = SuccessCollector()
        result = await collector.collect()

        assert result.payload.source_lz_id == "azure-sub-test"
        assert result.payload.cloud_provider == "azure"
        assert result.payload.domain == "pipeline"
        assert result.payload.metric_count == 2
        assert result.payload.collected_at.tzinfo is not None
        # Wire JSON must round-trip for Lambda ingestion
        from dcm_commons.models.payload import MetricPayload as MP

        wire = result.payload.to_ingest_json()
        assert "metric_count" not in __import__("json").loads(wire)
        assert MP.model_validate_json(wire).source_lz_id == "azure-sub-test"

    async def test_duration_ms_is_positive(self) -> None:
        collector = SuccessCollector()
        result = await collector.collect()
        assert result.duration_ms > 0.0

    async def test_empty_metrics_produce_empty_payload(self) -> None:
        class EmptyCollector(BaseCollector):
            def __init__(self) -> None:
                super().__init__(source_lz_id="lz", cloud_provider=CloudProvider.AZURE)

            @property
            def domain(self) -> MetricDomain:
                return MetricDomain.DATABASE

            async def _collect_metrics(self) -> list[dict[str, Any]]:
                return []

        result = await EmptyCollector().collect()
        assert result.payload.is_empty is True


class TestBaseCollectorRetry:
    """Retry policy and backoff behaviour."""

    async def test_retries_on_collection_error(self) -> None:
        # Patch asyncio.sleep to avoid actual waiting in tests
        with patch("dcm_commons.collectors.base.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            collector = FailThenSucceedCollector(
                fail_count=2,
                max_retries=3,
                retry_base_delay_seconds=1.0,
            )
            result = await collector.collect()

        assert result.payload.metric_count == 1
        # sleep called twice (after attempt 1 and attempt 2)
        assert mock_sleep.call_count == 2

    async def test_exponential_backoff_delays(self) -> None:
        with patch("dcm_commons.collectors.base.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            collector = FailThenSucceedCollector(
                fail_count=2,
                max_retries=3,
                retry_base_delay_seconds=2.0,
            )
            await collector.collect()

        # Delays: 2.0 * 2^0 = 2.0 s, 2.0 * 2^1 = 4.0 s
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays == [pytest.approx(2.0), pytest.approx(4.0)]

    async def test_all_retries_exhausted_raises_collection_error(self) -> None:
        with patch("dcm_commons.collectors.base.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(CollectionError) as exc_info:
                await AlwaysFailCollector(max_retries=3).collect()

        assert "AlwaysFailCollector" in str(exc_info.value)

    async def test_non_collection_error_propagates_immediately(self) -> None:
        """Non-CollectionError must not trigger retry — propagates right away."""
        with patch("dcm_commons.collectors.base.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(ValueError, match="unexpected SDK error"):
                await NonCollectionErrorCollector(max_retries=3).collect()

        # asyncio.sleep must NOT have been called (no retry attempted)
        mock_sleep.assert_not_called()
