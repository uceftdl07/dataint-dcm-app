"""Tests de `pipelines.gold_dbx_usage.consumer_daily`."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from pipelines.gold_dbx_usage.consumer_daily import build_consumer_daily


def _consumer_query(fakes: SimpleNamespace, lower_bound: date | None) -> str:
    sentinel = fakes.DataFrame("consumer_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_consumer_daily(
        spark,
        table_daily_table="it.sch.gold_dbx_usage_table_daily",
        lower_bound=lower_bound,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0]


def test_consumer_daily_full_run_has_no_lower_bound_filter(fakes: SimpleNamespace) -> None:
    query = _consumer_query(fakes, lower_bound=None)
    assert "period_start >= DATE" not in query


def test_consumer_daily_incremental_run_filters_period_start(fakes: SimpleNamespace) -> None:
    query = _consumer_query(fakes, lower_bound=date(2026, 8, 14))
    assert "AND period_start >= DATE '2026-08-14'" in query


def test_consumer_daily_distinct_data_products_counts_full_table_name(
    fakes: SimpleNamespace,
) -> None:
    """Corrige F013 : `table_full_name` (jamais NULL) au lieu du tuple eclate.

    `COUNT(DISTINCT catalog, schema, table_name)` ecarterait toute ligne a
    composante NULL -- cf. `pipelines.gold_dbx_usage.table_daily` docstring.
    """
    query = _consumer_query(fakes, lower_bound=None)
    assert "COUNT(DISTINCT table_full_name) AS distinct_data_products" in query


def test_consumer_daily_consumer_type_uses_priority_ranked_max(
    fakes: SimpleNamespace,
) -> None:
    """Corrige F003 : `MAX()` sur l'encodage priorise, pas `MAX(consumer_type)` brut."""
    query = _consumer_query(fakes, lower_bound=None)
    assert "MAX(consumer_type)" not in query
    assert "MAX(CONCAT(CASE consumer_type" in query


def test_consumer_daily_rank_by_cost_partitioned_by_period_start(
    fakes: SimpleNamespace,
) -> None:
    query = _consumer_query(fakes, lower_bound=None)
    assert "RANK() OVER (PARTITION BY period_start ORDER BY SUM(estimated_cost_usd) DESC)" in query
    assert "AS consumer_rank" in query


def test_consumer_daily_groups_by_grain_columns(fakes: SimpleNamespace) -> None:
    query = _consumer_query(fakes, lower_bound=None)
    assert "GROUP BY cloud_provider, consumer_id, period_start" in query
