"""Agregation gold `gold_dbx_compute_serverless_governance` (snapshot gouvernance).

Etat de gouvernance de la depense SERVERLESS par surface d'usage : part de
dollars refacturable (tag owner, tag centre de cout), part attribuee a une
politique de budget, part rattachee a une identite, dollars sans proprietaire,
dollars sans cle d'objet, et inventaire des politiques de budget qui couvrent la
surface. Alimente la matrice de couverture de la page serverless.

Snapshot BORNE dans le temps (`activity_lower_bound`, cf.
`specs.GOVERNANCE_ACTIVITY_WINDOW_DAYS` = 90 jours), meme gabarit que
`cluster_governance` : recalcul complet a chaque run sur un perimetre borne, les
lignes sorties de la fenetre etant supprimees a l'ecriture (cf.
`SERVERLESS_GOVERNANCE_SPEC.absent_row_delete_guard`) et non ici.

TOUTE mesure citee dans ce module vient de la FENETRE DE REFERENCE
2026-06-12..2026-09-09 (90 jours), catalogue `it` / schema
`ba_data_connect_monitoring__d` en dev, prise le 2026-09-10, BI-CLOUD sauf
mention explicite du cloud (cf.
`specs/025-serverless-compute-page/T001e-baseline-measures.md`) : 1 036 222,34 $
de depense serverless (AWS 767 022,09 $, Azure 269 200,25 $). Cette precision
n'est pas de la ceremonie : sur le MEME perimetre, la part de dollars sans
proprietaire vaut 2,2 % sur 90 jours et 7,22 % sur l'historique complet
(266 421,06 $) -- plus du triple, l'attribution d'identite s'etant nettement
amelioree recemment. Publier l'un pour l'autre est faux. Les reperes de la story
T001 sont eux MONO-CLOUD (aws) et sans fenetre declaree : sa "couverture policy
8,4 % du serverless global" vaut 13,4 % bi-cloud contre 7,6 % sur aws seul, et
son "0,3 % SQL" conflait deux surfaces (`SQL_WAREHOUSE` 0,0 %, `MV_ST_REFRESH`
8,8 % aws / 37,0 % azure).

SOURCE = LES LIGNES DE FACTURATION (`curated_dbx_billing_usage` x
`curated_dbx_billing_list_prices`), et NON
`gold_dbx_compute_serverless_cost_daily` dont cette table partage pourtant le
perimetre exact. Mesure sur la meme fenetre de 31 jours : le cout sans
proprietaire vaut 8 704,20 $ au niveau LIGNE contre 8 605,66 $ au grain
jour-objet du daily. L'ecart de 98,54 $ est exactement l'orphelin
d'`AI_ENDPOINT` : a ce grain, ses lignes sans identite fusionnent avec des lignes
qui en portent une et le groupe entier herite d'un principal. Une table de
gouvernance construite sur le daily SOUS-ESTIME donc structurellement les
orphelins -- d'ou la relecture de la facturation et les CTE non agregees
ci-dessous.

ANTI-DOUBLE-COMPTAGE -- `cost_usd` agrege LES MEMES lignes de facturation que
`serverless_cost_daily`, `cluster_cost_daily`, `job_cluster_cost_daily`,
`pipeline_cost_daily` et `warehouse_cost_daily` : ne jamais sommer cette table
avec elles. La somme des surfaces d'un cloud redonne en revanche exactement la
depense serverless de ce cloud (le `CASE` de surface partitionne les lignes).

LE LEVIER LE PLUS LOURD N'EST PAS DANS LA STORY, et cette table est faite pour
le rendre visible : `SQL_WAREHOUSE` pese 458 205,68 $ sur la fenetre de
reference (44 % du serverless, aws 372 051,29 $ + azure 86 154,39 $) avec 0,0 %
de couverture `budget_policy_id` et 0 politique distincte SUR LES DEUX CLOUDS.
Aucune autre surface ne combine ce poids et cette absence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.specs import COST_CENTER_TAG_KEYS, OWNER_TAG_KEYS
from pipelines.gold_dbx_compute.sql_helpers import (
    SERVERLESS_OBJECT_ID_SENTINEL,
    identity_principal_expr,
    identity_source_expr,
    lower_bound_predicate,
    serverless_object_id_expr,
    serverless_scope_predicate,
    serverless_surface_case_expr,
    tag_present_sql,
)

if TYPE_CHECKING:
    from datetime import date

    from pyspark.sql import DataFrame, SparkSession


def build_serverless_governance(
    spark: SparkSession,
    *,
    billing_usage_table: str,
    billing_list_prices_table: str,
    activity_lower_bound: date,
) -> DataFrame:
    """Construit `gold_dbx_compute_serverless_governance`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        billing_usage_table: nom qualifie (`catalog.schema.table`) de
            `curated_dbx_billing_usage` (source de facturation directe).
        billing_list_prices_table: nom qualifie de
            `curated_dbx_billing_list_prices` (prix effectif).
        activity_lower_bound: borne basse incluse du perimetre : seules les
            lignes facturees a partir de cette date sont evaluees (cf.
            `GOVERNANCE_ACTIVITY_WINDOW_DAYS`). Sur cette table l'activite EST
            la ligne de facturation -- il n'existe pas d'autre signal, le
            serverless n'ayant aucune ligne dans
            `curated_dbx_compute_clusters`.

    Returns:
        Le DataFrame `gold_dbx_compute_serverless_governance` resultant.

    Grain : `(cloud_provider, workspace_id, serverless_surface)` -- etat de
    gouvernance courant, TOUJOURS recalcule en entier (snapshot, pas une serie
    temporelle) sur le perimetre borne par `activity_lower_bound`.
    12 surfaces sont presentes cote aws et 11 cote azure sur la fenetre de
    reference : la seule absente est `OTHER`, coherent avec le classement de
    l'ancien `LAKEHOUSE_MONITORING` en `PLATFORM_AUTO`. Ne JAMAIS exiger
    12 lignes par cloud -- une surface sans ligne facturee n'a pas de ligne ici.

    AUCUNE des cles de merge n'est NULL, et ce n'est pas un detail de style :
    `pipelines.common.writers.merge_into_table` fusionne sur `<=>` null-safe,
    donc une cle NULL ne leve rien -- elle fond silencieusement tout un
    workspace en UNE ligne corrompue. `serverless_surface` est garantie par la
    branche `ELSE 'OTHER'` du `CASE` (cf.
    `sql_helpers.serverless_surface_case_expr`), et 0 ligne du perimetre ne
    porte un `workspace_id` NULL (mesure sur la fenetre de reference). Les
    egalites `=` des jointures finales en dependent.

    Regle de publication des mesures : UN numerateur en dollars par axe, PLUS sa
    part en pourcentage ; le complementaire se soustrait de `cost_usd` et n'est
    PAS publie. Le numerateur retenu est celui que la gouvernance doit lire --
    les dollars COUVERTS pour les tags et les politiques, les dollars ORPHELINS
    pour l'identite (97,8 % de couverture : c'est le residu qui porte
    l'information).

    Champs et formule de calcul :
      - `serverless_surface` : usage derriere la depense (12 valeurs, jamais
        NULL), cf. `sql_helpers.serverless_surface_case_expr` -- y compris le
        controle a rejouer sur `OTHER`.
      - `cost_usd` : `SUM(usage_quantity x effective_price)` sur la fenetre,
        toutes unites de facturation confondues (DBU, GB, HOUR, DSU). C'est le
        denominateur de toutes les parts de cette table.
      - `cost_usd_with_owner_tag` / `owner_tag_coverage_pct` : dollars portant
        une cle de tag `owner` (orthographes de `OWNER_TAG_KEYS`, casse ignoree,
        valeur vide refusee, cf. `sql_helpers.tag_present_sql`). 3,1 % bi-cloud
        (4,0 % aws / 0,6 % azure) : la constante est QUASI AVEUGLE sur le
        serverless, et elle est publiee telle quelle a dessein -- elle est
        partagee avec `cluster_governance`, y ajouter une graphie changerait des
        chiffres de conformite DEJA PUBLIES par cette autre table. Candidats
        mesures et volontairement non retenus : aws `CreatorEmail` 3,7 % et
        `CreateBy` 3,2 % (tags INJECTES par Databricks, les compter gonflerait
        une conformite que personne n'a choisie), azure `AppOwner` 5,3 % et
        `CyberContact` 5,3 % (tags TTE deliberes, a arbitrer separement).
      - `cost_usd_with_cost_center_tag` / `cost_center_tag_coverage_pct` : idem
        pour les cles de `COST_CENTER_TAG_KEYS`. 19,6 % bi-cloud, mais 11,5 %
        aws contre 42,8 % azure : la moyenne bi-cloud ne decrit ni l'un ni
        l'autre.
      - AUCUNE mesure de "au moins un tag" n'est publiee, et c'est un choix
        MESURE, pas un oubli : sur azure la cle plateforme `Environment` est
        presente sur 100,0 % de la depense, donc une couverture booleenne
        afficherait 0 % de non-tague et dirait a FinOps qu'il n'y a rien a faire
        sur azure -- alors que sa meilleure cle METIER plafonne a 60,5 %
        (`AppName`) et que `AppCode` tombe a 12,4 %. Cote aws il n'existe aucune
        etiquette obligatoire equivalente : 151 409,66 $ (54,73 %) n'ont aucun
        tag du tout. Seules des cles NOMMEES sont donc mesurees ici.
      - `cost_usd_with_budget_policy` / `budget_policy_coverage_pct` : dollars
        attribues a une politique de budget (`usage_metadata.budget_policy_id`,
        et NON `usage_policy_id` -- cf. `serverless_cost_daily` : la colonne
        recente perdrait silencieusement 188 744 lignes d'historique). 13,4 %
        bi-cloud (7,6 % aws / 29,8 % azure), et l'ecart entre surfaces est le
        fait marquant : `JOB` 19,6 % aws contre 67,2 % azure, `DLT_PIPELINE`
        43,3 % / 37,0 %, `SQL_WAREHOUSE` 0,0 % sur les deux clouds pour 44 % de
        la depense.
      - `cost_usd_without_identity` / `identity_coverage_pct` : dollars dont la
        facturation ne porte AUCUNE identite, et part inverse. Formule de la
        cascade : `run_as` a defaut `owned_by` a defaut `created_by` (cf.
        `sql_helpers.identity_principal_expr`). 97,8 % de couverture bi-cloud,
        concentree sur deux surfaces : `NETWORKING` 0,0 % (orphelin integral) et
        `LAKEBASE` 5,5 % aws / 0,1 % azure. `AI_ENDPOINT` n'est PAS a 100 %
        (99,6 % aws / 96,8 % azure), contrairement a ce qu'affirme la story.
      - `identity_source_mix` : champs porteurs de l'identite observes sur la
        surface, liste TRIEE ET DEDUPLIQUEE jointe par `+` (ex.
        `NONE+OWNED_BY`), jamais NULL. Le champ porteur CHANGE par surface
        (`SQL_WAREHOUSE` 100 % `OWNED_BY`, `APP` 100 % `CREATED_BY`, jobs et
        notebooks 100 % `RUN_AS`) et "proprietaire" n'est pas "executant" au
        sens de la refacturation : sans cette colonne, une matrice d'attribution
        melangerait les deux semantiques sans le dire. C'est un ENSEMBLE non
        pondere -- le poids des dollars sans identite est dans
        `identity_coverage_pct`, pas ici.
      - `cost_usd_without_object_key` : dollars dont la surface n'expose aucun
        objet listable, donc que la page ne peut rattacher qu'au workspace
        (sentinelle `_NO_OBJECT`, cf. `sql_helpers.serverless_object_id_expr`).
        Mesure de gouvernance a part entiere : ces dollars sont hors de portee
        de toute action par objet, meme quand ils portent un tag et une
        identite.
      - `budget_policy_count` / `budget_policy_inventory` : nombre de politiques
        de budget distinctes attachees a la surface, et leur inventaire
        `array<struct<cost_usd, budget_policy_id>>` trie par cout decroissant.
        L'inventaire NE PORTE PAS DE NOM de politique, et ce n'est pas une
        omission : `system.billing` n'expose que `account_prices`,
        `attributed_usage`, `list_prices` et `usage` -- il n'existe AUCUNE table
        de budget policies, ni en systeme ni en curated. Le decompte
        account-wide se rebatit en explosant l'inventaire (69 politiques
        distinctes sur la fenetre de reference : 49 aws + 20 azure, aucun
        recoupement), ce que `budget_policy_count` ne donne pas -- une meme
        politique peut couvrir plusieurs surfaces. `budget_policy_count` vaut 0
        (et non NULL) quand aucune politique n'est attachee : c'est un fait
        mesure, pas une inconnue ; l'inventaire est alors NULL, sans perte
        d'information.
      - `window_start` / `window_end` : bornes de la mesure. `window_start` est
        la borne DEMANDEE (`activity_lower_bound`) et reste portee par la ligne
        parce qu'un snapshot survit a son run (les lignes absentes ne sont
        supprimees qu'apres un delai de grace) : sans elle, une ligne ecrite par
        un run precedent serait lue avec la fenetre du run courant. `window_end`
        est le dernier jour REELLEMENT facture dans curated POUR CE CLOUD, pas
        la veille du run : le retard d'arrivee de la facturation est de
        3 a 8 jours, et les deux clouds sont deux flux de collecte distincts. Un
        `window_end` nettement plus ancien que d'habitude signale une collecte
        curated en retard, pas une baisse de depense.
    """
    usage_window_filter = lower_bound_predicate("usage_date", activity_lower_bound)
    activity_floor = activity_lower_bound.isoformat()
    query = f"""
    WITH usage_filtered AS (
        SELECT
            cloud_provider,
            workspace_id,
            usage_date,
            sku_name,
            usage_quantity,
            usage_metadata.budget_policy_id AS budget_policy_id,
            {identity_principal_expr()} AS identity_principal,
            {identity_source_expr()} AS identity_source,
            {tag_present_sql("custom_tags", OWNER_TAG_KEYS)} AS has_owner_tag,
            {tag_present_sql("custom_tags", COST_CENTER_TAG_KEYS)} AS has_cost_center_tag,
            {serverless_surface_case_expr()} AS serverless_surface,
            usage_metadata
        FROM {billing_usage_table}
        WHERE {serverless_scope_predicate()}
        {usage_window_filter}
    ),
    keyed AS (
        -- CTE distincte de `usage_filtered` : la cle d'objet DEPEND de la
        -- surface (le champ porteur change par surface), elle ne peut donc pas
        -- se calculer dans le meme SELECT que le CASE qui la produit.
        SELECT
            cloud_provider,
            workspace_id,
            usage_date,
            sku_name,
            usage_quantity,
            budget_policy_id,
            identity_principal,
            identity_source,
            has_owner_tag,
            has_cost_center_tag,
            serverless_surface,
            {serverless_object_id_expr()} AS object_id
        FROM usage_filtered
    ),
    priced AS (
        -- VOLONTAIREMENT NON AGREGEE : toutes les mesures de cette table sont
        -- des parts de DOLLARS evaluees LIGNE A LIGNE. Agreger avant ferait
        -- heriter une identite, un tag ou une policy a des lignes qui n'en
        -- portent pas -- 98,54 $ d'orphelins d'`AI_ENDPOINT` disparaissent ainsi
        -- au grain jour-objet (cf. docstring du module).
        SELECT
            k.cloud_provider,
            k.workspace_id,
            k.serverless_surface,
            k.usage_date,
            k.budget_policy_id,
            k.identity_principal,
            k.identity_source,
            k.has_owner_tag,
            k.has_cost_center_tag,
            k.object_id <> '{SERVERLESS_OBJECT_ID_SENTINEL}' AS has_object_key,
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
         AND lp.price_start_time <= k.usage_date
         AND (lp.price_end_time IS NULL OR k.usage_date < lp.price_end_time)
    ),
    surface_grain AS (
        SELECT
            cloud_provider,
            workspace_id,
            serverless_surface,
            SUM(line_cost_usd) AS cost_usd,
            SUM(CASE WHEN has_owner_tag THEN line_cost_usd ELSE 0 END)
                AS cost_usd_with_owner_tag,
            SUM(CASE WHEN has_cost_center_tag THEN line_cost_usd ELSE 0 END)
                AS cost_usd_with_cost_center_tag,
            SUM(CASE WHEN budget_policy_id IS NOT NULL THEN line_cost_usd ELSE 0 END)
                AS cost_usd_with_budget_policy,
            SUM(CASE WHEN identity_principal IS NULL THEN line_cost_usd ELSE 0 END)
                AS cost_usd_without_identity,
            SUM(CASE WHEN has_object_key THEN 0 ELSE line_cost_usd END)
                AS cost_usd_without_object_key,
            concat_ws('+', sort_array(collect_set(identity_source))) AS identity_source_mix
        FROM priced
        GROUP BY cloud_provider, workspace_id, serverless_surface
    ),
    coverage AS (
        -- Les parts en % se calculent ICI, depuis une source unique, pour que
        -- chacune soit rapportee au cout de LA MEME ligne de grain.
        -- `NULLIF(cost_usd, 0)` rend NULL et non 0 quand la surface n'a coute
        -- 0 $ -- cas reel, le SKU `GENIE_FREE_USAGE` facture des DBU GRATUITS :
        -- une part de dollars n'est pas definie sans dollars, et 0 % affirmerait
        -- a tort "rien n'est couvert".
        SELECT
            *,
            cost_usd_with_owner_tag / NULLIF(cost_usd, 0) * 100 AS owner_tag_coverage_pct,
            cost_usd_with_cost_center_tag / NULLIF(cost_usd, 0) * 100
                AS cost_center_tag_coverage_pct,
            cost_usd_with_budget_policy / NULLIF(cost_usd, 0) * 100
                AS budget_policy_coverage_pct,
            (cost_usd - cost_usd_without_identity) / NULLIF(cost_usd, 0) * 100
                AS identity_coverage_pct
        FROM surface_grain
    ),
    policy_grain AS (
        -- 1er niveau de l'inventaire : le cout PAR POLITIQUE. Un `collect_list`
        -- applique directement a `priced` rendrait une entree par LIGNE DE
        -- FACTURATION (des millions), pas une par politique.
        SELECT
            cloud_provider,
            workspace_id,
            serverless_surface,
            budget_policy_id,
            SUM(line_cost_usd) AS policy_cost_usd
        FROM priced
        WHERE budget_policy_id IS NOT NULL
        GROUP BY cloud_provider, workspace_id, serverless_surface, budget_policy_id
    ),
    policy_inventory AS (
        -- 2e niveau : `COUNT(*)` sur `policy_grain` EST le
        -- `COUNT(DISTINCT budget_policy_id)` de la facturation (une ligne par
        -- politique et par surface).
        -- `sort_array` compare les structs CHAMP PAR CHAMP dans l'ordre de
        -- DECLARATION : la cle de tri doit donc etre le PREMIER champ, d'ou un
        -- schema publie `(cost_usd, budget_policy_id)` et non l'inverse --
        -- permuter les deux champs trierait par identifiant, silencieusement.
        -- Les ex-aequo de cout sont departages par identifiant, ce qui rend
        -- l'ordre du tableau deterministe d'un run a l'autre.
        SELECT
            cloud_provider,
            workspace_id,
            serverless_surface,
            COUNT(*) AS budget_policy_count,
            sort_array(
                collect_list(named_struct('cost_usd', policy_cost_usd,
                                          'budget_policy_id', budget_policy_id)),
                false
            ) AS budget_policy_inventory
        FROM policy_grain
        GROUP BY cloud_provider, workspace_id, serverless_surface
    ),
    measured_window AS (
        -- Borne haute REELLE de la mesure, PAR CLOUD : les deux clouds sont deux
        -- flux de collecte distincts, un MAX global masquerait le retard de l'un
        -- derriere l'avance de l'autre.
        SELECT
            cloud_provider,
            MAX(usage_date) AS window_end
        FROM usage_filtered
        GROUP BY cloud_provider
    )
    SELECT
        c.cloud_provider,
        c.workspace_id,
        c.serverless_surface,
        c.cost_usd,
        c.cost_usd_with_owner_tag,
        c.owner_tag_coverage_pct,
        c.cost_usd_with_cost_center_tag,
        c.cost_center_tag_coverage_pct,
        c.cost_usd_with_budget_policy,
        c.budget_policy_coverage_pct,
        c.cost_usd_without_identity,
        c.identity_coverage_pct,
        c.cost_usd_without_object_key,
        c.identity_source_mix,
        COALESCE(p.budget_policy_count, 0) AS budget_policy_count,
        p.budget_policy_inventory,
        DATE '{activity_floor}' AS window_start,
        w.window_end,
        current_timestamp() AS _generated_at
    FROM coverage c
    LEFT JOIN policy_inventory p
      ON p.cloud_provider = c.cloud_provider
     AND p.workspace_id = c.workspace_id
     AND p.serverless_surface = c.serverless_surface
    LEFT JOIN measured_window w
      ON w.cloud_provider = c.cloud_provider
    """
    return spark.sql(query)
