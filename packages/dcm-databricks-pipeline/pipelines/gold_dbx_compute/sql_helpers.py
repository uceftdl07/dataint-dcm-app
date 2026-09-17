"""Helpers SQL partages par les builders `gold_dbx_compute` (fenetre incrementale).

Purs helpers de formatage de predicats SQL (aucune dependance Spark) : chaque
builder (`cluster_cost_daily`, `cluster_efficiency_daily`,
`cluster_reliability_daily`) les utilise pour construire son `WHERE`
incremental a partir d'un `lower_bound` optionnel (`None` = lecture complete,
1er run ; une date = fenetre glissante des runs suivants).
"""

from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date


def sql_string_list(values: tuple[str, ...]) -> str:
    """Formate un tuple de chaines en liste SQL litterale : `'a', 'b'`."""
    return ", ".join(f"'{value}'" for value in values)


def tag_present_sql(tags_expr: str, tag_keys: tuple[str, ...]) -> str:
    """Predicat de presence d'un tag, INSENSIBLE A LA CASSE de la cle.

    `tags_expr` : expression `map<string, string>` (ex. `lc.tags`). `tag_keys` :
    orthographes acceptees de la cle (comparees en minuscules, espaces de bord
    ignores) — plusieurs entrees pour une meme notion (ex. `cost_center`,
    `costcenter`, `cost-center`). Un acces direct `tags['owner']` est une
    correspondance EXACTE (casse comprise) : sur un parc reel les cles sont
    saisies a la main (`Owner`, `OWNER`), d'ou la normalisation via
    `map_filter` + `lower(trim(k))`.

    Une cle de valeur vide (`''`) ne compte PAS comme renseignee
    (`nullif(trim(v), '')`). `COALESCE(..., false)` : `tags` NULL (aucun tag)
    vaut `false`, jamais NULL (`size(NULL)` renvoie NULL en Spark 3).
    """
    if not tag_keys:
        raise ValueError("tag_keys must not be empty")
    keys_sql = sql_string_list(tuple(key.lower() for key in tag_keys))
    return (
        f"COALESCE(size(map_filter({tags_expr}, (k, v) -> "
        f"lower(trim(k)) IN ({keys_sql}) AND nullif(trim(v), '') IS NOT NULL)) > 0, false)"
    )


def rolling_windows_array_sql(windows: tuple[int, ...]) -> str:
    """Formate un tuple d'entiers en litteral `array(...)` SQL : `array(1, 7, 30, 90)`.

    Utilise par les builders `*_rolling` pour materialiser une ligne par
    fenetre glissante (`window_days`) via `explode(...)` : chaque objet
    (cluster/warehouse/job) est agrege sur chacune des fenetres configurees
    (`ROLLING_WINDOWS`) a partir de sa table `*_daily` gold, sans relire la
    couche curated.
    """
    return "array(" + ", ".join(str(window) for window in windows) + ")"


def lower_bound_predicate(column: str, lower_bound: date | None) -> str:
    """Predicat `AND col >= DATE '...'` (chaine vide si pas de fenetre).

    `None` => full (tout l'historique curated disponible, 1er run) ; une date
    borne la lecture curated a la fenetre incrementale (runs suivants, cf.
    `pipelines.gold_dbx_compute.specs.INCREMENTAL_LOOKBACK_DAYS`).
    """
    if lower_bound is None:
        return ""
    return f"AND {column} >= DATE '{lower_bound.isoformat()}'"


# --- Produit d'origine de la ligne de facturation (`billing_origin_product`) --
# `usage_metadata.cluster_id` et `usage_metadata.dlt_pipeline_id` ne sont PAS
# reserves au compute qui porte ce nom : un service manage (inference, fonctions
# d'IA, base managee, recherche vectorielle, ingestion Lakeflow Connect)
# facture son propre cout en le rattachant a l'objet APPELANT via ces memes
# champs. Un rollup qui filtre sur la seule presence de l'id agrege donc du cout
# qui n'est pas le sien, sans que rien ne leve d'erreur.
# `billing_origin_product` est le seul discriminant porte par la ligne de
# facturation elle-meme.
#
# LISTE BLANCHE (`IN (...)`) et non liste noire (`NOT IN ('MODEL_SERVING',
# 'AI_FUNCTIONS')`), pour trois raisons :
#   1. Databricks AJOUTE des produits, et une liste noire les fait entrer
#      silencieusement. Mesure dev du 2026-09-10 sur l'historique complet :
#      `AI_FUNCTIONS` n'apparait qu'au 2025-11-07 et `DATABASE` au 2025-09-09 --
#      deux produits qu'une liste noire ecrite en 2025-08 aurait laisses entrer
#      sans un seul signal. Une liste blanche les laisse dehors jusqu'a une
#      decision explicite : le defaut penche du cote du sous-comptage visible
#      (un produit absent de la page) plutot que du sur-comptage invisible.
#   2. Le sur-comptage est le faux positif COUTEUX cote FinOps : compter les DBU
#      d'un appel d'inference comme du cout de cluster fait proposer le
#      rightsizing d'un cluster dont le cout n'est pas son compute. L'erreur
#      inverse (un produit legitime hors liste) est bornee et auditable par la
#      requete de controle ci-dessous.
#   3. C'est la convention deja en place dans ces builders : `cluster_type_case_expr`
#      et `compute_kind_case_expr` enumerent les valeurs connues et replient tout
#      le reste sur `OTHER`, que `cluster_cost_daily` exclut ensuite
#      (`WHERE cluster_type <> 'OTHER'`). Une liste noire introduirait la
#      convention inverse dans la meme requete.
#
# Verifie AVANT d'ecrire ce filtre (mesure dev 2026-09-10, historique complet
# depuis 2023-08-26) : aucune ligne ne porte `billing_origin_product` NULL dans
# les deux perimetres, donc l'`IN` n'ecarte rien par effet de bord d'un NULL.
#
# Requete de controle, a rejouer quand un produit manque a une page ou qu'un
# cout inattendu y apparait -- elle liste ce que le filtre laisse dehors :
#   SELECT billing_origin_product, COUNT(*), MIN(usage_date), MAX(usage_date)
#   FROM <curated_dbx_billing_usage>
#   WHERE usage_metadata.cluster_id IS NOT NULL      -- ou dlt_pipeline_id
#   GROUP BY 1 ORDER BY 2 DESC

