"""Tests for lambda_ingestion.sqs_publisher — SQS message publishing.

Uses ``moto`` to mock the SQS API; no real AWS calls are made.
"""

from __future__ import annotations

import json
import os
import uuid
from unittest.mock import MagicMock, patch

import boto3
import pytest

from lambda_ingestion.sqs_publisher import SQSPublisher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_payload(
    domain: str = "pipeline",
    cloud_provider: str = "azure",
    source_lz_id: str = "lz-azure-001",
    metric_count: int = 1,
) -> MagicMock:
    payload = MagicMock()
    payload.domain = domain
    payload.cloud_provider = cloud_provider
    payload.source_lz_id = source_lz_id
    payload.collection_run_id = uuid.uuid4()
    payload.model_dump_json.return_value = json.dumps(
        {
            "collection_run_id": str(payload.collection_run_id),
            "domain": domain,
            "cloud_provider": cloud_provider,
            "source_lz_id": source_lz_id,
            "metrics": [{}] * metric_count,
        }
    )
    return payload


# ---------------------------------------------------------------------------
# Tests using moto
# ---------------------------------------------------------------------------


@pytest.fixture()
def sqs_queue():  # type: ignore[no-untyped-def]
    """Create a real moto SQS queue and return (queue_url, sqs_client).
    
    Sets AWS_DEFAULT_REGION so that SQSPublisher.__init__ can create
    a boto3 client without specifying region explicitly.
    """
    pytest.importorskip("moto")
    import moto  # type: ignore[import-untyped]

    # Set region in environment for SQSPublisher.__init__
    old_region = os.environ.get("AWS_DEFAULT_REGION")
    os.environ["AWS_DEFAULT_REGION"] = "eu-west-1"
    
    try:
        with moto.mock_aws():
            client = boto3.client("sqs", region_name="eu-west-1")
            resp = client.create_queue(QueueName="dcm-metrics-test")
            queue_url = resp["QueueUrl"]
            yield queue_url, client
    finally:
        # Restore original region setting
        if old_region is not None:
            os.environ["AWS_DEFAULT_REGION"] = old_region
        else:
            os.environ.pop("AWS_DEFAULT_REGION", None)


class TestSQSPublisherWithMoto:
    def test_publish_returns_message_id(self, sqs_queue) -> None:  # type: ignore[no-untyped-def]
        queue_url, sqs_client = sqs_queue
        publisher = SQSPublisher(queue_url=queue_url)
        payload = _make_payload()

        message_id = publisher.publish(payload)
        assert isinstance(message_id, str)
        assert len(message_id) > 0

    def test_message_body_is_valid_json(self, sqs_queue) -> None:  # type: ignore[no-untyped-def]
        queue_url, sqs_client = sqs_queue
        publisher = SQSPublisher(queue_url=queue_url)
        payload = _make_payload(domain="cost", cloud_provider="aws")

        publisher.publish(payload)

        messages = sqs_client.receive_message(
            QueueUrl=queue_url,
            MessageAttributeNames=["All"],
            MaxNumberOfMessages=1,
        ).get("Messages", [])

        assert len(messages) == 1
        body = json.loads(messages[0]["Body"])
        assert body["domain"] == "cost"
        assert body["cloud_provider"] == "aws"

    def test_message_attributes_set_correctly(self, sqs_queue) -> None:  # type: ignore[no-untyped-def]
        queue_url, sqs_client = sqs_queue
        publisher = SQSPublisher(queue_url=queue_url)
        payload = _make_payload(
            domain="database",
            cloud_provider="aws",
            source_lz_id="aws-account-123",
        )

        publisher.publish(payload)

        messages = sqs_client.receive_message(
            QueueUrl=queue_url,
            MessageAttributeNames=["All"],
            MaxNumberOfMessages=1,
        ).get("Messages", [])

        attrs = messages[0]["MessageAttributes"]
        assert attrs["domain"]["StringValue"] == "database"
        assert attrs["cloud_provider"]["StringValue"] == "aws"
        assert attrs["source_lz_id"]["StringValue"] == "aws-account-123"

    def test_all_attributes_have_string_data_type(self, sqs_queue) -> None:  # type: ignore[no-untyped-def]
        queue_url, sqs_client = sqs_queue
        publisher = SQSPublisher(queue_url=queue_url)
        payload = _make_payload()

        publisher.publish(payload)

        messages = sqs_client.receive_message(
            QueueUrl=queue_url,
            MessageAttributeNames=["All"],
            MaxNumberOfMessages=1,
        ).get("Messages", [])

        attrs = messages[0]["MessageAttributes"]
        for attr_name in ("domain", "cloud_provider", "source_lz_id"):
            assert attrs[attr_name]["DataType"] == "String", (
                f"{attr_name} must be String type"
            )


# ---------------------------------------------------------------------------
# Tests using unittest.mock (no moto required)
# ---------------------------------------------------------------------------


class TestSQSPublisherWithMock:
    def test_publish_calls_send_message_with_correct_args(self) -> None:
        mock_sqs = MagicMock()
        mock_sqs.send_message.return_value = {"MessageId": "test-msg-id-123"}

        with patch("boto3.client", return_value=mock_sqs):
            publisher = SQSPublisher(queue_url="https://sqs.eu-west-1.amazonaws.com/123/q")

        payload = _make_payload(
            domain="cluster",
            cloud_provider="azure",
            source_lz_id="lz-azure-dp",
        )

        result = publisher.publish(payload)

        assert result == "test-msg-id-123"
        mock_sqs.send_message.assert_called_once()
        call_kwargs = mock_sqs.send_message.call_args.kwargs
        assert call_kwargs["QueueUrl"] == "https://sqs.eu-west-1.amazonaws.com/123/q"
        assert call_kwargs["MessageBody"] == payload.model_dump_json.return_value

    def test_publish_propagates_sqs_exceptions(self) -> None:
        mock_sqs = MagicMock()
        mock_sqs.send_message.side_effect = RuntimeError("SQS throttled")

        with patch("boto3.client", return_value=mock_sqs):
            publisher = SQSPublisher(queue_url="https://sqs.eu-west-1.amazonaws.com/123/q")

        with pytest.raises(RuntimeError, match="SQS throttled"):
            publisher.publish(_make_payload())
