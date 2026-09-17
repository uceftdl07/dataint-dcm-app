"""Tests de `pipelines.gold_dbx_compute.warehouse_query_performance_daily`.

Pas de vraie `SparkSession` : `build_warehouse_query_performance_daily`
construit un unique `spark.sql(...)`, verifie ici via le texte SQL genere
(`FakeSpark`).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from pipelines.gold_dbx_compute.warehouse_query_performance_daily import (
    build_warehouse_query_performance_daily,
)

_WAREHOUSES = "it.sch.curated_dbx_compute_warehouses"


def _query_perf_query(fakes: SimpleNamespace, lower_bound: date | None) -> tuple[str, object]:
    sentinel = fakes.DataFrame("warehouse_query_performance_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_warehouse_query_performance_daily(
        spark,
        query_history_table="it.sch.curated_dbx_query_history",
        warehouses_table=_WAREHOUSES,
        lower_bound=lower_bound,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0], result


def test_query_performance_daily_full_run_has_no_lower_bound_filter(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _query_perf_query(fakes, lower_bound=None)
    assert "to_date(start_time) >= DATE" not in query


def test_query_performance_daily_incremental_run_filters_start_time_window(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _query_perf_query(fakes, lower_bound=date(2026, 8, 14))
    assert "AND to_date(start_time) >= DATE '2026-08-14'" in query


def test_query_performance_daily_filters_on_scalar_compute_struct(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _query_perf_query(fakes, lower_bound=None)
    # `compute` est un struct scalaire sur cette table : acces direct par
    # point, jamais de LATERAL VIEW explode.
    assert "compute.warehouse_id IS NOT NULL" in query
    assert "LATERAL VIEW" not in query


def test_query_performance_daily_computes_failure_rate(fakes: SimpleNamespace) -> None:
    query, _ = _query_perf_query(fakes, lower_bound=None)
    assert "execution_status IN ('FAILED', 'CANCELED')" in query
    assert "a.failed_count / NULLIF(a.query_count, 0) * 100 AS failure_rate_pct" in query


def test_query_performance_daily_computes_latency_percentiles(fakes: SimpleNamespace) -> None:
    query, _ = _query_perf_query(fakes, lower_bound=None)
    assert "percentile_approx(total_duration_ms, 0.50) AS latency_p50_ms" in query
    assert "percentile_approx(total_duration_ms, 0.95) AS latency_p95_ms" in query
    assert "percentile_approx(total_duration_ms, 0.99) AS latency_p99_ms" in query


def test_query_performance_daily_computes_queue_time_and_spill_and_cache(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _query_perf_query(fakes, lower_bound=None)
    assert "AVG(waiting_for_compute_duration_ms) AS queue_time_avg_ms" in query
    assert (
        "percentile_approx(waiting_for_compute_duration_ms, 0.95) AS queue_time_p95_ms" in query
    )
    assert "SUM(CASE WHEN spilled_local_bytes > 0 THEN 1 ELSE 0 END) AS spill_query_count" in query
    assert "AVG(read_io_cache_percent) AS cache_hit_pct" in query


def test_query_performance_daily_derives_top_slow_statement(fakes: SimpleNamespace) -> None:
    query, _ = _query_perf_query(fakes, lower_bound=None)
    assert "statement_id AS top_slow_statement_id" in query
    assert "ORDER BY total_duration_ms DESC" in query


def test_query_performance_daily_resolves_warehouse_name_as_of_period_start(
    fakes: SimpleNamespace,
) -> None:
    """`warehouse_name` = etat curated le plus recent du jour agrege (fin de journee).

    Cette table ne lisait que `curated_dbx_query_history` : la CTE
    `warehouses_as_of` est copiee sur celle de `warehouse_cost_daily` (meme
    predicat de borne, meme `QUALIFY`), pour que les 4 familles de tables
    warehouse resolvent le nom exactement de la meme facon.
    """
    query, _ = _query_perf_query(fakes, lower_bound=None)
    assert f"LEFT JOIN {_WAREHOUSES} w" in query
    assert "AND w.change_time < a.period_start + INTERVAL 1 DAY" in query
    assert "PARTITION BY a.cloud_provider, a.workspace_id, a.warehouse_id, a.period_start" in query
    assert "ORDER BY w.change_time DESC" in query
    assert "            w.warehouse_name\n" in query
    assert "        wa.warehouse_name,\n" in query


def test_query_performance_daily_names_warehouse_created_within_the_aggregated_day(
    fakes: SimpleNamespace,
) -> None:
    """Un warehouse dont l'unique `change_time` tombe DANS le jour J est nomme sur J.

    `period_start` est une DATE : `change_time <= period_start` la caste a
    minuit et n'admet donc aucune version d'un warehouse cree en cours de
    journee, qui sortait sans nom -- et, ce nom NULL etant repris par
    `latest_attrs`, se propageait aux 4 fenetres de `*_rolling` (SC-001 mesure
    a 90,3 % en w90 avant correction). Ne pas "resserrer" ce predicat par
    mimetisme sur l'ancienne version.
    """
    query, _ = _query_perf_query(fakes, lower_bound=None)
    assert "w.change_time < a.period_start + INTERVAL 1 DAY" in query
    assert "w.change_time <= a.period_start" not in query
    # Le tri du QUALIFY est inchange : c'est lui qui retient la version la plus
    # recente de la journee, donc l'etat de FIN de journee.
    assert "ORDER BY w.change_time DESC" in query


def test_query_performance_daily_warehouse_join_enriches_without_filtering(
    fakes: SimpleNamespace,
) -> None:
    """La jointure curated enrichit, elle ne filtre ni ne duplique.

    `LEFT JOIN` uniquement : un warehouse absent de
    `curated_dbx_compute_warehouses` garde sa ligne avec `warehouse_name` NULL
    (P9, aucune valeur de repli fabriquee en gold). Le `QUALIFY` ne garde qu'un
    seul etat curated par (warehouse, jour) : plusieurs `change_time` anterieurs
    ne peuvent pas dupliquer la ligne du jour.
    """
    query, _ = _query_perf_query(fakes, lower_bound=None)
    # Une seule lecture du curated, et elle est en LEFT JOIN.
    assert query.count(_WAREHOUSES) == 1
    assert f"JOIN {_WAREHOUSES}" not in query.replace(f"LEFT JOIN {_WAREHOUSES}", "")
    assert "LEFT JOIN warehouses_as_of wa" in query
    assert "INNER JOIN" not in query
