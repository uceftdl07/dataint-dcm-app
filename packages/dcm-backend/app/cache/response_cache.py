"""Short-lived in-memory cache for read-heavy API responses."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from ..auth.scope_model import AllowedScope

T = TypeVar("T")

_CACHE: dict[str, tuple[Any, float]] = {}
_CACHE_LOCK = asyncio.Lock()
_DEFAULT_TTL_SECONDS = 120.0
_MAX_ENTRIES = 256


def _purge_expired_locked(now: float | None = None) -> None:
    current = now if now is not None else time.monotonic()
    expired = [key for key, (_, expires_at) in _CACHE.items() if current >= expires_at]
    for key in expired:
        del _CACHE[key]


def build_cache_key(namespace: str, **parts: Any) -> str:
    payload = json.dumps(parts, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode()).hexdigest()[:24]
    return f"{namespace}:{digest}"


def cache_key_ids(ids: list[str] | None) -> list[str] | None:
    """Normalize an ID scope list for :func:`build_cache_key`.

    Order must not create distinct keys, but ``None`` and ``[]`` must never
    share one: ``None`` means "no filter — every row", while ``[]`` means "an
    empty scope — no row at all" (see ``resolve_effective_lz_ids``). Since this
    cache is process-wide and shared by all callers, a truthiness test here
    (``if ids else None``) would hand an unrestricted admin's payload to a
    project member whose scope resolves to nothing.
    """
    return sorted(ids) if ids is not None else None


def cache_key_scope(scope: AllowedScope) -> dict[str, Any]:
    """Normalize a two-dimension RBAC scope for :func:`build_cache_key`.

    The cache is process-wide, so **every** dimension a query filters on has to
    appear in the key. Keying on the LZ dimension alone was harmless only as long
    as the workspace dimension was not enforced; the moment it is, two projects
    sharing an LZ scope but granted different workspaces would read each other's
    payload — the exact leak the filter is there to prevent.
    """
    if scope.unrestricted:
        return {"unrestricted": True}
    return {
        "unrestricted": False,
        "lz_ids": sorted(scope.lz_ids),
        "workspace_ids": sorted(scope.workspace_ids),
    }


async def get_cached_response(
    key: str,
    fetch: Callable[[], Awaitable[T]],
    *,
    ttl_seconds: float = _DEFAULT_TTL_SECONDS,
) -> T:
    now = time.monotonic()
    async with _CACHE_LOCK:
        _purge_expired_locked(now)
        entry = _CACHE.get(key)
        if entry is not None and entry[1] > now:
            return entry[0]

    result = await fetch()

    async with _CACHE_LOCK:
        _purge_expired_locked()
        _CACHE[key] = (result, time.monotonic() + ttl_seconds)
        if len(_CACHE) > _MAX_ENTRIES:
            oldest_key = min(_CACHE, key=lambda candidate: _CACHE[candidate][1])
            del _CACHE[oldest_key]

    return result


def clear_response_cache() -> None:
    """Drop all cached API payloads (tests, deploy hooks)."""
    _CACHE.clear()
