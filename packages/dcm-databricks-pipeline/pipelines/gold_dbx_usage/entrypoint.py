"""Point d'entree de la tache wheel Gold Usage Data Product (`[project.scripts]`).

Symetrique a `pipelines.gold_dbx_compute.entrypoint` (meme mecanique :
resolution de la `SparkSession`/des parametres, deux modes cluster/local, meme
strategie de fenetre incrementale) mais pour le domaine usage
(adoption/FinOps des data products Unity Catalog).

La fenetre incrementale est ancree sur la COUVERTURE REELLE de la table gold cible
(`pipelines.common.incremental.compute_gap_aware_lower_bound`), pas sur le seul
`today - incremental_lookback_days` : une fenetre calee sur `today` sous-compte en
silence des qu'un run a ete manque ou qu'un jour est arrive en retard.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
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
from pipelines.gold_dbx_usage.consumer_daily import build_consumer_daily
from pipelines.gold_dbx_usage.ephemeral_tables import purge_ephemeral_rows
from pipelines.gold_dbx_usage.forecast_daily import write_usage_forecast
from pipelines.gold_dbx_usage.recommendations import build_usage_recommendations
from pipelines.gold_dbx_usage.specs import (
    DEFAULT_CATALOG,
    DEFAULT_SCHEMA,
    FORECAST_HORIZON_DAYS,
    FORECAST_MAX_OBSERVED_RATIO,
    FORECAST_MIN_OBSERVED_DAYS,
    FORECAST_OBSERVED_LOOKBACK_DAYS,
    FORECAST_PREDICTION_INTERVAL_WIDTH,
    GOLD_CONSUMER_DAILY,
    GOLD_RECOMMENDATIONS,
    GOLD_SPECS,
    GOLD_TABLE_CATALOG,
    GOLD_TABLE_DAILY,
    GOLD_TABLE_GOVERNANCE,
    GOLD_TABLE_POPULARITY_DAILY,
    GOLD_TABLE_QUERY_PERFORMANCE_DAILY,
)
from pipelines.gold_dbx_usage.table_catalog import build_table_catalog
from pipelines.gold_dbx_usage.table_daily import build_table_daily
from pipelines.gold_dbx_usage.table_governance import build_table_governance
from pipelines.gold_dbx_usage.table_popularity_daily import build_table_popularity_daily
from pipelines.gold_dbx_usage.table_query_performance_daily import (
    build_table_query_performance_daily,
)
from pipelines.system_tables.specs import (
    CURATED_ACCESS_AUDIT,
    CURATED_ACCESS_TABLE_LINEAGE,
    CURATED_BILLING_LIST_PRICES,
    CURATED_BILLING_USAGE,
    CURATED_QUERY_HISTORY,
    CURATED_UC_TABLE_OPERATIONS,
    CURATED_UC_TABLE_TAGS,
    CURATED_UC_TABLES,
)

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

    from pipelines.gold_dbx_usage.specs import GoldAggregationSpec

# Parametres nommes passes par la tache `python_wheel_task` (named_parameters).
# `warehouse_id` : uniquement requis pour `table=forecast_daily` (`ai_forecast`
# exige un Pro/Serverless SQL Warehouse, cf. `pipelines.gold_dbx_usage.forecast_daily`).
# Aucun secret : ce plugin ne lit que des tables Unity Catalog deja qualifiees.
PARAM_NAMES = ("table", "catalog", "schema", "full_refresh", "warehouse_id")

# Colonne d'horodatage d'ecriture, presente sur les 6 builders de ce plugin
# (`current_timestamp() AS _generated_at`) : permet a
# `compute_gap_aware_lower_bound` de reperer les jours ecrits trop tot pour avoir
# absorbe les arrivees tardives de la couche curated.
GENERATED_AT_COLUMN = "_generated_at"

# Tables gold dont les lignes d'ephemeres sont RETIREES apres l'ecriture (cf.
# `pipelines.gold_dbx_usage.ephemeral_tables`) : TOUTES celles qui portent la cle de table.
#
# Le registre seul ne suffirait pas -- l'exclusion en aval lit la PRESENCE d'une ligne
# `is_deleted` au registre, donc retirer cette ligne sans retirer les lignes de fait
# rendrait l'ephemere VISIBLE comme une table vivante, l'inverse de ce que le filtre
# `include_deleted` de l'API a livre (spec 024, FR-023). Les faits seuls ne suffiraient pas
# non plus : la ligne du registre resterait, et avec elle l'anti-appartenance que les
# requetes de recommandation paient a chaque appel.
#
# `table_governance` en fait partie bien qu'elle DERIVE du registre : `merge_into_table`
# l'ecrit sans `absent_row_delete_predicate`, donc une cle que le registre ne produit plus
# n'y est ni rafraichie ni supprimee -- elle gele. La croissance sans borne se deplacerait
# simplement d'une table en aval.
#
# Deux tables n'y sont pas, pour deux raisons differentes :
#   - `consumer_daily` est au grain CONSOMMATEUR et ne porte aucune colonne de la cle de
#     table : il n'y a rien a apparier. Elle herite du filtre par `table_daily`.
#   - `recommendations` s'auto-repare : son `FULL OUTER JOIN` avec l'existant marque
#     `status = 'RESOLVED'` toute recommandation dont le candidat n'est plus emis, et les
#     sources d'ou venaient ses candidats d'ephemeres sont justement purgees ci-dessus.
PURGED_OF_EPHEMERAL_TABLES = frozenset(
    {
        "table_catalog",
        "table_daily",
        "table_popularity_daily",
        "table_query_performance_daily",
        "table_governance",
    }
)

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
      - la spec n'a pas de watermark (`table_catalog`/`table_governance`,
        snapshots toujours recalcules en entier) ;
      - `--full-refresh` explicite ;
      - la table gold cible n'existe pas encore (tout premier run).

    Sinon, la borne est ancree sur la COUVERTURE REELLE de la table gold cible
    (`compute_gap_aware_lower_bound`) et non sur le seul `today -
    incremental_lookback_days`. Une fenetre calee sur `today` ne rattrape pas un jour
    qu'aucun run n'a couvert pendant ses `lookback_days` : ce jour sort de toutes les
    fenetres suivantes, definitivement et sans signal, seul un `--full-refresh` manuel
    le reparant. Elle laisse aussi le dernier jour ecrit fige sur son compte partiel,
    ecrit alors que la source curated arrivait encore. La borne elargie couvre les
    deux cas : elle descend jusqu'au trou et reprend ce dernier jour.
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


def _log_deleted_table_count(spark: SparkSession, table_catalog_table: str) -> None:
    """Journalise le nombre de tables `DELETED` par `cloud_provider` (FR-018).

    Mesure de controle : un pic de suppressions doit rester visible sans table de
    metrique dediee. Le compte s'agrege sur le registre une fois ECRIT -- il porte
    alors sur ce qui est reellement publie, et non sur un plan recalcule une
    seconde fois.
    """
    rows = spark.sql(
        f"""
        SELECT cloud_provider, COUNT(*) AS deleted_count
        FROM {table_catalog_table}
        WHERE is_deleted
        GROUP BY cloud_provider
        """
    ).collect()
    counts = ", ".join(f"{row[0]}={row[1]}" for row in rows) or "aucune"
    _LOGGER.info("%s : tables supprimees par cloud_provider -> %s.", table_catalog_table, counts)


def main(spark: Any, params: dict[str, str], *, profile: str | None = None) -> None:  # noqa: ANN401
    """Orchestration : calcule et ecrit la table gold selectionnee par `--table`.

    Fonction testable sans cluster reel (spark peut etre un fake enregistrant
    les appels `sql()`). `profile` transmis a `write_usage_forecast`
    (`table=forecast_daily`) -- authentification `WorkspaceClient` pour l'API
    Statement Execution, cf. docstring de ce builder.
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
    full_refresh = params.get("full_refresh", "").strip().lower() in {"1", "true", "yes"}
    warehouse_id = params.get("warehouse_id", "").strip()
    if table == "forecast_daily" and not warehouse_id:
        raise ValueError(
            "Le parametre 'warehouse_id' est requis pour 'forecast_daily' (ai_forecast "
            "exige un Pro/Serverless SQL Warehouse, incompatible avec l'environnement "
            "serverless generique de ce job)."
        )
    today = datetime.now(UTC).date()
    qualified_target_table = _qualify(catalog, schema, spec.target_table)

    if table == "forecast_daily":
        write_usage_forecast(
            spark,
            warehouse_id=warehouse_id,
            target_table=qualified_target_table,
            table_popularity_daily_table=_qualify(catalog, schema, GOLD_TABLE_POPULARITY_DAILY),
            table_catalog_table=_qualify(catalog, schema, GOLD_TABLE_CATALOG),
            observed_lower_bound=today - timedelta(days=FORECAST_OBSERVED_LOOKBACK_DAYS),
            horizon_date=today + timedelta(days=FORECAST_HORIZON_DAYS),
            horizon_days=FORECAST_HORIZON_DAYS,
            merge_keys=spec.merge_keys,
            prediction_interval_width=FORECAST_PREDICTION_INTERVAL_WIDTH,
            min_observed_days=FORECAST_MIN_OBSERVED_DAYS,
            max_observed_ratio=FORECAST_MAX_OBSERVED_RATIO,
            column_comments=spec.column_comments,
            table_comment=spec.table_comment,
            profile=profile,
        )
        return

    lower_bound = _resolve_lower_bound(
        spark, spec, qualified_target_table, full_refresh=full_refresh, today=today
    )

    # Registre de dispatch : cle du registre `GOLD_SPECS` -> fonction de calcul.
    # Une nouvelle table gold AJOUTE une entree ici, sans modifier les entrees
    # existantes (cf. merge-strategy.md). `forecast_daily` n'y figure PAS :
    # ecriture directe (`write_usage_forecast`, cas special ci-dessus) car le
    # calcul ET l'ecriture doivent s'executer sur le SQL Warehouse, jamais via
    # `merge_into_table` (cf. docstring `pipelines.gold_dbx_usage.forecast_daily`).
    builders: dict[str, Callable[[], DataFrame]] = {
        "table_daily": lambda: build_table_daily(
            spark,
            lineage_table=_qualify(catalog, schema, CURATED_ACCESS_TABLE_LINEAGE),
            access_audit_table=_qualify(catalog, schema, CURATED_ACCESS_AUDIT),
            query_history_table=_qualify(catalog, schema, CURATED_QUERY_HISTORY),
            billing_usage_table=_qualify(catalog, schema, CURATED_BILLING_USAGE),
            billing_list_prices_table=_qualify(catalog, schema, CURATED_BILLING_LIST_PRICES),
            uc_tables_table=_qualify(catalog, schema, CURATED_UC_TABLES),
            table_operations_table=_qualify(catalog, schema, CURATED_UC_TABLE_OPERATIONS),
            lower_bound=lower_bound,
        ),
        "table_popularity_daily": lambda: build_table_popularity_daily(
            spark,
            table_daily_table=_qualify(catalog, schema, GOLD_TABLE_DAILY),
            lineage_table=_qualify(catalog, schema, CURATED_ACCESS_TABLE_LINEAGE),
            uc_table_tags_table=_qualify(catalog, schema, CURATED_UC_TABLE_TAGS),
            lower_bound=lower_bound,
        ),
        "consumer_daily": lambda: build_consumer_daily(
            spark,
            table_daily_table=_qualify(catalog, schema, GOLD_TABLE_DAILY),
            lower_bound=lower_bound,
        ),
        "table_query_performance_daily": lambda: build_table_query_performance_daily(
            spark,
            lineage_table=_qualify(catalog, schema, CURATED_ACCESS_TABLE_LINEAGE),
            query_history_table=_qualify(catalog, schema, CURATED_QUERY_HISTORY),
            uc_tables_table=_qualify(catalog, schema, CURATED_UC_TABLES),
            table_operations_table=_qualify(catalog, schema, CURATED_UC_TABLE_OPERATIONS),
            lower_bound=lower_bound,
        ),
        "table_catalog": lambda: build_table_catalog(
            spark,
            uc_tables_table=_qualify(catalog, schema, CURATED_UC_TABLES),
            uc_table_tags_table=_qualify(catalog, schema, CURATED_UC_TABLE_TAGS),
            table_operations_table=_qualify(catalog, schema, CURATED_UC_TABLE_OPERATIONS),
            lineage_table=_qualify(catalog, schema, CURATED_ACCESS_TABLE_LINEAGE),
            query_history_table=_qualify(catalog, schema, CURATED_QUERY_HISTORY),
            table_daily_table=_qualify(catalog, schema, GOLD_TABLE_DAILY),
        ),
        "table_governance": lambda: build_table_governance(
            spark,
            table_catalog_table=_qualify(catalog, schema, GOLD_TABLE_CATALOG),
            table_popularity_daily_table=_qualify(catalog, schema, GOLD_TABLE_POPULARITY_DAILY),
        ),
        "recommendations": lambda: build_usage_recommendations(
            spark,
            governance_table=_qualify(catalog, schema, GOLD_TABLE_GOVERNANCE),
            catalog_table=_qualify(catalog, schema, GOLD_TABLE_CATALOG),
            popularity_daily_table=_qualify(catalog, schema, GOLD_TABLE_POPULARITY_DAILY),
            query_performance_daily_table=_qualify(
                catalog, schema, GOLD_TABLE_QUERY_PERFORMANCE_DAILY
            ),
            consumer_daily_table=_qualify(catalog, schema, GOLD_CONSUMER_DAILY),
            recommendations_table=_qualify(catalog, schema, GOLD_RECOMMENDATIONS),
            generated_date=today,
        ),
    }
    df = builders[table]()
    merge_into_table(
        spark,
        df,
        target_table=qualified_target_table,
        merge_keys=spec.merge_keys,
        column_comments=spec.column_comments,
        table_comment=spec.table_comment,
    )
    if table in PURGED_OF_EPHEMERAL_TABLES:
        # ORDRE IMPOSE : ecrire, purger, PUIS compter. La purge doit suivre l'ecriture --
        # c'est le MERGE du writer qui vient de (re)poser les lignes, et lui seul ne
        # supprime jamais -- et le comptage doit suivre la purge, sinon la mesure de
        # controle annonce des suppressions qui ne sont plus dans la table.
        purge_ephemeral_rows(
            spark,
            target_table=qualified_target_table,
            uc_tables_table=_qualify(catalog, schema, CURATED_UC_TABLES),
            table_operations_table=_qualify(catalog, schema, CURATED_UC_TABLE_OPERATIONS),
        )
    if table == "table_catalog":
        _log_deleted_table_count(spark, qualified_target_table)


def _debug_params_from_env() -> dict[str, str]:
    """Assemble les `named_parameters` de debug depuis les env vars `DBG_*`."""
    params = {name: os.environ.get(f"DBG_{name.upper()}", "") for name in PARAM_NAMES}
    params["catalog"] = params["catalog"] or DEFAULT_CATALOG
    params["schema"] = params["schema"] or DEFAULT_SCHEMA
    return params


def run(argv: list[str] | None = None) -> None:  # pragma: no cover - runtime Databricks
    """Point d'entree console de la tache wheel (`[project.scripts]`)."""
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
