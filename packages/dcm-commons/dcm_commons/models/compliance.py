"""Backward-compatibility shim — Sprint 7 (2026-04-13).

``ComplianceMetric`` is now ``StandardCheckMetric``.  This module re-exports the
new class under the old name so existing collector code continues to import
without changes until each component is updated in its own sprint.
"""

from dcm_commons.models.standard_check import StandardCheckMetric as ComplianceMetric

__all__ = ["ComplianceMetric"]
