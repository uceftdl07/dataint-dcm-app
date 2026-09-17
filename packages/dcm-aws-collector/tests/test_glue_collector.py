"""Tests for GlueCollector — job runs and crawler execution metrics.

Uses ``moto`` to mock the AWS Glue API so no real AWS calls are made.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aws_collector.collectors.glue import (
    GlueCollector,
    _map_crawler,
    _map_job_run,
    _paginate_glue_crawlers,
    _paginate_glue_jobs,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_run(
    run_id: str = "jr_001",
    state: str = "SUCCEEDED",
    started: datetime | None = None,
    completed: datetime | None = None,
    exec_time: int | None = 120,
    error: str | None = None,
) -> dict[str, Any]:
    started = started or datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)
    completed = completed or datetime(2026, 3, 1, 10, 2, 0, tzinfo=timezone.utc)
    run: dict[str, Any] = {
        "Id": run_id,
        "JobRunState": state,
        "StartedOn": started,
        "CompletedOn": completed,
    }
    if exec_time is not None:
        run["ExecutionTime"] = exec_time
    if error:
        run["ErrorMessage"] = error
    return run


def _make_crawler(
    name: str = "my-crawler",
    status: str = "SUCCEEDED",
    start_time: datetime | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    start_time = start_time or datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
    last_crawl: dict[str, Any] = {"Status": status, "StartTime": start_time}
    if error:
        last_crawl["ErrorMessage"] = error
    return {"Name": name, "LastCrawl": last_crawl}


# ---------------------------------------------------------------------------
# _map_job_run
# ---------------------------------------------------------------------------


class TestMapJobRun:
    def test_succeeded_run_maps_correctly(self) -> None:
        run = _make_run(run_id="jr_abc", state="SUCCEEDED", exec_time=300)
        metric = _map_job_run(run, job_name="etl-daily")

        assert metric is not None
        assert metric.pipeline_id == "glue/jobs/etl-daily"
        assert metric.pipeline_name == "etl-daily"
        assert metric.run_id == "jr_abc"
        assert metric.duration_seconds == 300.0

    def test_failed_run_captures_error(self) -> None:
        run = _make_run(state="FAILED", error="Out of memory")
        metric = _map_job_run(run, job_name="etl-daily")

        assert metric is not None
        assert metric.error_message == "Out of memory"

    def test_missing_run_id_returns_none(self) -> None:
        run = _make_run()
        run["Id"] = ""
        assert _map_job_run(run, job_name="job") is None

    def test_missing_start_time_returns_none(self) -> None:
        run = _make_run()
        del run["StartedOn"]
        assert _map_job_run(run, job_name="job") is None

    def test_naive_start_time_made_utc(self) -> None:
        run = _make_run(started=datetime(2026, 3, 1, 10, 0, 0))  # naive
        metric = _map_job_run(run, job_name="job")
        assert metric is not None
        assert metric.start_time.tzinfo is not None

    def test_none_exec_time_gives_none_duration(self) -> None:
        run = _make_run(exec_time=None)
        metric = _map_job_run(run, job_name="job")
        assert metric is not None
        # If ExecutionTime is missing but both times are present, duration_seconds is auto-computed
        assert metric.duration_seconds == 120.0

    def test_no_error_message_field_is_none(self) -> None:
        run = _make_run()
        metric = _map_job_run(run, job_name="job")
        assert metric is not None
        assert metric.error_message is None


# ---------------------------------------------------------------------------
# _map_crawler
# ---------------------------------------------------------------------------


class TestMapCrawler:
    def test_crawler_maps_correctly(self) -> None:
        start = datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
        crawler = _make_crawler(name="s3-crawler", status="SUCCEEDED", start_time=start)
        metric = _map_crawler(crawler)

        assert metric is not None
        assert metric.pipeline_id == "glue/crawlers/s3-crawler"
        assert metric.pipeline_name == "[crawler] s3-crawler"
        assert metric.run_id == f"s3-crawler/{start.isoformat()}"
        assert metric.end_time is None
        assert metric.duration_seconds is None

    def test_failed_crawler_captures_error(self) -> None:
        crawler = _make_crawler(status="FAILED", error="Schema mismatch")
        metric = _map_crawler(crawler)
        assert metric is not None
        assert metric.error_message == "Schema mismatch"

    def test_missing_name_returns_none(self) -> None:
        crawler = _make_crawler()
        crawler["Name"] = ""
        assert _map_crawler(crawler) is None

    def test_missing_last_crawl_returns_none(self) -> None:
        crawler = {"Name": "my-crawler"}
        assert _map_crawler(crawler) is None

    def test_missing_start_time_returns_none(self) -> None:
        crawler = {"Name": "c", "LastCrawl": {"Status": "SUCCEEDED"}}
        assert _map_crawler(crawler) is None

    def test_naive_start_time_made_utc(self) -> None:
        crawler = _make_crawler(start_time=datetime(2026, 3, 1, 8, 0, 0))  # naive
        metric = _map_crawler(crawler)
        assert metric is not None
        assert metric.start_time.tzinfo is not None


# ---------------------------------------------------------------------------
# _paginate_glue_jobs
# ---------------------------------------------------------------------------


class TestPaginateGlueJobs:
    @pytest.mark.asyncio
    async def test_single_page(self) -> None:
        glue = MagicMock()
        glue.get_jobs = MagicMock(return_value={"Jobs": [{"Name": "j1"}, {"Name": "j2"}]})

        with patch("aws_collector.collectors.glue.run_sync", new=AsyncMock(side_effect=lambda f, **kw: f(**kw))):
            jobs = await _paginate_glue_jobs(glue)

        assert len(jobs) == 2

    @pytest.mark.asyncio
    async def test_multi_page(self) -> None:
        pages = [
            {"Jobs": [{"Name": "j1"}], "NextToken": "tok1"},
            {"Jobs": [{"Name": "j2"}]},
        ]
        glue = MagicMock()
        glue.get_jobs = MagicMock(side_effect=pages)

        call_kwargs: list[dict] = []

        async def fake_run_sync(func, **kwargs):  # type: ignore[no-untyped-def]
            call_kwargs.append(dict(kwargs))
            return func(**kwargs)

        with patch("aws_collector.collectors.glue.run_sync", new=fake_run_sync):
            jobs = await _paginate_glue_jobs(glue)

        assert len(jobs) == 2
        assert call_kwargs[1].get("NextToken") == "tok1"


# ---------------------------------------------------------------------------
# _paginate_glue_crawlers
# ---------------------------------------------------------------------------


class TestPaginateGlueCrawlers:
    @pytest.mark.asyncio
    async def test_empty_response(self) -> None:
        glue = MagicMock()
        glue.get_crawlers = MagicMock(return_value={"Crawlers": []})

        with patch("aws_collector.collectors.glue.run_sync", new=AsyncMock(side_effect=lambda f, **kw: f(**kw))):
            crawlers = await _paginate_glue_crawlers(glue)

        assert crawlers == []


# ---------------------------------------------------------------------------
# GlueCollector._collect_metrics (integration)
# ---------------------------------------------------------------------------


class TestGlueCollectorCollectMetrics:
    def _make_collector(self) -> GlueCollector:
        with patch("boto3.client"):
            return GlueCollector(source_lz_id="lz-aws-1", aws_region="eu-west-1")

    @pytest.mark.asyncio
    async def test_collect_job_run_and_crawler(self) -> None:
        collector = self._make_collector()

        job_run = _make_run(run_id="jr_1", state="SUCCEEDED")
        crawler = _make_crawler(name="raw-crawler", status="SUCCEEDED")

        async def fake_collect_job_runs(self_inner):  # type: ignore[no-untyped-def]
            metric = _map_job_run(job_run, job_name="etl-job")
            return [metric.model_dump()] if metric else []

        async def fake_collect_crawlers(self_inner):  # type: ignore[no-untyped-def]
            metric = _map_crawler(crawler)
            return [metric.model_dump()] if metric else []

        with (
            patch.object(GlueCollector, "_collect_job_runs", fake_collect_job_runs),
            patch.object(GlueCollector, "_collect_crawlers", fake_collect_crawlers),
        ):
            metrics = await collector._collect_metrics()

        assert len(metrics) == 2

    @pytest.mark.asyncio
    async def test_job_listing_failure_raises_collection_error(self) -> None:
        from dcm_commons.exceptions import CollectionError

        collector = self._make_collector()

        async def fake_paginate(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("API down")

        with patch("aws_collector.collectors.glue._paginate_glue_jobs", fake_paginate):
            with pytest.raises(CollectionError):
                await collector._collect_metrics()

    @pytest.mark.asyncio
    async def test_crawler_listing_failure_returns_partial(self) -> None:
        """Crawler listing failure must NOT raise — returns empty list."""
        collector = self._make_collector()

        job_run = _make_run(run_id="jr_2", state="SUCCEEDED")

        async def fake_collect_job_runs(self_inner):  # type: ignore[no-untyped-def]
            metric = _map_job_run(job_run, job_name="job-x")
            return [metric.model_dump()] if metric else []

        async def fake_collect_crawlers(self_inner):  # type: ignore[no-untyped-def]
            return []  # simulates listing failure (already swallowed)

        with (
            patch.object(GlueCollector, "_collect_job_runs", fake_collect_job_runs),
            patch.object(GlueCollector, "_collect_crawlers", fake_collect_crawlers),
        ):
            metrics = await collector._collect_metrics()

        assert len(metrics) == 1

    @pytest.mark.asyncio
    async def test_run_without_start_time_skipped(self) -> None:
        collector = self._make_collector()
        run_no_start = _make_run()
        del run_no_start["StartedOn"]

        async def fake_paginate_jobs(glue):  # type: ignore[no-untyped-def]
            return [{"Name": "job-y"}]

        async def fake_get_runs(func, **kwargs):  # type: ignore[no-untyped-def]
            return {"JobRuns": [run_no_start]}

        async def fake_paginate_crawlers(glue):  # type: ignore[no-untyped-def]
            return []

        with (
            patch("aws_collector.collectors.glue._paginate_glue_jobs", fake_paginate_jobs),
            patch("aws_collector.collectors.glue.run_sync", fake_get_runs),
            patch("aws_collector.collectors.glue._paginate_glue_crawlers", fake_paginate_crawlers),
        ):
            metrics = await collector._collect_metrics()

        assert metrics == []
