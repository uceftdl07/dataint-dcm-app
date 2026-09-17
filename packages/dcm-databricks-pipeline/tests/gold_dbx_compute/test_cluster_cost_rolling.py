"""Tests de `pipelines.gold_dbx_compute.cluster_cost_rolling` (regles de derivation).

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`, qui n'instancie
jamais de Spark reel) : `build_cluster_cost_rolling` construit un unique
`spark.sql(...)`, verifie ici via le texte SQL genere (`FakeSpark`).
"""

from __future__ import annotations

from types import SimpleNamespace

from pipelines.gold_dbx_compute.cluster_cost_rolling import build_cluster_cost_rolling


def _rolling_query(fakes: SimpleNamespace) -> tuple[str, object]:
    sentinel = fakes.DataFrame("cost_rolling_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_cluster_cost_rolling(
        spark,
        cluster_cost_daily_table="it.sch.gold_dbx_compute_cluster_cost_daily",
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0], result


def test_cluster_cost_rolling_reads_only_daily_table_no_curated(
    fakes: SimpleNamespace,
) -> None:
    # Rollup pur : lit UNIQUEMENT la table quotidienne gold, jamais une table
    # curated (les metriques cout/DBU sont additives -> somme exacte sans
    # relecture curated).
    query, _ = _rolling_query(fakes)
    assert "it.sch.gold_dbx_compute_cluster_cost_daily" in query
    assert "curated_" not in query


def test_cluster_cost_rolling_keeps_only_all_purpose_clusters(
    fakes: SimpleNamespace,
) -> None:
    # SC-001 : la liste gold ne retient que les clusters ALL_PURPOSE ; les
    # cluster_id ephemeres JOB/PIPELINE sont exclus des la CTE daily.
    query, _ = _rolling_query(fakes)
    assert (
        "FROM it.sch.gold_dbx_compute_cluster_cost_daily\n"
        "        WHERE cluster_type = 'ALL_PURPOSE'" in query
    )


def test_cluster_cost_rolling_materializes_the_four_configured_windows(
    fakes: SimpleNamespace,
) -> None:
    # Une ligne par fenetre via explode(array(1, 7, 30, 90)) -> colonne
    # window_days (defaut ROLLING_WINDOWS).
    query, _ = _rolling_query(fakes)
    assert "explode(array(1, 7, 30, 90)) AS window_days" in query


def test_cluster_cost_rolling_anchors_windows_on_max_period_start(
    fakes: SimpleNamespace,
) -> None:
    # Toutes les fenetres sont ancrees sur le meme dernier jour disponible
    # (MAX(period_start)) : le classement cost_rank compare les clusters sur
    # des periodes de meme borne haute.
    query, _ = _rolling_query(fakes)
    assert "MAX(period_start) AS as_of_date" in query
    assert "date_add(a.as_of_date, -(w.window_days - 1)) AS window_start" in query


def test_cluster_cost_rolling_sums_additive_metrics_over_window(
    fakes: SimpleNamespace,
) -> None:
    # Fenetre courante = (as_of - window_days, as_of] : period_start >
    # as_of - window_days.
    query, _ = _rolling_query(fakes)
    assert "WHEN d.period_start > date_add(a.as_of_date, -w.window_days)" in query
    assert "THEN d.dbu_quantity ELSE 0" in query
    assert "THEN d.cost_usd ELSE 0" in query


def test_cluster_cost_rolling_computes_previous_equal_length_window(
    fakes: SimpleNamespace,
) -> None:
    # Fenetre precedente de MEME longueur = (as_of - 2*window_days,
    # as_of - window_days] : period_start <= as_of - window_days, borne par le
    # WHERE a as_of - 2*window_days.
    query, _ = _rolling_query(fakes)
    assert "WHEN d.period_start <= date_add(a.as_of_date, -w.window_days)" in query
    assert "AS cost_usd_prev_window" in query
    assert "d.period_start > date_add(a.as_of_date, -2 * w.window_days)" in query
    assert (
        "(g.cost_usd - g.cost_usd_prev_window)\n"
        "            / NULLIF(g.cost_usd_prev_window, 0) * 100 AS cost_delta_pct" in query
    )


def test_cluster_cost_rolling_ranks_within_each_window(fakes: SimpleNamespace) -> None:
    # cost_rank partitionne par window_days (pas globalement) : un cluster est
    # classe vs les autres SUR LA MEME fenetre.
    query, _ = _rolling_query(fakes)
    assert "RANK() OVER (PARTITION BY g.window_days ORDER BY g.cost_usd DESC) AS cost_rank" in query
    assert (
        "RANK() OVER (PARTITION BY g.window_days ORDER BY g.cost_usd DESC)\n"
        "            <= 10 AS is_top_cost" in query
    )


def test_cluster_cost_rolling_keeps_latest_descriptive_attributes(
    fakes: SimpleNamespace,
) -> None:
    # Identite/attribution resolue au dernier etat connu du cluster (ligne
    # period_start la plus recente), pas repetee par fenetre.
    query, _ = _rolling_query(fakes)
    assert (
        "QUALIFY ROW_NUMBER() OVER (\n"
        "            PARTITION BY cloud_provider, workspace_id, cluster_id\n"
        "            ORDER BY period_start DESC\n"
        "        ) = 1" in query
    )
    for attr in ("cluster_name", "cluster_type", "owner", "cost_center", "sku_group"):
        assert f"la.{attr}" in query


def test_cluster_cost_rolling_drops_day_over_day_columns(fakes: SimpleNamespace) -> None:
    # cost_usd_prev_day / delta J-1 n'ont pas de sens a la maille fenetre :
    # remplaces par cost_usd_prev_window.
    query, _ = _rolling_query(fakes)
    assert "cost_usd_prev_day" not in query


def test_cluster_cost_rolling_excludes_objects_inactive_in_both_windows(
    fakes: SimpleNamespace,
) -> None:
    # Un cluster sans cout ni fenetre courante ni precedente n'est pas
    # materialise (evite 4 lignes par cluster mort > 90 jours).
    query, _ = _rolling_query(fakes)
    assert "WHERE g.cost_usd <> 0 OR g.cost_usd_prev_window <> 0" in query


def test_cluster_cost_rolling_custom_windows_and_threshold(fakes: SimpleNamespace) -> None:
    sentinel = fakes.DataFrame("cost_rolling_result")
    spark = fakes.Spark(sql_result=sentinel)
    build_cluster_cost_rolling(
        spark,
        cluster_cost_daily_table="it.sch.gold_dbx_compute_cluster_cost_daily",
        rolling_windows=(1, 14),
        top_cost_rank_threshold=5,
    )
    query = spark.sql_calls[0]
    assert "explode(array(1, 14)) AS window_days" in query
    assert "<= 5 AS is_top_cost" in query
