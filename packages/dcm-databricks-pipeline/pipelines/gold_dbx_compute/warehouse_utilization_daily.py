"""Agregation gold `gold_dbx_compute_warehouse_utilization_daily` (idle / rightsizing).

Utilisation quotidienne des SQL Warehouses Databricks : temps allume (running)
vs. temps avec des requetes reellement actives, stabilite du scaling
automatique, et recommandation de redimensionnement (rightsizing) avec
economie estimee. Alimente le diagnostic de sur/sous-dimensionnement des
warehouses.

L'EFFICIENCE N'EST CALCULEE QUE POUR LE COMPUTE CLASSIQUE / PRO. En serverless,
l'utilisateur n'est pas facture au temps allume mais au compute consomme par ses
requetes : reduire l'idle d'un warehouse serverless ne rend aucun dollar, et un
ratio actif/allume structurellement bas y est le comportement ATTENDU (le
warehouse demarre a l'arrivee d'une requete et s'arrete quelques minutes apres).
Le calcul lui-meme est juste - c'est sa lecture economique qui ne tient pas :
mesure en dev sur 15 j (2026-08-25 -> 09-08, AWS), `idle_pct` median 96,3 %,
95,6 % des jours-warehouse au-dela du seuil de 60 %, 353 des 398 warehouses
serverless marques `OVER` et ~49 100 $/15 j (~98 k$/30 j) d'
`estimated_savings_usd` IRREALISABLES. Les champs de diagnostic economique sont
donc mis a NULL (« sans objet ») sur ces lignes, et la colonne `is_serverless`
dit POURQUOI - sans elle, l'IHM et le backend lisent un NULL muet, qui se
confond avec une donnee manquante. Les metriques d'activite brutes
(`running_hours`, `active_query_hours`, `peak_concurrency`, scaling) restent
renseignees : elles sont justes dans les deux mondes. Le signal d'efficience
serverless est le $ par requete et le temps de file (`query_history`), pas
l'idle.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.specs import (
    WAREHOUSE_IDLE_PCT_OVER_THRESHOLD,
    WAREHOUSE_PEAK_CONCURRENCY_UNDER_RATIO,
    WAREHOUSE_QUERY_HISTORY_LOOKBACK_DAYS,
    WAREHOUSE_QUERY_STILL_RUNNING_MAX_HOURS,
    WAREHOUSE_SESSION_LOOKBACK_DAYS,
    WAREHOUSE_TYPE_SERVERLESS,
)
from pipelines.gold_dbx_compute.sql_helpers import lower_bound_predicate, sql_string_list

if TYPE_CHECKING:
    from datetime import date

    from pyspark.sql import DataFrame, SparkSession

# Evenements `system.compute.warehouse_events` marquant le debut/fin d'une
# session "allume" du warehouse. `STARTING` (et non `RUNNING`) parce qu'il borne
# le DEBUT REEL de l'allumage : un warehouse est allume des sa mise en route,
# pas seulement une fois pret a servir - `RUNNING -> STOPPED` amputerait chaque
# session de sa rampe de demarrage. Ce n'est PAS un defaut de journalisation de
# `RUNNING`, contrairement a ce qu'affirmait la version precedente de ce
# commentaire : mesure le 2026-09-10, `RUNNING` est emis 55 886 fois sur 393
# warehouses serverless (AWS), soit autant que `STARTING` (55 880 / 380) - le
# choix reste valide, sa justification d'origine etait fausse.
WAREHOUSE_STARTING_EVENT = "STARTING"
WAREHOUSE_STOPPED_EVENT = "STOPPED"
# Evenements de mise a l'echelle : scale up regroupe les 2 variantes
# observees (transition + confirmation), scale down se limite a la variante
# documentee dans le mapping (`compute_datamapping.md` Section 3.2 ne liste que
# `SCALED_DOWN`, pas `SCALING_DOWN`) -> ecart volontaire, pas une omission.
WAREHOUSE_SCALE_UP_EVENTS = ("SCALING_UP", "SCALED_UP")
WAREHOUSE_SCALE_DOWN_EVENTS = ("SCALED_DOWN",)


def build_warehouse_utilization_daily(
    spark: SparkSession,
    *,
    warehouse_events_table: str,
    warehouses_table: str,
    query_history_table: str,
    cost_daily_table: str,
    billing_usage_table: str,
    lower_bound: date | None,
    idle_pct_over_threshold: float = WAREHOUSE_IDLE_PCT_OVER_THRESHOLD,
    peak_concurrency_under_ratio: float = WAREHOUSE_PEAK_CONCURRENCY_UNDER_RATIO,
) -> DataFrame:
    """Construit `gold_dbx_compute_warehouse_utilization_daily`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        warehouse_events_table: nom qualifie (`catalog.schema.table`) de
            `curated_dbx_compute_warehouse_events` (journal d'evenements).
        warehouses_table: nom qualifie de `curated_dbx_compute_warehouses`
            (dernier etat connu du warehouse, pour `warehouse_name`/
            `auto_stop_minutes`/`max_clusters`).
        query_history_table: nom qualifie de `curated_dbx_query_history`
            (signal d'activite reelle et pic de concurrence).
        cost_daily_table: nom qualifie de
            `gold_dbx_compute_warehouse_cost_daily` (montant $ des economies
            estimees).
        billing_usage_table: nom qualifie de `curated_dbx_billing_usage`
            (discriminant serverless via `product_features.is_serverless`, cf.
            `is_serverless` ci-dessous).
        lower_bound: borne basse incluse de `period_start` pour la lecture
            incrementale ; `None` pour recalculer l'historique complet.
        idle_pct_over_threshold: seuil (%) au-dela duquel le warehouse est
            considere surdimensionne (defaut
            `WAREHOUSE_IDLE_PCT_OVER_THRESHOLD`).
        peak_concurrency_under_ratio: ratio (pic de requetes concurrentes /
            `max_clusters`) au-dela duquel le warehouse est considere
            sous-dimensionne (defaut `WAREHOUSE_PEAK_CONCURRENCY_UNDER_RATIO`).

    Returns:
        Le DataFrame `gold_dbx_compute_warehouse_utilization_daily` resultant.

    Grain : `(cloud_provider, workspace_id, warehouse_id, period_start)`.
    Source : `curated_dbx_compute_warehouse_events` (sessions running,
    scaling) + `curated_dbx_query_history` (activite reelle, pic de
    concurrence) + dernier etat connu du warehouse
    (`curated_dbx_compute_warehouses`) + `gold_dbx_compute_warehouse_cost_daily`
    (montant $ des economies estimees) + `curated_dbx_billing_usage`
    (discriminant serverless, cf. `is_serverless`). La lecture de
    `curated_dbx_compute_warehouse_events` applique un tampon de
    `WAREHOUSE_SESSION_LOOKBACK_DAYS` (30 jours) AVANT `lower_bound`,
    uniquement pour reconstruire les sessions STARTING -> STOPPED (cf.
    `running_hours` ci-dessous) -- `query_history` et la sortie restent
    bornees a `lower_bound` sans tampon.

    Champs et formule de calcul :
      - `is_serverless` : forme de compute du warehouse CE JOUR-LA, jamais NULL
        (un NULL se confondrait avec une donnee manquante alors que la question
        « serverless ou pas » a toujours une reponse). Resolu en cascade :
        (1) facturation du jour (`product_features.is_serverless` sur les lignes
        portant `usage_metadata.warehouse_id`), source d'autorite car c'est la
        forme REELLEMENT facturee ; (2) a defaut de ligne de facturation ce
        jour-la, `warehouse_type = 'SERVERLESS'` au dernier etat connu
        (`warehouses_as_of`, meme borne `change_time < period_start + 1 jour`) ;
        (3) a defaut des deux, `false`. Mesure en dev le 2026-09-10 : (1) resout
        16 218 des 16 781 jours-warehouse (96,6 %), (2) les 563 restants
        (3,4 %), (3) aucun -- le repli `false` ne peut de toute facon rien
        fabriquer, un jour sans facturation a `cost_usd` NULL donc
        `estimated_savings_usd` NULL. Grain JOURNALIER et non par warehouse : 68
        warehouses changent de forme au fil de l'historique et 63
        jours-warehouse melangent les deux formes le meme jour, replies par
        `MAX` (serverless l'emporte) -- biais volontaire vers « ne pas afficher
        d'economie non encaissable ».
      - `warehouse_type` : type de compute DECLARE du warehouse ce jour-la
        (`SERVERLESS`/`PRO`/`CLASSIC`), ce que le booleen `is_serverless` ne
        peut pas dire -- il ne distingue pas PRO de CLASSIC alors que les deux
        sont peuples (mesure account-wide le 2026-09-11 : 359 warehouses PRO,
        162 CLASSIC cote curated dev). Lu sur `warehouses_as_of`, donc meme
        borne `change_time < period_start + 1 jour` que `warehouse_name`, et
        AUCUNE jointure supplementaire. SUBORDONNE a `is_serverless`, jamais
        l'inverse : (1) `is_serverless` vrai -> `'SERVERLESS'`, meme si le type
        declare dit PRO (3 jours-warehouse mesures) ; (2) type declare
        `'SERVERLESS'` dementi par la facturation du jour -> NULL, car on ne
        sait pas lequel de PRO/CLASSIC a ete facture et l'inventer serait faux
        (1 jour-warehouse mesure) ; (3) sinon le type declare tel quel. Cette
        subordination n'est pas cosmetique : le backend supprime les economies
        non encaissables sur le seul `is_serverless`, une ligne « PRO » avec
        `is_serverless` vrai casserait cette suppression. NULL quand le
        warehouse est absent de `curated_dbx_compute_warehouses` a cette date
        (cas (3) sur une valeur NULL). Le domaine n'est PAS ferme a trois
        valeurs : `REAL_TIME` existe cote curated (1 warehouse, aucune session
        donc aucune ligne gold au 2026-09-11) et passerait tel quel par le cas
        (3) -- cf. `WAREHOUSE_TYPE_SERVERLESS` dans `specs.py`.
      - `warehouse_name` : nom du warehouse, resolu au dernier etat connu du
        jour agrege (`change_time < period_start + 1 jour` : etat connu a un
        instant quelconque de `period_start`, pas seulement avant minuit - un
        cast `TIMESTAMP <= DATE` a minuit exclurait a tort les warehouses crees
        le jour meme, cas des ephemeres de bundle), meme regle que
        `warehouse_cost_daily.build_warehouse_cost_daily`. `LEFT JOIN` : un
        warehouse absent de `curated_dbx_compute_warehouses` garde sa ligne
        avec `warehouse_name` a NULL -- la jointure enrichit, elle ne filtre
        pas, et aucune valeur de repli n'est fabriquee ici (le repli sur l'id
        est une decision d'affichage, cote IHM).
      - `running_hours` : nombre d'heures ou le warehouse etait allume ce
        jour-la. Reconstruit a partir des evenements `STARTING`/`STOPPED`
        (marqueur `STARTING` retenu plutot que `RUNNING` parce qu'il borne le
        debut REEL de l'allumage, rampe de demarrage comprise ; `RUNNING` est
        bien journalise en serverless -- 55 886 evenements sur 393 warehouses
        mesures le 2026-09-10 -- contrairement a ce qu'affirmait la version
        precedente de cette docstring) : chaque `STARTING`
        ouvre une session fermee par le prochain `STOPPED` du meme
        warehouse ; les `STARTING` consecutifs sans `STOPPED` entre eux sont
        dedupliques (`LAG`/`LEAD` sur la sous-sequence STARTING/STOPPED) pour
        ne garder que le premier de la serie. Une session sans `STOPPED`
        visible est consideree encore ouverte, sa fin bornee a
        `current_timestamp()`. Un `STOPPED` sans aucun evenement precedent
        (`prev_event_type IS NULL`, session deja ouverte avant le debut de
        la fenetre lue, au-dela de `WAREHOUSE_SESSION_LOOKBACK_DAYS`) ouvre
        une session implicite a minuit du jour de ce `STOPPED`
        (`implicit_opening_sessions`) plutot que d'etre perdu -- limite de
        retention non contournable pour les jours precedents, mais evite un
        `idle_pct` negatif sur le jour de cloture. Chaque session est
        ensuite decoupee par jour calendaire traverse (`LATERAL VIEW explode(sequence(...))`,
        `GREATEST`/`LEAST`) pour n'attribuer a chaque jour que sa fraction
        d'heures reelle, plutot que la duree totale au seul jour de depart --
        necessaire pour les sessions a cheval sur plusieurs jours. Le tampon
        de lecture `WAREHOUSE_SESSION_LOOKBACK_DAYS` (30 jours avant
        `lower_bound`) garantit que le `STARTING` d'une session encore
        ouverte reste visible meme s'il precede la fenetre incrementale.
      - `active_query_hours` : duree reelle (fractionnaire) ou au moins une
        requete tournait sur ce warehouse. Calculee par balayage
        (sweep-line) sur les intervalles `[start_time, end_time)` de chaque
        requete (partage avec `peak_concurrency`, cf.
        `concurrency_events`/`concurrency_running`) : union des intervalles,
        sans double-compter les chevauchements, mesuree dans la meme unite
        (heures reelles) que `running_hours`. Une requete avec `end_time`
        NULL et un `start_time` recent
        (`WAREHOUSE_QUERY_STILL_RUNNING_MAX_HOURS`, 24h) est consideree
        encore en cours (`end_time` coalesce a `current_timestamp()`) ; au-
        dela de ce seuil, la ligne est exclue du balayage (donnee orpheline,
        cf. `query_history_filtered`). Chaque requete est d'abord decoupee
        par jour calendaire traverse (`query_history_by_day`, meme principe
        que `running_sessions_by_day` : `LATERAL VIEW
        explode(sequence(...))` + `GREATEST`/`LEAST` bornant chaque segment
        aux limites `[jour 00:00:00, jour+1 00:00:00)`) AVANT d'alimenter le
        balayage, afin qu'une requete a cheval sur minuit ne contribue a
        `active_query_hours`/`peak_concurrency` que pour la fraction de sa
        duree reellement ecoulee dans chaque jour traverse. La lecture de
        `query_history` est bornee a `WAREHOUSE_QUERY_HISTORY_LOOKBACK_DAYS`
        (1 jour) avant `lower_bound` pour que la portion d'une requete
        demarree la veille et se terminant dans la fenetre lue reste prise
        en compte.
      - `idle_pct` : part du temps allume sans requete active. Formule :
        `(running_hours - active_query_hours) / NULLIF(running_hours, 0) *
        100`. NULL si `is_serverless` : l'idle d'un warehouse serverless n'est
        pas un gaspillage mais son mode de fonctionnement, et il n'est pas
        facture (cf. entete de module).
      - `active_to_running_ratio` : part du temps allume reellement exploite.
        Formule : `active_query_hours / NULLIF(running_hours, 0)`. NULL si
        `is_serverless`, meme raison qu'`idle_pct`.
      - `auto_stop_minutes`/`has_auto_stop` : configuration d'auto-arret du
        warehouse au dernier etat connu du jour agrege (meme CTE
        `warehouses_as_of` et donc meme borne `change_time < period_start +
        1 jour` que `warehouse_name`). Formule : `has_auto_stop =
        auto_stop_minutes > 0`. NULL si `is_serverless` : l'auto-arret y est
        gere par la plateforme et n'est pas un levier d'economie actionnable --
        renvoyer `has_auto_stop = false` declencherait une recommandation
        « auto-stop manquant » sans objet (cf. `recommendations.py`).
      - `scale_up_events`/`scale_down_events` : nombre d'evenements de mise a
        l'echelle ce jour-la (`WAREHOUSE_SCALE_UP_EVENTS`/
        `WAREHOUSE_SCALE_DOWN_EVENTS`).
      - `avg_cluster_count`/`max_cluster_count` : taille du warehouse
        observee sur la journee (moyenne et pic de `cluster_count`).
      - `peak_concurrency` : nombre maximum de requetes executees
        simultanement dans la journee. Meme balayage que
        `active_query_hours` : chaque requete emet +1 a `start_time` et -1 a
        `end_time`, la somme cumulee triee par instant donne la concurrence
        courante, dont on retient le maximum -- evite un self-join O(n^2)
        qui ne passe pas a l'echelle sur plusieurs mois d'historique.
      - `utilization_status` : diagnostic de dimensionnement. `'OVER'`
        (surdimensionne) si `idle_pct > idle_pct_over_threshold` ; `'UNDER'`
        (sous-dimensionne) si `peak_concurrency >= max_clusters *
        peak_concurrency_under_ratio` ; sinon `'OPTIMAL'`. NULL si
        `is_serverless` : sans levier de dimensionnement au temps allume, le
        verdict n'a pas de sens (353 des 398 warehouses serverless seraient
        marques `OVER` a tort).
      - `rightsizing_reco` : recommandation lisible d'ajustement, derivee de
        `utilization_status`. NULL si `is_serverless` (aucune action a
        recommander sur ce levier).
      - `estimated_savings_usd` : economie estimee en dollars si la
        recommandation est appliquee, seulement quand `utilization_status =
        'OVER'`. Formule : `cost_usd * idle_pct / 100` (part du cout
        attribuable au temps idle). NULL si `is_serverless` : cette part
        n'existe pas en serverless, ou la facturation suit le compute des
        requetes et non le temps allume -- ~49 100 $ sur 15 j (~98 k$/30 j,
        AWS) d'economies irrealisables etaient affichees avant cette regle.
    """
    # Tampon avant `lower_bound` pour voir le `STARTING` d'une session encore
    # ouverte qui precederait la fenetre incrementale ; `query_history` et la
    # sortie restent bornes a `lower_bound` (cf. docstring ci-dessus).
    session_lookback_lower_bound = (
        lower_bound - timedelta(days=WAREHOUSE_SESSION_LOOKBACK_DAYS)
        if lower_bound is not None
        else None
    )
    # Tampon avant `lower_bound` pour ne pas perdre la fraction (dans la
    # fenetre lue) d'une requete demarree la veille et a cheval sur minuit ;
    # le decoupage par jour calendaire (`query_history_by_day`) et le filtre
    # de sortie (`output_period_filter`) empechent toute fuite hors fenetre.
    query_lookback_lower_bound = (
        lower_bound - timedelta(days=WAREHOUSE_QUERY_HISTORY_LOOKBACK_DAYS)
        if lower_bound is not None
        else None
    )
    events_date_filter = lower_bound_predicate("event_time", session_lookback_lower_bound)
    query_date_filter = lower_bound_predicate("to_date(start_time)", query_lookback_lower_bound)
    output_period_filter = lower_bound_predicate("period_start", lower_bound)
    # Pas de tampon sur la facturation : le discriminant serverless est joint sur
    # le MEME jour que la ligne de sortie, la fenetre de sortie suffit.
    billing_date_filter = lower_bound_predicate("usage_date", lower_bound)
    scale_up_sql = sql_string_list(WAREHOUSE_SCALE_UP_EVENTS)
    scale_down_sql = sql_string_list(WAREHOUSE_SCALE_DOWN_EVENTS)
    query_still_running_max_hours = WAREHOUSE_QUERY_STILL_RUNNING_MAX_HOURS
    query = f"""
    WITH events_filtered AS (
        SELECT
            cloud_provider,
            workspace_id,
            warehouse_id,
            event_type,
            cluster_count,
            event_time,
            to_date(event_time) AS period_start
        FROM {warehouse_events_table}
        WHERE 1 = 1
        {events_date_filter}
    ),
    -- Sous-sequence filtree aux 2 seuls evenements STARTING/STOPPED : STARTING
    -- borne le debut reel de l'allumage (rampe de demarrage comprise), la ou
    -- RUNNING ne marque que le moment ou le warehouse est pret a servir
    -- (cf. docstring de `build_warehouse_utilization_daily`).
    running_stopped_events AS (
        SELECT
            cloud_provider,
            workspace_id,
            warehouse_id,
            event_type,
            event_time,
            period_start
        FROM events_filtered
        WHERE event_type IN ('{WAREHOUSE_STARTING_EVENT}', '{WAREHOUSE_STOPPED_EVENT}')
    ),
    -- Deduplication des STARTING consecutifs (sans STOPPED entre eux) : seul
    -- le PREMIER STARTING d'une serie ininterrompue ouvre une session.
    tagged_events AS (
        SELECT
            *,
            LAG(event_type) OVER (
                PARTITION BY cloud_provider, workspace_id, warehouse_id ORDER BY event_time
            ) AS prev_event_type
        FROM running_stopped_events
    ),
    session_marker_events AS (
        SELECT
            cloud_provider,
            workspace_id,
            warehouse_id,
            event_type,
            event_time,
            period_start
        FROM tagged_events
        WHERE NOT (
            event_type = '{WAREHOUSE_STARTING_EVENT}'
            AND prev_event_type <=> '{WAREHOUSE_STARTING_EVENT}'
        )
    ),
    ordered_events AS (
        SELECT
            *,
            LEAD(event_time) OVER (
                PARTITION BY cloud_provider, workspace_id, warehouse_id ORDER BY event_time
            ) AS next_event_time,
            LEAD(event_type) OVER (
                PARTITION BY cloud_provider, workspace_id, warehouse_id ORDER BY event_time
            ) AS next_event_type
        FROM session_marker_events
    ),
    -- Session implicite pour un STOPPED sans aucun evenement precedent
    -- (`prev_event_type IS NULL`, calcule sur `tagged_events` avant tout
    -- dedup) : ce STOPPED est le tout premier evenement STARTING/STOPPED
    -- jamais capture pour ce warehouse -- la session etait donc deja
    -- ouverte avant le debut de la fenetre lue (limite de retention/
    -- lookback, pas un STARTING manquant par erreur).
    implicit_opening_sessions AS (
        SELECT
            cloud_provider,
            workspace_id,
            warehouse_id,
            CAST(to_date(event_time) AS TIMESTAMP) AS session_start,
            event_time AS session_end
        FROM tagged_events
        WHERE event_type = '{WAREHOUSE_STOPPED_EVENT}'
          AND prev_event_type IS NULL
    ),
    running_sessions AS (
        SELECT
            cloud_provider,
            workspace_id,
            warehouse_id,
            event_time AS session_start,
            CASE
                WHEN next_event_type = '{WAREHOUSE_STOPPED_EVENT}' THEN next_event_time
                ELSE current_timestamp()
            END AS session_end
        FROM ordered_events
        WHERE event_type = '{WAREHOUSE_STARTING_EVENT}'
          AND (
              next_event_type = '{WAREHOUSE_STOPPED_EVENT}'
              OR next_event_type IS NULL
          )
        UNION ALL
        SELECT
            cloud_provider,
            workspace_id,
            warehouse_id,
            session_start,
            session_end
        FROM implicit_opening_sessions
    ),
    -- Decoupe chaque session par jour calendaire traverse : une session qui
    -- chevauche minuit (ou plusieurs jours) est ventilee au prorata du temps
    -- reellement ecoule dans chaque jour (`GREATEST`/`LEAST` bornent la
    -- session aux limites `[jour 00:00:00, jour+1 00:00:00)` de chaque jour
    -- traverse), plutot qu'attribuee en bloc au jour de son `STARTING`.
    running_sessions_by_day AS (
        SELECT
            rs.cloud_provider,
            rs.workspace_id,
            rs.warehouse_id,
            d AS period_start,
            (
                CAST(
                    LEAST(rs.session_end, CAST(d AS TIMESTAMP) + INTERVAL 1 DAY) AS DOUBLE
                )
                - CAST(GREATEST(rs.session_start, CAST(d AS TIMESTAMP)) AS DOUBLE)
            ) / 3600.0 AS session_hours
        FROM running_sessions rs
        LATERAL VIEW explode(
            sequence(to_date(rs.session_start), to_date(rs.session_end))
        ) exploded_days AS d
    ),
    daily_running AS (
        SELECT
            cloud_provider, workspace_id, warehouse_id, period_start,
            SUM(session_hours) AS running_hours
        FROM running_sessions_by_day
        GROUP BY cloud_provider, workspace_id, warehouse_id, period_start
    ),
    daily_scaling AS (
        SELECT
            cloud_provider, workspace_id, warehouse_id, period_start,
            SUM(CASE WHEN event_type IN ({scale_up_sql}) THEN 1 ELSE 0 END) AS scale_up_events,
            SUM(CASE WHEN event_type IN ({scale_down_sql}) THEN 1 ELSE 0 END) AS scale_down_events,
            AVG(cluster_count) AS avg_cluster_count,
            MAX(cluster_count) AS max_cluster_count
        FROM events_filtered
        GROUP BY cloud_provider, workspace_id, warehouse_id, period_start
    ),
    query_history_filtered AS (
        SELECT
            cloud_provider,
            workspace_id,
            compute.warehouse_id AS warehouse_id,
            start_time,
            -- `end_time` NULL plausible (requete encore en cours) coalesce a
            -- `current_timestamp()` (cf. docstring `active_query_hours`) --
            -- le WHERE ci-dessous exclut deja les lignes trop anciennes.
            COALESCE(end_time, current_timestamp()) AS end_time
        FROM {query_history_table}
        WHERE compute.warehouse_id IS NOT NULL
          -- Une requete sans `end_time` est consideree encore en cours
          -- uniquement si son `start_time` est recent
          -- (`WAREHOUSE_QUERY_STILL_RUNNING_MAX_HOURS`) ; au-dela, la ligne
          -- est exclue plutot que coalescee (cf. docstring `active_query_hours`).
          AND (
              end_time IS NOT NULL
              OR start_time >= current_timestamp() - INTERVAL {query_still_running_max_hours} HOURS
          )
        {query_date_filter}
    ),
    -- Decoupe chaque requete par jour calendaire traverse (meme principe que
    -- `running_sessions_by_day`) : une requete a cheval sur minuit n'alimente
    -- le balayage, pour chaque jour, que de la fraction de sa duree
    -- reellement ecoulee ce jour-la (`GREATEST`/`LEAST` bornent le segment
    -- aux limites `[jour 00:00:00, jour+1 00:00:00)`), avec `period_start`
    -- egal au jour traverse.
    query_history_by_day AS (
        SELECT
            qhf.cloud_provider,
            qhf.workspace_id,
            qhf.warehouse_id,
            d AS period_start,
            GREATEST(qhf.start_time, CAST(d AS TIMESTAMP)) AS clipped_start,
            LEAST(qhf.end_time, CAST(d AS TIMESTAMP) + INTERVAL 1 DAY) AS clipped_end
        FROM query_history_filtered qhf
        LATERAL VIEW explode(
            sequence(to_date(qhf.start_time), to_date(qhf.end_time))
        ) exploded_days AS d
    ),
    -- Balayage (sweep-line) partage par `active_query_hours` et
    -- `peak_concurrency` : chaque segment quotidien emet un evenement +1 a
    -- `clipped_start` et -1 a `clipped_end` -- evite un self-join O(n^2) par
    -- chevauchement d'intervalle, qui ne passe pas a l'echelle sur plusieurs
    -- mois d'historique. A egalite d'instant, une fin (-1) est traitee AVANT
    -- un debut (+1) via `ORDER BY ts, delta` (delta = -1 < +1) : deux
    -- requetes qui se touchent exactement (fin de l'une = debut de l'autre)
    -- ne comptent jamais comme simultanees.
    concurrency_events AS (
        SELECT
            cloud_provider, workspace_id, warehouse_id, period_start,
            clipped_start AS ts, 1 AS delta
        FROM query_history_by_day
        UNION ALL
        SELECT
            cloud_provider, workspace_id, warehouse_id, period_start,
            clipped_end AS ts, -1 AS delta
        FROM query_history_by_day
    ),
    -- `concurrency` = nombre de requetes actives juste apres cette ligne,
    -- jusqu'a `next_ts` (evenement suivant du meme warehouse/jour). Sert a
    -- la fois a `peak_concurrency` (MAX) et `active_query_hours` (somme des
    -- segments `[ts, next_ts)` ou `concurrency > 0`, cf. CTE suivante).
    concurrency_running AS (
        SELECT
            cloud_provider, workspace_id, warehouse_id, period_start,
            ts,
            SUM(delta) OVER (
                PARTITION BY cloud_provider, workspace_id, warehouse_id, period_start
                ORDER BY ts, delta
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) AS concurrency,
            LEAD(ts) OVER (
                PARTITION BY cloud_provider, workspace_id, warehouse_id, period_start
                ORDER BY ts, delta
            ) AS next_ts
        FROM concurrency_events
    ),
    peak_concurrency AS (
        SELECT
            cloud_provider, workspace_id, warehouse_id, period_start,
            MAX(concurrency) AS peak_concurrency
        FROM concurrency_running
        GROUP BY cloud_provider, workspace_id, warehouse_id, period_start
    ),
    -- `active_query_hours` : duree reelle (union d'intervalles, pas de
    -- double-comptage des chevauchements) ou au moins une requete est
    -- active. Somme des segments `[ts, next_ts)` dont la concurrence est
    -- strictement positive, convertie en heures.
    active_query_hours AS (
        SELECT
            cloud_provider, workspace_id, warehouse_id, period_start,
            SUM(
                CASE
                    WHEN concurrency > 0 AND next_ts IS NOT NULL
                        THEN (CAST(next_ts AS DOUBLE) - CAST(ts AS DOUBLE)) / 3600.0
                    ELSE 0
                END
            ) AS active_query_hours
        FROM concurrency_running
        GROUP BY cloud_provider, workspace_id, warehouse_id, period_start
    ),
    -- Discriminant serverless du JOUR, lu sur la facturation : c'est la forme
    -- reellement facturee, seule source d'autorite (un meme warehouse_id peut
    -- changer de forme au fil de l'historique -- 68 cas mesures en dev). `MAX`
    -- sur un jour qui melange les deux formes (63 cas) : serverless l'emporte,
    -- pour ne jamais afficher une economie non encaissable.
    billing_serverless_by_day AS (
        SELECT
            cloud_provider,
            workspace_id,
            usage_metadata.warehouse_id AS warehouse_id,
            usage_date AS period_start,
            MAX(CASE WHEN product_features.is_serverless THEN 1 ELSE 0 END) = 1 AS is_serverless
        FROM {billing_usage_table}
        WHERE usage_metadata.warehouse_id IS NOT NULL
          AND product_features.is_serverless IS NOT NULL
        {billing_date_filter}
        GROUP BY cloud_provider, workspace_id, usage_metadata.warehouse_id, usage_date
    ),
    warehouses_as_of AS (
        SELECT
            r.cloud_provider,
            r.workspace_id,
            r.warehouse_id,
            r.period_start,
            w.warehouse_name,
            w.auto_stop_minutes,
            w.max_clusters,
            w.warehouse_type
        FROM daily_running r
        LEFT JOIN {warehouses_table} w
          ON w.cloud_provider = r.cloud_provider
         AND w.workspace_id = r.workspace_id
         AND w.warehouse_id = r.warehouse_id
         AND w.change_time < r.period_start + INTERVAL 1 DAY
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY r.cloud_provider, r.workspace_id, r.warehouse_id, r.period_start
            ORDER BY w.change_time DESC
        ) = 1
    ),
    enriched AS (
        SELECT
            dr.cloud_provider,
            dr.workspace_id,
            dr.warehouse_id,
            dr.period_start,
            dr.running_hours,
            COALESCE(aqh.active_query_hours, 0) AS active_query_hours,
            wa.warehouse_name,
            wa.auto_stop_minutes,
            wa.max_clusters,
            COALESCE(ds.scale_up_events, 0) AS scale_up_events,
            COALESCE(ds.scale_down_events, 0) AS scale_down_events,
            ds.avg_cluster_count,
            ds.max_cluster_count,
            pc.peak_concurrency,
            cd.cost_usd,
            -- Type declare BRUT, alias explicite : il n'est pas servi tel quel en
            -- sortie (il y est d'abord aligne sur `is_serverless`, cf. le SELECT
            -- final). Deux noms distincts pour deux valeurs distinctes.
            wa.warehouse_type AS declared_warehouse_type,
            -- Cascade facturation -> type declare -> `false`, jamais NULL : un
            -- NULL ici se lirait comme une donnee manquante alors que la
            -- question a toujours une reponse (cf. docstring `is_serverless`).
            COALESCE(
                bs.is_serverless,
                wa.warehouse_type = '{WAREHOUSE_TYPE_SERVERLESS}',
                false
            ) AS is_serverless
        FROM daily_running dr
        LEFT JOIN active_query_hours aqh
          ON aqh.cloud_provider = dr.cloud_provider
         AND aqh.workspace_id = dr.workspace_id
         AND aqh.warehouse_id = dr.warehouse_id
         AND aqh.period_start = dr.period_start
        LEFT JOIN warehouses_as_of wa
          ON wa.cloud_provider = dr.cloud_provider
         AND wa.workspace_id = dr.workspace_id
         AND wa.warehouse_id = dr.warehouse_id
         AND wa.period_start = dr.period_start
        LEFT JOIN daily_scaling ds
          ON ds.cloud_provider = dr.cloud_provider
         AND ds.workspace_id = dr.workspace_id
         AND ds.warehouse_id = dr.warehouse_id
         AND ds.period_start = dr.period_start
        LEFT JOIN peak_concurrency pc
          ON pc.cloud_provider = dr.cloud_provider
         AND pc.workspace_id = dr.workspace_id
         AND pc.warehouse_id = dr.warehouse_id
         AND pc.period_start = dr.period_start
        LEFT JOIN {cost_daily_table} cd
          ON cd.cloud_provider = dr.cloud_provider
         AND cd.workspace_id = dr.workspace_id
         AND cd.warehouse_id = dr.warehouse_id
         AND cd.period_start = dr.period_start
        LEFT JOIN billing_serverless_by_day bs
          ON bs.cloud_provider = dr.cloud_provider
         AND bs.workspace_id = dr.workspace_id
         AND bs.warehouse_id = dr.warehouse_id
         AND bs.period_start = dr.period_start
    ),
    with_metrics AS (
        SELECT
            e.*,
            (e.running_hours - e.active_query_hours) / NULLIF(e.running_hours, 0) * 100
                AS idle_pct,
            e.active_query_hours / NULLIF(e.running_hours, 0) AS active_to_running_ratio
        FROM enriched e
    )
    SELECT
        cloud_provider,
        workspace_id,
        warehouse_id,
        period_start,
        warehouse_name,
        is_serverless,
        -- Type declare, ce que le booleen ci-dessus ne peut pas dire (il ne
        -- distingue pas PRO de CLASSIC). L'ORDRE DES BRANCHES EST LA REGLE :
        -- `is_serverless` gagne toujours (il est lu sur la facturation, et le
        -- backend y adosse la suppression des economies non encaissables), et un
        -- type declare SERVERLESS dementi par la facturation vaut NULL plutot
        -- qu'un PRO/CLASSIC invente. NE PAS reordonner, ne pas servir le type
        -- declare brut (cf. docstring `warehouse_type` pour les cas mesures).
        CASE
            WHEN is_serverless THEN '{WAREHOUSE_TYPE_SERVERLESS}'
            WHEN declared_warehouse_type = '{WAREHOUSE_TYPE_SERVERLESS}' THEN NULL
            ELSE declared_warehouse_type
        END AS warehouse_type,
        -- Metriques d'activite : justes dans les deux mondes, toujours servies.
        running_hours,
        active_query_hours,
        -- Diagnostic d'efficience : SANS OBJET en serverless (facturation au
        -- compute des requetes, pas au temps allume) -> NULL plutot qu'un
        -- verdict faux. NE PAS retirer ces gardes sans retirer aussi
        -- `is_serverless` : l'IHM et `recommendations.py` s'appuient sur le
        -- couple (NULL + raison) pour afficher « non applicable ».
        CASE WHEN is_serverless THEN NULL ELSE idle_pct END AS idle_pct,
        CASE
            WHEN is_serverless THEN NULL
            ELSE active_to_running_ratio
        END AS active_to_running_ratio,
        CASE WHEN is_serverless THEN NULL ELSE auto_stop_minutes END AS auto_stop_minutes,
        CASE WHEN is_serverless THEN NULL ELSE auto_stop_minutes > 0 END AS has_auto_stop,
        scale_up_events,
        scale_down_events,
        avg_cluster_count,
        max_cluster_count,
        peak_concurrency,
        CASE
            WHEN is_serverless THEN NULL
            WHEN idle_pct > {idle_pct_over_threshold} THEN 'OVER'
            WHEN peak_concurrency >= max_clusters * {peak_concurrency_under_ratio} THEN 'UNDER'
            ELSE 'OPTIMAL'
        END AS utilization_status,
        CASE
            WHEN is_serverless THEN NULL
            WHEN idle_pct > {idle_pct_over_threshold}
                THEN 'Reduire la taille du warehouse ou activer l''auto-stop'
            WHEN peak_concurrency >= max_clusters * {peak_concurrency_under_ratio}
                THEN 'Augmenter max_clusters pour absorber les pics de concurrence'
            ELSE 'Dimensionnement optimal, aucune action requise'
        END AS rightsizing_reco,
        CASE
            WHEN is_serverless THEN NULL
            WHEN idle_pct > {idle_pct_over_threshold} THEN cost_usd * idle_pct / 100
            ELSE NULL
        END AS estimated_savings_usd,
        current_timestamp() AS _generated_at
    FROM with_metrics
    WHERE 1 = 1
    {output_period_filter}
    """
    return spark.sql(query)
