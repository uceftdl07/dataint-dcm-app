"""Structured logging utilities for all DCM components.

Every DCM component (agents, Lambda, backend) must call ``configure_logging()``
once at startup, then use ``get_logger(__name__)`` to obtain module-level loggers.

Log schema (JSON in production)::

    {
        "timestamp":         "2026-03-18T10:30:00.123456Z",
        "level":             "info",
        "logger":            "dcm_azure_collector.collectors.datafactory",
        "event":             "collection_completed",
        "component":         "dcm-azure-collector",
        "collection_run_id": "3f4a1b2c-...",
        "cloud_provider":    "azure",
        "domain":            "pipeline",
        "metrics_count":     42,
        "duration_ms":       1230
    }

Output format is auto-detected:

- **Production** (non-TTY or ``DCM_ENV=production``): JSON, one record per line,
  compatible with CloudWatch Logs Insights and Azure Log Analytics queries.
- **Development** (TTY): human-readable colored console output via structlog.

Correlation IDs:

Use ``bind_contextvars()`` to attach fields that should appear in every
subsequent log record within the current async context (e.g. ``collection_run_id``)::

    from dcm_commons.logging_utils import bind_contextvars, clear_contextvars

    bind_contextvars(collection_run_id=run_id, cloud_provider="azure")
    logger.info("collection_started")      # includes run_id automatically
    clear_contextvars()                    # clean up after the request/task
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable
from typing import Any

import structlog

__all__ = [
    "LogMarker",
    "configure_logging",
    "get_logger",
    "bind_contextvars",
    "clear_contextvars",
    "log_line",
]

# Re-export structlog helpers so callers only need to import from this module.
bind_contextvars = structlog.contextvars.bind_contextvars
clear_contextvars = structlog.contextvars.clear_contextvars


class LogMarker:
    """ASCII markers for quick scanning in Azure Log stream / App Insights."""

    START = ">>"
    OK = "OK"
    WARN = "!!"
    FAIL = "XX"
    SKIP = "--"
    SLEEP = "zz"
    INGEST = "->"


def log_line(marker: str, summary: str, **fields: Any) -> dict[str, Any]:
    """Attach ``marker`` + one-line ``summary`` to a structured log record.

    Example::

        logger.info("collector_succeeded", **log_line(
            LogMarker.OK, "[2/4] cost: 26 metrics", collector="cost_management",
        ))
    """
    return {"marker": marker, "summary": summary, **fields}


def configure_logging(
    component: str,
    level: str = "INFO",
    *,
    force_json: bool | None = None,
) -> None:
    """Configure structured logging for a DCM component.

    Must be called **once** at application startup, before creating any logger.
    Subsequent calls are idempotent (structlog caches on first use).

    Args:
        component:  Logical component name injected into every log record.
                    Use the package/service name (e.g. ``"dcm-azure-collector"``).
        level:      Minimum log level. Accepts ``"DEBUG"``, ``"INFO"``,
                    ``"WARNING"``, ``"ERROR"``. Defaults to ``"INFO"``.
        force_json: Override format detection.
                    ``True`` forces JSON output, ``False`` forces console.
                    ``None`` (default) auto-detects from TTY and ``DCM_ENV``.
    """
    numeric_level = _parse_level(level)
    use_json = _should_use_json(force_json)

    # Configure the stdlib root logger so third-party libraries (azure-sdk,
    # msal, httpx) emit through the same pipeline.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
        force=True,
    )

    shared_processors: list[structlog.types.Processor] = [
        # Inject fields from the current async context (e.g. collection_run_id)
        structlog.contextvars.merge_contextvars,
        # Add the logger name (module path)
        structlog.stdlib.add_logger_name,
        # Add log level string
        structlog.stdlib.add_log_level,
        # Format positional args into the event string
        structlog.stdlib.PositionalArgumentsFormatter(),
        # ISO-8601 UTC timestamp
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        # Render exc_info into a structured traceback field
        structlog.processors.ExceptionRenderer(),
        # Inject static component field
        _make_component_processor(component),
    ]

    renderer: structlog.types.Processor
    if use_json:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True, exception_formatter=structlog.dev.plain_traceback)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog bound logger for a module.

    Args:
        name: The module name, typically ``__name__``.

    Returns:
        A bound logger ready to use with keyword-argument structured fields.

    Example::

        logger = get_logger(__name__)
        logger.info("task_started", task_id="abc-123", domain="pipeline")
        logger.warning("retry_attempt", attempt=2, max_attempts=3)
        logger.error("task_failed", error=str(exc), exc_info=exc)
    """
    return structlog.get_logger(name)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _should_use_json(force_json: bool | None) -> bool:
    """Determine whether to use JSON or console rendering."""
    if force_json is not None:
        return force_json
    env_name = os.getenv("DCM_ENV", "development").lower()
    is_production = env_name == "production"
    is_non_tty = not sys.stderr.isatty()
    return is_production or is_non_tty


def _parse_level(level: str) -> int:
    """Convert a level string to a stdlib logging integer level."""
    numeric = getattr(logging, level.upper(), None)
    if not isinstance(numeric, int):
        raise ValueError(
            f"Invalid log level '{level}'. "
            f"Expected one of: DEBUG, INFO, WARNING, ERROR, CRITICAL."
        )
    return numeric


def _make_component_processor(component: str) -> Callable[..., Any]:
    """Return a structlog processor that injects a static ``component`` field."""

    def _processor(
        logger: Any,  # noqa: ANN401
        method: str,
        event_dict: dict[str, Any],
    ) -> dict[str, Any]:
        event_dict.setdefault("component", component)
        return event_dict

    return _processor
