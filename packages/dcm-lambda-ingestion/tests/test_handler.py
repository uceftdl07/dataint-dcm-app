"""Tests for lambda_ingestion.handler — Lambda entry point.

Patches validate_payload and SQSPublisher to test HTTP handling in isolation.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from lambda_ingestion import handler as handler_module
from lambda_ingestion.handler import _bad_request, _internal_error, _ok, _parse_body, handler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _api_gw_event(body: Any, *, as_string: bool = True) -> dict[str, Any]:
    """Build a minimal API Gateway proxy event."""
    return {"body": json.dumps(body) if as_string else body}


def _mock_payload(run_id: str = "run-abc-123") -> MagicMock:
    payload = MagicMock()
    payload.collection_run_id = run_id
    payload.domain = "pipeline"
    payload.cloud_provider = "azure"
    payload.metrics = [MagicMock()]
    return payload


# ---------------------------------------------------------------------------
# _parse_body
# ---------------------------------------------------------------------------


class TestParseBody:
    def test_string_body_decoded(self) -> None:
        event = {"body": json.dumps({"key": "val"})}
        result = _parse_body(event)
        assert result == {"key": "val"}

    def test_dict_body_returned_as_is(self) -> None:
        body = {"already": "decoded"}
        result = _parse_body({"body": body})
        assert result is body

    def test_missing_body_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="missing"):
            _parse_body({})

    def test_invalid_json_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="not valid JSON"):
            _parse_body({"body": "not-json{{"})

    def test_non_object_json_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="JSON object"):
            _parse_body({"body": json.dumps([1, 2, 3])})


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------


class TestResponseHelpers:
    def test_ok_returns_202(self) -> None:
        resp = _ok("my-run-id")
        assert resp["statusCode"] == 202
        body = json.loads(resp["body"])
        assert body["run_id"] == "my-run-id"
        assert body["status"] == "accepted"

    def test_bad_request_returns_400(self) -> None:
        resp = _bad_request("some error")
        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert "some error" in body["error"]

    def test_internal_error_returns_500(self) -> None:
        resp = _internal_error()
        assert resp["statusCode"] == 500
        body = json.loads(resp["body"])
        assert "internal server error" in body["error"]


# ---------------------------------------------------------------------------
# handler()
# ---------------------------------------------------------------------------


class TestHandler:
    @pytest.fixture(autouse=True)
    def reset_publisher(self) -> None:  # type: ignore[return]
        """Reset the module-level publisher singleton before each test."""
        handler_module._publisher = None
        yield
        handler_module._publisher = None

    def test_happy_path_returns_202(self) -> None:
        payload = _mock_payload("run-001")

        with (
            patch("lambda_ingestion.handler.validate_payload", return_value=payload),
            patch("lambda_ingestion.handler._get_publisher") as mock_get_pub,
        ):
            mock_pub = MagicMock()
            mock_pub.publish.return_value = "sqs-msg-id-001"
            mock_get_pub.return_value = mock_pub

            resp = handler(_api_gw_event({"dummy": "body"}), context=None)

        assert resp["statusCode"] == 202
        body = json.loads(resp["body"])
        assert body["run_id"] == "run-001"
        assert body["status"] == "accepted"

    def test_missing_body_returns_400(self) -> None:
        resp = handler({}, context=None)
        assert resp["statusCode"] == 400
        assert "missing" in json.loads(resp["body"])["error"]

    def test_invalid_json_body_returns_400(self) -> None:
        resp = handler({"body": "{{bad json"}, context=None)
        assert resp["statusCode"] == 400

    def test_validation_failure_returns_400(self) -> None:
        with patch(
            "lambda_ingestion.handler.validate_payload",
            side_effect=ValueError("Payload validation failed: 2 error(s)"),
        ):
            resp = handler(_api_gw_event({"data": "ok"}), context=None)

        assert resp["statusCode"] == 400
        body = json.loads(resp["body"])
        assert "validation" in body["error"].lower()

    def test_sqs_error_returns_500(self) -> None:
        payload = _mock_payload()

        with (
            patch("lambda_ingestion.handler.validate_payload", return_value=payload),
            patch("lambda_ingestion.handler._get_publisher") as mock_get_pub,
        ):
            mock_pub = MagicMock()
            mock_pub.publish.side_effect = RuntimeError("SQS unavailable")
            mock_get_pub.return_value = mock_pub

            resp = handler(_api_gw_event({"dummy": "body"}), context=None)

        assert resp["statusCode"] == 500

    def test_dict_body_accepted_without_json_decode(self) -> None:
        payload = _mock_payload("run-dict")

        with (
            patch("lambda_ingestion.handler.validate_payload", return_value=payload),
            patch("lambda_ingestion.handler._get_publisher") as mock_get_pub,
        ):
            mock_pub = MagicMock()
            mock_pub.publish.return_value = "msg-id"
            mock_get_pub.return_value = mock_pub

            # body already a dict (API Gateway can pass pre-decoded body)
            resp = handler(_api_gw_event({"key": "val"}, as_string=False), context=None)

        assert resp["statusCode"] == 202

    def test_publisher_singleton_created_once(self) -> None:
        """_get_publisher() must not create a new SQSPublisher on every call."""
        import os

        payload = _mock_payload()

        with (
            patch("lambda_ingestion.handler.validate_payload", return_value=payload),
            patch.dict(os.environ, {"SQS_QUEUE_URL": "https://sqs.test.amazonaws.com/123/q"}),
            patch("lambda_ingestion.sqs_publisher.boto3.client") as mock_client,
        ):
            mock_sqs = MagicMock()
            mock_sqs.send_message.return_value = {"MessageId": "mid"}
            mock_client.return_value = mock_sqs

            handler(_api_gw_event({"dummy": 1}), context=None)
            handler(_api_gw_event({"dummy": 2}), context=None)

        # SQSPublisher.__init__ calls boto3.client once; second call reuses singleton.
        assert mock_client.call_count == 1

    def test_response_has_content_type_header(self) -> None:
        payload = _mock_payload()

        with (
            patch("lambda_ingestion.handler.validate_payload", return_value=payload),
            patch("lambda_ingestion.handler._get_publisher") as mock_get_pub,
        ):
            mock_pub = MagicMock()
            mock_pub.publish.return_value = "mid"
            mock_get_pub.return_value = mock_pub

            resp = handler(_api_gw_event({}), context=None)

        assert resp["headers"]["Content-Type"] == "application/json"
