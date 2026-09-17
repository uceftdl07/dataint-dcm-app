"""Tests de `pipelines.system_tables.purge_entrypoint` (cablage + selection + qualification UC).

`purge_absent_rows`/`write_purge_audit_record` sont monkeypatches sur le module
`purge_entrypoint` (import absolu ⇒ reference globale propre au module
consommateur), meme convention que `tests/system_tables/test_entrypoint.py`.
"""

from __future__ import annotations

from typing import Any

import pytest

import pipelines.common.models as models
import pipelines.common.purge as purge
import pipelines.system_tables.purge_entrypoint as purge_entrypoint
import pipelines.system_tables.specs as specs

_ENABLED_CURATED_TABLES = (
    "curated_dbx_uc_tables",
    "curated_dbx_uc_table_tags",
    "curated_dbx_compute_node_types",
    "curated_dbx_billing_list_prices",
)


def _base_params() -> dict[str, str]:
    """Params nommes minimaux valides pour `main` (Azure desactive, toutes tables)."""
    return dict.fromkeys(purge_entrypoint.PARAM_NAMES, "") | {
        "catalog": "it",
        "schema": "ba_data_connect_monitoring__d",
        "collection_run_id": "run-1",
        "collected_at": "2026-09-01T00:00:00Z",
    }


def _capture_purge_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, bool]]:
    """Remplace `purge_absent_rows` : capture (curated_table, cloud, dry_run)."""
    calls: list[tuple[str, str, bool]] = []

    def _fake_purge_absent_rows(
        _spark: Any, spec: Any, cloud_provider: str, **kwargs: Any  # noqa: ANN401
    ) -> purge.PurgeAuditRecord:
        calls.append((spec.curated_table, cloud_provider, bool(kwargs["dry_run"])))
        return purge.PurgeAuditRecord(
            collection_run_id="run-1",
            curated_table=spec.curated_table,
            cloud_provider=cloud_provider,
            run_mode="dry_run" if kwargs["dry_run"] else "real",
            rows_in_source=0,
            rows_in_curated_before=0,
            rows_to_delete=0,
            rows_deleted=0,
            guardrail_breached=False,
            threshold_absolute=int(kwargs["threshold_absolute"]),
            threshold_percentage=float(kwargs["threshold_percentage"]),
            started_at="s",
            finished_at="f",
            collected_at="2026-09-01T00:00:00Z",
        )

    monkeypatch.setattr(purge_entrypoint, "purge_absent_rows", _fake_purge_absent_rows)
    return calls


def _silence_audit_writes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    writes: list[str] = []
    monkeypatch.setattr(
        purge_entrypoint,
        "write_purge_audit_record",
        lambda _spark, audit_table, _record: writes.append(audit_table),
    )
    return writes


def test_main_purges_all_enabled_tables_aws_only_when_azure_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _capture_purge_calls(monkeypatch)
    audit_writes = _silence_audit_writes(monkeypatch)

    purge_entrypoint.main(spark=object(), secrets=object(), params=_base_params())

    prefix = "it.ba_data_connect_monitoring__d."
    assert {c[0] for c in calls} == {prefix + table for table in _ENABLED_CURATED_TABLES}
    assert all(cloud == "aws" for _table, cloud, _dry_run in calls)
    assert all(dry_run is False for _table, _cloud, dry_run in calls)
    assert audit_writes == [prefix + "curated_dbx_purge_audit_log"] * len(calls)


def test_main_purges_single_table_when_table_param_set(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_purge_calls(monkeypatch)
    _silence_audit_writes(monkeypatch)
    params = _base_params() | {"table": "uc_tables"}

    purge_entrypoint.main(spark=object(), secrets=object(), params=params)

    assert calls == [("it.ba_data_connect_monitoring__d.curated_dbx_uc_tables", "aws", False)]


def test_main_purges_aws_and_azure_when_azure_config_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _capture_purge_calls(monkeypatch)
    _silence_audit_writes(monkeypatch)
    monkeypatch.setattr(
        purge_entrypoint,
        "_read_azure_config",
        lambda *_a, **_k: models.AzureConnectionConfig(
            host="h", http_path="p", tenant_id="t", client_id="c", client_secret="s"
        ),
    )
    params = _base_params() | {"table": "uc_tables"}

    purge_entrypoint.main(spark=object(), secrets=object(), params=params)

    assert [cloud for _table, cloud, _dry_run in calls] == ["aws", "azure"]


def test_dry_run_param_true_is_parsed_as_boolean(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_purge_calls(monkeypatch)
    _silence_audit_writes(monkeypatch)
    params = _base_params() | {"table": "uc_tables", "dry_run": "true"}

    purge_entrypoint.main(spark=object(), secrets=object(), params=params)

    assert calls[0][2] is True


def test_dry_run_param_defaults_to_false(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture_purge_calls(monkeypatch)
    _silence_audit_writes(monkeypatch)
    params = _base_params() | {"table": "uc_tables"}

    purge_entrypoint.main(spark=object(), secrets=object(), params=params)

    assert calls[0][2] is False


def test_main_raises_on_table_not_in_purge_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    # `billing_usage` est une cle VALIDE du socle d'ingestion (specs.SPECS) mais
    # PAS du registre opt-in de purge (incrementale, jamais activee) : garde-fou.
    monkeypatch.setattr(purge_entrypoint, "purge_absent_rows", lambda *_a, **_k: None)
    params = _base_params() | {"table": "billing_usage"}

    with pytest.raises(ValueError, match="non activee pour la purge"):
        purge_entrypoint.main(spark=object(), secrets=object(), params=params)


def test_main_raises_when_catalog_or_schema_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(purge_entrypoint, "purge_absent_rows", lambda *_a, **_k: None)
    params = _base_params() | {"schema": ""}

    with pytest.raises(ValueError, match="catalog"):
        purge_entrypoint.main(spark=object(), secrets=object(), params=params)


def test_debug_params_default_to_dev_catalog_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in purge_entrypoint.PARAM_NAMES:
        monkeypatch.delenv(f"DBG_{name.upper()}", raising=False)

    params = purge_entrypoint._debug_params_from_env()

    assert params["catalog"] == specs.DEFAULT_CATALOG
    assert params["schema"] == specs.DEFAULT_SCHEMA
    # `table` vide par defaut ⇒ purge de toutes les tables activees en debug.
    assert params["table"] == ""
