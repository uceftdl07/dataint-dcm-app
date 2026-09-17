"""Agregation gold `gold_dbx_compute_pipeline_update_stats` (grain execution).

Une ligne par EXECUTION de pipeline DLT/Lakeflow (« update ») : forme de compute,
etat terminal, duree horloge, declencheur, identite d'execution et cible de
performance. C'est la table qui rend comparables les updates serverless et
classiques a l'unite d'oeuvre du produit (une execution), ce que la couche
curated ne peut pas faire : la source est PERIODISEE.

POURQUOI CETTE TABLE EXISTE, ET PAS UNE AGREGATION DANS L'INGESTION
`system.lakeflow.pipeline_update_timeline` publie une ligne par TRANCHE d'etat
d'un update : 422 167 lignes pour 412 350 updates, jusqu'a 12 tranches pour un
seul update (mesures dev du 2026-09-10 sur tout l'historique disponible,
2025-09-08..2026-09-10, compte AWS `dbc-223d60ab-45bd`, 61 workspaces, 13 211
pipelines). Agreger au grain update DANS l'ingestion aurait ete faux pour une
raison mesurable et pas seulement doctrinale : la lecture curated est
incrementale (`DEFAULT_LOOKBACK_DAYS` = 3 jours), or 427 updates (0,104 %) se
terminent un autre jour calendaire que celui ou ils commencent, dont 184
multi-tranches totalisant 3 065,2 h de duree, 40 etales sur 4 jours calendaires
ou plus, le plus long sur 19 jours (448,1 h). Sur ceux-la, un agregat calcule
dans la fenetre de lecture aurait un `MIN(period_start_time)` TRONQUE, et le
MERGE aurait ecrase une ligne correcte par une ligne plus courte — exactement les
updates longs qui font l'interet d'une page d'efficacite. L'ingestion reste donc
fidele source (cf. `pipelines.system_tables.ingest`), et l'agregation vit ici.

Le meme chiffre commande la fenetre de CETTE table : l'entree n'est JAMAIS
bornee, seule la SORTIE l'est (cf. `lower_bound` ci-dessous).

MESURES CITEES : toutes prises en dev le 2026-09-10 sur
`system.lakeflow.pipeline_update_timeline` (source de la curated), sur
l'historique complet disponible 2025-09-08..2026-09-10 sauf fenetre explicitement
indiquee. La source ne conserve qu'environ un an glissant (367 jours entre la
plus ancienne ligne et la mesure) : cette table gold est donc la memoire longue,
la source ne rejouera pas ce qu'elle a expire.

LE PIEGE DE CETTE TABLE : LE TAUX D'ECHEC PAR UPDATE
Un update n'est PAS une demande d'execution. 412 350 updates correspondent a
347 683 `request_id` distincts : 14 056 requetes ont ete retentees, jusqu'a 14
tentatives pour une seule. Compter les echecs par update compte donc les
tentatives, et le serverless retente plus (1,21 update par requete contre 1,07 en
classique). Consequence mesuree sur l'historique complet :

  - par UPDATE : serverless 23,16 % d'echec (78 736 / 339 957) contre classique
    11,52 % (8 337 / 72 388), soit un rapport de 2,01x ;
  - par REQUETE, etat de la DERNIERE tentative : serverless 7,03 %
    (19 700 / 280 178) contre classique 5,19 % (3 504 / 67 505), rapport 1,35x.

La lecture par update SUR-ESTIME donc l'ecart serverless/classique d'un facteur
1,49x. Et sur les 30 derniers jours (2026-08-11..2026-09-10, fenetre posee sur
`update_end_time` — l'axe que filtrera un consommateur) le rapport S'INVERSE :
par update, classique 27,76 % contre serverless 7,18 % ; par requete, 13,24 %
contre 2,02 %. Aucun taux d'echec issu de cette table ne doit donc etre
publie sans sa fenetre. C'est pourquoi `request_id` est une colonne de cette
table et pourquoi son commentaire Unity Catalog porte la requete de
deduplication : le consommateur doit pouvoir corriger sans relire la source.

Ce qui NE s'inverse pas, en revanche, c'est la duree : p50 des updates
`COMPLETED` de 82 s en serverless contre 694 s en classique sur l'historique
complet (8,5x), et 93 s contre 846 s sur les 30 derniers jours (9,1x). Le gain de
latence est robuste au choix de fenetre, l'ecart de fiabilite non.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.sql_helpers import lower_bound_predicate

if TYPE_CHECKING:
    from datetime import date

    from pyspark.sql import DataFrame, SparkSession


def build_pipeline_update_stats(
    spark: SparkSession,
    *,
    pipeline_update_timeline_table: str,
    lower_bound: date | None,
) -> DataFrame:
    """Construit `gold_dbx_compute_pipeline_update_stats`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        pipeline_update_timeline_table: nom qualifie (`catalog.schema.table`) de
            `curated_dbx_lakeflow_pipeline_update_timeline`. La table CURATED, et
            jamais `system.lakeflow.pipeline_update_timeline` : aucun builder gold
            de ce plugin ne lit `system.*` (la couche curated porte
            `cloud_provider`, qui unifie AWS natif et Azure cross-tenant, et le
            backend ne lit que des tables du catalogue applicatif).
        lower_bound: borne basse incluse de la fenetre de REECRITURE, appliquee a
            `update_end_time` (cf. la section fenetre ci-dessous). `None` = tout
            l'historique curated est reecrit (1er run ou `--full-refresh`).

    Returns:
        Le DataFrame `gold_dbx_compute_pipeline_update_stats` resultant.

    FENETRE : L'ENTREE N'EST JAMAIS BORNEE, LA SORTIE L'EST
    `lower_bound` filtre l'AGREGAT deja complet (`WHERE 1 = 1` + filtre de
    sortie, meme gabarit que `pipeline_cost_daily`), pas la lecture curated. Ce
    n'est pas une precaution de style : borner la lecture tronquerait
    `MIN(period_start_time)` pour les 427 updates qui changent de jour calendaire
    en cours de route (40 d'entre eux depassent 4 jours, un atteint 19 jours), et
    le MERGE remplacerait alors une duree correcte par une duree plus courte,
    sans qu'aucune erreur ne soit levee. Le scan curated complet est le prix
    assume de cette exactitude : 422 167 lignes au 2026-09-10 (~1 550 lignes par
    jour de croissance), volume negligeable au regard des autres sources de ce
    plugin. Ce que la fenetre economise est l'ECRITURE : 15 054 updates reecrits
    sur 10 jours contre 412 350 en recalcul complet, soit 27x moins de lignes
    fusionnees par run.

    Le filtre porte sur `update_end_time` et NON sur `update_start_time`, qui est
    le choix naturel et faux : un update commence avant la borne mais termine
    apres resterait fige dans son etat partiel. Mesure du 2026-09-10 sur une
    fenetre de 10 jours : 2 updates sont dans ce cas. `update_end_time` est aussi
    le `watermark_column` de la spec, donc la colonne dont
    `compute_gap_aware_lower_bound` inspecte la couverture — filtre et detection
    de trous partagent le meme axe, et une source `period_end_time` sans aucun
    NULL (mesure : 0 sur 422 167 lignes) garantit qu'aucune ligne n'est invisible
    a cette detection.

    Colonnes et formules (toutes les mesures : dev, 2026-09-10) :
      - `cloud_provider`, `update_id` : CLE DE MERGE, et aussi le `GROUP BY`
        exact. `update_id` est globalement unique — 412 350 ids distincts pour
        412 350 couples `(workspace_id, update_id)` et autant de triplets avec
        `pipeline_id`. Ajouter les deux parents a la cle n'apporterait donc aucun
        pouvoir discriminant, seulement un mode de panne : si le `pipeline_id`
        rattache a un `update_id` changeait, un MERGE sur 4 colonnes INSERERAIT
        un doublon au lieu de mettre a jour, cassant le grain qui est la raison
        d'etre de la table. Grouper sur la cle de merge elle-meme rend cette
        divergence structurellement impossible : une ligne de sortie par cle,
        toujours.
      - `workspace_id`, `pipeline_id` : ATTRIBUTS (`MAX`), pas des cles. Exacts
        par mesure — 0 update sur 412 350 porte plus d'une valeur.
      - `compute_type` = `MAX(compute.type)`, 2 valeurs (`SERVERLESS_COMPUTE`,
        `CLASSIC_COMPUTE`), aucun NULL sur les 422 167 lignes. C'est le
        discriminant central de la page, et il est ici de bien meilleure qualite
        que son equivalent cote jobs : `job_run_timeline.compute_ids` est vide
        ou NULL sur 97,0 % des lignes (6 465 611 / 6 668 284, mesure dev
        2026-09-10) et ne rend de toute facon que des IDENTIFIANTS, pas un
        type — il faut une jointure de plus pour retrouver la forme de compute.
      - `result_state` = `MAX(result_state)`, exact par MESURE et non par
        contrat : 9 817 des 422 167 lignes portent `result_state IS NULL` (les
        tranches intermediaires), l'etat terminal n'est porte que par UNE ligne,
        et 0 update sur 412 350 expose deux etats non-NULL. `MAX()` ignore les
        NULL et rend donc cette unique valeur, sans le cout d'un
        `row_number() OVER (ORDER BY period_start_time DESC)`. SI un jour deux
        etats non-NULL coexistaient, `MAX()` en choisirait un par ordre
        ALPHABETIQUE, en silence : c'est la limite a connaitre.
        Reste NULL pour un update encore en cours au moment du calcul (0 cas
        mesure, mais rien ne l'interdit) — surtout ne pas replier ce NULL sur
        `'UNKNOWN'`, un taux d'echec doit pouvoir l'exclure de son denominateur.
      - `duration_sec` = `unix_timestamp(MAX(period_end_time)) -
        unix_timestamp(MIN(period_start_time))` : duree HORLOGE. Verifie
        equivalent a la somme des tranches (ecart median 0,0 s, p95 0,0 s, 0
        update au-dela de 60 s sur les 9 683 updates multi-tranches) : les
        tranches pavent l'intervalle sans trou. La definition horloge est
        retenue parce qu'elle s'explique en une phrase. Mesure de coherence : 0
        duree negative, 0 NULL, 248 updates a 0 s.
      - `update_start_time` / `update_end_time` : bornes de l'update entier, donc
        `MIN`/`MAX` sur TOUTES ses tranches — c'est precisement ce que la fenetre
        d'entree non bornee protege.
      - `request_id` = `MAX(request_id)`, exact par mesure (0 update sur 412 350
        en porte plus d'un, 0 NULL, 0 chaine vide) et globalement unique lui
        aussi (347 683 valeurs distinctes = autant de triplets avec
        workspace/pipeline). C'est la cle de DEDUPLICATION des retentatives, cf.
        le piege documente dans le docstring du module.
      - `trigger_type`, `update_type`, `run_as_user_name` : attributs `MAX`, 0
        update ambigu. `run_as_user_name` est NULL sur 4 886 lignes source.
      - `performance_target` = `MAX(trigger_details.job_task.performance_target)`
        : NULL sur 100 % des updates classiques et 39,6 % des serverless — ce
        champ n'existe que pour un update declenche par une tache de job. Un
        indicateur construit dessus doit donc rapporter a la population
        renseignee, pas au total.
      - `period_count` = `COUNT(*)` : nombre de tranches source agregees (1 a 12,
        9 683 updates au-dela de 1, soit 2,35 %). Publie pour rendre l'agregation
        AUDITABLE sans relire la curated — `SUM(period_count)` de cette table
        doit egaler le `COUNT(*)` de la curated sur le meme perimetre. C'est le
        seul `COUNT(*)` legitime sur cette source : compter les lignes curated
        pour compter des executions sur-compterait de 9 817 unites.
      - `_generated_at` : horodatage d'ecriture, exige par
        `compute_gap_aware_lower_bound` (detection des jours ecrits trop tot).

    Deliberement ABSENTS, pour que l'omission ne passe pas pour un oubli :
      - `compute.cluster_id` — NULL sur 81,7 % des lignes (le serverless n'a pas
        de cluster) ; le rapprochement cout/efficacite du cote classique passe
        deja par `dlt_pipeline_id` dans `pipeline_efficiency_daily`. Si un besoin
        apparait, `MAX(compute.cluster_id)` est exact (0 update ambigu).
      - `attempt_number` / `is_last_attempt` — derivables en une fenetre sur
        `request_id` cote lecture, mais un rang MATERIALISE deviendrait FAUX en
        silence : la retentative qui arrive apres que la ligne de la tentative
        precedente soit sortie de la fenetre de reecriture ne peut plus la
        corriger. Mesure : 6 requetes etalent leurs tentatives sur 10 jours ou
        plus, jusqu'a 49 jours. Le calcul reste donc a la lecture.
      - les 3 colonnes ARRAY de la source (`refresh_selection`,
        `full_refresh_selection`, `reset_checkpoint_selection`) : vides sur plus
        de 99,8 % des lignes, et sans usage produit a ce jour.
    """
    # Fenetre de REECRITURE, appliquee a la sortie. Meme helper et meme gabarit
    # que `output_period_filter` dans `pipeline_cost_daily` / `serverless_cost_daily`,
    # a une difference pres, et elle est la raison d'etre de cette table : ici
    # AUCUN filtre n'est pose sur la lecture curated (cf. docstring).
    output_window_filter = lower_bound_predicate("update_end_time", lower_bound)
    query = f"""
    WITH per_update AS (
        SELECT
            cloud_provider,
            update_id,
            MAX(workspace_id) AS workspace_id,
            MAX(pipeline_id) AS pipeline_id,
            MAX(compute.type) AS compute_type,
            MAX(result_state) AS result_state,
            unix_timestamp(MAX(period_end_time))
                - unix_timestamp(MIN(period_start_time)) AS duration_sec,
            MIN(period_start_time) AS update_start_time,
            MAX(period_end_time) AS update_end_time,
            MAX(request_id) AS request_id,
            MAX(trigger_type) AS trigger_type,
            MAX(update_type) AS update_type,
            MAX(run_as_user_name) AS run_as_user_name,
            MAX(trigger_details.job_task.performance_target) AS performance_target,
            COUNT(*) AS period_count
        FROM {pipeline_update_timeline_table}
        GROUP BY cloud_provider, update_id
    )
    SELECT
        cloud_provider,
        update_id,
        workspace_id,
        pipeline_id,
        compute_type,
        result_state,
        duration_sec,
        update_start_time,
        update_end_time,
        request_id,
        trigger_type,
        update_type,
        run_as_user_name,
        performance_target,
        period_count,
        current_timestamp() AS _generated_at
    FROM per_update
    WHERE 1 = 1
    {output_window_filter}
    """
    return spark.sql(query)
