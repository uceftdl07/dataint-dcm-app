"""Payload validation — parse and validate raw dicts against MetricPayload.

This module provides a single function :func:`validate_payload` that converts
a raw (already JSON-decoded) dictionary into a fully validated
:class:`~dcm_commons.metrics.MetricPayload` instance.  Any validation error
is surfaced as a :class:`ValueError` so that the Lambda handler can return a
clean ``400 Bad Request`` without leaking internal Pydantic tracebacks.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from dcm_commons.models.payload import MetricPayload

__all__ = ["validate_payload"]


def validate_payload(raw: dict[str, Any]) -> MetricPayload:
    """Parse and validate a raw dictionary into a :class:`MetricPayload`.

    Args:
        raw: JSON-decoded request body as a Python dictionary.

    Returns:
        A fully validated :class:`~dcm_commons.metrics.MetricPayload` instance.

    Raises:
        ValueError: If ``raw`` does not conform to the :class:`MetricPayload`
            schema.  The message includes the error count from Pydantic so that
            callers can surface a meaningful ``400`` response without exposing
            the full validation trace.
    """
    try:
        return MetricPayload.model_validate(raw)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or '(root)'}: {err['msg']}"
            for err in exc.errors()[:8]
        )
        raise ValueError(
            f"Payload validation failed: {exc.error_count()} error(s) — {details}"
        ) from exc
