"""Backward-compatibility shim — Sprint 7 (2026-04-13).

``ClusterMetric`` is now ``ComputeMetric``.  This module re-exports the new
class under the old name so existing collector code continues to import without
changes until each component is updated in its own sprint.
"""

from dcm_commons.models.compute import ComputeMetric as ClusterMetric

__all__ = ["ClusterMetric"]
