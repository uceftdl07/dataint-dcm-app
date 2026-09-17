"""Agregation gold `gold_dbx_compute_total_cost_daily` (FinOps cout total).

Cout Databricks total par workspace et par jour, deduplique entre les 5
familles de compute (clusters ALL_PURPOSE, SQL Warehouses, jobs, pipelines,
serverless hors job/pipeline/warehouse). Remplace la logique de UNION ALL
avec filtres d'exclusion jusque-la dupliquee cote consommateurs (DCM app
`dashboard_bundle.py`, cf. DCINT-335) par une seule table gold deja
consolidee.

Le cout Databricks n'a pas de table source unique : chaque type de compute
facture separement, et 3 des 5 tables `*_cost_daily` couvrent deja CLASSIC +
SERVERLESS pour leur perimetre (`job_cluster_cost_daily`,
`pipeline_cost_daily`, `warehouse_cost_daily` couvre l'equivalent SQL
Warehouse de `serverless_cost_daily`). Un UNION ALL naif sur les 5 tables
surestime donc le total : `cluster_cost_daily` re-decoupe une partie du cout
JOB/PIPELINE par type de cluster, et `serverless_cost_daily` re-decoupe une
partie du cout JOB/DLT_PIPELINE/SQL_WAREHOUSE par surface serverless.

`warehouse_cost_daily` et `serverless_cost_daily(serverless_surface=
'SQL_WAREHOUSE')` ne sont pas strictement identiques par workspace :
`warehouse_cost_daily` est un sur-ensemble, jamais une sous-estimation, donc
aucun risque de doublon a l'exclure du cote serverless et a garder
`warehouse_cost_daily` tel quel comme source de verite pour ce perimetre (le
contraire — sommer les deux — aurait double-compte).

`lz_id`/`ba_name` (Business Application) : PARTIELS, pas garantis non-NULL.
Mapping `workspace_id -> subscription_or_account_id` via
`dim_reference_landing_zone_dbx_workspace` (`pipelines.reference_lz`), puis
jointure vers `dim_landing_zone` qui porte `lz_id` ET
`business_application_name` (cf. `pipelines.gold_landing_zone.view`).
`dim_landing_zone` est un INNER JOIN strict vers
`dim_reference_landing_zone_business_application` (clarif C1 de
`pipelines.gold_landing_zone.view`), donc toute LZ sans Business Application
associee est absente de `dim_landing_zone` et n'enrichit pas cette table.
Choix produit assume malgre le taux de couverture : exposer `lz_id`/`ba_name`
NULL plutot que de les omettre, les consommateurs peuvent filtrer eux-memes.

Pas de `compute_category` de detail : cette table est un TOTAL, le detail par
famille de compute reste dans les 5 tables sources.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.sql_helpers import lower_bound_predicate

if TYPE_CHECKING:
    from datetime import date

    from pyspark.sql import DataFrame, SparkSession


def build_total_cost_daily(
    spark: SparkSession,
    *,
    cluster_cost_daily_table: str,
    warehouse_cost_daily_table: str,
    job_cluster_cost_daily_table: str,
    pipeline_cost_daily_table: str,
    serverless_cost_daily_table: str,
    dbx_workspace_reference_table: str,
    dim_landing_zone_table: str,
    lower_bound: date | None,
) -> DataFrame:
    """Construit `gold_dbx_compute_total_cost_daily`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        cluster_cost_daily_table: nom qualifie de
            `gold_dbx_compute_cluster_cost_daily`.
        warehouse_cost_daily_table: nom qualifie de
            `gold_dbx_compute_warehouse_cost_daily`.
        job_cluster_cost_daily_table: nom qualifie de
            `gold_dbx_compute_job_cluster_cost_daily`.
        pipeline_cost_daily_table: nom qualifie de
            `gold_dbx_compute_pipeline_cost_daily`.
        serverless_cost_daily_table: nom qualifie de
            `gold_dbx_compute_serverless_cost_daily`.
        dbx_workspace_reference_table: nom qualifie de
            `dim_reference_landing_zone_dbx_workspace` (`workspace_id ->
            subscription_or_account_id`, cle unique `workspace_id`).
        dim_landing_zone_table: nom qualifie de `dim_landing_zone` (porte
            `lz_id` ET `business_application_name`, cle unique
            `subscription_or_account_id`).
        lower_bound: borne basse incluse de `period_start` pour la lecture
            incrementale ; `None` pour recalculer l'historique complet. Les 5
            tables sources sont deja des gold quotidiennes stabilisees, la
            meme borne s'applique donc directement en lecture (pas de tampon
            de lag supplementaire, contrairement aux builders qui lisent la
            facturation brute).

    Returns:
        Le DataFrame `gold_dbx_compute_total_cost_daily` resultant.

    Grain : `(cloud_provider, workspace_id, period_start)`. Source cout : les
    5 tables gold `*_cost_daily` deja calculees (aucune relecture de la
    facturation curated), chacune restreinte a la tranche qu'elle possede en
    propre pour eviter le double comptage (cf. docstring du module) :
      - `cluster_cost_daily` : uniquement `cluster_type = 'ALL_PURPOSE'`
        (JOB/PIPELINE sont deja dans les rollups billing-direct
        correspondants).
      - `warehouse_cost_daily` : integrale.
      - `job_cluster_cost_daily` : integrale (CLASSIC + SERVERLESS).
      - `pipeline_cost_daily` : integrale (CLASSIC + SERVERLESS).
      - `serverless_cost_daily` : `serverless_surface NOT IN ('JOB',
        'DLT_PIPELINE', 'SQL_WAREHOUSE')` (ces trois surfaces sont deja
        comptees via job/pipeline/warehouse ci-dessus).

    `cost_usd` : somme des 5 tranches ci-dessus, groupee par
    `(cloud_provider, workspace_id, period_start)` — une meme table source
    peut porter plusieurs lignes par jour et par workspace (plusieurs
    clusters/warehouses/jobs/pipelines/objets serverless), d'ou le `SUM` final
    plutot qu'une simple union preservant le detail.

    `lz_id`/`ba_name` : resolus au dernier etat connu du workspace
    (`dbx_workspace_reference_table`, dedup a 1 ligne par `workspace_id` par
    precaution meme si la source est deja a cette grain), puis jointure sur
    `subscription_or_account_id` vers `dim_landing_zone_table` (deja dedup a 1
    ligne par `subscription_or_account_id`, cf. `pipelines.gold_landing_zone
    .view`). `LEFT JOIN` des deux cotes : un workspace sans reference ou sans
    LZ/BA associee garde sa ligne de cout, avec `lz_id`/`ba_name` NULL (cf.
    docstring du module pour le taux de couverture mesure).
    """
    period_filter = lower_bound_predicate("period_start", lower_bound)
    query = f"""
    WITH unioned AS (
        SELECT cloud_provider, workspace_id, period_start, cost_usd
        FROM {cluster_cost_daily_table}
        WHERE cluster_type = 'ALL_PURPOSE'
        {period_filter}
        UNION ALL
        SELECT cloud_provider, workspace_id, period_start, cost_usd
        FROM {warehouse_cost_daily_table}
        WHERE 1 = 1
        {period_filter}
        UNION ALL
        SELECT cloud_provider, workspace_id, period_start, cost_usd
        FROM {job_cluster_cost_daily_table}
        WHERE 1 = 1
        {period_filter}
        UNION ALL
        SELECT cloud_provider, workspace_id, period_start, cost_usd
        FROM {pipeline_cost_daily_table}
        WHERE 1 = 1
        {period_filter}
        UNION ALL
        SELECT cloud_provider, workspace_id, period_start, cost_usd
        FROM {serverless_cost_daily_table}
        WHERE serverless_surface NOT IN ('JOB', 'DLT_PIPELINE', 'SQL_WAREHOUSE')
        {period_filter}
    ),
    totals AS (
        SELECT
            cloud_provider,
            workspace_id,
            period_start,
            SUM(cost_usd) AS cost_usd
        FROM unioned
        GROUP BY cloud_provider, workspace_id, period_start
    ),
    workspace_ref AS (
        SELECT workspace_id, subscription_or_account_id
        FROM {dbx_workspace_reference_table}
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY workspace_id ORDER BY updated_at DESC
        ) = 1
    )
    SELECT
        t.cloud_provider,
        t.workspace_id,
        t.period_start,
        t.cost_usd,
        lz.lz_id,
        lz.business_application_name AS ba_name,
        current_timestamp() AS _generated_at
    FROM totals t
    LEFT JOIN workspace_ref wr ON wr.workspace_id = t.workspace_id
    LEFT JOIN {dim_landing_zone_table} lz
      ON lz.subscription_or_account_id = wr.subscription_or_account_id
    """
    return spark.sql(query)
