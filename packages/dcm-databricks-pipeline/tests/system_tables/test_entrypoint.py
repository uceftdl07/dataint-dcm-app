"""Tests de `pipelines.system_tables.entrypoint` (cablage + selection + qualification UC).

`ingest_system_table` est monkeypatche sur le module `entrypoint` (import absolu
⇒ reference globale propre au module consommateur).
"""

from __future__ import annotations

import pytest

import pipelines.system_tables.entrypoint as entrypoint
import pipelines.system_tables.specs as specs


def _base_params() -> dict[str, str]:
    """Params nommes minimaux valides pour `main` (Azure desactive, toutes tables)."""
    return dict.fromkeys(entrypoint.PARAM_NAMES, "") | {
        "catalog": "it",
        "schema": "ba_data_connect_monitoring__d",
        "collection_run_id": "run-1",
        "collected_at": "2026-07-30T00:00:00Z",
        "lookback_days": "3",
    }


def _capture_ingested(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    captured: list[str] = []
    monkeypatch.setattr(
        entrypoint,
        "ingest_system_table",
        lambda _spark, spec, **_k: captured.append(spec.curated_table),
    )
    return captured


def test_main_ingests_all_tables_when_table_param_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sans `--table` (debug local), toutes les tables sont ingerees, qualifiees UC."""
    captured = _capture_ingested(monkeypatch)

    entrypoint.main(spark=object(), secrets=object(), params=_base_params())

    prefix = "it.ba_data_connect_monitoring__d."
    assert captured == [prefix + spec.curated_table for spec in specs.SPECS.values()]
    # Les specs module-level ne sont pas mutees (dataclasses.replace ⇒ copie).
    assert specs.BILLING_USAGE_SPEC.curated_table == "curated_dbx_billing_usage"


def test_main_ingests_single_table_when_table_param_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--table` renseigne (iteration for_each) ⇒ une seule table ingeree."""
    captured = _capture_ingested(monkeypatch)
    params = _base_params() | {"table": "access_audit"}

    entrypoint.main(spark=object(), secrets=object(), params=params)

    assert captured == ["it.ba_data_connect_monitoring__d.curated_dbx_access_audit"]


def test_main_raises_on_unknown_table(monkeypatch: pytest.MonkeyPatch) -> None:
    """Garde-fou : un `inputs` desynchronise du registre echoue explicitement."""
    monkeypatch.setattr(entrypoint, "ingest_system_table", lambda *_a, **_k: None)
    params = _base_params() | {"table": "does_not_exist"}

    with pytest.raises(ValueError, match="Table inconnue"):
        entrypoint.main(spark=object(), secrets=object(), params=params)


def test_main_raises_when_catalog_or_schema_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Garde-fou : sans catalog/schema, on refuse d'ecrire (cible par defaut)."""
    monkeypatch.setattr(entrypoint, "ingest_system_table", lambda *_a, **_k: None)
    params = _base_params() | {"schema": ""}

    with pytest.raises(ValueError, match="catalog"):
        entrypoint.main(spark=object(), secrets=object(), params=params)


def test_debug_params_default_to_dev_catalog_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """En debug local, catalog/schema retombent sur la target dev par defaut."""
    for name in entrypoint.PARAM_NAMES:
        monkeypatch.delenv(f"DBG_{name.upper()}", raising=False)

    params = entrypoint._debug_params_from_env()

    assert params["catalog"] == specs.DEFAULT_CATALOG
    assert params["schema"] == specs.DEFAULT_SCHEMA
    # `table` vide par defaut ⇒ ingestion de toutes les tables en debug.
    assert params["table"] == ""