# Produits dont le cout facture EST du cout de cluster (`cluster_cost_daily`).
# Les 5 produits mesures dans ce perimetre sont ces 3 + `AI_FUNCTIONS` et
# `MODEL_SERVING`. Ce que le filtre retire de la table gold : 791,02 $ sur 97
# clusters (`AI_FUNCTIONS` 567,34 $ / 55 clusters, `MODEL_SERVING` 223,68 $ / 42
# clusters), du 2025-10-28 au 2026-09-09. Le reste de ces deux produits
# (681,04 $ + 15 208,15 $) porte des `cluster_id` absents de
# `curated_dbx_compute_clusters`, deja exclus par `WHERE cluster_type <>
# 'OTHER'` : c'est ce repli qui masquait le defaut, il ne couvrait que la partie
# des endpoints inconnus du referentiel cluster.
BILLING_PRODUCTS_CLUSTER_COMPUTE: tuple[str, ...] = ("JOBS", "ALL_PURPOSE", "DLT")

# Produits dont le cout facture EST du cout de pipeline DLT/Lakeflow
# (`pipeline_cost_daily`). Ce perimetre est le plus contamine des deux : sur
# l'historique complet, 10 972 ids non-DLT pour 37 100,58 $ portaient un
# `dlt_pipeline_id` (`SQL` 10 499 ids / 22 674,71 $ -- des requetes SQL, pas des
# pipelines ; `LAKEFLOW_CONNECT` 49 / 9 873,47 $ ; `DATABASE` 293 / 2 614,01 $ ;
# `VECTOR_SEARCH` 130 / 1 938,16 $ ; `AI_FUNCTIONS` 1 / 0,23 $), contre 9 298
# pipelines DLT reels pour 347 264,22 $.
#
# ARBITRAGE A CONNAITRE : `LAKEFLOW_CONNECT` designe de VRAIS pipelines
# d'ingestion manages (49 ids, 9 873,47 $, 2025-02-12..2026-03-18), pas un cout
# rattache a un appelant. Ils sont exclus ici parce que la page et les
# `compute_kind` de `pipeline_cost_daily` decrivent le cout DLT, et qu'un
# pipeline d'ingestion manage n'a ni cluster ni la meme unite d'oeuvre. Si le
# metier veut les suivre sur cette page, le changement tient en une ligne :
# ajouter `"LAKEFLOW_CONNECT"` ici (et corriger les commentaires de colonne de
# `specs.py`) -- pas retirer le filtre.
BILLING_PRODUCTS_DLT_PIPELINE: tuple[str, ...] = ("DLT",)


def billing_origin_product_predicate(products: tuple[str, ...]) -> str:
    """Predicat `billing_origin_product IN ('A', 'B')` (liste blanche).

    `products` vide leve : `IN ()` est une erreur de syntaxe Spark, mais SURTOUT
    une liste blanche vide viderait silencieusement la table gold si la
    generation du predicat etait rendue conditionnelle un jour. Le fail-fast est
    ici, pas dans les builders.
    """
    if not products:
        raise ValueError("products must not be empty")
    return f"billing_origin_product IN ({sql_string_list(products)})"


# Categories de `cluster_type` (derive de `cluster_source`, cf.
# `cluster_type_case_expr`). Constantes partagees plutot que litteraux repetes
# dans chaque builder pour eviter toute derive entre modules.
CLUSTER_TYPE_ALL_PURPOSE = "ALL_PURPOSE"
CLUSTER_TYPE_JOB = "JOB"
CLUSTER_TYPE_PIPELINE = "PIPELINE"
CLUSTER_TYPE_OTHER = "OTHER"


