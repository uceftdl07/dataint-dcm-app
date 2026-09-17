"""Application configuration loaded from environment + Secrets Manager."""


from __future__ import annotations

# Force explicit .env load for backend, even when uvicorn starts from the repo root.
from pathlib import Path

from dotenv import load_dotenv

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ENV_FILE = _BACKEND_DIR / ".env"
# Local .env must win over stale shell exports when the file is updated.
load_dotenv(_ENV_FILE, override=True)

import json
import logging
import os

import boto3
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .cors import CORSSettings

__all__ = ["Settings", "CORSSettings"]

logger = logging.getLogger(__name__)


def _presence(value: str | None) -> str:
    if value is None:
        return "unset"
    if value == "":
        return "EMPTY"
    if value.strip() == "":
        return "BLANK"
    return "set"


def _env_presence(name: str) -> str:
    return _presence(os.environ.get(name))


_SENSITIVE_ENV_MARKERS = ("SECRET", "TOKEN", "PASSWORD", "PRIVATE_KEY", "ACCESS_KEY", "API_KEY")

_DCM_ENV_KEYS_TO_LOG = (
    "DCM_APP_NAME",
    "DCM_ENVIRONMENT",
    "DCM_DATABRICKS_HOST",
    "DCM_DATABRICKS_WAREHOUSE_ID",
    "DCM_DATABRICKS_HTTP_PATH",
    "DCM_DATABRICKS_CATALOG",
    "DCM_DATABRICKS_SCHEMA",
    "DCM_DATABRICKS_SPN_CLIENT_ID",
    "DCM_DATABRICKS_SPN_CLIENT_SECRET",
    "DCM_DATABRICKS_SPN_CLIENT_SECRET_ARN",
    "DCM_DATABRICKS_TOKEN",
    "DCM_ENTRA_TENANT_ID",
    "DCM_ENTRA_CLIENT_ID",
    "DCM_AUTH_DISABLED",
    "DCM_COLLECTOR_API_KEY",
    "DCM_CORS_ALLOWED_ORIGINS",
    "DCM_SECRET_NAME",
    "DCM_TEAMS_WEBHOOK_URL",
    "DCM_FRONTEND_URL",
    "DCM_CHAT_PROVIDER",
    "DCM_GENIE_SPACE_ID",
    "DCM_GENIE_API_BASE_URL",
)


def _safe_env_value(name: str) -> str:
    value = os.environ.get(name)
    presence = _presence(value)
    if presence != "set":
        return presence
    if any(marker in name.upper() for marker in _SENSITIVE_ENV_MARKERS):
        return f"set(len={len(value or '')})"
    return str(value)


def _safe_secret_ref(secret_id: str) -> str:
    if not secret_id:
        return "(empty)"
    if ":secret:" in secret_id:
        return f"...:secret:{secret_id.rsplit(':secret:', 1)[1]}"
    return f"non-arn-value(len={len(secret_id)})"


def _secret_string(secret_id: str) -> str:
    sm = boto3.client("secretsmanager")
    response = sm.get_secret_value(SecretId=secret_id)
    return str(response.get("SecretString") or "")


def _secret_value(secret_id: str, *keys: str) -> str:
    raw = _secret_string(secret_id)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw

    if not isinstance(parsed, dict):
        return raw

    for key in keys:
        value = parsed.get(key)
        if value:
            return str(value)
    return ""


