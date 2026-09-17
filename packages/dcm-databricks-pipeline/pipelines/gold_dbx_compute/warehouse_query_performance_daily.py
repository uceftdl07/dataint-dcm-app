"""Agregation gold `gold_dbx_compute_warehouse_query_performance_daily`.

Performance quotidienne des requetes executees sur les SQL Warehouses
Databricks : volume et taux d'echec, latences (percentiles), temps
d'attente en file, requetes avec spill disque, taux de cache et volumes
scannes. Alimente le diagnostic de performance des warehouses (requetes
lentes, echecs, sous-dimensionnement memoire).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.sql_helpers import (
    HISTOGRAM_LATENCY_MS_EDGES,
    histogram_from_edges_sql,
    lower_bound_predicate,
    sql_string_list,
)

if TYPE_CHECKING:
    from datetime import date

    from pyspark.sql import DataFrame, SparkSession

# Statuts `system.query.history.execution_status` consideres comme un echec
# (hors succes/annulation volontaire non liee a une erreur).
FAILED_EXECUTION_STATUSES = ("FAILED", "CANCELED")


def build_warehouse_query_performance_daily(
    spark: SparkSession,
    *,
    query_history_table: str,
    warehouses_table: str,
    lower_bound: date | None,
) -> DataFrame:
    """Construit `gold_dbx_compute_warehouse_query_performance_daily`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        query_history_table: nom qualifie (`catalog.schema.table`) de
            `curated_dbx_query_history` (passthrough strict de
            `system.query.history`).
        warehouses_table: nom qualifie de `curated_dbx_compute_warehouses`
            (identite du warehouse au dernier etat connu, pour
            `warehouse_name`).
        lower_bound: borne basse incluse de `period_start` pour la lecture
            incrementale ; `None` pour recalculer l'historique complet.

    Returns:
        Le DataFrame `gold_dbx_compute_warehouse_query_performance_daily`
        resultant.

    Grain : `(cloud_provider, workspace_id, warehouse_id, period_start)`.
    Source : `curated_dbx_query_history` (metriques), filtre sur
    `compute.warehouse_id IS NOT NULL` (`compute` est un struct scalaire sur
    cette table -- acces direct par point, pas de `LATERAL VIEW explode`) +
    `curated_dbx_compute_warehouses` (identite du warehouse, sans effet sur les
    metriques). Pas de fenetre tampon (contrairement a `cost_daily`) : aucune
    comparaison a la veille sur cette table.

    Champs et formule de calcul :
      - `warehouse_name` : nom du warehouse, resolu au dernier etat connu du
        jour agrege (`change_time < period_start + 1 jour` : etat connu a un
        instant quelconque de `period_start`, pas seulement avant minuit - un
        cast `TIMESTAMP <= DATE` a minuit exclurait a tort les warehouses crees
        le jour meme, cas des ephemeres de bundle), meme CTE `warehouses_as_of` que
        `warehouse_cost_daily.build_warehouse_cost_daily`. `LEFT JOIN` : un
        warehouse absent de `curated_dbx_compute_warehouses` garde sa ligne
        avec `warehouse_name` a NULL -- la jointure enrichit, elle ne filtre
        pas, et aucune valeur de repli n'est fabriquee ici (le repli sur l'id
        est une decision d'affichage, cote IHM).
      - `query_count` : nombre de requetes executees sur ce warehouse ce
        jour-la. Formule : `COUNT(statement_id)`.
      - `failed_count` : nombre de requetes en echec ou annulees. Formule :
        `COUNT` des lignes dont `execution_status` est dans
        `FAILED_EXECUTION_STATUSES` (`FAILED`, `CANCELED`).
      - `failure_rate_pct` : taux d'echec du jour, en pourcentage. Formule :
        `failed_count / NULLIF(query_count, 0) * 100`.
      - `latency_p50_ms`/`latency_p95_ms`/`latency_p99_ms` : distribution de
        la duree totale des requetes. Formule : `percentile_approx
        (total_duration_ms, 0.50/0.95/0.99)`.
      - `queue_time_avg_ms`/`queue_time_p95_ms` : temps passe en file
        d'attente avant execution (signal de sous-dimensionnement du
        warehouse). Formule : `AVG`/`percentile_approx(0.95)` de
        `waiting_for_compute_duration_ms`.
      - `spill_query_count` : nombre de requetes ayant deborde sur disque
        (memoire insuffisante). Formule : `COUNT` des lignes ou
        `spilled_local_bytes > 0`.
      - `cache_hit_pct` : taux moyen de lecture depuis le cache disque.
        Formule : `AVG(read_io_cache_percent)`.
      - `bytes_scanned`/`rows_scanned` : volume de donnees lu par les
        requetes du jour. Formule : `SUM(read_bytes)`/`SUM(read_rows)`.
      - `top_slow_statement_id` : identifiant de la requete la plus lente du
        jour. Formule : `statement_id` associe au `MAX(total_duration_ms)`
        (`ROW_NUMBER() OVER (... ORDER BY total_duration_ms DESC) = 1`).
    """
    period_filter = lower_bound_predicate("to_date(start_time)", lower_bound)
    failed_statuses_sql = sql_string_list(FAILED_EXECUTION_STATUSES)
    latency_hist_sql = histogram_from_edges_sql(
        "total_duration_ms", HISTOGRAM_LATENCY_MS_EDGES
    )
    queue_time_hist_sql = histogram_from_edges_sql(
        "waiting_for_compute_duration_ms", HISTOGRAM_LATENCY_MS_EDGES
    )
    query = f"""
    WITH query_history_filtered AS (
        SELECT
            cloud_provider,
            workspace_id,
            compute.warehouse_id AS warehouse_id,
            to_date(start_time) AS period_start,
            statement_id,
            execution_status,
            total_duration_ms,
            waiting_for_compute_duration_ms,
            spilled_local_bytes,
            read_io_cache_percent,
            read_bytes,
            read_rows
        FROM {query_history_table}
        WHERE compute.warehouse_id IS NOT NULL
        {period_filter}
    ),
    aggregated AS (
        SELECT
            cloud_provider,
            workspace_id,
            warehouse_id,
            period_start,
            COUNT(statement_id) AS query_count,
            SUM(CASE WHEN execution_status IN ({failed_statuses_sql}) THEN 1 ELSE 0 END)
                AS failed_count,
            percentile_approx(total_duration_ms, 0.50) AS latency_p50_ms,
            percentile_approx(total_duration_ms, 0.95) AS latency_p95_ms,
            percentile_approx(total_duration_ms, 0.99) AS latency_p99_ms,
            AVG(waiting_for_compute_duration_ms) AS queue_time_avg_ms,
            percentile_approx(waiting_for_compute_duration_ms, 0.95) AS queue_time_p95_ms,
            {latency_hist_sql}
                AS latency_hist,
            {queue_time_hist_sql}
                AS queue_time_hist,
            SUM(CASE WHEN spilled_local_bytes > 0 THEN 1 ELSE 0 END) AS spill_query_count,
            AVG(read_io_cache_percent) AS cache_hit_pct,
            SUM(read_bytes) AS bytes_scanned,
            SUM(read_rows) AS rows_scanned
        FROM query_history_filtered
        GROUP BY cloud_provider, workspace_id, warehouse_id, period_start
    ),
    slowest AS (
        SELECT
            cloud_provider,
            workspace_id,
            warehouse_id,
            period_start,
            statement_id AS top_slow_statement_id
        FROM query_history_filtered
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY cloud_provider, workspace_id, warehouse_id, period_start
            ORDER BY total_duration_ms DESC
        ) = 1
    ),
    -- Identite du warehouse au dernier etat connu du jour agrege : copie de la
    -- CTE homonyme de `warehouse_cost_daily` (meme borne `change_time <
    -- period_start + INTERVAL 1 DAY`, meme `QUALIFY`), pour que les 4 tables
    -- warehouse resolvent `warehouse_name` a l'identique. NE PAS resserrer la
    -- borne en `<= period_start` : `period_start` est une DATE, donc minuit, et
    -- un warehouse cree dans la journee sortirait sans nom. Le `QUALIFY` est ce
    -- qui garantit UNE seule ligne par (warehouse, jour) : sans lui, chaque
    -- `change_time` anterieur dupliquerait la journee.
    warehouses_as_of AS (
        SELECT
            a.cloud_provider,
            a.workspace_id,
            a.warehouse_id,
            a.period_start,
            w.warehouse_name
        FROM aggregated a
        LEFT JOIN {warehouses_table} w
          ON w.cloud_provider = a.cloud_provider
         AND w.workspace_id = a.workspace_id
         AND w.warehouse_id = a.warehouse_id
         AND w.change_time < a.period_start + INTERVAL 1 DAY
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY a.cloud_provider, a.workspace_id, a.warehouse_id, a.period_start
            ORDER BY w.change_time DESC
        ) = 1
    )
    SELECT
        a.cloud_provider,
        a.workspace_id,
        a.warehouse_id,
        a.period_start,
        wa.warehouse_name,
        a.query_count,
        a.failed_count,
        a.failed_count / NULLIF(a.query_count, 0) * 100 AS failure_rate_pct,
        a.latency_p50_ms,
        a.latency_p95_ms,
        a.latency_p99_ms,
        a.queue_time_avg_ms,
        a.queue_time_p95_ms,
        a.latency_hist,
        a.queue_time_hist,
        a.spill_query_count,
        a.cache_hit_pct,
        a.bytes_scanned,
        a.rows_scanned,
        s.top_slow_statement_id,
        current_timestamp() AS _generated_at
    FROM aggregated a
    LEFT JOIN slowest s
      ON s.cloud_provider = a.cloud_provider
     AND s.workspace_id = a.workspace_id
     AND s.warehouse_id = a.warehouse_id
     AND s.period_start = a.period_start
    LEFT JOIN warehouses_as_of wa
      ON wa.cloud_provider = a.cloud_provider
     AND wa.workspace_id = a.workspace_id
     AND wa.warehouse_id = a.warehouse_id
     AND wa.period_start = a.period_start
    """
    return spark.sql(query)
