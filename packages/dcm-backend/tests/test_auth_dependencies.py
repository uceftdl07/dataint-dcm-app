from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.auth.dependencies import (
    CurrentUser,
    _auth_cache_key,
    _get_cached_dcm_user,
    _set_cached_dcm_user,
    _audience_matches,
    _expected_audiences,
    _expected_issuers,
    _issuer_matches,
    clear_auth_user_cache,
    get_current_user,
    invalidate_auth_user_cache,
)
from app.config import Settings


def test_expected_audiences_accepts_app_id_uri_and_client_id() -> None:
    settings = Settings(entra_client_id="api://15817864-589d-4a33-ada4-ec40fa309a7b")

    audiences = _expected_audiences(settings)

    assert "api://15817864-589d-4a33-ada4-ec40fa309a7b" in audiences
    assert "15817864-589d-4a33-ada4-ec40fa309a7b" in audiences
    assert _audience_matches("api://15817864-589d-4a33-ada4-ec40fa309a7b", audiences)
    assert _audience_matches("15817864-589d-4a33-ada4-ec40fa309a7b", audiences)


def test_expected_issuers_accepts_entra_v1_and_v2_tokens() -> None:
    settings = Settings(entra_tenant_id="329e91b0-e21f-48fb-a071-456717ecc28e")

    issuers = _expected_issuers(settings)

    assert _issuer_matches(
        "https://login.microsoftonline.com/329e91b0-e21f-48fb-a071-456717ecc28e/v2.0",
        issuers,
    )
    assert _issuer_matches(
        "https://sts.windows.net/329e91b0-e21f-48fb-a071-456717ecc28e/",
        issuers,
    )


def test_auth_cache_key_prefers_entra_oid() -> None:
    claims = {"oid": "user-oid", "preferred_username": "user@example.com"}

    assert _auth_cache_key(claims) == "oid:user-oid"


def test_auth_cache_key_falls_back_to_email() -> None:
    claims = {"preferred_username": "User@Example.COM"}

    assert _auth_cache_key(claims) == "email:user@example.com"


@pytest.mark.asyncio()
async def test_auth_user_cache_hit_skips_databricks_lookup() -> None:
    clear_auth_user_cache()
    claims = {"oid": "cached-user", "preferred_username": "cached@example.com"}
    cached_user = CurrentUser(
        id="user-1",
        entra_oid="cached-user",
        email="cached@example.com",
        role="viewer",
        lz_ids=["lz-a"],
        claims=claims,
    )
    await _set_cached_dcm_user("oid:cached-user", cached_user)

    request = AsyncMock()
    request.url.path = "/api/v1/dashboard/overview"
    request.app.state.settings = Settings(auth_disabled=False)

    with patch("app.auth.dependencies._decode_claims", AsyncMock(return_value=claims)):
        with patch("app.auth.dependencies._load_dcm_user", AsyncMock()) as load_user:
            user = await get_current_user(request, AsyncMock(), AsyncMock())

    load_user.assert_not_awaited()
    assert user.id == "user-1"
    assert user.lz_ids == ["lz-a"]
    assert user.claims == claims


@pytest.mark.asyncio()
async def test_auth_user_cache_miss_loads_and_stores_user() -> None:
    clear_auth_user_cache()
    claims = {"oid": "fresh-user", "preferred_username": "fresh@example.com"}
    loaded_user = CurrentUser(
        id="user-2",
        entra_oid="fresh-user",
        email="fresh@example.com",
        role="manager",
        lz_ids=["lz-b"],
        claims=claims,
    )

    request = AsyncMock()
    request.url.path = "/api/v1/pipelines"
    request.app.state.settings = Settings(auth_disabled=False)

    with patch("app.auth.dependencies._decode_claims", AsyncMock(return_value=claims)):
        with patch(
            "app.auth.dependencies._load_dcm_user",
            AsyncMock(return_value=loaded_user),
        ) as load_user:
            user = await get_current_user(request, AsyncMock(), AsyncMock())

    load_user.assert_awaited_once()
    assert user == loaded_user
    assert await _get_cached_dcm_user("oid:fresh-user") == loaded_user


@pytest.mark.asyncio()
async def test_invalidate_auth_user_cache_drops_oid_and_email_keys() -> None:
    clear_auth_user_cache()
    user = CurrentUser(
        id="user-3",
        entra_oid="drop-me",
        email="drop@example.com",
        role="viewer",
    )
    await _set_cached_dcm_user("oid:drop-me", user)
    await _set_cached_dcm_user("email:drop@example.com", user)

    invalidate_auth_user_cache(entra_oid="drop-me", email="Drop@Example.COM")

    assert await _get_cached_dcm_user("oid:drop-me") is None
    assert await _get_cached_dcm_user("email:drop@example.com") is None