def cluster_type_case_expr(cluster_source_column: str) -> str:
    """CASE SQL mappant `cluster_source` (brut) vers `cluster_type` (categorie).

    `system.compute.clusters` n'expose aucun champ "cluster type" (All-Purpose
    vs Job) dedie : c'est `cluster_source` qui porte cette notion. Mapping
    (aligne sur les onglets "All-purpose compute"/"Job compute" de l'UI
    Databricks) :
      - `JOB` -> `JOB` (cluster ephemere, recree a chaque execution).
      - `UI`/`API` -> `ALL_PURPOSE` (cluster persistant). `API` est regroupe
        avec `UI` par convention observee (un cluster vraiment ephemere pour
        un job reste tague `JOB`, jamais `API`) - pas garanti par une doc
        officielle Databricks au niveau du champ, a re-verifier si le
        comportement source change.
      - `PIPELINE`/`PIPELINE_MAINTENANCE` -> `PIPELINE` (cluster DLT/Lakeflow).
      - toute autre valeur -> `OTHER` (jamais un NULL implicite, qui se
        confondrait avec une jointure ratee).
    """
    return (
        "CASE "
        f"WHEN {cluster_source_column} = 'JOB' THEN '{CLUSTER_TYPE_JOB}' "
        f"WHEN {cluster_source_column} IN ('UI', 'API') THEN '{CLUSTER_TYPE_ALL_PURPOSE}' "
        f"WHEN {cluster_source_column} IN ('PIPELINE', 'PIPELINE_MAINTENANCE') "
        f"THEN '{CLUSTER_TYPE_PIPELINE}' "
        f"ELSE '{CLUSTER_TYPE_OTHER}' END"
    )


# Forme de compute derriere une ligne de facturation DLT (cf.
# `compute_kind_case_expr`). Deux valeurs, jamais NULL : la page "DLT clusters"
# de l'IHM filtre `CLASSIC`, un NULL y serait un pipeline invisible.
COMPUTE_KIND_CLASSIC = "CLASSIC"
COMPUTE_KIND_SERVERLESS = "SERVERLESS"


def compute_kind_case_expr(cluster_id_column: str) -> str:
    """CASE SQL derivant `compute_kind` (`CLASSIC`/`SERVERLESS`) d'une ligne DLT.

    Le rollup cout des pipelines est BILLING-DIRECT
    (`usage_metadata.dlt_pipeline_id IS NOT NULL`) et ne porte donc aucun
    `cluster_type` : ce CASE est le seul discriminant disponible entre un
    pipeline execute sur des clusters DLT classiques et un pipeline serverless.

    `cluster_id IS NOT NULL` n'est pas une heuristique mais un proxy EXACT du
    cluster DLT, mesure en dev le 2026-09-09 : les 6 375 clusters ephemeres
    portes par les lignes DLT facturees ont TOUS `cluster_source = 'PIPELINE'`
    (100 %), aucun absent de `curated_dbx_compute_clusters` -- soit exactement
    ce que `cluster_type_case_expr` replie en `cluster_type = 'PIPELINE'`
    (`PIPELINE_MAINTENANCE` compris). Une ligne DLT sans `cluster_id` n'a donc
    pas de cluster du tout : c'est du serverless.

    Bascule vers le champ OFFICIEL `product_features.is_serverless` envisagee
    (recommandee par la story) puis REJETEE SUR MESURE le 2026-09-10, sur
    l'historique complet et les deux clouds (2 033 499 lignes DLT,
    2024-02-13..2026-09-09) : l'equivalence annoncee "parfaite" ne l'est pas --
    1 discordance, et c'est le champ officiel qui se trompe (aws, 2026-07-31,
    workspace 66097812060322, sku_name
    `ENTERPRISE_JOBS_SERVERLESS_COMPUTE_EUROPE_FRANKFURT` : `cluster_id` NULL
    donc serverless, mais `is_serverless` NULL). Comme `compute_kind` est une
    CLE DE MERGE ecrite avec un `ELSE`, la bascule n'aurait pas produit une cle
    NULL reperable mais une ligne serverless etiquetee `CLASSIC` en silence.
    Verrouille par
    `test_compute_kind_case_expr_stays_on_cluster_id_not_is_serverless` ; detail
    dans `specs/025-serverless-compute-page/T001g-baseline-measures.md` 4.3.

    A re-verifier si Databricks se met a facturer un cluster DLT classique sans
    renseigner `usage_metadata.cluster_id` : le controle est le comptage de
    `cluster_source` distincts derriere les `cluster_id` des lignes DLT.
    """
    return (
        f"CASE WHEN {cluster_id_column} IS NOT NULL THEN '{COMPUTE_KIND_CLASSIC}' "
        f"ELSE '{COMPUTE_KIND_SERVERLESS}' END"
    )


