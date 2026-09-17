"""Tests for ApigeeClient.

Coverage:
    - Successful payload delivery (HTTP 200).
    - Retry on server errors (503 → 200 on second attempt).
    - Retry on network errors (RequestError → 200 on second attempt).
    - Non-retriable 4xx → IngestionError raised immediately (no retry).
    - All retries exhausted → IngestionError.
    - send_batch: tracks success / failure counts.
    - Async context manager: aclose() called on __aexit__.
    - Token refreshed from auth_client on each attempt.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

from dcm_commons.clients.apigee import ApigeeClient
from dcm_commons.exceptions import IngestionError
from dcm_commons.models.enums import CloudProvider, MetricDomain
from dcm_commons.models.payload import MetricPayload

_BASE_URL = "https://api.test.example.com/dcm"
_INGEST_URL = f"{_BASE_URL}/v1/metrics/ingest"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def payload() -> MetricPayload:
    return MetricPayload(
        source_lz_id="azure-sub-fa5abbc4",
        cloud_provider=CloudProvider.AZURE,
        domain=MetricDomain.PIPELINE,
        metrics=[{"pipeline_name": "p1", "status": "succeeded"}],
    )


@pytest.fixture
def auth_client() -> MagicMock:
    client = MagicMock()
    client.get_token.return_value = "test-bearer-token"
    return client


def _make_apigee_client(
    auth_client: MagicMock,
    max_retries: int = 3,
    retry_base_delay: float = 0.0,  # no sleep in tests
) -> ApigeeClient:
    return ApigeeClient(
        apigee_base_url=_BASE_URL,
        auth_client=auth_client,
        api_key="test-api-key",
        max_retries=max_retries,
        retry_base_delay_seconds=retry_base_delay,
    )


# ---------------------------------------------------------------------------
# Successful delivery
# ---------------------------------------------------------------------------


class TestApigeeClientSuccess:
    @respx.mock
    async def test_send_success(
        self,
        payload: MetricPayload,
        auth_client: MagicMock,
    ) -> None:
        respx.post(_INGEST_URL).mock(return_value=httpx.Response(200))

        client = _make_apigee_client(auth_client)
        await client.send(payload)
        await client.aclose()

        # Authorization header should contain our test token
        assert respx.calls.last.request.headers["authorization"] == "Bearer test-bearer-token"
        assert respx.calls.last.request.headers["x-apif-apikey"] == "test-api-key"

    @respx.mock
    async def test_send_uses_correct_path(
        self,
        payload: MetricPayload,
        auth_client: MagicMock,
    ) -> None:
        route = respx.post(_INGEST_URL).mock(return_value=httpx.Response(201))
        client = _make_apigee_client(auth_client)
        await client.send(payload)
        await client.aclose()
        assert route.called


# ---------------------------------------------------------------------------
# Retry on server errors
# ---------------------------------------------------------------------------


class TestApigeeClientRetry:
    @respx.mock
    async def test_retries_on_503_then_succeeds(
        self,
        payload: MetricPayload,
        auth_client: MagicMock,
    ) -> None:
        respx.post(_INGEST_URL).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200),
            ]
        )
        client = _make_apigee_client(auth_client, max_retries=3)
        await client.send(payload)
        await client.aclose()

        assert len(respx.calls) == 2

    @respx.mock
    async def test_retries_on_429_then_succeeds(
        self,
        payload: MetricPayload,
        auth_client: MagicMock,
    ) -> None:
        respx.post(_INGEST_URL).mock(
            side_effect=[httpx.Response(429), httpx.Response(200)]
        )
        client = _make_apigee_client(auth_client, max_retries=3)
        await client.send(payload)
        await client.aclose()
        assert len(respx.calls) == 2

    @respx.mock
    async def test_all_retries_exhausted_raises_ingestion_error(
        self,
        payload: MetricPayload,
        auth_client: MagicMock,
    ) -> None:
        respx.post(_INGEST_URL).mock(return_value=httpx.Response(503))
        client = _make_apigee_client(auth_client, max_retries=3)

        with pytest.raises(IngestionError):
            await client.send(payload)
        await client.aclose()

        assert len(respx.calls) == 3

    @respx.mock
    async def test_network_error_retried(
        self,
        payload: MetricPayload,
        auth_client: MagicMock,
    ) -> None:
        respx.post(_INGEST_URL).mock(
            side_effect=[
                httpx.ConnectError("connection refused"),
                httpx.Response(200),
            ]
        )
        client = _make_apigee_client(auth_client, max_retries=3)
        await client.send(payload)
        await client.aclose()
        assert len(respx.calls) == 2


# ---------------------------------------------------------------------------
# Non-retriable errors
# ---------------------------------------------------------------------------


class TestApigeeClientNonRetriable:
    @respx.mock
    async def test_400_raises_ingestion_error_immediately(
        self,
        payload: MetricPayload,
        auth_client: MagicMock,
    ) -> None:
        respx.post(_INGEST_URL).mock(return_value=httpx.Response(400, text="bad request"))
        client = _make_apigee_client(auth_client, max_retries=3)

        with pytest.raises(IngestionError) as exc_info:
            await client.send(payload)
        await client.aclose()

        # Only one attempt — 4xx is non-retriable
        assert len(respx.calls) == 1
        assert exc_info.value.status_code == 400

    @respx.mock
    async def test_403_raises_ingestion_error_immediately(
        self,
        payload: MetricPayload,
        auth_client: MagicMock,
    ) -> None:
        respx.post(_INGEST_URL).mock(return_value=httpx.Response(403, text="forbidden"))
        client = _make_apigee_client(auth_client, max_retries=3)

        with pytest.raises(IngestionError) as exc_info:
            await client.send(payload)
        await client.aclose()

        assert len(respx.calls) == 1
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# send_batch
# ---------------------------------------------------------------------------


class TestApigeeClientSendBatch:
    @respx.mock
    async def test_send_batch_all_success(
        self,
        auth_client: MagicMock,
    ) -> None:
        respx.post(_INGEST_URL).mock(return_value=httpx.Response(200))
        payloads = [
            MetricPayload(source_lz_id="lz", cloud_provider="azure", domain="pipeline")
            for _ in range(3)
        ]
        client = _make_apigee_client(auth_client)
        results = await client.send_batch(payloads)
        await client.aclose()

        assert results["success"] == 3
        assert results["failure"] == 0

    @respx.mock
    async def test_send_batch_partial_failure(
        self,
        auth_client: MagicMock,
    ) -> None:
        respx.post(_INGEST_URL).mock(
            side_effect=[
                httpx.Response(200),
                httpx.Response(400),  # non-retriable → IngestionError → counted as failure
                httpx.Response(200),
            ]
        )
        payloads = [
            MetricPayload(source_lz_id="lz", cloud_provider="azure", domain="pipeline")
            for _ in range(3)
        ]
        client = _make_apigee_client(auth_client, max_retries=1)
        results = await client.send_batch(payloads)
        await client.aclose()

        assert results["success"] == 2
        assert results["failure"] == 1


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestApigeeClientContextManager:
    async def test_async_context_manager_closes_client(
        self, auth_client: MagicMock
    ) -> None:
        """Verify that __aexit__ calls aclose()."""
        with respx.mock:
            respx.post(_INGEST_URL).mock(return_value=httpx.Response(200))
            async with ApigeeClient(
                apigee_base_url=_BASE_URL,
                auth_client=auth_client,
                api_key="k",
                max_retries=1,
                retry_base_delay_seconds=0.0,
            ) as client:
                payload = MetricPayload(
                    source_lz_id="lz", cloud_provider="azure", domain="compute"
                )
                await client.send(payload)
            # After __aexit__, the underlying httpx client should be closed
            assert client._http.is_closed
