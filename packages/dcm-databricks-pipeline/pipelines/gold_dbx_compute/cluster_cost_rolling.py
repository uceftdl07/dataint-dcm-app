"""Agregation gold `gold_dbx_compute_cluster_cost_rolling` (FinOps, fenetres glissantes).

Rollup 1/7/30/90 jours de `gold_dbx_compute_cluster_cost_daily` : pour chaque
cluster, cout et DBU cumules sur les derniers `window_days` jours "as of" le
dernier jour disponible, variation vs la fenetre precedente de meme longueur et
classement par cout. Alimente les vues FinOps "derniers 7/30/90 jours" sans
relire la couche curated (seule la table quotidienne gold est lue).

Metriques 100 % additives (cout, DBU) : la somme sur une fenetre se deduit
exactement des valeurs quotidiennes, aucun composant supplementaire n'est requis
cote table `*_daily` (contrairement aux moyennes/ratios/percentiles des autres
tables `*_rolling`). Les colonnes jour-a-jour (`cost_usd_prev_day`) sont
abandonnees : elles n'ont pas de sens a la maille fenetre.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.specs import ROLLING_WINDOWS, TOP_COST_RANK_THRESHOLD
from pipelines.gold_dbx_compute.sql_helpers import (
    CLUSTER_TYPE_ALL_PURPOSE,
    rolling_windows_array_sql,
)

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession


def build_cluster_cost_rolling(
    spark: SparkSession,
    *,
    cluster_cost_daily_table: str,
    rolling_windows: tuple[int, ...] = ROLLING_WINDOWS,
    top_cost_rank_threshold: int = TOP_COST_RANK_THRESHOLD,
) -> DataFrame:
    """Construit `gold_dbx_compute_cluster_cost_rolling`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        cluster_cost_daily_table: nom qualifie (`catalog.schema.table`) de
            `gold_dbx_compute_cluster_cost_daily` (unique source ; aucune
            relecture curated).
        rolling_windows: fenetres glissantes (jours) a materialiser, une ligne
            par cluster ET par fenetre (defaut `ROLLING_WINDOWS`).
        top_cost_rank_threshold: nombre de clusters consideres "top cost" par
            fenetre (defaut `TOP_COST_RANK_THRESHOLD`), utilise pour
            `is_top_cost`.

    Returns:
        Le DataFrame `gold_dbx_compute_cluster_cost_rolling` resultant.

    Grain : `(cloud_provider, workspace_id, cluster_id, window_days)`. Snapshot
    "as of" le dernier jour disponible (`as_of_date = MAX(period_start)`) : toutes
    les fenetres sont ancrees sur ce meme jour, si bien que le classement
    `cost_rank` compare les clusters sur des periodes de meme borne haute.

    Champs et formule de calcul :
      - `as_of_date` : `MAX(period_start)` de la table quotidienne (borne haute
        incluse, commune a toutes les fenetres).
      - `window_start` : `as_of_date - (window_days - 1)` (premier jour inclus).
      - `cluster_name`/`cluster_type`/`owner`/`cost_center`/`sku_group` :
        dernier etat connu du cluster (ligne quotidienne de `period_start` la
        plus recente, tous jours confondus <= `as_of_date`).
      - `dbu_quantity`/`cost_usd` : somme des valeurs quotidiennes sur la
        fenetre `(as_of_date - window_days, as_of_date]` (additif exact).
      - `cost_usd_prev_window` : meme somme sur la fenetre precedente de meme
        longueur `(as_of_date - 2*window_days, as_of_date - window_days]`.
      - `cost_delta_pct` : `(cost_usd - cost_usd_prev_window) /
        cost_usd_prev_window * 100`.
      - `cost_rank` : `RANK() OVER (PARTITION BY window_days ORDER BY cost_usd
        DESC)` (classement au sein de chaque fenetre, tous clusters confondus).
      - `is_top_cost` : `cost_rank <= top_cost_rank_threshold`.

    Un cluster sans cout ni sur la fenetre courante ni sur la precedente est
    exclu de la sortie (`cost_usd <> 0 OR cost_usd_prev_window <> 0`) : evite de
    materialiser 4 lignes par cluster mort depuis plus de 90 jours.
    """
    windows_array = rolling_windows_array_sql(rolling_windows)
    query = f"""
    WITH daily AS (
        SELECT
            cloud_provider,
            workspace_id,
            cluster_id,
            period_start,
            cluster_name,
            cluster_type,
            owner,
            cost_center,
            sku_group,
            dbu_quantity,
            cost_usd
        FROM {cluster_cost_daily_table}
        WHERE cluster_type = '{CLUSTER_TYPE_ALL_PURPOSE}'
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
            cluster_id,
            cluster_name,
            cluster_type,
            owner,
            cost_center,
            sku_group
        FROM daily
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY cloud_provider, workspace_id, cluster_id
            ORDER BY period_start DESC
        ) = 1
    ),
    agg AS (
        SELECT
            d.cloud_provider,
            d.workspace_id,
            d.cluster_id,
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
                    WHEN d.period_start <= date_add(a.as_of_date, -w.window_days)
                    THEN d.cost_usd ELSE 0
                END) AS cost_usd_prev_window
        FROM daily d
        CROSS JOIN anchor a
        CROSS JOIN windows w
        WHERE d.period_start > date_add(a.as_of_date, -2 * w.window_days)
          AND d.period_start <= a.as_of_date
        GROUP BY d.cloud_provider, d.workspace_id, d.cluster_id, w.window_days, a.as_of_date
    )
    SELECT
        g.cloud_provider,
        g.workspace_id,
        g.cluster_id,
        g.window_days,
        g.as_of_date,
        g.window_start,
        la.cluster_name,
        la.cluster_type,
        la.owner,
        la.cost_center,
        la.sku_group,
        g.dbu_quantity,
        g.cost_usd,
        g.cost_usd_prev_window,
        (g.cost_usd - g.cost_usd_prev_window)
            / NULLIF(g.cost_usd_prev_window, 0) * 100 AS cost_delta_pct,
        RANK() OVER (PARTITION BY g.window_days ORDER BY g.cost_usd DESC) AS cost_rank,
        RANK() OVER (PARTITION BY g.window_days ORDER BY g.cost_usd DESC)
            <= {top_cost_rank_threshold} AS is_top_cost,
        current_timestamp() AS _generated_at
    FROM agg g
    LEFT JOIN latest_attrs la
      ON la.cloud_provider = g.cloud_provider
     AND la.workspace_id = g.workspace_id
     AND la.cluster_id = g.cluster_id
    WHERE g.cost_usd <> 0 OR g.cost_usd_prev_window <> 0
    """
    return spark.sql(query)
