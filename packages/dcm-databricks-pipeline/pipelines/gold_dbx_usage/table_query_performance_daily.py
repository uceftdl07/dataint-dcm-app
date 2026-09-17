"""Agregation gold `gold_dbx_usage_table_query_performance_daily` — perf (T002).

Grain : `(cloud_provider, catalog, schema, table_name, period_start)`. Source :
`curated_dbx_access_table_lineage` (`statement_id IS NOT NULL`, resout quel(s)
objet(s) UC une requete a lus) jointe a `curated_dbx_query_history` (volume,
latence, statut). Independante des autres tables de ce module : elle ne lit que
des tables curated, jamais un gold `gold_dbx_usage_*`. C'est pourquoi elle porte son
propre filtre d'ephemerite (`ephemeral_tables`) au lieu d'en heriter comme
`table_popularity_daily` et `consumer_daily` heritent de celui de `table_daily`.

`statement_id` est a la fois le discriminant des lignes retenues et la cle de
jointure vers `query_history`. `entity_type` ne peut pas en tenir le role
(`DBSQL_QUERY` ne couvre qu'une part marginale du lineage, ce qui reduirait la
table aux requetes DBSQL interactives, jobs exclus) et `entity_id` n'est pas
joignable (espace d'identifiants disjoint).

`bytes_scanned`/`rows_scanned` attribuent a CHAQUE objet lu le volume TOTAL de la
requete, sans prorata -- contrairement a `table_daily`, qui doit repartir un cout.
La question posee ici est « combien de volume les requetes touchant cet objet
ont-elles brasse ». Leur somme sur plusieurs objets d'une meme requete depasse
donc le volume de cette requete : ne pas les sommer entre objets.
"""

from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING

from pipelines.gold_dbx_usage.ephemeral_tables import (
    ephemeral_keys_cte,
    not_ephemeral_predicate,
)
from pipelines.gold_dbx_usage.specs import (
    LATENCY_BUCKET_OVERFLOW_KEY,
    LATENCY_BUCKET_UPPER_BOUNDS_MS,
)
from pipelines.gold_dbx_usage.sql_helpers import (
    LINEAGE_NAMED_OBJECT_TYPES,
    lower_bound_predicate,
    sql_string_list,
)

if TYPE_CHECKING:
    from datetime import date

    from pyspark.sql import DataFrame, SparkSession

# Statuts `system.query.history.execution_status` consideres comme un echec
# (memes valeurs que `gold_dbx_compute.warehouse_query_performance_daily`).
FAILED_EXECUTION_STATUSES = ("FAILED", "CANCELED")


def _latency_bucket_counts_sql() -> str:
    """Agregat `MAP<STRING, BIGINT>` des durees par bucket -- a placer dans le GROUP BY.

    Buckets a bornes hautes INCLUSES (`LATENCY_BUCKET_UPPER_BOUNDS_MS`) : le
    premier retient `d <= b0`, le k-ieme `b(k-1) < d <= bk`, le dernier
    (`LATENCY_BUCKET_OVERFLOW_KEY`) `d > b(-1)`. Bornes disjointes et couvrantes :
    toute duree tombe dans exactement un bucket.

    `COUNT(DISTINCT ... statement_id)` et non `COUNT(*)`, pour la meme raison que
    `failed_count` : un statement peut apparaitre sur plusieurs lignes du grain
    (meme table lue depuis deux workspaces), et la somme des compteurs doit
    rester egale a `query_count`, lui aussi distinct.

    `map_filter(..., n > 0)` retire les buckets vides : une (table, jour) sans
    requete dans une tranche n'a pas de compteur a zero, elle n'a pas de cle du
    tout. Un consommateur qui additionne des buckets traite donc une cle absente
    comme zero.

    Une duree `NULL` ne satisfait aucun predicat et ne tombe dans aucun bucket --
    meme population que `percentile_approx`, aucune valeur de repli fabriquee.
    """
    bounds = LATENCY_BUCKET_UPPER_BOUNDS_MS
    predicates = [f"total_duration_ms <= {bounds[0]}"]
    predicates.extend(
        f"total_duration_ms > {low} AND total_duration_ms <= {high}"
        for low, high in pairwise(bounds)
    )
    predicates.append(f"total_duration_ms > {bounds[-1]}")
    keys = [str(bound) for bound in bounds] + [LATENCY_BUCKET_OVERFLOW_KEY]
    entries = ",\n            ".join(
        f"'{key}', COUNT(DISTINCT CASE WHEN {predicate} THEN statement_id END)"
        for key, predicate in zip(keys, predicates, strict=True)
    )
    return f"map_filter(map(\n            {entries}\n        ), (bucket, n) -> n > 0)"


