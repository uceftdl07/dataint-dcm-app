"""DCM Commons — shared library for Data Connect Monitoring.

Provides models, authentication, base collector, Apigee client, exceptions,
and structured logging utilities used by all DCM components:

- ``dcm-azure-collector``
- ``dcm-aws-collector``
- ``dcm-lambda-ingestion``
- ``dcm-databricks-pipeline``
- ``dcm-backend``

Quick start::

    from dcm_commons.logging_utils import configure_logging, get_logger
    from dcm_commons.models import MetricPayload, CloudProvider, MetricDomain
    from dcm_commons.auth import EntraIDAuthClient
    from dcm_commons.collectors import BaseCollector
    from dcm_commons.clients import ApigeeClient
    from dcm_commons.exceptions import CollectionError, IngestionError

    configure_logging("my-component")
    logger = get_logger(__name__)
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
