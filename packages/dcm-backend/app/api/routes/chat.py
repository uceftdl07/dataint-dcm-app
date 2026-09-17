"""Talk-to-Data conversational endpoint (Phase 0 — templates, no LLM)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import Depends, Request
from fastapi.routing import APIRouter
from pydantic import BaseModel, Field

from ...auth.dependencies import get_allowed_lz_ids
from ...chat.service import ChatAnswer, resolve_chat_answer
from ...db.connection import DatabricksWarehousePool, get_db

__all__ = ["router"]

router = APIRouter()


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)


class ChatResponse(BaseModel):
    intent: str
    thinking_steps: list[str]
    text: str
    source_label: str
    sources: list[str]


class ChatHealthResponse(BaseModel):
    status: Literal["ok"]
    mode: Literal["phase0-template"]
    llm_enabled: bool


@router.get("/health", response_model=ChatHealthResponse)
async def get_chat_health() -> ChatHealthResponse:
    """Simple readiness endpoint for Talk-to-Data chat API."""
    return ChatHealthResponse(
        status="ok",
        mode="phase0-template",
        llm_enabled=False,
    )


@router.post("", response_model=ChatResponse)
async def post_chat(
    fastapi_request: Request,
    request: ChatRequest,
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
) -> ChatResponse:
    """Answer a natural-language question using live DCM Unity Catalog data."""
    answer: ChatAnswer = await resolve_chat_answer(
        db,
        fastapi_request.app.state.settings,  # type: ignore[attr-defined]
        allowed_lz_ids,
        [{"role": message.role, "content": message.content} for message in request.messages],
    )
    return ChatResponse(
        intent=answer.intent,
        thinking_steps=answer.thinking_steps,
        text=answer.text,
        source_label=answer.source_label,
        sources=answer.sources,
    )
