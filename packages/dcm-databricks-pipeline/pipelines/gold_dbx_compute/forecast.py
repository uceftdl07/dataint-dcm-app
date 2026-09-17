"""Agregation gold `gold_dbx_compute_forecast_daily` (socle predictif).

Projection des metriques clusters + jobs + warehouses via `ai_forecast`
(fonction SQL native Databricks, table-valued) sur l'historique deja
materialise des tables gold `*_daily` - alimente l'anticipation
budget/rightsizing (cf. `compute_datamapping.md` §4.2).

Couvre 11 combinaisons (object_type, metrique) :
  - `CLUSTER` (hors clusters JOB et PIPELINE, cf. ci-dessous) : `cost_usd`,
    `dbu_quantity` (depuis `gold_dbx_compute_cluster_cost_daily`),
    `cpu_util_p95_pct` (depuis `gold_dbx_compute_cluster_efficiency_daily`).
  - `JOB` : `cost_usd`, `dbu_quantity` (depuis
    `gold_dbx_compute_job_cluster_cost_daily`, rollup par job_id).
  - `PIPELINE` : `cost_usd`, `dbu_quantity` (depuis
    `gold_dbx_compute_pipeline_cost_daily`, grain `dlt_pipeline_id` stable dans
    le temps). Aucune passe d'efficacite (`cpu_util_p95_pct`) : il n'existe pas
    de table d'efficacite au grain pipeline (hors scope, cf. `pipeline_cost_daily.py`).
  - `WAREHOUSE` : `cost_usd`, `dbu_quantity` (depuis
    `gold_dbx_compute_warehouse_cost_daily`), `query_count`,
    `queue_time_p95_ms` (depuis
    `gold_dbx_compute_warehouse_query_performance_daily`).

Les clusters `cluster_type` JOB et PIPELINE (ephemeres - `cluster_id` recree a
chaque execution, cf. `pipelines.gold_dbx_compute.job_cluster_cost_daily`) sont
EXCLUS du grain CLUSTER (`cost_usd`/`dbu_quantity`/`cpu_util_p95_pct`) : la
tres grande majorite n'a qu'1 seul jour d'historique reel dans la fenetre
d'entrainement, ce qui produit une serie degenree pour `ai_forecast` (0 ou 1
point), pas juste redondante avec le passage `JOB` ci-dessus qui a un
historique reel (agrege par job, pas par cluster). Aucune prevision
`cpu_util_p95_pct` au grain JOB : pas de table d'efficiency au grain job
(decision hors scope, cf. `job_cluster_cost_daily.py`).

`ai_forecast` est table-valued (`SELECT * FROM ai_forecast(...)`, jamais un
scalaire) : PySpark n'a pas d'API DataFrame dediee, l'appel passe entierement
par du SQL. `group_col` de `ai_forecast` n'accepte qu'UNE seule colonne : les 3
colonnes d'identite (`cloud_provider`, `workspace_id`, `cluster_id`/
`warehouse_id`) sont donc concatenees en une cle composite (`object_key`) avant
l'appel, puis re-eclatees apres (cf. `_split_object_key_columns`).

Tous les historiques d'entrainement passent par `_observed_sql`, qui DENSIFIE
la serie (jours sans ligne source a 0) pour les metriques ADDITIVES
(`cost_usd`, `dbu_quantity`, `query_count`) et la laisse creuse pour les
metriques de DISTRIBUTION (`cpu_util_p95_pct`, `queue_time_p95_ms`) : un jour
ou le cluster est eteint coute 0 $ mais n'a pas une utilisation CPU de 0 %.
C'est cette distinction qui impose DEUX passes sur
`gold_dbx_compute_warehouse_query_performance_daily`, dont les deux metriques
projetees ne sont pas de la meme nature.

`ai_forecast` exige un Pro/Serverless SQL Warehouse (doc officielle
Databricks) - pas du SQL Spark standard executable sur n'importe quel compute,
incompatible avec l'environnement serverless generique d'une tache
`python_wheel_task`. `render_forecast_query` reste une fonction PURE (construit
le texte SQL, ne l'execute pas) : `build_compute_forecast` execute ce texte via
l'API Statement Execution (`databricks.sdk`) contre `warehouse_id`, puis
reintegre le resultat en DataFrame Spark (`spark.createDataFrame`) pour rester
compatible avec `merge_into_table` (Spark natif) sans aucun changement en aval.
"""

from __future__ import annotations

import time
from datetime import date
from typing import TYPE_CHECKING, Any

from pyspark.sql import functions as F
from pyspark.sql.types import DateType, DoubleType, StringType, StructField, StructType

from pipelines.gold_dbx_compute.sql_helpers import CLUSTER_TYPE_JOB, CLUSTER_TYPE_PIPELINE

if TYPE_CHECKING:
    from databricks.sdk.service.sql import ExternalLink
    from pyspark.sql import DataFrame, SparkSession

# Separateur de la cle composite `object_key` (cf. docstring module). `::` :
# jamais present dans un `cloud_provider`/`workspace_id`/`cluster_id` reel, ET
# sans signification speciale en regex (contrairement a `||`, une alternation)
# - `split()` (regex Java) peut donc le reutiliser tel quel, sans echappement.
_OBJECT_KEY_SEPARATOR = "::"

# Bornes metier passees a `ai_forecast` (`parameters` JSON, cf. reference
# `databricks-ai-functions/3-ai-forecast.md`) : aucune metrique projetee ne
# peut etre negative (cout, DBU, pourcentage, nombre de requetes, temps
# d'attente) ; `cpu_util_p95_pct` a de plus un plafond naturel a 100
# (pourcentage). Sans ces bornes, une serie en baisse peut projeter des
# valeurs hors du domaine metier valide.
_NON_NEGATIVE_FORECAST_PARAMETERS = '{"global_floor": 0}'
_PERCENTAGE_FORECAST_PARAMETERS = '{"global_floor": 0, "global_cap": 100}'

