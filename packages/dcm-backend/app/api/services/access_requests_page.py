"""Access request endpoints — unauthenticated DCM access requests and LZ scope extensions.

Kept out of the route per the route→service→pool pattern.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.request import Request as UrlRequest
from urllib.request import urlopen
from uuid import uuid4

from fastapi import HTTPException, status

from ...auth.dependencies import CurrentUser
from ...config import Settings
from ...db.connection import DatabricksWarehousePool
from ...db.tables import qualified_lz_dimension_table, qualified_table
from .governance_page import fetch_active_landing_zone_rows, row_to_landing_zone

__all__ = [
    "create_request",
    "create_lz_scope_extension_request",
    "fetch_landing_zones_for_request_form",
    "fetch_registration_status",
    "send_teams_notification",
    "validate_active_landing_zone_ids",
]

logger = logging.getLogger(__name__)


async def send_teams_notification(
    settings: Settings,
    request_data: dict[str, Any],
    *,
    is_reactivation: bool = False,
    is_lz_scope_extension: bool = False,
) -> None:
    """Send Teams webhook notification for new access request."""
    webhook_url = settings.teams_webhook_url
    if not webhook_url:
        # No webhook configured, skip notification
        logger.warning("Teams webhook URL not configured, skipping notification")
        return

    logger.info(f"Teams webhook URL configured: {webhook_url[:50]}...")

    # Build adaptive card for Teams
    title = (
        "🔄 DCM Account Reactivation Request" if is_reactivation else "🔔 New DCM Access Request"
    )
    who = request_data["display_name"]
    summary = f"{'Reactivation' if is_reactivation else 'New request'} from {who}"
    if is_lz_scope_extension:
        title = "➕ DCM Landing Zone Scope Request"
        summary = f"Scope extension from {request_data['display_name']}"

    card = {
        "@type": "MessageCard",
        "@context": "https://schema.org/extensions",
        "themeColor": "FF8C00" if is_reactivation else "0078D7",
        "summary": summary,
        "sections": [
            {
                "activityTitle": title,
                "activitySubtitle": f"From {request_data['display_name']}",
                "activityImage": "https://cdn-icons-png.flaticon.com/512/1077/1077063.png",
                "facts": [
                    {
                        "name": "Type",
                        "value": (
                            "Account Reactivation"
                            if is_reactivation
                            else ("Landing Zone scope" if is_lz_scope_extension else "New Account")
                        ),
                    },
                    {"name": "Email", "value": request_data["email"]},
                    {"name": "Name", "value": request_data["display_name"]},
                    {
                        "name": "Requested Landing Zones",
                        "value": ", ".join(request_data["requested_lz_ids"])
                        if request_data["requested_lz_ids"]
                        else "None (general access)",
                    },
                ],
                "text": f"**Justification:**\n\n{request_data['justification']}",
            }
        ],
        "potentialAction": [
            {
                "@type": "OpenUri",
                "name": "Manage in DCM Admin",
                "targets": [
                    {
                        "os": "default",
                        "uri": f"{settings.frontend_url}/admin?tab=notifications",
                    }
                ],
            }
        ],
    }

    # Send to Teams
    try:
        logger.info(
            f"Sending Teams notification for access request (reactivation={is_reactivation})"
        )
        headers = {"Content-Type": "application/json"}
        data = json.dumps(card).encode("utf-8")
        req = UrlRequest(webhook_url, data=data, headers=headers, method="POST")
        with urlopen(req, timeout=30) as response:  # noqa: S310 - increased timeout for Office 365
            if response.status != 200:
                logger.error(f"Teams webhook returned status {response.status}")
                raise Exception(f"Teams webhook returned {response.status}")
            logger.info(f"Teams notification sent successfully (status {response.status})")
    except Exception as exc:
        # Log but don't fail the request
        logger.error(f"Failed to send Teams notification: {exc}", exc_info=True)


async def create_request(
    db: DatabricksWarehousePool | None,
    settings: Settings,
    payload: Any,
) -> dict[str, Any]:
    """Create a new access request (unauthenticated).

    This does NOT require authentication - it's for users who are not
    yet registered in DCM. The request is stored in the database and a Teams
    notification is sent to admins.

    Raises:
        HTTPException: 409 if user already exists or has pending request
    """
    logger.info(
        f"Access request received for email={payload.email}, display_name={payload.display_name}"
    )

    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection not available",
        )

    # Check if user already exists
    users_table = qualified_table(settings, "dcm_app_users")
    existing_user = await db.fetchone(
        f"""
        SELECT id, is_active
        FROM {users_table}
        WHERE LOWER(email) = LOWER(?)
        LIMIT 1
        """,
        payload.email,
    )

    is_reactivation = False
    if existing_user is not None:
        # If user exists and is active, reject the request
        if bool(existing_user["is_active"]):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You are already registered in DCM. Please try logging in again.",
            )
        # If user exists but is inactive, allow reactivation request
        is_reactivation = True

    # Check if there's already a pending request
    requests_table = qualified_table(settings, "dcm_access_requests")
    existing_request = await db.fetchone(
        f"""
        SELECT id
        FROM {requests_table}
        WHERE LOWER(email) = LOWER(?) AND status = 'pending'
        LIMIT 1
        """,
        payload.email,
    )
    if existing_request is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a pending request. Please wait for admin review.",
        )

    # Create access request
    request_id = str(uuid4())
    lz_ids_json = json.dumps(payload.requested_lz_ids)

    await db.execute(
        f"""
        INSERT INTO {requests_table}
            (id, email, display_name, entra_oid, justification, requested_lz_ids,
             status, requested_at, reviewed_by, reviewed_at)
        VALUES (?, ?, ?, ?, ?, ?, 'pending', current_timestamp(), NULL, NULL)
        """,
        request_id,
        payload.email,
        payload.display_name,
        payload.entra_oid or f"email:{payload.email}",
        payload.justification,
        lz_ids_json,
    )

    # Send Teams notification (async, don't block on failure)
    try:
        await send_teams_notification(
            settings,
            {
                "id": request_id,
                "email": payload.email,
                "display_name": payload.display_name,
                "justification": payload.justification,
                "requested_lz_ids": payload.requested_lz_ids,
            },
            is_reactivation=is_reactivation,
        )
    except Exception as exc:
        # Log but don't fail
        logger.error(f"Teams notification failed: {exc}", exc_info=True)

    logger.info(
        f"Access request created successfully: id={request_id}, email={payload.email}, "
        f"type={'reactivation' if is_reactivation else 'new'}"
    )

    return {
        "id": request_id,
        "email": payload.email,
        "status": "pending",
        "message": "Votre demande a été envoyée aux administrateurs",
    }


async def fetch_registration_status(
    db: DatabricksWarehousePool,
    settings: Settings,
    email: str,
) -> dict[str, Any]:
    """Check whether an email is registered in DCM (unauthenticated).

    Used by the frontend to give a clear message when Entra ID token
    acquisition fails: the user may already have DCM access but be missing
    from the frontend/backend App Registration. Discloses no more than the
    409 responses of the create-request endpoint already do.
    """
    normalized = email.strip().lower()
    if "@" not in normalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="email must be a valid address",
        )

    users_table = qualified_table(settings, "dcm_app_users")
    user = await db.fetchone(
        f"""
        SELECT is_active
        FROM {users_table}
        WHERE LOWER(email) = LOWER(?)
        LIMIT 1
        """,
        normalized,
    )

    requests_table = qualified_table(settings, "dcm_access_requests")
    pending = await db.fetchone(
        f"""
        SELECT id
        FROM {requests_table}
        WHERE LOWER(email) = LOWER(?) AND status = 'pending'
        LIMIT 1
        """,
        normalized,
    )

    return {
        "registered": user is not None,
        "is_active": bool(user["is_active"]) if user is not None else False,
        "has_pending_request": pending is not None,
    }


async def fetch_landing_zones_for_request_form(
    db: DatabricksWarehousePool,
    settings: Settings,
) -> dict[str, Any]:
    """Public catalog of monitored landing zones for access-request forms."""
    rows = await fetch_active_landing_zone_rows(db, settings)
    items = [
        {
            "lz_id": lz["lz_id"],
            "lz_name": lz["lz_name"],
            "cloud_provider": lz["cloud_provider"],
            "environment": lz["environment"],
            "ba_name": lz["ba_name"],
        }
        for lz in (row_to_landing_zone(row) for row in rows)
    ]
    return {"items": items, "total": len(items)}


async def validate_active_landing_zone_ids(
    db: DatabricksWarehousePool,
    settings: Settings,
    lz_ids: list[str],
) -> None:
    table = qualified_lz_dimension_table(settings)
    placeholders = ", ".join("?" for _ in lz_ids)
    rows = await db.fetchall(
        f"""
        SELECT lz_id
        FROM {table}
        WHERE lz_id IN ({placeholders})
        """,
        *lz_ids,
    )
    existing = {row["lz_id"] for row in rows}
    missing = sorted(set(lz_ids) - existing)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Unknown or inactive landing zones", "lz_ids": missing},
        )


async def create_lz_scope_extension_request(
    db: DatabricksWarehousePool,
    settings: Settings,
    current_user: CurrentUser,
    payload: Any,
) -> dict[str, Any]:
    """Allow an active DCM user to request additional landing zone scope."""
    await validate_active_landing_zone_ids(db, settings, payload.requested_lz_ids)

    already_granted = set(current_user.lz_ids)
    if current_user.role in {"admin", "super_admin"}:
        already_granted = set(payload.requested_lz_ids)

    missing_scope = [lz_id for lz_id in payload.requested_lz_ids if lz_id not in already_granted]
    if not missing_scope:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have access to the requested landing zones",
        )

    requests_table = qualified_table(settings, "dcm_access_requests")
    existing_request = await db.fetchone(
        f"""
        SELECT id
        FROM {requests_table}
        WHERE LOWER(email) = LOWER(?) AND status = 'pending'
        LIMIT 1
        """,
        current_user.email,
    )
    if existing_request is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a pending access request. Please wait for admin review.",
        )

    request_id = str(uuid4())
    await db.execute(
        f"""
        INSERT INTO {requests_table}
            (id, email, display_name, entra_oid, justification, requested_lz_ids,
             status, requested_at, reviewed_by, reviewed_at)
        VALUES (?, ?, ?, ?, ?, ?, 'pending', current_timestamp(), NULL, NULL)
        """,
        request_id,
        current_user.email,
        current_user.display_name or current_user.email,
        current_user.entra_oid,
        payload.justification,
        json.dumps(missing_scope),
    )

    try:
        await send_teams_notification(
            settings,
            {
                "id": request_id,
                "email": current_user.email,
                "display_name": current_user.display_name or current_user.email,
                "justification": payload.justification,
                "requested_lz_ids": missing_scope,
            },
            is_lz_scope_extension=True,
        )
    except Exception as exc:
        logger.error(f"Teams notification failed: {exc}", exc_info=True)

    return {
        "id": request_id,
        "email": current_user.email,
        "status": "pending",
        "requested_lz_ids": missing_scope,
        "message": "Your landing zone request was sent to administrators",
    }
