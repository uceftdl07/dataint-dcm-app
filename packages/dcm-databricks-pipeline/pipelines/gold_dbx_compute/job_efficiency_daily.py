"""Agregation gold `gold_dbx_compute_job_efficiency_daily` (efficacite par job).

Rollup de `gold_dbx_compute_cluster_efficiency_daily` par job Databricks plutot
que par cluster ephemere : les clusters `cluster_type = 'JOB'` sont recrees a
chaque execution (`cluster_id` change a chaque run), `job_id` est la seule cle
stable pour suivre l'utilisation d'un job au fil de ses executions.

ATTENTION -- `gold_dbx_compute_cluster_efficiency_daily` NE DOIT PAS etre
filtree sur `cluster_type = 'ALL_PURPOSE'` : c'est la source de cette table.
Seule sa variante `_rolling` porte ce filtre (SC-001). Un filtre ajoute "pour
l'uniformite" dans `cluster_efficiency_daily` viderait silencieusement cette
table.

Regles de derivation (cf. spec 024, research.md R8) :
  - Moyennes (`cpu_util_avg_pct`, `mem_util_avg_pct`, `cpu_wait_avg_pct`,
    `worker_count_avg`) et `idle_pct` : ponderees par le temps allume
    (`uptime_hours`) de chaque cluster -- une moyenne simple donnerait le meme
    poids a un cluster allume 5 minutes qu'a un cluster allume 5 heures.
  - Percentiles : JAMAIS moyennes (un p95 de p95 n'a pas de sens). Recalcules
    a partir des histogrammes `cpu_util_hist`/`mem_util_hist` sommes bucket par
    bucket, exactement comme `cluster_efficiency_rolling`.
  - Sommes additives : `uptime_hours`, `active_hours`, `autoscale_oscillation`,
    `estimated_savings_usd`. Maxima : `worker_count_max`.
  - `cluster_count` : nombre de clusters JOB distincts ayant execute le job.
  - Diagnostics (`utilization_status`, `rightsizing_reco`) : memes seuils que le
    grain cluster. PAS de `is_zombie` : a ce grain la colonne serait `false`
    partout (un cluster JOB s'arrete avec sa tache) et se lirait comme un
    controle qui passe.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.grain_resolution import (
    JOB_NAME_COALESCE_SQL,
    job_clusters_cte_sql,
    job_name_ctes_sql,
    job_name_joins_sql,
)
from pipelines.gold_dbx_compute.sql_helpers import (
    CLUSTER_TYPE_JOB,
    HISTOGRAM_UTILIZATION_EDGES,
    histogram_bucket_count,
    lower_bound_predicate,
    percentile_from_histogram_sql,
    sum_histograms_sql,
)

if TYPE_CHECKING:
    from datetime import date

    from pyspark.sql import DataFrame, SparkSession


def build_job_efficiency_daily(
    spark: SparkSession,
    *,
    cluster_efficiency_daily_table: str,
    job_task_run_timeline_table: str,
    job_run_timeline_table: str,
    lakeflow_jobs_table: str,
    lower_bound: date | None,
) -> DataFrame:
    """Construit `gold_dbx_compute_job_efficiency_daily`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        cluster_efficiency_daily_table: nom qualifie (`catalog.schema.table`) de
            `gold_dbx_compute_cluster_efficiency_daily`, restreint ici aux
            clusters `cluster_type = 'JOB'`.
        job_task_run_timeline_table: nom qualifie de
            `curated_dbx_lakeflow_job_task_run_timeline` (resolution
            `cluster_id -> job_id`, cf. `grain_resolution.job_clusters_cte_sql`).
        job_run_timeline_table: nom qualifie de
            `curated_dbx_lakeflow_job_run_timeline` (`run_name`, seul nom
            disponible pour un run SOUMIS).
        lakeflow_jobs_table: nom qualifie de `curated_dbx_lakeflow_jobs`
            (dernier etat connu du job, pour `job_name`).
        lower_bound: borne basse incluse de `period_start` pour la lecture
            incrementale ; `None` pour recalculer l'historique complet.

    Returns:
        Le DataFrame `gold_dbx_compute_job_efficiency_daily` resultant.

    Grain : `(cloud_provider, workspace_id, job_id, period_start)`.
    Source : `gold_dbx_compute_cluster_efficiency_daily` (clusters `JOB`) +
    `curated_dbx_lakeflow_job_task_run_timeline` (lignee `cluster_id -> job_id`)
    + `curated_dbx_lakeflow_jobs` / `curated_dbx_lakeflow_job_run_timeline`
    (`job_name`, meme resolution que `job_cluster_cost_daily`).

    `INNER JOIN` DELIBERE sur le mapping : une ligne d'efficacite dont le
    `job_id` n'est pas resolvable est EXCLUE, jamais rattachee a `job_id = NULL`
    (cle de merge null-safe `<=>`, cf. `grain_resolution.job_clusters_cte_sql`).

    NE PAS sommer les `uptime_hours` de cette table avec ceux de
    `gold_dbx_compute_cluster_efficiency_daily` ni de
    `gold_dbx_compute_pipeline_efficiency_daily` : les trois agregent des
    sous-ensembles DISJOINTS des memes lignes `node_timeline`.

    L'ecart de population avec `gold_dbx_compute_job_cluster_cost_daily` est
    ATTENDU : l'efficacite vient de `node_timeline` (aucune ligne pour un job
    serverless), le cout vient de la facturation. Il se mesure et se documente,
    il ne se comble pas par une valeur par defaut.
    """
    # 1 jour tampon sur la lecture du MAPPING uniquement (jamais sur la sortie) :
    # une tache demarree avant minuit peut n'avoir de ligne de timeline que la
    # veille de la premiere journee recalculee ; sans ce tampon son cluster ne
    # serait pas resolvable et sa journee disparaitrait de la sortie.
    mapping_lower_bound = lower_bound - timedelta(days=1) if lower_bound is not None else None
    task_run_period_filter = lower_bound_predicate("t.period_start_time", mapping_lower_bound)
    # La sortie, elle, est bornee a `lower_bound` : `period_start` de la source
    # gold est deja au grain jour, aucun self-join J-1 ne la fait remonter.
    efficiency_period_filter = lower_bound_predicate("ce.period_start", lower_bound)
    job_clusters_cte = job_clusters_cte_sql(
        job_task_run_timeline_table=job_task_run_timeline_table,
        period_filter=task_run_period_filter,
    )
    job_name_ctes = job_name_ctes_sql(
        grain_cte="agg",
        lakeflow_jobs_table=lakeflow_jobs_table,
        job_run_timeline_table=job_run_timeline_table,
    )
    num_buckets = histogram_bucket_count(HISTOGRAM_UTILIZATION_EDGES)
    cpu_p95 = percentile_from_histogram_sql("g.cpu_util_hist", HISTOGRAM_UTILIZATION_EDGES, 0.95)
    mem_p95 = percentile_from_histogram_sql("g.mem_util_hist", HISTOGRAM_UTILIZATION_EDGES, 0.95)
    query = f"""
    WITH {job_clusters_cte},
    daily AS (
        SELECT
            jc.job_id,
            ce.cloud_provider,
            ce.workspace_id,
            ce.cluster_id,
            ce.period_start,
            ce.cpu_util_avg_pct,
            ce.mem_util_avg_pct,
            ce.cpu_wait_avg_pct,
            ce.cpu_util_hist,
            ce.mem_util_hist,
            ce.idle_pct,
            ce.uptime_hours,
            ce.active_hours,
            ce.worker_count_avg,
            ce.worker_count_max,
            ce.autoscale_oscillation,
            ce.driver_node_type,
            ce.worker_node_type,
            ce.autoscale_enabled,
            ce.autoscale_min_workers,
            ce.autoscale_max_workers,
            ce.configured_worker_count,
            ce.recommended_node_type,
            ce.estimated_savings_usd
        FROM {cluster_efficiency_daily_table} ce
        JOIN job_clusters jc
          ON jc.cloud_provider = ce.cloud_provider
         AND jc.workspace_id = ce.workspace_id
         AND jc.cluster_id = ce.cluster_id
        WHERE ce.cluster_type = '{CLUSTER_TYPE_JOB}'
        {efficiency_period_filter}
    ),
    agg AS (
        SELECT
            d.cloud_provider,
            d.workspace_id,
            d.job_id,
            d.period_start,
            COUNT(DISTINCT d.cluster_id) AS cluster_count,
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
        GROUP BY d.cloud_provider, d.workspace_id, d.job_id, d.period_start
    ),
    latest_attrs AS (
        SELECT
            cloud_provider,
            workspace_id,
            job_id,
            period_start,
            driver_node_type,
            worker_node_type,
            -- Taille VOULUE (cf. cluster_efficiency_daily) : a ne pas confondre
            -- avec worker_count_avg/worker_count_max, agreges sur les tailles
            -- observees par minute.
            autoscale_enabled,
            autoscale_min_workers,
            autoscale_max_workers,
            configured_worker_count,
            recommended_node_type
        FROM daily
        -- Cluster le plus REPRESENTATIF du jour, pas le plus recent : a ce grain
        -- la source n'a aucun horodatage intra-journalier permettant d'ordonner
        -- deux clusters du meme jour. `cluster_id` ne sert qu'a rendre le
        -- resultat deterministe en cas d'egalite de temps allume.
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY cloud_provider, workspace_id, job_id, period_start
            ORDER BY uptime_hours DESC, cluster_id DESC
        ) = 1
    ),
    {job_name_ctes},
    with_metrics AS (
        SELECT
            g.*,
            {JOB_NAME_COALESCE_SQL},
            {cpu_p95} AS cpu_util_p95_pct,
            {mem_p95} AS mem_util_p95_pct
        FROM agg g
        {job_name_joins_sql("g")}
    )
    SELECT
        m.cloud_provider,
        m.workspace_id,
        m.job_id,
        m.job_name,
        m.period_start,
        m.cluster_count,
        m.cpu_util_avg_pct,
        m.cpu_util_p95_pct,
        m.mem_util_avg_pct,
        m.mem_util_p95_pct,
        m.cpu_wait_avg_pct,
        -- Histogrammes EXPOSES (contrairement a cluster_efficiency_rolling) :
        -- ils sont la source des percentiles de job_efficiency_rolling, qui les
        -- somme a nouveau sur sa fenetre.
        m.cpu_util_hist,
        m.mem_util_hist,
        m.idle_pct,
        m.uptime_hours,
        m.active_hours,
        m.worker_count_avg,
        m.worker_count_max,
        m.autoscale_oscillation,
        la.driver_node_type,
        la.worker_node_type,
        la.autoscale_enabled,
        la.autoscale_min_workers,
        la.autoscale_max_workers,
        la.configured_worker_count,
        -- Memes seuils que cluster_efficiency_daily / _rolling.
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
     AND la.job_id = m.job_id
     AND la.period_start = m.period_start
    """
    return spark.sql(query)
