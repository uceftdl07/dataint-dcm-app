"""Agregation gold `gold_dbx_compute_cluster_governance` (snapshot conformite).

Etat de conformite courant de chaque cluster Databricks : tagging
obligatoire (owner/cost_center), version DBR toujours sous support LTS,
surdimensionnement recent, configuration single-node. Alimente le suivi de
gouvernance des clusters avec une action recommandee et sa severite.

Snapshot BORNE dans le temps (`activity_lower_bound`) : seuls les clusters vus
actifs ou modifies sur la fenetre sont evalues, et les regles de tagging/version
DBR ne visent que les clusters `ALL_PURPOSE` (`governance_applies`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pipelines.gold_dbx_compute.specs import (
    COST_CENTER_TAG_KEYS,
    DBR_LTS_RELEASE_DATES,
    DBR_LTS_SUPPORT_WINDOW_YEARS,
    GOVERNANCE_RECENT_DAYS,
    OWNER_TAG_KEYS,
)
from pipelines.gold_dbx_compute.sql_helpers import (
    CLUSTER_TYPE_ALL_PURPOSE,
    cluster_type_case_expr,
    sql_string_list,
    tag_present_sql,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date

    from pyspark.sql import DataFrame, SparkSession


def dbr_lts_versions_supported_as_of(
    today: date,
    *,
    release_dates: Mapping[str, date] = DBR_LTS_RELEASE_DATES,
    window_years: int = DBR_LTS_SUPPORT_WINDOW_YEARS,
) -> frozenset[str]:
    """Versions DBR LTS dont le support (GA + `window_years` ans) couvre `today`.

    Formule : une version `v` est retenue si `today < ga_date(v) +
    window_years annees`. Calcule a chaque run avec le `today` du run (jamais
    `date.today()` ici, pour rester testable) : evite de devoir retirer une
    version de `DBR_LTS_RELEASE_DATES` a la fin de son support.
    """
    return frozenset(
        version
        for version, ga_date in release_dates.items()
        if today < ga_date.replace(year=ga_date.year + window_years)
    )


def build_cluster_governance(
    spark: SparkSession,
    *,
    clusters_table: str,
    efficiency_daily_table: str,
    dbr_lts_versions: frozenset[str],
    activity_lower_bound: date,
    governance_recent_days: int = GOVERNANCE_RECENT_DAYS,
) -> DataFrame:
    """Construit `gold_dbx_compute_cluster_governance`.

    Args:
        spark: session Spark utilisee pour executer la requete generee.
        clusters_table: nom qualifie (`catalog.schema.table`) de
            `curated_dbx_compute_clusters` (dernier etat connu du cluster).
        efficiency_daily_table: nom qualifie de
            `gold_dbx_compute_cluster_efficiency_daily` (signal de
            surdimensionnement recent ET signal d'activite delimitant le
            perimetre, cf. `activity_lower_bound`).
        dbr_lts_versions: versions DBR LTS encore supportees a la date du
            run (cf. `dbr_lts_versions_supported_as_of`).
        activity_lower_bound: borne basse incluse du perimetre : seuls les
            clusters vus actifs (`period_start >= borne` cote efficiency) ou
            modifies (`change_time >= borne`) depuis cette date sont evalues
            (cf. `GOVERNANCE_ACTIVITY_WINDOW_DAYS`).
        governance_recent_days: fenetre en jours consideree "recente" pour le
            signal `node_oversized` (defaut `GOVERNANCE_RECENT_DAYS`).

    Returns:
        Le DataFrame `gold_dbx_compute_cluster_governance` resultant.

    Grain : `(cloud_provider, workspace_id, cluster_id)` — dernier etat connu,
    TOUJOURS recalcule en entier (snapshot, pas une serie temporelle) mais sur
    un PERIMETRE BORNE dans le temps par `activity_lower_bound` : sans borne, le
    snapshot reevalue chaque run tout cluster jamais vu en curated, dont les
    clusters JOB/PIPELINE ephemeres (une ligne par execution), et grossit
    indefiniment. Les lignes sorties de la fenetre sont supprimees a l'ecriture
    (cf. `CLUSTER_GOVERNANCE_SPEC.absent_row_delete_guard`), pas ici.

    `dbr_version` (ex. `16.4.x-scala2.12`, `-aarch64-`, `-photon-`,
    `-cpu-ml-` selon le flavor, ou `dlt:...` pour les clusters Delta Live
    Tables) n'est jamais litteralement au format lisible officiel Databricks
    (`'16.4.x-lts'`) utilise par `DBR_LTS_RELEASE_DATES`. `dbr_lts_key`
    extrait donc le prefixe `major.minor.x` de `dbr_version` avant de
    comparer. Cas `dlt:...` (pas de prefixe numerique en tete) :
    `regexp_extract` sans correspondance renvoie `''` (chaine vide, PAS
    `NULL`, comportement Spark documente) -> `dbr_lts_key = '-lts'`, qui ne
    correspond jamais a une entree du referentiel -> `dbr_is_lts_current`
    reste `false` pour ces clusters (resultat attendu, pas un bug : un
    cluster DLT n'est de toute facon pas cible par la recommandation "mettre
    a jour vers une LTS supportee").

    Champs et formule de calcul :
      - `governance_applies` : vrai si les regles de TAGGING et de VERSION DBR
        s'appliquent au cluster. Formule : `cluster_type = 'ALL_PURPOSE'`. Les
        tags et le runtime d'un cluster JOB/PIPELINE sont imposes par la
        definition du job/pipeline, la correction se fait la-bas et non par
        cluster. `node_oversized` reste evalue pour tous les types (propriete
        observee du cluster lui-meme).
      - `has_owner_tag`/`has_cost_center_tag` : conformite au tagging
        obligatoire. Formule : presence d'une cle de tag `owner` /
        `cost_center` (orthographes de `OWNER_TAG_KEYS` /
        `COST_CENTER_TAG_KEYS`, casse ignoree, valeur non vide) sur le dernier
        etat connu du cluster (cf. `sql_helpers.tag_present_sql`).
      - `dbr_version` : version du runtime Databricks (passthrough).
      - `dbr_is_lts_current` : vrai si la version DBR est une LTS encore
        supportee par Databricks. Formule : `dbr_lts_key IN
        (dbr_lts_versions)` (cf. `dbr_lts_versions_supported_as_of`).
      - `node_oversized` : vrai si le cluster a ete detecte surdimensionne
        recemment. Formule : `utilization_status = 'OVER'` (dans
        `gold_dbx_compute_cluster_efficiency_daily`) au moins une fois durant
        les `governance_recent_days` derniers jours connus.
      - `is_single_node` : vrai si le cluster est configure en single-node.
        Formule : `worker_count = 0`.
      - `recommended_action`/`severity` : action de gouvernance a mener et
        son niveau de priorite. Formule : priorite (la plus haute en
        premier) — tag manquant (`LOW`) > DBR obsolete (`HIGH`) > cluster
        surdimensionne (`MEDIUM`). Les deux premieres regles ne sont evaluees
        que si `governance_applies`.
      - `cluster_type` : categorie du cluster derivee de `cluster_source`
        (deja inclus via `SELECT c.*` de `latest_clusters`) via
        `cluster_type_case_expr` : `ALL_PURPOSE`, `JOB` (ephemere, cf.
        `gold_dbx_compute.job_cluster_cost_daily`) ou `PIPELINE`. Les clusters
        `OTHER` (cluster_source non mappe, cf. `gold_dbx_compute.cluster_cost_daily`)
        sont exclus de la sortie, comme les autres tables gold clusters.
    """
    lts_versions_sql = sql_string_list(tuple(sorted(dbr_lts_versions)))
    activity_floor = activity_lower_bound.isoformat()
    applies = f"({cluster_type_case_expr('lc.cluster_source')} = '{CLUSTER_TYPE_ALL_PURPOSE}')"
    query = f"""
    WITH recent_activity AS (
        SELECT DISTINCT cloud_provider, workspace_id, cluster_id
        FROM {efficiency_daily_table}
        WHERE period_start >= DATE '{activity_floor}'
    ),
    latest_clusters AS (
        SELECT c.*
        FROM {clusters_table} c
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY c.cloud_provider, c.workspace_id, c.cluster_id
            ORDER BY c.change_time DESC
        ) = 1
    ),
    -- Perimetre : cluster vu actif sur la fenetre, ou dont la configuration a
    -- change depuis (cluster cree/modifie mais pas encore demarre).
    in_scope_clusters AS (
        SELECT lc.*
        FROM latest_clusters lc
        LEFT JOIN recent_activity ra
          ON ra.cloud_provider = lc.cloud_provider AND ra.workspace_id = lc.workspace_id
         AND ra.cluster_id = lc.cluster_id
        WHERE ra.cluster_id IS NOT NULL
           OR lc.change_time >= DATE '{activity_floor}'
    ),
    recent_efficiency AS (
        SELECT
            cloud_provider, workspace_id, cluster_id,
            MAX(CASE WHEN utilization_status = 'OVER' THEN 1 ELSE 0 END) AS node_oversized_flag
        FROM (
            SELECT
                *,
                RANK() OVER (
                    PARTITION BY cloud_provider, workspace_id, cluster_id
                    ORDER BY period_start DESC
                ) AS recency_rank
            FROM {efficiency_daily_table}
            WHERE period_start >= DATE '{activity_floor}'
        ) ranked
        WHERE recency_rank <= {governance_recent_days}
        GROUP BY cloud_provider, workspace_id, cluster_id
    ),
    tagged AS (
        SELECT
            lc.*,
            {applies} AS governance_applies,
            {tag_present_sql("lc.tags", OWNER_TAG_KEYS)} AS has_owner_tag,
            {tag_present_sql("lc.tags", COST_CENTER_TAG_KEYS)} AS has_cost_center_tag,
            COALESCE(lc.worker_count = 0, false) AS is_single_node,
            CONCAT(
                regexp_extract(lc.dbr_version, '^([0-9]+(?:\\.[0-9]+)?\\.x)', 1),
                '-lts'
            ) AS dbr_lts_key
        FROM in_scope_clusters lc
    )
    SELECT
        t.cloud_provider,
        t.workspace_id,
        t.cluster_id,
        t.cluster_name,
        {cluster_type_case_expr("t.cluster_source")} AS cluster_type,
        t.governance_applies,
        t.has_owner_tag,
        t.has_cost_center_tag,
        t.dbr_version,
        (t.dbr_lts_key IN ({lts_versions_sql})) AS dbr_is_lts_current,
        (COALESCE(re.node_oversized_flag, 0) = 1) AS node_oversized,
        t.is_single_node,
        CASE
            WHEN t.governance_applies AND (NOT t.has_owner_tag OR NOT t.has_cost_center_tag)
                THEN 'Ajouter les tags owner/cost_center manquants'
            WHEN t.governance_applies AND t.dbr_lts_key NOT IN ({lts_versions_sql})
                THEN 'Mettre a jour vers une version DBR LTS supportee'
            WHEN COALESCE(re.node_oversized_flag, 0) = 1
                THEN 'Redimensionner le cluster (surdimensionne)'
            ELSE NULL
        END AS recommended_action,
        CASE
            WHEN t.governance_applies AND (NOT t.has_owner_tag OR NOT t.has_cost_center_tag)
                THEN 'LOW'
            WHEN t.governance_applies AND t.dbr_lts_key NOT IN ({lts_versions_sql}) THEN 'HIGH'
            WHEN COALESCE(re.node_oversized_flag, 0) = 1 THEN 'MEDIUM'
            ELSE NULL
        END AS severity,
        current_timestamp() AS _generated_at
    FROM tagged t
    LEFT JOIN recent_efficiency re
      ON re.cloud_provider = t.cloud_provider AND re.workspace_id = t.workspace_id
     AND re.cluster_id = t.cluster_id
    WHERE {cluster_type_case_expr("t.cluster_source")} = '{CLUSTER_TYPE_ALL_PURPOSE}'
    """
    return spark.sql(query)
