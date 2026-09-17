"""Azure Collector entrypoint — continuous App Service WebJob process.

The agent runs an infinite collection loop, sleeping
``collection_interval_seconds`` between cycles.  On each cycle it:

1. Instantiates all **enabled** collectors (from :envvar:`DCM_ENABLED_COLLECTORS`).
2. Runs each collector sequentially and accumulates non-empty
   :class:`~dcm_commons.models.payload.MetricPayload` objects.
3. Ships the batch to Apigee via
   :class:`~dcm_commons.clients.apigee.ApigeeClient`.

A single :class:`~dcm_commons.clients.apigee.ApigeeClient` is kept open for
the lifetime of the process so the underlying ``httpx.AsyncClient`` can reuse
HTTP/1.1 keep-alive connections and TLS sessions.

Exit behaviour
--------------
``SIGTERM`` / ``SIGINT`` (Ctrl-C) → logs a clean shutdown message and breaks
the loop after the current cycle finishes.  The App Service WebJob runtime
will restart the process automatically on exit.
"""


from __future__ import annotations

import asyncio
import os
import logging
import signal
import sys
from typing import Any

import structlog  # type: ignore[import-untyped]

from dcm_commons.auth.entra_id import EntraIDAuthClient
from dcm_commons.clients.apigee import ApigeeClient
from dcm_commons.logging_utils import configure_logging, get_logger, LogMarker, log_line

# --- Correction logger ---
configure_logging(component="dcm-azure-collector", level=os.getenv("DCM_LOG_LEVEL", "INFO"))

from azure_collector.health_server import start_app_service_health_server
from azure_collector.collectors import (
    ActivityRunCollector,
    CostManagementCollector,
    DatabaseCollector,
    DataFactoryCollector,
    DatabricksCollector,
    DatabricksPipelineCollector,
    DatabricksWorkflowCollector,
    DatabricksUserCollector,
    SecurityCenterCollector,
    StandardCheckCollector,
)
from azure_collector.config import AzureCollectorConfig, _DEFAULT_COLLECTORS, azure_credential

__all__ = ["run"]

# Module-level logger — configured lazily after configure_logging() runs.
_logger = get_logger(__name__)


def _flush_stdout() -> None:
    """Force stdout flush so App Service log stream shows milestones immediately."""
    sys.stdout.flush()

# ---------------------------------------------------------------------------
# Collector registry
# ---------------------------------------------------------------------------

# Maps the collector name (value used in DCM_ENABLED_COLLECTORS) to its class.
# Order within the dict is irrelevant — execution order follows the enabled list.
_COLLECTOR_REGISTRY: dict[str, type[Any]] = {
    "datafactory": DataFactoryCollector,
    "activity_runs": ActivityRunCollector,
    "databricks": DatabricksCollector,
    "databricks_pipelines": DatabricksPipelineCollector,
    "databricks_workflows": DatabricksWorkflowCollector,
    "users": DatabricksUserCollector,
    "cost_management": CostManagementCollector,
    "databases": DatabaseCollector,
    "security_center": SecurityCenterCollector,
    "standard_checks": StandardCheckCollector,
}

if set(_COLLECTOR_REGISTRY) != set(_DEFAULT_COLLECTORS):
    raise RuntimeError(
        "Collector registry and _DEFAULT_COLLECTORS are out of sync: "
        f"registry={sorted(_COLLECTOR_REGISTRY)}, defaults={sorted(_DEFAULT_COLLECTORS)}"
    )


# ---------------------------------------------------------------------------
# Collection cycle
# ---------------------------------------------------------------------------


