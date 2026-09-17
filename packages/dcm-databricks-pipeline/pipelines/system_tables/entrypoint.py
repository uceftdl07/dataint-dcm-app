"""Point d'entree de la tache wheel System Tables (`[project.scripts]`).

Seul module cable au runtime Databricks : il resout la `SparkSession`, les
secrets et les parametres, puis delegue l'ingestion a
`pipelines.system_tables.ingest`. Deux modes :
  - cluster/serverless (tache wheel) : SparkSession + `dbutils.secrets` + argv ;
  - local (debug F5) : Databricks Connect serverless + secrets locaux + env `DBG_*`.

Le parametre `--table` selectionne UNE table du registre `specs.SPECS` a ingerer :
c'est la valeur `{{input}}` d'une iteration `for_each` du job (une table = une
task parallele). Si `--table` est vide (debug local), toutes les tables sont
ingerees sequentiellement.

Aucune logique metier ici (cablage uniquement) ; aucun secret code en dur (P8).
"""

from __future__ import annotations

import logging
import os
from dataclasses import replace
from datetime import datetime
from typing import Any, cast

from pipelines.common.incremental import DEFAULT_LOOKBACK_DAYS
from pipelines.common.models import AzureConnectionConfig, IngestionSpec
from pipelines.common.runtime import (
    LOCAL_DEBUG_PROFILE,
    LocalDebugSecrets,
    local_debug_spark,
    on_databricks_cluster,
    parse_named_parameters,
)
from pipelines.system_tables.ingest import ingest_system_table
from pipelines.system_tables.specs import (
    DEFAULT_CATALOG,
    DEFAULT_SCHEMA,
    SPECS,
)

# Parametres nommes passes par la tache `python_wheel_task` (named_parameters).
# Aucun n'est sensible : les identifiants Entra du SP sont resolus depuis le
# secret scope Databricks via `dbutils.secrets` (P8 : jamais en dur). `table`
# selectionne la table du registre a ingerer (valeur `{{input}}` du `for_each`).
PARAM_NAMES = (
    "table",
    "catalog",
    "schema",
    "collection_run_id",
    "collected_at",
    "azure_host",
    "azure_http_path",
    "azure_secret_scope",
    "azure_tenant_id_key",
    "azure_client_id_key",
    "azure_secret_key",
    "lookback_days",
    "azure_batch_size",
)

# Cle de secret (dans le scope) -> variable d'env de surcharge locale. Permet de
# debugger sans droit de lecture sur le secret scope (P8 : secret jamais en dur).
_SECRET_ENV_OVERRIDES = {
    "azure-sp-tenant-id": "DBX_AZ_TENANT_ID",
    "azure-sp-client-id": "DBX_AZ_CLIENT_ID",
    "azure-sp-client-secret": "DBX_AZ_CLIENT_SECRET",
}


def _read_azure_config(params: dict[str, str], secrets: Any) -> AzureConnectionConfig | None:  # noqa: ANN401
    """Assemble la config Azure depuis les parametres ; None si desactive.

    Les identifiants sensibles (tenant_id, client_id, client secret) ne sont
    jamais passes en parametre de tache : ils sont resolus depuis le secret scope
    Databricks (`azure_secret_scope`) via `dbutils.secrets` (P8 : jamais en dur).
    Seuls l'hote et le http_path (non sensibles) sont passes en clair.
    """
    host = params["azure_host"].strip()
    if not host:
        return None
    scope = params["azure_secret_scope"].strip()

    def _secret(key_param: str) -> str:
        return cast("str", secrets.get(scope=scope, key=params[key_param].strip()))

    return AzureConnectionConfig(
        host=host,
        http_path=params["azure_http_path"].strip(),
        tenant_id=_secret("azure_tenant_id_key"),
        client_id=_secret("azure_client_id_key"),
        client_secret=_secret("azure_secret_key"),
    )


def _selected_specs(params: dict[str, str]) -> dict[str, IngestionSpec]:
    """Resout les tables a ingerer depuis le parametre `--table`.

    - `table` renseigne : une seule table (iteration `for_each`, valeur `{{input}}`).
      Une cle inconnue leve une erreur explicite (garde-fou contre un `inputs`
      desynchronise du registre cote job).
    - `table` vide (debug local) : toutes les tables du registre, sequentiellement.
    """
    table = params["table"].strip()
    if not table:
        return dict(SPECS)
    if table not in SPECS:
        known = ", ".join(SPECS)
        raise ValueError(f"Table inconnue '{table}' ; valeurs attendues : {known}.")
    return {table: SPECS[table]}


