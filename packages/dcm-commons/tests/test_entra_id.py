"""Tests for EntraIDAuthClient.

Coverage:
    - Successful token acquisition and in-memory caching.
    - Automatic refresh when token is expired.
    - MSAL failure maps to AuthenticationError (not RuntimeError).
    - Token expiry buffer: token refreshed before the hard deadline.
    - Thread safety: concurrent get_token() calls do not double-refresh.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from freezegun import freeze_time

from dcm_commons.auth.entra_id import EntraIDAuthClient, TokenCredential
from dcm_commons.exceptions import AuthenticationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_msal_success(token: str = "tok-abc", expires_in: int = 3600) -> dict:
    """Return a minimal MSAL success response dict."""
    return {"access_token": token, "expires_in": expires_in}


def _make_msal_failure(error: str = "invalid_client") -> dict:
    """Return a minimal MSAL error response dict."""
    return {"error": error, "error_description": f"{error}: details"}


def _make_client(
    msal_app: MagicMock,
    scope: str = "api://dcm/.default",
) -> EntraIDAuthClient:
    """Build an ``EntraIDAuthClient`` with the provided mocked MSAL app.

    ``msal.ConfidentialClientApplication`` is patched *before* construction so
    that ``EntraIDAuthClient.__init__`` never makes real network calls to Azure.
    """
    with patch("dcm_commons.auth.entra_id.msal.ConfidentialClientApplication", return_value=msal_app):
        client = EntraIDAuthClient(
            tenant_id="tenant-id",
            client_id="client-id",
            client_secret="client-secret",
            scope=scope,
        )
    return client


# ---------------------------------------------------------------------------
# TokenCredential
# ---------------------------------------------------------------------------


class TestTokenCredential:
    def test_not_expired_well_before_deadline(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        cred = TokenCredential(access_token="tok", expires_at=future)
        assert cred.is_expired() is False

    def test_expired_when_past_deadline(self) -> None:
        past = datetime.now(timezone.utc) - timedelta(seconds=1)
        cred = TokenCredential(access_token="tok", expires_at=past)
        assert cred.is_expired() is True

    def test_expired_within_buffer(self) -> None:
        """Token should be considered expired when within the buffer window."""
        almost_expired = datetime.now(timezone.utc) + timedelta(seconds=30)
        cred = TokenCredential(access_token="tok", expires_at=almost_expired)
        # buffer_seconds=60 > 30 s remaining → expired
        assert cred.is_expired(buffer_seconds=60) is True

    def test_frozen_dataclass(self) -> None:
        cred = TokenCredential(
            access_token="tok",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            cred.access_token = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# EntraIDAuthClient
# ---------------------------------------------------------------------------


class TestEntraIDAuthClientSuccess:
    """Happy-path token acquisition."""

    def test_get_token_calls_msal_on_first_call(self) -> None:
        msal_app = MagicMock()
        msal_app.acquire_token_for_client.return_value = _make_msal_success("token-1")
        client = _make_client(msal_app)

        token = client.get_token()

        assert token == "token-1"
        msal_app.acquire_token_for_client.assert_called_once()

    def test_second_call_uses_cache(self) -> None:
        msal_app = MagicMock()
        msal_app.acquire_token_for_client.return_value = _make_msal_success("token-2")
        client = _make_client(msal_app)

        t1 = client.get_token()
        t2 = client.get_token()

        assert t1 == t2 == "token-2"
        # MSAL should only be called once — second call uses cache
        msal_app.acquire_token_for_client.assert_called_once()

    def test_token_refreshed_after_expiry(self) -> None:
        msal_app = MagicMock()
        # First call returns a very short-lived token (expires in 1 s)
        msal_app.acquire_token_for_client.side_effect = [
            _make_msal_success("token-short", expires_in=1),
            _make_msal_success("token-fresh", expires_in=3600),
        ]
        client = _make_client(msal_app)

        first = client.get_token()

        # Manually expire the cached token
        assert client._cached_token is not None
        expired = TokenCredential(
            access_token=client._cached_token.access_token,
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        client._cached_token = expired

        second = client.get_token()

        assert first == "token-short"
        assert second == "token-fresh"
        assert msal_app.acquire_token_for_client.call_count == 2


class TestEntraIDAuthClientFailure:
    """Token acquisition failure handling."""

    def test_msal_error_raises_authentication_error(self) -> None:
        msal_app = MagicMock()
        msal_app.acquire_token_for_client.return_value = _make_msal_failure("invalid_client")
        client = _make_client(msal_app)

        with pytest.raises(AuthenticationError) as exc_info:
            client.get_token()

        assert "invalid_client" in str(exc_info.value)

    def test_msal_empty_response_raises_authentication_error(self) -> None:
        msal_app = MagicMock()
        msal_app.acquire_token_for_client.return_value = {}  # no access_token key
        client = _make_client(msal_app)

        with pytest.raises(AuthenticationError):
            client.get_token()

    def test_raises_authentication_error_not_runtime_error(self) -> None:
        msal_app = MagicMock()
        msal_app.acquire_token_for_client.return_value = _make_msal_failure()
        client = _make_client(msal_app)

        with pytest.raises(AuthenticationError):
            client.get_token()
        # Ensure it's not accidentally a RuntimeError
        try:
            client.get_token()
        except AuthenticationError:
            pass
        except RuntimeError as exc:
            pytest.fail(f"Expected AuthenticationError, got RuntimeError: {exc}")


class TestEntraIDAuthClientThreadSafety:
    """Concurrent get_token() calls must not cause double-refresh."""

    def test_concurrent_calls_refresh_once(self) -> None:
        call_count = 0
        lock = threading.Lock()

        def _slow_acquire(**_kwargs: object) -> dict:
            nonlocal call_count
            time.sleep(0.05)  # simulate network latency
            with lock:
                call_count += 1
            return _make_msal_success("shared-token")

        msal_app = MagicMock()
        msal_app.acquire_token_for_client.side_effect = _slow_acquire
        client = _make_client(msal_app)

        tokens: list[str] = []
        errors: list[Exception] = []

        def _worker() -> None:
            try:
                tokens.append(client.get_token())
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=_worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Unexpected errors: {errors}"
        assert all(tok == "shared-token" for tok in tokens)
        # The lock ensures only one thread performs the MSAL call
        assert call_count == 1
