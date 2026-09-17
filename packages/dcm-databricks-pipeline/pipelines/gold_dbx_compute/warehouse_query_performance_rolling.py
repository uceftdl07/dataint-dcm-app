"""Agregation gold `gold_dbx_compute_warehouse_query_performance_rolling` (fenetres).

Rollup 1/7/30/90 jours de `gold_dbx_compute_warehouse_query_performance_daily` :
pour chaque SQL Warehouse, volume, taux d'echec et latences des requetes
recalcules sur les derniers `window_days` jours "as of" le dernier jour
disponible.

Regles de derivation :
  - Percentiles (`latency_p50_ms`, `latency_p95_ms`, `latency_p99_ms`,
    `queue_time_p95_ms`) : recalcules a partir des histogrammes quotidiens
    (`latency_hist`/`queue_time_hist`) sommes bucket par bucket sur la fenetre,
    les percentiles quotidiens n'etant pas moyennables (cf.
    `sql_helpers.percentile_from_histogram_sql`). Les histogrammes fusionnes
    restent internes (CTE) et ne sont pas materialises en sortie (aucun
    consommateur aval, seuls les percentiles sont exposes).
  - Sommes additives : `query_count`, `failed_count`, `spill_query_count`,
    `bytes_scanned`, `rows_scanned`.
  - Ratios recalcules sur les sommes de la fenetre : `failure_rate_pct`.
  - Moyennes ponderees par le nombre de requetes : `queue_time_avg_ms`,
    `cache_hit_pct`.
  - `warehouse_name` : repris au dernier jour connu, comme
    `top_slow_statement_id`. Un warehouse renomme au milieu de la fenetre y porte
    donc son nom le PLUS RECENT, seul nom qui permette de le retrouver tel qu'il
    s'appelle aujourd'hui.
  - `top_slow_statement_id` : repris au dernier jour connu (la table quotidienne
    ne porte pas la duree associee, un max global sur la fenetre n'est donc pas
    calculable ; reflete la requete la plus lente du dernier jour).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.specs import ROLLING_WINDOWS
from pipelines.gold_dbx_compute.sql_helpers import (
    HISTOGRAM_LATENCY_MS_EDGES,
    histogram_bucket_count,
    percentile_from_histogram_sql,
    rolling_windows_array_sql,
    sum_histograms_sql,
)

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession


def build_warehouse_query_performance_rolling(
    spark: SparkSession,
    *,
    warehouse_query_performance_daily_table: str,
    rolling_windows: tuple[int, ...] = ROLLING_WINDOWS,
) -> DataFrame:
    """Construit `gold_dbx_compute_warehouse_query_performance_rolling`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        warehouse_query_performance_daily_table: nom qualifie
            (`catalog.schema.table`) de
            `gold_dbx_compute_warehouse_query_performance_daily` (unique source).
        rolling_windows: fenetres glissantes (jours) a materialiser, une ligne
            par warehouse ET par fenetre (defaut `ROLLING_WINDOWS`).

    Returns:
        Le DataFrame `gold_dbx_compute_warehouse_query_performance_rolling`
        resultant.

    Grain : `(cloud_provider, workspace_id, warehouse_id, window_days)`.
    Snapshot "as of" le dernier jour disponible (`as_of_date =
    MAX(period_start)`).
    """
    windows_array = rolling_windows_array_sql(rolling_windows)
    num_buckets = histogram_bucket_count(HISTOGRAM_LATENCY_MS_EDGES)
    p50 = percentile_from_histogram_sql("g.latency_hist", HISTOGRAM_LATENCY_MS_EDGES, 0.50)
    p95 = percentile_from_histogram_sql("g.latency_hist", HISTOGRAM_LATENCY_MS_EDGES, 0.95)
    p99 = percentile_from_histogram_sql("g.latency_hist", HISTOGRAM_LATENCY_MS_EDGES, 0.99)
    queue_p95 = percentile_from_histogram_sql(
        "g.queue_time_hist", HISTOGRAM_LATENCY_MS_EDGES, 0.95
    )
    query = f"""
    WITH daily AS (
        SELECT
            cloud_provider,
            workspace_id,
            warehouse_id,
            period_start,
            warehouse_name,
            query_count,
            failed_count,
            queue_time_avg_ms,
            latency_hist,
            queue_time_hist,
            spill_query_count,
            cache_hit_pct,
            bytes_scanned,
            rows_scanned,
            top_slow_statement_id
        FROM {warehouse_query_performance_daily_table}
    ),
    anchor AS (
        SELECT MAX(period_start) AS as_of_date FROM daily
    ),
    windows AS (
        SELECT explode({windows_array}) AS window_days
    ),
    latest_attrs AS (
        SELECT
            cloud_provider,
            workspace_id,
            warehouse_id,
            warehouse_name,
            top_slow_statement_id
        FROM daily
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY cloud_provider, workspace_id, warehouse_id
            ORDER BY period_start DESC
        ) = 1
    ),
    agg AS (
        SELECT
            d.cloud_provider,
            d.workspace_id,
            d.warehouse_id,
            w.window_days,
            a.as_of_date,
            date_add(a.as_of_date, -(w.window_days - 1)) AS window_start,
            SUM(d.query_count) AS query_count,
            SUM(d.failed_count) AS failed_count,
            SUM(d.spill_query_count) AS spill_query_count,
            SUM(d.bytes_scanned) AS bytes_scanned,
            SUM(d.rows_scanned) AS rows_scanned,
            SUM(d.queue_time_avg_ms * d.query_count)
                / NULLIF(SUM(CASE WHEN d.queue_time_avg_ms IS NOT NULL
                                  THEN d.query_count END), 0) AS queue_time_avg_ms,
            SUM(d.cache_hit_pct * d.query_count)
                / NULLIF(SUM(CASE WHEN d.cache_hit_pct IS NOT NULL
                                  THEN d.query_count END), 0) AS cache_hit_pct,
            {sum_histograms_sql("d.latency_hist", num_buckets)} AS latency_hist,
            {sum_histograms_sql("d.queue_time_hist", num_buckets)} AS queue_time_hist
        FROM daily d
        CROSS JOIN anchor a
        CROSS JOIN windows w
        WHERE d.period_start > date_add(a.as_of_date, -w.window_days)
          AND d.period_start <= a.as_of_date
        GROUP BY d.cloud_provider, d.workspace_id, d.warehouse_id, w.window_days, a.as_of_date
    ),
    with_metrics AS (
        SELECT
            g.*,
            g.failed_count / NULLIF(g.query_count, 0) * 100 AS failure_rate_pct,
            {p50} AS latency_p50_ms,
            {p95} AS latency_p95_ms,
            {p99} AS latency_p99_ms,
            {queue_p95} AS queue_time_p95_ms
        FROM agg g
    )
    SELECT
        m.cloud_provider,
        m.workspace_id,
        m.warehouse_id,
        m.window_days,
        m.as_of_date,
        m.window_start,
        la.warehouse_name,
        m.query_count,
        m.failed_count,
        m.failure_rate_pct,
        m.latency_p50_ms,
        m.latency_p95_ms,
        m.latency_p99_ms,
        m.queue_time_avg_ms,
        m.queue_time_p95_ms,
        m.spill_query_count,
        m.cache_hit_pct,
        m.bytes_scanned,
        m.rows_scanned,
        la.top_slow_statement_id,
        current_timestamp() AS _generated_at
    FROM with_metrics m
    LEFT JOIN latest_attrs la
      ON la.cloud_provider = m.cloud_provider
     AND la.workspace_id = m.workspace_id
     AND la.warehouse_id = m.warehouse_id
    WHERE m.query_count > 0
    """
    return spark.sql(query)
