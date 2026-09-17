"""Tests de `pipelines.common.purge` (mecanisme generique de purge full-load).

Meme convention que `tests/system_tables/test_ingest.py` : les fonctions du
socle (`read_native_source`, `read_azure_batches`) sont monkeypatchees sur le
module CONSOMMATEUR (`purge`), pas de vraie `SparkSession` (coherent avec
`tests/conftest.py`).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import pipelines.common.models as models
import pipelines.common.purge as purge
import pipelines.common.writers as writers
import pipelines.system_tables.specs as specs

UC_TABLES_MERGE_KEYS = specs.UC_TABLES_SPEC.merge_keys

# ---------------------------------------------------------------------------
# _guardrail_breached — garde-fou volumetrique pur (seuil le plus restrictif)
# ---------------------------------------------------------------------------


def test_guardrail_breached_retains_the_most_restrictive_threshold() -> None:
    # percentage_limit = 1000 * 0.5 = 500 ; absolute = 100 -> effective = 100.
    assert (
        purge._guardrail_breached(
            rows_to_delete=150,
            rows_in_curated_before=1000,
            threshold_absolute=100,
            threshold_percentage=0.5,
        )
        is True
    )
    assert (
        purge._guardrail_breached(
            rows_to_delete=80,
            rows_in_curated_before=1000,
            threshold_absolute=100,
            threshold_percentage=0.5,
        )
        is False
    )


def test_guardrail_not_breached_when_nothing_to_delete() -> None:
    assert (
        purge._guardrail_breached(
            rows_to_delete=0,
            rows_in_curated_before=0,
            threshold_absolute=1000,
            threshold_percentage=0.2,
        )
        is False
    )


# ---------------------------------------------------------------------------
# _count_*_sql — 3 requetes INDEPENDANTES (jamais combinees dans un seul
# SELECT : evite la collision d'exprId Catalyst constatee en execution reelle,
# cf. docstring de _count_rows_to_delete_sql), anti-join pousse en SQL,
# cloud_provider exclu de la comparaison source (colonne d'enveloppe absente
# d'une lecture brute)
# ---------------------------------------------------------------------------


def test_count_rows_in_source_sql() -> None:
    sql = purge._count_rows_in_source_sql("_stg_src")
    assert sql == "SELECT COUNT(*) AS n FROM _stg_src"


def test_count_rows_in_curated_sql() -> None:
    sql = purge._count_rows_in_curated_sql("it.sch.curated_dbx_uc_tables", "aws")
    assert "it.sch.curated_dbx_uc_tables" in sql
    assert "cloud_provider = 'aws'" in sql


def test_count_rows_to_delete_sql_excludes_cloud_provider_from_source_comparison() -> None:
    sql = purge._count_rows_to_delete_sql(
        "it.sch.curated_dbx_uc_tables", "_stg_src", UC_TABLES_MERGE_KEYS, "aws"
    )

    assert "s.cloud_provider" not in sql
    assert "t.table_catalog <=> s.table_catalog" in sql
    assert "cloud_provider = 'aws'" in sql
    assert "NOT EXISTS" in sql


# ---------------------------------------------------------------------------
# purge_absent_rows — table curated absente (tout premier run)
# ---------------------------------------------------------------------------


def test_purge_absent_rows_returns_zero_record_when_curated_table_missing(
    fakes: SimpleNamespace,
) -> None:
    spark = fakes.Spark(existing_tables=set())

    record = purge.purge_absent_rows(
        spark,
        specs.UC_TABLES_SPEC,
        "aws",
        collection_run_id="run-1",
        collected_at="2026-09-01T00:00:00Z",
        threshold_absolute=1000,
        threshold_percentage=0.20,
    )

    assert record.rows_in_source == 0
    assert record.rows_in_curated_before == 0
    assert record.rows_to_delete == 0
    assert record.rows_deleted == 0
    assert record.guardrail_breached is False
    assert record.run_mode == "real"
    assert spark.sql_calls == []


# ---------------------------------------------------------------------------
# purge_absent_rows — AWS natif, garde-fou non franchi -> suppression reelle
# ---------------------------------------------------------------------------


def test_purge_absent_rows_deletes_when_under_guardrail(
    fakes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = specs.UC_TABLES_SPEC
    sql_results = [
        SimpleNamespace(collect=lambda: [{"n": 100}]),
        SimpleNamespace(collect=lambda: [{"n": 105}]),
        SimpleNamespace(collect=lambda: [{"n": 5}]),
    ]
    spark = fakes.Spark(existing_tables={spec.curated_table}, sql_result=sql_results)
    source_df = fakes.DataFrame("uc_tables_source")
    monkeypatch.setattr(purge, "read_native_source", lambda _s, _spec: source_df)

    record = purge.purge_absent_rows(
        spark,
        spec,
        "aws",
        collection_run_id="run-1",
        collected_at="2026-09-01T00:00:00Z",
        threshold_absolute=1000,
        threshold_percentage=0.20,
    )

    assert record.rows_to_delete == 5
    assert record.rows_deleted == 5
    assert record.guardrail_breached is False
    delete_merges = [c for c in spark.sql_calls if "WHEN NOT MATCHED BY SOURCE" in c]
    assert len(delete_merges) == 1
    assert f"INTO {spec.curated_table}" in delete_merges[0]


# ---------------------------------------------------------------------------
# purge_absent_rows — garde-fou franchi -> aucune suppression, anomalie tracee
# ---------------------------------------------------------------------------


def test_purge_absent_rows_skips_delete_when_guardrail_breached(
    fakes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = specs.UC_TABLES_SPEC
    # effective_limit = min(1000, 1000 * 0.20 = 200) = 200 ; 900 > 200 -> breche.
    sql_results = [
        SimpleNamespace(collect=lambda: [{"n": 10}]),
        SimpleNamespace(collect=lambda: [{"n": 1000}]),
        SimpleNamespace(collect=lambda: [{"n": 900}]),
    ]
    spark = fakes.Spark(existing_tables={spec.curated_table}, sql_result=sql_results)
    source_df = fakes.DataFrame("uc_tables_source")
    monkeypatch.setattr(purge, "read_native_source", lambda _s, _spec: source_df)

    record = purge.purge_absent_rows(
        spark,
        spec,
        "aws",
        collection_run_id="run-1",
        collected_at="2026-09-01T00:00:00Z",
        threshold_absolute=1000,
        threshold_percentage=0.20,
    )

    assert record.guardrail_breached is True
    assert record.rows_deleted == 0
    assert not any("WHEN NOT MATCHED BY SOURCE" in c for c in spark.sql_calls)


# ---------------------------------------------------------------------------
# purge_absent_rows — dry_run=True : calcule + trace, jamais de DELETE reel
# ---------------------------------------------------------------------------


def test_purge_absent_rows_dry_run_never_deletes(
    fakes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = specs.UC_TABLES_SPEC
    sql_results = [
        SimpleNamespace(collect=lambda: [{"n": 100}]),
        SimpleNamespace(collect=lambda: [{"n": 105}]),
        SimpleNamespace(collect=lambda: [{"n": 5}]),
    ]
    spark = fakes.Spark(existing_tables={spec.curated_table}, sql_result=sql_results)
    source_df = fakes.DataFrame("uc_tables_source")
    monkeypatch.setattr(purge, "read_native_source", lambda _s, _spec: source_df)

    record = purge.purge_absent_rows(
        spark,
        spec,
        "aws",
        collection_run_id="run-1",
        collected_at="2026-09-01T00:00:00Z",
        threshold_absolute=1000,
        threshold_percentage=0.20,
        dry_run=True,
    )

    assert record.run_mode == "dry_run"
    assert record.rows_to_delete == 5
    assert record.rows_deleted == 0
    assert not any("WHEN NOT MATCHED BY SOURCE" in c for c in spark.sql_calls)


# ---------------------------------------------------------------------------
# purge_absent_rows — idempotence : rejouer sur un etat deja purge est un no-op
# ---------------------------------------------------------------------------


def test_purge_absent_rows_is_noop_when_already_purged(
    fakes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = specs.UC_TABLES_SPEC
    sql_results = [
        SimpleNamespace(collect=lambda: [{"n": 100}]),
        SimpleNamespace(collect=lambda: [{"n": 100}]),
        SimpleNamespace(collect=lambda: [{"n": 0}]),
    ]
    spark = fakes.Spark(existing_tables={spec.curated_table}, sql_result=sql_results)
    source_df = fakes.DataFrame("uc_tables_source")
    monkeypatch.setattr(purge, "read_native_source", lambda _s, _spec: source_df)

    record = purge.purge_absent_rows(
        spark,
        spec,
        "aws",
        collection_run_id="run-2",
        collected_at="2026-09-01T00:00:00Z",
        threshold_absolute=1000,
        threshold_percentage=0.20,
    )

    assert record.rows_to_delete == 0
    assert record.rows_deleted == 0
    assert record.guardrail_breached is False
    assert not any("WHEN NOT MATCHED BY SOURCE" in c for c in spark.sql_calls)


# ---------------------------------------------------------------------------
# purge_absent_rows — Azure sans source disponible -> garde-fou force (jamais
# de suppression a l'aveugle)
# ---------------------------------------------------------------------------


def test_purge_absent_rows_forces_breach_when_azure_config_absent(
    fakes: SimpleNamespace,
) -> None:
    spec = specs.UC_TABLES_SPEC
    curated_count_row = SimpleNamespace(collect=lambda: [{"n": 42}])
    spark = fakes.Spark(existing_tables={spec.curated_table}, sql_result=curated_count_row)

    record = purge.purge_absent_rows(
        spark,
        spec,
        "azure",
        collection_run_id="run-1",
        collected_at="2026-09-01T00:00:00Z",
        threshold_absolute=1000,
        threshold_percentage=0.20,
        azure_config=None,
    )

    assert record.rows_in_source == 0
    assert record.rows_in_curated_before == 42
    assert record.rows_to_delete == 42
    assert record.rows_deleted == 0
    assert record.guardrail_breached is True


# ---------------------------------------------------------------------------
# purge_absent_rows — Azure : lots bornes stages puis relus, staging supprime
# ---------------------------------------------------------------------------


def test_purge_absent_rows_azure_stages_batches_then_drops_staging(
    fakes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = specs.UC_TABLES_SPEC
    sql_results = [
        SimpleNamespace(collect=lambda: [{"n": 3}]),
        SimpleNamespace(collect=lambda: [{"n": 3}]),
        SimpleNamespace(collect=lambda: [{"n": 0}]),
    ]
    spark = fakes.Spark(existing_tables={spec.curated_table}, sql_result=sql_results)
    batches = [fakes.DataFrame(f"azure_batch_{i}") for i in range(2)]
    monkeypatch.setattr(purge, "read_azure_batches", lambda *_a, **_k: iter(batches))
    config = models.AzureConnectionConfig(
        host="h", http_path="p", tenant_id="t", client_id="c", client_secret="s"
    )

    record = purge.purge_absent_rows(
        spark,
        spec,
        "azure",
        collection_run_id="run-1",
        collected_at="2026-09-01T00:00:00Z",
        threshold_absolute=1000,
        threshold_percentage=0.20,
        azure_config=config,
    )

    staging = writers.staging_table_name(spec.curated_table, "purge_run-1")
    assert all(b.saved_as == [staging] for b in batches)
    assert batches[0].write_modes == ["overwrite"]
    assert batches[1].write_modes == ["append"]
    assert f"DROP TABLE IF EXISTS {staging}" in spark.sql_calls
    assert record.rows_to_delete == 0
