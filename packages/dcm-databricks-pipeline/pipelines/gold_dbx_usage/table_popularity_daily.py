"""Agregation gold `gold_dbx_usage_table_popularity_daily` — popularite (T002).

Agregat quotidien par data product : consommateurs distincts, volume, cout,
repartition par type de consommateur, fan-out aval, classement et delta J-1.
Source : `gold_dbx_usage_table_daily` (calcule par le meme job, en amont via
`depends_on`) + `curated_dbx_access_table_lineage` (fan-out) +
`curated_dbx_uc_table_tags` (owner/domain).
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from pipelines.gold_dbx_usage.sql_helpers import (
    LINEAGE_NAMED_OBJECT_TYPES,
    lower_bound_predicate,
    sql_string_list,
)

if TYPE_CHECKING:
    from datetime import date

    from pyspark.sql import DataFrame, SparkSession


def build_table_popularity_daily(
    spark: SparkSession,
    *,
    table_daily_table: str,
    lineage_table: str,
    uc_table_tags_table: str,
    lower_bound: date | None,
) -> DataFrame:
    """Construit `gold_dbx_usage_table_popularity_daily`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        table_daily_table: nom qualifie de `gold_dbx_usage_table_daily`.
        lineage_table: nom qualifie de `curated_dbx_access_table_lineage`
            (calcul du `downstream_fanout`).
        uc_table_tags_table: nom qualifie de `curated_dbx_uc_table_tags`
            (tags `owner`/`domain`).
        lower_bound: borne basse incluse de `period_start` pour la lecture
            incrementale ; `None` pour recalculer l'historique complet.

    Returns:
        Le DataFrame `gold_dbx_usage_table_popularity_daily` resultant.

    `popularity_rank` : `RANK() OVER (PARTITION BY cloud_provider, period_start
    ORDER BY request_count DESC)` -- `cloud_provider` fait partie du grain, donc
    de la partition, sinon les tables aws et azure se classent dans un meme
    palmares.

    `request_count_prev_day`/`request_delta_pct` : self-join exact sur J-1, jamais
    un `LAG`, qui sauterait silencieusement les jours sans activite (meme
    raisonnement que `gold_dbx_compute.warehouse_cost_daily`). 1 jour tampon est lu
    avant `lower_bound` pour que ce self-join voie J-1 au bord de la fenetre
    incrementale, puis exclu de la sortie.

    `downstream_fanout` : `COUNT(DISTINCT target_table_full_name)` sur les lignes de
    lineage ou cette table est la SOURCE, soit les objets aval nommes produits a
    partir d'elle. `0` reste `0` et non NULL : une table lue sans rien produire en
    aval est un fan-out mesure a zero, pas une mesure absente.
    """
    lag_lookback_lower_bound = lower_bound - timedelta(days=1) if lower_bound is not None else None
    table_daily_filter = lower_bound_predicate("period_start", lag_lookback_lower_bound)
    lineage_filter = lower_bound_predicate("event_date", lag_lookback_lower_bound)
    output_period_filter = lower_bound_predicate("period_start", lower_bound)
    named_object_types_sql = sql_string_list(LINEAGE_NAMED_OBJECT_TYPES)

    query = f"""
    WITH daily_agg AS (
        SELECT
            cloud_provider, catalog, schema, table_name, period_start,
            COUNT(DISTINCT consumer_id) AS distinct_consumers,
            SUM(request_count) AS request_count,
            SUM(rows_read) AS rows_read,
            SUM(data_read_bytes) AS data_read_bytes,
            SUM(estimated_cost_usd) AS estimated_cost_usd
        FROM {table_daily_table}
        WHERE 1 = 1 {table_daily_filter}
        GROUP BY cloud_provider, catalog, schema, table_name, period_start
    ),
    consumers_by_type AS (
        SELECT
            cloud_provider, catalog, schema, table_name, period_start,
            map_from_entries(collect_list(struct(consumer_type, cnt))) AS consumers_by_type
        FROM (
            SELECT
                cloud_provider, catalog, schema, table_name, period_start, consumer_type,
                COUNT(DISTINCT consumer_id) AS cnt
            FROM {table_daily_table}
            WHERE 1 = 1 {table_daily_filter}
            GROUP BY cloud_provider, catalog, schema, table_name, period_start, consumer_type
        )
        GROUP BY cloud_provider, catalog, schema, table_name, period_start
    ),
    fanout AS (
        -- FAN-OUT AVAL = objets produits A PARTIR de cette table, donc le cote CIBLE
        -- du lineage. Compter `entity_id` compterait l'entite qui LIT (job, notebook,
        -- requete) : des lecteurs, pas un fan-out. La distinction n'est pas cosmetique
        -- -- cette colonne alimente `severity` et `recommended_action` de
        -- `gold_dbx_usage_table_governance`, dont `'archiver'`.
        -- `COUNT(DISTINCT)` ignore les `target_table_full_name` NULL, ce qui exclut les
        -- cibles `PATH` (chemin de stockage, sans nom qualifie) : le fan-out compte les
        -- objets aval NOMMES.
        -- Le GROUP BY porte sur les colonnes natives et non sur les alias, pour ne pas
        -- dependre de la resolution d'alias lateral en GROUP BY.
        SELECT
            cloud_provider,
            to_date(event_time) AS period_start,
            source_table_catalog AS catalog,
            source_table_schema AS schema,
            source_table_name AS table_name,
            COUNT(DISTINCT target_table_full_name) AS downstream_fanout
        FROM {lineage_table}
        WHERE source_type IN ({named_object_types_sql})
          AND source_table_full_name IS NOT NULL
        {lineage_filter}
        GROUP BY
            cloud_provider, to_date(event_time),
            source_table_catalog, source_table_schema, source_table_name
    ),
    owner_domain AS (
        SELECT
            cloud_provider,
            catalog_name AS catalog,
            schema_name AS schema,
            table_name,
            MAX(CASE WHEN tag_name = 'owner' THEN tag_value END) AS owner,
            MAX(CASE WHEN tag_name = 'domain' THEN tag_value END) AS domain
        FROM {uc_table_tags_table}
        GROUP BY cloud_provider, catalog_name, schema_name, table_name
    ),
    enriched AS (
        SELECT
            da.cloud_provider, da.catalog, da.schema, da.table_name, da.period_start,
            da.distinct_consumers, da.request_count, da.rows_read, da.data_read_bytes,
            da.estimated_cost_usd, cbt.consumers_by_type,
            COALESCE(f.downstream_fanout, 0) AS downstream_fanout,
            od.owner, od.domain
        FROM daily_agg da
        LEFT JOIN consumers_by_type cbt
          ON cbt.cloud_provider = da.cloud_provider AND cbt.catalog = da.catalog
         AND cbt.schema = da.schema AND cbt.table_name = da.table_name
         AND cbt.period_start = da.period_start
        LEFT JOIN fanout f
          ON f.cloud_provider = da.cloud_provider AND f.catalog = da.catalog
         AND f.schema = da.schema AND f.table_name = da.table_name
         AND f.period_start = da.period_start
        LEFT JOIN owner_domain od
          ON od.cloud_provider = da.cloud_provider AND od.catalog = da.catalog
         AND od.schema = da.schema AND od.table_name = da.table_name
    ),
    with_prev_day AS (
        SELECT
            e.*,
            prev.request_count AS request_count_prev_day
        FROM enriched e
        LEFT JOIN enriched prev
          ON prev.cloud_provider = e.cloud_provider AND prev.catalog = e.catalog
         AND prev.schema = e.schema AND prev.table_name = e.table_name
         AND prev.period_start = e.period_start - INTERVAL 1 DAY
    )
    SELECT
        cloud_provider,
        catalog,
        schema,
        table_name,
        concat_ws('.', catalog, schema, table_name) AS table_full_name,
        owner,
        domain,
        period_start,
        distinct_consumers,
        request_count,
        rows_read,
        data_read_bytes,
        estimated_cost_usd,
        consumers_by_type,
        downstream_fanout,
        -- `cloud_provider` DANS la partition : il fait partie du grain de la table.
        -- Sans lui il n'existe qu'un rang 1 par jour pour les deux clouds confondus,
        -- et le rang d'une table varie selon l'activite de l'autre cloud.
        RANK() OVER (
            PARTITION BY cloud_provider, period_start ORDER BY request_count DESC
        ) AS popularity_rank,
        request_count_prev_day,
        (request_count - request_count_prev_day) / NULLIF(request_count_prev_day, 0) * 100
            AS request_delta_pct,
        current_timestamp() AS _generated_at
    FROM with_prev_day
    WHERE 1 = 1
    {output_period_filter}
    """
    return spark.sql(query)
