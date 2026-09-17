"""Agregation gold `gold_dbx_compute_cluster_efficiency_rolling` (utilisation, fenetres).

Rollup 1/7/30/90 jours de `gold_dbx_compute_cluster_efficiency_daily` : pour
chaque cluster, utilisation CPU/memoire et diagnostic de dimensionnement
recalcules sur les derniers `window_days` jours "as of" le dernier jour
disponible.

Regles de derivation :
  - Percentiles (`cpu_util_p95_pct`, `mem_util_p95_pct`) : recalcules a partir
    des histogrammes quotidiens (`cpu_util_hist`/`mem_util_hist`) sommes bucket
    par bucket sur la fenetre, les percentiles quotidiens n'etant pas
    moyennables (cf. `sql_helpers.percentile_from_histogram_sql`). Les
    histogrammes fusionnes restent internes (CTE) et ne sont pas materialises
    en sortie (aucun consommateur aval, seuls les percentiles sont exposes).
  - Moyennes (`cpu_util_avg_pct`, `mem_util_avg_pct`, `cpu_wait_avg_pct`,
    `worker_count_avg`) et `idle_pct` : moyennes ponderees par le temps allume
    (`uptime_hours`) de chaque jour.
  - Sommes additives : `uptime_hours`, `active_hours`, `autoscale_oscillation`,
    `estimated_savings_usd`.
  - Maxima : `worker_count_max`.
  - Diagnostics (`is_zombie`, `utilization_status`, `rightsizing_reco`) :
    recalcules a partir des metriques de la fenetre (memes seuils que la table
    quotidienne, cf. `cluster_efficiency_daily`).
  - Attributs descriptifs (`cluster_name`, `cluster_type`, `driver_node_type`,
    `worker_node_type`, `recommended_node_type`) et configuration de taille
    (`autoscale_enabled`, `autoscale_min_workers`, `autoscale_max_workers`,
    `configured_worker_count`) : repris au dernier jour connu.
  - Fenetre precedente (`uptime_hours_prev_window`, `idle_pct_prev_window`) :
    memes formules que la fenetre courante, appliquees a
    `(as_of_date - 2*window_days, as_of_date - window_days]` par la CTE dediee
    `prev_agg`, jointe en `LEFT JOIN` — l'absence de fenetre precedente reste
    `NULL`, jamais `0`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.specs import ROLLING_WINDOWS
from pipelines.gold_dbx_compute.sql_helpers import (
    CLUSTER_TYPE_ALL_PURPOSE,
    HISTOGRAM_UTILIZATION_EDGES,
    histogram_bucket_count,
    percentile_from_histogram_sql,
    rolling_windows_array_sql,
    sum_histograms_sql,
)

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession


def build_cluster_efficiency_rolling(
    spark: SparkSession,
    *,
    cluster_efficiency_daily_table: str,
    rolling_windows: tuple[int, ...] = ROLLING_WINDOWS,
) -> DataFrame:
    """Construit `gold_dbx_compute_cluster_efficiency_rolling`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        cluster_efficiency_daily_table: nom qualifie (`catalog.schema.table`)
            de `gold_dbx_compute_cluster_efficiency_daily` (unique source).
        rolling_windows: fenetres glissantes (jours) a materialiser, une ligne
            par cluster ET par fenetre (defaut `ROLLING_WINDOWS`).

    Returns:
        Le DataFrame `gold_dbx_compute_cluster_efficiency_rolling` resultant.

    Grain : `(cloud_provider, workspace_id, cluster_id, window_days)`. Snapshot
    "as of" le dernier jour disponible (`as_of_date = MAX(period_start)`).

    Un cluster sans aucun jour dans la fenetre COURANTE n'est pas materialise
    (la CTE `agg` pilote la sortie, cf. `WHERE m.uptime_hours > 0`) : ses
    colonnes de fenetre precedente ne sont donc jamais exposees seules.
    """
    windows_array = rolling_windows_array_sql(rolling_windows)
    num_buckets = histogram_bucket_count(HISTOGRAM_UTILIZATION_EDGES)
    cpu_p95 = percentile_from_histogram_sql("g.cpu_util_hist", HISTOGRAM_UTILIZATION_EDGES, 0.95)
    mem_p95 = percentile_from_histogram_sql("g.mem_util_hist", HISTOGRAM_UTILIZATION_EDGES, 0.95)
    query = f"""
    WITH daily AS (
        SELECT
            cloud_provider,
            workspace_id,
            cluster_id,
            period_start,
            cluster_name,
            cluster_type,
            cpu_util_avg_pct,
            mem_util_avg_pct,
            cpu_wait_avg_pct,
            cpu_util_hist,
            mem_util_hist,
            idle_pct,
            uptime_hours,
            active_hours,
            worker_count_avg,
            worker_count_max,
            autoscale_oscillation,
            driver_node_type,
            worker_node_type,
            autoscale_enabled,
            autoscale_min_workers,
            autoscale_max_workers,
            configured_worker_count,
            recommended_node_type,
            estimated_savings_usd
        FROM {cluster_efficiency_daily_table}
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
            driver_node_type,
            worker_node_type,
            -- Taille VOULUE au dernier jour connu (cf. cluster_efficiency_daily) :
            -- a ne pas confondre avec worker_count_avg/worker_count_max, agreges
            -- sur la fenetre a partir des tailles observees par minute.
            autoscale_enabled,
            autoscale_min_workers,
            autoscale_max_workers,
            configured_worker_count,
            recommended_node_type
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
            SUM(d.uptime_hours) AS uptime_hours,
            SUM(d.active_hours) AS active_hours,
            SUM(d.autoscale_oscillation) AS autoscale_oscillation,
            SUM(d.estimated_savings_usd) AS estimated_savings_usd,
            MAX(d.worker_count_max) AS worker_count_max,
            SUM(d.cpu_util_avg_pct * d.uptime_hours)
                / NULLIF(SUM(CASE WHEN d.cpu_util_avg_pct IS NOT NULL
                                  THEN d.uptime_hours END), 0) AS cpu_util_avg_pct,
            SUM(d.mem_util_avg_pct * d.uptime_hours)
                / NULLIF(SUM(CASE WHEN d.mem_util_avg_pct IS NOT NULL
                                  THEN d.uptime_hours END), 0) AS mem_util_avg_pct,
            SUM(d.cpu_wait_avg_pct * d.uptime_hours)
                / NULLIF(SUM(CASE WHEN d.cpu_wait_avg_pct IS NOT NULL
                                  THEN d.uptime_hours END), 0) AS cpu_wait_avg_pct,
            SUM(d.worker_count_avg * d.uptime_hours)
                / NULLIF(SUM(CASE WHEN d.worker_count_avg IS NOT NULL
                                  THEN d.uptime_hours END), 0) AS worker_count_avg,
            SUM(d.idle_pct * d.uptime_hours)
                / NULLIF(SUM(CASE WHEN d.idle_pct IS NOT NULL
                                  THEN d.uptime_hours END), 0) AS idle_pct,
            {sum_histograms_sql("d.cpu_util_hist", num_buckets)} AS cpu_util_hist,
            {sum_histograms_sql("d.mem_util_hist", num_buckets)} AS mem_util_hist
        FROM daily d
        CROSS JOIN anchor a
        CROSS JOIN windows w
        WHERE d.period_start > date_add(a.as_of_date, -w.window_days)
          AND d.period_start <= a.as_of_date
        GROUP BY d.cloud_provider, d.workspace_id, d.cluster_id, w.window_days, a.as_of_date
    ),
    -- Fenetre PRECEDENTE de meme longueur, dans une CTE dediee plutot qu'en
    -- elargissant `agg` a 2 * window_days (cf. research.md R1) : conditionner les
    -- 13 agregats d'`agg` - dont 4 moyennes ponderees, 2 histogrammes et 1 maximum -
    -- reviendrait a les reecrire tous, au risque de fausser une metrique en
    -- production, pour le seul benefice de l'uniformite de style.
    -- ATTENTION : ne comparer que des colonnes calculees a l'identique. Toute
    -- evolution de la formule d'`idle_pct` dans `agg` doit etre repercutee ici.
    prev_agg AS (
        SELECT
            d.cloud_provider,
            d.workspace_id,
            d.cluster_id,
            w.window_days,
            SUM(d.uptime_hours) AS uptime_hours_prev_window,
            SUM(d.idle_pct * d.uptime_hours)
                / NULLIF(SUM(CASE WHEN d.idle_pct IS NOT NULL
                                  THEN d.uptime_hours END), 0) AS idle_pct_prev_window
        FROM daily d
        CROSS JOIN anchor a
        CROSS JOIN windows w
        WHERE d.period_start > date_add(a.as_of_date, -2 * w.window_days)
          AND d.period_start <= date_add(a.as_of_date, -w.window_days)
        GROUP BY d.cloud_provider, d.workspace_id, d.cluster_id, w.window_days
    ),
    with_metrics AS (
        SELECT
            g.*,
            {cpu_p95} AS cpu_util_p95_pct,
            {mem_p95} AS mem_util_p95_pct
        FROM agg g
    )
    SELECT
        m.cloud_provider,
        m.workspace_id,
        m.cluster_id,
        m.window_days,
        m.as_of_date,
        m.window_start,
        la.cluster_name,
        la.cluster_type,
        m.cpu_util_avg_pct,
        m.cpu_util_p95_pct,
        m.mem_util_avg_pct,
        m.mem_util_p95_pct,
        m.cpu_wait_avg_pct,
        m.idle_pct,
        m.uptime_hours,
        m.active_hours,
        -- Fenetre precedente de meme longueur : NULL (jamais 0) quand elle ne
        -- contient aucun jour, un 0 se lisant "allume zero heure" donc une chute
        -- de 100 %, au lieu de "pas de comparaison possible".
        p.uptime_hours_prev_window,
        p.idle_pct_prev_window,
        m.worker_count_avg,
        m.worker_count_max,
        m.autoscale_oscillation,
        la.driver_node_type,
        la.worker_node_type,
        la.autoscale_enabled,
        la.autoscale_min_workers,
        la.autoscale_max_workers,
        la.configured_worker_count,
        -- Diagnostics recalcules sur la fenetre (memes seuils que cluster_efficiency_daily).
        (m.uptime_hours > 8 AND m.cpu_util_p95_pct < 15 AND m.active_hours < 1) AS is_zombie,
        CASE
            WHEN m.cpu_util_p95_pct < 40 AND m.mem_util_p95_pct < 50 THEN 'OVER'
            WHEN m.cpu_util_p95_pct > 85 OR m.mem_util_p95_pct > 85 THEN 'UNDER'
            ELSE 'OPTIMAL'
        END AS utilization_status,
        la.recommended_node_type,
        CASE
            WHEN m.cpu_util_p95_pct < 40 AND m.mem_util_p95_pct < 50
                 AND la.recommended_node_type IS NOT NULL
                THEN concat('Reduire vers ', la.recommended_node_type)
            WHEN m.cpu_util_p95_pct < 40 AND m.mem_util_p95_pct < 50
                THEN 'Reduire la taille du cluster (aucun node type plus petit disponible)'
            WHEN m.cpu_util_p95_pct > 85 OR m.mem_util_p95_pct > 85
                THEN 'Augmenter la taille du cluster (CPU/memoire proches de la saturation)'
            ELSE NULL
        END AS rightsizing_reco,
        m.estimated_savings_usd,
        current_timestamp() AS _generated_at
    FROM with_metrics m
    LEFT JOIN latest_attrs la
      ON la.cloud_provider = m.cloud_provider
     AND la.workspace_id = m.workspace_id
     AND la.cluster_id = m.cluster_id
    -- window_days FAIT PARTIE de la cle : prev_agg porte une ligne par cluster ET
    -- par fenetre, joindre sans lui multiplierait chaque ligne de sortie par 4.
    LEFT JOIN prev_agg p
      ON p.cloud_provider = m.cloud_provider
     AND p.workspace_id = m.workspace_id
     AND p.cluster_id = m.cluster_id
     AND p.window_days = m.window_days
    WHERE m.uptime_hours > 0
    """
    return spark.sql(query)
