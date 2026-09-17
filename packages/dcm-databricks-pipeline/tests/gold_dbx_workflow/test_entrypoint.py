"""Tests de `pipelines.gold_dbx_workflow.entrypoint` (dispatch --table).

Verifie le cablage complet dispatch -> merge_into_table pour chaque table du
registre, avec un `spark`/`merge_into_table` factices (pas de vraie ecriture
Delta). Assertion principale : aucune table gold n'est ecrite sans que son
builder ait d'abord lu exclusivement les system tables lakeflow (memes stubs
que `test_bridges.py`/`test_builders.py`).
"""

from __future__ import annotations

import importlib

import pytest

from pipelines.gold_dbx_workflow.specs import GOLD_SPECS

_FORBIDDEN_SOURCES = ("curated_dbx_workflow_runs", "curated_dbx_workflow_task_runs")


@pytest.fixture
def entrypoint_module(wf_fakes, monkeypatch: pytest.MonkeyPatch):
    spark_stub, reads = wf_fakes
    merge_calls: list[dict] = []

    mod = importlib.import_module("pipelines.gold_dbx_workflow.entrypoint")

    def _fake_merge_into_table(spark, df, **kwargs):  # noqa: ANN001, ANN003, ANN202
        merge_calls.append(kwargs)

    monkeypatch.setattr(mod, "merge_into_table", _fake_merge_into_table)
    return mod, spark_stub, reads, merge_calls


@pytest.mark.parametrize("table", sorted(GOLD_SPECS))
def test_main_dispatches_each_table_and_never_reads_collector_tables(
    entrypoint_module, table: str
) -> None:
    mod, spark_stub, reads, merge_calls = entrypoint_module
    mod.main(
        spark_stub,
        {
            "table": table,
            "catalog": "it",
            "schema": "ba_data_connect_monitoring__d",
            "full_refresh": "",
            "one_off_purge": "",
        },
    )
    assert len(merge_calls) == 1
    assert merge_calls[0]["target_table"] == (
        f"it.ba_data_connect_monitoring__d.{GOLD_SPECS[table].target_table}"
    )
    for forbidden in _FORBIDDEN_SOURCES:
        assert forbidden not in reads


def test_main_rejects_unknown_table(entrypoint_module) -> None:
    mod, spark_stub, _reads, _merge_calls = entrypoint_module
    with pytest.raises(ValueError, match="inconnue"):
        mod.main(
            spark_stub,
            {
                "table": "not_a_real_table",
                "catalog": "it",
                "schema": "ba_data_connect_monitoring__d",
                "full_refresh": "",
                "one_off_purge": "",
            },
        )


def test_main_requires_catalog_and_schema(entrypoint_module) -> None:
    mod, spark_stub, _reads, _merge_calls = entrypoint_module
    with pytest.raises(ValueError, match="catalog"):
        mod.main(
            spark_stub,
            {
                "table": "success_rate",
                "catalog": "",
                "schema": "ba_data_connect_monitoring__d",
                "full_refresh": "",
                "one_off_purge": "",
            },
        )
