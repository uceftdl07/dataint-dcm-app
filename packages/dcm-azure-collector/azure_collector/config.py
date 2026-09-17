"""Configuration for the Azure DCM collector agent.

All secrets are loaded from **Azure Key Vault** via the managed identity of
the App Service WebJob.  Non-secret parameters are read from environment
variables, which are set in the App Service application settings.

Secret names (Key Vault)
------------------------
``dcm-entra-tenant-id``
    Azure AD tenant GUID.
``dcm-entra-client-id``
    App Registration client (application) GUID.
``dcm-entra-client-secret``
    App Registration client secret value.
``dcm-apigee-api-key``
    Apigee proxy API key header value.

Environment variables
---------------------
``DCM_KEY_VAULT_URL``
    Full URL of the Key Vault instance (required).
    Example: ``https://kv-dcm-azure-lz-prod.vault.azure.net/``
``AZURE_SUBSCRIPTION_ID``
    The Azure subscription ID being monitored (required).
``DCM_SOURCE_LZ_ID``
    Landing zone identifier embedded in every ``MetricPayload``
    (e.g. ``"azure-sub-fa5abbc4"``).  Required.
``DCM_APIGEE_BASE_URL``
    Base URL of the Apigee proxy (required).
    Example: ``https://api.example.com/dcm``
``DCM_ENTRA_SCOPE``
    OAuth2 scope for Entra ID token acquisition.
    Defaults to ``"api://dcm-ingestion/.default"``.
``DCM_COLLECTION_INTERVAL``
    Collection cycle interval in seconds.  Defaults to ``"300"`` (5 minutes).
``DCM_PIPELINE_LOOKBACK_HOURS``
    How many hours back to query ADF pipeline runs.  Defaults to ``"168"`` (7 days).
``DCM_ENABLED_COLLECTORS``
    Comma-separated list of enabled collector names.
    Defaults to all nine Azure collectors (ADF pipelines, activity runs, compute,
    Databricks pipelines, users, cost, database, security, standard checks).
``IDENTITY_ENDPOINT``
    Set automatically by Azure (App Service, ACI) when Managed Identity is enabled.
    When present, ``ManagedIdentityCredential`` is used instead of
    ``DefaultAzureCredential`` (avoids unnecessary fallback probes).
``AZURE_CLIENT_ID``
    Client ID of a **user-assigned** managed identity (required on ACI when using
    ``--assign-identity`` with a user-assigned identity).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from azure.identity import DefaultAzureCredential, ManagedIdentityCredential  # type: ignore[import-untyped]
from azure.keyvault.secrets import SecretClient  # type: ignore[import-untyped]

from dcm_commons.exceptions import ConfigurationError
from dcm_commons.logging_utils import get_logger

__all__ = ["AzureCollectorConfig", "azure_credential"]

_logger = get_logger(__name__)

_DEFAULT_SCOPE = "api://dcm-ingestion/.default"
_DEFAULT_INTERVAL = 300
_DEFAULT_LOOKBACK_HOURS = 168
# All Azure collectors — default runtime set (do not shrink without intent).
_DEFAULT_COLLECTORS = [
    "datafactory",
    "activity_runs",
    "databricks",
    "databricks_pipelines",
    "databricks_workflows",
    "users",
    "cost_management",
    "databases",
    "security_center",
    "standard_checks",
]

# CSV for App Service / .env copy-paste when explicit list is required.
DEFAULT_COLLECTORS_CSV = ",".join(_DEFAULT_COLLECTORS)


@dataclass
class AzureCollectorConfig:
    """Fully-loaded configuration for the Azure collector agent.

    Attributes:
        subscription_id:            Azure subscription ID being monitored.
        source_lz_id:               Landing zone identifier for ``MetricPayload``.
        apigee_base_url:            Base URL of the Apigee proxy.
        entra_tenant_id:            Azure AD tenant GUID.
        entra_client_id:            App Registration client GUID.
        entra_client_secret:        App Registration client secret.
        entra_scope:                OAuth2 scope for token acquisition.
        apigee_api_key:             Apigee proxy API key.
        collection_interval_seconds: Seconds between collection cycles.
        pipeline_lookback_hours:    Hours of ADF pipeline run history to query.
        enabled_collectors:         Names of collectors to run each cycle.
    """

    subscription_id: str
    source_lz_id: str
    apigee_base_url: str
    entra_tenant_id: str
    entra_client_id: str
    entra_client_secret: str
    entra_scope: str
    apigee_api_key: str
    collection_interval_seconds: int = _DEFAULT_INTERVAL
    pipeline_lookback_hours: int = _DEFAULT_LOOKBACK_HOURS
    enabled_collectors: list[str] = field(default_factory=lambda: list(_DEFAULT_COLLECTORS))

    @classmethod
    def from_env_and_keyvault(cls) -> AzureCollectorConfig:
        """Load configuration from environment variables and Azure Key Vault.

        Uses ``ManagedIdentityCredential`` when the ``IDENTITY_ENDPOINT``
        environment variable is present (i.e. running inside an App Service
        with Managed Identity enabled).  Falls back to ``DefaultAzureCredential``
        for local development (developer credentials, env vars, etc.).

        Returns:
            A fully populated :class:`AzureCollectorConfig`.

        Raises:
            ConfigurationError: If any required environment variable or Key
                                Vault secret is missing or invalid.
        """
        key_vault_url = os.getenv("DCM_KEY_VAULT_URL") or os.getenv("KEY_VAULT_URL")
        if not key_vault_url:
            raise ConfigurationError(
                "DCM_KEY_VAULT_URL",
                "must be set to the full Azure Key Vault URI "
                "(e.g. https://kv-dcm-prod.vault.azure.net/)",
            )

        subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID", "")
        if not subscription_id:
            raise ConfigurationError(
                "AZURE_SUBSCRIPTION_ID",
                "must be set to the Azure subscription ID being monitored",
            )

        source_lz_id = os.getenv("DCM_SOURCE_LZ_ID", "")
        if not source_lz_id:
            raise ConfigurationError(
                "DCM_SOURCE_LZ_ID",
                "must be set to the landing zone identifier "
                "(e.g. 'azure-sub-fa5abbc4')",
            )

        apigee_base_url = os.getenv("DCM_APIGEE_BASE_URL", "")
        if not apigee_base_url:
            raise ConfigurationError(
                "DCM_APIGEE_BASE_URL",
                "must be set to the Apigee proxy base URL",
            )

        credential = azure_credential()

        _logger.info(
            "config_loading_secrets",
            key_vault_url=key_vault_url,
            using_managed_identity=bool(os.getenv("IDENTITY_ENDPOINT")),
        )

        kv_client = SecretClient(vault_url=key_vault_url, credential=credential)

        entra_tenant_id = os.getenv("DCM_ENTRA_TENANT_ID")
        if entra_tenant_id:
            _logger.info("entra_tenant_id loaded from env var DCM_ENTRA_TENANT_ID")
        else:
            try:
                entra_tenant_id = _get_secret(kv_client, "dcm-entra-tenant-id")
                _logger.info("entra_tenant_id loaded from Key Vault secret dcm-entra-tenant-id")
            except Exception:
                raise ConfigurationError(
                    "dcm-entra-tenant-id",
                    "Secret 'dcm-entra-tenant-id' introuvable dans Key Vault et variable "
                    "d'environnement DCM_ENTRA_TENANT_ID non définie.",
                ) from None

        try:
            entra_client_id = _get_secret(kv_client, "dcm-entra-client-id")
        except Exception:
            entra_client_id = os.getenv("DCM_ENTRA_CLIENT_ID")
            if not entra_client_id:
                raise ConfigurationError(
                    "dcm-entra-client-id",
                    "Secret 'dcm-entra-client-id' introuvable dans Key Vault et variable d'environnement DCM_ENTRA_CLIENT_ID non définie."
                )

        try:
            entra_client_secret = _get_secret(kv_client, "dcm-entra-client-secret")
        except Exception:
            entra_client_secret = os.getenv("DCM_ENTRA_CLIENT_SECRET")
            if not entra_client_secret:
                raise ConfigurationError(
                    "dcm-entra-client-secret",
                    "Secret 'dcm-entra-client-secret' introuvable dans Key Vault et variable d'environnement DCM_ENTRA_CLIENT_SECRET non définie."
                )

        try:
            apigee_api_key = _get_secret(kv_client, "dcm-apigee-api-key")
        except Exception:
            apigee_api_key = os.getenv("DCM_APIGEE_API_KEY")
            if not apigee_api_key:
                raise ConfigurationError(
                    "dcm-apigee-api-key",
                    "Secret 'dcm-apigee-api-key' introuvable dans Key Vault et variable d'environnement DCM_APIGEE_API_KEY non définie."
                )

        # Parse optional numeric/list settings.
        collection_interval = _parse_int(
            "DCM_COLLECTION_INTERVAL", _DEFAULT_INTERVAL, min_value=60
        )
        pipeline_lookback = _parse_int(
            "DCM_PIPELINE_LOOKBACK_HOURS", _DEFAULT_LOOKBACK_HOURS, min_value=1
        )

        enabled_collectors = _resolve_enabled_collectors(
            os.getenv("DCM_ENABLED_COLLECTORS")
        )

        config = cls(
            subscription_id=subscription_id,
            source_lz_id=source_lz_id,
            apigee_base_url=apigee_base_url,
            entra_tenant_id=entra_tenant_id,
            entra_client_id=entra_client_id,
            entra_client_secret=entra_client_secret,
            entra_scope=os.getenv("DCM_ENTRA_SCOPE", _DEFAULT_SCOPE),
            apigee_api_key=apigee_api_key,
            collection_interval_seconds=collection_interval,
            pipeline_lookback_hours=pipeline_lookback,
            enabled_collectors=enabled_collectors,
        )

        _logger.info(
            "config_loaded",
            subscription_id=subscription_id,
            source_lz_id=source_lz_id,
            enabled_collectors=enabled_collectors,
            collection_interval_seconds=collection_interval,
            pipeline_lookback_hours=pipeline_lookback,
        )
        return config


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def azure_credential() -> DefaultAzureCredential | ManagedIdentityCredential:
    """Return the Azure credential for the current runtime (App Service, ACI, or local)."""
    if os.getenv("IDENTITY_ENDPOINT"):
        client_id = os.getenv("AZURE_CLIENT_ID")
        if client_id:
            _logger.info(
                "azure_credential_created",
                credential_type="ManagedIdentityCredential",
                user_assigned=True,
                client_id=client_id,
            )
            return ManagedIdentityCredential(client_id=client_id)
        _logger.info(
            "azure_credential_created",
            credential_type="ManagedIdentityCredential",
            user_assigned=False,
        )
        return ManagedIdentityCredential()
    _logger.info(
        "azure_credential_created",
        credential_type="DefaultAzureCredential",
    )
    return DefaultAzureCredential()


def _get_secret(client: SecretClient, name: str) -> str:
    """Retrieve a secret value from Key Vault, raising ConfigurationError on failure.

    Args:
        client: Authenticated ``SecretClient``.
        name:   Secret name in Key Vault.

    Returns:
        The non-empty secret value string.

    Raises:
        ConfigurationError: If the secret is missing, disabled, or empty.
    """
    try:
        secret = client.get_secret(name)
    except Exception as exc:
        raise ConfigurationError(
            name,
            f"Secret '{name}' could not be retrieved from Key Vault: {exc}",
        ) from exc

    value = secret.value
    if not value:
        raise ConfigurationError(name, f"Secret '{name}' exists but has an empty value.")
    return value


def _resolve_enabled_collectors(raw: str | None) -> list[str]:
    """Return the list of collectors to run.

    Unset, empty, ``all``, or ``*`` → all collectors in :data:`_DEFAULT_COLLECTORS`.
    Any other value → comma-separated names (unknown names are dropped with a warning).
    If the parsed list is empty after filtering, falls back to all collectors.
    """
    if raw is None or not raw.strip() or raw.strip().lower() in ("all", "*"):
        return list(_DEFAULT_COLLECTORS)

    names = [c.strip() for c in raw.split(",") if c.strip()]
    if not names:
        return list(_DEFAULT_COLLECTORS)

    known = set(_DEFAULT_COLLECTORS)
    enabled = [n for n in names if n in known]
    unknown = [n for n in names if n not in known]
    if unknown:
        _logger.warning(
            "config_unknown_collectors_ignored",
            unknown=unknown,
            valid=list(_DEFAULT_COLLECTORS),
        )
    return enabled if enabled else list(_DEFAULT_COLLECTORS)


def _parse_int(env_var: str, default: int, *, min_value: int = 1) -> int:
    """Parse an integer environment variable with a default and minimum bound.

    Args:
        env_var:   Environment variable name.
        default:   Value to use when the variable is absent.
        min_value: Minimum acceptable value.

    Returns:
        The parsed integer, clamped to ``min_value`` if too small.
    """
    raw = os.getenv(env_var)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        _logger.warning(
            "config_invalid_int",
            env_var=env_var,
            raw_value=raw,
            fallback=default,
        )
        return default
    return max(value, min_value)
