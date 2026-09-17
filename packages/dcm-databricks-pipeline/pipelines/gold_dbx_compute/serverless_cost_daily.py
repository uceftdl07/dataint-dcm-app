"""Agregation gold `gold_dbx_compute_serverless_cost_daily` (FinOps serverless).

Cout quotidien de la depense SERVERLESS, par surface d'usage et par objet. C'est
la table qui rend visible une depense que TOUS les rollups bases cluster
ignorent par construction : le serverless n'a ni `cluster_id`, ni
`cluster_source`, ni ligne dans `curated_dbx_compute_clusters`.

TOUTE mesure citee dans ce module vient de la FENETRE DE REFERENCE
2026-08-10..2026-09-09 (31 jours), catalogue `it` / schema
`ba_data_connect_monitoring__d` en dev, prise le 2026-09-10, BI-CLOUD sauf
mention explicite du cloud. Cette precision n'est pas de la ceremonie : les
chiffres du spike melangeaient une fenetre 30 j et un cloud unique, ce qui a
produit deux affirmations fausses (cf.
`specs/025-serverless-compute-page/T001d-baseline-measures.md`). Sur cette
fenetre, la depense serverless vaut 380 638,71 $ (AWS 276 672,18 $,
Azure 103 966,54 $), repartie sur 12 surfaces.

Rollup BILLING-DIRECT (meme mecanique que `pipeline_cost_daily` /
`job_cluster_cost_daily`) : `curated_dbx_billing_usage` x
`curated_dbx_billing_list_prices`, plus deux referentiels de NOM
(`curated_dbx_compute_warehouses`, `curated_dbx_lakeflow_pipelines`). Aucune
resolution de cluster : il n'y en a pas.

ANTI-DOUBLE-COMPTAGE -- cette table agrege LES MEMES lignes de facturation que
`cluster_cost_daily`, `job_cluster_cost_daily`, `pipeline_cost_daily` et
`warehouse_cost_daily`, vues sous un autre axe (la forme de compute au lieu de
l'objet metier). NE JAMAIS la sommer avec elles : le total serait faux, pas
enrichi. Sommer les `serverless_surface` ENTRE ELLES est en revanche legitime et
redonne exactement la depense serverless totale -- le `CASE` de surface
partitionne les lignes (12 valeurs, aucune ligne dans deux surfaces).

Deux niveaux d'agregation, et non un seul : le cout par execution
(`cost_per_run_histogram`, `run_count`) exige un premier `GROUP BY` par
`job_run_id` AVANT le `GROUP BY` du grain, parce que
`sql_helpers.histogram_from_edges_sql` est un agregat de LIGNES -- l'appliquer
directement a la facturation compterait des tranches de facturation, pas des
executions (une execution de 4 min produit plusieurs lignes).

Le cout facture n'est pas que du DBU : 2 268,41 $ sont factures en GB et
250,56 $ en HOUR (surface `NETWORKING`, qui a donc `dbu_quantity = 0` pour
2 518,97 $ de cout), 583,73 $ en DSU (`LAKEBASE`), 377 536,01 $ en DBU.
`cost_usd` couvre toutes les unites, `dbu_quantity` seulement les DBU : leur
rapport n'est PAS un prix unitaire.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.specs import TOP_COST_RANK_THRESHOLD
from pipelines.gold_dbx_compute.sql_helpers import (
    HISTOGRAM_COST_PER_RUN_EDGES,
    SERVERLESS_OBJECT_ID_SENTINEL,
    SERVERLESS_SURFACE_JOB,
    histogram_from_edges_sql,
    identity_principal_expr,
    identity_source_expr,
    lower_bound_predicate,
    serverless_object_id_expr,
    serverless_scope_predicate,
    serverless_surface_case_expr,
)

if TYPE_CHECKING:
    from datetime import date

    from pyspark.sql import DataFrame, SparkSession

# Surfaces dont la cle d'objet est un `warehouse_id` / un `pipeline_id`, donc
# resolvables dans un referentiel curated. Le gating par surface n'est pas
# cosmetique : sans lui, un `notebook_id` egal par hasard a un `warehouse_id`
# nommerait un notebook avec le nom d'un warehouse. Mesure sur la fenetre de
# reference : 0 ligne de grain nommee a la fois par les DEUX referentiels, donc
# 0 collision aujourd'hui -- le gating est preventif, et il reduit au passage le
# volume joint.
_WAREHOUSE_NAME_SURFACES = ("SQL_WAREHOUSE",)
_PIPELINE_NAME_SURFACES = ("DLT_PIPELINE", "MV_ST_REFRESH", "LAKEBASE")


def _surface_list_sql(surfaces: tuple[str, ...]) -> str:
    """Formate un tuple de surfaces en liste SQL litterale (`'A', 'B'`)."""
    return ", ".join(f"'{surface}'" for surface in surfaces)


def build_serverless_cost_daily(
    spark: SparkSession,
    *,
    billing_usage_table: str,
    billing_list_prices_table: str,
    warehouses_table: str,
    lakeflow_pipelines_table: str,
    lower_bound: date | None,
    top_cost_rank_threshold: int = TOP_COST_RANK_THRESHOLD,
) -> DataFrame:
    """Construit `gold_dbx_compute_serverless_cost_daily`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        billing_usage_table: nom qualifie (`catalog.schema.table`) de
            `curated_dbx_billing_usage` (source de facturation directe).
        billing_list_prices_table: nom qualifie de
            `curated_dbx_billing_list_prices` (prix effectif).
        warehouses_table: nom qualifie de `curated_dbx_compute_warehouses`
            (referentiel de NOM des warehouses, surface `SQL_WAREHOUSE`).
        lakeflow_pipelines_table: nom qualifie de
            `curated_dbx_lakeflow_pipelines` (referentiel de NOM des pipelines,
            surfaces `DLT_PIPELINE` / `MV_ST_REFRESH` / `LAKEBASE`).
        lower_bound: borne basse incluse de `period_start` pour la lecture
            incrementale ; `None` pour recalculer l'historique complet.
        top_cost_rank_threshold: nombre d'objets consideres "top cost" par jour
            ET par surface (defaut `TOP_COST_RANK_THRESHOLD`).

    Returns:
        Le DataFrame `gold_dbx_compute_serverless_cost_daily` resultant.

    Grain : `(cloud_provider, workspace_id, serverless_surface, object_id,
    period_start)`. 109 748 lignes sur la fenetre de reference.

    `workspace_id` RESTE dans le grain alors que la plupart des ids Databricks
    sont globalement uniques : `AI_ENDPOINT` fait exception (932 `endpoint_id`
    distincts pour 939 couples `(workspace_id, endpoint_id)` sur l'historique
    COMPLET), et sans `workspace_id` ces 7 endpoints homonymes fusionneraient
    leur cout.

    AUCUNE des deux cles de merge derivees n'est NULL, et ce n'est pas un detail
    de style : `pipelines.common.writers.merge_into_table` fusionne sur `<=>`
    null-safe, donc une cle NULL ne leve rien -- elle fond silencieusement tout
    un workspace en UNE ligne corrompue. `serverless_surface` est garantie par
    la branche `ELSE 'OTHER'` du `CASE`, `object_id` par la sentinelle
    `_NO_OBJECT` (33 425,57 $, 8,78 % de la depense de la fenetre de reference,
    bi-cloud ; 9,50 % sur AWS seul, 6,87 % sur Azure seul). Corollaire
    utile : le self-join J-1 peut s'egaliser sur `object_id` avec un `=`
    ordinaire, sans perdre les lignes sans objet.

    Champs et formule de calcul :
      - `serverless_surface` : usage derriere la depense (12 valeurs, jamais
        NULL), cf. `sql_helpers.serverless_surface_case_expr` -- y compris le
        controle a rejouer sur `OTHER`.
      - `object_id` / `has_object_key` : objet factureur au sein de la surface,
        ou la sentinelle `_NO_OBJECT` quand la surface n'a pas d'objet listable
        (grain workspace). `has_object_key` = faux sur la sentinelle : c'est le
        filtre a utiliser cote IHM plutot qu'une comparaison a la chaine.
      - `object_name` : nom de l'objet, cascade a 4 niveaux (jamais NULL).
        Nom NATIF de la facturation (`job_name`, `notebook_path`, `app_name`,
        `endpoint_name`, `ai_gateway.endpoint_name`) A DEFAUT le referentiel
        warehouse, A DEFAUT le referentiel pipeline, A DEFAUT l'`object_id`
        lui-meme. Les deux replis referentiels ne sont pas du luxe -- part du
        cout de la surface nommee NATIVEMENT : `JOB` et `APP` 100 %,
        `AI_ENDPOINT` 99,2 %, `NOTEBOOK` 97,7 %, mais `SQL_WAREHOUSE` 0 %
        (165 457,41 $, la plus grosse surface), `DLT_PIPELINE` 0 %,
        `MV_ST_REFRESH` 0 %, `LAKEBASE` 0 %. Avec les referentiels :
        `SQL_WAREHOUSE` 99,93 %, `DLT_PIPELINE` 100 %, `MV_ST_REFRESH` 98,31 %,
        `LAKEBASE` 3,08 % (ses `endpoint_id` ne sont pas des pipelines, le repli
        n'y rattrape que les rares lignes portant un `dlt_pipeline_id`).
        `change_time < period_start + 1 jour` (etat connu a un instant
        quelconque de la journee, meme piege que `cluster_name` dans
        `cluster_cost_daily`).
      - `billing_origin_product` : produit(s) brut(s) de la facturation, pour
        l'audit. Il n'est PAS fonctionnellement determine par le grain -- une
        surface regroupe plusieurs produits (`AI_ENDPOINT` en couvre 6,
        `PLATFORM_AUTO` 4) et le meme objet peut en facturer plusieurs le meme
        jour : 1 148 lignes sur 109 748 (`PLATFORM_AUTO` 840 lignes /
        4 353,11 $, `AI_ENDPOINT` 308 / 1 132,03 $). D'ou la liste TRIEE ET
        DEDUPLIQUEE jointe par `+` (`MODEL_SERVING+VECTOR_SEARCH`) plutot qu'un
        `MAX()` : sur 98,95 % des lignes la valeur est le produit unique et un
        filtre d'egalite marche, sur le reste la multiplicite est VISIBLE au lieu
        d'etre tronquee au hasard.
      - `performance_target` : cible de performance serverless, renseignee par
        Databricks pour les seules surfaces `JOB` et `DLT_PIPELINE` (100 % de
        leur cout, 2 valeurs distinctes : `STANDARD` et
        `PERFORMANCE_OPTIMIZED`) et NULL sur les 10 autres : un NULL ici veut
        dire "sans objet pour cette surface", pas "non renseigne". `MIXED` quand
        une meme ligne de grain porte deux cibles (28 lignes sur 109 748, dont
        19 en `JOB` et 9 en `DLT_PIPELINE`) : melange visible plutot que valeur
        choisie au hasard.
      - `budget_policy_id` : politique de budget attribuee, `MAX()` quand la
        ligne de grain en porte plusieurs (68 lignes sur 109 748). C'est bien
        `usage_metadata.budget_policy_id` et NON `usage_policy_id`, et pas parce
        que l'un serait l'alias de l'autre : sur l'historique COMPLET
        (33 879 602 lignes), `budget_policy_id` est un SUR-ENSEMBLE STRICT --
        188 744 lignes le portent avec `usage_policy_id` NULL (toutes entre
        2025-02-10 et 2025-09-22), 0 ligne porte l'inverse, et 0 ligne ou les
        deux sont renseignes ne les voit differer. `usage_policy_id` est la
        colonne RECENTE : la retenir perdrait SILENCIEUSEMENT l'attribution de
        policy de ces 188 744 lignes.
      - `identity_principal` / `identity_source` : responsable et champ d'ou il
        vient, cf. `sql_helpers.identity_principal_expr`. Les deux sont pris sur
        la MEME ligne source (`max_by`) : les calculer independamment les
        desynchroniserait sur les 2 405 lignes de grain (sur 109 748) qui portent
        plusieurs identites.
      - `has_custom_tags` : au moins un tag utilisateur sur au moins une ligne du
        jour (60,3 % du cout de la fenetre de reference ; de 12,0 % sur
        `NETWORKING` a 100 % sur `GENIE`). Jamais NULL (`custom_tags` absent =
        faux).
      - `dbu_quantity` : `SUM(usage_quantity)` restreint aux lignes
        `usage_unit = 'DBU'`. ATTENTION, cette table est le seul rollup ou des
        DBU peuvent etre GRATUITS : le SKU `GENIE_FREE_USAGE` n'a AUCUNE ligne de
        prix (66 688 lignes, 102 105 DBU, 0,00 $ sur la fenetre de reference).
        C'est le SEUL SKU du perimetre dans ce cas -- verifie exhaustivement, la
        jointure de prix ne rate rien d'autre -- et il explique a lui seul le
        rapport `dbu_quantity` / `cost_usd` aberrant de la surface `GENIE`
        (321 124 DBU pour 18 397,47 $). Tous les autres sont prices, le
        `COALESCE(effective_price, 0)` ne masque donc pas une jointure ratee
        ailleurs. Controle : `SUM(usage_quantity)` par SKU sans ligne de prix.
      - `cost_usd` : `SUM(usage_quantity x effective_price)`, prix joint sur la
        fenetre `price_start_time <= usage_date < price_end_time`.
      - `cost_usd_prev_day` / `cost_delta_pct` : self-join EXACT sur J-1 (jamais
        un `LAG`), egalise sur `serverless_surface` ET `object_id`. Sans cette
        egalisation, deux lignes de MEME cle de merge ne differant que par
        `cost_usd_prev_day` seraient produites, et rien ne leverait d'erreur :
        `merge_into_table` applique `dropDuplicates(merge_keys)` et en garderait
        une ARBITRAIREMENT. La lecture facturation inclut 1 jour tampon avant
        `lower_bound` pour que ce self-join voie J-1 au bord de la fenetre ; ce
        jour tampon est exclu de la sortie.
      - `run_count` : nombre d'executions du jour, `NULL` (et JAMAIS 0) hors
        surface `JOB` -- seule surface ou `usage_metadata.job_run_id` existe.
        0 signifierait "aucune execution", ce qui est faux : la metrique n'est
        pas definie pour un warehouse ou un endpoint. Sur la fenetre de
        reference, 0,00 $ de la surface `JOB` est facture sans `job_run_id` : la
        restriction ne perd donc aucun cout. ATTENTION, c'est un compte de
        RUN-JOURS (162 123 sur la fenetre) : une execution a cheval sur minuit
        compte pour 2 -- 522 executions sont dans ce cas (339 AWS, 183 Azure),
        soit 0,32 % des 161 550 executions.
      - `cost_per_run_histogram` : distribution du cout par execution
        (`array<bigint>`, 19 buckets, cf.
        `sql_helpers.HISTOGRAM_COST_PER_RUN_EDGES`), NULL hors surface `JOB`
        comme `run_count`. Materialisee parce qu'un percentile quotidien n'est
        ni sommable ni moyennable : `serverless_cost_rolling` fusionne ces
        histogrammes puis en recalcule les percentiles.
      - `cost_rank` / `is_top_cost` : classement par cout du jour AU SEIN de
        chaque surface (partition `(period_start, serverless_surface)`) : l'IHM
        affiche ce rang sur une liste filtree par surface, un rang toutes
        surfaces confondues y commencerait a 40. Douze lignes peuvent donc
        porter `cost_rank = 1` le meme jour, une par surface. `RANK()` (pas
        `ROW_NUMBER()`) : en cas d'ex-aequo a la frontiere du seuil, plus de
        `top_cost_rank_threshold` objets peuvent etre marques le meme jour
        (comportement voulu, pas un bug).
    """
    # 1 jour tampon avant `lower_bound` : sans lui, le self-join sur
    # `period_start - 1 jour` (cf. `with_prev_day`) ne verrait pas J-1 au bord de
    # la fenetre incrementale et ecraserait a tort une valeur deja en base par
    # NULL. La sortie reste bornee a `lower_bound` (`output_period_filter`).
    lag_lookback_lower_bound = lower_bound - timedelta(days=1) if lower_bound is not None else None
    usage_date_filter = lower_bound_predicate("usage_date", lag_lookback_lower_bound)
    output_period_filter = lower_bound_predicate("period_start", lower_bound)
    cost_per_run_histogram = histogram_from_edges_sql("run_cost_usd", HISTOGRAM_COST_PER_RUN_EDGES)
    query = f"""
    WITH usage_filtered AS (
        SELECT
            cloud_provider,
            workspace_id,
            usage_date AS period_start,
            sku_name,
            usage_unit,
            usage_quantity,
            billing_origin_product,
            usage_metadata.job_run_id AS job_run_id,
            usage_metadata.budget_policy_id AS budget_policy_id,
            product_features.performance_target AS performance_target,
            COALESCE(
                usage_metadata.job_name,
                usage_metadata.notebook_path,
                usage_metadata.app_name,
                usage_metadata.endpoint_name,
                usage_metadata.ai_gateway.endpoint_name
            ) AS object_name_native,
            {identity_principal_expr()} AS identity_principal,
            {identity_source_expr()} AS identity_source,
            COALESCE(size(custom_tags) > 0, false) AS has_custom_tags,
            {serverless_surface_case_expr()} AS serverless_surface,
            usage_metadata
        FROM {billing_usage_table}
        WHERE {serverless_scope_predicate()}
        {usage_date_filter}
    ),
    keyed AS (
        -- CTE distincte de `usage_filtered` : la cle d'objet DEPEND de la
        -- surface (le champ porteur change par surface), elle ne peut donc pas
        -- se calculer dans le meme SELECT que le CASE qui la produit.
        SELECT
            cloud_provider,
            workspace_id,
            period_start,
            sku_name,
            usage_unit,
            usage_quantity,
            billing_origin_product,
            job_run_id,
            budget_policy_id,
            performance_target,
            object_name_native,
            identity_principal,
            identity_source,
            has_custom_tags,
            serverless_surface,
            {serverless_object_id_expr()} AS object_id
        FROM usage_filtered
    ),
    priced AS (
        -- VOLONTAIREMENT NON AGREGEE, contrairement a la CTE homonyme des
        -- builders voisins : le cout par execution (`runs` ci-dessous) est un
        -- second niveau d'agregation qui doit relire les lignes.
        SELECT
            k.cloud_provider,
            k.workspace_id,
            k.serverless_surface,
            k.object_id,
            k.period_start,
            k.usage_unit,
            k.usage_quantity,
            k.billing_origin_product,
            k.job_run_id,
            k.budget_policy_id,
            k.performance_target,
            k.object_name_native,
            k.identity_principal,
            k.identity_source,
            k.has_custom_tags,
            k.usage_quantity * COALESCE(lp.effective_price, 0) AS line_cost_usd
        FROM keyed k
        LEFT JOIN (
            SELECT
                cloud_provider,
                sku_name,
                price_start_time,
                price_end_time,
                pricing.effective_list.default AS effective_price
            FROM {billing_list_prices_table}
        ) lp
          ON lp.cloud_provider = k.cloud_provider
         AND lp.sku_name = k.sku_name
         AND lp.price_start_time <= k.period_start
         AND (lp.price_end_time IS NULL OR k.period_start < lp.price_end_time)
    ),
    grain AS (
        SELECT
            cloud_provider,
            workspace_id,
            serverless_surface,
            object_id,
            period_start,
            SUM(CASE WHEN usage_unit = 'DBU' THEN usage_quantity ELSE 0 END) AS dbu_quantity,
            SUM(line_cost_usd) AS cost_usd,
            MAX(object_name_native) AS object_name_native,
            concat_ws('+', sort_array(collect_set(billing_origin_product)))
                AS billing_origin_product,
            CASE
                WHEN COUNT(DISTINCT performance_target) > 1 THEN 'MIXED'
                ELSE MAX(performance_target)
            END AS performance_target,
            MAX(budget_policy_id) AS budget_policy_id,
            MAX(identity_principal) AS identity_principal,
            CASE
                WHEN MAX(identity_principal) IS NULL THEN 'NONE'
                ELSE max_by(identity_source, identity_principal)
            END AS identity_source,
            MAX(CASE WHEN has_custom_tags THEN 1 ELSE 0 END) = 1 AS has_custom_tags
        FROM priced
        GROUP BY cloud_provider, workspace_id, serverless_surface, object_id, period_start
    ),
    runs AS (
        -- 1er niveau d'agregation du cout par EXECUTION : une execution produit
        -- plusieurs lignes de facturation (tranches horaires, SKU multiples).
        SELECT
            cloud_provider,
            workspace_id,
            serverless_surface,
            object_id,
            period_start,
            job_run_id,
            SUM(line_cost_usd) AS run_cost_usd
        FROM priced
        WHERE serverless_surface = '{SERVERLESS_SURFACE_JOB}'
          AND job_run_id IS NOT NULL
        GROUP BY
            cloud_provider, workspace_id, serverless_surface, object_id, period_start, job_run_id
    ),
    runs_agg AS (
        -- 2e niveau : `COUNT(*)` sur `runs` EST le `COUNT(DISTINCT job_run_id)`
        -- de la facturation (une ligne par run et par jour). La restriction de
        -- `runs` a la surface JOB est ce qui rend `run_count` NULL (jamais 0)
        -- ailleurs, via le LEFT JOIN de `enriched`.
        SELECT
            cloud_provider,
            workspace_id,
            serverless_surface,
            object_id,
            period_start,
            COUNT(*) AS run_count,
            {cost_per_run_histogram} AS cost_per_run_histogram
        FROM runs
        GROUP BY cloud_provider, workspace_id, serverless_surface, object_id, period_start
    ),
    warehouses_as_of AS (
        SELECT
            g.cloud_provider,
            g.workspace_id,
            g.serverless_surface,
            g.object_id,
            g.period_start,
            w.warehouse_name
        FROM grain g
        LEFT JOIN {warehouses_table} w
          ON w.cloud_provider = g.cloud_provider
         AND w.workspace_id = g.workspace_id
         AND w.warehouse_id = g.object_id
         AND g.serverless_surface IN ({_surface_list_sql(_WAREHOUSE_NAME_SURFACES)})
         AND w.change_time < g.period_start + INTERVAL 1 DAY
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY g.cloud_provider, g.workspace_id, g.serverless_surface,
                         g.object_id, g.period_start
            ORDER BY w.change_time DESC
        ) = 1
    ),
    pipelines_as_of AS (
        SELECT
            g.cloud_provider,
            g.workspace_id,
            g.serverless_surface,
            g.object_id,
            g.period_start,
            pl.name AS pipeline_name
        FROM grain g
        LEFT JOIN {lakeflow_pipelines_table} pl
          ON pl.cloud_provider = g.cloud_provider
         AND pl.workspace_id = g.workspace_id
         AND pl.pipeline_id = g.object_id
         AND g.serverless_surface IN ({_surface_list_sql(_PIPELINE_NAME_SURFACES)})
         AND pl.change_time < g.period_start + INTERVAL 1 DAY
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY g.cloud_provider, g.workspace_id, g.serverless_surface,
                         g.object_id, g.period_start
            ORDER BY pl.change_time DESC
        ) = 1
    ),
    enriched AS (
        SELECT
            g.cloud_provider,
            g.workspace_id,
            g.serverless_surface,
            g.object_id,
            g.period_start,
            COALESCE(
                g.object_name_native, wa.warehouse_name, pa.pipeline_name, g.object_id
            ) AS object_name,
            g.billing_origin_product,
            g.performance_target,
            g.budget_policy_id,
            g.identity_principal,
            g.identity_source,
            g.has_custom_tags,
            g.object_id <> '{SERVERLESS_OBJECT_ID_SENTINEL}' AS has_object_key,
            g.dbu_quantity,
            g.cost_usd,
            ra.run_count,
            ra.cost_per_run_histogram
        FROM grain g
        LEFT JOIN warehouses_as_of wa
          ON wa.cloud_provider = g.cloud_provider
         AND wa.workspace_id = g.workspace_id
         AND wa.serverless_surface = g.serverless_surface
         AND wa.object_id = g.object_id
         AND wa.period_start = g.period_start
        LEFT JOIN pipelines_as_of pa
          ON pa.cloud_provider = g.cloud_provider
         AND pa.workspace_id = g.workspace_id
         AND pa.serverless_surface = g.serverless_surface
         AND pa.object_id = g.object_id
         AND pa.period_start = g.period_start
        LEFT JOIN runs_agg ra
          ON ra.cloud_provider = g.cloud_provider
         AND ra.workspace_id = g.workspace_id
         AND ra.serverless_surface = g.serverless_surface
         AND ra.object_id = g.object_id
         AND ra.period_start = g.period_start
    ),
    with_prev_day AS (
        -- Self-join EXACT sur J-1, egalise sur les DEUX cles derivees. Les
        -- egalites `=` ordinaires suffisent : ni `serverless_surface` ni
        -- `object_id` ne peut etre NULL (branche ELSE et sentinelle).
        SELECT
            e.*,
            prev.cost_usd AS cost_usd_prev_day
        FROM enriched e
        LEFT JOIN enriched prev
          ON prev.cloud_provider = e.cloud_provider
         AND prev.workspace_id = e.workspace_id
         AND prev.serverless_surface = e.serverless_surface
         AND prev.object_id = e.object_id
         AND prev.period_start = e.period_start - INTERVAL 1 DAY
    )
    SELECT
        cloud_provider,
        workspace_id,
        serverless_surface,
        object_id,
        period_start,
        object_name,
        billing_origin_product,
        performance_target,
        budget_policy_id,
        identity_principal,
        identity_source,
        has_custom_tags,
        has_object_key,
        dbu_quantity,
        cost_usd,
        cost_usd_prev_day,
        (cost_usd - cost_usd_prev_day) / NULLIF(cost_usd_prev_day, 0) * 100 AS cost_delta_pct,
        run_count,
        cost_per_run_histogram,
        RANK() OVER (
            PARTITION BY period_start, serverless_surface ORDER BY cost_usd DESC
        ) AS cost_rank,
        RANK() OVER (PARTITION BY period_start, serverless_surface ORDER BY cost_usd DESC)
            <= {top_cost_rank_threshold} AS is_top_cost,
        current_timestamp() AS _generated_at
    FROM with_prev_day
    WHERE 1 = 1
    {output_period_filter}
    """
    return spark.sql(query)
