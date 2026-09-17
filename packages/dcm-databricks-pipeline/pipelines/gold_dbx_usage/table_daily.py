"""Agregation gold `gold_dbx_usage_table_daily` — fait de consommation (T002).

Grain : `(cloud_provider, catalog, schema, table_name, consumer_id, period_start)`.
Succede a `gold_data_product_usage` (route backend `data_product_usage.py`).

Quatre branches, aucune source n'etant suffisante seule : le lineage cote SOURCE
avec `statement_id` (volume/duree/cout via `query_history`) et sans (rien a
joindre), l'audit `getTable` (acces UI/API qu'aucune requete ne trace) et le
lineage cote CIBLE (volumes ecrits seuls, le statement etant deja compte).

Ce que la requete tient pour vrai des sources :
  - `statement_id` est la colonne de jointure vers `query_history` et le seul
    discriminant entre les deux branches de lecture. Ni `entity_type` (dont
    `DBSQL_QUERY` ne couvre qu'une part marginale du lineage) ni `entity_id`
    (espace d'identifiants disjoint) ne peuvent en tenir le role.
  - le volume et la duree ne dependent d'aucun rattachement a la facturation, dont
    seul le COUT depend. Un SQL warehouse se rattache par `compute.warehouse_id` ;
    tout le reste passe par `query_source.job_info.job_id`, `compute.cluster_id`
    restant vide sur la totalite des statements (cf. `COST_BASIS_*`).
  - `access.audit` encode une identite absente par la chaine `'unknown'`, jamais
    par un SQL NULL (cf. `CONSUMER_IDENTITY_ABSENT_LITERALS`).
  - `curated_dbx_uc_tables` est filtree par privilege OBJET PAR OBJET :
    l'absence d'un objet du registre ne prouve pas son inexistence
    (cf. `catalog_resolution_status`).

Regle transverse : `NULL` = « non mesure », `0` = « mesure a zero ». Ne jamais
fabriquer l'un pour l'autre, et ne jamais masquer une jointure cassee par un
`COALESCE(..., 0)`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelines.gold_dbx_usage.ephemeral_tables import (
    ephemeral_keys_cte,
    not_ephemeral_predicate,
)
from pipelines.gold_dbx_usage.sql_helpers import (
    CATALOG_RESOLUTION_NEVER_RESOLVED,
    CATALOG_RESOLUTION_NOT_VISIBLE,
    CATALOG_RESOLUTION_RESOLVED,
    CONSUMER_TYPE_UNKNOWN,
    COST_ATTRIBUTION_EQUAL_PARTS_FALLBACK,
    COST_BASIS_CLUSTER_PRORATA,
    COST_BASIS_MIXED,
    COST_BASIS_SERVERLESS_JOB_PRORATA,
    COST_BASIS_WAREHOUSE_PRORATA,
    LINEAGE_ENTITY_TYPE_QUERY,
    LINEAGE_NAMED_OBJECT_TYPES,
    consumer_type_from_identity,
    decode_consumer_type_priority,
    encode_consumer_type_priority,
    lower_bound_predicate,
    split_full_name,
    sql_string_list,
)

if TYPE_CHECKING:
    from datetime import date

    from pyspark.sql import DataFrame, SparkSession

# Cles candidates de `request_params` portant le nom qualifie de la table pour une
# action `getTable` : `full_name_arg` est celle d'Unity Catalog, `name_arg` un repli
# pour les variantes observees sur d'autres actions UC.
_GET_TABLE_FULL_NAME_EXPR = (
    "COALESCE(request_params['full_name_arg'], request_params['name_arg'])"
)


def build_table_daily(
    spark: SparkSession,
    *,
    lineage_table: str,
    access_audit_table: str,
    query_history_table: str,
    billing_usage_table: str,
    billing_list_prices_table: str,
    uc_tables_table: str,
    table_operations_table: str,
    lower_bound: date | None,
) -> DataFrame:
    """Construit `gold_dbx_usage_table_daily`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        lineage_table: nom qualifie de `curated_dbx_access_table_lineage`.
        access_audit_table: nom qualifie de `curated_dbx_access_audit`.
        query_history_table: nom qualifie de `curated_dbx_query_history`.
        billing_usage_table: nom qualifie de `curated_dbx_billing_usage`.
        billing_list_prices_table: nom qualifie de `curated_dbx_billing_list_prices`.
        uc_tables_table: nom qualifie de `curated_dbx_uc_tables`, registre des
            objets rattaches a un data product.
        table_operations_table: nom qualifie de `curated_dbx_uc_table_operations`
            (preuve d'ephemerite, cf. `ephemeral_tables`).
        lower_bound: borne basse incluse de `period_start` pour la lecture
            incrementale ; `None` pour recalculer l'historique complet.

    Returns:
        Le DataFrame `gold_dbx_usage_table_daily` resultant.

    Attribution du cout et de la duree, en deux etages : le cout quotidien d'un
    SEAU de facturation (`billing_usage` valorise par `billing_list_prices`) est
    reparti entre ses requetes au prorata de `total_duration_ms`, puis chaque
    requete est repartie a PARTS EGALES entre ses tables sources distinctes,
    aucune des deux sources ne portant de volume par table source.

    Trois seaux, disjoints par construction et donc jamais comptes deux fois : le
    warehouse, le cluster, et le job serverless (`usage_metadata.job_id`, sur les
    seules lignes de facture qui n'ont ni cluster ni warehouse). `cost_basis` dit de
    quel seau chaque ligne chiffree tient son cout : les trois ne mesurent pas la
    meme grandeur, et seul le warehouse rend un prorata fidele (cf.
    `COST_BASIS_*`). Un statement sans aucun rattachement reste a
    `estimated_cost_usd` NULL, volume et duree restant renseignes.

    `rows_written`/`data_written_bytes` viennent de `written_rows`/`written_bytes`
    de `query_history`, rattaches a la table CIBLE via le cote `target_*` du
    lineage et repartis a parts egales entre les cibles distinctes du statement.
    """
    # Seule la branche audit parse une chaine : `request_params` ne porte le nom
    # qualifie que concatene. Le lineage, lui, publie les 3 parties en colonnes
    # natives (cf. `lineage_table_reads` / `lineage_table_writes`).
    audit_catalog_expr, audit_schema_expr, audit_table_name_expr = split_full_name(
        _GET_TABLE_FULL_NAME_EXPR
    )
    lineage_date_filter = lower_bound_predicate("event_date", lower_bound)
    audit_date_filter = lower_bound_predicate("event_date", lower_bound)
    query_date_filter = lower_bound_predicate("to_date(start_time)", lower_bound)
    usage_date_filter = lower_bound_predicate("usage_date", lower_bound)
    output_period_filter = lower_bound_predicate("period_start", lower_bound)
    named_object_types_sql = sql_string_list(LINEAGE_NAMED_OBJECT_TYPES)
    # L'identite d'une lecture de requete : `executed_by` de `query.history` quand la
    # requete y est presente, sinon `created_by` du lineage (seule identite dont on
    # dispose hors SQL warehouse). `created_by` pouvant valoir le litteral
    # `'System-User'`, la qualification passe par le helper NULL-safe partage.
    query_consumer_identity = "COALESCE(qc.executed_by, ql.lineage_created_by)"
    consumer_identity_type_expr = consumer_type_from_identity(query_consumer_identity)
    write_consumer_type_expr = consumer_type_from_identity(
        "COALESCE(qw.executed_by, lw.lineage_created_by)"
    )

    ephemeral_keys = ephemeral_keys_cte(
        uc_tables_table=uc_tables_table,
        table_operations_table=table_operations_table,
    )
    not_ephemeral = not_ephemeral_predicate("a")
    query = f"""
    WITH {ephemeral_keys},
    lineage_table_reads AS (
        SELECT
            cloud_provider,
            workspace_id,
            to_date(event_time) AS period_start,
            event_time,
            source_table_full_name,
            -- Colonnes natives, pas un `split(source_table_full_name)` : la source
            -- publie deja les 3 parties, et le parsing casse sur un identifiant
            -- quote contenant un `.` (cf. `split_full_name`, reserve a l'audit).
            source_table_catalog AS catalog,
            source_table_schema AS schema,
            source_table_name AS table_name,
            entity_type,
            entity_id,
            statement_id,
            created_by
        FROM {lineage_table}
        -- Tous les objets UC portant un nom qualifie, pas seulement `TABLE` : une vue
        -- est un objet lu (cf. `LINEAGE_NAMED_OBJECT_TYPES`).
        -- Aucun filtre sur `direct_access` : une lecture de la vue `v` au-dessus de
        -- `t` produit une ligne sur `v` et une ligne indirecte sur `t`, toutes deux
        -- retenues. Le cout a parts egales porte donc sur `v` ET `t` : la part de
        -- `t` baisse, le total par requete est inchange.
        WHERE source_type IN ({named_object_types_sql})
          AND source_table_full_name IS NOT NULL
        {lineage_date_filter}
    ),
    lineage_table_writes AS (
        -- Cote CIBLE : identifie la table ECRITE par un statement, celle a qui les
        -- volumes `written_rows`/`written_bytes` de `query.history` sont rattaches.
        -- Le GROUP BY est structurel : une requete lisant N tables et ecrivant 1
        -- cible produit N lignes portant la MEME cible (fan-in), donc N fois
        -- `written_rows`.
        SELECT
            cloud_provider,
            workspace_id,
            statement_id,
            target_table_full_name,
            target_table_catalog AS catalog,
            target_table_schema AS schema,
            target_table_name AS table_name,
            MIN(to_date(event_time)) AS lineage_period_start,
            MAX(event_time) AS lineage_event_time,
            MAX(created_by) AS lineage_created_by
        FROM {lineage_table}
        -- Discriminant `statement_id`, jamais `entity_type` : une ecriture de job ou
        -- de notebook porte un `statement_id` joignable sans porter `DBSQL_QUERY`.
        WHERE target_type IN ({named_object_types_sql})
          AND target_table_full_name IS NOT NULL
          AND statement_id IS NOT NULL
        {lineage_date_filter}
        GROUP BY
            cloud_provider, workspace_id, statement_id, target_table_full_name,
            target_table_catalog, target_table_schema, target_table_name
    ),
    query_lineage AS (
        -- AGREGAT au grain (statement, table source), pas une projection : la source
        -- porte plusieurs lignes par couple (fan-out des cibles, `event_id` repetable,
        -- expansion de vue). Sans ce GROUP BY toutes les metriques sont multipliees
        -- d'autant -- un INSERT vers 3 cibles compte 3 requetes et 3x son cout. Un
        -- `DISTINCT` ne suffirait pas : il dependrait des colonnes projetees.
        -- Les `lineage_*` sont les replis quand `query.history` n'a pas le statement.
        SELECT
            cloud_provider, workspace_id, statement_id, source_table_full_name,
            catalog, schema, table_name,
            MIN(period_start) AS lineage_period_start,
            MAX(event_time) AS lineage_event_time,
            MAX(created_by) AS lineage_created_by,
            MAX(entity_id) AS lineage_entity_id,
            MAX(entity_type) AS lineage_entity_type
        FROM lineage_table_reads
        -- DISCRIMINANT = `statement_id` : c'est la presence de la colonne de jointure
        -- qui route la ligne, pas un proxy sur le type d'entite.
        WHERE statement_id IS NOT NULL
        GROUP BY
            cloud_provider, workspace_id, statement_id, source_table_full_name,
            catalog, schema, table_name
    ),
    query_table_counts AS (
        SELECT cloud_provider, workspace_id, statement_id,
               COUNT(DISTINCT source_table_full_name) AS n_tables
        FROM query_lineage
        GROUP BY cloud_provider, workspace_id, statement_id
    ),
    query_history_filtered AS (
        -- AUCUN filtre de rattachement : volume et duree sont renseignes independamment
        -- de tout lien vers la facturation. Un `cluster_id IS NOT NULL OR warehouse_id
        -- IS NOT NULL` ecarterait ici pres de la moitie des statements. Le seau n'est
        -- projete que comme PORTE DU COUT : seul le prorata sur la facturation en a
        -- besoin.
        SELECT
            cloud_provider,
            workspace_id,
            statement_id,
            executed_by,
            to_date(start_time) AS period_start,
            start_time,
            -- Le compute dedie prime sur le job : un statement declenche par un job mais
            -- execute sur un warehouse est facture par ce warehouse, la facture
            -- serverless du job ne couvrant que son compute propre. Les deux colonnes
            -- se lisent ensemble -- `cost_basis` discrimine le seau, `cost_bucket_id`
            -- l'identifie dedans -- et le `CASE` suit le `COALESCE` terme par terme :
            -- desynchroniser les deux nommerait un seau autre que celui dont
            -- l'identifiant a ete retenu.
            CASE
                WHEN compute.cluster_id IS NOT NULL
                    THEN '{COST_BASIS_CLUSTER_PRORATA}'
                WHEN compute.warehouse_id IS NOT NULL
                    THEN '{COST_BASIS_WAREHOUSE_PRORATA}'
                WHEN query_source.job_info.job_id IS NOT NULL
                    THEN '{COST_BASIS_SERVERLESS_JOB_PRORATA}'
            END AS cost_basis,
            COALESCE(
                compute.cluster_id, compute.warehouse_id, query_source.job_info.job_id
            ) AS cost_bucket_id,
            execution_status,
            total_duration_ms,
            read_bytes,
            read_rows,
            written_rows,
            written_bytes
        FROM {query_history_table}
        WHERE 1 = 1
        {query_date_filter}
    ),
    cluster_usage AS (
        -- Seau que la source ne permet pas encore de rejoindre : cote facture,
        -- `usage_metadata.cluster_id` est bien rempli, mais cote requete
        -- `compute.cluster_id` est vide sur la TOTALITE des statements -- `query.history`
        -- nomme le type du compute (`CLASSIC_COMPUTE`), pas la ressource. Conserve pour
        -- que le cout des clusters arrive sans redeveloppement si la source publie un
        -- jour cet identifiant (cf. `COST_BASIS_CLUSTER_PRORATA`).
        SELECT
            cloud_provider, workspace_id,
            '{COST_BASIS_CLUSTER_PRORATA}' AS cost_basis,
            usage_metadata.cluster_id AS cost_bucket_id,
            usage_date AS period_start, sku_name, usage_unit, usage_quantity
        FROM {billing_usage_table}
        WHERE usage_metadata.cluster_id IS NOT NULL
        {usage_date_filter}
    ),
    warehouse_usage AS (
        -- Seul seau dont le prorata de duree soit fidele : un SQL warehouse n'execute
        -- que des requetes, donc sa facture ne couvre rien d'autre qu'elles.
        SELECT
            cloud_provider, workspace_id,
            '{COST_BASIS_WAREHOUSE_PRORATA}' AS cost_basis,
            usage_metadata.warehouse_id AS cost_bucket_id,
            usage_date AS period_start, sku_name, usage_unit, usage_quantity
        FROM {billing_usage_table}
        WHERE usage_metadata.warehouse_id IS NOT NULL
        {usage_date_filter}
    ),
    serverless_job_usage AS (
        -- Seul seau rattachable pour tout ce qui n'est pas un SQL warehouse. La
        -- condition d'entree exige l'ABSENCE de cluster et de warehouse : ce seau est
        -- donc disjoint des deux precedents par construction, et aucune ligne de
        -- facture ne peut etre comptee deux fois. `usage_metadata.job_id` est aussi
        -- porte par les lignes de facture d'un job sur cluster, que `cluster_usage`
        -- prend deja -- sans cette exigence, elles entreraient dans deux seaux.
        SELECT
            cloud_provider, workspace_id,
            '{COST_BASIS_SERVERLESS_JOB_PRORATA}' AS cost_basis,
            usage_metadata.job_id AS cost_bucket_id,
            usage_date AS period_start, sku_name, usage_unit, usage_quantity
        FROM {billing_usage_table}
        WHERE usage_metadata.cluster_id IS NULL
          AND usage_metadata.warehouse_id IS NULL
          AND usage_metadata.job_id IS NOT NULL
        {usage_date_filter}
    ),
    billing_buckets AS (
        SELECT * FROM cluster_usage
        UNION ALL
        SELECT * FROM warehouse_usage
        UNION ALL
        SELECT * FROM serverless_job_usage
    ),
    billing_buckets_priced AS (
        SELECT
            u.cloud_provider, u.workspace_id, u.cost_basis, u.cost_bucket_id,
            u.period_start,
            u.usage_quantity * lp.effective_price AS line_cost_usd
        FROM billing_buckets u
        LEFT JOIN (
            SELECT cloud_provider, sku_name, price_start_time, price_end_time,
                   pricing.effective_list.default AS effective_price
            FROM {billing_list_prices_table}
        ) lp
          ON lp.cloud_provider = u.cloud_provider
         AND lp.sku_name = u.sku_name
         AND lp.price_start_time <= u.period_start
         AND (lp.price_end_time IS NULL OR u.period_start < lp.price_end_time)
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY u.cloud_provider, u.workspace_id, u.cost_basis, u.cost_bucket_id,
                         u.period_start, u.sku_name
            ORDER BY lp.price_start_time DESC
        ) = 1
    ),
    bucket_daily_cost AS (
        SELECT
            cloud_provider, workspace_id, cost_basis, cost_bucket_id, period_start,
            SUM(line_cost_usd) AS cost_usd
        FROM billing_buckets_priced
        GROUP BY cloud_provider, workspace_id, cost_basis, cost_bucket_id, period_start
    ),
    bucket_daily_duration AS (
        -- DENOMINATEUR du prorata : la duree de tous les statements du MEME seau ce
        -- jour-la. Les statements sans seau (`cost_bucket_id` NULL) en sont exclus pour
        -- ne pas former un groupe NULL qui gonflerait le denominateur des autres ;
        -- `NULL = NULL` etant faux, leur cout reste NULL dans `query_cost`.
        SELECT cloud_provider, workspace_id, cost_basis, cost_bucket_id, period_start,
               SUM(total_duration_ms) AS total_duration_ms
        FROM query_history_filtered
        WHERE cost_bucket_id IS NOT NULL
        GROUP BY cloud_provider, workspace_id, cost_basis, cost_bucket_id, period_start
    ),
    query_cost AS (
        SELECT
            qh.cloud_provider, qh.workspace_id, qh.statement_id, qh.executed_by,
            qh.period_start, qh.start_time, qh.execution_status, qh.total_duration_ms,
            qh.read_bytes, qh.read_rows, qh.cost_basis,
            qh.total_duration_ms / NULLIF(cdd.total_duration_ms, 0) * cdc.cost_usd
                AS query_cost_usd
        FROM query_history_filtered qh
        -- `cost_basis` fait partie des deux cles de jointure, et pas seulement
        -- `cost_bucket_id` : rien ne garantit qu'un identifiant de job ne collide pas
        -- avec un identifiant de cluster ou de warehouse.
        LEFT JOIN bucket_daily_cost cdc
          ON cdc.cloud_provider = qh.cloud_provider AND cdc.workspace_id = qh.workspace_id
         AND cdc.cost_basis = qh.cost_basis AND cdc.cost_bucket_id = qh.cost_bucket_id
         AND cdc.period_start = qh.period_start
        LEFT JOIN bucket_daily_duration cdd
          ON cdd.cloud_provider = qh.cloud_provider AND cdd.workspace_id = qh.workspace_id
         AND cdd.cost_basis = qh.cost_basis AND cdd.cost_bucket_id = qh.cost_bucket_id
         AND cdd.period_start = qh.period_start
    ),
    query_reads AS (
        -- `period_start` vient de la REQUETE, pas du lineage : `query_lineage` agrege
        -- plusieurs evenements par (statement, source) et n'a donc pas de date unique.
        -- L'ajouter a son GROUP BY produirait un doublon pour un statement dont les
        -- evenements encadrent minuit.
        SELECT
            ql.cloud_provider,
            COALESCE(qc.period_start, ql.lineage_period_start) AS period_start,
            ql.catalog, ql.schema, ql.table_name,
            COALESCE(
                qc.executed_by, ql.lineage_created_by, ql.lineage_entity_id, 'unknown'
            ) AS consumer_id,
            -- `entity_type` prime sur l'identite quand il est renseigne : cette branche
            -- recoit aussi des `JOB`/`NOTEBOOK`/`DASHBOARD_V3`. `DBSQL_QUERY` est
            -- exclu -- hors du vocabulaire publie de la colonne, et le consommateur
            -- d'une requete DBSQL est son auteur.
            CASE
                WHEN ql.lineage_entity_type IS NOT NULL
                     AND ql.lineage_entity_type <> '{LINEAGE_ENTITY_TYPE_QUERY}'
                    THEN ql.lineage_entity_type
                ELSE {consumer_identity_type_expr}
            END AS consumer_type,
            1 AS request_count,
            qc.read_rows / NULLIF(qtc.n_tables, 0) AS rows_read,
            CAST(NULL AS DOUBLE) AS rows_written,
            qc.read_bytes / NULLIF(qtc.n_tables, 0) AS data_read_bytes,
            CAST(NULL AS DOUBLE) AS data_written_bytes,
            (qc.total_duration_ms / 1000.0) / NULLIF(qtc.n_tables, 0) AS duration_seconds,
            qc.query_cost_usd / NULLIF(qtc.n_tables, 0) AS estimated_cost_usd,
            -- La methode ne s'affirme que si un cout a reellement ete calcule :
            -- annoncer `equal_parts_fallback` sur une ligne sans cout decrirait un
            -- calcul qui n'a pas eu lieu.
            CASE WHEN qc.statement_id IS NULL THEN CAST(NULL AS STRING)
                 ELSE '{COST_ATTRIBUTION_EQUAL_PARTS_FALLBACK}' END
                AS cost_attribution_method,
            -- Meme regle pour le seau : le libelle suit le COUT et non le statement.
            -- Un statement rattache a un seau dont la facture manque n'a pas de cout,
            -- donc pas de base a annoncer.
            CASE WHEN qc.query_cost_usd IS NULL THEN CAST(NULL AS STRING)
                 ELSE qc.cost_basis END AS cost_basis,
            CASE WHEN qc.execution_status IN ('FAILED', 'CANCELED') THEN 1 ELSE 0 END
                AS failed_access_count,
            COALESCE(qc.start_time, ql.lineage_event_time) AS last_used_at_ts,
            -- Preuve d'existence : une ligne de lineage atteste que l'objet existe,
            -- le moteur ne tracant pas la lecture d'une table inexistante. Sert a
            -- distinguer « absent du registre » de « invisible du pipeline »
            -- (cf. `catalog_resolution_status`).
            TRUE AS existence_proven
        FROM query_lineage ql
        -- LEFT et non INNER : une lecture dont `query_history` n'a pas le statement
        -- figure SANS cout au lieu de disparaitre -- aucune autre branche ne la
        -- reprendrait, elle porte un `statement_id`.
        LEFT JOIN query_cost qc
          ON qc.cloud_provider = ql.cloud_provider AND qc.workspace_id = ql.workspace_id
         AND qc.statement_id = ql.statement_id
        -- LEFT aussi : `NULL = NULL` etant faux, un `statement_id` NULL ne matche
        -- jamais, et un INNER perdrait ici la population que le LEFT ci-dessus
        -- preserve. Sans denominateur les metriques restent NULL (`NULLIF(NULL, 0)`).
        LEFT JOIN query_table_counts qtc
          ON qtc.cloud_provider = ql.cloud_provider AND qtc.workspace_id = ql.workspace_id
         AND qtc.statement_id = ql.statement_id
    ),
    non_query_reads AS (
        -- Complement EXACT de `query_lineage` : les lectures sans `statement_id`, donc
        -- rien a joindre a `query.history`. La partition est NULL-safe par
        -- construction (`IS NULL` / `IS NOT NULL`) ; un couple `= 'DBSQL_QUERY'` /
        -- `!= 'DBSQL_QUERY'` laisserait les `entity_type` NULL hors des DEUX branches.
        SELECT
            cloud_provider, period_start, catalog, schema, table_name,
            COALESCE(created_by, entity_id, 'unknown') AS consumer_id,
            COALESCE(entity_type, '{CONSUMER_TYPE_UNKNOWN}') AS consumer_type,
            1 AS request_count,
            -- NULL et non `0` : sans `statement_id`, volume et duree ne sont pas
            -- mesurables. `0` affirmerait « a lu zero ligne » et diluerait les
            -- moyennes en aval.
            CAST(NULL AS DOUBLE) AS rows_read,
            CAST(NULL AS DOUBLE) AS rows_written,
            CAST(NULL AS DOUBLE) AS data_read_bytes,
            CAST(NULL AS DOUBLE) AS data_written_bytes,
            CAST(NULL AS DOUBLE) AS duration_seconds,
            CAST(NULL AS DOUBLE) AS estimated_cost_usd,
            -- Aucun cout calcule ici : annoncer une methode d'attribution ou un seau
            -- de facturation decrirait un calcul qui n'a pas eu lieu.
            CAST(NULL AS STRING) AS cost_attribution_method,
            CAST(NULL AS STRING) AS cost_basis,
            0 AS failed_access_count,
            event_time AS last_used_at_ts,
            TRUE AS existence_proven
        FROM lineage_table_reads
        WHERE statement_id IS NULL
    ),
    audit_reads AS (
        SELECT
            cloud_provider,
            to_date(event_time) AS period_start,
            {audit_catalog_expr} AS catalog,
            {audit_schema_expr} AS schema,
            {audit_table_name_expr} AS table_name,
            COALESCE(
                NULLIF(user_identity.email, 'unknown'), user_identity.subject_name, 'unknown'
            ) AS consumer_id,
            CASE
                WHEN user_identity.email IS NULL OR user_identity.email = 'unknown'
                    THEN CASE WHEN user_identity.subject_name IS NULL
                              THEN '{CONSUMER_TYPE_UNKNOWN}'
                              ELSE 'SERVICE_PRINCIPAL' END
                WHEN user_identity.email LIKE '%@%' THEN 'USER'
                ELSE 'SERVICE_PRINCIPAL'
            END AS consumer_type,
            1 AS request_count,
            -- `access.audit` ne porte AUCUN volume ni duree : un `getTable` est une
            -- lecture de metadonnees UC (UI/API), pas une requete. NULL = "non
            -- mesure" ; `0` aurait affirme une lecture vide.
            CAST(NULL AS DOUBLE) AS rows_read,
            CAST(NULL AS DOUBLE) AS rows_written,
            CAST(NULL AS DOUBLE) AS data_read_bytes,
            CAST(NULL AS DOUBLE) AS data_written_bytes,
            CAST(NULL AS DOUBLE) AS duration_seconds,
            CAST(NULL AS DOUBLE) AS estimated_cost_usd,
            CAST(NULL AS STRING) AS cost_attribution_method,
            CAST(NULL AS STRING) AS cost_basis,
            CASE WHEN response['status_code'] NOT IN ('200', '0') THEN 1 ELSE 0 END
                AS failed_access_count,
            event_time AS last_used_at_ts,
            -- Seule branche ou l'existence n'est PAS acquise : `getTable` journalise
            -- aussi les resolutions qui echouent. Un `404` porte le nom d'un objet
            -- inexistant (faute de frappe, table supprimee). Un `403` n'est pas une
            -- preuve non plus : l'objet existe peut-etre, l'audit ne le dit pas -- la
            -- preuve viendra du lineage s'il y en a.
            response['status_code'] = '200' AS existence_proven
        FROM {access_audit_table}
        WHERE action_name = 'getTable' AND {_GET_TABLE_FULL_NAME_EXPR} IS NOT NULL
        {audit_date_filter}
    ),
    query_write_volumes AS (
        -- Statements ayant ECRIT quelque chose, derives de `query_history_filtered`
        -- (donc deja bornes par la fenetre incrementale). Ne pas rajouter de predicat
        -- ici sans parentheser le `OR` : `A OR B AND x` se parse `A OR (B AND x)` et
        -- ne filtrerait qu'une branche.
        SELECT cloud_provider, workspace_id, statement_id, period_start, start_time,
               executed_by, written_rows, written_bytes
        FROM query_history_filtered
        WHERE written_rows IS NOT NULL OR written_bytes IS NOT NULL
    ),
    query_write_target_counts AS (
        SELECT cloud_provider, workspace_id, statement_id,
               COUNT(DISTINCT target_table_full_name) AS n_targets
        FROM lineage_table_writes
        GROUP BY cloud_provider, workspace_id, statement_id
    ),
    query_writes AS (
        -- Branche d'ECRITURE : alimente `rows_written`/`data_written_bytes` et
        -- `last_used_at`, RIEN d'autre. Les autres metriques restent neutres -- le
        -- meme `statement_id` est deja compte par `query_reads`, les renseigner ici
        -- double-compterait la requete.
        SELECT
            lw.cloud_provider,
            COALESCE(qw.period_start, lw.lineage_period_start) AS period_start,
            lw.catalog, lw.schema, lw.table_name,
            COALESCE(qw.executed_by, lw.lineage_created_by, 'unknown') AS consumer_id,
            {write_consumer_type_expr} AS consumer_type,
            0 AS request_count,
            CAST(NULL AS DOUBLE) AS rows_read,
            qw.written_rows / NULLIF(wtc.n_targets, 0) AS rows_written,
            CAST(NULL AS DOUBLE) AS data_read_bytes,
            qw.written_bytes / NULLIF(wtc.n_targets, 0) AS data_written_bytes,
            CAST(NULL AS DOUBLE) AS duration_seconds,
            CAST(NULL AS DOUBLE) AS estimated_cost_usd,
            CAST(NULL AS STRING) AS cost_attribution_method,
            CAST(NULL AS STRING) AS cost_basis,
            0 AS failed_access_count,
            COALESCE(qw.start_time, lw.lineage_event_time) AS last_used_at_ts,
            TRUE AS existence_proven
        FROM lineage_table_writes lw
        JOIN query_write_target_counts wtc
          ON wtc.cloud_provider = lw.cloud_provider AND wtc.workspace_id = lw.workspace_id
         AND wtc.statement_id = lw.statement_id
        -- INNER : sans volume cote `query.history`, cette branche n'a rien a
        -- apporter (elle ne compte pas de requete), donc aucune ligne a produire.
        JOIN query_write_volumes qw
          ON qw.cloud_provider = lw.cloud_provider AND qw.workspace_id = lw.workspace_id
         AND qw.statement_id = lw.statement_id
    ),
    all_reads AS (
        SELECT * FROM query_reads
        UNION ALL
        SELECT * FROM non_query_reads
        UNION ALL
        SELECT * FROM audit_reads
        UNION ALL
        SELECT * FROM query_writes
    ),
    aggregated AS (
        SELECT
            cloud_provider, period_start, catalog, schema, table_name, consumer_id,
            MAX({encode_consumer_type_priority("consumer_type")}) AS consumer_type_ranked,
            SUM(request_count) AS request_count,
            SUM(rows_read) AS rows_read,
            SUM(rows_written) AS rows_written,
            SUM(data_read_bytes) AS data_read_bytes,
            SUM(data_written_bytes) AS data_written_bytes,
            SUM(duration_seconds) AS duration_seconds,
            SUM(estimated_cost_usd) AS estimated_cost_usd,
            -- Nombre d'acces du groupe pour lesquels un cout a ete calcule. `SUM()`
            -- ignorant les NULL, un groupe melangeant acces chiffres et non mesurables
            -- rend un total partiel indistinguable d'un total complet : cette colonne
            -- est le denominateur qui le dit (`< request_count` => partiel).
            SUM(CASE WHEN estimated_cost_usd IS NOT NULL THEN request_count ELSE 0 END)
                AS costed_request_count,
            -- `MAX()` et non un litteral en dur, qui annoncerait une methode
            -- d'attribution meme sur un groupe sans aucun cout calcule. `MAX()`
            -- ignorant les NULL, la methode ressort des qu'une ligne est chiffree.
            MAX(cost_attribution_method) AS cost_attribution_method,
            -- Un groupe peut chiffrer des acces sur les DEUX seaux (un warehouse et un
            -- job serverless ayant lu la meme table le meme jour). `MAX()` en
            -- designerait un seul, au hasard de l'ordre alphabetique, alors que le total
            -- additionne deux grandeurs differentes : le dire. `COUNT(DISTINCT)`
            -- ignorant les NULL, un groupe ou une seule base est chiffree garde cette
            -- base, les acces non mesures ne la brouillant pas.
            CASE WHEN COUNT(DISTINCT cost_basis) > 1 THEN '{COST_BASIS_MIXED}'
                 ELSE MAX(cost_basis) END AS cost_basis,
            SUM(failed_access_count) AS failed_access_count,
            MAX(last_used_at_ts) AS last_used_at,
            -- `MAX` (OR logique sur des booleens) : il suffit d'UN acces reussi pour
            -- que l'existence soit prouvee, les echecs des autres branches ne la
            -- retirent pas.
            MAX(existence_proven) AS existence_proven
        FROM all_reads
        GROUP BY cloud_provider, period_start, catalog, schema, table_name, consumer_id
    )
    SELECT
        a.period_start AS usage_date,
        a.catalog,
        a.schema,
        a.table_name,
        concat_ws('.', a.catalog, a.schema, a.table_name) AS table_full_name,
        a.consumer_id,
        a.consumer_id AS consumer_name,
        a.cloud_provider,
        a.period_start,
        a.request_count,
        a.rows_read,
        a.rows_written,
        a.data_read_bytes,
        a.data_written_bytes,
        a.duration_seconds,
        a.estimated_cost_usd,
        a.costed_request_count,
        a.cost_attribution_method,
        a.cost_basis,
        {decode_consumer_type_priority("a.consumer_type_ranked")} AS consumer_type,
        a.failed_access_count,
        a.last_used_at,
        (uc.table_catalog IS NULL) AS unknown_data_product,
        -- Desambigue `unknown_data_product`, qui confond « hors data product » et « le
        -- pipeline n'a pas le droit de voir cet objet ». La fenetre est celle de
        -- l'OBJET-JOUR : `period_start` doit y figurer, sinon le statut d'un jour
        -- dependrait de la largeur de la fenetre incrementale recalculee.
        CASE
            WHEN uc.table_catalog IS NOT NULL THEN '{CATALOG_RESOLUTION_RESOLVED}'
            WHEN MAX(a.existence_proven) OVER (
                PARTITION BY a.cloud_provider, a.period_start,
                             a.catalog, a.schema, a.table_name
            ) THEN '{CATALOG_RESOLUTION_NOT_VISIBLE}'
            ELSE '{CATALOG_RESOLUTION_NEVER_RESOLVED}'
        END AS catalog_resolution_status,
        current_timestamp() AS _generated_at
    FROM aggregated a
    LEFT JOIN {uc_tables_table} uc
      ON uc.cloud_provider = a.cloud_provider
     AND uc.table_catalog = a.catalog
     AND uc.table_schema = a.schema
     AND uc.table_name = a.table_name
    WHERE 1 = 1
    {output_period_filter}
      -- UNE EPHEMERE N'OBTIENT AUCUNE LIGNE DE FAIT. C'est ici que l'exclusion doit se
      -- faire, et pas seulement au registre : l'exclusion en aval lit la PRESENCE d'une
      -- ligne `is_deleted` au registre, donc purger le registre sans filtrer les faits
      -- rendrait l'ephemere VISIBLE comme une table vivante (cf. `ephemeral_tables`).
      -- `table_popularity_daily` et `consumer_daily` derivent de cette table et heritent
      -- donc du filtre ; `table_query_performance_daily`, non, elle porte le sien.
      AND {not_ephemeral}
    """
    return spark.sql(query)
