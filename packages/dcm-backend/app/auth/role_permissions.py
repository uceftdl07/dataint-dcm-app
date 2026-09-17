"""DCM role permissions — pages, dashboard widgets and features."""

from __future__ import annotations

from typing import Any

from ..config import Settings
from ..db.connection import DatabricksWarehousePool
from ..db.tables import qualified_table

__all__ = [
    "DCM_STORED_ROLES",
    "DCM_EFFECTIVE_ROLES",
    "LEGACY_ROLE_TO_EFFECTIVE",
    "LEGACY_PLATFORM_ADMIN_ROLES",
    "LEGACY_UNRESTRICTED_ROLES",
    "PLATFORM_ADMIN_ROLE",
    "DEFAULT_ROLE_PERMISSIONS",
    "map_effective_role",
    "resolves_to_platform_admin",
    "resolve_permission_role",
    "get_role_permissions",
    "permissions_for_role",
]

# Roles still found in ``dcm_app_users.role`` (some rows predate the flat→project
# migration of feature 015). Kept for the admin UI listing, NOT for assignment.
DCM_STORED_ROLES = frozenset(
    {"pending", "viewer", "data_architect", "manager", "admin", "super_admin"}
)

# The 3 effective roles of the reduced model (FR-006): project ``viewer`` /
# project ``admin`` + platform ``super_admin``. This is the only set an admin may
# assign; ``DCM_EFFECTIVE_ROLES`` must enumerate to exactly these three (SC-003).
DCM_EFFECTIVE_ROLES = frozenset({"viewer", "admin", "super_admin"})

# Read-only compatibility mapping for legacy flat roles (FR-007). Applied when
# resolving a stored role; the legacy names are NEVER re-exposed as assignable.
# ``admin`` / ``super_admin`` / ``viewer`` are already effective (identity);
# ``pending`` and unknown roles resolve to ``None`` (no effective role).
LEGACY_ROLE_TO_EFFECTIVE: dict[str, str] = {
    "data_architect": "viewer",
    "manager": "viewer",
}


def map_effective_role(role: str) -> str | None:
    """Resolve a stored role to its effective role, or ``None`` if it has none.

    Legacy ``manager`` / ``data_architect`` map to ``viewer``; ``pending`` and
    unknown roles have no effective role. Never used to *assign* a role.
    """
    if role in DCM_EFFECTIVE_ROLES:
        return role
    return LEGACY_ROLE_TO_EFFECTIVE.get(role)


# ─── Platform-admin authority ────────────────────────────────────────────────
# Platform admin is decided by ``dcm_app_users.platform_role``, the single source
# of truth: it is what ``require_platform_admin`` reads and what the admin UI
# writes when promoting someone. ``dcm_app_users.role`` only carries the account
# lifecycle (``pending`` → ``viewer``) plus legacy values.
PLATFORM_ADMIN_ROLE = "super_admin"

# TRANSITION — rows that predate the backfill of ``platform_role`` still carry
# their authority in ``role``, so a legacy ``role = super_admin`` is honoured to
# avoid locking existing super admins out. Remove once every row is backfilled.
LEGACY_PLATFORM_ADMIN_ROLES = frozenset({"super_admin"})

# TRANSITION — legacy DCM data-admin roles keep unrestricted data access (no
# project scoping) until they are onboarded to projects. Remove with the flat
# ``dcm_user_lz_access`` path.
LEGACY_UNRESTRICTED_ROLES = frozenset({"admin", "super_admin"})


def resolves_to_platform_admin(*, role: str | None, platform_role: str | None) -> bool:
    """Is this user a platform admin? The one definition every guard shares.

    ``platform_role`` decides; a legacy ``role = super_admin`` is accepted during
    the transition (see :data:`LEGACY_PLATFORM_ADMIN_ROLES`) so pre-backfill rows
    are not locked out of the administration surfaces.
    """
    if (platform_role or "") == PLATFORM_ADMIN_ROLE:
        return True
    return (role or "") in LEGACY_PLATFORM_ADMIN_ROLES

