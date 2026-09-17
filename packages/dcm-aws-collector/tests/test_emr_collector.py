"""Tests for EMRCollector — cluster state snapshots.

Uses ``unittest.mock`` to stub boto3 calls; no real AWS calls are made.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aws_collector.collectors.emr import EMRCollector, _map_cluster, _paginate_clusters
from aws_collector._aws_utils import map_emr_state
from dcm_commons.models.enums import ComputeState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_cluster(
    cluster_id: str = "j-ABCDEF",
    name: str = "spark-etl",
    state: str = "RUNNING",
    num_core: int = 3,
    num_task: int = 2,
    release_label: str = "emr-7.0.0",
    created_at: datetime | None = None,
    tags: list[dict] | None = None,
) -> dict[str, Any]:
    created_at = created_at or datetime(2026, 3, 1, 8, 0, 0, tzinfo=timezone.utc)
    return {
        "Id": cluster_id,
        "Name": name,
        "Status": {
            "State": state,
            "Timeline": {"CreationDateTime": created_at},
        },
        "InstanceGroups": [
            {"InstanceGroupType": "MASTER", "RunningInstanceCount": 1},
            {"InstanceGroupType": "CORE", "RunningInstanceCount": num_core},
            {"InstanceGroupType": "TASK", "RunningInstanceCount": num_task},
        ],
        "ReleaseLabel": release_label,
        "Ec2InstanceAttributes": {"Ec2SubnetId": "subnet-123"},
        "Tags": tags or [{"Key": "env", "Value": "prod"}],
    }


# ---------------------------------------------------------------------------
# map_emr_state
# ---------------------------------------------------------------------------


    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("STARTING", ComputeState.STARTING),
            ("BOOTSTRAPPING", ComputeState.STARTING),
            ("RUNNING", ComputeState.RUNNING),
            ("WAITING", ComputeState.RUNNING),
            ("TERMINATING", ComputeState.TERMINATING),
            ("TERMINATED", ComputeState.TERMINATED),
            ("TERMINATED_WITH_ERRORS", ComputeState.ERROR),
            ("UNKNOWN_STATE", ComputeState.UNKNOWN),
        ],
    )
    def test_state_mapping(self, raw: str, expected: ComputeState) -> None:
        assert map_emr_state(raw) == expected


# ---------------------------------------------------------------------------
# _map_cluster
# ---------------------------------------------------------------------------


class TestMapCluster:
    def test_full_cluster_mapped_correctly(self) -> None:
        cluster = _make_cluster(num_core=4, num_task=2)
        metric = _map_cluster(cluster)

        assert metric is not None
        assert metric.compute_resource_id == "j-ABCDEF"
        assert metric.resource_name == "spark-etl"
        assert metric.num_workers == 6  # 4 CORE + 2 TASK
        assert metric.spark_version == "emr-7.0.0"
        assert metric.state == ComputeState.RUNNING
        assert metric.tags == {"env": "prod"}

    def test_master_node_excluded_from_workers(self) -> None:
        cluster = _make_cluster(num_core=0, num_task=0)
        metric = _map_cluster(cluster)
        assert metric is not None
        assert metric.num_workers == 0

    def test_missing_id_returns_none(self) -> None:
        cluster = _make_cluster()
        cluster["Id"] = ""
        assert _map_cluster(cluster) is None

    def test_name_falls_back_to_id(self) -> None:
        cluster = _make_cluster()
        cluster["Name"] = ""
        metric = _map_cluster(cluster)
        assert metric is not None
        assert metric.resource_name == "j-ABCDEF"

    def test_start_time_aware_preserved(self) -> None:
        start = datetime(2026, 3, 1, 8, 0, 0, tzinfo=timezone.utc)
        cluster = _make_cluster(created_at=start)
        metric = _map_cluster(cluster)
        assert metric is not None
        assert metric.start_time == start

    def test_naive_start_time_made_utc(self) -> None:
        cluster = _make_cluster(created_at=datetime(2026, 3, 1, 8, 0, 0))  # naive
        metric = _map_cluster(cluster)
        assert metric is not None
        assert metric.start_time is not None
        assert metric.start_time.tzinfo is not None

    def test_missing_creation_time_gives_none_start(self) -> None:
        cluster = _make_cluster()
        cluster["Status"]["Timeline"] = {}
        metric = _map_cluster(cluster)
        assert metric is not None
        assert metric.start_time is None

    def test_tags_parsed_correctly(self) -> None:
        cluster = _make_cluster(tags=[{"Key": "team", "Value": "data"}, {"Key": "cost-centre", "Value": "dc-01"}])
        metric = _map_cluster(cluster)
        assert metric is not None
        assert metric.tags == {"team": "data", "cost-centre": "dc-01"}

    def test_tag_without_key_skipped(self) -> None:
        cluster = _make_cluster(tags=[{"Value": "orphan"}])
        metric = _map_cluster(cluster)
        assert metric is not None
        assert metric.tags == {}

    def test_terminated_state_mapped(self) -> None:
        cluster = _make_cluster(state="TERMINATED")
        metric = _map_cluster(cluster)
        assert metric is not None
        assert metric.state == ComputeState.TERMINATED


# ---------------------------------------------------------------------------
# _paginate_clusters
# ---------------------------------------------------------------------------


class TestPaginateClusters:
    @pytest.mark.asyncio
    async def test_single_page_no_marker(self) -> None:
        emr = MagicMock()
        emr.list_clusters = MagicMock(return_value={"Clusters": [{"Id": "j-1"}, {"Id": "j-2"}]})

        with patch("aws_collector.collectors.emr.run_sync", new=AsyncMock(side_effect=lambda f, **kw: f(**kw))):
            summaries = await _paginate_clusters(emr)

        assert len(summaries) == 2

    @pytest.mark.asyncio
    async def test_multi_page_follows_marker(self) -> None:
        pages = [
            {"Clusters": [{"Id": "j-1"}], "Marker": "m1"},
            {"Clusters": [{"Id": "j-2"}]},
        ]
        emr = MagicMock()
        emr.list_clusters = MagicMock(side_effect=pages)

        passed_kwargs: list[dict] = []

        async def fake_run_sync(func, **kwargs):  # type: ignore[no-untyped-def]
            passed_kwargs.append(dict(kwargs))
            return func(**kwargs)

        with patch("aws_collector.collectors.emr.run_sync", new=fake_run_sync):
            summaries = await _paginate_clusters(emr)

        assert len(summaries) == 2
        assert passed_kwargs[1].get("Marker") == "m1"


# ---------------------------------------------------------------------------
# EMRCollector._collect_metrics
# ---------------------------------------------------------------------------


class TestEMRCollectorCollectMetrics:
    def _make_collector(self) -> EMRCollector:
        with patch("boto3.client"):
            return EMRCollector(source_lz_id="lz-aws-1", aws_region="eu-west-1")

    @pytest.mark.asyncio
    async def test_collects_cluster_metrics(self) -> None:
        collector = self._make_collector()
        cluster = _make_cluster()
        detail_resp = {"Cluster": cluster}

        async def fake_paginate(emr):  # type: ignore[no-untyped-def]
            return [{"Id": cluster["Id"]}]

        async def fake_run_sync(func, **kwargs):  # type: ignore[no-untyped-def]
            return detail_resp

        with (
            patch("aws_collector.collectors.emr._paginate_clusters", fake_paginate),
            patch("aws_collector.collectors.emr.run_sync", fake_run_sync),
        ):
            metrics = await collector._collect_metrics()

        assert len(metrics) == 1
        assert metrics[0]["compute_resource_id"] == "j-ABCDEF"

    @pytest.mark.asyncio
    async def test_listing_failure_raises_collection_error(self) -> None:
        from dcm_commons.exceptions import CollectionError

        collector = self._make_collector()

        async def fake_paginate(emr):  # type: ignore[no-untyped-def]
            raise RuntimeError("network error")

        with patch("aws_collector.collectors.emr._paginate_clusters", fake_paginate):
            with pytest.raises(CollectionError):
                await collector._collect_metrics()

    @pytest.mark.asyncio
    async def test_describe_failure_skips_cluster(self) -> None:
        collector = self._make_collector()

        async def fake_paginate(emr):  # type: ignore[no-untyped-def]
            return [{"Id": "j-BAD"}, {"Id": "j-GOOD"}]

        good_cluster = _make_cluster(cluster_id="j-GOOD")

        async def fake_run_sync(func, **kwargs):  # type: ignore[no-untyped-def]
            if kwargs.get("ClusterId") == "j-BAD":
                raise RuntimeError("throttled")
            return {"Cluster": good_cluster}

        with (
            patch("aws_collector.collectors.emr._paginate_clusters", fake_paginate),
            patch("aws_collector.collectors.emr.run_sync", fake_run_sync),
        ):
            metrics = await collector._collect_metrics()

        assert len(metrics) == 1
        assert metrics[0]["compute_resource_id"] == "j-GOOD"

    @pytest.mark.asyncio
    async def test_empty_cluster_id_in_summary_skipped(self) -> None:
        collector = self._make_collector()

        async def fake_paginate(emr):  # type: ignore[no-untyped-def]
            return [{"Id": ""}]  # no ID

        with patch("aws_collector.collectors.emr._paginate_clusters", fake_paginate):
            metrics = await collector._collect_metrics()

        assert metrics == []
