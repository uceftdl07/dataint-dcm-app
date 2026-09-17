"""Unit tests for Databricks warehouse settings."""

from __future__ import annotations

import json
import logging

import pytest

from app.config import Settings


def test_resolved_http_path_from_warehouse_id() -> None:
    settings = Settings(
        databricks_warehouse_id="cf12d9eaa80a7ec5",
        databricks_http_path="",
    )
    assert settings.resolved_http_path == "/sql/1.0/warehouses/cf12d9eaa80a7ec5"


def test_resolved_http_path_explicit_override() -> None:
    settings = Settings(
        databricks_warehouse_id="cf12d9eaa80a7ec5",
        databricks_http_path="/sql/1.0/warehouses/custom",
    )
    assert settings.resolved_http_path == "/sql/1.0/warehouses/custom"


def test_resolved_entra_jwks_uri_from_tenant_id() -> None:
    settings = Settings(
        entra_tenant_id="329e91b0-e21f-48fb-a071-456717ecc28e",
    )

    assert (
        settings.resolved_entra_jwks_uri
        == "https://login.microsoftonline.com/329e91b0-e21f-48fb-a071-456717ecc28e/discovery/v2.0/keys"
    )


def test_resolved_entra_jwks_uri_empty_without_tenant_id() -> None:
    settings = Settings(entra_tenant_id="")

    assert settings.resolved_entra_jwks_uri == ""


def test_uses_spn_auth_when_client_credentials_set() -> None:
    settings = Settings(
        databricks_spn_client_id="c92fca2d-0533-4392-8b28-c916f421f2f3",
        databricks_spn_client_secret="secret",
        databricks_token="dapi-token",
    )
    assert settings.uses_spn_auth() is True
    assert settings.uses_pat_auth() is False


def test_uses_pat_auth_when_no_spn() -> None:
    settings = Settings(
        databricks_token="dapi-token",
        databricks_spn_client_id="",
        databricks_spn_client_secret="",
    )
    assert settings.uses_spn_auth() is False
    assert settings.uses_pat_auth() is True


def test_extracts_spn_secret_when_ecs_injects_json_document() -> None:
    settings = Settings(
        databricks_spn_client_id="c92fca2d-0533-4392-8b28-c916f421f2f3",
        databricks_spn_client_secret=json.dumps(
            {
                "DCM_DATABRICKS_SPN_CLIENT_SECRET": "actual-secret",
                "DCM_DATABRICKS_TOKEN": "",
            }
        ),
    )

    assert settings.databricks_spn_client_secret == "actual-secret"
    assert settings.uses_spn_auth() is True


def test_rejects_json_spn_secret_without_expected_key() -> None:
    settings = Settings(
        databricks_spn_client_id="c92fca2d-0533-4392-8b28-c916f421f2f3",
        databricks_spn_client_secret=json.dumps({"other": "value"}),
    )

    assert settings.databricks_spn_client_secret == ""
    assert settings.uses_spn_auth() is False


def test_runtime_env_diagnostics_redacts_secrets(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("DCM_DATABRICKS_HOST", "dbc-example.cloud.databricks.com")
    monkeypatch.setenv("DCM_DATABRICKS_SPN_CLIENT_SECRET", "super-secret")
    monkeypatch.setenv("DCM_DATABRICKS_TOKEN", "dapi-token-value")

    caplog.set_level(logging.INFO)
    Settings().log_runtime_env_diagnostics()

    assert "dbc-example.cloud.databricks.com" in caplog.text
    assert "DCM_DATABRICKS_SPN_CLIENT_SECRET" in caplog.text
    assert "set(len=12)" in caplog.text
    assert "super-secret" not in caplog.text
    assert "dapi-token-value" not in caplog.text
