"""Agregation gold `gold_dbx_usage_recommendations` (socle reactif, T004).

Rule engine transverse : evalue les 5 categories de regles de
`usage_datamapping.md` §4.1 sur les tables gold `governance`/`catalog`/
`query_performance_daily`/`consumer_daily` deja calculees (T002/T003), data
products ET consommateurs, et produit un fait actionnable unifie avec cycle
de vie `OPEN` -> `RESOLVED` -- meme mecanique que
`pipelines.gold_dbx_compute.recommendations` (cf. `_existing_state_cte` pour
le detail du cycle de vie).

`recommendation_id` = hash de la cle metier (`cloud_provider`, `object_type`,
`object_id`, `category`) ET de `first_seen_date` (PAS `generated_date`) :
reste stable tout au long de la vie de l'anomalie. Ecart assume vs la formule
litterale de `usage_datamapping.md` §4.1
(`sha2(object_type||object_id||category||generated_date)`) : un hash sur
`generated_date` change de valeur CHAQUE jour ou la regle se declenche encore,
ce qui romprait directement l'AC T004 "0 doublon sur re-run, first_seen_date
preserve" (une nouvelle ligne serait creee a chaque run au lieu de mettre a
jour la ligne existante). Meme correction deja appliquee par
`gold_dbx_compute.recommendations` (precedent direct, meme domaine
transverse) -- reprise ici plutot que de reproduire un defaut deja identifie.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelines.gold_dbx_usage.specs import (
    USAGE_FAILURE_RATE_PCT_THRESHOLD,
    USAGE_HIGH_COST_USD_THRESHOLD,
)

if TYPE_CHECKING:
    from datetime import date

    from pyspark.sql import DataFrame, SparkSession

# Schema (types) de `gold_dbx_usage_recommendations`, hors cles/derivees
# (`recommendation_id`, `mode`, `status`, `_generated_at`) : reutilise pour
# fabriquer une source "existante" vide et typee au tout premier run (aucune
# table cible a lire), cf. `_existing_state_cte`.
_EXISTING_STATE_NULL_COLUMNS = (
    ("cloud_provider", "STRING"),
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

    Ce builder gere/ecrit les DEUX types d'objet (`DATA_PRODUCT` et
    `CONSUMER`) : lit donc l'integralite de l'etat existant, sans filtre
    `object_type`.

    Filtre `status = 'OPEN'` : une ligne `RESOLVED` ne doit PAS etre
    retrouvee par la jointure sur cle metier de `merged`, sinon sa
    `first_seen_date` d'origine serait reprise si l'anomalie se redeclenche
    des mois/annees plus tard, contredisant le principe de "nouvelle
    detection apres resolution" (cf. docstring module). Consequence acceptee :
    l'ancienne ligne `RESOLVED` n'est plus jamais reecrite par un run
    ulterieur (elle reste figee en base tant qu'aucune reouverture ne cree
    une nouvelle ligne a cote). Meme convention que
    `gold_dbx_compute.recommendations._existing_state_cte` (statut `ACK`
    non gere ici non plus -- pas de mecanisme d'acquittement dans ce module).
    """
    if table_exists:
        source = f"SELECT * FROM {recommendations_table} WHERE status = 'OPEN'"
    else:
        null_columns = ", ".join(
            f"CAST(NULL AS {sql_type}) AS {name}" for name, sql_type in _EXISTING_STATE_NULL_COLUMNS
        )
        source = f"SELECT {null_columns} WHERE 1 = 0"
    return f"existing AS (\n    {source}\n)"


