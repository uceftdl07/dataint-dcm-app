"""Notification channel validation and dry-run test helpers."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

__all__ = ["validate_channel_config", "test_notification_channel"]

SUPPORTED_CHANNEL_TYPES = {"teams", "email"}
_SECRET_KEY_MARKERS = ("secret", "token", "password", "webhook_url", "api_key")


def _contains_raw_secret_key(value: dict[str, Any]) -> bool:
    for key, item in value.items():
        normalized_key = key.lower()
        if any(marker in normalized_key for marker in _SECRET_KEY_MARKERS):
            if not normalized_key.endswith("_ref") and normalized_key != "secret_ref":
                return True
        if isinstance(item, dict) and _contains_raw_secret_key(item):
            return True
    return False


def validate_channel_config(channel_type: str, config: dict[str, Any]) -> dict[str, Any]:
    """Validate supported notification configs without accepting raw secrets."""
    if channel_type not in SUPPORTED_CHANNEL_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only teams and email notification channels are supported",
        )
    if _contains_raw_secret_key(config):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Notification config must store secret references, not raw secret values",
        )

    if channel_type == "teams" and not config.get("webhook_secret_ref"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Teams channels require webhook_secret_ref",
        )
    if channel_type == "email" and not config.get("recipients"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email channels require recipients",
        )
    return config


async def test_notification_channel(channel_type: str, config: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic dry-run result; real delivery is outside this feature scope."""
    validate_channel_config(channel_type, config)
    return {
        "status": "accepted",
        "channel_type": channel_type,
        "dry_run": True,
        "message": "Notification channel configuration is valid.",
    }
