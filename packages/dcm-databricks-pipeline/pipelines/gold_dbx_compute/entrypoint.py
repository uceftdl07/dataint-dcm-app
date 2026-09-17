"""Point d'entree de la tache wheel Gold Compute Clusters (`[project.scripts]`).

Symetrique a `pipelines.system_tables.entrypoint` (meme mecanique : resolution
de la `SparkSession`/des parametres, deux modes cluster/local) mais sans partie
Azure/secrets : ce plugin ne fait QUE lire des tables Unity Catalog deja
qualifiees (curated), jamais de connexion cross-tenant.

Le parametre `--table` selectionne UNE agregation gold du registre
`gold_dbx_compute.specs.GOLD_SPECS` a calculer (valeur `{{input}}` d'une
iteration `for_each` du job). Resout la fenetre de rafraichissement (full au
premier run ; ensuite fenetre incrementale ancree sur la couverture reelle de la
table cible, cf. `pipelines.common.incremental.compute_gap_aware_lower_bound` et
`research.md` R9) puis delegue le calcul aux builders
`pipelines.gold_dbx_compute.cluster_*` et l'ecriture idempotente a
`pipelines.common.writers.merge_into_table`.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from pipelines.common.incremental import compute_gap_aware_lower_bound
from pipelines.common.runtime import (
    LOCAL_DEBUG_PROFILE,
    local_debug_spark,
    on_databricks_cluster,
    parse_named_parameters,
)
from pipelines.common.writers import merge_into_table
from pipelines.gold_dbx_compute.cluster_cost_daily import build_cluster_cost_daily
from pipelines.gold_dbx_compute.cluster_cost_rolling import build_cluster_cost_rolling
from pipelines.gold_dbx_compute.cluster_efficiency_daily import build_cluster_efficiency_daily
from pipelines.gold_dbx_compute.cluster_efficiency_rolling import (
    build_cluster_efficiency_rolling,
)
from pipelines.gold_dbx_compute.cluster_governance import (
    build_cluster_governance,
    dbr_lts_versions_supported_as_of,
)
from pipelines.gold_dbx_compute.cluster_reliability_daily import build_cluster_reliability_daily
from pipelines.gold_dbx_compute.cluster_reliability_rolling import (
    build_cluster_reliability_rolling,
)
from pipelines.gold_dbx_compute.forecast import build_compute_forecast
from pipelines.gold_dbx_compute.job_cluster_cost_daily import build_job_cluster_cost_daily
from pipelines.gold_dbx_compute.job_cluster_cost_rolling import build_job_cluster_cost_rolling
from pipelines.gold_dbx_compute.job_efficiency_daily import build_job_efficiency_daily
from pipelines.gold_dbx_compute.job_efficiency_rolling import build_job_efficiency_rolling
from pipelines.gold_dbx_compute.pipeline_cost_daily import build_pipeline_cost_daily
from pipelines.gold_dbx_compute.pipeline_cost_rolling import build_pipeline_cost_rolling
from pipelines.gold_dbx_compute.pipeline_efficiency_daily import build_pipeline_efficiency_daily
from pipelines.gold_dbx_compute.pipeline_efficiency_rolling import (
    build_pipeline_efficiency_rolling,
)
from pipelines.gold_dbx_compute.pipeline_update_stats import build_pipeline_update_stats
from pipelines.gold_dbx_compute.recommendations import build_compute_recommendations
from pipelines.gold_dbx_compute.serverless_cost_daily import build_serverless_cost_daily
from pipelines.gold_dbx_compute.serverless_cost_rolling import build_serverless_cost_rolling
from pipelines.gold_dbx_compute.serverless_governance import build_serverless_governance
from pipelines.gold_dbx_compute.specs import (
    DEFAULT_CATALOG,
    DEFAULT_SCHEMA,
    FORECAST_HORIZON_DAYS,
    FORECAST_MAX_OBSERVED_RATIO,
    FORECAST_MIN_OBSERVED_DAYS,
    FORECAST_OBSERVED_LOOKBACK_DAYS,
    FORECAST_PREDICTION_INTERVAL_WIDTH,
    GOLD_CLUSTER_COST_DAILY,
    GOLD_CLUSTER_COST_ROLLING,
    GOLD_CLUSTER_EFFICIENCY_DAILY,
    GOLD_CLUSTER_EFFICIENCY_ROLLING,
    GOLD_CLUSTER_GOVERNANCE,
    GOLD_CLUSTER_RELIABILITY_DAILY,
    GOLD_CLUSTER_RELIABILITY_ROLLING,
    GOLD_JOB_CLUSTER_COST_DAILY,
    GOLD_JOB_EFFICIENCY_DAILY,
    GOLD_PIPELINE_COST_DAILY,
    GOLD_PIPELINE_EFFICIENCY_DAILY,
    GOLD_RECOMMENDATIONS,
    GOLD_SERVERLESS_COST_DAILY,
    GOLD_SPECS,
    GOLD_WAREHOUSE_COST_DAILY,
    GOLD_WAREHOUSE_COST_ROLLING,
    GOLD_WAREHOUSE_QUERY_PERFORMANCE_DAILY,
    GOLD_WAREHOUSE_QUERY_PERFORMANCE_ROLLING,
    GOLD_WAREHOUSE_UTILIZATION_DAILY,
    GOLD_WAREHOUSE_UTILIZATION_ROLLING,
    GOVERNANCE_ACTIVITY_WINDOW_DAYS,
)
from pipelines.gold_dbx_compute.total_cost_daily import build_total_cost_daily
from pipelines.gold_dbx_compute.warehouse_cost_daily import build_warehouse_cost_daily
from pipelines.gold_dbx_compute.warehouse_cost_rolling import build_warehouse_cost_rolling
from pipelines.gold_dbx_compute.warehouse_query_performance_daily import (
    build_warehouse_query_performance_daily,
)
from pipelines.gold_dbx_compute.warehouse_query_performance_rolling import (
    build_warehouse_query_performance_rolling,
)
from pipelines.gold_dbx_compute.warehouse_utilization_daily import build_warehouse_utilization_daily
from pipelines.gold_dbx_compute.warehouse_utilization_rolling import (
    build_warehouse_utilization_rolling,
)
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
)

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

    from pipelines.gold_dbx_compute.specs import GoldAggregationSpec

# Parametres nommes passes par la tache `python_wheel_task` (named_parameters).
# Aucun secret : ce plugin ne lit que des tables Unity Catalog deja qualifiees.
# `warehouse_id` : uniquement requis pour `table=forecast_daily` (`ai_forecast`
# exige un Pro/Serverless SQL Warehouse, incompatible avec l'environnement
# serverless generique de ce job, cf. `pipelines.gold_dbx_compute.forecast`) ;
# vide/ignore pour les autres tables.
# `one_off_purge` : levier de REPARATION PONCTUELLE, cf. `_apply_one_off_purge`.
# Volontairement ABSENT de `resources/job_dcm_gold_dbx_compute.yml` : aucune
# tache planifiee ne doit pouvoir le porter, meme a vide. Il n'existe que pour
# un run declenche a la main.
PARAM_NAMES = ("table", "catalog", "schema", "full_refresh", "warehouse_id", "one_off_purge")

# Colonne d'horodatage d'ecriture, presente sur TOUTES les tables gold de ce
# plugin (`current_timestamp() AS _generated_at` dans chaque builder) : permet a
# `compute_gap_aware_lower_bound` de reperer les jours ecrits trop tot pour
# avoir absorbe les arrivees tardives de la couche curated.
GENERATED_AT_COLUMN = "_generated_at"

_LOGGER = logging.getLogger(__name__)


def _qualify(catalog: str, schema: str, table_name: str) -> str:
    """Qualifie un nom de table curated/gold avec `catalog.schema`."""
    return f"{catalog}.{schema}.{table_name}"


def _resolve_lower_bound(
    spark: SparkSession,
    spec: GoldAggregationSpec,
    qualified_target_table: str,
    *,
    full_refresh: bool,
    today: date,
) -> date | None:
    """Resout la borne basse de lecture curated (fenetre de rafraichissement).

    `None` (full) quand :
      - la spec n'a pas de watermark (`governance`, snapshot toujours recalcule) ;
      - `--full-refresh` explicite ;
      - la table gold cible n'existe pas encore (tout premier run : agrege tout
        l'historique curated disponible, cf. `research.md` R9).

    Sinon, la borne est ancree sur la COUVERTURE REELLE de la table gold cible
    (`compute_gap_aware_lower_bound`), pas sur le seul `today -
    incremental_lookback_days` : une fenetre calee sur `today` perd
    definitivement tout jour qu'aucun run n'a couvert dans sa fenetre (run non
    declenche/en echec, curated en retard). Cette resolution est commune a
    TOUTES les tables du registre `GOLD_SPECS` : aucun builder n'a a s'en
    preoccuper.
    """
    if spec.watermark_column is None:
        return None
    if full_refresh or not spark.catalog.tableExists(qualified_target_table):
        return None
    lower_bound = compute_gap_aware_lower_bound(
        spark,
        target_table=qualified_target_table,
        watermark_column=spec.watermark_column,
        lookback_days=spec.incremental_lookback_days or 0,
        today=today,
        generated_at_column=GENERATED_AT_COLUMN,
    )
    nominal_bound = today - timedelta(days=spec.incremental_lookback_days or 0)
    if lower_bound < nominal_bound:
        _LOGGER.info(
            "%s : trou/jour non stabilise detecte, fenetre elargie a %s >= %s "
            "(fenetre nominale : %s).",
            qualified_target_table,
            spec.watermark_column,
            lower_bound.isoformat(),
            nominal_bound.isoformat(),
        )
    else:
        _LOGGER.info(
            "%s : fenetre incrementale %s >= %s.",
            qualified_target_table,
            spec.watermark_column,
            lower_bound.isoformat(),
        )
    return lower_bound


def _source_watermark_floor(df: DataFrame, watermark_column: str) -> date | None:
    """Plus petite valeur de `watermark_column` REELLEMENT produite par `df`.

    Sert de borne de suppression quand la fenetre est `full` (`lower_bound` a
    `None` : premier run ou `--full-refresh`), cas ou le recalcul ne s'arrete pas
    a une date connue d'avance mais a la couverture de la source curated. Prendre
    le `MIN` de la SORTIE et non celui de la cible est ce qui protege l'historique
    gold plus ancien que cette couverture : ces jours-la, le recalcul ne dit rien,
    il n'a donc pas a les supprimer.

    `None` (aucune suppression, cf. `resolve_absent_row_delete_predicate`) si la
    sortie est vide : c'est le cas d'un run degrade, exactement celui qu'il ne
    faut pas laisser vider la table.

    Cout : une action Spark de plus sur le plan du builder, donc une evaluation
    supplementaire de sa requete. Volontairement limitee au mode full (rare,
    declenche a la main) et aux seules specs qui activent la suppression.
    """
    rows = df.selectExpr(f"MIN({watermark_column}) AS window_floor").collect()
    floor = rows[0][0] if rows else None
    return floor.date() if isinstance(floor, datetime) else floor


def _boolean_param(params: dict[str, str], name: str) -> bool:
    """Lit un parametre nomme booleen : absent ou vide = faux.

    Les `named_parameters` d'une tache wheel sont TOUJOURS des chaines, et une
    reference `{{job.parameters.x}}` non fournie arrive comme chaine vide : le
    defaut doit donc etre faux, jamais une erreur.
    """
    return params.get(name, "").strip().lower() in {"1", "true", "yes"}


def _apply_one_off_purge(
    spec: GoldAggregationSpec, *, full_refresh: bool, run_started_at: datetime
) -> GoldAggregationSpec:
    """Arme la suppression des lignes absentes POUR CE RUN UNIQUEMENT.

    A utiliser apres un changement de POPULATION d'un builder (un filtre ajoute,
    ex. le predicat `billing_origin_product` de T001c) : le recalcul corrige les
    valeurs des lignes qu'il produit encore, mais laisse en base les lignes que
    la nouvelle definition ne produit plus. Un `MERGE` en upsert pur ne supprime
    rien.

    Pourquoi un parametre de run et pas `absent_row_delete_guard` dans la spec :
    la spec est le REGIME PERMANENT. Y poser le garde-fou signifierait que cette
    table accepte definitivement de perdre un jour deja ecrit des qu'un run est
    degrade -- exactement ce que le commentaire de
    `WAREHOUSE_UTILIZATION_DAILY_SPEC` interdit d'etendre aux `*_daily` qui
    agregent la facturation. Ici rien n'est persiste : le run suivant, sans le
    parametre, est de nouveau en upsert pur. Le retour au regime permanent est
    donc l'ETAT PAR DEFAUT, il n'y a rien a retirer ensuite.

    Trois refus explicites, tous fail-fast (un run qui echoue est reparable, une
    purge partielle silencieuse ne se voit pas) :
      - sans `full_refresh` : la suppression est bornee a la fenetre recalculee
        (`resolve_absent_row_delete_predicate`), soit `INCREMENTAL_LOOKBACK_DAYS`
        = 10 jours. Elle ne toucherait donc pas les 2 ans d'historique a
        nettoyer, tout en RAPPORTANT un succes.
      - spec sans `watermark_column` : rien ne borne alors la suppression, qui
        s'appliquerait a toute la table -- un builder degrade la viderait.
      - spec portant DEJA un garde-fou : elle se nettoie toute seule en regime
        permanent ; l'ecraser remplacerait sa grace volumetrique par ce seuil de
        run, donc changerait la semantique d'une table qui n'a rien demande.

    Garde-fou injecte : `_generated_at < <debut du run>` et non la grace
    volumetrique de 7 jours (`SNAPSHOT_ABSENT_ROW_GRACE_DAYS`). Mesure dev du
    2026-09-10 : `pipeline_cost_daily` n'a qu'UNE valeur de `_generated_at`
    (2026-09-09), `cluster_cost_daily` en a 5 entre le 2026-08-30 et le
    2026-09-09. La grace de 7 jours ne supprimerait donc rien sur la premiere et
    seulement la fraction ecrite avant J-7 sur la seconde : une purge partielle,
    presentee comme reussie. Le seuil "debut du run" cible exactement les lignes
    ecrites AVANT ce run, c'est-a-dire les orphelines.
    L'horodatage est ancre en UTC (`+00:00`) et non laisse a la timezone de
    session : `_generated_at` vient de `current_timestamp()`, comparer les deux
    via un litteral sans zone dependrait du reglage du warehouse.

    Filets de securite conserves : la suppression reste bornee par le `MIN` du
    watermark REELLEMENT produit par le builder (`_source_watermark_floor`), et
    une sortie vide annule la suppression au lieu de vider la table
    (`_absent_row_delete_predicate`). Rien n'est irreversible non plus : ces
    tables gold sont integralement recalculables depuis la couche curated, et le
    `MERGE` est une version Delta (time travel).

    Tracabilite : ce warning dans les logs de la tache, et `DESCRIBE HISTORY
    <table gold>` qui donne le compte exact
    (`operationMetrics.numTargetRowsDeleted`) de la version produite. ATTENTION :
    un run soumis par `databricks jobs submit` n'est PAS enregistre comme job et
    n'apparait pas dans la liste de l'IHM (verifie, CLI v1.10.0) : la trace qui
    fait foi est la version Delta, pas une page de job.

    Procedure operateur (aucune modification du bundle, run a la main) :
      1. `databricks jobs get <job_id> -p <profil OAuth>` pour recuperer le
         `python_wheel_task` + `environments` deja deployes de la tache visee ;
      2. resoumettre ce meme spec en run unique via `databricks jobs submit`, en
         ajoutant `one_off_purge: "true"` et `full_refresh: "true"` aux
         `named_parameters` ;
      3. relire `numTargetRowsDeleted` dans `DESCRIBE HISTORY`, puis relancer les
         tables aval (cf. rapport T001c pour l'ordre).
    """
    if not full_refresh:
        raise ValueError(
            "'one_off_purge' exige 'full_refresh' : sans lui la suppression est bornee "
            "a la fenetre incrementale (10 jours) et laisserait tout l'historique "
            "anterieur non nettoye en rapportant un succes."
        )
    if spec.watermark_column is None:
        raise ValueError(
            f"'one_off_purge' refuse pour '{spec.target_table}' : sans watermark_column, "
            "aucune borne ne limite la suppression et un recalcul degrade viderait la "
            "table entiere."
        )
    if spec.absent_row_delete_guard is not None:
        raise ValueError(
            f"'one_off_purge' refuse pour '{spec.target_table}' : cette spec supprime "
            "deja les lignes absentes en regime permanent ; l'ecraser changerait sa "
            "semantique au lieu de reparer quoi que ce soit."
        )
    cutoff = f"{run_started_at.strftime('%Y-%m-%d %H:%M:%S')}+00:00"
    guard = f"t.{GENERATED_AT_COLUMN} < TIMESTAMP '{cutoff}'"
    _LOGGER.warning(
        "%s : PURGE PONCTUELLE armee pour ce run (one_off_purge). Les lignes que le "
        "recalcul complet ne produit plus et ecrites avant %s seront SUPPRIMEES "
        "(garde-fou : %s). Rien n'est persiste : le run suivant repasse en upsert pur.",
        spec.target_table,
        cutoff,
        guard,
    )
    return replace(spec, absent_row_delete_guard=guard)


def _absent_row_delete_predicate(
    spec: GoldAggregationSpec, df: DataFrame, *, lower_bound: date | None
) -> str | None:
    """Predicat `WHEN NOT MATCHED BY SOURCE ... THEN DELETE` du run courant.

    Unique point de passage : la spec ne porte que le garde-fou volumetrique, la
    borne de fenetre est ajoutee ici (cf.
    `GoldAggregationSpec.resolve_absent_row_delete_predicate`). En incremental la
    borne est la fenetre deja resolue ; en full elle est lue sur la sortie du
    builder — et ce `MIN` n'est calcule que si une suppression est effectivement
    demandee, pour ne rien couter aux specs en upsert pur.

    Sur une spec SANS `watermark_column` (snapshots `*_rolling`/`governance`,
    `forecast_daily`), le garde-fou est le predicat complet : rien ne borne la
    suppression, donc une sortie vide supprimerait tout ce que le garde-fou
    laisse passer. D'ou la verification d'emptiness ici — le pendant de ce que
    `_source_watermark_floor` fait deja pour les tables a watermark, avec le
    meme cout (une action Spark, uniquement pour les specs qui suppriment).
    """
    if spec.absent_row_delete_guard is not None and spec.watermark_column is None and df.isEmpty():
        _LOGGER.warning(
            "%s : suppression des lignes absentes DESACTIVEE pour ce run (sortie du "
            "builder vide : un run degrade ne doit pas vider la table).",
            spec.target_table,
        )
        return None
    window_floor = lower_bound
    if (
        window_floor is None
        and spec.absent_row_delete_guard is not None
        and spec.watermark_column is not None
    ):
        window_floor = _source_watermark_floor(df, spec.watermark_column)
    predicate = spec.resolve_absent_row_delete_predicate(window_floor=window_floor)
    if spec.absent_row_delete_guard is not None and predicate is None:
        _LOGGER.warning(
            "%s : suppression des lignes absentes DESACTIVEE pour ce run "
            "(aucune borne de fenetre sur %s : sortie du builder vide ?).",
            spec.target_table,
            spec.watermark_column,
        )
    return predicate


def main(spark: Any, params: dict[str, str], *, profile: str | None = None) -> None:  # noqa: ANN401
    """Orchestration : calcule et ecrit la table gold selectionnee par `--table`.

    Fonction testable sans cluster reel (spark peut etre un fake enregistrant
    les appels `sql()`). Qualifie les tables via `catalog`/`schema` (vars bundle,
    differentes par target) : sans qualification, l'ecriture irait dans le
    catalog/schema par defaut de la session au lieu de la cible Unity Catalog
    (meme garde-fou que `pipelines.system_tables.entrypoint.main`).

    `profile` : `None` sur cluster (authentification native au contexte du
    job) ou profil CLI de debug local - transmis uniquement a `forecast_daily`
    (`ai_forecast` execute via un SQL Warehouse, cf.
    `pipelines.gold_dbx_compute.forecast`), ignore par les autres builders.
    """
    catalog = params["catalog"].strip()
    schema = params["schema"].strip()
    if not catalog or not schema:
        raise ValueError(
            "Les parametres 'catalog' et 'schema' sont requis pour qualifier les "
            "tables gold/curated (sinon ecriture dans le catalog/schema par defaut "
            "de la session au lieu de la cible Unity Catalog)."
        )
    table = params["table"].strip()
    if table not in GOLD_SPECS:
        known = ", ".join(GOLD_SPECS)
        raise ValueError(f"Table gold inconnue '{table}' ; valeurs attendues : {known}.")
    spec = GOLD_SPECS[table]
    full_refresh = _boolean_param(params, "full_refresh")
    warehouse_id = params.get("warehouse_id", "").strip()
    if table == "forecast_daily" and not warehouse_id:
        raise ValueError(
            "Le parametre 'warehouse_id' est requis pour 'forecast_daily' (ai_forecast "
            "exige un Pro/Serverless SQL Warehouse, incompatible avec l'environnement "
            "serverless generique de ce job)."
        )
    # Un seul instant de reference pour tout le run : `today` (fenetre) et le
    # seuil de purge ponctuelle doivent venir du meme appel, sinon un run qui
    # traverse minuit UTC melangerait deux jours.
    run_started_at = datetime.now(UTC)
    today = run_started_at.date()
    if _boolean_param(params, "one_off_purge"):
        # Ne modifie PAS `GOLD_SPECS` : `replace` sur une dataclass frozen rend
        # une copie, portee au seul run courant.
        spec = _apply_one_off_purge(spec, full_refresh=full_refresh, run_started_at=run_started_at)
    qualified_target_table = _qualify(catalog, schema, spec.target_table)

    lower_bound = _resolve_lower_bound(
        spark, spec, qualified_target_table, full_refresh=full_refresh, today=today
    )

    # Registre de dispatch : cle du registre `GOLD_SPECS` -> fonction de calcul.
    # Nouvelles tables gold AJOUTENT une entree ici, sans modifier les entrees
    # existantes (cf. merge-strategy.md).
    builders: dict[str, Callable[[], DataFrame]] = {
        "cluster_cost_daily": lambda: build_cluster_cost_daily(
            spark,
            billing_usage_table=_qualify(catalog, schema, CURATED_BILLING_USAGE),
            billing_list_prices_table=_qualify(catalog, schema, CURATED_BILLING_LIST_PRICES),
            clusters_table=_qualify(catalog, schema, CURATED_COMPUTE_CLUSTERS),
            lower_bound=lower_bound,
        ),
        "cluster_cost_rolling": lambda: build_cluster_cost_rolling(
            spark,
            cluster_cost_daily_table=_qualify(catalog, schema, GOLD_CLUSTER_COST_DAILY),
        ),
        "cluster_efficiency_daily": lambda: build_cluster_efficiency_daily(
            spark,
            node_timeline_table=_qualify(catalog, schema, CURATED_COMPUTE_NODE_TIMELINE),
            clusters_table=_qualify(catalog, schema, CURATED_COMPUTE_CLUSTERS),
            node_types_table=_qualify(catalog, schema, CURATED_COMPUTE_NODE_TYPES),
            job_task_run_timeline_table=_qualify(
                catalog, schema, CURATED_LAKEFLOW_JOB_TASK_RUN_TIMELINE
            ),
            cost_daily_table=_qualify(catalog, schema, GOLD_CLUSTER_COST_DAILY),
            lower_bound=lower_bound,
        ),
        "cluster_efficiency_rolling": lambda: build_cluster_efficiency_rolling(
            spark,
            cluster_efficiency_daily_table=_qualify(
                catalog, schema, GOLD_CLUSTER_EFFICIENCY_DAILY
            ),
        ),
        "cluster_reliability_daily": lambda: build_cluster_reliability_daily(
            spark,
            clusters_table=_qualify(catalog, schema, CURATED_COMPUTE_CLUSTERS),
            access_audit_table=_qualify(catalog, schema, CURATED_ACCESS_AUDIT),
            lower_bound=lower_bound,
        ),
        "cluster_reliability_rolling": lambda: build_cluster_reliability_rolling(
            spark,
            cluster_reliability_daily_table=_qualify(
                catalog, schema, GOLD_CLUSTER_RELIABILITY_DAILY
            ),
        ),
        "cluster_governance": lambda: build_cluster_governance(
            spark,
            clusters_table=_qualify(catalog, schema, CURATED_COMPUTE_CLUSTERS),
            efficiency_daily_table=_qualify(catalog, schema, GOLD_CLUSTER_EFFICIENCY_DAILY),
            dbr_lts_versions=dbr_lts_versions_supported_as_of(today),
            activity_lower_bound=today - timedelta(days=GOVERNANCE_ACTIVITY_WINDOW_DAYS),
        ),
        # Rollup BILLING-DIRECT depuis T001b : lit la facturation curated
        # (`usage_metadata.job_id`), plus `cluster_cost_daily` ni la lignee
        # `job_task_run_timeline` -- seul le NOM du job reste resolu depuis
        # lakeflow. C'est ce qui fait entrer le cout des jobs serverless.
        "job_cluster_cost_daily": lambda: build_job_cluster_cost_daily(
            spark,
            billing_usage_table=_qualify(catalog, schema, CURATED_BILLING_USAGE),
            billing_list_prices_table=_qualify(catalog, schema, CURATED_BILLING_LIST_PRICES),
            job_run_timeline_table=_qualify(
                catalog, schema, CURATED_LAKEFLOW_JOB_RUN_TIMELINE
            ),
            lakeflow_jobs_table=_qualify(catalog, schema, CURATED_LAKEFLOW_JOBS),
            lower_bound=lower_bound,
        ),
        "job_cluster_cost_rolling": lambda: build_job_cluster_cost_rolling(
            spark,
            job_cluster_cost_daily_table=_qualify(catalog, schema, GOLD_JOB_CLUSTER_COST_DAILY),
        ),
        "pipeline_cost_daily": lambda: build_pipeline_cost_daily(
            spark,
            billing_usage_table=_qualify(catalog, schema, CURATED_BILLING_USAGE),
            billing_list_prices_table=_qualify(catalog, schema, CURATED_BILLING_LIST_PRICES),
            lakeflow_pipelines_table=_qualify(catalog, schema, CURATED_LAKEFLOW_PIPELINES),
            lower_bound=lower_bound,
        ),
        "pipeline_cost_rolling": lambda: build_pipeline_cost_rolling(
            spark,
            pipeline_cost_daily_table=_qualify(catalog, schema, GOLD_PIPELINE_COST_DAILY),
        ),
        # Efficacite par job/pipeline : source `cluster_efficiency_daily` (JAMAIS
        # filtree sur ALL_PURPOSE, cf. docstrings des builders) + la MEME
        # resolution de grain que les rollups de cout ci-dessus
        # (`grain_resolution`), pour que cout et efficacite ne puissent pas
        # rattacher un meme cluster a deux jobs/pipelines differents.
        "job_efficiency_daily": lambda: build_job_efficiency_daily(
            spark,
            cluster_efficiency_daily_table=_qualify(
                catalog, schema, GOLD_CLUSTER_EFFICIENCY_DAILY
            ),
            job_task_run_timeline_table=_qualify(
                catalog, schema, CURATED_LAKEFLOW_JOB_TASK_RUN_TIMELINE
            ),
            job_run_timeline_table=_qualify(catalog, schema, CURATED_LAKEFLOW_JOB_RUN_TIMELINE),
            lakeflow_jobs_table=_qualify(catalog, schema, CURATED_LAKEFLOW_JOBS),
            lower_bound=lower_bound,
        ),
        "job_efficiency_rolling": lambda: build_job_efficiency_rolling(
            spark,
            job_efficiency_daily_table=_qualify(catalog, schema, GOLD_JOB_EFFICIENCY_DAILY),
        ),
        "pipeline_efficiency_daily": lambda: build_pipeline_efficiency_daily(
            spark,
            cluster_efficiency_daily_table=_qualify(
                catalog, schema, GOLD_CLUSTER_EFFICIENCY_DAILY
            ),
            billing_usage_table=_qualify(catalog, schema, CURATED_BILLING_USAGE),
            lakeflow_pipelines_table=_qualify(catalog, schema, CURATED_LAKEFLOW_PIPELINES),
            lower_bound=lower_bound,
        ),
        "pipeline_efficiency_rolling": lambda: build_pipeline_efficiency_rolling(
            spark,
            pipeline_efficiency_daily_table=_qualify(
                catalog, schema, GOLD_PIPELINE_EFFICIENCY_DAILY
            ),
        ),
        "warehouse_cost_daily": lambda: build_warehouse_cost_daily(
            spark,
            billing_usage_table=_qualify(catalog, schema, CURATED_BILLING_USAGE),
            billing_list_prices_table=_qualify(catalog, schema, CURATED_BILLING_LIST_PRICES),
            warehouses_table=_qualify(catalog, schema, CURATED_COMPUTE_WAREHOUSES),
            query_history_table=_qualify(catalog, schema, CURATED_QUERY_HISTORY),
            lower_bound=lower_bound,
        ),
        "warehouse_cost_rolling": lambda: build_warehouse_cost_rolling(
            spark,
            warehouse_cost_daily_table=_qualify(catalog, schema, GOLD_WAREHOUSE_COST_DAILY),
        ),
        "warehouse_utilization_daily": lambda: build_warehouse_utilization_daily(
            spark,
            warehouse_events_table=_qualify(catalog, schema, CURATED_COMPUTE_WAREHOUSE_EVENTS),
            warehouses_table=_qualify(catalog, schema, CURATED_COMPUTE_WAREHOUSES),
            query_history_table=_qualify(catalog, schema, CURATED_QUERY_HISTORY),
            cost_daily_table=_qualify(catalog, schema, GOLD_WAREHOUSE_COST_DAILY),
            billing_usage_table=_qualify(catalog, schema, CURATED_BILLING_USAGE),
            lower_bound=lower_bound,
        ),
        "warehouse_utilization_rolling": lambda: build_warehouse_utilization_rolling(
            spark,
            warehouse_utilization_daily_table=_qualify(
                catalog, schema, GOLD_WAREHOUSE_UTILIZATION_DAILY
            ),
        ),
        "warehouse_query_performance_daily": lambda: build_warehouse_query_performance_daily(
            spark,
            query_history_table=_qualify(catalog, schema, CURATED_QUERY_HISTORY),
            warehouses_table=_qualify(catalog, schema, CURATED_COMPUTE_WAREHOUSES),
            lower_bound=lower_bound,
        ),
        "warehouse_query_performance_rolling": lambda: build_warehouse_query_performance_rolling(
            spark,
            warehouse_query_performance_daily_table=_qualify(
                catalog, schema, GOLD_WAREHOUSE_QUERY_PERFORMANCE_DAILY
            ),
        ),
        "recommendations": lambda: build_compute_recommendations(
            spark,
            cluster_efficiency_rolling_table=_qualify(
                catalog, schema, GOLD_CLUSTER_EFFICIENCY_ROLLING
            ),
            cluster_reliability_rolling_table=_qualify(
                catalog, schema, GOLD_CLUSTER_RELIABILITY_ROLLING
            ),
            governance_table=_qualify(catalog, schema, GOLD_CLUSTER_GOVERNANCE),
            cluster_cost_rolling_table=_qualify(catalog, schema, GOLD_CLUSTER_COST_ROLLING),
            warehouse_utilization_rolling_table=_qualify(
                catalog, schema, GOLD_WAREHOUSE_UTILIZATION_ROLLING
            ),
            warehouse_query_performance_rolling_table=_qualify(
                catalog, schema, GOLD_WAREHOUSE_QUERY_PERFORMANCE_ROLLING
            ),
            warehouse_cost_rolling_table=_qualify(catalog, schema, GOLD_WAREHOUSE_COST_ROLLING),
            recommendations_table=_qualify(catalog, schema, GOLD_RECOMMENDATIONS),
            generated_date=today,
        ),
        "forecast_daily": lambda: build_compute_forecast(
            spark,
            warehouse_id=warehouse_id,
            cost_daily_table=_qualify(catalog, schema, GOLD_CLUSTER_COST_DAILY),
            efficiency_daily_table=_qualify(catalog, schema, GOLD_CLUSTER_EFFICIENCY_DAILY),
            job_cluster_cost_daily_table=_qualify(catalog, schema, GOLD_JOB_CLUSTER_COST_DAILY),
            pipeline_cost_daily_table=_qualify(catalog, schema, GOLD_PIPELINE_COST_DAILY),
            warehouse_cost_daily_table=_qualify(catalog, schema, GOLD_WAREHOUSE_COST_DAILY),
            warehouse_query_performance_daily_table=_qualify(
                catalog, schema, GOLD_WAREHOUSE_QUERY_PERFORMANCE_DAILY
            ),
            observed_lower_bound=today - timedelta(days=FORECAST_OBSERVED_LOOKBACK_DAYS),
            horizon_date=today + timedelta(days=FORECAST_HORIZON_DAYS),
            horizon_days=FORECAST_HORIZON_DAYS,
            prediction_interval_width=FORECAST_PREDICTION_INTERVAL_WIDTH,
            min_observed_days=FORECAST_MIN_OBSERVED_DAYS,
            max_observed_ratio=FORECAST_MAX_OBSERVED_RATIO,
            profile=profile,
        ),
        # Depense serverless (T001d) : billing-direct, AUCUNE table de clusters en
        # entree -- le serverless n'en a pas. Les deux referentiels ne servent
        # qu'a nommer les objets que la facturation ne nomme pas (warehouses,
        # pipelines).
        "serverless_cost_daily": lambda: build_serverless_cost_daily(
            spark,
            billing_usage_table=_qualify(catalog, schema, CURATED_BILLING_USAGE),
            billing_list_prices_table=_qualify(catalog, schema, CURATED_BILLING_LIST_PRICES),
            warehouses_table=_qualify(catalog, schema, CURATED_COMPUTE_WAREHOUSES),
            lakeflow_pipelines_table=_qualify(catalog, schema, CURATED_LAKEFLOW_PIPELINES),
            lower_bound=lower_bound,
        ),
        "serverless_cost_rolling": lambda: build_serverless_cost_rolling(
            spark,
            serverless_cost_daily_table=_qualify(catalog, schema, GOLD_SERVERLESS_COST_DAILY),
        ),
        # Gouvernance serverless (T001e) : relit la FACTURATION et non
        # `serverless_cost_daily`, dont le grain jour-objet sous-estime les
        # orphelins (cf. le module builder). Ce snapshot ne depend donc d'aucune
        # autre table gold, et sa fenetre est celle de `cluster_governance`.
        "serverless_governance": lambda: build_serverless_governance(
            spark,
            billing_usage_table=_qualify(catalog, schema, CURATED_BILLING_USAGE),
            billing_list_prices_table=_qualify(catalog, schema, CURATED_BILLING_LIST_PRICES),
            activity_lower_bound=today - timedelta(days=GOVERNANCE_ACTIVITY_WINDOW_DAYS),
        ),
        # Statistiques d'EXECUTION de pipeline (T001f) : une seule source, la
        # curated periodisee, et AUCUNE table gold en entree. `lower_bound` est
        # ici une fenetre de SORTIE (le builder n'en borne pas sa lecture, cf.
        # son docstring) : elle limite ce qui est fusionne, pas ce qui est lu.
        "pipeline_update_stats": lambda: build_pipeline_update_stats(
            spark,
            pipeline_update_timeline_table=_qualify(
                catalog, schema, CURATED_LAKEFLOW_PIPELINE_UPDATE_TIMELINE
            ),
            lower_bound=lower_bound,
        ),
        # Cout total deduplique (DCINT-335) : lit les 5 tables gold *_cost_daily
        # deja calculees, AUCUNE relecture de la facturation curated -- chacune
        # restreinte a la tranche qu'elle possede en propre (cf. docstring du
        # builder) pour ne compter chaque dollar de facturation qu'une seule fois.
        "total_cost_daily": lambda: build_total_cost_daily(
            spark,
            cluster_cost_daily_table=_qualify(catalog, schema, GOLD_CLUSTER_COST_DAILY),
            warehouse_cost_daily_table=_qualify(catalog, schema, GOLD_WAREHOUSE_COST_DAILY),
            job_cluster_cost_daily_table=_qualify(catalog, schema, GOLD_JOB_CLUSTER_COST_DAILY),
            pipeline_cost_daily_table=_qualify(catalog, schema, GOLD_PIPELINE_COST_DAILY),
            serverless_cost_daily_table=_qualify(catalog, schema, GOLD_SERVERLESS_COST_DAILY),
            dbx_workspace_reference_table=_qualify(catalog, schema, CURATED_DBX_WORKSPACE),
            dim_landing_zone_table=_qualify(catalog, schema, DIM_LANDING_ZONE_VIEW),
            lower_bound=lower_bound,
        ),
    }
    df = builders[table]()
    merge_into_table(
        spark,
        df,
        target_table=qualified_target_table,
        merge_keys=spec.merge_keys,
        absent_row_delete_predicate=_absent_row_delete_predicate(spec, df, lower_bound=lower_bound),
        column_comments=spec.column_comments,
        table_comment=spec.table_comment,
    )


def _debug_params_from_env() -> dict[str, str]:
    """Assemble les `named_parameters` de debug depuis les env vars `DBG_*`.

    Meme convention que `pipelines.system_tables.entrypoint._debug_params_from_env` :
    defaut vide (parametre non fourni), catalog/schema replies sur les defauts
    de debug local si absents.
    """
    params = {name: os.environ.get(f"DBG_{name.upper()}", "") for name in PARAM_NAMES}
    params["catalog"] = params["catalog"] or DEFAULT_CATALOG
    params["schema"] = params["schema"] or DEFAULT_SCHEMA
    return params


def run(argv: list[str] | None = None) -> None:  # pragma: no cover - runtime Databricks
    """Point d'entree console de la tache wheel (`[project.scripts]`).

    Sur cluster Databricks (tache wheel) : resout la `SparkSession` au runtime,
    parse les `named_parameters` passes en argv. En LOCAL (debug,
    `on_databricks_cluster()` faux) : construit une session Databricks Connect
    serverless et lit les parametres depuis les env vars `DBG_*` (cf.
    `.vscode/launch.json`).
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    logging.getLogger("pipelines").setLevel(logging.INFO)
    if on_databricks_cluster():
        from pyspark.sql import SparkSession

        spark: Any = SparkSession.builder.getOrCreate()
        params = parse_named_parameters(PARAM_NAMES, argv)
        profile = None
    else:
        profile = os.environ.get("DATABRICKS_CONFIG_PROFILE", LOCAL_DEBUG_PROFILE)
        spark = local_debug_spark(profile)
        params = _debug_params_from_env()
    main(spark, params, profile=profile)


if __name__ == "__main__":  # pragma: no cover - cluster (wheel) ou debug local (Connect)
    run()
