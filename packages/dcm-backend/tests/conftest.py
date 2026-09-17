"""Shared pytest fixtures for dcm-backend unit tests.

All tests mock :class:`DatabricksWarehousePool` so no real Databricks SQL Warehouse
connection is needed.  The fixture patches ``app.state.db_pool`` with a
:class:`unittest.mock.AsyncMock` before each test.

Usage in test modules::

    async def test_something(client, mock_db):
        mock_db.fetchall.return_value = [...]
        resp = await client.get("/api/v1/...")
        assert resp.status_code == 200
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock, Mock

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import clear_auth_user_cache
from app.cache.response_cache import clear_response_cache
from app.db.tables import qualified_table
from app.main import app


@pytest.fixture(autouse=True)
def clear_auth_user_cache_between_tests() -> Iterator[None]:
    clear_auth_user_cache()
    yield
    clear_auth_user_cache()


@pytest.fixture(autouse=True)
def clear_response_cache_between_tests() -> Iterator[None]:
    clear_response_cache()
    yield
    clear_response_cache()


@pytest.fixture(autouse=True)
def auth_disabled_for_route_tests() -> Iterator[None]:
    """Exercise route handlers without live Entra JWT validation."""
    settings = app.state.settings
    original = settings.auth_disabled
    settings.auth_disabled = True
    try:
        yield
    finally:
        settings.auth_disabled = original


@pytest.fixture()
def mock_db() -> AsyncMock:
    """Return a fresh AsyncMock that mimics :class:`DatabricksWarehousePool`."""
    db = AsyncMock()
    db.fetchall = AsyncMock(return_value=[])
    db.fetchone = AsyncMock(return_value=None)
    db.fetchscalar = AsyncMock(return_value=None)
    db.execute = AsyncMock(return_value=1)
    # ``table`` is synchronous on the real pool: left as an AsyncMock attribute it
    # would return a coroutine and every query string would embed its repr.
    db.table = Mock(side_effect=lambda name: qualified_table(app.state.settings, name))
    return db


@pytest.fixture()
async def client(mock_db: AsyncMock) -> AsyncIterator[AsyncClient]:
    """Async httpx client with the FastAPI app, db_pool replaced by mock_db."""
    # Override app.state.db_pool with the mock — no lifespan startup needed
    app.state.db_pool = mock_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
