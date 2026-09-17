"""Point d'entree de la tache wheel Curated Purge (`[project.scripts]`).

Meme pattern que `pipelines.system_tables.entrypoint` : seul module cable au
runtime Databricks, resout la `SparkSession`, les secrets et les parametres
puis delegue a `pipelines.common.purge.purge_absent_rows`. Deux modes :
  - cluster/serverless (tache wheel) : SparkSession + `dbutils.secrets` + argv ;
  - local (debug F5) : Databricks Connect serverless + secrets locaux + env
    `DBG_*`.

Job SEPARE de `dcm_system_tables` (cron, chemin d'execution) : ce module
n'importe JAMAIS `pipelines.system_tables.ingest`/`entrypoint` (story T001,
"Out of scope" — additif uniquement au socle d'ingestion existant).

Le parametre `--table` selectionne UNE table du registre opt-in
`purge_specs.PURGE_ENABLED_KEYS` a purger : c'est la valeur `{{input}}` d'une
iteration `for_each` du job `dcm_curated_purge` (une table = une task
parallele). Une cle hors registre (y compris une cle valide du socle
d'ingestion mais NON activee pour la purge) leve une erreur explicite.

Aucune logique metier ici (cablage uniquement) ; aucun secret code en dur (P8).
"""

from __future__ import annotations

import logging
import os
from dataclasses import replace
from typing import Any, cast

from pipelines.common.models import AzureConnectionConfig, IngestionSpec
from pipelines.common.purge import purge_absent_rows, write_purge_audit_record
from pipelines.common.runtime import (
    LOCAL_DEBUG_PROFILE,
    LocalDebugSecrets,
    local_debug_spark,
    on_databricks_cluster,
    parse_named_parameters,
)
from pipelines.system_tables.purge_specs import (
    CURATED_PURGE_AUDIT_LOG,
    PURGE_ENABLED_KEYS,
)
from pipelines.system_tables.specs import DEFAULT_CATALOG, DEFAULT_SCHEMA, SPECS

# Parametres nommes passes par la tache `python_wheel_task` (named_parameters).
# Aucun n'est sensible : les identifiants Entra du SP sont resolus depuis le
# secret scope Databricks via `dbutils.secrets` (P8 : jamais en dur). `table`
# selectionne la table du registre opt-in a purger (valeur `{{input}}` du
# `for_each`). `dry_run` : "true" simule (calcule + trace en audit) sans DELETE.
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
    "dry_run",
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

    Identique a `pipelines.system_tables.entrypoint._read_azure_config` (meme
    contrat de parametres/secrets) — duplique volontairement (job separe,
    aucun import croise vers `system_tables.entrypoint`, cf. story T001).
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


def _selected_purge_keys(params: dict[str, str]) -> tuple[str, ...]:
    """Resout les tables a purger depuis le parametre `--table`.

    - `table` renseigne (iteration `for_each`) : une seule table. Une cle
      inconnue du registre OPT-IN (meme une table valide du socle d'ingestion
      mais non activee pour la purge) leve une erreur explicite.
    - `table` vide (debug local) : toutes les tables activees, sequentiellement.
    """
    table = params["table"].strip()
    if not table:
        return tuple(PURGE_ENABLED_KEYS)
    if table not in PURGE_ENABLED_KEYS:
        known = ", ".join(PURGE_ENABLED_KEYS)
        raise ValueError(
            f"Table inconnue ou non activee pour la purge '{table}' ; "
            f"valeurs attendues : {known}."
        )
    return (table,)


def main(spark: Any, secrets: Any, params: dict[str, str]) -> None:  # noqa: ANN401
    """Orchestration : purge la (ou les) table(s) curated selectionnee(s) (AWS ⊎ Azure).

    Meme garde-fou de qualification UC que `system_tables.entrypoint.main`
    (`catalog`/`schema` obligatoires) : sans qualification, le `COUNT`/`MERGE`
    de purge s'executerait dans le catalog/schema par defaut de la session
    au lieu de la cible Unity Catalog reelle.
    """
    catalog = params["catalog"].strip()
    schema = params["schema"].strip()
    if not catalog or not schema:
        raise ValueError(
            "Les parametres 'catalog' et 'schema' sont requis pour qualifier les "
            "tables curated (sinon lecture/suppression dans le catalog/schema par "
            "defaut de la session au lieu de la cible Unity Catalog)."
        )
    schema_prefix = f"{catalog}.{schema}"
    audit_table = f"{schema_prefix}.{CURATED_PURGE_AUDIT_LOG}"
    collection_run_id = params["collection_run_id"]
    collected_at = params["collected_at"]
    dry_run = params["dry_run"].strip().lower() == "true"
    azure_config = _read_azure_config(params, secrets)

    for key in _selected_purge_keys(params):
        spec = SPECS[key]
        guardrail = PURGE_ENABLED_KEYS[key]
        # `curated_table` du registre reste NON qualifie (portable entre targets
        # dev/prod) ; la qualification n'intervient qu'a l'execution, comme dans
        # `system_tables.entrypoint.main`.
        qualified_spec: IngestionSpec = replace(
            spec, curated_table=f"{schema_prefix}.{spec.curated_table}"
        )
        purge_kwargs: dict[str, Any] = {
            "collection_run_id": collection_run_id,
            "collected_at": collected_at,
            "threshold_absolute": guardrail.threshold_absolute,
            "threshold_percentage": guardrail.threshold_percentage,
            "dry_run": dry_run,
            "azure_config": azure_config,
        }
        record = purge_absent_rows(spark, qualified_spec, "aws", **purge_kwargs)
        write_purge_audit_record(spark, audit_table, record)
        if azure_config is not None:
            record = purge_absent_rows(spark, qualified_spec, "azure", **purge_kwargs)
            write_purge_audit_record(spark, audit_table, record)


def _debug_params_from_env() -> dict[str, str]:
    """Assemble les `named_parameters` de debug depuis les env vars `DBG_*`.

    En prod (tache wheel) ces valeurs viennent des `named_parameters` du job ;
    en debug elles proviennent de la config de lancement VS Code. Defaut vide
    ⇒ parametre non fourni (`DBG_AZURE_HOST=""` desactive la lecture Azure ;
    `DBG_TABLE=""` purge toutes les tables activees ; `DBG_DRY_RUN=""` ⇒
    `dry_run=False`). `collection_run_id`/`collected_at` generes localement.
    """
    import uuid
    from datetime import UTC, datetime

    params = {name: os.environ.get(f"DBG_{name.upper()}", "") for name in PARAM_NAMES}
    params["collection_run_id"] = params["collection_run_id"] or f"local-debug-{uuid.uuid4()}"
    params["collected_at"] = params["collected_at"] or datetime.now(UTC).isoformat()
    params["catalog"] = params["catalog"] or DEFAULT_CATALOG
    params["schema"] = params["schema"] or DEFAULT_SCHEMA
    return params


def run(argv: list[str] | None = None) -> None:  # pragma: no cover - runtime Databricks
    """Point d'entree console de la tache wheel (`[project.scripts]`).

    Identique au cablage de `system_tables.entrypoint.run` (cluster vs debug
    local via Databricks Connect) — voir ce module pour le detail.
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
