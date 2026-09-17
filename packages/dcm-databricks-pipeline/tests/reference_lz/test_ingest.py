"""Tests de `pipelines.reference_lz.ingest` (orchestration bespoke AWS ⊎ Azure -> curated).

Les fonctions du socle sont monkeypatchees sur le module CONSOMMATEUR (`ingest`),
meme convention que `tests/system_tables/test_ingest.py`. `dedupe_by_key` /
`filter_null_or_empty_key` sont deja testees isolement dans
`tests/common/test_transforms.py` : ici on stubbe leur passthrough pour ne
verifier que le CABLAGE (renommage par cloud, staging, MERGE), pas leur
semantique interne.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import pipelines.common.models as models
import pipelines.common.writers as writers
import pipelines.reference_lz.ingest as ingest


@pytest.fixture(autouse=True)
def _stub_f_and_primitives(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub `F` (pas de JVM) + passthrough des 2 primitives dedup/filtre."""
    stub_f = SimpleNamespace(
        lit=lambda value: ("lit", value),
        to_timestamp=lambda value: ("to_timestamp", value),
    )
    monkeypatch.setattr(ingest, "F", stub_f)
    monkeypatch.setattr(ingest, "filter_null_or_empty_key", lambda df, *_keys: df)
    monkeypatch.setattr(ingest, "dedupe_by_key", lambda df, _keys: df)


def _azure_config() -> models.AzureConnectionConfig:
    return models.AzureConnectionConfig(
        host="h", http_path="p", tenant_id="t", client_id="c", client_secret="s"
    )


# ---------------------------------------------------------------------------
# dim_reference_landing_zone_dbx_workspace
# ---------------------------------------------------------------------------