# --- Histogrammes a buckets fixes (percentiles fusionnables sur fenetres) ----
# Les percentiles quotidiens (`percentile_approx`) ne sont ni sommables ni
# moyennables : on ne peut pas recalculer un p95 sur 30 jours a partir de 30
# p95 quotidiens. Les builders `*_daily` materialisent donc une distribution a
# buckets fixes (comptes par tranche, `array<bigint>`), que les builders
# `*_rolling` somment element par element sur la fenetre (`sum_histograms_sql`)
# puis reconvertissent en percentile (`percentile_from_histogram_sql`). La
# resolution du percentile est bornee par la largeur des buckets (approxime).

# Utilisation CPU/memoire (%) : bornes hautes tous les 5 % de 5 a 100, plus un
# bucket overflow (> 100 %). 21 buckets.
HISTOGRAM_UTILIZATION_EDGES: tuple[float, ...] = tuple(float(x) for x in range(5, 101, 5))

# Latence / temps d'attente des requetes (ms) : bornes quasi-logarithmiques
# (doublement) de 50 ms a ~410 s, plus un bucket overflow. 15 buckets.
HISTOGRAM_LATENCY_MS_EDGES: tuple[float, ...] = (
    50.0,
    100.0,
    200.0,
    400.0,
    800.0,
    1600.0,
    3200.0,
    6400.0,
    12800.0,
    25600.0,
    51200.0,
    102400.0,
    204800.0,
    409600.0,
)


# Cout d'une execution serverless ($) : bornes quasi-logarithmiques
# (doublement) de 0,01 $ a 1 310,72 $, plus un bucket overflow. 19 buckets.
#
# Bornes calees sur la distribution MESUREE (dev, 2026-09-10, fenetre de
# reference 2026-08-10..2026-09-09, bi-cloud, cout par (run, JOUR) de la surface
# JOB -- 162 123 run-jours) :
#   - 18 489 run-jours (11,4 %) coutent <= 0,01 $ : la premiere borne est bien
#     placee, elle isole le bruit sans ecraser le reste.
#   - p50 0,1261 $ / p95 1,0446 $ / p99 9,1436 $ bi-cloud ; AWS SEUL p95
#     1,4897 $ / p99 14,789 $ contre 0,8226 $ / 2,8651 $ sur Azure -- la queue
#     est un phenomene AWS, et c'est pourquoi toute mesure de percentile publiee
#     ici precise son cloud. Le coeur de la distribution tombe dans les buckets
#     4 a 11.
#   - 117 run-jours depassent 50 $ et pesent 13 520,44 $ : NE PAS s'arreter a
#     ~50 $, ils finiraient dans un overflow non borne et rendraient p99 comme
#     max illisibles. Max mesure 1 137,99 $ (AWS), sous la derniere borne : le
#     bucket overflow est vide (0 run-jour), ce qui est le controle a rejouer.
#     ATTENTION, une execution ENTIERE re-sommee a cheval sur minuit atteint
#     1 345,12 $ (AWS) et DEPASSERAIT la derniere borne : l'histogramme est au
#     grain run-JOUR et ne peut pas la voir, cf. `serverless_cost_rolling`.
HISTOGRAM_COST_PER_RUN_EDGES: tuple[float, ...] = (
    0.01,
    0.02,
    0.04,
    0.08,
    0.16,
    0.32,
    0.64,
    1.28,
    2.56,
    5.12,
    10.24,
    20.48,
    40.96,
    81.92,
    163.84,
    327.68,
    655.36,
    1310.72,
)


def histogram_bucket_count(edges: tuple[float, ...]) -> int:
    """Nombre de buckets pour des bornes `edges` : `len(edges) + 1` (overflow)."""
    return len(edges) + 1


def histogram_representatives(edges: tuple[float, ...]) -> tuple[float, ...]:
    """Valeur representative de chaque bucket (milieu de tranche).

    Bucket 0 = `edges[0] / 2` ; bucket k = milieu de `(edges[k-1], edges[k]]` ;
    bucket overflow = `edges[-1]` (borne haute, estimation conservatrice).
    Longueur = `len(edges) + 1`. Utilisee par `percentile_from_histogram_sql`
    pour convertir un rang en valeur.
    """
    reps = [edges[0] / 2]
    reps.extend((lo + hi) / 2 for lo, hi in pairwise(edges))
    reps.append(edges[-1])
    return tuple(reps)


def histogram_from_edges_sql(value_expr: str, edges: tuple[float, ...]) -> str:
    """`array(...)` de comptes par bucket -- agregat, a placer dans un `GROUP BY`.

    Buckets a bornes hautes croissantes `edges` : bucket 0 = valeurs
    `<= edges[0]` ; bucket k = `edges[k-1] < v <= edges[k]` ; dernier bucket =
    overflow (`v > edges[-1]`). Les valeurs `NULL` sont exclues (aucun bucket).
    Longueur du tableau = `len(edges) + 1`. Materialise une distribution
    sommable, base des percentiles recalcules sur fenetre glissante.
    """
    parts = [f"SUM(CASE WHEN {value_expr} <= {edges[0]} THEN 1 ELSE 0 END)"]
    parts.extend(
        f"SUM(CASE WHEN {value_expr} > {lo} AND {value_expr} <= {hi} THEN 1 ELSE 0 END)"
        for lo, hi in pairwise(edges)
    )
    parts.append(f"SUM(CASE WHEN {value_expr} > {edges[-1]} THEN 1 ELSE 0 END)")
    return "array(" + ", ".join(parts) + ")"