async def run_collection_cycle(
    config: AzureCollectorConfig,
    credential: Any,
    apigee: ApigeeClient,
) -> None:
    """Execute one full collection cycle: collect → batch-send to Apigee.

    Each enabled collector is run sequentially.  A failure in one collector
    is logged and does not abort the cycle — the remaining collectors still
    run and their payloads are sent normally.

    Args:
        config:     Fully loaded collector configuration.
        credential: Shared ``azure.identity`` credential instance used by
                    every collector to authenticate against Azure APIs.
        apigee:     Open :class:`~dcm_commons.clients.apigee.ApigeeClient`
                    (managed by the caller, kept alive across cycles).
    """
    collector_count = len(config.enabled_collectors)
    _logger.info(
        "collection_cycle_started",
        **log_line(
            LogMarker.START,
            f"Cycle start — {collector_count} collectors: {', '.join(config.enabled_collectors)}",
            enabled=config.enabled_collectors,
            pipeline_lookback_hours=config.pipeline_lookback_hours,
        ),
    )
    _flush_stdout()

    payloads = []

    for index, name in enumerate(config.enabled_collectors, start=1):
        cls = _COLLECTOR_REGISTRY.get(name)
        if cls is None:
            _logger.warning(
                "unknown_collector_skipped",
                **log_line(LogMarker.SKIP, f"Unknown collector skipped: {name}", collector=name),
            )
            continue

        # Build constructor kwargs common to all collector classes.
        kwargs: dict[str, Any] = {
            "source_lz_id": config.source_lz_id,
            "subscription_id": config.subscription_id,
            "credential": credential,
        }
        # ADF collectors share the pipeline run lookback window.
        if name in ("datafactory", "activity_runs"):
            kwargs["lookback_hours"] = config.pipeline_lookback_hours

        collector = cls(**kwargs)

        _logger.info(
            "collector_run_starting",
            **log_line(
                LogMarker.START,
                f"[{index}/{collector_count}] {name} — collecting",
                collector=name,
                index=index,
                total=collector_count,
            ),
        )
        _flush_stdout()

        try:
            result = await collector.collect()
        except Exception as exc:
            _logger.error(
                "collector_failed",
                **log_line(
                    LogMarker.FAIL,
                    f"[{index}/{collector_count}] {name} — FAILED: {exc}",
                    collector=name,
                    index=index,
                    total=collector_count,
                    reason=str(exc),
                ),
            )
            _flush_stdout()
            continue

        if result.payload.is_empty:
            _logger.warning(
                "collector_empty_payload",
                **log_line(
                    LogMarker.WARN,
                    f"[{index}/{collector_count}] {name} — empty (0 metrics)",
                    collector=name,
                    index=index,
                    total=collector_count,
                ),
            )
            _flush_stdout()
            continue

        payloads.append(result.payload)
        domain = getattr(result.payload, "domain", "?")
        _logger.info(
            "collector_succeeded",
            **log_line(
                LogMarker.OK,
                f"[{index}/{collector_count}] {name} — {result.payload.metric_count} metrics ({domain})",
                collector=name,
                index=index,
                total=collector_count,
                metrics=result.payload.metric_count,
                duration_ms=round(result.duration_ms),
            ),
        )
        _flush_stdout()

    if not payloads:
        _logger.warning(
            "collection_cycle_no_data",
            **log_line(LogMarker.WARN, "Cycle done — nothing to send to Apigee"),
        )
        return

    # Environnement local : si DCM_LOCAL_DEV=1, enregistrer les payloads en local, sinon comportement normal
    import os
    if os.getenv("DCM_LOCAL_DEV", "0") == "1":
        import json
        _logger.warning(
            "local_dev_mode",
            msg="DCM_LOCAL_DEV=1 : skipping send_batch, saving payloads to local file",
            payloads=[json.loads(p.to_ingest_json()) for p in payloads],
        )
        print("[LOCAL DEV] Payloads enregistrés dans payloads_local_test.json")
        with open("payloads_local_test.json", "w", encoding="utf-8") as f:
            json.dump(
                [json.loads(p.to_ingest_json()) for p in payloads],
                f,
                ensure_ascii=False,
                indent=2,
            )
        return

    payloads_summary = [
        {
            "domain": getattr(p, "domain", None),
            "metric_count": getattr(p, "metric_count", None),
            "collection_run_id": getattr(p, "collection_run_id", None),
        }
        for p in payloads
    ]
    summary_parts = [
        f"{s.get('domain') or '?'}:{s.get('metric_count') or 0}" for s in payloads_summary
    ]
    _logger.info(
        "apigee_send_batch_start",
        **log_line(
            LogMarker.INGEST,
            f"Apigee ingest — {len(payloads)} payload(s) [{', '.join(summary_parts)}]",
            total_payloads=len(payloads),
            payloads_summary=payloads_summary,
        ),
    )

    try:
        send_results = await apigee.send_batch(payloads)
        _logger.info(
            "apigee_send_batch_success",
            **log_line(
                LogMarker.OK,
                f"Apigee OK — {send_results['success']}/{len(payloads)} delivered",
                sent_success=send_results["success"],
                sent_failure=send_results["failure"],
                total_payloads=len(payloads),
            ),
        )
    except Exception as exc:
        _logger.error(
            "apigee_send_batch_failed",
            **log_line(
                LogMarker.FAIL,
                f"Apigee FAILED — {exc}",
                error=str(exc),
                total_payloads=len(payloads),
            ),
        )
        raise

    _logger.info(
        "collection_cycle_done",
        **log_line(
            LogMarker.OK,
            f"Cycle done — sent {send_results['success']}/{len(payloads)} payload(s)",
            sent_success=send_results["success"],
            sent_failure=send_results["failure"],
            total_payloads=len(payloads),
        ),
    )


