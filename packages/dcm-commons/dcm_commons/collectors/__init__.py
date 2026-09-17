"""DCM collector base classes.

Collector agents inherit from :class:`BaseCollector` and implement
``_collect_metrics()`` to produce domain-specific metric dicts.

Typical usage::

    from dcm_commons.collectors import BaseCollector, CollectionResult
    from dcm_commons.models.enums import MetricDomain

    class MyCollector(BaseCollector):
        @property
        def domain(self) -> MetricDomain:
            return MetricDomain.PIPELINE

        async def _collect_metrics(self) -> list[dict]:
            ...
"""

from __future__ import annotations

from dcm_commons.collectors.base import BaseCollector, CollectionResult

__all__ = [
    "BaseCollector",
    "CollectionResult",
]
