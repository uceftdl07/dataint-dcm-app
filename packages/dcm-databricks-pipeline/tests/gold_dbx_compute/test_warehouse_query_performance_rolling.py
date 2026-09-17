"""Tests de `pipelines.gold_dbx_compute.warehouse_query_performance_rolling`.

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`) :
`build_warehouse_query_performance_rolling` construit un unique `spark.sql(...)`,
verifie ici via le texte SQL genere (`FakeSpark`).
"""

from __future__ import annotations

from types import SimpleNamespace

from pipelines.gold_dbx_compute.warehouse_query_performance_rolling import (
    build_warehouse_query_performance_rolling,
)

_DAILY = "it.sch.gold_dbx_compute_warehouse_query_performance_daily"


def _rolling_query(fakes: SimpleNamespace) -> tuple[str, object]:
    sentinel = fakes.DataFrame("warehouse_query_performance_rolling_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_warehouse_query_performance_rolling(
        spark,
        warehouse_query_performance_daily_table=_DAILY,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0], result


def test_qp_rolling_reads_only_daily_table_no_curated(fakes: SimpleNamespace) -> None:
    query, _ = _rolling_query(fakes)
    assert _DAILY in query
    assert "curated_" not in query


def test_qp_rolling_materializes_the_four_configured_windows(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "explode(array(1, 7, 30, 90)) AS window_days" in query


def test_qp_rolling_anchors_windows_on_max_period_start(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "MAX(period_start) AS as_of_date" in query
    assert "date_add(a.as_of_date, -(w.window_days - 1)) AS window_start" in query


def test_qp_rolling_uses_current_window_only(fakes: SimpleNamespace) -> None:
    query, _ = _rolling_query(fakes)
    assert "d.period_start > date_add(a.as_of_date, -w.window_days)" in query
    assert "d.period_start <= a.as_of_date" in query
    assert "prev_window" not in query


def test_qp_rolling_sums_additive_metrics(fakes: SimpleNamespace) -> None:
    query, _ = _rolling_query(fakes)
    assert "SUM(d.query_count) AS query_count" in query
    assert "SUM(d.failed_count) AS failed_count" in query
    assert "SUM(d.spill_query_count) AS spill_query_count" in query
    assert "SUM(d.bytes_scanned) AS bytes_scanned" in query
    assert "SUM(d.rows_scanned) AS rows_scanned" in query


def test_qp_rolling_weights_averages_by_query_count(fakes: SimpleNamespace) -> None:
    query, _ = _rolling_query(fakes)
    assert "SUM(d.queue_time_avg_ms * d.query_count)" in query
    assert "SUM(d.cache_hit_pct * d.query_count)" in query
    assert "SUM(CASE WHEN d.queue_time_avg_ms IS NOT NULL" in query


def test_qp_rolling_merges_histograms_bucketwise(fakes: SimpleNamespace) -> None:
    query, _ = _rolling_query(fakes)
    assert "transform(sequence(0," in query
    assert "collect_list(d.latency_hist)" in query
    assert "collect_list(d.queue_time_hist)" in query
    assert "AS latency_hist" in query
    assert "AS queue_time_hist" in query


def test_qp_rolling_recomputes_percentiles_from_histograms(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "g.latency_hist" in query
    assert "g.queue_time_hist" in query
    assert "AS latency_p50_ms" in query
    assert "AS latency_p95_ms" in query
    assert "AS latency_p99_ms" in query
    assert "AS queue_time_p95_ms" in query
    assert "THEN NULL" in query


def test_qp_rolling_recomputes_failure_rate_over_window(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "g.failed_count / NULLIF(g.query_count, 0) * 100 AS failure_rate_pct" in query


def test_qp_rolling_keeps_latest_top_slow_statement(fakes: SimpleNamespace) -> None:
    query, _ = _rolling_query(fakes)
    assert (
        "QUALIFY ROW_NUMBER() OVER (\n"
        "            PARTITION BY cloud_provider, workspace_id, warehouse_id\n"
        "            ORDER BY period_start DESC\n"
        "        ) = 1" in query
    )
    assert "la.top_slow_statement_id" in query


def test_qp_rolling_keeps_latest_warehouse_name(fakes: SimpleNamespace) -> None:
    """`warehouse_name` repris au dernier jour connu, comme `top_slow_statement_id`.

    Un warehouse renomme au milieu de la fenetre y apparait sous son nom le PLUS
    RECENT (`latest_attrs`, `ORDER BY period_start DESC`). Aucune relecture
    curated : le nom arrive par la table quotidienne (rollup pur).
    """
    query, _ = _rolling_query(fakes)
    # Lu dans la CTE `daily` puis repris dans `latest_attrs` : 2 occurrences a
    # la maille des colonnes de CTE (indentation 12).
    assert query.count("            warehouse_name,\n") == 2
    assert "la.warehouse_name" in query


def test_qp_rolling_excludes_warehouses_with_no_queries(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "WHERE m.query_count > 0" in query


def test_qp_rolling_custom_windows(fakes: SimpleNamespace) -> None:
    sentinel = fakes.DataFrame("warehouse_query_performance_rolling_result")
    spark = fakes.Spark(sql_result=sentinel)
    build_warehouse_query_performance_rolling(
        spark,
        warehouse_query_performance_daily_table=_DAILY,
        rolling_windows=(1, 14),
    )
    query = spark.sql_calls[0]
    assert "explode(array(1, 14)) AS window_days" in query