def test_ingest_dbx_workspace_aws_only_renames_and_merges(
    fakes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    curated_table = "dim_reference_landing_zone_dbx_workspace"
    spark = fakes.Spark(existing_tables=set())
    aws_src = fakes.DataFrame(
        "aws_src", columns=["workspace_id", "workspace_name", "aws_account_id", "cloud"]
    )
    monkeypatch.setattr(ingest, "read_native_source", lambda _s, _spec: aws_src)

    ingest.ingest_dbx_workspace(
        spark,
        curated_table=curated_table,
        azure_config=None,
        collection_run_id="run-1",
        collected_at="2026-08-20T00:00:00Z",
    )

    assert aws_src.distinct_called is True
    assert aws_src.renamed_columns == [
        ("aws_account_id", "subscription_or_account_id"),
        ("cloud", "cloud_provider"),
    ]
    assert "updated_at" in [name for name, _ in aws_src.added_columns]
    # Table absente ⇒ creation directe (saveAsTable), pas de MERGE.
    assert aws_src.saved_as == [curated_table]
    assert spark.sql_calls == []


def test_ingest_dbx_workspace_azure_batches_stage_then_merge(
    fakes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    curated_table = "dim_reference_landing_zone_dbx_workspace"
    spark = fakes.Spark(existing_tables={curated_table})
    aws_src = fakes.DataFrame(
        "aws_src", columns=["workspace_id", "workspace_name", "aws_account_id", "cloud"]
    )
    azure_batches = [
        fakes.DataFrame(
            f"azure_batch_{i}",
            columns=["workspace_id", "workspace_name", "subscription_id", "cloud"],
        )
        for i in range(2)
    ]
    staged_df = fakes.DataFrame("staged")
    spark.read.table.return_value = staged_df

    monkeypatch.setattr(ingest, "read_native_source", lambda _s, _spec: aws_src)
    monkeypatch.setattr(ingest, "read_azure_batches", lambda *_a, **_k: iter(azure_batches))

    ingest.ingest_dbx_workspace(
        spark,
        curated_table=curated_table,
        azure_config=_azure_config(),
        collection_run_id="run-1",
        collected_at="2026-08-20T00:00:00Z",
    )

    for batch in azure_batches:
        assert batch.distinct_called is True
        assert batch.renamed_columns == [
            ("subscription_id", "subscription_or_account_id"),
            ("cloud", "cloud_provider"),
        ]

    staging = writers.staging_table_name(curated_table, "run-1")
    assert azure_batches[0].saved_as == [staging]
    assert azure_batches[0].write_modes == ["overwrite"]
    assert azure_batches[1].saved_as == [staging]
    assert azure_batches[1].write_modes == ["append"]

    # 1 MERGE AWS + 1 MERGE Azure (depuis le staging) malgre les 2 lots.
    merges = [c for c in spark.sql_calls if c.startswith("MERGE WITH SCHEMA EVOLUTION INTO")]
    assert len(merges) == 2
    assert all(f"INTO {curated_table}" in m for m in merges)
    # Le staging ephemere est toujours supprime en fin.
    assert f"DROP TABLE IF EXISTS {staging}" in spark.sql_calls


def test_ingest_dbx_workspace_skips_azure_when_config_none(
    fakes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    spark = fakes.Spark(existing_tables=set())
    aws_src = fakes.DataFrame(
        "aws_src", columns=["workspace_id", "workspace_name", "aws_account_id", "cloud"]
    )
    azure_reader = MagicMock()

    monkeypatch.setattr(ingest, "read_native_source", lambda _s, _spec: aws_src)
    monkeypatch.setattr(ingest, "read_azure_batches", azure_reader)

    ingest.ingest_dbx_workspace(
        spark,
        curated_table="dim_reference_landing_zone_dbx_workspace",
        azure_config=None,
        collection_run_id="run-1",
        collected_at="2026-08-20T00:00:00Z",
    )

    azure_reader.assert_not_called()


def test_ingest_dbx_workspace_skips_merge_when_azure_source_empty(
    fakes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    curated_table = "dim_reference_landing_zone_dbx_workspace"
    spark = fakes.Spark(existing_tables=set())
    aws_src = fakes.DataFrame(
        "aws_src", columns=["workspace_id", "workspace_name", "aws_account_id", "cloud"]
    )

    monkeypatch.setattr(ingest, "read_native_source", lambda _s, _spec: aws_src)
    monkeypatch.setattr(ingest, "read_azure_batches", lambda *_a, **_k: iter(()))

    ingest.ingest_dbx_workspace(
        spark,
        curated_table=curated_table,
        azure_config=_azure_config(),
        collection_run_id="run-1",
        collected_at="2026-08-20T00:00:00Z",
    )

    # Azure vide ⇒ aucun MERGE (AWS ecrit seul par saveAsTable, table absente).
    assert aws_src.saved_as == [curated_table]
    assert spark.sql_calls == []


# ---------------------------------------------------------------------------
# dim_reference_landing_zone_business_application
# ---------------------------------------------------------------------------


def test_ingest_business_application_stages_batches_then_merges(
    fakes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    curated_table = "dim_reference_landing_zone_business_application"
    spark = fakes.Spark(existing_tables={curated_table})
    azure_batches = [
        fakes.DataFrame(
            "ba_batch", columns=["name", "ba_id", "lz_id", "cloud"]
        )
    ]
    staged_df = fakes.DataFrame("staged")
    spark.read.table.return_value = staged_df

    monkeypatch.setattr(ingest, "read_azure_batches", lambda *_a, **_k: iter(azure_batches))

    ingest.ingest_business_application(
        spark,
        curated_table=curated_table,
        azure_config=_azure_config(),
        collection_run_id="run-1",
        collected_at="2026-08-20T00:00:00Z",
    )

    batch = azure_batches[0]
    assert batch.distinct_called is True
    assert batch.renamed_columns == [
        ("name", "business_application_name"),
        ("ba_id", "business_application_id"),
        ("lz_id", "subscription_or_account_id"),
        ("cloud", "cloud_provider"),
    ]
    staging = writers.staging_table_name(curated_table, "run-1")
    assert batch.saved_as == [staging]
    merges = [c for c in spark.sql_calls if c.startswith("MERGE WITH SCHEMA EVOLUTION INTO")]
    assert len(merges) == 1
    assert f"INTO {curated_table}" in merges[0]
    assert f"DROP TABLE IF EXISTS {staging}" in spark.sql_calls


def test_ingest_business_application_no_merge_when_source_empty(
    fakes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    spark = fakes.Spark(existing_tables=set())
    monkeypatch.setattr(ingest, "read_azure_batches", lambda *_a, **_k: iter(()))

    ingest.ingest_business_application(
        spark,
        curated_table="dim_reference_landing_zone_business_application",
        azure_config=_azure_config(),
        collection_run_id="run-1",
        collected_at="2026-08-20T00:00:00Z",
    )

    assert spark.sql_calls == []


# ---------------------------------------------------------------------------
# dim_business_application
# ---------------------------------------------------------------------------


def test_ingest_business_application_dim_projects_ba_and_merges(
    fakes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    curated_table = "dim_business_application"
    spark = fakes.Spark(existing_tables={curated_table})
    azure_batches = [fakes.DataFrame("ba_dim_batch", columns=["name", "ba_id"])]
    staged_df = fakes.DataFrame("staged")
    spark.read.table.return_value = staged_df

    monkeypatch.setattr(ingest, "read_azure_batches", lambda *_a, **_k: iter(azure_batches))

    ingest.ingest_business_application_dim(
        spark,
        curated_table=curated_table,
        azure_config=_azure_config(),
        collection_run_id="run-1",
        collected_at="2026-08-20T00:00:00Z",
    )

    batch = azure_batches[0]
    assert batch.distinct_called is True
    # Seuls name/ba_id renommes (pas de lz_id/cloud : catalogue BA distinct).
    assert batch.renamed_columns == [
        ("name", "business_application_name"),
        ("ba_id", "business_application_id"),
    ]
    staging = writers.staging_table_name(curated_table, "run-1")
    assert batch.saved_as == [staging]
    merges = [c for c in spark.sql_calls if c.startswith("MERGE WITH SCHEMA EVOLUTION INTO")]
    assert len(merges) == 1
    assert f"INTO {curated_table}" in merges[0]
    assert f"DROP TABLE IF EXISTS {staging}" in spark.sql_calls


def test_ingest_business_application_dim_no_merge_when_source_empty(
    fakes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    spark = fakes.Spark(existing_tables=set())
    monkeypatch.setattr(ingest, "read_azure_batches", lambda *_a, **_k: iter(()))

    ingest.ingest_business_application_dim(
        spark,
        curated_table="dim_business_application",
        azure_config=_azure_config(),
        collection_run_id="run-1",
        collected_at="2026-08-20T00:00:00Z",
    )

    assert spark.sql_calls == []
