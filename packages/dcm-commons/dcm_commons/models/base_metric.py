"""Shared Pydantic base class for all DCM domain metric models.

Every domain model (``PipelineMetric``, ``ClusterMetric``, etc.) inherits from
``BaseMetricModel`` to enforce a uniform configuration policy across the entire
model hierarchy.  Centralising the ``ConfigDict`` here means that tightening or
relaxing a setting (e.g. enabling ``extra = "forbid"``) is a single-line change.

Design decisions
----------------
frozen
    Instances are immutable after construction.  This makes them safe to hash,
    cache, and pass across threads without defensive copying.

str_strip_whitespace
    Strips leading/trailing whitespace from every string field automatically.
    Prevents subtle bugs where cloud APIs return ``"pipeline_name "`` (trailing
    space) which would break equality checks and Lakebase UPSERT logic.

use_enum_values
    Enum fields store and serialise their underlying string values rather than
    the enum member itself.  This ensures that ``model_dump()`` and
    ``model_dump(mode="json")`` both produce plain strings, making JSON
    round-trips transparent without explicit ``.value`` calls.

populate_by_name
    Allows model construction by both field name and alias.  Required when
    domain models use ``alias`` for fields whose JSON keys use hyphens or
    reserved Python keywords.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = ["BaseMetricModel"]


class BaseMetricModel(BaseModel):
    """Immutable Pydantic base for all DCM metric models.

    Inherit from this class instead of ``pydantic.BaseModel`` for every domain
    metric model in ``dcm_commons.models``.

    Example::

        class PipelineMetric(BaseMetricModel):
            pipeline_id: str
            pipeline_name: str
            status: PipelineRunStatus
    """

    model_config = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
        use_enum_values=True,
        populate_by_name=True,
    )
