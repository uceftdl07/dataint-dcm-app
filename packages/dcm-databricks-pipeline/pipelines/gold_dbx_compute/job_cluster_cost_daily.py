"""Agregation gold `gold_dbx_compute_job_cluster_cost_daily` (FinOps jobs).

Cout quotidien par job Databricks plutot que par cluster ephemere. Les clusters
`cluster_type = 'JOB'` sont recrees a chaque execution (`cluster_id`/nom
changent a chaque run) : `job_id` (stable dans le temps) est la seule cle de
regroupement viable pour suivre le cout d'un job au fil de ses executions.

Ce rollup a ete un rollup de `gold_dbx_compute_cluster_cost_daily`
(`cluster_type = 'JOB'`) avec un `INNER JOIN` sur
`curated_dbx_lakeflow_job_task_run_timeline` pour resoudre `cluster_id ->
job_id`. Il est desormais BILLING-DIRECT, comme `pipeline_cost_daily` :
`usage_metadata.job_id` est porte par la ligne de facturation elle-meme
(100 % des lignes portent aussi `job_run_id`, mesure en dev le 2026-09-10),
donc aucune resolution par le cluster n'est necessaire.

CE QUE CE CHANGEMENT CORRIGE : le rollup precedent heritait du filtre
`usage_metadata.cluster_id IS NOT NULL` de `cluster_cost_daily`, et un job
SERVERLESS n'a JAMAIS de `cluster_id`. Tout le cout des jobs serverless etait
donc exclu en amont, silencieusement : 56 841 $ AWS + 28 812 $ Azure sur 30
jours (mesure en dev le 2026-09-10, fenetre 2026-08-11..2026-09-09, 3 689 jobs).
Le passage en billing-direct les fait entrer, et `compute_kind` -- dans le GRAIN
et pas en simple attribut -- les distingue du classique : 926 jours-job sur
70 980 facturent les DEUX formes le meme jour (131 jobs sur 8 457 sur la
fenetre), hors du grain leur cout resterait melange.

Le sous-ensemble CLASSIC, lui, est inchange : les 44 234 jours-job de la table
gold existante retrouvent TOUS leur equivalent billing-direct au meme
`(job_id, period_start)`, avec le meme `cluster_count` a 2 lignes pres, et le
meme total (24 431,24 $ vs 24 431,52 $ AWS, 21 750,24 $ vs 21 750,77 $ Azure --
l'ecart est le prix d'un cluster absent de `curated_dbx_compute_clusters`). La
resolution `cluster_id -> job_id` de `job_task_run_timeline` et le `job_id`
porte par la facturation ne se contredisent donc nulle part sur la fenetre
mesuree : la refonte n'est pas un deplacement de cout entre jobs, c'est un
ajout.

Effet de bord favorable : la LIMITE DE COUVERTURE HISTORIQUE de la version
precedente disparait. Elle venait de l'`INNER JOIN` sur
`job_task_run_timeline` (retention source ~1 an, 2026-07-19 en dev) ; la
facturation remonte a 2023-08-26 dans le meme workspace. Un recalcul complet
couvre desormais toute la retention de la facturation.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.grain_resolution import (
    JOB_NAME_COALESCE_SQL,
    job_name_ctes_sql,
    job_name_joins_sql,
)
from pipelines.gold_dbx_compute.specs import TOP_COST_RANK_THRESHOLD
from pipelines.gold_dbx_compute.sql_helpers import (
    compute_kind_case_expr,
    lower_bound_predicate,
)

if TYPE_CHECKING:
    from datetime import date

    from pyspark.sql import DataFrame, SparkSession


def build_job_cluster_cost_daily(
    spark: SparkSession,
    *,
    billing_usage_table: str,
    billing_list_prices_table: str,
    job_run_timeline_table: str,
    lakeflow_jobs_table: str,
    lower_bound: date | None,
    top_cost_rank_threshold: int = TOP_COST_RANK_THRESHOLD,
) -> DataFrame:
    """Construit `gold_dbx_compute_job_cluster_cost_daily`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        billing_usage_table: nom qualifie (`catalog.schema.table`) de
            `curated_dbx_billing_usage` (source de facturation directe).
        billing_list_prices_table: nom qualifie de
            `curated_dbx_billing_list_prices` (prix effectif).
        job_run_timeline_table: nom qualifie de
            `curated_dbx_lakeflow_job_run_timeline` (colonne `run_name`, seul
            nom disponible pour un run SOUMIS, cf. la regle `job_name`).
        lakeflow_jobs_table: nom qualifie de `curated_dbx_lakeflow_jobs`
            (dernier etat connu du job, pour `job_name` -- uniquement les jobs
            ayant une DEFINITION persistee).
        lower_bound: borne basse incluse de `period_start` pour la lecture
            incrementale ; `None` pour recalculer l'historique complet.
        top_cost_rank_threshold: nombre de jobs consideres "top cost" par
            jour ET par forme de compute (defaut `TOP_COST_RANK_THRESHOLD`),
            utilise pour `is_top_cost`.

    Returns:
        Le DataFrame `gold_dbx_compute_job_cluster_cost_daily` resultant.

    Grain : `(cloud_provider, workspace_id, job_id, compute_kind,
    period_start)`.
    Source : `curated_dbx_billing_usage` (lignes rattachees a un job, filtrees
    `usage_metadata.job_id IS NOT NULL`, agregees par jour) +
    `curated_dbx_billing_list_prices` (prix effectif) + dernier etat connu du
    job (`curated_dbx_lakeflow_jobs`, pour `job_name`) +
    `curated_dbx_lakeflow_job_run_timeline` (`run_name`, nom des runs soumis
    sans definition de job).

    NE PAS sommer cette table avec `gold_dbx_compute_cluster_cost_daily`
    (`ALL_PURPOSE`) ni avec `gold_dbx_compute_pipeline_cost_daily` : les trois
    agregent des sous-ensembles DISJOINTS des memes lignes de facturation (par
    `cluster_type` / `job_id` / `dlt_pipeline_id`), pas des sources de cout
    independantes. La disjonction est mesuree, pas supposee : les clusters
    derriere les lignes `job_id NOT NULL` sont a 99,99 % `cluster_source =
    'JOB'` (194 446 / 194 446 lignes AWS, 86 760 / 86 790 Azure, le reste etant
    un cluster absent de `curated_dbx_compute_clusters`), donc le sous-ensemble
    `compute_kind = 'CLASSIC'` de cette table est exactement le sous-ensemble
    `cluster_type = 'JOB'` de `cluster_cost_daily`. En revanche sommer les deux
    `compute_kind` DE CETTE table est legitime et redonne exactement le cout
    job total : les deux formes partitionnent les memes lignes de facturation.

    Cles de merge `job_id` et `compute_kind` JAMAIS NULL : le filtre
    `usage_metadata.job_id IS NOT NULL` de `usage_filtered` garantit la
    premiere, le `CASE` binaire de `compute_kind_case_expr` (branche `ELSE`) la
    seconde. Une cle de merge NULL fusionnerait toutes ces lignes en une seule
    ligne corrompue via le `<=>` null-safe de
    `pipelines.common.writers.merge_into_table`. C'est la meme garantie que
    l'`INNER JOIN` sur `job_clusters` apportait avant, obtenue par un filtre au
    lieu d'une jointure -- et sans son cout de couverture.

    Autres produits que `JOBS` portant `job_id` (mesure dev 2026-09-10, tout
    l'historique -- ils sont CINQ, pas deux) : `AI_FUNCTIONS` (261,17 $, 31
    jobs, depuis 2026-04-10), `DLT` (176,59 $, 370 jobs, mais seulement jusqu'au
    2024-02-12), `PREDICTIVE_OPTIMIZATION` (131,95 $, 976 jobs),
    `LAKEHOUSE_MONITORING` (80,22 $, 12 jobs) et `MODEL_SERVING` (10,03 $, 23
    jobs). Total 659,96 $ contre 1 819 847,46 $ pour `JOBS`, soit 0,04 %.
    Volontairement NON filtres, et c'est la difference de FOND avec les deux
    filtres poses en T001c : un job est le proprietaire legitime de ce qu'il
    declenche (le cout de l'appel d'IA est bien un cout du job), alors qu'un
    cluster n'est pas proprietaire du cout d'un service qu'il a seulement
    appele, et qu'un `dlt_pipeline_id` porte par une requete SQL ne designe pas
    un pipeline du tout. Cette table est un rollup d'ORCHESTRATION, les deux
    autres des rollups de RESSOURCE.
    Ce qui reste faux ici est etroit : les trois produits qui portent un
    `cluster_id` (`AI_FUNCTIONS`, `MODEL_SERVING`, `DLT`) sont classes `CLASSIC`
    alors que `product_features.is_serverless` y est NULL ; les deux autres
    n'en portent aucun et passent donc en `SERVERLESS`. Si ce poste grossit, le
    correctif est de porter `billing_origin_product` dans le grain -- separer le
    cout propre du job de ce qu'il a declenche sans perdre ni l'un ni l'autre.
    T001c n'a PAS fait ca : il a ajoute un filtre (liste blanche) sur les deux
    tables ou le cout n'appartenait pas au grain. Ne pas transposer.
    Le `DLT` de cette liste ne double-compte pas avec
    `gold_dbx_compute_pipeline_cost_daily` : mesure sur tout l'historique, ZERO
    ligne de facturation porte a la fois `job_id` et `dlt_pipeline_id`. Ces
    176,59 $ ne sont donc lisibles que dans cette table.

    Champs et formule de calcul :
      - `compute_kind` : `CLASSIC` (le job a tourne sur des clusters,
        `usage_metadata.cluster_id` renseigne) ou `SERVERLESS` (aucun cluster
        derriere la ligne facturee), jamais NULL. Discriminant EXACT, pas une
        heuristique : cf. `sql_helpers.compute_kind_case_expr`, et verifie sur
        le produit `JOBS` ou il coincide sans exception avec
        `product_features.is_serverless` (272 828 + 209 703 lignes
        `is_serverless = true` toutes sans `cluster_id`, 281 236 lignes
        `false` toutes avec). Un job qui a migre (ou qui alterne) produit DEUX
        lignes le meme jour, une par forme -- c'est l'objet du grain.
      - `job_name` : nom du job au dernier etat connu (`change_time <
        period_start + 1 jour` : etat connu a un instant quelconque de
        `period_start`, pas seulement avant minuit - meme piege que
        `cluster_name` dans les tables gold clusters), A DEFAUT le nom du RUN
        (`job_run_timeline.run_name`).
        Les deux sources de nom sont DISJOINTES PAR CONSTRUCTION, mesure sur
        les deux clouds : un run declenche depuis une definition de job
        (`JOB_RUN`) a 100 % une ligne dans `curated_dbx_lakeflow_jobs` et
        `run_name` NULL ; un run soumis par API (`jobs/runs/submit`) n'a
        AUCUNE ligne dans `curated_dbx_lakeflow_jobs` (0 % des couples
        `(workspace_id, job_id)` y existent, par conception : il n'y a pas de
        definition a persister) et porte `run_name` a 100 %. Un `COALESCE`
        des deux est donc exact et SUFFIT : aucun predicat sur le type de run
        n'est necessaire (ce serait une fausse precision, perimee au prochain
        type ajoute par Databricks) - propriete verrouillee par un test.
        Reste NULL apres repli : les runs lances depuis un notebook
        (`WORKFLOW_RUN`), qui n'ont de nom NULLE PART dans la source (0 sur
        192 902 lignes mesurees). C'est un plafond de la source, pas un
        defaut de resolution a corriger ici. Pas de repli sur `job_id` (a la
        difference de `pipeline_name`) : la colonne est documentee "reste
        vide", et c'est le consommateur qui substitue l'id (cf.
        `COALESCE(NULLIF(job_name, ''), job_id)` cote backend).
      - `cluster_count` : nombre de clusters JOB ephemeres distincts ayant
        execute ce job ce jour-la. Formule : `COUNT(DISTINCT
        usage_metadata.cluster_id)`. Vaut donc 0, et non NULL, sur une ligne
        `SERVERLESS` : c'est le cardinal EXACT d'un ensemble vide (aucun
        cluster n'a ete provisionne), pas une mesure manquante -- et cela
        garde la colonne sommable telle quelle dans
        `job_cluster_cost_rolling`. `compute_kind` porte l'information "pas de
        cluster du tout", c'est a l'IHM d'y afficher un tiret plutot qu'un 0.
      - `dbu_quantity` : volume de DBU consommes par le job ce jour-la.
        Formule : `SUM(usage_quantity)` restreint aux lignes `usage_unit =
        'DBU'`.
      - `cost_usd` : cout total en dollars du job ce jour-la. Formule :
        `SUM(usage_quantity * effective_price)`, ou `effective_price` vient de
        `curated_dbx_billing_list_prices` joint sur la fenetre
        `price_start_time <= usage_date < price_end_time`.
      - `cost_usd_prev_day`/`cost_delta_pct` : memes formules que
        `cluster_cost_daily`, au grain job (self-join exact sur J-1, jamais un
        `LAG`). Le self-join est egalise sur `compute_kind` : sans cela un job
        mixte verrait sa ligne CLASSIC de J s'apparier aussi a sa ligne
        SERVERLESS de J-1, produisant DEUX lignes de meme cle de merge ne
        differant que par `cost_usd_prev_day`. Rien ne leverait d'erreur :
        `merge_into_table` applique `dropDuplicates(merge_keys)` avant le
        MERGE et en garderait une ARBITRAIREMENT, donc un `cost_delta_pct`
        calcule un run sur deux contre le cout de l'autre forme de compute.
        926 jours-job mesures sont dans ce cas (contre 2 pipelines seulement
        cote DLT : ici le piege est massif, pas anecdotique). La lecture
        curated inclut 1 jour tampon avant `lower_bound` pour que ce self-join
        voie J-1 au bord de la fenetre incrementale ; ce jour tampon est exclu
        de la sortie (`period_start >= lower_bound`).
      - `cost_rank`/`is_top_cost` : classement des jobs par cout du jour, AU
        SEIN de chaque `compute_kind` (partition `(period_start,
        compute_kind)`), comme cote pipeline : une page filtree sur une forme
        de compute doit y lire un rang qui commence a 1. Deux lignes peuvent
        donc porter `cost_rank = 1` le meme jour, une par forme -- un
        consommateur qui veut un classement toutes formes confondues doit
        d'abord agreger sur `compute_kind`, il ne peut pas reutiliser ce rang.
        `RANK()` (pas `ROW_NUMBER()`) : en cas d'ex-aequo sur `cost_usd` a la
        frontiere du seuil, `is_top_cost` peut marquer plus de
        `top_cost_rank_threshold` jobs le meme jour (constate sur donnee
        reelle, jusqu'a 13 jobs pour un seuil de 10) - comportement
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
    # Resolution du NOM seule, partagee avec `job_efficiency_daily` (cf.
    # `grain_resolution`) : cout et efficacite doivent porter le meme
    # `job_name` pour un `job_id` donne. La resolution du GRAIN n'est plus
    # partagee : ce builder lit `job_id` sur la facturation, l'efficacite
    # continue de le deduire du `cluster_id` faute de facturation cote
    # `node_timeline`. Les deux sources ont ete confrontees sans desaccord (cf.
    # docstring du module).
    job_name_ctes = job_name_ctes_sql(
        grain_cte="priced",
        lakeflow_jobs_table=lakeflow_jobs_table,
        job_run_timeline_table=job_run_timeline_table,
    )
    # Discriminant job classique / serverless, derive de la ligne de facturation
    # elle-meme : ce rollup ne resout aucun cluster (cf. docstring du module).
    compute_kind_expr = compute_kind_case_expr("usage_metadata.cluster_id")
    query = f"""
    WITH usage_filtered AS (
        SELECT
            cloud_provider,
            workspace_id,
            usage_metadata.job_id AS job_id,
            {compute_kind_expr} AS compute_kind,
            usage_metadata.cluster_id AS cluster_id,
            usage_date AS period_start,
            sku_name,
            usage_unit,
            usage_quantity
        FROM {billing_usage_table}
        WHERE usage_metadata.job_id IS NOT NULL
        {usage_date_filter}
    ),
    priced AS (
        SELECT
            u.cloud_provider,
            u.workspace_id,
            u.job_id,
            u.compute_kind,
            u.period_start,
            COUNT(DISTINCT u.cluster_id) AS cluster_count,
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
            u.cloud_provider, u.workspace_id, u.job_id, u.compute_kind, u.period_start
    ),
    {job_name_ctes},
    enriched AS (
        SELECT
            pr.cloud_provider,
            pr.workspace_id,
            pr.job_id,
            pr.compute_kind,
            {JOB_NAME_COALESCE_SQL},
            pr.period_start,
            pr.cluster_count,
            pr.dbu_quantity,
            pr.cost_usd
        FROM priced pr
        {job_name_joins_sql("pr")}
    ),
    with_prev_day AS (
        SELECT
            e.*,
            prev.cost_usd AS cost_usd_prev_day
        FROM enriched e
        LEFT JOIN enriched prev
          ON prev.cloud_provider = e.cloud_provider
         AND prev.workspace_id = e.workspace_id
         AND prev.job_id = e.job_id
         AND prev.compute_kind = e.compute_kind
         AND prev.period_start = e.period_start - INTERVAL 1 DAY
    )
    SELECT
        cloud_provider,
        workspace_id,
        job_id,
        compute_kind,
        job_name,
        period_start,
        cluster_count,
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