def sum_histograms_sql(histogram_column: str, num_buckets: int) -> str:
    """Somme element par element des histogrammes d'un groupe -- agregat `GROUP BY`.

    `transform(sequence(...), i -> aggregate(collect_list(hist), ...))` :
    additionne le bucket i de tous les histogrammes quotidiens de la fenetre.
    Renvoie un `array<bigint>` de longueur `num_buckets`. A utiliser dans le
    `GROUP BY` d'un builder `*_rolling`.
    """
    return (
        f"transform(sequence(0, {num_buckets - 1}), "
        f"i -> aggregate(collect_list({histogram_column}), CAST(0 AS BIGINT), "
        f"(acc, h) -> acc + h[i]))"
    )


def percentile_from_histogram_sql(
    histogram_column: str, edges: tuple[float, ...], probability: float
) -> str:
    """Percentile approxime a partir d'un histogramme (comptes + bornes `edges`).

    Renvoie la valeur representative du premier bucket dont le cumul atteint
    `probability * total`, ou `NULL` si l'histogramme est vide. `edges` doit
    etre le meme jeu de bornes que celui passe a `histogram_from_edges_sql`.
    Approximation : resolution bornee par la largeur des buckets.
    """
    reps = histogram_representatives(edges)
    reps_sql = "array(" + ", ".join(str(r) for r in reps) + ")"
    total = f"aggregate({histogram_column}, CAST(0 AS BIGINT), (a, x) -> a + x)"
    # Index 0-base du premier bucket dont le cumul inclusif atteint le rang cible.
    idx = (
        f"size(filter(transform(sequence(1, {len(reps)}), "
        f"k -> aggregate(slice({histogram_column}, 1, k), CAST(0 AS BIGINT), (a, x) -> a + x)), "
        f"c -> c < {probability} * {total}))"
    )
    return f"CASE WHEN {total} = 0 THEN NULL ELSE {reps_sql}[{idx}] END"


# --- Depense SERVERLESS : perimetre, surface, cle d'objet, identite (T001d) ---
# Le serverless ne porte NI `cluster_id`, NI `cluster_source`, NI ligne dans
# `curated_dbx_compute_clusters` : tous les rollups bases cluster l'ignorent par
# construction. La facturation est la seule source ou il existe, d'ou ces
# helpers, partages par les tables serverless (`serverless_cost_daily`,
# `serverless_cost_rolling`, et le snapshot de gouvernance a venir) plutot que
# recopies dans chacune.

# Produits factures SANS `product_features.is_serverless = true` mais qui n'ont
# pourtant aucun compute classique derriere eux (services manages : il n'y a pas
# de cluster a provisionner, donc rien a marquer serverless). Sans cette union,
# la page perdrait des surfaces entieres.
# Mesure dev 2026-09-10 (fenetre de reference 2026-08-10..2026-09-09, bi-cloud,
# curated) : sans cette union, 44 423,98 $ sur 380 638,71 $ (11,7 %) seraient
# perdus, car non marques `is_serverless = true` -- GENIE 18 397,47 $,
# AI_ENDPOINT 17 420,85 $, LAKEBASE 6 081,87 $, NETWORKING 2 518,97 $,
# LAKEFLOW_CONNECT (surface `OTHER`) 4,82 $.
# LISTE BLANCHE, meme raison que `BILLING_PRODUCTS_CLUSTER_COMPUTE` : Databricks
# AJOUTE des produits (`AI_FUNCTIONS` apparait au 2025-11-07, `DATABASE` au
# 2025-09-09 sur l'historique complet) et une liste noire les ferait entrer sans
# un seul signal. Un produit manquant se voit ici : son cout tombe dans
# `serverless_surface = 'OTHER'`, dont le controle est documente avec
# `serverless_surface_case_expr`.
SERVERLESS_SCOPE_PRODUCTS: tuple[str, ...] = (
    "GENIE",
    "MODEL_SERVING",
    "VECTOR_SEARCH",
    "LAKEBASE",
    "NETWORKING",
    "AI_FUNCTIONS",
    "AI_GATEWAY",
    "LAKEFLOW_CONNECT",
    "SUPERVISOR_AGENT",
    "AGENT_EVALUATION",
)


def serverless_scope_predicate() -> str:
    """Perimetre serverless : `is_serverless = true` UNION les produits manages.

    A placer directement apres un `WHERE ` indente a 8 espaces (l'indentation
    de continuation est deja dans la chaine, alignee sous `product_features`).

    `product_features.is_serverless` seul ne suffit pas : les services manages
    (Genie, endpoints d'inference, Lakebase, networking) ne le renseignent pas
    alors qu'aucun cluster ne tourne derriere eux, cf.
    `SERVERLESS_SCOPE_PRODUCTS`.
    """
    products_sql = sql_string_list(SERVERLESS_SCOPE_PRODUCTS)
    return (
        "(product_features.is_serverless = true\n"
        f"               OR billing_origin_product IN ({products_sql}))"
    )


