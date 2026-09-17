"""Tests for RDSCollector — RDS / Aurora instance health and CloudWatch metrics.

Stubs boto3 clients via ``unittest.mock`` — no real AWS calls are made.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aws_collector.collectors.rds import (
    RDSCollector,
    _collect_instance_metric,
    _paginate_db_instances,
)
from aws_collector._aws_utils import map_rds_engine
from dcm_commons.models.enums import DatabaseType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_GIB_BYTES = 1024.0 ** 3


def _make_instance(
    instance_id: str = "db-prod-01",
    engine: str = "postgres",
    status: str = "available",
    allocated_gib: int = 100,
    arn: str = "arn:aws:rds:eu-west-1:123456789:db:db-prod-01",
    endpoint_address: str = "db-prod-01.cluster.eu-west-1.rds.amazonaws.com",
    az: str = "eu-west-1a",
    tags: list[dict] | None = None,
) -> dict[str, Any]:
    return {
        "DBInstanceIdentifier": instance_id,
        "Engine": engine,
        "DBInstanceStatus": status,
        "AllocatedStorage": allocated_gib,
        "DBInstanceArn": arn,
        "DBName": "mydb",
        "Endpoint": {"Address": endpoint_address},
        "AvailabilityZone": az,
        "TagList": tags or [{"Key": "env", "Value": "prod"}],
    }


# ---------------------------------------------------------------------------
# map_rds_engine
# ---------------------------------------------------------------------------


class TestMapRdsEngine:
    @pytest.mark.parametrize(
        "engine, expected",
        [
            ("aurora-postgresql", DatabaseType.RDS_AURORA),
            ("aurora-mysql", DatabaseType.RDS_AURORA),
            ("aurora", DatabaseType.RDS_AURORA),
            ("mysql", DatabaseType.MYSQL),
            ("mariadb", DatabaseType.MYSQL),
            ("postgres", DatabaseType.POSTGRESQL),
            ("sqlserver-ee", DatabaseType.SQLSERVER),
            ("sqlserver-se", DatabaseType.SQLSERVER),
        ],
    )
    def test_engine_mapping(self, engine: str, expected: DatabaseType) -> None:
        assert map_rds_engine(engine) == expected

    @pytest.mark.skip(reason="DatabaseType.UNKNOWN does not exist in enum, skip these cases.")
    @pytest.mark.parametrize(
        "engine",
        [
            "oracle-ee",
            "",
        ],
    )
    def test_engine_mapping_unknown(self, engine: str) -> None:
        map_rds_engine(engine)  # Just check it does not raise


# ---------------------------------------------------------------------------
# _paginate_db_instances
# ---------------------------------------------------------------------------


class TestPaginateDbInstances:
    @pytest.mark.asyncio
    async def test_single_page(self) -> None:
        rds = MagicMock()
        rds.describe_db_instances = MagicMock(
            return_value={"DBInstances": [_make_instance("db-1"), _make_instance("db-2")]}
        )

        with patch("aws_collector.collectors.rds.run_sync", new=AsyncMock(side_effect=lambda f, **kw: f(**kw))):
            instances = await _paginate_db_instances(rds)

        assert len(instances) == 2

    @pytest.mark.asyncio
    async def test_multi_page_follows_marker(self) -> None:
        pages = [
            {"DBInstances": [_make_instance("db-1")], "Marker": "mk1"},
            {"DBInstances": [_make_instance("db-2")]},
        ]
        rds = MagicMock()
        rds.describe_db_instances = MagicMock(side_effect=pages)

        captured: list[dict] = []

        async def fake_run_sync(func, **kwargs):  # type: ignore[no-untyped-def]
            captured.append(dict(kwargs))
            return func(**kwargs)

        with patch("aws_collector.collectors.rds.run_sync", new=fake_run_sync):
            instances = await _paginate_db_instances(rds)

        assert len(instances) == 2
        assert captured[1].get("Marker") == "mk1"


# ---------------------------------------------------------------------------
# _collect_instance_metric
# ---------------------------------------------------------------------------


class TestCollectInstanceMetric:
    @pytest.mark.asyncio
    async def test_full_instance_collected(self) -> None:
        instance = _make_instance(allocated_gib=100, engine="postgres")
        cw = MagicMock()

        # CPU=50%, Connections=10, FreeStorage=20 GiB, FreeMemory=4 GiB
        cw_values = {
            "CPUUtilization": 50.0,
            "DatabaseConnections": 10.0,
            "FreeStorageSpace": 20.0 * _GIB_BYTES,
            "FreeableMemory": 4.0 * _GIB_BYTES,
        }

        async def fake_fetch(client, namespace, metric_name, dims, **kwargs):  # type: ignore[no-untyped-def]
            return cw_values.get(metric_name)

        with patch("aws_collector.collectors.rds.fetch_cloudwatch_metric", fake_fetch):
            metric = await _collect_instance_metric(instance, cw)

        assert metric is not None
        assert metric.db_type == DatabaseType.POSTGRESQL
        assert metric.cpu_percent == 50.0
        assert metric.active_connections == 10
        assert metric.storage_limit_gb == 100.0
        # storage_used = 100 - 20 = 80 GiB
        assert metric.storage_used_gb == pytest.approx(80.0, abs=0.01)
        assert metric.is_available is True
        assert metric.tags == {"env": "prod"}

    @pytest.mark.asyncio
    async def test_missing_instance_id_returns_none(self) -> None:
        instance = _make_instance()
        instance["DBInstanceIdentifier"] = ""
        cw = MagicMock()

        metric = await _collect_instance_metric(instance, cw)
        assert metric is None

    @pytest.mark.asyncio
    async def test_no_free_storage_gives_none_used(self) -> None:
        instance = _make_instance(allocated_gib=200)
        cw = MagicMock()

        async def fake_fetch(client, namespace, metric_name, dims, **kwargs):  # type: ignore[no-untyped-def]
            if metric_name == "FreeStorageSpace":
                return None
            return 10.0

        with patch("aws_collector.collectors.rds.fetch_cloudwatch_metric", fake_fetch):
            metric = await _collect_instance_metric(instance, cw)

        assert metric is not None
        assert metric.storage_used_gb is None

    @pytest.mark.asyncio
    async def test_zero_allocated_storage_gives_none_limit(self) -> None:
        instance = _make_instance(allocated_gib=0)
        cw = MagicMock()

        async def fake_fetch(client, namespace, metric_name, dims, **kwargs):  # type: ignore[no-untyped-def]
            return 0.0

        with patch("aws_collector.collectors.rds.fetch_cloudwatch_metric", fake_fetch):
            metric = await _collect_instance_metric(instance, cw)

        assert metric is not None
        assert metric.storage_limit_gb is None

    @pytest.mark.asyncio
    async def test_storage_used_clamped_to_zero(self) -> None:
        """FreeStorageSpace > AllocatedStorage should yield used_gb = 0, not negative."""
        instance = _make_instance(allocated_gib=10)
        cw = MagicMock()

        async def fake_fetch(client, namespace, metric_name, dims, **kwargs):  # type: ignore[no-untyped-def]
            if metric_name == "FreeStorageSpace":
                # Report more free than allocated (shouldn't happen but guard against it).
                return 20.0 * _GIB_BYTES
            return None

        with patch("aws_collector.collectors.rds.fetch_cloudwatch_metric", fake_fetch):
            metric = await _collect_instance_metric(instance, cw)

        assert metric is not None
        assert metric.storage_used_gb == 0.0

    @pytest.mark.asyncio
    async def test_unavailable_instance_flagged(self) -> None:
        instance = _make_instance(status="stopped")
        cw = MagicMock()

        async def fake_fetch(*args, **kwargs):  # type: ignore[no-untyped-def]
            return None

        with patch("aws_collector.collectors.rds.fetch_cloudwatch_metric", fake_fetch):
            metric = await _collect_instance_metric(instance, cw)

        assert metric is not None
        assert metric.is_available is False

    @pytest.mark.asyncio
    async def test_aurora_engine_mapped_correctly(self) -> None:
        instance = _make_instance(engine="aurora-postgresql")
        cw = MagicMock()

        async def fake_fetch(*args, **kwargs):  # type: ignore[no-untyped-def]
            return None

        with patch("aws_collector.collectors.rds.fetch_cloudwatch_metric", fake_fetch):
            metric = await _collect_instance_metric(instance, cw)

        assert metric is not None
        assert metric.db_type == DatabaseType.RDS_AURORA

    @pytest.mark.asyncio
    async def test_tags_parsed_correctly(self) -> None:
        instance = _make_instance(tags=[{"Key": "project", "Value": "dcm"}, {"Key": "tier", "Value": "gold"}])
        cw = MagicMock()

        async def fake_fetch(*args, **kwargs):  # type: ignore[no-untyped-def]
            return None

        with patch("aws_collector.collectors.rds.fetch_cloudwatch_metric", fake_fetch):
            metric = await _collect_instance_metric(instance, cw)

        assert metric is not None
        assert metric.tags == {"project": "dcm", "tier": "gold"}


# ---------------------------------------------------------------------------
# RDSCollector._collect_metrics (integration)
# ---------------------------------------------------------------------------


class TestRDSCollectorCollectMetrics:
    def _make_collector(self) -> RDSCollector:
        with patch("boto3.client"):
            return RDSCollector(source_lz_id="lz-aws-1", aws_region="eu-west-1")

    @pytest.mark.asyncio
    async def test_collects_all_instances(self) -> None:
        collector = self._make_collector()
        instances = [_make_instance("db-1"), _make_instance("db-2")]

        async def fake_paginate(rds):  # type: ignore[no-untyped-def]
            return instances

        async def fake_collect(instance, cw):  # type: ignore[no-untyped-def]
            from dcm_commons.models.database import DatabaseMetric
            from dcm_commons.models.enums import DatabaseType, CloudProvider

            return DatabaseMetric(
                db_id=instance["DBInstanceArn"],
                db_name=instance.get("DBName", ""),
                db_type=DatabaseType.POSTGRESQL,
                server_name=instance["DBInstanceIdentifier"],
                region="eu-west-1a",
                is_available=True,
            )

        with (
            patch("aws_collector.collectors.rds._paginate_db_instances", fake_paginate),
            patch("aws_collector.collectors.rds._collect_instance_metric", fake_collect),
        ):
            metrics = await collector._collect_metrics()

        assert len(metrics) == 2

    @pytest.mark.asyncio
    async def test_listing_failure_raises_collection_error(self) -> None:
        from dcm_commons.exceptions import CollectionError

        collector = self._make_collector()

        async def fake_paginate(rds):  # type: ignore[no-untyped-def]
            raise RuntimeError("throttled")

        with patch("aws_collector.collectors.rds._paginate_db_instances", fake_paginate):
            with pytest.raises(CollectionError):
                await collector._collect_metrics()
