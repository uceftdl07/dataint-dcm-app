"""Tests for RedshiftCollector — cluster health and CloudWatch performance metrics.

Stubs boto3 Redshift and CloudWatch clients via ``unittest.mock``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aws_collector.collectors.redshift import (
    RedshiftCollector,
    _collect_cluster_metric,
    _paginate_clusters,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_cluster(
    cluster_id: str = "my-cluster",
    status: str = "available",
    db_name: str = "dev",
    az: str = "eu-west-1a",
    total_storage_mb: int | None = 2_048_000,  # ~2 TB
    endpoint_address: str = "my-cluster.abcdef.eu-west-1.redshift.amazonaws.com",
    tags: list[dict] | None = None,
) -> dict[str, Any]:
    cluster: dict[str, Any] = {
        "ClusterIdentifier": cluster_id,
        "ClusterStatus": status,
        "DBName": db_name,
        "AvailabilityZone": az,
        "Endpoint": {"Address": endpoint_address},
        "Tags": tags or [{"TagKey": "env", "TagValue": "prod"}],
    }
    if total_storage_mb is not None:
        cluster["TotalStorageCapacityInMegaBytes"] = total_storage_mb
    return cluster


# ---------------------------------------------------------------------------
# _paginate_clusters
# ---------------------------------------------------------------------------


class TestPaginateClusters:
    @pytest.mark.asyncio
    async def test_single_page(self) -> None:
        rs = MagicMock()
        rs.describe_clusters = MagicMock(return_value={"Clusters": [_make_cluster("c1"), _make_cluster("c2")]})

        with patch("aws_collector.collectors.redshift.run_sync", new=AsyncMock(side_effect=lambda f, **kw: f(**kw))):
            clusters = await _paginate_clusters(rs)

        assert len(clusters) == 2

    @pytest.mark.asyncio
    async def test_multi_page_follows_marker(self) -> None:
        pages = [
            {"Clusters": [_make_cluster("c1")], "Marker": "m1"},
            {"Clusters": [_make_cluster("c2")]},
        ]
        rs = MagicMock()
        rs.describe_clusters = MagicMock(side_effect=pages)

        captured: list[dict] = []

        async def fake_run_sync(func, **kwargs):  # type: ignore[no-untyped-def]
            captured.append(dict(kwargs))
            return func(**kwargs)

        with patch("aws_collector.collectors.redshift.run_sync", new=fake_run_sync):
            clusters = await _paginate_clusters(rs)

        assert len(clusters) == 2
        assert captured[1].get("Marker") == "m1"


# ---------------------------------------------------------------------------
# _collect_cluster_metric
# ---------------------------------------------------------------------------


_MB_TO_GB = 1.0 / 1024.0


class TestCollectClusterMetric:
    @pytest.mark.asyncio
    async def test_full_cluster_collected(self) -> None:
        cluster = _make_cluster(total_storage_mb=1_024_000)  # 1 000 GB
        cw = MagicMock()

        cw_values = {
            "CPUUtilization": 35.0,
            "PercentageDiskSpaceUsed": 60.0,
            "DatabaseConnections": 8.0,
        }

        async def fake_fetch(client, namespace, metric_name, dims, **kwargs):  # type: ignore[no-untyped-def]
            return cw_values.get(metric_name)

        with patch("aws_collector.collectors.redshift.fetch_cloudwatch_metric", fake_fetch):
            metric = await _collect_cluster_metric(cluster, cw)

        assert metric is not None
        assert metric.cpu_percent == pytest.approx(35.0)
        assert metric.active_connections == 8
        expected_limit = round(1_024_000 * _MB_TO_GB, 2)  # ~1000 GB
        assert metric.storage_limit_gb == pytest.approx(expected_limit, rel=1e-3)
        # storage_used = limit * 60 / 100
        assert metric.storage_used_gb == pytest.approx(expected_limit * 0.60, rel=1e-3)
        assert metric.is_available is True
        assert metric.tags == {"env": "prod"}

    @pytest.mark.asyncio
    async def test_missing_cluster_id_returns_none(self) -> None:
        cluster = _make_cluster()
        cluster["ClusterIdentifier"] = ""
        cw = MagicMock()

        metric = await _collect_cluster_metric(cluster, cw)
        assert metric is None

    @pytest.mark.asyncio
    async def test_no_storage_capacity_gives_none_limit(self) -> None:
        cluster = _make_cluster(total_storage_mb=None)
        cw = MagicMock()

        async def fake_fetch(*args, **kwargs):  # type: ignore[no-untyped-def]
            return 10.0

        with patch("aws_collector.collectors.redshift.fetch_cloudwatch_metric", fake_fetch):
            metric = await _collect_cluster_metric(cluster, cw)

        assert metric is not None
        assert metric.storage_limit_gb is None
        assert metric.storage_used_gb is None

    @pytest.mark.asyncio
    async def test_no_disk_pct_gives_none_used(self) -> None:
        cluster = _make_cluster(total_storage_mb=512_000)
        cw = MagicMock()

        async def fake_fetch(client, namespace, metric_name, dims, **kwargs):  # type: ignore[no-untyped-def]
            if metric_name == "PercentageDiskSpaceUsed":
                return None
            return 20.0

        with patch("aws_collector.collectors.redshift.fetch_cloudwatch_metric", fake_fetch):
            metric = await _collect_cluster_metric(cluster, cw)

        assert metric is not None
        assert metric.storage_used_gb is None

    @pytest.mark.asyncio
    async def test_status_prep_for_resize_is_available(self) -> None:
        cluster = _make_cluster(status="available, prep-for-resize")
        cw = MagicMock()

        async def fake_fetch(*args, **kwargs):  # type: ignore[no-untyped-def]
            return None

        with patch("aws_collector.collectors.redshift.fetch_cloudwatch_metric", fake_fetch):
            metric = await _collect_cluster_metric(cluster, cw)

        assert metric is not None
        assert metric.is_available is True

    @pytest.mark.asyncio
    async def test_modifying_status_not_available(self) -> None:
        cluster = _make_cluster(status="modifying")
        cw = MagicMock()

        async def fake_fetch(*args, **kwargs):  # type: ignore[no-untyped-def]
            return None

        with patch("aws_collector.collectors.redshift.fetch_cloudwatch_metric", fake_fetch):
            metric = await _collect_cluster_metric(cluster, cw)

        assert metric is not None
        assert metric.is_available is False

    @pytest.mark.asyncio
    async def test_tags_redshift_format_parsed(self) -> None:
        cluster = _make_cluster(tags=[{"TagKey": "team", "TagValue": "data"}, {"TagKey": "tier", "TagValue": "gold"}])
        cw = MagicMock()

        async def fake_fetch(*args, **kwargs):  # type: ignore[no-untyped-def]
            return None

        with patch("aws_collector.collectors.redshift.fetch_cloudwatch_metric", fake_fetch):
            metric = await _collect_cluster_metric(cluster, cw)

        assert metric is not None
        assert metric.tags == {"team": "data", "tier": "gold"}

    @pytest.mark.asyncio
    async def test_tag_without_tag_key_skipped(self) -> None:
        cluster = _make_cluster(tags=[{"TagValue": "orphan"}])
        cw = MagicMock()

        async def fake_fetch(*args, **kwargs):  # type: ignore[no-untyped-def]
            return None

        with patch("aws_collector.collectors.redshift.fetch_cloudwatch_metric", fake_fetch):
            metric = await _collect_cluster_metric(cluster, cw)

        assert metric is not None
        assert metric.tags == {}

    @pytest.mark.asyncio
    async def test_endpoint_address_used_as_server_name(self) -> None:
        cluster = _make_cluster(endpoint_address="my-cluster.abc.eu-west-1.redshift.amazonaws.com")
        cw = MagicMock()

        async def fake_fetch(*args, **kwargs):  # type: ignore[no-untyped-def]
            return None

        with patch("aws_collector.collectors.redshift.fetch_cloudwatch_metric", fake_fetch):
            metric = await _collect_cluster_metric(cluster, cw)

        assert metric is not None
        assert metric.server_name == "my-cluster.abc.eu-west-1.redshift.amazonaws.com"

    @pytest.mark.asyncio
    async def test_connections_rounded_to_int(self) -> None:
        cluster = _make_cluster()
        cw = MagicMock()

        async def fake_fetch(client, namespace, metric_name, dims, **kwargs):  # type: ignore[no-untyped-def]
            if metric_name == "DatabaseConnections":
                return 7.8
            return None

        with patch("aws_collector.collectors.redshift.fetch_cloudwatch_metric", fake_fetch):
            metric = await _collect_cluster_metric(cluster, cw)

        assert metric is not None
        assert metric.active_connections == 8


# ---------------------------------------------------------------------------
# RedshiftCollector._collect_metrics (integration)
# ---------------------------------------------------------------------------


class TestRedshiftCollectorCollectMetrics:
    def _make_collector(self) -> RedshiftCollector:
        with patch("boto3.client"):
            return RedshiftCollector(source_lz_id="lz-aws-1", aws_region="eu-west-1")

    @pytest.mark.asyncio
    async def test_collects_all_clusters(self) -> None:
        collector = self._make_collector()
        clusters = [_make_cluster("c1"), _make_cluster("c2")]

        async def fake_paginate(rs):  # type: ignore[no-untyped-def]
            return clusters

        async def fake_collect(cluster, cw):  # type: ignore[no-untyped-def]
            from dcm_commons.models.database import DatabaseMetric
            from dcm_commons.models.enums import DatabaseType

            return DatabaseMetric(
                db_id=f"arn::cluster:{cluster['ClusterIdentifier']}",
                db_name=cluster.get("DBName", ""),
                db_type=DatabaseType.REDSHIFT,
                server_name=cluster["ClusterIdentifier"],
                region="eu-west-1a",
                is_available=True,
            )

        with (
            patch("aws_collector.collectors.redshift._paginate_clusters", fake_paginate),
            patch("aws_collector.collectors.redshift._collect_cluster_metric", fake_collect),
        ):
            metrics = await collector._collect_metrics()

        assert len(metrics) == 2

    @pytest.mark.asyncio
    async def test_listing_failure_raises_collection_error(self) -> None:
        from dcm_commons.exceptions import CollectionError

        collector = self._make_collector()

        async def fake_paginate(rs):  # type: ignore[no-untyped-def]
            raise RuntimeError("network error")

        with patch("aws_collector.collectors.redshift._paginate_clusters", fake_paginate):
            with pytest.raises(CollectionError):
                await collector._collect_metrics()

    @pytest.mark.asyncio
    async def test_none_metric_skipped(self) -> None:
        """_collect_cluster_metric returning None must not add an entry to the list."""
        collector = self._make_collector()

        async def fake_paginate(rs):  # type: ignore[no-untyped-def]
            return [_make_cluster("no-id")]

        async def fake_collect(cluster, cw):  # type: ignore[no-untyped-def]
            return None  # e.g. missing ClusterIdentifier

        with (
            patch("aws_collector.collectors.redshift._paginate_clusters", fake_paginate),
            patch("aws_collector.collectors.redshift._collect_cluster_metric", fake_collect),
        ):
            metrics = await collector._collect_metrics()

        assert metrics == []
