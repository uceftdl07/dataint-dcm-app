"""Custom exception hierarchy for the Data Connect Monitoring platform.

All DCM components raise exceptions derived from ``DCMError``, enabling
callers to distinguish DCM failures from unexpected third-party exceptions
and to apply fine-grained error handling strategies.

Exception hierarchy::

    DCMError
    ├── ConfigurationError   — invalid or missing configuration at startup
    ├── AuthenticationError  — Entra ID token acquisition failure
    ├── CollectionError      — metric retrieval failure from a cloud provider
    └── IngestionError       — payload delivery failure to Apigee gateway

Usage example::

    from dcm_commons.exceptions import CollectionError, IngestionError

    try:
        payload = await collector.collect()
    except CollectionError as exc:
        logger.error("collection_failed",
                     collector=exc.collector_name, reason=exc.reason)
    except DCMError:
        # Catch-all for any DCM-related failure
        raise
"""

from __future__ import annotations

__all__ = [
    "DCMError",
    "ConfigurationError",
    "AuthenticationError",
    "CollectionError",
    "IngestionError",
]


class DCMError(Exception):
    """Base class for all DCM-specific exceptions.

    Catch this to handle any DCM error without caring about the sub-type.
    Catch a subclass when you need to distinguish the failure mode.
    """


class ConfigurationError(DCMError):
    """Raised when a required configuration parameter is missing or invalid.

    Typically raised during application startup, before any collection begins.
    The agent should exit with a non-zero code when this is raised.

    Args:
        parameter: The name of the missing or invalid config key.
        reason:    Human-readable explanation of why the value is invalid.

    Example::

        raise ConfigurationError("DCM_APIGEE_BASE_URL", "must not be empty")
    """

    def __init__(self, parameter: str, reason: str) -> None:
        self.parameter = parameter
        self.reason = reason
        super().__init__(f"Configuration error for '{parameter}': {reason}")


class AuthenticationError(DCMError):
    """Raised when Entra ID token acquisition fails.

    Wraps MSAL error responses without exposing internal MSAL error codes to
    calling code. The ``reason`` attribute provides a human-readable summary.

    Args:
        reason: Human-readable description of the failure (from MSAL response).

    Example::

        raise AuthenticationError("invalid_client: The provided client secret is incorrect.")
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Entra ID authentication failed: {reason}")


class CollectionError(DCMError):
    """Raised when a collector cannot retrieve metrics from the cloud provider.

    The ``collector_name`` attribute enables granular tracking when multiple
    collectors run within the same agent process.

    Args:
        collector_name: The class name of the failing collector
                        (e.g. "DataFactoryCollector").
        reason:         Human-readable description of the failure.

    Example::

        raise CollectionError("DataFactoryCollector", "subscription not found") from exc
    """

    def __init__(self, collector_name: str, reason: str) -> None:
        self.collector_name = collector_name
        self.reason = reason
        super().__init__(f"[{collector_name}] Collection failed: {reason}")


class IngestionError(DCMError):
    """Raised when payload delivery to the Apigee gateway fails definitively.

    Raised only after all retry attempts are exhausted. The ``status_code``
    is ``None`` for network-level failures (timeouts, DNS errors).

    Args:
        reason:      Human-readable failure description.
        status_code: HTTP status code from Apigee, or ``None`` for network errors.

    Example::

        raise IngestionError("gateway returned 503", status_code=503) from exc
    """

    def __init__(self, reason: str, *, status_code: int | None = None) -> None:
        self.reason = reason
        self.status_code = status_code
        http_part = f" (HTTP {status_code})" if status_code is not None else ""
        super().__init__(f"Ingestion failed{http_part}: {reason}")
