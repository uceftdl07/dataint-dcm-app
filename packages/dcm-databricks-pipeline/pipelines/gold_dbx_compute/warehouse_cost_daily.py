"""Agregation gold `gold_dbx_compute_warehouse_cost_daily` (FinOps SQL Warehouses).

Cout quotidien par SQL Warehouse Databricks : DBU consommes, cout USD,
evolution vs le jour precedent, nombre de requetes executees, cout par
requete et utilisateur le plus consommateur du jour. Alimente le suivi
FinOps des couts de compute SQL Warehouses (identification des principaux
consommateurs, tendance jour apres jour).
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.sql_helpers import lower_bound_predicate

if TYPE_CHECKING:
    from datetime import date

    from pyspark.sql import DataFrame, SparkSession


def build_warehouse_cost_daily(
    spark: SparkSession,
    *,
    billing_usage_table: str,
    billing_list_prices_table: str,
    warehouses_table: str,
    query_history_table: str,
    lower_bound: date | None,
) -> DataFrame:
    """Construit `gold_dbx_compute_warehouse_cost_daily`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        billing_usage_table: nom qualifie (`catalog.schema.table`) de
            `curated_dbx_billing_usage`.
        billing_list_prices_table: nom qualifie de
            `curated_dbx_billing_list_prices`.
        warehouses_table: nom qualifie de `curated_dbx_compute_warehouses`
            (dernier etat connu du warehouse).
        query_history_table: nom qualifie de `curated_dbx_query_history`
            (comptage de requetes et utilisateur le plus consommateur).
        lower_bound: borne basse incluse de `period_start` pour la lecture
            incrementale ; `None` pour recalculer l'historique complet.

    Returns:
        Le DataFrame `gold_dbx_compute_warehouse_cost_daily` resultant.

    Grain : `(cloud_provider, workspace_id, warehouse_id, period_start)`.
    Source : `curated_dbx_billing_usage` (lignes rattachees a un warehouse,
    agregees par jour) + `curated_dbx_billing_list_prices` (prix effectif) +
    dernier etat connu du warehouse (`curated_dbx_compute_warehouses`) +
    `curated_dbx_query_history` (comptage de requetes, utilisateur le plus
    consommateur). Pas de `source_lz_id`/`ba_name` ni de `cost_rank`/
    `is_top_cost` sur cette table (cf. `WAREHOUSE_DAILY_MERGE_KEYS` dans
    `pipelines.gold_dbx_compute.specs`).

    Champs et formule de calcul :
      - `warehouse_name`/`warehouse_size` : identite et taille du warehouse,
        resolues au dernier etat connu (`change_time < period_start + 1 jour` :
        etat connu a un instant quelconque de `period_start`, pas seulement
        avant minuit - un cast `TIMESTAMP <= DATE` a minuit exclurait a tort
        les warehouses crees le jour meme, cas des ephemeres de bundle ;
        meme borne que la famille gold clusters/jobs).
      - `dbu_quantity` : volume de DBU consommes par le warehouse ce jour-la.
        Formule : `SUM(usage_quantity)` restreint aux lignes `usage_unit =
        'DBU'`.
      - `cost_usd` : cout total en dollars du warehouse ce jour-la. Formule :
        `SUM(usage_quantity * effective_price)`, ou `effective_price` vient de
        `curated_dbx_billing_list_prices` joint sur la fenetre
        `price_start_time <= usage_date < price_end_time` (meme jointure que
        `cluster_cost_daily.build_cluster_cost_daily`).
      - `cost_usd_prev_day` : cout du jour calendaire precedent, pour
        comparaison. Formule : self-join exact sur `period_start - 1 jour`
        (jamais un `LAG`, meme raisonnement que pour les clusters : un `LAG`
        sauterait silencieusement les jours sans usage). La lecture curated
        inclut 1 jour tampon avant `lower_bound` pour que ce self-join voie
        J-1 au bord de la fenetre incrementale ; ce jour tampon est exclu de
        la sortie (`period_start >= lower_bound`).
      - `cost_delta_pct` : variation du cout par rapport a la veille, en
        pourcentage. Formule : `(cost_usd - cost_usd_prev_day) /
        cost_usd_prev_day * 100`.
      - `query_count` : nombre de requetes executees sur ce warehouse ce
        jour-la. Formule : `COUNT(statement_id)` de `curated_dbx_query_history`
        filtre sur `compute.warehouse_id IS NOT NULL` (acces direct par point,
        `compute` etant un struct scalaire sur cette table, pas un array).
      - `cost_per_query_usd` : cout moyen par requete ce jour-la. Formule :
        `cost_usd / NULLIF(query_count, 0)`.
      - `top_consumer` : utilisateur ayant le plus consomme de temps
        d'execution sur ce warehouse ce jour-la. Formule : `executed_by` avec
        la plus grande somme de `total_duration_ms`, tous statements
        confondus (`ROW_NUMBER() OVER (... ORDER BY SUM(total_duration_ms)
        DESC) = 1`).
    """
    # 1 jour tampon avant `lower_bound` : sans lui, le self-join sur
    # `period_start - 1 jour` (cf. `with_prev_day` ci-dessous) ne verrait pas
    # J-1 au bord de la fenetre incrementale. Jamais reecrit : le filtre de
    # sortie reste sur `period_start >= lower_bound` (`output_period_filter`).
    lag_lookback_lower_bound = lower_bound - timedelta(days=1) if lower_bound is not None else None
    usage_date_filter = lower_bound_predicate("usage_date", lag_lookback_lower_bound)
    query_date_filter = lower_bound_predicate("to_date(start_time)", lower_bound)
    output_period_filter = lower_bound_predicate("period_start", lower_bound)
    query = f"""
    WITH usage_filtered AS (
        SELECT
            cloud_provider,
            workspace_id,
            usage_metadata.warehouse_id AS warehouse_id,
            usage_date AS period_start,
            sku_name,
            usage_unit,
            usage_quantity
        FROM {billing_usage_table}
        WHERE usage_metadata.warehouse_id IS NOT NULL
        {usage_date_filter}
    ),
    priced AS (
        SELECT
            u.cloud_provider,
            u.workspace_id,
            u.warehouse_id,
            u.period_start,
            SUM(CASE WHEN u.usage_unit = 'DBU' THEN u.usage_quantity ELSE 0 END) AS dbu_quantity,
            SUM(u.usage_quantity * COALESCE(lp.effective_price, 0)) AS cost_usd
        FROM usage_filtered u
        LEFT JOIN (
            SELECT
                cloud_provider,
                sku_name,
                price_start_time,
                price_end_time,
                pricing.effective_list.default AS effective_price
            FROM {billing_list_prices_table}
        ) lp
          ON lp.cloud_provider = u.cloud_provider
         AND lp.sku_name = u.sku_name
         AND lp.price_start_time <= u.period_start
         AND (lp.price_end_time IS NULL OR u.period_start < lp.price_end_time)
        GROUP BY u.cloud_provider, u.workspace_id, u.warehouse_id, u.period_start
    ),
    warehouses_as_of AS (
        SELECT
            p.cloud_provider,
            p.workspace_id,
            p.warehouse_id,
            p.period_start,
            w.warehouse_name,
            w.warehouse_size
        FROM priced p
        LEFT JOIN {warehouses_table} w
          ON w.cloud_provider = p.cloud_provider
         AND w.workspace_id = p.workspace_id
         AND w.warehouse_id = p.warehouse_id
         AND w.change_time < p.period_start + INTERVAL 1 DAY
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY p.cloud_provider, p.workspace_id, p.warehouse_id, p.period_start
            ORDER BY w.change_time DESC
        ) = 1
    ),
    query_history_filtered AS (
        SELECT
            cloud_provider,
            workspace_id,
            compute.warehouse_id AS warehouse_id,
            to_date(start_time) AS period_start,
            statement_id,
            executed_by,
            total_duration_ms
        FROM {query_history_table}
        WHERE compute.warehouse_id IS NOT NULL
        {query_date_filter}
    ),
    query_counts AS (
        SELECT
            cloud_provider,
            workspace_id,
            warehouse_id,
            period_start,
            COUNT(statement_id) AS query_count
        FROM query_history_filtered
        GROUP BY cloud_provider, workspace_id, warehouse_id, period_start
    ),
    user_durations AS (
        SELECT
            cloud_provider,
            workspace_id,
            warehouse_id,
            period_start,
            executed_by,
            SUM(total_duration_ms) AS total_duration_ms
        FROM query_history_filtered
        GROUP BY cloud_provider, workspace_id, warehouse_id, period_start, executed_by
    ),
    top_consumer AS (
        SELECT
            cloud_provider,
            workspace_id,
            warehouse_id,
            period_start,
            executed_by AS top_consumer
        FROM user_durations
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY cloud_provider, workspace_id, warehouse_id, period_start
            ORDER BY total_duration_ms DESC
        ) = 1
    ),
    enriched AS (
        SELECT
            wa.cloud_provider,
            wa.workspace_id,
            wa.warehouse_id,
            wa.period_start,
            wa.warehouse_name,
            wa.warehouse_size,
            p.dbu_quantity,
            p.cost_usd,
            qc.query_count,
            tc.top_consumer
        FROM warehouses_as_of wa
        JOIN priced p
          ON p.cloud_provider = wa.cloud_provider
         AND p.workspace_id = wa.workspace_id
         AND p.warehouse_id = wa.warehouse_id
         AND p.period_start = wa.period_start
        LEFT JOIN query_counts qc
          ON qc.cloud_provider = wa.cloud_provider
         AND qc.workspace_id = wa.workspace_id
         AND qc.warehouse_id = wa.warehouse_id
         AND qc.period_start = wa.period_start
        LEFT JOIN top_consumer tc
          ON tc.cloud_provider = wa.cloud_provider
         AND tc.workspace_id = wa.workspace_id
         AND tc.warehouse_id = wa.warehouse_id
         AND tc.period_start = wa.period_start
    ),
    with_prev_day AS (
        SELECT
            e.*,
            prev.cost_usd AS cost_usd_prev_day
        FROM enriched e
        LEFT JOIN enriched prev
          ON prev.cloud_provider = e.cloud_provider
         AND prev.workspace_id = e.workspace_id
         AND prev.warehouse_id = e.warehouse_id
         AND prev.period_start = e.period_start - INTERVAL 1 DAY
    )
    SELECT
        cloud_provider,
        workspace_id,
        warehouse_id,
        period_start,
        warehouse_name,
        warehouse_size,
        dbu_quantity,
        cost_usd,
        cost_usd_prev_day,
        (cost_usd - cost_usd_prev_day) / NULLIF(cost_usd_prev_day, 0) * 100 AS cost_delta_pct,
        COALESCE(query_count, 0) AS query_count,
        cost_usd / NULLIF(query_count, 0) AS cost_per_query_usd,
        top_consumer,
        current_timestamp() AS _generated_at
    FROM with_prev_day
    WHERE 1 = 1
    {output_period_filter}
    """
    return spark.sql(query)
