"""Runtime generique : parsing des parametres et bootstrap de debug local.

Regroupe les briques d'orchestration independantes du domaine :
  - `parse_named_parameters` : parse les `named_parameters` d'une tache wheel ;
  - `on_databricks_cluster` : detecte le contexte d'execution ;
  - `LocalDebugSecrets` / `local_debug_spark` : runtime de debug local via
    Databricks Connect (breakpoints hors cluster).
Aucun secret n'est code en dur (constitution DCM P8) ; les surcharges d'env sont
injectees par l'appelant.
"""

from __future__ import annotations

import argparse
import os
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from pyspark.sql import SparkSession


# Profil CLI (~/.databrickscfg) par defaut pour le debug local. Surchargeable via
# la variable d'env `DATABRICKS_CONFIG_PROFILE`.
# Profil OAuth (U2M) et NON `DEFAULT` : les PAT (`token = dapi...`) sont
# interdits, et c'est precisement ce que `DEFAULT` contient sur les postes
# configures avant cette regle -- un defaut pointant dessus fait authentifier
# chaque debug local avec un PAT. Cree/rafraichi par
# `databricks auth login --host <workspace> --profile dcm-dev` (cf. README).
LOCAL_DEBUG_PROFILE = "dcm-dev"


def parse_named_parameters(
    param_names: Sequence[str], argv: list[str] | None = None
) -> dict[str, str]:
    """Parse les `named_parameters` d'une tache wheel (`--cle valeur`).

    Databricks passe les `named_parameters` du `python_wheel_task` sur la ligne
    de commande. On les recupere via argparse (defaut vide ⇒ parametre optionnel
    non fourni), ce qui remplace les `dbutils.widgets` du mode notebook.
    """
    parser = argparse.ArgumentParser(description="DCM — ingestion system tables (tache wheel)")
    for name in param_names:
        parser.add_argument(f"--{name}", default="")
    namespace = parser.parse_args(argv)
    return {name: getattr(namespace, name) for name in param_names}


def on_databricks_cluster() -> bool:
    """True si execute sur un cluster/serverless Databricks (tache wheel).

    `DATABRICKS_RUNTIME_VERSION` n'est present que dans l'environnement d'un
    cluster Databricks ; absent en local ⇒ mode debug via Databricks Connect.
    """
    return "DATABRICKS_RUNTIME_VERSION" in os.environ


class LocalDebugSecrets:
    """Accessor `dbutils.secrets`-compatible pour le debug local.

    Expose `get(scope, key)` comme `dbutils.secrets`. Resolution :
      1. variable d'env de surcharge (`env_overrides[key]`) si definie ;
      2. sinon lecture du secret scope Databricks via le WorkspaceClient (profil
         CLI), identique a l'execution reelle sur le cluster.
    Jamais de secret code en dur (constitution DCM P8) ; `env_overrides` mappe une
    cle de secret vers le nom d'une variable d'env de surcharge locale.
    """

    def __init__(self, profile: str, env_overrides: Mapping[str, str] | None = None) -> None:
        self._profile = profile
        self._env_overrides = dict(env_overrides or {})
        self._workspace: Any = None  # WorkspaceClient paresseux : cree au 1er acces scope

    def get(self, scope: str, key: str) -> str:
        env_var = self._env_overrides.get(key)
        if env_var and os.environ.get(env_var, "").strip():
            return os.environ[env_var].strip()
        if self._workspace is None:
            from databricks.sdk import WorkspaceClient

            self._workspace = WorkspaceClient(profile=self._profile)
        return cast("str", self._workspace.dbutils.secrets.get(scope=scope, key=key))


def local_debug_spark(profile: str) -> SparkSession:
    """Session de debug local : Databricks Connect (compute serverless).

    Le code Python tourne en local (breakpoints) ; les operations Spark sont
    deleguees au compute SERVERLESS du workspace via Databricks Connect.
    """
    from databricks.connect import DatabricksSession

    return cast(
        "SparkSession", DatabricksSession.builder.profile(profile).serverless(True).getOrCreate()
    )
