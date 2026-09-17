"""Agregation gold `gold_dbx_usage_table_catalog` — registre/fraicheur (T003).

Grain : `(cloud_provider, catalog, schema, table_name)` — snapshot complet,
TOUJOURS recalcule en entier (pas de fenetre incrementale, meme pattern que
`gold_dbx_compute.cluster_governance`).

Sources :
  1. `curated_dbx_uc_tables` (miroir de `system.information_schema.tables`) :
     grain, `table_type`, `created`, `created_by`, `last_altered`.
  2. `curated_dbx_uc_table_tags` (miroir de `system.information_schema.table_tags`)
     : pivot `owner`/`domain`/`cost_center`/`classification`/`is_data_product`
     par match EXACT sur `tag_name`.
  3. `curated_dbx_uc_table_operations` (`system.access.audit` filtre sur
     `ACCESS_AUDIT_WRITE_ACTIONS`) : derniere operation connue. L'identifiant de
     table s'extrait par branche selon `action_name` et non via
     `split_full_name` -- `createTable` porte `catalog_name`/`schema_name`/`name`
     la ou `deleteTable`/`updateTables` portent `full_name_arg`, une ligne de
     partage que ce helper n'exprime pas (cf. `ephemeral_tables.table_operations_cte`).
  4. `curated_dbx_access_table_lineage` cote CIBLE, joint a
     `curated_dbx_query_history` par `statement_id` : quelle table un statement a
     ecrite, et combien de lignes il y a ecrit (`written_rows`).
  5. `gold_dbx_usage_table_daily` (meme job, en amont via `depends_on`) :
     `last_read_at` = `MAX(last_used_at)`, tous consommateurs et jours confondus.

UNE TABLE EPHEMERE N'EST PAS UNE TABLE SUPPRIMEE. Une table dont l'audit a vu la
naissance et la mort a moins de `EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS` d'intervalle
n'obtient AUCUNE ligne ici -- ni `DELETED`, ni `UNKNOWN`, ni rien : elle n'a jamais ete
un objet gouverne, seulement un intermediaire d'execution (cf. la CTE `deleted_only`).
Sa naissance vient de l'audit et non du referentiel : une table supprimee n'a plus de
ligne dans `curated_dbx_uc_tables`, donc plus de `created`.

CE FILTRE NE SUFFIT PAS SEUL. Il n'ecrit plus de ligne d'ephemere, mais il ne retire rien
de ce qui est deja ecrit -- ni le stock des runs anterieurs, ni la ligne `ACTIVE` d'une
table qu'un run a vue VIVANTE entre son `createTable` et son `deleteTable`, entree par le
referentiel sans passer par `deleted_only`. C'est le role de
`ephemeral_tables.purge_ephemeral_rows`, appelee apres l'ecriture, dont le predicat est le
complement strict de celui-ci (cf. `LIVED_LONG_ENOUGH_PREDICATE` et
`WAS_EPHEMERAL_PREDICATE`, definis une seule fois pour les cinq tables concernees).

DERNIERE ECRITURE ET DERNIERE OPERATION SONT DEUX CHOSES, et deux sources distinctes.
`last_write_at` vient du lineage qualifie par `written_rows` : une ecriture prouvee.
`last_operation_at` vient de l'audit et date le dernier evenement quel qu'il soit,
`createTable` et `deleteTable` compris. L'audit ne peut pas prouver une ecriture -- il
journalise des appels d'API Unity Catalog, sans compteur de lignes -- donc il ne sert
jamais a `last_write_at`. `freshness_basis` dit lequel des deux signaux a produit
`freshness_lag_hours` (cf. `FRESHNESS_BASIS_*`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelines.gold_dbx_usage.ephemeral_tables import (
    CREATED_EVENT_AT_EXPR,
    DELETE_TABLE_ACTION,
    LAST_OPERATION_AT_EXPR,
    LIVED_LONG_ENOUGH_PREDICATE,
    table_operations_cte,
)
from pipelines.gold_dbx_usage.sql_helpers import (
    FRESHNESS_BASIS_LINEAGE_WRITE,
    FRESHNESS_BASIS_TABLE_ALTERED,
    LIFECYCLE_STATE_ACTIVE,
    LIFECYCLE_STATE_DELETED,
    LIFECYCLE_STATE_UNKNOWN,
    LINEAGE_WRITTEN_OBJECT_TYPES,
    sql_string_list,
)

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession


def build_table_catalog(
    spark: SparkSession,
    *,
    uc_tables_table: str,
    uc_table_tags_table: str,
    table_operations_table: str,
    lineage_table: str,
    query_history_table: str,
    table_daily_table: str,
) -> DataFrame:
    """Construit `gold_dbx_usage_table_catalog`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        uc_tables_table: nom qualifie de `curated_dbx_uc_tables`.
        uc_table_tags_table: nom qualifie de `curated_dbx_uc_table_tags`.
        table_operations_table: nom qualifie de `curated_dbx_uc_table_operations`
            (calcul de `last_operation*` et d'une des deux preuves d'ecriture).
        lineage_table: nom qualifie de `curated_dbx_access_table_lineage`
            (cote CIBLE : quelle table un statement a ecrite).
        query_history_table: nom qualifie de `curated_dbx_query_history`
            (`written_rows`, joint au lineage par `statement_id`).
        table_daily_table: nom qualifie de `gold_dbx_usage_table_daily`
            (calcul de `last_read_at`).

    Returns:
        Le DataFrame `gold_dbx_usage_table_catalog` resultant.

    Colonnes derivees :
      - `last_write_at` = ecriture prouvee, cote cible du lineage qualifie par
        `written_rows` (cf. la CTE `lineage_writes`). Une cible de lineage seule ne
        prouve rien : c'est le noeud aval d'une arete, qu'une lecture a travers une
        vue produit aussi. `NULL` quand aucune ecriture n'est prouvee, notamment sur
        les vues, dont la fraicheur est celle de leurs tables sous-jacentes.
      - `last_operation` = `max_by(action_name, event_time)` et `last_operation_at`
        = `MAX(event_time)` sur les TROIS actions d'audit : la derniere operation
        connue, ecriture ou non. `last_operation` est exposee brute.
      - `last_operation_by` = email de l'utilisateur, nom du principal de service
        a defaut, `NULL` si aucune identite n'est capturee.
      - `freshness_lag_hours` se replie sur `last_altered_at` quand aucune ecriture
        n'est prouvee, et `freshness_basis` nomme le signal retenu : les deux ne
        valent pas la meme preuve (cf. `FRESHNESS_BASIS_*`). NULL seulement si les
        deux manquent, jamais une valeur inventee.
      - `is_data_product` : vrai des qu'un tag `data_product` existe pour la
        table, quelle que soit sa valeur -- seule la presence compte.
    """
    written_object_types_sql = sql_string_list(LINEAGE_WRITTEN_OBJECT_TYPES)
    query = f"""
    WITH base AS (
        SELECT
            cloud_provider,
            table_catalog AS catalog,
            table_schema AS schema,
            table_name,
            table_type,
            created AS created_at,
            created_by,
            last_altered AS last_altered_at
        FROM {uc_tables_table}
    ),
    tags AS (
        SELECT
            cloud_provider,
            catalog_name AS catalog,
            schema_name AS schema,
            table_name,
            MAX(CASE WHEN tag_name = 'owner' THEN tag_value END) AS owner,
            MAX(CASE WHEN tag_name = 'domain' THEN tag_value END) AS domain,
            MAX(CASE WHEN tag_name = 'cost_center' THEN tag_value END) AS cost_center,
            MAX(CASE WHEN tag_name = 'classification' THEN tag_value END) AS classification,
            MAX(CASE WHEN tag_name = 'data_product' THEN 1 ELSE 0 END) = 1
                AS is_data_product
        FROM {uc_table_tags_table}
        GROUP BY cloud_provider, catalog_name, schema_name, table_name
    ),
    table_operations AS (
{table_operations_cte(table_operations_table, indent="        ", extra_columns=("user_identity",))}
    ),
    last_operation AS (
        SELECT
            cloud_provider,
            catalog,
            schema,
            table_name,
            MAX_BY(action_name, event_time) AS last_operation,
            -- « Derniere operation », jamais « derniere ecriture » : ce MAX porte les 3
            -- actions, dont `createTable`/`deleteTable` qui datent la declaration ou la
            -- suppression au catalogue sans qu'une ligne soit ecrite. `last_write_at` se
            -- calcule ailleurs, sur une preuve d'ecriture (cf. `lineage_writes`).
            {LAST_OPERATION_AT_EXPR},
            -- Naissance vue par l'AUDIT, a ne pas confondre avec `created_at`, qui vient
            -- du referentiel et reste la seule date de creation publiee. Celle-ci ne sert
            -- qu'a mesurer la duree de vie dans `deleted_only` : une table supprimee n'a
            -- plus de ligne au referentiel, donc plus de `created` a comparer.
            {CREATED_EVENT_AT_EXPR},
            MAX_BY(COALESCE(user_identity.email, user_identity.subject_name), event_time)
                AS last_operation_by
        FROM table_operations
        GROUP BY cloud_provider, catalog, schema, table_name
    ),
    deleted_only AS (
        -- Une table supprimee n'a plus AUCUNE ligne source : elle a disparu de
        -- `curated_dbx_uc_tables` (full load purge) et `merge_into_table` ne supprime
        -- jamais de ligne cible. Sans ce squelette, une table deja connue garderait
        -- `is_deleted = false` pour toujours, et une table jamais vue n'apparaitrait
        -- jamais. Effet de bord voulu : l'etat `DELETED` une fois ecrit survit a la
        -- sortie de l'evenement d'audit de la fenetre de retention.
        --
        -- D'ou le filtre de DUREE DE VIE : sans lui cet effet de bord accumule sans borne
        -- des lignes pour des objets qui n'ont jamais existe pour personne, et cette
        -- accumulation degrade toute anti-appartenance calculee sur le registre
        -- (spec 024, FR-024). Le predicat est en POSITIF, « garder si la vie a dure » --
        -- voir `LIVED_LONG_ENOUGH_PREDICATE` pour pourquoi ce n'est pas un `NOT (...)`.
        --
        -- Ce filtre ne suffit pas a lui seul : une table qu'un run a vue VIVANTE a deja
        -- sa ligne, que ce `WHERE` ne peut plus retirer. C'est le role de
        -- `ephemeral_tables.purge_ephemeral_rows`, apres l'ecriture.
        SELECT lo.cloud_provider, lo.catalog, lo.schema, lo.table_name
        FROM last_operation lo
        LEFT ANTI JOIN base b
          ON b.cloud_provider = lo.cloud_provider AND b.catalog = lo.catalog
         AND b.schema = lo.schema AND b.table_name = lo.table_name
        WHERE lo.last_operation = '{DELETE_TABLE_ACTION}'
          AND (
              {LIVED_LONG_ENOUGH_PREDICATE}
          )
    ),
    socle AS (
        -- `present_in_referential` est porte par la ligne plutot que recalcule en aval :
        -- c'est la branche d'origine qui le sait, et un EXISTS refait apres l'union
        -- relirait le referentiel une seconde fois pour la meme reponse.
        SELECT
            cloud_provider,
            catalog,
            schema,
            table_name,
            table_type,
            created_at,
            created_by,
            last_altered_at,
            true AS present_in_referential
        FROM base
        UNION ALL
        SELECT
            cloud_provider,
            catalog,
            schema,
            table_name,
            CAST(NULL AS STRING) AS table_type,
            CAST(NULL AS TIMESTAMP) AS created_at,
            CAST(NULL AS STRING) AS created_by,
            CAST(NULL AS TIMESTAMP) AS last_altered_at,
            false AS present_in_referential
        FROM deleted_only
    ),
    lineage_writes AS (
        -- Preuve d'ecriture par le nombre de lignes ecrites. Le cote CIBLE du lineage
        -- designe le noeud AVAL d'une arete, pas la table ecrite : lire une table a
        -- travers une vue produit l'arete « table source -> vue », dont la cible est la
        -- vue. Trois conditions rendent la cible interpretable comme une ecriture.
        --
        -- 1. `target_type` porteur de donnees. `VIEW` et `METRIC_VIEW` sont exclus : ils
        --    n'ont pas de contenu propre, leur fraicheur est celle de leurs tables
        --    sous-jacentes, et leur cible ne vient que d'une traversee en lecture.
        -- 2. `written_rows > 0` quand `query_history` repond : mesure directe, la seule
        --    de tout le modele. Elle ecarte le `MERGE` qui ne matche rien, le `DELETE`
        --    sans effet et le `CREATE` d'une table vide, tous porteurs d'une cible.
        --    Un `written_rows` NULL est ecarte aussi, le predicat rendant NULL : seule
        --    absence de mesure assimilee a un zero dans le modele, marginale en volume.
        -- 3. Cible acceptee sans mesure quand `query_history` ne repond pas : `PIPELINE`
        --    n'a jamais de `statement_id`, `JOB` rarement, tous deux ecrivant hors
        --    instruction SQL journalisee. Branche DOMINANTE cote ecriture et non cas
        --    residuel -- une valeur `lineage_write` atteste donc qu'un statement a cible
        --    la table, pas qu'une ligne y a ete ecrite.
        --
        -- Aucun filtre de fenetre : cette table gold est un snapshot recalcule en
        -- entier, et borner la lecture ferait regresser une fraicheur deja connue.
        SELECT
            l.cloud_provider,
            l.target_table_catalog AS catalog,
            l.target_table_schema AS schema,
            l.target_table_name AS table_name,
            MAX(l.event_time) AS lineage_write_at
        FROM {lineage_table} l
        LEFT JOIN {query_history_table} q
          ON q.cloud_provider = l.cloud_provider AND q.statement_id = l.statement_id
        WHERE l.target_type IN ({written_object_types_sql})
          AND l.target_table_name IS NOT NULL
          AND (q.written_rows > 0 OR q.statement_id IS NULL)
        GROUP BY
            l.cloud_provider, l.target_table_catalog, l.target_table_schema,
            l.target_table_name
    ),
    last_read AS (
        SELECT
            cloud_provider,
            catalog,
            schema,
            table_name,
            MAX(last_used_at) AS last_read_at
        FROM {table_daily_table}
        GROUP BY cloud_provider, catalog, schema, table_name
    ),
    joined AS (
        -- Les colonnes derivees sont calculees APRES cette CTE et non dedans : SQL
        -- n'autorise pas a reutiliser un alias dans le SELECT qui le definit, et
        -- `last_write_at` sert trois fois en aval. L'ecrire une seule fois empeche que
        -- la valeur publiee, l'anciennete et la base annoncee divergent.
        SELECT
            b.cloud_provider,
            b.catalog,
            b.schema,
            b.table_name,
            b.table_type,
            b.created_at,
            b.created_by,
            b.last_altered_at,
            b.present_in_referential,
            t.owner,
            t.domain,
            t.cost_center,
            t.classification,
            t.is_data_product,
            lo.last_operation,
            lo.last_operation_at,
            lo.last_operation_by,
            lw.lineage_write_at AS last_write_at,
            lr.last_read_at
        FROM socle b
        LEFT JOIN tags t
          ON t.cloud_provider = b.cloud_provider AND t.catalog = b.catalog
         AND t.schema = b.schema AND t.table_name = b.table_name
        LEFT JOIN last_operation lo
          ON lo.cloud_provider = b.cloud_provider AND lo.catalog = b.catalog
         AND lo.schema = b.schema AND lo.table_name = b.table_name
        LEFT JOIN lineage_writes lw
          ON lw.cloud_provider = b.cloud_provider AND lw.catalog = b.catalog
         AND lw.schema = b.schema AND lw.table_name = b.table_name
        LEFT JOIN last_read lr
          ON lr.cloud_provider = b.cloud_provider AND lr.catalog = b.catalog
         AND lr.schema = b.schema AND lr.table_name = b.table_name
    ),
    with_lifecycle AS (
        -- L'etat est derive dans sa propre CTE parce qu'il sert TROIS fois en aval
        -- (l'etat lui-meme, `is_deleted`, `deleted_at`) : SQL n'autorise pas a
        -- reutiliser un alias dans le SELECT qui le definit, et trois copies du meme
        -- `CASE` finiraient par diverger.
        SELECT
            *,
            CASE
                WHEN present_in_referential THEN '{LIFECYCLE_STATE_ACTIVE}'
                WHEN last_operation = '{DELETE_TABLE_ACTION}' THEN '{LIFECYCLE_STATE_DELETED}'
                ELSE '{LIFECYCLE_STATE_UNKNOWN}'
            END AS lifecycle_state
        FROM joined
    )
    SELECT
        cloud_provider,
        catalog,
        schema,
        table_name,
        concat_ws('.', catalog, schema, table_name) AS table_full_name,
        table_type,
        owner,
        domain,
        cost_center,
        classification,
        COALESCE(is_data_product, false) AS is_data_product,
        created_at,
        created_by,
        last_write_at,
        last_operation,
        last_operation_at,
        last_operation_by,
        last_altered_at,
        last_read_at,
        lifecycle_state,
        -- Non-NULL par construction : le `CASE` amont a un `ELSE`, donc l'egalite ne
        -- rend jamais NULL. Un `NOT is_deleted` en aval ne peut pas filtrer en silence.
        lifecycle_state = '{LIFECYCLE_STATE_DELETED}' AS is_deleted,
        CASE WHEN lifecycle_state = '{LIFECYCLE_STATE_DELETED}' THEN last_operation_at END
            AS deleted_at,
        -- Le `CASE` reproduit terme par terme le `COALESCE` ci-dessous : desynchroniser
        -- les deux annoncerait une base autre que celle dont la valeur a ete retenue.
        CASE
            WHEN last_write_at IS NOT NULL THEN '{FRESHNESS_BASIS_LINEAGE_WRITE}'
            WHEN last_altered_at IS NOT NULL THEN '{FRESHNESS_BASIS_TABLE_ALTERED}'
        END AS freshness_basis,
        -- Repli sur `last_altered_at` : sans lui l'anciennete reste NULL sur la majorite
        -- du catalogue, et `is_stale_but_consumed` se tait sur des tables pourtant lues.
        -- `freshness_basis` dit quand ce repli a servi.
        (unix_timestamp(current_timestamp())
            - unix_timestamp(COALESCE(last_write_at, last_altered_at))) / 3600
            AS freshness_lag_hours,
        current_timestamp() AS _generated_at
    FROM with_lifecycle
    """
    return spark.sql(query)
