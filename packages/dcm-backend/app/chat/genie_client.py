"""Databricks Genie client using the Genie Conversation API (SDK)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from databricks.sdk import WorkspaceClient

from ..config import Settings

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True)
class GenieAnswer:
    text: str
    sources: list[str]


class GenieClient:
    """Call a configured Genie Space via the Databricks SDK."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def configured(self) -> bool:
        return bool(
            self._settings.genie_space_id.strip()
            and (self._settings.databricks_token.strip() or self._settings.uses_spn_auth())
        )

    def _build_workspace_client(self) -> WorkspaceClient:
        host = f"https://{self._settings.databricks_host}"
        if self._settings.databricks_token.strip():
            return WorkspaceClient(host=host, token=self._settings.databricks_token.strip())
        return WorkspaceClient(
            host=host,
            client_id=self._settings.databricks_spn_client_id,
            client_secret=self._settings.databricks_spn_client_secret,
        )

    async def ask(self, question: str) -> GenieAnswer:
        space_id = self._settings.genie_space_id.strip()
        if not space_id:
            raise RuntimeError("DCM_GENIE_SPACE_ID is required for Genie.")
        if not self.configured:
            raise RuntimeError("Genie is not configured (missing Databricks credentials).")

        client = self._build_workspace_client()

        def _call() -> Any:
            return client.genie.start_conversation_and_wait(
                space_id=space_id,
                content=question,
                timeout=timedelta(seconds=_DEFAULT_TIMEOUT_SECONDS),
            )

        logger.info("Genie SDK ask space_id=%s...", space_id[:8])
        message = await asyncio.to_thread(_call)
        text = extract_genie_message_text(message)
        if not text:
            raise RuntimeError("Genie answer was empty.")
        return GenieAnswer(text=text, sources=[f"genie_space:{space_id}"])


def extract_genie_message_text(message: Any) -> str:
    """Extract readable text from a Genie SDK message object."""
    parts: list[str] = []

    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        parts.append(content.strip())

    attachments = getattr(message, "attachments", None) or []
    for attachment in attachments:
        text_obj = getattr(attachment, "text", None)
        if text_obj is not None:
            text_content = getattr(text_obj, "content", None)
            if isinstance(text_content, str) and text_content.strip():
                parts.append(text_content.strip())
                continue

        query_obj = getattr(attachment, "query", None)
        if query_obj is not None:
            query_text = getattr(query_obj, "query", None) or getattr(query_obj, "description", None)
            if isinstance(query_text, str) and query_text.strip():
                parts.append(f"SQL:\n{query_text.strip()}")

    if parts:
        return "\n\n".join(parts)

    status = getattr(message, "status", None)
    if status is not None:
        return str(status)
    return ""
