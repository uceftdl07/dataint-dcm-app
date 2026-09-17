"""Agregation gold `gold_dbx_compute_warehouse_utilization_rolling` (idle / rightsizing, fenetres).

Rollup 1/7/30/90 jours de `gold_dbx_compute_warehouse_utilization_daily` : pour
chaque SQL Warehouse, temps allume vs. temps actif cumules sur les derniers
`window_days` jours "as of" le dernier jour disponible, part de temps idle
recalculee sur la fenetre et diagnostic de dimensionnement recalcule sur la
fenetre.

Regles de derivation : `running_hours`/`active_query_hours`/`scale_up_events`/
`scale_down_events`/`estimated_savings_usd` sont additifs (somme). `idle_pct` et
`active_to_running_ratio` sont des ratios : recalcules a partir des sommes de la
fenetre (pas la moyenne des ratios quotidiens). `avg_cluster_count` est une
moyenne ponderee par le temps allume ; `max_cluster_count`/`peak_concurrency`
sont des maxima (MAX du MAX). `utilization_status`/`rightsizing_reco` sont
recalcules a partir des metriques de la fenetre. L'identite du warehouse
(`warehouse_name`) et la configuration d'auto-arret (`auto_stop_minutes`/
`has_auto_stop`) sont reprises au dernier etat connu : un warehouse renomme au
milieu de la fenetre y porte donc son nom le PLUS RECENT, seul nom qui permette
de le retrouver tel qu'il s'appelle aujourd'hui. `warehouse_type` suit la meme
logique de recence avec une nuance : le dernier jour RENSEIGNE de la fenetre (un
jour sans type connu n'efface pas le type de la veille), et toujours aligne sur
`is_serverless`.

NOTE : le diagnostic UNDER de la table quotidienne utilise `max_clusters`
(configuration du warehouse), non porte a la maille fenetre. Cette table le
remplace par `max_cluster_count` (nombre max de clusters *observe* sur la
fenetre) comme proxy de capacite -- ecart volontaire vs la table quotidienne.

SERVERLESS : comme la table quotidienne, cette table ne diagnostique
l'efficience que du compute classique / pro (`idle_pct`,
`active_to_running_ratio`, `auto_stop_minutes`, `has_auto_stop`,
`utilization_status`, `rightsizing_reco`, `estimated_savings_usd` a NULL quand
`is_serverless`). La neutralisation doit etre REFAITE ICI et non seulement
heritee : `idle_pct`, `active_to_running_ratio`, `utilization_status` et
`rightsizing_reco` sont RECALCULES a partir des sommes de la fenetre, donc un
`idle_pct` de 96 % et un verdict `OVER` non actionnables reapparaitraient a la
maille fenetre -- c'est cette table que lit `recommendations.py` (fenetre 30 j).
`estimated_savings_usd` est deja purge des jours serverless par la somme (la
table quotidienne les a mis a NULL) ; il est neanmoins mis a NULL ici quand
`is_serverless`, pour qu'une fenetre mixte ne presente pas une economie
residuelle a cote d'un diagnostic sans objet.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.specs import (
    ROLLING_WINDOWS,
    WAREHOUSE_IDLE_PCT_OVER_THRESHOLD,
    WAREHOUSE_PEAK_CONCURRENCY_UNDER_RATIO,
    WAREHOUSE_TYPE_SERVERLESS,
)
from pipelines.gold_dbx_compute.sql_helpers import rolling_windows_array_sql

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession


def build_warehouse_utilization_rolling(
    spark: SparkSession,
    *,
    warehouse_utilization_daily_table: str,
    rolling_windows: tuple[int, ...] = ROLLING_WINDOWS,
    idle_pct_over_threshold: float = WAREHOUSE_IDLE_PCT_OVER_THRESHOLD,
    peak_concurrency_under_ratio: float = WAREHOUSE_PEAK_CONCURRENCY_UNDER_RATIO,
) -> DataFrame:
    """Construit `gold_dbx_compute_warehouse_utilization_rolling`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        warehouse_utilization_daily_table: nom qualifie (`catalog.schema.table`)
            de `gold_dbx_compute_warehouse_utilization_daily` (unique source).
        rolling_windows: fenetres glissantes (jours) a materialiser, une ligne
            par warehouse ET par fenetre (defaut `ROLLING_WINDOWS`).
        idle_pct_over_threshold: seuil (%) au-dela duquel le warehouse est
            diagnostique surdimensionne sur la fenetre (defaut
            `WAREHOUSE_IDLE_PCT_OVER_THRESHOLD`).
        peak_concurrency_under_ratio: ratio (pic de concurrence / nombre max de
            clusters observe) au-dela duquel le warehouse est diagnostique
            sous-dimensionne (defaut `WAREHOUSE_PEAK_CONCURRENCY_UNDER_RATIO`).

    Returns:
        Le DataFrame `gold_dbx_compute_warehouse_utilization_rolling` resultant.

    Grain : `(cloud_provider, workspace_id, warehouse_id, window_days)`. Snapshot
    "as of" le dernier jour disponible (`as_of_date = MAX(period_start)`).

    `warehouse_type` a la maille fenetre = type declare du dernier jour
    RENSEIGNE de la fenetre, et non du dernier jour tout court : une fenetre de
    90 jours peut melanger des jours de types differents (ou sans type connu du
    tout, warehouse absent du referentiel ce jour-la), et c'est le plus recent
    qui decrit le warehouse tel qu'il est aujourd'hui -- meme regle que
    `warehouse_name`/`auto_stop_minutes`. La difference avec `latest_attrs` porte
    sur ce seul mot « renseigne » : un dernier jour a NULL n'efface pas un type
    connu la veille, la ou `latest_attrs` propagerait le NULL. Comme la table
    quotidienne, la colonne reste SUBORDONNEE a `is_serverless` de la fenetre :
    des qu'un jour de la fenetre est serverless, elle vaut `'SERVERLESS'`.

    `is_serverless` a la maille fenetre = AU MOINS UN jour serverless dans la
    fenetre (`MAX` du booleen quotidien), pas le dernier etat connu : des qu'une
    partie du temps allume de la fenetre est serverless, le ratio recalcule sur
    les sommes de la fenetre n'est plus interpretable economiquement. Meme biais
    volontaire que la table quotidienne sur un jour mixte -- ne jamais afficher
    une economie non encaissable. Consequence assumee : un warehouse repasse de
    serverless a classique garde un diagnostic NULL sur les fenetres longues
    jusqu'a ce qu'elles aient defile (la fenetre 1 j, elle, redevient immediatement
    exploitable).
    """
    windows_array = rolling_windows_array_sql(rolling_windows)
    query = f"""
    WITH daily AS (
        SELECT
            cloud_provider,
            workspace_id,
            warehouse_id,
            period_start,
            warehouse_name,
            warehouse_type,
            running_hours,
            active_query_hours,
            auto_stop_minutes,
            has_auto_stop,
            scale_up_events,
            scale_down_events,
            avg_cluster_count,
            max_cluster_count,
            peak_concurrency,
            estimated_savings_usd,
            is_serverless
        FROM {warehouse_utilization_daily_table}
    ),
    anchor AS (
        SELECT MAX(period_start) AS as_of_date FROM daily
    ),
    windows AS (
        SELECT explode({windows_array}) AS window_days
    ),
    latest_attrs AS (
        SELECT
            cloud_provider,
            workspace_id,
            warehouse_id,
            warehouse_name,
            auto_stop_minutes,
            has_auto_stop
        FROM daily
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY cloud_provider, workspace_id, warehouse_id
            ORDER BY period_start DESC
        ) = 1
    ),
    agg AS (
        SELECT
            d.cloud_provider,
            d.workspace_id,
            d.warehouse_id,
            w.window_days,
            a.as_of_date,
            date_add(a.as_of_date, -(w.window_days - 1)) AS window_start,
            SUM(d.running_hours) AS running_hours,
            SUM(d.active_query_hours) AS active_query_hours,
            SUM(d.scale_up_events) AS scale_up_events,
            SUM(d.scale_down_events) AS scale_down_events,
            SUM(d.estimated_savings_usd) AS estimated_savings_usd,
            SUM(d.avg_cluster_count * d.running_hours)
                / NULLIF(SUM(CASE WHEN d.avg_cluster_count IS NOT NULL
                                  THEN d.running_hours END), 0) AS avg_cluster_count,
            MAX(d.max_cluster_count) AS max_cluster_count,
            MAX(d.peak_concurrency) AS peak_concurrency,
            -- Au moins un jour serverless dans la fenetre (cf. docstring) :
            -- suffit a rendre le diagnostic d'efficience non interpretable.
            MAX(CASE WHEN d.is_serverless THEN 1 ELSE 0 END) = 1 AS is_serverless,
            -- Type declare du dernier jour RENSEIGNE de la fenetre : la cle de
            -- tri est masquee a NULL sur les jours sans type connu, que `MAX_BY`
            -- ignore alors. Sans ce masque, un dernier jour vide effacerait le
            -- type connu la veille. Pas dans `latest_attrs` pour cette raison :
            -- cette CTE sert le dernier jour tout court, NULL compris.
            MAX_BY(
                d.warehouse_type,
                CASE WHEN d.warehouse_type IS NOT NULL THEN d.period_start END
            ) AS warehouse_type
        FROM daily d
        CROSS JOIN anchor a
        CROSS JOIN windows w
        WHERE d.period_start > date_add(a.as_of_date, -w.window_days)
          AND d.period_start <= a.as_of_date
        GROUP BY d.cloud_provider, d.workspace_id, d.warehouse_id, w.window_days, a.as_of_date
    ),
    with_metrics AS (
        SELECT
            g.*,
            (g.running_hours - g.active_query_hours) / NULLIF(g.running_hours, 0) * 100
                AS idle_pct,
            g.active_query_hours / NULLIF(g.running_hours, 0) AS active_to_running_ratio
        FROM agg g
    )
    SELECT
        m.cloud_provider,
        m.workspace_id,
        m.warehouse_id,
        m.window_days,
        m.as_of_date,
        m.window_start,
        la.warehouse_name,
        m.is_serverless,
        -- Subordination a `is_serverless` REFAITE ici (meme raison que la
        -- neutralisation ci-dessous) : `is_serverless` de la fenetre est plus
        -- large que celui d'un jour (`MAX`), une fenetre mixte doit donc afficher
        -- SERVERLESS. La 2e branche est inatteignable tant que la table
        -- quotidienne tient sa garde -- gardee volontairement pour que la
        -- coherence de cette table ne depende pas d'une invariante d'ailleurs.
        CASE
            WHEN m.is_serverless THEN '{WAREHOUSE_TYPE_SERVERLESS}'
            WHEN m.warehouse_type = '{WAREHOUSE_TYPE_SERVERLESS}' THEN NULL
            ELSE m.warehouse_type
        END AS warehouse_type,
        m.running_hours,
        m.active_query_hours,
        -- Meme neutralisation que la table quotidienne, REFAITE sur les
        -- metriques recalculees de la fenetre (cf. entete de module) : ne pas
        -- retirer ces gardes sans retirer aussi `is_serverless`.
        CASE WHEN m.is_serverless THEN NULL ELSE m.idle_pct END AS idle_pct,
        CASE
            WHEN m.is_serverless THEN NULL
            ELSE m.active_to_running_ratio
        END AS active_to_running_ratio,
        CASE WHEN m.is_serverless THEN NULL ELSE la.auto_stop_minutes END AS auto_stop_minutes,
        CASE WHEN m.is_serverless THEN NULL ELSE la.has_auto_stop END AS has_auto_stop,
        m.scale_up_events,
        m.scale_down_events,
        m.avg_cluster_count,
        m.max_cluster_count,
        m.peak_concurrency,
        CASE
            WHEN m.is_serverless THEN NULL
            WHEN m.idle_pct > {idle_pct_over_threshold} THEN 'OVER'
            WHEN m.peak_concurrency >= m.max_cluster_count * {peak_concurrency_under_ratio}
                THEN 'UNDER'
            ELSE 'OPTIMAL'
        END AS utilization_status,
        CASE
            WHEN m.is_serverless THEN NULL
            WHEN m.idle_pct > {idle_pct_over_threshold}
                THEN 'Reduire la taille du warehouse ou activer l''auto-stop'
            WHEN m.peak_concurrency >= m.max_cluster_count * {peak_concurrency_under_ratio}
                THEN 'Augmenter max_clusters pour absorber les pics de concurrence'
            ELSE 'Dimensionnement optimal, aucune action requise'
        END AS rightsizing_reco,
        CASE
            WHEN m.is_serverless THEN NULL
            ELSE m.estimated_savings_usd
        END AS estimated_savings_usd,
        current_timestamp() AS _generated_at
    FROM with_metrics m
    LEFT JOIN latest_attrs la
      ON la.cloud_provider = m.cloud_provider
     AND la.workspace_id = m.workspace_id
     AND la.warehouse_id = m.warehouse_id
    WHERE m.running_hours > 0
    """
    return spark.sql(query)
