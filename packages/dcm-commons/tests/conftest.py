"""Shared pytest fixtures for dcm-commons test suite.

All fixtures here are available to every test module without explicit import.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from dcm_commons.auth.entra_id import EntraIDAuthClient
from dcm_commons.models.enums import CloudProvider, MetricDomain
from dcm_commons.models.payload import MetricPayload


@pytest.fixture
def utc_now() -> datetime:
    """Return the current UTC datetime with timezone info."""
    return datetime.now(timezone.utc)


@pytest.fixture
def mock_auth_client() -> MagicMock:
    """``EntraIDAuthClient`` that always returns a static test bearer token.

    Use this in tests that require an auth client without triggering
    real MSAL calls.
    """
    client = MagicMock(spec=EntraIDAuthClient)
    client.get_token.return_value = "test-bearer-token-abcdef"
    return client


@pytest.fixture
def sample_payload() -> MetricPayload:
    """A minimal valid ``MetricPayload`` for use across test modules."""
    return MetricPayload(
        source_lz_id="azure-sub-fa5abbc4",
        cloud_provider=CloudProvider.AZURE,
        domain=MetricDomain.PIPELINE,
        metrics=[{"pipeline_name": "test_pipeline", "status": "succeeded"}],
        metadata={"region": "westeurope"},
    )


@pytest.fixture
def empty_payload() -> MetricPayload:
    """A ``MetricPayload`` with no metrics (empty collection run)."""
    return MetricPayload(
        source_lz_id="aws-account-123456789",
        cloud_provider=CloudProvider.AWS,
        domain=MetricDomain.COMPUTE,
        metrics=[],
    )
