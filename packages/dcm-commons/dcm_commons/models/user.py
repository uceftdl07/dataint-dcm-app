"""User / identity metrics — Databricks SCIM users and AWS IAM identities.

A ``UserMetric`` represents a snapshot of a user account at a point in time.
Collecting user metrics enables governance use cases:

- Detect **inactive users** (``last_activity_at`` older than 90 days).
- Monitor **privilege creep** (users with unexpected admin roles).
- Track **group membership** changes over time.

Data sources
------------
- **Databricks (Azure/AWS)**: SCIM v2 API — ``GET /api/2.0/preview/scim/v2/Users``
- **AWS IAM**: ``iam.list_users()`` + ``iam.generate_credential_report()``
  (the credential report provides ``last_activity_at`` per user)
- **Azure AD**: Microsoft Graph ``/v1.0/users`` (if in scope)

Deduplication key
-----------------
``(user_id, source_lz_id)`` — same user may appear in multiple workspaces
or accounts, each managed by a different LZ agent.

Example::

    from dcm_commons.models.user import UserMetric
    from dcm_commons.models.enums import UserType

    metric = UserMetric(
        user_id="1234567890",
        user_name="yahia.zerdoumi@company.com",
        user_type=UserType.DATABRICKS,
        display_name="Yahia ZERDOUMI",
        workspace_or_account="https://adb-3059738143768593.13.azuredatabricks.net",
        is_active=True,
        groups=["admins", "data-engineers"],
        roles=["CAN_MANAGE"],
    )
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field, field_validator

from dcm_commons.models.base_metric import BaseMetricModel
from dcm_commons.models.enums import UserType

__all__ = ["UserMetric"]


class UserMetric(BaseMetricModel):
    """Governance snapshot for a single user identity.

    Attributes:
        user_id:                Unique identifier from the source system.
                                SCIM ID for Databricks, ARN for AWS IAM.
        user_name:              Login name / email address.
        user_type:              Identity system managing this account.
        is_active:              ``False`` when account is suspended or deactivated.
        display_name:           Human-friendly full name (optional).
        workspace_or_account:   Databricks workspace URL or AWS account alias.
                                Helps scope the user when multiple workspaces
                                share the same underlying identity provider.
        last_activity_at:       UTC timestamp of last recorded activity.
                                ``None`` when not available (e.g. new account).
        groups:                 List of group names this user belongs to.
        roles:                  List of roles or entitlements assigned.
        tags:                   Arbitrary key/value metadata from the source.
    """

    user_id: str = Field(
        ...,
        description="Unique user identifier (Databricks SCIM ID or IAM ARN).",
    )
    user_name: str = Field(..., description="Login name or email address.")
    user_type: UserType
    is_active: bool = True
    display_name: str | None = None
    workspace_or_account: str | None = Field(
        default=None,
        description="Databricks workspace URL or AWS account alias.",
    )
    last_activity_at: datetime | None = None
    groups: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    tags: dict[str, Any] = Field(default_factory=dict)

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("last_activity_at", mode="before")
    @classmethod
    def _ensure_utc(cls, v: datetime | None) -> datetime | None:
        """Coerce naive datetimes to UTC."""
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"UserMetric("
            f"user={self.user_name!r}, "
            f"type={self.user_type}, "
            f"active={self.is_active}, "
            f"groups={len(self.groups)})"
        )