# Plafond ABSOLU des metriques en pourcentage, repris de `global_cap` ci-dessus.
# Sert de borne de plausibilite a `cpu_util_p95_pct`, a la place de la borne
# relative appliquee aux autres metriques : un taux d'utilisation qui passe de
# 8 % a 90 % est invraisemblable pour un modele, pas impossible dans les faits,
# et 100 est deja la seule valeur que la metrique ne peut pas depasser.
_PERCENTAGE_CEILING = "100"

# Ecretage de la borne HAUTE au plafond de plausibilite de sa passe (relatif a
# la serie, ou `_PERCENTAGE_CEILING`). Le filtre sur `predicted_value` ne suffit
# pas : `ai_forecast` peut rendre une valeur projetee plausible assortie d'un
# intervalle de confiance de plusieurs ordres de grandeur au-dessus, et
# l'exposition AGREGE `upper_bound` sur tout le parc pour tracer sa bande -- une
# seule borne aberrante y ecrase la courbe du realise. L'exposition combine les
# demi-largeurs en quadrature (`√Σ demi²`) plutot que de les sommer, ce qui ne
# protege pas de ce cas : un terme tres superieur aux autres domine la racine.
#
# ECRETE, pas filtre : la ligne est plausible, c'est son intervalle qui ne l'est
# pas ; la supprimer couterait de la couverture pour un defaut qui ne touche pas
# la valeur projetee. `CASE` et non `LEAST` : `LEAST` IGNORE les NULL et
# renverrait le plafond la ou le modele n'a rendu aucune borne, fabriquant une
# valeur -- ici `NULL > plafond` vaut NULL, la branche `ELSE` preserve le NULL
# (cf. `_coerce_forecast_row`, qui ne fabrique jamais de valeur non plus).
# La borne BASSE n'a besoin de rien : `global_floor` la tient a 0 par le bas, et
# elle reste sous `predicted_value`, deja plafonnee par le `WHERE`.
_CLIPPED_UPPER_BOUND = (
    "CASE WHEN upper_bound > max_plausible_value"
    " THEN max_plausible_value ELSE upper_bound END AS upper_bound"
)

# Delai entre deux verifications de statut d'un statement en cours :
# `ai_forecast` (ajustement de modele) depasse souvent le `wait_timeout` max de
# l'API Statement Execution (50s) - on poll donc jusqu'a l'etat terminal.
_STATEMENT_POLL_INTERVAL_SECONDS = 2.0

# Schema explicite du resultat de `render_forecast_query` : necessaire pour
# reconstruire un DataFrame Spark a partir des lignes renvoyees par l'API
# Statement Execution (toutes les valeurs y transitent en chaines, cf.
# `_coerce_forecast_row`). `_generated_at` n'y figure pas : ajoute a part par
# `build_compute_forecast` via `current_timestamp()` (Spark natif), pas par la
# requete executee sur le warehouse.
_FORECAST_RESULT_SCHEMA = StructType(
    [
        StructField("cloud_provider", StringType(), True),
        StructField("workspace_id", StringType(), True),
        StructField("object_type", StringType(), True),
        StructField("object_id", StringType(), True),
        StructField("metric_name", StringType(), True),
        StructField("horizon_date", DateType(), True),
        StructField("predicted_value", DoubleType(), True),
        StructField("lower_bound", DoubleType(), True),
        StructField("upper_bound", DoubleType(), True),
        StructField("method", StringType(), True),
    ]
)


def _split_object_key_columns(alias: str) -> str:
    """Fragment SQL : re-eclate `object_key` (`{alias}.object_key`) en 3 colonnes.

    Inverse de `concat_ws('::', cloud_provider, workspace_id, cluster_id)` (ou
    `warehouse_id`) - `ai_forecast` ne renvoie que la cle de groupe composite
    en sortie (cf. docstring module), jamais les colonnes d'origine qui la
    composent.
    """
    parts = f"split({alias}.object_key, '{_OBJECT_KEY_SEPARATOR}')"
    return (
        f"{parts}[0] AS cloud_provider, "
        f"{parts}[1] AS workspace_id, "
        f"{parts}[2] AS object_id"
    )


def _object_key_expr(object_key_columns: tuple[str, ...]) -> str:
    """Expression SQL de la cle composite de groupe (cf. docstring module)."""
    return f"concat_ws('{_OBJECT_KEY_SEPARATOR}', {', '.join(object_key_columns)})"


def _observed_window(observed_lower_bound: date, extra_conditions: tuple[str, ...]) -> str:
    """Condition `WHERE` de la fenetre d'entrainement, commune aux sous-requetes.

    La borne HAUTE exclut le jour en cours : les tables `*_daily` le portent des
    la premiere execution de la journee, mais partiellement (mesure en dev a la
    mi-journee : 562 $ de cout job contre ~4 400 $ sur une journee pleine). Le
    modele lit ce creux comme un effondrement reel, et l'horizon s'ancre sur un
    jour incomplet -- la prevision ne commence alors que DEMAIN, laissant
    aujourd'hui sans valeur ni observee ni predite.
    """
    return " AND ".join(
        (
            f"period_start >= DATE '{observed_lower_bound.isoformat()}'",
            "period_start < current_date()",
            *extra_conditions,
        )
    )


def _last_observed_day_sql(
    *,
    source_table: str,
    observed_lower_bound: date,
    extra_conditions: tuple[str, ...] = (),
) -> str:
    """Sous-requete scalaire : dernier jour REELLEMENT observe dans la fenetre.

    Sert de reference au plafond d'horizon de chaque passe (cf.
    `render_forecast_query`) : `horizon` seul est une date absolue, donc le
    nombre de jours projetes varie avec la fraicheur de la source.
    """
    window = _observed_window(observed_lower_bound, extra_conditions)
    return f"(SELECT MAX(period_start) FROM {source_table} WHERE {window})"