# Valeur de `serverless_surface` portant les executions de jobs : SEULE surface
# ou une notion d'"execution" existe (`usage_metadata.job_run_id`), donc seule
# ou `run_count` et le cout par run sont definis. Ailleurs la metrique n'est pas
# nulle, elle n'a pas de sens -- d'ou NULL et jamais 0 (cf.
# `serverless_cost_daily`).
SERVERLESS_SURFACE_JOB = "JOB"

# Repli EXPLICITE du CASE de surface : un produit facture non classe y tombe et
# devient visible, au lieu d'etre absorbe dans une surface existante.
SERVERLESS_SURFACE_OTHER = "OTHER"

# Les 12 valeurs produites par `serverless_surface_case_expr`, dans l'ordre du
# CASE. Source de verite pour les tests (le CASE est ecrit tel quel, cf.
# docstring) et pour l'IHM. AJOUTER une valeur ici en meme temps que la branche.
SERVERLESS_SURFACES: tuple[str, ...] = (
    "JOB",
    "DLT_PIPELINE",
    "MV_ST_REFRESH",
    "SQL_WAREHOUSE",
    "NOTEBOOK",
    "APP",
    "GENIE",
    "AI_ENDPOINT",
    "LAKEBASE",
    "NETWORKING",
    "PLATFORM_AUTO",
    SERVERLESS_SURFACE_OTHER,
)


