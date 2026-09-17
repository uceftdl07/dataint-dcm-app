"""Contrat d'agregation : registre des tables gold usage.

Symetrique a `pipelines.gold_dbx_compute.specs` (meme structure
`GoldAggregationSpec`) mais pour le domaine Usage Data Product. Une nouvelle table
gold s'y ajoute par une entree, sans modifier la structure existante.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pipelines.gold_dbx_usage.sql_helpers import EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS
from pipelines.system_tables.specs import (
    CURATED_ACCESS_AUDIT,
    CURATED_ACCESS_TABLE_LINEAGE,
    CURATED_BILLING_LIST_PRICES,
    CURATED_BILLING_USAGE,
    CURATED_QUERY_HISTORY,
    CURATED_UC_TABLE_OPERATIONS,
    CURATED_UC_TABLE_TAGS,
    CURATED_UC_TABLES,
    DEFAULT_CATALOG,
    DEFAULT_SCHEMA,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "CONSUMER_DAILY_MERGE_KEYS",
    "CONSUMER_DAILY_SPEC",
    "CONSUMER_DAILY_TABLE_COMMENT",
    "CRITICAL_FANOUT_THRESHOLD",
    "DEFAULT_CATALOG",
    "DEFAULT_SCHEMA",
    "FORECAST_DAILY_MERGE_KEYS",
    "FORECAST_DAILY_SPEC",
    "FORECAST_DAILY_TABLE_COMMENT",
    "FORECAST_HORIZON_DAYS",
    "FORECAST_MAX_OBSERVED_RATIO",
    "FORECAST_MIN_OBSERVED_DAYS",
    "FORECAST_OBSERVED_LOOKBACK_DAYS",
    "FORECAST_PREDICTION_INTERVAL_WIDTH",
    "GOLD_CONSUMER_DAILY",
    "GOLD_FORECAST_DAILY",
    "GOLD_RECOMMENDATIONS",
    "GOLD_SPECS",
    "GOLD_SPEC_KEYS",
    "GOLD_TABLE_CATALOG",
    "GOLD_TABLE_DAILY",
    "GOLD_TABLE_GOVERNANCE",
    "GOLD_TABLE_POPULARITY_DAILY",
    "GOLD_TABLE_QUERY_PERFORMANCE_DAILY",
    "INCREMENTAL_LOOKBACK_DAYS",
    "LATENCY_BUCKET_OVERFLOW_KEY",
    "LATENCY_BUCKET_UPPER_BOUNDS_MS",
    "RECOMMENDATIONS_MERGE_KEYS",
    "RECOMMENDATIONS_SPEC",
    "RECOMMENDATIONS_TABLE_COMMENT",
    "STALE_WRITE_LAG_HOURS",
    "TABLE_CATALOG_MERGE_KEYS",
    "TABLE_CATALOG_SPEC",
    "TABLE_CATALOG_TABLE_COMMENT",
    "TABLE_DAILY_MERGE_KEYS",
    "TABLE_DAILY_SPEC",
    "TABLE_DAILY_TABLE_COMMENT",
    "TABLE_GOVERNANCE_MERGE_KEYS",
    "TABLE_GOVERNANCE_SPEC",
    "TABLE_GOVERNANCE_TABLE_COMMENT",
    "TABLE_POPULARITY_DAILY_MERGE_KEYS",
    "TABLE_POPULARITY_DAILY_SPEC",
    "TABLE_POPULARITY_DAILY_TABLE_COMMENT",
    "TABLE_QUERY_PERFORMANCE_DAILY_MERGE_KEYS",
    "TABLE_QUERY_PERFORMANCE_DAILY_SPEC",
    "TABLE_QUERY_PERFORMANCE_DAILY_TABLE_COMMENT",
    "UNUSED_AFTER_DAYS",
    "USAGE_FAILURE_RATE_PCT_THRESHOLD",
    "USAGE_HIGH_COST_USD_THRESHOLD",
    "GoldAggregationSpec",
]


@dataclass(frozen=True)
class GoldAggregationSpec:
    """Decrit une agregation gold : plusieurs tables curated -> une table gold.

    Identique a `pipelines.gold_dbx_compute.specs.GoldAggregationSpec` : meme
    contrat, duplique plutot que partage entre domaines gold.
    `watermark_column`/`incremental_lookback_days` pilotent la fenetre de
    rafraichissement (full au 1er run, incrementale ensuite) ;
    `column_comments`/`table_comment` sont attaches a la table gold via
    `pipelines.common.writers.merge_into_table`.
    """

    source_tables: tuple[str, ...]
    target_table: str
    merge_keys: tuple[str, ...]
    watermark_column: str | None = None
    initial_mode: str = "full"
    incremental_lookback_days: int | None = None
    column_comments: Mapping[str, str] = field(default_factory=dict)
    table_comment: str = ""


# Fenetre incrementale des runs suivant le premier (meme valeur que
# `gold_dbx_compute`) : ne recalcule/upsert que `period_start >= today - N jours`.
INCREMENTAL_LOOKBACK_DAYS = 3

# Seuil "table non utilisee" pour `gold_dbx_usage_table_governance`, colocalise ici
# avec les autres constantes de seuil du domaine usage.
UNUSED_AFTER_DAYS = 90

# Seuil de fan-out aval a partir duquel une table est consideree "critique"
# (`is_critical`, cf. spec.md Acceptance Scenario 2 / contracts/gold-usage-contract.md).
CRITICAL_FANOUT_THRESHOLD = 5

# SLA de fraicheur d'ecriture (heures) utilise par `is_stale_but_consumed` :
# au-dela, une table encore activement lue (`days_since_last_read < 7`) mais
# dont la derniere ecriture depasse ce seuil est signalee comme "perimee mais
# consommee" (cf. spec.md Acceptance Scenario 2).
STALE_WRITE_LAG_HOURS = 24

# Seuils du rule engine `gold_dbx_usage_recommendations` (T004, regles
# RELIABILITY/FINOPS de `usage_datamapping.md` §4.1) : aucune valeur n'est
# fixee par les docs sources ("seuil" generique dans le tableau, ni clarifiee
# en spec.md Clarifications comme les seuils T003) -- meme convention que
# `gold_dbx_compute.specs.WAREHOUSE_FAILURE_RATE_PCT_THRESHOLD` (donnee de
# configuration documentee, pas une valeur magique dans le SQL). Valeurs
# choisies a partir de la distribution reelle en dev (dev_local,
# 2026-09-07) plutot qu'arbitrairement :
#   - failure_rate_pct : p50=0, p90=0, p99=75 sur
#     gold_dbx_usage_table_query_performance_daily (50 769 lignes) -- 5.0
#     isole ~7.4% des lignes (3 770/50 769), meme valeur que le seuil warehouse
#     compute (coherence inter-domaines).
#   - estimated_cost_usd (grain consumer/jour) : p50=0, p90=0.0045, p95=0.10,
#     p99=1.15 sur gold_dbx_usage_consumer_daily (54 213 lignes) -- 1.0 isole
#     le haut de la distribution (~1%) sans jamais flaguer un cout negligeable.
USAGE_FAILURE_RATE_PCT_THRESHOLD = 5.0
USAGE_HIGH_COST_USD_THRESHOLD = 1.0

# Bornes hautes INCLUSES (ms) des buckets de `latency_bucket_counts` sur
# `gold_dbx_usage_table_query_performance_daily`. Log-espacees, de la requete
# instantanee (10 ms) au timeout applicatif (5 min), plus un bucket de
# debordement.
#
# Raison d'etre : `percentile_approx` n'est ni sommable ni moyennable -- aucun
# P95 de periode n'est recalculable a partir de N `latency_p95_ms` quotidiens.
# Des COMPTEURS par bucket le sont, par simple somme : l'API reconstitue un P95
# sur une periode arbitraire sans rescanner `curated_dbx_query_history` (D10).
#
# Ces bornes sont un CONTRAT, pas un detail de requete : elles deviennent les
# cles du MAP ecrit en gold. Les modifier rend l'historique deja ecrit
# inadditionnable avec les nouvelles lignes -- elles vivent donc ici, jamais en
# litteral dans le SQL, et un changement impose un full-refresh de la table.
LATENCY_BUCKET_UPPER_BOUNDS_MS: tuple[int, ...] = (
    10,
    25,
    50,
    100,
    250,
    500,
    1_000,
    2_500,
    5_000,
    10_000,
    30_000,
    60_000,
    300_000,
)
# Cle du bucket de debordement (durees strictement superieures a la derniere
# borne). Non numerique a dessein : un tri de cles doit la faire ressortir comme
# non bornee, pas comme une valeur comparable aux autres.
LATENCY_BUCKET_OVERFLOW_KEY = "inf"

# --- Tables gold usage (T002) ------------------------------------------------
GOLD_TABLE_DAILY = "gold_dbx_usage_table_daily"
GOLD_TABLE_POPULARITY_DAILY = "gold_dbx_usage_table_popularity_daily"
GOLD_CONSUMER_DAILY = "gold_dbx_usage_consumer_daily"
GOLD_TABLE_QUERY_PERFORMANCE_DAILY = "gold_dbx_usage_table_query_performance_daily"

# --- Tables gold usage (T003) : registre / gouvernance ----------------------
GOLD_TABLE_CATALOG = "gold_dbx_usage_table_catalog"
GOLD_TABLE_GOVERNANCE = "gold_dbx_usage_table_governance"

# Grain registre/gouvernance (cf. contracts/gold-usage-contract.md) : snapshot
# complet, sans period_start (cf. R9/R8 repris de gold_dbx_compute.cluster_governance
# -- pas de watermark ni de fenetre incrementale).
TABLE_CATALOG_MERGE_KEYS = ("cloud_provider", "catalog", "schema", "table_name")
TABLE_GOVERNANCE_MERGE_KEYS = ("cloud_provider", "catalog", "schema", "table_name")

# Grain du fait de consommation (cf. contracts/gold-usage-contract.md).
TABLE_DAILY_MERGE_KEYS = (
    "cloud_provider",
    "catalog",
    "schema",
    "table_name",
    "consumer_id",
    "period_start",
)
TABLE_POPULARITY_DAILY_MERGE_KEYS = (
    "cloud_provider",
    "catalog",
    "schema",
    "table_name",
    "period_start",
)
CONSUMER_DAILY_MERGE_KEYS = ("cloud_provider", "consumer_id", "period_start")
TABLE_QUERY_PERFORMANCE_DAILY_MERGE_KEYS = (
    "cloud_provider",
    "catalog",
    "schema",
    "table_name",
    "period_start",
)

# Commentaires communs aux tables SNAPSHOT (pas de `period_start` -- table_catalog/
# table_governance, recalcul complet, cf. TABLE_CATALOG_SPEC/TABLE_GOVERNANCE_SPEC).
_USAGE_SNAPSHOT_COMMON_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": "Fournisseur cloud du workspace (azure ou aws).",
    "catalog": "Catalogue Unity Catalog du data product.",
    "schema": "Schema Unity Catalog du data product.",
    "table_name": "Nom de la table du data product.",
    "table_full_name": "Nom qualifie derive : concat_ws('.', catalog, schema, table_name).",
    "_generated_at": "Horodatage de generation de cette ligne.",
}
# Commentaires communs aux tables de FAIT quotidien (`period_start` en plus). Ne PAS
# reutiliser pour une table snapshot : `ALTER TABLE ... ALTER COLUMN period_start`
# echoue avec `UNRESOLVED_COLUMN` si la colonne n'existe pas.
_USAGE_DAILY_COMMON_COLUMN_COMMENTS: dict[str, str] = {
    **_USAGE_SNAPSHOT_COMMON_COLUMN_COMMENTS,
    "period_start": "Jour agrege (grain quotidien).",
}

# Meme phrase pour les 4 tables purgees hors registre : leur contrat ne promet plus un
# comportement uniquement additif. Ecrite une seule fois -- 4 formulations divergentes
# d'une meme regle sont 4 occasions de la contredire.
_EPHEMERAL_PURGE_CONTRACT = (
    "Une table EPHEMERE, dont l'audit a vu la naissance et la mort a moins de "
    f"{EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS} secondes d'intervalle, n'obtient aucune "
    "ligne : ce n'est pas un objet gouverne mais un intermediaire d'execution (table de "
    "staging creee et droppee par le meme run de job). Les lignes deja ecrites pour une "
    "telle cle sont RETIREES par un run ulterieur des que l'audit le prouve -- c'est le "
    "seul cas ou une ligne disparait de cette table."
)
TABLE_DAILY_TABLE_COMMENT = (
    "Fait de consommation quotidien par data product et consommateur — succede "
    "a gold_data_product_usage. Source : curated_dbx_access_table_lineage + "
    "curated_dbx_access_audit (getTable) + curated_dbx_query_history + "
    "curated_dbx_billing_usage/billing_list_prices + curated_dbx_uc_tables. "
    "Le grain couvre TOUT objet Unity Catalog portant un nom qualifie : tables, "
    "vues, vues materialisees, streaming tables et metric views (seuls les acces "
    "par chemin de stockage, source_type PATH, sont hors perimetre). Une lecture "
    "via une vue est comptee sur la vue ET sur la table sous-jacente (expansion "
    "de vue), les deux etant de vraies lectures : ne pas sommer les lignes de "
    "plusieurs objets d'une meme requete en esperant retrouver un compte de "
    "requetes. " + _EPHEMERAL_PURGE_CONTRACT
)
TABLE_DAILY_COLUMN_COMMENTS: dict[str, str] = {
    **_USAGE_DAILY_COMMON_COLUMN_COMMENTS,
    "usage_date": "Alias de period_start (compat historique gold_data_product_usage).",
    "consumer_id": "Identite consommatrice (created_by / user_identity / entite lineage).",
    "consumer_name": "Libelle lisible du consommateur (= consumer_id, alias UI).",
    "consumer_type": (
        "USER, SERVICE_PRINCIPAL, JOB, DASHBOARD_V3, NOTEBOOK, PIPELINE ou UNKNOWN "
        "(identite ou type d'entite non qualifiable, par exemple un entity_type NULL "
        "en amont dans le lineage). Jamais NULL en sortie."
    ),
    "request_count": "Nombre d'acces/requetes du jour pour ce couple (table, consommateur).",
    "costed_request_count": (
        "Sous-ensemble de request_count dont le cout a pu etre calcule (statement "
        "joignable a query_history ET a une ligne de facturation compute). SUM ignorant "
        "les NULL, un estimated_cost_usd dont costed_request_count < request_count est "
        "une SOUS-ESTIMATION ; costed_request_count = 0 va de pair avec un cout NULL."
    ),
    "rows_read": (
        "Lignes lues, attribuees au prorata des tables sources d'une requete. NULL "
        "(jamais 0) quand la lecture n'est pas mesurable : acces getTable de "
        "access.audit, ou evenement de lineage sans statement_id (pipelines DLT)."
    ),
    "rows_written": (
        "Lignes ecrites dans cette table (query_history.written_rows), attribuees au "
        "prorata des tables CIBLES du statement (cote target_* du lineage). NULL "
        "(jamais 0) quand le statement n'est pas joignable, c'est-a-dire quand "
        "l'evenement de lineage ne porte pas de statement_id -- cas des pipelines DLT."
    ),
    "data_read_bytes": (
        "Octets lus, attribues au prorata des tables sources d'une requete. NULL "
        "(jamais 0) quand la lecture n'est pas mesurable, meme raison que rows_read."
    ),
    "data_written_bytes": (
        "Octets ecrits dans cette table (query_history.written_bytes), attribues au "
        "prorata des tables CIBLES du statement. NULL quand le volume n'est pas "
        "joignable, meme raison que rows_written (jamais 0)."
    ),
    "duration_seconds": (
        "Temps compute cumule attribue (secondes). NULL quand le statement n'est pas "
        "joignable a query_history (jamais 0)."
    ),
    "estimated_cost_usd": (
        "Cout attribue (methode cf. cost_attribution_method). NULL quand aucun cout "
        "n'a pu etre calcule ; partiel si costed_request_count < request_count. Le "
        "partage a parts egales porte sur tous les objets sources de la requete, "
        "vues incluses : une table lue via une vue partage donc le cout avec cette "
        "vue. Le total par requete reste egal au cout de la requete (redistribution, "
        "pas duplication), mais le cout d'une table n'est pas comparable a celui "
        "qu'elle aurait si la vue n'existait pas."
    ),
    "cost_attribution_method": (
        "equal_parts_fallback : seule methode implementee aujourd'hui (repartition a "
        "parts egales du cout/duree d'une requete multi-data-product entre ses tables "
        "sources). weighted_bytes (au prorata du volume par table) n'est PAS une option "
        "disponible : ni le lineage ni query.history ne portent de volume par table "
        "source. NULL quand aucune ligne du groupe n'a de cout calcule -- la colonne "
        "decrit un calcul effectue, pas une intention. Colonne interne, non exposee en "
        "contrat API."
    ),
    "cost_basis": (
        "Seau de facturation dont le prorata de duree tire estimated_cost_usd. "
        "warehouse_prorata : facture d'un SQL warehouse, qui n'execute que des requetes "
        "-- seule base dont le prorata soit fidele. serverless_job_prorata : facture "
        "d'un job serverless, qui couvre TOUT le job (code non-SQL compris), donc "
        "l'integralite du cout du job revient a ses seuls statements SQL ; a lire comme "
        "« ce que coute la charge qui a touche cette table », pas comme le cout des "
        "requetes elles-memes. cluster_prorata : meme lecture que le job serverless, "
        "mais ne produit aucune ligne tant que query_history.compute.cluster_id reste "
        "vide (la source nomme le TYPE du compute, pas la ressource). mixed : le groupe "
        "additionne des acces de plusieurs seaux, donc des grandeurs differentes. NULL "
        "quand aucune ligne du groupe n'a de cout calcule. Les seaux sont disjoints par "
        "construction : aucune ligne de facture n'est comptee deux fois."
    ),

    "failed_access_count": "Acces refuses/en echec du jour.",
    "unknown_data_product": (
        "Vrai si (catalog, schema, table_name) n'est pas resolu dans le registre "
        "curated_dbx_uc_tables — la ligne reste presente, jamais droppee. ATTENTION : "
        "ce booleen ne dit PAS que l'objet est hors data product, il melange cette "
        "absence avec un manque de privileges du pipeline, qui est le cas majoritaire. "
        "Utiliser catalog_resolution_status pour trancher."
    ),
    "catalog_resolution_status": (
        "Desambiguise unknown_data_product : RESOLVED (objet present dans "
        "curated_dbx_uc_tables), NOT_VISIBLE_TO_PIPELINE (au moins un acces a REUSSI "
        "sur cet objet ce jour-la, il existe donc, mais le pipeline n'a pas le "
        "privilege de le voir dans system.information_schema.tables, qui filtre objet "
        "par objet), NEVER_RESOLVED (aucun acces reussi : objet probablement "
        "inexistant, ex. faute de frappe ou table supprimee). Un NOT_VISIBLE_TO_PIPELINE "
        "massif est un defaut de GRANTS a corriger cote Unity Catalog sur le principal "
        "d'ingestion, pas un defaut de pipeline : aucune requete ne peut le rattraper."
    ),
    "last_used_at": "Dernier acces du jour (horodatage).",
}

TABLE_POPULARITY_DAILY_TABLE_COMMENT = (
    "Popularite quotidienne par data product : consommateurs distincts, volume, "
    "cout, classement et delta J-1. Source : gold_dbx_usage_table_daily + "
    "curated_dbx_access_table_lineage (downstream_fanout) + curated_dbx_uc_tables/tags. "
    + _EPHEMERAL_PURGE_CONTRACT
)
TABLE_POPULARITY_DAILY_COLUMN_COMMENTS: dict[str, str] = {
    **_USAGE_DAILY_COMMON_COLUMN_COMMENTS,
    "owner": "Tag owner / table_owner du data product.",
    "domain": "Tag domaine metier du data product.",
    "distinct_consumers": "Identites consommatrices distinctes du jour.",
    "request_count": "Acces/requetes du jour, tous consommateurs confondus.",
    "rows_read": "Lignes lues, tous consommateurs confondus.",
    "data_read_bytes": "Octets lus, tous consommateurs confondus.",
    "estimated_cost_usd": "Cout attribue du jour, tous consommateurs confondus.",
    "consumers_by_type": "Repartition du nombre de consommateurs distincts par consumer_type.",
    "downstream_fanout": (
        "Nombre d'objets aval NOMMES distincts produits a partir de ce data product "
        "(COUNT(DISTINCT target_table_full_name) du lineage ou il est source ; les "
        "cibles PATH, sans nom qualifie, sont exclues). 0 est une mesure -- table lue "
        "sans rien produire en aval -- pas une absence de mesure."
    ),
    "popularity_rank": (
        "Rang du jour par request_count decroissant (1 = le plus lu), au sein d'un "
        "meme cloud_provider (partie du grain de la table)."
    ),
    "request_count_prev_day": "request_count de la veille (delta adoption).",
    "request_delta_pct": "Variation de request_count vs la veille, en pourcentage.",
}

CONSUMER_DAILY_TABLE_COMMENT = (
    "Agregat quotidien par consommateur : data products distincts, volume, cout "
    "et classement. Source : gold_dbx_usage_table_daily."
)
CONSUMER_DAILY_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": _USAGE_DAILY_COMMON_COLUMN_COMMENTS["cloud_provider"],
    "consumer_id": "Identite consommatrice.",
    "period_start": _USAGE_DAILY_COMMON_COLUMN_COMMENTS["period_start"],
    "consumer_name": "Libelle lisible du consommateur.",
    "consumer_type": "USER, SERVICE_PRINCIPAL, JOB, DASHBOARD, NOTEBOOK ou PIPELINE.",
    "distinct_data_products": "Tables distinctes (catalog, schema, table_name) consommees.",
    "request_count": "Acces/requetes du jour.",
    "rows_read": "Lignes lues cumulees du jour.",
    "data_read_bytes": "Octets lus cumules du jour.",
    "duration_seconds": "Compute cumule attribue (secondes).",
    "estimated_cost_usd": "Cout cumule attribue.",
    "consumer_rank": "Rang du jour par estimated_cost_usd decroissant.",
    "_generated_at": _USAGE_DAILY_COMMON_COLUMN_COMMENTS["_generated_at"],
}

TABLE_QUERY_PERFORMANCE_DAILY_TABLE_COMMENT = (
    "Performance d'acces quotidienne par data product : volume/echecs de "
    "requetes, latences. Source : curated_dbx_access_table_lineage "
    "(statement_id IS NOT NULL, tous entity_type confondus) + "
    "curated_dbx_query_history. " + _EPHEMERAL_PURGE_CONTRACT
)
TABLE_QUERY_PERFORMANCE_DAILY_COLUMN_COMMENTS: dict[str, str] = {
    **_USAGE_DAILY_COMMON_COLUMN_COMMENTS,
    "query_count": "Requetes distinctes lisant ce data product ce jour-la.",
    "failed_count": "Requetes distinctes FAILED ou CANCELED (jamais un compte de lignes).",
    "failure_rate_pct": (
        "failed_count / query_count * 100 -- les deux termes comptent des statements "
        "distincts, donc la valeur reste bornee a 100."
    ),
    "latency_p50_ms": "Mediane de la duree totale des requetes.",
    "latency_p95_ms": "95e percentile de la duree totale des requetes.",
    "latency_bucket_counts": (
        "Distribution des durees de requete : cle = borne haute incluse du bucket en ms "
        f"(bornes {LATENCY_BUCKET_UPPER_BOUNDS_MS}, plus "
        f"'{LATENCY_BUCKET_OVERFLOW_KEY}' au-dela), valeur = requetes distinctes de la "
        "(table, jour) tombant dans ce bucket. Additionnable entre jours, contrairement "
        "a latency_p50_ms/latency_p95_ms : c'est la seule base d'un percentile de "
        "periode. Buckets vides omis ; un statement sans total_duration_ms ne tombe dans "
        "aucun bucket, la somme des compteurs vaut donc query_count des lors que toute "
        "requete a une duree mesuree."
    ),
    "bytes_scanned": (
        "Volume total lu par les requetes touchant ce data product (volume de la "
        "requete attribue en ENTIER a chaque objet lu, sans prorata -- ne pas sommer "
        "cette colonne entre objets d'une meme requete)."
    ),
    "rows_scanned": "Lignes lues, meme regle d'attribution que bytes_scanned.",
}

TABLE_DAILY_SPEC = GoldAggregationSpec(
    source_tables=(
        CURATED_ACCESS_TABLE_LINEAGE,
        CURATED_ACCESS_AUDIT,
        CURATED_QUERY_HISTORY,
        CURATED_BILLING_USAGE,
        CURATED_BILLING_LIST_PRICES,
        CURATED_UC_TABLES,
    ),
    target_table=GOLD_TABLE_DAILY,
    merge_keys=TABLE_DAILY_MERGE_KEYS,
    watermark_column="period_start",
    incremental_lookback_days=INCREMENTAL_LOOKBACK_DAYS,
    column_comments=TABLE_DAILY_COLUMN_COMMENTS,
    table_comment=TABLE_DAILY_TABLE_COMMENT,
)

TABLE_POPULARITY_DAILY_SPEC = GoldAggregationSpec(
    source_tables=(GOLD_TABLE_DAILY, CURATED_ACCESS_TABLE_LINEAGE, CURATED_UC_TABLES),
    target_table=GOLD_TABLE_POPULARITY_DAILY,
    merge_keys=TABLE_POPULARITY_DAILY_MERGE_KEYS,
    watermark_column="period_start",
    incremental_lookback_days=INCREMENTAL_LOOKBACK_DAYS,
    column_comments=TABLE_POPULARITY_DAILY_COLUMN_COMMENTS,
    table_comment=TABLE_POPULARITY_DAILY_TABLE_COMMENT,
)

CONSUMER_DAILY_SPEC = GoldAggregationSpec(
    source_tables=(GOLD_TABLE_DAILY,),
    target_table=GOLD_CONSUMER_DAILY,
    merge_keys=CONSUMER_DAILY_MERGE_KEYS,
    watermark_column="period_start",
    incremental_lookback_days=INCREMENTAL_LOOKBACK_DAYS,
    column_comments=CONSUMER_DAILY_COLUMN_COMMENTS,
    table_comment=CONSUMER_DAILY_TABLE_COMMENT,
)

TABLE_QUERY_PERFORMANCE_DAILY_SPEC = GoldAggregationSpec(
    source_tables=(CURATED_ACCESS_TABLE_LINEAGE, CURATED_QUERY_HISTORY),
    target_table=GOLD_TABLE_QUERY_PERFORMANCE_DAILY,
    merge_keys=TABLE_QUERY_PERFORMANCE_DAILY_MERGE_KEYS,
    watermark_column="period_start",
    incremental_lookback_days=INCREMENTAL_LOOKBACK_DAYS,
    column_comments=TABLE_QUERY_PERFORMANCE_DAILY_COLUMN_COMMENTS,
    table_comment=TABLE_QUERY_PERFORMANCE_DAILY_TABLE_COMMENT,
)

# `table_catalog` (T003) : registre/fraicheur/derniere operation par data
# product. Snapshot complet (pas de watermark, meme pattern que
# `gold_dbx_compute.cluster_governance`). FR-008 : ne porte PAS
# source_lz_id/subscription_or_account_id -- aucune table gold usage n'en
# porte (la table `gold_dbx_usage_dim_workspace` initialement prevue en T003
# comme exception documentee a FR-008 a ete retiree : la resolution
# workspace_id -> LZ vit desormais uniquement dans `dim_dbx_workspace`
# (spec 020, `pipelines.gold_dbx_workspace`), deja jointe par `dim_landing_zone`
# -- redondante, cf. `specs/019-usage-data-product-gold/stories/
# T003-gold-usage-catalog-governance.md`).
TABLE_CATALOG_TABLE_COMMENT = (
    "Registre / fraicheur / derniere operation qualifiee par data product — "
    "base du cycle de vie (cf. gold_dbx_usage_table_governance). Source : "
    "curated_dbx_uc_tables + curated_dbx_uc_table_tags (pivot owner/domain/"
    "cost_center/classification/is_data_product par egalite stricte sur tag_name) + "
    "curated_dbx_uc_table_operations (derniere operation, action_name IN "
    "('createTable', 'deleteTable', 'updateTables')) + "
    "curated_dbx_access_table_lineage cote cible + gold_dbx_usage_table_daily "
    "(last_read_at). La derniere ECRITURE et la derniere OPERATION sont deux "
    "colonnes distinctes : cf. last_write_at, last_operation_at et freshness_basis. "
    "Porte aussi le cycle de vie au catalogue (lifecycle_state / is_deleted / "
    "deleted_at), derive par CORROBORATION de deux signaux : une table est dite "
    "supprimee seulement si elle est absente de curated_dbx_uc_tables ET que sa "
    "derniere operation d'audit est un deleteTable. L'absence seule ne prouve rien "
    "(privilege manquant sur le principal d'ingestion) et vaut UNKNOWN. A ce titre, "
    "la table porte aussi une ligne pour les tables supprimees, absentes du "
    "referentiel, dont les colonnes de registre sont NULL. Exception : une table "
    "EPHEMERE, dont l'audit a vu la naissance et la mort a moins de "
    f"{EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS} secondes d'intervalle, n'obtient aucune "
    "ligne -- ce n'est pas un objet gouverne mais un intermediaire d'execution (table "
    "de staging creee et droppee par le meme run de job). Une ligne d'ephemere deja "
    "ecrite est RETIREE par un run ulterieur des que l'audit le prouve : c'est le seul "
    "cas ou une ligne disparait de cette table."
)
TABLE_CATALOG_COLUMN_COMMENTS: dict[str, str] = {
    **_USAGE_SNAPSHOT_COMMON_COLUMN_COMMENTS,
    "table_type": "Type de table Unity Catalog (curated_dbx_uc_tables.table_type, passthrough).",
    "owner": "Tag propriétaire du data product (tag_name = 'owner').",
    "domain": "Tag domaine metier du data product.",
    "cost_center": "Tag centre de coût du data product (tag_name = 'cost_center').",
    "classification": "Tag de classification (sensibilite donnee) du data product.",
    "is_data_product": (
        "Vrai si un tag `tag_name = 'data_product'` existe pour cette table "
        "(presence seule, valeur du tag ignoree)."
    ),
    "created_at": "Date de creation de la table (curated_dbx_uc_tables.created).",
    "created_by": "Createur de la table (curated_dbx_uc_tables.created_by).",
    "last_write_at": (
        "Derniere ecriture de CONTENU prouvee : curated_dbx_access_table_lineage cote "
        "cible, joint a curated_dbx_query_history par statement_id et retenu si "
        "written_rows > 0 (mesure directe). Sont donc EXCLUS le MERGE qui ne matche "
        "rien, le DELETE sans effet et le CREATE d'une table vide. La cible est "
        "acceptee sans mesure quand la query history ne couvre pas le statement, cas "
        "des ecritures de PIPELINE et de JOB. Seuls les target_type porteurs de "
        "donnees comptent (TABLE, STREAMING_TABLE, MATERIALIZED_VIEW) : une VIEW "
        "apparait en cible des qu'une lecture la traverse. L'audit Unity Catalog ne "
        "contribue PAS a cette colonne -- il journalise des appels d'API, sans "
        "compteur de lignes ; voir last_operation_at pour la derniere operation quelle "
        "qu'elle soit. NULL quand aucune ecriture n'est prouvee -- notamment sur les "
        "VIEW, dont la fraicheur est celle de leurs tables sous-jacentes."
    ),
    "last_operation": (
        "action_name brut de la derniere operation (max_by(action_name, "
        "event_time)) -- 'createTable'/'deleteTable'/'updateTables', valeur "
        "brute exposee telle quelle (choix documente, cf. docstring "
        "table_catalog.py)."
    ),
    "last_operation_at": (
        "event_time de la derniere operation d'audit quelle qu'elle soit "
        "(MAX(event_time) sur les 3 action_name), createTable et deleteTable "
        "compris. DISTINCT de last_write_at, qui vient d'une autre source et "
        "n'admet qu'une ecriture prouvee : une valeur ici ne dit pas qu'une ligne a "
        "ete ecrite."
    ),
    "last_operation_by": (
        "Auteur de la derniere operation (max_by(COALESCE(user_identity.email, "
        "user_identity.subject_name), event_time)) -- email utilisateur, nom "
        "du principal de service a defaut, ou NULL si non capture."
    ),
    "last_altered_at": "Derniere alteration connue (curated_dbx_uc_tables.last_altered).",
    "last_read_at": (
        "Dernier acces en lecture connu (MAX(gold_dbx_usage_table_daily.last_used_at))."
    ),
    "freshness_basis": (
        "Signal dont freshness_lag_hours tire son anciennete. lineage_write : cible "
        "du lineage qualifiee par written_rows, seule preuve d'ecriture du modele, "
        "bornee par la retention du lineage. table_altered : repli sur last_altered_at, seul "
        "signal couvrant tout le catalogue, mais qui n'est PAS une preuve d'ecriture "
        "-- la doc Databricks le definit comme l'horodatage de derniere modification "
        "de la DEFINITION de la relation. Il peut donc se tromper dans les deux sens : "
        "trop recent quand seule la metadonnee a change (SET TBLPROPERTIES), trop "
        "ancien quand une ecriture ne l'a pas fait bouger (mesure : anterieur a une "
        "ecriture attestee par le lineage dans 44 % des cas). Sur cette base, "
        "freshness_lag_hours est une estimation et is_stale_but_consumed une "
        "heuristique. NULL quand aucun des deux signaux n'existe."
    ),
    "freshness_lag_hours": (
        "Anciennete de la derniere ecriture en heures : (unix_timestamp(now()) - "
        "unix_timestamp(COALESCE(last_write_at, last_altered_at))) / 3600. Lire "
        "freshness_basis pour savoir laquelle des deux a servi. NULL si les deux "
        "sont NULL (jamais une valeur inventee)."
    ),
    "lifecycle_state": (
        "Etat de cycle de vie au catalogue, par corroboration de deux signaux. "
        "ACTIVE : la cle est presente dans curated_dbx_uc_tables (miroir purge a "
        "chaque full load, donc une presence atteste l'existence au moment du run) "
        "-- cette presence PRIME sur tout evenement passe, une table recreee "
        "redevient donc ACTIVE. DELETED : absente du referentiel ET derniere "
        "operation d'audit = deleteTable. UNKNOWN : absente du referentiel sans "
        "preuve de suppression, cas majoritairement du a un privilege manquant sur "
        "le principal d'ingestion -- traitee comme NON supprimee. Une table ephemere "
        f"(vie auditee de moins de {EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS} secondes) "
        "n'a aucune ligne du tout : ne pas la chercher ici sous un autre etat. Age "
        "inconnu (createTable hors fenetre de retention d'audit) : la table est "
        "gardee, jamais ecartee sur un doute."
    ),
    "is_deleted": (
        "Raccourci de lifecycle_state = 'DELETED'. jamais NULL par construction : "
        "UNKNOWN vaut false, pour qu'un WHERE NOT is_deleted en aval ne filtre "
        "jamais silencieusement. Ne PAS denormaliser sur les tables de fait "
        "quotidiennes : leur MERGE incremental y figerait la valeur sur tout "
        "l'historique anterieur ; filtrer par jointure sur cette table."
    ),
    "deleted_at": (
        "last_operation_at de l'evenement deleteTable retenu, NULL des que "
        "is_deleted = false. Date l'evenement d'AUDIT, pas la disparition du "
        "referentiel : les deux peuvent differer du delai de rafraichissement de "
        "la couche curated."
    ),
}

TABLE_CATALOG_SPEC = GoldAggregationSpec(
    source_tables=(
        CURATED_UC_TABLES,
        CURATED_UC_TABLE_TAGS,
        CURATED_UC_TABLE_OPERATIONS,
        CURATED_ACCESS_TABLE_LINEAGE,
        CURATED_QUERY_HISTORY,
        GOLD_TABLE_DAILY,
    ),
    target_table=GOLD_TABLE_CATALOG,
    merge_keys=TABLE_CATALOG_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=TABLE_CATALOG_COLUMN_COMMENTS,
    table_comment=TABLE_CATALOG_TABLE_COMMENT,
)

# `table_governance` (T003) : snapshot de cycle de vie (inutilise, orphelin,
# critique) derive de `table_catalog` + `table_popularity_daily` (dernier jour
# connu, fan-out). Meme pattern non-incremental que `table_catalog`.
TABLE_GOVERNANCE_TABLE_COMMENT = (
    "Snapshot de gouvernance/cycle de vie par data product : inutilisation, "
    "orphelinat de tags, fraicheur vs consommation, criticite (fan-out), "
    "action/severite recommandees. Source : gold_dbx_usage_table_catalog + "
    "gold_dbx_usage_table_popularity_daily (dernier jour connu, downstream_fanout). "
    + _EPHEMERAL_PURGE_CONTRACT
)
TABLE_GOVERNANCE_COLUMN_COMMENTS: dict[str, str] = {
    **_USAGE_SNAPSHOT_COMMON_COLUMN_COMMENTS,
    "days_since_last_read": (
        "datediff(current_date(), last_read_at) -- NULL si jamais lu "
        "(table_catalog.last_read_at NULL), traite comme inutilise par is_unused."
    ),
    "is_unused": f"days_since_last_read IS NULL OR days_since_last_read > {UNUSED_AFTER_DAYS}.",
    "has_owner_tag": "table_catalog.owner IS NOT NULL.",
    "has_domain_tag": "table_catalog.domain IS NOT NULL.",
    "has_cost_center_tag": "table_catalog.cost_center IS NOT NULL.",
    "is_orphan": "Vrai si aucun des 3 tags owner/domain/cost_center n'est present.",
    "is_stale_but_consumed": (
        f"freshness_lag_hours > {STALE_WRITE_LAG_HOURS} AND days_since_last_read "
        "< 7 -- NULL-safe (freshness_lag_hours ou days_since_last_read NULL "
        "n'evalue jamais a vrai)."
    ),
    "downstream_fanout": (
        "downstream_fanout du dernier jour connu dans "
        "gold_dbx_usage_table_popularity_daily, COALESCE(..., 0) si jamais calcule."
    ),
    "is_critical": f"downstream_fanout >= {CRITICAL_FANOUT_THRESHOLD}.",
    "lifecycle_state": (
        "Recopie de gold_dbx_usage_table_catalog.lifecycle_state (ACTIVE / DELETED "
        "/ UNKNOWN) -- propagee par jointure a chaque recalcul, jamais figee."
    ),
    "is_deleted": (
        "Recopie de gold_dbx_usage_table_catalog.is_deleted. La ligne d'une table "
        "supprimee est CONSERVEE (auditabilite) et ses mesures brutes restent "
        "calculees : seuls recommended_action et severity sont neutralises."
    ),
    "deleted_at": "Recopie de gold_dbx_usage_table_catalog.deleted_at.",
    "recommended_action": (
        "NULL des que is_deleted (aucune action possible sur un objet qui n'existe "
        "plus au catalogue). Sinon, heuristique produit ajustable (pas une formule "
        "figee spec.md) : 'archiver' si is_unused, sinon 'documenter' si is_orphan, "
        "sinon 'surveiller' si is_stale_but_consumed, sinon NULL."
    ),
    "severity": (
        "NULL des que is_deleted, pour la meme raison que recommended_action. "
        "Sinon, heuristique produit ajustable : 'high' si is_critical AND "
        "is_unused, sinon 'medium' si is_unused OR is_orphan, sinon 'low' si "
        "is_stale_but_consumed, sinon NULL."
    ),
}

TABLE_GOVERNANCE_SPEC = GoldAggregationSpec(
    source_tables=(GOLD_TABLE_CATALOG, GOLD_TABLE_POPULARITY_DAILY),
    target_table=GOLD_TABLE_GOVERNANCE,
    merge_keys=TABLE_GOVERNANCE_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=TABLE_GOVERNANCE_COLUMN_COMMENTS,
    table_comment=TABLE_GOVERNANCE_TABLE_COMMENT,
)

# `recommendations` (T004) : fait actionnable unifie (regles de seuil sur
# governance/catalog/query_performance_daily/consumer_daily), cycle de vie
# OPEN/RESOLVED -- meme pattern que `gold_dbx_compute.recommendations`
# (`recommendation_id` stable = hash sur la cle metier + `first_seen_date`,
# PAS `generated_date` -- cf. docstring `recommendations.py` : un hash sur
# `generated_date` changerait de valeur chaque jour et romprait le
# dedoublonnage exige par l'AC "0 doublon sur re-run", ecart assume vs la
# formule litterale du spike `usage_datamapping.md` §4.1 qui utilisait
# `generated_date`).
GOLD_RECOMMENDATIONS = "gold_dbx_usage_recommendations"
RECOMMENDATIONS_MERGE_KEYS = ("recommendation_id",)

RECOMMENDATIONS_TABLE_COMMENT = (
    "Fait actionnable unifie (reco d'optimisation), data products + "
    "consommateurs (T004) : regles de seuil sur les gold governance/catalog/"
    "popularity_daily/query_performance_daily/consumer_daily, cycle de vie "
    "OPEN/RESOLVED. "
    "Source : gold_dbx_usage_table_governance + gold_dbx_usage_table_catalog "
    "+ gold_dbx_usage_table_popularity_daily "
    "+ gold_dbx_usage_table_query_performance_daily + gold_dbx_usage_consumer_daily."
)
RECOMMENDATIONS_COLUMN_COMMENTS: dict[str, str] = {
    "recommendation_id": (
        "Cle stable de la recommandation. Formule : hash du fournisseur "
        "cloud, du type d'objet, de son identifiant, de la categorie et de "
        "la date de premiere detection (pas la date du jour) -- reste "
        "identique tout au long du cycle de vie de l'anomalie."
    ),
    "cloud_provider": "Fournisseur cloud du data product ou du consommateur (azure ou aws).",
    "object_type": "Type d'objet concerne par la recommandation (DATA_PRODUCT ou CONSUMER).",
    "object_id": (
        "Identifiant de l'objet : table_full_name (DATA_PRODUCT) ou "
        "consumer_id (CONSUMER)."
    ),
    "object_name": "Nom lisible de l'objet, au dernier etat connu.",
    "category": "Categorie metier : LIFECYCLE, FRESHNESS, GOVERNANCE, RELIABILITY ou FINOPS.",
    "mode": "Mode de generation de la recommandation : toujours REACTIVE (regle de seuil).",
    "title": "Resume court de l'anomalie detectee.",
    "detail": "Contexte chiffre de l'anomalie (valeurs mesurees).",
    "recommended_action": "Action concrete proposee.",
    "estimated_savings_usd": (
        "Cout de calcul/stockage recent observe pouvant etre evite (regle "
        "LIFECYCLE inutilise uniquement -- dernier cout journalier connu du "
        "data product ; NULL pour les autres categories, aucune estimation "
        "chiffrable disponible)."
    ),
    "severity": "Niveau de priorite : LOW, MEDIUM ou HIGH.",
    "personas": "Roles concernes par cette recommandation (OWN, FIN, GOV, DE, AN).",
    "status": (
        "Etat du cycle de vie : OPEN (condition toujours vraie) ou RESOLVED "
        "(condition qui ne se declenche plus). Formule : OPEN si l'objet "
        "declenche encore la regle de cette categorie aujourd'hui ; RESOLVED "
        "si l'anomalie etait connue (presente dans l'etat precedent) mais "
        "qu'aucune regle de cette categorie ne se declenche plus pour cet objet."
    ),
    "first_seen_date": "Date de premiere detection de cette anomalie (preservee au fil des runs).",
    "last_seen_date": "Derniere date ou la condition a ete observee comme vraie.",
    "_generated_at": "Horodatage de generation de cette ligne.",
}

RECOMMENDATIONS_SPEC = GoldAggregationSpec(
    source_tables=(
        GOLD_TABLE_GOVERNANCE,
        GOLD_TABLE_CATALOG,
        GOLD_TABLE_POPULARITY_DAILY,
        GOLD_TABLE_QUERY_PERFORMANCE_DAILY,
        GOLD_CONSUMER_DAILY,
    ),
    target_table=GOLD_RECOMMENDATIONS,
    merge_keys=RECOMMENDATIONS_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=RECOMMENDATIONS_COLUMN_COMMENTS,
    table_comment=RECOMMENDATIONS_TABLE_COMMENT,
)

# `forecast_daily` (T004) : projection des metriques cle via `ai_forecast`
# (cf. `pipelines.gold_dbx_usage.forecast_daily`, meme mecanisme Statement
# Execution que `pipelines.gold_dbx_compute.forecast`, research.md R5). Pas
# de watermark/fenetre incrementale : `ai_forecast` relit l'historique complet
# de `table_popularity_daily` necessaire a la projection a chaque run.
#
# Grain : `(cloud_provider, object_type, object_id, metric_name, horizon_date)`,
# object_type toujours 'DATA_PRODUCT' (une seule source, contrairement au
# compute qui projette CLUSTER/JOB/WAREHOUSE) -- cf. contracts/gold-usage-contract.md.
GOLD_FORECAST_DAILY = "gold_dbx_usage_forecast_daily"
FORECAST_DAILY_MERGE_KEYS = (
    "cloud_provider",
    "object_type",
    "object_id",
    "metric_name",
    "horizon_date",
)

# Memes valeurs que `gold_dbx_compute.specs` (meme convention, cf. docstrings
# la-bas) : aucune duree n'est fixee par usage_datamapping.md §4.2.
FORECAST_OBSERVED_LOOKBACK_DAYS = 14
FORECAST_HORIZON_DAYS = 7
FORECAST_PREDICTION_INTERVAL_WIDTH = 0.95

# Nombre minimal de jours d'activite REELLE (lignes presentes dans
# `table_popularity_daily`, avant densification) exige pour projeter un data
# product. Une table lue 1 ou 2 fois dans la fenetre n'a pas de serie
# temporelle : la projeter revient a extrapoler une tendance depuis un point
# isole, pour un volume de lignes proportionnel au parc (l'immense majorite des
# tables d'un catalogue UC est dans ce cas). Meme raisonnement que l'exclusion
# des clusters ephemeres du grain CLUSTER dans `gold_dbx_compute.forecast`.
#
# Seuil porte de 3 a 8 jours : STRICTEMENT SUPERIEUR a l'horizon
# (`FORECAST_HORIZON_DAYS = 7`) -- on ne projette pas plus loin qu'on n'observe.
# A 3 jours, `ai_forecast` ajustait un modele explosif sur les series a
# decrochement (1, 1, 1, 5 437, 11 948...) et publiait des projections de
# plusieurs ordres de grandeur au-dessus du reel, sans lever la moindre erreur.
# Cout mesure en dev sur la fenetre de 14 jours : les tables a 3-7 jours
# d'activite ne portent que 0,9 % des requetes et 2,6 % du cout observes.
FORECAST_MIN_OBSERVED_DAYS = 8

# Plafond de plausibilite RELATIF a la serie : une projection superieure a
# `FORECAST_MAX_OBSERVED_RATIO x` le maximum journalier observe de sa propre
# serie n'est pas publiee. Un plafond scalaire (`global_cap` de `ai_forecast`)
# ne l'attrape pas -- il est aveugle aux petites series qui explosent vers une
# valeur absurde mais inferieure au plafond global. Mesure en dev : le garde-fou
# ecarte 1,7 % a 4,3 % des lignes selon l'horizon, et ramene le total projete
# de 2,9 x 10^15 a 3,4 x 10^6 requetes/jour, pour 5,4 x 10^6 observees.
FORECAST_MAX_OBSERVED_RATIO = 10.0

FORECAST_DAILY_TABLE_COMMENT = (
    "Projection predictive (ai_forecast) des 4 metriques d'adoption/FinOps "
    "par data product : request_count, distinct_consumers, estimated_cost_usd, "
    "data_read_bytes. Entrainement sur les "
    f"{FORECAST_OBSERVED_LOOKBACK_DAYS} derniers jours REVOLUS (le jour en "
    "cours, partiel, est exclu), projection sur les "
    f"{FORECAST_HORIZON_DAYS} jours qui suivent le dernier jour observe "
    "(horizon_date). Un jour sans lecture compte pour 0 dans l'entrainement "
    "(serie densifiee sur le calendrier de la fenetre) : la projection est une "
    "valeur par jour calendaire, pas par jour actif. Les tables ayant moins de "
    f"{FORECAST_MIN_OBSERVED_DAYS} jours d'activite reelle dans la fenetre ne "
    "sont pas projetees (aucune ligne). Une projection superieure a "
    f"{FORECAST_MAX_OBSERVED_RATIO:g} fois le maximum journalier observe de sa "
    "propre serie n'est pas publiee non plus. "
    "Source : gold_dbx_usage_table_popularity_daily."
)
FORECAST_DAILY_COLUMN_COMMENTS: dict[str, str] = {
    "cloud_provider": "Fournisseur cloud du data product (azure ou aws).",
    "object_type": "Type d'objet projete : toujours DATA_PRODUCT.",
    "object_id": "table_full_name du data product projete.",
    "metric_name": (
        "Metrique projetee : request_count, distinct_consumers, "
        "estimated_cost_usd ou data_read_bytes."
    ),
    "horizon_date": "Jour projete (horizon de la prevision).",
    "predicted_value": (
        "Valeur projetee pour ce jour. Formule : sortie `{metric}_forecast` de "
        "la fonction ai_forecast, calculee sur l'historique gold quotidien de "
        "la metrique concernee. Jamais NULL, et jamais superieure a "
        f"{FORECAST_MAX_OBSERVED_RATIO:g} fois le maximum journalier observe "
        "de la serie : les lignes qui ne respectent pas ces deux bornes ne "
        "sont pas publiees."
    ),
    "lower_bound": (
        "Borne basse de l'intervalle de confiance. Formule : sortie "
        "`{metric}_lower` de ai_forecast (largeur d'intervalle : cf. "
        "FORECAST_PREDICTION_INTERVAL_WIDTH)."
    ),
    "upper_bound": (
        "Borne haute de l'intervalle de confiance. Formule : sortie "
        "`{metric}_upper` de ai_forecast (meme largeur d'intervalle que "
        "lower_bound), ECRETEE au meme plafond que predicted_value "
        f"({FORECAST_MAX_OBSERVED_RATIO:g} fois le maximum journalier observe "
        "de la serie) : ai_forecast rend un intervalle de plusieurs ordres de "
        "grandeur au-dessus d'une valeur projetee pourtant plausible. La "
        "valeur ecretee vaut donc exactement ce plafond, pas la sortie du "
        "modele."
    ),
    "method": "Methode de projection utilisee : toujours ai_forecast.",
    "_generated_at": "Horodatage de generation de cette ligne.",
}

FORECAST_DAILY_SPEC = GoldAggregationSpec(
    # `table_catalog` est une source de FILTRE (exclusion des tables supprimees de
    # l'historique d'entrainement), pas de metrique : declaree ici quand meme, le
    # registre devant refleter les tables reellement lues par le SQL emis.
    source_tables=(GOLD_TABLE_POPULARITY_DAILY, GOLD_TABLE_CATALOG),
    target_table=GOLD_FORECAST_DAILY,
    merge_keys=FORECAST_DAILY_MERGE_KEYS,
    watermark_column=None,
    initial_mode="full",
    incremental_lookback_days=None,
    column_comments=FORECAST_DAILY_COLUMN_COMMENTS,
    table_comment=FORECAST_DAILY_TABLE_COMMENT,
)

# Registre de dispatch (cle courte -> spec), consomme par
# `pipelines.gold_dbx_usage.entrypoint`. T003/T004 AJOUTENT des entrees ici,
# sans modifier les entrees existantes (cf. merge-strategy.md).
GOLD_SPECS: dict[str, GoldAggregationSpec] = {
    "table_daily": TABLE_DAILY_SPEC,
    "table_popularity_daily": TABLE_POPULARITY_DAILY_SPEC,
    "consumer_daily": CONSUMER_DAILY_SPEC,
    "table_query_performance_daily": TABLE_QUERY_PERFORMANCE_DAILY_SPEC,
    "table_catalog": TABLE_CATALOG_SPEC,
    "table_governance": TABLE_GOVERNANCE_SPEC,
    "recommendations": RECOMMENDATIONS_SPEC,
    "forecast_daily": FORECAST_DAILY_SPEC,
}
GOLD_SPEC_KEYS = tuple(GOLD_SPECS)