def _daily_sql(
    *,
    source_table: str,
    object_key_columns: tuple[str, ...],
    metrics: tuple[str, ...],
    observed_lower_bound: date,
    densify: bool,
    extra_conditions: tuple[str, ...] = (),
) -> str:
    """Fragment SQL : une ligne par (objet, jour), agregee explicitement.

    Les sources jobs/pipelines portent `compute_kind` dans leur grain et
    livrent deux lignes le meme jour pour un objet mixte, ce que `ai_forecast`
    lirait comme deux points au meme horodatage. `SUM` pour les metriques
    additives, `MAX` pour celles de distribution : un p95 ne se somme pas.
    """
    key = _object_key_expr(object_key_columns)
    window = _observed_window(observed_lower_bound, extra_conditions)
    aggregate = "SUM" if densify else "MAX"
    aggregated = ", ".join(f"{aggregate}({metric}) AS {metric}" for metric in metrics)
    return f"""(
                    SELECT {key} AS object_key, period_start, {aggregated}
                    FROM {source_table}
                    WHERE {window}
                    GROUP BY {key}, period_start
                )"""


def _observed_bounds_sql(
    *,
    source_table: str,
    object_key_columns: tuple[str, ...],
    metrics: tuple[str, ...],
    observed_lower_bound: date,
    densify: bool,
    extra_conditions: tuple[str, ...] = (),
) -> str:
    """Fragment SQL : maximum journalier OBSERVE de chaque serie, par metrique.

    Borne de plausibilite de la passe correspondante. Le maximum porte sur la
    valeur journaliere AGREGEE (cf. `_daily_sql`), pas sur les lignes brutes :
    pour un objet mixte, la journee vaut la somme de ses formes de compute, et
    c'est ce total qui fait reference.
    """
    daily = _daily_sql(
        source_table=source_table,
        object_key_columns=object_key_columns,
        metrics=metrics,
        observed_lower_bound=observed_lower_bound,
        densify=densify,
        extra_conditions=extra_conditions,
    )
    maximums = ", ".join(f"MAX({metric}) AS {metric}_max" for metric in metrics)
    return f"""
        SELECT object_key, {maximums}
        FROM {daily} daily
        GROUP BY object_key"""


def _observed_sql(
    *,
    source_table: str,
    object_key_columns: tuple[str, ...],
    metrics: tuple[str, ...],
    observed_lower_bound: date,
    min_observed_days: int,
    densify: bool,
    extra_conditions: tuple[str, ...] = (),
) -> str:
    """Fragment SQL : historique d'entrainement d'une passe, argument de `observed =>`.

    Deux sous-requetes communes aux deux modes :

      - `eligible` : les objets ayant au moins `min_observed_days` jours
        d'activite REELLE dans la fenetre. Un cluster vu 1 seul jour n'a pas de
        serie temporelle : le projeter extrapole depuis un point isole, sur un
        volume proportionnel au parc (99,22 % des `cluster_id` n'ont qu'un jour
        d'historique, cf. `specs.FORECAST_OBSERVED_LOOKBACK_DAYS`).
      - `daily` : une ligne par (objet, jour), agregee explicitement — les
        sources jobs/pipelines portent `compute_kind` dans leur grain et
        livrent deux lignes le meme jour pour un objet mixte, ce que
        `ai_forecast` lirait comme deux points au meme horodatage.

    `densify` distingue les deux natures de metrique, et c'est la difference
    qui compte ici :

      - `True` (metriques ADDITIVES : `cost_usd`, `dbu_quantity`,
        `query_count`) : produit cartesien objets eligibles x jours de la
        fenetre, les jours sans ligne source a 0. Un jour sans ligne vaut
        reellement 0 $ / 0 DBU / 0 requete, et sans ces zeros le modele ajuste
        le niveau sur les seuls jours ACTIFS : la projection, lue en aval comme
        une valeur par jour calendaire, est surevaluee du rapport
        jours_calendaires / jours_actifs (un cluster allume du lundi au
        vendredi se voit projeter ses jours ouvres comme des jours moyens).
        L'agregat est `SUM`.
      - `False` (metriques de DISTRIBUTION : `cpu_util_p95_pct`,
        `queue_time_p95_ms`) : la serie reste creuse. Un jour ou le cluster est
        eteint n'a pas une utilisation CPU de 0 %, il n'en a aucune ; densifier
        a 0 ferait baisser un p95 qui n'a pas bouge. L'agregat est `MAX` (un
        p95 ne se somme pas), sans effet quand la source est deja au grain.

    Le calendrier de densification est l'ensemble des jours DISTINCTS presents
    dans la fenetre, jamais un `sequence()` de dates fabriquees : la borne
    haute est ainsi le dernier jour reellement charge, et non un jour que la
    source n'a pas encore livre — qui serait densifie a 0 et tirerait la
    prevision vers le bas.
    """
    key = _object_key_expr(object_key_columns)
    window = _observed_window(observed_lower_bound, extra_conditions)
    eligible = f"""(
                    SELECT {key} AS object_key
                    FROM {source_table}
                    WHERE {window}
                    GROUP BY {key}
                    HAVING COUNT(DISTINCT period_start) >= {min_observed_days}
                ) eligible"""
    daily = f"""{
        _daily_sql(
            source_table=source_table,
            object_key_columns=object_key_columns,
            metrics=metrics,
            observed_lower_bound=observed_lower_bound,
            densify=densify,
            extra_conditions=extra_conditions,
        )
    } daily"""
    if not densify:
        columns = ", ".join(f"daily.{metric}" for metric in metrics)
        return f"""
                SELECT daily.object_key, daily.period_start, {columns}
                FROM {daily}
                JOIN {eligible}
                  ON eligible.object_key = daily.object_key"""
    coalesced = ", ".join(f"COALESCE(daily.{metric}, 0) AS {metric}" for metric in metrics)
    return f"""
                SELECT eligible.object_key, calendar.period_start, {coalesced}
                FROM {eligible}
                CROSS JOIN (
                    SELECT DISTINCT period_start
                    FROM {source_table}
                    WHERE {window}
                ) calendar
                LEFT JOIN {daily}
                  ON daily.object_key = eligible.object_key
                 AND daily.period_start = calendar.period_start"""


