"""Agregation gold `gold_dbx_compute_cluster_cost_daily` (FinOps clusters).

Cout quotidien par cluster Databricks : DBU consommes, cout USD, evolution
vs le jour precedent et classement des clusters les plus couteux du jour.
Alimente le suivi FinOps des couts de compute clusters (identification des
clusters a fort cout, tendance jour apres jour).

La population est delimitee par DEUX predicats, pas un :
`usage_metadata.cluster_id IS NOT NULL` **et** `billing_origin_product IN
('JOBS', 'ALL_PURPOSE', 'DLT')` (T001c). Le premier seul faisait entrer le cout
de services manages qui rattachent leur facturation au cluster APPELANT :
791,02 $ sur 97 clusters visibles dans cette table (mesure dev 2026-09-10,
2025-10-28..2026-09-09), du cout d'inference et de fonctions d'IA compte comme
du cout de cluster. Les volumes par produit et la justification de la liste
blanche sont dans `sql_helpers.BILLING_PRODUCTS_CLUSTER_COMPUTE`.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.specs import TOP_COST_RANK_THRESHOLD
from pipelines.gold_dbx_compute.sql_helpers import (
    BILLING_PRODUCTS_CLUSTER_COMPUTE,
    billing_origin_product_predicate,
    cluster_type_case_expr,
    lower_bound_predicate,
)

if TYPE_CHECKING:
    from datetime import date

    from pyspark.sql import DataFrame, SparkSession


def build_cluster_cost_daily(
    spark: SparkSession,
    *,
    billing_usage_table: str,
    billing_list_prices_table: str,
    clusters_table: str,
    lower_bound: date | None,
    top_cost_rank_threshold: int = TOP_COST_RANK_THRESHOLD,
) -> DataFrame:
    """Construit `gold_dbx_compute_cluster_cost_daily`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        billing_usage_table: nom qualifie (`catalog.schema.table`) de
            `curated_dbx_billing_usage`.
        billing_list_prices_table: nom qualifie de
            `curated_dbx_billing_list_prices`.
        clusters_table: nom qualifie de `curated_dbx_compute_clusters`
            (dernier etat connu du cluster).
        lower_bound: borne basse incluse de `period_start` pour la lecture
            incrementale ; `None` pour recalculer l'historique complet.
        top_cost_rank_threshold: nombre de clusters consideres "top cost" par
            jour (defaut `TOP_COST_RANK_THRESHOLD`), utilise pour `is_top_cost`.

    Returns:
        Le DataFrame `gold_dbx_compute_cluster_cost_daily` resultant.

    Grain : `(cloud_provider, workspace_id, cluster_id, period_start)`.
    Source : `curated_dbx_billing_usage` (lignes rattachees a un cluster ET
    facturees par un produit de compute cluster, cf. docstring du module,
    agregees par jour) + `curated_dbx_billing_list_prices` (prix effectif) +
    dernier etat connu du cluster (`curated_dbx_compute_clusters`).

    Champs et formule de calcul :
      - `cluster_name`/`owner`/`cost_center` : identite et attribution du
        cluster, resolues au dernier etat connu (`change_time < period_start
        + 1 jour` : etat connu a un instant quelconque de `period_start`, pas
        seulement avant minuit - `TIMESTAMP <= DATE` cast a minuit exclurait
        a tort les clusters crees le jour meme).
        `owner` = `COALESCE(tags['owner'], owned_by)` : le tag
        explicite prime sur `owned_by`, qui est rempli automatiquement par
        Databricks a la creation (souvent un UUID de service principal ou un
        compte d'automatisation, pas une attribution metier deliberee).
      - `cluster_type` : categorie du cluster derivee de `cluster_source`
        (dernier etat connu) via `cluster_type_case_expr` : `ALL_PURPOSE`
        (`UI`/`API`, persistant), `JOB` (ephemere - recree a chaque
        execution) ou `PIPELINE` (DLT/Lakeflow). Databricks n'expose cette
        distinction sous aucun champ dedie ; permet de filtrer les clusters
        JOB (dont `cluster_id` change a chaque run, cf.
        `gold_dbx_compute.job_cluster_cost_daily`) plutot que de les melanger
        aux clusters persistants dans les analyses agregees. Les clusters
        sans aucun etat connu dans `curated_dbx_compute_clusters` sont
        exclus de la sortie plutot qu'exposes sans identite
        (`cluster_name`/`owner`/`cost_center`) ni type fiables.
      - `sku_group` : categorie de facturation du cluster ce jour-la.
        Formule : `'serverless'` si `sku_name LIKE '%SERVERLESS%'`, `'photon'`
        si `LIKE '%PHOTON%'`, sinon `'classic'`.
        `'serverless'` N'EST PLUS PRODUCTIBLE depuis T001c et c'est normal : un
        cluster est par definition du compute provisionne, et les seules lignes
        `%SERVERLESS%` portant un `cluster_id` venaient de `AI_FUNCTIONS` /
        `MODEL_SERVING` (mesure dev 2026-09-10, historique complet depuis
        2023-08-26 : zero ligne `%SERVERLESS%` dans les 3 produits retenus). La
        branche est CONSERVEE comme temoin : sa reapparition signalerait que
        Databricks a change sa facturation (un produit de compute cluster
        facture sur un SKU serverless), pas un bug de ce builder. `'photon'`
        reste produit normalement (3 a 4 SKU par produit retenu). Le cout du
        compute VRAIMENT serverless (jobs et pipelines sans cluster) n'a jamais
        ete dans cette table : il n'a pas de `cluster_id`, il est dans
        `job_cluster_cost_daily` / `pipeline_cost_daily` sous
        `compute_kind = 'SERVERLESS'`.
      - `dbu_quantity` : volume de DBU consommes par le cluster ce jour-la.
        Formule : `SUM(usage_quantity)` restreint aux lignes `usage_unit =
        'DBU'`.
      - `cost_usd` : cout total en dollars du cluster ce jour-la. Formule :
        `SUM(usage_quantity * effective_price)`, ou `effective_price` vient de
        `curated_dbx_billing_list_prices` joint sur la fenetre
        `price_start_time <= usage_date < price_end_time`.
      - `cost_usd_prev_day` : cout du jour calendaire precedent, pour
        comparaison. Formule : self-join exact sur `period_start - 1 jour`
        (jamais un `LAG`, qui sauterait silencieusement les jours sans usage
        et ramenerait le cout d'un jour bien plus ancien qu'hier). La lecture
        curated inclut 1 jour tampon avant `lower_bound` pour que ce self-join
        voie J-1 au bord de la fenetre incrementale ; ce jour tampon est
        exclu de la sortie (`period_start >= lower_bound`).
      - `cost_delta_pct` : variation du cout par rapport a la veille, en
        pourcentage. Formule : `(cost_usd - cost_usd_prev_day) /
        cost_usd_prev_day * 100`.
      - `cost_rank` : position du cluster dans le classement des couts du
        jour (1 = le plus cher), tous clusters confondus (pas de decoupage
        par landing zone : `account_id` issu de `system.billing.usage` est
        l'UUID du compte Databricks, pas l'identifiant cloud natif de
        `dim_landing_zone`. Un mapping `workspace_id -> lz_id` PARTIEL existe
        via `dim_reference_landing_zone_dbx_workspace` + `dim_landing_zone`
        (cf. `gold_dbx_compute.total_cost_daily`), mais n'est pas joint ici).
        Formule : `RANK() OVER (PARTITION BY period_start ORDER BY cost_usd
        DESC)`.
      - `is_top_cost` : vrai si le cluster fait partie des clusters les plus
        couteux du jour. Formule : `cost_rank <= top_cost_rank_threshold`.
    """
    # 1 jour tampon avant `lower_bound` : sans lui, le self-join sur
    # `period_start - 1 jour` (cf. `with_prev_day` ci-dessous) ne verrait pas
    # J-1 au bord de la fenetre incrementale et ecraserait a tort une valeur
    # deja en base par NULL. Jamais reecrit : le filtre de sortie reste sur
    # `period_start >= lower_bound` (`output_period_filter`).
    lag_lookback_lower_bound = lower_bound - timedelta(days=1) if lower_bound is not None else None
    usage_date_filter = lower_bound_predicate("usage_date", lag_lookback_lower_bound)
    output_period_filter = lower_bound_predicate("period_start", lower_bound)
    # `cluster_id IS NOT NULL` ne suffit PAS a delimiter la population : un
    # service manage rattache sa facturation au cluster appelant via ce meme
    # champ (cf. `sql_helpers.BILLING_PRODUCTS_CLUSTER_COMPUTE`). Ce predicat
    # doit rester dans `usage_filtered`, en amont du `GROUP BY` : applique apres
    # agregation il n'ecarterait plus des lignes mais des jours-cluster entiers,
    # dont ceux qui melangent un vrai cout de cluster et un cout etranger.
    product_predicate = billing_origin_product_predicate(BILLING_PRODUCTS_CLUSTER_COMPUTE)
    query = f"""
    WITH usage_filtered AS (
        SELECT
            cloud_provider,
            workspace_id,
            usage_metadata.cluster_id AS cluster_id,
            usage_date AS period_start,
            sku_name,
            usage_unit,
            usage_quantity
        FROM {billing_usage_table}
        WHERE usage_metadata.cluster_id IS NOT NULL
          AND {product_predicate}
        {usage_date_filter}
    ),
    priced AS (
        SELECT
            u.cloud_provider,
            u.workspace_id,
            u.cluster_id,
            u.period_start,
            SUM(CASE WHEN u.usage_unit = 'DBU' THEN u.usage_quantity ELSE 0 END) AS dbu_quantity,
            SUM(u.usage_quantity * COALESCE(lp.effective_price, 0)) AS cost_usd,
            MAX(CASE
                    WHEN u.sku_name LIKE '%SERVERLESS%' THEN 3
                    WHEN u.sku_name LIKE '%PHOTON%' THEN 2
                    ELSE 1
                END) AS sku_priority
        FROM usage_filtered u
        LEFT JOIN (
            SELECT
                cloud_provider,
                sku_name,
                price_start_time,
                price_end_time,
                pricing.effective_list.default AS effective_price
            FROM {billing_list_prices_table}
        ) lp
          ON lp.cloud_provider = u.cloud_provider
         AND lp.sku_name = u.sku_name
         AND lp.price_start_time <= u.period_start
         AND (lp.price_end_time IS NULL OR u.period_start < lp.price_end_time)
        GROUP BY u.cloud_provider, u.workspace_id, u.cluster_id, u.period_start
    ),
    clusters_as_of AS (
        SELECT
            p.cloud_provider,
            p.workspace_id,
            p.cluster_id,
            p.period_start,
            c.cluster_name,
            c.cluster_source,
            c.owned_by,
            c.tags
        FROM priced p
        LEFT JOIN {clusters_table} c
          ON c.cloud_provider = p.cloud_provider
         AND c.workspace_id = p.workspace_id
         AND c.cluster_id = p.cluster_id
         AND c.change_time < p.period_start + INTERVAL 1 DAY
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY p.cloud_provider, p.workspace_id, p.cluster_id, p.period_start
            ORDER BY c.change_time DESC
        ) = 1
    ),
    enriched AS (
        SELECT
            pr.cloud_provider,
            pr.workspace_id,
            pr.cluster_id,
            pr.period_start,
            ca.cluster_name,
            {cluster_type_case_expr("ca.cluster_source")} AS cluster_type,
            COALESCE(ca.tags['owner'], ca.owned_by) AS owner,
            ca.tags['cost_center'] AS cost_center,
            -- Branche `serverless` = temoin, plus atteignable depuis le filtre
            -- produit (cf. docstring `sku_group`). NE PAS la supprimer : c'est
            -- elle qui rendrait visible un changement de facturation Databricks.
            CASE
                WHEN pr.sku_priority = 3 THEN 'serverless'
                WHEN pr.sku_priority = 2 THEN 'photon'
                ELSE 'classic'
            END AS sku_group,
            pr.dbu_quantity,
            pr.cost_usd
        FROM priced pr
        LEFT JOIN clusters_as_of ca
          ON ca.cloud_provider = pr.cloud_provider
         AND ca.workspace_id = pr.workspace_id
         AND ca.cluster_id = pr.cluster_id
         AND ca.period_start = pr.period_start
    ),
    with_prev_day AS (
        SELECT
            e.*,
            prev.cost_usd AS cost_usd_prev_day
        FROM enriched e
        LEFT JOIN enriched prev
          ON prev.cloud_provider = e.cloud_provider
         AND prev.workspace_id = e.workspace_id
         AND prev.cluster_id = e.cluster_id
         AND prev.period_start = e.period_start - INTERVAL 1 DAY
    )
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
        cost_usd,
        cost_usd_prev_day,
        (cost_usd - cost_usd_prev_day) / NULLIF(cost_usd_prev_day, 0) * 100 AS cost_delta_pct,
        RANK() OVER (PARTITION BY period_start ORDER BY cost_usd DESC) AS cost_rank,
        RANK() OVER (PARTITION BY period_start ORDER BY cost_usd DESC)
            <= {top_cost_rank_threshold} AS is_top_cost,
        current_timestamp() AS _generated_at
    FROM with_prev_day
    WHERE cluster_type <> 'OTHER'
    {output_period_filter}
    """
    return spark.sql(query)
