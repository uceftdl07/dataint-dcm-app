"""Tests for POST /api/v1/chat (Talk-to-Data Phase 0)."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.main import app
from app.chat.genie_client import GenieClient, extract_genie_message_text
from app.chat.intent import detect_intent


@pytest.fixture(autouse=True)
def reset_chat_provider() -> Iterator[None]:
    settings = app.state.settings
    original_provider = settings.chat_provider
    settings.chat_provider = "local_loaders"
    try:
        yield
    finally:
        settings.chat_provider = original_provider


class TestGenieMessageParsing:
    def test_extract_text_from_attachments(self) -> None:
        message = SimpleNamespace(
            content="",
            attachments=[
                SimpleNamespace(
                    text=SimpleNamespace(content="Top pipeline failures by cloud."),
                    query=None,
                )
            ],
        )
        assert extract_genie_message_text(message) == "Top pipeline failures by cloud."

    def test_extract_text_from_message_content(self) -> None:
        message = SimpleNamespace(content="Direct answer.", attachments=[])
        assert extract_genie_message_text(message) == "Direct answer."


class TestGenieClient:
    def test_requires_space_id(self) -> None:
        settings = app.state.settings
        original_space = settings.genie_space_id
        settings.genie_space_id = ""
        try:
            client = GenieClient(settings)
            assert client.configured is False
        finally:
            settings.genie_space_id = original_space


class TestDetectIntent:
    def test_costs_intent(self) -> None:
        assert detect_intent("Compare my Azure and AWS costs this month") == "costs"

    def test_pipelines_intent(self) -> None:
        assert detect_intent("Which jobs failed today?") == "pipelines"

    def test_pipelines_intent_multicloud(self) -> None:
        assert detect_intent("Which pipelines are failing on Azure and AWS?") == "pipelines"

    def test_unsupported_intent(self) -> None:
        assert detect_intent("Can you tell me a joke?") == "unsupported"


class TestPostChat:
    async def test_chat_health(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/chat/health")
        assert resp.status_code == 200
        assert resp.json() == {
            "status": "ok",
            "mode": "phase0-template",
            "llm_enabled": False,
        }

    async def test_costs_answer(self, client: AsyncClient, mock_db: AsyncMock) -> None:
        mock_db.fetchscalar.return_value = 1500.0
        mock_db.fetchall.side_effect = [
            [{"cloud_provider": "azure", "total": 1000.0}],
            [{"service_name": "Databricks", "cloud_provider": "azure", "total": 800.0}],
        ]

        resp = await client.post(
            "/api/v1/chat",
            json={"messages": [{"role": "user", "content": "Compare my cloud costs"}]},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["intent"] == "costs"
        assert body["source_label"] == "DCM API"
        assert "FinOps summary" in body["text"]
        assert len(body["thinking_steps"]) == 3

    async def test_unsupported_answer(self, client: AsyncClient, mock_db: AsyncMock) -> None:
        resp = await client.post(
            "/api/v1/chat",
            json={"messages": [{"role": "user", "content": "Tell me a joke"}]},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["intent"] == "unsupported"
        assert body["source_label"] == "DataIQ"
        assert "cannot answer this question" in body["text"].lower()

    async def test_api_error_answer(self, client: AsyncClient, mock_db: AsyncMock) -> None:
        mock_db.fetchscalar.side_effect = RuntimeError("warehouse unavailable")

        resp = await client.post(
            "/api/v1/chat",
            json={"messages": [{"role": "user", "content": "Compare my cloud costs"}]},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["source_label"] == "Error API"
        assert "cannot reach the DCM APIs" in body["text"]

    async def test_genie_provider_answer(self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = app.state.settings
        original_provider = settings.chat_provider
        original_space_id = settings.genie_space_id
        settings.chat_provider = "genie"
        settings.genie_space_id = "01f15e67003e126ea459bf68f629f2d9"

        from app.chat.genie_client import GenieAnswer

        async def _fake_ask(self, question: str) -> GenieAnswer:  # noqa: ANN001
            return GenieAnswer(text=f"GENIE: {question}", sources=["genie_space"])

        monkeypatch.setattr("app.chat.genie_client.GenieClient.ask", _fake_ask)
        try:
            resp = await client.post(
                "/api/v1/chat",
                json={"messages": [{"role": "user", "content": "Compare my cloud costs"}]},
            )
        finally:
            settings.chat_provider = original_provider
            settings.genie_space_id = original_space_id

        assert resp.status_code == 200
        body = resp.json()
        assert body["source_label"] == "Databricks Genie"
        assert body["text"].startswith("GENIE:")

    async def test_genie_handles_unsupported_intent(self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = app.state.settings
        original_provider = settings.chat_provider
        original_space_id = settings.genie_space_id
        settings.chat_provider = "genie"
        settings.genie_space_id = "01f15e67003e126ea459bf68f629f2d9"

        from app.chat.genie_client import GenieAnswer

        async def _fake_ask(self, question: str) -> GenieAnswer:  # noqa: ANN001
            return GenieAnswer(text=f"GENIE: {question}", sources=["genie_space"])

        monkeypatch.setattr("app.chat.genie_client.GenieClient.ask", _fake_ask)
        try:
            resp = await client.post(
                "/api/v1/chat",
                json={"messages": [{"role": "user", "content": "fait une proposition pour corriger ça"}]},
            )
        finally:
            settings.chat_provider = original_provider
            settings.genie_space_id = original_space_id

        assert resp.status_code == 200
        body = resp.json()
        assert body["source_label"] == "Databricks Genie"
        assert body["text"].startswith("GENIE:")

    async def test_requires_messages(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/chat", json={"messages": []})
        assert resp.status_code == 422