def main(spark: Any, secrets: Any, params: dict[str, str]) -> None:  # noqa: ANN401
    """Orchestration : ingere la (ou les) system table(s) selectionnee(s) (Azure ⊎ AWS).

    `secrets` est un accessor de secrets (`dbutils.secrets`) ; `params` le dict
    des parametres nommes deja parses. Fonction testable sans cluster reel.

    Les tables curated sont qualifiees `catalog.schema.table` a partir des
    parametres `catalog` / `schema` (vars bundle, differentes par target). Sans
    qualification, `saveAsTable`/`MERGE` ecriraient dans le catalog/schema PAR
    DEFAUT de la session (ex. `hive_metastore.default`) au lieu de la cible UC :
    les donnees seraient invisibles pour le backend. La qualification est donc
    obligatoire (garde-fou ci-dessous).
    """
    catalog = params["catalog"].strip()
    schema = params["schema"].strip()
    if not catalog or not schema:
        raise ValueError(
            "Les parametres 'catalog' et 'schema' sont requis pour qualifier les "
            "tables curated (sinon ecriture dans le catalog/schema par defaut de "
            "la session au lieu de la cible Unity Catalog)."
        )
    schema_prefix = f"{catalog}.{schema}"
    collection_run_id = params["collection_run_id"]
    collected_at = params["collected_at"]
    azure_config = _read_azure_config(params, secrets)
    lookback_days = int(params["lookback_days"].strip() or DEFAULT_LOOKBACK_DAYS)
    azure_batch_size_raw = params["azure_batch_size"].strip()
    azure_batch_size = int(azure_batch_size_raw) if azure_batch_size_raw else None

    for spec in _selected_specs(params).values():
        qualified_spec = replace(spec, curated_table=f"{schema_prefix}.{spec.curated_table}")
        ingest_kwargs: dict = {
            "collection_run_id": collection_run_id,
            "collected_at": collected_at,
            "azure_config": azure_config,
            "lookback_days": lookback_days,
        }
        if azure_batch_size is not None:
            ingest_kwargs["azure_batch_size"] = azure_batch_size
        ingest_system_table(spark, qualified_spec, **ingest_kwargs)


def _debug_params_from_env() -> dict[str, str]:
    """Assemble les `named_parameters` de debug depuis les env vars `DBG_*`.

    En prod (tache wheel) ces valeurs viennent des `named_parameters` du job ;
    en debug elles proviennent de la config de lancement VS Code
    (`.vscode/launch.json`, alignee sur `databricks.yml` target dev). Defaut vide
    ⇒ parametre non fourni (ex. `DBG_AZURE_HOST=""` desactive la lecture Azure ;
    `DBG_TABLE=""` ingere toutes les tables du registre).
    `collection_run_id` / `collected_at` sont generes localement s'ils manquent.
    """
    import uuid
    from datetime import UTC

    params = {name: os.environ.get(f"DBG_{name.upper()}", "") for name in PARAM_NAMES}
    params["collection_run_id"] = params["collection_run_id"] or f"local-debug-{uuid.uuid4()}"
    params["collected_at"] = params["collected_at"] or datetime.now(UTC).isoformat()
    params["catalog"] = params["catalog"] or DEFAULT_CATALOG
    params["schema"] = params["schema"] or DEFAULT_SCHEMA
    return params


def run(argv: list[str] | None = None) -> None:  # pragma: no cover - runtime Databricks
    """Point d'entree console de la tache wheel (`[project.scripts]`).

    Sur cluster Databricks (tache wheel) : resout la `SparkSession` et
    `dbutils.secrets` au runtime, parse les `named_parameters` passes en argv.

    En LOCAL (debug, `on_databricks_cluster()` faux) : construit une session
    Databricks Connect serverless et un accessor de secrets local
    (`LocalDebugSecrets`), et lit les parametres depuis les env vars `DBG_*`.
    Cela permet de poser des breakpoints et d'executer `main()` pas-a-pas depuis
    VS Code (F5) sans deployer ni lancer le job — voir `.vscode/launch.json`.
    """
    # basicConfig est no-op si Databricks a déjà des handlers ; setLevel force
    # INFO sur notre package dans les deux cas.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    logging.getLogger("pipelines").setLevel(logging.INFO)
    if on_databricks_cluster():
        from databricks.sdk.runtime import dbutils
        from pyspark.sql import SparkSession

        spark: Any = SparkSession.builder.getOrCreate()
        secrets: Any = dbutils.secrets
        params = parse_named_parameters(PARAM_NAMES, argv)
    else:
        profile = os.environ.get("DATABRICKS_CONFIG_PROFILE", LOCAL_DEBUG_PROFILE)
        spark = local_debug_spark(profile)
        secrets = LocalDebugSecrets(profile, _SECRET_ENV_OVERRIDES)
        params = _debug_params_from_env()
    main(spark, secrets, params)


if __name__ == "__main__":  # pragma: no cover - cluster (wheel) ou debug local (Connect)
    run()
