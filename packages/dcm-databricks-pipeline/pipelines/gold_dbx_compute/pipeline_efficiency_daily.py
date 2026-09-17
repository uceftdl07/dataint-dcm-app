"""Agregation gold `gold_dbx_compute_pipeline_efficiency_daily` (efficacite DLT).

Rollup de `gold_dbx_compute_cluster_efficiency_daily` par pipeline
Lakeflow/DLT plutot que par cluster ephemere : les clusters
`cluster_type = 'PIPELINE'` sont recrees a chaque execution (`cluster_id` change
a chaque run), `dlt_pipeline_id` est la seule cle stable pour suivre
l'utilisation d'un pipeline au fil de ses executions.

ATTENTION -- `gold_dbx_compute_cluster_efficiency_daily` NE DOIT PAS etre
filtree sur `cluster_type = 'ALL_PURPOSE'` : c'est la source de cette table.
Seule sa variante `_rolling` porte ce filtre (SC-001). Un filtre ajoute "pour
l'uniformite" dans `cluster_efficiency_daily` viderait silencieusement cette
table.

Contrairement au rollup COUT (`pipeline_cost_daily`, billing-direct : chaque
ligne de facturation porte deja `usage_metadata.dlt_pipeline_id`), l'efficacite
vient de `node_timeline`, au grain `cluster_id` : une resolution
`cluster_id -> dlt_pipeline_id` est donc necessaire ici. Elle est tiree de la
MEME source que le cout (cf. `grain_resolution.pipeline_clusters_cte_sql`, R7),
pour que cout et efficacite ne puissent pas designer deux pipelines differents
pour un meme cluster.

Regles de derivation : identiques a `job_efficiency_daily` (moyennes ponderees
par `uptime_hours`, percentiles recalcules depuis les histogrammes sommes,
sommes additives, pas de `is_zombie`).
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.grain_resolution import (
    pipeline_clusters_cte_sql,
    pipeline_name_coalesce_sql,
    pipeline_name_cte_sql,
    pipeline_name_join_sql,
)
from pipelines.gold_dbx_compute.sql_helpers import (
    CLUSTER_TYPE_PIPELINE,
    HISTOGRAM_UTILIZATION_EDGES,
    histogram_bucket_count,
    lower_bound_predicate,
    percentile_from_histogram_sql,
    sum_histograms_sql,
)

if TYPE_CHECKING:
    from datetime import date

    from pyspark.sql import DataFrame, SparkSession


def build_pipeline_efficiency_daily(
    spark: SparkSession,
    *,
    cluster_efficiency_daily_table: str,
    billing_usage_table: str,
    lakeflow_pipelines_table: str,
    lower_bound: date | None,
) -> DataFrame:
    """Construit `gold_dbx_compute_pipeline_efficiency_daily`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        cluster_efficiency_daily_table: nom qualifie (`catalog.schema.table`) de
            `gold_dbx_compute_cluster_efficiency_daily`, restreint ici aux
            clusters `cluster_type = 'PIPELINE'`.
        billing_usage_table: nom qualifie de `curated_dbx_billing_usage`
            (resolution `cluster_id -> dlt_pipeline_id`, cf.
            `grain_resolution.pipeline_clusters_cte_sql`).
        lakeflow_pipelines_table: nom qualifie de
            `curated_dbx_lakeflow_pipelines` (dernier etat connu du pipeline,
            pour `pipeline_name`).
        lower_bound: borne basse incluse de `period_start` pour la lecture
            incrementale ; `None` pour recalculer l'historique complet.

    Returns:
        Le DataFrame `gold_dbx_compute_pipeline_efficiency_daily` resultant.

    Grain : `(cloud_provider, workspace_id, dlt_pipeline_id, period_start)`.
    Source : `gold_dbx_compute_cluster_efficiency_daily` (clusters `PIPELINE`) +
    `curated_dbx_billing_usage` (mapping R7) + `curated_dbx_lakeflow_pipelines`
    (`pipeline_name`, meme resolution que `pipeline_cost_daily`).

    `INNER JOIN` DELIBERE sur le mapping : une ligne d'efficacite dont le
    `dlt_pipeline_id` n'est pas resolvable est EXCLUE (8 clusters AWS sur 5037
    mesures), jamais rattachee a `dlt_pipeline_id = NULL` -- cle de merge
    null-safe `<=>`.

    Les pipelines DLT SERVERLESS n'ont aucun cluster, donc aucune ligne dans
    `node_timeline` : ils sont absents de cette table sans perdre leur ligne de
    COUT dans `gold_dbx_compute_pipeline_cost_daily`. L'ecart de population
    entre les deux tables est ATTENDU, il se mesure et se documente, il ne se
    comble pas par une valeur par defaut.

    NE PAS sommer les `uptime_hours` de cette table avec ceux de
    `gold_dbx_compute_cluster_efficiency_daily` ni de
    `gold_dbx_compute_job_efficiency_daily` : les trois agregent des
    sous-ensembles DISJOINTS des memes lignes `node_timeline`.
    """
    # 1 jour tampon sur la lecture du MAPPING uniquement (jamais sur la sortie) :
    # une mise a jour de pipeline demarree avant minuit peut n'avoir de ligne de
    # facturation portant son `cluster_id` que la veille de la premiere journee
    # recalculee ; sans ce tampon son cluster ne serait pas resolvable.
    mapping_lower_bound = lower_bound - timedelta(days=1) if lower_bound is not None else None
    usage_date_filter = lower_bound_predicate("u.usage_date", mapping_lower_bound)
    efficiency_period_filter = lower_bound_predicate("ce.period_start", lower_bound)
    pipeline_clusters_cte = pipeline_clusters_cte_sql(
        billing_usage_table=billing_usage_table,
        period_filter=usage_date_filter,
    )
    pipelines_as_of_cte = pipeline_name_cte_sql(
        grain_cte="agg",
        lakeflow_pipelines_table=lakeflow_pipelines_table,
    )
    num_buckets = histogram_bucket_count(HISTOGRAM_UTILIZATION_EDGES)
    cpu_p95 = percentile_from_histogram_sql("g.cpu_util_hist", HISTOGRAM_UTILIZATION_EDGES, 0.95)
    mem_p95 = percentile_from_histogram_sql("g.mem_util_hist", HISTOGRAM_UTILIZATION_EDGES, 0.95)
    query = f"""
    WITH {pipeline_clusters_cte},
    daily AS (
        SELECT
            pc.dlt_pipeline_id,
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
        JOIN pipeline_clusters pc
          ON pc.cloud_provider = ce.cloud_provider
         AND pc.workspace_id = ce.workspace_id
         AND pc.cluster_id = ce.cluster_id
        WHERE ce.cluster_type = '{CLUSTER_TYPE_PIPELINE}'
        {efficiency_period_filter}
    ),
    agg AS (
        SELECT
            d.cloud_provider,
            d.workspace_id,
            d.dlt_pipeline_id,
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
        GROUP BY d.cloud_provider, d.workspace_id, d.dlt_pipeline_id, d.period_start
    ),
    latest_attrs AS (
        SELECT
            cloud_provider,
            workspace_id,
            dlt_pipeline_id,
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
            PARTITION BY cloud_provider, workspace_id, dlt_pipeline_id, period_start
            ORDER BY uptime_hours DESC, cluster_id DESC
        ) = 1
    ),
    {pipelines_as_of_cte},
    with_metrics AS (
        SELECT
            g.*,
            {pipeline_name_coalesce_sql("g")},
            {cpu_p95} AS cpu_util_p95_pct,
            {mem_p95} AS mem_util_p95_pct
        FROM agg g
        {pipeline_name_join_sql("g")}
    )
    SELECT
        m.cloud_provider,
        m.workspace_id,
        m.dlt_pipeline_id,
        m.pipeline_name,
        m.period_start,
        m.cluster_count,
        m.cpu_util_avg_pct,
        m.cpu_util_p95_pct,
        m.mem_util_avg_pct,
        m.mem_util_p95_pct,
        m.cpu_wait_avg_pct,
        -- Histogrammes EXPOSES (contrairement a cluster_efficiency_rolling) :
        -- ils sont la source des percentiles de pipeline_efficiency_rolling, qui
        -- les somme a nouveau sur sa fenetre.
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
     AND la.dlt_pipeline_id = m.dlt_pipeline_id
     AND la.period_start = m.period_start
    """
    return spark.sql(query)
