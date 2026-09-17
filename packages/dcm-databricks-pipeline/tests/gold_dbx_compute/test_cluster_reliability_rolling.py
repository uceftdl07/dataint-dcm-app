"""Tests de `pipelines.gold_dbx_compute.cluster_reliability_rolling` (regles de derivation).

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`) :
`build_cluster_reliability_rolling` construit un unique `spark.sql(...)`, verifie
ici via le texte SQL genere (`FakeSpark`).
"""

from __future__ import annotations

from types import SimpleNamespace

from pipelines.gold_dbx_compute.cluster_reliability_rolling import (
    build_cluster_reliability_rolling,
)


def _rolling_query(fakes: SimpleNamespace) -> tuple[str, object]:
    sentinel = fakes.DataFrame("reliability_rolling_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_cluster_reliability_rolling(
        spark,
        cluster_reliability_daily_table="it.sch.gold_dbx_compute_cluster_reliability_daily",
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0], result


def test_cluster_reliability_rolling_reads_only_daily_table_no_curated(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "it.sch.gold_dbx_compute_cluster_reliability_daily" in query
    assert "curated_" not in query


def test_cluster_reliability_rolling_materializes_the_four_configured_windows(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "explode(array(1, 7, 30, 90)) AS window_days" in query


def test_cluster_reliability_rolling_anchors_windows_on_max_period_start(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "MAX(period_start) AS as_of_date" in query
    assert "date_add(a.as_of_date, -(w.window_days - 1)) AS window_start" in query


def test_cluster_reliability_rolling_sums_additive_counts_over_window(
    fakes: SimpleNamespace,
) -> None:
    # start_count et unexpected_termination_count sont additifs -> somme
    # directe sur la fenetre courante.
    query, _ = _rolling_query(fakes)
    assert "SUM(d.start_count) AS start_count" in query
    assert "SUM(d.unexpected_termination_count) AS unexpected_termination_count" in query
    assert "WHERE d.period_start > date_add(a.as_of_date, -w.window_days)" in query


def test_cluster_reliability_rolling_weights_avg_startup_by_start_count(
    fakes: SimpleNamespace,
) -> None:
    # avg_startup_seconds est une moyenne : recalculee ponderee par le nombre
    # de demarrages du jour (SUM(avg * start_count) / SUM(start_count)), les
    # jours sans latence mesuree etant exclus de la ponderation.
    query, _ = _rolling_query(fakes)
    assert "d.avg_startup_seconds * d.start_count" in query
    assert "AS avg_startup_seconds" in query
    assert "WHEN d.avg_startup_seconds IS NOT NULL" in query


def test_cluster_reliability_rolling_keeps_latest_categorical_and_config(
    fakes: SimpleNamespace,
) -> None:
    # cluster_type / top_termination_reason / config d'auto-arret repris au
    # dernier etat connu (pas agreges sur la fenetre).
    query, _ = _rolling_query(fakes)
    assert (
        "QUALIFY ROW_NUMBER() OVER (\n"
        "            PARTITION BY cloud_provider, workspace_id, cluster_id\n"
        "            ORDER BY period_start DESC\n"
        "        ) = 1" in query
    )
    for attr in (
        "cluster_name",
        "cluster_type",
        "top_termination_reason",
        "auto_termination_minutes",
        "has_auto_termination",
    ):
        assert f"la.{attr}" in query


def test_cluster_reliability_rolling_excludes_inactive_objects(
    fakes: SimpleNamespace,
) -> None:
    # Un cluster sans demarrage ni terminaison anormale sur la fenetre n'est
    # pas materialise.
    query, _ = _rolling_query(fakes)
    assert "WHERE g.start_count > 0 OR g.unexpected_termination_count > 0" in query


def test_cluster_reliability_rolling_custom_windows(fakes: SimpleNamespace) -> None:
    sentinel = fakes.DataFrame("reliability_rolling_result")
    spark = fakes.Spark(sql_result=sentinel)
    build_cluster_reliability_rolling(
        spark,
        cluster_reliability_daily_table="it.sch.gold_dbx_compute_cluster_reliability_daily",
        rolling_windows=(1, 14),
    )
    query = spark.sql_calls[0]
    assert "explode(array(1, 14)) AS window_days" in query
