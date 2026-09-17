"""Tests de `pipelines.gold_dbx_compute.warehouse_cost_daily` (regles de derivation).

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`) :
`build_warehouse_cost_daily` construit un unique `spark.sql(...)`, verifie ici
via le texte SQL genere (`FakeSpark`).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from pipelines.gold_dbx_compute.warehouse_cost_daily import build_warehouse_cost_daily


def _cost_daily_query(fakes: SimpleNamespace, lower_bound: date | None) -> tuple[str, object]:
    sentinel = fakes.DataFrame("warehouse_cost_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_warehouse_cost_daily(
        spark,
        billing_usage_table="it.sch.curated_dbx_billing_usage",
        billing_list_prices_table="it.sch.curated_dbx_billing_list_prices",
        warehouses_table="it.sch.curated_dbx_compute_warehouses",
        query_history_table="it.sch.curated_dbx_query_history",
        lower_bound=lower_bound,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0], result


def test_warehouse_cost_daily_full_run_has_no_lower_bound_filter(fakes: SimpleNamespace) -> None:
    query, _ = _cost_daily_query(fakes, lower_bound=None)
    assert "usage_date >= DATE" not in query
    assert "to_date(start_time) >= DATE" not in query
    assert "period_start >= DATE" not in query


def test_warehouse_cost_daily_incremental_run_filters_usage_date_window(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _cost_daily_query(fakes, lower_bound=date(2026, 8, 14))
    # Lecture curated avec 1 jour tampon (J-1) pour que le self-join de
    # cost_usd_prev_day voie J-1 au bord de la fenetre incrementale.
    assert "AND usage_date >= DATE '2026-08-13'" in query
    # query_history n'est jamais compare a la veille : pas de tampon.
    assert "AND to_date(start_time) >= DATE '2026-08-14'" in query
    # Mais la sortie (et donc le MERGE) reste bornee a lower_bound, le jour
    # tampon n'est jamais reecrit.
    assert "AND period_start >= DATE '2026-08-14'" in query


def test_warehouse_cost_daily_filters_on_warehouse_usage_and_compute(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _cost_daily_query(fakes, lower_bound=None)
    assert "usage_metadata.warehouse_id IS NOT NULL" in query
    assert "compute.warehouse_id IS NOT NULL" in query
    assert "compute.warehouse_id AS warehouse_id" in query


def test_warehouse_cost_daily_computes_delta_and_cost_per_query(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _cost_daily_query(fakes, lower_bound=None)
    # Self-join exact sur le jour calendaire precedent, pas un LAG.
    assert "prev.period_start = e.period_start - INTERVAL 1 DAY" in query
    assert "prev.cost_usd AS cost_usd_prev_day" in query
    assert "NULLIF(cost_usd_prev_day, 0) * 100 AS cost_delta_pct" in query
    assert "cost_usd / NULLIF(query_count, 0) AS cost_per_query_usd" in query


def test_warehouse_cost_daily_derives_top_consumer_from_longest_duration_user(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _cost_daily_query(fakes, lower_bound=None)
    assert "SUM(total_duration_ms) AS total_duration_ms" in query
    assert "ORDER BY total_duration_ms DESC\n        ) = 1" in query
    assert "executed_by AS top_consumer" in query


def test_warehouse_cost_daily_names_warehouse_created_within_the_aggregated_day(
    fakes: SimpleNamespace,
) -> None:
    """Un warehouse dont l'unique `change_time` tombe DANS le jour J est nomme sur J.

    `period_start` est une DATE : `change_time <= period_start` la caste a
    minuit et n'admet donc aucune version d'un warehouse cree en cours de
    journee, qui sortait sans nom. La borne fin de journee (`< period_start +
    INTERVAL 1 DAY`) est celle de la famille cluster/job -- une seule
    convention dans le depot. Ne pas "resserrer" ce predicat par mimetisme sur
    l'ancienne version : le defaut reviendrait sur tous les warehouses
    ephemeres (crees et utilises le meme jour, jamais retouches).
    """
    query, _ = _cost_daily_query(fakes, lower_bound=None)
    assert "w.change_time < p.period_start + INTERVAL 1 DAY" in query
    assert "w.change_time <= p.period_start" not in query
    # Le tri du QUALIFY est inchange : c'est lui qui retient la version la plus
    # recente de la journee, donc l'etat de FIN de journee.
    assert "ORDER BY w.change_time DESC" in query


def test_warehouse_cost_daily_no_cost_rank_or_landing_zone_join(
    fakes: SimpleNamespace,
) -> None:
    # Pas de cost_rank/is_top_cost (non demande) ni de jointure dim_landing_zone
    # sur cette table (cf. data-model.md "Couche GOLD -- SQL Warehouses").
    query, _ = _cost_daily_query(fakes, lower_bound=None)
    assert "cost_rank" not in query
    assert "is_top_cost" not in query
    assert "dim_landing_zone" not in query
