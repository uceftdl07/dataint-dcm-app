"""Configuration for the AWS DCM collector agent.

All secrets (Entra ID credentials, Apigee API key) are loaded from
**AWS Secrets Manager** via the ECS Task IAM Role — no static credentials
are ever used.  Non-secret parameters are read from environment variables
set in the ECS Task Definition.

Secret layout (Secrets Manager — single JSON secret)
-----------------------------------------------------
The secret referenced by ``DCM_SECRET_NAME`` must contain the following
JSON keys::

    {
        "entra_tenant_id":     "...",
        "entra_client_id":     "...",
        "entra_client_secret": "...",
        "apigee_api_key":      "..."
    }

Environment variables (ECS Task Definition)
-------------------------------------------
``DCM_SECRET_NAME``
    Name or ARN of the Secrets Manager secret (required).
``AWS_DEFAULT_REGION``
    AWS region of the monitored account (required, e.g. ``"eu-west-1"``).
``DCM_SOURCE_LZ_ID``
    Landing zone identifier embedded in every ``MetricPayload``
    (e.g. ``"aws-account-551656632516"``).  Required.
``DCM_APIGEE_BASE_URL``
    Base URL of the Apigee proxy (required).
    Example: ``https://api.corporate.com/dcm``
``DCM_ENTRA_SCOPE``
    OAuth2 scope for Entra ID token acquisition.
    Defaults to ``"api://dcm-ingestion/.default"``.
``DCM_ENABLED_COLLECTORS``
    Comma-separated list of enabled collector names.
    Defaults to all five: ``"glue,emr,rds,cost_explorer,redshift"``.
``DCM_COST_LOOKBACK_DAYS``
    Number of days of cost history to retrieve from Cost Explorer.
    Defaults to ``"30"``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from dcm_commons.exceptions import ConfigurationError
from dcm_commons.logging_utils import get_logger

from aws_collector._aws_utils import create_aws_client

__all__ = ["AWSCollectorConfig"]

_logger = get_logger(__name__)

_DEFAULT_SCOPE = "api://dcm-ingestion/.default"
_DEFAULT_REGION = "eu-west-1"
_DEFAULT_COST_LOOKBACK_DAYS = 30
_DEFAULT_COLLECTORS = ["glue", "emr", "rds", "cost_explorer", "redshift"]


@dataclass
class AWSCollectorConfig:
    """Fully-loaded configuration for the AWS collector agent.

    Attributes:
        aws_region:           AWS region of the monitored account.
        source_lz_id:         Landing zone identifier for ``MetricPayload``.
        apigee_base_url:      Base URL of the Apigee proxy.
        entra_tenant_id:      Azure AD tenant GUID.
        entra_client_id:      App Registration client GUID.
        entra_client_secret:  App Registration client secret.
        entra_scope:          OAuth2 scope for token acquisition.
        apigee_api_key:       Apigee proxy API key.
        cost_lookback_days:   Days of cost history to retrieve.
        enabled_collectors:   Names of collectors to run.
    """

    aws_region: str
    source_lz_id: str
    apigee_base_url: str
    entra_tenant_id: str
    entra_client_id: str
    entra_client_secret: str
    entra_scope: str
    apigee_api_key: str
    cost_lookback_days: int = _DEFAULT_COST_LOOKBACK_DAYS
    enabled_collectors: list[str] = field(
        default_factory=lambda: list(_DEFAULT_COLLECTORS)
    )

    @classmethod
    def from_secrets_manager(cls) -> AWSCollectorConfig:
        """Load configuration from environment variables and AWS Secrets Manager.

        The ECS Task IAM Role must grant ``secretsmanager:GetSecretValue``
        on the secret referenced by ``DCM_SECRET_NAME``.

        Returns:
            A fully populated :class:`AWSCollectorConfig`.

        Raises:
            ConfigurationError: If any required environment variable is missing
                                or if the Secrets Manager call fails.
        """
        secret_name = os.getenv("DCM_SECRET_NAME", "")
        if not secret_name:
            raise ConfigurationError(
                "DCM_SECRET_NAME",
                "must be set to the name or ARN of the Secrets Manager secret",
            )

        region = os.getenv("AWS_DEFAULT_REGION", _DEFAULT_REGION)

        source_lz_id = os.getenv("DCM_SOURCE_LZ_ID", "")
        if not source_lz_id:
            raise ConfigurationError(
                "DCM_SOURCE_LZ_ID",
                "must be set to the landing zone identifier "
                "(e.g. 'aws-account-551656632516')",
            )

        apigee_base_url = os.getenv("DCM_APIGEE_BASE_URL", "")
        if not apigee_base_url:
            raise ConfigurationError(
                "DCM_APIGEE_BASE_URL",
                "must be set to the Apigee proxy base URL",
            )

        _logger.info(
            "config_loading_secrets",
            secret_name=secret_name,
            region=region,
        )

        try:
            sm = create_aws_client("secretsmanager", region_name=region)
            resp = sm.get_secret_value(SecretId=secret_name)
            secrets: dict[str, str] = json.loads(resp["SecretString"])
        except Exception as exc:
            raise ConfigurationError(
                "Secrets Manager",
                f"Failed to load secret '{secret_name}': {exc}",
            ) from exc

        def _require(key: str) -> str:
            val = secrets.get(key, "")
            if not val:
                raise ConfigurationError(
                    key,
                    f"Key '{key}' is missing or empty in Secrets Manager secret "
                    f"'{secret_name}'.",
                )
            return val

        entra_tenant_id = _require("entra_tenant_id")
        entra_client_id = _require("entra_client_id")
        entra_client_secret = _require("entra_client_secret")
        apigee_api_key = _require("apigee_api_key")

        raw_collectors = os.getenv("DCM_ENABLED_COLLECTORS", "")
        enabled_collectors = (
            [c.strip() for c in raw_collectors.split(",") if c.strip()]
            if raw_collectors
            else list(_DEFAULT_COLLECTORS)
        )

        cost_lookback_days = _parse_int(
            "DCM_COST_LOOKBACK_DAYS", _DEFAULT_COST_LOOKBACK_DAYS, min_value=1
        )

        config = cls(
            aws_region=region,
            source_lz_id=source_lz_id,
            apigee_base_url=apigee_base_url,
            entra_tenant_id=entra_tenant_id,
            entra_client_id=entra_client_id,
            entra_client_secret=entra_client_secret,
            entra_scope=os.getenv("DCM_ENTRA_SCOPE", _DEFAULT_SCOPE),
            apigee_api_key=apigee_api_key,
            cost_lookback_days=cost_lookback_days,
            enabled_collectors=enabled_collectors,
        )

        _logger.info(
            "config_loaded",
            source_lz_id=source_lz_id,
            region=region,
            enabled_collectors=enabled_collectors,
            cost_lookback_days=cost_lookback_days,
        )
        return config


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_int(env_var: str, default: int, *, min_value: int = 1) -> int:
    """Parse an integer environment variable with a default and minimum bound.

    Args:
        env_var:   Environment variable name.
        default:   Value to use when the variable is absent.
        min_value: Minimum acceptable value (clamped, not rejected).

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
