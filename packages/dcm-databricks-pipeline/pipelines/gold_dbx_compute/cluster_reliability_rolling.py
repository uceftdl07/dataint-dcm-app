"""Agregation gold `gold_dbx_compute_cluster_reliability_rolling` (fiabilite, fenetres).

Rollup 1/7/30/90 jours de `gold_dbx_compute_cluster_reliability_daily` : pour
chaque cluster, demarrages et terminaisons anormales cumules sur les derniers
`window_days` jours "as of" le dernier jour disponible, temps de demarrage moyen
pondere sur la fenetre et configuration/raison de terminaison au dernier etat
connu.

Regles de derivation : `start_count`/`unexpected_termination_count` sont
additifs (somme). `avg_startup_seconds` est une moyenne : recalculee ponderee
par le nombre de demarrages du jour (SUM(avg * start_count) / SUM(start_count)),
seuls les jours ayant une latence mesuree entrant dans la ponderation. Les
champs categoriels/de configuration (`cluster_name`, `cluster_type`,
`top_termination_reason`, `auto_termination_minutes`, `has_auto_termination`)
sont repris au dernier etat connu -- `top_termination_reason` reflete donc le
dernier jour, pas l'ensemble de la fenetre.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.specs import ROLLING_WINDOWS
from pipelines.gold_dbx_compute.sql_helpers import rolling_windows_array_sql

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession


def build_cluster_reliability_rolling(
    spark: SparkSession,
    *,
    cluster_reliability_daily_table: str,
    rolling_windows: tuple[int, ...] = ROLLING_WINDOWS,
) -> DataFrame:
    """Construit `gold_dbx_compute_cluster_reliability_rolling`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        cluster_reliability_daily_table: nom qualifie (`catalog.schema.table`)
            de `gold_dbx_compute_cluster_reliability_daily` (unique source).
        rolling_windows: fenetres glissantes (jours) a materialiser, une ligne
            par cluster ET par fenetre (defaut `ROLLING_WINDOWS`).

    Returns:
        Le DataFrame `gold_dbx_compute_cluster_reliability_rolling` resultant.

    Grain : `(cloud_provider, workspace_id, cluster_id, window_days)`. Snapshot
    "as of" le dernier jour disponible (`as_of_date = MAX(period_start)`).

    Champs : `start_count`/`unexpected_termination_count` sommes sur la fenetre
    `(as_of_date - window_days, as_of_date]` ; `avg_startup_seconds` = moyenne
    ponderee par les demarrages du jour ; `cluster_name`/`cluster_type`/
    `top_termination_reason`/`auto_termination_minutes`/`has_auto_termination`
    au dernier etat connu.
    """
    windows_array = rolling_windows_array_sql(rolling_windows)
    query = f"""
    WITH daily AS (
        SELECT
            cloud_provider,
            workspace_id,
            cluster_id,
            period_start,
            cluster_name,
            cluster_type,
            start_count,
            avg_startup_seconds,
            unexpected_termination_count,
            top_termination_reason,
            auto_termination_minutes,
            has_auto_termination
        FROM {cluster_reliability_daily_table}
    ),
    anchor AS (
        SELECT MAX(period_start) AS as_of_date FROM daily
    ),
    windows AS (
        SELECT explode({windows_array}) AS window_days
    ),
    latest_attrs AS (
        SELECT
            cloud_provider,
            workspace_id,
            cluster_id,
            cluster_name,
            cluster_type,
            top_termination_reason,
            auto_termination_minutes,
            has_auto_termination
        FROM daily
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY cloud_provider, workspace_id, cluster_id
            ORDER BY period_start DESC
        ) = 1
    ),
    agg AS (
        SELECT
            d.cloud_provider,
            d.workspace_id,
            d.cluster_id,
            w.window_days,
            a.as_of_date,
            date_add(a.as_of_date, -(w.window_days - 1)) AS window_start,
            SUM(d.start_count) AS start_count,
            SUM(d.unexpected_termination_count) AS unexpected_termination_count,
            SUM(CASE
                    WHEN d.avg_startup_seconds IS NOT NULL
                    THEN d.avg_startup_seconds * d.start_count
                END)
                / NULLIF(SUM(CASE
                    WHEN d.avg_startup_seconds IS NOT NULL
                    THEN d.start_count
                END), 0) AS avg_startup_seconds
        FROM daily d
        CROSS JOIN anchor a
        CROSS JOIN windows w
        WHERE d.period_start > date_add(a.as_of_date, -w.window_days)
          AND d.period_start <= a.as_of_date
        GROUP BY d.cloud_provider, d.workspace_id, d.cluster_id, w.window_days, a.as_of_date
    )
    SELECT
        g.cloud_provider,
        g.workspace_id,
        g.cluster_id,
        g.window_days,
        g.as_of_date,
        g.window_start,
        la.cluster_name,
        la.cluster_type,
        g.start_count,
        g.avg_startup_seconds,
        g.unexpected_termination_count,
        la.top_termination_reason,
        la.auto_termination_minutes,
        la.has_auto_termination,
        current_timestamp() AS _generated_at
    FROM agg g
    LEFT JOIN latest_attrs la
      ON la.cloud_provider = g.cloud_provider
     AND la.workspace_id = g.workspace_id
     AND la.cluster_id = g.cluster_id
    WHERE g.start_count > 0 OR g.unexpected_termination_count > 0
    """
    return spark.sql(query)
