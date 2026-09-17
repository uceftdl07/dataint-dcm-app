"""AWS Glue collector — job runs and crawler executions.

Enumerates all AWS Glue jobs and crawlers in the account/region and
collects their most recent execution status.

Key API calls
-------------
``glue.get_jobs(NextToken=...)``
    Paginated list of all Glue job definitions.
``glue.get_job_runs(JobName, MaxResults=20)``
    The 20 most recent runs for a single Glue job.
``glue.get_crawlers(NextToken=...)``
    Paginated list of all Glue crawlers with their last-crawl status.

Lakebase target
---------------
``dcm.monitoring.pipeline_runs``
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dcm_commons.collectors.base import BaseCollector
from dcm_commons.exceptions import CollectionError
from dcm_commons.logging_utils import get_logger
from dcm_commons.models.enums import CloudProvider, MetricDomain, TriggerType
from dcm_commons.models.pipeline import PipelineMetric

from aws_collector._aws_utils import (
    create_aws_client,
    map_glue_crawler_status,
    map_glue_job_status,
    run_sync,
)

__all__ = ["GlueCollector"]

_logger = get_logger(__name__)

# Maximum recent runs to retrieve per job (avoids fetching unlimited history).
_MAX_RUNS_PER_JOB: int = 20


class GlueCollector(BaseCollector):
    """Collects AWS Glue job run and crawler execution metrics.

    For each Glue job, retrieves the ``_MAX_RUNS_PER_JOB`` most recent
    runs and maps them to :class:`~dcm_commons.models.pipeline.PipelineMetric`.
    For each crawler, the last-crawl result is mapped to a pipeline-style
    metric so that crawler failures appear alongside job failures in the
    monitoring dashboard.

    Args:
        source_lz_id: Landing zone identifier.
        aws_region:   AWS region (e.g. ``"eu-west-1"``).
        max_retries:  Retry attempts on transient failures.
        retry_base_delay_seconds: Base delay for exponential back-off.
    """

    def __init__(
        self,
        source_lz_id: str,
        aws_region: str,
        *,
        subscription_or_account_id: str | None = None,
        max_retries: int = 3,
        retry_base_delay_seconds: float = 2.0,
    ) -> None:
        super().__init__(
            source_lz_id=source_lz_id,
            cloud_provider=CloudProvider.AWS,
            subscription_or_account_id=subscription_or_account_id,
            max_retries=max_retries,
            retry_base_delay_seconds=retry_base_delay_seconds,
        )
        self._glue = create_aws_client("glue", region_name=aws_region)

    @property
    def domain(self) -> MetricDomain:
        """Return the pipeline metric domain."""
        return MetricDomain.PIPELINE

    async def _collect_metrics(self) -> list[dict[str, Any]]:
        """Collect recent Glue job runs and crawler last-crawl results.

        Returns:
            List of :class:`~dcm_commons.models.pipeline.PipelineMetric` dicts.

        Raises:
            CollectionError: If the top-level job or crawler listing fails.
        """
        metrics: list[dict[str, Any]] = []

        job_metrics = await self._collect_job_runs()
        metrics.extend(job_metrics)

        crawler_metrics = await self._collect_crawlers()
        metrics.extend(crawler_metrics)

        _logger.info(
            "glue_collection_done",
            job_run_count=len(job_metrics),
            crawler_count=len(crawler_metrics),
        )
        return metrics

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _collect_job_runs(self) -> list[dict[str, Any]]:
        """List all Glue jobs and collect their most recent runs.

        Returns:
            List of serialised :class:`PipelineMetric` dicts for job runs.

        Raises:
            CollectionError: If the initial ``get_jobs`` pagination fails.
        """
        try:
            jobs = await _paginate_glue_jobs(self._glue)
        except Exception as exc:
            raise CollectionError(
                "GlueCollector",
                f"Failed to list Glue jobs: {exc}",
            ) from exc

        _logger.debug("glue_jobs_found", count=len(jobs))
        metrics: list[dict[str, Any]] = []

        for job in jobs:
            job_name: str = job.get("Name", "")
            if not job_name:
                continue

            try:
                runs = await run_sync(
                    self._glue.get_job_runs,
                    JobName=job_name,
                    MaxResults=_MAX_RUNS_PER_JOB,
                )
            except Exception as exc:
                _logger.warning(
                    "glue_job_runs_failed",
                    job=job_name,
                    reason=str(exc),
                )
                continue

            for run in runs.get("JobRuns", []):
                metric = _map_job_run(run, job_name=job_name)
                if metric is not None:
                    metrics.append(metric.model_dump())

        return metrics

    async def _collect_crawlers(self) -> list[dict[str, Any]]:
        """List all Glue crawlers and record their last-crawl status.

        Crawlers with no prior run (``LastCrawl`` absent) are skipped.

        Returns:
            List of serialised :class:`PipelineMetric` dicts for crawlers.
        """
        try:
            crawlers = await _paginate_glue_crawlers(self._glue)
        except Exception as exc:
            _logger.warning("glue_crawlers_list_failed", reason=str(exc))
            return []

        _logger.debug("glue_crawlers_found", count=len(crawlers))
        metrics: list[dict[str, Any]] = []

        for crawler in crawlers:
            metric = _map_crawler(crawler)
            if metric is not None:
                metrics.append(metric.model_dump())

        return metrics


# ---------------------------------------------------------------------------
# Pagination helpers
# ---------------------------------------------------------------------------


async def _paginate_glue_jobs(glue: Any) -> list[dict[str, Any]]:
    """Paginate through all Glue jobs using ``NextToken``.

    Args:
        glue: boto3 Glue client.

    Returns:
        Flat list of all job definition dicts.
    """
    jobs: list[dict[str, Any]] = []
    next_token: str | None = None

    while True:
        kwargs: dict[str, Any] = {}
        if next_token:
            kwargs["NextToken"] = next_token

        response = await run_sync(glue.get_jobs, **kwargs)
        jobs.extend(response.get("Jobs", []))

        next_token = response.get("NextToken")
        if not next_token:
            break

    return jobs


async def _paginate_glue_crawlers(glue: Any) -> list[dict[str, Any]]:
    """Paginate through all Glue crawlers using ``NextToken``.

    Args:
        glue: boto3 Glue client.

    Returns:
        Flat list of all crawler dicts.
    """
    crawlers: list[dict[str, Any]] = []
    next_token: str | None = None

    while True:
        kwargs: dict[str, Any] = {}
        if next_token:
            kwargs["NextToken"] = next_token

        response = await run_sync(glue.get_crawlers, **kwargs)
        crawlers.extend(response.get("Crawlers", []))

        next_token = response.get("NextToken")
        if not next_token:
            break

    return crawlers


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


def _map_job_run(
    run: dict[str, Any],
    job_name: str,
) -> PipelineMetric | None:
    """Map a Glue job run dict to a :class:`PipelineMetric`.

    Args:
        run:      Raw job run dict from ``get_job_runs``.
        job_name: Name of the parent Glue job.

    Returns:
        A :class:`PipelineMetric`, or ``None`` if the run lacks a run ID.
    """
    run_id: str = run.get("Id", "")
    if not run_id:
        return None

    start_time: datetime | None = run.get("StartedOn")
    if start_time is None:
        return None
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)

    end_time: datetime | None = run.get("CompletedOn")
    if end_time is not None and end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=timezone.utc)

    # ExecutionTime is in seconds (integer).
    exec_time_s = run.get("ExecutionTime")
    duration_seconds: float | None = float(exec_time_s) if exec_time_s is not None else None

    error_message: str | None = run.get("ErrorMessage") or None

    return PipelineMetric(
        pipeline_id=f"glue/jobs/{job_name}",
        pipeline_name=job_name,
        run_id=run_id,
        status=map_glue_job_status(run.get("JobRunState")),
        trigger_type=TriggerType.SCHEDULED,  # Glue jobs run on schedule or trigger
        start_time=start_time,
        end_time=end_time,
        duration_seconds=duration_seconds,
        error_message=error_message,
    )


def _map_crawler(crawler: dict[str, Any]) -> PipelineMetric | None:
    """Map a Glue crawler dict to a :class:`PipelineMetric`.

    Uses the ``LastCrawl`` field as the most recent execution result.

    Args:
        crawler: Raw crawler dict from ``get_crawlers``.

    Returns:
        A :class:`PipelineMetric`, or ``None`` if the crawler has no prior run.
    """
    crawler_name: str = crawler.get("Name", "")
    last_crawl: dict[str, Any] = crawler.get("LastCrawl", {})
    if not crawler_name or not last_crawl:
        return None

    start_time: datetime | None = last_crawl.get("StartTime")
    if start_time is None:
        return None
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)

    error_message: str | None = last_crawl.get("ErrorMessage") or None

    # Crawlers don't have a per-run UUID — use name + start time as surrogate ID.
    run_id = f"{crawler_name}/{start_time.isoformat()}"

    return PipelineMetric(
        pipeline_id=f"glue/crawlers/{crawler_name}",
        pipeline_name=f"[crawler] {crawler_name}",
        run_id=run_id,
        status=map_glue_crawler_status(last_crawl.get("Status")),
        trigger_type=TriggerType.SCHEDULED,
        start_time=start_time,
        end_time=None,
        duration_seconds=None,
        error_message=error_message,
    )
