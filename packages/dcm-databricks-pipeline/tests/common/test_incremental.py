"""Tests de `pipelines.common.incremental` (watermark, lookback, pruning)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pipelines.common.incremental as incremental
import pipelines.system_tables.specs as specs

# ---------------------------------------------------------------------------
# compute_lower_bound — borne basse incrementale
# ---------------------------------------------------------------------------


def test_compute_lower_bound_returns_none_without_watermark(fakes: SimpleNamespace) -> None:
    spark = fakes.Spark(existing_tables={specs.BILLING_LIST_PRICES_SPEC.curated_table})

    assert incremental.compute_lower_bound(spark, specs.BILLING_LIST_PRICES_SPEC, "aws", 3) is None
    assert spark.sql_calls == []


def test_compute_lower_bound_returns_none_when_table_absent(fakes: SimpleNamespace) -> None:
    spark = fakes.Spark(existing_tables=set())

    assert incremental.compute_lower_bound(spark, specs.BILLING_USAGE_SPEC, "aws", 3) is None
    assert spark.sql_calls == []


def test_compute_lower_bound_subtracts_lookback(fakes: SimpleNamespace) -> None:
    watermark = datetime(2026, 7, 30, 12, 0, 0)
    result_row = SimpleNamespace(collect=lambda: [{"wm": watermark}])
    spark = fakes.Spark(
        existing_tables={specs.BILLING_USAGE_SPEC.curated_table}, sql_result=result_row
    )

    lower = incremental.compute_lower_bound(spark, specs.BILLING_USAGE_SPEC, "aws", 3)

    assert lower == datetime(2026, 7, 27, 12, 0, 0)
    assert "MAX(usage_end_time)" in spark.sql_calls[0]
    assert "cloud_provider = 'aws'" in spark.sql_calls[0]


def test_compute_lower_bound_returns_none_when_watermark_null(fakes: SimpleNamespace) -> None:
    result_row = SimpleNamespace(collect=lambda: [{"wm": None}])
    spark = fakes.Spark(
        existing_tables={specs.BILLING_USAGE_SPEC.curated_table}, sql_result=result_row
    )

    assert incremental.compute_lower_bound(spark, specs.BILLING_USAGE_SPEC, "azure", 3) is None


# ---------------------------------------------------------------------------
# compute_lower_bound — fenetre de backfill initiale (premier run)
# ---------------------------------------------------------------------------


def test_compute_lower_bound_uses_initial_window_when_table_absent(fakes: SimpleNamespace) -> None:
    spec = replace(specs.BILLING_USAGE_SPEC, initial_lookback_days=30)
    spark = fakes.Spark(existing_tables=set())

    lower = incremental.compute_lower_bound(spark, spec, "azure", 3)

    assert lower is not None
    expected = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
    assert abs((lower - expected).total_seconds()) < 60
    assert spark.sql_calls == []


def test_compute_lower_bound_uses_initial_window_when_no_rows(fakes: SimpleNamespace) -> None:
    spec = replace(specs.BILLING_USAGE_SPEC, initial_lookback_days=30)
    result_row = SimpleNamespace(collect=lambda: [{"wm": None}])
    spark = fakes.Spark(existing_tables={spec.curated_table}, sql_result=result_row)

    lower = incremental.compute_lower_bound(spark, spec, "azure", 3)

    assert lower is not None
    expected = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
    assert abs((lower - expected).total_seconds()) < 60


def test_compute_lower_bound_full_backfill_when_no_initial_window(fakes: SimpleNamespace) -> None:
    # Sans `initial_lookback_days`, le premier run reste un backfill complet
    # (comportement FinOps : historique de couts). None => aucun filtre.
    spark = fakes.Spark(existing_tables=set())

    assert specs.BILLING_USAGE_SPEC.initial_lookback_days is None
    assert incremental.compute_lower_bound(spark, specs.BILLING_USAGE_SPEC, "aws", 3) is None


# ---------------------------------------------------------------------------
# gap_scan_sql — diagnostic de couverture de la table cible (fonction pure)
# ---------------------------------------------------------------------------

_GAP_TARGET = "it.sch.gold_dbx_compute_cluster_cost_daily"
_GAP_TODAY = date(2026, 8, 17)


def _gap_scan(*, generated_at_column: str | None = "_generated_at", lookback_days: int = 3) -> str:
    return incremental.gap_scan_sql(
        _GAP_TARGET,
        "period_start",
        inspection_floor=_GAP_TODAY - timedelta(days=90),
        lookback_days=lookback_days,
        generated_at_column=generated_at_column,
    )


def test_gap_scan_sql_aggregates_the_target_table_by_watermark_day() -> None:
    sql = _gap_scan()

    assert f"FROM {_GAP_TARGET}" in sql
    assert "SELECT to_date(period_start) AS day" in sql
    assert "GROUP BY to_date(period_start)" in sql


def test_gap_scan_sql_bounds_the_inspection_to_the_detection_window() -> None:
    # Plancher d'inspection explicite : le cout du scan de detection doit rester
    # stable dans le temps (cf. DEFAULT_GAP_DETECTION_WINDOW_DAYS), un trou plus
    # ancien ne se repare que par `--full-refresh`.
    sql = _gap_scan()

    assert "WHERE to_date(period_start) >= DATE '2026-05-19'" in sql


def test_gap_scan_sql_reports_the_first_interior_hole_only() -> None:
    # Un jour absent AVANT le premier jour present n'est pas un trou : une table
    # dont l'historique commence le 6 juillet (retention de la source curated)
    # ne doit pas etre recalculee depuis l'origine des temps. La detection porte
    # donc sur l'ecart entre deux jours presents (LEAD), pas sur un calendrier.
    sql = _gap_scan()

    assert "LEAD(day) OVER (ORDER BY day) AS next_day" in sql
    assert (
        "MIN(CASE WHEN next_day > date_add(day, 1) THEN date_add(day, 1) END)\n"
        "            AS first_missing_day" in sql
    )


def test_gap_scan_sql_flags_a_day_written_before_the_source_could_settle() -> None:
    # Jour present mais ecrit avant que curated ait absorbe ses arrivees tardives
    # (run trop precoce) : sous-compte, donc a recalculer bien qu'il soit present.
    # Borne INCLUSIVE (`<=`) : une ecriture pile a `jour + lookback_days` tombe le
    # jour de la fermeture de la fenetre, donc avant qu'elle ne soit fermee.
    sql = _gap_scan(lookback_days=3)

    assert "MAX(_generated_at) AS last_written_at" in sql
    assert (
        "MIN(CASE WHEN to_date(last_written_at) <= date_add(day, 3) THEN day END)"
        " AS first_unsettled_day" in sql
    )


def test_gap_scan_sql_without_generated_at_column_never_flags_unsettled_days() -> None:
    # Table cible sans colonne d'horodatage d'ecriture : la stabilisation n'est
    # pas mesurable, la colonne doit rester typee (CAST) pour que la lecture de
    # la ligne de resultat reste uniforme cote appelant.
    sql = _gap_scan(generated_at_column=None)

    assert "CAST(NULL AS DATE) AS first_unsettled_day" in sql
    assert "CAST(NULL AS TIMESTAMP) AS last_written_at" in sql
    assert "MAX(_generated_at)" not in sql


# ---------------------------------------------------------------------------
# compute_gap_aware_lower_bound — borne ancree sur la couverture reelle
# ---------------------------------------------------------------------------


def _gap_row(
    *,
    last_day: date | None = _GAP_TODAY,
    first_missing_day: date | None = None,
    first_unsettled_day: date | None = None,
) -> SimpleNamespace:
    row = {
        "last_day": last_day,
        "first_missing_day": first_missing_day,
        "first_unsettled_day": first_unsettled_day,
    }
    return SimpleNamespace(collect=lambda: [row])


def _gap_aware_bound(fakes: SimpleNamespace, row: SimpleNamespace) -> date:
    spark = fakes.Spark(existing_tables={_GAP_TARGET}, sql_result=row)
    return incremental.compute_gap_aware_lower_bound(
        spark,
        target_table=_GAP_TARGET,
        watermark_column="period_start",
        lookback_days=3,
        today=_GAP_TODAY,
        generated_at_column="_generated_at",
    )


def test_gap_aware_lower_bound_is_the_nominal_window_on_a_continuous_table(
    fakes: SimpleNamespace,
) -> None:
    # Cas courant (run quotidien nominal) : couverture continue jusqu'a today,
    # aucun elargissement -> le cout du dispositif est nul le reste du temps.
    assert _gap_aware_bound(fakes, _gap_row()) == _GAP_TODAY - timedelta(days=3)


def test_gap_aware_lower_bound_widens_down_to_an_interior_hole(fakes: SimpleNamespace) -> None:
    # Le recalcul repart DU TROU, pas du seul jour manquant : les jours qui le
    # suivent ont ete agreges depuis une source incomplete.
    hole = date(2026, 8, 4)

    assert _gap_aware_bound(fakes, _gap_row(first_missing_day=hole)) == hole


def test_gap_aware_lower_bound_recomputes_the_last_written_day(fakes: SimpleNamespace) -> None:
    # Trou de QUEUE (pipeline arretee plusieurs semaines) : equivalent du
    # `MAX(watermark)` de `compute_lower_bound` cote curated. La reprise inclut le
    # dernier jour ecrit LUI-MEME (et non `+ 1 jour`) : il est le moins stabilise
    # de tous, curated etant encore en train d'arriver quand il a ete ecrit.
    last_written = date(2026, 7, 20)

    assert _gap_aware_bound(fakes, _gap_row(last_day=last_written)) == last_written


def test_gap_aware_lower_bound_widens_down_to_an_unsettled_day(fakes: SimpleNamespace) -> None:
    unsettled = date(2026, 8, 9)

    assert _gap_aware_bound(fakes, _gap_row(first_unsettled_day=unsettled)) == unsettled


def test_gap_aware_lower_bound_keeps_the_lowest_of_all_candidates(fakes: SimpleNamespace) -> None:
    # Plusieurs anomalies simultanees : la borne la plus basse gagne (aucune
    # cause de recalcul ne doit etre masquee par une autre).
    row = _gap_row(
        last_day=date(2026, 8, 12),
        first_missing_day=date(2026, 8, 4),
        first_unsettled_day=date(2026, 7, 29),
    )

    assert _gap_aware_bound(fakes, row) == date(2026, 7, 29)


def test_gap_aware_lower_bound_falls_back_to_nominal_window_on_empty_coverage(
    fakes: SimpleNamespace,
) -> None:
    # Table cible existante mais vide (ou entierement hors fenetre d'inspection) :
    # les 3 scalaires sont NULL. La fenetre nominale s'applique, sans planter.
    row = _gap_row(last_day=None)

    assert _gap_aware_bound(fakes, row) == _GAP_TODAY - timedelta(days=3)


def test_gap_aware_lower_bound_accepts_a_timestamp_watermark(fakes: SimpleNamespace) -> None:
    # `to_date(...)` renvoie une DATE, mais un watermark deja de type TIMESTAMP
    # peut remonter tel quel selon le connecteur : normalise via `_as_date`.
    row = SimpleNamespace(
        collect=lambda: [
            {
                "last_day": datetime(2026, 7, 20, 23, 59, 59),
                "first_missing_day": None,
                "first_unsettled_day": None,
            }
        ]
    )

    assert _gap_aware_bound(fakes, row) == date(2026, 7, 20)


# ---------------------------------------------------------------------------
# Regression : le 2026-08-27 de `gold_dbx_compute_cluster_cost_daily` (dev)
#
# Cas reel mesure : jour ecrit une seule fois, le 2026-08-30, soit exactement
# `jour + lookback_days` (3). Aucun trou interieur, aucun jour manquant autour —
# les deux tests ci-dessous couvrent les deux maillons qui le laissaient passer :
# la borne stricte du scan SQL, puis la reprise a `last_day + 1`.
# ---------------------------------------------------------------------------

_REGRESSION_DAY = date(2026, 8, 27)
_REGRESSION_WRITTEN_AT = date(2026, 8, 30)
_REGRESSION_RUN_DAY = date(2026, 9, 4)


def test_gap_scan_sql_flags_the_day_written_exactly_at_its_window_close() -> None:
    # Avec une borne stricte, `to_date('2026-08-30') < date_add('2026-08-27', 3)`
    # est faux : le jour etait declare stabilise alors que sa DERNIERE ecriture
    # tombait le jour meme de la fermeture de sa fenetre, donc sans aucune
    # ecriture posterieure (2 242 clusters en gold pour 9 123 en curated, 652 $
    # au lieu de ~3 800 $). L'expression doit rendre ce jour eligible.
    sql = _gap_scan(lookback_days=3)

    # L'ecriture tombe PILE sur la fermeture de la fenetre : c'est ce que la
    # comparaison inclusive rattrape, et que `<` laissait passer.
    assert _REGRESSION_DAY + timedelta(days=3) == _REGRESSION_WRITTEN_AT
    assert "to_date(last_written_at) <= date_add(day, 3)" in sql


def test_gap_aware_lower_bound_recomputes_the_last_written_day_instead_of_skipping_it(
    fakes: SimpleNamespace,
) -> None:
    # Deuxieme maillon : au run du 2026-09-04, le scan remontait `last_day` =
    # 2026-08-27 avec `first_missing_day` et `first_unsettled_day` NULL. Le
    # candidat `last_day + 1` fixait la borne au 2026-08-28 et condamnait le 27
    # definitivement (aucun run ulterieur ne pouvait plus le recalculer).
    spark = fakes.Spark(
        existing_tables={_GAP_TARGET}, sql_result=_gap_row(last_day=_REGRESSION_DAY)
    )

    bound = incremental.compute_gap_aware_lower_bound(
        spark,
        target_table=_GAP_TARGET,
        watermark_column="period_start",
        lookback_days=3,
        today=_REGRESSION_RUN_DAY,
        generated_at_column="_generated_at",
    )

    assert bound == _REGRESSION_DAY
    assert bound != _REGRESSION_DAY + timedelta(days=1)


# ---------------------------------------------------------------------------
# partition_predicate — pruning de partition
# ---------------------------------------------------------------------------


def test_partition_predicate_uses_lowest_bound() -> None:
    aws = datetime(2026, 7, 27, 0, 0, 0)
    azure = datetime(2026, 7, 25, 0, 0, 0)

    predicate = incremental.partition_predicate(specs.BILLING_USAGE_SPEC, aws, azure)

    assert predicate == "t.usage_date >= DATE '2026-07-25'"


def test_partition_predicate_none_when_not_partitioned() -> None:
    lower = datetime(2026, 7, 27, 0, 0, 0)

    assert incremental.partition_predicate(specs.BILLING_LIST_PRICES_SPEC, lower, None) is None


def test_partition_predicate_none_on_full_load() -> None:
    assert incremental.partition_predicate(specs.BILLING_USAGE_SPEC, None, None) is None