def build_usage_recommendations(
    spark: SparkSession,
    *,
    governance_table: str,
    catalog_table: str,
    popularity_daily_table: str,
    query_performance_daily_table: str,
    consumer_daily_table: str,
    recommendations_table: str,
    generated_date: date,
) -> DataFrame:
    """Construit `gold_dbx_usage_recommendations` (data products + consommateurs).

    Args:
        spark: session Spark utilisee pour executer la requete generee (et
            verifier l'existence de `recommendations_table` : premiere
            ecriture ou etat a faire evoluer, cf. `_existing_state_cte`).
        governance_table: nom qualifie de `gold_dbx_usage_table_governance`
            (regles LIFECYCLE/FRESHNESS/GOVERNANCE-orphan).
        catalog_table: nom qualifie de `gold_dbx_usage_table_catalog` (regle
            GOVERNANCE-classification, et `table_full_name`/`object_name`).
        popularity_daily_table: nom qualifie de
            `gold_dbx_usage_table_popularity_daily` (source de
            `estimated_cost_usd` au grain table -- utilise comme
            `estimated_savings_usd` de la regle LIFECYCLE "inutilise").
        query_performance_daily_table: nom qualifie de
            `gold_dbx_usage_table_query_performance_daily` (regle RELIABILITY).
        consumer_daily_table: nom qualifie de `gold_dbx_usage_consumer_daily`
            (regle FINOPS).
        recommendations_table: nom qualifie de la table CIBLE
            `gold_dbx_usage_recommendations` elle-meme -- lue (pas ecrite
            ici) pour retrouver l'etat existant (`first_seen_date`, anomalies
            precedemment `OPEN` a transitionner en `RESOLVED`).
        generated_date: date du run (utilisee comme `first_seen_date`/
            `last_seen_date` pour les anomalies nouvellement/toujours
            detectees ; jamais utilisee dans `recommendation_id`, cf.
            docstring module).

    Returns:
        Le DataFrame de `gold_dbx_usage_recommendations` (nouvelles,
        toujours ouvertes, ou nouvellement resolues) -- a passer a
        `merge_into_table` (cle `recommendation_id`).

    Regles couvertes (cf. `usage_datamapping.md` §4.1), objet `DATA_PRODUCT`
    sauf mention contraire :
      - LIFECYCLE (MEDIUM) : `governance.is_unused = true AND is_critical =
        false` -- "proposer depreciation/suppression". Mutuellement
        exclusive par construction avec la regle suivante (`is_critical`
        oppose), pas de dedoublonnage necessaire entre les deux.
      - LIFECYCLE (HIGH) : `governance.is_critical = true AND is_unused =
        true` ("contradiction lineage") -- "ne PAS deprecier, investiguer
        les dependances aval".
      - FRESHNESS (HIGH) : `governance.is_stale_but_consumed = true`.
      - GOVERNANCE (LOW, priorite 1) : `governance.is_orphan = true` --
        "ajouter tags owner/domain/cost-center".
      - GOVERNANCE (MEDIUM, priorite 2) : `catalog.classification IS NULL
        AND catalog.is_data_product = true` -- "classifier la donnee". Au
        plus UNE ligne GOVERNANCE par objet (ordre de priorite = ordre du
        tableau `usage_datamapping.md` §4.1, meme convention que
        `gold_dbx_compute.recommendations` pour les categories a regles
        multiples).
      - RELIABILITY (HIGH) : `query_performance_daily.failure_rate_pct >
        {USAGE_FAILURE_RATE_PCT_THRESHOLD}` (dernier jour connu).
      - FINOPS (MEDIUM, objet `CONSUMER`) :
        `consumer_daily.estimated_cost_usd > {USAGE_HIGH_COST_USD_THRESHOLD}`
        (dernier jour connu) -- seule regle au grain consommateur, pas data
        product (cf. `usage_datamapping.md` §4.1 ligne FINOPS : `object_type
        = CONSUMER`).

    Aucune regle `DATA_PRODUCT` ne se declenche sur une table supprimee au
    registre : une recommandation sur un objet qui n'existe plus ne mene nulle
    part. La regle FINOPS est au grain CONSOMMATEUR (aucune cle table a
    rapprocher du registre) et reste donc intacte. L'etat existant, lui, est
    relu SANS ce filtre : une recommandation deja `OPEN` sur une table depuis
    supprimee doit rester dans le `FULL OUTER JOIN` pour basculer `RESOLVED`
    par la mecanique en place, au lieu de rester `OPEN` en base pour toujours.

    Cycle de vie (`status`) : identique a
    `gold_dbx_compute.recommendations.build_compute_recommendations` -- un
    objet present dans `existing` (etat `OPEN`) mais dont plus aucune regle
    ne se declenche aujourd'hui transitionne en `RESOLVED` ; un objet qui
    redeclenche une regle apres resolution est traite comme une VRAIE
    nouvelle detection (nouveau `first_seen_date`, nouveau
    `recommendation_id`, seconde ligne inseree a cote de l'ancienne qui reste
    `RESOLVED` et figee en base -- aucun `DELETE`/purge).
    """
    existing_cte = _existing_state_cte(
        recommendations_table, spark.catalog.tableExists(recommendations_table)
    )
    generated_date_sql = f"DATE '{generated_date.isoformat()}'"
    query = f"""
    WITH latest_popularity AS (
        SELECT * FROM {popularity_daily_table}
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY cloud_provider, table_full_name ORDER BY period_start DESC
        ) = 1
    ),
    latest_query_performance AS (
        SELECT * FROM {query_performance_daily_table}
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY cloud_provider, catalog, schema, table_name ORDER BY period_start DESC
        ) = 1
    ),
    latest_consumer AS (
        SELECT * FROM {consumer_daily_table}
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY cloud_provider, consumer_id ORDER BY period_start DESC
        ) = 1
    ),
    lifecycle_candidates AS (
        SELECT
            cloud_provider, 'DATA_PRODUCT' AS object_type,
            table_full_name AS object_id, table_full_name AS object_name,
            'LIFECYCLE' AS category, severity, title, detail,
            recommended_action, estimated_savings_usd, personas
        FROM (
            SELECT
                g.cloud_provider, g.table_full_name,
                'MEDIUM' AS severity, 'Data product inutilise' AS title,
                CONCAT(
                    'Aucune lecture depuis ',
                    CAST(g.days_since_last_read AS STRING), ' jours (ou jamais lu).'
                ) AS detail,
                'Proposer depreciation / suppression' AS recommended_action,
                lp.estimated_cost_usd AS estimated_savings_usd,
                array('OWN', 'FIN', 'GOV') AS personas
            FROM {governance_table} g
            LEFT JOIN {catalog_table} c
              ON c.cloud_provider = g.cloud_provider AND c.table_full_name = g.table_full_name
            LEFT JOIN latest_popularity lp
              ON lp.cloud_provider = g.cloud_provider AND lp.table_full_name = g.table_full_name
            WHERE g.is_unused AND NOT g.is_critical AND NOT g.is_deleted

            UNION ALL

            SELECT
                g.cloud_provider, g.table_full_name,
                'HIGH' AS severity, 'Data product critique marque inutilise' AS title,
                CONCAT(
                    'downstream_fanout=', CAST(g.downstream_fanout AS STRING),
                    ', aucune lecture depuis ', CAST(g.days_since_last_read AS STRING), ' jours.'
                ) AS detail,
                'Ne PAS deprecier ; investiguer les dependances aval' AS recommended_action,
                CAST(NULL AS DOUBLE) AS estimated_savings_usd,
                array('OWN', 'GOV') AS personas
            FROM {governance_table} g
            WHERE g.is_critical AND g.is_unused AND NOT g.is_deleted
        )
    ),
    freshness_candidates AS (
        SELECT
            g.cloud_provider, 'DATA_PRODUCT' AS object_type,
            g.table_full_name AS object_id, g.table_full_name AS object_name,
            'FRESHNESS' AS category, 'HIGH' AS severity,
            'Data product perime mais toujours consomme' AS title,
            CONCAT(
                'freshness_lag_hours=', CAST(ROUND(c.freshness_lag_hours, 1) AS STRING),
                'h, derniere lecture il y a ', CAST(g.days_since_last_read AS STRING), ' jours.'
            ) AS detail,
            'Corriger le pipeline amont ; prevenir les consommateurs' AS recommended_action,
            CAST(NULL AS DOUBLE) AS estimated_savings_usd,
            array('DE', 'OWN') AS personas
        FROM {governance_table} g
        LEFT JOIN {catalog_table} c
          ON c.cloud_provider = g.cloud_provider AND c.table_full_name = g.table_full_name
        WHERE g.is_stale_but_consumed AND NOT g.is_deleted
    ),
    governance_candidates AS (
        SELECT
            cloud_provider, object_type, object_id, object_name, category,
            severity, title, detail, recommended_action, estimated_savings_usd, personas
        FROM (
            SELECT
                g.cloud_provider, 'DATA_PRODUCT' AS object_type,
                g.table_full_name AS object_id, g.table_full_name AS object_name,
                'GOVERNANCE' AS category, 'LOW' AS severity,
                'Data product orphelin (aucun tag de gouvernance)' AS title,
                CONCAT(
                    'has_owner_tag=', CAST(g.has_owner_tag AS STRING),
                    ', has_domain_tag=', CAST(g.has_domain_tag AS STRING),
                    ', has_cost_center_tag=', CAST(g.has_cost_center_tag AS STRING), '.'
                ) AS detail,
                'Ajouter les tags owner/domain/cost-center' AS recommended_action,
                CAST(NULL AS DOUBLE) AS estimated_savings_usd,
                array('GOV', 'FIN') AS personas,
                1 AS rule_priority
            FROM {governance_table} g
            WHERE g.is_orphan AND NOT g.is_deleted

            UNION ALL

            SELECT
                c.cloud_provider, 'DATA_PRODUCT' AS object_type,
                c.table_full_name AS object_id, c.table_full_name AS object_name,
                'GOVERNANCE' AS category, 'MEDIUM' AS severity,
                'Data product publie sans classification' AS title,
                'is_data_product=true, classification=NULL.' AS detail,
                'Classifier la donnee' AS recommended_action,
                CAST(NULL AS DOUBLE) AS estimated_savings_usd,
                array('GOV') AS personas,
                2 AS rule_priority
            FROM {catalog_table} c
            WHERE c.is_data_product AND c.classification IS NULL AND NOT c.is_deleted
        )
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY cloud_provider, object_type, object_id ORDER BY rule_priority
        ) = 1
    ),
    reliability_candidates AS (
        SELECT
            lp.cloud_provider, 'DATA_PRODUCT' AS object_type,
            lp.table_full_name AS object_id, lp.table_full_name AS object_name,
            'RELIABILITY' AS category, 'HIGH' AS severity,
            'Taux d''echec eleve sur ce data product' AS title,
            CONCAT(
                'Taux d''echec=', CAST(ROUND(lp.failure_rate_pct, 1) AS STRING), '%.'
            ) AS detail,
            'Investiguer les acces en echec (droits/schema)' AS recommended_action,
            CAST(NULL AS DOUBLE) AS estimated_savings_usd,
            array('DE', 'AN') AS personas
        FROM latest_query_performance lp
        -- Table de FAIT : elle ne porte pas l'etat de cycle de vie et ne doit pas le
        -- porter. Jointure EXTERNE + COALESCE : une cle jamais resolue au registre
        -- reste candidate, elle ne doit pas etre filtree en silence.
        LEFT JOIN {catalog_table} c
          ON c.cloud_provider = lp.cloud_provider AND c.table_full_name = lp.table_full_name
        WHERE lp.failure_rate_pct > {USAGE_FAILURE_RATE_PCT_THRESHOLD}
          AND NOT COALESCE(c.is_deleted, false)
    ),
    finops_candidates AS (
        SELECT
            lc.cloud_provider, 'CONSUMER' AS object_type,
            lc.consumer_id AS object_id, lc.consumer_name AS object_name,
            'FINOPS' AS category, 'MEDIUM' AS severity,
            'Cout de consommation eleve' AS title,
            CONCAT(
                'Cout estime du jour=', CAST(ROUND(lc.estimated_cost_usd, 2) AS STRING), ' USD.'
            ) AS detail,
            'Sensibiliser / optimiser le consommateur' AS recommended_action,
            CAST(NULL AS DOUBLE) AS estimated_savings_usd,
            array('FIN') AS personas
        FROM latest_consumer lc
        WHERE lc.estimated_cost_usd > {USAGE_HIGH_COST_USD_THRESHOLD}
    ),
    candidates AS (
        SELECT * FROM lifecycle_candidates
        UNION ALL
        SELECT * FROM freshness_candidates
        UNION ALL
        SELECT * FROM governance_candidates
        UNION ALL
        SELECT * FROM reliability_candidates
        UNION ALL
        SELECT * FROM finops_candidates
    ),
    {existing_cte},
    merged AS (
        SELECT
            COALESCE(c.cloud_provider, ex.cloud_provider) AS cloud_provider,
            COALESCE(c.object_type, ex.object_type) AS object_type,
            COALESCE(c.object_id, ex.object_id) AS object_id,
            COALESCE(c.object_name, ex.object_name) AS object_name,
            COALESCE(c.category, ex.category) AS category,
            'REACTIVE' AS mode,
            COALESCE(c.title, ex.title) AS title,
            COALESCE(c.detail, ex.detail) AS detail,
            COALESCE(c.recommended_action, ex.recommended_action) AS recommended_action,
            COALESCE(c.estimated_savings_usd, ex.estimated_savings_usd) AS estimated_savings_usd,
            COALESCE(c.severity, ex.severity) AS severity,
            COALESCE(c.personas, ex.personas) AS personas,
            CASE WHEN c.object_id IS NOT NULL THEN 'OPEN' ELSE 'RESOLVED' END AS status,
            COALESCE(ex.first_seen_date, {generated_date_sql}) AS first_seen_date,
            CASE
                WHEN c.object_id IS NOT NULL THEN {generated_date_sql}
                ELSE ex.last_seen_date
            END AS last_seen_date
        FROM candidates c
        FULL OUTER JOIN existing ex
          ON ex.cloud_provider = c.cloud_provider AND ex.object_type = c.object_type
         AND ex.object_id = c.object_id AND ex.category = c.category
    )
    SELECT
        sha2(
            concat_ws('||', cloud_provider, object_type, object_id, category,
                CAST(first_seen_date AS STRING)),
            256
        ) AS recommendation_id,
        cloud_provider, object_type, object_id, object_name, category, mode,
        title, detail, recommended_action, estimated_savings_usd, severity,
        personas, status, first_seen_date, last_seen_date,
        current_timestamp() AS _generated_at
    FROM merged
    """
    return spark.sql(query)
