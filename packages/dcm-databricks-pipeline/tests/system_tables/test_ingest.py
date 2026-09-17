"""Tests de `pipelines.system_tables.ingest` (orchestration Azure ⊎ AWS -> curated).

Les fonctions du socle sont monkeypatchees sur le module CONSOMMATEUR (`ingest`)
car les imports absolus font que `ingest` detient sa propre reference globale
(`ingest.read_native_source`, `ingest.read_azure_batches`,
`ingest.compute_lower_bound`).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import pipelines.common.models as models
import pipelines.common.writers as writers
import pipelines.system_tables.ingest as ingest
import pipelines.system_tables.specs as specs


def test_ingest_unions_aws_and_azure_then_merges(
    fake_functions: None, fakes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    spark = fakes.Spark(existing_tables={specs.CURATED_BILLING_USAGE})
    aws_src = fakes.DataFrame("aws_src")
    azure_batch = fakes.DataFrame("azure_batch")

    monkeypatch.setattr(ingest, "compute_lower_bound", lambda *_a, **_k: None)
    monkeypatch.setattr(ingest, "read_native_source", lambda _s, _spec, _lb=None: aws_src)
    monkeypatch.setattr(ingest, "read_azure_batches", lambda *_a, **_k: iter([azure_batch]))

    ingest.ingest_system_table(
        spark,
        specs.BILLING_USAGE_SPEC,
        collection_run_id="run-1",
        collected_at="2026-07-30T00:00:00Z",
        azure_config=models.AzureConnectionConfig(
            host="h",
            http_path="p",
            tenant_id="t",
            client_id="c",
            client_secret="s",
        ),
    )

    # MERGE separes par cloud : un pour AWS, un pour le lot Azure (0 doublon).
    merges = [c for c in spark.sql_calls if c.startswith("MERGE WITH SCHEMA EVOLUTION INTO")]
    assert len(merges) == 2
    assert all(f"INTO {specs.BILLING_USAGE_SPEC.curated_table}" in m for m in merges)


def test_ingest_azure_stages_batches_then_single_merge(
    fake_functions: None, fakes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Azure : N lots ⇒ N append staging + 1 seul MERGE final + DROP du staging."""
    spark = fakes.Spark(existing_tables={specs.CURATED_BILLING_USAGE})
    aws_src = fakes.DataFrame("aws_src")
    batches = [fakes.DataFrame(f"azure_batch_{i}") for i in range(3)]

    monkeypatch.setattr(ingest, "compute_lower_bound", lambda *_a, **_k: None)
    monkeypatch.setattr(ingest, "read_native_source", lambda _s, _spec, _lb=None: aws_src)
    monkeypatch.setattr(ingest, "read_azure_batches", lambda *_a, **_k: iter(batches))

    ingest.ingest_system_table(
        spark,
        specs.BILLING_USAGE_SPEC,
        collection_run_id="run-1",
        collected_at="2026-07-30T00:00:00Z",
        azure_config=models.AzureConnectionConfig(
            host="h", http_path="p", tenant_id="t", client_id="c", client_secret="s"
        ),
    )

    staging = writers.staging_table_name(specs.BILLING_USAGE_SPEC.curated_table, "run-1")
    # Chaque lot est append vers le meme staging ; overwrite au 1er, append ensuite.
    assert all(b.saved_as == [staging] for b in batches)
    assert batches[0].write_modes == ["overwrite"]
    assert batches[1].write_modes == ["append"]
    assert batches[2].write_modes == ["append"]

    # Un seul MERGE Azure (depuis le staging) malgre les 3 lots.
    merges = [c for c in spark.sql_calls if c.startswith("MERGE WITH SCHEMA EVOLUTION INTO")]
    assert len(merges) == 2  # AWS + Azure(staging)
    # Le staging ephemere est toujours supprime en fin.
    assert f"DROP TABLE IF EXISTS {staging}" in spark.sql_calls


def test_ingest_aws_only_when_azure_disabled(
    fake_functions: None, fakes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    spark = fakes.Spark(existing_tables=set())
    aws_src = fakes.DataFrame("aws_src")
    azure_reader = MagicMock()

    monkeypatch.setattr(ingest, "compute_lower_bound", lambda *_a, **_k: None)
    monkeypatch.setattr(ingest, "read_native_source", lambda _s, _spec, _lb=None: aws_src)
    monkeypatch.setattr(ingest, "read_azure_batches", azure_reader)

    ingest.ingest_system_table(
        spark,
        specs.BILLING_LIST_PRICES_SPEC,
        collection_run_id="run-1",
        collected_at="2026-07-30T00:00:00Z",
        azure_config=None,
    )

    azure_reader.assert_not_called()
    assert aws_src.saved_as == [specs.BILLING_LIST_PRICES_SPEC.curated_table]


def test_ingest_skips_azure_when_source_empty(
    fake_functions: None, fakes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    spark = fakes.Spark(existing_tables=set())
    aws_src = fakes.DataFrame("aws_src")

    monkeypatch.setattr(ingest, "compute_lower_bound", lambda *_a, **_k: None)
    monkeypatch.setattr(ingest, "read_native_source", lambda _s, _spec, _lb=None: aws_src)
    monkeypatch.setattr(ingest, "read_azure_batches", lambda *_a, **_k: iter(()))

    ingest.ingest_system_table(
        spark,
        specs.BILLING_USAGE_SPEC,
        collection_run_id="run-1",
        collected_at="2026-07-30T00:00:00Z",
        azure_config=models.AzureConnectionConfig(
            host="h", http_path="p", tenant_id="t", client_id="c", client_secret="s"
        ),
    )

    # Azure vide ⇒ aucun MERGE Azure, AWS seul ecrit (table absente ⇒ saveAsTable).
    assert aws_src.saved_as == [specs.BILLING_USAGE_SPEC.curated_table]
    assert spark.sql_calls == []
