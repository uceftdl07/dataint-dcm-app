"""Tests de `pipelines.reference_lz.entrypoint` (cablage + selection + garde-fou FR-004).

`ingest_dbx_workspace` / `ingest_business_application` sont monkeypatchees sur
le module `entrypoint` (import absolu ⇒ reference globale propre au module
consommateur), meme convention que `tests/system_tables/test_entrypoint.py`.
"""

from __future__ import annotations

import pytest

import pipelines.reference_lz.entrypoint as entrypoint
import pipelines.reference_lz.specs as specs


def _base_params() -> dict[str, str]:
    """Params nommes minimaux valides pour `main` (Azure desactive, toutes tables)."""
    return dict.fromkeys(entrypoint.PARAM_NAMES, "") | {
        "catalog": "it",
        "schema": "ba_data_connect_monitoring__d",
        "collection_run_id": "run-1",
        "collected_at": "2026-08-20T00:00:00Z",
    }


def _azure_params() -> dict[str, str]:
    return _base_params() | {
        "azure_host": "adb-123.azuredatabricks.net",
        "azure_http_path": "/sql/1.0/warehouses/abc",
        "azure_secret_scope": "dcm-secret-scope",
        "azure_tenant_id_key": "azure-sp-tenant-id",
        "azure_client_id_key": "azure-sp-client-id",
        "azure_secret_key": "azure-sp-client-secret",
    }


class _FakeSecrets:
    def get(self, scope: str, key: str) -> str:
        return f"{scope}:{key}"


def _capture_ingested(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    captured: list[str] = []
    monkeypatch.setattr(
        entrypoint,
        "ingest_dbx_workspace",
        lambda _spark, *, curated_table, **_k: captured.append(("dbx_workspace", curated_table)),
    )
    monkeypatch.setattr(
        entrypoint,
        "ingest_business_application",
        lambda _spark, *, curated_table, **_k: captured.append(
            ("business_application", curated_table)
        ),
    )
    monkeypatch.setattr(
        entrypoint,
        "ingest_business_application_dim",
        lambda _spark, *, curated_table, **_k: captured.append(
            ("business_application_dim", curated_table)
        ),
    )
    return captured


def test_main_ingests_both_tables_when_table_param_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sans `--table` (debug local), les 3 tables sont ingerees, qualifiees UC.

    Azure doit etre configure ici : `business_application` /
    `business_application_dim` n'ont pas de source AWS et `main` refuse (FR-004)
    de les ingerer sans config Azure resolue.
    """
    captured = _capture_ingested(monkeypatch)

    entrypoint.main(spark=object(), secrets=_FakeSecrets(), params=_azure_params())

    prefix = "it.ba_data_connect_monitoring__d."
    assert captured == [
        ("dbx_workspace", prefix + specs.CURATED_DBX_WORKSPACE),
        ("business_application", prefix + specs.CURATED_BUSINESS_APPLICATION),
        ("business_application_dim", prefix + specs.CURATED_BUSINESS_APPLICATION_DIM),
    ]


def test_main_ingests_single_table_when_table_param_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--table` renseigne (iteration for_each) ⇒ une seule table ingeree."""
    captured = _capture_ingested(monkeypatch)
    params = _base_params() | {"table": specs.TABLE_DBX_WORKSPACE}

    entrypoint.main(spark=object(), secrets=object(), params=params)

    assert captured == [
        ("dbx_workspace", "it.ba_data_connect_monitoring__d." + specs.CURATED_DBX_WORKSPACE)
    ]


def test_main_raises_on_unknown_table(monkeypatch: pytest.MonkeyPatch) -> None:
    """Garde-fou : un `inputs` desynchronise du registre echoue explicitement."""
    monkeypatch.setattr(entrypoint, "ingest_dbx_workspace", lambda *_a, **_k: None)
    monkeypatch.setattr(entrypoint, "ingest_business_application", lambda *_a, **_k: None)
    params = _base_params() | {"table": "does_not_exist"}

    with pytest.raises(ValueError, match="Table inconnue"):
        entrypoint.main(spark=object(), secrets=object(), params=params)


def test_main_raises_when_catalog_or_schema_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Garde-fou : sans catalog/schema, on refuse d'ecrire (cible par defaut)."""
    monkeypatch.setattr(entrypoint, "ingest_dbx_workspace", lambda *_a, **_k: None)
    monkeypatch.setattr(entrypoint, "ingest_business_application", lambda *_a, **_k: None)
    params = _base_params() | {"schema": ""}

    with pytest.raises(ValueError, match="catalog"):
        entrypoint.main(spark=object(), secrets=object(), params=params)


def test_main_raises_when_business_application_selected_without_azure_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Garde-fou FR-004 : `business_application` sans config Azure ⇒ erreur explicite."""
    monkeypatch.setattr(entrypoint, "ingest_dbx_workspace", lambda *_a, **_k: None)
    called = []
    monkeypatch.setattr(
        entrypoint, "ingest_business_application", lambda *_a, **_k: called.append(True)
    )
    params = _base_params() | {"table": specs.TABLE_BUSINESS_APPLICATION}

    with pytest.raises(ValueError, match="business_application"):
        entrypoint.main(spark=object(), secrets=object(), params=params)

    assert called == []


def test_main_ingests_business_application_when_azure_config_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`business_application` selectionnee AVEC config Azure ⇒ ingestion normale."""
    captured = _capture_ingested(monkeypatch)
    params = _azure_params() | {"table": specs.TABLE_BUSINESS_APPLICATION}

    entrypoint.main(spark=object(), secrets=_FakeSecrets(), params=params)

    assert captured == [
        (
            "business_application",
            "it.ba_data_connect_monitoring__d." + specs.CURATED_BUSINESS_APPLICATION,
        )
    ]


def test_main_raises_when_business_application_dim_selected_without_azure_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Garde-fou FR-004 : `business_application_dim` sans config Azure ⇒ erreur."""
    monkeypatch.setattr(entrypoint, "ingest_dbx_workspace", lambda *_a, **_k: None)
    monkeypatch.setattr(entrypoint, "ingest_business_application", lambda *_a, **_k: None)
    called = []
    monkeypatch.setattr(
        entrypoint, "ingest_business_application_dim", lambda *_a, **_k: called.append(True)
    )
    params = _base_params() | {"table": specs.TABLE_BUSINESS_APPLICATION_DIM}

    with pytest.raises(ValueError, match="business_application_dim"):
        entrypoint.main(spark=object(), secrets=object(), params=params)

    assert called == []


def test_main_ingests_business_application_dim_when_azure_config_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`business_application_dim` AVEC config Azure ⇒ ingestion du catalogue BA."""
    captured = _capture_ingested(monkeypatch)
    params = _azure_params() | {"table": specs.TABLE_BUSINESS_APPLICATION_DIM}

    entrypoint.main(spark=object(), secrets=_FakeSecrets(), params=params)

    assert captured == [
        (
            "business_application_dim",
            "it.ba_data_connect_monitoring__d." + specs.CURATED_BUSINESS_APPLICATION_DIM,
        )
    ]


def test_debug_params_default_to_dev_catalog_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """En debug local, catalog/schema retombent sur la target dev par defaut."""
    for name in entrypoint.PARAM_NAMES:
        monkeypatch.delenv(f"DBG_{name.upper()}", raising=False)

    params = entrypoint._debug_params_from_env()

    assert params["catalog"] == specs.DEFAULT_CATALOG
    assert params["schema"] == specs.DEFAULT_SCHEMA
    # `table` vide par defaut ⇒ ingestion des 2 tables en debug.
    assert params["table"] == ""
