"""DCM Lambda Ingestion — AWS Lambda function for metric payload ingestion.

This package implements the serverless ingestion endpoint of the Data Connect
Monitoring (DCM) platform.  It is deployed as an **AWS Lambda function**
invoked via API Gateway (internal VPC endpoint) after Apigee has validated
the Bearer JWT from the collecting agent.

Flow
----
1. Apigee forwards the HTTP POST body to API Gateway over VPC Lattice (mTLS).
2. This Lambda validates the JSON body against the Pydantic
   :class:`~dcm_commons.metrics.MetricPayload` schema.
3. The validated payload is published to the SQS target queue with routing
   attributes (``domain``, ``cloud_provider``, ``source_lz_id``).
4. A ``202 Accepted`` response is returned with the ``collection_run_id``.

The Lambda is stateless — the :class:`~lambda_ingestion.sqs_publisher.SQSPublisher`
is instantiated once per cold-start (module-level singleton) to reuse the
underlying boto3 connection pool across warm invocations.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
