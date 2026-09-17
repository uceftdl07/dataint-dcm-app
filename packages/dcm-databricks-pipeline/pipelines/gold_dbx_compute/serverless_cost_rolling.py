"""Agregation gold `gold_dbx_compute_serverless_cost_rolling` (FinOps serverless, fenetres).

Rollup 1/7/30/90 jours de `gold_dbx_compute_serverless_cost_daily` : pour chaque
objet serverless, cout/DBU cumules sur les derniers `window_days` jours "as of"
le dernier jour disponible, variation vs la fenetre precedente de meme longueur,
percentiles du cout par execution et classement par cout AU SEIN de sa surface.

Regles de derivation :
  - Sommes additives : `cost_usd`, `dbu_quantity`, `run_count`.
  - `cost_usd_prev_window` : fenetre precedente de meme longueur, `NULL` (et non
    `0`) quand elle est VIDE -- `0` affirmerait "cet objet existait et n'a rien
    coute", ce qui est faux d'un objet cree pendant la fenetre courante. Le
    `SUM(CASE ... END)` sans `ELSE` produit exactement cela.
  - Percentiles du cout par execution (`cost_per_run_p50_usd`, `_p95_usd`,
    `_p99_usd`) : RECALCULES a partir des histogrammes quotidiens
    (`cost_per_run_histogram`) sommes bucket par bucket sur la fenetre, un
    percentile quotidien n'etant ni sommable ni moyennable (cf.
    `sql_helpers.percentile_from_histogram_sql`). Une moyenne de p95 quotidiens
    n'a aucune signification statistique. L'histogramme fusionne EST expose ici,
    contrairement a `warehouse_query_performance_rolling` : la page serverless
    trace la distribution du cout par execution, pas seulement ses percentiles.
  - Attributs non additifs (`object_name`, `identity_principal`,
    `identity_source`, `budget_policy_id`, `performance_target`,
    `billing_origin_product`) : repris au DERNIER jour connu de l'objet. Un objet
    renomme, ou dont le `run_as` change au milieu de la fenetre, y porte donc son
    etat le PLUS RECENT -- le seul qui permette de le retrouver tel qu'il est
    aujourd'hui. `identity_principal` et `identity_source` sont pris sur la MEME
    ligne, les desynchroniser rendrait la matrice de refacturation fausse.
  - `has_custom_tags` : OR sur la fenetre COURANTE (au moins un jour tague), et
    non "dernier etat connu" : la question posee est "cet objet est-il taguable /
    refacturable", pas "l'etait-il hier".

ANTI-DOUBLE-COMPTAGE -- rollup des MEMES lignes de facturation que
`cluster_cost_rolling`, `job_cluster_cost_rolling`, `pipeline_cost_rolling` et
`warehouse_cost_rolling`, vues sous l'axe de la forme de compute. NE JAMAIS y
sommer cette table. Ni sommer plusieurs `window_days` entre elles (fenetres
emboitees). Sommer les `serverless_surface` d'une MEME fenetre est en revanche
legitime et redonne la depense serverless totale de cette fenetre.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.specs import ROLLING_WINDOWS, TOP_COST_RANK_THRESHOLD
from pipelines.gold_dbx_compute.sql_helpers import (
    HISTOGRAM_COST_PER_RUN_EDGES,
    SERVERLESS_OBJECT_ID_SENTINEL,
    histogram_bucket_count,
    percentile_from_histogram_sql,
    rolling_windows_array_sql,
    sum_histograms_sql,
)

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession


def build_serverless_cost_rolling(
    spark: SparkSession,
    *,
    serverless_cost_daily_table: str,
    rolling_windows: tuple[int, ...] = ROLLING_WINDOWS,
    top_cost_rank_threshold: int = TOP_COST_RANK_THRESHOLD,
) -> DataFrame:
    """Construit `gold_dbx_compute_serverless_cost_rolling`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        serverless_cost_daily_table: nom qualifie (`catalog.schema.table`) de
            `gold_dbx_compute_serverless_cost_daily` (unique source).
        rolling_windows: fenetres glissantes (jours) a materialiser, une ligne
            par objet ET par fenetre (defaut `ROLLING_WINDOWS`).
        top_cost_rank_threshold: nombre d'objets consideres "top cost" par
            fenetre ET par surface (defaut `TOP_COST_RANK_THRESHOLD`).

    Returns:
        Le DataFrame `gold_dbx_compute_serverless_cost_rolling` resultant.

    Grain : `(cloud_provider, workspace_id, serverless_surface, object_id,
    window_days)`. Snapshot "as of" le dernier jour disponible (`as_of_date =
    MAX(period_start)`), donc table integralement reecrite a chaque run.

    `serverless_surface` et `object_id` sont repris du daily et heritent de ses
    garanties de non-nullite (branche `ELSE 'OTHER'` du `CASE`, sentinelle
    `_NO_OBJECT`) : indispensable, `merge_into_table` fusionnant sur `<=>`
    null-safe. Cf. `serverless_cost_daily` pour le detail du piege.

    Champs specifiques :
      - `run_count` : somme des `run_count` quotidiens sur la fenetre courante,
        `NULL` (jamais `0`) hors surface `JOB` ou en l'absence de jour avec
        execution. ATTENTION, c'est un compte de RUN-JOURS et non d'executions
        distinctes : une execution a cheval sur minuit compte pour 2. Mesure dev
        2026-09-10 (fenetre de reference 2026-08-10..2026-09-09, bi-cloud) :
        339 executions AWS et 183 Azure sont a cheval sur minuit, soit 522 sur
        161 550 executions (0,32 %) et 573 run-jours en trop sur 162 123
        (0,35 %) -- l'ecart est reel mais marginal, et le grain quotidien de la
        source ne permet pas de faire mieux sans relire la facturation.
      - `cost_per_run_histogram` : histogrammes quotidiens fusionnes bucket par
        bucket sur la fenetre courante (`array<bigint>`, 19 buckets, cf.
        `sql_helpers.HISTOGRAM_COST_PER_RUN_EDGES`), donc distribution du cout
        par RUN-JOUR, meme reserve que `run_count`. `NULL` (jamais un tableau de
        zeros) quand il n'y a aucune execution : le masquage est explicite dans
        `with_metrics`, `collect_list` ignorant les `NULL` et `aggregate` sur une
        liste vide renvoyant `0`.
      - `cost_per_run_p50_usd` / `_p95_usd` / `_p99_usd` : percentiles relus de
        cet histogramme, resolution bornee par la largeur des buckets. Mesure dev
        2026-09-10 (fenetre de reference 2026-08-10..2026-09-09, toutes lignes
        de surface `JOB` confondues) : p50 0,1261 $, p95 1,0446 $, p99 9,1436 $
        par run-jour en BI-CLOUD -- mais p95 1,4897 $ et p99 14,789 $ sur AWS
        seul contre 0,8226 $ et 2,8651 $ sur Azure. La queue est un phenomene
        AWS ; un percentile serverless cite sans son cloud ne veut rien dire, et
        c'est exactement la confusion qui a fait reecrire deux fois le §10.4 du
        spike. Les bornes montent jusqu'a 1 310,72 $ pour que la queue reste
        lisible : 117 run-jours depassent 50 $ et pesent 13 520,44 $, le plus
        cher atteint 1 137,99 $ (AWS). Le bucket overflow est donc VIDE sur la
        fenetre mesuree, ce qui est le comportement voulu -- s'il se remplit, la
        queue est a re-borner. Il ne peut PAS l'etre par une execution a cheval
        sur minuit, meme couteuse : la plus chere atteint 1 345,12 $ (AWS)
        au-dela de la derniere borne, mais elle entre dans l'histogramme par
        tranches quotidiennes, chacune sous la borne.
      - `cost_rank` / `is_top_cost` : classement par cout au sein de chaque
        couple `(window_days, serverless_surface)` -- et NON de la seule
        `window_days` : l'IHM affiche ce rang sur une liste filtree par surface,
        un rang toutes surfaces confondues y commencerait a 40. Douze lignes
        peuvent donc porter `cost_rank = 1` pour une meme fenetre, une par
        surface.

    Un objet sans cout ni sur la fenetre courante ni sur la precedente est
    exclu.
    """
    windows_array = rolling_windows_array_sql(rolling_windows)
    num_buckets = histogram_bucket_count(HISTOGRAM_COST_PER_RUN_EDGES)
    # Percentiles relus sur l'histogramme FUSIONNE de la fenetre courante, jamais
    # une moyenne de percentiles quotidiens.
    p50 = percentile_from_histogram_sql(
        "g.cost_per_run_histogram_raw", HISTOGRAM_COST_PER_RUN_EDGES, 0.50
    )
    p95 = percentile_from_histogram_sql(
        "g.cost_per_run_histogram_raw", HISTOGRAM_COST_PER_RUN_EDGES, 0.95
    )
    p99 = percentile_from_histogram_sql(
        "g.cost_per_run_histogram_raw", HISTOGRAM_COST_PER_RUN_EDGES, 0.99
    )
    # `collect_list` ignore les NULL : sans ce masquage a la fenetre courante, la
    # fusion melangerait les histogrammes des DEUX fenetres (la CTE `agg` lit
    # 2 x `window_days` jours pour calculer la fenetre precedente).
    current_window_histogram = (
        "CASE WHEN d.period_start > date_add(a.as_of_date, -w.window_days)"
        " THEN d.cost_per_run_histogram END"
    )
    merged_histogram = sum_histograms_sql(current_window_histogram, num_buckets)
    query = f"""
    WITH daily AS (
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
            dbu_quantity,
            cost_usd,
            run_count,
            cost_per_run_histogram
        FROM {serverless_cost_daily_table}
    ),
    anchor AS (
        SELECT MAX(period_start) AS as_of_date FROM daily
    ),
    windows AS (
        SELECT explode({windows_array}) AS window_days
    ),
    latest_attrs AS (
        -- Grain COMPLET du daily hors `period_start`, `serverless_surface`
        -- INCLUSE : contrairement au `compute_kind` de `pipeline_cost_rolling`,
        -- la surface fait partie de l'identite de l'objet et ses attributs en
        -- dependent (le nom d'un `dlt_pipeline_id` vu en `MV_ST_REFRESH` n'est
        -- pas celui du meme id vu en `DLT_PIPELINE`).
        SELECT
            cloud_provider,
            workspace_id,
            serverless_surface,
            object_id,
            object_name,
            billing_origin_product,
            performance_target,
            budget_policy_id,
            identity_principal,
            identity_source
        FROM daily
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY cloud_provider, workspace_id, serverless_surface, object_id
            ORDER BY period_start DESC
        ) = 1
    ),
    agg AS (
        SELECT
            d.cloud_provider,
            d.workspace_id,
            d.serverless_surface,
            d.object_id,
            w.window_days,
            a.as_of_date,
            date_add(a.as_of_date, -(w.window_days - 1)) AS window_start,
            SUM(CASE
                    WHEN d.period_start > date_add(a.as_of_date, -w.window_days)
                    THEN d.dbu_quantity ELSE 0
                END) AS dbu_quantity,
            SUM(CASE
                    WHEN d.period_start > date_add(a.as_of_date, -w.window_days)
                    THEN d.cost_usd ELSE 0
                END) AS cost_usd,
            -- Pas d'`ELSE 0` ici, a la difference des deux sommes ci-dessus :
            -- fenetre precedente vide => NULL, cf. docstring.
            SUM(CASE
                    WHEN d.period_start <= date_add(a.as_of_date, -w.window_days)
                    THEN d.cost_usd
                END) AS cost_usd_prev_window,
            -- Idem : `run_count` quotidien est NULL hors surface JOB, un SUM sans
            -- `ELSE` propage donc le NULL au lieu de fabriquer un 0 trompeur.
            SUM(CASE
                    WHEN d.period_start > date_add(a.as_of_date, -w.window_days)
                    THEN d.run_count
                END) AS run_count,
            MAX(CASE
                    WHEN d.period_start > date_add(a.as_of_date, -w.window_days)
                         AND d.has_custom_tags
                    THEN 1 ELSE 0
                END) = 1 AS has_custom_tags,
            -- Vaut 19 zeros (et non NULL) en l'absence d'execution : masque dans
            -- `with_metrics`.
            {merged_histogram} AS cost_per_run_histogram_raw
        FROM daily d
        CROSS JOIN anchor a
        CROSS JOIN windows w
        WHERE d.period_start > date_add(a.as_of_date, -2 * w.window_days)
          AND d.period_start <= a.as_of_date
        GROUP BY
            d.cloud_provider,
            d.workspace_id,
            d.serverless_surface,
            d.object_id,
            w.window_days,
            a.as_of_date
    ),
    with_metrics AS (
        -- `run_count IS NULL` <=> aucune execution dans la fenetre courante (les
        -- deux colonnes viennent du meme masquage) : c'est le predicat qui rend
        -- histogramme et percentiles NULL au lieu de 19 zeros et d'un p50 lu
        -- dans un histogramme vide.
        SELECT
            g.*,
            CASE
                WHEN g.run_count IS NULL THEN NULL
                ELSE g.cost_per_run_histogram_raw
            END AS cost_per_run_histogram,
            CASE WHEN g.run_count IS NULL THEN NULL ELSE {p50} END AS cost_per_run_p50_usd,
            CASE WHEN g.run_count IS NULL THEN NULL ELSE {p95} END AS cost_per_run_p95_usd,
            CASE WHEN g.run_count IS NULL THEN NULL ELSE {p99} END AS cost_per_run_p99_usd
        FROM agg g
    )
    SELECT
        m.cloud_provider,
        m.workspace_id,
        m.serverless_surface,
        m.object_id,
        m.window_days,
        m.as_of_date,
        m.window_start,
        la.object_name,
        la.billing_origin_product,
        la.performance_target,
        la.budget_policy_id,
        la.identity_principal,
        la.identity_source,
        m.has_custom_tags,
        m.object_id <> '{SERVERLESS_OBJECT_ID_SENTINEL}' AS has_object_key,
        m.dbu_quantity,
        m.cost_usd,
        m.cost_usd_prev_window,
        (m.cost_usd - m.cost_usd_prev_window)
            / NULLIF(m.cost_usd_prev_window, 0) * 100 AS cost_delta_pct,
        m.run_count,
        m.cost_per_run_histogram,
        m.cost_per_run_p50_usd,
        m.cost_per_run_p95_usd,
        m.cost_per_run_p99_usd,
        RANK() OVER (
            PARTITION BY m.window_days, m.serverless_surface ORDER BY m.cost_usd DESC
        ) AS cost_rank,
        RANK() OVER (PARTITION BY m.window_days, m.serverless_surface ORDER BY m.cost_usd DESC)
            <= {top_cost_rank_threshold} AS is_top_cost,
        current_timestamp() AS _generated_at
    FROM with_metrics m
    LEFT JOIN latest_attrs la
      ON la.cloud_provider = m.cloud_provider
     AND la.workspace_id = m.workspace_id
     AND la.serverless_surface = m.serverless_surface
     AND la.object_id = m.object_id
    -- `COALESCE` obligatoire : `cost_usd_prev_window` peut etre NULL et
    -- `NULL <> 0` vaut NULL, ce qui EXCLURAIT la ligne au lieu de la garder.
    WHERE m.cost_usd <> 0 OR COALESCE(m.cost_usd_prev_window, 0) <> 0
    """
    return spark.sql(query)
