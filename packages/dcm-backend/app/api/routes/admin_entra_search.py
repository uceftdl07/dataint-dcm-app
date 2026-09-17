"""EntraID user search endpoint using Microsoft Graph API."""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.routing import APIRouter

from ...auth.dependencies import CurrentUser
from ...auth.scope import require_platform_admin
from ...config import Settings

__all__ = ["router"]

router = APIRouter()


def _settings(request: Request) -> Settings:
    return request.app.state.settings


async def _search_entra_users(
    settings: Settings,
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search users in EntraID using Microsoft Graph API.
    
    Note: This requires proper app registration with User.Read.All permission
    and client credentials flow to get an access token for Graph API.
    
    For now, this is a placeholder implementation. In production, you need:
    1. Service principal with Graph API permissions
    2. Client credentials to get access token
    3. Call to https://graph.microsoft.com/v1.0/users
    """
    # TODO: Implement actual Microsoft Graph API call
    # This requires:
    # - Settings for Graph API client ID and secret
    # - Token acquisition using client credentials flow
    # - HTTP call to https://graph.microsoft.com/v1.0/users?$filter=...
    
    # For now, return empty list
    # In production, replace with actual Graph API implementation
    return []


@router.get("/admin/entra-users/search")
async def search_entra_users(
    request: Request,
    _: Annotated[CurrentUser, Depends(require_platform_admin)],
    q: Annotated[str, Query(min_length=2, description="Search query (email, name)")] = "",
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> dict[str, Any]:
    """Search users in Microsoft EntraID directory.
    
    **Authentication required**: super_admin role
    
    This endpoint allows administrators to search for users in the corporate
    EntraID directory to add them to DCM. The search looks for users by email
    or display name.
    
    **Microsoft Graph API Required**:
    - This endpoint requires a service principal with User.Read.All permission
    - Configure DCM_GRAPH_CLIENT_ID and DCM_GRAPH_CLIENT_SECRET in settings
    - The service principal must be granted admin consent for the permission
    
    Example:
    ```
    GET /api/v1/admin/entra-users/search?q=john.doe&limit=10
    ```
    
    Returns:
        dict: List of matching users with id, email, displayName, jobTitle
        
    Raises:
        HTTPException: 401 if not authenticated, 403 if not super_admin
    """
    settings = _settings(request)
    
    if not q or len(q) < 2:
        return {
            "items": [],
            "total": 0,
            "query": q,
        }
    
    try:
        users = await _search_entra_users(settings, q, limit)
        return {
            "items": users,
            "total": len(users),
            "query": q,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"EntraID search failed: {str(exc)}",
        ) from exc