def serverless_surface_case_expr() -> str:
    """CASE SQL mappant `billing_origin_product` vers `serverless_surface`.

    A placer dans un SELECT indente a 12 espaces (l'indentation de continuation
    est deja dans la chaine). Ne porte PAS son `AS` (convention des autres
    helpers de ce module).

    Regroupe les 23 produits factures mesures en dev sur l'HISTORIQUE COMPLET
    (2023-08-26..2026-09-09) en 12 surfaces exploitables par la page : un
    `billing_origin_product` brut n'est pas une surface (6 produits differents
    sont un seul et meme endpoint d'IA du point de vue du cout), et une surface
    n'est pas un produit (`MV_ST_REFRESH` et `SQL_WAREHOUSE` sortent tous deux
    du produit `SQL`, discrimines par la presence d'un `dlt_pipeline_id`).
    20 produits sont nommes ici, les 3 autres tombent dans `OTHER` (voir plus
    bas, la liste est verrouillee par un test).

    JAMAIS NULL (branche `ELSE`) : c'est une CLE DE MERGE. Une cle NULL ne leve
    rien -- `pipelines.common.writers.merge_into_table` fusionne sur `<=>`
    null-safe et fondrait tout un workspace en une ligne corrompue.

    `GENIE` est separe de `AI_ENDPOINT` : c'est la seule surface d'IA sans
    `endpoint_id` (0 sur 18 397,47 $ mesures sur la fenetre de reference
    2026-08-10..2026-09-09, bi-cloud), et elle pese plus qu'`AI_ENDPOINT` entier
    (17 565,03 $). Les fusionner fabriquerait un faux grain objet, dont 100 % du
    cout tomberait sur la sentinelle.

    `ELSE 'OTHER'` est un MECANISME DE VISIBILITE, pas un repli de confort (la
    v1 du spike repliait sur `PLATFORM_AUTO`, ce qui masquait le probleme dans
    une surface credible). CONTROLE A REJOUER -- il porte sur la COMPOSITION
    d'`OTHER` et non sur un montant : seuls les 3 produits ci-dessous ont le
    droit d'y etre, tout QUATRIEME doit etre CLASSE, pas absorbe.
      SELECT cloud_provider, billing_origin_product, SUM(...) FROM <usage>
      WHERE <serverless_scope_predicate()> GROUP BY 1, 2
    Un seuil en dollars serait FAUX ici, et la premiere version de ce docstring
    l'etait : elle annoncait "<= ~10 $ par cloud" en citant les 4,82 $ de la
    fenetre de reference de 31 jours, alors que cette table se construit sur
    l'HISTORIQUE COMPLET, ou `OTHER` vaut 13 464,88 $ -- mille fois le seuil
    annonce, sans qu'aucun produit neuf soit apparu. Mesure dev 2026-09-10 sur
    2023-08-26..2026-09-09 :
      - `LAKEFLOW_CONNECT` : 9 880,03 $ AWS (73 787 lignes, depuis 2025-02-12),
        0 $ Azure. Ni plateforme automatique, ni objet listable, donc
        legitimement `OTHER` -- et c'est le SEUL produit force dans le perimetre
        par `SERVERLESS_SCOPE_PRODUCTS` a ne pas avoir de branche ici, ce qu'un
        test verrouille.
      - `SHARED_SERVERLESS_COMPUTE` : 90,46 $ AWS, 75 lignes, et uniquement du
        2024-08-15 au 2024-09-02 (SKU eteint depuis).
      - `BASE_ENVIRONMENTS` : 0,07 $ AWS, 17 lignes.
    Soit 0,365 % des 3 687 894,38 $ de depense serverless de l'historique
    (AWS 2 887 598,80 $, Azure 800 295,58 $).

    Le `CASE` est une LISTE BLANCHE, et `DATA_CLASSIFICATION` montre pourquoi :
    mesure dev 2026-09-10 sur l'historique COMPLET, ce produit existe sur les
    DEUX clouds (aws 495 lignes / 113,91 $, du 2025-11-24 au 2026-01-15 ; azure
    648 lignes / 582,32 $, du 2026-02-19 au 2026-09-08) -- il s'est simplement
    ARRETE sur AWS en janvier 2026, ce qu'une fenetre de 30 jours mesuree en
    septembre ne peut pas voir. Un produit peut donc apparaitre sur un cloud,
    cesser, puis revenir : seule une liste blanche avec un `ELSE 'OTHER'`
    surveille rend ce retour visible.

    Corollaire d'une liste blanche : elle doit couvrir les noms HISTORIQUES, pas
    seulement les noms courants. `PLATFORM_AUTO` porte pour cette raison DEUX
    noms de la meme fonctionnalite, `DATA_QUALITY_MONITORING` et son nom
    precedent `LAKEHOUSE_MONITORING`. La preuve que c'est un renommage et non
    deux produits est dans les SKU : les deux portent EXACTEMENT le meme
    ensemble (`ENTERPRISE_JOBS_SERVERLESS_COMPUTE_EUROPE_FRANKFURT` cote AWS,
    `PREMIUM_JOBS_SERVERLESS_COMPUTE_EU_WEST` +
    `PREMIUM_JOBS_SERVERLESS_COMPUTE_FRANCE_CENTRAL` cote Azure), avec relais
    dans le temps -- l'ancien nom s'arrete le 2026-02-06, le nouveau demarre le
    2025-11-06 (azure) / 2025-12-15 (aws). Ne retenir que le nom RECENT ferait
    tomber 3 494,32 $ (AWS 2 837,39 $, Azure 656,93 $) dans `OTHER`, et une
    fenetre de 31 jours mesuree en septembre ne peut pas le voir : c'est
    exactement le piege de `usage_policy_id` face a `budget_policy_id` decrit
    dans `serverless_cost_daily`, ou retenir la colonne RECENTE perdrait
    silencieusement 188 744 lignes d'historique.
    """
    return """CASE
              WHEN billing_origin_product = 'JOBS' THEN 'JOB'
              WHEN billing_origin_product = 'DLT' THEN 'DLT_PIPELINE'
              WHEN billing_origin_product = 'SQL'
                   AND usage_metadata.dlt_pipeline_id IS NOT NULL THEN 'MV_ST_REFRESH'
              WHEN billing_origin_product = 'SQL' THEN 'SQL_WAREHOUSE'
              WHEN billing_origin_product = 'INTERACTIVE' THEN 'NOTEBOOK'
              WHEN billing_origin_product = 'APPS' THEN 'APP'
              WHEN billing_origin_product = 'GENIE' THEN 'GENIE'
              WHEN billing_origin_product IN ('MODEL_SERVING', 'VECTOR_SEARCH', 'AI_GATEWAY',
                                              'SUPERVISOR_AGENT', 'AI_FUNCTIONS',
                                              'AGENT_EVALUATION') THEN 'AI_ENDPOINT'
              WHEN billing_origin_product IN ('DATABASE', 'LAKEBASE') THEN 'LAKEBASE'
              WHEN billing_origin_product = 'NETWORKING' THEN 'NETWORKING'
              WHEN billing_origin_product IN ('PREDICTIVE_OPTIMIZATION',
                                              'DATA_QUALITY_MONITORING',
                                              'LAKEHOUSE_MONITORING',
                                              'FINE_GRAINED_ACCESS_CONTROL',
                                              'DATA_CLASSIFICATION') THEN 'PLATFORM_AUTO'
              ELSE 'OTHER'
            END"""


# Sentinelle de `object_id` pour les surfaces sans objet identifiable (grain
# workspace). Le prefixe `_` la distingue d'un id Databricks reel (aucun n'en
# porte). VALEUR TECHNIQUE : `object_id` est une CLE DE MERGE, et
# `merge_into_table` fusionne sur `<=>` null-safe -- une cle NULL n'echoue pas,
# elle fond silencieusement tout un workspace en UNE ligne corrompue. Mesure dev
# 2026-09-10 (fenetre de reference 2026-08-10..2026-09-09) : 33 425,57 $ dans ce
# cas, soit 8,78 % de la depense serverless BI-CLOUD -- AWS 26 281,05 $ / 9,50 %,
# Azure 7 144,52 $ / 6,87 %. En LIGNES la sentinelle en porte plus de la moitie
# (1 531 218 contre 1 286 959 avec cle) pour moins d'un dixieme du cout : laisser
# cette cle a NULL aurait donc fusionne la majorite de la table.
SERVERLESS_OBJECT_ID_SENTINEL = "_NO_OBJECT"


