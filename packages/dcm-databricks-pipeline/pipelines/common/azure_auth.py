"""Authentification Azure AD (Entra M2M) pour la ressource Databricks.

Isole le flux client-credentials : un service principal Entra obtient un jeton
d'acces pour la ressource Azure Databricks, ensuite passe au SQL Warehouse. Les
identifiants proviennent d'une `AzureConnectionConfig` (jamais en dur — P8).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pipelines.common.models import AzureConnectionConfig


# ID de ressource Azure AD de Databricks (constant, identique pour tous les tenants).
AZURE_DATABRICKS_RESOURCE = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"


def make_credentials_provider(
    config: AzureConnectionConfig,
) -> Callable[..., Callable[[], dict[str, str]]]:
    """Retourne un `credentials_provider` (auto-refresh) pour le SQL connector.

    `ClientSecretCredential` cache le token et le rafraichit automatiquement
    avant expiration. En passant un `credentials_provider` au lieu d'un token
    statique, le connecteur rappelle `header_factory()` a chaque requete Thrift
    et obtient toujours un token valide — meme apres 1h de `fetchmany` en boucle
    sur les grandes tables (bug RequestError avec le token statique).
    """
    from azure.identity import ClientSecretCredential

    credential = ClientSecretCredential(
        tenant_id=config.tenant_id,
        client_id=config.client_id,
        client_secret=config.client_secret,
    )

    def header_factory() -> dict[str, str]:
        token = credential.get_token(f"{AZURE_DATABRICKS_RESOURCE}/.default").token
        return {"Authorization": f"Bearer {token}"}

    # CredentialsProvider = () -> HeaderFactory ; HeaderFactory = () -> headers.
    def credentials_provider() -> Callable[[], dict[str, str]]:
        return header_factory

    return credentials_provider
