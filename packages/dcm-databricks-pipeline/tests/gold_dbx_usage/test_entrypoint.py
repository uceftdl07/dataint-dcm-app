"""Tests de `pipelines.gold_dbx_usage.entrypoint` (fenetre + dispatch + ecriture).

La fenetre d'un run suivant est ancree sur la COUVERTURE REELLE de la table cible
(`compute_gap_aware_lower_bound`) et non sur le seul `today - lookback`. Un tel run
emet donc DEUX requetes : le scan de couverture, puis celle du builder -- les fakes
passes via `sql_result` suivent cet ordre.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

import pipelines.gold_dbx_usage.entrypoint as entrypoint
import pipelines.gold_dbx_usage.specs as specs
from pipelines.gold_dbx_usage.ephemeral_tables import TABLE_KEY_COLUMNS
from tests.conftest import gap_scan_row

TODAY = date(2026, 8, 17)
NOMINAL_BOUND = TODAY - timedelta(days=specs.INCREMENTAL_LOOKBACK_DAYS)
TARGET_TABLE_DAILY = "it.sch.gold_dbx_usage_table_daily"


def _continuous_coverage() -> SimpleNamespace:
    """Couverture continue jusqu'a `TODAY` : la fenetre nominale doit s'appliquer."""
    return gap_scan_row(last_day=TODAY)


def _spark_for(
    fakes: SimpleNamespace,
    spec: specs.GoldAggregationSpec,
    target: str,
    result_df: Any,  # noqa: ANN401 - le DataFrame factice n'a pas de type public
) -> Any:  # noqa: ANN401
    """Session factice cablee sur la sequence d'appels reelle de la spec.

    Une table a watermark emet d'abord le scan de couverture de sa cible, puis la requete
    du builder ; un snapshot n'emet que la seconde. Sans cette distinction, le `sql_result`
    d'un snapshot serait consomme par un scan qui n'a pas lieu, et le builder recevrait la
    ligne de couverture.
    """
    results: list[Any] = [result_df]
    if spec.watermark_column is not None:
        results.insert(0, _continuous_coverage())
    return fakes.Spark(existing_tables={target}, sql_result=results)


def test_resolve_lower_bound_is_none_on_first_run(fakes: SimpleNamespace) -> None:
    spark = fakes.Spark(existing_tables=set())
    lower_bound = entrypoint._resolve_lower_bound(
        spark,
        specs.TABLE_DAILY_SPEC,
        TARGET_TABLE_DAILY,
        full_refresh=False,
        today=TODAY,
    )
    assert lower_bound is None


def test_resolve_lower_bound_is_incremental_window_on_subsequent_run(
    fakes: SimpleNamespace,
) -> None:
    spark = fakes.Spark(
        existing_tables={TARGET_TABLE_DAILY}, sql_result=[_continuous_coverage()]
    )
    lower_bound = entrypoint._resolve_lower_bound(
        spark, specs.TABLE_DAILY_SPEC, TARGET_TABLE_DAILY, full_refresh=False, today=TODAY
    )
    assert lower_bound == NOMINAL_BOUND


def test_resolve_lower_bound_widens_the_window_down_to_a_missing_day(
    fakes: SimpleNamespace,
) -> None:
    """Un jour qu'aucun run n'a couvert pendant sa fenetre de `lookback_days` sort
    de toutes les fenetres nominales suivantes : sans elargissement, le trou est
    permanent et sans signal, seul un `--full-refresh` manuel le reparant. Le
    recalcul repart du trou LUI-MEME, les jours qui le suivent ayant ete calcules sur
    une source incomplete."""
    hole = date(2026, 8, 4)
    spark = fakes.Spark(
        existing_tables={TARGET_TABLE_DAILY},
        sql_result=[gap_scan_row(last_day=TODAY, first_missing_day=hole)],
    )
    lower_bound = entrypoint._resolve_lower_bound(
        spark, specs.TABLE_DAILY_SPEC, TARGET_TABLE_DAILY, full_refresh=False, today=TODAY
    )
    assert lower_bound == hole
    assert lower_bound < NOMINAL_BOUND


def test_resolve_lower_bound_recomputes_the_last_written_day(
    fakes: SimpleNamespace,
) -> None:
    """Trou de QUEUE (job arrete plusieurs semaines) : la fenetre nominale ne
    couvre que ses derniers jours et laisse un trou definitif entre elle et le
    dernier jour ecrit. La reprise inclut ce dernier jour LUI-MEME : ecrit alors que
    la source curated arrivait encore, il est partiel."""
    last_written = date(2026, 7, 20)
    spark = fakes.Spark(
        existing_tables={TARGET_TABLE_DAILY},
        sql_result=[gap_scan_row(last_day=last_written)],
    )
    lower_bound = entrypoint._resolve_lower_bound(
        spark, specs.TABLE_DAILY_SPEC, TARGET_TABLE_DAILY, full_refresh=False, today=TODAY
    )
    assert lower_bound == last_written


def test_resolve_lower_bound_scans_the_target_table_on_its_watermark(
    fakes: SimpleNamespace,
) -> None:
    """Le scan porte sur la table CIBLE, sa colonne de watermark et `_generated_at`
    (present sur les 6 builders du domaine) : sans cette derniere, un jour ecrit
    trop tot pour avoir absorbe les arrivees tardives serait indetectable."""
    spark = fakes.Spark(
        existing_tables={TARGET_TABLE_DAILY}, sql_result=[_continuous_coverage()]
    )
    entrypoint._resolve_lower_bound(
        spark, specs.TABLE_DAILY_SPEC, TARGET_TABLE_DAILY, full_refresh=False, today=TODAY
    )
    scan_query = spark.sql_calls[0]
    assert TARGET_TABLE_DAILY in scan_query
    assert "to_date(period_start)" in scan_query
    assert "_generated_at" in scan_query


def test_resolve_lower_bound_full_refresh_forces_full_even_if_target_exists(
    fakes: SimpleNamespace,
) -> None:
    # Aucun `sql_result` : `--full-refresh` doit court-circuiter AVANT le scan de
    # couverture (sinon un full refresh paierait un scan dont il ignore le resultat).
    spark = fakes.Spark(existing_tables={TARGET_TABLE_DAILY})
    lower_bound = entrypoint._resolve_lower_bound(
        spark, specs.TABLE_DAILY_SPEC, TARGET_TABLE_DAILY, full_refresh=True, today=TODAY
    )
    assert lower_bound is None
    assert spark.sql_calls == []


def test_main_requires_catalog_and_schema(fakes: SimpleNamespace) -> None:
    spark = fakes.Spark()
    with pytest.raises(ValueError, match="catalog"):
        entrypoint.main(spark, {"table": "table_daily", "catalog": "", "schema": ""})


def test_main_rejects_unknown_table(fakes: SimpleNamespace) -> None:
    spark = fakes.Spark()
    with pytest.raises(ValueError, match="inconnue"):
        entrypoint.main(spark, {"table": "not_a_table", "catalog": "it", "schema": "sch"})


def test_main_first_run_dispatches_table_daily_without_window_filter(
    fakes: SimpleNamespace,
) -> None:
    result_df = fakes.DataFrame("table_daily_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(spark, {"table": "table_daily", "catalog": "it", "schema": "sch"})
    build_query = spark.sql_calls[0]
    assert "period_start >= DATE" not in build_query
    assert "it.sch.gold_dbx_usage_table_daily" in result_df.saved_as


def test_main_subsequent_run_uses_incremental_window_and_merges(
    fakes: SimpleNamespace,
) -> None:
    result_df = fakes.DataFrame("table_daily_result")
    # Un run suivant emet d'abord le scan de couverture de la table cible, puis la
    # requete du builder : `sql_result` est consomme dans cet ordre.
    spark = fakes.Spark(
        existing_tables={TARGET_TABLE_DAILY},
        sql_result=[_continuous_coverage(), result_df],
    )
    entrypoint.main(spark, {"table": "table_daily", "catalog": "it", "schema": "sch"})
    build_query = spark.sql_calls[1]
    assert "AND period_start >= DATE" in build_query
    assert any("MERGE" in call for call in spark.sql_calls[2:])


def test_main_dispatches_table_popularity_daily(fakes: SimpleNamespace) -> None:
    result_df = fakes.DataFrame("table_popularity_daily_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(
        spark, {"table": "table_popularity_daily", "catalog": "it", "schema": "sch"}
    )
    build_query = spark.sql_calls[0]
    assert "it.sch.gold_dbx_usage_table_daily" in build_query
    assert "it.sch.gold_dbx_usage_table_popularity_daily" in result_df.saved_as


def test_main_dispatches_consumer_daily(fakes: SimpleNamespace) -> None:
    result_df = fakes.DataFrame("consumer_daily_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(spark, {"table": "consumer_daily", "catalog": "it", "schema": "sch"})
    build_query = spark.sql_calls[0]
    assert "it.sch.gold_dbx_usage_table_daily" in build_query
    assert "it.sch.gold_dbx_usage_consumer_daily" in result_df.saved_as


def test_main_dispatches_table_query_performance_daily(fakes: SimpleNamespace) -> None:
    result_df = fakes.DataFrame("table_query_performance_daily_result")
    spark = fakes.Spark(existing_tables=set(), sql_result=result_df)
    entrypoint.main(
        spark,
        {"table": "table_query_performance_daily", "catalog": "it", "schema": "sch"},
    )
    build_query = spark.sql_calls[0]
    # Le test de DISPATCH atteste qu'on construit CE builder-la sur les bonnes tables
    # sources ; le detail de ses predicats appartient a ses propres tests.
    assert "it.sch.curated_dbx_access_table_lineage" in build_query
    assert "it.sch.curated_dbx_query_history" in build_query
    assert "lineage_query AS (" in build_query
    assert (
        "it.sch.gold_dbx_usage_table_query_performance_daily" in result_df.saved_as
    )


def test_main_dispatches_table_catalog_without_window_filter_even_if_target_exists(
    fakes: SimpleNamespace,
) -> None:
    # table_catalog n'a pas de watermark (snapshot) : meme si la table cible
    # existe deja, `_resolve_lower_bound` doit rester `None`.
    target = "it.sch.gold_dbx_usage_table_catalog"
    result_df = fakes.DataFrame("table_catalog_result")
    spark = fakes.Spark(existing_tables={target}, sql_result=result_df)
    entrypoint.main(spark, {"table": "table_catalog", "catalog": "it", "schema": "sch"})
    build_query = spark.sql_calls[0]
    assert "it.sch.curated_dbx_uc_tables" in build_query
    assert "it.sch.curated_dbx_uc_table_tags" in build_query
    assert "it.sch.curated_dbx_uc_table_operations" in build_query
    assert "it.sch.gold_dbx_usage_table_daily" in build_query
    assert any("MERGE" in call and target in call for call in spark.sql_calls[1:])


def test_main_dispatches_table_governance_without_window_filter_even_if_target_exists(
    fakes: SimpleNamespace,
) -> None:
    # table_governance n'a pas de watermark (snapshot) : meme si la table
    # cible existe deja, `_resolve_lower_bound` doit rester `None`.
    target = "it.sch.gold_dbx_usage_table_governance"
    result_df = fakes.DataFrame("table_governance_result")
    spark = fakes.Spark(existing_tables={target}, sql_result=result_df)
    entrypoint.main(spark, {"table": "table_governance", "catalog": "it", "schema": "sch"})
    build_query = spark.sql_calls[0]
    assert "it.sch.gold_dbx_usage_table_catalog" in build_query
    assert "it.sch.gold_dbx_usage_table_popularity_daily" in build_query
    assert any("MERGE" in call and target in call for call in spark.sql_calls[1:])


def test_main_dispatches_recommendations_reading_all_four_upstream_gold_tables(
    fakes: SimpleNamespace,
) -> None:
    # recommendations n'a pas de watermark (snapshot) : meme si la table
    # cible existe deja, `_resolve_lower_bound` doit rester `None`. Lit les 5
    # tables gold amont (governance/catalog/popularity_daily/
    # query_performance_daily/consumer).
    target = "it.sch.gold_dbx_usage_recommendations"
    result_df = fakes.DataFrame("recommendations_result")
    spark = fakes.Spark(existing_tables={target}, sql_result=result_df)
    entrypoint.main(spark, {"table": "recommendations", "catalog": "it", "schema": "sch"})
    build_query = spark.sql_calls[0]
    assert "it.sch.gold_dbx_usage_table_governance" in build_query
    assert "it.sch.gold_dbx_usage_table_catalog" in build_query
    assert "it.sch.gold_dbx_usage_table_popularity_daily" in build_query
    assert "it.sch.gold_dbx_usage_table_query_performance_daily" in build_query
    assert "it.sch.gold_dbx_usage_consumer_daily" in build_query
    assert any("MERGE" in call and target in call for call in spark.sql_calls[1:])


def test_main_requires_warehouse_id_for_forecast_daily(fakes: SimpleNamespace) -> None:
    # ai_forecast exige un SQL Warehouse, incompatible avec l'environnement
    # serverless generique de ce job - warehouse_id est donc obligatoire pour
    # cette table uniquement (pas pour les 7 autres).
    spark = fakes.Spark()
    with pytest.raises(ValueError, match="warehouse_id"):
        entrypoint.main(
            spark, {"table": "forecast_daily", "catalog": "it", "schema": "sch"}
        )


def test_main_logs_the_deleted_table_count_per_cloud_provider(
    fakes: SimpleNamespace, caplog: pytest.LogCaptureFixture
) -> None:
    """Mesure de controle FR-018 : un pic de suppressions doit etre visible.

    Aucune table de metrique dediee (P12) -- le compte s'agrege directement sur la
    table qui porte l'etat, une fois ecrite : la mesure porte alors sur ce qui est
    reellement publie, et non sur un plan recalcule une seconde fois.
    """
    target = "it.sch.gold_dbx_usage_table_catalog"
    result_df = fakes.DataFrame("table_catalog_result", rows=[["aws", 3], ["azure", 1]])
    spark = fakes.Spark(existing_tables={target}, sql_result=result_df)
    with caplog.at_level(logging.INFO, logger=entrypoint.__name__):
        entrypoint.main(spark, {"table": "table_catalog", "catalog": "it", "schema": "sch"})
    count_query = spark.sql_calls[-1]
    assert f"FROM {target}" in count_query
    assert "WHERE is_deleted" in count_query
    assert "GROUP BY cloud_provider" in count_query
    assert "aws=3" in caplog.text
    assert "azure=1" in caplog.text


def test_main_purges_ephemeral_rows_between_writing_the_registry_and_counting(
    fakes: SimpleNamespace,
) -> None:
    """L'ordre des trois etapes est porteur de sens, pas une preference de style.

    La purge doit suivre l'ECRITURE -- c'est le MERGE du writer qui vient de reposer les
    lignes, et lui ne supprime jamais -- et preceder le COMPTAGE, sinon la mesure de
    controle FR-018 annonce des suppressions qui ne sont plus dans la table.
    """
    target = "it.sch.gold_dbx_usage_table_catalog"
    result_df = fakes.DataFrame("table_catalog_result")
    spark = fakes.Spark(existing_tables={target}, sql_result=result_df)
    entrypoint.main(spark, {"table": "table_catalog", "catalog": "it", "schema": "sch"})
    purges = [call for call in spark.sql_calls if "WHEN MATCHED THEN DELETE" in call]
    assert len(purges) == 1
    purge = purges[0]
    assert f"MERGE INTO {target}" in purge
    assert "it.sch.curated_dbx_uc_tables" in purge
    assert "it.sch.curated_dbx_uc_table_operations" in purge
    # Compare a l'indice du MERGE D'ECRITURE, jamais a `0 < i < len - 1` : cet encadrement
    # accepte tous les indices intermediaires, et les commentaires/`ALTER COLUMN` du writer
    # en occupent des dizaines. Deplacer la purge AVANT l'ecriture le laisserait vrai,
    # alors que c'est precisement l'ordre epingle ici.
    write_index = next(
        index
        for index, call in enumerate(spark.sql_calls)
        if "MERGE WITH SCHEMA EVOLUTION" in call or ("MERGE INTO" in call and call is not purge)
    )
    purge_index = spark.sql_calls.index(purge)
    count_index = len(spark.sql_calls) - 1
    assert write_index < purge_index < count_index
    assert "WHERE is_deleted" in spark.sql_calls[count_index]


def test_the_purged_perimeter_is_exactly_the_tables_carrying_the_table_key() -> None:
    """Le perimetre est ecrit en dur, mais il n'est pas arbitraire : il se DERIVE.

    Une table gold porte la cle de table ou ne la porte pas ; celles qui la portent doivent
    toutes etre purgees, sinon elles accumulent des lignes d'ephemeres sans aucun signal.
    La liste reste explicite dans le module -- un lecteur doit voir laquelle est concernee
    sans executer une comprehension -- et ce test interdit qu'elle derive du critere. Une
    nouvelle table gold portant la cle fait tomber ce test, pas un incident en production.
    """
    derived = {
        name
        for name, spec in specs.GOLD_SPECS.items()
        if set(TABLE_KEY_COLUMNS) <= set(spec.merge_keys)
    }
    assert derived == set(entrypoint.PURGED_OF_EPHEMERAL_TABLES)


@pytest.mark.parametrize(
    "table",
    ["table_daily", "table_popularity_daily", "table_query_performance_daily", "table_governance"],
)
def test_main_also_purges_ephemeral_rows_from_the_tables_keyed_by_table(
    fakes: SimpleNamespace, table: str
) -> None:
    """Purger le registre SEUL livrerait l'inverse du but poursuivi.

    L'exclusion en aval lit la PRESENCE d'une ligne `is_deleted` au registre, jamais
    l'absence de ligne : retirer cette ligne sans retirer les lignes de fait rendrait
    l'ephemere visible comme une table VIVANTE dans les pages d'usage. Et `table_governance`
    est ecrite sans `absent_row_delete_predicate` : une cle que le registre ne produit plus
    n'y serait ni rafraichie ni supprimee, elle gelerait.
    """
    spec = specs.GOLD_SPECS[table]
    target = f"it.sch.{spec.target_table}"
    result_df = fakes.DataFrame(f"{table}_result")
    spark = _spark_for(fakes, spec, target, result_df)
    entrypoint.main(spark, {"table": table, "catalog": "it", "schema": "sch"})
    purges = [call for call in spark.sql_calls if "WHEN MATCHED THEN DELETE" in call]
    assert len(purges) == 1
    assert f"MERGE INTO {target} AS cible" in purges[0]


@pytest.mark.parametrize("table", ["consumer_daily", "recommendations"])
def test_main_does_not_purge_the_tables_that_carry_no_table_key(
    fakes: SimpleNamespace, table: str
) -> None:
    """Deux tables restent hors purge, pour deux raisons differentes.

    `consumer_daily` est au grain CONSOMMATEUR : elle ne porte aucune colonne de la cle de
    table, il n'y a rien a apparier -- elle herite du filtre par `table_daily`.
    `recommendations` s'auto-repare : son `FULL OUTER JOIN` avec l'existant marque
    `status = 'RESOLVED'` toute recommandation dont le candidat n'est plus emis, et les
    sources de ses candidats sont justement purgees.
    """
    spec = specs.GOLD_SPECS[table]
    target = f"it.sch.{spec.target_table}"
    result_df = fakes.DataFrame(f"{table}_result")
    spark = _spark_for(fakes, spec, target, result_df)
    entrypoint.main(spark, {"table": table, "catalog": "it", "schema": "sch"})
    assert not any("WHEN MATCHED THEN DELETE" in call for call in spark.sql_calls)


def test_main_does_not_count_deleted_tables_for_the_other_gold_tables(
    fakes: SimpleNamespace,
) -> None:
    """La mesure ne porte QUE sur le registre : les 4 tables de fait ne portent pas
    `is_deleted` (interdiction de denormalisation), une agregation dessus echouerait
    a l'analyse."""
    target = "it.sch.gold_dbx_usage_table_governance"
    result_df = fakes.DataFrame("table_governance_result")
    spark = fakes.Spark(existing_tables={target}, sql_result=result_df)
    entrypoint.main(spark, {"table": "table_governance", "catalog": "it", "schema": "sch"})
    assert not any("WHERE is_deleted" in call for call in spark.sql_calls)


def test_main_passes_the_table_catalog_to_the_forecast_builder(
    fakes: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sans ce parametre, le forecast n'a aucun moyen de connaitre l'etat de cycle
    de vie : `table_popularity_daily` ne le porte pas et ne doit pas le porter."""
    captured: dict[str, Any] = {}

    def _capture(spark: object, **kwargs: Any) -> None:  # noqa: ANN401
        captured.update(kwargs)

    monkeypatch.setattr(entrypoint, "write_usage_forecast", _capture)
    entrypoint.main(
        fakes.Spark(),
        {
            "table": "forecast_daily",
            "catalog": "it",
            "schema": "sch",
            "warehouse_id": "wh-1",
        },
    )
    assert captured["table_catalog_table"] == "it.sch.gold_dbx_usage_table_catalog"
