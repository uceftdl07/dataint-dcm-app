"""Databricks SCIM user collector — identity governance for all workspaces.

Enumerates all Databricks workspaces in the subscription, then calls the SCIM v2
API on each workspace to retrieve user accounts, group memberships, and roles.

Authentication
--------------
Uses a Databricks-scoped token (same mechanism as DatabricksCollector) rather
than a PAT token, to avoid per-workspace secret management.

Key API calls
-------------
``GET management.azure.com/.../Microsoft.Databricks/workspaces``
    List all Databricks workspace ARM resources in the subscription.
``GET {workspace_url}/api/2.0/preview/scim/v2/Users``
    SCIM v2 paginated list of user accounts in a workspace.
    Parameters: ``startIndex`` (1-based), ``count`` (page size, max 100).
``GET {workspace_url}/api/2.0/preview/scim/v2/Groups``
    Resolve group display names (optional enrichment).

Governance use cases enabled
-----------------------------
- Detect inactive users (``last_activity_at`` > 90 days old).
- Monitor privilege creep (unexpected admin memberships).
- Count active vs total users per workspace.
- Track group membership changes over time (Delta time-travel on CURATED).

Lakebase target
---------------
``dcm.monitoring.user_metrics``
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from azure.identity import DefaultAzureCredential  # type: ignore[import-untyped]

from dcm_commons.collectors.base import BaseCollector
from dcm_commons.exceptions import CollectionError
from dcm_commons.logging_utils import get_logger
from dcm_commons.models.enums import CloudProvider, MetricDomain, UserType
from dcm_commons.models.user import UserMetric

from azure_collector._azure_utils import get_databricks_token, get_mgmt_token

__all__ = ["DatabricksUserCollector"]

_logger = get_logger(__name__)

_MGMT_BASE = "https://management.azure.com"
_DB_API_VERSION = "2023-02-01"
_SCIM_PAGE_SIZE = 100
_REQUEST_TIMEOUT = 30.0


class DatabricksUserCollector(BaseCollector):
    """Collects user identity snapshots from all Databricks workspaces.

    One :class:`UserMetric` is produced per user per workspace.  The SCIM API
    does not expose ``last_activity_at`` natively; for that, the Databricks
    Audit Log API (cluster or notebook events) would be needed.  This collector
    sets ``last_activity_at=None`` and populates ``groups`` and ``roles``
    from the SCIM response.

    Args:
        source_lz_id:     Landing zone identifier.
        subscription_id:  Azure subscription ID.
        credential:       ``azure.identity`` credential.  If ``None``,
                          ``DefaultAzureCredential`` is used.
        max_users_per_workspace: Cap per workspace to avoid very large payloads.
        max_retries:      Retry attempts on transient failures.
        retry_base_delay_seconds: Base delay for exponential back-off.
    """

    def __init__(
        self,
        source_lz_id: str,
        subscription_id: str,
        *,
        credential: Any | None = None,
        max_users_per_workspace: int = 5000,
        max_retries: int = 3,
        retry_base_delay_seconds: float = 2.0,
    ) -> None:
        super().__init__(
            source_lz_id=source_lz_id,
            cloud_provider=CloudProvider.AZURE,
            subscription_or_account_id=subscription_id,
            max_retries=max_retries,
            retry_base_delay_seconds=retry_base_delay_seconds,
        )
        self._subscription_id = subscription_id
        self._credential = credential or DefaultAzureCredential()
        self._max_users_per_workspace = max_users_per_workspace

    @property
    def domain(self) -> MetricDomain:
        """Return the user metric domain."""
        return MetricDomain.USER

    # ------------------------------------------------------------------
    # BaseCollector implementation
    # ------------------------------------------------------------------

    async def _collect_metrics(self) -> list[dict[str, Any]]:
        """Enumerate all Databricks workspaces and collect user SCIM data."""
        mgmt_token = await get_mgmt_token(self._credential)
        db_token = await get_databricks_token(self._credential)

        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            workspaces = await self._list_workspaces(client, mgmt_token)
            all_metrics: list[UserMetric] = []
            for ws in workspaces:
                try:
                    users = await self._collect_workspace_users(
                        client, db_token, ws
                    )
                    all_metrics.extend(users)
                except Exception as exc:  # noqa: BLE001
                    _logger.warning(
                        "user_workspace_skip workspace=%s reason=%s",
                        ws.get("name"), exc,
                    )

        _logger.info(
            "user_collected subscription=%s total=%d",
            self._subscription_id, len(all_metrics),
        )
        return [m.model_dump() for m in all_metrics]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _list_workspaces(
        self,
        client: httpx.AsyncClient,
        mgmt_token: str,
    ) -> list[dict[str, Any]]:
        """Return all Databricks workspaces in the subscription."""
        url = (
            f"{_MGMT_BASE}/subscriptions/{self._subscription_id}"
            f"/providers/Microsoft.Databricks/workspaces"
            f"?api-version={_DB_API_VERSION}"
        )
        response = await client.get(
            url, headers={"Authorization": f"Bearer {mgmt_token}"}
        )
        if response.status_code != 200:
            raise CollectionError(
                f"[DatabricksUserCollector] List workspaces failed: "
                f"HTTP {response.status_code} — {response.text}"
            )
        return response.json().get("value", [])

    async def _collect_workspace_users(
        self,
        client: httpx.AsyncClient,
        db_token: str,
        workspace: dict[str, Any],
    ) -> list[UserMetric]:
        """Paginate through the SCIM /Users endpoint for a single workspace."""
        ws_name: str = workspace.get("name", "unknown")
        props: dict[str, Any] = workspace.get("properties", {})
        workspace_url: str = props.get("workspaceUrl", "")
        if not workspace_url.startswith("https://"):
            workspace_url = f"https://{workspace_url}"

        metrics: list[UserMetric] = []
        start_index = 1  # SCIM uses 1-based pagination

        while len(metrics) < self._max_users_per_workspace:
            url = (
                f"{workspace_url}/api/2.0/preview/scim/v2/Users"
                f"?startIndex={start_index}&count={_SCIM_PAGE_SIZE}"
            )
            response = await client.get(
                url, headers={"Authorization": f"Bearer {db_token}"}
            )
            if response.status_code != 200:
                _logger.warning(
                    "user_scim_error workspace=%s status=%d",
                    ws_name, response.status_code,
                )
                break

            data = response.json()
            resources: list[dict[str, Any]] = data.get("Resources", [])
            if not resources:
                break  # last page

            for resource in resources:
                metric = self._map_scim_user(resource, workspace_url)
                if metric:
                    metrics.append(metric)

            total_results: int = data.get("totalResults", 0)
            start_index += _SCIM_PAGE_SIZE
            if start_index > total_results:
                break  # no more pages

        _logger.info(
            "user_workspace_done workspace=%s users=%d",
            ws_name, len(metrics),
        )
        return metrics

    @staticmethod
    def _map_scim_user(
        resource: dict[str, Any],
        workspace_url: str,
    ) -> UserMetric | None:
        """Map a SCIM /Users resource to a :class:`UserMetric`."""
        user_id: str = resource.get("id", "")
        if not user_id:
            return None

        # Primary username: userName field
        user_name: str = resource.get("userName", "")
        display_name: str | None = resource.get("displayName")
        is_active: bool = resource.get("active", True)

        # Groups: list of {display: "admins", $ref: "...", value: "123"}
        groups: list[str] = [
            g.get("display", "") or g.get("value", "")
            for g in resource.get("groups", [])
            if g.get("display") or g.get("value")
        ]

        # Entitlements: list of {value: "allow-cluster-create"}
        roles: list[str] = [
            e.get("value", "")
            for e in resource.get("entitlements", [])
            if e.get("value")
        ]

        return UserMetric(
            user_id=user_id,
            user_name=user_name,
            display_name=display_name,
            user_type=UserType.DATABRICKS,
            is_active=is_active,
            workspace_or_account=workspace_url,
            last_activity_at=None,  # Not available from SCIM — requires audit log
            groups=groups,
            roles=roles,
            tags={"scim_external_id": resource.get("externalId", "")},
        )
