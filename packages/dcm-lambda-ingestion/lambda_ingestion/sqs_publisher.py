"""SQS publisher — serialises and enqueues a MetricPayload for downstream processing.

Each published message carries three **MessageAttributes** so that SQS filter
policies (or the Databricks consumer) can route payloads without deserialising
the full body:

* ``domain``         — e.g. ``"pipeline"``, ``"cluster"``, ``"cost"``, ``"database"``
* ``cloud_provider`` — ``"azure"`` or ``"aws"``
* ``source_lz_id``  — opaque Landing Zone identifier (e.g. ``"aws-account-551656632516"``)
"""

from __future__ import annotations

import boto3  # type: ignore[import-untyped]

from dcm_commons.models.payload import MetricPayload

__all__ = ["SQSPublisher"]


class SQSPublisher:
    """Publishes :class:`~dcm_commons.metrics.MetricPayload` messages to an SQS queue.

    The underlying boto3 SQS client is created once in ``__init__`` and reused
    across all :meth:`publish` calls.  When the Lambda is warm, this avoids
    re-establishing TCP connections on every invocation.

    Args:
        queue_url: Full SQS queue URL
            (e.g. ``https://sqs.eu-west-1.amazonaws.com/123456789012/dcm-metrics-queue``).
    """

    def __init__(self, queue_url: str) -> None:
        self._queue_url = queue_url
        self._sqs = boto3.client("sqs")

    def publish(self, payload: MetricPayload) -> str:
        """Serialise ``payload`` to JSON and send it to the SQS queue.

        The message body is produced by :meth:`~pydantic.BaseModel.model_dump_json`
        so that all Pydantic types (``datetime``, ``Enum``, ``UUID``, …) are
        serialised correctly.

        Args:
            payload: Validated :class:`~dcm_commons.metrics.MetricPayload` to enqueue.

        Returns:
            The SQS ``MessageId`` string returned by the service.

        Raises:
            Exception: Propagated from boto3 on any SQS error (throttling,
                permissions, queue not found, …).  The Lambda handler converts
                these to ``500`` responses.
        """
        response = self._sqs.send_message(
            QueueUrl=self._queue_url,
            MessageBody=payload.model_dump_json(),
            MessageAttributes={
                "domain": {
                    "DataType": "String",
                    "StringValue": str(payload.domain),
                },
                "cloud_provider": {
                    "DataType": "String",
                    "StringValue": str(payload.cloud_provider),
                },
                "source_lz_id": {
                    "DataType": "String",
                    "StringValue": payload.source_lz_id,
                },
            },
        )
        return str(response["MessageId"])
