"""Agregation gold `gold_dbx_compute_cluster_efficiency_daily` (utilisation / rightsizing).

Utilisation quotidienne des clusters Databricks : charge CPU/memoire,
temps actif vs. idle, stabilite de l'autoscaling, detection des clusters
zombies et recommandation de redimensionnement (rightsizing) avec economie
estimee. Alimente le diagnostic de sur/sous-dimensionnement des clusters.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.sql_helpers import (
    HISTOGRAM_UTILIZATION_EDGES,
    cluster_type_case_expr,
    histogram_from_edges_sql,
    lower_bound_predicate,
)

if TYPE_CHECKING:
    from datetime import date

    from pyspark.sql import DataFrame, SparkSession


def build_cluster_efficiency_daily(
    spark: SparkSession,
    *,
    node_timeline_table: str,
    clusters_table: str,
    node_types_table: str,
    job_task_run_timeline_table: str,
    cost_daily_table: str,
    lower_bound: date | None,
) -> DataFrame:
    """Construit `gold_dbx_compute_cluster_efficiency_daily`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        node_timeline_table: nom qualifie (`catalog.schema.table`) de
            `curated_dbx_compute_node_timeline`.
        clusters_table: nom qualifie de `curated_dbx_compute_clusters`
            (dernier etat connu du cluster).
        node_types_table: nom qualifie de `curated_dbx_compute_node_types`
            (referentiel des types de node, pour le rightsizing).
        job_task_run_timeline_table: nom qualifie de
            `curated_dbx_lakeflow_job_task_run_timeline` (signal d'activite).
        cost_daily_table: nom qualifie de
            `gold_dbx_compute_cluster_cost_daily` (montant $ des economies
            estimees).
        lower_bound: borne basse incluse de `period_start` pour la lecture
            incrementale ; `None` pour recalculer l'historique complet.

    Returns:
        Le DataFrame `gold_dbx_compute_cluster_efficiency_daily` resultant.

    Grain : `(cloud_provider, workspace_id, cluster_id, period_start)`.
    Source : `curated_dbx_compute_node_timeline` (grain minute, agrege par
    jour) + `curated_dbx_lakeflow_job_task_run_timeline` (signal d'activite) +
    `curated_dbx_compute_node_types` (rightsizing) + `gold_dbx_compute_cluster_cost_daily`
    (montant $ des economies estimees).

    Champs et formule de calcul :
      - `cpu_util_avg_pct`/`cpu_util_p95_pct` : niveau d'utilisation CPU du
        cluster sur la journee (moyenne, puis pic soutenu au 95e percentile,
        base du rightsizing). Formule : `AVG`/`percentile_approx(0.95)` de
        `cpu_user_percent + cpu_system_percent`, calcule par minute puis
        agrege par jour.
      - `mem_util_avg_pct`/`mem_util_p95_pct` : niveau d'utilisation memoire
        (moyenne et pic soutenu). Formule : memes agregats sur
        `mem_used_percent`.
      - `cpu_wait_avg_pct` : part du temps CPU passe en attente I/O (signal de
        goulot d'etranglement disque/reseau plutot que de calcul). Formule :
        `AVG(cpu_wait_percent)`.
      - `idle_pct`/`uptime_hours` : part du temps allume sans aucune tache
        active, et nombre d'heures allume au total. Formule : `idle_pct =
        idle_minutes / running_minutes * 100`, ou une minute est "idle" si
        aucune tache n'y est active (cf. `has_active_task` ci-dessous) ;
        `uptime_hours = running_minutes / 60`.
      - `active_hours` : nombre d'heures ou au moins une tache a reellement
        tourne sur ce cluster. Une minute de `node_timeline` est consideree
        active s'il existe une ligne de
        `curated_dbx_lakeflow_job_task_run_timeline` dont la periode
        (`period_start_time`/`period_end_time`) chevauche cette minute ET
        dont l'array `compute` (`array<struct<type,cluster_id,warehouse_id>>`)
        contient un element de `cluster_id` correspondant (fonction d'ordre
        superieur `exists(...)`, pas de dot-notation puisque `compute` est un
        array). Ce signal remplace `curated_dbx_query_history`, qui ne trace
        que les requetes executees sur des SQL Warehouses — jamais sur des
        clusters classiques (`compute.cluster_id` toujours `NULL` sur cette
        table). Formule : `(running_minutes - idle_minutes) / 60`, soit le
        COMPLEMENT EXACT de `idle_pct` sur la meme grille par minute que
        `uptime_hours` — donc `active_hours <= uptime_hours` par
        construction. Limite residuelle : `compute` n'est peuple par Databricks
        que depuis fin novembre 2025 ; les periodes plus anciennes n'apportent
        aucun signal d'activite (traitees comme non actives, donc
        `active_hours = 0`).
      - `worker_count_avg`/`worker_count_max` : taille du cluster observee sur
        la journee (moyenne et pic). Formule : `AVG`/`MAX` du nombre de
        workers par minute (lignes `driver = false`).
      - `autoscale_oscillation` : instabilite de l'autoscaling (nombre de
        fois ou la taille du cluster a change dans la journee). Formule :
        nombre de minutes ou le nombre de workers differe de la minute
        precedente (`LAG` partitionne par cluster).
      - `cluster_name`/`driver_node_type`/`worker_node_type` : identite et
        configuration materielle du cluster au dernier etat connu
        (`change_time < period_start + 1 jour` : etat connu a un instant
        quelconque de `period_start`, pas seulement avant minuit - un cast
        `TIMESTAMP <= DATE` a minuit exclurait a tort les clusters crees le
        jour meme).
      - `autoscale_enabled`/`autoscale_min_workers`/`autoscale_max_workers`/
        `configured_worker_count` : taille VOULUE du cluster, au meme dernier
        etat connu (a ne pas confondre avec `worker_count_avg`/
        `worker_count_max`, tailles OBSERVEES par minute). Formule :
        `autoscale_enabled = min_autoscale_workers IS NOT NULL AND
        max_autoscale_workers IS NOT NULL`, les bornes et `worker_count` etant
        reprises telles quelles. Autoscaling actif => bornes renseignees et
        `configured_worker_count` NULL ; taille fixe => l'inverse exactement
        (modes mutuellement exclusifs cote source). Les quatre colonnes sont
        exposees separement plutot que fusionnees par un
        `COALESCE(min_autoscale_workers, worker_count)`, qui afficherait une
        plage d'autoscaling "2-2" sur un cluster qui n'en a aucune.
      - `cluster_type` : categorie du cluster derivee de `cluster_source`
        (dernier etat connu) via `cluster_type_case_expr` : `ALL_PURPOSE`,
        `JOB` (ephemere - recree a chaque execution, cf.
        `gold_dbx_compute.job_cluster_cost_daily`) ou `PIPELINE`. Permet de
        filtrer les clusters JOB des clusters persistants avant toute
        analyse agregee d'utilisation. Les clusters sans aucun etat connu
        dans `curated_dbx_compute_clusters` (categorie `OTHER`, cf.
        `gold_dbx_compute.cluster_cost_daily`) sont exclus de la sortie
        plutot qu'exposes sans `driver_node_type`/`worker_node_type` ni type
        fiables.
      - `is_zombie` : cluster allume longtemps avec une charge quasi nulle et
        aucune activite detectee — candidat a l'arret. Formule :
        `uptime_hours > 8 AND cpu_util_p95_pct < 15 AND active_hours < 1`.
      - `utilization_status` : diagnostic de dimensionnement. Formule :
        `'OVER'` (surdimensionne) si `cpu_util_p95_pct < 40 AND
        mem_util_p95_pct < 50` ; `'UNDER'` (sous-dimensionne) si
        `cpu_util_p95_pct > 85 OR mem_util_p95_pct > 85` ; sinon `'OPTIMAL'`.
      - `recommended_node_type` : type d'instance plus petit propose en
        remplacement. Formule : node le plus proche (par `core_count`)
        strictement plus petit que `worker_node_type`, cherche dans
        `curated_dbx_compute_node_types` (pas de colonne de prix disponible
        dans ce referentiel : le candidat retenu est une approximation par
        taille, pas par cout reel).
      - `rightsizing_reco` : recommandation lisible d'ajustement de la taille
        du cluster, derivee de `utilization_status` et de la disponibilite
        d'un `recommended_node_type`.
      - `estimated_savings_usd` : economie estimee en dollars si la
        recommandation de redimensionnement est appliquee, seulement quand
        `utilization_status = 'OVER'` et qu'un node plus petit existe.
        Formule : `cost_usd` du jour (lu dans
        `gold_dbx_compute_cluster_cost_daily`) `* (1 - recommended_core_count
        / current_core_count)` (pas de tarif par node_type disponible :
        approximation par ratio de `core_count`).
    """
    period_filter = lower_bound_predicate("to_date(start_time)", lower_bound)
    query = f"""
    WITH node_timeline_filtered AS (
        SELECT
            cloud_provider,
            account_id,
            workspace_id,
            cluster_id,
            instance_id,
            start_time,
            driver,
            node_type,
            cpu_user_percent,
            cpu_system_percent,
            cpu_wait_percent,
            mem_used_percent,
            to_date(start_time) AS period_start
        FROM {node_timeline_table}
        WHERE 1 = 1
        {period_filter}
    ),
    per_minute AS (
        SELECT
            cloud_provider,
            account_id,
            workspace_id,
            cluster_id,
            period_start,
            start_time,
            COUNT(CASE WHEN driver = false THEN 1 END) AS worker_count_minute,
            AVG(cpu_user_percent + cpu_system_percent) AS cpu_util_minute,
            AVG(mem_used_percent) AS mem_util_minute,
            AVG(cpu_wait_percent) AS cpu_wait_minute
        FROM node_timeline_filtered
        GROUP BY cloud_provider, account_id, workspace_id, cluster_id, period_start, start_time
    ),
    per_minute_with_prev AS (
        SELECT
            pm.*,
            LAG(worker_count_minute) OVER (
                PARTITION BY cloud_provider, workspace_id, cluster_id
                ORDER BY start_time
            ) AS prev_worker_count
        FROM per_minute pm
    ),
    minutes_activity AS (
        SELECT
            pm.*,
            EXISTS (
                SELECT 1
                FROM {job_task_run_timeline_table} jt
                WHERE jt.workspace_id = pm.workspace_id
                  AND jt.period_start_time < pm.start_time + INTERVAL 1 MINUTES
                  AND jt.period_end_time > pm.start_time
                  AND exists(jt.compute, c -> c.cluster_id = pm.cluster_id)
            ) AS has_active_task
        FROM per_minute_with_prev pm
    ),
    daily_metrics AS (
        SELECT
            cloud_provider,
            workspace_id,
            cluster_id,
            period_start,
            AVG(cpu_util_minute) AS cpu_util_avg_pct,
            percentile_approx(cpu_util_minute, 0.95) AS cpu_util_p95_pct,
            AVG(mem_util_minute) AS mem_util_avg_pct,
            percentile_approx(mem_util_minute, 0.95) AS mem_util_p95_pct,
            AVG(cpu_wait_minute) AS cpu_wait_avg_pct,
            {histogram_from_edges_sql("cpu_util_minute", HISTOGRAM_UTILIZATION_EDGES)}
                AS cpu_util_hist,
            {histogram_from_edges_sql("mem_util_minute", HISTOGRAM_UTILIZATION_EDGES)}
                AS mem_util_hist,
            COUNT(*) AS running_minutes,
            SUM(CASE WHEN NOT has_active_task THEN 1 ELSE 0 END) AS idle_minutes,
            COUNT(*) / 60.0 AS uptime_hours,
            AVG(worker_count_minute) AS worker_count_avg,
            MAX(worker_count_minute) AS worker_count_max,
            SUM(
                CASE
                    WHEN prev_worker_count IS NOT NULL AND worker_count_minute <> prev_worker_count
                    THEN 1
                    ELSE 0
                END
            ) AS autoscale_oscillation
        FROM minutes_activity
        GROUP BY cloud_provider, workspace_id, cluster_id, period_start
    ),
    clusters_as_of AS (
        SELECT
            d.cloud_provider,
            d.workspace_id,
            d.cluster_id,
            d.period_start,
            c.cluster_source,
            c.cluster_name,
            c.driver_node_type,
            c.worker_node_type,
            -- Autoscaling actif <=> les DEUX bornes sont renseignees ; taille fixe
            -- <=> worker_count renseigne et bornes NULL. Les deux modes sont
            -- mutuellement exclusifs et complets cote source (cf. research.md R2) :
            -- la detection est exacte, pas heuristique.
            (c.min_autoscale_workers IS NOT NULL AND c.max_autoscale_workers IS NOT NULL)
                AS autoscale_enabled,
            c.min_autoscale_workers AS autoscale_min_workers,
            c.max_autoscale_workers AS autoscale_max_workers,
            c.worker_count AS configured_worker_count
        FROM daily_metrics d
        LEFT JOIN {clusters_table} c
          ON c.cloud_provider = d.cloud_provider
         AND c.workspace_id = d.workspace_id
         AND c.cluster_id = d.cluster_id
         AND c.change_time < d.period_start + INTERVAL 1 DAY
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY d.cloud_provider, d.workspace_id, d.cluster_id, d.period_start
            ORDER BY c.change_time DESC
        ) = 1
    ),
    -- Node le plus proche (par core_count) STRICTEMENT plus petit que le
    -- worker_node_type courant : candidat de "downsizing" (pas de prix par
    -- node_type disponible cote referentiel, cf. docstring de la fonction).
    smaller_node_candidate AS (
        SELECT
            ca.cloud_provider,
            ca.workspace_id,
            ca.cluster_id,
            ca.period_start,
            nt.node_type AS recommended_node_type,
            nt.core_count AS recommended_core_count,
            cur.core_count AS current_core_count,
            ROW_NUMBER() OVER (
                PARTITION BY ca.cloud_provider, ca.workspace_id, ca.cluster_id, ca.period_start
                ORDER BY nt.core_count DESC
            ) AS rn
        FROM clusters_as_of ca
        LEFT JOIN {node_types_table} cur
          ON cur.cloud_provider = ca.cloud_provider AND cur.node_type = ca.worker_node_type
        LEFT JOIN {node_types_table} nt
          ON nt.cloud_provider = ca.cloud_provider
         AND nt.core_count < cur.core_count
    ),
    recommended AS (
        SELECT
            cloud_provider, workspace_id, cluster_id, period_start,
            recommended_node_type, recommended_core_count, current_core_count
        FROM smaller_node_candidate
        WHERE rn = 1
    ),
    cost AS (
        SELECT cloud_provider, workspace_id, cluster_id, period_start, cost_usd
        FROM {cost_daily_table}
    )
    SELECT
        w.cloud_provider,
        w.workspace_id,
        w.cluster_id,
        w.period_start,
        ca.cluster_name,
        {cluster_type_case_expr("ca.cluster_source")} AS cluster_type,
        w.cpu_util_avg_pct,
        w.cpu_util_p95_pct,
        w.mem_util_avg_pct,
        w.mem_util_p95_pct,
        w.cpu_wait_avg_pct,
        w.cpu_util_hist,
        w.mem_util_hist,
        (w.idle_minutes / NULLIF(w.running_minutes, 0)) * 100 AS idle_pct,
        w.uptime_hours,
        -- Complement exact d'idle_pct sur la grille par minute (cf. docstring) :
        -- garantit active_hours <= uptime_hours.
        (w.running_minutes - w.idle_minutes) / 60.0 AS active_hours,
        w.worker_count_avg,
        w.worker_count_max,
        w.autoscale_oscillation,
        ca.driver_node_type,
        ca.worker_node_type,
        -- Configuration de taille (voulue), a distinguer de worker_count_avg/
        -- worker_count_max ci-dessus, qui sont des tailles OBSERVEES par minute.
        ca.autoscale_enabled,
        ca.autoscale_min_workers,
        ca.autoscale_max_workers,
        ca.configured_worker_count,
        (
            w.uptime_hours > 8
            AND w.cpu_util_p95_pct < 15
            AND (w.running_minutes - w.idle_minutes) / 60.0 < 1
        ) AS is_zombie,
        CASE
            WHEN w.cpu_util_p95_pct < 40 AND w.mem_util_p95_pct < 50 THEN 'OVER'
            WHEN w.cpu_util_p95_pct > 85 OR w.mem_util_p95_pct > 85 THEN 'UNDER'
            ELSE 'OPTIMAL'
        END AS utilization_status,
        r.recommended_node_type,
        CASE
            WHEN w.cpu_util_p95_pct < 40 AND w.mem_util_p95_pct < 50
                 AND r.recommended_node_type IS NOT NULL
                THEN concat('Reduire vers ', r.recommended_node_type)
            WHEN w.cpu_util_p95_pct < 40 AND w.mem_util_p95_pct < 50
                THEN 'Reduire la taille du cluster (aucun node type plus petit disponible)'
            WHEN w.cpu_util_p95_pct > 85 OR w.mem_util_p95_pct > 85
                THEN 'Augmenter la taille du cluster (CPU/memoire proches de la saturation)'
            ELSE NULL
        END AS rightsizing_reco,
        CASE
            WHEN w.cpu_util_p95_pct < 40 AND w.mem_util_p95_pct < 50
                 AND r.recommended_core_count IS NOT NULL AND r.current_core_count > 0
                THEN cst.cost_usd * (1 - (r.recommended_core_count / r.current_core_count))
            ELSE NULL
        END AS estimated_savings_usd,
        current_timestamp() AS _generated_at
    FROM daily_metrics w
    LEFT JOIN clusters_as_of ca
      ON ca.cloud_provider = w.cloud_provider AND ca.workspace_id = w.workspace_id
     AND ca.cluster_id = w.cluster_id AND ca.period_start = w.period_start
    LEFT JOIN recommended r
      ON r.cloud_provider = w.cloud_provider AND r.workspace_id = w.workspace_id
     AND r.cluster_id = w.cluster_id AND r.period_start = w.period_start
    LEFT JOIN cost cst
      ON cst.cloud_provider = w.cloud_provider AND cst.workspace_id = w.workspace_id
     AND cst.cluster_id = w.cluster_id AND cst.period_start = w.period_start
    WHERE {cluster_type_case_expr("ca.cluster_source")} <> 'OTHER'
    """
    return spark.sql(query)
