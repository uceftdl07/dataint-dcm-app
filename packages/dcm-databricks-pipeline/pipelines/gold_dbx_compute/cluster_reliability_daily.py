"""Agregation gold `gold_dbx_compute_cluster_reliability_daily` (fiabilite).

Fiabilite quotidienne des clusters Databricks : nombre de demarrages, temps
de demarrage moyen, terminaisons pour une raison anormale et raison la plus
frequente, configuration d'auto-arret. Alimente le suivi des incidents et
de la stabilite operationnelle des clusters.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.sql_helpers import (
    cluster_type_case_expr,
    lower_bound_predicate,
    sql_string_list,
)

if TYPE_CHECKING:
    from datetime import date

    from pyspark.sql import DataFrame, SparkSession


# Actions d'audit `system.access.audit` (service "clusters") du demarrage
# d'un cluster ; noms d'evenements d'audit, pas les endpoints REST
# Databricks Clusters.
ACCESS_AUDIT_CLUSTER_START_ACTIONS = ("create", "start")

# Actions d'audit de la terminaison d'un cluster.
ACCESS_AUDIT_CLUSTER_TERMINATE_ACTIONS = ("delete", "permanentDelete")

# Actions d'audit de completion asynchrone d'un demarrage (`create`/`start`).
ACCESS_AUDIT_CLUSTER_START_RESULT_ACTIONS = ("createResult", "startResult")

# Action d'audit de completion asynchrone d'une terminaison (`delete`).
ACCESS_AUDIT_CLUSTER_TERMINATE_RESULT_ACTIONS = ("deleteResult",)

# Cle du `request_params` portant la raison de terminaison sur `deleteResult`.
TERMINATION_REASON_KEY = "clusterTerminationReasonCode"

# Raisons de terminaison considerees normales, exclues de
# `unexpected_termination_count`.
EXPECTED_TERMINATION_REASONS = ("USER_REQUEST", "INACTIVITY", "JOB_FINISHED")


def build_cluster_reliability_daily(
    spark: SparkSession,
    *,
    clusters_table: str,
    access_audit_table: str,
    lower_bound: date | None,
) -> DataFrame:
    """Construit `gold_dbx_compute_cluster_reliability_daily`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        clusters_table: nom qualifie (`catalog.schema.table`) de
            `curated_dbx_compute_clusters` (dernier etat connu du cluster).
        access_audit_table: nom qualifie de `curated_dbx_access_audit`
            (evenements de cycle de vie cluster).
        lower_bound: borne basse incluse de `period_start` pour la lecture
            incrementale ; `None` pour recalculer l'historique complet.

    Returns:
        Le DataFrame `gold_dbx_compute_cluster_reliability_daily` resultant.

    Grain : `(cloud_provider, workspace_id, cluster_id, period_start)`.
    Source : evenements de cycle de vie cluster dans `curated_dbx_access_audit`
    (`event_date`) + dernier etat connu de `curated_dbx_compute_clusters` pour
    `auto_termination_minutes`.

    `cluster_id` : la clef varie selon l'action -> `COALESCE` sur les 3 formes
    rencontrees : `request_params['cluster_id']` (snake_case ; `start`/
    `delete`/`permanentDelete`), `request_params['clusterId']` (camelCase ;
    `createResult`/`startResult`/`deleteResult`), et pour `create` (qui n'a
    PAS de `cluster_id` dans `request_params` : l'ID n'existe pas encore au
    moment de la requete) `get_json_object(response.result, '$.cluster_id')`.

    Champs et formule de calcul :
      - `start_count` : nombre de fois ou le cluster a demarre dans la
        journee. Formule : `COUNT(*)` des actions `create`/`start`.
      - `avg_startup_seconds` : temps moyen mis par le cluster pour demarrer.
        Formule : `AVG(next_event_time - event_time)` ou `next_event_time`
        (via `LEAD` partitionne par cluster, ordonne par `event_time`) est
        explicitement la completion `createResult`/`startResult` du
        `create`/`start` correspondant (pas la prochaine transition de cycle
        de vie quelconque, ce qui fausserait la latence mesuree).
      - `unexpected_termination_count` : nombre de terminaisons pour une
        raison anormale (hors arret utilisateur, inactivite ou fin de job).
        Formule : `COUNT` des evenements `deleteResult` dont la raison
        (`request_params['clusterTerminationReasonCode']`) n'est pas dans
        `EXPECTED_TERMINATION_REASONS`.
      - `top_termination_reason` : raison de terminaison la plus frequente ce
        jour-la. Formule : `mode()` de la raison de terminaison parmi les
        evenements `deleteResult`.
      - `auto_termination_minutes`/`has_auto_termination` : configuration
        d'auto-arret du cluster au dernier etat connu (`change_time <
        period_start + 1 jour` : etat connu a un instant quelconque de
        `period_start`, pas seulement avant minuit - un cast `TIMESTAMP
        <= DATE` a minuit exclurait a tort les clusters crees le jour
        meme).
      - `cluster_type` : categorie du cluster derivee de `cluster_source`
        (dernier etat connu) via `cluster_type_case_expr` : `ALL_PURPOSE`,
        `JOB` (ephemere, cf. `gold_dbx_compute.job_cluster_cost_daily`) ou
        `PIPELINE`. Permet de filtrer les clusters JOB des clusters
        persistants avant toute analyse agregee de fiabilite. Les clusters
        sans aucun etat connu dans `curated_dbx_compute_clusters` (categorie
        `OTHER`, cf. `gold_dbx_compute.cluster_cost_daily`) sont exclus de la
        sortie plutot qu'exposes sans `auto_termination_minutes` ni type
        fiables.
      - `cluster_name` : nom du cluster au dernier etat connu (meme jointure
        `clusters_as_of` que `cluster_type`/`auto_termination_minutes`) -
        permet a `gold_dbx_compute.recommendations` de resoudre `object_name`
        directement depuis cette table (rolling), sans dependre du perimetre
        borne de `gold_dbx_compute_cluster_governance`.
    """
    all_cluster_actions = (
        ACCESS_AUDIT_CLUSTER_START_ACTIONS
        + ACCESS_AUDIT_CLUSTER_TERMINATE_ACTIONS
        + ACCESS_AUDIT_CLUSTER_START_RESULT_ACTIONS
        + ACCESS_AUDIT_CLUSTER_TERMINATE_RESULT_ACTIONS
    )
    start_actions_sql = sql_string_list(ACCESS_AUDIT_CLUSTER_START_ACTIONS)
    start_result_actions_sql = sql_string_list(ACCESS_AUDIT_CLUSTER_START_RESULT_ACTIONS)
    terminate_result_actions_sql = sql_string_list(ACCESS_AUDIT_CLUSTER_TERMINATE_RESULT_ACTIONS)
    expected_reasons_sql = sql_string_list(EXPECTED_TERMINATION_REASONS)
    period_filter = lower_bound_predicate("event_date", lower_bound)
    query = f"""
    WITH audit_raw AS (
        SELECT
            cloud_provider,
            account_id,
            workspace_id,
            event_time,
            event_date,
            action_name,
            request_params,
            COALESCE(
                request_params['cluster_id'],
                request_params['clusterId'],
                get_json_object(response.result, '$.cluster_id')
            ) AS cluster_id
        FROM {access_audit_table}
        WHERE action_name IN ({sql_string_list(all_cluster_actions)})
        {period_filter}
    ),
    audit_filtered AS (
        -- Exclut les evenements sans cluster_id resolvable (ex. `create` en
        -- echec, REQUEST_LIMIT_EXCEEDED : jamais assigne puisque le cluster
        -- n'a jamais existe). Sans ce filtre, ces echecs se regroupent sous
        -- une cle cluster_id NULL qui casse le grain per-cluster de la table.
        SELECT * FROM audit_raw WHERE cluster_id IS NOT NULL
    ),
    starts AS (
        SELECT
            cloud_provider, workspace_id, cluster_id, event_date AS period_start,
            COUNT(*) AS start_count
        FROM audit_filtered
        WHERE action_name IN ({start_actions_sql})
        GROUP BY cloud_provider, workspace_id, cluster_id, event_date
    ),
    ordered_events AS (
        SELECT
            *,
            LEAD(event_time) OVER (
                PARTITION BY cloud_provider, workspace_id, cluster_id ORDER BY event_time
            ) AS next_event_time,
            LEAD(action_name) OVER (
                PARTITION BY cloud_provider, workspace_id, cluster_id ORDER BY event_time
            ) AS next_action_name
        FROM audit_filtered
    ),
    startup_latency AS (
        SELECT
            cloud_provider, workspace_id, cluster_id, event_date AS period_start,
            AVG(
                CASE
                    WHEN action_name IN ({start_actions_sql})
                     AND next_action_name IN ({start_result_actions_sql})
                    THEN CAST(next_event_time AS DOUBLE) - CAST(event_time AS DOUBLE)
                END
            ) AS avg_startup_seconds
        FROM ordered_events
        GROUP BY cloud_provider, workspace_id, cluster_id, event_date
    ),
    terminations AS (
        SELECT
            cloud_provider, workspace_id, cluster_id, event_date AS period_start,
            SUM(
                CASE
                    WHEN action_name IN ({terminate_result_actions_sql})
                     AND COALESCE(request_params['{TERMINATION_REASON_KEY}'], 'UNKNOWN')
                         NOT IN ({expected_reasons_sql})
                    THEN 1
                    ELSE 0
                END
            ) AS unexpected_termination_count,
            mode(
                CASE
                    WHEN action_name IN ({terminate_result_actions_sql})
                    THEN request_params['{TERMINATION_REASON_KEY}']
                END
            ) AS top_termination_reason
        FROM audit_filtered
        GROUP BY cloud_provider, workspace_id, cluster_id, event_date
    ),
    all_keys AS (
        SELECT cloud_provider, workspace_id, cluster_id, period_start FROM starts
        UNION
        SELECT cloud_provider, workspace_id, cluster_id, period_start FROM terminations
        UNION
        SELECT cloud_provider, workspace_id, cluster_id, period_start FROM startup_latency
    ),
    clusters_as_of AS (
        SELECT
            k.cloud_provider, k.workspace_id, k.cluster_id, k.period_start,
            c.cluster_name,
            c.cluster_source,
            c.auto_termination_minutes
        FROM all_keys k
        LEFT JOIN {clusters_table} c
          ON c.cloud_provider = k.cloud_provider
         AND c.workspace_id = k.workspace_id
         AND c.cluster_id = k.cluster_id
         AND c.change_time < k.period_start + INTERVAL 1 DAY
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY k.cloud_provider, k.workspace_id, k.cluster_id, k.period_start
            ORDER BY c.change_time DESC
        ) = 1
    )
    SELECT
        w.cloud_provider,
        w.workspace_id,
        w.cluster_id,
        w.period_start,
        w.cluster_name,
        {cluster_type_case_expr("w.cluster_source")} AS cluster_type,
        COALESCE(s.start_count, 0) AS start_count,
        sl.avg_startup_seconds,
        COALESCE(t.unexpected_termination_count, 0) AS unexpected_termination_count,
        t.top_termination_reason,
        w.auto_termination_minutes,
        (COALESCE(w.auto_termination_minutes, 0) > 0) AS has_auto_termination,
        current_timestamp() AS _generated_at
    FROM clusters_as_of w
    LEFT JOIN starts s
      ON s.cloud_provider = w.cloud_provider AND s.workspace_id = w.workspace_id
     AND s.cluster_id = w.cluster_id AND s.period_start = w.period_start
    LEFT JOIN startup_latency sl
      ON sl.cloud_provider = w.cloud_provider AND sl.workspace_id = w.workspace_id
     AND sl.cluster_id = w.cluster_id AND sl.period_start = w.period_start
    LEFT JOIN terminations t
      ON t.cloud_provider = w.cloud_provider AND t.workspace_id = w.workspace_id
     AND t.cluster_id = w.cluster_id AND t.period_start = w.period_start
    WHERE {cluster_type_case_expr("w.cluster_source")} <> 'OTHER'
    """
    return spark.sql(query)
