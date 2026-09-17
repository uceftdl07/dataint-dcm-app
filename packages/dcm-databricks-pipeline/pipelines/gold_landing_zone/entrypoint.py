"""Point d'entree de la tache wheel Gold Landing Zone (`[project.scripts]`).

Symetrique a `pipelines.gold_dbx_workspace.entrypoint` (meme mecanique : resolution
de la `SparkSession` et des parametres, deux modes cluster/local ; aucune partie
Azure/secrets, uniquement des objets Unity Catalog deja qualifies). Ce plugin ne
calcule ni n'ecrit de table : il (re)cree la vue `dim_landing_zone` via
`spark.sql(build_dim_landing_zone_view_sql(catalog, schema))`, apres avoir
supprime la table physique homonyme laissee par le rename DLT.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from pipelines.common.runtime import (
    LOCAL_DEBUG_PROFILE,
    local_debug_spark,
    on_databricks_cluster,
    parse_named_parameters,
)
from pipelines.gold_landing_zone.view import build_dim_landing_zone_view_sql
from pipelines.system_tables.specs import DEFAULT_CATALOG, DEFAULT_SCHEMA

# Parametres nommes passes par la tache `python_wheel_task` (named_parameters).
# Aucun secret : ce plugin ne fait que du DDL sur des objets Unity Catalog deja
# qualifies par `catalog`/`schema`.
PARAM_NAMES = ("catalog", "schema")


def main(spark: Any, params: dict[str, str]) -> None:  # noqa: ANN401
    """Orchestration : (re)cree la vue `dim_landing_zone` (SQL pur, idempotent).

    Fonction testable sans cluster reel (spark peut etre un fake enregistrant les
    appels `sql()`). Qualifie la vue et ses objets source via `catalog`/`schema`
    (vars bundle, differentes par target) : sans qualification, le DDL viserait le
    catalog/schema par defaut de la session au lieu de la cible Unity Catalog
    (meme garde-fou que `pipelines.gold_dbx_workspace.entrypoint.main`).
    """
    catalog = params["catalog"].strip()
    schema = params["schema"].strip()
    if not catalog or not schema:
        raise ValueError(
            "Les parametres 'catalog' et 'schema' sont requis pour qualifier la vue "
            "dim_landing_zone et ses objets source (sinon DDL dans le catalog/schema "
            "par defaut de la session au lieu de la cible Unity Catalog)."
        )
    logging.getLogger("pipelines").info(
        "Creation/mise a jour de la vue %s.%s.dim_landing_zone", catalog, schema
    )
    # Migration one-off : le rename DLT (dim_landing_zone -> dim_landing_zone_collector)
    # laisse orpheline l'ancienne table physique `dim_landing_zone` ; une vue ne peut
    # remplacer une table homonyme, d'ou ce DROP idempotent avant le CREATE VIEW.
    spark.sql(f"DROP TABLE IF EXISTS {catalog}.{schema}.dim_landing_zone")
    spark.sql(build_dim_landing_zone_view_sql(catalog, schema))


def _debug_params_from_env() -> dict[str, str]:
    """Assemble les `named_parameters` de debug depuis les env vars `DBG_*`.

    Meme convention que `pipelines.gold_dbx_workspace.entrypoint._debug_params_from_env` :
    catalog/schema replient sur les defauts de debug local si absents.
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
