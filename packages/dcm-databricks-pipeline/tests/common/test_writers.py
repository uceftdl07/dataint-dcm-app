"""Tests de `pipelines.common.writers` (MERGE idempotent + staging)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import pipelines.common.writers as writers
import pipelines.system_tables.specs as specs

# ---------------------------------------------------------------------------
# Construction du MERGE
# ---------------------------------------------------------------------------


def test_build_merge_sql_is_idempotent_upsert() -> None:
    sql = writers.build_merge_sql(
        "it.ba_data_connect_monitoring__d.curated_dbx_billing_usage",
        "_stg_finops_merge_source",
        ("cloud_provider", "record_id"),
    )

    assert "MERGE WITH SCHEMA EVOLUTION INTO" in sql
    assert "it.ba_data_connect_monitoring__d.curated_dbx_billing_usage" in sql
    assert "ON t.cloud_provider <=> s.cloud_provider AND t.record_id <=> s.record_id" in sql
    assert "WHEN MATCHED THEN UPDATE SET *" in sql
    assert "WHEN NOT MATCHED THEN INSERT *" in sql


def test_build_merge_sql_rejects_empty_keys() -> None:
    with pytest.raises(ValueError, match="merge_keys"):
        writers.build_merge_sql("t", "s", ())


def test_build_merge_sql_has_no_delete_clause_by_default() -> None:
    # Upsert pur : correct pour une serie temporelle (un jour deja ecrit reste
    # vrai), et garantit qu'aucun appelant existant ne se met a supprimer.
    sql = writers.build_merge_sql("t", "s", ("id",))

    assert "WHEN NOT MATCHED BY SOURCE" not in sql
    assert "DELETE" not in sql


def test_build_merge_sql_deletes_absent_rows_only_under_the_given_predicate() -> None:
    # Snapshot d'etat courant : sans clause DELETE, la table accumule
    # indefiniment les objets disparus. Le predicat sert de garde-fou (seules
    # les lignes anciennes sont supprimables) pour qu'un run degrade -- source
    # vide ou partielle -- ne puisse pas vider la table.
    sql = writers.build_merge_sql(
        "it.sch.gold_dbx_compute_cluster_governance",
        "_stg_src",
        ("cloud_provider", "workspace_id", "cluster_id"),
        None,
        "t._generated_at < date_add(current_date(), -7)",
    )

    assert "WHEN MATCHED THEN UPDATE SET *" in sql
    assert "WHEN NOT MATCHED THEN INSERT *" in sql
    assert (
        "WHEN NOT MATCHED BY SOURCE AND "
        "(t._generated_at < date_add(current_date(), -7)) THEN DELETE" in sql
    )


# ---------------------------------------------------------------------------
# merge_into_table — creation puis upsert
# ---------------------------------------------------------------------------


def test_merge_creates_table_on_first_run(fakes: SimpleNamespace) -> None:
    spark = fakes.Spark(existing_tables=set())
    df = fakes.DataFrame("unified")

    writers.merge_into_table(
        spark,
        df,
        target_table="curated_dbx_billing_usage",
        merge_keys=("cloud_provider", "record_id"),
    )

    assert df.saved_as == ["curated_dbx_billing_usage"]
    assert spark.sql_calls == []


def test_merge_upserts_on_existing_table(fakes: SimpleNamespace) -> None:
    spark = fakes.Spark(existing_tables={"curated_dbx_billing_usage"})
    df = fakes.DataFrame("unified")

    writers.merge_into_table(
        spark,
        df,
        target_table="curated_dbx_billing_usage",
        merge_keys=("cloud_provider", "record_id"),
    )

    assert df.saved_as == []
    assert df.temp_views == ["_stg_merge_source__curated_dbx_billing_usage"]
    assert len(spark.sql_calls) == 1
    assert spark.sql_calls[0].startswith("MERGE WITH SCHEMA EVOLUTION INTO")
    assert "curated_dbx_billing_usage" in spark.sql_calls[0]


def test_merge_partitions_table_on_first_run(fakes: SimpleNamespace) -> None:
    spark = fakes.Spark(existing_tables=set())
    df = fakes.DataFrame("unified")

    writers.merge_into_table(
        spark,
        df,
        target_table=specs.BILLING_USAGE_SPEC.curated_table,
        merge_keys=specs.BILLING_USAGE_SPEC.merge_keys,
        partition_columns=specs.BILLING_USAGE_SPEC.partition_columns,
    )

    assert df.saved_as == [specs.BILLING_USAGE_SPEC.curated_table]
    assert df.partitioned_by == ["usage_date"]


def test_merge_applies_partition_predicate_on_upsert(fakes: SimpleNamespace) -> None:
    spark = fakes.Spark(existing_tables={specs.BILLING_USAGE_SPEC.curated_table})
    df = fakes.DataFrame("unified")

    writers.merge_into_table(
        spark,
        df,
        target_table=specs.BILLING_USAGE_SPEC.curated_table,
        merge_keys=specs.BILLING_USAGE_SPEC.merge_keys,
        partition_columns=specs.BILLING_USAGE_SPEC.partition_columns,
        partition_predicate="t.usage_date >= DATE '2026-07-25'",
    )

    assert "AND t.usage_date >= DATE '2026-07-25'" in spark.sql_calls[0]


def test_merge_threads_absent_row_delete_predicate_to_the_merge(fakes: SimpleNamespace) -> None:
    spark = fakes.Spark(existing_tables={"gold_dbx_compute_cluster_governance"})
    df = fakes.DataFrame("governance")

    writers.merge_into_table(
        spark,
        df,
        target_table="gold_dbx_compute_cluster_governance",
        merge_keys=("cloud_provider", "workspace_id", "cluster_id"),
        absent_row_delete_predicate="t._generated_at < date_add(current_date(), -7)",
    )

    assert (
        "WHEN NOT MATCHED BY SOURCE AND "
        "(t._generated_at < date_add(current_date(), -7)) THEN DELETE" in spark.sql_calls[0]
    )


def test_merge_source_view_name_avoids_collision_between_target_tables(
    fakes: SimpleNamespace,
) -> None:
    # La vue temporaire source du MERGE est derivee de `target_table` (pas un
    # nom fixe partage) : deux tables cibles differentes ne doivent jamais
    # produire la meme vue, meme dans la meme session Spark.
    spark = fakes.Spark(existing_tables={"it.sch.table_a", "it.sch.table_b"})

    writers.merge_into_table(
        spark,
        fakes.DataFrame("a"),
        target_table="it.sch.table_a",
        merge_keys=("id",),
    )
    df_b = fakes.DataFrame("b")
    writers.merge_into_table(
        spark,
        df_b,
        target_table="it.sch.table_b",
        merge_keys=("id",),
    )

    assert df_b.temp_views == ["_stg_merge_source__it_sch_table_b"]
    assert "it_sch_table_a" not in df_b.temp_views[0]


# ---------------------------------------------------------------------------
# Nom de la table de staging
# ---------------------------------------------------------------------------


def test_merge_deduplicates_source_on_merge_keys(fakes: SimpleNamespace) -> None:
    spark = fakes.Spark(existing_tables={"curated_dbx_billing_usage"})
    df = fakes.DataFrame("unified")

    writers.merge_into_table(
        spark,
        df,
        target_table="curated_dbx_billing_usage",
        merge_keys=("cloud_provider", "record_id"),
    )

    assert df.deduplicated_on == ["cloud_provider", "record_id"]


# ---------------------------------------------------------------------------
# Commentaires de table/colonnes (visibles dans Catalog Explorer)
# ---------------------------------------------------------------------------


def test_merge_attaches_table_and_column_comments_on_creation(fakes: SimpleNamespace) -> None:
    spark = fakes.Spark(existing_tables=set())
    df = fakes.DataFrame("unified")

    writers.merge_into_table(
        spark,
        df,
        target_table="gold_dbx_compute_cluster_cost_daily",
        merge_keys=("cloud_provider", "cluster_id"),
        table_comment="FinOps clusters : cout quotidien.",
        column_comments={"cost_usd": "Cout total en dollars ce jour-la."},
    )

    assert df.saved_as == ["gold_dbx_compute_cluster_cost_daily"]
    assert (
        "COMMENT ON TABLE gold_dbx_compute_cluster_cost_daily IS "
        "'FinOps clusters : cout quotidien.'" in spark.sql_calls
    )
    assert (
        "ALTER TABLE gold_dbx_compute_cluster_cost_daily ALTER COLUMN cost_usd "
        "COMMENT 'Cout total en dollars ce jour-la.'" in spark.sql_calls
    )


def test_merge_escapes_single_quotes_in_comments(fakes: SimpleNamespace) -> None:
    spark = fakes.Spark(existing_tables=set())
    df = fakes.DataFrame("unified")

    writers.merge_into_table(
        spark,
        df,
        target_table="t",
        merge_keys=("id",),
        table_comment="Cluster's cost table",
    )

    assert "COMMENT ON TABLE t IS 'Cluster''s cost table'" in spark.sql_calls[0]


def test_merge_reapplies_comments_on_existing_table(fakes: SimpleNamespace) -> None:
    # Operation de metadonnees pure (aucun scan), reappliquee a chaque run (pas
    # seulement a la creation) : permet aux tables deja existantes (creees
    # avant l'ajout de cette fonctionnalite) de recevoir leurs commentaires au
    # prochain run planifie, sans script de backfill dedie.
    spark = fakes.Spark(existing_tables={"gold_dbx_compute_cluster_cost_daily"})
    df = fakes.DataFrame("unified")

    writers.merge_into_table(
        spark,
        df,
        target_table="gold_dbx_compute_cluster_cost_daily",
        merge_keys=("cloud_provider", "cluster_id"),
        table_comment="FinOps clusters : cout quotidien.",
        column_comments={"cost_usd": "Cout total en dollars ce jour-la."},
    )

    assert spark.sql_calls[0].startswith("MERGE WITH SCHEMA EVOLUTION INTO")
    assert (
        "COMMENT ON TABLE gold_dbx_compute_cluster_cost_daily IS "
        "'FinOps clusters : cout quotidien.'" in spark.sql_calls
    )
    assert (
        "ALTER TABLE gold_dbx_compute_cluster_cost_daily ALTER COLUMN cost_usd "
        "COMMENT 'Cout total en dollars ce jour-la.'" in spark.sql_calls
    )
    assert spark.sql_calls[0].startswith("MERGE WITH SCHEMA EVOLUTION INTO")


def test_staging_table_name_sanitizes_run_id() -> None:
    name = writers.staging_table_name("it.sch.curated_x", "local-debug/abc.1")
    assert name == "it.sch.curated_x__stg_local_debug_abc_1"


# ---------------------------------------------------------------------------
# non_cloud_merge_keys / build_purge_merge_sql / purge_rows_not_in_source
# (T001, 020-purge-curated-full-load)
# ---------------------------------------------------------------------------


def test_non_cloud_merge_keys_strips_cloud_provider() -> None:
    assert writers.non_cloud_merge_keys(("cloud_provider", "a", "b")) == ("a", "b")
    assert writers.non_cloud_merge_keys(("a", "b")) == ("a", "b")
    assert writers.non_cloud_merge_keys(("cloud_provider",)) == ()


def test_build_purge_merge_sql_deletes_unmatched_rows_for_cloud_only() -> None:
    sql = writers.build_purge_merge_sql(
        "it.sch.curated_dbx_uc_tables",
        "_stg_src",
        specs.UC_TABLES_SPEC.merge_keys,
        "aws",
    )

    assert sql.startswith("MERGE INTO it.sch.curated_dbx_uc_tables AS t")
    assert "ON t.table_catalog <=> s.table_catalog" in sql
    # cloud_provider n'est jamais compare cote source (colonne d'enveloppe,
    # absente d'une lecture BRUTE de la table system.* source).
    assert "s.cloud_provider" not in sql
    assert "t.cloud_provider = 'aws'" in sql
    assert "WHEN NOT MATCHED BY SOURCE AND t.cloud_provider = 'aws' THEN DELETE" in sql


def test_build_purge_merge_sql_rejects_cloud_provider_only_keys() -> None:
    with pytest.raises(ValueError, match="merge_keys"):
        writers.build_purge_merge_sql("t", "s", ("cloud_provider",), "aws")


def test_purge_rows_not_in_source_creates_view_and_runs_delete_merge(
    fakes: SimpleNamespace,
) -> None:
    spark = fakes.Spark()
    df = fakes.DataFrame("source")

    writers.purge_rows_not_in_source(
        spark,
        df,
        target_table="curated_dbx_uc_tables",
        merge_keys=specs.UC_TABLES_SPEC.merge_keys,
        cloud_provider="azure",
    )

    assert df.temp_views == ["_stg_merge_source__curated_dbx_uc_tables__purge"]
    assert len(spark.sql_calls) == 1
    assert spark.sql_calls[0].startswith("MERGE INTO curated_dbx_uc_tables AS t")
    assert (
        "WHEN NOT MATCHED BY SOURCE AND t.cloud_provider = 'azure' THEN DELETE"
        in spark.sql_calls[0]
    )
