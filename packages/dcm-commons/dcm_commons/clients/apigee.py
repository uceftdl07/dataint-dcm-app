"""Async HTTP client for sending ``MetricPayload`` to the Apigee ingestion gateway.

The gateway validates the bearer token, checks the API key, then forwards the
payload via VPC Lattice to the Lambda Ingestion API → SQS → Databricks pipeline.

Usage as async context manager (recommended)::

    async with ApigeeClient(
        apigee_base_url=settings.apigee_url,
        auth_client=auth,
        api_key=settings.api_key,
    ) as client:
        await client.send(payload)

Usage with explicit lifecycle (e.g. long-lived agent process)::

    client = ApigeeClient(...)
    try:
        await client.send(payload)
    finally:
        await client.aclose()

Retry policy
------------
``send()`` retries the request on retriable HTTP status codes (429, 5xx) and
network-level errors (timeouts, connection refused) up to ``max_retries`` times.
Delay between attempts follows exponential back-off::

    delay = retry_base_delay * 2^(attempt - 1)   # e.g. 2 s, 4 s, 8 s

Client errors (4xx, excluding 429) are **not** retried — the same request would
produce the same rejection.

Note on ``httpx.AsyncClient`` reuse:
    A single ``httpx.AsyncClient`` is created at construction time and reused
    for the lifetime of the ``ApigeeClient``.  Creating a new client per call
    is an anti-pattern that bypasses connection pooling and adds significant
    latency overhead for HTTPS handshakes.
"""

from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Final

import httpx

from dcm_commons.auth.entra_id import EntraIDAuthClient
from dcm_commons.exceptions import IngestionError
from dcm_commons.logging_utils import get_logger
from dcm_commons.models.payload import MetricPayload

__all__ = ["ApigeeClient"]

_INGEST_PATH: Final = "/v1/metrics/ingest"
_DEFAULT_TIMEOUT: Final = 30.0
_DEFAULT_MAX_RETRIES: Final = 3
_DEFAULT_RETRY_BASE_DELAY: Final = 2.0  # seconds

# HTTP status codes that indicate a transient server-side issue — safe to retry.
_RETRIABLE_STATUS: Final = frozenset({429, 500, 502, 503, 504})