# Fallback when dcm_role_permissions is empty or unavailable.
#
# ``viewer`` — every DCM data interface, the data itself being scoped to the
# project's LZ + Databricks workspaces. The one exception is
# ``page:unity-catalog``: the raw-table explorer takes an arbitrary
# ``catalog.schema.table``, so no scope can be attached to it and it stays with
# the unrestricted roles (see :func:`app.auth.scope.require_unrestricted_scope`).
DEFAULT_ROLE_PERMISSIONS: dict[str, dict[str, set[str]]] = {
    "pending": {"page": set(), "widget": set(), "feature": set()},
    "viewer": {
        "page": {
            "page:dashboard",
            "page:datafactory",
            "page:pipelines",
            "page:clusters",
            "page:alerts",
            "page:security",
            "page:costs",
            "page:governance",
            "page:databricks",
            "page:databases",
            "page:talk-to-data",
            "page:status",
            "page:projects",
            "page:settings",
        },
        "widget": {
            "widget:dashboard:pipelines",
            "widget:dashboard:failures",
            "widget:dashboard:clusters",
            "widget:dashboard:alerts",
            "widget:dashboard:cost_total",
            "widget:dashboard:governance",
            "widget:dashboard:finops_card",
            "widget:dashboard:datafactory_card",
            "widget:dashboard:databricks_card",
            "widget:dashboard:databases_card",
        },
        "feature": set(),
    },
    "admin": {
        "page": {
            "page:dashboard",
            "page:datafactory",
            "page:pipelines",
            "page:clusters",
            "page:alerts",
            "page:security",
            "page:costs",
            "page:governance",
            "page:users",
            "page:unity-catalog",
            "page:databricks",
            "page:databases",
            "page:talk-to-data",
            "page:projects",
            "page:settings",
            "page:status",
        },
        "widget": {
            "widget:dashboard:pipelines",
            "widget:dashboard:failures",
            "widget:dashboard:clusters",
            "widget:dashboard:alerts",
            "widget:dashboard:cost_total",
            "widget:dashboard:governance",
            "widget:dashboard:finops_card",
            "widget:dashboard:datafactory_card",
            "widget:dashboard:databricks_card",
            "widget:dashboard:databases_card",
        },
        "feature": {"feature:admin_ui"},
    },
    "super_admin": {
        "page": {
            "page:dashboard",
            "page:datafactory",
            "page:pipelines",
            "page:clusters",
            "page:alerts",
            "page:security",
            "page:costs",
            "page:governance",
            "page:users",
            "page:unity-catalog",
            "page:databricks",
            "page:databases",
            "page:talk-to-data",
            "page:projects",
            "page:settings",
            "page:status",
            "page:admin",
        },
        "widget": {
            "widget:dashboard:pipelines",
            "widget:dashboard:failures",
            "widget:dashboard:clusters",
            "widget:dashboard:alerts",
            "widget:dashboard:cost_total",
            "widget:dashboard:governance",
            "widget:dashboard:finops_card",
            "widget:dashboard:datafactory_card",
            "widget:dashboard:databricks_card",
            "widget:dashboard:databases_card",
        },
        "feature": {"feature:admin_ui"},
    },
}


def resolve_permission_role(role: str, platform_role: str | None = None) -> str:
    """Which permission set applies to this user.

    A platform admin always gets the ``super_admin`` set — ``page:admin`` follows
    ``platform_role``, not the lifecycle ``role`` column. Otherwise legacy roles
    are resolved to their effective role (FR-007) and anything unmapped falls back
    to the empty ``pending`` set.
    """
    if resolves_to_platform_admin(role=role, platform_role=platform_role):
        return PLATFORM_ADMIN_ROLE
    return map_effective_role(role) or "pending"


def permissions_for_role(role: str, platform_role: str | None = None) -> dict[str, list[str]]:
    """Return allowed resource keys grouped by type for one role."""
    effective = resolve_permission_role(role, platform_role)
    defaults = DEFAULT_ROLE_PERMISSIONS.get(effective, DEFAULT_ROLE_PERMISSIONS["viewer"])
    return {
        resource_type: sorted(keys)
        for resource_type, keys in defaults.items()
        if keys
    }


async def get_role_permissions(
    db: DatabricksWarehousePool,
    settings: Settings,
    role: str,
    platform_role: str | None = None,
) -> dict[str, list[str]]:
    """Load permissions from Unity Catalog, falling back to in-code defaults."""
    role = resolve_permission_role(role, platform_role)

    table = qualified_table(settings, "dcm_role_permissions")
    try:
        rows = await db.fetchall(
            f"""
            SELECT resource_type, resource_key
            FROM {table}
            WHERE role = ? AND is_allowed = TRUE
            ORDER BY resource_type, resource_key
            """,
            role,
        )
    except Exception:
        return permissions_for_role(role)

    if not rows:
        return permissions_for_role(role)

    grouped: dict[str, list[str]] = {"page": [], "widget": [], "feature": []}
    for row in rows:
        resource_type = str(row["resource_type"])
        resource_key = str(row["resource_key"])
        grouped.setdefault(resource_type, []).append(resource_key)
    return grouped


def permissions_payload(role: str, permissions: dict[str, list[str]]) -> dict[str, Any]:
    """Serialize permissions for API responses."""
    all_keys = sorted(
        key for keys in permissions.values() for key in keys
    )
    return {
        "role": role,
        "pages": permissions.get("page", []),
        "widgets": permissions.get("widget", []),
        "features": permissions.get("feature", []),
        "allowed": all_keys,
    }
