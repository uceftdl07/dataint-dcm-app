"""Agregation gold `gold_dbx_usage_table_governance` — cycle de vie (T003).

Grain : `(cloud_provider, catalog, schema, table_name)` — snapshot complet,
meme pattern non-incremental que `table_catalog` (pas de
`period_start`, recalcul integral a chaque run).

Sources :
  - `gold_dbx_usage_table_catalog` (T003, meme job, tache chainee par
    `depends_on`) : `last_read_at`, presence des tags `owner`/`domain`/
    `cost_center`, `freshness_lag_hours`.
  - `gold_dbx_usage_table_popularity_daily` (T002) : `downstream_fanout` du
    dernier jour connu par table (dedup `QUALIFY ROW_NUMBER() ... ORDER BY
    period_start DESC = 1`, meme pattern que `table_catalog`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelines.gold_dbx_usage.specs import (
    CRITICAL_FANOUT_THRESHOLD,
    STALE_WRITE_LAG_HOURS,
    UNUSED_AFTER_DAYS,
)

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession


def build_table_governance(
    spark: SparkSession,
    *,
    table_catalog_table: str,
    table_popularity_daily_table: str,
) -> DataFrame:
    """Construit `gold_dbx_usage_table_governance`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        table_catalog_table: nom qualifie de `gold_dbx_usage_table_catalog`.
        table_popularity_daily_table: nom qualifie de
            `gold_dbx_usage_table_popularity_daily` (calcul de
            `downstream_fanout`).

    Returns:
        Le DataFrame `gold_dbx_usage_table_governance` resultant.

    Formules (seuils clarifies, cf. spec.md Acceptance Scenario 2 /
    `contracts/gold-usage-contract.md`) :
      - `days_since_last_read` = `datediff(current_date(), last_read_at)` --
        NULL si `last_read_at` est NULL (jamais lu).
      - `is_unused` = `days_since_last_read IS NULL OR days_since_last_read >
        90` -- une table jamais lue est traitee comme inutilisee (choix
        NULL-safe explicite, documente ici : ne jamais laisser un NULL
        evaluer silencieusement a "recemment lue").
      - `has_owner_tag`/`has_domain_tag`/`has_cost_center_tag` = presence des
        tags correspondants sur `table_catalog`.
      - `is_orphan` = vrai si aucun des 3 tags n'est present.
      - `is_stale_but_consumed` = `freshness_lag_hours > 24 AND
        days_since_last_read < 7` -- NULL-safe par construction : un operande
        NULL rend la condition NULL (jamais vraie), jamais traite comme faux
        explicite ni comme vrai.
      - `downstream_fanout` = dernier jour connu dans
        `table_popularity_daily`, `COALESCE(..., 0)` si jamais calcule.
      - `is_critical` = `downstream_fanout >= 5`.
      - `recommended_action`/`severity` = heuristique produit ajustable (PAS
        une formule figee par spec.md, jugement documente et simple) :
        `recommended_action` privilegie `is_unused` (archiver) puis
        `is_orphan` (documenter) puis `is_stale_but_consumed` (surveiller) ;
        `severity` marque `high` uniquement si critique ET inutilisee,
        `medium` si inutilisee OU orpheline, `low` si perimee-mais-consommee,
        sinon NULL.
      - `lifecycle_state`/`is_deleted`/`deleted_at` = propages depuis
        `table_catalog` par JOINTURE (jamais recalcules ici : un seul endroit
        derive l'etat). Une table supprimee sort avec `recommended_action` et
        `severity` a NULL -- la branche passe AVANT toutes les autres, sinon
        `is_unused` (vrai par construction sur une table jamais relue) ferait
        recommander d'archiver du neant. Les drapeaux bruts (`is_unused`,
        `is_orphan`, ...) restent calcules : ce sont des MESURES, que la
        gouvernance doit pouvoir relire sur l'inventaire de ce qui a disparu.
    """
    query = f"""
    WITH latest_popularity AS (
        SELECT cloud_provider, catalog, schema, table_name, downstream_fanout
        FROM {table_popularity_daily_table}
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY cloud_provider, catalog, schema, table_name
            ORDER BY period_start DESC
        ) = 1
    ),
    enriched AS (
        SELECT
            c.cloud_provider,
            c.catalog,
            c.schema,
            c.table_name,
            c.table_full_name,
            datediff(current_date(), c.last_read_at) AS days_since_last_read,
            c.owner,
            c.domain,
            c.cost_center,
            c.freshness_lag_hours,
            c.lifecycle_state,
            c.is_deleted,
            c.deleted_at,
            COALESCE(p.downstream_fanout, 0) AS downstream_fanout
        FROM {table_catalog_table} c
        LEFT JOIN latest_popularity p
          ON p.cloud_provider = c.cloud_provider AND p.catalog = c.catalog
         AND p.schema = c.schema AND p.table_name = c.table_name
    ),
    flagged AS (
        SELECT
            *,
            (days_since_last_read IS NULL OR days_since_last_read > {UNUSED_AFTER_DAYS})
                AS is_unused,
            (owner IS NOT NULL) AS has_owner_tag,
            (domain IS NOT NULL) AS has_domain_tag,
            (cost_center IS NOT NULL) AS has_cost_center_tag,
            (owner IS NULL AND domain IS NULL AND cost_center IS NULL) AS is_orphan,
            (freshness_lag_hours > {STALE_WRITE_LAG_HOURS} AND days_since_last_read < 7)
                AS is_stale_but_consumed,
            (downstream_fanout >= {CRITICAL_FANOUT_THRESHOLD}) AS is_critical
        FROM enriched
    )
    SELECT
        cloud_provider,
        catalog,
        schema,
        table_name,
        table_full_name,
        days_since_last_read,
        is_unused,
        has_owner_tag,
        has_domain_tag,
        has_cost_center_tag,
        is_orphan,
        is_stale_but_consumed,
        downstream_fanout,
        is_critical,
        lifecycle_state,
        is_deleted,
        deleted_at,
        CASE
            WHEN is_deleted THEN NULL
            WHEN is_unused THEN 'archiver'
            WHEN is_orphan THEN 'documenter'
            WHEN is_stale_but_consumed THEN 'surveiller'
            ELSE NULL
        END AS recommended_action,
        CASE
            WHEN is_deleted THEN NULL
            WHEN is_critical AND is_unused THEN 'high'
            WHEN is_unused OR is_orphan THEN 'medium'
            WHEN is_stale_but_consumed THEN 'low'
            ELSE NULL
        END AS severity,
        current_timestamp() AS _generated_at
    FROM flagged
    """
    return spark.sql(query)
