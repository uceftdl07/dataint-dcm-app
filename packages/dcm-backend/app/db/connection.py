"""Async wrapper for Databricks SQL Warehouse connections.

The databricks-sql-connector library is synchronous. Blocking calls run in
``asyncio.to_thread`` so FastAPI handlers stay non-blocking.

Auth order: SPN OAuth M2M (``credentials_provider``) if client id + secret are set,
otherwise PAT via ``access_token`` (local dev only).

A bounded pool of connections is opened at startup. Each query checks out one
connection, runs, then returns it. Stale sessions are discarded (never returned
to the pool) and replaced so the pool does not keep dead handles.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any, TypeVar

import httpx
from databricks import sql
from databricks.sdk.core import Config, oauth_service_principal
from fastapi import HTTPException, Request

from ..config import Settings
from .tables import qualified_table

__all__ = ["DatabricksWarehousePool", "get_db"]

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT_SECONDS = 30
_CONNECT_TIMEOUT_GRACE_SECONDS = 5
_DEFAULT_POOL_SIZE = 8
_POOL_ACQUIRE_TIMEOUT_SECONDS = 30

# Azure AD resource ID for Azure Databricks (first-party app).
_AZURE_DATABRICKS_SCOPE = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default"

_STALE_SESSION_MARKERS = (
    "invalid sessionhandle",
    "session is closed",
    "session expired",
)

_T = TypeVar("_T")


def _fetch_azure_aad_token(settings: Settings) -> str:
    """Exchange Azure AD SPN credentials for a Databricks workspace access token."""
    tenant = settings.entra_tenant_id.strip()
    if not tenant:
        raise ValueError("DCM_ENTRA_TENANT_ID is required for Azure AD SPN auth")

    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": settings.databricks_spn_client_id,
        "client_secret": settings.databricks_spn_client_secret,
        "scope": _AZURE_DATABRICKS_SCOPE,
    }
    with httpx.Client(timeout=_CONNECT_TIMEOUT_SECONDS) as client:
        response = client.post(url, data=data)
        if response.status_code >= 400:
            detail = response.text[:300]
            raise ValueError(
                f"Azure AD token request failed ({response.status_code}): {detail}"
            )
        token = response.json().get("access_token")
        if not token:
            raise ValueError("Azure AD token response missing access_token")
        return token


def _credential_provider(settings: Settings) -> Callable[[], Callable[[], dict[str, str]]]:
    """Return credentials_provider for databricks-sql-connector.

    The connector calls ``provider()`` once to get a header factory, then
    ``header_factory()`` on each request (see ``ExternalAuthProvider``).

    Azure Databricks needs an Azure AD client-credentials token. Databricks-native
    ``oauth_service_principal`` only works for Databricks-managed service principals.
    """

    def _provider() -> Callable[[], dict[str, str]]:
        if settings.entra_tenant_id.strip():

            def _azure_headers() -> dict[str, str]:
                token = _fetch_azure_aad_token(settings)
                return {"Authorization": f"Bearer {token}"}

            return _azure_headers

        config = Config(
            host=f"https://{settings.databricks_host}",
            client_id=settings.databricks_spn_client_id,
            client_secret=settings.databricks_spn_client_secret,
        )
        return oauth_service_principal(config)

    return _provider


def _is_stale_session_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in _STALE_SESSION_MARKERS)


class DatabricksWarehousePool:
    """Bounded pool of Databricks SQL Warehouse connections.

    Stored on ``app.state.db_pool`` during application lifespan.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._pool_size = _DEFAULT_POOL_SIZE
        self._acquire_timeout_seconds = _POOL_ACQUIRE_TIMEOUT_SECONDS
        self._available: asyncio.Queue[sql.Connection] = asyncio.Queue(maxsize=self._pool_size)
        self._total_connections = 0
        self._closed = False
        self._replenish_lock = asyncio.Lock()

    @property
    def pool_size(self) -> int:
        return self._pool_size

    def table(self, table_name: str) -> str:
        """Return the fully qualified reference of a monitoring table.

        The schema is environment-specific (``…__d`` in dev, ``…__p`` in prod), so a
        query that spells it out is wrong in every other environment. Use this
        wherever ``settings`` is not already at hand — the pool owns the settings, so
        no service signature has to carry them just to name a table.
        """
        return qualified_table(self._settings, table_name)

    def _create_connection_sync(self) -> sql.Connection:
        settings = self._settings
        http_path = settings.resolved_http_path
        if not http_path:
            raise ValueError(
                "Databricks HTTP path is empty — set DCM_DATABRICKS_WAREHOUSE_ID "
                "or DCM_DATABRICKS_HTTP_PATH"
            )

        connect_kwargs: dict[str, Any] = {
            "server_hostname": settings.databricks_host,
            "http_path": http_path,
            "catalog": settings.databricks_catalog,
            "schema": settings.databricks_schema,
        }
        if settings.uses_spn_auth():
            connect_kwargs["credentials_provider"] = _credential_provider(settings)
        else:
            connect_kwargs["access_token"] = settings.databricks_token

        return sql.connect(
            **connect_kwargs,
            _socket_timeout=_CONNECT_TIMEOUT_SECONDS,
            _request_timeout=_CONNECT_TIMEOUT_SECONDS,
        )

    @staticmethod
    def _close_connection_sync(connection: sql.Connection) -> None:
        try:
            connection.close()
        except Exception:  # noqa: BLE001 — best-effort close
            pass

    async def _open_connection(self) -> sql.Connection:
        timeout_seconds = _CONNECT_TIMEOUT_SECONDS + _CONNECT_TIMEOUT_GRACE_SECONDS
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._create_connection_sync),
                timeout=timeout_seconds,
            )
        except TimeoutError as exc:
            settings = self._settings
            raise TimeoutError(
                "Timed out after "
                f"{timeout_seconds}s connecting to Databricks SQL Warehouse "
                f"(host={settings.databricks_host}, http_path={settings.resolved_http_path}, "
                f"catalog={settings.databricks_catalog}, schema={settings.databricks_schema}). "
                "Check ECS outbound network/DNS/TLS access to Databricks and OAuth endpoints."
            ) from exc

    async def connect(self) -> None:
        """Pre-warm the connection pool at application startup."""
        if not self._settings.uses_spn_auth() and not self._settings.uses_pat_auth():
            raise ValueError(
                "Databricks credentials missing — set DCM_DATABRICKS_SPN_CLIENT_ID + "
                "DCM_DATABRICKS_SPN_CLIENT_SECRET (recommended) or DCM_DATABRICKS_TOKEN (PAT)"
            )

        connections = await asyncio.gather(
            *[self._open_connection() for _ in range(self._pool_size)]
        )
        for connection in connections:
            await self._available.put(connection)
            self._total_connections += 1

        logger.info(
            "Databricks SQL Warehouse pool ready (size=%s acquire_timeout=%ss)",
            self._pool_size,
            self._acquire_timeout_seconds,
        )

    async def disconnect(self) -> None:
        """Close all pooled connections on application shutdown."""
        self._closed = True
        while True:
            try:
                connection = self._available.get_nowait()
            except asyncio.QueueEmpty:
                break
            await asyncio.to_thread(self._close_connection_sync, connection)
            self._total_connections = max(0, self._total_connections - 1)

    async def _replenish_pool(self) -> None:
        """Replace one discarded connection so the pool stays at capacity."""
        async with self._replenish_lock:
            if self._closed or self._total_connections >= self._pool_size:
                return
            connection = await self._open_connection()
            self._total_connections += 1
            await self._available.put(connection)
            logger.info(
                "Databricks pool replenished (active=%s/%s)",
                self._total_connections,
                self._pool_size,
            )

    async def _acquire(self) -> sql.Connection:
        if self._closed:
            raise RuntimeError("Database pool is closed")

        try:
            return self._available.get_nowait()
        except asyncio.QueueEmpty:
            pass

        try:
            return await asyncio.wait_for(
                self._available.get(),
                timeout=self._acquire_timeout_seconds,
            )
        except TimeoutError as exc:
            in_use = self._total_connections - self._available.qsize()
            raise TimeoutError(
                "Databricks connection pool exhausted "
                f"({in_use}/{self._pool_size} in use) after "
                f"{self._acquire_timeout_seconds}s"
            ) from exc

    async def _release(self, connection: sql.Connection, *, healthy: bool) -> None:
        if self._closed or not healthy:
            await asyncio.to_thread(self._close_connection_sync, connection)
            self._total_connections = max(0, self._total_connections - 1)
            if not self._closed:
                await self._replenish_pool()
            return

        await self._available.put(connection)

    async def _run_with_connection(self, operation: Callable[[sql.Connection], _T]) -> _T:
        """Checkout a connection, run *operation*, return it or discard if stale."""

        connection = await self._acquire()

        def _attempt(active: sql.Connection) -> _T:
            return operation(active)

        try:
            result = await asyncio.to_thread(_attempt, connection)
        except Exception as exc:
            if _is_stale_session_error(exc):
                logger.warning("Databricks stale session discarded: %s", exc)
                await self._release(connection, healthy=False)
                retry_connection = await self._acquire()
                try:
                    result = await asyncio.to_thread(_attempt, retry_connection)
                except Exception as retry_exc:
                    await self._release(
                        retry_connection,
                        healthy=not _is_stale_session_error(retry_exc),
                    )
                    raise
                await self._release(retry_connection, healthy=True)
                return result
            await self._release(connection, healthy=True)
            raise
        else:
            await self._release(connection, healthy=True)
            return result

    async def fetchall(self, query: str, *args: Any) -> list[dict[str, Any]]:
        """Execute *query* and return all rows as dictionaries."""

        def _execute(connection: sql.Connection) -> list[dict[str, Any]]:
            cursor = connection.cursor()
            try:
                cursor.execute(query, args if args else None)
                if cursor.description is None:
                    return []
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]
            finally:
                cursor.close()

        return await self._run_with_connection(_execute)

    async def fetchone(self, query: str, *args: Any) -> dict[str, Any] | None:
        """Execute *query* and return the first row as a dictionary, or None."""

        def _execute(connection: sql.Connection) -> dict[str, Any] | None:
            cursor = connection.cursor()
            try:
                cursor.execute(query, args if args else None)
                if cursor.description is None:
                    return None
                columns = [desc[0] for desc in cursor.description]
                row = cursor.fetchone()
                return dict(zip(columns, row, strict=False)) if row else None
            finally:
                cursor.close()

        return await self._run_with_connection(_execute)

    async def fetchscalar(self, query: str, *args: Any) -> Any:
        """Execute *query* and return a single scalar (e.g. COUNT)."""

        def _execute(connection: sql.Connection) -> Any:
            cursor = connection.cursor()
            try:
                cursor.execute(query, args if args else None)
                row = cursor.fetchone()
                return row[0] if row else None
            finally:
                cursor.close()

        return await self._run_with_connection(_execute)

    async def execute(self, query: str, *args: Any) -> int:
        """Execute INSERT/UPDATE/DELETE and return affected row count."""

        def _execute(connection: sql.Connection) -> int:
            cursor = connection.cursor()
            try:
                cursor.execute(query, args if args else None)
                return cursor.rowcount or 0
            finally:
                cursor.close()

        return await self._run_with_connection(_execute)


def get_db(request: Request) -> DatabricksWarehousePool:
    """FastAPI dependency — returns the shared pool from ``app.state.db_pool``."""
    pool = request.app.state.db_pool
    if pool is None:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "degraded",
                "database": "unreachable",
                "error": "Database pool not initialized — no Databricks connection available",
            },
        )
    return pool  # type: ignore[no-any-return]
