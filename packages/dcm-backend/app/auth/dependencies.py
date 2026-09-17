"""FastAPI dependencies for Entra identity, DCM roles and LZ permissions."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from functools import lru_cache
from typing import Annotated, Any
from urllib.request import urlopen
from uuid import uuid4

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field

from ..config import Settings
from ..db.connection import DatabricksWarehousePool, get_db
from ..db.tables import qualified_table
from .notifications import notify_new_pending_user
from .role_permissions import (
    DCM_EFFECTIVE_ROLES,
    DCM_STORED_ROLES,
    LEGACY_UNRESTRICTED_ROLES,
    map_effective_role,
    resolves_to_platform_admin,
)
from .scope_model import AllowedScope

__all__ = [
    "AuthenticatedIdentity",
    "CurrentUser",
    "clear_auth_user_cache",
    "get_allowed_lz_ids",
    "get_allowed_workspace_ids",
    "get_authenticated_identity",
    "get_current_user",
    "invalidate_auth_user_cache",
    "is_platform_admin",
    "require_role",
]

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)
DCM_ROLES = set(DCM_STORED_ROLES)
PENDING_ACCOUNT_MESSAGE = (
    "Votre compte est en attente d'approbation par un administrateur DCM."
)

def _expected_audiences(settings: Settings) -> set[str]:
    audience = settings.entra_client_id.strip()
    if not audience:
        return set()

    audiences = {audience}
    if audience.startswith("api://"):
        app_id = audience.removeprefix("api://")
        if "/" not in app_id:
            audiences.add(app_id)
    return audiences


def _audience_matches(claimed_audience: Any, expected_audiences: set[str]) -> bool:
    if not expected_audiences:
        return True
    if isinstance(claimed_audience, str):
        return claimed_audience in expected_audiences
    if isinstance(claimed_audience, list):
        return any(str(audience) in expected_audiences for audience in claimed_audience)
    return False


def _expected_issuers(settings: Settings) -> set[str]:
    tenant_id = settings.entra_tenant_id.strip()
    if not tenant_id:
        return set()

    return {
        f"https://login.microsoftonline.com/{tenant_id}/v2.0",
        f"https://sts.windows.net/{tenant_id}/",
    }


def _issuer_matches(claimed_issuer: Any, expected_issuers: set[str]) -> bool:
    if not expected_issuers:
        return True
    return isinstance(claimed_issuer, str) and claimed_issuer in expected_issuers


class CurrentUser(BaseModel):
    """Authenticated DCM user loaded from Entra claims and ``dcm_app_users``."""

    id: str
    entra_oid: str
    email: str
    display_name: str | None = None
    role: str
    platform_role: str = "user"
    is_active: bool = True
    lz_ids: list[str] = Field(default_factory=list)
    scope: AllowedScope = Field(default_factory=AllowedScope)
    claims: dict[str, Any] = Field(default_factory=dict)


def _email_from_claims(claims: dict[str, Any]) -> str | None:
    for claim_name in ("preferred_username", "upn", "email"):
        value = claims.get(claim_name)
        if value:
            return str(value)
    return None


# Reuse DCM user + LZ access across parallel API calls (same page load).
_AUTH_USER_CACHE_TTL_SECONDS = 60
_AUTH_USER_CACHE_MAX_ENTRIES = 500
_auth_user_cache: dict[str, tuple[CurrentUser, float]] = {}
_auth_user_cache_lock = asyncio.Lock()


def _auth_cache_key(claims: dict[str, Any]) -> str | None:
    entra_oid = str(claims.get("oid") or claims.get("sub") or "").strip()
    if entra_oid:
        return f"oid:{entra_oid}"
    email = _email_from_claims(claims)
    if email:
        return f"email:{email.lower()}"
    return None


def _purge_expired_auth_user_cache_locked(now: float | None = None) -> None:
    current = now if now is not None else time.monotonic()
    expired_keys = [
        key for key, (_, expires_at) in _auth_user_cache.items() if current >= expires_at
    ]
    for key in expired_keys:
        del _auth_user_cache[key]


async def _get_cached_dcm_user(cache_key: str) -> CurrentUser | None:
    async with _auth_user_cache_lock:
        entry = _auth_user_cache.get(cache_key)
        if entry is None:
            _purge_expired_auth_user_cache_locked()
            return None
        user, expires_at = entry
        if time.monotonic() >= expires_at:
            del _auth_user_cache[cache_key]
            return None
        return user


async def _set_cached_dcm_user(cache_key: str, user: CurrentUser) -> None:
    async with _auth_user_cache_lock:
        _purge_expired_auth_user_cache_locked()
        _auth_user_cache[cache_key] = (user, time.monotonic() + _AUTH_USER_CACHE_TTL_SECONDS)
        if len(_auth_user_cache) > _AUTH_USER_CACHE_MAX_ENTRIES:
            oldest_key = min(_auth_user_cache, key=lambda key: _auth_user_cache[key][1])
            del _auth_user_cache[oldest_key]


def clear_auth_user_cache() -> None:
    """Drop all cached DCM users (tests, deploy hooks)."""
    _auth_user_cache.clear()


def invalidate_auth_user_cache(*, entra_oid: str | None = None, email: str | None = None) -> None:
    """Drop one cached user after admin role/LZ changes."""
    keys: list[str] = []
    if entra_oid:
        keys.append(f"oid:{entra_oid}")
    if email:
        keys.append(f"email:{email.lower()}")
    for key in keys:
        _auth_user_cache.pop(key, None)


@lru_cache(maxsize=8)
def _fetch_jwks(jwks_uri: str) -> dict[str, Any]:
    with urlopen(jwks_uri, timeout=10) as response:  # noqa: S310 - trusted configured URL
        return json.loads(response.read().decode("utf-8"))


async def _decode_claims(
    settings: Settings,
    credentials: HTTPAuthorizationCredentials | None,
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        logger.warning("[DCM_AUTH] rejected: missing or invalid Authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jwks_uri = settings.resolved_entra_jwks_uri
    if not jwks_uri:
        logger.error("[DCM_AUTH] rejected: DCM_ENTRA_TENANT_ID is not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DCM_ENTRA_TENANT_ID is not configured",
        )

    token = credentials.credentials
    logger.info(
        "[DCM_AUTH] jwt_decode_start entra_client_id=%s expected_audiences=%s token_len=%s",
        settings.entra_client_id or "(empty)",
        sorted(_expected_audiences(settings)),
        len(token),
    )
    try:
        header = jwt.get_unverified_header(token)
        jwks = await asyncio.to_thread(_fetch_jwks, jwks_uri)
        key = next(
            (item for item in jwks.get("keys", []) if item.get("kid") == header.get("kid")),
            None,
        )
        if key is None:
            logger.warning(
                "[DCM_AUTH] rejected: JWT signing key not found kid=%s",
                header.get("kid"),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="JWT signing key not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=None,
            options={
                "verify_aud": False,
                "verify_iss": False,
            },
        )
        logger.info(
            "[DCM_AUTH] jwt_claims aud=%s iss=%s oid=%s email=%s",
            claims.get("aud"),
            claims.get("iss"),
            claims.get("oid") or claims.get("sub"),
            _email_from_claims(claims) or "(empty)",
        )
        if not _audience_matches(claims.get("aud"), _expected_audiences(settings)):
            logger.warning(
                "[DCM_AUTH] rejected: invalid audience token_aud=%s expected=%s",
                claims.get("aud"),
                sorted(_expected_audiences(settings)),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token audience",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not _issuer_matches(claims.get("iss"), _expected_issuers(settings)):
            logger.warning(
                "[DCM_AUTH] rejected: invalid issuer token_iss=%s expected=%s",
                claims.get("iss"),
                sorted(_expected_issuers(settings)),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token issuer",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return claims
    except HTTPException:
        raise
    except JWTError as exc:
        logger.warning("[DCM_AUTH] rejected: invalid bearer token error=%s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def _is_unrestricted(*, role: str, platform_role: str) -> bool:
    """Does this user bypass project scoping entirely?

    Platform admins do, by design. Legacy DCM data-admins also do, as an explicit
    TRANSITION (:data:`LEGACY_UNRESTRICTED_ROLES`) so pre-015 accounts keep their
    access until they are onboarded to projects — the target model is that every
    non-platform-admin only sees the scope of their projects.
    """
    if resolves_to_platform_admin(role=role, platform_role=platform_role):
        return True
    return role in LEGACY_UNRESTRICTED_ROLES


def _scope_from_flat(
    *, role: str, platform_role: str, lz_ids: list[str], workspace_ids: list[str]
) -> AllowedScope:
    """Build a scope from flat sources (dev headers / legacy access)."""
    if _is_unrestricted(role=role, platform_role=platform_role):
        return AllowedScope(unrestricted=True)
    return AllowedScope(lz_ids=list(lz_ids), workspace_ids=list(workspace_ids))


def _dev_user_from_headers(request: Request) -> CurrentUser:
    role = request.headers.get("x-dcm-role", "viewer")
    if role not in DCM_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid X-DCM-Role")

    raw_lz_ids = request.headers.get("x-dcm-lz-ids", "")
    lz_ids = [item.strip() for item in raw_lz_ids.split(",") if item.strip()]
    raw_ws_ids = request.headers.get("x-dcm-workspace-ids", "")
    workspace_ids = [item.strip() for item in raw_ws_ids.split(",") if item.strip()]
    platform_role = request.headers.get("x-dcm-platform-role", "user")
    return CurrentUser(
        id=request.headers.get("x-dcm-user-id", "dev-user"),
        entra_oid=request.headers.get("x-dcm-entra-oid", "dev-entra-oid"),
        email=request.headers.get("x-dcm-email", "dev.user@example.com"),
        display_name=request.headers.get("x-dcm-display-name", "DCM Dev User"),
        role=role,
        platform_role=platform_role,
        is_active=True,
        lz_ids=lz_ids,
        scope=_scope_from_flat(
            role=role,
            platform_role=platform_role,
            lz_ids=lz_ids,
            workspace_ids=workspace_ids,
        ),
        claims={"auth_disabled": True},
    )


async def _load_dcm_user(
    db: DatabricksWarehousePool,
    settings: Settings,
    claims: dict[str, Any],
) -> CurrentUser:
    entra_oid = str(claims.get("oid") or claims.get("sub") or "")
    email = _email_from_claims(claims)
    if not entra_oid and not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain a usable user identifier",
        )

    users_table = qualified_table(settings, "dcm_app_users")
    logger.info(
        "[DCM_AUTH] unity_catalog_lookup catalog=%s schema=%s table=%s entra_oid=%s email=%s",
        settings.databricks_catalog,
        settings.databricks_schema,
        users_table,
        entra_oid or "(empty)",
        email or "(empty)",
    )
    user = await db.fetchone(
        f"""
        SELECT id, entra_oid, email, display_name, role, platform_role, is_active
        FROM {users_table}
        WHERE entra_oid = ? OR LOWER(email) = LOWER(?)
        LIMIT 1
        """,
        entra_oid,
        email or "",
    )
    if user is None:
        if not entra_oid or not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token does not contain a usable user identifier",
            )
        display_name = str(claims.get("name") or email)
        user_id = str(uuid4())
        logger.info(
            "[DCM_AUTH] auto_create_pending catalog=%s schema=%s entra_oid=%s email=%s",
            settings.databricks_catalog,
            settings.databricks_schema,
            entra_oid,
            email,
        )
        await db.execute(
            f"""
            INSERT INTO {users_table}
                (id, entra_oid, email, display_name, role, is_active, created_at, last_login_at)
            VALUES (?, ?, ?, ?, 'pending', FALSE, current_timestamp(), current_timestamp())
            """,
            user_id,
            entra_oid,
            email,
            display_name,
        )
        await notify_new_pending_user(
            settings,
            email=email,
            display_name=display_name,
            entra_oid=entra_oid,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="account_pending",
        )

    if user["role"] not in DCM_ROLES:
        logger.warning(
            "[DCM_AUTH] invalid_role catalog=%s schema=%s email=%s role=%s",
            settings.databricks_catalog,
            settings.databricks_schema,
            user["email"],
            user["role"],
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid DCM role")

    # Best-effort telemetry: concurrent requests race on the same row and Delta
    # raises DELTA_CONCURRENT_APPEND — never let that failure break auth.
    try:
        await db.execute(
            f"""
            UPDATE {users_table}
            SET last_login_at = current_timestamp()
            WHERE id = ?
            """,
            user["id"],
        )
    except Exception as exc:  # noqa: BLE001 - last_login write must not fail auth
        logger.warning(
            "[DCM_AUTH] last_login_update_failed email=%s error=%s",
            user["email"],
            exc,
        )

    if user["role"] == "pending":
        logger.warning(
            "[DCM_AUTH] account_pending catalog=%s schema=%s email=%s",
            settings.databricks_catalog,
            settings.databricks_schema,
            user["email"],
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="account_pending",
        )
    if not bool(user["is_active"]):
        logger.warning(
            "[DCM_AUTH] account_inactive catalog=%s schema=%s email=%s",
            settings.databricks_catalog,
            settings.databricks_schema,
            user["email"],
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="account_inactive",
        )
    effective_role = map_effective_role(user["role"])
    if effective_role is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid DCM role")

    stored_entra_oid = user["entra_oid"]
    if entra_oid and str(stored_entra_oid).startswith("email:"):
        await db.execute(
            f"""
            UPDATE {users_table}
            SET entra_oid = ?
            WHERE id = ?
            """,
            entra_oid,
            user["id"],
        )
        stored_entra_oid = entra_oid

    platform_role = user["platform_role"] or "user"
    # Feature 016 — a user's data scope IS their project membership: the LZ +
    # Databricks-workspace scope is the union of the caller's ACTIVE projects,
    # computed once here so the per-route ``get_allowed_lz_ids`` dependency stays
    # DB-free. The flat ``dcm_user_lz_access`` table is no longer an access
    # source. Legacy DCM data-admins keep unrestricted access as an explicit
    # transition — see :func:`_is_unrestricted`.
    if _is_unrestricted(role=effective_role, platform_role=platform_role):
        scope = AllowedScope(unrestricted=True)
    else:
        from .scope import get_allowed_scope

        scope = await get_allowed_scope(
            db, settings, user_id=user["id"], platform_role=platform_role
        )
    # ``lz_ids`` is a derived, backward-compat view of the LZ dimension for the
    # few display/edge consumers (``/auth/me``, notification defaults); empty for
    # unrestricted admins, exactly as before.
    lz_ids = list(scope.lz_ids)
    logger.info(
        "[DCM_AUTH] success catalog=%s schema=%s email=%s role=%s lz_count=%s",
        settings.databricks_catalog,
        settings.databricks_schema,
        user["email"],
        user["role"],
        len(lz_ids),
    )
    return CurrentUser(
        id=user["id"],
        entra_oid=stored_entra_oid,
        email=user["email"],
        display_name=user["display_name"],
        role=effective_role,
        platform_role=platform_role,
        is_active=bool(user["is_active"]),
        lz_ids=lz_ids,
        scope=scope,
        claims=claims,
    )


async def get_current_user(
    request: Request,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    settings: Settings = request.app.state.settings
    if settings.auth_disabled:
        logger.info("[DCM_AUTH] auth_disabled path=%s using dev headers", request.url.path)
        return _dev_user_from_headers(request)

    logger.info(
        "[DCM_AUTH] request path=%s auth_disabled=%s catalog=%s schema=%s",
        request.url.path,
        settings.auth_disabled,
        settings.databricks_catalog,
        settings.databricks_schema,
    )
    claims = await _decode_claims(settings, credentials)
    cache_key = _auth_cache_key(claims)
    if cache_key is not None:
        cached_user = await _get_cached_dcm_user(cache_key)
        if cached_user is not None:
            logger.info(
                "[DCM_AUTH] cache_hit key=%s email=%s path=%s",
                cache_key,
                cached_user.email,
                request.url.path,
            )
            return cached_user.model_copy(update={"claims": claims})

    user = await _load_dcm_user(db, settings, claims)
    if cache_key is not None:
        await _set_cached_dcm_user(cache_key, user)
    return user


async def get_allowed_lz_ids(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[str] | None:
    """Return allowed LZ IDs; ``None`` means unrestricted full-data access.

    Feature 015 — the LZ scope is derived from the caller's active projects and
    carried on :class:`CurrentUser` (computed once at auth time). Reading it here
    keeps every existing metric route project-scoped on the LZ dimension with
    zero per-route change (decision D3) and without an extra query.
    """
    if current_user.scope.unrestricted:
        return None
    return current_user.scope.lz_ids


async def get_allowed_workspace_ids(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[str] | None:
    """Return allowed Databricks workspace IDs; ``None`` means unrestricted.

    The second dimension of the project scope, the counterpart of
    :func:`get_allowed_lz_ids`. Gold ``gold_dbx_compute_*`` tables carry a
    ``workspace_id`` but no ``source_lz_id``, so this is the *only* dimension
    that can scope them: without it a project member reads every workspace's
    compute and warehouse metrics.
    """
    if current_user.scope.unrestricted:
        return None
    return current_user.scope.workspace_ids


def is_platform_admin(current_user: CurrentUser) -> bool:
    """Is the caller a platform admin? Use this instead of comparing role strings.

    Single entry point for every guard and every response field, so the admin UI,
    ``require_platform_admin`` and the RBAC permission set can never disagree on
    who is a platform admin.
    """
    return resolves_to_platform_admin(
        role=current_user.role, platform_role=current_user.platform_role
    )


def require_role(*roles: str) -> Callable[[CurrentUser], CurrentUser]:
    invalid_roles = set(roles) - DCM_EFFECTIVE_ROLES
    if invalid_roles:
        raise ValueError(f"Unknown DCM roles: {', '.join(sorted(invalid_roles))}")

    async def _dependency(
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
    ) -> CurrentUser:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient DCM role",
            )
        return current_user

    return _dependency


class AuthenticatedIdentity(BaseModel):
    """Entra identity proven by a valid token, without a DCM account.

    Self-service register/join are hit by a visitor who is signed in with Entra
    but has no ``dcm_app_users`` row yet, so :func:`get_current_user` (which 403s
    on pending accounts) cannot be used. The identity is taken from the verified
    token, never from the request body — closing the email-spoofing gap.
    """

    entra_oid: str
    email: str
    display_name: str | None = None
    claims: dict[str, Any] = Field(default_factory=dict)


async def get_authenticated_identity(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthenticatedIdentity:
    """Verified Entra identity for endpoints open to not-yet-provisioned users."""
    settings: Settings = request.app.state.settings
    if settings.auth_disabled:
        return AuthenticatedIdentity(
            entra_oid=request.headers.get("x-dcm-entra-oid", "dev-entra-oid"),
            email=request.headers.get("x-dcm-email", "dev.user@example.com"),
            display_name=request.headers.get("x-dcm-display-name", "DCM Dev User"),
            claims={"auth_disabled": True},
        )

    claims = await _decode_claims(settings, credentials)
    entra_oid = str(claims.get("oid") or claims.get("sub") or "").strip()
    email = _email_from_claims(claims)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token does not contain a usable email",
        )
    return AuthenticatedIdentity(
        entra_oid=entra_oid,
        email=email,
        display_name=str(claims.get("name") or email),
        claims=claims,
    )
