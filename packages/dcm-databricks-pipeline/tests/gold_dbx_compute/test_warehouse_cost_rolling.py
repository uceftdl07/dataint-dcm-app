"""Tests de `pipelines.gold_dbx_compute.warehouse_cost_rolling` (regles de derivation).

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`) :
`build_warehouse_cost_rolling` construit un unique `spark.sql(...)`, verifie ici
via le texte SQL genere (`FakeSpark`).
"""

from __future__ import annotations

from types import SimpleNamespace

from pipelines.gold_dbx_compute.warehouse_cost_rolling import build_warehouse_cost_rolling


def _rolling_query(fakes: SimpleNamespace) -> tuple[str, object]:
    sentinel = fakes.DataFrame("warehouse_cost_rolling_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_warehouse_cost_rolling(
        spark,
        warehouse_cost_daily_table="it.sch.gold_dbx_compute_warehouse_cost_daily",
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0], result


def test_warehouse_cost_rolling_reads_only_daily_table_no_curated(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "it.sch.gold_dbx_compute_warehouse_cost_daily" in query
    assert "curated_" not in query


def test_warehouse_cost_rolling_materializes_the_four_configured_windows(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "explode(array(1, 7, 30, 90)) AS window_days" in query


def test_warehouse_cost_rolling_anchors_windows_on_max_period_start(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "MAX(period_start) AS as_of_date" in query
    assert "date_add(a.as_of_date, -(w.window_days - 1)) AS window_start" in query


def test_warehouse_cost_rolling_sums_additive_metrics_over_window(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "WHEN d.period_start > date_add(a.as_of_date, -w.window_days)" in query
    assert "THEN d.dbu_quantity ELSE 0" in query
    assert "THEN d.cost_usd ELSE 0" in query
    assert "THEN d.query_count ELSE 0" in query


def test_warehouse_cost_rolling_recomputes_cost_per_query_over_window(
    fakes: SimpleNamespace,
) -> None:
    # cost_per_query_usd est une moyenne : recalculee a partir des sommes de la
    # fenetre (cout total / requetes totales), pas la moyenne des ratios
    # quotidiens.
    query, _ = _rolling_query(fakes)
    assert "g.cost_usd / NULLIF(g.query_count, 0) AS cost_per_query_usd" in query


def test_warehouse_cost_rolling_computes_previous_equal_length_window(
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


def test_warehouse_cost_rolling_keeps_latest_descriptive_attributes(
    fakes: SimpleNamespace,
) -> None:
    # Nom/taille/top_consumer resolus au dernier jour connu du warehouse. Le
    # top_consumer reflete donc le dernier jour, pas l'ensemble de la fenetre.
    query, _ = _rolling_query(fakes)
    assert (
        "QUALIFY ROW_NUMBER() OVER (\n"
        "            PARTITION BY cloud_provider, workspace_id, warehouse_id\n"
        "            ORDER BY period_start DESC\n"
        "        ) = 1" in query
    )
    for attr in ("warehouse_name", "warehouse_size", "top_consumer"):
        assert f"la.{attr}" in query


def test_warehouse_cost_rolling_has_no_cost_rank(fakes: SimpleNamespace) -> None:
    # Aligne sur la table quotidienne source : pas de cost_rank/is_top_cost pour
    # les warehouses (non demande, cf. WAREHOUSE_DAILY_MERGE_KEYS).
    query, _ = _rolling_query(fakes)
    assert "cost_rank" not in query
    assert "is_top_cost" not in query


def test_warehouse_cost_rolling_drops_day_over_day_columns(fakes: SimpleNamespace) -> None:
    query, _ = _rolling_query(fakes)
    assert "cost_usd_prev_day" not in query


def test_warehouse_cost_rolling_excludes_objects_inactive_in_both_windows(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "WHERE g.cost_usd <> 0 OR g.cost_usd_prev_window <> 0" in query


def test_warehouse_cost_rolling_custom_windows(fakes: SimpleNamespace) -> None:
    sentinel = fakes.DataFrame("warehouse_cost_rolling_result")
    spark = fakes.Spark(sql_result=sentinel)
    build_warehouse_cost_rolling(
        spark,
        warehouse_cost_daily_table="it.sch.gold_dbx_compute_warehouse_cost_daily",
        rolling_windows=(1, 14),
    )
    query = spark.sql_calls[0]
    assert "explode(array(1, 14)) AS window_days" in query
