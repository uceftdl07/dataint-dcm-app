"""AWS Collector entrypoint — one-shot ECS Fargate task.

Execution model
---------------
This agent runs as a **one-shot** ECS Fargate task invoked every 5 minutes by
an EventBridge Scheduler rule.  It collects metrics from all enabled AWS
services, forwards the payloads to the DCM ingestion API (Apigee), and exits
with code 0 on success or 1 on fatal error.

Environment variables
---------------------
DCM_SECRET_NAME
    Name of the AWS Secrets Manager secret that holds Entra ID credentials
    and the Apigee API key (required).
DCM_SOURCE_LZ_ID
    Identifier of the Landing Zone being monitored (required).
DCM_AWS_REGION
    AWS region of the monitored account (required).
DCM_APIGEE_BASE_URL
    Base URL of the Apigee proxy endpoint (required).
DCM_ENABLED_COLLECTORS
    Comma-separated list of collector names to activate.  Defaults to all
    five: ``glue,emr,rds,cost_explorer,redshift``.
DCM_COST_LOOKBACK_DAYS
    Number of days of cost history for :class:`CostExplorerCollector`
    (default: ``30``).
DCM_LOG_LEVEL
    Logging level (default: ``INFO``).
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

from dcm_commons.clients.apigee import ApigeeClient
from dcm_commons.auth.entra_id import EntraIDAuthClient
from dcm_commons.logging_utils import configure_logging, get_logger
from dcm_commons.models.payload import MetricPayload

from aws_collector.collectors import (
    CostExplorerCollector,
    EMRCollector,
    GlueCollector,
    RDSCollector,
    RedshiftCollector,
)
from aws_collector.config import AWSCollectorConfig

__all__ = ["run", "run_collection"]

_logger = get_logger(__name__)


def anonymize(value: str | None) -> str:
    if value is None:
        return "null"
    return value[:2] + "*" * max(0, len(value) - 2)

# ---------------------------------------------------------------------------
# Collector registry
# ---------------------------------------------------------------------------

_COLLECTOR_MAP: dict[str, type] = {
    "glue": GlueCollector,
    "emr": EMRCollector,
    "rds": RDSCollector,
    "cost_explorer": CostExplorerCollector,
    "redshift": RedshiftCollector,
}


# ---------------------------------------------------------------------------
# Async collection cycle
# ---------------------------------------------------------------------------


async def run_collection(config: AWSCollectorConfig) -> None:
    """Execute one collection cycle across all enabled collectors.

    Iterates over every collector listed in ``config.enabled_collectors``,
    invokes :meth:`~dcm_commons.collectors.base.BaseCollector.collect`, and
    accumulates non-empty payloads.  The batch is forwarded to the Apigee
    proxy in a single call at the end of the cycle.

    Per-collector failures are logged and skipped so that one broken service
    cannot prevent the others from being collected.

    Args:
        config: Runtime configuration loaded from Secrets Manager.
    """
    auth_kwargs: dict[str, Any] = {
        "tenant_id": config.entra_tenant_id,
        "client_id": config.entra_client_id,
        "client_secret": config.entra_client_secret,
        "scope": config.entra_scope,
    }
    _logger.info(f"ApigeeClient initialized with base URL: {config.apigee_base_url}  ")
    _logger.info(f"ApigeeClient initialized with tenant_id: {config.entra_tenant_id}  ")
    _logger.info(f"ApigeeClient initialized with entra_client_secret: {anonymize(config.entra_client_secret)}  ")
    _logger.info(f"ApigeeClient initialized with client_id: {config.entra_client_id}  ")
    _logger.info(f"ApigeeClient initialized with entra_scope: {config.entra_scope}  ")
    _logger.info(f"ApigeeClient initialized with apigee_api_key: {anonymize(config.apigee_api_key)}  ")

    account_id = await _resolve_aws_account_id(config.aws_region)
    _logger.info("aws_account_id_resolved", account_id=account_id or "(empty)")

    async with ApigeeClient(
        apigee_base_url=config.apigee_base_url,
        api_key=config.apigee_api_key,
        auth_client=EntraIDAuthClient(**auth_kwargs),
    ) as apigee:
        payloads: list[MetricPayload] = []

        for name in config.enabled_collectors:
            cls = _COLLECTOR_MAP.get(name)
            if cls is None:
                _logger.warning("aws_collector_unknown", collector=name)
                continue

            # Build kwargs specific to each collector type.
            kwargs: dict[str, Any] = {
                "source_lz_id": config.source_lz_id,
                "aws_region": config.aws_region,
                "subscription_or_account_id": account_id or None,
            }
            if name == "cost_explorer":
                kwargs["lookback_days"] = config.cost_lookback_days

            collector = cls(**kwargs)

            try:
                result = await collector.collect()
            except Exception as exc:  # noqa: BLE001
                _logger.error(
                    "aws_collector_failed",
                    collector=name,
                    reason=str(exc),
                )
                continue

            if result.payload.is_empty:
                _logger.debug("aws_collector_empty", collector=name)
                continue

            _logger.info(
                "aws_collector_success",
                collector=name,
                metric_count=result.payload.metric_count,
                duration_ms=result.duration_ms,
                source_lz_id=result.payload.source_lz_id,
                domain=result.payload.domain,
                cloud_provider=result.payload.cloud_provider,
            )
            payloads.append(result.payload)

        if not payloads:
            _logger.info("aws_collection_nothing_to_send")
            return

        counts = await apigee.send_batch(payloads)
        _logger.info(
            "aws_batch_sent",
            payloads_total=len(payloads),
            success=counts.get("success", 0),
            failure=counts.get("failure", 0),
        )


async def _resolve_aws_account_id(aws_region: str) -> str:
    """Best-effort STS account id for MetricPayload.subscription_or_account_id."""
    try:
        from aws_collector._aws_utils import create_aws_client, run_sync

        sts = create_aws_client("sts", region_name=aws_region)
        identity = await run_sync(sts.get_caller_identity)
        return str(identity.get("Account") or "")
    except Exception as exc:  # noqa: BLE001
        _logger.warning("aws_account_id_resolve_failed", reason=str(exc))
        return ""


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def run() -> None:
    """Synchronous entrypoint called by the ECS task command.

    1. Initialises structured logging.
    2. Loads configuration from Secrets Manager.
    3. Runs the async collection cycle.
    4. Exits with code 0 on success or 1 on unhandled error.
    """
    configure_logging(
        component="dcm-aws-collector",
        level=os.getenv("DCM_LOG_LEVEL", "INFO"),
    )

    _logger.info("aws_collector_starting")
    _logger.debug("aws_collector_starting")

    try:
        config = AWSCollectorConfig.from_secrets_manager()
    except Exception as exc:  # noqa: BLE001
        _logger.critical("aws_collector_config_failed", reason=str(exc))
        sys.exit(1)

    _logger.info(
        "aws_collector_config_loaded",
        source_lz_id=config.source_lz_id,
        aws_region=config.aws_region,
        enabled_collectors=config.enabled_collectors,
    )

    try:
        asyncio.run(run_collection(config))
    except Exception as exc:  # noqa: BLE001
        _logger.critical("aws_collector_unhandled_error", reason=str(exc))
        sys.exit(1)

    _logger.info("aws_collector_done")
    # ECS task terminates naturally — exit 0 implicit.


if __name__ == "__main__":
    run()