class ApigeeClient:
    """Async HTTP client for delivering ``MetricPayload`` to Apigee.

    Manages a persistent ``httpx.AsyncClient`` (connection pooling) and handles
    token refresh, retry with exponential back-off, and structured logging.

    Args:
        apigee_base_url:        Base URL of the Apigee proxy
                                (e.g. ``"https://api.example.com/dcm"``).
                                Trailing slashes are stripped automatically.
        auth_client:            :class:`EntraIDAuthClient` instance for bearer
                                token acquisition.
        api_key:                Apigee API key sent in the ``X-API-Key`` header.
        timeout:                Per-request timeout in seconds.  Defaults to 30.
        max_retries:            Maximum number of send attempts per payload.
                                Defaults to 3.
        retry_base_delay_seconds: Base delay (seconds) for exponential back-off.
                                  Delay after attempt *n* =
                                  ``retry_base_delay_seconds * 2^(n-1)``.
                                  Defaults to 2.0.
    """

    def __init__(
        self,
        apigee_base_url: str,
        auth_client: EntraIDAuthClient,
        api_key: str,
        *,
        timeout: float = _DEFAULT_TIMEOUT,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        retry_base_delay_seconds: float = _DEFAULT_RETRY_BASE_DELAY,
    ) -> None:
        self._auth = auth_client
        self._api_key = api_key
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay_seconds
        base_url = apigee_base_url.rstrip("/")
        self._logger = get_logger(__name__)
        self._http = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )

    # ------------------------------------------------------------------
    # Async context manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> ApigeeClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP client and release connections."""
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def send(self, payload: MetricPayload) -> None:
        """Deliver a single ``MetricPayload`` to the Apigee ingestion endpoint.

        Retries on transient failures (5xx, 429, network errors) with
        exponential back-off.  Non-retriable client errors (4xx) raise
        :class:`~dcm_commons.exceptions.IngestionError` immediately.

        Args:
            payload: The metric payload to deliver.

        Raises:
            IngestionError: If delivery fails after all retry attempts, or if
                            Apigee returns a non-retriable 4xx error.
        """
        # Wire body must be a valid MetricPayload envelope (required by Lambda).
        body = payload.to_ingest_json()
        MetricPayload.model_validate_json(body)
        last_exc: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            self._logger.info(
                "apigee_entra_token_requesting",
                attempt=attempt,
                collection_run_id=payload.collection_run_id,
                domain=payload.domain,
                source_lz_id=payload.source_lz_id,
                cloud_provider=payload.cloud_provider,
                metric_count=payload.metric_count,
            )
            token = self._auth.get_token()
            self._logger.info(
                "apigee_entra_token_acquired",
                attempt=attempt,
                collection_run_id=payload.collection_run_id,
                domain=payload.domain,
            )
            request_headers = {
                "Authorization": f"Bearer {token}",
                "x-apif-apikey": self._api_key,
                "Content-Type": "application/json",
            }
            request = self._http.build_request(
                "POST",
                _INGEST_PATH,
                content=body,
                headers=request_headers,
            )
            try:
                response = await self._http.send(request)

                # Client errors (4xx, not 429) are never retriable.
                if response.is_client_error and response.status_code != 429:
                    raise IngestionError(
                        f"Apigee rejected payload: {response.text[:300]}",
                        status_code=response.status_code,
                    )

                if response.status_code in _RETRIABLE_STATUS:
                    # Raise to trigger the retry path below.
                    response.raise_for_status()

                response.raise_for_status()  # catch any remaining non-2xx

                self._logger.info(
                    "payload_delivered",
                    collection_run_id=payload.collection_run_id,
                    domain=payload.domain,
                    metric_count=payload.metric_count,
                    attempt=attempt,
                    status_code=response.status_code,
                )
                return  # success

            except IngestionError:
                raise  # non-retriable — propagate immediately

            except httpx.HTTPStatusError as exc:
                last_exc = exc
                self._logger.warning(
                    "apigee_server_error",
                    attempt=attempt,
                    max_retries=self._max_retries,
                    status_code=exc.response.status_code,
                    collection_run_id=payload.collection_run_id,
                    error=repr(exc),
                    url = request.url,
                )

            except httpx.RequestError as exc:
                last_exc = exc
                self._logger.warning(
                    "apigee_network_error",
                    attempt=attempt,
                    max_retries=self._max_retries,
                    error=repr(exc),
                    collection_run_id=payload.collection_run_id,
                    url = request.url,
                    exc_info=exc
                )

            if attempt < self._max_retries:
                delay = self._retry_base_delay * (2.0 ** (attempt - 1))
                self._logger.debug(
                    "apigee_retry_scheduled",
                    attempt=attempt,
                    delay_seconds=round(delay, 1),
                )
                await asyncio.sleep(delay)

        # All retries exhausted.
        status_code: int | None = getattr(
            getattr(last_exc, "response", None), "status_code", None
        )
        raise IngestionError(
            f"Delivery failed after {self._max_retries} attempt(s): {repr(last_exc)}",
            status_code=status_code,
        ) from last_exc

    async def send_batch(self, payloads: list[MetricPayload]) -> dict[str, int]:
        """Send multiple payloads sequentially, tolerating individual failures.

        Args:
            payloads: List of payloads to deliver.

        Returns:
            A dict with keys ``"success"`` and ``"failure"`` containing counts.
        """
        results: dict[str, int] = {"success": 0, "failure": 0}
        for index, payload in enumerate(payloads, start=1):
            self._logger.info(
                "apigee_send_batch_item_starting",
                index=index,
                total=len(payloads),
                collection_run_id=payload.collection_run_id,
                domain=payload.domain,
                metric_count=payload.metric_count,
            )
            try:
                await self.send(payload)
                results["success"] += 1
            except IngestionError as exc:
                self._logger.error(
                    "batch_payload_failed",
                    collection_run_id=payload.collection_run_id,
                    domain=payload.domain,
                    reason=str(exc),
                )
                results["failure"] += 1
        return results