# ---------------------------------------------------------------------------
# Main async loop
# ---------------------------------------------------------------------------


async def _run_loop(config: AzureCollectorConfig) -> None:
    """Run the infinite collection loop with graceful signal handling.

    Registers ``SIGTERM`` and ``SIGINT`` handlers via
    ``asyncio.get_event_loop().add_signal_handler()`` (the correct asyncio
    pattern — avoids thread-safety issues with ``signal.signal()``).

    Args:
        config: Fully loaded :class:`AzureCollectorConfig`.
    """
    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def _request_shutdown() -> None:
        _logger.info("shutdown_requested")
        stop_event.set()

    # SIGTERM is sent by the App Service WebJob runtime on graceful shutdown.
    # SIGINT handles interactive Ctrl-C during local development.   
    # add_signal_handler is Unix-only; fall back to signal.signal on Windows.
    if sys.platform == "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda s, f: _request_shutdown())
    else:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _request_shutdown)

    credential: Any = azure_credential()


    def anonymize(value: str | None) -> str:
        if value is None:
            return "null"
        return value[:2] + "*" * max(0, len(value) - 2)

    secrets = ["DCM_ENTRA_CLIENT_SECRET", "DCM_APIGEE_API_KEY" ]
    # Log structuré de toutes les variables d'environnement DCM_ENTRA_* et DCM_APIGEE_*
    env_vars = {k: (v if not k in secrets else anonymize(v)) for k, v in os.environ.items() if k.startswith("DCM_ENTRA_") or k.startswith("DCM_APIGEE_")}
    _logger.info("env_vars_used", **env_vars)

    # Log détaillé des infos d'auth utilisées pour ApigeeClient
    _logger.info(
        "apigee_auth_config",
        entra_tenant_id=config.entra_tenant_id,
        entra_client_id=config.entra_client_id,
        entra_client_secret=anonymize(config.entra_client_secret),
        entra_scope=config.entra_scope,
        apigee_base_url=config.apigee_base_url,
        apigee_api_key=anonymize(config.apigee_api_key),
    )

    _logger.info("entra_auth_client_creating")
    _flush_stdout()
    auth_client = EntraIDAuthClient(
        tenant_id=config.entra_tenant_id,
        client_id=config.entra_client_id,
        client_secret=config.entra_client_secret,
        scope=config.entra_scope,
    )
    _logger.info("entra_auth_client_created")
    _flush_stdout()

    _logger.info("entra_token_warmup_starting", scope=config.entra_scope)
    _flush_stdout()
    await asyncio.to_thread(auth_client.get_token)
    _logger.info("entra_token_warmup_succeeded", scope=config.entra_scope)
    _flush_stdout()

    _logger.info(
        "agent_started",
        subscription_id=config.subscription_id,
        source_lz_id=config.source_lz_id,
        interval_seconds=config.collection_interval_seconds,
        collectors=config.enabled_collectors,
        pipeline_lookback_hours=config.pipeline_lookback_hours,
    )
    _flush_stdout()

    if os.getenv("DCM_LOG_LEVEL", "INFO").upper() != "DEBUG":
        # silence requests library logs below WARNING to reduce noise, since httpx is used for all Apigee calls
        request_logger = logging.getLogger("azure.core.pipeline.policies.http_logging_policy")
        request_logger.setLevel(logging.WARNING)

    # Keep a single ApigeeClient open for the process lifetime — connection
    # pooling and TLS session reuse significantly reduce per-cycle latency.
    _logger.info("apigee_client_entering", base_url=config.apigee_base_url)
    _flush_stdout()
    async with ApigeeClient(
        apigee_base_url=config.apigee_base_url,
        auth_client=auth_client,
        api_key=config.apigee_api_key,
    ) as apigee:
        _logger.info("apigee_client_ready")
        _flush_stdout()
        while not stop_event.is_set():
            try:
                await run_collection_cycle(config, credential, apigee)
            except Exception as exc:
                # Catch-all for unexpected errors in the cycle orchestration
                # itself (not individual collectors, which are caught inside).
                _logger.error("collection_cycle_unhandled_error", reason=str(exc))

            # Sleep for the configured interval, but wake up immediately if a
            # shutdown signal arrives.
            _logger.info(
                "collection_cycle_sleeping",
                **log_line(
                    LogMarker.SLEEP,
                    f"Sleep {config.collection_interval_seconds}s until next cycle",
                    interval_seconds=config.collection_interval_seconds,
                ),
            )
            _flush_stdout()
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=float(config.collection_interval_seconds),
                )
            except asyncio.TimeoutError:
                _logger.info(
                    "collection_cycle_sleep_done",
                    **log_line(LogMarker.START, "Sleep done — next cycle"),
                )
                _flush_stdout()

    _logger.info("agent_stopped")


