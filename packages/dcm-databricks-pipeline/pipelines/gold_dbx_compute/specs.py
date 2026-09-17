"""Contrat d'agregation : registre des tables gold compute (clusters).

Symetrique a `pipelines.system_tables.specs` (meme esprit : la spec porte toute
la configuration metier, aucune mecanique ici) mais pour la couche GOLD : au
lieu d'une seule table source -> une seule table curated, une agregation gold
lit PLUSIEURS tables curated deja unifiees et ecrit UNE table gold.

Scaffolding partage : ce registre (`GOLD_SPECS`) et les constantes de ce module
seront etendus par T003 (warehouses) et T004 (transverse reactif/predictif) —
ajouter une entree, ne jamais modifier la structure existante (cf.
`specs/012-compute-metrics-ingestion/merge-strategy.md`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

# Tables curated sources (deja produites par `pipelines.system_tables`, cf. T001) :
# importees depuis le registre existant plutot que redeclarees en dur ici, pour
# ne jamais diverger si ces noms changent un jour cote curated.
from pipelines.gold_landing_zone.view import DIM_LANDING_ZONE_VIEW
from pipelines.reference_lz.specs import CURATED_DBX_WORKSPACE
from pipelines.system_tables.specs import (
    CURATED_ACCESS_AUDIT,
    CURATED_BILLING_LIST_PRICES,
    CURATED_BILLING_USAGE,
    CURATED_COMPUTE_CLUSTERS,
    CURATED_COMPUTE_NODE_TIMELINE,
    CURATED_COMPUTE_NODE_TYPES,
    CURATED_COMPUTE_WAREHOUSE_EVENTS,
    CURATED_COMPUTE_WAREHOUSES,
    CURATED_LAKEFLOW_JOB_RUN_TIMELINE,
    CURATED_LAKEFLOW_JOB_TASK_RUN_TIMELINE,
    CURATED_LAKEFLOW_JOBS,
    CURATED_LAKEFLOW_PIPELINE_UPDATE_TIMELINE,
    CURATED_LAKEFLOW_PIPELINES,
    CURATED_QUERY_HISTORY,
    DEFAULT_CATALOG,
    DEFAULT_SCHEMA,
)

__all__ = [
    "CLUSTER_COST_DAILY_SPEC",
    "CLUSTER_COST_ROLLING_MERGE_KEYS",
    "CLUSTER_COST_ROLLING_SPEC",
    "CLUSTER_DAILY_MERGE_KEYS",
    "CLUSTER_EFFICIENCY_DAILY_SPEC",
    "CLUSTER_EFFICIENCY_ROLLING_MERGE_KEYS",
    "CLUSTER_EFFICIENCY_ROLLING_SPEC",
    "CLUSTER_GOVERNANCE_MERGE_KEYS",
    "CLUSTER_GOVERNANCE_SPEC",
    "CLUSTER_RELIABILITY_DAILY_SPEC",
    "CLUSTER_RELIABILITY_ROLLING_MERGE_KEYS",
    "CLUSTER_RELIABILITY_ROLLING_SPEC",
    "COST_CENTER_TAG_KEYS",
    "DBR_LTS_RELEASE_DATES",
    "DBR_LTS_SUPPORT_WINDOW_YEARS",
    "DEFAULT_CATALOG",
    "DEFAULT_SCHEMA",
    "FORECAST_ABSENT_ROW_DELETE_GUARD",
    "FORECAST_DAILY_SPEC",
    "FORECAST_HORIZON_DAYS",
    "FORECAST_MAX_OBSERVED_RATIO",
    "FORECAST_MERGE_KEYS",
    "FORECAST_MIN_OBSERVED_DAYS",
    "FORECAST_OBSERVED_LOOKBACK_DAYS",
    "FORECAST_PREDICTION_INTERVAL_WIDTH",
    "GOLD_CLUSTER_COST_DAILY",
    "GOLD_CLUSTER_COST_ROLLING",
    "GOLD_CLUSTER_EFFICIENCY_DAILY",
    "GOLD_CLUSTER_EFFICIENCY_ROLLING",
    "GOLD_CLUSTER_GOVERNANCE",
    "GOLD_CLUSTER_RELIABILITY_DAILY",
    "GOLD_CLUSTER_RELIABILITY_ROLLING",
    "GOLD_FORECAST_DAILY",
    "GOLD_JOB_CLUSTER_COST_DAILY",
    "GOLD_JOB_CLUSTER_COST_ROLLING",
    "GOLD_JOB_EFFICIENCY_DAILY",
    "GOLD_JOB_EFFICIENCY_ROLLING",
    "GOLD_PIPELINE_COST_DAILY",
    "GOLD_PIPELINE_COST_ROLLING",
    "GOLD_PIPELINE_EFFICIENCY_DAILY",
    "GOLD_PIPELINE_EFFICIENCY_ROLLING",
    "GOLD_PIPELINE_UPDATE_STATS",
    "GOLD_RECOMMENDATIONS",
    "GOLD_SERVERLESS_COST_DAILY",
    "GOLD_SERVERLESS_COST_ROLLING",
    "GOLD_SERVERLESS_GOVERNANCE",
    "GOLD_SPECS",
    "GOLD_SPEC_KEYS",
    "GOLD_TOTAL_COST_DAILY",
    "GOLD_WAREHOUSE_COST_DAILY",
    "GOLD_WAREHOUSE_COST_ROLLING",
    "GOLD_WAREHOUSE_QUERY_PERFORMANCE_DAILY",
    "GOLD_WAREHOUSE_QUERY_PERFORMANCE_ROLLING",
    "GOLD_WAREHOUSE_UTILIZATION_DAILY",
    "GOLD_WAREHOUSE_UTILIZATION_ROLLING",
    "GOVERNANCE_ACTIVITY_WINDOW_DAYS",
    "GOVERNANCE_RECENT_DAYS",
    "INCREMENTAL_LOOKBACK_DAYS",
    "JOB_CLUSTER_COST_DAILY_MERGE_KEYS",
    "JOB_CLUSTER_COST_DAILY_SPEC",
    "JOB_CLUSTER_COST_ROLLING_MERGE_KEYS",
    "JOB_CLUSTER_COST_ROLLING_SPEC",
    "JOB_EFFICIENCY_DAILY_MERGE_KEYS",
    "JOB_EFFICIENCY_DAILY_SPEC",
    "JOB_EFFICIENCY_ROLLING_MERGE_KEYS",
    "JOB_EFFICIENCY_ROLLING_SPEC",
    "OWNER_TAG_KEYS",
    "PIPELINE_COST_DAILY_MERGE_KEYS",
    "PIPELINE_COST_DAILY_SPEC",
    "PIPELINE_COST_ROLLING_MERGE_KEYS",
    "PIPELINE_COST_ROLLING_SPEC",
    "PIPELINE_EFFICIENCY_DAILY_MERGE_KEYS",
    "PIPELINE_EFFICIENCY_DAILY_SPEC",
    "PIPELINE_EFFICIENCY_ROLLING_MERGE_KEYS",
    "PIPELINE_EFFICIENCY_ROLLING_SPEC",
    "PIPELINE_UPDATE_STATS_MERGE_KEYS",
    "PIPELINE_UPDATE_STATS_SPEC",
    "RECOMMENDATIONS_MERGE_KEYS",
    "RECOMMENDATIONS_RESOLVED_RETENTION_DAYS",
    "RECOMMENDATIONS_ROLLING_WINDOW_DAYS",
    "RECOMMENDATIONS_SPEC",
    "ROLLING_WINDOWS",
    "SERVERLESS_COST_DAILY_MERGE_KEYS",
    "SERVERLESS_COST_DAILY_SPEC",
    "SERVERLESS_COST_ROLLING_MERGE_KEYS",
    "SERVERLESS_COST_ROLLING_SPEC",
    "SERVERLESS_GOVERNANCE_MERGE_KEYS",
    "SERVERLESS_GOVERNANCE_SPEC",
    "SNAPSHOT_ABSENT_ROW_DELETE_GUARD",
    "SNAPSHOT_ABSENT_ROW_GRACE_DAYS",
    "TOP_COST_RANK_THRESHOLD",
    "TOTAL_COST_DAILY_MERGE_KEYS",
    "TOTAL_COST_DAILY_SPEC",
    "WAREHOUSE_COST_DAILY_SPEC",
    "WAREHOUSE_COST_ROLLING_MERGE_KEYS",
    "WAREHOUSE_COST_ROLLING_SPEC",
    "WAREHOUSE_DAILY_MERGE_KEYS",
    "WAREHOUSE_FAILURE_RATE_PCT_THRESHOLD",
    "WAREHOUSE_IDLE_PCT_OVER_THRESHOLD",
    "WAREHOUSE_PEAK_CONCURRENCY_UNDER_RATIO",
    "WAREHOUSE_QUERY_HISTORY_LOOKBACK_DAYS",
    "WAREHOUSE_QUERY_PERFORMANCE_DAILY_SPEC",
    "WAREHOUSE_QUERY_PERFORMANCE_ROLLING_MERGE_KEYS",
    "WAREHOUSE_QUERY_PERFORMANCE_ROLLING_SPEC",
    "WAREHOUSE_QUERY_STILL_RUNNING_MAX_HOURS",
    "WAREHOUSE_QUEUE_TIME_P95_THRESHOLD_MS",
    "WAREHOUSE_SESSION_LOOKBACK_DAYS",
    "WAREHOUSE_SPILL_QUERY_COUNT_THRESHOLD",
    "WAREHOUSE_TYPE_SERVERLESS",
    "WAREHOUSE_UTILIZATION_DAILY_SPEC",
    "WAREHOUSE_UTILIZATION_ROLLING_MERGE_KEYS",
    "WAREHOUSE_UTILIZATION_ROLLING_SPEC",
    "GoldAggregationSpec",
]


@dataclass(frozen=True)
class GoldAggregationSpec:
    """Decrit une agregation gold : plusieurs tables curated -> une table gold.

    Generique (aucune notion de domaine compute) : un plugin gold instancie
    cette spec pour ses propres tables. Pilote la fenetre de rafraichissement
    (cf. `research.md` R9) :

    - `watermark_column` : colonne de grain temporel de la table CIBLE (gold)
      utilisee pour determiner si la table existe deja (premier run) ; `None`
      pour les snapshots recalcules integralement a chaque run (ex.
      `governance`, sans grain `period_start`).
    - `initial_mode` : strategie du tout premier run (table cible absente) ;
      seule la valeur `"full"` est geree aujourd'hui (agrege tout l'historique
      curated disponible, backfille par la couche curated — cf. `INITIAL_BACKFILL_DAYS`
      de `pipelines.system_tables.specs`).
    - `incremental_lookback_days` : fenetre (jours) des runs suivants —
      `period_start >= today - N` ; `None` quand `watermark_column` est `None`
      (pas de fenetre, toujours recalcule en entier).
    - `column_comments`/`table_comment` : commentaires attaches a la table gold
      a sa creation (`COMMENT ON TABLE` / `ALTER TABLE ... ALTER COLUMN ...
      COMMENT`, cf. `pipelines.common.writers.merge_into_table`) — visibles
      dans Catalog Explorer (UI Databricks), independamment de la docstring
      Python du builder qui derive la table.
    - `absent_row_delete_guard` : active la SUPPRESSION des lignes cible absentes
      du resultat du builder (`WHEN NOT MATCHED BY SOURCE AND <predicat> THEN
      DELETE`, cf. `pipelines.common.writers.build_merge_sql`). `None` (defaut)
      = upsert pur, aucune ligne n'est jamais supprimee : une cle que le
      recalcul ne produit plus survit indefiniment. Ce champ ne porte QUE le
      garde-fou volumetrique (typiquement l'anciennete de `_generated_at`), pas
      le predicat complet : celui-ci s'obtient par
      `resolve_absent_row_delete_predicate`, seul point de passage vers le
      MERGE.
    """

    source_tables: tuple[str, ...]
    target_table: str
    merge_keys: tuple[str, ...]
    watermark_column: str | None = None
    initial_mode: str = "full"
    incremental_lookback_days: int | None = None
    column_comments: Mapping[str, str] = field(default_factory=dict)
    table_comment: str = ""
    absent_row_delete_guard: str | None = None

    def resolve_absent_row_delete_predicate(self, *, window_floor: date | None) -> str | None:
        """Predicat de suppression complet, BORNE a la fenetre recalculee.

        Seule facon d'obtenir un predicat de suppression : le garde-fou seul
        (`absent_row_delete_guard`) n'est jamais suffisant sur une table a
        watermark. `partition_predicate` n'etant pas transmis par la couche gold,
        la condition `ON` du MERGE ne prune rien : TOUTE ligne cible hors du lot
        frais est `NOT MATCHED BY SOURCE`, donc candidate au DELETE. Sur une
        table `*_daily` en incremental, le garde-fou seul supprimerait ainsi tout
        l'historique anterieur a la fenetre.

        D'ou les trois cas, dans cet ordre :

        - `watermark_column is None` (snapshot `*_rolling`/`governance`, reecrit
          en ENTIER a chaque run) : le garde-fou suffit, la source EST la
          reference complete ;
        - `watermark_column` + `window_floor` : le garde-fou est conjugue a
          `t.<watermark> >= DATE '<floor>'`. Une conjonction ne peut que
          RESTREINDRE la suppression, jamais l'elargir — la borne ne peut donc
          pas etre annulee par le contenu du garde-fou ;
        - `watermark_column` sans `window_floor` (fenetre inconnue : full
          refresh sur une source vide) : renvoie `None`. Pas de borne, pas de
          suppression — l'oubli de la borne devient impossible, il ne peut plus
          se traduire que par une suppression qui n'a pas lieu.
        """
        if self.absent_row_delete_guard is None:
            return None
        if self.watermark_column is None:
            return self.absent_row_delete_guard
        if window_floor is None:
            return None
        return (
            f"t.{self.watermark_column} >= DATE '{window_floor.isoformat()}' "
            f"AND ({self.absent_row_delete_guard})"
        )


# Fenetre incrementale des runs suivant le premier (cf. research.md R9) : ne
# recalcule/upsert que `period_start >= today - N jours`, sans re-scanner
# l'historique curated complet a chaque run.
#
# 10 et non 3 : le retard d'arrivee des sources curated a ete mesure en dev (aout
# 2026) par `datediff(to_date(collected_at), <jour>)` sur les trois sources des
# tables `*_daily` (`curated_dbx_billing_usage`, `curated_dbx_access_audit`,
# `curated_dbx_compute_node_timeline`) : 3 a 8 jours en regime etabli, mode 3-4.
# Une fenetre de 3 jours etait donc calee sur le MINIMUM observe — tout jour
# arrive plus tard etait agrege sous-compte puis jamais recalcule (2026-08-27 :
# 2 242 clusters ecrits en gold pour 9 123 presents en curated, 652 $ au lieu de
# ~3 800 $, et les fenetres glissantes 30/90 j sous-comptaient d'autant).
# 10 = retard maximum mesure + 2 jours de marge.
#
# NE PAS BAISSER cette valeur pour reduire le cout d'un run sans avoir remesure
# le retard de collecte : c'est un plancher de correction, pas un reglage de
# volumetrie. Partagee volontairement par les 7 specs `*_daily` : les trois
# sources mesurees passent par le meme collecteur et ont le meme profil de retard.
INCREMENTAL_LOOKBACK_DAYS = 10

# Nombre de jours gold recents consideres pour `governance.node_oversized`
# (dernier etat de `utilization_status` sur cette fenetre, cf. data-mapping §2.4).
GOVERNANCE_RECENT_DAYS = 3

# Orthographes acceptees des tags obligatoires, comparees en MINUSCULES (cf.
# `sql_helpers.tag_present_sql`) : sur un parc reel les cles sont saisies a la
# main (`Owner`, `OWNER`, `owner`), un acces exact `tags['owner']` ne reconnait
# donc qu'une variante et declare non conforme un cluster qui porte bien le tag.
# AJOUTER une orthographe ici (jamais en retirer) si la convention evolue. Les
# tags d'affectation du parc (`BU`, `Project`) valent centre de cout.
OWNER_TAG_KEYS = ("owner",)
COST_CENTER_TAG_KEYS = ("cost_center", "costcenter", "cost-center", "bu", "project")

# Delai de grace (jours) avant qu'une ligne absente du recalcul soit supprimee
# (cf. `GoldAggregationSpec.absent_row_delete_guard`). Garde-fou volumetrique :
# un run degrade (source curated vide/partielle) ne peut pas vider la table, les
# lignes rafraichies dans les derniers jours etant protegees.
#
# Contrepartie a connaitre AVANT de le monter : sur une table a watermark, une
# ligne n'est supprimable que si elle est A LA FOIS hors grace et DANS la fenetre
# recalculee. Ce delai doit donc rester INFERIEUR a `INCREMENTAL_LOOKBACK_DAYS`
# (7 < 10), sinon la fenetre a deja depasse la ligne quand la grace expire et
# l'orpheline devient immortelle en regime incremental.
SNAPSHOT_ABSENT_ROW_GRACE_DAYS = 7

# Garde-fou de suppression partage par les snapshots (`*_rolling`, `governance`)
# et par les tables `*_daily` qui activent la suppression : une ligne n'est
# supprimable que si son dernier rafraichissement date de plus de
# `SNAPSHOT_ABSENT_ROW_GRACE_DAYS`. Sur une table a watermark, la BORNE DE
# FENETRE lui est conjuguee par `resolve_absent_row_delete_predicate` — ne jamais
# passer cette chaine directement a `merge_into_table`.
SNAPSHOT_ABSENT_ROW_DELETE_GUARD = (
    f"t._generated_at < date_add(current_date(), -{SNAPSHOT_ABSENT_ROW_GRACE_DAYS})"
)

# Duree de conservation (jours apres `last_seen_date`) des recommandations qui ne
# sont plus produites par le rule engine — typiquement `RESOLVED` (l'anomalie ne
# se declenche plus) ou portant sur un objet disparu. Au-dela, la ligne est
# supprimee : sans cela `gold_dbx_compute_recommendations` conserve
# indefiniment l'historique de tous les clusters ephemeres jamais vus.
RECOMMENDATIONS_RESOLVED_RETENTION_DAYS = 90

# Seuil du classement `cost_rank` retenu comme "top cout" (`is_top_cost`).
TOP_COST_RANK_THRESHOLD = 10

# Fenetres glissantes (en jours) materialisees par les tables `*_rolling` : une
# ligne par objet ET par fenetre (colonne `window_days`), agregee "as of" le
# dernier jour disponible dans la table `*_daily` source. `1` = equivalent du
# grain quotidien courant (fenetre d'un seul jour), `7`/`30`/`90` = derniers
# 7/30/90 jours. AJOUTER une valeur (jamais en retirer) si un nouvel horizon est
# requis cote produit. Ordre croissant conserve pour la lisibilite.
ROLLING_WINDOWS = (1, 7, 30, 90)

# Fenetre d'activite (jours) delimitant le perimetre du snapshot
# `gold_dbx_compute_cluster_governance` : seuls les clusters vus actifs (ou
# modifies) sur cette fenetre sont evalues. Un snapshot d'etat courant SANS borne
# temporelle reevalue tout cluster jamais apparu en curated, dont les clusters
# JOB/PIPELINE ephemeres (une ligne par execution) : la table croit indefiniment
# et son contenu decrit surtout des objets qui n'existent plus. Alignee sur
# `max(ROLLING_WINDOWS)` : au-dela de la plus large fenetre d'analyse, un cluster
# inactif n'alimente plus aucun indicateur, donc plus aucune action.
GOVERNANCE_ACTIVITY_WINDOW_DAYS = max(ROLLING_WINDOWS)

# Date de disponibilite generale (GA) de chaque version Databricks Runtime LTS
# (pas de table de reference/API Databricks dediee, cf. sub-spec T002). Databricks
# garantit un support LTS de `DBR_LTS_SUPPORT_WINDOW_YEARS` ans a partir de la
# date GA (cf. "Databricks Runtime LTS version support schedule",
# docs.databricks.com/en/release-notes/runtime) : la fin de support se deduit
# donc de la date GA, pas besoin de retirer une entree quand le support se
# termine (cf. `cluster_governance.dbr_lts_versions_supported_as_of`). A COMPLETER
# (ajouter une ligne, jamais en retirer) a chaque nouvelle release LTS.
DBR_LTS_RELEASE_DATES: dict[str, date] = {
    "13.3.x-lts": date(2023, 8, 22),
    "14.3.x-lts": date(2024, 2, 1),
    "15.4.x-lts": date(2024, 8, 19),
    "16.4.x-lts": date(2025, 5, 9),
    "17.3.x-lts": date(2025, 10, 22),
    "18.x-lts": date(2026, 6, 10),
}

# Duree du support LTS Databricks (annees a partir de la date GA), cf. reference
# ci-dessus.
DBR_LTS_SUPPORT_WINDOW_YEARS = 3

# --- Tables gold clusters ---------------------------------------------------
GOLD_CLUSTER_COST_DAILY = "gold_dbx_compute_cluster_cost_daily"
GOLD_CLUSTER_COST_ROLLING = "gold_dbx_compute_cluster_cost_rolling"
GOLD_CLUSTER_EFFICIENCY_DAILY = "gold_dbx_compute_cluster_efficiency_daily"
GOLD_CLUSTER_EFFICIENCY_ROLLING = "gold_dbx_compute_cluster_efficiency_rolling"
GOLD_CLUSTER_RELIABILITY_DAILY = "gold_dbx_compute_cluster_reliability_daily"
GOLD_CLUSTER_RELIABILITY_ROLLING = "gold_dbx_compute_cluster_reliability_rolling"
GOLD_CLUSTER_GOVERNANCE = "gold_dbx_compute_cluster_governance"

# Grain commun des 3 tables `*_daily` (cf. data-model.md §"Couche GOLD — Clusters").
# Pas de `source_lz_id` : `account_id` (system.billing.usage/system.compute.clusters)
# est l'UUID du compte Databricks, pas l'identifiant cloud natif de
# `dim_landing_zone.subscription_or_account_id`. Un mapping `workspace_id ->
# lz_id` PARTIEL existe via `dim_reference_landing_zone_dbx_workspace` +
# `dim_landing_zone` (cf. `gold_dbx_compute.total_cost_daily`), mais n'est pas
# joint ici : `cost_rank`/`is_top_cost` restent calcules globalement par jour,
# pas par landing zone.
CLUSTER_DAILY_MERGE_KEYS = (
    "cloud_provider",
    "workspace_id",
    "cluster_id",
    "period_start",
)
# `governance` : snapshot du dernier etat connu, sans `period_start`.
CLUSTER_GOVERNANCE_MERGE_KEYS = (
    "cloud_provider",
    "workspace_id",
    "cluster_id",
)

# Grain des tables `*_rolling` : `period_start` (jour) est remplace par
# `window_days` (la fenetre glissante). Une table `*_rolling` est un snapshot
# "as of" le dernier jour disponible : chaque objet a une ligne par fenetre
# (1/7/30/90), reecrite a chaque run (pas d'accumulation dans le temps).
#
# CONSEQUENCE, et c'est pourquoi les 10 specs `*_rolling` portent toutes
# `absent_row_delete_guard` : `as_of_date` n'etant dans AUCUNE de ces cles, une
# ligne dont la cle n'est plus produite n'est pas remplacee — elle SURVIT sous
# son ancien `as_of_date` et devient indistinguable d'une ligne courante par la
# seule cle de merge. Mesure en dev le 2026-09-10 sur
# `warehouse_utilization_rolling` : 162 lignes figees sur 3 `as_of_date`
# anterieurs. Un upsert pur est donc faux ici, alors qu'il est correct sur une
# table `*_daily` (ou `period_start` fait partie de la cle : un jour ecrit reste
# vrai).
CLUSTER_COST_ROLLING_MERGE_KEYS = (
    "cloud_provider",
    "workspace_id",
    "cluster_id",
    "window_days",
)
# Meme grain `*_rolling` pour la fiabilite (cluster + window_days).
CLUSTER_RELIABILITY_ROLLING_MERGE_KEYS = CLUSTER_COST_ROLLING_MERGE_KEYS
# Meme grain `*_rolling` pour l'efficience (cluster + window_days).
CLUSTER_EFFICIENCY_ROLLING_MERGE_KEYS = CLUSTER_COST_ROLLING_MERGE_KEYS

# Commentaires communs aux 3 tables `*_daily` (grain quotidien). Fusionnes avec
# les commentaires specifiques a chaque table pour l'attachement Catalog
# Explorer (cf. `pipelines.common.writers.merge_into_table`) : chaque champ
# et sa formule de calcul restent documentes dans le docstring du builder
# correspondant (`pipelines.gold_dbx_compute.cluster_*`) — ce dictionnaire est
# la version courte, lisible depuis l'UI Databricks.
_CLUSTER_DAILY_COMMON_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": "Fournisseur cloud du workspace (azure ou aws).",
    "workspace_id": "Identifiant du workspace Databricks.",
    "cluster_id": "Identifiant du cluster de calcul.",
    "period_start": "Jour agrege (grain quotidien).",
    "cluster_type": (
        "Categorie du cluster, derivee de cluster_source (champ absent de "
        "system.compute.clusters) : ALL_PURPOSE (UI/API, persistant), JOB "
        "(job cluster, ephemere - recree a chaque execution) ou PIPELINE "
        "(PIPELINE/PIPELINE_MAINTENANCE, cluster DLT/Lakeflow). Permet de "
        "filtrer les clusters JOB avant toute analyse agregee (cf. "
        "gold_dbx_compute_job_cluster_cost_daily pour leur suivi par job)."
    ),
    "_generated_at": "Horodatage de generation de cette ligne.",
}

CLUSTER_COST_DAILY_TABLE_COMMENT = (
    "FinOps clusters : cout quotidien en dollars, DBU consommes, variation vs "
    "J-1 et classement par cout. Source : curated_dbx_billing_usage + "
    "curated_dbx_billing_list_prices + curated_dbx_compute_clusters. "
    "Population : uniquement le cout facture COMME du compute cluster (produits "
    "JOBS, ALL_PURPOSE, DLT). Le cout d'un service manage (inference, fonctions "
    "d'IA) que la facturation rattache au cluster appelant est exclu : c'est le "
    "cout du service, pas celui du cluster."
)
CLUSTER_COST_DAILY_COLUMN_COMMENTS: dict[str, str] = {
    **_CLUSTER_DAILY_COMMON_COLUMN_COMMENTS,
    "cluster_name": "Nom du cluster, au dernier etat connu ce jour-la.",
    "owner": (
        "Proprietaire du cluster. Formule : le tag 'owner' du cluster ; s'il "
        "n'est pas renseigne, le compte technique qui a cree le cluster."
    ),
    "cost_center": "Centre de cout (tag 'cost_center' du cluster, vide si non renseigne).",
    "sku_group": (
        "Categorie de facturation : classic ou photon. Formule : determinee a "
        "partir du type de service facture ce jour-la. La valeur serverless "
        "n'est plus produite -- un cluster est du compute provisionne, et les "
        "seules lignes serverless rattachees a un cluster etaient du cout de "
        "service manage, desormais exclu. Le cout du compute reellement "
        "serverless se lit dans gold_dbx_compute_job_cluster_cost_daily et "
        "gold_dbx_compute_pipeline_cost_daily (compute_kind = SERVERLESS)."
    ),
    "dbu_quantity": (
        "Volume de DBU (unite de facturation Databricks) consomme ce jour-la. "
        "Formule : somme des DBU factures sur la journee."
    ),
    "cost_usd": (
        "Cout total en dollars du cluster ce jour-la. Formule : quantite "
        "consommee (DBU) multipliee par le prix unitaire effectif, sommee sur "
        "la journee."
    ),
    "cost_usd_prev_day": (
        "Cout du jour calendaire precedent, pour comparaison. Formule : cout "
        "total (cost_usd) du meme cluster, calcule pour la veille."
    ),
    "cost_delta_pct": (
        "Variation du cout par rapport a la veille, en pourcentage. Formule : "
        "(cout du jour - cout de la veille) / cout de la veille x 100."
    ),
    "cost_rank": (
        "Classement du cluster par cout ce jour-la (1 = le plus cher), tous "
        "clusters confondus. Formule : position du cluster quand on trie tous "
        "les clusters du jour par cout decroissant."
    ),
    "is_top_cost": (
        "Vrai si le cluster fait partie des clusters les plus couteux ce "
        "jour-la. Formule : vrai si le classement (cost_rank) est parmi les "
        "10 premiers."
    ),
}

CLUSTER_COST_ROLLING_TABLE_COMMENT = (
    "FinOps clusters, fenetres glissantes : cout et DBU cumules sur les "
    "derniers 1/7/30/90 jours (colonne window_days) 'as of' le dernier jour "
    "disponible, avec variation vs la fenetre precedente de meme longueur et "
    "classement par cout. Rollup de gold_dbx_compute_cluster_cost_daily "
    "(aucune relecture curated)."
)
CLUSTER_COST_ROLLING_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": "Fournisseur cloud du workspace (azure ou aws).",
    "workspace_id": "Identifiant du workspace Databricks.",
    "cluster_id": "Identifiant du cluster de calcul.",
    "window_days": (
        "Longueur de la fenetre glissante en jours (1, 7, 30 ou 90). 1 = "
        "equivalent du grain quotidien (un seul jour), 7/30/90 = derniers "
        "7/30/90 jours."
    ),
    "as_of_date": (
        "Dernier jour disponible dans la table quotidienne source, borne haute "
        "(incluse) de toutes les fenetres. Formule : MAX(period_start)."
    ),
    "window_start": (
        "Premier jour (inclus) de la fenetre. Formule : as_of_date - "
        "(window_days - 1)."
    ),
    "cluster_type": (
        "Categorie du cluster (ALL_PURPOSE/JOB/PIPELINE), au dernier etat "
        "connu dans la fenetre."
    ),
    "cluster_name": "Nom du cluster, au dernier etat connu dans la fenetre.",
    "owner": "Proprietaire du cluster, au dernier etat connu dans la fenetre.",
    "cost_center": "Centre de cout du cluster, au dernier etat connu dans la fenetre.",
    "sku_group": (
        "Categorie de facturation (classic ou photon), au dernier jour. La "
        "valeur serverless n'est plus produite, cf. "
        "gold_dbx_compute_cluster_cost_daily."
    ),
    "dbu_quantity": (
        "Volume de DBU consommes sur la fenetre. Formule : somme des DBU "
        "quotidiens sur les window_days jours."
    ),
    "cost_usd": (
        "Cout total en dollars sur la fenetre. Formule : somme des couts "
        "quotidiens sur les window_days jours."
    ),
    "cost_usd_prev_window": (
        "Cout total sur la fenetre precedente de meme longueur, pour "
        "comparaison. Formule : somme des couts quotidiens sur les window_days "
        "jours qui precedent immediatement la fenetre courante."
    ),
    "cost_delta_pct": (
        "Variation du cout vs la fenetre precedente, en pourcentage. Formule : "
        "(cout fenetre - cout fenetre precedente) / cout fenetre precedente x 100."
    ),
    "cost_rank": (
        "Classement du cluster par cout sur la fenetre (1 = le plus cher), "
        "tous clusters confondus, au sein de la meme window_days. Formule : "
        "position quand on trie les clusters de la fenetre par cout decroissant."
    ),
    "is_top_cost": (
        "Vrai si le cluster fait partie des clusters les plus couteux de la "
        "fenetre. Formule : vrai si cost_rank est parmi les 10 premiers."
    ),
    "_generated_at": "Horodatage de generation de cette ligne.",
}

CLUSTER_EFFICIENCY_DAILY_TABLE_COMMENT = (
    "Utilisation CPU/memoire et recommandations de redimensionnement "
    "(rightsizing) par cluster et par jour. Source : "
    "curated_dbx_compute_node_timeline + curated_dbx_lakeflow_job_task_run_timeline + "
    "curated_dbx_compute_node_types + gold_dbx_compute_cluster_cost_daily."
)
CLUSTER_EFFICIENCY_DAILY_COLUMN_COMMENTS: dict[str, str] = {
    **_CLUSTER_DAILY_COMMON_COLUMN_COMMENTS,
    "cluster_name": "Nom du cluster, au dernier etat connu ce jour-la.",
    "cpu_util_avg_pct": (
        "Utilisation CPU moyenne sur la journee (%). Formule : moyenne du "
        "pourcentage de CPU utilise (calcul + systeme), sur toutes les minutes "
        "de la journee."
    ),
    "cpu_util_p95_pct": (
        "Utilisation CPU au 95e percentile sur la journee (%), base du "
        "rightsizing. Formule : valeur en dessous de laquelle se trouvent 95% "
        "des mesures minute par minute (pic soutenu, en ignorant les rares "
        "pointes extremes)."
    ),
    "mem_util_avg_pct": (
        "Utilisation memoire moyenne sur la journee (%). Formule : moyenne du "
        "pourcentage de memoire utilisee sur toutes les minutes de la journee."
    ),
    "mem_util_p95_pct": (
        "Utilisation memoire au 95e percentile sur la journee (%). Formule : "
        "valeur en dessous de laquelle se trouvent 95% des mesures minute par "
        "minute."
    ),
    "cpu_wait_avg_pct": (
        "Temps CPU passe en attente I/O, moyenne journaliere (%). Formule : "
        "moyenne du pourcentage de temps CPU en attente de disque/reseau sur "
        "la journee."
    ),
    "cpu_util_hist": (
        "Histogramme de l'utilisation CPU minute par minute (%), 21 buckets a "
        "bornes tous les 5% de 0 a 100 plus overflow >100. Distribution "
        "sommable permettant de recalculer les percentiles CPU sur des "
        "fenetres glissantes (cf. table _rolling)."
    ),
    "mem_util_hist": (
        "Histogramme de l'utilisation memoire minute par minute (%), memes "
        "buckets que cpu_util_hist (21 tranches de 5%). Distribution sommable "
        "pour le recalcul des percentiles memoire sur fenetres glissantes."
    ),
    "idle_pct": (
        "Part du temps allume sans tache active (%). Formule : minutes sans "
        "aucune tache en cours divisees par le nombre total de minutes "
        "allume, x 100."
    ),
    "uptime_hours": (
        "Nombre d'heures ou le cluster etait allume ce jour-la. Formule : "
        "nombre de minutes ou le cluster etait actif, divise par 60."
    ),
    "active_hours": (
        "Nombre d'heures avec au moins une tache active. Formule : minutes "
        "allume comportant au moins une tache en cours, divisees par 60 (soit "
        "uptime_hours moins la part idle) : toujours inferieur ou egal a "
        "uptime_hours."
    ),
    "worker_count_avg": (
        "Nombre moyen de workers sur la journee. Formule : moyenne du nombre "
        "de workers observes minute par minute."
    ),
    "worker_count_max": (
        "Nombre maximum de workers observe sur la journee. Formule : le plus "
        "grand nombre de workers observe sur une minute donnee."
    ),
    "autoscale_oscillation": (
        "Nombre de changements de taille du cluster (instabilite de "
        "l'autoscaling). Formule : nombre de fois ou le nombre de workers a "
        "change d'une minute a l'autre."
    ),
    "driver_node_type": "Type d'instance du noeud driver, au dernier etat connu.",
    "worker_node_type": "Type d'instance des noeuds worker, au dernier etat connu.",
    "autoscale_enabled": (
        "Vrai si l'autoscaling est active sur le cluster, au dernier etat connu. "
        "Formule : vrai si les deux bornes d'autoscaling (min et max workers) "
        "sont renseignees."
    ),
    "autoscale_min_workers": (
        "Nombre minimum de workers autorise par l'autoscaling (valeur de "
        "configuration, au dernier etat connu). Vide si l'autoscaling est "
        "desactive."
    ),
    "autoscale_max_workers": (
        "Nombre maximum de workers autorise par l'autoscaling (valeur de "
        "configuration, au dernier etat connu). Vide si l'autoscaling est "
        "desactive."
    ),
    "configured_worker_count": (
        "Nombre de workers configure en taille fixe (au dernier etat connu), 0 "
        "pour un cluster single-node. Vide si l'autoscaling est active : les "
        "deux modes sont exclusifs, la taille voulue se lit alors dans les "
        "bornes d'autoscaling. A ne pas confondre avec worker_count_avg/"
        "worker_count_max, qui sont les tailles OBSERVEES sur la journee."
    ),
    "is_zombie": (
        "Vrai si le cluster est allume longtemps avec une charge quasi nulle et "
        "aucune tache active. Formule : allume plus de 8h, CPU sous 15% au pic "
        "soutenu, et moins d'1h d'activite detectee dans la journee."
    ),
    "utilization_status": (
        "Diagnostic de dimensionnement : OVER (surdimensionne), UNDER "
        "(sous-dimensionne) ou OPTIMAL. Formule : OVER si CPU et memoire "
        "restent bas (CPU < 40%, memoire < 50%) ; UNDER si l'un des deux est "
        "proche de la saturation (> 85%) ; sinon OPTIMAL."
    ),
    "recommended_node_type": (
        "Type d'instance plus petit propose si le cluster est surdimensionne. "
        "Formule : le type d'instance immediatement plus petit (en nombre de "
        "coeurs) que celui utilise actuellement."
    ),
    "rightsizing_reco": (
        "Recommandation lisible d'ajustement de la taille du cluster. "
        "Formule : texte genere a partir du diagnostic de dimensionnement "
        "(utilization_status) et du type d'instance recommande."
    ),
    "estimated_savings_usd": (
        "Economie estimee en dollars si la recommandation de redimensionnement "
        "est appliquee. Formule : cout du jour (cost_usd) multiplie par la "
        "part de coeurs economises en passant au type d'instance recommande."
    ),
}

CLUSTER_RELIABILITY_DAILY_TABLE_COMMENT = (
    "Fiabilite des clusters : demarrages, latence de demarrage, terminaisons "
    "anormales et configuration d'auto-arret. Source : curated_dbx_access_audit "
    "+ curated_dbx_compute_clusters."
)
CLUSTER_RELIABILITY_DAILY_COLUMN_COMMENTS: dict[str, str] = {
    **_CLUSTER_DAILY_COMMON_COLUMN_COMMENTS,
    "cluster_name": "Nom du cluster, au dernier etat connu ce jour-la.",
    "start_count": (
        "Nombre de demarrages du cluster ce jour-la. Formule : nombre "
        "d'evenements de demarrage enregistres dans la journee."
    ),
    "avg_startup_seconds": (
        "Temps moyen de demarrage du cluster, en secondes. Formule : moyenne "
        "du temps ecoule entre chaque demande de demarrage et sa completion "
        "effective."
    ),
    "unexpected_termination_count": (
        "Nombre de terminaisons pour une raison anormale (hors arret "
        "utilisateur, inactivite ou fin de job). Formule : nombre d'arrets du "
        "cluster dont la raison n'est ni une demande utilisateur, ni "
        "l'inactivite, ni la fin normale d'un job."
    ),
    "top_termination_reason": (
        "Raison de terminaison la plus frequente ce jour-la. Formule : raison "
        "d'arret la plus souvent observee parmi tous les arrets du jour."
    ),
    "auto_termination_minutes": (
        "Delai d'auto-arret configure sur le cluster, en minutes (valeur de "
        "configuration du cluster)."
    ),
    "has_auto_termination": (
        "Vrai si l'auto-arret est active sur le cluster. Formule : vrai si le "
        "delai d'auto-arret configure est superieur a 0."
    ),
}

CLUSTER_GOVERNANCE_TABLE_COMMENT = (
    "Snapshot de conformite des clusters (dernier etat connu) : tags "
    "obligatoires, version DBR, surdimensionnement et action recommandee. "
    f"Limite aux clusters actifs ou modifies sur les {GOVERNANCE_ACTIVITY_WINDOW_DAYS} "
    "derniers jours ; les lignes sorties de cette fenetre sont supprimees au run "
    "suivant. Source : curated_dbx_compute_clusters + "
    "gold_dbx_compute_cluster_efficiency_daily."
)
CLUSTER_GOVERNANCE_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": "Fournisseur cloud du workspace (azure ou aws).",
    "workspace_id": "Identifiant du workspace Databricks.",
    "cluster_id": "Identifiant du cluster de calcul.",
    "cluster_name": "Nom du cluster, au dernier etat connu.",
    "cluster_type": (
        "Categorie du cluster, derivee de cluster_source (champ absent de "
        "system.compute.clusters) : ALL_PURPOSE (UI/API, persistant), JOB "
        "(job cluster, ephemere - recree a chaque execution) ou PIPELINE "
        "(PIPELINE/PIPELINE_MAINTENANCE, cluster DLT/Lakeflow). Permet de "
        "filtrer les clusters JOB avant toute analyse agregee (cf. "
        "gold_dbx_compute_job_cluster_cost_daily pour leur suivi par job)."
    ),
    "governance_applies": (
        "Vrai si les regles de gouvernance (tags obligatoires, version DBR) "
        "s'appliquent a ce cluster. Formule : vrai pour les clusters "
        "ALL_PURPOSE uniquement. Les tags et le runtime d'un cluster JOB ou "
        "PIPELINE sont imposes par la definition du job/pipeline, pas par le "
        "cluster : la conformite se corrige la-bas, une action par execution "
        "ephemere n'aurait aucun destinataire."
    ),
    "has_owner_tag": (
        "Vrai si le cluster porte un tag 'owner'. Formule : vrai si une cle de "
        "tag vaut 'owner' (casse ignoree) avec une valeur non vide."
    ),
    "has_cost_center_tag": (
        "Vrai si le cluster porte un tag de centre de cout. Formule : vrai si "
        "une cle de tag vaut 'cost_center', 'costcenter', 'cost-center', 'bu' "
        "ou 'project' (casse ignoree) avec une valeur non vide."
    ),
    "dbr_version": "Version du runtime Databricks (DBR) du cluster.",
    "dbr_is_lts_current": (
        "Vrai si la version DBR est une LTS encore supportee par Databricks. "
        "Formule : vrai si la version du runtime correspond a une LTS dont la "
        "periode de support (3 ans apres sa sortie) n'est pas terminee."
    ),
    "node_oversized": (
        "Vrai si le cluster a ete detecte surdimensionne au cours des "
        "derniers jours. Formule : vrai si le diagnostic de dimensionnement a "
        "indique 'surdimensionne' au moins une fois durant les 3 derniers "
        "jours."
    ),
    "is_single_node": (
        "Vrai si le cluster est configure en single-node (0 worker). Formule "
        ": vrai si le nombre de workers configures est egal a 0."
    ),
    "recommended_action": (
        "Action de gouvernance recommandee. Formule : tag manquant en "
        "priorite ; sinon version DBR obsolete ; sinon cluster surdimensionne "
        "— la premiere condition remplie determine l'action affichee. Les deux "
        "premieres regles ne sont evaluees que si governance_applies est vrai ; "
        "le surdimensionnement, lui, est une propriete du cluster lui-meme et "
        "reste evalue pour tous."
    ),
    "severity": (
        "Niveau de priorite de l'action recommandee : LOW, MEDIUM ou HIGH. "
        "Formule : meme ordre de priorite que recommended_action (tag "
        "manquant = LOW, DBR obsolete = HIGH, surdimensionne = MEDIUM)."
    ),
    "_generated_at": "Horodatage de generation de cette ligne.",
}


CLUSTER_COST_DAILY_SPEC = GoldAggregationSpec(
    source_tables=(
        CURATED_BILLING_USAGE,
        CURATED_BILLING_LIST_PRICES,
        CURATED_COMPUTE_CLUSTERS,
    ),
    target_table=GOLD_CLUSTER_COST_DAILY,
    merge_keys=CLUSTER_DAILY_MERGE_KEYS,
    watermark_column="period_start",
    initial_mode="full",
    incremental_lookback_days=INCREMENTAL_LOOKBACK_DAYS,
    column_comments=CLUSTER_COST_DAILY_COLUMN_COMMENTS,
    table_comment=CLUSTER_COST_DAILY_TABLE_COMMENT,
)

# Rollup 1/7/30/90 jours de la table quotidienne cout : source unique
# `GOLD_CLUSTER_COST_DAILY` (aucune relecture curated). `watermark_column=None`
# + `incremental_lookback_days=None` : snapshot recalcule integralement a chaque
# run (comme `governance`) — la fenetre 90 jours impose de toute facon de lire
# tout l'historique quotidien, et le MERGE sur (objet, window_days) reecrit
# l'unique snapshot courant.
CLUSTER_COST_ROLLING_SPEC = GoldAggregationSpec(
    source_tables=(GOLD_CLUSTER_COST_DAILY,),
    target_table=GOLD_CLUSTER_COST_ROLLING,
    merge_keys=CLUSTER_COST_ROLLING_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=CLUSTER_COST_ROLLING_COLUMN_COMMENTS,
    table_comment=CLUSTER_COST_ROLLING_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)

CLUSTER_EFFICIENCY_DAILY_SPEC = GoldAggregationSpec(
    source_tables=(
        CURATED_COMPUTE_NODE_TIMELINE,
        CURATED_COMPUTE_CLUSTERS,
        CURATED_COMPUTE_NODE_TYPES,
        CURATED_LAKEFLOW_JOB_TASK_RUN_TIMELINE,  # signal d'activite (idle_pct/active_hours)
        GOLD_CLUSTER_COST_DAILY,  # pour `estimated_savings_usd` (cout du jour)
    ),
    target_table=GOLD_CLUSTER_EFFICIENCY_DAILY,
    merge_keys=CLUSTER_DAILY_MERGE_KEYS,
    watermark_column="period_start",
    initial_mode="full",
    incremental_lookback_days=INCREMENTAL_LOOKBACK_DAYS,
    column_comments=CLUSTER_EFFICIENCY_DAILY_COLUMN_COMMENTS,
    table_comment=CLUSTER_EFFICIENCY_DAILY_TABLE_COMMENT,
)

CLUSTER_EFFICIENCY_ROLLING_TABLE_COMMENT = (
    "Utilisation des clusters Databricks, fenetres glissantes : CPU/memoire "
    "et diagnostic de dimensionnement recalcules sur les derniers 1/7/30/90 "
    "jours (colonne window_days) 'as of' le dernier jour disponible. Rollup de "
    "gold_dbx_compute_cluster_efficiency_daily (aucune relecture curated). Les "
    "percentiles (cpu/mem p95) sont recalcules a partir des histogrammes "
    "quotidiens sommes sur la fenetre, les percentiles quotidiens n'etant pas "
    "moyennables ; les moyennes sont ponderees par le temps allume."
)
CLUSTER_EFFICIENCY_ROLLING_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": "Fournisseur cloud du workspace (azure ou aws).",
    "workspace_id": "Identifiant du workspace Databricks.",
    "cluster_id": "Identifiant du cluster de calcul.",
    "window_days": (
        "Longueur de la fenetre glissante en jours (1, 7, 30 ou 90). 1 = "
        "equivalent du grain quotidien, 7/30/90 = derniers 7/30/90 jours."
    ),
    "as_of_date": (
        "Dernier jour disponible dans la table quotidienne source, borne haute "
        "(incluse) de toutes les fenetres. Formule : MAX(period_start)."
    ),
    "window_start": (
        "Premier jour (inclus) de la fenetre. Formule : as_of_date - "
        "(window_days - 1)."
    ),
    "cluster_name": "Nom du cluster, au dernier jour connu.",
    "cluster_type": (
        "Categorie du cluster (ALL_PURPOSE, JOB, PIPELINE), au dernier jour "
        "connu."
    ),
    "cpu_util_avg_pct": (
        "Utilisation CPU moyenne sur la fenetre (%). Formule : moyenne des "
        "moyennes quotidiennes ponderee par le temps allume de chaque jour."
    ),
    "cpu_util_p95_pct": (
        "Utilisation CPU au 95e percentile sur la fenetre (%). Formule : "
        "percentile recalcule a partir de l'histogramme CPU somme sur la "
        "fenetre (resolution bornee par la largeur des buckets, 5%)."
    ),
    "mem_util_avg_pct": (
        "Utilisation memoire moyenne sur la fenetre (%). Formule : moyenne des "
        "moyennes quotidiennes ponderee par le temps allume."
    ),
    "mem_util_p95_pct": (
        "Utilisation memoire au 95e percentile sur la fenetre (%). Formule : "
        "percentile recalcule a partir de l'histogramme memoire somme sur la "
        "fenetre."
    ),
    "cpu_wait_avg_pct": (
        "Temps CPU en attente I/O moyen sur la fenetre (%). Formule : moyenne "
        "des moyennes quotidiennes ponderee par le temps allume."
    ),
    "idle_pct": (
        "Part du temps allume sans tache active sur la fenetre (%). Formule : "
        "moyenne des idle_pct quotidiens ponderee par le temps allume."
    ),
    "uptime_hours": (
        "Nombre total d'heures ou le cluster etait allume sur la fenetre. "
        "Formule : somme des heures allume quotidiennes."
    ),
    "active_hours": (
        "Nombre total d'heures ou au moins une tache a tourne sur la fenetre. "
        "Formule : somme des heures actives quotidiennes."
    ),
    "uptime_hours_prev_window": (
        "Nombre total d'heures allume sur la fenetre precedente de meme "
        "longueur, pour comparaison. Formule : somme des heures allume "
        "quotidiennes sur les window_days jours qui precedent immediatement la "
        "fenetre courante. Vide (jamais 0) si aucun jour n'est disponible sur "
        "cette periode : l'absence de comparaison n'est pas une baisse de 100 %."
    ),
    "idle_pct_prev_window": (
        "Part du temps allume sans tache active sur la fenetre precedente de "
        "meme longueur (%). Formule : moyenne des idle_pct quotidiens ponderee "
        "par le temps allume, identique a celle d'idle_pct, appliquee aux "
        "window_days jours qui precedent la fenetre courante. Vide (jamais 0) "
        "si aucun jour n'est disponible sur cette periode. La variation "
        "s'exprime en POINTS de pourcentage (idle_pct - idle_pct_prev_window), "
        "pas en pourcentage."
    ),
    "worker_count_avg": (
        "Nombre moyen de workers sur la fenetre. Formule : moyenne des "
        "moyennes quotidiennes ponderee par le temps allume."
    ),
    "worker_count_max": (
        "Nombre maximum de workers observe sur la fenetre. Formule : maximum "
        "des maxima quotidiens."
    ),
    "autoscale_oscillation": (
        "Nombre total de changements de taille du cluster sur la fenetre. "
        "Formule : somme des oscillations quotidiennes."
    ),
    "driver_node_type": "Type d'instance du driver, au dernier jour connu.",
    "worker_node_type": "Type d'instance des workers, au dernier jour connu.",
    "autoscale_enabled": (
        "Vrai si l'autoscaling est active sur le cluster, au dernier jour connu. "
        "Formule : vrai si les deux bornes d'autoscaling (min et max workers) "
        "sont renseignees."
    ),
    "autoscale_min_workers": (
        "Nombre minimum de workers autorise par l'autoscaling (configuration, au "
        "dernier jour connu). Vide si l'autoscaling est desactive."
    ),
    "autoscale_max_workers": (
        "Nombre maximum de workers autorise par l'autoscaling (configuration, au "
        "dernier jour connu). Vide si l'autoscaling est desactive."
    ),
    "configured_worker_count": (
        "Nombre de workers configure en taille fixe (au dernier jour connu), 0 "
        "pour un cluster single-node. Vide si l'autoscaling est active : les deux "
        "modes sont exclusifs, la taille voulue se lit alors dans les bornes "
        "d'autoscaling. A ne pas confondre avec worker_count_avg/worker_count_max, "
        "qui sont les tailles OBSERVEES sur la fenetre."
    ),
    "is_zombie": (
        "Cluster allume longtemps avec charge quasi nulle et aucune activite "
        "sur la fenetre. Formule : uptime_hours > 8 ET cpu_util_p95_pct < 15 "
        "ET active_hours < 1 (memes seuils que la table quotidienne, appliques "
        "aux totaux de la fenetre)."
    ),
    "utilization_status": (
        "Diagnostic de dimensionnement sur la fenetre : OVER, UNDER ou "
        "OPTIMAL. Formule : OVER si cpu_p95 < 40 ET mem_p95 < 50 ; UNDER si "
        "cpu_p95 > 85 OU mem_p95 > 85 ; sinon OPTIMAL (percentiles de la "
        "fenetre)."
    ),
    "recommended_node_type": (
        "Type d'instance plus petit propose en remplacement, au dernier jour "
        "connu."
    ),
    "rightsizing_reco": (
        "Recommandation lisible d'ajustement, derivee du diagnostic de la "
        "fenetre."
    ),
    "estimated_savings_usd": (
        "Economie estimee en dollars sur la fenetre. Formule : somme des "
        "economies estimees quotidiennes."
    ),
    "_generated_at": "Horodatage de generation de cette ligne.",
}

CLUSTER_EFFICIENCY_ROLLING_SPEC = GoldAggregationSpec(
    source_tables=(GOLD_CLUSTER_EFFICIENCY_DAILY,),
    target_table=GOLD_CLUSTER_EFFICIENCY_ROLLING,
    merge_keys=CLUSTER_EFFICIENCY_ROLLING_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=CLUSTER_EFFICIENCY_ROLLING_COLUMN_COMMENTS,
    table_comment=CLUSTER_EFFICIENCY_ROLLING_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)

CLUSTER_RELIABILITY_DAILY_SPEC = GoldAggregationSpec(
    source_tables=(
        CURATED_COMPUTE_CLUSTERS,
        CURATED_ACCESS_AUDIT,
    ),
    target_table=GOLD_CLUSTER_RELIABILITY_DAILY,
    merge_keys=CLUSTER_DAILY_MERGE_KEYS,
    watermark_column="period_start",
    initial_mode="full",
    incremental_lookback_days=INCREMENTAL_LOOKBACK_DAYS,
    column_comments=CLUSTER_RELIABILITY_DAILY_COLUMN_COMMENTS,
    table_comment=CLUSTER_RELIABILITY_DAILY_TABLE_COMMENT,
)

CLUSTER_RELIABILITY_ROLLING_TABLE_COMMENT = (
    "Fiabilite des clusters, fenetres glissantes : demarrages et terminaisons "
    "anormales cumules sur les derniers 1/7/30/90 jours (colonne window_days) "
    "'as of' le dernier jour disponible, temps de demarrage moyen pondere sur "
    "la fenetre et configuration/raison de terminaison au dernier etat connu. "
    "Rollup de gold_dbx_compute_cluster_reliability_daily (aucune relecture "
    "curated)."
)
CLUSTER_RELIABILITY_ROLLING_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": "Fournisseur cloud du workspace (azure ou aws).",
    "workspace_id": "Identifiant du workspace Databricks.",
    "cluster_id": "Identifiant du cluster de calcul.",
    "window_days": (
        "Longueur de la fenetre glissante en jours (1, 7, 30 ou 90). 1 = "
        "equivalent du grain quotidien (un seul jour), 7/30/90 = derniers "
        "7/30/90 jours."
    ),
    "as_of_date": (
        "Dernier jour disponible dans la table quotidienne source, borne haute "
        "(incluse) de toutes les fenetres. Formule : MAX(period_start)."
    ),
    "window_start": (
        "Premier jour (inclus) de la fenetre. Formule : as_of_date - "
        "(window_days - 1)."
    ),
    "cluster_type": (
        "Categorie du cluster (ALL_PURPOSE/JOB/PIPELINE), au dernier etat "
        "connu dans la fenetre."
    ),
    "cluster_name": "Nom du cluster, au dernier etat connu dans la fenetre.",
    "start_count": (
        "Nombre total de demarrages du cluster sur la fenetre. Formule : somme "
        "des demarrages quotidiens sur les window_days jours."
    ),
    "avg_startup_seconds": (
        "Temps moyen de demarrage du cluster sur la fenetre, en secondes. "
        "Formule : moyenne des temps de demarrage quotidiens ponderee par le "
        "nombre de demarrages de chaque jour (seuls les jours avec une latence "
        "mesuree entrent dans la ponderation)."
    ),
    "unexpected_termination_count": (
        "Nombre total de terminaisons anormales sur la fenetre. Formule : "
        "somme des terminaisons anormales quotidiennes sur les window_days "
        "jours."
    ),
    "top_termination_reason": (
        "Raison de terminaison la plus frequente, au dernier jour connu "
        "(reflete le dernier jour de la fenetre, pas l'ensemble de la fenetre)."
    ),
    "auto_termination_minutes": (
        "Delai d'auto-arret configure sur le cluster, en minutes, au dernier "
        "etat connu."
    ),
    "has_auto_termination": (
        "Vrai si l'auto-arret est active sur le cluster, au dernier etat "
        "connu."
    ),
    "_generated_at": "Horodatage de generation de cette ligne.",
}

CLUSTER_RELIABILITY_ROLLING_SPEC = GoldAggregationSpec(
    source_tables=(GOLD_CLUSTER_RELIABILITY_DAILY,),
    target_table=GOLD_CLUSTER_RELIABILITY_ROLLING,
    merge_keys=CLUSTER_RELIABILITY_ROLLING_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=CLUSTER_RELIABILITY_ROLLING_COLUMN_COMMENTS,
    table_comment=CLUSTER_RELIABILITY_ROLLING_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)

# `governance` : snapshot du dernier etat connu, sans `period_start` -> pas de
# watermark ni de fenetre incrementale, toujours recalcule en entier (cf. R9/R8).
# Le perimetre recalcule etant borne a `GOVERNANCE_ACTIVITY_WINDOW_DAYS`, un
# upsert pur laisserait indefiniment en place les clusters sortis de la fenetre :
# les lignes absentes du recalcul sont donc supprimees, apres le delai de grace
# `SNAPSHOT_ABSENT_ROW_GRACE_DAYS` qui protege la table d'un run degrade.
CLUSTER_GOVERNANCE_SPEC = GoldAggregationSpec(
    source_tables=(
        CURATED_COMPUTE_CLUSTERS,
        GOLD_CLUSTER_EFFICIENCY_DAILY,
    ),
    target_table=GOLD_CLUSTER_GOVERNANCE,
    merge_keys=CLUSTER_GOVERNANCE_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=CLUSTER_GOVERNANCE_COLUMN_COMMENTS,
    table_comment=CLUSTER_GOVERNANCE_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)


# --- Table gold job clusters (rollup billing-direct par job_id) -------------
# Les clusters `cluster_type = 'JOB'` (derive de `cluster_source`, cf.
# `sql_helpers.cluster_type_case_expr`) sont ephemeres : Databricks recree un
# `cluster_id` (et un nom) a chaque execution, ce qui rend ces 2 identifiants
# inutilisables pour suivre un job dans le temps. `job_id` (stable) est la cle
# de regroupement retenue -- portee DIRECTEMENT par la facturation
# (`usage_metadata.job_id`), plus resolue via
# `curated_dbx_lakeflow_job_task_run_timeline`.
#
# Rollup BILLING-DIRECT depuis T001b, comme `pipeline_cost_daily` ci-dessous.
# La version precedente agregeait `gold_dbx_compute_cluster_cost_daily`
# (`cluster_type = 'JOB'`) et heritait de son filtre `usage_metadata.cluster_id
# IS NOT NULL` : un job SERVERLESS n'ayant jamais de `cluster_id`, 56 841 $ AWS
# + 28 812 $ Azure sur 30 jours etaient exclus silencieusement (mesure en dev le
# 2026-09-10). D'ou aussi `compute_kind` dans le GRAIN et pas en attribut : 926
# jours-job sur 70 980 facturent les DEUX formes le meme jour.
#
# NE PAS sommer cette table avec `cluster_cost_daily` ni
# `pipeline_cost_daily` : sous-ensembles disjoints des memes lignes de
# facturation, le meme $ compterait deux fois. Sommer les deux `compute_kind`
# DE CETTE table est en revanche legitime. Scope volontairement limite au
# cout/DBU (additif, sans ambiguite) : les metriques d'efficiency/reliability/
# governance par job ne sont pas additives de la meme facon (percentile,
# moyenne ponderee, seuils penses pour un cluster persistant) et restent une
# decision separee, non couverte ici.
GOLD_JOB_CLUSTER_COST_DAILY = "gold_dbx_compute_job_cluster_cost_daily"

# MIGRATION REQUISE AVANT LE PREMIER RUN DE CE CHANGEMENT DE GRAIN (T001b).
# `compute_kind` est une cle de merge NOUVELLE sur une table DEJA EN
# PRODUCTION : le MERGE echoue a l'analyse tant que la colonne n'existe pas
# cote cible (`DELTA_MERGE_UNRESOLVED_EXPRESSION: Cannot resolve
# t.compute_kind in search condition`), et aucun `full_refresh` n'y change
# rien -- le MERGE ne demarre pas. Les deux procedures possibles sont
# documentees dans `pipelines/common/writers.py` (docstring de
# `merge_into_table`).
# RECOMMANDATION : `DROP TABLE` des deux tables (`..._job_cluster_cost_daily`
# puis `..._job_cluster_cost_rolling`) suivi d'un run complet, PAS l'`ALTER
# TABLE ADD COLUMN` + backfill a 'CLASSIC'. Trois raisons mesurees en dev le
# 2026-09-10 :
#   1. rien a preserver : l'historique gold va du 2026-07-07 au 2026-09-09
#      (76 192 lignes) alors que `curated_dbx_billing_usage` remonte au
#      2023-08-26. La table est integralement recalculable, et le recalcul
#      ETEND l'historique au lieu de le perdre.
#   2. l'`ALTER` + backfill laisserait une table a COUVERTURE MIXTE : les
#      lignes 'CLASSIC' anciennes seraient conservees, mais leurs lignes
#      'SERVERLESS' du meme jour n'apparaitraient qu'a partir de la fenetre
#      incrementale (`INCREMENTAL_LOOKBACK_DAYS`). L'invariant "somme des
#      `compute_kind` = cout job total de la facturation" serait donc FAUX sur
#      tous les jours anterieurs, sans qu'aucune colonne ne le signale.
#   3. le backfill est une ecriture DML de migration a ecrire, relire et
#      autoriser, pour un resultat strictement inferieur au recalcul.
# Aucun parametre de run a passer apres le DROP : `_resolve_lower_bound`
# (`entrypoint.py`) rend `None` des que la table cible n'existe pas, donc le
# run nominal suivant recalcule DEJA l'historique complet. `full_refresh=true`
# serait redondant.
# `UNDROP TABLE` reste disponible 7 jours (tables UC MANAGED) si le run de
# reconstruction echoue. Ordonner le DROP du daily AVANT le rolling : le
# rolling ne lit que le daily, l'inverse laisserait un rolling au grain
# ancien pointant sur un daily au grain neuf.

JOB_CLUSTER_COST_DAILY_MERGE_KEYS = (
    "cloud_provider",
    "workspace_id",
    "job_id",
    "compute_kind",
    "period_start",
)

JOB_CLUSTER_COST_DAILY_TABLE_COMMENT = (
    "FinOps jobs : cout quotidien par job Databricks (job_id, stable) plutot "
    "que par cluster JOB ephemere. Rollup BILLING-DIRECT : agrege "
    "curated_dbx_billing_usage filtre sur usage_metadata.job_id, price par "
    "curated_dbx_billing_list_prices, nom resolu depuis "
    "curated_dbx_lakeflow_jobs + curated_dbx_lakeflow_job_run_timeline (nom "
    "des runs soumis). Couvre le compute CLASSIC ET SERVERLESS : un job "
    "serverless n'a pas de cluster_id, il etait exclu de cette table avant "
    "T001b. Ne PAS sommer avec gold_dbx_compute_cluster_cost_daily "
    "(ALL_PURPOSE) ni gold_dbx_compute_pipeline_cost_daily : sous-ensembles "
    "disjoints des memes lignes de facturation (double comptage). Sommer les "
    "deux compute_kind DE CETTE table est en revanche legitime : les deux "
    "formes partitionnent les memes lignes et leur somme redonne le cout job "
    "total."
)
JOB_CLUSTER_COST_DAILY_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": "Fournisseur cloud du workspace (azure ou aws).",
    "workspace_id": "Identifiant du workspace Databricks.",
    "job_id": (
        "Identifiant du job Databricks. Stable dans le temps (assigne une "
        "seule fois a la creation du job), contrairement au cluster_id "
        "ephemere qui change a chaque execution. Porte directement par la "
        "facturation (usage_metadata.job_id)."
    ),
    "compute_kind": (
        "Forme de compute derriere le cout : CLASSIC (le job a tourne sur des "
        "clusters, usage_metadata.cluster_id renseigne) ou SERVERLESS (aucun "
        "cluster derriere la ligne facturee). Jamais NULL. Fait partie du "
        "grain : un job qui a migre, ou qui alterne, a une ligne par forme et "
        "par jour (926 jours-job mesures en dev sur 30 jours). Proxy exact et "
        "non heuristique -- sur le produit JOBS il coincide sans exception avec "
        "product_features.is_serverless (mesure dev 2026-09-10)."
    ),
    "job_name": (
        "Nom du job, au dernier etat connu. Pour un run SOUMIS par API "
        "(jobs/runs/submit), qui n'a pas de definition de job persistee : le "
        "nom du RUN (run_name), a defaut de nom de job. Reste vide pour un run "
        "lance depuis un notebook, qui n'a de nom dans aucune source."
    ),
    "period_start": "Jour agrege (grain quotidien).",
    "cluster_count": (
        "Nombre de clusters JOB ephemeres distincts ayant execute ce job ce "
        "jour-la. Formule : COUNT(DISTINCT usage_metadata.cluster_id). Vaut 0 "
        "(et non NULL) sur une ligne compute_kind = 'SERVERLESS' : aucun "
        "cluster n'y est provisionne, c'est un ensemble vide mesure, pas une "
        "valeur manquante."
    ),
    "dbu_quantity": (
        "Volume total de DBU consomme par ce job ce jour-la, dans cette forme "
        "de compute. Formule : SUM(usage_quantity) restreint aux lignes "
        "usage_unit = 'DBU'."
    ),
    "cost_usd": (
        "Cout total en dollars de ce job ce jour-la, dans cette forme de "
        "compute. Formule : SUM(usage_quantity x effective_price)."
    ),
    "cost_usd_prev_day": (
        "Cout du jour calendaire precedent, pour comparaison. Formule : cout "
        "total (cost_usd) du meme job, calcule pour la veille."
    ),
    "cost_delta_pct": (
        "Variation du cout par rapport a la veille, en pourcentage. Formule : "
        "(cout du jour - cout de la veille) / cout de la veille x 100."
    ),
    "cost_rank": (
        "Classement du job par cout ce jour-la (1 = le plus cher), AU SEIN de "
        "son compute_kind et non toutes formes confondues : une page filtree "
        "sur une forme de compute doit y lire un rang qui commence a 1. Deux "
        "lignes du meme jour peuvent donc porter cost_rank = 1, une par forme, "
        "et un classement toutes formes confondues demande d'agreger sur "
        "compute_kind avant de reclasser. Formule : position du job quand on "
        "trie les jobs du jour de ce compute_kind par cout decroissant."
    ),
    "is_top_cost": (
        "Vrai si le job fait partie des jobs les plus couteux ce jour-la dans "
        "son compute_kind. Formule : vrai si le classement (cost_rank) est "
        "parmi les 10 premiers. cost_rank utilise RANK() : en cas d'ex-aequo "
        "de cout a la frontiere du seuil, plus de 10 jobs peuvent etre marques "
        "is_top_cost=true le meme jour (comportement voulu, pas un bug)."
    ),
    "_generated_at": "Horodatage de generation de cette ligne.",
}

JOB_CLUSTER_COST_DAILY_SPEC = GoldAggregationSpec(
    source_tables=(
        CURATED_BILLING_USAGE,
        CURATED_BILLING_LIST_PRICES,
        # Porte `run_name` : seul nom d'un run soumis par API, absent de `jobs`.
        CURATED_LAKEFLOW_JOB_RUN_TIMELINE,
        CURATED_LAKEFLOW_JOBS,
    ),
    target_table=GOLD_JOB_CLUSTER_COST_DAILY,
    merge_keys=JOB_CLUSTER_COST_DAILY_MERGE_KEYS,
    watermark_column="period_start",
    initial_mode="full",
    incremental_lookback_days=INCREMENTAL_LOOKBACK_DAYS,
    column_comments=JOB_CLUSTER_COST_DAILY_COLUMN_COMMENTS,
    table_comment=JOB_CLUSTER_COST_DAILY_TABLE_COMMENT,
)

GOLD_JOB_CLUSTER_COST_ROLLING = "gold_dbx_compute_job_cluster_cost_rolling"

# Grain `*_rolling` : `period_start` remplace par `window_days` (cf.
# CLUSTER_COST_ROLLING_MERGE_KEYS). `compute_kind` est repris de la table
# quotidienne (T001b) : sans lui, la fenetre re-melangerait ce que le grain
# quotidien vient de separer. Meme migration requise que pour le daily (cf. le
# bloc MIGRATION ci-dessus) : cette table est aussi deja en production.
JOB_CLUSTER_COST_ROLLING_MERGE_KEYS = (
    "cloud_provider",
    "workspace_id",
    "job_id",
    "compute_kind",
    "window_days",
)

JOB_CLUSTER_COST_ROLLING_TABLE_COMMENT = (
    "FinOps jobs, fenetres glissantes : cout, DBU et nombre de clusters JOB "
    "cumules sur les derniers 1/7/30/90 jours (colonne window_days) 'as of' le "
    "dernier jour disponible, avec variation vs la fenetre precedente de meme "
    "longueur et classement par cout. Rollup de "
    "gold_dbx_compute_job_cluster_cost_daily (aucune relecture curated). Ne "
    "PAS sommer avec gold_dbx_compute_cluster_cost_rolling ni "
    "gold_dbx_compute_pipeline_cost_rolling (double comptage). Ni sommer "
    "plusieurs window_days entre elles (fenetres emboitees). Sommer les deux "
    "compute_kind d'une meme window_days est en revanche legitime et redonne le "
    "cout job total de la fenetre."
)
JOB_CLUSTER_COST_ROLLING_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": "Fournisseur cloud du workspace (azure ou aws).",
    "workspace_id": "Identifiant du workspace Databricks.",
    "job_id": (
        "Identifiant du job Databricks, stable dans le temps (cf. table "
        "quotidienne source)."
    ),
    "compute_kind": (
        "Forme de compute derriere le cout : CLASSIC (clusters JOB) ou "
        "SERVERLESS (aucun cluster). Jamais NULL, repris de la table "
        "quotidienne source. Fait partie du grain : un job mixte a une ligne "
        "par forme et par fenetre."
    ),
    "window_days": (
        "Longueur de la fenetre glissante en jours (1, 7, 30 ou 90). 1 = "
        "equivalent du grain quotidien (un seul jour), 7/30/90 = derniers "
        "7/30/90 jours."
    ),
    "as_of_date": (
        "Dernier jour disponible dans la table quotidienne source, borne haute "
        "(incluse) de toutes les fenetres. Formule : MAX(period_start)."
    ),
    "window_start": (
        "Premier jour (inclus) de la fenetre. Formule : as_of_date - "
        "(window_days - 1)."
    ),
    "job_name": (
        "Nom du job, au dernier etat connu dans la fenetre. Pour un run SOUMIS "
        "par API (jobs/runs/submit), qui n'a pas de definition de job "
        "persistee : le nom du RUN (run_name), a defaut de nom de job. Reste "
        "vide pour un run lance depuis un notebook, qui n'a de nom dans aucune "
        "source."
    ),
    "cluster_count": (
        "Nombre de clusters JOB ephemeres distincts ayant execute ce job sur "
        "la fenetre. Formule : somme des comptes distincts quotidiens -- exacte "
        "car les clusters JOB sont ephemeres (un cluster_id distinct par "
        "execution, jamais reutilise d'un jour a l'autre). Vaut 0 sur une ligne "
        "compute_kind = 'SERVERLESS' (aucun cluster provisionne)."
    ),
    "dbu_quantity": (
        "Volume de DBU consommes sur la fenetre. Formule : somme des DBU "
        "quotidiens sur les window_days jours."
    ),
    "cost_usd": (
        "Cout total en dollars sur la fenetre. Formule : somme des couts "
        "quotidiens sur les window_days jours."
    ),
    "cost_usd_prev_window": (
        "Cout total sur la fenetre precedente de meme longueur, pour "
        "comparaison. Formule : somme des couts quotidiens sur les window_days "
        "jours qui precedent immediatement la fenetre courante."
    ),
    "cost_delta_pct": (
        "Variation du cout vs la fenetre precedente, en pourcentage. Formule : "
        "(cout fenetre - cout fenetre precedente) / cout fenetre precedente x 100."
    ),
    "cost_rank": (
        "Classement du job par cout sur la fenetre (1 = le plus cher), au sein "
        "du meme couple (window_days, compute_kind) : une page filtree sur une "
        "forme de compute doit y lire un rang qui commence a 1. Deux lignes "
        "d'une meme fenetre peuvent donc porter cost_rank = 1, une par forme. "
        "Formule : position quand on trie les jobs de la fenetre et de ce "
        "compute_kind par cout decroissant."
    ),
    "is_top_cost": (
        "Vrai si le job fait partie des jobs les plus couteux de la fenetre "
        "dans son compute_kind. Formule : vrai si cost_rank est parmi les 10 "
        "premiers."
    ),
    "_generated_at": "Horodatage de generation de cette ligne.",
}

JOB_CLUSTER_COST_ROLLING_SPEC = GoldAggregationSpec(
    source_tables=(GOLD_JOB_CLUSTER_COST_DAILY,),
    target_table=GOLD_JOB_CLUSTER_COST_ROLLING,
    merge_keys=JOB_CLUSTER_COST_ROLLING_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=JOB_CLUSTER_COST_ROLLING_COLUMN_COMMENTS,
    table_comment=JOB_CLUSTER_COST_ROLLING_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)


# --- Tables gold pipelines DLT (rollup billing-direct par dlt_pipeline_id) ---
# Symetrique du rollup job (ci-dessus), BILLING-DIRECT comme lui depuis T001b :
# ce rollup lit directement
# curated_dbx_billing_usage filtre sur usage_metadata.dlt_pipeline_id (porte par
# chaque ligne de facturation d'un pipeline, y compris ses lignes de
# maintenance PIPELINE_MAINTENANCE - mesure en dev). Aucune resolution
# cluster_id -> dlt_pipeline_id : le cout de maintenance est capture nativement,
# rattache au pipeline parent. Cle de merge dlt_pipeline_id JAMAIS NULL (filtre
# IS NOT NULL cote builder).
# Ce filtre IS NOT NULL ne suffit PAS a delimiter la population : d'autres
# produits factures portent un dlt_pipeline_id (10 972 ids non-DLT, 37 100,58 $
# sur l'historique complet, dont 10 499 requetes SQL - mesure dev 2026-09-10).
# D'ou le second predicat billing_origin_product IN ('DLT') depuis T001c (cf.
# sql_helpers.BILLING_PRODUCTS_DLT_PIPELINE, qui porte la justification liste
# blanche / liste noire et l'arbitrage LAKEFLOW_CONNECT).
# Etant billing-direct, ce rollup ne porte aucun cluster_type : compute_kind
# (T008) est le seul discriminant DLT classique / DLT serverless, et il est dans
# le GRAIN -- les pipelines qui facturent les deux formes (2 sur 2 972 en dev,
# fenetre 30 j) garderaient sinon un cout melange. Valeurs CLASSIC / SERVERLESS,
# jamais NULL (CASE binaire cote builder).
GOLD_PIPELINE_COST_DAILY = "gold_dbx_compute_pipeline_cost_daily"

PIPELINE_COST_DAILY_MERGE_KEYS = (
    "cloud_provider",
    "workspace_id",
    "dlt_pipeline_id",
    "compute_kind",
    "period_start",
)

PIPELINE_COST_DAILY_TABLE_COMMENT = (
    "FinOps pipelines DLT : cout quotidien par pipeline Lakeflow/DLT "
    "(dlt_pipeline_id, stable) plutot que par cluster PIPELINE ephemere. "
    "Rollup BILLING-DIRECT : agrege curated_dbx_billing_usage filtre sur "
    "usage_metadata.dlt_pipeline_id (lignes d'execution ET de maintenance du "
    "pipeline) ET sur billing_origin_product = 'DLT', price par "
    "curated_dbx_billing_list_prices, nom resolu depuis "
    "curated_dbx_lakeflow_pipelines. Le filtre produit est necessaire : "
    "d'autres produits factures (requetes SQL, ingestion Lakeflow Connect, "
    "bases managees, recherche vectorielle) portent aussi un dlt_pipeline_id "
    "et ne sont pas des pipelines DLT. Cette table ne couvre donc pas tout ce "
    "qui porte un dlt_pipeline_id. Ne PAS sommer avec "
    "gold_dbx_compute_cluster_cost_daily (ALL_PURPOSE) ni "
    "gold_dbx_compute_job_cluster_cost_daily : sous-ensembles disjoints des "
    "memes lignes de facturation (double comptage). Sommer les deux "
    "compute_kind DE CETTE table est en revanche legitime : les deux formes "
    "partitionnent les memes lignes et leur somme redonne le cout DLT total."
)
PIPELINE_COST_DAILY_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": "Fournisseur cloud du workspace (azure ou aws).",
    "workspace_id": "Identifiant du workspace Databricks.",
    "dlt_pipeline_id": (
        "Identifiant du pipeline Lakeflow/DLT. Stable dans le temps "
        "(assigne une seule fois a la creation du pipeline), contrairement au "
        "cluster PIPELINE ephemere recree a chaque execution. Porte "
        "directement par la facturation (usage_metadata.dlt_pipeline_id), y "
        "compris pour les lignes de maintenance. Ce champ de facturation n'est "
        "pas reserve aux pipelines DLT (des requetes SQL, entre autres, le "
        "portent aussi) : seules les lignes du produit DLT sont retenues ici."
    ),
    "compute_kind": (
        "Forme de compute derriere le cout : CLASSIC (le pipeline a tourne sur "
        "des clusters DLT, usage_metadata.cluster_id renseigne) ou SERVERLESS "
        "(aucun cluster derriere la ligne facturee). Jamais NULL. Fait partie "
        "du grain : un pipeline qui a migre, ou qui alterne, a une ligne par "
        "forme et par jour. Proxy exact et non heuristique -- les 6 375 "
        "clusters ephemeres portes par les lignes DLT facturees ont tous "
        "cluster_source = 'PIPELINE' (mesure dev 2026-09-09), donc une ligne "
        "sans cluster_id n'a pas de cluster du tout."
    ),
    "pipeline_name": (
        "Nom du pipeline, au dernier etat connu dans "
        "curated_dbx_lakeflow_pipelines. A defaut (aucune definition encore "
        "ingeree), le dlt_pipeline_id lui-meme."
    ),
    "period_start": "Jour agrege (grain quotidien).",
    "dbu_quantity": (
        "Volume total de DBU consomme par ce pipeline ce jour-la (execution + "
        "maintenance). Formule : SUM(usage_quantity) restreint aux lignes "
        "usage_unit = 'DBU'."
    ),
    "cost_usd": (
        "Cout total en dollars de ce pipeline ce jour-la (execution + "
        "maintenance). Formule : SUM(usage_quantity x effective_price)."
    ),
    "cost_usd_prev_day": (
        "Cout du jour calendaire precedent, pour comparaison. Formule : cout "
        "total (cost_usd) du meme pipeline, calcule pour la veille."
    ),
    "cost_delta_pct": (
        "Variation du cout par rapport a la veille, en pourcentage. Formule : "
        "(cout du jour - cout de la veille) / cout de la veille x 100."
    ),
    "cost_rank": (
        "Classement du pipeline par cout ce jour-la (1 = le plus cher), AU SEIN "
        "de son compute_kind et non toutes formes confondues : l'IHM affiche ce "
        "rang sur une liste filtree CLASSIC. Deux lignes du meme jour peuvent "
        "donc porter cost_rank = 1, une par forme. Formule : position du "
        "pipeline quand on trie les pipelines du jour de ce compute_kind par "
        "cout decroissant."
    ),
    "is_top_cost": (
        "Vrai si le pipeline fait partie des plus couteux ce jour-la dans son "
        "compute_kind. Formule : vrai si le classement (cost_rank) est parmi "
        "les 10 premiers. cost_rank utilise RANK() : en cas d'ex-aequo de cout "
        "a la frontiere du seuil, plus de 10 pipelines peuvent etre marques "
        "is_top_cost=true le meme jour (comportement voulu, pas un bug)."
    ),
    "_generated_at": "Horodatage de generation de cette ligne.",
}

PIPELINE_COST_DAILY_SPEC = GoldAggregationSpec(
    source_tables=(
        CURATED_BILLING_USAGE,
        CURATED_BILLING_LIST_PRICES,
        # Referentiel de NOM : dernier etat connu du pipeline (pipeline_name).
        CURATED_LAKEFLOW_PIPELINES,
    ),
    target_table=GOLD_PIPELINE_COST_DAILY,
    merge_keys=PIPELINE_COST_DAILY_MERGE_KEYS,
    watermark_column="period_start",
    initial_mode="full",
    incremental_lookback_days=INCREMENTAL_LOOKBACK_DAYS,
    column_comments=PIPELINE_COST_DAILY_COLUMN_COMMENTS,
    table_comment=PIPELINE_COST_DAILY_TABLE_COMMENT,
)

GOLD_PIPELINE_COST_ROLLING = "gold_dbx_compute_pipeline_cost_rolling"

# Grain `*_rolling` : `period_start` remplace par `window_days`. `compute_kind`
# est repris de la table quotidienne (T008) : sans lui, la fenetre re-melangerait
# ce que le grain quotidien vient de separer.
PIPELINE_COST_ROLLING_MERGE_KEYS = (
    "cloud_provider",
    "workspace_id",
    "dlt_pipeline_id",
    "compute_kind",
    "window_days",
)

PIPELINE_COST_ROLLING_TABLE_COMMENT = (
    "FinOps pipelines DLT, fenetres glissantes : cout et DBU cumules sur les "
    "derniers 1/7/30/90 jours (colonne window_days) 'as of' le dernier jour "
    "disponible, avec variation vs la fenetre precedente de meme longueur et "
    "classement par cout. Rollup de gold_dbx_compute_pipeline_cost_daily "
    "(aucune relecture curated). Ne PAS sommer avec "
    "gold_dbx_compute_cluster_cost_rolling ni "
    "gold_dbx_compute_job_cluster_cost_rolling (double comptage). Ni sommer "
    "plusieurs window_days entre elles (fenetres emboitees). Sommer les deux "
    "compute_kind d'une meme window_days est en revanche legitime et redonne le "
    "cout DLT total de la fenetre."
)
PIPELINE_COST_ROLLING_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": "Fournisseur cloud du workspace (azure ou aws).",
    "workspace_id": "Identifiant du workspace Databricks.",
    "dlt_pipeline_id": (
        "Identifiant du pipeline Lakeflow/DLT, stable dans le temps (cf. table "
        "quotidienne source)."
    ),
    "compute_kind": (
        "Forme de compute derriere le cout : CLASSIC (clusters DLT) ou "
        "SERVERLESS (aucun cluster). Jamais NULL, repris de la table "
        "quotidienne source. Fait partie du grain : un pipeline mixte a une "
        "ligne par forme et par fenetre."
    ),
    "window_days": (
        "Longueur de la fenetre glissante en jours (1, 7, 30 ou 90). 1 = "
        "equivalent du grain quotidien (un seul jour), 7/30/90 = derniers "
        "7/30/90 jours."
    ),
    "as_of_date": (
        "Dernier jour disponible dans la table quotidienne source, borne haute "
        "(incluse) de toutes les fenetres. Formule : MAX(period_start)."
    ),
    "window_start": (
        "Premier jour (inclus) de la fenetre. Formule : as_of_date - "
        "(window_days - 1)."
    ),
    "pipeline_name": (
        "Nom du pipeline, au dernier etat connu dans la fenetre. A defaut, le "
        "dlt_pipeline_id lui-meme."
    ),
    "dbu_quantity": (
        "Volume de DBU consommes sur la fenetre. Formule : somme des DBU "
        "quotidiens sur les window_days jours."
    ),
    "cost_usd": (
        "Cout total en dollars sur la fenetre. Formule : somme des couts "
        "quotidiens sur les window_days jours."
    ),
    "cost_usd_prev_window": (
        "Cout total sur la fenetre precedente de meme longueur, pour "
        "comparaison. Formule : somme des couts quotidiens sur les window_days "
        "jours qui precedent immediatement la fenetre courante."
    ),
    "cost_delta_pct": (
        "Variation du cout vs la fenetre precedente, en pourcentage. Formule : "
        "(cout fenetre - cout fenetre precedente) / cout fenetre precedente x 100."
    ),
    "cost_rank": (
        "Classement du pipeline par cout sur la fenetre (1 = le plus cher), au "
        "sein du meme couple (window_days, compute_kind) : l'IHM affiche ce "
        "rang sur une liste filtree CLASSIC, un rang toutes formes confondues y "
        "commencerait a 40. Deux lignes d'une meme fenetre peuvent donc porter "
        "cost_rank = 1, une par forme. Formule : position quand on trie les "
        "pipelines de la fenetre et de ce compute_kind par cout decroissant."
    ),
    "is_top_cost": (
        "Vrai si le pipeline fait partie des plus couteux de la fenetre dans "
        "son compute_kind. Formule : vrai si cost_rank est parmi les 10 "
        "premiers."
    ),
    "_generated_at": "Horodatage de generation de cette ligne.",
}

PIPELINE_COST_ROLLING_SPEC = GoldAggregationSpec(
    source_tables=(GOLD_PIPELINE_COST_DAILY,),
    target_table=GOLD_PIPELINE_COST_ROLLING,
    merge_keys=PIPELINE_COST_ROLLING_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=PIPELINE_COST_ROLLING_COLUMN_COMMENTS,
    table_comment=PIPELINE_COST_ROLLING_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)


# --- Tables gold efficacite par job / pipeline (T004) -----------------------
# Pendant EFFICACITE des rollups de cout ci-dessus : les tables de cout
# repondent "combien coute ce job/pipeline", celles-ci "sa taille est-elle la
# bonne". Meme cle stable (`job_id` / `dlt_pipeline_id`), meme grain quotidien +
# fenetres glissantes, mais source differente : `node_timeline` (via
# `gold_dbx_compute_cluster_efficiency_daily`) et non la facturation.
#
# Consequence a NE PAS chercher a corriger : la population de ces tables est
# plus petite que celle des tables de cout. Un job ou un pipeline SERVERLESS n'a
# aucun cluster, donc aucune ligne `node_timeline`, donc aucune ligne ici -- il
# garde en revanche sa ligne de cout. L'ecart se mesure et se documente, il ne se
# comble pas par une valeur par defaut.
#
# `gold_dbx_compute_cluster_efficiency_daily` est la source des deux familles :
# elle NE DOIT PAS etre filtree sur `cluster_type = 'ALL_PURPOSE'` (seule sa
# variante `_rolling` porte ce filtre, cf. SC-001), sinon ces quatre tables se
# vident silencieusement.
#
# NE PAS sommer les heures de ces tables entre elles ni avec
# `gold_dbx_compute_cluster_efficiency_daily` : les trois agregent des
# sous-ensembles DISJOINTS (par `cluster_type`) des memes lignes `node_timeline`.

# Colonnes de metriques communes aux deux tables `*_efficiency_daily` : seules
# les colonnes de grain (`job_id`/`job_name` vs
# `dlt_pipeline_id`/`pipeline_name`) et `cluster_count` differe. Factorisees
# pour que les deux tables ne puissent pas documenter differemment un calcul
# identique.
_STABLE_GRAIN_EFFICIENCY_DAILY_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": "Fournisseur cloud du workspace (azure ou aws).",
    "workspace_id": "Identifiant du workspace Databricks.",
    "period_start": "Jour agrege (grain quotidien).",
    "cpu_util_avg_pct": (
        "Utilisation CPU moyenne sur la journee (%), tous clusters ephemeres "
        "confondus. Formule : moyenne des moyennes de chaque cluster, ponderee "
        "par son temps allume -- un cluster allume 5 minutes ne pese pas autant "
        "qu'un cluster allume 5 heures."
    ),
    "cpu_util_p95_pct": (
        "Utilisation CPU au 95e percentile sur la journee (%), base du "
        "rightsizing. Formule : percentile RECALCULE a partir des histogrammes "
        "CPU minute par minute des clusters du jour, sommes bucket par bucket "
        "(un percentile ne se moyenne pas). Resolution bornee par la largeur des "
        "buckets, 5%."
    ),
    "mem_util_avg_pct": (
        "Utilisation memoire moyenne sur la journee (%), tous clusters ephemeres "
        "confondus. Formule : moyenne des moyennes de chaque cluster, ponderee "
        "par son temps allume."
    ),
    "mem_util_p95_pct": (
        "Utilisation memoire au 95e percentile sur la journee (%). Formule : "
        "percentile recalcule a partir des histogrammes memoire sommes sur les "
        "clusters du jour."
    ),
    "cpu_wait_avg_pct": (
        "Temps CPU passe en attente I/O sur la journee (%). Formule : moyenne "
        "des moyennes de chaque cluster, ponderee par son temps allume."
    ),
    "cpu_util_hist": (
        "Histogramme de l'utilisation CPU minute par minute (%), 21 buckets a "
        "bornes tous les 5% de 0 a 100 plus overflow >100, somme sur les "
        "clusters du jour. Distribution sommable permettant de recalculer les "
        "percentiles CPU sur des fenetres glissantes (cf. table _rolling)."
    ),
    "mem_util_hist": (
        "Histogramme de l'utilisation memoire minute par minute (%), memes "
        "buckets que cpu_util_hist (21 tranches de 5%), somme sur les clusters "
        "du jour. Distribution sommable pour le recalcul des percentiles "
        "memoire sur fenetres glissantes."
    ),
    "idle_pct": (
        "Part du temps allume sans tache active (%). Formule : moyenne des "
        "idle_pct de chaque cluster, ponderee par son temps allume."
    ),
    "uptime_hours": (
        "Nombre d'heures ou les clusters etaient allumes ce jour-la. Formule : "
        "somme des heures allume de tous les clusters du jour -- plusieurs "
        "clusters ephemeres pouvant tourner en parallele, cette somme peut "
        "depasser 24 h pour une seule journee."
    ),
    "active_hours": (
        "Nombre d'heures avec au moins une tache active, tous clusters "
        "confondus. Formule : somme des heures actives de chaque cluster "
        "(toujours inferieur ou egal a uptime_hours)."
    ),
    "worker_count_avg": (
        "Nombre moyen de workers par cluster sur la journee. Formule : moyenne "
        "des moyennes de chaque cluster, ponderee par son temps allume. Ce "
        "n'est PAS le nombre total de workers simultanes du job/pipeline."
    ),
    "worker_count_max": (
        "Nombre maximum de workers observe sur un cluster ce jour-la. Formule : "
        "maximum des maxima de chaque cluster."
    ),
    "autoscale_oscillation": (
        "Nombre total de changements de taille observes ce jour-la "
        "(instabilite de l'autoscaling). Formule : somme des oscillations de "
        "chaque cluster du jour."
    ),
    "driver_node_type": (
        "Type d'instance du noeud driver, lu sur le cluster le plus "
        "representatif du jour (celui reste allume le plus longtemps)."
    ),
    "worker_node_type": (
        "Type d'instance des noeuds worker, lu sur le cluster le plus "
        "representatif du jour (celui reste allume le plus longtemps)."
    ),
    "autoscale_enabled": (
        "Vrai si l'autoscaling est active sur le cluster le plus representatif "
        "du jour. Formule : vrai si les deux bornes d'autoscaling (min et max "
        "workers) sont renseignees."
    ),
    "autoscale_min_workers": (
        "Nombre minimum de workers autorise par l'autoscaling (valeur de "
        "configuration du cluster le plus representatif du jour). Vide si "
        "l'autoscaling est desactive."
    ),
    "autoscale_max_workers": (
        "Nombre maximum de workers autorise par l'autoscaling (valeur de "
        "configuration du cluster le plus representatif du jour). Vide si "
        "l'autoscaling est desactive."
    ),
    "configured_worker_count": (
        "Nombre de workers configure en taille fixe sur le cluster le plus "
        "representatif du jour, 0 pour un cluster single-node. Vide si "
        "l'autoscaling est active : les deux modes sont exclusifs, la taille "
        "voulue se lit alors dans les bornes d'autoscaling. A ne pas confondre "
        "avec worker_count_avg/worker_count_max, qui sont les tailles OBSERVEES."
    ),
    "utilization_status": (
        "Diagnostic de dimensionnement : OVER (surdimensionne), UNDER "
        "(sous-dimensionne) ou OPTIMAL. Formule : OVER si CPU et memoire "
        "restent bas (cpu_p95 < 40%, mem_p95 < 50%) ; UNDER si l'un des deux "
        "est proche de la saturation (> 85%) ; sinon OPTIMAL. Memes seuils que "
        "le grain cluster."
    ),
    "recommended_node_type": (
        "Type d'instance plus petit propose si le calcul est surdimensionne, lu "
        "sur le cluster le plus representatif du jour."
    ),
    "rightsizing_reco": (
        "Recommandation lisible d'ajustement de la taille du calcul. Formule : "
        "texte genere a partir du diagnostic (utilization_status) et du type "
        "d'instance recommande."
    ),
    "estimated_savings_usd": (
        "Economie estimee en dollars si la recommandation est appliquee sur "
        "l'ensemble des clusters du jour. Formule : somme des economies "
        "estimees de chaque cluster."
    ),
    "_generated_at": "Horodatage de generation de cette ligne.",
}

# Idem pour les deux tables `*_efficiency_rolling`. Les histogrammes ne sont PAS
# exposes ici : ils ne servent qu'a recalculer les percentiles de la fenetre.
_STABLE_GRAIN_EFFICIENCY_ROLLING_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": "Fournisseur cloud du workspace (azure ou aws).",
    "workspace_id": "Identifiant du workspace Databricks.",
    "window_days": (
        "Longueur de la fenetre glissante en jours (1, 7, 30 ou 90). 1 = "
        "equivalent du grain quotidien (un seul jour), 7/30/90 = derniers "
        "7/30/90 jours."
    ),
    "as_of_date": (
        "Dernier jour disponible dans la table quotidienne source, borne haute "
        "(incluse) de toutes les fenetres. Formule : MAX(period_start)."
    ),
    "window_start": (
        "Premier jour (inclus) de la fenetre. Formule : as_of_date - "
        "(window_days - 1)."
    ),
    "cpu_util_avg_pct": (
        "Utilisation CPU moyenne sur la fenetre (%). Formule : moyenne des "
        "moyennes quotidiennes ponderee par le temps allume de chaque jour."
    ),
    "cpu_util_p95_pct": (
        "Utilisation CPU au 95e percentile sur la fenetre (%). Formule : "
        "percentile recalcule a partir des histogrammes CPU quotidiens sommes "
        "sur la fenetre (resolution bornee par la largeur des buckets, 5%)."
    ),
    "mem_util_avg_pct": (
        "Utilisation memoire moyenne sur la fenetre (%). Formule : moyenne des "
        "moyennes quotidiennes ponderee par le temps allume."
    ),
    "mem_util_p95_pct": (
        "Utilisation memoire au 95e percentile sur la fenetre (%). Formule : "
        "percentile recalcule a partir des histogrammes memoire quotidiens "
        "sommes sur la fenetre."
    ),
    "cpu_wait_avg_pct": (
        "Temps CPU en attente I/O moyen sur la fenetre (%). Formule : moyenne "
        "des moyennes quotidiennes ponderee par le temps allume."
    ),
    "idle_pct": (
        "Part du temps allume sans tache active sur la fenetre (%). Formule : "
        "moyenne des idle_pct quotidiens ponderee par le temps allume."
    ),
    "uptime_hours": (
        "Nombre total d'heures allume sur la fenetre, tous clusters ephemeres "
        "confondus. Formule : somme des heures allume quotidiennes (peut "
        "depasser 24 h par jour, plusieurs clusters pouvant tourner en "
        "parallele)."
    ),
    "active_hours": (
        "Nombre total d'heures ou au moins une tache a tourne sur la fenetre. "
        "Formule : somme des heures actives quotidiennes."
    ),
    "uptime_hours_prev_window": (
        "Nombre total d'heures allume sur la fenetre precedente de meme "
        "longueur, pour comparaison. Formule : somme des heures allume "
        "quotidiennes sur les window_days jours qui precedent immediatement la "
        "fenetre courante. Vide (jamais 0) si aucun jour n'est disponible sur "
        "cette periode : l'absence de comparaison n'est pas une baisse de 100 %."
    ),
    "idle_pct_prev_window": (
        "Part du temps allume sans tache active sur la fenetre precedente de "
        "meme longueur (%). Formule : moyenne des idle_pct quotidiens ponderee "
        "par le temps allume, identique a celle d'idle_pct, appliquee aux "
        "window_days jours qui precedent la fenetre courante. Vide (jamais 0) "
        "si aucun jour n'est disponible sur cette periode. La variation "
        "s'exprime en POINTS de pourcentage (idle_pct - idle_pct_prev_window), "
        "pas en pourcentage."
    ),
    "worker_count_avg": (
        "Nombre moyen de workers par cluster sur la fenetre. Formule : moyenne "
        "des moyennes quotidiennes ponderee par le temps allume."
    ),
    "worker_count_max": (
        "Nombre maximum de workers observe sur un cluster de la fenetre. "
        "Formule : maximum des maxima quotidiens."
    ),
    "autoscale_oscillation": (
        "Nombre total de changements de taille sur la fenetre. Formule : somme "
        "des oscillations quotidiennes."
    ),
    "driver_node_type": "Type d'instance du driver, au dernier jour connu.",
    "worker_node_type": "Type d'instance des workers, au dernier jour connu.",
    "autoscale_enabled": (
        "Vrai si l'autoscaling etait active au dernier jour connu. Formule : "
        "vrai si les deux bornes d'autoscaling (min et max workers) sont "
        "renseignees."
    ),
    "autoscale_min_workers": (
        "Nombre minimum de workers autorise par l'autoscaling (configuration, "
        "au dernier jour connu). Vide si l'autoscaling est desactive."
    ),
    "autoscale_max_workers": (
        "Nombre maximum de workers autorise par l'autoscaling (configuration, "
        "au dernier jour connu). Vide si l'autoscaling est desactive."
    ),
    "configured_worker_count": (
        "Nombre de workers configure en taille fixe (au dernier jour connu), 0 "
        "pour un cluster single-node. Vide si l'autoscaling est active : les "
        "deux modes sont exclusifs, la taille voulue se lit alors dans les "
        "bornes d'autoscaling. A ne pas confondre avec worker_count_avg/"
        "worker_count_max, qui sont les tailles OBSERVEES sur la fenetre."
    ),
    "utilization_status": (
        "Diagnostic de dimensionnement sur la fenetre : OVER, UNDER ou "
        "OPTIMAL. Formule : OVER si cpu_p95 < 40 ET mem_p95 < 50 ; UNDER si "
        "cpu_p95 > 85 OU mem_p95 > 85 ; sinon OPTIMAL (percentiles de la "
        "fenetre, memes seuils que la table quotidienne)."
    ),
    "recommended_node_type": (
        "Type d'instance plus petit propose en remplacement, au dernier jour "
        "connu."
    ),
    "rightsizing_reco": (
        "Recommandation lisible d'ajustement, derivee du diagnostic de la "
        "fenetre."
    ),
    "estimated_savings_usd": (
        "Economie estimee en dollars sur la fenetre. Formule : somme des "
        "economies estimees quotidiennes."
    ),
    "_generated_at": "Horodatage de generation de cette ligne.",
}

GOLD_JOB_EFFICIENCY_DAILY = "gold_dbx_compute_job_efficiency_daily"

# Grain du cout MOINS `compute_kind`, et plus un alias de
# `JOB_CLUSTER_COST_DAILY_MERGE_KEYS` depuis T001b : cette table descend de
# `node_timeline`, qui n'echantillonne que des CLUSTERS -- elle ne contient donc
# que du job classique, et la colonne `compute_kind` n'y existe pas. La reprendre
# dans la cle de merge ferait echouer le MERGE sur une colonne inconnue. NE PAS
# "realigner" ces deux tuples : leur ecart est la consequence documentee de deux
# sources differentes (facturation vs node_timeline). L'identite VOULUE qui
# subsiste est "une ligne par job et par jour", a `compute_kind` pres.
JOB_EFFICIENCY_DAILY_MERGE_KEYS = (
    "cloud_provider",
    "workspace_id",
    "job_id",
    "period_start",
)

JOB_EFFICIENCY_DAILY_TABLE_COMMENT = (
    "Utilisation CPU/memoire et recommandations de redimensionnement "
    "(rightsizing) par JOB et par jour : rollup de "
    "gold_dbx_compute_cluster_efficiency_daily (cluster_type = 'JOB') par job_id "
    "stable plutot que par cluster ephemere. Ne PAS sommer les heures avec "
    "gold_dbx_compute_cluster_efficiency_daily ni "
    "gold_dbx_compute_pipeline_efficiency_daily (sous-ensembles disjoints des "
    "memes lignes node_timeline). Source : "
    "gold_dbx_compute_cluster_efficiency_daily + "
    "curated_dbx_lakeflow_job_task_run_timeline (lignee cluster_id -> job_id) + "
    "curated_dbx_lakeflow_jobs + curated_dbx_lakeflow_job_run_timeline (nom des "
    "runs soumis). COUVERTURE : population plus petite que "
    "gold_dbx_compute_job_cluster_cost_daily (un job serverless n'a aucun "
    "cluster, donc aucune ligne node_timeline) et limitee par l'historique plus "
    "court de job_task_run_timeline - verifier MIN(period_start)."
)
JOB_EFFICIENCY_DAILY_COLUMN_COMMENTS: dict[str, str] = {
    **_STABLE_GRAIN_EFFICIENCY_DAILY_COLUMN_COMMENTS,
    "job_id": (
        "Identifiant du job Databricks. Stable dans le temps (assigne une "
        "seule fois a la creation du job), contrairement au cluster_id "
        "ephemere qui change a chaque execution."
    ),
    "job_name": (
        "Nom du job, au dernier etat connu. Pour un run SOUMIS par API "
        "(jobs/runs/submit), qui n'a pas de definition de job persistee : le "
        "nom du RUN (run_name), a defaut de nom de job. Reste vide pour un run "
        "lance depuis un notebook, qui n'a de nom dans aucune source."
    ),
    "cluster_count": (
        "Nombre de clusters JOB ephemeres distincts ayant execute ce job ce "
        "jour-la. Formule : COUNT(DISTINCT cluster_id)."
    ),
}

JOB_EFFICIENCY_DAILY_SPEC = GoldAggregationSpec(
    source_tables=(
        GOLD_CLUSTER_EFFICIENCY_DAILY,
        # Lignee `cluster_id -> job_id` (meme CTE que job_cluster_cost_daily).
        CURATED_LAKEFLOW_JOB_TASK_RUN_TIMELINE,
        # Porte `run_name` : seul nom d'un run soumis par API, absent de `jobs`.
        CURATED_LAKEFLOW_JOB_RUN_TIMELINE,
        CURATED_LAKEFLOW_JOBS,
    ),
    target_table=GOLD_JOB_EFFICIENCY_DAILY,
    merge_keys=JOB_EFFICIENCY_DAILY_MERGE_KEYS,
    watermark_column="period_start",
    initial_mode="full",
    incremental_lookback_days=INCREMENTAL_LOOKBACK_DAYS,
    column_comments=JOB_EFFICIENCY_DAILY_COLUMN_COMMENTS,
    table_comment=JOB_EFFICIENCY_DAILY_TABLE_COMMENT,
)

GOLD_JOB_EFFICIENCY_ROLLING = "gold_dbx_compute_job_efficiency_rolling"

# Grain `*_rolling` : `period_start` remplace par `window_days`. Comme le daily
# ci-dessus, ce n'est plus un alias du grain de cout : pas de `compute_kind` sur
# une table alimentee par `node_timeline`.
JOB_EFFICIENCY_ROLLING_MERGE_KEYS = (
    "cloud_provider",
    "workspace_id",
    "job_id",
    "window_days",
)

JOB_EFFICIENCY_ROLLING_TABLE_COMMENT = (
    "Utilisation des JOBS Databricks, fenetres glissantes : CPU/memoire et "
    "diagnostic de dimensionnement recalcules sur les derniers 1/7/30/90 jours "
    "(colonne window_days) 'as of' le dernier jour disponible. Rollup de "
    "gold_dbx_compute_job_efficiency_daily (aucune relecture curated). Les "
    "percentiles (cpu/mem p95) sont recalcules a partir des histogrammes "
    "quotidiens sommes sur la fenetre, les percentiles quotidiens n'etant pas "
    "moyennables ; les moyennes sont ponderees par le temps allume. Un job sans "
    "aucun jour dans la fenetre courante est absent de la table."
)
JOB_EFFICIENCY_ROLLING_COLUMN_COMMENTS: dict[str, str] = {
    **_STABLE_GRAIN_EFFICIENCY_ROLLING_COLUMN_COMMENTS,
    "job_id": (
        "Identifiant du job Databricks, stable dans le temps (cf. table "
        "quotidienne source)."
    ),
    "job_name": (
        "Nom du job, au dernier jour connu dans la fenetre. Pour un run SOUMIS "
        "par API (jobs/runs/submit) : le nom du RUN (run_name), a defaut de nom "
        "de job. Reste vide pour un run lance depuis un notebook."
    ),
    "cluster_count": (
        "Nombre de clusters JOB ephemeres distincts ayant execute ce job sur la "
        "fenetre. Formule : somme des comptes distincts quotidiens -- exacte car "
        "les clusters JOB sont ephemeres (un cluster_id distinct par execution, "
        "jamais reutilise d'un jour a l'autre)."
    ),
}

JOB_EFFICIENCY_ROLLING_SPEC = GoldAggregationSpec(
    source_tables=(GOLD_JOB_EFFICIENCY_DAILY,),
    target_table=GOLD_JOB_EFFICIENCY_ROLLING,
    merge_keys=JOB_EFFICIENCY_ROLLING_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=JOB_EFFICIENCY_ROLLING_COLUMN_COMMENTS,
    table_comment=JOB_EFFICIENCY_ROLLING_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)

GOLD_PIPELINE_EFFICIENCY_DAILY = "gold_dbx_compute_pipeline_efficiency_daily"

# Grain du cout MOINS `compute_kind`, et pas un alias de
# `PIPELINE_COST_DAILY_MERGE_KEYS` -- exactement comme cote job depuis T001b,
# ou l'alias a du etre defait pour la meme raison : cette table descend de
# `node_timeline`, qui n'echantillonne que des CLUSTERS -- elle ne contient donc
# que du DLT classique, et la colonne `compute_kind` n'y existe pas. La reprendre
# dans la cle de merge ferait echouer le MERGE sur une colonne inconnue. NE PAS
# "realigner" ces deux tuples : leur ecart est la consequence documentee de deux
# sources differentes (facturation vs node_timeline).
PIPELINE_EFFICIENCY_DAILY_MERGE_KEYS = (
    "cloud_provider",
    "workspace_id",
    "dlt_pipeline_id",
    "period_start",
)

PIPELINE_EFFICIENCY_DAILY_TABLE_COMMENT = (
    "Utilisation CPU/memoire et recommandations de redimensionnement "
    "(rightsizing) par PIPELINE Lakeflow/DLT et par jour : rollup de "
    "gold_dbx_compute_cluster_efficiency_daily (cluster_type = 'PIPELINE') par "
    "dlt_pipeline_id stable plutot que par cluster ephemere. Ne PAS sommer les "
    "heures avec gold_dbx_compute_cluster_efficiency_daily ni "
    "gold_dbx_compute_job_efficiency_daily (sous-ensembles disjoints des memes "
    "lignes node_timeline). Source : "
    "gold_dbx_compute_cluster_efficiency_daily + curated_dbx_billing_usage "
    "(resolution cluster_id -> dlt_pipeline_id, meme source que le cout) + "
    "curated_dbx_lakeflow_pipelines. COUVERTURE : les pipelines DLT SERVERLESS "
    "n'ont aucun cluster, donc aucune ligne ici, alors qu'ils gardent leur ligne "
    "de cout dans gold_dbx_compute_pipeline_cost_daily - l'ecart de population "
    "entre les deux tables est ATTENDU. Cette table etant par construction "
    "100 % classique, elle ne porte PAS de colonne compute_kind : le pendant "
    "comparable cote cout est le sous-ensemble compute_kind = 'CLASSIC'."
)
PIPELINE_EFFICIENCY_DAILY_COLUMN_COMMENTS: dict[str, str] = {
    **_STABLE_GRAIN_EFFICIENCY_DAILY_COLUMN_COMMENTS,
    "dlt_pipeline_id": (
        "Identifiant du pipeline Lakeflow/DLT. Stable dans le temps (assigne "
        "une seule fois a la creation du pipeline), contrairement au cluster "
        "PIPELINE ephemere recree a chaque execution. Resolu depuis "
        "usage_metadata (cluster_id -> dlt_pipeline_id), meme source que le "
        "cout."
    ),
    "pipeline_name": (
        "Nom du pipeline, au dernier etat connu dans "
        "curated_dbx_lakeflow_pipelines. A defaut (aucune definition encore "
        "ingeree), le dlt_pipeline_id lui-meme."
    ),
    "cluster_count": (
        "Nombre de clusters PIPELINE ephemeres distincts ayant execute ce "
        "pipeline ce jour-la. Formule : COUNT(DISTINCT cluster_id)."
    ),
}

PIPELINE_EFFICIENCY_DAILY_SPEC = GoldAggregationSpec(
    source_tables=(
        GOLD_CLUSTER_EFFICIENCY_DAILY,
        # Resolution `cluster_id -> dlt_pipeline_id` : MEME source que
        # pipeline_cost_daily, pour que cout et efficacite ne puissent pas
        # designer deux pipelines differents pour un meme cluster.
        CURATED_BILLING_USAGE,
        # Referentiel de NOM : dernier etat connu du pipeline (pipeline_name).
        CURATED_LAKEFLOW_PIPELINES,
    ),
    target_table=GOLD_PIPELINE_EFFICIENCY_DAILY,
    merge_keys=PIPELINE_EFFICIENCY_DAILY_MERGE_KEYS,
    watermark_column="period_start",
    initial_mode="full",
    incremental_lookback_days=INCREMENTAL_LOOKBACK_DAYS,
    column_comments=PIPELINE_EFFICIENCY_DAILY_COLUMN_COMMENTS,
    table_comment=PIPELINE_EFFICIENCY_DAILY_TABLE_COMMENT,
)

GOLD_PIPELINE_EFFICIENCY_ROLLING = "gold_dbx_compute_pipeline_efficiency_rolling"

# Meme raison que `PIPELINE_EFFICIENCY_DAILY_MERGE_KEYS` : pas de `compute_kind`
# dans une table qui ne mesure que des clusters.
PIPELINE_EFFICIENCY_ROLLING_MERGE_KEYS = (
    "cloud_provider",
    "workspace_id",
    "dlt_pipeline_id",
    "window_days",
)

PIPELINE_EFFICIENCY_ROLLING_TABLE_COMMENT = (
    "Utilisation des PIPELINES Lakeflow/DLT, fenetres glissantes : CPU/memoire "
    "et diagnostic de dimensionnement recalcules sur les derniers 1/7/30/90 "
    "jours (colonne window_days) 'as of' le dernier jour disponible. Rollup de "
    "gold_dbx_compute_pipeline_efficiency_daily (aucune relecture curated). Les "
    "percentiles (cpu/mem p95) sont recalcules a partir des histogrammes "
    "quotidiens sommes sur la fenetre, les percentiles quotidiens n'etant pas "
    "moyennables ; les moyennes sont ponderees par le temps allume. Un pipeline "
    "sans aucun jour dans la fenetre courante est absent de la table."
)
PIPELINE_EFFICIENCY_ROLLING_COLUMN_COMMENTS: dict[str, str] = {
    **_STABLE_GRAIN_EFFICIENCY_ROLLING_COLUMN_COMMENTS,
    "dlt_pipeline_id": (
        "Identifiant du pipeline Lakeflow/DLT, stable dans le temps (cf. table "
        "quotidienne source)."
    ),
    "pipeline_name": (
        "Nom du pipeline, au dernier jour connu dans la fenetre. A defaut, le "
        "dlt_pipeline_id lui-meme."
    ),
    "cluster_count": (
        "Nombre de clusters PIPELINE ephemeres distincts ayant execute ce "
        "pipeline sur la fenetre. Formule : somme des comptes distincts "
        "quotidiens -- exacte car les clusters PIPELINE sont ephemeres (un "
        "cluster_id distinct par mise a jour, jamais reutilise d'un jour a "
        "l'autre)."
    ),
}

PIPELINE_EFFICIENCY_ROLLING_SPEC = GoldAggregationSpec(
    source_tables=(GOLD_PIPELINE_EFFICIENCY_DAILY,),
    target_table=GOLD_PIPELINE_EFFICIENCY_ROLLING,
    merge_keys=PIPELINE_EFFICIENCY_ROLLING_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=PIPELINE_EFFICIENCY_ROLLING_COLUMN_COMMENTS,
    table_comment=PIPELINE_EFFICIENCY_ROLLING_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)


# --- Tables gold SQL Warehouses (T003) --------------------------------------
GOLD_WAREHOUSE_COST_DAILY = "gold_dbx_compute_warehouse_cost_daily"
GOLD_WAREHOUSE_UTILIZATION_DAILY = "gold_dbx_compute_warehouse_utilization_daily"
GOLD_WAREHOUSE_QUERY_PERFORMANCE_DAILY = "gold_dbx_compute_warehouse_query_performance_daily"
GOLD_WAREHOUSE_QUERY_PERFORMANCE_ROLLING = (
    "gold_dbx_compute_warehouse_query_performance_rolling"
)

# Grain commun des 3 tables `*_daily` (cf. data-model.md Section "Couche GOLD —
# SQL Warehouses"). Pas de `source_lz_id` : meme limitation structurelle que
# `CLUSTER_DAILY_MERGE_KEYS` -- `account_id` (system.billing.usage/
# system.compute.warehouses) n'est pas mappable de facon fiable vers
# `dim_landing_zone.subscription_or_account_id`. Pas de `cost_rank`/
# `is_top_cost` sur ces tables (non demande, a la difference des clusters).
WAREHOUSE_DAILY_MERGE_KEYS = (
    "cloud_provider",
    "workspace_id",
    "warehouse_id",
    "period_start",
)

# Seuil (%) au-dela duquel un warehouse est diagnostique surdimensionne
# (`utilization_status = 'OVER'`), cf. compute_datamapping.md Section 3.2.
WAREHOUSE_IDLE_PCT_OVER_THRESHOLD = 60.0
# Ratio (pic de requetes concurrentes / max_clusters) au-dela duquel un
# warehouse est diagnostique sous-dimensionne (`utilization_status = 'UNDER'`).
WAREHOUSE_PEAK_CONCURRENCY_UNDER_RATIO = 0.8

# Seuils du rule engine `gold_dbx_compute_recommendations` (T004, regles
# WAREHOUSE de `compute_datamapping.md` §4.1) : aucune valeur n'est fixee par
# les docs sources ("seuil" generique dans le tableau) - valeurs choisies ici,
# donnee de configuration plutot que valeur magique dans le SQL.
# Temps d'attente en file (p95, millisecondes) au-dela duquel un warehouse est
# signale en sous-dimensionnement de scaling (RIGHTSIZING).
WAREHOUSE_QUEUE_TIME_P95_THRESHOLD_MS = 5000
# Taux d'echec quotidien (%) au-dela duquel les requetes en echec sont
# signalees (RELIABILITY).
WAREHOUSE_FAILURE_RATE_PCT_THRESHOLD = 5.0
# Nombre de requetes avec spill disque/memoire dans la journee au-dela duquel
# un tuning de requetes/upsize cible est signale (RIGHTSIZING).
WAREHOUSE_SPILL_QUERY_COUNT_THRESHOLD = 10

# Fenetre glissante (jours) sur laquelle le rule engine
# `gold_dbx_compute_recommendations` lit les metriques : il consomme les tables
# `*_rolling` filtrees sur `window_days = RECOMMENDATIONS_ROLLING_WINDOW_DAYS`
# plutot que le dernier jour des tables `*_daily`. 30 jours = signal soutenu :
# une reco de rightsizing/FinOps repose sur un comportement durable (pas un jour
# creux isole), evite le "flapping" OPEN/RESOLVED d'une semaine a l'autre et
# s'aligne sur le cycle de facturation mensuel. Les regles GOVERNANCE restent
# sur le snapshot `gold_dbx_compute_cluster_governance` (aucune variante
# rolling : c'est un etat courant, pas une metrique agregeable).
RECOMMENDATIONS_ROLLING_WINDOW_DAYS = 30

# Tampon (jours) ajoute AVANT `lower_bound` pour la seule lecture de
# `curated_dbx_compute_warehouse_events` dans `warehouse_utilization_daily`
# (reconstruction des sessions STARTING -> STOPPED). Une session encore
# ouverte (warehouse serverless jamais arrete) dont le `STARTING` precede la
# fenetre incrementale (`INCREMENTAL_LOOKBACK_DAYS`) doit rester visible a ce run
# pour que `running_hours` reste correct sur les jours de la fenetre. Doit donc
# rester SUPERIEUR a `INCREMENTAL_LOOKBACK_DAYS`, quelle que soit sa valeur.
# Meme ordre de grandeur que `INITIAL_BACKFILL_DAYS` (system_tables) :
# large tampon borne plutot qu'un `None` (full re-scan a chaque run) ou qu'un
# tampon d'1 jour (insuffisant pour des sessions ouvertes plusieurs jours).
# Limite residuelle : une session ouverte plus de 30 jours sans `STOPPED`
# reste sous-estimee jusqu'au prochain `--full-refresh`.
WAREHOUSE_SESSION_LOOKBACK_DAYS = 30

# Fenetre (heures) au-dela de laquelle une requete `curated_dbx_query_history`
# avec `end_time` NULL n'est PLUS consideree comme plausiblement encore en
# cours, et est exclue du balayage sweep-line (`active_query_hours`/
# `peak_concurrency`) plutot que traitee comme active jusqu'a
# `current_timestamp()`. Sans cette borne, une ligne dont la completion n'a
# jamais ete re-ingeree (cf. watermark `start_time` de `QUERY_HISTORY_SPEC`)
# serait comptee comme active indefiniment. Une requete SQL warehouse
# legitimement encore RUNNING au-dela de 24h est extremement improbable ;
# au-dela de ce seuil, la ligne est exclue plutot que comptee comme active.
WAREHOUSE_QUERY_STILL_RUNNING_MAX_HOURS = 24

# Tampon (jours) ajoute AVANT `lower_bound` pour la lecture de
# `curated_dbx_query_history` dans `warehouse_utilization_daily`
# (`active_query_hours`/`peak_concurrency`). Une requete demarree la veille
# de `lower_bound` et se terminant dans la fenetre lue doit rester visible
# pour que sa portion du jour courant soit prise en compte (`to_date(start_time)
# < lower_bound` sans ce tampon l'exclurait entierement) ; `query_history_by_day`
# decoupe ensuite chaque requete par jour calendaire traverse pour n'attribuer
# a chaque jour que sa fraction reelle. 1 jour suffit pour la tres grande
# majorite des requetes SQL warehouse (bornees par
# `WAREHOUSE_QUERY_STILL_RUNNING_MAX_HOURS` quand `end_time` est NULL) ;
# limite residuelle : une requete terminee dont la duree reelle depasse ce
# tampon (demarree plus de 24h avant `lower_bound`) resterait sous-comptee
# jusqu'au prochain `--full-refresh`.
WAREHOUSE_QUERY_HISTORY_LOOKBACK_DAYS = 1

# Valeur de `curated_dbx_compute_warehouses.warehouse_type` designant un
# warehouse serverless. Vocabulaire PARTAGE par la table d'utilisation
# quotidienne et son rollup (d'ou sa place ici plutot que dans un builder) : il
# sert a la fois de repli au discriminant de facturation (`is_serverless`) et de
# valeur exposee par la colonne `warehouse_type` du gold, qui ne doit jamais
# contredire ce discriminant.
#
# Le domaine de `warehouse_type` est OUVERT, et c'est mesure : le 2026-09-11 sur
# le curated dev, SERVERLESS (1477 warehouses), PRO (359), CLASSIC (162) -- et
# REAL_TIME (1). Ce 4e SKU n'a aujourd'hui aucune session dans
# `warehouse_events` (0 ligne dans le gold quotidien), mais rien ne garantit
# qu'il y reste. Les builders laissent donc PASSER la valeur declaree telle
# quelle au lieu de la ramener a un enum ferme de trois valeurs : un SKU inconnu
# doit s'afficher, pas disparaitre dans un NULL. Corollaire pour les
# consommateurs (API/IHM) : afficher la chaine recue, ne pas la valider contre
# une liste fermee.
WAREHOUSE_TYPE_SERVERLESS = "SERVERLESS"

# Commentaires communs aux 3 tables warehouses `*_daily` (grain quotidien).
# Meme role que `_CLUSTER_DAILY_COMMON_COLUMN_COMMENTS` : version courte,
# lisible depuis Catalog Explorer (UI Databricks).
_WAREHOUSE_DAILY_COMMON_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": "Fournisseur cloud du workspace (azure ou aws).",
    "workspace_id": "Identifiant du workspace Databricks.",
    "warehouse_id": "Identifiant du SQL Warehouse.",
    "period_start": "Jour agrege (grain quotidien).",
    "_generated_at": "Horodatage de generation de cette ligne.",
}

# Regle de resolution de `warehouse_name`, portee a l'identique sur les tables
# d'utilisation et de performance (grain jour puis grain fenetre). Ce texte est
# la SEULE documentation que verra un analyste qui requete la table depuis
# Catalog Explorer sans lire le code : il enonce donc la regle, pas seulement le
# libelle de la colonne.
_WAREHOUSE_NAME_DAILY_COLUMN_COMMENT = (
    "Nom du warehouse, au dernier etat connu a la FIN du jour agrege. Formule : "
    "nom porte par curated_dbx_compute_warehouses a sa derniere modification "
    "survenue avant la fin du jour agrege (change_time < period_start + "
    "INTERVAL 1 DAY) - un warehouse cree ou renomme en cours de journee porte "
    "donc, pour ce jour, son nom de fin de journee. NULL si le warehouse n'y "
    "figure pas : aucun nom de repli n'est fabrique."
)
_WAREHOUSE_NAME_WINDOW_COLUMN_COMMENT = (
    "Nom du warehouse, au dernier jour connu de la fenetre (meme reprise que "
    "les autres attributs portes a la maille fenetre). Un warehouse renomme "
    "pendant la fenetre y porte donc son nom le plus recent, pas celui du "
    "premier jour. NULL si le nom est inconnu."
)

# Discriminant serverless : cette colonne est ce qui rend LISIBLES les colonnes
# d'efficience vides (idle_pct, estimated_savings_usd...). Sans elle, un analyste
# lit un NULL muet et conclut a une donnee manquante, pas a un « sans objet ».
_IS_SERVERLESS_COLUMN_COMMENT = (
    "Vrai si le warehouse tournait en serverless ce jour-la (jamais vide). "
    "Formule : forme de compute effectivement facturee ce jour-la "
    "(product_features.is_serverless de curated_dbx_billing_usage), a defaut le "
    "type declare du warehouse (warehouse_type = SERVERLESS) au dernier etat "
    "connu, a defaut faux ; si le jour melange les deux formes, serverless "
    "l'emporte. Explique pourquoi les colonnes d'efficience (idle_pct, "
    "active_to_running_ratio, auto_stop_minutes, has_auto_stop, "
    "utilization_status, rightsizing_reco, estimated_savings_usd) sont vides sur "
    "ces lignes : en serverless, la facturation suit le compute des requetes et "
    "non le temps allume, un temps allume inutilise n'y coute donc rien et ne "
    "constitue aucune economie a realiser."
)
# Type de compute DECLARE, complement indispensable de `is_serverless` : un
# booleen ne distingue pas PRO de CLASSIC, alors que les deux existent bel et
# bien (mesure du 2026-09-11 : 359 warehouses PRO, 162 CLASSIC). Le commentaire
# enonce surtout la SUBORDINATION a `is_serverless` : c'est la seule chose qu'un
# analyste ne peut pas deviner en lisant les deux colonnes cote a cote.
_WAREHOUSE_TYPE_DAILY_COLUMN_COMMENT = (
    "Type de compute declare du warehouse ce jour-la : SERVERLESS, PRO ou "
    "CLASSIC. Formule : type declare par curated_dbx_compute_warehouses au "
    "dernier etat connu a la fin du jour agrege (meme regle que warehouse_name), "
    "MAIS toujours aligne sur is_serverless, qui reste la reference car il est lu "
    "sur la facturation - seule forme reellement facturee. Vaut donc SERVERLESS "
    "des qu'is_serverless est vrai, meme si le type declare dit PRO (3 "
    "jours-warehouse dans ce cas, mesure dev 2026-09-11) ; et vide si le type "
    "declare dit SERVERLESS alors que la facturation du jour dit le contraire (1 "
    "jour-warehouse) - on ne sait alors pas lequel de PRO ou CLASSIC a ete "
    "facture, et l'inventer serait faux. Vide egalement si le warehouse ne figure "
    "pas dans curated_dbx_compute_warehouses a cette date. D'autres types "
    "peuvent apparaitre (REAL_TIME existe deja cote curated) : la valeur declaree "
    "est servie telle quelle, jamais ramenee de force a l'une des trois."
)
_WAREHOUSE_TYPE_WINDOW_COLUMN_COMMENT = (
    "Type de compute declare du warehouse (SERVERLESS, PRO ou CLASSIC) au dernier "
    "jour RENSEIGNE de la fenetre - et non au dernier jour tout court : un jour "
    "sans type connu (warehouse absent du referentiel ce jour-la) n'efface pas un "
    "type connu la veille. Une fenetre de 90 jours peut melanger des jours de "
    "types differents ; c'est le plus recent qui decrit le warehouse tel qu'il "
    "est aujourd'hui, meme regle que warehouse_name. Toujours aligne sur "
    "is_serverless de la fenetre : des qu'un jour de la fenetre est serverless, "
    "la colonne vaut SERVERLESS. Vide si aucun jour de la fenetre ne porte de "
    "type connu."
)

_IS_SERVERLESS_WINDOW_COLUMN_COMMENT = (
    "Vrai si AU MOINS UN jour de la fenetre tournait en serverless (jamais "
    "vide). Formule : maximum du discriminant serverless quotidien sur les jours "
    "de la fenetre - un seul jour serverless suffit a rendre les ratios "
    "recalcules sur la fenetre non interpretables economiquement. Explique "
    "pourquoi les colonnes d'efficience de la ligne sont vides (sans objet) : "
    "cf. la table quotidienne."
)

WAREHOUSE_COST_DAILY_TABLE_COMMENT = (
    "FinOps SQL Warehouses : cout quotidien en dollars, DBU consommes, "
    "variation vs J-1, nombre de requetes et cout par requete. Source : "
    "curated_dbx_billing_usage + curated_dbx_billing_list_prices + "
    "curated_dbx_compute_warehouses + curated_dbx_query_history."
)
WAREHOUSE_COST_DAILY_COLUMN_COMMENTS: dict[str, str] = {
    **_WAREHOUSE_DAILY_COMMON_COLUMN_COMMENTS,
    "warehouse_name": "Nom du warehouse, au dernier etat connu ce jour-la.",
    "warehouse_size": "Taille du warehouse (ex. X-Small, Medium), au dernier etat connu.",
    "dbu_quantity": (
        "Volume de DBU (unite de facturation Databricks) consomme ce jour-la. "
        "Formule : somme des DBU factures sur la journee."
    ),
    "cost_usd": (
        "Cout total en dollars du warehouse ce jour-la. Formule : quantite "
        "consommee (DBU) multipliee par le prix unitaire effectif, sommee sur "
        "la journee."
    ),
    "cost_usd_prev_day": (
        "Cout du jour calendaire precedent, pour comparaison. Formule : cout "
        "total (cost_usd) du meme warehouse, calcule pour la veille."
    ),
    "cost_delta_pct": (
        "Variation du cout par rapport a la veille, en pourcentage. Formule : "
        "(cout du jour - cout de la veille) / cout de la veille x 100."
    ),
    "query_count": (
        "Nombre de requetes executees sur ce warehouse ce jour-la. Formule : "
        "comptage des requetes de curated_dbx_query_history dont le compute "
        "cible est ce warehouse."
    ),
    "cost_per_query_usd": (
        "Cout moyen par requete ce jour-la. Formule : cout total (cost_usd) "
        "divise par le nombre de requetes (query_count)."
    ),
    "top_consumer": (
        "Utilisateur ayant le plus consomme de temps d'execution sur ce "
        "warehouse ce jour-la. Formule : utilisateur avec la plus grande "
        "somme de duree de requetes, tous statements confondus."
    ),
}

WAREHOUSE_UTILIZATION_DAILY_TABLE_COMMENT = (
    "Utilisation des SQL Warehouses : temps allume vs. temps avec requetes "
    "actives, stabilite du scaling et recommandations de redimensionnement "
    "(rightsizing). Le diagnostic d'efficience ne concerne que le compute "
    "classique / pro : sur les warehouses serverless (is_serverless), la "
    "facturation suit le compute des requetes et non le temps allume, donc "
    "idle_pct, active_to_running_ratio, auto_stop_minutes, has_auto_stop, "
    "utilization_status, rightsizing_reco et estimated_savings_usd sont vides "
    "(sans objet) ; les metriques d'activite restent renseignees. Source : "
    "curated_dbx_compute_warehouse_events + "
    "curated_dbx_query_history + curated_dbx_compute_warehouses + "
    "gold_dbx_compute_warehouse_cost_daily + curated_dbx_billing_usage."
)
WAREHOUSE_UTILIZATION_DAILY_COLUMN_COMMENTS: dict[str, str] = {
    **_WAREHOUSE_DAILY_COMMON_COLUMN_COMMENTS,
    "warehouse_name": _WAREHOUSE_NAME_DAILY_COLUMN_COMMENT,
    "is_serverless": _IS_SERVERLESS_COLUMN_COMMENT,
    "warehouse_type": _WAREHOUSE_TYPE_DAILY_COLUMN_COMMENT,
    "running_hours": (
        "Nombre d'heures ou le warehouse etait allume ce jour-la. Formule : "
        "somme des sessions STARTING -> STOPPED observees dans le journal "
        "d'evenements (STARTING borne le debut reel de l'allumage, rampe de "
        "demarrage comprise)."
    ),
    "active_query_hours": (
        "Duree reelle (fractionnaire) ou au moins une requete tournait sur "
        "ce warehouse. Formule : union des intervalles d'execution des "
        "requetes du jour (sans double-compter les chevauchements)."
    ),
    "idle_pct": (
        "Part du temps allume sans requete active (%). Formule : (heures "
        "allume - heures actives) / heures allume x 100. Vide sur un warehouse "
        "serverless : l'idle y est le fonctionnement attendu et n'est pas "
        "facture."
    ),
    "active_to_running_ratio": (
        "Part du temps allume reellement exploite. Formule : heures actives "
        "divisees par heures allume. Vide sur un warehouse serverless (meme "
        "raison qu'idle_pct)."
    ),
    "auto_stop_minutes": (
        "Delai d'auto-arret configure sur le warehouse, en minutes (valeur "
        "de configuration au dernier etat connu). Vide sur un warehouse "
        "serverless : l'arret y est gere par la plateforme."
    ),
    "has_auto_stop": (
        "Vrai si l'auto-arret est active sur le warehouse. Formule : vrai si "
        "le delai d'auto-arret configure est superieur a 0. Vide sur un "
        "warehouse serverless (sans objet)."
    ),
    "scale_up_events": (
        "Nombre d'evenements de montee en charge (scale up) ce jour-la. "
        "Formule : comptage des evenements de type SCALING_UP/SCALED_UP."
    ),
    "scale_down_events": (
        "Nombre d'evenements de descente en charge (scale down) ce jour-la. "
        "Formule : comptage des evenements de type SCALED_DOWN."
    ),
    "avg_cluster_count": (
        "Nombre moyen de clusters du warehouse sur la journee. Formule : "
        "moyenne du nombre de clusters observe sur tous les evenements du "
        "jour."
    ),
    "max_cluster_count": (
        "Nombre maximum de clusters du warehouse observe sur la journee. "
        "Formule : le plus grand nombre de clusters observe sur un "
        "evenement du jour."
    ),
    "peak_concurrency": (
        "Pic de requetes executees simultanement dans la journee. Formule : "
        "nombre maximum de requetes dont les intervalles d'execution se "
        "chevauchent, tous instants confondus de la journee."
    ),
    "utilization_status": (
        "Diagnostic de dimensionnement : OVER (surdimensionne), UNDER "
        "(sous-dimensionne) ou OPTIMAL. Formule : OVER si le temps idle "
        "depasse le seuil configure ; UNDER si le pic de concurrence "
        "approche la capacite maximale (max_clusters) ; sinon OPTIMAL. Vide "
        "sur un warehouse serverless : aucun levier de dimensionnement au "
        "temps allume, donc aucun verdict a rendre."
    ),
    "rightsizing_reco": (
        "Recommandation lisible d'ajustement de la taille ou de la "
        "configuration du warehouse. Formule : texte genere a partir du "
        "diagnostic de dimensionnement (utilization_status). Vide sur un "
        "warehouse serverless (aucune action a recommander sur ce levier)."
    ),
    "estimated_savings_usd": (
        "Economie estimee en dollars si la recommandation est appliquee. "
        "Formule : cout du jour (cost_usd) multiplie par la part de temps "
        "idle (idle_pct), uniquement quand le warehouse est diagnostique "
        "surdimensionne. Vide sur un warehouse serverless : cette economie "
        "n'existe pas, la facturation y suit le compute des requetes et non le "
        "temps allume."
    ),
}

WAREHOUSE_QUERY_PERFORMANCE_DAILY_TABLE_COMMENT = (
    "Performance des requetes SQL Warehouses : volume, taux d'echec, "
    "latences (percentiles), temps de file d'attente, spill disque et taux "
    "de cache. Source : curated_dbx_query_history (metriques) + "
    "curated_dbx_compute_warehouses (nom du warehouse, sans effet sur les "
    "metriques)."
)
WAREHOUSE_QUERY_PERFORMANCE_DAILY_COLUMN_COMMENTS: dict[str, str] = {
    **_WAREHOUSE_DAILY_COMMON_COLUMN_COMMENTS,
    "warehouse_name": _WAREHOUSE_NAME_DAILY_COLUMN_COMMENT,
    "query_count": "Nombre de requetes executees sur ce warehouse ce jour-la.",
    "failed_count": (
        "Nombre de requetes en echec ou annulees ce jour-la. Formule : "
        "comptage des requetes dont le statut est FAILED ou CANCELED."
    ),
    "failure_rate_pct": (
        "Taux d'echec du jour, en pourcentage. Formule : requetes en echec "
        "divisees par le nombre total de requetes x 100."
    ),
    "latency_p50_ms": (
        "Duree mediane des requetes, en millisecondes. Formule : 50e "
        "percentile de la duree totale des requetes."
    ),
    "latency_p95_ms": (
        "Duree des requetes au 95e percentile, en millisecondes (pic "
        "soutenu, en ignorant les rares pointes extremes)."
    ),
    "latency_p99_ms": (
        "Duree des requetes au 99e percentile, en millisecondes (pointes "
        "extremes)."
    ),
    "queue_time_avg_ms": (
        "Temps moyen passe en file d'attente avant l'execution effective de "
        "la requete, en millisecondes (signal de sous-dimensionnement du "
        "warehouse)."
    ),
    "queue_time_p95_ms": (
        "Temps passe en file d'attente au 95e percentile, en millisecondes."
    ),
    "latency_hist": (
        "Histogramme de la duree des requetes (ms), 15 buckets a bornes quasi-"
        "logarithmiques (50 ms a ~410 s plus overflow). Distribution sommable "
        "permettant de recalculer les percentiles de latence sur des fenetres "
        "glissantes (cf. table _rolling)."
    ),
    "queue_time_hist": (
        "Histogramme du temps d'attente en file (ms), memes buckets que "
        "latency_hist. Distribution sommable pour le recalcul des percentiles "
        "de file d'attente sur fenetres glissantes."
    ),
    "spill_query_count": (
        "Nombre de requetes ayant deborde sur disque par manque de memoire. "
        "Formule : comptage des requetes ayant ecrit des donnees "
        "temporaires locales (spill)."
    ),
    "cache_hit_pct": (
        "Taux moyen de lecture depuis le cache disque du warehouse (%). "
        "Formule : moyenne du pourcentage de lecture servie par le cache."
    ),
    "bytes_scanned": (
        "Volume total de donnees lues par les requetes du jour, en octets. "
        "Formule : somme des octets lus."
    ),
    "rows_scanned": (
        "Nombre total de lignes lues par les requetes du jour. Formule : "
        "somme des lignes lues."
    ),
    "top_slow_statement_id": (
        "Identifiant de la requete la plus lente du jour. Formule : "
        "identifiant de la requete ayant la plus longue duree totale "
        "d'execution."
    ),
}


WAREHOUSE_COST_DAILY_SPEC = GoldAggregationSpec(
    source_tables=(
        CURATED_BILLING_USAGE,
        CURATED_BILLING_LIST_PRICES,
        CURATED_COMPUTE_WAREHOUSES,
        CURATED_QUERY_HISTORY,
    ),
    target_table=GOLD_WAREHOUSE_COST_DAILY,
    merge_keys=WAREHOUSE_DAILY_MERGE_KEYS,
    watermark_column="period_start",
    initial_mode="full",
    incremental_lookback_days=INCREMENTAL_LOOKBACK_DAYS,
    column_comments=WAREHOUSE_COST_DAILY_COLUMN_COMMENTS,
    table_comment=WAREHOUSE_COST_DAILY_TABLE_COMMENT,
)

GOLD_WAREHOUSE_COST_ROLLING = "gold_dbx_compute_warehouse_cost_rolling"

# Grain `*_rolling` : `period_start` remplace par `window_days`. Pas de
# `cost_rank` (aligne sur la table quotidienne source, cf. commentaire de
# WAREHOUSE_DAILY_MERGE_KEYS).
WAREHOUSE_COST_ROLLING_MERGE_KEYS = (
    "cloud_provider",
    "workspace_id",
    "warehouse_id",
    "window_days",
)

WAREHOUSE_COST_ROLLING_TABLE_COMMENT = (
    "FinOps warehouses, fenetres glissantes : cout, DBU et nombre de requetes "
    "cumules sur les derniers 1/7/30/90 jours (colonne window_days) 'as of' le "
    "dernier jour disponible, cout moyen par requete recalcule sur la fenetre "
    "et variation vs la fenetre precedente de meme longueur. Rollup de "
    "gold_dbx_compute_warehouse_cost_daily (aucune relecture curated)."
)
WAREHOUSE_COST_ROLLING_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": "Fournisseur cloud du workspace (azure ou aws).",
    "workspace_id": "Identifiant du workspace Databricks.",
    "warehouse_id": "Identifiant du SQL Warehouse.",
    "window_days": (
        "Longueur de la fenetre glissante en jours (1, 7, 30 ou 90). 1 = "
        "equivalent du grain quotidien (un seul jour), 7/30/90 = derniers "
        "7/30/90 jours."
    ),
    "as_of_date": (
        "Dernier jour disponible dans la table quotidienne source, borne haute "
        "(incluse) de toutes les fenetres. Formule : MAX(period_start)."
    ),
    "window_start": (
        "Premier jour (inclus) de la fenetre. Formule : as_of_date - "
        "(window_days - 1)."
    ),
    "warehouse_name": "Nom du warehouse, au dernier etat connu dans la fenetre.",
    "warehouse_size": "Taille du warehouse, au dernier etat connu dans la fenetre.",
    "dbu_quantity": (
        "Volume de DBU consommes sur la fenetre. Formule : somme des DBU "
        "quotidiens sur les window_days jours."
    ),
    "cost_usd": (
        "Cout total en dollars sur la fenetre. Formule : somme des couts "
        "quotidiens sur les window_days jours."
    ),
    "query_count": (
        "Nombre de requetes executees sur la fenetre. Formule : somme des "
        "comptages quotidiens sur les window_days jours."
    ),
    "cost_per_query_usd": (
        "Cout moyen par requete sur la fenetre. Formule : cout total de la "
        "fenetre divise par le nombre de requetes de la fenetre."
    ),
    "top_consumer": (
        "Utilisateur ayant le plus consomme de temps d'execution, au dernier "
        "jour connu (reflete le dernier jour de la fenetre, pas l'ensemble de "
        "la fenetre)."
    ),
    "cost_usd_prev_window": (
        "Cout total sur la fenetre precedente de meme longueur, pour "
        "comparaison. Formule : somme des couts quotidiens sur les window_days "
        "jours qui precedent immediatement la fenetre courante."
    ),
    "cost_delta_pct": (
        "Variation du cout vs la fenetre precedente, en pourcentage. Formule : "
        "(cout fenetre - cout fenetre precedente) / cout fenetre precedente x 100."
    ),
    "_generated_at": "Horodatage de generation de cette ligne.",
}

WAREHOUSE_COST_ROLLING_SPEC = GoldAggregationSpec(
    source_tables=(GOLD_WAREHOUSE_COST_DAILY,),
    target_table=GOLD_WAREHOUSE_COST_ROLLING,
    merge_keys=WAREHOUSE_COST_ROLLING_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=WAREHOUSE_COST_ROLLING_COLUMN_COMMENTS,
    table_comment=WAREHOUSE_COST_ROLLING_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)

# SEULE table `*_daily` a activer la suppression des lignes absentes, et c'est
# volontairement une exception : ses jours-warehouse ne sont pas de purs faits
# horodates, ils sont RECONSTRUITS par sessionnisation des evenements
# `warehouse_events`. Un jour recalcule sur une source plus complete peut donc ne
# plus produire du tout un jour-warehouse ecrit par un run precedent — mesure en
# dev le 2026-09-10 : 75 jours-warehouse fantomes (24,0 h allumees pile, 0 h
# active, 0 $), 37/37 des warehouses concernes existant toujours par ailleurs.
# La suppression est bornee a la fenetre recalculee par
# `resolve_absent_row_delete_predicate` : sans cette borne, elle effacerait tout
# l'historique anterieur a la fenetre (cf. la docstring de cette methode).
# NE PAS etendre ce garde-fou aux autres tables `*_daily` sans avoir verifie
# qu'elles ont la meme propriete : celles qui agregent directement la
# facturation ou `node_timeline` n'ont aucune raison de perdre un jour deja ecrit.
# Corollaire, applique en T001c : un changement de POPULATION (un filtre ajoute a
# un builder) laisse derriere lui des lignes que la nouvelle definition ne produit
# plus. Ce n'est pas une raison d'armer ce garde-fou en permanence sur la table
# concernee -- ce serait accepter definitivement, pour une reparation ponctuelle,
# qu'elle perde un jour deja ecrit. Le nettoyage passe par le parametre de run
# `one_off_purge` (cf. `pipelines.gold_dbx_compute.entrypoint`), qui injecte le
# garde-fou pour UN run et ne persiste rien.
WAREHOUSE_UTILIZATION_DAILY_SPEC = GoldAggregationSpec(
    source_tables=(
        CURATED_COMPUTE_WAREHOUSE_EVENTS,
        CURATED_QUERY_HISTORY,
        CURATED_COMPUTE_WAREHOUSES,
        GOLD_WAREHOUSE_COST_DAILY,  # pour `estimated_savings_usd` (cout du jour)
        CURATED_BILLING_USAGE,  # pour `is_serverless` (forme de compute facturee)
    ),
    target_table=GOLD_WAREHOUSE_UTILIZATION_DAILY,
    merge_keys=WAREHOUSE_DAILY_MERGE_KEYS,
    watermark_column="period_start",
    initial_mode="full",
    incremental_lookback_days=INCREMENTAL_LOOKBACK_DAYS,
    column_comments=WAREHOUSE_UTILIZATION_DAILY_COLUMN_COMMENTS,
    table_comment=WAREHOUSE_UTILIZATION_DAILY_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)

GOLD_WAREHOUSE_UTILIZATION_ROLLING = "gold_dbx_compute_warehouse_utilization_rolling"

WAREHOUSE_UTILIZATION_ROLLING_MERGE_KEYS = (
    "cloud_provider",
    "workspace_id",
    "warehouse_id",
    "window_days",
)

WAREHOUSE_UTILIZATION_ROLLING_TABLE_COMMENT = (
    "Utilisation des SQL Warehouses, fenetres glissantes : temps allume vs. "
    "temps actif cumules sur les derniers 1/7/30/90 jours (colonne "
    "window_days) 'as of' le dernier jour disponible, part de temps idle et "
    "diagnostic de dimensionnement recalcules sur la fenetre. Rollup de "
    "gold_dbx_compute_warehouse_utilization_daily (aucune relecture curated). "
    "NOTE : le diagnostic UNDER utilise max_cluster_count (max observe sur la "
    "fenetre) comme proxy de capacite, la config max_clusters n'etant pas "
    "portee a la maille fenetre (ecart vs la table quotidienne). Comme la table "
    "quotidienne, le diagnostic d'efficience ne concerne que le compute "
    "classique / pro : il est vide (sans objet) des qu'un jour de la fenetre est "
    "serverless (is_serverless)."
)
WAREHOUSE_UTILIZATION_ROLLING_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": "Fournisseur cloud du workspace (azure ou aws).",
    "workspace_id": "Identifiant du workspace Databricks.",
    "warehouse_id": "Identifiant du SQL Warehouse.",
    "window_days": (
        "Longueur de la fenetre glissante en jours (1, 7, 30 ou 90). 1 = "
        "equivalent du grain quotidien (un seul jour), 7/30/90 = derniers "
        "7/30/90 jours."
    ),
    "as_of_date": (
        "Dernier jour disponible dans la table quotidienne source, borne haute "
        "(incluse) de toutes les fenetres. Formule : MAX(period_start)."
    ),
    "window_start": (
        "Premier jour (inclus) de la fenetre. Formule : as_of_date - "
        "(window_days - 1)."
    ),
    "warehouse_name": _WAREHOUSE_NAME_WINDOW_COLUMN_COMMENT,
    "is_serverless": _IS_SERVERLESS_WINDOW_COLUMN_COMMENT,
    "warehouse_type": _WAREHOUSE_TYPE_WINDOW_COLUMN_COMMENT,
    "running_hours": (
        "Nombre total d'heures ou le warehouse etait allume sur la fenetre. "
        "Formule : somme des heures allume quotidiennes."
    ),
    "active_query_hours": (
        "Duree totale (fractionnaire) ou au moins une requete tournait sur la "
        "fenetre. Formule : somme des heures actives quotidiennes."
    ),
    "idle_pct": (
        "Part du temps allume sans requete active sur la fenetre (%). Formule : "
        "(heures allume - heures actives) / heures allume x 100, recalcule a "
        "partir des sommes de la fenetre. Vide si un jour de la fenetre est "
        "serverless (is_serverless)."
    ),
    "active_to_running_ratio": (
        "Part du temps allume reellement exploite sur la fenetre. Formule : "
        "heures actives / heures allume, recalcule a partir des sommes. Vide si "
        "un jour de la fenetre est serverless (is_serverless)."
    ),
    "auto_stop_minutes": (
        "Delai d'auto-arret configure sur le warehouse, en minutes, au dernier "
        "etat connu. Vide si un jour de la fenetre est serverless "
        "(is_serverless) : l'arret y est gere par la plateforme."
    ),
    "has_auto_stop": (
        "Vrai si l'auto-arret est active sur le warehouse, au dernier etat "
        "connu. Vide si un jour de la fenetre est serverless (is_serverless)."
    ),
    "scale_up_events": (
        "Nombre total d'evenements de montee en charge sur la fenetre. "
        "Formule : somme des evenements scale up quotidiens."
    ),
    "scale_down_events": (
        "Nombre total d'evenements de descente en charge sur la fenetre. "
        "Formule : somme des evenements scale down quotidiens."
    ),
    "avg_cluster_count": (
        "Nombre moyen de clusters du warehouse sur la fenetre. Formule : "
        "moyenne des moyennes quotidiennes ponderee par le temps allume de "
        "chaque jour."
    ),
    "max_cluster_count": (
        "Nombre maximum de clusters du warehouse observe sur la fenetre. "
        "Formule : maximum des maxima quotidiens."
    ),
    "peak_concurrency": (
        "Pic de requetes executees simultanement sur la fenetre. Formule : "
        "maximum des pics quotidiens."
    ),
    "utilization_status": (
        "Diagnostic de dimensionnement sur la fenetre : OVER (surdimensionne), "
        "UNDER (sous-dimensionne) ou OPTIMAL. Formule : OVER si idle_pct de la "
        "fenetre depasse le seuil ; UNDER si le pic de concurrence approche "
        "max_cluster_count (proxy de capacite) ; sinon OPTIMAL. Vide si un jour "
        "de la fenetre est serverless (is_serverless) : aucun levier de "
        "dimensionnement au temps allume."
    ),
    "rightsizing_reco": (
        "Recommandation lisible d'ajustement, derivee du diagnostic "
        "(utilization_status) de la fenetre. Vide si un jour de la fenetre est "
        "serverless (is_serverless)."
    ),
    "estimated_savings_usd": (
        "Economie estimee en dollars sur la fenetre. Formule : somme des "
        "economies estimees quotidiennes (uniquement les jours diagnostiques "
        "surdimensionnes). Vide si un jour de la fenetre est serverless "
        "(is_serverless) : cette economie n'existe pas en serverless."
    ),
    "_generated_at": "Horodatage de generation de cette ligne.",
}

WAREHOUSE_UTILIZATION_ROLLING_SPEC = GoldAggregationSpec(
    source_tables=(GOLD_WAREHOUSE_UTILIZATION_DAILY,),
    target_table=GOLD_WAREHOUSE_UTILIZATION_ROLLING,
    merge_keys=WAREHOUSE_UTILIZATION_ROLLING_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=WAREHOUSE_UTILIZATION_ROLLING_COLUMN_COMMENTS,
    table_comment=WAREHOUSE_UTILIZATION_ROLLING_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)

WAREHOUSE_QUERY_PERFORMANCE_DAILY_SPEC = GoldAggregationSpec(
    # `curated_dbx_compute_warehouses` n'apporte aucune metrique : uniquement
    # `warehouse_name` au dernier etat connu (LEFT JOIN, cf.
    # `warehouse_query_performance_daily.build_warehouse_query_performance_daily`).
    source_tables=(CURATED_QUERY_HISTORY, CURATED_COMPUTE_WAREHOUSES),
    target_table=GOLD_WAREHOUSE_QUERY_PERFORMANCE_DAILY,
    merge_keys=WAREHOUSE_DAILY_MERGE_KEYS,
    watermark_column="period_start",
    initial_mode="full",
    incremental_lookback_days=INCREMENTAL_LOOKBACK_DAYS,
    column_comments=WAREHOUSE_QUERY_PERFORMANCE_DAILY_COLUMN_COMMENTS,
    table_comment=WAREHOUSE_QUERY_PERFORMANCE_DAILY_TABLE_COMMENT,
)

WAREHOUSE_QUERY_PERFORMANCE_ROLLING_MERGE_KEYS = (
    "cloud_provider",
    "workspace_id",
    "warehouse_id",
    "window_days",
)

WAREHOUSE_QUERY_PERFORMANCE_ROLLING_TABLE_COMMENT = (
    "Performance des requetes SQL Warehouses, fenetres glissantes : volume, "
    "taux d'echec et latences recalcules sur les derniers 1/7/30/90 jours "
    "(colonne window_days) 'as of' le dernier jour disponible. Rollup de "
    "gold_dbx_compute_warehouse_query_performance_daily (aucune relecture "
    "curated). Les percentiles de latence et de file d'attente sont recalcules "
    "a partir des histogrammes quotidiens sommes sur la fenetre, les "
    "percentiles quotidiens n'etant pas moyennables."
)
WAREHOUSE_QUERY_PERFORMANCE_ROLLING_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": "Fournisseur cloud du workspace (azure ou aws).",
    "workspace_id": "Identifiant du workspace Databricks.",
    "warehouse_id": "Identifiant du SQL Warehouse.",
    "window_days": (
        "Longueur de la fenetre glissante en jours (1, 7, 30 ou 90). 1 = "
        "equivalent du grain quotidien, 7/30/90 = derniers 7/30/90 jours."
    ),
    "as_of_date": (
        "Dernier jour disponible dans la table quotidienne source, borne haute "
        "(incluse) de toutes les fenetres. Formule : MAX(period_start)."
    ),
    "window_start": (
        "Premier jour (inclus) de la fenetre. Formule : as_of_date - "
        "(window_days - 1)."
    ),
    "warehouse_name": _WAREHOUSE_NAME_WINDOW_COLUMN_COMMENT,
    "query_count": (
        "Nombre total de requetes executees sur la fenetre. Formule : somme "
        "des volumes quotidiens."
    ),
    "failed_count": (
        "Nombre total de requetes en echec ou annulees sur la fenetre. "
        "Formule : somme des echecs quotidiens."
    ),
    "failure_rate_pct": (
        "Taux d'echec sur la fenetre (%). Formule : echecs totaux / requetes "
        "totales x 100, recalcule sur les sommes de la fenetre."
    ),
    "latency_p50_ms": (
        "Duree mediane des requetes sur la fenetre (ms). Formule : 50e "
        "percentile recalcule a partir de l'histogramme de latence somme sur "
        "la fenetre (resolution bornee par la largeur des buckets)."
    ),
    "latency_p95_ms": (
        "Duree des requetes au 95e percentile sur la fenetre (ms). Formule : "
        "recalcule a partir de l'histogramme de latence somme sur la fenetre."
    ),
    "latency_p99_ms": (
        "Duree des requetes au 99e percentile sur la fenetre (ms). Formule : "
        "recalcule a partir de l'histogramme de latence somme sur la fenetre."
    ),
    "queue_time_avg_ms": (
        "Temps moyen en file d'attente sur la fenetre (ms). Formule : moyenne "
        "des moyennes quotidiennes ponderee par le nombre de requetes."
    ),
    "queue_time_p95_ms": (
        "Temps en file d'attente au 95e percentile sur la fenetre (ms). "
        "Formule : recalcule a partir de l'histogramme de file d'attente somme "
        "sur la fenetre."
    ),
    "spill_query_count": (
        "Nombre total de requetes ayant deborde sur disque sur la fenetre. "
        "Formule : somme des comptages quotidiens."
    ),
    "cache_hit_pct": (
        "Taux moyen de lecture depuis le cache sur la fenetre (%). Formule : "
        "moyenne des taux quotidiens ponderee par le nombre de requetes."
    ),
    "bytes_scanned": (
        "Volume total d'octets lus par les requetes sur la fenetre. Formule : "
        "somme des volumes quotidiens."
    ),
    "rows_scanned": (
        "Nombre total de lignes lues par les requetes sur la fenetre. "
        "Formule : somme des volumes quotidiens."
    ),
    "top_slow_statement_id": (
        "Identifiant de la requete la plus lente du dernier jour connu (la "
        "table quotidienne ne porte pas la duree, un maximum global sur la "
        "fenetre n'est pas calculable)."
    ),
    "_generated_at": "Horodatage de generation de cette ligne.",
}

WAREHOUSE_QUERY_PERFORMANCE_ROLLING_SPEC = GoldAggregationSpec(
    source_tables=(GOLD_WAREHOUSE_QUERY_PERFORMANCE_DAILY,),
    target_table=GOLD_WAREHOUSE_QUERY_PERFORMANCE_ROLLING,
    merge_keys=WAREHOUSE_QUERY_PERFORMANCE_ROLLING_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=WAREHOUSE_QUERY_PERFORMANCE_ROLLING_COLUMN_COMMENTS,
    table_comment=WAREHOUSE_QUERY_PERFORMANCE_ROLLING_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)


# --- Table gold transverse reactive (T004) ----------------------------------
# `recommendations` : fait actionnable unifie (rule engine), cle = `recommendation_id`
# (hash stable workspace_id||object_type||object_id||category||first_seen_date,
# cf. `pipelines.gold_dbx_compute.recommendations` pour le detail du choix de
# `first_seen_date` plutot que la date du run dans ce hash). Pas de watermark/
# fenetre incrementale (cf. R9 scope note) : le rule engine relit l'etat
# courant complet des tables gold `*_daily`/`governance` a chaque run, pour
# detecter correctement les transitions OPEN -> RESOLVED.
#
# Couvre les 10 regles CLUSTER + WAREHOUSE de `compute_datamapping.md` §4.1.
GOLD_RECOMMENDATIONS = "gold_dbx_compute_recommendations"

RECOMMENDATIONS_MERGE_KEYS = ("recommendation_id",)

RECOMMENDATIONS_TABLE_COMMENT = (
    "Fait actionnable unifie (reco d'optimisation), clusters + warehouses (T004) : "
    "regles de seuil sur les gold *_daily/governance, cycle de vie "
    "OPEN/RESOLVED (les lignes non observees depuis plus de "
    f"{RECOMMENDATIONS_RESOLVED_RETENTION_DAYS} jours sont purgees). "
    "Source : gold_dbx_compute_cluster_efficiency_daily + "
    "gold_dbx_compute_cluster_reliability_daily + gold_dbx_compute_cluster_governance "
    "+ gold_dbx_compute_cluster_cost_daily + gold_dbx_compute_warehouse_utilization_daily "
    "+ gold_dbx_compute_warehouse_query_performance_daily + gold_dbx_compute_warehouse_cost_daily."
)
RECOMMENDATIONS_COLUMN_COMMENTS: dict[str, str] = {
    "recommendation_id": (
        "Cle stable de la recommandation. Formule : hash du workspace, du type "
        "d'objet, de son identifiant, de la categorie et de la date de "
        "premiere detection (pas la date du jour) — reste identique tout au "
        "long du cycle de vie de l'anomalie."
    ),
    "cloud_provider": "Fournisseur cloud du workspace (azure ou aws).",
    "workspace_id": "Identifiant du workspace Databricks.",
    "object_type": "Type d'objet concerne par la recommandation (CLUSTER ou WAREHOUSE).",
    "object_id": "Identifiant de l'objet (cluster_id ou warehouse_id).",
    "object_name": "Nom lisible de l'objet, au dernier etat connu.",
    "category": "Categorie metier : FINOPS, RIGHTSIZING, RELIABILITY ou GOVERNANCE.",
    "mode": "Mode de generation de la recommandation : toujours REACTIVE (regle de seuil).",
    "title": "Resume court de l'anomalie detectee.",
    "detail": "Contexte chiffre de l'anomalie (valeurs mesurees).",
    "recommended_action": "Action concrete proposee.",
    "estimated_savings_usd": (
        "Economie estimee en dollars si l'action est appliquee (NULL si non chiffrable)."
    ),
    "severity": "Niveau de priorite : LOW, MEDIUM ou HIGH.",
    "personas": "Roles concernes par cette recommandation (FIN, DE, AN, GOV).",
    "status": (
        "Etat du cycle de vie : OPEN (condition toujours vraie), ACK (prise en "
        "compte, non gere par ce rule engine) ou RESOLVED (condition qui ne se "
        "declenche plus). Formule : OPEN si l'objet declenche encore la regle de "
        "cette categorie aujourd'hui ; RESOLVED si l'anomalie etait connue "
        "(presente dans l'etat precedent) mais qu'aucune regle de cette "
        "categorie ne se declenche plus pour cet objet."
    ),
    "first_seen_date": "Date de premiere detection de cette anomalie (preservee au fil des runs).",
    "last_seen_date": "Derniere date ou la condition a ete observee comme vraie.",
    "_generated_at": "Horodatage de generation de cette ligne.",
}

# Couvre les 4 tables gold clusters (T002) + les 3 tables gold warehouses (T003).
# Le rule engine lit les variantes `*_rolling` (fenetre 30 j, cf.
# RECOMMENDATIONS_ROLLING_WINDOW_DAYS) ; seule la GOVERNANCE reste sur le
# snapshot `cluster_governance` (aucune variante rolling).
# Le builder ne produit que les recommandations vivantes (OPEN/ACK) et celles
# qu'il vient de basculer en RESOLVED : les lignes absentes du resultat sont donc
# des anomalies resolues lors d'un run PRECEDENT (ou portant sur un objet
# disparu), conservees `RECOMMENDATIONS_RESOLVED_RETENTION_DAYS` jours apres leur
# derniere observation puis supprimees.
RECOMMENDATIONS_SPEC = GoldAggregationSpec(
    source_tables=(
        GOLD_CLUSTER_EFFICIENCY_ROLLING,
        GOLD_CLUSTER_RELIABILITY_ROLLING,
        GOLD_CLUSTER_GOVERNANCE,
        GOLD_CLUSTER_COST_ROLLING,
        GOLD_WAREHOUSE_UTILIZATION_ROLLING,
        GOLD_WAREHOUSE_QUERY_PERFORMANCE_ROLLING,
        GOLD_WAREHOUSE_COST_ROLLING,
    ),
    target_table=GOLD_RECOMMENDATIONS,
    merge_keys=RECOMMENDATIONS_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=RECOMMENDATIONS_COLUMN_COMMENTS,
    table_comment=RECOMMENDATIONS_TABLE_COMMENT,
    absent_row_delete_guard=(
        "t.last_seen_date < "
        f"date_add(current_date(), -{RECOMMENDATIONS_RESOLVED_RETENTION_DAYS})"
    ),
)

# --- Table gold transverse predictive (T004) --------------------------------
# `forecast_daily` : projection des metriques cle via `ai_forecast` (cf.
# `pipelines.gold_dbx_compute.forecast`). Pas de watermark/fenetre
# incrementale (cf. R9 scope note) : `ai_forecast` relit l'historique complet
# des tables gold `*_daily` necessaire a la projection a chaque run.
#
# Grain : `(cloud_provider, object_type, object_id, metric_name, horizon_date)`
# (cf. `research.md` R8/`compute_datamodel.md` §4.2, moins `source_lz_id` -
# retire de toutes les specs gold compute : le mapping `workspace_id -> lz_id`
# (cf. `gold_dbx_compute.total_cost_daily`) est PARTIEL et n'est pas joint au
# grain par objet de cette table).
#
# Couvre les 5 metriques de `compute_datamapping.md` §4.2 : `cost_usd`,
# `dbu_quantity` (clusters + warehouses), `cpu_util_p95_pct` (clusters),
# `query_count`, `queue_time_p95_ms` (warehouses).
GOLD_FORECAST_DAILY = "gold_dbx_compute_forecast_daily"

FORECAST_MERGE_KEYS = (
    "cloud_provider",
    "workspace_id",
    "object_type",
    "object_id",
    "metric_name",
    "horizon_date",
)

# Fenetre (jours avant aujourd'hui) des donnees passees a `ai_forecast` en
# entrainement (`observed`, cf. `pipelines.gold_dbx_compute.forecast`). Double
# effet, par construction (un seul filtre `period_start >=`, pas deux
# mecanismes separes) : (1) borne l'historique d'entrainement a une fenetre
# fixe pour tout objet, quel que soit son age reel ; (2) un objet SANS AUCUNE
# ligne dans cette fenetre (pas d'activite recente) n'apparait plus du tout
# dans `observed` -> aucune ligne de prevision produite pour lui. Necessaire
# car les cluster_id sont tres majoritairement ephemeres (99,22 % n'ont qu'1
# seul jour d'historique reel) : sans cette borne, `ai_forecast` produit une
# ligne par jour depuis le jour APRES la derniere donnee reelle jusqu'a
# `horizon_date`, ce qui comble un historique de plusieurs annees pour un
# cluster mort depuis longtemps.
FORECAST_OBSERVED_LOOKBACK_DAYS = 14

# Horizon de projection (jours au-dela d'aujourd'hui) passe a `ai_forecast`.
# Pas de valeur imposee par les docs sources (research.md R7/compute_datamapping.md
# §4.2 ne fixent pas de duree) : 7 jours, plus court que la fenetre
# d'entrainement (`FORECAST_OBSERVED_LOOKBACK_DAYS`) pour rester sur un horizon
# de prevision resserre.
FORECAST_HORIZON_DAYS = 7

# Largeur d'intervalle de confiance passee a `ai_forecast` (`prediction_interval_width`,
# 0-1) : 0.95 = valeur par defaut native de `ai_forecast`, explicitee ici pour
# rester une donnee de configuration (pas une valeur magique dans le SQL).
FORECAST_PREDICTION_INTERVAL_WIDTH = 0.95

# Jours d'activite REELLE minimum dans la fenetre d'entrainement pour qu'un
# objet soit projete (cf. `pipelines.gold_dbx_compute.forecast._observed_sql`).
# Un objet vu 1 ou 2 jours n'a pas de serie temporelle, la "prevision"
# extrapole alors un point isole, sur un volume proportionnel au parc (99,22 %
# des `cluster_id` n'ont qu'un jour d'historique). Prolonge au grain objet
# l'exclusion des clusters JOB/PIPELINE, qui repose sur le meme constat.
#
# Seuil porte de 3 a 8 jours : STRICTEMENT SUPERIEUR a l'horizon
# (`FORECAST_HORIZON_DAYS = 7`) -- on ne projette pas plus loin qu'on n'observe.
# Contrairement au domaine usage, il n'est pas gratuit : mesure en dev sur la
# fenetre de 14 jours, la part du cout observe restant projetee tombe a 83,2 %
# (CLUSTER), 89,2 % (JOB) et 93,3 % (WAREHOUSE). C'est le prix de series
# d'entrainement plus courtes que ce qu'elles pretendent prevoir ; la somme d'un
# parc devient un minorant, ce que l'API declare.
FORECAST_MIN_OBSERVED_DAYS = 8

# Plafond de plausibilite RELATIF a la serie : une projection superieure a
# `FORECAST_MAX_OBSERVED_RATIO x` le maximum journalier observe de sa propre
# serie n'est pas publiee. Un plafond scalaire (`global_cap`) ne l'attrape pas --
# il est aveugle aux petites series qui explosent vers une valeur absurde mais
# inferieure au plafond global. Mesure en dev avant garde-fou : 867 M$/6 jours
# projetes au grain JOB pour ~4 400 $/jour observes, dont 38,9 M$/jour pour un
# seul job. Les 305 jobs divergents (5 % du parc) ne portent que 5,2 % du cout
# observe : la borne est quasi gratuite en couverture.
FORECAST_MAX_OBSERVED_RATIO = 10.0

# Suppression des previsions FUTURES qu'un run ne produit plus (objet devenu
# inactif ou passe sous `FORECAST_MIN_OBSERVED_DAYS`) : sans elle, le MERGE en
# upsert pur les laisse en table indefiniment et l'API les additionne a la
# prevision courante — une "prevision" cumulant plusieurs runs pour le meme
# jour. Contrairement aux autres garde-fous, celui-ci ne porte PAS sur
# `_generated_at` : les horizons deja passes doivent survivre (trace de ce qui
# avait ete predit), seul le futur est reconstruit a chaque run. La table est
# integralement recalculable et n'a pas de `watermark_column`, donc la source
# EST la reference complete du futur.
FORECAST_ABSENT_ROW_DELETE_GUARD = "t.horizon_date >= current_date()"

FORECAST_DAILY_TABLE_COMMENT = (
    "Projection predictive (ai_forecast) des metriques cle, clusters (hors "
    "JOB) + jobs + pipelines + warehouses : cout, DBU, utilisation CPU p95 "
    "(clusters), cout/DBU (jobs, pipelines et warehouses), volume de requetes "
    "et temps de file d'attente (warehouses). Entrainement sur les "
    f"{FORECAST_OBSERVED_LOOKBACK_DAYS} derniers jours REVOLUS (le jour en "
    "cours, partiel, est exclu), projection sur les "
    f"{FORECAST_HORIZON_DAYS} jours suivant le dernier jour observe "
    "(horizon_date). Les metriques additives (cout, DBU, volume de requetes) "
    "sont entrainees sur une serie densifiee : un jour sans ligne source vaut "
    "0, la valeur projetee est donc par jour calendaire et non par jour "
    "d'activite. Les metriques de distribution (utilisation CPU p95, temps de "
    "file p95) restent sur une serie creuse : un jour sans activite n'a pas de "
    f"percentile. Les objets ayant moins de {FORECAST_MIN_OBSERVED_DAYS} jours "
    "d'activite reelle dans la fenetre ne sont pas projetes. Une projection "
    f"superieure a {FORECAST_MAX_OBSERVED_RATIO:g} fois le maximum journalier "
    "observe de sa propre serie n'est pas publiee (100 pour cpu_util_p95_pct, "
    "plafond absolu), et upper_bound est ecretee a ce meme plafond. Les clusters "
    "JOB et PIPELINE (ephemeres) sont exclus du grain CLUSTER : leur cout/DBU "
    "est projete au grain JOB (rollup stable job_id) et au grain PIPELINE "
    "(rollup stable dlt_pipeline_id), cf. "
    "gold_dbx_compute_job_cluster_cost_daily et "
    "gold_dbx_compute_pipeline_cost_daily. "
    "Source : gold_dbx_compute_cluster_cost_daily + "
    "gold_dbx_compute_cluster_efficiency_daily + "
    "gold_dbx_compute_job_cluster_cost_daily + "
    "gold_dbx_compute_pipeline_cost_daily + "
    "gold_dbx_compute_warehouse_cost_daily + "
    "gold_dbx_compute_warehouse_query_performance_daily."
)
FORECAST_DAILY_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": "Fournisseur cloud du workspace (azure ou aws).",
    "workspace_id": "Identifiant du workspace Databricks.",
    "object_type": "Type d'objet projete (CLUSTER, JOB, PIPELINE ou WAREHOUSE).",
    "object_id": (
        "Identifiant de l'objet (cluster_id, job_id, dlt_pipeline_id ou "
        "warehouse_id selon object_type)."
    ),
    "metric_name": (
        "Metrique projetee : cost_usd/dbu_quantity/cpu_util_p95_pct "
        "(CLUSTER, hors clusters JOB), cost_usd/dbu_quantity (JOB), "
        "cost_usd/dbu_quantity (PIPELINE), "
        "cost_usd/dbu_quantity/query_count/queue_time_p95_ms (WAREHOUSE)."
    ),
    "horizon_date": "Jour projete (horizon de la prevision).",
    "predicted_value": (
        "Valeur projetee pour ce jour. Formule : sortie `{metric}_forecast` de "
        "la fonction ai_forecast, calculee sur l'historique gold quotidien de "
        "la metrique concernee. Jamais NULL, et jamais superieure a "
        f"{FORECAST_MAX_OBSERVED_RATIO:g} fois le maximum journalier observe "
        "de la serie (100 pour cpu_util_p95_pct, plafond absolu) : les lignes "
        "qui ne respectent pas ces deux bornes ne sont pas publiees."
    ),
    "lower_bound": (
        "Borne basse de l'intervalle de confiance. Formule : sortie "
        "`{metric}_lower` de ai_forecast (largeur d'intervalle : cf. "
        "FORECAST_PREDICTION_INTERVAL_WIDTH)."
    ),
    "upper_bound": (
        "Borne haute de l'intervalle de confiance. Formule : sortie "
        "`{metric}_upper` de ai_forecast (meme largeur d'intervalle que "
        "lower_bound), ECRETEE au meme plafond que predicted_value : "
        "ai_forecast rend un intervalle de plusieurs ordres de grandeur "
        "au-dessus d'une valeur projetee pourtant plausible. La valeur ecretee "
        "vaut donc exactement ce plafond, pas la sortie du modele."
    ),
    "method": "Methode de projection utilisee : toujours ai_forecast.",
    "_generated_at": "Horodatage de generation de cette ligne.",
}

# Couvre les metriques clusters hors JOB (T002), jobs (rollup job_cluster_cost_daily),
# pipelines (rollup pipeline_cost_daily, T001d) et warehouses (T003).
FORECAST_DAILY_SPEC = GoldAggregationSpec(
    source_tables=(
        GOLD_CLUSTER_COST_DAILY,
        GOLD_CLUSTER_EFFICIENCY_DAILY,
        GOLD_JOB_CLUSTER_COST_DAILY,
        GOLD_PIPELINE_COST_DAILY,
        GOLD_WAREHOUSE_COST_DAILY,
        GOLD_WAREHOUSE_QUERY_PERFORMANCE_DAILY,
    ),
    target_table=GOLD_FORECAST_DAILY,
    merge_keys=FORECAST_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=FORECAST_DAILY_COLUMN_COMMENTS,
    table_comment=FORECAST_DAILY_TABLE_COMMENT,
    absent_row_delete_guard=FORECAST_ABSENT_ROW_DELETE_GUARD,
)


# --- Tables gold depense SERVERLESS (T001d) ---------------------------------
# Angle mort de TOUS les rollups ci-dessus : le serverless ne porte ni
# `cluster_id`, ni `cluster_source`, ni ligne dans `curated_dbx_compute_clusters`
# -- les tables basees cluster l'ignorent par construction, et celles qui sont
# billing-direct ne le voient que sous l'angle de leur objet metier (un job, un
# pipeline). Toutes les mesures de cette section viennent de la FENETRE DE
# REFERENCE 2026-08-10..2026-09-09 (31 j), dev, bi-cloud sauf mention du cloud,
# prises le 2026-09-10 (cf. `specs/025-serverless-compute-page/
# T001d-baseline-measures.md`) : 380 638,71 $ de depense serverless
# (AWS 276 672,18 $, Azure 103 966,54 $), repartis sur 12 surfaces d'usage dont 4
# n'ont AUCUNE autre table gold ou apparaitre (`APP` 22 754,36 $,
# `GENIE` 18 397,47 $, `AI_ENDPOINT` 17 565,03 $, `LAKEBASE` 6 275,22 $).
# Le grain est `(surface, objet)` et non `(objet)` : la surface est ce qui donne
# un sens a `object_id`, dont le champ porteur CHANGE par surface (cf.
# `sql_helpers.serverless_object_id_expr`).
GOLD_SERVERLESS_COST_DAILY = "gold_dbx_compute_serverless_cost_daily"

# Ni `serverless_surface` ni `object_id` ne peut etre NULL, et ce n'est pas un
# choix de style : `merge_into_table` fusionne sur `<=>` NULL-SAFE, donc une cle
# NULL ne leve rien -- elle fond silencieusement tout un workspace en une ligne
# corrompue. Garanties respectivement par la branche `ELSE 'OTHER'` du CASE de
# surface et par la sentinelle `_NO_OBJECT` (33 425,57 $, 8,78 % de la depense
# bi-cloud de la fenetre de reference -- 9,50 % sur AWS seul, 6,87 % sur Azure
# seul --, portes par des surfaces sans objet listable).
SERVERLESS_COST_DAILY_MERGE_KEYS = (
    "cloud_provider",
    "workspace_id",
    "serverless_surface",
    "object_id",
    "period_start",
)

SERVERLESS_COST_DAILY_TABLE_COMMENT = (
    "FinOps serverless : cout quotidien de la depense SERVERLESS par surface "
    "d'usage (serverless_surface) et par objet (object_id). Rend visible une "
    "depense que tous les rollups bases cluster ignorent par construction, le "
    "serverless n'ayant ni cluster_id ni cluster_source ni ligne dans "
    "curated_dbx_compute_clusters. Rollup BILLING-DIRECT : agrege "
    "curated_dbx_billing_usage sur le perimetre "
    "product_features.is_serverless = true UNION les produits factures sans "
    "compute classique derriere eux (GENIE, MODEL_SERVING, VECTOR_SEARCH, "
    "LAKEBASE, NETWORKING, AI_FUNCTIONS, AI_GATEWAY, LAKEFLOW_CONNECT, "
    "SUPERVISOR_AGENT, AGENT_EVALUATION), price par "
    "curated_dbx_billing_list_prices, noms resolus depuis "
    "curated_dbx_compute_warehouses et curated_dbx_lakeflow_pipelines. Ne PAS "
    "sommer avec gold_dbx_compute_cluster_cost_daily, "
    "gold_dbx_compute_job_cluster_cost_daily, "
    "gold_dbx_compute_pipeline_cost_daily ni "
    "gold_dbx_compute_warehouse_cost_daily : cette table agrege LES MEMES "
    "lignes de facturation, vues sous l'axe de la forme de compute au lieu de "
    "l'objet metier (double comptage). Sommer les serverless_surface ENTRE "
    "ELLES est en revanche legitime et redonne la depense serverless totale : "
    "les 12 surfaces partitionnent les lignes, aucune ligne n'appartient a "
    "deux surfaces."
)
SERVERLESS_COST_DAILY_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": "Fournisseur cloud du workspace (azure ou aws).",
    "workspace_id": (
        "Identifiant du workspace Databricks. Fait partie du grain meme si la "
        "plupart des identifiants Databricks sont globalement uniques : les "
        "endpoints IA font exception (932 endpoint_id distincts pour 939 couples "
        "(workspace_id, endpoint_id) sur l'historique complet, mesure dev "
        "2026-09-10), et sans workspace_id ces homonymes fusionneraient leur "
        "cout."
    ),
    "serverless_surface": (
        "Usage derriere la depense serverless : JOB, DLT_PIPELINE, "
        "MV_ST_REFRESH (rafraichissement de vue materialisee ou de streaming "
        "table), SQL_WAREHOUSE, NOTEBOOK, APP, GENIE, AI_ENDPOINT (model "
        "serving, recherche vectorielle, AI gateway, agents), LAKEBASE, "
        "NETWORKING, PLATFORM_AUTO (optimisation predictive, monitoring de "
        "qualite, controle d'acces fin, classification de donnees) ou OTHER. "
        "Jamais NULL. Fait partie du grain. OTHER est un dispositif de "
        "VISIBILITE, pas un fourre-tout, et le controle porte sur sa "
        "COMPOSITION et non sur un montant : sur l'historique complet "
        "(2023-08-26..2026-09-09, mesure dev 2026-09-10) il ne contient que "
        "LAKEFLOW_CONNECT (9 880,03 $ AWS), SHARED_SERVERLESS_COMPUTE (90,46 $, "
        "SKU eteint depuis septembre 2024) et BASE_ENVIRONMENTS (0,07 $), soit "
        "9 970,56 $ = 0,27 % de la depense serverless de l'historique. Tout "
        "QUATRIEME produit qui y apparait doit etre classe explicitement -- y "
        "compris un produit deja connu qui REVIENT apres une interruption, "
        "comme DATA_CLASSIFICATION arrete sur AWS en janvier 2026 et toujours "
        "facture sur Azure, et y compris un produit RENOMME : PLATFORM_AUTO "
        "couvre pour cette raison LAKEHOUSE_MONITORING, ancien nom de "
        "DATA_QUALITY_MONITORING (memes SKU exactement, relais au 2026-02-06), "
        "sans quoi 3 494,32 $ d'historique tomberaient ici."
    ),
    "object_id": (
        "Identifiant de l'objet qui facture, AU SEIN de sa surface : job_id, "
        "dlt_pipeline_id, warehouse_id, notebook_id, app_id ou endpoint_id "
        "selon serverless_surface. Vaut la sentinelle '_NO_OBJECT' quand la "
        "surface n'expose aucun objet listable (GENIE, PLATFORM_AUTO, "
        "NETWORKING, OTHER : grain workspace) -- 33 425,57 $, soit 8,78 % de la "
        "depense bi-cloud de la fenetre de reference 2026-08-10..2026-09-09 "
        "(9,50 % sur AWS seul, 6,87 % sur Azure seul), mesure dev 2026-09-10. "
        "Jamais NULL : voir has_object_key pour filtrer sans comparer a la "
        "chaine."
    ),
    "period_start": "Jour agrege (grain quotidien).",
    "object_name": (
        "Nom de l'objet, jamais NULL. Formule : nom porte par la facturation "
        "(job_name, notebook_path, app_name, endpoint_name) a defaut le nom "
        "connu dans curated_dbx_compute_warehouses, a defaut celui connu dans "
        "curated_dbx_lakeflow_pipelines, a defaut l'object_id lui-meme. Les "
        "deux replis referentiels sont indispensables : la facturation ne nomme "
        "nativement ni les warehouses, ni les pipelines, ni Lakebase (0 % de "
        "leur cout, dont 165 457,41 $ pour la seule surface SQL_WAREHOUSE, "
        "fenetre de reference 2026-08-10..2026-09-09, mesure dev 2026-09-10 ; les "
        "referentiels en nomment ensuite 99,93 %). Etat connu du referentiel a la "
        "fin de la journee agregee."
    ),
    "billing_origin_product": (
        "Produit Databricks facture, tel quel, pour l'audit. Liste TRIEE ET "
        "DEDUPLIQUEE jointe par '+' quand le meme objet facture plusieurs "
        "produits le meme jour (1 148 lignes sur 109 748, fenetre de reference "
        "2026-08-10..2026-09-09 : PLATFORM_AUTO 840, AI_ENDPOINT 308) : sur les "
        "98,95 % de lignes restantes la valeur est le produit unique et un "
        "filtre d'egalite fonctionne. Une surface regroupe volontairement "
        "plusieurs produits (AI_ENDPOINT en couvre 6)."
    ),
    "performance_target": (
        "Cible de performance serverless declaree par Databricks "
        "(product_features.performance_target). Renseignee pour les seules "
        "surfaces JOB et DLT_PIPELINE (100 % de leur cout, 2 valeurs : STANDARD "
        "et PERFORMANCE_OPTIMIZED) et NULL ailleurs : un NULL signifie donc 'sans "
        "objet pour cette surface', pas 'non renseigne'. Vaut MIXED quand la "
        "meme ligne porte deux cibles dans la journee (28 lignes sur 109 748, "
        "fenetre de reference 2026-08-10..2026-09-09)."
    ),
    "budget_policy_id": (
        "Politique de budget attribuee a la depense "
        "(usage_metadata.budget_policy_id, et non usage_policy_id : ce n'est pas "
        "un alias mais un SUR-ENSEMBLE STRICT -- sur l'historique complet, "
        "188 744 lignes sur 33 879 602 ont usage_policy_id NULL alors que "
        "budget_policy_id est renseigne, 0 ligne porte l'inverse et 0 ligne ne "
        "les voit differer ; usage_policy_id est la colonne recente, la retenir "
        "perdrait silencieusement ces 188 744 attributions -- mesure dev "
        "2026-09-10). NULL quand aucune politique n'est attachee. Valeur "
        "maximale quand la ligne en porte plusieurs dans la journee (68 lignes "
        "sur 109 748)."
    ),
    "identity_principal": (
        "Responsable de la depense, au dernier etat connu de la journee. "
        "Formule : identity_metadata.run_as a defaut owned_by a defaut "
        "created_by. NULL quand la facturation ne porte aucune identite "
        "(8 605,66 $, 2,26 % de la depense bi-cloud de la fenetre de reference "
        "2026-08-10..2026-09-09, mesure dev 2026-09-10 : LAKEBASE 6 081,87 $, "
        "NETWORKING 2 518,97 $, OTHER 4,82 $). Lire identity_source AVANT de "
        "s'en servir pour refacturer : "
        "'proprietaire' et 'executant' ne sont pas la meme semantique."
    ),
    "identity_source": (
        "Champ d'ou vient identity_principal : RUN_AS (executant), OWNED_BY "
        "(proprietaire), CREATED_BY (createur) ou NONE (aucune identite "
        "facturee). Jamais NULL. Necessaire parce que le champ porteur CHANGE "
        "par surface (fenetre de reference 2026-08-10..2026-09-09, en part de "
        "cout : SQL_WAREHOUSE 100 % OWNED_BY, APP 100 % CREATED_BY, JOB/NOTEBOOK/"
        "DLT_PIPELINE/GENIE/PLATFORM_AUTO 100 % RUN_AS, AI_ENDPOINT 92,2 % "
        "CREATED_BY et 7,2 % RUN_AS). Pris sur la MEME ligne source "
        "qu'identity_principal."
    ),
    "has_custom_tags": (
        "Vrai si au moins une ligne de facturation de la journee porte au moins "
        "un tag utilisateur (custom_tags non vide) : proxy de refacturabilite. "
        "Jamais NULL. 60,3 % de la depense de la fenetre de reference "
        "2026-08-10..2026-09-09 (mesure dev 2026-09-10), de 12,0 % sur "
        "NETWORKING a 100 % sur GENIE."
    ),
    "has_object_key": (
        "Faux quand object_id vaut la sentinelle '_NO_OBJECT', c'est-a-dire "
        "quand la surface n'expose aucun objet listable et que la ligne est au "
        "grain workspace. Filtre a utiliser plutot qu'une comparaison a la "
        "chaine. Jamais NULL."
    ),
    "dbu_quantity": (
        "Volume de DBU consommes par cet objet ce jour-la. Formule : "
        "SUM(usage_quantity) restreint aux lignes usage_unit = 'DBU'. Le rapport "
        "cost_usd / dbu_quantity N'EST PAS un prix unitaire : d'une part la "
        "depense est aussi facturee en GB, HOUR et DSU (la surface NETWORKING a "
        "0 DBU pour 2 518,97 $), d'autre part le SKU GENIE_FREE_USAGE consomme "
        "des DBU GRATUITS (102 105 DBU pour 0,00 $ ; seul SKU du perimetre sans "
        "aucune ligne de prix, ce qui explique les 321 124 DBU de la surface "
        "GENIE pour 18 397,47 $ -- fenetre de reference 2026-08-10..2026-09-09, "
        "mesure dev 2026-09-10)."
    ),
    "cost_usd": (
        "Cout total en dollars de cet objet ce jour-la, toutes unites de "
        "facturation confondues (DBU, GB, HOUR, DSU). Formule : "
        "SUM(usage_quantity x effective_price)."
    ),
    "cost_usd_prev_day": (
        "Cout du jour calendaire precedent, pour comparaison. Formule : cout "
        "total (cost_usd) du meme couple (serverless_surface, object_id), "
        "calcule pour la veille. NULL quand l'objet n'a rien facture la veille."
    ),
    "cost_delta_pct": (
        "Variation du cout par rapport a la veille, en pourcentage. Formule : "
        "(cout du jour - cout de la veille) / cout de la veille x 100."
    ),
    "run_count": (
        "Nombre d'executions facturees ce jour-la. NULL -- et JAMAIS 0 -- hors "
        "surface JOB : c'est la seule surface dont la facturation porte un "
        "job_run_id, et 0 affirmerait a tort 'aucune execution' pour un "
        "warehouse ou un endpoint. Formule : nombre de job_run_id distincts du "
        "jour. Une execution a cheval sur minuit compte pour un run-jour dans "
        "chacune des deux journees : 522 executions sur 161 550 (0,32 %) sont "
        "dans ce cas sur la fenetre de reference 2026-08-10..2026-09-09, soit "
        "573 run-jours en trop sur 162 123 (mesure dev 2026-09-10)."
    ),
    "cost_per_run_histogram": (
        "Distribution du cout par execution, en comptes par tranche de dollars "
        "(array de 19 entiers : <= 0,01 $, puis doublement jusqu'a 1 310,72 $, "
        "puis une tranche au-dela). NULL comme run_count hors surface JOB. "
        "Materialisee parce qu'un percentile quotidien ne peut ni se sommer ni "
        "se moyenner : gold_dbx_compute_serverless_cost_rolling fusionne ces "
        "histogrammes tranche par tranche puis en relit les percentiles."
    ),
    "cost_rank": (
        "Classement de l'objet par cout ce jour-la (1 = le plus cher), AU SEIN "
        "de sa serverless_surface et non toutes surfaces confondues : l'IHM "
        "affiche ce rang sur une liste filtree par surface. Douze lignes du "
        "meme jour peuvent donc porter cost_rank = 1, une par surface. Formule "
        ": position de l'objet quand on trie les objets du jour de cette "
        "surface par cout decroissant."
    ),
    "is_top_cost": (
        "Vrai si l'objet fait partie des plus couteux ce jour-la dans sa "
        "surface. Formule : vrai si le classement (cost_rank) est parmi les 10 "
        "premiers. cost_rank utilise RANK() : en cas d'ex-aequo de cout a la "
        "frontiere du seuil, plus de 10 objets peuvent etre marques "
        "is_top_cost=true le meme jour (comportement voulu, pas un bug)."
    ),
    "_generated_at": "Horodatage de generation de cette ligne.",
}

# PAS de `absent_row_delete_guard` ici, contrairement a
# `WAREHOUSE_UTILIZATION_DAILY_SPEC` : ce rollup est billing-direct, donc un jour
# deja ecrit n'a aucune raison de disparaitre d'un run a l'autre (la facturation
# ne se retracte pas). Un changement de population -- par exemple une surface
# reclassee depuis OTHER -- se nettoie par le parametre de run `one_off_purge`,
# pas par un garde-fou permanent.
SERVERLESS_COST_DAILY_SPEC = GoldAggregationSpec(
    source_tables=(
        CURATED_BILLING_USAGE,
        CURATED_BILLING_LIST_PRICES,
        # Referentiels de NOM uniquement : la facturation serverless ne nomme ni
        # les warehouses ni les pipelines.
        CURATED_COMPUTE_WAREHOUSES,
        CURATED_LAKEFLOW_PIPELINES,
    ),
    target_table=GOLD_SERVERLESS_COST_DAILY,
    merge_keys=SERVERLESS_COST_DAILY_MERGE_KEYS,
    watermark_column="period_start",
    initial_mode="full",
    incremental_lookback_days=INCREMENTAL_LOOKBACK_DAYS,
    column_comments=SERVERLESS_COST_DAILY_COLUMN_COMMENTS,
    table_comment=SERVERLESS_COST_DAILY_TABLE_COMMENT,
)

GOLD_SERVERLESS_COST_ROLLING = "gold_dbx_compute_serverless_cost_rolling"

# Grain `*_rolling` : `period_start` remplace par `window_days`. La surface reste
# dans le grain, pour la meme raison que dans la table quotidienne : sans elle,
# la fenetre re-melangerait des objets de nature differente.
SERVERLESS_COST_ROLLING_MERGE_KEYS = (
    "cloud_provider",
    "workspace_id",
    "serverless_surface",
    "object_id",
    "window_days",
)

SERVERLESS_COST_ROLLING_TABLE_COMMENT = (
    "FinOps serverless, fenetres glissantes : cout et DBU cumules sur les "
    "derniers 1/7/30/90 jours (colonne window_days) 'as of' le dernier jour "
    "disponible, avec variation vs la fenetre precedente de meme longueur, "
    "percentiles du cout par execution et classement par cout au sein de "
    "chaque surface. Rollup de gold_dbx_compute_serverless_cost_daily (aucune "
    "relecture curated). Ne PAS sommer avec "
    "gold_dbx_compute_cluster_cost_rolling, "
    "gold_dbx_compute_job_cluster_cost_rolling, "
    "gold_dbx_compute_pipeline_cost_rolling ni "
    "gold_dbx_compute_warehouse_cost_rolling : memes lignes de facturation "
    "vues sous l'axe de la forme de compute (double comptage). Ni sommer "
    "plusieurs window_days entre elles (fenetres emboitees). Sommer les "
    "serverless_surface d'une MEME window_days est en revanche legitime et "
    "redonne la depense serverless totale de la fenetre."
)
SERVERLESS_COST_ROLLING_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": "Fournisseur cloud du workspace (azure ou aws).",
    "workspace_id": (
        "Identifiant du workspace Databricks (cf. table quotidienne source : "
        "les endpoint_id ne sont pas uniques entre workspaces)."
    ),
    "serverless_surface": (
        "Usage derriere la depense serverless (12 valeurs, jamais NULL), repris "
        "de la table quotidienne source. Fait partie du grain."
    ),
    "object_id": (
        "Identifiant de l'objet qui facture au sein de sa surface, ou la "
        "sentinelle '_NO_OBJECT' quand la surface est au grain workspace. "
        "Jamais NULL, repris de la table quotidienne source. Filtrer sur "
        "has_object_key plutot que comparer cette chaine technique."
    ),
    "window_days": (
        "Longueur de la fenetre glissante en jours (1, 7, 30 ou 90). 1 = "
        "equivalent du grain quotidien (un seul jour), 7/30/90 = derniers "
        "7/30/90 jours."
    ),
    "as_of_date": (
        "Dernier jour disponible dans la table quotidienne source, borne haute "
        "(incluse) de toutes les fenetres. Formule : MAX(period_start)."
    ),
    "window_start": (
        "Premier jour (inclus) de la fenetre. Formule : as_of_date - (window_days - 1)."
    ),
    "object_name": (
        "Nom de l'objet au dernier jour connu de la fenetre, jamais NULL. Un "
        "objet renomme en cours de fenetre y porte son nom le PLUS RECENT, seul "
        "nom qui permette de le retrouver tel qu'il s'appelle aujourd'hui. A "
        "defaut de nom connu, l'object_id lui-meme."
    ),
    "billing_origin_product": (
        "Produit Databricks facture, au dernier jour connu de la fenetre (cf. "
        "table quotidienne source pour la forme 'PRODUIT_A+PRODUIT_B')."
    ),
    "performance_target": (
        "Cible de performance serverless au dernier jour connu de la fenetre. "
        "NULL hors surfaces JOB et DLT_PIPELINE : 'sans objet', pas 'non "
        "renseigne'."
    ),
    "budget_policy_id": (
        "Politique de budget au dernier jour connu de la fenetre. NULL quand "
        "aucune politique n'est attachee."
    ),
    "identity_principal": (
        "Responsable de la depense au dernier jour connu de la fenetre "
        "(run_as, a defaut owned_by, a defaut created_by). NULL quand la "
        "facturation ne porte aucune identite. Lire identity_source avant de "
        "s'en servir pour refacturer."
    ),
    "identity_source": (
        "Champ d'ou vient identity_principal : RUN_AS, OWNED_BY, CREATED_BY ou "
        "NONE. Jamais NULL. Pris sur la MEME ligne quotidienne "
        "qu'identity_principal, les desynchroniser rendrait la matrice de "
        "refacturation fausse."
    ),
    "has_custom_tags": (
        "Vrai si au moins un jour de la fenetre courante porte un tag "
        "utilisateur (OU logique sur la fenetre, et non 'dernier etat connu' : "
        "la question posee est la refacturabilite de l'objet). Jamais NULL."
    ),
    "has_object_key": (
        "Faux quand object_id vaut la sentinelle '_NO_OBJECT' (surface au grain "
        "workspace). Jamais NULL."
    ),
    "dbu_quantity": (
        "Volume de DBU consommes sur la fenetre. Formule : somme des DBU "
        "quotidiens sur les window_days jours. Ne pas en deduire un prix "
        "unitaire (cf. table quotidienne source)."
    ),
    "cost_usd": (
        "Cout total en dollars sur la fenetre, toutes unites de facturation "
        "confondues. Formule : somme des couts quotidiens sur les window_days "
        "jours."
    ),
    "cost_usd_prev_window": (
        "Cout total sur la fenetre precedente de meme longueur, pour "
        "comparaison. Formule : somme des couts quotidiens sur les window_days "
        "jours qui precedent immediatement la fenetre courante. NULL -- et "
        "JAMAIS 0 -- quand cette fenetre precedente est vide : 0 affirmerait "
        "que l'objet existait et n'a rien coute, ce qui est faux d'un objet "
        "cree pendant la fenetre courante."
    ),
    "cost_delta_pct": (
        "Variation du cout vs la fenetre precedente, en pourcentage. Formule : "
        "(cout fenetre - cout fenetre precedente) / cout fenetre precedente "
        "x 100. NULL quand la fenetre precedente est vide ou nulle."
    ),
    "run_count": (
        "Nombre d'executions facturees sur la fenetre courante. NULL -- et "
        "JAMAIS 0 -- hors surface JOB ou en l'absence d'execution. Formule : "
        "somme des run_count quotidiens. C'est un compte de RUN-JOURS : une "
        "execution a cheval sur minuit compte pour 2 (522 executions sur "
        "161 550, soit 0,32 %, sur la fenetre de reference "
        "2026-08-10..2026-09-09 mesuree en dev le 2026-09-10)."
    ),
    "cost_per_run_histogram": (
        "Histogrammes quotidiens du cout par execution fusionnes tranche par "
        "tranche sur la fenetre courante (array de 19 entiers, memes tranches "
        "que la table quotidienne source). NULL -- et jamais un tableau de "
        "zeros -- en l'absence d'execution. Distribution par RUN-JOUR, meme "
        "reserve que run_count."
    ),
    "cost_per_run_p50_usd": (
        "Cout median d'une execution sur la fenetre, en dollars. Formule : "
        "percentile 50 relu de cost_per_run_histogram, JAMAIS une moyenne des "
        "medianes quotidiennes (un percentile ne se moyenne pas). Resolution "
        "bornee par la largeur des tranches de l'histogramme. NULL en "
        "l'absence d'execution."
    ),
    "cost_per_run_p95_usd": (
        "Cout d'une execution au 95e percentile sur la fenetre, en dollars. "
        "Formule : percentile 95 relu de cost_per_run_histogram."
    ),
    "cost_per_run_p99_usd": (
        "Cout d'une execution au 99e percentile sur la fenetre, en dollars. "
        "Formule : percentile 99 relu de cost_per_run_histogram. Les tranches "
        "montent jusqu'a 1 310,72 $ pour que la queue reste lisible : sur la "
        "fenetre de reference 2026-08-10..2026-09-09 (mesure dev 2026-09-10), "
        "117 run-jours depassent 50 $ et pesent 13 520,44 $. A lire par cloud : "
        "le p99 bi-cloud vaut 9,1436 $ mais 14,789 $ sur AWS seul contre "
        "2,8651 $ sur Azure."
    ),
    "cost_rank": (
        "Classement de l'objet par cout sur la fenetre (1 = le plus cher), au "
        "sein du meme couple (window_days, serverless_surface) : l'IHM affiche "
        "ce rang sur une liste filtree par surface, un rang toutes surfaces "
        "confondues y commencerait a 40. Douze lignes d'une meme fenetre "
        "peuvent donc porter cost_rank = 1, une par surface."
    ),
    "is_top_cost": (
        "Vrai si l'objet fait partie des plus couteux de la fenetre dans sa "
        "surface. Formule : vrai si cost_rank est parmi les 10 premiers."
    ),
    "_generated_at": "Horodatage de generation de cette ligne.",
}

SERVERLESS_COST_ROLLING_SPEC = GoldAggregationSpec(
    source_tables=(GOLD_SERVERLESS_COST_DAILY,),
    target_table=GOLD_SERVERLESS_COST_ROLLING,
    merge_keys=SERVERLESS_COST_ROLLING_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=SERVERLESS_COST_ROLLING_COLUMN_COMMENTS,
    table_comment=SERVERLESS_COST_ROLLING_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)


# --- Table gold gouvernance SERVERLESS (T001e) ------------------------------
# Snapshot de gouvernance de la depense serverless, meme gabarit que
# `CLUSTER_GOVERNANCE_SPEC` (pas de watermark, recalcul complet, perimetre borne,
# suppression des lignes sorties de la fenetre). Toutes les mesures de cette
# section viennent de la FENETRE DE REFERENCE 2026-06-12..2026-09-09 (90 j =
# `GOVERNANCE_ACTIVITY_WINDOW_DAYS`), dev, bi-cloud sauf mention du cloud, prises
# le 2026-09-10 (cf. `specs/025-serverless-compute-page/
# T001e-baseline-measures.md`) : 1 036 222,34 $ de depense serverless
# (aws 767 022,09 $, azure 269 200,25 $).
# La FENETRE fait partie de la mesure : sur le meme perimetre, la part de dollars
# sans proprietaire vaut 2,2 % sur 90 jours et 7,22 % sur l'historique complet
# (266 421,06 $). Chaque chiffre publie ici porte donc sa fenetre ET son cloud.
# Source = LES LIGNES DE FACTURATION et non `gold_dbx_compute_serverless_cost_daily`
# (mesure : 8 704,20 $ d'orphelins au niveau ligne contre 8 605,66 $ au grain
# jour-objet sur la meme fenetre de 31 jours -- une table de gouvernance batie sur
# le daily sous-estime structurellement les orphelins, cf. le module builder).
GOLD_SERVERLESS_GOVERNANCE = "gold_dbx_compute_serverless_governance"

# Grain plus GROSSIER que celui des deux tables de cout serverless : ni `object_id`
# ni `period_start`. Une matrice de couverture se lit par surface, et une part de
# dollars par objet-jour n'est ni sommable ni actionnable.
# `serverless_surface` est une CLE DE MERGE et `merge_into_table` fusionne sur
# `<=>` NULL-SAFE : une cle NULL ne leve rien, elle fond silencieusement tout un
# workspace en une ligne corrompue. Garantie par la branche `ELSE 'OTHER'` du CASE
# de surface ; 0 ligne du perimetre ne porte un `workspace_id` NULL (mesure sur la
# fenetre de reference).
SERVERLESS_GOVERNANCE_MERGE_KEYS = (
    "cloud_provider",
    "workspace_id",
    "serverless_surface",
)

SERVERLESS_GOVERNANCE_TABLE_COMMENT = (
    "Gouvernance de la depense SERVERLESS par surface d'usage : part de dollars "
    "refacturable (tag owner, tag centre de cout), part attribuee a une "
    "politique de budget, part rattachee a une identite, dollars sans "
    "proprietaire, dollars sans cle d'objet, et inventaire des politiques de "
    f"budget. SNAPSHOT sur les {GOVERNANCE_ACTIVITY_WINDOW_DAYS} derniers jours "
    "de facturation (colonnes window_start / window_end, portees par chaque "
    "ligne) : integralement recalcule a chaque run, les lignes sorties de la "
    "fenetre etant supprimees au run suivant. La fenetre fait partie de la "
    "mesure et n'est pas une convention : sur le meme perimetre, la part de "
    "dollars sans proprietaire vaut 2,2 % sur 90 jours et 7,22 % sur "
    "l'historique complet (mesure dev 2026-09-10). Rollup BILLING-DIRECT : "
    "agrege curated_dbx_billing_usage (perimetre serverless de "
    "gold_dbx_compute_serverless_cost_daily) price par "
    "curated_dbx_billing_list_prices, LIGNE A LIGNE et non depuis la table "
    "quotidienne -- au grain jour-objet, des lignes sans identite fusionnent "
    "avec des lignes qui en portent une et les orphelins sont sous-estimes "
    "(8 605,66 $ au lieu de 8 704,20 $ sur une meme fenetre de 31 jours). Ne PAS "
    "sommer avec gold_dbx_compute_serverless_cost_daily ni avec les rollups "
    "cluster / job / pipeline / warehouse : memes lignes de facturation, double "
    "comptage. Sommer les serverless_surface d'un MEME cloud est en revanche "
    "legitime et redonne la depense serverless de ce cloud (les surfaces "
    "partitionnent les lignes). Une seule mesure en dollars est publiee par axe "
    "de gouvernance, plus sa part en pourcentage : le complementaire se "
    "soustrait de cost_usd. L'inventaire de politiques de budget ne peut PAS "
    "porter de nom de politique : system.billing n'expose que account_prices, "
    "attributed_usage, list_prices et usage, aucune table de budget policies "
    "n'existe (verifie le 2026-09-10)."
)
SERVERLESS_GOVERNANCE_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": (
        "Fournisseur cloud du workspace (azure ou aws). A lire pour TOUTE mesure "
        "de cette table : les deux clouds n'ont ni les memes tags obligatoires "
        "ni la meme adoption des politiques de budget (couverture policy 7,6 % "
        "aws contre 29,8 % azure sur la fenetre de reference "
        "2026-06-12..2026-09-09, mesure dev 2026-09-10)."
    ),
    "workspace_id": "Identifiant du workspace Databricks. Fait partie du grain.",
    "serverless_surface": (
        "Usage derriere la depense serverless : JOB, DLT_PIPELINE, "
        "MV_ST_REFRESH, SQL_WAREHOUSE, NOTEBOOK, APP, GENIE, AI_ENDPOINT, "
        "LAKEBASE, NETWORKING, PLATFORM_AUTO ou OTHER (cf. "
        "gold_dbx_compute_serverless_cost_daily pour le detail des produits "
        "regroupes). Jamais NULL. Fait partie du grain. Toutes les surfaces ne "
        "sont pas presentes sur les deux clouds : 12 cote aws et 11 cote azure "
        "sur la fenetre de reference 2026-06-12..2026-09-09 (OTHER absent cote "
        "azure), une surface sans ligne facturee n'ayant pas de ligne ici."
    ),
    "cost_usd": (
        "Cout total en dollars de cette surface sur la fenetre "
        "(window_start..window_end), toutes unites de facturation confondues "
        "(DBU, GB, HOUR, DSU). Formule : SUM(usage_quantity x effective_price). "
        "Denominateur de toutes les parts de cette table. Reperes sur la fenetre "
        "de reference 2026-06-12..2026-09-09 (mesure dev 2026-09-10) : "
        "1 036 222,34 $ bi-cloud, dont SQL_WAREHOUSE 458 205,68 $ soit 44 % a "
        "elle seule."
    ),
    "cost_usd_with_owner_tag": (
        "Dollars de la surface portant un tag d'appartenance (cle owner, casse "
        "ignoree, valeur vide refusee). Numerateur de owner_tag_coverage_pct."
    ),
    "owner_tag_coverage_pct": (
        "Part du cout de la surface portant un tag owner, en pourcentage. "
        "3,1 % bi-cloud sur la fenetre de reference 2026-06-12..2026-09-09 "
        "(4,0 % aws / 0,6 % azure, mesure dev 2026-09-10) : la cle mesuree est "
        "QUASI AVEUGLE sur le serverless, un taux bas ici ne veut donc pas dire "
        "que la depense n'a pas de responsable connu -- lire identity_coverage_pct "
        "(97,8 %) pour cela. Angle mort connu et non corrige a dessein : la liste "
        "des orthographes acceptees est partagee avec "
        "gold_dbx_compute_cluster_governance, y ajouter une graphie changerait "
        "des chiffres de conformite deja publies par cette autre table. "
        "Candidats mesures et ecartes : aws CreatorEmail 3,7 % et CreateBy 3,2 % "
        "(tags injectes par Databricks, non choisis par les equipes), azure "
        "AppOwner 5,3 % et CyberContact 5,3 % (tags TTE deliberes, a arbitrer). "
        "NULL quand la surface n'a coute 0 $ (une part de dollars n'est pas "
        "definie sans dollars), jamais 0 dans ce cas."
    ),
    "cost_usd_with_cost_center_tag": (
        "Dollars de la surface portant un tag de centre de cout (cles "
        "cost_center / costcenter / cost-center / bu / project, casse ignoree, "
        "valeur vide refusee). Numerateur de cost_center_tag_coverage_pct."
    ),
    "cost_center_tag_coverage_pct": (
        "Part du cout de la surface portant un tag de centre de cout, en "
        "pourcentage. 19,6 % bi-cloud sur la fenetre de reference "
        "2026-06-12..2026-09-09, mais 11,5 % aws contre 42,8 % azure (mesure dev "
        "2026-09-10) : la moyenne bi-cloud ne decrit aucun des deux parcs. "
        "ATTENTION, il n'existe volontairement AUCUNE mesure de 'au moins un tag' "
        "dans cette table : sur azure la cle plateforme Environment est presente "
        "sur 100,0 % de la depense, une couverture booleenne afficherait donc "
        "0 % de non-tague alors que la meilleure cle METIER azure plafonne a "
        "60,5 % (AppName) et que AppCode tombe a 12,4 % ; cote aws, sans "
        "etiquette obligatoire equivalente, 151 409,66 $ (54,73 %) n'ont aucun "
        "tag. Seules des cles nommees sont mesurees. NULL quand la surface n'a "
        "coute 0 $."
    ),
    "cost_usd_with_budget_policy": (
        "Dollars de la surface attribues a une politique de budget "
        "(usage_metadata.budget_policy_id, et non usage_policy_id qui est la "
        "colonne recente et perdrait silencieusement 188 744 lignes "
        "d'historique, cf. gold_dbx_compute_serverless_cost_daily). Numerateur "
        "de budget_policy_coverage_pct."
    ),
    "budget_policy_coverage_pct": (
        "Part du cout de la surface attribuee a une politique de budget, en "
        "pourcentage. 13,4 % bi-cloud sur la fenetre de reference "
        "2026-06-12..2026-09-09 (7,6 % aws / 29,8 % azure, mesure dev "
        "2026-09-10). L'ecart entre surfaces et entre clouds est le fait "
        "marquant, pas la moyenne : JOB 19,6 % aws contre 67,2 % azure, "
        "DLT_PIPELINE 43,3 % / 37,0 %, NOTEBOOK 23,5 % / 40,9 %. Et le levier le "
        "plus lourd est SQL_WAREHOUSE : 458 205,68 $ (44 % du serverless "
        "bi-cloud) a 0,0 % de couverture et 0 politique distincte sur les DEUX "
        "clouds. NULL quand la surface n'a coute 0 $."
    ),
    "cost_usd_without_identity": (
        "Dollars de la surface dont la facturation ne porte AUCUNE identite : "
        "depense sans proprietaire, non refacturable en l'etat. Formule : cout "
        "des lignes ou identity_metadata.run_as, owned_by et created_by sont "
        "tous NULL. 22 464,37 $ bi-cloud sur la fenetre de reference "
        "2026-06-12..2026-09-09 (15 931,23 $ aws / 6 533,14 $ azure, mesure dev "
        "2026-09-10), concentres sur NETWORKING (orphelin integral, 4 472,67 $ "
        "sur les deux clouds) et LAKEBASE. Mesure LIGNE A LIGNE : au "
        "grain jour-objet de gold_dbx_compute_serverless_cost_daily, des lignes "
        "sans identite fusionnent avec des lignes qui en portent une et ce "
        "montant est sous-estime."
    ),
    "identity_coverage_pct": (
        "Part du cout de la surface rattachee a une identite, en pourcentage. "
        "Formule : (cost_usd - cost_usd_without_identity) / cost_usd x 100. "
        "97,8 % bi-cloud sur la fenetre de reference 2026-06-12..2026-09-09 "
        "(97,9 % aws / 97,6 % azure, mesure dev 2026-09-10). Le residu est "
        "concentre : NETWORKING 0,0 % sur les deux clouds, LAKEBASE 5,5 % aws / "
        "0,1 % azure, OTHER 0,3 % aws. Attention, AI_ENDPOINT n'est PAS a 100 % "
        "(99,6 % aws / 96,8 % azure). NULL quand la surface n'a coute 0 $."
    ),
    "cost_usd_without_object_key": (
        "Dollars de la surface que la facturation ne rattache a aucun objet "
        "listable (sentinelle _NO_OBJECT de "
        "gold_dbx_compute_serverless_cost_daily), donc connus au seul grain "
        "workspace. 79 279,45 $ bi-cloud sur la fenetre de reference "
        "2026-06-12..2026-09-09, soit 7,6 % de la depense serverless "
        "(61 846,43 $ aws / 17 433,02 $ azure, mesure dev 2026-09-10). Vaut "
        "100 % du cout des surfaces GENIE, PLATFORM_AUTO, NETWORKING et OTHER, "
        "qui n'exposent aucun objet. Mesure de gouvernance "
        "a part entiere : ces dollars sont hors de portee de toute action par "
        "objet, meme quand ils portent un tag et une identite."
    ),
    "identity_source_mix": (
        "Champs porteurs de l'identite observes sur la surface, liste TRIEE ET "
        "DEDUPLIQUEE jointe par '+' : RUN_AS (executant), OWNED_BY "
        "(proprietaire), CREATED_BY (createur), NONE (aucune identite facturee) "
        "-- par exemple NONE+OWNED_BY. Jamais NULL. Necessaire parce que le champ "
        "porteur CHANGE par surface (SQL_WAREHOUSE 100 % OWNED_BY, APP 100 % "
        "CREATED_BY, jobs et notebooks 100 % RUN_AS, en part de cout sur la "
        "fenetre de reference 2026-06-12..2026-09-09) et que 'proprietaire' et "
        "'executant' ne sont pas la meme semantique de refacturation. C'est un "
        "ENSEMBLE non pondere : le poids de la depense sans identite est dans "
        "identity_coverage_pct, pas ici."
    ),
    "budget_policy_count": (
        "Nombre de politiques de budget distinctes attachees a la depense de "
        "cette surface. Vaut 0 -- et non NULL -- quand aucune politique n'est "
        "attachee : c'est un fait mesure, pas une inconnue. Ne PAS sommer entre "
        "surfaces ou entre workspaces pour obtenir un total : une meme politique "
        "peut couvrir plusieurs surfaces. Le decompte global se rebatit en "
        "explosant budget_policy_inventory (69 politiques distinctes sur la "
        "fenetre de reference 2026-06-12..2026-09-09 : 49 aws + 20 azure, aucun "
        "recoupement entre clouds, mesure dev 2026-09-10)."
    ),
    "budget_policy_inventory": (
        "Inventaire des politiques de budget qui couvrent cette surface : "
        "tableau de (cost_usd, budget_policy_id) trie par cout DECROISSANT, "
        "ex-aequo departages par identifiant. NULL quand aucune politique n'est "
        "attachee (budget_policy_count = 0 porte deja l'information). Le cout de "
        "tri est le PREMIER champ du struct parce que le tri d'un tableau de "
        "structs compare les champs dans l'ordre de declaration. AUCUN NOM de "
        "politique n'est disponible, et ce n'est pas une omission : "
        "system.billing n'expose que account_prices, attributed_usage, "
        "list_prices et usage, il n'existe aucune table de budget policies ni en "
        "systeme ni en curated (verifie le 2026-09-10). Ne pas promettre un nom "
        "de policy cote IHM."
    ),
    "window_start": (
        "Premier jour (inclus) de la fenetre mesuree par cette ligne. Formule : "
        f"jour du run - {GOVERNANCE_ACTIVITY_WINDOW_DAYS} jours. Porte par la "
        "ligne parce qu'un snapshot survit a son run : une ligne sortie du "
        "perimetre n'est supprimee qu'apres un delai de grace, la lire avec la "
        "fenetre du run courant serait faux."
    ),
    "window_end": (
        "Dernier jour (inclus) REELLEMENT facture dans curated POUR CE CLOUD, et "
        "non la veille du run : la facturation arrive avec 3 a 8 jours de retard, "
        "et les deux clouds sont deux flux de collecte distincts. Formule : "
        "MAX(usage_date) des lignes du perimetre sur ce cloud. Un window_end "
        "nettement plus ancien qu'a l'accoutumee signale une collecte curated en "
        "retard, pas une baisse de depense."
    ),
    "_generated_at": "Horodatage de generation de cette ligne.",
}

SERVERLESS_GOVERNANCE_SPEC = GoldAggregationSpec(
    source_tables=(CURATED_BILLING_USAGE, CURATED_BILLING_LIST_PRICES),
    target_table=GOLD_SERVERLESS_GOVERNANCE,
    merge_keys=SERVERLESS_GOVERNANCE_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=SERVERLESS_GOVERNANCE_COLUMN_COMMENTS,
    table_comment=SERVERLESS_GOVERNANCE_TABLE_COMMENT,
    absent_row_delete_guard=SNAPSHOT_ABSENT_ROW_DELETE_GUARD,
)


# --- Table gold statistiques d'EXECUTION de pipeline (T001f) -----------------
# Une ligne par update Lakeflow/DLT. C'est la premiere table gold de ce plugin
# dont le grain est une EXECUTION et non un jour : elle existe parce que la
# source est PERIODISEE (une ligne par tranche d'etat) et qu'aucune agregation
# au grain update n'est possible dans l'ingestion sans casser son caractere
# fidele-source (raisonnement mesure dans le docstring de
# `pipelines.gold_dbx_compute.pipeline_update_stats`).
#
# MESURES DE CETTE SECTION : dev, prises le 2026-09-10 sur
# `system.lakeflow.pipeline_update_timeline` (la source de la curated, celle-ci
# n'existant pas encore), historique complet disponible 2025-09-08..2026-09-10
# sauf fenetre indiquee, compte aws `dbc-223d60ab-45bd`, 61 workspaces, 13 211
# pipelines, 422 167 lignes pour 412 350 updates. La source est VIVANTE : une
# remesure quelques minutes plus tard rend 412 362 updates. Les totaux cites
# sont donc des instantanes horodates, pas des invariants — les CONTROLES d'apres
# deploiement doivent comparer gold et curated (deux tables figees entre deux
# runs), jamais gold et `system.*`.
GOLD_PIPELINE_UPDATE_STATS = "gold_dbx_compute_pipeline_update_stats"

# Cle de merge VOLONTAIREMENT plus courte que le grain annonce : ni
# `workspace_id` ni `pipeline_id`, qui sont des attributs. `update_id` est
# globalement unique (412 350 ids distincts pour autant de couples
# `(workspace_id, update_id)` et autant de triplets avec `pipeline_id`) : les
# deux parents n'ajoutent aucun pouvoir discriminant, seulement un mode de
# panne — si le rattachement d'un update changeait, un MERGE sur quatre
# colonnes INSERERAIT un doublon au lieu de mettre a jour, cassant le grain qui
# est la raison d'etre de la table.
# `merge_into_table` fusionne sur `<=>` NULL-SAFE : une cle NULL ne leve rien,
# elle fond silencieusement plusieurs updates en une ligne. Aucune des deux
# colonnes n'est nullable en pratique (0 NULL sur les 422 167 lignes source), et
# `cloud_provider` est pose par la couche curated, pas par la source.
# Le `GROUP BY` du builder est EXACTEMENT cette cle : une ligne de sortie par
# cle, structurellement.
PIPELINE_UPDATE_STATS_MERGE_KEYS = (
    "cloud_provider",
    "update_id",
)

PIPELINE_UPDATE_STATS_TABLE_COMMENT = (
    "Une ligne par EXECUTION de pipeline Lakeflow/DLT (« update ») : forme de "
    "compute, etat terminal, duree horloge, declencheur, identite d'execution "
    "et cible de performance. Grain (cloud_provider, update_id) ; workspace_id "
    "et pipeline_id sont des ATTRIBUTS et non des cles (update_id est "
    "globalement unique : 412 350 ids pour autant de triplets, mesure dev "
    "2026-09-10). Source : curated_dbx_lakeflow_pipeline_update_timeline, qui "
    "est PERIODISEE — une ligne par tranche d'etat, 422 167 lignes pour 412 350 "
    "updates a la meme date. Cette table est donc le seul endroit ou le grain "
    "'execution' existe : compter les executions par COUNT(*) sur la curated "
    "sur-compte de 9 817 unites. "
    "PIEGE A CONNAITRE AVANT DE PUBLIER UN TAUX D'ECHEC : un update est une "
    "TENTATIVE, pas une demande d'execution. 412 350 updates correspondent a "
    "347 683 request_id distincts, 14 056 requetes ont ete retentees (jusqu'a "
    "14 tentatives), et le serverless retente plus que le classique (1,21 "
    "update par requete contre 1,07). Taux d'echec = result_state = 'FAILED' "
    "rapporte aux executions de la fenetre DONT L'ETAT EST CONNU : CANCELED "
    "(0,70 %) reste au denominateur, result_state NULL en est EXCLU (cf. le "
    "commentaire de cette colonne). Attention, le 2,33 % de NULL souvent cite "
    "est un taux LIGNE de la curated (9 817 / 422 167) et ne se transpose PAS "
    "ici : au grain update il vaut 0 %, car 0 update sur 412 350 n'a que des "
    "tranches sans etat. Confondre les deux est exactement le piege du COUNT(*) "
    "que cette table existe pour supprimer. Sur "
    "l'historique complet 2025-09-08..2026-09-10 : par UPDATE, serverless "
    "23,16 % contre classique 11,52 % (rapport 2,01x) ; par REQUETE, etat de la "
    "DERNIERE tentative, 7,03 % contre 5,19 % (rapport 1,35x) — la lecture par "
    "update SUR-ESTIME l'ecart serverless/classique d'un facteur 1,49x. Sur les "
    "30 derniers jours (2026-08-11..2026-09-10, fenetre posee sur "
    "update_end_time, soit le meme axe que celui que filtrera un consommateur) "
    "le rapport S'INVERSE : par update, classique 27,76 % contre serverless "
    "7,18 % ; par requete, 13,24 % contre 2,02 %. "
    "Aucun taux issu de cette table ne doit donc etre publie "
    "sans sa fenetre, et la deduplication des retentatives passe par request_id "
    "(cf. le commentaire de cette colonne, qui porte la requete). Ce qui ne "
    "s'inverse pas, c'est la duree : p50 des updates COMPLETED de 82 s en "
    "serverless contre 694 s en classique sur l'historique complet, 93 s contre "
    "846 s sur 30 jours. "
    "result_state NULL n'est PAS une anomalie (update encore en cours au moment "
    "du calcul) et n'est deliberement pas replie sur 'UNKNOWN' : un taux "
    "d'echec doit pouvoir exclure ces lignes de son denominateur. "
    f"Rafraichissement INCREMENTAL sur update_end_time (fenetre de "
    f"{INCREMENTAL_LOOKBACK_DAYS} jours), mais l'agregation lit TOUTE la "
    "curated : borner l'entree tronquerait MIN(period_start_time) des 427 "
    "updates qui changent de jour calendaire en cours de route (40 au-dela de 4 "
    "jours, un a 19 jours). Upsert pur, aucune ligne n'est jamais supprimee : la "
    "source ne conserve qu'environ un an glissant (367 jours au 2026-09-10), "
    "cette table est la memoire longue. Ne PAS sommer duration_sec avec les "
    "heures des tables *_efficiency_* (unites et perimetres differents) ; une "
    "duree d'execution n'est pas un cout, le cout reste dans "
    "gold_dbx_compute_pipeline_cost_daily."
)
PIPELINE_UPDATE_STATS_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": (
        "Fournisseur cloud du workspace (aws ou azure), pose par la couche "
        "curated et non par la system table. Fait partie du grain et de la cle "
        "de merge. ATTENTION a la portee des reperes chiffres de cette table : "
        "ils ont tous ete mesures cote AWS (compte dbc-223d60ab-45bd, "
        "2026-09-10), la partie azure etant ingeree par JDBC cross-tenant et "
        "non mesurable avant le premier run. Ne pas presumer que les ratios "
        "serverless/classique s'y transposent."
    ),
    "update_id": (
        "Identifiant de l'execution du pipeline. Grain de la table et cle de "
        "merge : globalement unique (412 350 valeurs distinctes pour autant de "
        "couples avec workspace_id, mesure dev 2026-09-10). Une execution "
        "n'est PAS une demande d'execution : les retentatives portent des "
        "update_id differents et un meme request_id (cf. request_id)."
    ),
    "workspace_id": (
        "Workspace Databricks proprietaire du pipeline. ATTRIBUT et non cle : "
        "MAX() sur les tranches de l'update, exact par mesure (0 update sur "
        "412 350 porte deux valeurs, mesure dev 2026-09-10). Jointure vers "
        "curated_dbx_access_workspaces_latest pour le nom du workspace."
    ),
    "pipeline_id": (
        "Pipeline Lakeflow/DLT execute. ATTRIBUT et non cle (MAX(), 0 update "
        "ambigu sur 412 350, mesure dev 2026-09-10). Jointure vers "
        "curated_dbx_lakeflow_pipelines "
        "pour le nom et le proprietaire. Meme espace d'identifiants que "
        "usage_metadata.dlt_pipeline_id cote facturation, mais le "
        "rapprochement n'a pas ete verifie par jointure a ce jour : le "
        "confirmer avant de publier un cout par execution."
    ),
    "compute_type": (
        "Forme de compute de l'execution : SERVERLESS_COMPUTE ou "
        "CLASSIC_COMPUTE. Formule : MAX(compute.type) sur les tranches. Jamais "
        "NULL (0 sur 422 167 lignes source, mesure dev 2026-09-10) — qualite "
        "nettement meilleure que son equivalent cote jobs, ou "
        "job_run_timeline.compute_ids est vide ou NULL sur 97,0 % des lignes "
        "(6 465 611 / 6 668 284, mesure dev 2026-09-10) et ne rend que des "
        "identifiants, pas un type. C'est le discriminant central de toute "
        "comparaison serverless / classique."
    ),
    "result_state": (
        "Etat terminal de l'execution : COMPLETED, FAILED, CANCELED, ou NULL "
        "quand l'update etait encore en cours au moment du calcul. Repartition "
        "au 2026-09-10 : 322 393 COMPLETED, 87 076 FAILED, 2 888 CANCELED, et "
        "AUCUN NULL — le 2,33 % de NULL de la curated est un taux LIGNE qui ne "
        "se transpose pas a ce grain (0 update sur 412 350 n'a que des tranches "
        "sans etat). "
        "NULL n'est PAS une anomalie pour autant, et n'est deliberement pas "
        "replie sur 'UNKNOWN' : un taux d'echec doit EXCLURE ces lignes de son "
        "denominateur. Formule : MAX(result_state), exact par MESURE et non par "
        "contrat — 9 817 des 422 167 lignes source portent result_state IS NULL "
        "(tranches intermediaires), l'etat terminal n'est porte que par UNE "
        "ligne, et 0 update sur 412 362 expose deux etats non-NULL ; MAX() "
        "ignore les NULL et rend donc cette unique valeur. SI deux etats "
        "non-NULL coexistaient un jour, MAX() en choisirait un par ordre "
        "ALPHABETIQUE, en silence (CANCELED avant COMPLETED avant FAILED). "
        "Ne jamais deriver un taux d'echec de cette colonne sans lire d'abord "
        "le commentaire de request_id : par update, l'ecart "
        "serverless/classique est sur-estime de 1,49x."
    ),
    "duration_sec": (
        "Duree HORLOGE de l'execution en secondes : "
        "unix_timestamp(MAX(period_end_time)) - "
        "unix_timestamp(MIN(period_start_time)) sur toutes les tranches. "
        "Verifiee equivalente a la somme des tranches (ecart median 0,0 s, p95 "
        "0,0 s, 0 update au-dela de 60 s sur les 9 683 updates "
        "multi-tranches) : les tranches pavent l'intervalle sans trou. La "
        "definition horloge est retenue parce qu'elle s'explique en une phrase. "
        "Coherence mesuree : 0 duree negative, 0 NULL, 248 updates a 0 s. "
        "Filtrer sur result_state = 'COMPLETED' pour toute statistique de "
        "latence : une execution echouee s'arrete plus tot et tire les "
        "quantiles vers le bas. Reperes p50 COMPLETED (dev 2026-09-10) : 82 s "
        "en serverless contre 694 s en classique sur l'historique complet, 93 s "
        "contre 846 s sur les 30 derniers jours."
    ),
    "update_start_time": (
        "Debut de l'execution : MIN(period_start_time) sur TOUTES ses tranches, "
        "y compris celles qui sont hors de la fenetre de reecriture — c'est "
        "l'unique raison pour laquelle l'agregation lit toute la curated. "
        "N'EST PAS la colonne de fenetrage de cette table (cf. "
        "update_end_time) : 427 updates (0,104 %) terminent un autre jour "
        "calendaire que celui ou ils commencent (mesure dev 2026-09-10)."
    ),
    "update_end_time": (
        "Fin de l'execution : MAX(period_end_time) sur toutes ses tranches, "
        "jamais NULL (0 NULL sur 422 167 lignes source). Colonne de WATERMARK "
        "et de FENETRAGE de cette table, et donc l'axe sur lequel la couverture "
        "est verifiee : le fenetrage se fait sur la FIN et non sur le debut, "
        "sinon un update commence avant la borne mais termine apres resterait "
        "fige dans son etat partiel (2 cas sur une fenetre de 10 jours au "
        "2026-09-10). Pour une execution encore en cours, cette valeur est la "
        "fin de la derniere tranche connue et avancera au run suivant."
    ),
    "request_id": (
        "Demande d'execution dont cette execution est une TENTATIVE. Formule : "
        "MAX(request_id), exact par mesure (0 update sur 412 350 en porte plus "
        "d'un, 0 NULL, 0 chaine vide) et globalement unique lui aussi "
        "(347 683 valeurs distinctes). C'EST LA CLE DE DEDUPLICATION DES "
        "RETENTATIVES : 412 350 updates pour 347 683 requetes, 14 056 requetes "
        "retentees, jusqu'a 14 tentatives, et le serverless retente plus "
        "(1,21 update par requete contre 1,07 en classique). Un taux d'echec "
        "par update SUR-ESTIME donc l'ecart serverless/classique d'un facteur "
        "1,49x : 23,16 % contre 11,52 % (rapport 2,01x) par update, mais "
        "7,03 % contre 5,19 % (rapport 1,35x) par requete sur l'historique "
        "complet 2025-09-08..2026-09-10 (mesures dev 2026-09-10) ; sur les 30 "
        "derniers jours le rapport s'inverse (par update : classique 27,76 % "
        "contre serverless 7,18 %). Pour raisonner par demande, garder la "
        "DERNIERE tentative : SELECT * FROM (SELECT *, row_number() OVER "
        "(PARTITION BY cloud_provider, request_id ORDER BY update_end_time "
        "DESC, update_id DESC) AS rn FROM "
        "gold_dbx_compute_pipeline_update_stats) WHERE rn = 1. Le rang n'est "
        "PAS materialise a dessein : 6 requetes etalent leurs tentatives sur "
        "10 jours ou plus (jusqu'a 49), une colonne figee deviendrait fausse "
        "en silence des que la retentative arriverait apres la sortie de la "
        "tentative precedente de la fenetre de reecriture."
    ),
    "trigger_type": (
        "Origine du declenchement de l'execution telle que publiee par la "
        "source (MAX(), 0 update ambigu sur 412 350, mesure dev 2026-09-10). "
        "A croiser avec "
        "performance_target, renseigne seulement pour les executions "
        "declenchees par une tache de job."
    ),
    "update_type": (
        "Nature de l'execution telle que publiee par la source, ex. "
        "rafraichissement normal ou complet (MAX(), 0 update ambigu). Une "
        "execution de type full refresh relit tout l'historique : ne pas "
        "melanger ses durees avec celles des rafraichissements incrementaux "
        "dans une meme moyenne."
    ),
    "run_as_user_name": (
        "Identite sous laquelle l'execution a tourne (MAX(), 0 update "
        "ambigu). NULL sur 4 886 lignes source (mesure dev 2026-09-10) : "
        "l'absence d'identite n'est pas une erreur de collecte. Colonne a "
        "traiter comme une donnee personnelle — ne jamais la recopier vers un "
        "environnement non-production."
    ),
    "performance_target": (
        "Cible de performance demandee a l'execution. Formule : "
        "MAX(trigger_details.job_task.performance_target). NULL sur 100 % des "
        "updates classiques et 39,6 % des serverless (mesure dev 2026-09-10) : "
        "ce champ n'existe que pour une execution declenchee par une tache de "
        "job. Tout indicateur construit dessus doit rapporter a la population "
        "RENSEIGNEE et non au total, sinon il mesure surtout le mode de "
        "declenchement."
    ),
    "period_count": (
        "Nombre de tranches d'etat source agregees dans cette ligne : 1 a 12, "
        "9 683 updates au-dela de 1 (2,35 %, mesure dev 2026-09-10). Colonne "
        "d'AUDIT, publiee pour verifier l'agregation sans relire la curated : "
        "SUM(period_count) de cette table doit egaler le COUNT(*) de "
        "curated_dbx_lakeflow_pipeline_update_timeline sur le meme perimetre. "
        "C'est aussi le seul COUNT(*) legitime sur cette source : compter les "
        "lignes curated pour compter des executions sur-compte de 9 817 unites."
    ),
    "_generated_at": "Horodatage de generation de cette ligne.",
}

PIPELINE_UPDATE_STATS_SPEC = GoldAggregationSpec(
    source_tables=(CURATED_LAKEFLOW_PIPELINE_UPDATE_TIMELINE,),
    target_table=GOLD_PIPELINE_UPDATE_STATS,
    merge_keys=PIPELINE_UPDATE_STATS_MERGE_KEYS,
    # Watermark sur un TIMESTAMP et non sur une colonne `period_start` de type
    # DATE comme les tables `*_daily` : `gap_scan_sql` encapsule deja la colonne
    # dans `to_date(...)`, la detection de trous reste donc journaliere, et
    # `lower_bound_predicate` compare le timestamp a un litteral DATE (minuit),
    # ce qui borne bien la fenetre au jour.
    watermark_column="update_end_time",
    initial_mode="full",
    incremental_lookback_days=INCREMENTAL_LOOKBACK_DAYS,
    column_comments=PIPELINE_UPDATE_STATS_COLUMN_COMMENTS,
    table_comment=PIPELINE_UPDATE_STATS_TABLE_COMMENT,
    # Upsert PUR, contrairement aux snapshots de gouvernance : la source ne
    # conserve qu'environ un an glissant, une suppression des lignes absentes du
    # recalcul effacerait donc l'historique que cette table est justement la
    # pour garder.
    absent_row_delete_guard=None,
)


# --- Table gold transverse cout total (DCINT-335) --------------------------
# `total_cost_daily` : cout Databricks total par workspace et par jour, deja
# deduplique entre les 5 familles de compute (cf. docstring de
# `pipelines.gold_dbx_compute.total_cost_daily`). Remplace la logique de UNION
# ALL + filtres d'exclusion jusque-la dupliquee cote consommateurs (app DCM
# `dashboard_bundle.py`).
GOLD_TOTAL_COST_DAILY = "gold_dbx_compute_total_cost_daily"

# Pas de `cluster_id`/`warehouse_id`/`job_id`/`dlt_pipeline_id`/`object_id`
# dans le grain : cette table est un TOTAL par workspace, pas un detail par
# objet (le detail reste dans les 5 tables sources). `lz_id`/`ba_name` sont
# des attributs enrichis (pas des cles de merge), via
# `dim_reference_landing_zone_dbx_workspace` + `dim_landing_zone` -- PARTIEL,
# NULL pour les workspaces sans Landing Zone/Business Application associee
# (cf. docstring du builder).
TOTAL_COST_DAILY_MERGE_KEYS = (
    "cloud_provider",
    "workspace_id",
    "period_start",
)

TOTAL_COST_DAILY_TABLE_COMMENT = (
    "Cout Databricks total par workspace et par jour, deja deduplique entre "
    "les 5 familles de compute (clusters ALL_PURPOSE, SQL Warehouses, jobs, "
    "pipelines, serverless hors job/pipeline/warehouse). Source cout : les 5 "
    "tables gold gold_dbx_compute_{cluster,warehouse,job_cluster,pipeline,"
    "serverless}_cost_daily, chacune restreinte a la tranche qu'elle possede "
    "en propre pour eviter le double comptage (cf. docstring du builder). "
    "lz_id/ba_name enrichis via dim_reference_landing_zone_dbx_workspace + "
    "dim_landing_zone, PARTIELS - NULL pour le reste, expose tel quel "
    "plutot qu'omis. Pas de detail par objet ni par famille de compute sur "
    "cette table (reste dans les 5 sources)."
)
TOTAL_COST_DAILY_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": "Fournisseur cloud du workspace (azure ou aws).",
    "workspace_id": "Identifiant du workspace Databricks.",
    "period_start": "Jour (UTC) sur lequel le cout est agrege.",
    "cost_usd": (
        "Cout total en dollars du workspace ce jour-la, tous types de "
        "compute confondus. Formule : SOMME des cost_usd des 5 tables "
        "sources, chacune restreinte a sa tranche propre (cf. docstring du "
        "builder) pour ne compter chaque dollar de facturation qu'une seule "
        "fois."
    ),
    "lz_id": (
        "Identifiant de la Landing Zone du workspace, via "
        "dim_reference_landing_zone_dbx_workspace -> dim_landing_zone "
        "(subscription_or_account_id). PARTIEL : NULL pour les workspaces "
        "sans reference ou sans Landing Zone/Business Application associee."
    ),
    "ba_name": (
        "Nom de la Business Application (BA) du workspace, meme jointure que "
        "lz_id (dim_landing_zone.business_application_name). Meme "
        "couverture partielle que lz_id : les deux viennent du meme INNER "
        "JOIN cote dim_landing_zone (cf. pipelines.gold_landing_zone.view)."
    ),
    "_generated_at": "Horodatage de generation de cette ligne.",
}

TOTAL_COST_DAILY_SPEC = GoldAggregationSpec(
    source_tables=(
        GOLD_CLUSTER_COST_DAILY,
        GOLD_WAREHOUSE_COST_DAILY,
        GOLD_JOB_CLUSTER_COST_DAILY,
        GOLD_PIPELINE_COST_DAILY,
        GOLD_SERVERLESS_COST_DAILY,
        CURATED_DBX_WORKSPACE,
        DIM_LANDING_ZONE_VIEW,
    ),
    target_table=GOLD_TOTAL_COST_DAILY,
    merge_keys=TOTAL_COST_DAILY_MERGE_KEYS,
    watermark_column="period_start",
    initial_mode="full",
    incremental_lookback_days=INCREMENTAL_LOOKBACK_DAYS,
    column_comments=TOTAL_COST_DAILY_COLUMN_COMMENTS,
    table_comment=TOTAL_COST_DAILY_TABLE_COMMENT,
)


# Registre des tables gold clusters + warehouses + transverse, keye par un
# identifiant court et stable — valeur `{{input}}` d'une iteration `for_each`
# du job (`--table` de l'entrypoint). Aucune entree existante n'est retiree/renommee
# jamais retirer/renommer celles-ci (cf. merge-strategy.md).
GOLD_SPECS: dict[str, GoldAggregationSpec] = {
    "cluster_cost_daily": CLUSTER_COST_DAILY_SPEC,
    "cluster_cost_rolling": CLUSTER_COST_ROLLING_SPEC,
    "cluster_efficiency_daily": CLUSTER_EFFICIENCY_DAILY_SPEC,
    "cluster_efficiency_rolling": CLUSTER_EFFICIENCY_ROLLING_SPEC,
    "cluster_reliability_daily": CLUSTER_RELIABILITY_DAILY_SPEC,
    "cluster_reliability_rolling": CLUSTER_RELIABILITY_ROLLING_SPEC,
    "cluster_governance": CLUSTER_GOVERNANCE_SPEC,
    "job_cluster_cost_daily": JOB_CLUSTER_COST_DAILY_SPEC,
    "job_cluster_cost_rolling": JOB_CLUSTER_COST_ROLLING_SPEC,
    "pipeline_cost_daily": PIPELINE_COST_DAILY_SPEC,
    "pipeline_cost_rolling": PIPELINE_COST_ROLLING_SPEC,
    "job_efficiency_daily": JOB_EFFICIENCY_DAILY_SPEC,
    "job_efficiency_rolling": JOB_EFFICIENCY_ROLLING_SPEC,
    "pipeline_efficiency_daily": PIPELINE_EFFICIENCY_DAILY_SPEC,
    "pipeline_efficiency_rolling": PIPELINE_EFFICIENCY_ROLLING_SPEC,
    "warehouse_cost_daily": WAREHOUSE_COST_DAILY_SPEC,
    "warehouse_cost_rolling": WAREHOUSE_COST_ROLLING_SPEC,
    "warehouse_utilization_daily": WAREHOUSE_UTILIZATION_DAILY_SPEC,
    "warehouse_utilization_rolling": WAREHOUSE_UTILIZATION_ROLLING_SPEC,
    "warehouse_query_performance_daily": WAREHOUSE_QUERY_PERFORMANCE_DAILY_SPEC,
    "warehouse_query_performance_rolling": WAREHOUSE_QUERY_PERFORMANCE_ROLLING_SPEC,
    "recommendations": RECOMMENDATIONS_SPEC,
    "forecast_daily": FORECAST_DAILY_SPEC,
    "serverless_cost_daily": SERVERLESS_COST_DAILY_SPEC,
    "serverless_cost_rolling": SERVERLESS_COST_ROLLING_SPEC,
    "serverless_governance": SERVERLESS_GOVERNANCE_SPEC,
    "pipeline_update_stats": PIPELINE_UPDATE_STATS_SPEC,
    "total_cost_daily": TOTAL_COST_DAILY_SPEC,
}

# Identifiants de tables, dans l'ordre : source de verite de la liste `inputs`
# du `for_each` cote job (garde le YAML et le code alignes).
GOLD_SPEC_KEYS = tuple(GOLD_SPECS)