def render_forecast_query(
    *,
    cost_daily_table: str,
    efficiency_daily_table: str,
    job_cluster_cost_daily_table: str,
    pipeline_cost_daily_table: str,
    warehouse_cost_daily_table: str,
    warehouse_query_performance_daily_table: str,
    observed_lower_bound: date,
    horizon_date: date,
    horizon_days: int,
    prediction_interval_width: float = 0.95,
    min_observed_days: int = 3,
    max_observed_ratio: float = 10.0,
) -> str:
    """Construit le texte SQL de `gold_dbx_compute_forecast_daily` (pur, non execute).

    Fonction PURE (aucun acces reseau/compute) : separee de `build_compute_forecast`
    pour rester testable par simple assertion de texte (cf. `test_forecast.py`),
    independamment du mecanisme d'execution (`ai_forecast` doit tourner sur un
    SQL Warehouse, cf. docstring module).

    Args:
        cost_daily_table: nom qualifie de `gold_dbx_compute_cluster_cost_daily`
            (historique source des metriques `cost_usd`/`dbu_quantity`,
            clusters non-JOB uniquement - cf. `cluster_type` ci-dessous).
        efficiency_daily_table: nom qualifie de
            `gold_dbx_compute_cluster_efficiency_daily` (historique source de
            `cpu_util_p95_pct`, clusters non-JOB uniquement).
        job_cluster_cost_daily_table: nom qualifie de
            `gold_dbx_compute_job_cluster_cost_daily` (historique source des
            metriques `cost_usd`/`dbu_quantity` au grain job, rollup des
            clusters JOB ephemeres).
        pipeline_cost_daily_table: nom qualifie de
            `gold_dbx_compute_pipeline_cost_daily` (historique source des
            metriques `cost_usd`/`dbu_quantity` au grain `dlt_pipeline_id`,
            rollup billing-direct des pipelines Lakeflow/DLT - id stable, pas
            de filtre `cluster_type`).
        warehouse_cost_daily_table: nom qualifie de
            `gold_dbx_compute_warehouse_cost_daily` (historique source des
            metriques `cost_usd`/`dbu_quantity` au grain warehouse).
        warehouse_query_performance_daily_table: nom qualifie de
            `gold_dbx_compute_warehouse_query_performance_daily` (historique
            source des metriques `query_count`/`queue_time_p95_ms`).
        observed_lower_bound: borne basse (`period_start >=`) appliquee AVANT
            l'appel `ai_forecast` sur les 6 tables source - calculee par
            l'appelant (`today - FORECAST_OBSERVED_LOOKBACK_DAYS`, cf.
            `pipelines.gold_dbx_compute.specs`).
        horizon_date: plafond ABSOLU passe a `horizon` de `ai_forecast` -
            calcule par l'appelant (`today + FORECAST_HORIZON_DAYS`, cf.
            `pipelines.gold_dbx_compute.specs`).
        horizon_days: nombre de jours projetes REELLEMENT conserves, compte a
            partir du dernier jour observe de CHAQUE passe
            (`FORECAST_HORIZON_DAYS`). Les deux bornes ne sont pas redondantes :
            `ai_forecast` projette du jour suivant la derniere observation
            jusqu'a `horizon`, donc le nombre de jours produits varie avec la
            fraicheur de la source (une source en retard de 2 jours produit 2
            jours de "prevision" deja passes, et 9 lignes la ou la table en
            annonce 7). Chaque passe est plafonnee sur SON dernier jour observe :
            les 6 tables source n'ont pas la meme fraicheur.
        prediction_interval_width: largeur de l'intervalle de confiance
            (0-1, defaut 0.95 = defaut natif `ai_forecast`).
        min_observed_days: jours d'activite reelle minimum pour etre projete
            (cf. `specs.FORECAST_MIN_OBSERVED_DAYS` et `_observed_sql`).
        max_observed_ratio: plafond de PLAUSIBILITE, relatif a la serie (cf.
            `specs.FORECAST_MAX_OBSERVED_RATIO`). Une prevision superieure a
            `max_observed_ratio x` le maximum journalier observe de SA PROPRE
            serie n'est pas publiee -- pas plus qu'une `predicted_value` NULL,
            qu'`ai_forecast` produit sans lever d'erreur sur une serie
            degeneree. Mesure en dev avant garde-fou : 38,9 M$/jour projetes
            pour UN job, 867 M$ pour le grain JOB entier (4 400 $/jour
            observes), et 2,6 x 10^46 ms de temps d'attente. Un plafond
            scalaire (`global_cap`) est aveugle a ce cas : il ne voit pas la
            petite serie qui explose sous le plafond global. `cpu_util_p95_pct`
            garde son plafond absolu de 100 (cf. `_PERCENTAGE_CEILING`). Le
            plafond de chaque passe ECRETE en plus `upper_bound` (cf.
            `_CLIPPED_UPPER_BOUND`), qu'`ai_forecast` peut rendre plusieurs
            ordres de grandeur au-dessus d'une `predicted_value` pourtant
            plausible.

    Returns:
        Le texte SQL complet (une ligne par
        `(cloud_provider, object_type, object_id, metric_name, horizon_date)`,
        clusters (hors JOB) + jobs + pipelines + warehouses).

    Grain : `(cloud_provider, workspace_id, object_type, object_id,
    metric_name, horizon_date)`. Source : les 6 tables gold `*_daily` passees
    en argument (jamais les tables curated directement).

    Champs et formule de calcul :
      - `observed_lower_bound` borne la fenetre d'entrainement passee a
        `ai_forecast` : double effet, par construction (un seul filtre, pas
        deux mecanismes separes) - (1) bornes l'historique d'entrainement a
        une fenetre fixe, independamment de l'age reel de l'objet ; (2) un
        objet dont TOUTES les lignes sont anterieures a cette borne n'a plus
        aucune ligne dans `observed` -> `ai_forecast` ne produit aucune
        prevision pour lui. Sans cette borne, `ai_forecast` fitte sur la
        totalite de l'historique disponible et produit une ligne par jour
        depuis le jour APRES la derniere donnee reelle jusqu'a `horizon_date` :
        pour un objet ephemere sans activite recente, ceci genere un volume de
        lignes de "prevision" disproportionne pour un objet qui n'existe plus.
      - Chaque `observed` passe par `_observed_sql` : eligibilite
        (`min_observed_days` jours d'activite reelle), agregation explicite au
        grain (objet, jour), et DENSIFICATION a 0 des jours sans ligne source
        pour les seules metriques additives (cf. la docstring de ce helper : un
        p95 n'a pas de valeur un jour ou le cluster est eteint, un cout en a
        une, 0).
      - Sept passes `ai_forecast` (une par table gold source, deux pour la
        performance de requetes dont les deux metriques n'ont pas la meme
        nature) :
        - `cost_usd` + `dbu_quantity` (clusters, hors JOB/PIPELINE : `WHERE
          cluster_type NOT IN ('JOB', 'PIPELINE')`) en un seul appel multi-metriques (meme
          table source `cost_daily_table`). `value_col` passe par un literal
          `array(...)`, PAS une chaine separee par virgules (une chaine
          `'a,b'` est lue comme UN seul nom de colonne litteral, jamais comme
          deux colonnes).
        - `cpu_util_p95_pct` (clusters, hors JOB/PIPELINE) en un appel separe (table
          source differente).
        - `cost_usd` + `dbu_quantity` au grain job (`job_cluster_cost_daily_table`,
          deja restreint aux clusters JOB via son rollup) en un appel
          multi-metriques distinct.
        - `cost_usd` + `dbu_quantity` au grain pipeline
          (`pipeline_cost_daily_table`, rollup billing-direct par
          `dlt_pipeline_id`) en un appel multi-metriques distinct. Pas de filtre
          `cluster_type` (la source n'a pas cette colonne), pas de passe
          d'efficacite (aucune table d'efficacite au grain pipeline). La somme
          du `GROUP BY` de `_observed_sql` conserve ici la semantique voulue :
          une prevision par pipeline, toutes formes de compute confondues (la
          source porte `compute_kind` dans son grain et livre deux lignes le
          meme jour pour un pipeline mixte). Si une prevision PAR forme devenait
          souhaitable, il faudrait ajouter `compute_kind` a `object_key` (et donc
          a `_split_object_key_columns`), pas retirer l'agregation.
        - `cost_usd` + `dbu_quantity` au grain warehouse
          (`warehouse_cost_daily_table`) en un appel multi-metriques distinct.
        - `query_count` (additif, densifie) puis `queue_time_p95_ms`
          (distribution, serie creuse) en DEUX appels sur la meme table source
          `warehouse_query_performance_daily_table` : un seul appel
          multi-metriques imposerait le meme historique aux deux, donc soit des
          zeros sur un p95, soit l'absence de zeros sur un compte.
      Chaque passe est groupee par `object_key` (cf. `_split_object_key_columns`)
      : une serie temporelle independante par objet (cluster, job, pipeline ou
      warehouse), bornee par `observed_lower_bound` (cf. ci-dessus), en pas
      journalier explicite (`frequency => 'D'`, jamais infere d'une serie a
      trous) et plafonnee a `horizon_days` jours apres le dernier jour observe
      de sa propre source.
    """
    cluster_conditions = (
        f"cluster_type NOT IN ('{CLUSTER_TYPE_JOB}', '{CLUSTER_TYPE_PIPELINE}')",
    )
    cluster_key = ("cloud_provider", "workspace_id", "cluster_id")
    job_key = ("cloud_provider", "workspace_id", "job_id")
    pipeline_key = ("cloud_provider", "workspace_id", "dlt_pipeline_id")
    warehouse_key = ("cloud_provider", "workspace_id", "warehouse_id")

    def observed(
        source_table: str,
        object_key_columns: tuple[str, ...],
        metrics: tuple[str, ...],
        *,
        densify: bool,
        extra_conditions: tuple[str, ...] = (),
    ) -> str:
        return _observed_sql(
            source_table=source_table,
            object_key_columns=object_key_columns,
            metrics=metrics,
            observed_lower_bound=observed_lower_bound,
            min_observed_days=min_observed_days,
            densify=densify,
            extra_conditions=extra_conditions,
        )

    def bounds(
        source_table: str,
        object_key_columns: tuple[str, ...],
        metrics: tuple[str, ...],
        *,
        densify: bool,
        extra_conditions: tuple[str, ...] = (),
    ) -> str:
        return _observed_bounds_sql(
            source_table=source_table,
            object_key_columns=object_key_columns,
            metrics=metrics,
            observed_lower_bound=observed_lower_bound,
            densify=densify,
            extra_conditions=extra_conditions,
        )

    def horizon_cap(source_table: str, extra_conditions: tuple[str, ...] = ()) -> str:
        last_day = _last_observed_day_sql(
            source_table=source_table,
            observed_lower_bound=observed_lower_bound,
            extra_conditions=extra_conditions,
        )
        # `period_start >= current_date()` : sur une passe de DISTRIBUTION la
        # serie reste creuse, donc `ai_forecast` repart de la derniere
        # observation de CHAQUE objet -- parfois vieille de plusieurs jours
        # (mesure en dev : 4 jours sur `queue_time_p95_ms`). Le plafond relatif
        # seul laissait alors passer des horizons deja passes, qui ne sont pas
        # des previsions.
        return (
            f"WHERE period_start >= current_date()"
            f" AND period_start <= date_add({last_day}, {horizon_days})"
        )

    # Un fragment `observed` et un plafond d'horizon par passe, calcules AVANT
    # la f-string : une expression multi-lignes dans une f-string exigerait
    # Python 3.12+ (PEP 701) cote runtime Databricks, pas seulement au lint.
    cluster_observed = observed(
        cost_daily_table,
        cluster_key,
        ("cost_usd", "dbu_quantity"),
        densify=True,
        extra_conditions=cluster_conditions,
    )
    cpu_util_observed = observed(
        efficiency_daily_table,
        cluster_key,
        ("cpu_util_p95_pct",),
        densify=False,
        extra_conditions=cluster_conditions,
    )
    job_observed = observed(
        job_cluster_cost_daily_table, job_key, ("cost_usd", "dbu_quantity"), densify=True
    )
    pipeline_observed = observed(
        pipeline_cost_daily_table, pipeline_key, ("cost_usd", "dbu_quantity"), densify=True
    )
    warehouse_observed = observed(
        warehouse_cost_daily_table, warehouse_key, ("cost_usd", "dbu_quantity"), densify=True
    )
    query_count_observed = observed(
        warehouse_query_performance_daily_table, warehouse_key, ("query_count",), densify=True
    )
    queue_time_observed = observed(
        warehouse_query_performance_daily_table,
        warehouse_key,
        ("queue_time_p95_ms",),
        densify=False,
    )
    cluster_cap = horizon_cap(cost_daily_table, cluster_conditions)
    cpu_util_cap = horizon_cap(efficiency_daily_table, cluster_conditions)
    job_cap = horizon_cap(job_cluster_cost_daily_table)
    pipeline_cap = horizon_cap(pipeline_cost_daily_table)
    warehouse_cap = horizon_cap(warehouse_cost_daily_table)
    warehouse_query_cap = horizon_cap(warehouse_query_performance_daily_table)

    # Une borne de plausibilite par passe, sur la meme source et la meme
    # fenetre que l'historique d'entrainement correspondant.
    cluster_bounds = bounds(
        cost_daily_table,
        cluster_key,
        ("cost_usd", "dbu_quantity"),
        densify=True,
        extra_conditions=cluster_conditions,
    )
    job_bounds = bounds(
        job_cluster_cost_daily_table, job_key, ("cost_usd", "dbu_quantity"), densify=True
    )
    pipeline_bounds = bounds(
        pipeline_cost_daily_table, pipeline_key, ("cost_usd", "dbu_quantity"), densify=True
    )
    warehouse_bounds = bounds(
        warehouse_cost_daily_table, warehouse_key, ("cost_usd", "dbu_quantity"), densify=True
    )
    query_count_bounds = bounds(
        warehouse_query_performance_daily_table, warehouse_key, ("query_count",), densify=True
    )
    queue_time_bounds = bounds(
        warehouse_query_performance_daily_table,
        warehouse_key,
        ("queue_time_p95_ms",),
        densify=False,
    )

    # (CTE de prevision, CTE de bornes, object_type, metrique). Une branche
    # d'unpivot par couple : `ai_forecast` rend une colonne par metrique
    # (`{metrique}_forecast`/`_lower`/`_upper`), la table une ligne. Une CTE de
    # bornes a `None` signale un plafond ABSOLU (pourcentage), qui n'a besoin
    # d'aucune lecture supplementaire de la source.
    unpivot_passes: tuple[tuple[str, str | None, str, str], ...] = (
        ("cost_and_dbu_forecast", "cluster_bounds", "CLUSTER", "cost_usd"),
        ("cost_and_dbu_forecast", "cluster_bounds", "CLUSTER", "dbu_quantity"),
        ("cpu_util_forecast", None, "CLUSTER", "cpu_util_p95_pct"),
        ("job_cost_and_dbu_forecast", "job_bounds", "JOB", "cost_usd"),
        ("job_cost_and_dbu_forecast", "job_bounds", "JOB", "dbu_quantity"),
        ("pipeline_cost_and_dbu_forecast", "pipeline_bounds", "PIPELINE", "cost_usd"),
        ("pipeline_cost_and_dbu_forecast", "pipeline_bounds", "PIPELINE", "dbu_quantity"),
        ("warehouse_cost_and_dbu_forecast", "warehouse_bounds", "WAREHOUSE", "cost_usd"),
        ("warehouse_cost_and_dbu_forecast", "warehouse_bounds", "WAREHOUSE", "dbu_quantity"),
        ("warehouse_query_count_forecast", "query_count_bounds", "WAREHOUSE", "query_count"),
        (
            "warehouse_queue_time_forecast",
            "queue_time_bounds",
            "WAREHOUSE",
            "queue_time_p95_ms",
        ),
    )
    unpivoted = "\n\n        UNION ALL\n\n".join(
        f"""        SELECT
            {_split_object_key_columns("f")},
            '{object_type}' AS object_type,
            f.period_start AS horizon_date,
            '{metric}' AS metric_name,
            f.{metric}_forecast AS predicted_value,
            f.{metric}_lower AS lower_bound,
            f.{metric}_upper AS upper_bound,
            {
            f"b.{metric}_max * {max_observed_ratio}"
            if bounds_cte
            else _PERCENTAGE_CEILING
        } AS max_plausible_value
        FROM {forecast_cte} f{
            f"\n        JOIN {bounds_cte} b ON b.object_key = f.object_key" if bounds_cte else ""
        }"""
        for forecast_cte, bounds_cte, object_type, metric in unpivot_passes
    )

    return f"""
    WITH cluster_bounds AS ({cluster_bounds}
    ),
    job_bounds AS ({job_bounds}
    ),
    pipeline_bounds AS ({pipeline_bounds}
    ),
    warehouse_bounds AS ({warehouse_bounds}
    ),
    query_count_bounds AS ({query_count_bounds}
    ),
    queue_time_bounds AS ({queue_time_bounds}
    ),
    cost_and_dbu_forecast AS (
        SELECT * FROM ai_forecast(
            observed => TABLE({cluster_observed}
            ),
            horizon => DATE '{horizon_date.isoformat()}',
            time_col => 'period_start',
            value_col => array('cost_usd', 'dbu_quantity'),
            group_col => 'object_key',
            frequency => 'D',
            prediction_interval_width => {prediction_interval_width},
            parameters => '{_NON_NEGATIVE_FORECAST_PARAMETERS}'
        )
        {cluster_cap}
    ),
    cpu_util_forecast AS (
        SELECT * FROM ai_forecast(
            observed => TABLE({cpu_util_observed}
            ),
            horizon => DATE '{horizon_date.isoformat()}',
            time_col => 'period_start',
            value_col => 'cpu_util_p95_pct',
            group_col => 'object_key',
            frequency => 'D',
            prediction_interval_width => {prediction_interval_width},
            parameters => '{_PERCENTAGE_FORECAST_PARAMETERS}'
        )
        {cpu_util_cap}
    ),
    job_cost_and_dbu_forecast AS (
        SELECT * FROM ai_forecast(
            observed => TABLE({job_observed}
            ),
            horizon => DATE '{horizon_date.isoformat()}',
            time_col => 'period_start',
            value_col => array('cost_usd', 'dbu_quantity'),
            group_col => 'object_key',
            frequency => 'D',
            prediction_interval_width => {prediction_interval_width},
            parameters => '{_NON_NEGATIVE_FORECAST_PARAMETERS}'
        )
        {job_cap}
    ),
    pipeline_cost_and_dbu_forecast AS (
        SELECT * FROM ai_forecast(
            observed => TABLE({pipeline_observed}
            ),
            horizon => DATE '{horizon_date.isoformat()}',
            time_col => 'period_start',
            value_col => array('cost_usd', 'dbu_quantity'),
            group_col => 'object_key',
            frequency => 'D',
            prediction_interval_width => {prediction_interval_width},
            parameters => '{_NON_NEGATIVE_FORECAST_PARAMETERS}'
        )
        {pipeline_cap}
    ),
    warehouse_cost_and_dbu_forecast AS (
        SELECT * FROM ai_forecast(
            observed => TABLE({warehouse_observed}
            ),
            horizon => DATE '{horizon_date.isoformat()}',
            time_col => 'period_start',
            value_col => array('cost_usd', 'dbu_quantity'),
            group_col => 'object_key',
            frequency => 'D',
            prediction_interval_width => {prediction_interval_width},
            parameters => '{_NON_NEGATIVE_FORECAST_PARAMETERS}'
        )
        {warehouse_cap}
    ),
    warehouse_query_count_forecast AS (
        SELECT * FROM ai_forecast(
            observed => TABLE({query_count_observed}
            ),
            horizon => DATE '{horizon_date.isoformat()}',
            time_col => 'period_start',
            value_col => 'query_count',
            group_col => 'object_key',
            frequency => 'D',
            prediction_interval_width => {prediction_interval_width},
            parameters => '{_NON_NEGATIVE_FORECAST_PARAMETERS}'
        )
        {warehouse_query_cap}
    ),
    warehouse_queue_time_forecast AS (
        SELECT * FROM ai_forecast(
            observed => TABLE({queue_time_observed}
            ),
            horizon => DATE '{horizon_date.isoformat()}',
            time_col => 'period_start',
            value_col => 'queue_time_p95_ms',
            group_col => 'object_key',
            frequency => 'D',
            prediction_interval_width => {prediction_interval_width},
            parameters => '{_NON_NEGATIVE_FORECAST_PARAMETERS}'
        )
        {warehouse_query_cap}
    ),
    unpivoted AS (
{unpivoted}
    )
    SELECT
        cloud_provider,
        workspace_id,
        object_type,
        object_id,
        metric_name,
        horizon_date,
        predicted_value,
        lower_bound,
        {_CLIPPED_UPPER_BOUND},
        'ai_forecast' AS method
    FROM unpivoted
    WHERE predicted_value IS NOT NULL
      AND predicted_value <= max_plausible_value
    """


