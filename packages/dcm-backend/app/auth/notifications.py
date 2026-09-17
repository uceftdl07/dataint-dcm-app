"""Outbound notifications for DCM auth lifecycle events."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from ..config import Settings

__all__ = ["notify_new_pending_user"]

logger = logging.getLogger(__name__)


async def notify_new_pending_user(
    settings: Settings,
    *,
    email: str,
    display_name: str | None,
    entra_oid: str,
    created_at: str | None = None,
) -> None:
    """Notify admins on Teams when a new DCM account is auto-created as pending."""
    webhook_url = settings.teams_webhook_url
    if not webhook_url:
        logger.warning("Teams webhook URL not configured, skipping pending-user notification")
        return

    admin_url = f"{settings.frontend_url.rstrip('/')}/admin?tab=users&filter=pending"
    card = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "themeColor": "FFA500",
        "summary": f"New pending DCM user: {email}",
        "sections": [
            {
                "activityTitle": "🆕 New DCM user awaiting approval",
                "activitySubtitle": display_name or email,
                "facts": [
                    {"name": "Email", "value": email},
                    {"name": "Display name", "value": display_name or "—"},
                    {"name": "Entra OID", "value": entra_oid},
                    {"name": "Status", "value": "pending — no portal access yet"},
                    {"name": "Created at", "value": created_at or "just now"},
                ],
                "text": (
                    "A new employee signed in via Microsoft Entra ID. "
                    "Approve their role and Landing Zones in DCM Admin → Access Control → Pending."
                ),
            }
        ],
        "potentialAction": [
            {
                "@type": "OpenUri",
                "name": "Review in DCM Admin",
                "targets": [{"os": "default", "uri": admin_url}],
            }
        ],
    }

    try:
        data = json.dumps(card).encode("utf-8")
        req = UrlRequest(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=30) as response:  # noqa: S310
            if response.status != 200:
                logger.error("Teams webhook returned status %s", response.status)
    except Exception as exc:
        logger.error("Failed to send pending-user Teams notification: %s", exc, exc_info=True)