def _extract_secret_from_json_value(value: str, *keys: str) -> tuple[str, bool, bool]:
    """Extract a named secret when ECS injects a whole JSON document."""
    if not value:
        return value, False, False
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value, False, False

    if not isinstance(parsed, dict):
        return value, False, False

    for key in keys:
        candidate = parsed.get(key)
        if candidate:
            return str(candidate), True, True
    return "", True, False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DCM_",
        env_file=str(_ENV_FILE),
        extra="ignore",  # DCM_CORS_* is loaded by CORSSettings, not Settings
    )

    app_name: str = "dcm-backend"
    environment: str = "development"

    # Databricks SQL Warehouse (Unity Catalog)
    databricks_host: str = "dbc-89e8d3b6-20ad.cloud.databricks.com"
    databricks_warehouse_id: str = "cf12d9eaa80a7ec5"
    databricks_http_path: str = ""  # optional override; default built from warehouse_id
    databricks_catalog: str = "it"
    # One schema per environment: ``__d`` dev, ``__p`` prod. The default is the dev
    # one so a local run without DCM_DATABRICKS_SCHEMA reads dev data instead of a
    # retired schema. Never hardcode either name in a query — go through
    # ``qualified_table`` / ``DatabricksWarehousePool.table``.
    databricks_schema: str = "ba_data_connect_monitoring__d"

    # Auth: SPN OAuth M2M (production) or PAT (local dev only)
    databricks_spn_client_id: str = ""
    databricks_spn_client_secret: str = ""
    databricks_spn_client_secret_arn: str = ""
    databricks_token: str = ""  # PAT — ignored when SPN credentials are set

    # Entra ID (JWT validation)
    entra_tenant_id: str = ""
    entra_client_id: str = ""
    auth_disabled: bool = False

    # Collector callbacks
    collector_api_key: str = ""

    # Teams webhook for access request notifications
    teams_webhook_url: str = ""
    
    # Frontend URL for Teams notifications links
    frontend_url: str = "http://localhost:4000"
    chat_provider: str = "local_loaders"
    genie_space_id: str = ""
    genie_api_base_url: str = ""

    # CORS


    allowed_origins: list[str] = ["http://localhost:4000", "https://dcm.alzp.tgscloud.net"]

    from pydantic import field_validator

    @field_validator('allowed_origins', mode='before')
    @classmethod
    def parse_allowed_origins(cls, v):
        if isinstance(v, list):
            return v
        import json
        try:
            parsed = json.loads(v)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
        return [s.strip() for s in v.split(',') if s.strip()]

    @classmethod
    def _parse_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, list):
            return value
        import json
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
        return [v.strip() for v in value.split(",") if v.strip()]

    @classmethod
    def __get_validators__(cls):
        yield from super().__get_validators__()
        yield cls._validate_allowed_origins

    @classmethod
    def _validate_allowed_origins(cls, values):
        # Pydantic v2: field name is 'allowed_origins'
        if "allowed_origins" in values:
            v = values["allowed_origins"]
            if isinstance(v, str):
                values["allowed_origins"] = cls._parse_origins(v)
        return values

    @classmethod
    def _parse_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, list):
            return value
        import json
        try:
            # Try JSON list
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
        # Fallback: comma-separated string
        return [v.strip() for v in value.split(",") if v.strip()]

    def model_post_init(self, __context):
        # Accept both JSON and comma-separated for allowed_origins
        if isinstance(self.allowed_origins, str):
            self.allowed_origins = self._parse_origins(self.allowed_origins)
        self._normalize_databricks_spn_client_secret()

    def _normalize_databricks_spn_client_secret(self) -> None:
        value, was_json, found_key = _extract_secret_from_json_value(
            self.databricks_spn_client_secret,
            "DCM_DATABRICKS_SPN_CLIENT_SECRET",
            "databricks_spn_client_secret",
        )
        if not was_json:
            return

        self.databricks_spn_client_secret = value
        if found_key:
            logger.info(
                "Databricks SPN client secret was a JSON document; extracted named secret value"
            )
        else:
            logger.warning(
                "Databricks SPN client secret was a JSON document but did not contain "
                "DCM_DATABRICKS_SPN_CLIENT_SECRET or databricks_spn_client_secret"
            )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resolved_http_path(self) -> str:
        """SQL Warehouse HTTP path — explicit path or derived from warehouse ID."""
        if self.databricks_http_path:
            return self.databricks_http_path
        if self.databricks_warehouse_id:
            return f"/sql/1.0/warehouses/{self.databricks_warehouse_id}"
        return ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resolved_entra_jwks_uri(self) -> str:
        """Microsoft Entra JWKS endpoint derived from the tenant ID."""
        if self.entra_tenant_id.strip():
            tenant_id = self.entra_tenant_id.strip()
            return f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
        return ""

    def uses_spn_auth(self) -> bool:
        return bool(self.databricks_spn_client_id and self.databricks_spn_client_secret)

    def uses_pat_auth(self) -> bool:
        return bool(self.databricks_token) and not self.uses_spn_auth()

    def log_runtime_env_diagnostics(self) -> None:
        """Log selected runtime env vars without exposing secret values."""
        logger.info(
            "Runtime DCM env keys present: %s",
            sorted(key for key in os.environ if key.startswith("DCM_")),
        )
        logger.info(
            "Runtime DCM env snapshot: %s",
            {key: _safe_env_value(key) for key in _DCM_ENV_KEYS_TO_LOG},
        )
        logger.info(
            "Runtime AWS/ECS env presence: AWS_REGION=%s AWS_DEFAULT_REGION=%s "
            "AWS_EXECUTION_ENV=%s AWS_CONTAINER_CREDENTIALS_RELATIVE_URI=%s "
            "ECS_CONTAINER_METADATA_URI_V4=%s",
            _safe_env_value("AWS_REGION"),
            _safe_env_value("AWS_DEFAULT_REGION"),
            _safe_env_value("AWS_EXECUTION_ENV"),
            _env_presence("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"),
            _env_presence("ECS_CONTAINER_METADATA_URI_V4"),
        )

    def log_databricks_diagnostics(self) -> None:
        """Log Databricks auth wiring without exposing secret values."""
        logger.info(
            "Databricks env presence: host=%s warehouse_id=%s catalog=%s schema=%s "
            "spn_client_id=%s spn_secret=%s spn_secret_arn=%s token=%s dcm_secret_name=%s",
            _env_presence("DCM_DATABRICKS_HOST"),
            _env_presence("DCM_DATABRICKS_WAREHOUSE_ID"),
            _env_presence("DCM_DATABRICKS_CATALOG"),
            _env_presence("DCM_DATABRICKS_SCHEMA"),
            _env_presence("DCM_DATABRICKS_SPN_CLIENT_ID"),
            _env_presence("DCM_DATABRICKS_SPN_CLIENT_SECRET"),
            _env_presence("DCM_DATABRICKS_SPN_CLIENT_SECRET_ARN"),
            _env_presence("DCM_DATABRICKS_TOKEN"),
            _env_presence("DCM_SECRET_NAME"),
        )
        logger.info(
            "Databricks auth resolution: uses_spn_auth=%s uses_pat_auth=%s "
            "settings_spn_client_id=%s settings_spn_secret=%s settings_spn_secret_arn=%s "
            "resolved_http_path=%s",
            self.uses_spn_auth(),
            self.uses_pat_auth(),
            _presence(self.databricks_spn_client_id),
            _presence(self.databricks_spn_client_secret),
            _presence(self.databricks_spn_client_secret_arn),
            self.resolved_http_path or "(empty)",
        )

    @classmethod
    def from_secrets_manager(cls) -> "Settings":
        """In production (ECS), load secrets from AWS Secrets Manager via VPC endpoint."""
        settings = cls()
        logger.info(
            "Databricks secret bootstrap: DCM_SECRET_NAME=%s direct_spn_secret=%s "
            "spn_secret_arn=%s",
            _env_presence("DCM_SECRET_NAME"),
            _env_presence("DCM_DATABRICKS_SPN_CLIENT_SECRET"),
            _env_presence("DCM_DATABRICKS_SPN_CLIENT_SECRET_ARN"),
        )
        secret_name = os.environ.get("DCM_SECRET_NAME")
        if secret_name:
            logger.info("Loading DCM settings from Secrets Manager ref %s", _safe_secret_ref(secret_name))
            try:
                secret = json.loads(_secret_string(secret_name))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not load DCM_SECRET_NAME=%s: %s", secret_name, exc)
            else:
                logger.info("Loaded DCM_SECRET_NAME keys: %s", sorted(str(key) for key in secret))
                settings.databricks_host = secret.get("databricks_host", settings.databricks_host)
                settings.databricks_warehouse_id = secret.get(
                    "databricks_warehouse_id", settings.databricks_warehouse_id
                )
                settings.databricks_http_path = secret.get(
                    "databricks_http_path", settings.databricks_http_path
                )
                settings.databricks_catalog = secret.get(
                    "databricks_catalog", settings.databricks_catalog
                )
                settings.databricks_schema = secret.get(
                    "databricks_schema", settings.databricks_schema
                )
                settings.databricks_spn_client_id = secret.get(
                    "databricks_spn_client_id",
                    secret.get("DCM_DATABRICKS_SPN_CLIENT_ID", settings.databricks_spn_client_id),
                )
                settings.databricks_spn_client_secret = secret.get(
                    "databricks_spn_client_secret",
                    secret.get(
                        "DCM_DATABRICKS_SPN_CLIENT_SECRET",
                        settings.databricks_spn_client_secret,
                    ),
                )
                settings.databricks_token = secret.get(
                    "databricks_token",
                    secret.get("DCM_DATABRICKS_TOKEN", settings.databricks_token),
                )
                settings.entra_client_id = secret.get("entra_client_id", settings.entra_client_id)
                settings._normalize_databricks_spn_client_secret()

        if settings.databricks_spn_client_secret:
            logger.info("Databricks SPN client secret already present before ARN lookup")
        elif settings.databricks_spn_client_secret_arn:
            logger.info(
                "Loading Databricks SPN client secret from Secrets Manager ref %s",
                _safe_secret_ref(settings.databricks_spn_client_secret_arn),
            )
            try:
                settings.databricks_spn_client_secret = _secret_value(
                    settings.databricks_spn_client_secret_arn,
                    "DCM_DATABRICKS_SPN_CLIENT_SECRET",
                    "databricks_spn_client_secret",
                )
                logger.info(
                    "Databricks SPN client secret loaded from ARN: %s",
                    _presence(settings.databricks_spn_client_secret),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Could not load DCM_DATABRICKS_SPN_CLIENT_SECRET_ARN=%s: %s",
                    _safe_secret_ref(settings.databricks_spn_client_secret_arn),
                    exc,
                )
        else:
            logger.warning(
                "No Databricks SPN client secret or secret ARN present after settings load "
                "(token=%s)",
                _presence(settings.databricks_token),
            )
        settings._normalize_databricks_spn_client_secret()
        return settings