def build_table_query_performance_daily(
    spark: SparkSession,
    *,
    lineage_table: str,
    query_history_table: str,
    uc_tables_table: str,
    table_operations_table: str,
    lower_bound: date | None,
) -> DataFrame:
    """Construit `gold_dbx_usage_table_query_performance_daily`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        lineage_table: nom qualifie de `curated_dbx_access_table_lineage`.
        query_history_table: nom qualifie de `curated_dbx_query_history`.
        uc_tables_table: nom qualifie de `curated_dbx_uc_tables` (referentiel, pour
            ecarter les tables ephemeres -- cf. `ephemeral_tables`).
        table_operations_table: nom qualifie de `curated_dbx_uc_table_operations`
            (duree de vie vue par l'audit, meme usage).
        lower_bound: borne basse incluse de `period_start` pour la lecture
            incrementale ; `None` pour recalculer l'historique complet.

    Returns:
        Le DataFrame `gold_dbx_usage_table_query_performance_daily` resultant.

    `query_count` : `COUNT(DISTINCT statement_id)` (une meme requete peut
    apparaitre plusieurs fois dans le lineage si elle lit la table via
    plusieurs chemins). `failure_rate_pct`/`latency_p50_ms`/`latency_p95_ms` :
    memes formules que `gold_dbx_compute.warehouse_query_performance_daily`,
    au grain data product au lieu du grain warehouse.

    `latency_bucket_counts` : distribution des durees par bucket a bornes fixes
    (cf. `_latency_bucket_counts_sql`). Les percentiles quotidiens ne se somment
    ni ne se moyennent ; ces compteurs si -- c'est ce qui rend un P95 de periode
    arbitraire calculable en aval, sans rescanner `query_history`.
    """
    lineage_filter = lower_bound_predicate("event_date", lower_bound)
    query_filter = lower_bound_predicate("to_date(start_time)", lower_bound)
    failed_statuses_sql = ", ".join(f"'{status}'" for status in FAILED_EXECUTION_STATUSES)
    named_object_types_sql = sql_string_list(LINEAGE_NAMED_OBJECT_TYPES)
    latency_bucket_counts_sql = _latency_bucket_counts_sql()
    ephemeral_keys = ephemeral_keys_cte(
        uc_tables_table=uc_tables_table,
        table_operations_table=table_operations_table,
    )
    not_ephemeral = not_ephemeral_predicate("lq")

    query = f"""
    WITH {ephemeral_keys},
    lineage_query AS (
        -- AGREGAT au grain (statement, objet lu), pas une projection : la source porte
        -- plusieurs lignes par couple (fan-out des cibles, `event_id` repetable,
        -- expansion de vue). Sans ce GROUP BY, `failed_count`, `bytes_scanned`,
        -- `rows_scanned` et la ponderation des percentiles sont multiplies par le
        -- nombre de lignes de lineage du statement.
        -- Un p95 restreint aux lignes `entity_type = 'DBSQL_QUERY'` ne serait pas un
        -- p95 imprecis : ce serait celui d'une AUTRE population.
        -- Colonnes natives, pas un `split(source_table_full_name)` : la source publie
        -- deja les 3 parties.
        SELECT
            cloud_provider,
            workspace_id,
            source_table_catalog AS catalog,
            source_table_schema AS schema,
            source_table_name AS table_name,
            statement_id
        FROM {lineage_table}
        WHERE source_type IN ({named_object_types_sql})
          AND source_table_full_name IS NOT NULL
          AND statement_id IS NOT NULL
        {lineage_filter}
        GROUP BY
            cloud_provider, workspace_id, statement_id, source_table_full_name,
            source_table_catalog, source_table_schema, source_table_name
    ),
    query_history_filtered AS (
        SELECT
            cloud_provider,
            workspace_id,
            statement_id,
            to_date(start_time) AS period_start,
            execution_status,
            total_duration_ms,
            read_bytes,
            read_rows
        FROM {query_history_table}
        WHERE 1 = 1
        {query_filter}
    ),
    joined AS (
        -- `period_start` vient de la REQUETE et n'est PAS une condition de jointure :
        -- l'egalite `qh.period_start = lq.period_start` ferait disparaitre tout
        -- statement dont l'evenement de lineage et le `start_time` tombent de part et
        -- d'autre de minuit.
        SELECT
            lq.cloud_provider, qh.period_start, lq.catalog, lq.schema, lq.table_name,
            qh.statement_id, qh.execution_status, qh.total_duration_ms,
            qh.read_bytes, qh.read_rows
        FROM lineage_query lq
        JOIN query_history_filtered qh
          ON qh.cloud_provider = lq.cloud_provider AND qh.workspace_id = lq.workspace_id
         AND qh.statement_id = lq.statement_id
        -- Cette table lit le lineage et `query_history` sans passer par
        -- `gold_dbx_usage_table_daily` : elle n'herite d'aucun filtre et porte donc le
        -- sien, la ou `table_popularity_daily` et `consumer_daily` heritent de celui de
        -- `table_daily`. Sans lui, une table de staging creee, lue et droppee par un meme
        -- run garderait ses lignes de perf, et l'exclusion en aval ne pourrait plus les
        -- cacher : elle lit la PRESENCE d'une ligne `is_deleted` au registre, que la purge
        -- retire justement (cf. le module `ephemeral_tables`).
        WHERE {not_ephemeral}
    )
    SELECT
        cloud_provider,
        catalog,
        schema,
        table_name,
        concat_ws('.', catalog, schema, table_name) AS table_full_name,
        period_start,
        COUNT(DISTINCT statement_id) AS query_count,
        -- `COUNT(DISTINCT ... statement_id)` et non `SUM(CASE ...)` : numerateur et
        -- denominateur doivent compter la meme chose, sinon `failure_rate_pct` depasse
        -- 100 % des qu'un statement en echec apparait sur plusieurs lignes.
        COUNT(DISTINCT CASE WHEN execution_status IN ({failed_statuses_sql})
                            THEN statement_id END) AS failed_count,
        COUNT(DISTINCT CASE WHEN execution_status IN ({failed_statuses_sql})
                            THEN statement_id END)
            / NULLIF(COUNT(DISTINCT statement_id), 0) * 100 AS failure_rate_pct,
        percentile_approx(total_duration_ms, 0.50) AS latency_p50_ms,
        percentile_approx(total_duration_ms, 0.95) AS latency_p95_ms,
        -- Distribution additionnable entre jours, la ou les deux percentiles
        -- ci-dessus ne le sont pas : sans elle, aucun P95 de periode n'est
        -- recalculable. Les deux coexistent, le percentile quotidien reste lu tel
        -- quel pour une journee unique.
        {latency_bucket_counts_sql} AS latency_bucket_counts,
        SUM(read_bytes) AS bytes_scanned,
        SUM(read_rows) AS rows_scanned,
        current_timestamp() AS _generated_at
    FROM joined
    GROUP BY cloud_provider, catalog, schema, table_name, period_start
    """
    return spark.sql(query)
