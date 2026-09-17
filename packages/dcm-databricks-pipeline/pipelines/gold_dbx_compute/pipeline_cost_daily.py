"""Agregation gold `gold_dbx_compute_pipeline_cost_daily` (FinOps pipelines DLT).

Cout quotidien par pipeline Lakeflow/DLT plutot que par cluster ephemere. Les
clusters `cluster_type = 'PIPELINE'` (et `PIPELINE_MAINTENANCE`) sont recrees a
chaque execution (`cluster_id`/nom changent a chaque run) : `dlt_pipeline_id`
(stable dans le temps) est la seule cle de regroupement viable pour suivre le
cout d'un pipeline au fil de ses executions.

Ce rollup est BILLING-DIRECT (comme le rollup job depuis T001b, passe au meme
mecanisme pour la meme raison) : `usage_metadata.dlt_pipeline_id` est porte
directement par chaque ligne de facturation d'un pipeline, y compris ses
lignes de maintenance
(`PIPELINE_MAINTENANCE`) -- mesure en dev (2026-09-09, `system.billing.usage`) :
toute ligne de maintenance porte `dlt_pipeline_id` (aucune ligne
`dlt_pipeline_id NULL / dlt_maintenance_id NOT NULL`). Aucune resolution
`cluster_id -> dlt_pipeline_id` n'est donc necessaire, et le cout de maintenance
est capture nativement, rattache au pipeline parent.

Le prix de ce billing-direct est qu'il faut delimiter la population SOI-MEME :
`usage_metadata.dlt_pipeline_id` n'est pas reserve aux pipelines DLT. Mesure dev
du 2026-09-10 (historique complet) : 10 972 ids non-DLT pour 37 100,58 $ le
portaient, dont 10 499 requetes `SQL` -- et 10 435 d'entre elles ont une ligne
dans `curated_dbx_lakeflow_pipelines`, donc apparaissaient avec un NOM de
pipeline dans la table gold, indistinguables d'un vrai pipeline. D'ou le second
predicat `billing_origin_product IN ('DLT')` (T001c) ; les volumes par produit et
l'arbitrage `LAKEFLOW_CONNECT` sont dans `sql_helpers`.

Ce rollup billing-direct ne portait aucun discriminant de compute : il melangeait
DLT classique et DLT serverless sans le dire, alors que le serverless est 97 % de
la population facturee en dev. D'ou la colonne `compute_kind` (T008), portee dans
le GRAIN et pas seulement en attribut -- 2 pipelines sur 2 972 (fenetre 30 j, dev)
facturent les deux formes, et hors du grain leur cout resterait melange.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.grain_resolution import (
    pipeline_name_coalesce_sql,
    pipeline_name_cte_sql,
    pipeline_name_join_sql,
)
from pipelines.gold_dbx_compute.specs import TOP_COST_RANK_THRESHOLD
from pipelines.gold_dbx_compute.sql_helpers import (
    BILLING_PRODUCTS_DLT_PIPELINE,
    billing_origin_product_predicate,
    compute_kind_case_expr,
    lower_bound_predicate,
)

if TYPE_CHECKING:
    from datetime import date

    from pyspark.sql import DataFrame, SparkSession


def build_pipeline_cost_daily(
    spark: SparkSession,
    *,
    billing_usage_table: str,
    billing_list_prices_table: str,
    lakeflow_pipelines_table: str,
    lower_bound: date | None,
    top_cost_rank_threshold: int = TOP_COST_RANK_THRESHOLD,
) -> DataFrame:
    """Construit `gold_dbx_compute_pipeline_cost_daily`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        billing_usage_table: nom qualifie (`catalog.schema.table`) de
            `curated_dbx_billing_usage` (source de facturation directe).
        billing_list_prices_table: nom qualifie de
            `curated_dbx_billing_list_prices` (prix effectif).
        lakeflow_pipelines_table: nom qualifie de
            `curated_dbx_lakeflow_pipelines` (dernier etat connu du pipeline,
            pour `pipeline_name` -- uniquement les pipelines ayant une
            DEFINITION persistee).
        lower_bound: borne basse incluse de `period_start` pour la lecture
            incrementale ; `None` pour recalculer l'historique complet.
        top_cost_rank_threshold: nombre de pipelines consideres "top cost" par
            jour (defaut `TOP_COST_RANK_THRESHOLD`), utilise pour `is_top_cost`.

    Returns:
        Le DataFrame `gold_dbx_compute_pipeline_cost_daily` resultant.

    Grain : `(cloud_provider, workspace_id, dlt_pipeline_id, compute_kind,
    period_start)`.
    Source : `curated_dbx_billing_usage` (lignes rattachees a un pipeline DLT,
    filtrees `usage_metadata.dlt_pipeline_id IS NOT NULL AND
    billing_origin_product IN ('DLT')`, agregees par jour) +
    `curated_dbx_billing_list_prices` (prix effectif) + dernier etat connu du
    pipeline (`curated_dbx_lakeflow_pipelines`, pour `pipeline_name`).

    Les DEUX predicats sont necessaires : `dlt_pipeline_id` est aussi renseigne
    par des produits qui ne sont pas des pipelines DLT (des requetes `SQL`
    surtout), cf. `sql_helpers.BILLING_PRODUCTS_DLT_PIPELINE`. Cette table ne
    couvre donc PAS tout ce qui porte un `dlt_pipeline_id` : c'est delibere, et
    l'arbitrage `LAKEFLOW_CONNECT` (vrais pipelines d'ingestion manages, exclus)
    est documente avec la constante.

    NE PAS sommer cette table avec `gold_dbx_compute_cluster_cost_daily`
    (`ALL_PURPOSE`) ni avec `gold_dbx_compute_job_cluster_cost_daily` : les
    trois agregent des sous-ensembles DISJOINTS des memes lignes de
    facturation (par `cluster_type` / `dlt_pipeline_id` / `job_id`), pas des
    sources de cout independantes. En revanche sommer les deux `compute_kind`
    DE CETTE table est legitime et redonne exactement le cout DLT total : les
    deux formes partitionnent les memes lignes de facturation.

    Cles de merge `dlt_pipeline_id` et `compute_kind` JAMAIS NULL : le filtre
    `usage_metadata.dlt_pipeline_id IS NOT NULL` de `usage_filtered` garantit la
    premiere, le `CASE` binaire de `compute_kind_case_expr` (branche `ELSE`) la
    seconde. Une cle de merge NULL fusionnerait toutes ces lignes en une
    seule ligne corrompue via le `<=>` null-safe de
    `pipelines.common.writers.merge_into_table`.

    Cout de MAINTENANCE : les lignes `PIPELINE_MAINTENANCE` de la facturation
    portent le meme `usage_metadata.dlt_pipeline_id` que le pipeline parent
    (mesure en dev, cf. docstring du module) : leur cout est donc capture
    nativement par le `GROUP BY dlt_pipeline_id`, sans cas special ni
    classification supplementaire.

    Champs et formule de calcul :
      - `compute_kind` : `CLASSIC` (le pipeline a tourne sur des clusters DLT,
        `usage_metadata.cluster_id` renseigne) ou `SERVERLESS` (aucun cluster
        derriere la ligne facturee), jamais NULL. Discriminant EXACT, pas une
        heuristique : cf. `sql_helpers.compute_kind_case_expr`. Un pipeline qui
        a migre (ou qui alterne) produit DEUX lignes le meme jour, une par
        forme -- c'est l'objet du grain.
      - `pipeline_name` : nom du pipeline au dernier etat connu (`change_time <
        period_start + 1 jour` : etat connu a un instant quelconque de
        `period_start`, pas seulement avant minuit - meme piege que
        `cluster_name` dans `cluster_cost_daily`), A DEFAUT le `dlt_pipeline_id`
        lui-meme (`COALESCE`) : un pipeline dont aucune definition n'est
        encore ingeree dans `curated_dbx_lakeflow_pipelines` (retard de
        watermark, run soumis sans definition persistee) reste identifiable
        par son id plutot que d'apparaitre sans nom.
      - `dbu_quantity` : volume de DBU consommes par le pipeline ce jour-la.
        Formule : `SUM(usage_quantity)` restreint aux lignes `usage_unit =
        'DBU'`.
      - `cost_usd` : cout total en dollars du pipeline ce jour-la. Formule :
        `SUM(usage_quantity * effective_price)`, ou `effective_price` vient de
        `curated_dbx_billing_list_prices` joint sur la fenetre
        `price_start_time <= usage_date < price_end_time`.
      - `cost_usd_prev_day`/`cost_delta_pct` : memes formules que
        `cluster_cost_daily`, au grain pipeline (self-join exact sur J-1,
        jamais un `LAG`). Le self-join est egalise sur `compute_kind` : sans
        cela un pipeline mixte verrait sa ligne CLASSIC de J s'apparier aussi a
        sa ligne SERVERLESS de J-1, produisant DEUX lignes de meme cle de merge
        ne differant que par `cost_usd_prev_day`. Rien ne leverait d'erreur :
        `merge_into_table` applique `dropDuplicates(merge_keys)` avant le MERGE
        et en garderait une ARBITRAIREMENT, donc un `cost_delta_pct` calcule un
        run sur deux contre le cout de l'autre forme de compute. La lecture
        curated inclut 1 jour tampon avant `lower_bound` pour que ce self-join
        voie J-1 au bord de la fenetre incrementale ; ce jour tampon est exclu
        de la sortie (`period_start >= lower_bound`).
      - `cost_rank`/`is_top_cost` : classement des pipelines par cout du jour,
        AU SEIN de chaque `compute_kind` (partition `(period_start,
        compute_kind)`) : l'IHM affiche ce rang sur une liste filtree
        `CLASSIC`, un rang toutes formes confondues s'y ouvrirait sur "40, 57,
        61...". Deux lignes peuvent donc porter `cost_rank = 1` le meme jour,
        une par forme. `RANK()` (pas `ROW_NUMBER()`) : en cas d'ex-aequo sur
        `cost_usd` a la frontiere du seuil, `is_top_cost` peut marquer plus de
        `top_cost_rank_threshold` pipelines le meme jour - comportement
        intentionnel ("au moins les N plus chers, ex-aequo inclus"), pas un
        bug.
    """
    # 1 jour tampon avant `lower_bound` : sans lui, le self-join sur
    # `period_start - 1 jour` (cf. `with_prev_day` ci-dessous) ne verrait pas
    # J-1 au bord de la fenetre incrementale et ecraserait a tort une valeur
    # deja en base par NULL. Jamais reecrit : le filtre de sortie reste sur
    # `period_start >= lower_bound` (`output_period_filter`).
    lag_lookback_lower_bound = lower_bound - timedelta(days=1) if lower_bound is not None else None
    usage_date_filter = lower_bound_predicate("usage_date", lag_lookback_lower_bound)
    output_period_filter = lower_bound_predicate("period_start", lower_bound)
    # Resolution du nom partagee avec `pipeline_efficiency_daily` (cf.
    # `grain_resolution`) : cout et efficacite doivent porter le meme
    # `pipeline_name` pour un `dlt_pipeline_id` donne.
    pipelines_as_of_cte = pipeline_name_cte_sql(
        grain_cte="priced",
        lakeflow_pipelines_table=lakeflow_pipelines_table,
    )
    # Discriminant DLT classique / serverless, derive de la ligne de facturation
    # elle-meme : ce rollup ne resout aucun cluster (cf. docstring du module).
    compute_kind_expr = compute_kind_case_expr("usage_metadata.cluster_id")
    # `dlt_pipeline_id IS NOT NULL` ne suffit PAS a delimiter la population : ce
    # champ est aussi renseigne par d'autres produits factures (cf.
    # `sql_helpers.BILLING_PRODUCTS_DLT_PIPELINE` pour les volumes mesures et
    # l'arbitrage `LAKEFLOW_CONNECT`).
    product_predicate = billing_origin_product_predicate(BILLING_PRODUCTS_DLT_PIPELINE)
    query = f"""
    WITH usage_filtered AS (
        SELECT
            cloud_provider,
            workspace_id,
            usage_metadata.dlt_pipeline_id AS dlt_pipeline_id,
            {compute_kind_expr} AS compute_kind,
            usage_date AS period_start,
            sku_name,
            usage_unit,
            usage_quantity
        FROM {billing_usage_table}
        WHERE usage_metadata.dlt_pipeline_id IS NOT NULL
          AND {product_predicate}
        {usage_date_filter}
    ),
    priced AS (
        SELECT
            u.cloud_provider,
            u.workspace_id,
            u.dlt_pipeline_id,
            u.compute_kind,
            u.period_start,
            SUM(CASE WHEN u.usage_unit = 'DBU' THEN u.usage_quantity ELSE 0 END) AS dbu_quantity,
            SUM(u.usage_quantity * COALESCE(lp.effective_price, 0)) AS cost_usd
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
        GROUP BY
            u.cloud_provider, u.workspace_id, u.dlt_pipeline_id, u.compute_kind, u.period_start
    ),
    {pipelines_as_of_cte},
    enriched AS (
        SELECT
            pr.cloud_provider,
            pr.workspace_id,
            pr.dlt_pipeline_id,
            pr.compute_kind,
            pr.period_start,
            {pipeline_name_coalesce_sql("pr")},
            pr.dbu_quantity,
            pr.cost_usd
        FROM priced pr
        {pipeline_name_join_sql("pr")}
    ),
    with_prev_day AS (
        SELECT
            e.*,
            prev.cost_usd AS cost_usd_prev_day
        FROM enriched e
        LEFT JOIN enriched prev
          ON prev.cloud_provider = e.cloud_provider
         AND prev.workspace_id = e.workspace_id
         AND prev.dlt_pipeline_id = e.dlt_pipeline_id
         AND prev.compute_kind = e.compute_kind
         AND prev.period_start = e.period_start - INTERVAL 1 DAY
    )
    SELECT
        cloud_provider,
        workspace_id,
        dlt_pipeline_id,
        compute_kind,
        pipeline_name,
        period_start,
        dbu_quantity,
        cost_usd,
        cost_usd_prev_day,
        (cost_usd - cost_usd_prev_day) / NULLIF(cost_usd_prev_day, 0) * 100 AS cost_delta_pct,
        RANK() OVER (
            PARTITION BY period_start, compute_kind ORDER BY cost_usd DESC
        ) AS cost_rank,
        RANK() OVER (PARTITION BY period_start, compute_kind ORDER BY cost_usd DESC)
            <= {top_cost_rank_threshold} AS is_top_cost,
        current_timestamp() AS _generated_at
    FROM with_prev_day
    WHERE 1 = 1
    {output_period_filter}
    """
    return spark.sql(query)
