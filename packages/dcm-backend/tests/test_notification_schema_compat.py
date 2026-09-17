"""Tests for notification preferences schema compatibility helpers."""

from __future__ import annotations

from app.notification.schema_compat import (
    is_missing_notification_lz_column_error,
    legacy_preferences_row,
)


def test_detects_missing_lz_column_error() -> None:
    exc = Exception(
        "[UNRESOLVED_COLUMN.WITH_SUGGESTION] `notification_lz_ids` cannot be resolved",
    )
    assert is_missing_notification_lz_column_error(exc) is True


def test_ignores_unrelated_errors() -> None:
    assert is_missing_notification_lz_column_error(Exception("connection timeout")) is False


def test_legacy_preferences_row_adds_empty_lz_list() -> None:
    row = legacy_preferences_row({"user_id": "u1", "show_security": True})
    assert row["notification_lz_ids"] == []
