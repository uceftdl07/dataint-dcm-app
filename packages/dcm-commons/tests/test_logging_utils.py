"""Tests for structured logging helpers."""

from __future__ import annotations

from dcm_commons.logging_utils import LogMarker, log_line


def test_log_line_includes_marker_and_summary() -> None:
    fields = log_line(LogMarker.OK, "[1/4] cost: 26 metrics", collector="cost_management")
    assert fields["marker"] == "OK"
    assert fields["summary"] == "[1/4] cost: 26 metrics"
    assert fields["collector"] == "cost_management"


def test_log_marker_values_are_ascii() -> None:
    assert LogMarker.FAIL == "XX"
    assert LogMarker.SLEEP == "zz"