def _fetch_external_link_rows(link: ExternalLink) -> list[list[Any]]:
    """Telecharge et parse un chunk `EXTERNAL_LINKS` (cf. `_execute_statement`).

    L'URL pre-signee (`link.external_link`) sert directement le contenu du
    chunk (ici un tableau JSON, `format=Format.JSON_ARRAY`) : simple GET HTTP,
    sans authentification Databricks (le lien porte sa propre credential
    temporaire, cf. doc `ExternalLink.external_link`). `link.http_headers`
    est vide dans ce cas (pas de cle de dechiffrement a transmettre) mais
    transmis par prudence si jamais present.
    """
    import requests

    resp = requests.get(link.external_link, headers=link.http_headers or {}, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _execute_statement(warehouse_id: str, query: str, profile: str | None) -> list[list[Any]]:
    """Execute `query` sur un SQL Warehouse et renvoie les lignes brutes.

    `ai_forecast` exige un Pro/Serverless SQL Warehouse (doc officielle
    Databricks) - incompatible avec l'environnement serverless generique du
    job (cf. docstring module). Poll jusqu'a l'etat terminal : le
    `wait_timeout` max de l'API (50s) est souvent insuffisant pour
    l'ajustement de modele `ai_forecast`. `profile` est `None` sur cluster
    (authentification native au contexte du job) ou le profil CLI de debug
    local (cf. `pipelines.common.runtime.LOCAL_DEBUG_PROFILE`), meme
    convention que `pipelines.common.runtime.LocalDebugSecrets`.

    `disposition=EXTERNAL_LINKS` (pas `INLINE`) : le volume reel (parc
    `cluster_id`/`warehouse_id` complet, 2 metriques par passe) peut depasser
    la limite de 25 MiB de `INLINE` ; `EXTERNAL_LINKS` n'a pas de limite de
    taille comparable (chaque chunk est telecharge separement via une URL
    pre-signee, cf. `_fetch_external_link_rows`).
    """
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.sql import Disposition, Format, StatementState

    workspace = WorkspaceClient(profile=profile) if profile else WorkspaceClient()
    response = workspace.statement_execution.execute_statement(
        warehouse_id=warehouse_id,
        statement=query,
        wait_timeout="50s",
        format=Format.JSON_ARRAY,
        disposition=Disposition.EXTERNAL_LINKS,
    )
    statement_id = response.statement_id
    while response.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(_STATEMENT_POLL_INTERVAL_SECONDS)
        response = workspace.statement_execution.get_statement(statement_id)
    if response.status.state != StatementState.SUCCEEDED:
        error = response.status.error
        message = error.message if error else str(response.status.state)
        raise RuntimeError(f"ai_forecast statement {response.status.state} : {message}")
    if response.result is None or not response.result.external_links:
        return []
    rows: list[list[Any]] = []
    links = list(response.result.external_links)
    seen_chunk_indexes = {link.chunk_index for link in links}
    while links:
        link = links.pop(0)
        rows.extend(_fetch_external_link_rows(link))
        next_index = link.next_chunk_index
        if next_index is not None and next_index not in seen_chunk_indexes:
            seen_chunk_indexes.add(next_index)
            chunk = workspace.statement_execution.get_statement_result_chunk_n(
                statement_id, next_index
            )
            links.extend(chunk.external_links or [])
    return rows


def _coerce_forecast_row(row: list[Any]) -> tuple[Any, ...]:
    """Convertit une ligne brute (chaines JSON) vers les types Python attendus.

    L'API Statement Execution (format JSON_ARRAY) renvoie TOUTES les valeurs
    comme des chaines, quel que soit leur type SQL declare - reconversion
    explicite necessaire avant `spark.createDataFrame(..., _FORECAST_RESULT_SCHEMA)`.
    Un NULL source reste `None` (jamais de valeur fabriquee).
    """
    (
        cloud_provider,
        workspace_id,
        object_type,
        object_id,
        metric_name,
        horizon_date_str,
        predicted_value,
        lower_bound,
        upper_bound,
        method,
    ) = row
    return (
        cloud_provider,
        workspace_id,
        object_type,
        object_id,
        metric_name,
        date.fromisoformat(horizon_date_str) if horizon_date_str else None,
        float(predicted_value) if predicted_value is not None else None,
        float(lower_bound) if lower_bound is not None else None,
        float(upper_bound) if upper_bound is not None else None,
        method,
    )


def build_compute_forecast(
    spark: SparkSession,
    *,
    warehouse_id: str,
    cost_daily_table: str,
    efficiency_daily_table: str,
    job_cluster_cost_daily_table: str,
    pipeline_cost_daily_table: str,
    warehouse_cost_daily_table: str,
    warehouse_query_performance_daily_table: str,
    observed_lower_bound: date,
    horizon_date: date,
    horizon_days: int,
    prediction_interval_width: float = 0.95,
    min_observed_days: int = 3,
    max_observed_ratio: float = 10.0,
    profile: str | None = None,
) -> DataFrame:
    """Construit `gold_dbx_compute_forecast_daily` (clusters, jobs, pipelines, warehouses).

    `ai_forecast` exige un Pro/Serverless SQL Warehouse (doc officielle
    Databricks) - un environnement serverless generique de job
    (`SparkSession.builder.getOrCreate()`) n'en est pas un. Le texte SQL
    (`render_forecast_query`, fonction pure) est donc execute via l'API
    Statement Execution contre `warehouse_id`, et le resultat est reintegre en
    DataFrame Spark pour rester compatible avec `merge_into_table` (Spark
    natif) sans changement en aval. `_generated_at` est ajoute apres coup via
    `current_timestamp()` (Spark natif sur le DataFrame reconstruit), pas par
    la requete executee sur le warehouse.

    Args:
        spark: session Spark du job - utilisee uniquement pour reconstruire le
            DataFrame final (`createDataFrame`) et y ajouter `_generated_at`,
            jamais pour executer `ai_forecast` lui-meme (cf. ci-dessus).
        warehouse_id: identifiant du SQL Warehouse (Pro/Serverless) contre
            lequel `ai_forecast` est execute (`--warehouse_id` du job, cf.
            `entrypoint.py`/`resources/job_dcm_gold_forecast.yml`).
        cost_daily_table: nom qualifie de `gold_dbx_compute_cluster_cost_daily`
            (historique source des metriques `cost_usd`/`dbu_quantity`,
            clusters non-JOB uniquement).
        efficiency_daily_table: nom qualifie de
            `gold_dbx_compute_cluster_efficiency_daily` (historique source de
            `cpu_util_p95_pct`, clusters non-JOB uniquement).
        job_cluster_cost_daily_table: nom qualifie de
            `gold_dbx_compute_job_cluster_cost_daily` (historique source de
            `cost_usd`/`dbu_quantity` au grain job).
        pipeline_cost_daily_table: nom qualifie de
            `gold_dbx_compute_pipeline_cost_daily` (historique source de
            `cost_usd`/`dbu_quantity` au grain `dlt_pipeline_id`).
        warehouse_cost_daily_table: nom qualifie de
            `gold_dbx_compute_warehouse_cost_daily` (historique source de
            `cost_usd`/`dbu_quantity` au grain warehouse).
        warehouse_query_performance_daily_table: nom qualifie de
            `gold_dbx_compute_warehouse_query_performance_daily` (historique
            source des metriques `query_count`/`queue_time_p95_ms`).
        observed_lower_bound: cf. `render_forecast_query`.
        horizon_date: cf. `render_forecast_query`.
        horizon_days: cf. `render_forecast_query`.
        prediction_interval_width: cf. `render_forecast_query`.
        min_observed_days: cf. `render_forecast_query`.
        max_observed_ratio: cf. `render_forecast_query`.
        profile: `None` sur cluster (authentification native au contexte du
            job) ou profil CLI de debug local.

    Returns:
        Le DataFrame de `gold_dbx_compute_forecast_daily` (une ligne par
        `(cloud_provider, object_type, object_id, metric_name, horizon_date)`,
        clusters hors JOB + jobs + pipelines + warehouses) - a passer a
        `merge_into_table`.
    """
    query = render_forecast_query(
        cost_daily_table=cost_daily_table,
        efficiency_daily_table=efficiency_daily_table,
        job_cluster_cost_daily_table=job_cluster_cost_daily_table,
        pipeline_cost_daily_table=pipeline_cost_daily_table,
        warehouse_cost_daily_table=warehouse_cost_daily_table,
        warehouse_query_performance_daily_table=warehouse_query_performance_daily_table,
        observed_lower_bound=observed_lower_bound,
        horizon_date=horizon_date,
        horizon_days=horizon_days,
        prediction_interval_width=prediction_interval_width,
        min_observed_days=min_observed_days,
        max_observed_ratio=max_observed_ratio,
    )
    raw_rows = _execute_statement(warehouse_id, query, profile)
    rows = [_coerce_forecast_row(row) for row in raw_rows]
    df = spark.createDataFrame(rows, schema=_FORECAST_RESULT_SCHEMA)
    return df.withColumn("_generated_at", F.current_timestamp())
