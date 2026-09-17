"""Agregation gold `gold_dbx_compute_recommendations` (socle reactif).

Rule engine transverse : evalue les 10 regles de seuil de
`compute_datamapping.md` §4.1 sur les tables gold `*_rolling` (fenetre 30 j,
cf. `RECOMMENDATIONS_ROLLING_WINDOW_DAYS`) et le snapshot `governance` deja
calculees (T002/T003), clusters ET warehouses, et produit un fait actionnable
unifie avec cycle de vie `OPEN` -> `RESOLVED` (`recommendation_id` stable sur
toute la duree de vie de l'anomalie, dedoublonnage par priorite quand
plusieurs regles partagent une categorie - la regle active peut donc changer
sous une identite stable, et la charge utile de la ligne suit la regle du jour,
jamais l'identite : cf. l'invariant « le chiffre suit la regle » dans
`build_compute_recommendations`, et `_existing_state_cte`). Alimente le suivi
reactif FinOps/Gouvernance/Fiabilite des clusters et warehouses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.specs import (
    RECOMMENDATIONS_ROLLING_WINDOW_DAYS,
    WAREHOUSE_FAILURE_RATE_PCT_THRESHOLD,
    WAREHOUSE_QUEUE_TIME_P95_THRESHOLD_MS,
    WAREHOUSE_SPILL_QUERY_COUNT_THRESHOLD,
)

if TYPE_CHECKING:
    from datetime import date

    from pyspark.sql import DataFrame, SparkSession

# Schema (types) de `gold_dbx_compute_recommendations`, hors cles/derivees
# (`recommendation_id`, `mode`, `status`, `_generated_at`) : reutilise pour
# fabriquer une source "existante" vide et typee au tout premier run (aucune
# table cible a lire), cf. `_existing_state_cte`.
_EXISTING_STATE_NULL_COLUMNS = (
    ("cloud_provider", "STRING"),
    ("workspace_id", "STRING"),
    ("object_type", "STRING"),
    ("object_id", "STRING"),
    ("object_name", "STRING"),
    ("category", "STRING"),
    ("title", "STRING"),
    ("detail", "STRING"),
    ("recommended_action", "STRING"),
    ("estimated_savings_usd", "DOUBLE"),
    ("severity", "STRING"),
    ("personas", "ARRAY<STRING>"),
    ("first_seen_date", "DATE"),
    ("last_seen_date", "DATE"),
)


def _existing_state_cte(recommendations_table: str, table_exists: bool) -> str:
    """CTE `existing` : dernier etat connu par cle metier, ou vide (1er run).

    Ce builder gere/ecrit les DEUX types d'objet (`CLUSTER` et `WAREHOUSE`) :
    lit donc l'integralite de l'etat existant, sans filtre `object_type`.

    Filtre `status IN ('OPEN', 'ACK')` : une ligne `RESOLVED` ne doit PAS
    etre retrouvee par la jointure sur cle metier de `merged`, sinon sa
    `first_seen_date` d'origine serait reprise si l'anomalie se redeclenche
    des mois/annees plus tard, contredisant le
    principe de "nouvelle detection apres resolution" (cf. docstring
    module). Consequence acceptee : l'ancienne ligne `RESOLVED` n'est plus
    jamais reecrite par un run ulterieur (elle reste figee en base tant
    qu'aucune reouverture ne cree une nouvelle ligne a cote).
    """
    if table_exists:
        source = f"SELECT * FROM {recommendations_table} WHERE status IN ('OPEN', 'ACK')"
    else:
        null_columns = ", ".join(
            f"CAST(NULL AS {sql_type}) AS {name}" for name, sql_type in _EXISTING_STATE_NULL_COLUMNS
        )
        source = f"SELECT {null_columns} WHERE 1 = 0"
    return f"existing AS (\n    {source}\n)"


def _latest_rolling_cte(cte_name: str, rolling_table: str, rolling_window_days: int) -> str:
    """CTE `latest_*` : le DERNIER snapshot de la fenetre, pas tous les snapshots.

    `WHERE window_days = N` ne suffit PAS a designer « le dernier » : les tables
    `*_rolling` portent une ligne par `as_of_date` de run, et `as_of_date` n'est
    dans AUCUNE de leurs cles de merge (ex.
    `WAREHOUSE_UTILIZATION_ROLLING_MERGE_KEYS` = cloud_provider, workspace_id,
    warehouse_id, window_days). Ce sont donc des snapshots d'etat courant : des
    que le run du jour ne produit plus une cle (objet sorti du perimetre,
    warehouse supprime), la ligne de la veille survit telle quelle avec son
    ancien `as_of_date` -- le MERGE ne supprime pas ce qu'il ne voit plus.

    Mesure en dev au moment du correctif : 13 459 recommandations `OPEN` etaient
    portees par des snapshots perimes (13 440 auto-terminaison cluster, 8
    rightsizing warehouse, 6 rightsizing cluster, 4 auto-stop warehouse, 1 taux
    d'echec) et transitionnent en `RESOLVED`.

    Sans ce filtre, le rule engine evaluait ses regles sur ces lignes perimees :
    un objet disparu continuait a generer des recommandations `OPEN` au lieu de
    transitionner en `RESOLVED` (ce que fait `merged` des qu'il ne sort plus de
    `candidates`), et sur les lignes anterieures a l'introduction de
    `is_serverless` la colonne vaut NULL, donc « classique », donc les gardes
    serverless de la regle auto-stop ne s'y appliquaient pas.

    Meme garde que la couche API (`compute_metrics_common._window_where`,
    parametre `latest_snapshot_table`), et volontairement sous la meme forme :
    le `MAX` porte sur TOUTE la table, pas sur la seule fenetre lue. Un `MAX`
    par `window_days` ressusciterait les lignes perimees d'une fenetre dont la
    population courante est vide, et ferait diverger le snapshot juge « courant »
    par le rule engine de celui affiche par l'API — une reco doit designer la
    ligne que l'utilisateur voit. Un run ecrit un seul `as_of_date` pour ses
    quatre fenetres, donc la forme globale ne perd rien.
    """
    return (
        f"{cte_name} AS (\n"
        f"        SELECT * FROM {rolling_table}\n"
        f"        WHERE window_days = {rolling_window_days}\n"
        f"          AND as_of_date = (SELECT MAX(as_of_date) FROM {rolling_table})\n"
        f"    )"
    )


def build_compute_recommendations(
    spark: SparkSession,
    *,
    cluster_efficiency_rolling_table: str,
    cluster_reliability_rolling_table: str,
    governance_table: str,
    cluster_cost_rolling_table: str,
    warehouse_utilization_rolling_table: str,
    warehouse_query_performance_rolling_table: str,
    warehouse_cost_rolling_table: str,
    recommendations_table: str,
    generated_date: date,
    rolling_window_days: int = RECOMMENDATIONS_ROLLING_WINDOW_DAYS,
) -> DataFrame:
    """Construit `gold_dbx_compute_recommendations` (clusters + warehouses).

    Args:
        spark: session Spark utilisee pour executer la requete generee (et
            verifier l'existence de `recommendations_table` : premiere ecriture
            ou etat a faire evoluer, cf. `_existing_state_cte`).
        cluster_efficiency_rolling_table: nom qualifie de
            `gold_dbx_compute_cluster_efficiency_rolling` (regles RIGHTSIZING/
            FINOPS zombie).
        cluster_reliability_rolling_table: nom qualifie de
            `gold_dbx_compute_cluster_reliability_rolling` (regle FINOPS
            auto-termination).
        governance_table: nom qualifie de
            `gold_dbx_compute_cluster_governance` (regles GOVERNANCE tags/DBR
            uniquement - `object_name` des regles RIGHTSIZING/FINOPS cluster
            vient directement de `latest_efficiency`/`latest_reliability`,
            deja porteuses de `cluster_name`) - snapshot,
            aucune variante rolling (etat courant, pas une metrique
            agregeable sur fenetre).
        cluster_cost_rolling_table: nom qualifie de
            `gold_dbx_compute_cluster_cost_rolling` (cout somme sur la fenetre,
            pour l'estimation d'economie de la regle zombie).
        warehouse_utilization_rolling_table: nom qualifie de
            `gold_dbx_compute_warehouse_utilization_rolling` (regles
            RIGHTSIZING/FINOPS auto-stop du warehouse).
        warehouse_query_performance_rolling_table: nom qualifie de
            `gold_dbx_compute_warehouse_query_performance_rolling` (regles
            RIGHTSIZING queue time/spill et RELIABILITY failure rate).
        warehouse_cost_rolling_table: nom qualifie de
            `gold_dbx_compute_warehouse_cost_rolling` (cout somme sur la
            fenetre pour l'estimation d'economie de la regle auto-stop, et
            `warehouse_name` pour `object_name`).
        recommendations_table: nom qualifie de la table CIBLE
            `gold_dbx_compute_recommendations` elle-meme - lue (pas ecrite ici)
            pour retrouver l'etat existant (`first_seen_date`, anomalies
            precedemment `OPEN` a transitionner en `RESOLVED`).
        generated_date: date du run (utilisee comme `first_seen_date`/
            `last_seen_date` pour les anomalies nouvellement/toujours
            detectees ; jamais utilisee telle quelle dans `recommendation_id`,
            cf. docstring module).
        rolling_window_days: fenetre glissante (jours) lue dans les tables
            `*_rolling` (`WHERE window_days = ...`). 30 par defaut
            (`RECOMMENDATIONS_ROLLING_WINDOW_DAYS`) : signal soutenu, pas un
            jour isole (cf. constante dans `specs.py`).

    Returns:
        Le DataFrame de `gold_dbx_compute_recommendations` (nouvelles,
        toujours ouvertes, ou nouvellement resolues, clusters ET warehouses) -
        a passer a `merge_into_table` (cle `recommendation_id`).

    Regles couvertes (cf. `compute_datamapping.md` §4.1) :
      - RIGHTSIZING (MEDIUM) : `efficiency.utilization_status = 'OVER'`
        (cluster, priorite 1) ; sinon `utilization.utilization_status =
        'OVER'` (warehouse, priorite 2) ; sinon `queue_time_p95_ms > seuil`
        (warehouse, priorite 3) ; sinon `spill_query_count > seuil`
        (warehouse, priorite 4) - au plus UNE ligne RIGHTSIZING par objet
        (cf. docstring module "Dedoublonnage").
      - FINOPS (HIGH) : `efficiency.is_zombie = true` (cluster, priorite 1) ;
        sinon `reliability.has_auto_termination = false` (cluster, priorite
        2) ; sinon `utilization.has_auto_stop = false` ET NON serverless
        (warehouse, priorite 3) - au plus UNE ligne FINOPS par objet.

    Les deux regles portant sur les warehouses surdimensionnes ne concernent que
    le compute classique / pro : la table d'utilisation met `utilization_status`
    et `has_auto_stop` a NULL sur les lignes serverless (aucun levier
    d'economie au temps allume, cf. `warehouse_utilization_daily`). La regle
    RIGHTSIZING se desactive d'elle-meme (`= 'OVER'` est faux sur un NULL) ; la
    regle FINOPS auto-stop demande un garde explicite, son `COALESCE(...,
    false)` transformant sinon le NULL en « auto-stop absent ».
      - GOVERNANCE (LOW puis HIGH, cluster ALL_PURPOSE uniquement) :
        `governance.has_owner_tag = false` (ou `has_cost_center_tag = false`)
        en priorite, sinon `governance.dbr_is_lts_current = false` - meme
        ordre de priorite que `cluster_governance.recommended_action`. Les deux
        regles sont filtrees sur `governance.governance_applies` (cf.
        `cluster_governance`).
      - RELIABILITY (HIGH, warehouse uniquement) : `failure_rate_pct > seuil`.

    Invariant « le chiffre suit la regle » : au sein d'une meme identite
    `(objet, categorie)` - celle que porte `recommendation_id` et sur laquelle
    joint `merged` - la regle ACTIVE peut changer d'un run a l'autre, puisque le
    `QUALIFY ... ORDER BY rule_priority` n'en retient qu'une et que la plus
    prioritaire peut cesser de se declencher. La charge utile de la ligne
    (`title`, `detail`, `recommended_action`, `estimated_savings_usd`,
    `severity`, `personas`) appartient donc a la REGLE et jamais a l'identite :
    des qu'un candidat existe aujourd'hui, `merged` prend TOUS ces champs chez
    lui, NULL compris (`CASE WHEN c.object_id IS NOT NULL`, jamais
    `COALESCE(c.x, ex.x)` qui ferait remonter la valeur de la regle de la veille
    sous le libelle de celle du jour). Seul `object_name` continue d'heriter de
    l'etat existant : propriete de l'objet, pas de la regle.

    Mesure en dev au moment du correctif (2026-09-10) : **72 lignes portaient
    27 116,40 $** herites d'une autre regle que celle affichee, sous un titre
    dont la regle declare `CAST(NULL AS DOUBLE)` - la ligne conseillait une
    chose et en chiffrait une autre. Deux categories, deux fois le meme
    mecanisme :

    * RIGHTSIZING, 64 lignes / 27 104,74 $ - le passage en serverless a mis
      `utilization_status` a NULL sur les 1 935 lignes serverless de
      `warehouse_utilization_rolling`, la priorite 2 (`= 'OVER'`) a cesse de se
      declencher et les priorites 3 et 4 (queue-time, spill) ont pris le relais
      sur les memes cles ;
    * FINOPS, 8 lignes / 11,66 $ - priorite 1 (`Cluster zombie`, qui calcule un
      chiffre) relayee par la priorite 2 (`Auto-terminaison manquante`, qui
      declare NULL). Verifie par time travel : a v5 et v12 ces 8
      `recommendation_id` portaient le titre `Cluster zombie` avec ces 11,66 $,
      legitimes a ce moment-la ; a v20 le titre a change et le chiffre est
      reste.

    La seconde categorie est la raison de ne pas s'arreter a la regle qui a
    rendu le defaut visible : le mecanisme est celui du `merged`, pas celui du
    serverless. Deux colonnes seulement pouvaient
    reellement traverser (`estimated_savings_usd`, et `detail` dont le `concat`
    rend NULL des qu'un argument est NULL - ex. `dbr_version` NULL sur la regle
    DBR obsolete, cf. `test_dbr_lts_rule_treats_null_as_non_conformant`) ; les
    quatre autres sont des litteraux non nuls cote candidat, donc le `CASE` y
    est un no-op, pris pour que l'invariant soit structurel plutot qu'a
    re-verifier colonne par colonne a chaque nouvelle regle.

    `object_name` (regles CLUSTER) est resolu depuis `latest_efficiency`/
    `latest_reliability` (`cluster_name`, deja porte par ces tables `*_rolling`),
    plus depuis `governance` pour les regles GOVERNANCE elles-memes - jamais via
    une jointure `governance` annexe : son perimetre est borne par
    `GOVERNANCE_ACTIVITY_WINDOW_DAYS`, plus etroit que celui des `*_rolling`,
    ce qui produisait un `object_name` NULL pour tout cluster hors de ce
    perimetre. `object_name` (regles WAREHOUSE) suit la meme
    logique : resolu depuis `latest_warehouse_utilization`/
    `latest_warehouse_query_performance` (`warehouse_name`, deja porte par ces
    tables `*_rolling`) - jamais via la jointure `latest_warehouse_cost`, dont
    le perimetre (source billing) peut ne pas couvrir un warehouse actif au
    sens utilisation/queue/erreurs mais sans activite de cout/DBU sur la
    fenetre, meme cause racine que le bug CLUSTER ci-dessus, decouverte
    ensuite sur les warehouses.

    Cycle de vie (`status`) : un objet present dans `existing` (etat
    `OPEN`/`ACK`) mais dont plus aucune regle ne se declenche aujourd'hui
    transitionne en `RESOLVED` (sa ligne est reecrite avec `status =
    'RESOLVED'`, `last_seen_date` inchangee - dernier jour ou l'anomalie a
    ete reellement observee). `_existing_state_cte` filtre `existing` sur
    `status IN ('OPEN', 'ACK')` : une ligne
    `RESOLVED` n'est donc plus jamais retrouvee par la jointure sur cle
    metier du CTE `merged`. Un objet qui redeclenche une regle apres
    resolution est ainsi traite comme une VRAIE nouvelle detection (nouveau
    `first_seen_date` = date du run, nouveau `recommendation_id`) : une
    seconde ligne est INSEREE a cote de l'ancienne, qui reste `RESOLVED` et
    figee en base. Ce module ne supprime rien lui-meme : l'expiration des lignes
    qu'il ne produit plus (resolues lors d'un run precedent, objets disparus) est
    portee par l'ecriture, via
    `RECOMMENDATIONS_SPEC.absent_row_delete_guard` (retention
    `RECOMMENDATIONS_RESOLVED_RETENTION_DAYS` jours apres `last_seen_date`).
    """
    existing_cte = _existing_state_cte(
        recommendations_table, spark.catalog.tableExists(recommendations_table)
    )
    generated_date_sql = f"DATE '{generated_date.isoformat()}'"
    # `governance` est le seul snapshot lu sans filtre de recence : il n'a pas de
    # notion de fenetre/`as_of_date` et se purge lui-meme a l'ecriture
    # (`CLUSTER_GOVERNANCE_SPEC.absent_row_delete_guard`), contrairement aux
    # tables `*_rolling` ci-dessus (cf. `_latest_rolling_cte`).
    rolling_ctes = ",\n    ".join(
        _latest_rolling_cte(cte_name, rolling_table, rolling_window_days)
        for cte_name, rolling_table in (
            ("latest_efficiency", cluster_efficiency_rolling_table),
            ("latest_reliability", cluster_reliability_rolling_table),
            ("latest_cost", cluster_cost_rolling_table),
            ("latest_warehouse_utilization", warehouse_utilization_rolling_table),
            ("latest_warehouse_query_performance", warehouse_query_performance_rolling_table),
            ("latest_warehouse_cost", warehouse_cost_rolling_table),
        )
    )
    query = f"""
    WITH {rolling_ctes},
    governance AS (
        SELECT * FROM {governance_table}
    ),
    rightsizing_candidates AS (
        SELECT
            cloud_provider, workspace_id, object_type, object_id, object_name,
            category, severity, title, detail, recommended_action,
            estimated_savings_usd, personas
        FROM (
            SELECT
                e.cloud_provider, e.workspace_id, 'CLUSTER' AS object_type,
                e.cluster_id AS object_id, e.cluster_name AS object_name,
                'RIGHTSIZING' AS category, 'MEDIUM' AS severity,
                'Cluster surdimensionne' AS title,
                CONCAT(
                    'Utilisation CPU p95=', CAST(ROUND(e.cpu_util_p95_pct, 1) AS STRING),
                    '%, memoire p95=', CAST(ROUND(e.mem_util_p95_pct, 1) AS STRING), '%.'
                ) AS detail,
                CONCAT(
                    'Reduire vers ',
                    COALESCE(e.recommended_node_type, 'un type d''instance plus petit')
                ) AS recommended_action,
                e.estimated_savings_usd,
                array('FIN', 'DE') AS personas,
                1 AS rule_priority
            FROM latest_efficiency e
            WHERE e.utilization_status = 'OVER'

            UNION ALL

            SELECT
                u.cloud_provider, u.workspace_id, 'WAREHOUSE' AS object_type,
                u.warehouse_id AS object_id, u.warehouse_name AS object_name,
                'RIGHTSIZING' AS category, 'MEDIUM' AS severity,
                'Warehouse surdimensionne' AS title,
                CONCAT('Temps idle=', CAST(ROUND(u.idle_pct, 1) AS STRING), '%.') AS detail,
                'Reduire la taille du warehouse' AS recommended_action,
                u.estimated_savings_usd,
                array('FIN', 'DE') AS personas,
                2 AS rule_priority
            FROM latest_warehouse_utilization u
            LEFT JOIN latest_warehouse_cost wc
              ON wc.cloud_provider = u.cloud_provider AND wc.workspace_id = u.workspace_id
             AND wc.warehouse_id = u.warehouse_id
            WHERE u.utilization_status = 'OVER'

            UNION ALL

            SELECT
                qp.cloud_provider, qp.workspace_id, 'WAREHOUSE' AS object_type,
                qp.warehouse_id AS object_id, qp.warehouse_name AS object_name,
                'RIGHTSIZING' AS category, 'MEDIUM' AS severity,
                'File d''attente saturee' AS title,
                CONCAT(
                    'Temps d''attente p95=', CAST(ROUND(qp.queue_time_p95_ms, 0) AS STRING), 'ms.'
                ) AS detail,
                'Augmenter max_clusters (scaling)' AS recommended_action,
                CAST(NULL AS DOUBLE) AS estimated_savings_usd,
                array('DE', 'AN') AS personas,
                3 AS rule_priority
            FROM latest_warehouse_query_performance qp
            LEFT JOIN latest_warehouse_cost wc
              ON wc.cloud_provider = qp.cloud_provider AND wc.workspace_id = qp.workspace_id
             AND wc.warehouse_id = qp.warehouse_id
            WHERE qp.queue_time_p95_ms > {WAREHOUSE_QUEUE_TIME_P95_THRESHOLD_MS}

            UNION ALL

            SELECT
                qp.cloud_provider, qp.workspace_id, 'WAREHOUSE' AS object_type,
                qp.warehouse_id AS object_id, qp.warehouse_name AS object_name,
                'RIGHTSIZING' AS category, 'MEDIUM' AS severity,
                'Requetes avec spill disque/memoire' AS title,
                CONCAT(
                    CAST(qp.spill_query_count AS STRING),
                    ' requetes avec spill sur {rolling_window_days} j.'
                ) AS detail,
                'Tuner les requetes ou upsize cible' AS recommended_action,
                CAST(NULL AS DOUBLE) AS estimated_savings_usd,
                array('DE') AS personas,
                4 AS rule_priority
            FROM latest_warehouse_query_performance qp
            LEFT JOIN latest_warehouse_cost wc
              ON wc.cloud_provider = qp.cloud_provider AND wc.workspace_id = qp.workspace_id
             AND wc.warehouse_id = qp.warehouse_id
            WHERE qp.spill_query_count > {WAREHOUSE_SPILL_QUERY_COUNT_THRESHOLD}
        )
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY cloud_provider, workspace_id, object_type, object_id
            ORDER BY rule_priority
        ) = 1
    ),
    finops_candidates AS (
        SELECT
            cloud_provider, workspace_id, object_type, object_id, object_name,
            category, severity, title, detail, recommended_action,
            estimated_savings_usd, personas
        FROM (
            SELECT
                e.cloud_provider, e.workspace_id, 'CLUSTER' AS object_type,
                e.cluster_id AS object_id, e.cluster_name AS object_name,
                'FINOPS' AS category, 'HIGH' AS severity,
                'Cluster zombie' AS title,
                CONCAT(
                    'Allume avec charge quasi nulle (idle=',
                    CAST(ROUND(e.idle_pct, 1) AS STRING), '%).'
                ) AS detail,
                'Eteindre le cluster ou activer l''auto-stop' AS recommended_action,
                ROUND(e.idle_pct / 100.0 * c.cost_usd, 2) AS estimated_savings_usd,
                array('FIN', 'DE') AS personas,
                1 AS rule_priority
            FROM latest_efficiency e
            LEFT JOIN latest_cost c
              ON c.cloud_provider = e.cloud_provider AND c.workspace_id = e.workspace_id
             AND c.cluster_id = e.cluster_id
            WHERE e.is_zombie = true

            UNION ALL

            SELECT
                r.cloud_provider, r.workspace_id, 'CLUSTER' AS object_type,
                r.cluster_id AS object_id, r.cluster_name AS object_name,
                'FINOPS' AS category, 'HIGH' AS severity,
                'Auto-terminaison manquante' AS title,
                'Le cluster n''a pas d''auto-terminaison configuree.' AS detail,
                'Imposer une auto-termination sur le cluster' AS recommended_action,
                CAST(NULL AS DOUBLE) AS estimated_savings_usd,
                array('FIN', 'GOV') AS personas,
                2 AS rule_priority
            FROM latest_reliability r
            WHERE r.has_auto_termination = false

            UNION ALL

            SELECT
                u.cloud_provider, u.workspace_id, 'WAREHOUSE' AS object_type,
                u.warehouse_id AS object_id, u.warehouse_name AS object_name,
                'FINOPS' AS category, 'HIGH' AS severity,
                'Auto-stop manquant' AS title,
                'Le warehouse n''a pas d''auto-stop configure.' AS detail,
                'Activer l''auto-stop sur le warehouse' AS recommended_action,
                ROUND(u.idle_pct / 100.0 * wc.cost_usd, 2) AS estimated_savings_usd,
                array('FIN', 'GOV') AS personas,
                3 AS rule_priority
            FROM latest_warehouse_utilization u
            LEFT JOIN latest_warehouse_cost wc
              ON wc.cloud_provider = u.cloud_provider AND wc.workspace_id = u.workspace_id
             AND wc.warehouse_id = u.warehouse_id
            -- Le garde serverless est INDISPENSABLE ici : la table d'utilisation
            -- met `has_auto_stop` a NULL sur les warehouses serverless (auto-stop
            -- gere par la plateforme), et le `COALESCE(..., false)` ci-dessous le
            -- lirait comme « auto-stop absent » -> une reco HIGH sans objet sur
            -- chaque warehouse serverless. `COALESCE(is_serverless, false)` :
            -- NULL sur les lignes ecrites avant l'introduction de la colonne.
            WHERE COALESCE(u.is_serverless, false) = false
              AND COALESCE(u.has_auto_stop, false) = false
        )
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY cloud_provider, workspace_id, object_type, object_id
            ORDER BY rule_priority
        ) = 1
    ),
    -- `governance_applies` (= cluster ALL_PURPOSE) filtre les deux regles :
    -- les tags et le runtime d'un cluster JOB/PIPELINE viennent de la definition
    -- du job/pipeline, une reco par execution ephemere n'a aucun destinataire.
    -- `COALESCE(..., false)` : la colonne est NULL sur les lignes ecrites avant
    -- son introduction (MERGE WITH SCHEMA EVOLUTION ne remplit pas le passe).
    governance_candidates AS (
        SELECT
            cloud_provider, workspace_id, object_type, object_id, object_name,
            category, severity, title, detail, recommended_action,
            estimated_savings_usd, personas
        FROM (
            SELECT
                cloud_provider, workspace_id, 'CLUSTER' AS object_type,
                cluster_id AS object_id, cluster_name AS object_name,
                'GOVERNANCE' AS category, 'LOW' AS severity,
                'Tags obligatoires manquants' AS title,
                'Le cluster ne porte pas les tags owner et/ou cost_center.' AS detail,
                'Ajouter les tags owner/cost_center manquants' AS recommended_action,
                CAST(NULL AS DOUBLE) AS estimated_savings_usd,
                array('GOV', 'FIN') AS personas,
                1 AS rule_priority
            FROM governance
            WHERE COALESCE(governance_applies, false)
              AND NOT (has_owner_tag AND has_cost_center_tag)

            UNION ALL

            SELECT
                cloud_provider, workspace_id, 'CLUSTER' AS object_type,
                cluster_id AS object_id, cluster_name AS object_name,
                'GOVERNANCE' AS category, 'HIGH' AS severity,
                'Version DBR obsolete' AS title,
                CONCAT('Version DBR actuelle non LTS supportee : ', dbr_version, '.') AS detail,
                'Monter la version DBR vers une LTS supportee' AS recommended_action,
                CAST(NULL AS DOUBLE) AS estimated_savings_usd,
                array('GOV', 'DE') AS personas,
                2 AS rule_priority
            FROM governance
            WHERE COALESCE(governance_applies, false)
              AND NOT COALESCE(dbr_is_lts_current, false)
        )
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY cloud_provider, workspace_id, object_type, object_id
            ORDER BY rule_priority
        ) = 1
    ),
    reliability_candidates AS (
        SELECT
            qp.cloud_provider, qp.workspace_id, 'WAREHOUSE' AS object_type,
            qp.warehouse_id AS object_id, qp.warehouse_name AS object_name,
            'RELIABILITY' AS category, 'HIGH' AS severity,
            'Taux d''echec eleve' AS title,
            CONCAT(
                'Taux d''echec=', CAST(ROUND(qp.failure_rate_pct, 1) AS STRING), '%.'
            ) AS detail,
            'Investiguer les requetes en echec' AS recommended_action,
            CAST(NULL AS DOUBLE) AS estimated_savings_usd,
            array('DE', 'AN') AS personas
        FROM latest_warehouse_query_performance qp
        LEFT JOIN latest_warehouse_cost wc
          ON wc.cloud_provider = qp.cloud_provider AND wc.workspace_id = qp.workspace_id
         AND wc.warehouse_id = qp.warehouse_id
        WHERE qp.failure_rate_pct > {WAREHOUSE_FAILURE_RATE_PCT_THRESHOLD}
    ),
    candidates AS (
        SELECT * FROM rightsizing_candidates
        UNION ALL
        SELECT * FROM finops_candidates
        UNION ALL
        SELECT * FROM governance_candidates
        UNION ALL
        SELECT * FROM reliability_candidates
    ),
    {existing_cte},
    merged AS (
        SELECT
            -- Cles de jointure : le `COALESCE` n'y sert que le cote RESOLVED (aucun
            -- candidat aujourd'hui). Cote apparie, la jointure impose deja
            -- `c.x = ex.x` : aucune valeur ne peut traverser.
            COALESCE(c.cloud_provider, ex.cloud_provider) AS cloud_provider,
            COALESCE(c.workspace_id, ex.workspace_id) AS workspace_id,
            COALESCE(c.object_type, ex.object_type) AS object_type,
            COALESCE(c.object_id, ex.object_id) AS object_id,
            -- Seul champ hors cle a heriter volontairement de `ex` : le nom est une
            -- propriete de l'OBJET (fixe par les cles de jointure), pas de la regle.
            -- L'heritage rattrape donc un nom que la source du jour n'a pas resolu,
            -- sans jamais melanger deux regles.
            COALESCE(c.object_name, ex.object_name) AS object_name,
            COALESCE(c.category, ex.category) AS category,
            'REACTIVE' AS mode,
            -- Charge utile de la REGLE : `CASE` et non `COALESCE(c.x, ex.x)`, meme
            -- forme que `status`/`last_seen_date` ci-dessous. Un candidat du jour
            -- impose TOUS ces champs, NULL compris : la regle active d'une identite
            -- `(objet, categorie)` change d'un run a l'autre, donc un `COALESCE`
            -- afficherait le chiffre de la regle de la veille sous le libelle de
            -- celle du jour (invariant « le chiffre suit la regle » et sa mesure :
            -- cf. docstring de `build_compute_recommendations`).
            CASE WHEN c.object_id IS NOT NULL THEN c.title ELSE ex.title END AS title,
            CASE WHEN c.object_id IS NOT NULL THEN c.detail ELSE ex.detail END AS detail,
            CASE
                WHEN c.object_id IS NOT NULL THEN c.recommended_action
                ELSE ex.recommended_action
            END AS recommended_action,
            CASE
                WHEN c.object_id IS NOT NULL THEN c.estimated_savings_usd
                ELSE ex.estimated_savings_usd
            END AS estimated_savings_usd,
            CASE WHEN c.object_id IS NOT NULL THEN c.severity ELSE ex.severity END AS severity,
            CASE WHEN c.object_id IS NOT NULL THEN c.personas ELSE ex.personas END AS personas,
            CASE WHEN c.object_id IS NOT NULL THEN 'OPEN' ELSE 'RESOLVED' END AS status,
            COALESCE(ex.first_seen_date, {generated_date_sql}) AS first_seen_date,
            CASE
                WHEN c.object_id IS NOT NULL THEN {generated_date_sql}
                ELSE ex.last_seen_date
            END AS last_seen_date
        FROM candidates c
        FULL OUTER JOIN existing ex
          ON ex.cloud_provider = c.cloud_provider AND ex.workspace_id = c.workspace_id
         AND ex.object_type = c.object_type AND ex.object_id = c.object_id
         AND ex.category = c.category
    )
    SELECT
        sha2(
            concat_ws(
                '||', workspace_id, object_type, object_id, category,
                CAST(first_seen_date AS STRING)
            ),
            256
        ) AS recommendation_id,
        cloud_provider, workspace_id, object_type, object_id, object_name,
        category, mode, title, detail, recommended_action, estimated_savings_usd,
        severity, personas, status, first_seen_date, last_seen_date,
        current_timestamp() AS _generated_at
    FROM merged
    """
    return spark.sql(query)

