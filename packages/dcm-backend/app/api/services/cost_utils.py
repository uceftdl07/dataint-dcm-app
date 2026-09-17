"""Shared cost query helpers — no route imports."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

_DEFAULT_LOOKBACK_DAYS = 30


def default_cost_dates() -> tuple[date, date]:
    today = datetime.now(UTC).date()
    return today - timedelta(days=_DEFAULT_LOOKBACK_DAYS), today


def iso_cost_period(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
