"""Agregation gold `gold_dbx_compute_warehouse_cost_rolling` (FinOps warehouses, fenetres).

Rollup 1/7/30/90 jours de `gold_dbx_compute_warehouse_cost_daily` : pour chaque
SQL Warehouse, cout/DBU/nombre de requetes cumules sur les derniers
`window_days` jours "as of" le dernier jour disponible, cout moyen par requete
recalcule sur la fenetre et variation vs la fenetre precedente de meme longueur.

Metriques additives (cout, DBU, query_count) sommees sur la fenetre ;
`cost_per_query_usd` recalcule a partir des sommes ; identite/taille du warehouse
et `top_consumer` repris au dernier jour connu. Comme la table quotidienne, pas
de `cost_rank` (non demande pour les warehouses). Les colonnes jour-a-jour
(`cost_usd_prev_day`) sont abandonnees (sans objet a la maille fenetre).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.specs import ROLLING_WINDOWS
from pipelines.gold_dbx_compute.sql_helpers import rolling_windows_array_sql

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession


def build_warehouse_cost_rolling(
    spark: SparkSession,
    *,
    warehouse_cost_daily_table: str,
    rolling_windows: tuple[int, ...] = ROLLING_WINDOWS,
) -> DataFrame:
    """Construit `gold_dbx_compute_warehouse_cost_rolling`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        warehouse_cost_daily_table: nom qualifie (`catalog.schema.table`) de
            `gold_dbx_compute_warehouse_cost_daily` (unique source).
        rolling_windows: fenetres glissantes (jours) a materialiser, une ligne
            par warehouse ET par fenetre (defaut `ROLLING_WINDOWS`).

    Returns:
        Le DataFrame `gold_dbx_compute_warehouse_cost_rolling` resultant.

    Grain : `(cloud_provider, workspace_id, warehouse_id, window_days)`. Snapshot
    "as of" le dernier jour disponible (`as_of_date = MAX(period_start)`).

    Champs : `dbu_quantity`/`cost_usd`/`query_count` sommes sur la fenetre
    `(as_of_date - window_days, as_of_date]` ; `cost_per_query_usd` = cost_usd /
    query_count recalcule sur la fenetre ; `cost_usd_prev_window` sur la fenetre
    precedente de meme longueur ; `cost_delta_pct` = variation ;
    `warehouse_name`/`warehouse_size`/`top_consumer` au dernier jour connu (le
    top consommateur reflete donc le dernier jour, pas l'ensemble de la fenetre).
    Un warehouse sans cout ni sur la fenetre courante ni sur la precedente est
    exclu.
    """
    windows_array = rolling_windows_array_sql(rolling_windows)
    query = f"""
    WITH daily AS (
        SELECT
            cloud_provider,
            workspace_id,
            warehouse_id,
            period_start,
            warehouse_name,
            warehouse_size,
            top_consumer,
            dbu_quantity,
            cost_usd,
            query_count
        FROM {warehouse_cost_daily_table}
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
            warehouse_size,
            top_consumer
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
            SUM(CASE
                    WHEN d.period_start > date_add(a.as_of_date, -w.window_days)
                    THEN d.dbu_quantity ELSE 0
                END) AS dbu_quantity,
            SUM(CASE
                    WHEN d.period_start > date_add(a.as_of_date, -w.window_days)
                    THEN d.cost_usd ELSE 0
                END) AS cost_usd,
            SUM(CASE
                    WHEN d.period_start > date_add(a.as_of_date, -w.window_days)
                    THEN d.query_count ELSE 0
                END) AS query_count,
            SUM(CASE
                    WHEN d.period_start <= date_add(a.as_of_date, -w.window_days)
                    THEN d.cost_usd ELSE 0
                END) AS cost_usd_prev_window
        FROM daily d
        CROSS JOIN anchor a
        CROSS JOIN windows w
        WHERE d.period_start > date_add(a.as_of_date, -2 * w.window_days)
          AND d.period_start <= a.as_of_date
        GROUP BY d.cloud_provider, d.workspace_id, d.warehouse_id, w.window_days, a.as_of_date
    )
    SELECT
        g.cloud_provider,
        g.workspace_id,
        g.warehouse_id,
        g.window_days,
        g.as_of_date,
        g.window_start,
        la.warehouse_name,
        la.warehouse_size,
        g.dbu_quantity,
        g.cost_usd,
        g.query_count,
        g.cost_usd / NULLIF(g.query_count, 0) AS cost_per_query_usd,
        la.top_consumer,
        g.cost_usd_prev_window,
        (g.cost_usd - g.cost_usd_prev_window)
            / NULLIF(g.cost_usd_prev_window, 0) * 100 AS cost_delta_pct,
        current_timestamp() AS _generated_at
    FROM agg g
    LEFT JOIN latest_attrs la
      ON la.cloud_provider = g.cloud_provider
     AND la.workspace_id = g.workspace_id
     AND la.warehouse_id = g.warehouse_id
    WHERE g.cost_usd <> 0 OR g.cost_usd_prev_window <> 0
    """
    return spark.sql(query)