async def _run_once(config: AzureCollectorConfig) -> None:
    """Run a single collection cycle then exit (local dev / CI smoke test)."""
    credential: Any = azure_credential()
    auth_client = EntraIDAuthClient(
        tenant_id=config.entra_tenant_id,
        client_id=config.entra_client_id,
        client_secret=config.entra_client_secret,
        scope=config.entra_scope,
    )
    _logger.info(
        "agent_started_once",
        subscription_id=config.subscription_id,
        source_lz_id=config.source_lz_id,
        collectors=config.enabled_collectors,
        pipeline_lookback_hours=config.pipeline_lookback_hours,
    )
    if os.getenv("DCM_LOG_LEVEL", "INFO").upper() != "DEBUG":
        request_logger = logging.getLogger(
            "azure.core.pipeline.policies.http_logging_policy"
        )
        request_logger.setLevel(logging.WARNING)
    async with ApigeeClient(
        apigee_base_url=config.apigee_base_url,
        auth_client=auth_client,
        api_key=config.apigee_api_key,
    ) as apigee:
        await run_collection_cycle(config, credential, apigee)
    _logger.info("agent_stopped_once")


# ---------------------------------------------------------------------------
# Synchronous entrypoint
# ---------------------------------------------------------------------------


def run(*, once: bool = False) -> None:
    """Synchronous entrypoint invoked by the ``dcm-azure-collector`` script.

    1. Configures structured logging (JSON in App Service, colored console
       locally).
    2. Loads configuration from environment variables and Azure Key Vault.
    3. Starts the async collection loop.

    Raises:
        SystemExit: With exit code ``1`` if configuration loading fails, so
                    the App Service WebJob runtime records a failed start.
    """
    configure_logging(
        component="dcm-azure-collector",
        level=os.getenv("DCM_LOG_LEVEL", "INFO"),
    )

    try:
        config = AzureCollectorConfig.from_env_and_keyvault()
        start_app_service_health_server()
    except Exception as exc:
        # structlog may not be fully initialised yet if the import itself
        # failed, so fall back to stderr.
        print(f"[FATAL] Configuration error — cannot start agent: {exc}", file=sys.stderr)
        _logger.error("agent_stopped", exc_info=exc)

        sys.exit(1)

    if once:
        asyncio.run(_run_once(config))
    else:
        asyncio.run(_run_loop(config))


if __name__ == "__main__":
    run(once="--once" in sys.argv)