def serverless_object_id_expr() -> str:
    """CASE SQL derivant `object_id` de `serverless_surface`, avec sentinelle.

    A placer dans un SELECT indente a 12 espaces, APRES la CTE qui materialise
    `serverless_surface` (l'expression reference cette colonne). Ne porte pas
    son `AS`.

    Le champ qui identifie l'objet CHANGE par surface : il n'existe aucun
    "object_id" generique dans `usage_metadata`. Les surfaces sans objet
    listable (`GENIE`, `PLATFORM_AUTO`, `NETWORKING`, `OTHER`) restent au grain
    workspace via la sentinelle `_NO_OBJECT` (cf.
    `SERVERLESS_OBJECT_ID_SENTINEL` pour le pourquoi et les montants).

    Mesure dev 2026-09-10 (fenetre de reference 2026-08-10..2026-09-09,
    bi-cloud) : la part de cout sans cle d'objet vaut 100 % sur ces 4 surfaces,
    9,3 % sur `LAKEBASE`, 2,3 % sur `NOTEBOOK`, 0,8 % sur `AI_ENDPOINT`, 0 %
    ailleurs. `usage_metadata.serverless_compute_id` n'est PAS une cle d'objet
    utilisable (identifiant de pool par workspace : 175 valeurs distinctes pour
    3 727 `job_id`, dont 2 510 en portent un).
    """
    return """COALESCE(
              CASE serverless_surface
                WHEN 'JOB' THEN usage_metadata.job_id
                WHEN 'DLT_PIPELINE' THEN usage_metadata.dlt_pipeline_id
                WHEN 'MV_ST_REFRESH' THEN usage_metadata.dlt_pipeline_id
                WHEN 'SQL_WAREHOUSE' THEN usage_metadata.warehouse_id
                WHEN 'NOTEBOOK' THEN usage_metadata.notebook_id
                WHEN 'APP' THEN usage_metadata.app_id
                WHEN 'AI_ENDPOINT' THEN COALESCE(usage_metadata.endpoint_id,
                                                 usage_metadata.ai_gateway.endpoint_id)
                WHEN 'LAKEBASE' THEN COALESCE(usage_metadata.endpoint_id,
                                              usage_metadata.dlt_pipeline_id)
                ELSE NULL
              END,
              '_NO_OBJECT'
            )"""


def identity_principal_expr() -> str:
    """Principal responsable de la ligne facturee (cascade `identity_metadata`).

    `run_as` (qui EXECUTE) puis `owned_by` (qui POSSEDE) puis `created_by` (qui
    a CREE) : le champ porteur change par surface, mesure dev 2026-09-10
    (fenetre de reference 2026-08-10..2026-09-09, bi-cloud, en part de cout) --
    `SQL_WAREHOUSE` 100 % `owned_by`, `APP` 100 % `created_by`, `AI_ENDPOINT`
    92,2 % `created_by` / 7,2 % `run_as`, jobs / notebooks / DLT / Genie /
    plateforme 100 % `run_as`. Une colonne unique tiree d'un seul de ces champs
    rendrait donc une matrice d'attribution fausse, ce qui etait le defaut de la
    v1 du spike ; d'ou aussi `identity_source_expr`, parce que "proprietaire" et
    "executant" ne sont pas la meme semantique de refacturation.

    `identity_metadata.run_by` est VOLONTAIREMENT absent de la cascade : mesure
    dev 2026-09-10 (fenetre de reference), il ne recupere 0,00 $ de la depense
    sans identite -- les 364,52 $ ou il est renseigne portent tous deja l'un des
    trois autres champs. L'ajouter allongerait la cascade sans rien attribuer.

    Peut valoir NULL (2,26 % du cout, 8 605,66 $ sur la fenetre de reference :
    `LAKEBASE` 6 081,87 $, `NETWORKING` 2 518,97 $, `OTHER` 4,82 $) : ce n'est
    PAS une cle de merge, un NULL y est une information de gouvernance (depense
    sans proprietaire) et non une corruption.
    """
    return (
        "COALESCE(identity_metadata.run_as, identity_metadata.owned_by, "
        "identity_metadata.created_by)"
    )


def identity_source_expr() -> str:
    """Champ d'ou vient `identity_principal` : jamais NULL, `NONE` si aucun.

    Rend la cascade de `identity_principal_expr` AUDITABLE : sans cette colonne,
    l'IHM ne peut pas distinguer un executant (`RUN_AS`, refacturable a l'usage)
    d'un proprietaire (`OWNED_BY`, refacturable a la possession) ni voir la
    depense orpheline (`NONE`). Les deux expressions doivent rester alignees :
    meme ordre de cascade, meme champs.
    """
    return (
        "CASE "
        "WHEN identity_metadata.run_as IS NOT NULL THEN 'RUN_AS' "
        "WHEN identity_metadata.owned_by IS NOT NULL THEN 'OWNED_BY' "
        "WHEN identity_metadata.created_by IS NOT NULL THEN 'CREATED_BY' "
        "ELSE 'NONE' END"
    )
