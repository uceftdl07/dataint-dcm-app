"""Tests de `pipelines.gold_dbx_compute.total_cost_daily` (regles de derivation).

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`) :
`build_total_cost_daily` construit un unique `spark.sql(...)`, verifie ici via
le texte SQL genere (`FakeSpark`).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from pipelines.gold_dbx_compute.total_cost_daily import build_total_cost_daily

_CLUSTER = "it.sch.gold_dbx_compute_cluster_cost_daily"
_WAREHOUSE = "it.sch.gold_dbx_compute_warehouse_cost_daily"
_JOB = "it.sch.gold_dbx_compute_job_cluster_cost_daily"
_PIPELINE = "it.sch.gold_dbx_compute_pipeline_cost_daily"
_SERVERLESS = "it.sch.gold_dbx_compute_serverless_cost_daily"
_WORKSPACE_REF = "it.sch.dim_reference_landing_zone_dbx_workspace"
_DIM_LZ = "it.sch.dim_landing_zone"


def _total_cost_query(fakes: SimpleNamespace, *, lower_bound: date | None = None) -> str:
    sentinel = fakes.DataFrame("total_cost_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_total_cost_daily(
        spark,
        cluster_cost_daily_table=_CLUSTER,
        warehouse_cost_daily_table=_WAREHOUSE,
        job_cluster_cost_daily_table=_JOB,
        pipeline_cost_daily_table=_PIPELINE,
        serverless_cost_daily_table=_SERVERLESS,
        dbx_workspace_reference_table=_WORKSPACE_REF,
        dim_landing_zone_table=_DIM_LZ,
        lower_bound=lower_bound,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0]


def test_total_cost_daily_reads_only_the_five_gold_daily_tables_no_curated(
    fakes: SimpleNamespace,
) -> None:
    # Aucune relecture de la facturation curated : les 5 tables sources sont
    # deja des gold quotidiennes deduplicables telles quelles.
    query = _total_cost_query(fakes)
    for table in (_CLUSTER, _WAREHOUSE, _JOB, _PIPELINE, _SERVERLESS):
        assert table in query
    assert "curated_" not in query


def test_total_cost_daily_restricts_cluster_to_all_purpose_only(
    fakes: SimpleNamespace,
) -> None:
    # JOB/PIPELINE cluster types sont deja dans job_cluster_cost_daily /
    # pipeline_cost_daily (billing-direct) : les inclure ici doublerait ce cout.
    query = _total_cost_query(fakes)
    assert f"FROM {_CLUSTER}\n        WHERE cluster_type = 'ALL_PURPOSE'" in query


def test_total_cost_daily_excludes_surfaces_already_covered_elsewhere(
    fakes: SimpleNamespace,
) -> None:
    # JOB/DLT_PIPELINE/SQL_WAREHOUSE surfaces sont deja comptees via
    # job_cluster_cost_daily / pipeline_cost_daily / warehouse_cost_daily.
    query = _total_cost_query(fakes)
    assert (
        "WHERE serverless_surface NOT IN ('JOB', 'DLT_PIPELINE', 'SQL_WAREHOUSE')" in query
    )


def test_total_cost_daily_keeps_warehouse_and_job_and_pipeline_unfiltered(
    fakes: SimpleNamespace,
) -> None:
    # warehouse_cost_daily / job_cluster_cost_daily / pipeline_cost_daily sont
    # deja la tranche complete qui leur appartient en propre (pas de WHERE de
    # double-comptage a leur appliquer).
    query = _total_cost_query(fakes)
    assert f"FROM {_WAREHOUSE}\n        WHERE 1 = 1" in query
    assert f"FROM {_JOB}\n        WHERE 1 = 1" in query
    assert f"FROM {_PIPELINE}\n        WHERE 1 = 1" in query


def test_total_cost_daily_sums_per_workspace_and_day_not_per_object(
    fakes: SimpleNamespace,
) -> None:
    # Grain (cloud_provider, workspace_id, period_start) : SUM apres UNION ALL,
    # pas un simple UNION preservant le detail par objet.
    query = _total_cost_query(fakes)
    assert "SUM(cost_usd) AS cost_usd" in query
    assert "GROUP BY cloud_provider, workspace_id, period_start" in query


def test_total_cost_daily_full_refresh_has_no_period_filter(
    fakes: SimpleNamespace,
) -> None:
    query = _total_cost_query(fakes, lower_bound=None)
    assert "period_start >=" not in query


def test_total_cost_daily_incremental_filters_all_five_sources_on_lower_bound(
    fakes: SimpleNamespace,
) -> None:
    query = _total_cost_query(fakes, lower_bound=date(2026, 8, 1))
    assert query.count("AND period_start >= DATE '2026-08-01'") == 5


def test_total_cost_daily_resolves_lz_id_and_ba_name_via_workspace_reference(
    fakes: SimpleNamespace,
) -> None:
    # workspace_id -> subscription_or_account_id (workspace_ref) -> lz_id +
    # business_application_name (dim_landing_zone), pas de relecture curated.
    query = _total_cost_query(fakes)
    assert _WORKSPACE_REF in query
    assert _DIM_LZ in query
    assert "lz.lz_id" in query
    assert "lz.business_application_name AS ba_name" in query


def test_total_cost_daily_left_joins_lz_reference_keeping_cost_rows_without_match(
    fakes: SimpleNamespace,
) -> None:
    # LEFT JOIN des deux cotes : un workspace sans reference ou sans LZ/BA
    # associee garde sa ligne de cout (lz_id/ba_name NULL), pas exclu.
    query = _total_cost_query(fakes)
    assert "LEFT JOIN workspace_ref wr ON wr.workspace_id = t.workspace_id" in query
    assert f"LEFT JOIN {_DIM_LZ} lz" in query
    assert "ON lz.subscription_or_account_id = wr.subscription_or_account_id" in query


def test_total_cost_daily_dedups_workspace_reference_to_one_row_per_workspace(
    fakes: SimpleNamespace,
) -> None:
    # Precaution meme si la source est deja a cette grain (comme les
    # `*_as_of` d'autres builders de ce module).
    query = _total_cost_query(fakes)
    assert (
        "QUALIFY ROW_NUMBER() OVER (\n"
        "            PARTITION BY workspace_id ORDER BY updated_at DESC\n"
        "        ) = 1" in query
    )
