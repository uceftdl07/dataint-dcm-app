"""DCM authentication — Entra ID OAuth2 ``client_credentials`` client.

Typical usage::

    from dcm_commons.auth import EntraIDAuthClient

    auth = EntraIDAuthClient(
        tenant_id=settings.tenant_id,
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        scope=settings.oauth_scope,
    )
    token = auth.get_token()
"""

from __future__ import annotations

from dcm_commons.auth.entra_id import EntraIDAuthClient, TokenCredential

__all__ = [
    "EntraIDAuthClient",
    "TokenCredential",
]
