"""Point d'entree de la tache wheel Reference LZ (`[project.scripts]`).

Meme convention que `pipelines.system_tables.entrypoint` : resout la
`SparkSession`, les secrets et les parametres, puis delegue a
`pipelines.reference_lz.ingest`. Contrairement a `system_tables`, aucun
`IngestionSpec` generique n'est ingere ici : le parametre `--table` selectionne
directement l'une des 3 fonctions bespoke (`ingest_dbx_workspace` /
`ingest_business_application` / `ingest_business_application_dim`), car leurs
sources divergent trop pour un socle d'ingestion unique (cf. `research.md` §3).

Garde-fou specifique (FR-004) : `business_application` et
`business_application_dim` n'ont AUCUNE source AWS (uniquement Azure
`ref_ba_lz`) -- les selectionner sans config Azure resolue leve une erreur
explicite plutot que de produire silencieusement une table vide.

Aucune logique metier ici (cablage uniquement) ; aucun secret code en dur (P8).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, cast

from pipelines.common.models import AzureConnectionConfig
from pipelines.common.runtime import (
    LOCAL_DEBUG_PROFILE,
    LocalDebugSecrets,
    local_debug_spark,
    on_databricks_cluster,
    parse_named_parameters,
)
from pipelines.reference_lz.ingest import (
    ingest_business_application,
    ingest_business_application_dim,
    ingest_dbx_workspace,
)
from pipelines.reference_lz.specs import (
    CURATED_TABLES,
    DEFAULT_CATALOG,
    DEFAULT_SCHEMA,
    TABLE_BUSINESS_APPLICATION,
    TABLE_BUSINESS_APPLICATION_DIM,
    TABLE_KEYS,
)

# Parametres nommes passes par la tache `python_wheel_task` (named_parameters).
# Aucun n'est sensible : les identifiants Entra du SP sont resolus depuis le
# secret scope Databricks via `dbutils.secrets` (P8 : jamais en dur). `table`
# selectionne la table du registre a ingerer (valeur `{{input}}` du `for_each`).
# Pas de `lookback_days`/`azure_batch_size` (contrairement a `system_tables`) :
# full-load sans watermark (FR-005), tables de reference petites -- le lot
# Azure global par defaut (`DEFAULT_AZURE_FETCH_BATCH_SIZE`) suffit.
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

    Meme mecanique que `pipelines.system_tables.entrypoint._read_azure_config`
    (identifiants sensibles resolus depuis `dbutils.secrets`, jamais en dur,
    P8) -- dupliquee ici plutot qu'importee : les 2 entrypoints restent des
    modules independants, chacun cable a sa propre tache wheel.
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


def _selected_tables(params: dict[str, str]) -> tuple[str, ...]:
    """Resout les tables a ingerer depuis le parametre `--table`.

    - `table` renseigne : une seule table (iteration `for_each`, valeur
      `{{input}}`). Une cle inconnue leve une erreur explicite (garde-fou
      contre un `inputs` desynchronise du registre cote job).
    - `table` vide (debug local) : les 2 tables, dans l'ordre du registre.
    """
    table = params["table"].strip()
    if not table:
        return TABLE_KEYS
    if table not in CURATED_TABLES:
        known = ", ".join(TABLE_KEYS)
        raise ValueError(f"Table inconnue '{table}' ; valeurs attendues : {known}.")
    return (table,)


def main(spark: Any, secrets: Any, params: dict[str, str]) -> None:  # noqa: ANN401
    """Orchestration : ingere la (ou les) table(s) referentiel selectionnee(s).

    `secrets` est un accessor de secrets (`dbutils.secrets`) ; `params` le dict
    des parametres nommes deja parses. Fonction testable sans cluster reel.

    Les tables curated sont qualifiees `catalog.schema.table` a partir des
    parametres `catalog` / `schema` (vars bundle, differentes par target) --
    sans qualification, l'ecriture irait dans le catalog/schema PAR DEFAUT de
    la session au lieu de la cible Unity Catalog (garde-fou ci-dessous).

    Garde-fou FR-004 : `business_application` n'a pas de source AWS ; la
    selectionner sans config Azure resolue (host vide) leve une erreur
    explicite plutot que d'ingerer silencieusement une table vide.
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

    for table in _selected_tables(params):
        curated_table = f"{schema_prefix}.{CURATED_TABLES[table]}"
        if table in (TABLE_BUSINESS_APPLICATION, TABLE_BUSINESS_APPLICATION_DIM):
            if azure_config is None:
                raise ValueError(
                    f"Table '{table}' selectionnee sans configuration Azure "
                    "(azure_host vide) : source unique Azure 'ref_ba_lz', "
                    "aucun fallback AWS possible (FR-004)."
                )
            ingest_fn = (
                ingest_business_application
                if table == TABLE_BUSINESS_APPLICATION
                else ingest_business_application_dim
            )
            ingest_fn(
                spark,
                curated_table=curated_table,
                azure_config=azure_config,
                collection_run_id=collection_run_id,
                collected_at=collected_at,
            )
        else:
            ingest_dbx_workspace(
                spark,
                curated_table=curated_table,
                azure_config=azure_config,
                collection_run_id=collection_run_id,
                collected_at=collected_at,
            )


def _debug_params_from_env() -> dict[str, str]:
    """Assemble les `named_parameters` de debug depuis les env vars `DBG_*`.

    Meme convention que `pipelines.system_tables.entrypoint._debug_params_from_env`.
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

    Meme mecanique que `pipelines.system_tables.entrypoint.run` (cluster/serverless
    vs debug local Databricks Connect, cf. docstring de ce dernier).
    """
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
