"""Microsoft Entra ID OAuth2 ``client_credentials`` authentication client.

Used by both Azure and AWS collector agents to acquire JWT bearer tokens that
are sent to the Apigee ingestion gateway on every payload delivery.

Thread safety
-------------
``EntraIDAuthClient`` is safe to share across threads.  The token cache is
protected by ``threading.Lock``, which serialises concurrent refresh attempts.
MSAL's ``ConfidentialClientApplication`` is synchronous — it must not be called
from an async context without a thread executor.  The collector agent should
call ``get_token()`` from a sync context (e.g. inside ``run_in_executor``) or
during the non-async startup phase before the event loop starts.

Token lifecycle
---------------
Tokens are cached in memory and considered expired 60 seconds before the
server-reported ``expires_in`` deadline (configurable via ``expiry_buffer_seconds``).
This buffer prevents using a token that is valid at the time of the check but
expires during the in-flight HTTP call to Apigee.

Example::

    from dcm_commons.auth.entra_id import EntraIDAuthClient

    auth = EntraIDAuthClient(
        tenant_id="329e91b0-…",
        client_id="4d96093b-…",
        client_secret=os.environ["DCM_CLIENT_SECRET"],
        scope="api://…/.default",
    )
    token = auth.get_token()   # cached after first call
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import msal  # type: ignore[import-untyped]

from dcm_commons.exceptions import AuthenticationError
from dcm_commons.logging_utils import get_logger

__all__ = ["EntraIDAuthClient", "TokenCredential"]

_DEFAULT_EXPIRY_BUFFER_SECONDS = 60
_DEFAULT_TOKEN_TTL_SECONDS = 3600  # fallback when 'expires_in' is absent from MSAL response


@dataclass(frozen=True, slots=True)
class TokenCredential:
    """Immutable holder for a cached access token.

    Attributes:
        access_token: The raw JWT bearer token string.
        expires_at:   UTC datetime after which the token is considered expired.
    """

    access_token: str
    expires_at: datetime

    def is_expired(self, buffer_seconds: int = _DEFAULT_EXPIRY_BUFFER_SECONDS) -> bool:
        """Return ``True`` if the token will expire within ``buffer_seconds``.

        Args:
            buffer_seconds: Safety margin before the server-reported expiry.
                            Defaults to 60 s to account for clock skew and
                            network latency between token check and usage.
        """
        deadline = self.expires_at - timedelta(seconds=buffer_seconds)
        return datetime.now(timezone.utc) >= deadline


class EntraIDAuthClient:
    """Acquires and caches OAuth2 bearer tokens via the ``client_credentials`` grant.

    Tokens are cached in memory and refreshed transparently before expiry.
    This class is safe to use from multiple threads (protected by a ``Lock``).

    Args:
        tenant_id:              Azure AD tenant GUID.
        client_id:              App Registration client (application) ID.
        client_secret:          App Registration client secret value.
        scope:                  OAuth2 scope requested from Entra ID.
                                For Apigee, typically ``"api://{client_id}/.default"``.
        expiry_buffer_seconds:  Refresh the token this many seconds before the
                                server-reported expiry deadline.  Defaults to 60.

    Raises:
        AuthenticationError: If MSAL fails to acquire a token (wrong credentials,
                             expired secret, insufficient permissions, etc.).
    """

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        scope: str,
        *,
        expiry_buffer_seconds: int = _DEFAULT_EXPIRY_BUFFER_SECONDS,
    ) -> None:
        self._scope = scope
        self._expiry_buffer = expiry_buffer_seconds
        self._cached_token: TokenCredential | None = None
        self._lock = threading.Lock()
        self._logger = get_logger(__name__)
        self._app = msal.ConfidentialClientApplication(
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
        )

    def get_token(self) -> str:
        """Return a valid access token, refreshing the cache if necessary.

        Thread-safe: concurrent callers will queue behind the lock and receive
        the same token once the first refresh completes.

        Returns:
            A valid JWT bearer token string.

        Raises:
            AuthenticationError: If token acquisition fails.
        """
        with self._lock:
            if self._cached_token is None or self._cached_token.is_expired(self._expiry_buffer):
                self._refresh_token()
            else:
                self._logger.info(
                    "entra_id_token_cache_hit",
                    scope=self._scope,
                    expires_at=self._cached_token.expires_at.isoformat(),
                )
            # At this point _refresh_token() has either succeeded or raised.
            assert self._cached_token is not None  # noqa: S101 — invariant
            return self._cached_token.access_token

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _refresh_token(self) -> None:
        """Acquire a fresh token from Entra ID and update the cache.

        Must be called while holding ``self._lock``.  Raises
        ``AuthenticationError`` on any MSAL failure so that callers never
        receive a ``RuntimeError`` or a bare dictionary-access ``KeyError``.
        """
        self._logger.info("entra_id_token_refresh_started", scope=self._scope)

        result: dict[str, object] = self._app.acquire_token_for_client(scopes=[self._scope])

        if "access_token" not in result:
            error: str = str(
                result.get("error_description")
                or result.get("error")
                or "unknown MSAL error"
            )
            self._logger.error("entra_id_token_refresh_failed", reason=error)
            raise AuthenticationError(error)

        expires_in = int(result.get("expires_in", _DEFAULT_TOKEN_TTL_SECONDS))
        self._cached_token = TokenCredential(
            access_token=str(result["access_token"]),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        )
        self._logger.info(
            "entra_id_token_refresh_succeeded",
            scope=self._scope,
            expires_in_seconds=expires_in,
        )
