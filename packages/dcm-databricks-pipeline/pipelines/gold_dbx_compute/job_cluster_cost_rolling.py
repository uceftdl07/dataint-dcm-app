"""Agregation gold `gold_dbx_compute_job_cluster_cost_rolling` (FinOps jobs, fenetres).

Rollup 1/7/30/90 jours de `gold_dbx_compute_job_cluster_cost_daily` : pour chaque
job, cout/DBU cumules sur les derniers `window_days` jours "as of" le dernier
jour disponible, variation vs la fenetre precedente de meme longueur et
classement par cout.

Metriques additives : cout et DBU se somment. `cluster_count` aussi : les
clusters JOB sont ephemeres (un `cluster_id` distinct par execution, jamais
reutilise d'un jour a l'autre), donc la somme des comptes distincts quotidiens
egale le nombre de clusters distincts sur la fenetre -- aucun stockage de la
liste des `cluster_id` cote table quotidienne n'est requis. Il vaut 0 sur les
lignes `SERVERLESS` (aucun cluster provisionne), ce qui reste sommable sans
`COALESCE`. Le nom du job est repris au dernier etat connu. Les colonnes
jour-a-jour (`cost_usd_prev_day`) sont abandonnees (sans objet a la maille
fenetre).

`compute_kind` est repris du daily et fait partie du grain (T001b) : un job
mixte a une ligne CLASSIC et une ligne SERVERLESS par fenetre, et les rangs sont
calcules DANS chaque forme (cf. `cost_rank`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.specs import ROLLING_WINDOWS, TOP_COST_RANK_THRESHOLD
from pipelines.gold_dbx_compute.sql_helpers import rolling_windows_array_sql

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession


def build_job_cluster_cost_rolling(
    spark: SparkSession,
    *,
    job_cluster_cost_daily_table: str,
    rolling_windows: tuple[int, ...] = ROLLING_WINDOWS,
    top_cost_rank_threshold: int = TOP_COST_RANK_THRESHOLD,
) -> DataFrame:
    """Construit `gold_dbx_compute_job_cluster_cost_rolling`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        job_cluster_cost_daily_table: nom qualifie (`catalog.schema.table`) de
            `gold_dbx_compute_job_cluster_cost_daily` (unique source).
        rolling_windows: fenetres glissantes (jours) a materialiser, une ligne
            par job ET par fenetre (defaut `ROLLING_WINDOWS`).
        top_cost_rank_threshold: nombre de jobs consideres "top cost" par
            fenetre (defaut `TOP_COST_RANK_THRESHOLD`).

    Returns:
        Le DataFrame `gold_dbx_compute_job_cluster_cost_rolling` resultant.

    Grain : `(cloud_provider, workspace_id, job_id, compute_kind,
    window_days)`. Snapshot "as of" le dernier jour disponible (`as_of_date =
    MAX(period_start)`).

    Champs : `dbu_quantity`/`cost_usd`/`cluster_count` sommes sur la fenetre
    `(as_of_date - window_days, as_of_date]` ; `cost_usd_prev_window` sur la
    fenetre precedente de meme longueur ; `cost_delta_pct` = variation ; `job_name`
    au dernier etat connu ; `compute_kind` (`CLASSIC`/`SERVERLESS`, jamais NULL)
    repris du daily ; `cost_rank`/`is_top_cost` = classement par cout au sein de
    chaque couple `(window_days, compute_kind)` -- et NON de la seule
    `window_days` : une page filtree sur une forme de compute doit y lire un rang
    qui commence a 1. Deux lignes peuvent donc porter `cost_rank = 1` pour une
    meme fenetre, une par forme, et un classement toutes formes confondues
    demande d'agreger sur `compute_kind` avant de reclasser. Un job sans cout ni
    sur la fenetre courante ni sur la precedente est exclu.

    Sommer les deux `compute_kind` d'une meme `window_days` est legitime et
    redonne le cout job total de la fenetre (les deux formes partitionnent les
    memes lignes de facturation). Ni sommer plusieurs `window_days` entre elles
    (fenetres emboitees), ni avec `gold_dbx_compute_cluster_cost_rolling` /
    `gold_dbx_compute_pipeline_cost_rolling` (sous-ensembles disjoints des memes
    lignes).
    """
    windows_array = rolling_windows_array_sql(rolling_windows)
    query = f"""
    WITH daily AS (
        SELECT
            cloud_provider,
            workspace_id,
            job_id,
            compute_kind,
            period_start,
            job_name,
            cluster_count,
            dbu_quantity,
            cost_usd
        FROM {job_cluster_cost_daily_table}
    ),
    anchor AS (
        SELECT MAX(period_start) AS as_of_date FROM daily
    ),
    windows AS (
        SELECT explode({windows_array}) AS window_days
    ),
    latest_attrs AS (
        -- Grain job, VOLONTAIREMENT sans `compute_kind` : `job_name` ne depend
        -- pas de la forme de compute, les deux lignes d'un job mixte portent le
        -- meme nom. Ajouter `compute_kind` a la partition ne changerait pas la
        -- valeur, et la jointure resterait 1:1 de toute facon.
        SELECT
            cloud_provider,
            workspace_id,
            job_id,
            job_name
        FROM daily
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY cloud_provider, workspace_id, job_id
            ORDER BY period_start DESC
        ) = 1
    ),
    agg AS (
        SELECT
            d.cloud_provider,
            d.workspace_id,
            d.job_id,
            d.compute_kind,
            w.window_days,
            a.as_of_date,
            date_add(a.as_of_date, -(w.window_days - 1)) AS window_start,
            SUM(CASE
                    WHEN d.period_start > date_add(a.as_of_date, -w.window_days)
                    THEN d.cluster_count ELSE 0
                END) AS cluster_count,
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
        GROUP BY
            d.cloud_provider,
            d.workspace_id,
            d.job_id,
            d.compute_kind,
            w.window_days,
            a.as_of_date
    )
    SELECT
        g.cloud_provider,
        g.workspace_id,
        g.job_id,
        g.compute_kind,
        g.window_days,
        g.as_of_date,
        g.window_start,
        la.job_name,
        g.cluster_count,
        g.dbu_quantity,
        g.cost_usd,
        g.cost_usd_prev_window,
        (g.cost_usd - g.cost_usd_prev_window)
            / NULLIF(g.cost_usd_prev_window, 0) * 100 AS cost_delta_pct,
        RANK() OVER (
            PARTITION BY g.window_days, g.compute_kind ORDER BY g.cost_usd DESC
        ) AS cost_rank,
        RANK() OVER (PARTITION BY g.window_days, g.compute_kind ORDER BY g.cost_usd DESC)
            <= {top_cost_rank_threshold} AS is_top_cost,
        current_timestamp() AS _generated_at
    FROM agg g
    LEFT JOIN latest_attrs la
      ON la.cloud_provider = g.cloud_provider
     AND la.workspace_id = g.workspace_id
     AND la.job_id = g.job_id
    WHERE g.cost_usd <> 0 OR g.cost_usd_prev_window <> 0
    """
    return spark.sql(query)
