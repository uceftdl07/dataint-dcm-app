"""Tests de `pipelines.gold_dbx_compute.job_cluster_cost_rolling` (regles de derivation).

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`) :
`build_job_cluster_cost_rolling` construit un unique `spark.sql(...)`, verifie ici
via le texte SQL genere (`FakeSpark`).
"""

from __future__ import annotations

from types import SimpleNamespace

from pipelines.gold_dbx_compute.job_cluster_cost_rolling import build_job_cluster_cost_rolling


def _rolling_query(fakes: SimpleNamespace) -> tuple[str, object]:
    sentinel = fakes.DataFrame("job_cost_rolling_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_job_cluster_cost_rolling(
        spark,
        job_cluster_cost_daily_table="it.sch.gold_dbx_compute_job_cluster_cost_daily",
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0], result


def test_job_cluster_cost_rolling_reads_only_daily_table_no_curated(
    fakes: SimpleNamespace,
) -> None:
    # Rollup pur : lit UNIQUEMENT la table quotidienne gold, jamais une table
    # curated.
    query, _ = _rolling_query(fakes)
    assert "it.sch.gold_dbx_compute_job_cluster_cost_daily" in query
    assert "curated_" not in query


def test_job_cluster_cost_rolling_materializes_the_four_configured_windows(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "explode(array(1, 7, 30, 90)) AS window_days" in query


def test_job_cluster_cost_rolling_anchors_windows_on_max_period_start(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "MAX(period_start) AS as_of_date" in query
    assert "date_add(a.as_of_date, -(w.window_days - 1)) AS window_start" in query


def test_job_cluster_cost_rolling_sums_additive_metrics_over_window(
    fakes: SimpleNamespace,
) -> None:
    # cost/DBU additifs ; cluster_count aussi (clusters JOB ephemeres, ids non
    # reutilises d'un jour a l'autre -> somme des comptes distincts = distinct
    # sur la fenetre).
    query, _ = _rolling_query(fakes)
    assert "WHEN d.period_start > date_add(a.as_of_date, -w.window_days)" in query
    assert "THEN d.dbu_quantity ELSE 0" in query
    assert "THEN d.cost_usd ELSE 0" in query
    assert "THEN d.cluster_count ELSE 0" in query


def test_job_cluster_cost_rolling_computes_previous_equal_length_window(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "WHEN d.period_start <= date_add(a.as_of_date, -w.window_days)" in query
    assert "AS cost_usd_prev_window" in query
    assert "d.period_start > date_add(a.as_of_date, -2 * w.window_days)" in query
    assert (
        "(g.cost_usd - g.cost_usd_prev_window)\n"
        "            / NULLIF(g.cost_usd_prev_window, 0) * 100 AS cost_delta_pct" in query
    )


def test_job_cluster_cost_rolling_ranks_within_each_window_and_compute_kind(
    fakes: SimpleNamespace,
) -> None:
    # `(window_days, compute_kind)` et non `window_days` seule : une page filtree
    # sur une forme de compute doit y lire un rang qui commence a 1. Deux lignes
    # d'une meme fenetre peuvent donc porter le rang 1, une par forme -- c'est
    # voulu, et un classement toutes formes confondues demande d'agreger sur
    # `compute_kind` avant de reclasser.
    query, _ = _rolling_query(fakes)
    assert (
        "RANK() OVER (\n"
        "            PARTITION BY g.window_days, g.compute_kind ORDER BY g.cost_usd DESC\n"
        "        ) AS cost_rank" in query
    )
    assert (
        "RANK() OVER (PARTITION BY g.window_days, g.compute_kind ORDER BY g.cost_usd DESC)\n"
        "            <= 10 AS is_top_cost" in query
    )


def test_job_cluster_cost_rolling_keeps_compute_kind_in_the_grain(
    fakes: SimpleNamespace,
) -> None:
    # Repris du daily et agrege PAR forme : sans `compute_kind` dans le GROUP BY,
    # la fenetre re-melangerait ce que le grain quotidien vient de separer (926
    # jours-job mixtes mesures en dev).
    query, _ = _rolling_query(fakes)
    assert (
        "GROUP BY\n"
        "            d.cloud_provider,\n"
        "            d.workspace_id,\n"
        "            d.job_id,\n"
        "            d.compute_kind,\n"
        "            w.window_days,\n"
        "            a.as_of_date" in query
    )
    assert "        g.job_id,\n        g.compute_kind,\n" in query


def test_job_cluster_cost_rolling_keeps_latest_job_name(fakes: SimpleNamespace) -> None:
    query, _ = _rolling_query(fakes)
    assert (
        "QUALIFY ROW_NUMBER() OVER (\n"
        "            PARTITION BY cloud_provider, workspace_id, job_id\n"
        "            ORDER BY period_start DESC\n"
        "        ) = 1" in query
    )
    assert "la.job_name" in query
    # Partition VOLONTAIREMENT sans `compute_kind` : le nom d'un job ne depend pas
    # de la forme de compute, les deux lignes d'un job mixte portent le meme. La
    # jointure reste 1:1 dans les deux cas.
    assert (
        "            PARTITION BY cloud_provider, workspace_id, job_id, compute_kind" not in query
    )


def test_job_cluster_cost_rolling_drops_day_over_day_columns(fakes: SimpleNamespace) -> None:
    query, _ = _rolling_query(fakes)
    assert "cost_usd_prev_day" not in query


def test_job_cluster_cost_rolling_excludes_objects_inactive_in_both_windows(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "WHERE g.cost_usd <> 0 OR g.cost_usd_prev_window <> 0" in query


def test_job_cluster_cost_rolling_custom_windows_and_threshold(fakes: SimpleNamespace) -> None:
    sentinel = fakes.DataFrame("job_cost_rolling_result")
    spark = fakes.Spark(sql_result=sentinel)
    build_job_cluster_cost_rolling(
        spark,
        job_cluster_cost_daily_table="it.sch.gold_dbx_compute_job_cluster_cost_daily",
        rolling_windows=(1, 14),
        top_cost_rank_threshold=5,
    )
    query = spark.sql_calls[0]
    assert "explode(array(1, 14)) AS window_days" in query
    assert "<= 5 AS is_top_cost" in query
