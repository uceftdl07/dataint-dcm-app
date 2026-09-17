"""Lambda handler — HTTP entry point for metric payload ingestion.

This module is the top-level entry point of the ``dcm-lambda-ingestion``
Lambda function.  It is configured as ``lambda_ingestion.handler.handler``
in the Lambda runtime.

Request format
--------------
The function expects a JSON body conforming to
:class:`~dcm_commons.metrics.MetricPayload`.  API Gateway / VPC Lattice
passes the raw HTTP body as ``event["body"]`` (string) or, when already
base64-decoded by the runtime, as a Python dict.

Response codes
--------------
202 Accepted
    Payload validated and enqueued successfully.
400 Bad Request
    Body is missing, not valid JSON, or fails Pydantic validation.
500 Internal Server Error
    Unexpected error (SQS unavailable, misconfigured environment, …).

Cold-start behaviour
--------------------
:data:`_publisher` is initialised **once** at module load time (after the
first invocation resolves ``SQS_QUEUE_URL`` from the environment).  Subsequent
warm invocations skip the boto3 client creation overhead.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from lambda_ingestion.sqs_publisher import SQSPublisher
from lambda_ingestion.validator import validate_payload

__all__ = ["handler"]

# Standard Lambda logging (JSON when deployed, text locally).
logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)

# Module-level singleton — created on first invocation (cold start).
_publisher: SQSPublisher | None = None


def _get_publisher() -> SQSPublisher:
    """Return the module-level :class:`SQSPublisher`, creating it if needed.

    The queue URL is read from the ``SQS_QUEUE_URL`` environment variable.
    This is deferred to the first call so that unit tests can patch the env
    before the publisher is instantiated.

    Returns:
        A ready :class:`SQSPublisher` instance.

    Raises:
        KeyError: If ``SQS_QUEUE_URL`` is not set in the environment.
    """
    global _publisher  # noqa: PLW0603
    if _publisher is None:
        _publisher = SQSPublisher(queue_url=os.environ["SQS_QUEUE_URL"])
    return _publisher


def _parse_body(event: dict[str, Any]) -> dict[str, Any]:
    """Extract and JSON-decode the request body from an API Gateway event.

    Args:
        event: Raw Lambda event dict from API Gateway / VPC Lattice.

    Returns:
        Decoded body as a Python dict.

    Raises:
        ValueError: If the body is absent or not valid JSON.
    """
    raw_body = event.get("body")
    if raw_body is None:
        raise ValueError("Request body is missing")

    if isinstance(raw_body, dict):
        return raw_body

    try:
        decoded: dict[str, Any] = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Request body is not valid JSON: {exc}") from exc

    if not isinstance(decoded, dict):
        raise ValueError("Request body must be a JSON object")

    return decoded


def _ok(run_id: str) -> dict[str, Any]:
    return {
        "statusCode": 202,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"run_id": run_id, "status": "accepted"}),
    }


def _bad_request(message: str) -> dict[str, Any]:
    return {
        "statusCode": 400,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": message}),
    }


def _internal_error() -> dict[str, Any]:
    return {
        "statusCode": 500,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": "internal server error"}),
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda handler for metric payload ingestion.

    Parses the HTTP request body, validates it against
    :class:`~dcm_commons.metrics.MetricPayload`, publishes to SQS, and
    returns the appropriate HTTP response dict consumed by API Gateway.

    Args:
        event:   API Gateway proxy integration event.
        context: Lambda context object (unused; present for signature compat).

    Returns:
        API Gateway response dict with ``statusCode``, ``headers``, and ``body``.
    """
    try:
        body = _parse_body(event)
    except ValueError as exc:
        _logger.warning("lambda_ingestion_bad_body reason=%s", exc)
        return _bad_request(str(exc))

    try:
        payload = validate_payload(body)
    except ValueError as exc:
        _logger.warning(
            "lambda_ingestion_validation_failed reason=%s body_keys=%s",
            exc,
            sorted(body.keys()) if isinstance(body, dict) else type(body).__name__,
        )
        return _bad_request(str(exc))

    try:
        message_id = _get_publisher().publish(payload)
    except Exception as exc:  # noqa: BLE001
        _logger.error("lambda_ingestion_sqs_error reason=%s", exc, exc_info=True)
        return _internal_error()

    _logger.info(
        "lambda_ingestion_accepted run_id=%s domain=%s cloud=%s metrics=%d sqs_message_id=%s",
        payload.collection_run_id,
        payload.domain,
        payload.cloud_provider,
        len(payload.metrics),
        message_id,
    )
    return _ok(str(payload.collection_run_id))
