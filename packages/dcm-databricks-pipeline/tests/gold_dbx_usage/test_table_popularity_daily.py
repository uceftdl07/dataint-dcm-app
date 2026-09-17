"""Tests de `pipelines.gold_dbx_usage.table_popularity_daily`."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from pipelines.gold_dbx_usage.table_popularity_daily import build_table_popularity_daily
from tests.conftest import strip_sql_comments


def _popularity_query(fakes: SimpleNamespace, lower_bound: date | None) -> str:
    sentinel = fakes.DataFrame("table_popularity_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_table_popularity_daily(
        spark,
        table_daily_table="it.sch.gold_dbx_usage_table_daily",
        lineage_table="it.sch.curated_dbx_access_table_lineage",
        uc_table_tags_table="it.sch.curated_dbx_uc_table_tags",
        lower_bound=lower_bound,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0]


def test_popularity_full_run_has_no_lower_bound_filter(fakes: SimpleNamespace) -> None:
    query = _popularity_query(fakes, lower_bound=None)
    assert "period_start >= DATE" not in query
    assert "event_date >= DATE" not in query


def test_popularity_incremental_run_uses_one_day_buffer(fakes: SimpleNamespace) -> None:
    query = _popularity_query(fakes, lower_bound=date(2026, 8, 14))
    # Tampon J-1 pour le self-join request_count_prev_day.
    assert "AND period_start >= DATE '2026-08-13'" in query
    assert "AND event_date >= DATE '2026-08-13'" in query
    assert "AND period_start >= DATE '2026-08-14'" in query


def test_popularity_rank_is_partitioned_per_cloud_provider(fakes: SimpleNamespace) -> None:
    """`cloud_provider` fait partie du grain, donc de la partition : sans lui, les
    tables aws et azure se classent dans un meme palmares -- un seul rang 1 par jour
    pour les deux clouds, et le rang d'une table qui varie selon l'activite de
    l'autre cloud."""
    query = _popularity_query(fakes, lower_bound=None)
    assert "PARTITION BY cloud_provider, period_start ORDER BY request_count DESC" in query


def test_popularity_prev_day_uses_exact_self_join_not_lag(fakes: SimpleNamespace) -> None:
    query = _popularity_query(fakes, lower_bound=None)
    assert "prev.period_start = e.period_start - INTERVAL 1 DAY" in query
    assert "LAG(" not in query


def test_popularity_downstream_fanout_counts_downstream_objects_not_readers(
    fakes: SimpleNamespace,
) -> None:
    """`COUNT(DISTINCT entity_id)` compte l'entite qui LIT (job, notebook, requete) :
    des lecteurs, pas un fan-out aval, qui se lit du cote CIBLE.

    Les deux definitions divergent sur la majorite des groupes, et cette colonne
    alimente `severity`/`recommended_action` de `table_governance`, dont `'archiver'`.
    """
    query = strip_sql_comments(_popularity_query(fakes, lower_bound=None))
    assert "COUNT(DISTINCT entity_id)" not in query
    assert "COUNT(DISTINCT target_table_full_name) AS downstream_fanout" in query
    # `0` est une mesure (table lue sans rien produire en aval), pas une absence.
    assert "COALESCE(f.downstream_fanout, 0) AS downstream_fanout" in query


def test_popularity_fanout_grain_reads_native_lineage_columns(
    fakes: SimpleNamespace,
) -> None:
    """Idem `table_daily`/`table_query_performance_daily` : les 3 parties du nom
    viennent des colonnes natives du lineage, pas d'un `split()`. Le GROUP BY porte
    sur les colonnes sources et non sur les alias du SELECT."""
    query = strip_sql_comments(_popularity_query(fakes, lower_bound=None))
    assert "split(source_table_full_name" not in query
    assert "source_table_catalog AS catalog" in query
    assert (
        "GROUP BY\n"
        "            cloud_provider, to_date(event_time),\n"
        "            source_table_catalog, source_table_schema, source_table_name"
    ) in query


def test_popularity_fanout_source_type_covers_every_named_uc_object(
    fakes: SimpleNamespace,
) -> None:
    """Lire une vue est une lecture : `source_type = 'TABLE'` seul l'ignore, et le
    fan-out aval d'une vue serait alors toujours absent."""
    query = strip_sql_comments(_popularity_query(fakes, lower_bound=None))
    assert "source_type = 'TABLE'" not in query
    for object_type in ("'TABLE'", "'VIEW'", "'MATERIALIZED_VIEW'", "'STREAMING_TABLE'"):
        assert object_type in query
