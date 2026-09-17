"""Point d'entree de la tache wheel Gold Databricks Workflow (`[project.scripts]`).

Symetrique a `pipelines.gold_dbx_compute.entrypoint` (meme mecanique de
resolution `SparkSession`/parametres), en plus simple : les 9 tables de ce
domaine sont TOUTES des snapshots (`watermark_column=None`), il n'y a donc
jamais de fenetre incrementale a resoudre (`_resolve_lower_bound`/
`compute_gap_aware_lower_bound` n'ont pas d'utilite ici, contrairement au
domaine compute) — chaque run relit l'integralite des system tables via les
vues-pont (`pipelines.gold_dbx_workflow.bridges`) et upsert/supprime les
lignes absentes via `pipelines.common.writers.merge_into_table`.

Le parametre `--table` selectionne UNE des 9 cles du registre
`gold_dbx_workflow.specs.GOLD_SPECS` (valeur `{{input}}` d'une iteration
`for_each` du job, cf. `resources/job_dcm_gold_dbx_workflow.yml`).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from pipelines.common.runtime import (
    LOCAL_DEBUG_PROFILE,
    local_debug_spark,
    on_databricks_cluster,
    parse_named_parameters,
)
from pipelines.common.writers import merge_into_table
from pipelines.gold_dbx_workflow.concurrency_1min import build_concurrency_1min
from pipelines.gold_dbx_workflow.duration_drift import build_duration_drift
from pipelines.gold_dbx_workflow.duration_percentiles import build_duration_percentiles
from pipelines.gold_dbx_workflow.never_run import build_never_run
from pipelines.gold_dbx_workflow.runs import build_runs
from pipelines.gold_dbx_workflow.specs import (
    DEFAULT_CATALOG,
    DEFAULT_SCHEMA,
    DIM_DBX_WORKSPACE_VIEW,
    GOLD_SPECS,
)
from pipelines.gold_dbx_workflow.success_rate import build_success_rate
from pipelines.gold_dbx_workflow.task_failure_rate import build_task_failure_rate
from pipelines.gold_dbx_workflow.task_health import build_task_health
from pipelines.gold_dbx_workflow.tasks import build_tasks
from pipelines.system_tables.specs import (
    CURATED_LAKEFLOW_JOB_RUN_TIMELINE,
    CURATED_LAKEFLOW_JOB_TASK_RUN_TIMELINE,
    CURATED_LAKEFLOW_JOBS,
)

if TYPE_CHECKING:
    from pyspark.sql import DataFrame

# Parametres nommes passes par la tache `python_wheel_task` (named_parameters).
# Aucun secret : ce plugin ne lit que des tables Unity Catalog deja qualifiees
# (system tables curated + dim_dbx_workspace), jamais de connexion cross-tenant.
PARAM_NAMES = ("table", "catalog", "schema", "full_refresh", "one_off_purge")

_LOGGER = logging.getLogger(__name__)


def _qualify(catalog: str, schema: str, table_name: str) -> str:
    """Qualifie un nom de table curated/gold avec `catalog.schema`."""
    return f"{catalog}.{schema}.{table_name}"


def _boolean_param(params: dict[str, str], name: str) -> bool:
    """Lit un parametre nomme booleen : absent ou vide = faux (meme regle que
    `pipelines.gold_dbx_compute.entrypoint._boolean_param` — les
    `named_parameters` d'une tache wheel sont toujours des chaines).
    """
    return params.get(name, "").strip().lower() in {"1", "true", "yes"}


def main(spark: Any, params: dict[str, str]) -> None:  # noqa: ANN401
    """Orchestration : calcule et ecrit la table gold workflow selectionnee par `--table`.

    Fonction testable sans cluster reel (spark peut etre un fake enregistrant
    les appels `sql()`/`table()`). Qualifie les tables via `catalog`/`schema`
    (vars bundle) : sans qualification, l'ecriture irait dans le catalog/schema
    par defaut de la session au lieu de la cible Unity Catalog.
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
        raise ValueError(f"Table gold workflow inconnue '{table}' ; valeurs attendues : {known}.")
    spec = GOLD_SPECS[table]
    full_refresh = _boolean_param(params, "full_refresh")  # cf. docstring module : sans effet
    # sur la lecture (toujours full), conserve pour homogeneite d'interface avec
    # `gold_dbx_compute` et un futur passage a une fenetre incrementale.
    _ = full_refresh

    job_run_timeline_table = _qualify(catalog, schema, CURATED_LAKEFLOW_JOB_RUN_TIMELINE)
    job_task_run_timeline_table = _qualify(catalog, schema, CURATED_LAKEFLOW_JOB_TASK_RUN_TIMELINE)
    jobs_table = _qualify(catalog, schema, CURATED_LAKEFLOW_JOBS)
    dim_dbx_workspace_table = _qualify(catalog, schema, DIM_DBX_WORKSPACE_VIEW)
    qualified_target_table = _qualify(catalog, schema, spec.target_table)

    # Registre de dispatch : cle du registre `GOLD_SPECS` -> fonction de calcul.
    # Nouvelles tables gold AJOUTENT une entree ici, sans modifier les entrees
    # existantes.
    builders: dict[str, Callable[[], DataFrame]] = {
        "success_rate": lambda: build_success_rate(
            spark,
            job_run_timeline_table=job_run_timeline_table,
            job_task_run_timeline_table=job_task_run_timeline_table,
            jobs_table=jobs_table,
            dim_dbx_workspace_table=dim_dbx_workspace_table,
        ),
        "duration_percentiles": lambda: build_duration_percentiles(
            spark,
            job_run_timeline_table=job_run_timeline_table,
            job_task_run_timeline_table=job_task_run_timeline_table,
            jobs_table=jobs_table,
            dim_dbx_workspace_table=dim_dbx_workspace_table,
        ),
        "duration_drift": lambda: build_duration_drift(
            spark,
            job_run_timeline_table=job_run_timeline_table,
            job_task_run_timeline_table=job_task_run_timeline_table,
            jobs_table=jobs_table,
            dim_dbx_workspace_table=dim_dbx_workspace_table,
        ),
        "task_failure_rate": lambda: build_task_failure_rate(
            spark,
            job_run_timeline_table=job_run_timeline_table,
            job_task_run_timeline_table=job_task_run_timeline_table,
            jobs_table=jobs_table,
            dim_dbx_workspace_table=dim_dbx_workspace_table,
        ),
        "concurrency_1min": lambda: build_concurrency_1min(
            spark,
            job_run_timeline_table=job_run_timeline_table,
            job_task_run_timeline_table=job_task_run_timeline_table,
            jobs_table=jobs_table,
            dim_dbx_workspace_table=dim_dbx_workspace_table,
        ),
        "task_health": lambda: build_task_health(
            spark,
            job_run_timeline_table=job_run_timeline_table,
            job_task_run_timeline_table=job_task_run_timeline_table,
            jobs_table=jobs_table,
        ),
        "runs": lambda: build_runs(
            spark,
            job_run_timeline_table=job_run_timeline_table,
            job_task_run_timeline_table=job_task_run_timeline_table,
            jobs_table=jobs_table,
            dim_dbx_workspace_table=dim_dbx_workspace_table,
        ),
        "tasks": lambda: build_tasks(
            spark,
            job_run_timeline_table=job_run_timeline_table,
            job_task_run_timeline_table=job_task_run_timeline_table,
            jobs_table=jobs_table,
        ),
        "never_run": lambda: build_never_run(
            spark,
            jobs_table=jobs_table,
            job_run_timeline_table=job_run_timeline_table,
        ),
    }
    df = builders[table]()

    # `watermark_column is None` pour les 9 specs de ce domaine :
    # `resolve_absent_row_delete_predicate` renvoie directement le garde-fou
    # (`SNAPSHOT_ABSENT_ROW_DELETE_GUARD`), sans borne de fenetre a conjuguer
    # (cf. docstring de `GoldAggregationSpec`).
    absent_row_delete_predicate = spec.resolve_absent_row_delete_predicate(window_floor=None)

    merge_into_table(
        spark,
        df,
        target_table=qualified_target_table,
        merge_keys=spec.merge_keys,
        absent_row_delete_predicate=absent_row_delete_predicate,
        column_comments=spec.column_comments,
        table_comment=spec.table_comment,
    )
    _LOGGER.info("gold_dbx_workflow.%s ecrit dans %s.", table, qualified_target_table)


def _debug_params_from_env() -> dict[str, str]:
    """Assemble les `named_parameters` de debug depuis les env vars `DBG_*`.

    Meme convention que `pipelines.gold_dbx_compute.entrypoint._debug_params_from_env` :
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
    serverless et lit les parametres depuis les env vars `DBG_*`.
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
    else:
        profile = os.environ.get("DATABRICKS_CONFIG_PROFILE", LOCAL_DEBUG_PROFILE)
        spark = local_debug_spark(profile)
        params = _debug_params_from_env()
    main(spark, params)


if __name__ == "__main__":  # pragma: no cover - cluster (wheel) ou debug local (Connect)
    run()

