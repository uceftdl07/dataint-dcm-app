"""Agregation gold `gold_dbx_usage_consumer_daily` — agregat par consommateur (T002).

Grain : `(cloud_provider, consumer_id, period_start)`. Source unique :
`gold_dbx_usage_table_daily` (deja calcule par ce meme job, tache `table_daily`
-> `consumer_daily` chainee par `depends_on`, cf. `research.md` R2) --
independant de `table_popularity_daily`/`table_query_performance_daily` (pas de
lecture croisee entre elles).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelines.gold_dbx_usage.sql_helpers import (
    decode_consumer_type_priority,
    encode_consumer_type_priority,
    lower_bound_predicate,
)

if TYPE_CHECKING:
    from datetime import date

    from pyspark.sql import DataFrame, SparkSession


def build_consumer_daily(
    spark: SparkSession,
    *,
    table_daily_table: str,
    lower_bound: date | None,
) -> DataFrame:
    """Construit `gold_dbx_usage_consumer_daily`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        table_daily_table: nom qualifie de `gold_dbx_usage_table_daily`.
        lower_bound: borne basse incluse de `period_start` pour la lecture
            incrementale ; `None` pour recalculer l'historique complet.

    Returns:
        Le DataFrame `gold_dbx_usage_consumer_daily` resultant.

    `distinct_data_products` : `COUNT(DISTINCT table_full_name)`. Corrige F013
    (audit `usage-gold-t002`) : `COUNT(DISTINCT catalog, schema, table_name)`
    ecarte toute ligne a composante NULL (aucune ici en pratique, mais
    `table_full_name` -- deja materialise sur `table_daily` -- est la forme
    canonique retenue partout ailleurs dans ce module, cf. `table_daily.py`).
    `consumer_type` : `MAX()` sur un encodage par priorite (corrige F003,
    memes regles que `table_daily` : `USER` > `SERVICE_PRINCIPAL` > le reste),
    pas un `MAX()` alphabetique brut qui elirait une valeur au hasard de
    l'alphabet quand un meme `consumer_id` apparait avec des `consumer_type`
    differents selon la branche source (query/lineage/audit).
    `consumer_rank` : `RANK() OVER (PARTITION BY period_start ORDER BY
    estimated_cost_usd DESC)`, meme partition que `popularity_rank` (cf.
    `table_popularity_daily`).
    """
    period_filter = lower_bound_predicate("period_start", lower_bound)

    query = f"""
    SELECT
        cloud_provider,
        consumer_id,
        MAX(consumer_name) AS consumer_name,
        {decode_consumer_type_priority(f"MAX({encode_consumer_type_priority('consumer_type')})")}
            AS consumer_type,
        period_start,
        COUNT(DISTINCT table_full_name) AS distinct_data_products,
        SUM(request_count) AS request_count,
        SUM(rows_read) AS rows_read,
        SUM(data_read_bytes) AS data_read_bytes,
        SUM(duration_seconds) AS duration_seconds,
        SUM(estimated_cost_usd) AS estimated_cost_usd,
        RANK() OVER (PARTITION BY period_start ORDER BY SUM(estimated_cost_usd) DESC)
            AS consumer_rank,
        current_timestamp() AS _generated_at
    FROM {table_daily_table}
    WHERE 1 = 1
    {period_filter}
    GROUP BY cloud_provider, consumer_id, period_start
    """
    return spark.sql(query)
