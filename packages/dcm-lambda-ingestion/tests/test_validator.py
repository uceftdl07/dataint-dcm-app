"""Tests for lambda_ingestion.validator — payload validation."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from lambda_ingestion.validator import validate_payload


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_payload(domain: str = "pipeline") -> dict[str, Any]:
    """Build a minimal valid MetricPayload dict."""
    return {
        "collection_run_id": str(uuid.uuid4()),
        "source_lz_id": "lz-azure-test",
        "cloud_provider": "azure",
        "domain": domain,
        "collected_at": "2026-03-19T10:00:00Z",
        "metrics": [
            {
                "pipeline_id": "adf/factories/my-factory/pipelines/etl",
                "pipeline_name": "etl",
                "run_id": str(uuid.uuid4()),
                "status": "succeeded",
                "trigger_type": "scheduled",
                "start_time": "2026-03-19T09:00:00Z",
            }
        ],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestValidatePayload:
    def test_valid_payload_returns_metric_payload(self) -> None:
        raw = _valid_payload()

        # Patch MetricPayload.model_validate to avoid dcm_commons dependency.
        mock_payload = MagicMock()
        with patch("lambda_ingestion.validator.MetricPayload.model_validate", return_value=mock_payload):
            result = validate_payload(raw)

        assert result is mock_payload

    def test_validation_error_raises_value_error(self) -> None:
        from pydantic import ValidationError

        # Create a real ValidationError via a tiny Pydantic model.
        from pydantic import BaseModel

        class _M(BaseModel):
            x: int

        try:
            _M.model_validate({"x": "not-an-int"})
        except ValidationError as ve:
            real_ve = ve

        with patch(
            "lambda_ingestion.validator.MetricPayload.model_validate",
            side_effect=real_ve,
        ):
            with pytest.raises(ValueError, match="Payload validation failed"):
                validate_payload({})

    def test_error_count_included_in_message(self) -> None:
        from pydantic import ValidationError
        from pydantic import BaseModel

        class _M(BaseModel):
            a: int
            b: str

        try:
            _M.model_validate({})
        except ValidationError as ve:
            real_ve = ve  # 2 errors

        with patch(
            "lambda_ingestion.validator.MetricPayload.model_validate",
            side_effect=real_ve,
        ):
            with pytest.raises(ValueError, match=r"\d+ error"):
                validate_payload({})

    def test_non_validation_exception_propagates(self) -> None:
        """Unexpected exceptions (e.g. AttributeError) are NOT swallowed."""
        with patch(
            "lambda_ingestion.validator.MetricPayload.model_validate",
            side_effect=AttributeError("oops"),
        ):
            with pytest.raises(AttributeError):
                validate_payload({})
