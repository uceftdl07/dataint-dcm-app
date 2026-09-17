"""Talk-to-Data chat orchestration service."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..config import Settings
from ..db.connection import DatabricksWarehousePool
from .genie_client import GenieClient
from .intent import ChatIntent, detect_intent, get_thinking_steps
from .loaders import load_chat_data
from .templates import TemplateAnswer, build_answer, build_api_error_answer, build_unsupported_answer

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatAnswer:
    intent: ChatIntent
    thinking_steps: list[str]
    text: str
    source_label: str
    sources: list[str]


def _extract_latest_user_query(messages: list[dict[str, str]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user" and message.get("content", "").strip():
            return message["content"].strip()
    return ""


def _to_chat_answer(intent: ChatIntent, template: TemplateAnswer) -> ChatAnswer:
    return ChatAnswer(
        intent=intent,
        thinking_steps=get_thinking_steps(intent),
        text=template.text,
        source_label=template.source_label,
        sources=template.sources,
    )


def _resolved_chat_provider(settings: Settings) -> str:
    provider = settings.chat_provider.strip().lower()
    if provider in ("", "empty") and settings.genie_space_id.strip():
        return "genie"
    return provider


def _uses_genie(settings: Settings) -> bool:
    return _resolved_chat_provider(settings) == "genie" and bool(settings.genie_space_id.strip())


async def _answer_via_genie(settings: Settings, intent: ChatIntent, query: str) -> ChatAnswer:
    genie = GenieClient(settings)
    genie_answer = await genie.ask(query)
    return ChatAnswer(
        intent=intent,
        thinking_steps=get_thinking_steps(intent),
        text=genie_answer.text,
        source_label="Databricks Genie",
        sources=genie_answer.sources,
    )


async def resolve_chat_answer(
    db: DatabricksWarehousePool,
    settings: Settings,
    allowed_lz_ids: list[str] | None,
    messages: list[dict[str, str]],
) -> ChatAnswer:
    """Resolve a chat answer from the latest user message."""
    query = _extract_latest_user_query(messages)
    intent = detect_intent(query)
    provider = _resolved_chat_provider(settings)

    if _uses_genie(settings):
        logger.info(
            "Talk-to-Data using Genie space_id=%s intent=%s",
            settings.genie_space_id.strip()[:8] + "...",
            intent,
        )
        try:
            return await _answer_via_genie(settings, intent, query)
        except Exception:
            logger.exception(
                "Genie failed for intent=%s — falling back to local_loaders if supported",
                intent,
            )
            if intent == "unsupported":
                return _to_chat_answer(intent, build_unsupported_answer())
    else:
        logger.info(
            "Talk-to-Data using local_loaders provider=%r genie_space_id=%s intent=%s",
            provider,
            "set" if settings.genie_space_id.strip() else "EMPTY",
            intent,
        )

    if intent == "unsupported":
        return _to_chat_answer(intent, build_unsupported_answer())

    try:
        data = await load_chat_data(db, allowed_lz_ids, intent)
        return _to_chat_answer(intent, build_answer(intent, data))
    except Exception:
        logger.exception("Talk-to-Data chat failed for intent=%s provider=%s", intent, provider)
        return _to_chat_answer(intent, build_api_error_answer())
