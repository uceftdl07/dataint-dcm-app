"""Tests de `pipelines.gold_dbx_compute.entrypoint` (fenetre + dispatch + ecriture).

Regles de fenetre couvertes ici :
1er run (table cible absente) => fenetre `full` (aucun filtre curated) ; run
suivant (table cible presente) => fenetre incrementale ancree sur la couverture
reelle de la table cible (au plus `today - incremental_lookback_days`, elargie
s'il manque un jour) ; `governance` (sans watermark) toujours `full`, quel que
soit l'etat de la table cible.

Un run suivant emet donc DEUX requetes : le scan de couverture de la table cible
(`compute_gap_aware_lower_bound`) puis la requete du builder. Les fakes fournis
via `sql_result` suivent cet ordre.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import pipelines.common.incremental as incremental
import pipelines.gold_dbx_compute.entrypoint as entrypoint
import pipelines.gold_dbx_compute.specs as specs
from tests.conftest import gap_scan_row

TODAY = date(2026, 8, 17)
NOMINAL_BOUND = TODAY - timedelta(days=specs.INCREMENTAL_LOOKBACK_DAYS)


def _gap_scan_row(
    *,
    last_day: date | None = TODAY,
    first_missing_day: date | None = None,
    first_unsettled_day: date | None = None,
) -> SimpleNamespace:
    """Scan de couverture avec, par defaut, une couverture continue jusqu'a `TODAY`.

    La FORME de la ligne vient de `tests.conftest.gap_scan_row` ; ce wrapper ne fixe
    que le defaut propre a ces tests : aucun trou, aucun jour non stabilise, dernier
    jour ecrit = `TODAY`, donc la fenetre nominale s'applique.
    """
    return gap_scan_row(
        last_day=last_day,
        first_missing_day=first_missing_day,
        first_unsettled_day=first_unsettled_day,
    )


def test_resolve_lower_bound_is_none_on_first_run(fakes: SimpleNamespace) -> None:
    spark = fakes.Spark(existing_tables=set())
    lower_bound = entrypoint._resolve_lower_bound(
        spark,
        specs.CLUSTER_COST_DAILY_SPEC,
        "it.sch.gold_dbx_compute_cluster_cost_daily",
        full_refresh=False,
        today=TODAY,
    )
    assert lower_bound is None


def test_resolve_lower_bound_is_incremental_window_on_subsequent_run(
    fakes: SimpleNamespace,
) -> None:
    target = "it.sch.gold_dbx_compute_cluster_cost_daily"
    spark = fakes.Spark(existing_tables={target}, sql_result=[_gap_scan_row()])
    lower_bound = entrypoint._resolve_lower_bound(
        spark,
        specs.CLUSTER_COST_DAILY_SPEC,
        target,
        full_refresh=False,
        today=TODAY,
    )
    assert lower_bound == NOMINAL_BOUND


def test_resolve_lower_bound_widens_the_window_down_to_a_missing_day(
    fakes: SimpleNamespace,
) -> None:
    # Un jour qu'aucun run n'a couvert dans sa fenetre sort de la fenetre
    # nominale le lendemain : cale sur `today`, il ne serait PLUS JAMAIS
    # recalcule (trou permanent, et fenetres glissantes qui sous-comptent). Le
    # recalcul repart donc du trou -- et pas seulement du jour manquant, les
    # jours qui le SUIVENT ayant ete calcules sur une source incomplete.
    target = "it.sch.gold_dbx_compute_cluster_cost_daily"
    hole = date(2026, 8, 4)
    spark = fakes.Spark(
        existing_tables={target},
        sql_result=[_gap_scan_row(first_missing_day=hole)],
    )
    lower_bound = entrypoint._resolve_lower_bound(
        spark,
        specs.CLUSTER_COST_DAILY_SPEC,
        target,
        full_refresh=False,
        today=TODAY,
    )
    assert lower_bound == hole
    assert lower_bound < NOMINAL_BOUND


def test_resolve_lower_bound_recomputes_the_last_written_day(
    fakes: SimpleNamespace,
) -> None:
    # Trou de QUEUE (pipeline arretee plusieurs semaines) : la fenetre nominale ne
    # couvrirait que ses N derniers jours et laisserait un trou definitif entre le
    # dernier jour ecrit et elle. La reprise inclut ce dernier jour LUI-MEME : il
    # a ete ecrit alors que curated etait encore en train d'arriver.
    target = "it.sch.gold_dbx_compute_cluster_cost_daily"
    last_written = date(2026, 7, 20)
    spark = fakes.Spark(
        existing_tables={target},
        sql_result=[_gap_scan_row(last_day=last_written)],
    )
    lower_bound = entrypoint._resolve_lower_bound(
        spark,
        specs.CLUSTER_COST_DAILY_SPEC,
        target,
        full_refresh=False,
        today=TODAY,
    )
    assert lower_bound == last_written


def test_resolve_lower_bound_recomputes_days_written_before_they_settled(
    fakes: SimpleNamespace,
) -> None:
    # Jour ecrit AVANT que la source curated ait absorbe ses arrivees tardives
    # (run trop precoce, pipeline reprise en cours de journee) : present mais
    # sous-compte, il est recalcule au lieu d'etre considere comme acquis.
    target = "it.sch.gold_dbx_compute_cluster_cost_daily"
    # Anterieur a la fenetre nominale : sinon c'est elle qui fixe la borne et le
    # test ne demontre plus l'elargissement.
    unsettled = date(2026, 8, 4)
    spark = fakes.Spark(
        existing_tables={target},
        sql_result=[_gap_scan_row(first_unsettled_day=unsettled)],
    )
    lower_bound = entrypoint._resolve_lower_bound(
        spark,
        specs.CLUSTER_COST_DAILY_SPEC,
        target,
        full_refresh=False,
        today=TODAY,
    )
    assert lower_bound == unsettled
    assert lower_bound < NOMINAL_BOUND


def test_resolve_lower_bound_scans_the_target_table_on_its_watermark(
    fakes: SimpleNamespace,
) -> None:
    # Le scan de couverture porte sur la table CIBLE (gold) et sa colonne de
    # watermark, avec la colonne d'horodatage d'ecriture commune aux tables gold.
    target = "it.sch.gold_dbx_compute_cluster_cost_daily"
    spark = fakes.Spark(existing_tables={target}, sql_result=[_gap_scan_row()])
    entrypoint._resolve_lower_bound(
        spark,
        specs.CLUSTER_COST_DAILY_SPEC,
        target,
        full_refresh=False,
        today=TODAY,
    )
    assert len(spark.sql_calls) == 1
    scan = spark.sql_calls[0]
    assert f"FROM {target}" in scan
    assert "to_date(period_start) AS day" in scan
    assert f"MAX({entrypoint.GENERATED_AT_COLUMN}) AS last_written_at" in scan


def test_resolve_lower_bound_ignores_a_hole_older_than_the_detection_window(
    fakes: SimpleNamespace,
) -> None:
    # La detection est bornee (cf. DEFAULT_GAP_DETECTION_WINDOW_DAYS) pour que le
    # cout du scan reste stable : le plancher d'inspection figure dans le SQL, un
    # trou plus ancien ne se repare que par `--full-refresh`.
    target = "it.sch.gold_dbx_compute_cluster_cost_daily"
    spark = fakes.Spark(existing_tables={target}, sql_result=[_gap_scan_row()])
    entrypoint._resolve_lower_bound(
        spark,
        specs.CLUSTER_COST_DAILY_SPEC,
        target,
        full_refresh=False,
        today=TODAY,
    )
    floor = TODAY - timedelta(days=incremental.DEFAULT_GAP_DETECTION_WINDOW_DAYS)
    assert f">= DATE '{floor.isoformat()}'" in spark.sql_calls[0]


def test_resolve_lower_bound_full_refresh_forces_full_even_if_target_exists(
    fakes: SimpleNamespace,
) -> None:
    target = "it.sch.gold_dbx_compute_cluster_cost_daily"
    spark = fakes.Spark(existing_tables={target})
    lower_bound = entrypoint._resolve_lower_bound(
        spark,
        specs.CLUSTER_COST_DAILY_SPEC,
        target,
        full_refresh=True,
        today=TODAY,
    )
    assert lower_bound is None


def test_resolve_lower_bound_governance_is_always_full(fakes: SimpleNamespace) -> None:
    target = "it.sch.gold_dbx_compute_cluster_governance"
    spark = fakes.Spark(existing_tables={target})
    lower_bound = entrypoint._resolve_lower_bound(
        spark,
        specs.CLUSTER_GOVERNANCE_SPEC,
        target,
        full_refresh=False,
        today=TODAY,
    )
    assert lower_bound is None


def test_main_requires_catalog_and_schema(fakes: SimpleNamespace) -> None:
    spark = fakes.Spark()
    with pytest.raises(ValueError, match="catalog"):
        entrypoint.main(spark, {"table": "cluster_cost_daily", "catalog": "", "schema": ""})


def test_main_rejects_unknown_table(fakes: SimpleNamespace) -> None:
    spark = fakes.Spark()
    with pytest.raises(ValueError, match="inconnue"):
        entrypoint.main(
            spark, {"table": "not_a_table", "catalog": "it", "schema": "sch"}
        )


def test_main_requires_warehouse_id_for_forecast_daily(fakes: SimpleNamespace) -> None:
    # ai_forecast exige un SQL Warehouse, incompatible avec l'environnement
    # serverless generique de ce job - warehouse_id est donc obligatoire pour
    # cette table uniquement (pas pour les 7 autres).
    spark = fakes.Spark()
    with pytest.raises(ValueError, match="warehouse_id"):
        entrypoint.main(
            spark, {"table": "forecast_daily", "catalog": "it", "schema": "sch"}
        )


def test_main_forecast_daily_threads_pipeline_cost_daily_table(
    fakes: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # forecast_daily passe par la Statement Execution API (pas spark.sql), donc
    # on capture les kwargs du builder pour verifier que la source PIPELINE
    # (gold_dbx_compute_pipeline_cost_daily) est bien cablee - grain
    # dlt_pipeline_id, cf. T001d.
    captured: dict[str, object] = {}

    def _capture(spark: object, **kwargs: object) -> object:
        captured.update(kwargs)
        return fakes.DataFrame("forecast_result")

    monkeypatch.setattr(entrypoint, "build_compute_forecast", _capture)
    spark = fakes.Spark(existing_tables=set())
    entrypoint.main(
        spark,
        {
            "table": "forecast_daily",
            "catalog": "it",
            "schema": "sch",
            "warehouse_id": "wh1",
        },
    )
    assert (
        captured["pipeline_cost_daily_table"]
        == "it.sch.gold_dbx_compute_pipeline_cost_daily"
    )
    assert (
        captured["job_cluster_cost_daily_table"]
        == "it.sch.gold_dbx_compute_job_cluster_cost_daily"
    )


def test_main_first_run_reads_curated_without_window_filter(fakes: SimpleNamespace) -> None:
    result_df = fakes.DataFrame("cost_daily_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(spark, {"table": "cluster_cost_daily", "catalog": "it", "schema": "sch"})
    build_query = spark.sql_calls[0]
    assert "usage_date >= DATE" not in build_query
    # Table cible absente => creation directe (saveAsTable), pas de MERGE.
    assert "it.sch.gold_dbx_compute_cluster_cost_daily" in result_df.saved_as


def test_main_subsequent_run_reads_curated_with_incremental_window(
    fakes: SimpleNamespace,
) -> None:
    target = "it.sch.gold_dbx_compute_cluster_cost_daily"
    result_df = fakes.DataFrame("cost_daily_result")
    # `main` cale sa fenetre nominale sur la date du jour reelle : la couverture
    # du fake est volontairement tres ancienne, pour que la borne observee ne
    # puisse venir que du scan de couverture, quelle que soit cette date.
    last_written = date(2026, 8, 1)
    spark = fakes.Spark(
        existing_tables={target},
        # 1er appel : scan de couverture de la table cible ; 2e : requete builder.
        sql_result=[_gap_scan_row(last_day=last_written), result_df],
    )
    entrypoint.main(spark, {"table": "cluster_cost_daily", "catalog": "it", "schema": "sch"})
    build_query = spark.sql_calls[1]
    assert "AND usage_date >= DATE" in build_query
    # La borne vient de la COUVERTURE de la table cible, pas de `today - lookback`
    # (qui laisserait definitif tout jour jamais couvert) : le fake s'arretant au
    # 2026-08-01, la sortie repart de ce jour-la (inclus, il est le moins stabilise).
    assert "AND period_start >= DATE '2026-08-01'" in build_query
    # Table cible presente => MERGE (appel spark.sql suivant le build).
    assert any("MERGE" in call for call in spark.sql_calls[2:])


def test_main_upsert_only_by_default_never_deletes_time_series_rows(
    fakes: SimpleNamespace,
) -> None:
    # Une table `*_daily` est une serie temporelle : un jour deja ecrit reste
    # vrai meme s'il sort de la fenetre recalculee. Aucune clause de suppression
    # ne doit donc apparaitre dans son MERGE.
    target = "it.sch.gold_dbx_compute_cluster_cost_daily"
    result_df = fakes.DataFrame("cost_daily_result")
    spark = fakes.Spark(existing_tables={target}, sql_result=[_gap_scan_row(), result_df])
    entrypoint.main(spark, {"table": "cluster_cost_daily", "catalog": "it", "schema": "sch"})
    merges = [call for call in spark.sql_calls if call.startswith("MERGE")]
    assert merges
    assert all("WHEN NOT MATCHED BY SOURCE" not in call for call in merges)


def test_main_governance_snapshot_merge_deletes_rows_out_of_scope(
    fakes: SimpleNamespace,
) -> None:
    # Snapshot borne dans le temps : sans suppression des lignes absentes du
    # recalcul, la table conserverait indefiniment les clusters sortis de la
    # fenetre (les clusters JOB/PIPELINE etant ephemeres, un cluster_id par
    # execution). Le predicat de grace protege les lignes recemment rafraichies.
    target = "it.sch.gold_dbx_compute_cluster_governance"
    # `row_count=1` : la suppression n'est armee que si le builder produit
    # quelque chose (un run degrade ne doit pas vider la table).
    result_df = fakes.DataFrame("governance_result", row_count=1)
    spark = fakes.Spark(existing_tables={target}, sql_result=result_df)
    entrypoint.main(spark, {"table": "cluster_governance", "catalog": "it", "schema": "sch"})
    merges = [call for call in spark.sql_calls if call.startswith("MERGE")]
    assert len(merges) == 1
    assert (
        "WHEN NOT MATCHED BY SOURCE AND (t._generated_at < date_add(current_date(), "
        f"-{specs.SNAPSHOT_ABSENT_ROW_GRACE_DAYS})) THEN DELETE" in merges[0]
    )


def test_main_governance_scope_is_bounded_by_the_activity_window(
    fakes: SimpleNamespace,
) -> None:
    result_df = fakes.DataFrame("governance_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(spark, {"table": "cluster_governance", "catalog": "it", "schema": "sch"})
    build_query = spark.sql_calls[0]
    assert "WHERE period_start >= DATE" in build_query
    assert "OR lc.change_time >= DATE" in build_query


def test_main_full_refresh_param_forces_full_window(fakes: SimpleNamespace) -> None:
    target = "it.sch.gold_dbx_compute_cluster_cost_daily"
    result_df = fakes.DataFrame("cost_daily_result")
    spark = fakes.Spark(existing_tables={target}, sql_result=result_df)
    entrypoint.main(
        spark,
        {
            "table": "cluster_cost_daily",
            "catalog": "it",
            "schema": "sch",
            "full_refresh": "true",
        },
    )
    build_query = spark.sql_calls[0]
    assert "usage_date >= DATE" not in build_query


# --- T003 : dispatch des 3 tables gold SQL Warehouses ------------------------


def test_main_dispatches_warehouse_cost_daily(fakes: SimpleNamespace) -> None:
    result_df = fakes.DataFrame("warehouse_cost_daily_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(
        spark, {"table": "warehouse_cost_daily", "catalog": "it", "schema": "sch"}
    )
    build_query = spark.sql_calls[0]
    assert "usage_metadata.warehouse_id IS NOT NULL" in build_query
    assert "it.sch.gold_dbx_compute_warehouse_cost_daily" in result_df.saved_as


def test_main_dispatches_warehouse_utilization_daily(fakes: SimpleNamespace) -> None:
    result_df = fakes.DataFrame("warehouse_utilization_daily_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(
        spark, {"table": "warehouse_utilization_daily", "catalog": "it", "schema": "sch"}
    )
    build_query = spark.sql_calls[0]
    assert "it.sch.gold_dbx_compute_warehouse_cost_daily" in build_query
    assert "it.sch.gold_dbx_compute_warehouse_utilization_daily" in result_df.saved_as


def test_main_dispatches_warehouse_query_performance_daily(fakes: SimpleNamespace) -> None:
    result_df = fakes.DataFrame("warehouse_query_performance_daily_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(
        spark,
        {"table": "warehouse_query_performance_daily", "catalog": "it", "schema": "sch"},
    )
    build_query = spark.sql_calls[0]
    assert "compute.warehouse_id IS NOT NULL" in build_query
    assert (
        "it.sch.gold_dbx_compute_warehouse_query_performance_daily" in result_df.saved_as
    )


def test_main_passes_curated_warehouses_to_query_performance_daily(
    fakes: SimpleNamespace,
) -> None:
    """Le builder recoit `warehouses_table` resolu depuis catalog/schema du run.

    `warehouse_name` (spec 023 T001) est resolu en gold : sans ce parametre le
    builder ne peut pas joindre `curated_dbx_compute_warehouses`. Le nom qualifie
    doit venir de la constante de table resolue avec le catalog/schema passes en
    parametres de la tache, jamais d'un litteral code en dur.
    """
    result_df = fakes.DataFrame("warehouse_query_performance_daily_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(
        spark,
        {"table": "warehouse_query_performance_daily", "catalog": "it", "schema": "sch"},
    )
    build_query = spark.sql_calls[0]
    assert "LEFT JOIN it.sch.curated_dbx_compute_warehouses w" in build_query


def test_main_passes_curated_job_run_timeline_to_job_cluster_cost_daily(
    fakes: SimpleNamespace,
) -> None:
    """Le builder recoit `job_run_timeline_table` resolu depuis catalog/schema du run.

    C'est la seule source du nom d'un run soumis (`jobs/runs/submit`), qui n'a
    aucune ligne dans `curated_dbx_lakeflow_jobs`. Le nom qualifie doit venir de
    la constante deja utilisee par les autres tables curated lakeflow, resolue
    avec le catalog/schema de la tache -- jamais d'un litteral code en dur.
    """
    result_df = fakes.DataFrame("job_cluster_cost_daily_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(
        spark, {"table": "job_cluster_cost_daily", "catalog": "it", "schema": "sch"}
    )
    build_query = spark.sql_calls[0]
    assert "FROM it.sch.curated_dbx_lakeflow_job_run_timeline r" in build_query
    assert entrypoint.CURATED_LAKEFLOW_JOB_RUN_TIMELINE == "curated_dbx_lakeflow_job_run_timeline"


def test_main_wires_job_cluster_cost_daily_to_curated_billing_not_to_the_gold_table(
    fakes: SimpleNamespace,
) -> None:
    # T001b : le dispatch doit passer la facturation curated (+ ses prix), et plus
    # `gold_dbx_compute_cluster_cost_daily` ni la lignee
    # `job_task_run_timeline`. Un recablage partiel (nouvelle signature, ancienne
    # source) leverait un TypeError ici, pas en production.
    result_df = fakes.DataFrame("job_cluster_cost_daily_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(spark, {"table": "job_cluster_cost_daily", "catalog": "it", "schema": "sch"})
    build_query = spark.sql_calls[0]
    assert "FROM it.sch.curated_dbx_billing_usage" in build_query
    assert "FROM it.sch.curated_dbx_billing_list_prices" in build_query
    assert "usage_metadata.job_id IS NOT NULL" in build_query
    assert "gold_dbx_compute_cluster_cost_daily" not in build_query
    assert "curated_dbx_lakeflow_job_task_run_timeline" not in build_query
    assert "it.sch.gold_dbx_compute_job_cluster_cost_daily" in result_df.saved_as


# --- T001c : dispatch des 2 tables gold pipelines DLT ------------------------


def test_main_dispatches_pipeline_cost_daily(fakes: SimpleNamespace) -> None:
    # Rollup BILLING-DIRECT : le builder lit la facturation curated filtree sur
    # usage_metadata.dlt_pipeline_id (pas de resolution via clusters) et ecrit la
    # table gold pipeline_cost_daily.
    result_df = fakes.DataFrame("pipeline_cost_daily_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(
        spark, {"table": "pipeline_cost_daily", "catalog": "it", "schema": "sch"}
    )
    build_query = spark.sql_calls[0]
    assert "usage_metadata.dlt_pipeline_id IS NOT NULL" in build_query
    assert "it.sch.curated_dbx_lakeflow_pipelines" in build_query
    assert "it.sch.gold_dbx_compute_pipeline_cost_daily" in result_df.saved_as


def test_main_dispatches_pipeline_cost_rolling(fakes: SimpleNamespace) -> None:
    # Rollup pur : lit UNIQUEMENT la table quotidienne gold pipeline_cost_daily.
    result_df = fakes.DataFrame("pipeline_cost_rolling_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(
        spark, {"table": "pipeline_cost_rolling", "catalog": "it", "schema": "sch"}
    )
    build_query = spark.sql_calls[0]
    assert "it.sch.gold_dbx_compute_pipeline_cost_daily" in build_query
    assert "it.sch.gold_dbx_compute_pipeline_cost_rolling" in result_df.saved_as


# --- T004 : dispatch des 4 tables gold efficacite job / pipeline -------------


def test_main_dispatches_job_efficiency_daily(fakes: SimpleNamespace) -> None:
    # Source = cluster_efficiency_daily (clusters JOB), PAS les tables de cout,
    # + les 3 tables curated de resolution du grain job et de son nom.
    result_df = fakes.DataFrame("job_efficiency_daily_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(
        spark, {"table": "job_efficiency_daily", "catalog": "it", "schema": "sch"}
    )
    build_query = spark.sql_calls[0]
    assert "FROM it.sch.gold_dbx_compute_cluster_efficiency_daily ce" in build_query
    assert "it.sch.curated_dbx_lakeflow_job_task_run_timeline" in build_query
    assert "it.sch.curated_dbx_lakeflow_jobs" in build_query
    assert "it.sch.curated_dbx_lakeflow_job_run_timeline" in build_query
    assert "WHERE ce.cluster_type = 'JOB'" in build_query
    assert "it.sch.gold_dbx_compute_job_efficiency_daily" in result_df.saved_as


def test_main_dispatches_job_efficiency_rolling(fakes: SimpleNamespace) -> None:
    # Rollup pur : lit UNIQUEMENT la table quotidienne gold job_efficiency_daily.
    result_df = fakes.DataFrame("job_efficiency_rolling_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(
        spark, {"table": "job_efficiency_rolling", "catalog": "it", "schema": "sch"}
    )
    build_query = spark.sql_calls[0]
    assert "FROM it.sch.gold_dbx_compute_job_efficiency_daily" in build_query
    assert "curated_" not in build_query
    assert "it.sch.gold_dbx_compute_job_efficiency_rolling" in result_df.saved_as


def test_main_dispatches_pipeline_efficiency_daily(fakes: SimpleNamespace) -> None:
    # Source = cluster_efficiency_daily (clusters PIPELINE) + la facturation
    # curated pour la resolution cluster_id -> dlt_pipeline_id (meme source que
    # le rollup de cout) + le referentiel de noms.
    result_df = fakes.DataFrame("pipeline_efficiency_daily_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(
        spark, {"table": "pipeline_efficiency_daily", "catalog": "it", "schema": "sch"}
    )
    build_query = spark.sql_calls[0]
    assert "FROM it.sch.gold_dbx_compute_cluster_efficiency_daily ce" in build_query
    assert "FROM it.sch.curated_dbx_billing_usage u" in build_query
    assert "it.sch.curated_dbx_lakeflow_pipelines" in build_query
    assert "WHERE ce.cluster_type = 'PIPELINE'" in build_query
    assert "it.sch.gold_dbx_compute_pipeline_efficiency_daily" in result_df.saved_as


def test_main_dispatches_pipeline_efficiency_rolling(fakes: SimpleNamespace) -> None:
    result_df = fakes.DataFrame("pipeline_efficiency_rolling_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(
        spark, {"table": "pipeline_efficiency_rolling", "catalog": "it", "schema": "sch"}
    )
    build_query = spark.sql_calls[0]
    assert "FROM it.sch.gold_dbx_compute_pipeline_efficiency_daily" in build_query
    assert "curated_" not in build_query
    assert "it.sch.gold_dbx_compute_pipeline_efficiency_rolling" in result_df.saved_as


# --- T001d : dispatch des 2 tables gold depense serverless -------------------
# Le serverless n'a NI `cluster_id` NI ligne dans `curated_dbx_compute_clusters` :
# ces deux tables sont les seules du job a ne pouvoir passer par aucune table de
# clusters, et le dispatch est le seul endroit ou ce cablage se verifie.


def test_main_dispatches_serverless_cost_daily(fakes: SimpleNamespace) -> None:
    result_df = fakes.DataFrame("serverless_cost_daily_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(spark, {"table": "serverless_cost_daily", "catalog": "it", "schema": "sch"})
    build_query = spark.sql_calls[0]
    assert "FROM it.sch.curated_dbx_billing_usage" in build_query
    assert "FROM it.sch.curated_dbx_billing_list_prices" in build_query
    assert "it.sch.gold_dbx_compute_serverless_cost_daily" in result_df.saved_as


def test_main_wires_serverless_cost_daily_to_no_cluster_table(fakes: SimpleNamespace) -> None:
    # Un cablage recopie d'un builder voisin passerait une table de clusters, et
    # la jointure viderait la table : aucune ligne serverless n'y figure.
    result_df = fakes.DataFrame("serverless_cost_daily_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(spark, {"table": "serverless_cost_daily", "catalog": "it", "schema": "sch"})
    build_query = spark.sql_calls[0]
    assert "curated_dbx_compute_clusters" not in build_query
    assert "gold_dbx_compute_cluster_cost_daily" not in build_query
    # Les deux seuls referentiels attendus ne servent qu'a NOMMER des objets que
    # la facturation ne nomme pas.
    assert "it.sch.curated_dbx_compute_warehouses w" in build_query
    assert "it.sch.curated_dbx_lakeflow_pipelines pl" in build_query


def test_main_dispatches_serverless_cost_rolling(fakes: SimpleNamespace) -> None:
    # Rollup pur : lit UNIQUEMENT la table quotidienne gold serverless_cost_daily.
    result_df = fakes.DataFrame("serverless_cost_rolling_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(spark, {"table": "serverless_cost_rolling", "catalog": "it", "schema": "sch"})
    build_query = spark.sql_calls[0]
    assert "FROM it.sch.gold_dbx_compute_serverless_cost_daily" in build_query
    assert "curated_" not in build_query
    assert "it.sch.gold_dbx_compute_serverless_cost_rolling" in result_df.saved_as


def test_main_serverless_cost_daily_merges_on_the_full_object_grain(
    fakes: SimpleNamespace,
) -> None:
    # Les 5 cles doivent arriver telles quelles au MERGE : `merge_into_table`
    # fusionne sur `<=>` null-safe, une cle oubliee agregerait silencieusement
    # des objets distincts au lieu de lever.
    target = "it.sch.gold_dbx_compute_serverless_cost_daily"
    result_df = fakes.DataFrame("serverless_cost_daily_result")
    spark = fakes.Spark(
        existing_tables={target},
        sql_result=[_gap_scan_row(last_day=date(2026, 8, 1)), result_df],
    )
    entrypoint.main(spark, {"table": "serverless_cost_daily", "catalog": "it", "schema": "sch"})
    merges = [call for call in spark.sql_calls if call.startswith("MERGE")]
    assert len(merges) == 1
    for key in specs.SERVERLESS_COST_DAILY_MERGE_KEYS:
        assert f"t.{key} <=> s.{key}" in merges[0]
    # Table a watermark alimentee en billing-direct : la facturation ne retracte
    # pas une ligne deja emise, donc aucune suppression n'est attendue.
    assert "THEN DELETE" not in merges[0]


def test_main_serverless_cost_rolling_deletes_absent_rows_after_the_grace_delay(
    fakes: SimpleNamespace,
) -> None:
    # Snapshot reecrit en entier et `as_of_date` hors des cles de merge : sans
    # garde-fou, un objet serverless disparu survivrait sous son ancien
    # `as_of_date` et passerait pour courant dans la page.
    target = "it.sch.gold_dbx_compute_serverless_cost_rolling"
    result_df = fakes.DataFrame("serverless_cost_rolling_result", row_count=1)
    spark = fakes.Spark(existing_tables={target}, sql_result=result_df)
    entrypoint.main(spark, {"table": "serverless_cost_rolling", "catalog": "it", "schema": "sch"})
    merges = [call for call in spark.sql_calls if call.startswith("MERGE")]
    assert len(merges) == 1
    assert (
        "WHEN NOT MATCHED BY SOURCE AND (t._generated_at < date_add(current_date(), "
        f"-{specs.SNAPSHOT_ABSENT_ROW_GRACE_DAYS})) THEN DELETE" in merges[0]
    )
    assert "period_start >=" not in merges[0]


# --- T001e : dispatch de la table gold gouvernance serverless ----------------


def test_main_dispatches_serverless_governance(fakes: SimpleNamespace) -> None:
    result_df = fakes.DataFrame("serverless_governance_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(spark, {"table": "serverless_governance", "catalog": "it", "schema": "sch"})
    build_query = spark.sql_calls[0]
    assert "FROM it.sch.curated_dbx_billing_usage" in build_query
    assert "FROM it.sch.curated_dbx_billing_list_prices" in build_query
    assert "it.sch.gold_dbx_compute_serverless_governance" in result_df.saved_as


def test_main_wires_serverless_governance_to_the_billing_lines_not_to_the_daily_gold(
    fakes: SimpleNamespace,
) -> None:
    # Cablage le plus tentant a "simplifier" : cette table a le perimetre EXACT de
    # gold_dbx_compute_serverless_cost_daily, mais au grain jour-objet du daily des
    # lignes sans identite fusionnent avec des lignes qui en portent une (8 605,66 $
    # d'orphelins au lieu de 8 704,20 $ sur une meme fenetre de 31 jours). Le
    # dispatch est le seul endroit ou ce choix se verifie.
    result_df = fakes.DataFrame("serverless_governance_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(spark, {"table": "serverless_governance", "catalog": "it", "schema": "sch"})
    build_query = spark.sql_calls[0]
    assert "gold_dbx_compute_serverless_cost_daily" not in build_query
    assert "curated_dbx_compute_clusters" not in build_query


def test_main_serverless_governance_scope_is_the_activity_window(
    fakes: SimpleNamespace,
) -> None:
    result_df = fakes.DataFrame("serverless_governance_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    # `main` prend sa date de reference sur l'horloge UTC : l'appel est encadre
    # pour que le test reste exact meme s'il traverse minuit.
    before = datetime.now(UTC).date()
    entrypoint.main(spark, {"table": "serverless_governance", "catalog": "it", "schema": "sch"})
    after = datetime.now(UTC).date()
    window = timedelta(days=specs.GOVERNANCE_ACTIVITY_WINDOW_DAYS)
    build_query = spark.sql_calls[0]
    filtered = set(re.findall(r"usage_date >= DATE '([\d-]+)'", build_query))
    assert filtered
    assert filtered <= {(before - window).isoformat(), (after - window).isoformat()}
    # Le plancher PUBLIE est celui qui a ete FILTRE : une ligne annoncant une
    # fenetre autre que celle mesuree rendrait chacun de ses pourcentages faux
    # sans qu'aucun test de spec ne le voie.
    assert set(re.findall(r"DATE '([\d-]+)' AS window_start", build_query)) == filtered


def test_main_serverless_governance_snapshot_deletes_rows_out_of_scope(
    fakes: SimpleNamespace,
) -> None:
    # Snapshot borne : sans suppression, une surface qui cesse de couter (ou un
    # workspace ferme) survivrait indefiniment dans la matrice de couverture avec
    # ses derniers pourcentages, presentes comme courants.
    target = "it.sch.gold_dbx_compute_serverless_governance"
    result_df = fakes.DataFrame("serverless_governance_result", row_count=1)
    spark = fakes.Spark(existing_tables={target}, sql_result=result_df)
    entrypoint.main(spark, {"table": "serverless_governance", "catalog": "it", "schema": "sch"})
    merges = [call for call in spark.sql_calls if call.startswith("MERGE")]
    assert len(merges) == 1
    assert (
        "WHEN NOT MATCHED BY SOURCE AND (t._generated_at < date_add(current_date(), "
        f"-{specs.SNAPSHOT_ABSENT_ROW_GRACE_DAYS})) THEN DELETE" in merges[0]
    )
    # Snapshot sans watermark : aucune borne de fenetre a poser sur la cible (et
    # aucune colonne de periode a borner).
    assert "period_start >=" not in merges[0]
    assert "window_start >=" not in merges[0]
    # Les 3 cles arrivent telles quelles : `merge_into_table` fusionne sur `<=>`
    # null-safe, une cle oubliee ecraserait des surfaces distinctes sans lever.
    for key in specs.SERVERLESS_GOVERNANCE_MERGE_KEYS:
        assert f"t.{key} <=> s.{key}" in merges[0]
    # Table sans watermark : la fenetre est toujours `full`, meme cible presente.
    assert not any("first_missing_day" in call for call in spark.sql_calls)


def test_serverless_governance_is_scheduled_by_the_job_without_any_dependency() -> None:
    # Une cle du registre que AUCUNE tache n'execute donne une table qui n'existe
    # jamais, sans qu'aucun test de code ne le voie. Et l'absence de `depends_on`
    # est ici un CHOIX : ce snapshot relit la facturation, pas
    # gold_dbx_compute_serverless_cost_daily -- le chainer laisserait croire
    # qu'il en derive.
    job_yaml = Path(__file__).parents[2] / "resources" / "job_dcm_gold_dbx_compute.yml"
    assert job_yaml.is_file(), f"{job_yaml} introuvable (chemin du bundle change ?)"
    text = job_yaml.read_text(encoding="utf-8")
    # Le bloc de LA tache seule : les taches sont separees par une ligne vide, et
    # le commentaire de la tache suivante parle lui aussi de `depends_on`.
    task = text.split("- task_key: gold_serverless_governance", 1)[1].split("\n\n", 1)[0]
    assert 'table:        "serverless_governance"' in task
    assert "environment_key: gold_compute_env" in task
    assert "depends_on" not in task
    # Snapshot integralement recalcule : un retry le rejouerait en entier pour
    # rien, et masquerait l'echec derriere une seconde execution facturee.
    assert "max_retries: 0" in task


# --- T001f : dispatch de la table gold statistiques d'execution ---------------


def test_main_dispatches_pipeline_update_stats(fakes: SimpleNamespace) -> None:
    result_df = fakes.DataFrame("pipeline_update_stats_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(spark, {"table": "pipeline_update_stats", "catalog": "it", "schema": "sch"})
    build_query = spark.sql_calls[0]
    assert "FROM it.sch.curated_dbx_lakeflow_pipeline_update_timeline" in build_query
    assert "it.sch.gold_dbx_compute_pipeline_update_stats" in result_df.saved_as
    # 1er run : aucune fenetre, tout l'historique curated est agrege.
    assert ">= DATE" not in build_query


def test_main_pipeline_update_stats_windows_only_the_output(fakes: SimpleNamespace) -> None:
    # La fenetre incrementale de cette table ne borne PAS sa lecture : elle est
    # posee sur l'agregat deja complet. Borner l'entree tronquerait
    # `MIN(period_start_time)` des 427 updates qui changent de jour calendaire
    # (jusqu'a 19 jours d'etalement) et le MERGE ecraserait une duree correcte
    # par une duree plus courte, sans lever d'erreur. Le dispatch est le seul
    # endroit ou l'on voit la fenetre RESOLUE atterrir dans la requete.
    target = "it.sch.gold_dbx_compute_pipeline_update_stats"
    result_df = fakes.DataFrame("pipeline_update_stats_result")
    spark = fakes.Spark(
        existing_tables={target},
        sql_result=[_gap_scan_row(), result_df],
    )
    entrypoint.main(spark, {"table": "pipeline_update_stats", "catalog": "it", "schema": "sch"})
    gap_scan, build_query = spark.sql_calls[0], spark.sql_calls[1]
    # La couverture est inspectee sur le MEME axe que celui que le builder
    # reecrit, et par jour (`gap_scan_sql` encapsule le TIMESTAMP dans to_date).
    assert f"FROM {target}" in gap_scan
    assert "to_date(update_end_time)" in gap_scan
    # `_gap_scan_row()` rend une couverture qui s'arrete au 2026-08-17 : la borne
    # retenue est ce dernier jour ecrit (candidat de trou de queue).
    assert "AND update_end_time >= DATE '2026-08-17'" in build_query
    # ... appliquee a la SORTIE, jamais a la lecture curated.
    per_update = build_query.split("FROM it.sch.curated_dbx_lakeflow_pipeline_update_timeline", 1)
    assert "update_end_time >=" not in per_update[0]
    assert "period_start_time >=" not in build_query
    assert "AND update_start_time >=" not in build_query


def test_main_pipeline_update_stats_is_a_pure_upsert(fakes: SimpleNamespace) -> None:
    # Aucune suppression, contrairement aux snapshots de gouvernance : la source
    # ne conserve qu'environ un an glissant, cette table est la memoire longue.
    # Un `WHEN NOT MATCHED BY SOURCE` effacerait l'historique que la source ne
    # peut plus rejouer.
    target = "it.sch.gold_dbx_compute_pipeline_update_stats"
    result_df = fakes.DataFrame("pipeline_update_stats_result")
    spark = fakes.Spark(
        existing_tables={target},
        sql_result=[_gap_scan_row(), result_df],
    )
    entrypoint.main(spark, {"table": "pipeline_update_stats", "catalog": "it", "schema": "sch"})
    merges = [call for call in spark.sql_calls if call.startswith("MERGE")]
    assert len(merges) == 1
    assert "WHEN NOT MATCHED BY SOURCE" not in merges[0]
    # Les 2 cles arrivent telles quelles : `merge_into_table` fusionne sur `<=>`
    # null-safe, une cle oubliee fondrait des executions distinctes sans lever.
    for key in specs.PIPELINE_UPDATE_STATS_MERGE_KEYS:
        assert f"t.{key} <=> s.{key}" in merges[0]
    assert "t.workspace_id <=> s.workspace_id" not in merges[0]
    assert result_df.select_exprs == []


def test_pipeline_update_stats_is_scheduled_by_the_job_without_any_dependency() -> None:
    # Une cle du registre qu'aucune tache n'execute donne une table qui n'existe
    # jamais, sans qu'aucun test de code ne le voie. Et l'absence de
    # `depends_on` est ici un CHOIX : cette table ne lit qu'une source curated,
    # aucune table gold.
    job_yaml = Path(__file__).parents[2] / "resources" / "job_dcm_gold_dbx_compute.yml"
    text = job_yaml.read_text(encoding="utf-8")
    task = text.split("- task_key: gold_pipeline_update_stats", 1)[1].split("\n\n", 1)[0]
    assert 'table:        "pipeline_update_stats"' in task
    assert "environment_key: gold_compute_env" in task
    assert "depends_on" not in task
    assert "max_retries: 0" in task


def test_every_gold_registry_key_is_scheduled_by_a_job() -> None:
    # Le garde-fou de l'entrypoint ne couvre qu'UN sens : une cle inconnue leve,
    # une cle du registre absente des YAML est SILENCIEUSE (la spec existe, ses
    # tests passent, la table n'est jamais produite). Ce test ferme l'autre sens.
    resources = Path(__file__).parents[2] / "resources"
    compute = (resources / "job_dcm_gold_dbx_compute.yml").read_text(encoding="utf-8")
    forecast = (resources / "job_dcm_gold_forecast.yml").read_text(encoding="utf-8")
    assert set(specs.GOLD_SPEC_KEYS) <= set(re.findall(r'table:\s+"(\w+)"', compute + forecast))
    # `forecast_daily` est la SEULE cle hors de ce job : `ai_forecast` exige un
    # warehouse SQL, pas l'environnement serverless de `dcm_gold_dbx_compute`.
    assert set(re.findall(r'table:\s+"(\w+)"', compute)) == set(specs.GOLD_SPEC_KEYS) - {
        "forecast_daily"
    }


# --- T001h : suppression des lignes cible absentes du recalcul ---------------
# Trois regimes a distinguer, et c'est tout l'enjeu de ces tests : un snapshot
# (`*_rolling`) est reecrit en entier, son garde-fou de grace suffit ; une table
# a watermark ne peut supprimer que DANS la fenetre recalculee ; une spec sans
# garde-fou ne supprime jamais rien.


def test_main_rolling_snapshot_deletes_absent_rows_after_the_grace_delay(
    fakes: SimpleNamespace,
) -> None:
    # `as_of_date` n'etant dans aucune cle de merge `*_rolling`, une ligne dont
    # la cle n'est plus produite survivrait sous son ancien `as_of_date` et
    # passerait pour courante (162 lignes mesurees en dev le 2026-09-10).
    target = "it.sch.gold_dbx_compute_warehouse_utilization_rolling"
    result_df = fakes.DataFrame("warehouse_utilization_rolling_result", row_count=1)
    spark = fakes.Spark(existing_tables={target}, sql_result=result_df)
    entrypoint.main(
        spark, {"table": "warehouse_utilization_rolling", "catalog": "it", "schema": "sch"}
    )
    merges = [call for call in spark.sql_calls if call.startswith("MERGE")]
    assert len(merges) == 1
    assert (
        "WHEN NOT MATCHED BY SOURCE AND (t._generated_at < date_add(current_date(), "
        f"-{specs.SNAPSHOT_ABSENT_ROW_GRACE_DAYS})) THEN DELETE" in merges[0]
    )
    # Snapshot sans watermark : la source EST la reference complete, aucune borne
    # de fenetre n'a de sens (et il n'y a pas de `period_start` a borner).
    assert "period_start >=" not in merges[0]


def test_main_warehouse_utilization_daily_delete_is_bounded_to_the_recomputed_window(
    fakes: SimpleNamespace,
) -> None:
    # LE test de non-regression destructrice. `entrypoint` ne transmet AUCUN
    # `partition_predicate` : toute ligne cible hors du lot frais est
    # `NOT MATCHED BY SOURCE`. Sans la borne `period_start >= <fenetre>`, ce
    # MERGE supprimerait donc tout l'historique anterieur a la fenetre
    # incrementale — ici les 2 mois de jours-warehouse deja ecrits. Si cette
    # assertion tombe, la suppression n'est plus bornee : ne pas "reparer" le
    # test, reparer la borne.
    target = "it.sch.gold_dbx_compute_warehouse_utilization_daily"
    result_df = fakes.DataFrame("warehouse_utilization_daily_result")
    last_written = date(2026, 8, 1)
    spark = fakes.Spark(
        existing_tables={target},
        sql_result=[_gap_scan_row(last_day=last_written), result_df],
    )
    entrypoint.main(
        spark, {"table": "warehouse_utilization_daily", "catalog": "it", "schema": "sch"}
    )
    merges = [call for call in spark.sql_calls if call.startswith("MERGE")]
    assert len(merges) == 1
    assert (
        "WHEN NOT MATCHED BY SOURCE AND (t.period_start >= DATE '2026-08-01' "
        "AND (t._generated_at < date_add(current_date(), "
        f"-{specs.SNAPSHOT_ABSENT_ROW_GRACE_DAYS}))) THEN DELETE" in merges[0]
    )
    # La borne est celle de la fenetre REELLEMENT recalculee : meme date que le
    # filtre de lecture du builder, jamais une constante.
    assert "AND period_start >= DATE '2026-08-01'" in spark.sql_calls[1]
    # En incremental, la borne vient de la fenetre deja resolue : aucun MIN
    # supplementaire n'est calcule sur la sortie du builder.
    assert result_df.select_exprs == []


def test_main_warehouse_utilization_daily_full_refresh_bounds_delete_on_the_source(
    fakes: SimpleNamespace,
) -> None:
    # En full la fenetre n'est pas connue d'avance : la borne est le premier jour
    # que le recalcul PRODUIT. Ce qui est plus ancien, le recalcul ne le dit pas,
    # il n'a donc pas a le supprimer (protection de l'historique gold plus ancien
    # que la couverture curated).
    target = "it.sch.gold_dbx_compute_warehouse_utilization_daily"
    result_df = fakes.DataFrame("warehouse_utilization_daily_result", rows=[[date(2026, 7, 15)]])
    spark = fakes.Spark(existing_tables={target}, sql_result=result_df)
    entrypoint.main(
        spark,
        {
            "table": "warehouse_utilization_daily",
            "catalog": "it",
            "schema": "sch",
            "full_refresh": "true",
        },
    )
    assert result_df.select_exprs == [("MIN(period_start) AS window_floor",)]
    merges = [call for call in spark.sql_calls if call.startswith("MERGE")]
    assert "WHEN NOT MATCHED BY SOURCE AND (t.period_start >= DATE '2026-07-15'" in merges[0]


def test_main_warehouse_utilization_daily_never_deletes_when_the_recompute_is_empty(
    fakes: SimpleNamespace,
) -> None:
    # Run degrade (source curated vide/indisponible) : aucune borne exploitable
    # => aucune suppression, plutot qu'une suppression non bornee.
    target = "it.sch.gold_dbx_compute_warehouse_utilization_daily"
    result_df = fakes.DataFrame("warehouse_utilization_daily_result", rows=[[None]])
    spark = fakes.Spark(existing_tables={target}, sql_result=result_df)
    entrypoint.main(
        spark,
        {
            "table": "warehouse_utilization_daily",
            "catalog": "it",
            "schema": "sch",
            "full_refresh": "true",
        },
    )
    merges = [call for call in spark.sql_calls if call.startswith("MERGE")]
    assert len(merges) == 1
    assert "WHEN NOT MATCHED BY SOURCE" not in merges[0]


def test_main_daily_spec_without_a_guard_never_emits_a_delete_clause(
    fakes: SimpleNamespace,
) -> None:
    # Non-regression : les 10 autres tables `*_daily` restent en upsert pur, et
    # leur MERGE ne doit couter aucun MIN supplementaire sur la sortie.
    target = "it.sch.gold_dbx_compute_warehouse_cost_daily"
    result_df = fakes.DataFrame("warehouse_cost_daily_result")
    spark = fakes.Spark(existing_tables={target}, sql_result=result_df)
    entrypoint.main(
        spark,
        {
            "table": "warehouse_cost_daily",
            "catalog": "it",
            "schema": "sch",
            "full_refresh": "true",
        },
    )
    merges = [call for call in spark.sql_calls if call.startswith("MERGE")]
    assert len(merges) == 1
    assert "WHEN NOT MATCHED BY SOURCE" not in merges[0]
    assert result_df.select_exprs == []


def test_main_forecast_daily_merge_purges_only_the_horizons_still_ahead(
    fakes: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Une PROJECTION n'est pas un fait date : un horizon futur que le recalcul ne
    # produit plus est perime (objet devenu ineligible, metrique retiree), et un
    # upsert pur le laisserait en base a cote de la nouvelle prevision du meme
    # jour. La borne `horizon_date >= current_date()` laisse en revanche
    # intactes les projections passees, seule trace de ce qui avait ete predit.
    # Le garde-fou de grace des snapshots ne conviendrait pas ici : sur un
    # horizon de 7 jours, `_generated_at < J-7` ne toucherait presque rien.
    target = "it.sch.gold_dbx_compute_forecast_daily"
    result_df = fakes.DataFrame("forecast_result", row_count=1)
    monkeypatch.setattr(
        entrypoint, "build_compute_forecast", lambda spark, **kwargs: result_df
    )
    spark = fakes.Spark(existing_tables={target}, sql_result=result_df)
    entrypoint.main(
        spark,
        {"table": "forecast_daily", "catalog": "it", "schema": "sch", "warehouse_id": "wh1"},
    )
    merges = [call for call in spark.sql_calls if call.startswith("MERGE")]
    assert len(merges) == 1
    assert (
        "WHEN NOT MATCHED BY SOURCE AND (t.horizon_date >= current_date()) THEN DELETE"
        in merges[0]
    )
    # Spec sans watermark : le garde-fou EST le predicat complet, aucune borne de
    # fenetre a lire sur la sortie (donc aucun MIN supplementaire).
    assert result_df.select_exprs == []


def test_main_snapshot_without_a_watermark_never_deletes_when_the_recompute_is_empty(
    fakes: SimpleNamespace,
) -> None:
    # Sur une spec SANS watermark (`*_rolling`, `governance`, `forecast_daily`),
    # rien ne borne la suppression : une sortie vide effacerait tout ce que le
    # garde-fou laisse passer. `_source_watermark_floor` protege deja les tables
    # a watermark de ce scenario ; ce test ferme l'autre moitie du registre.
    target = "it.sch.gold_dbx_compute_warehouse_utilization_rolling"
    result_df = fakes.DataFrame("warehouse_utilization_rolling_result")
    assert result_df.isEmpty()
    spark = fakes.Spark(existing_tables={target}, sql_result=result_df)
    entrypoint.main(
        spark, {"table": "warehouse_utilization_rolling", "catalog": "it", "schema": "sch"}
    )
    merges = [call for call in spark.sql_calls if call.startswith("MERGE")]
    assert len(merges) == 1
    assert "WHEN NOT MATCHED BY SOURCE" not in merges[0]


# --- T001c : purge ponctuelle apres un changement de population --------------
# Un filtre ajoute a un builder (ici le predicat `billing_origin_product`) rend
# orphelines les lignes deja ecrites que la nouvelle definition ne produit plus.
# Le nettoyage passe par un parametre de RUN, jamais par un garde-fou permanent
# dans la spec (cf. l'avertissement de `WAREHOUSE_UTILIZATION_DAILY_SPEC` :
# aucune `*_daily` agregeant la facturation ne doit accepter de perdre un jour
# deja ecrit). Ces tests verrouillent les deux moities de cette promesse : la
# purge fonctionne quand on la demande, et elle refuse tout ce qui la rendrait
# partielle ou non bornee.


def _one_off_purge_params(table: str, **extra: str) -> dict[str, str]:
    return {
        "table": table,
        "catalog": "it",
        "schema": "sch",
        "full_refresh": "true",
        "one_off_purge": "true",
        **extra,
    }


def test_one_off_purge_param_is_accepted_but_absent_from_the_scheduled_job() -> None:
    assert "one_off_purge" in entrypoint.PARAM_NAMES
    # Levier destructeur : il ne doit exister QUE pour un run declenche a la
    # main. Une tache planifiee qui le porterait, meme a vide, suffirait a le
    # rendre activable par erreur sur les 23 tables.
    job_yaml = Path(__file__).parents[2] / "resources" / "job_dcm_gold_dbx_compute.yml"
    assert job_yaml.is_file(), f"{job_yaml} introuvable (chemin du bundle change ?)"
    assert "one_off_purge" not in job_yaml.read_text(encoding="utf-8")


def test_main_one_off_purge_deletes_orphans_bounded_by_the_recomputed_history(
    fakes: SimpleNamespace,
) -> None:
    # Cas d'usage reel : `pipeline_cost_daily` recalcule sur tout l'historique
    # avec le nouveau filtre produit ; les jours-pipeline que le filtre exclut
    # desormais doivent DISPARAITRE, pas rester a cote des lignes corrigees.
    target = "it.sch.gold_dbx_compute_pipeline_cost_daily"
    result_df = fakes.DataFrame("pipeline_cost_daily_result", rows=[[date(2024, 2, 13)]])
    spark = fakes.Spark(existing_tables={target}, sql_result=result_df)
    before = datetime.now(UTC).replace(microsecond=0)
    entrypoint.main(spark, _one_off_purge_params("pipeline_cost_daily"))
    after = datetime.now(UTC)
    # Borne basse = premier jour REELLEMENT produit par le recalcul (et non une
    # constante) : ce qui est plus ancien, le recalcul ne le dit pas.
    assert result_df.select_exprs == [("MIN(period_start) AS window_floor",)]
    merges = [call for call in spark.sql_calls if call.startswith("MERGE")]
    assert len(merges) == 1
    clause = re.search(
        r"WHEN NOT MATCHED BY SOURCE AND \((.*?)\) THEN DELETE", merges[0], re.DOTALL
    )
    assert clause is not None, merges[0]
    predicate = clause.group(1)
    assert predicate.startswith("t.period_start >= DATE '2024-02-13' AND (")
    # Seuil = debut du run, et non la grace volumetrique de 7 jours : toutes les
    # lignes gold portent un `_generated_at` recent (mesure dev 2026-09-10), la
    # grace ne supprimerait donc rien ou seulement une fraction.
    assert "date_add(current_date()" not in predicate
    cutoff = re.search(r"t\._generated_at < TIMESTAMP '([^']+)'", predicate)
    assert cutoff is not None, predicate
    cutoff_at = datetime.strptime(cutoff.group(1), "%Y-%m-%d %H:%M:%S%z")
    assert before <= cutoff_at <= after
    assert cutoff_at.utcoffset() == timedelta(0), "seuil ancre en UTC, pas en heure de session"


def test_main_one_off_purge_left_out_keeps_the_pure_upsert(fakes: SimpleNamespace) -> None:
    # Regime permanent : rien n'est persiste par un run de purge, le run suivant
    # (sans le parametre, ou avec une valeur vide) ne supprime plus rien.
    target = "it.sch.gold_dbx_compute_pipeline_cost_daily"
    result_df = fakes.DataFrame("pipeline_cost_daily_result", rows=[[date(2024, 2, 13)]])
    spark = fakes.Spark(existing_tables={target}, sql_result=result_df)
    entrypoint.main(spark, _one_off_purge_params("pipeline_cost_daily", one_off_purge=""))
    merges = [call for call in spark.sql_calls if call.startswith("MERGE")]
    assert len(merges) == 1
    assert "WHEN NOT MATCHED BY SOURCE" not in merges[0]
    # Et aucun MIN inutile sur la sortie du builder.
    assert result_df.select_exprs == []


def test_main_one_off_purge_never_deletes_when_the_recompute_is_empty(
    fakes: SimpleNamespace,
) -> None:
    # Filet de securite le plus important de la purge : un recalcul vide (source
    # curated indisponible) ne donne aucune borne, donc AUCUNE suppression --
    # sinon ce run viderait la table entiere au lieu de la reparer.
    target = "it.sch.gold_dbx_compute_pipeline_cost_daily"
    result_df = fakes.DataFrame("pipeline_cost_daily_result", rows=[[None]])
    spark = fakes.Spark(existing_tables={target}, sql_result=result_df)
    entrypoint.main(spark, _one_off_purge_params("pipeline_cost_daily"))
    merges = [call for call in spark.sql_calls if call.startswith("MERGE")]
    assert len(merges) == 1
    assert "WHEN NOT MATCHED BY SOURCE" not in merges[0]


def test_main_one_off_purge_never_mutates_the_registry(fakes: SimpleNamespace) -> None:
    # `dataclasses.replace` rend une COPIE : la spec du registre reste en upsert
    # pur, y compris pour les runs suivants du meme process.
    target = "it.sch.gold_dbx_compute_pipeline_cost_daily"
    result_df = fakes.DataFrame("pipeline_cost_daily_result", rows=[[date(2024, 2, 13)]])
    spark = fakes.Spark(existing_tables={target}, sql_result=result_df)
    entrypoint.main(spark, _one_off_purge_params("pipeline_cost_daily"))
    assert specs.GOLD_SPECS["pipeline_cost_daily"].absent_row_delete_guard is None
    assert specs.PIPELINE_COST_DAILY_SPEC.absent_row_delete_guard is None


def test_main_one_off_purge_requires_full_refresh(fakes: SimpleNamespace) -> None:
    # Sans `full_refresh`, la suppression serait bornee a la fenetre incrementale
    # (10 jours) : elle nettoierait une fraction de l'historique en RAPPORTANT un
    # succes. Une purge partielle non signalee est pire qu'une purge absente.
    target = "it.sch.gold_dbx_compute_pipeline_cost_daily"
    result_df = fakes.DataFrame("pipeline_cost_daily_result", rows=[[date(2024, 2, 13)]])
    spark = fakes.Spark(existing_tables={target}, sql_result=[_gap_scan_row(), result_df])
    with pytest.raises(ValueError, match="full_refresh"):
        entrypoint.main(spark, _one_off_purge_params("pipeline_cost_daily", full_refresh=""))
    # Echec AVANT toute requete : ni scan, ni recalcul, ni MERGE.
    assert spark.sql_calls == []


def test_main_one_off_purge_refuses_a_spec_without_a_watermark(fakes: SimpleNamespace) -> None:
    # Sans watermark, `resolve_absent_row_delete_predicate` ne borne plus rien :
    # la suppression porterait sur toute la table, et un recalcul degrade la
    # viderait. `forecast_daily` cumule desormais les deux motifs de refus (pas
    # de watermark ET un garde-fou permanent) : c'est celui du watermark qui est
    # verifie d'abord, et le message doit rester le sien.
    spark = fakes.Spark(existing_tables={"it.sch.gold_dbx_compute_forecast_daily"})
    with pytest.raises(ValueError, match="watermark_column"):
        entrypoint.main(spark, _one_off_purge_params("forecast_daily", warehouse_id="wh1"))
    assert spark.sql_calls == []


def test_main_one_off_purge_refuses_a_spec_that_already_deletes(fakes: SimpleNamespace) -> None:
    # `warehouse_utilization_daily` se nettoie deja en regime permanent : ecraser
    # son garde-fou remplacerait sa grace volumetrique par le seuil de run, donc
    # changerait la semantique d'une table qui n'a rien demande.
    target = "it.sch.gold_dbx_compute_warehouse_utilization_daily"
    spark = fakes.Spark(existing_tables={target})
    with pytest.raises(ValueError, match="supprime deja"):
        entrypoint.main(spark, _one_off_purge_params("warehouse_utilization_daily"))
    assert spark.sql_calls == []
