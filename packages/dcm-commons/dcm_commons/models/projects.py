"""Pydantic models for the DCM access-governance project model (feature 015).

These are **API contract** models (request bodies and responses of the
``/v1/projects*`` routes and the enriched ``/auth/me``), not metric-transport
models — they intentionally do **not** inherit from :class:`BaseMetricModel`
(which is ``frozen`` and metric-oriented).

Wire format is **camelCase** (``alias_generator=to_camel``) while Python stays
snake_case; ``populate_by_name=True`` lets handlers build instances with the
snake_case field names. FastAPI serialises responses using the aliases, so the
frozen contract in ``contracts/projects-api.md`` is honoured.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from dcm_commons.models.enums import (
    PlatformRole,
    ProjectRole,
    ProjectStatus,
    RequestStatus,
    ScopeType,
)

__all__ = [
    "ProjectMembershipRef",
    "MeResponse",
    "ProjectCreate",
    "ProjectSummary",
    "ProjectDetail",
    "ProjectMember",
    "MemberRolePatch",
    "MemberAdd",
    "JoinRequestCreate",
    "JoinRequestItem",
    "ScopeRequestCreate",
    "ScopeRequestEntry",
    "ScopeRequestItem",
    "RequestDecision",
    "ProjectRejectRequest",
    "ProjectRegisterMember",
    "ProjectRegisterRequest",
    "ProjectRegisterResponse",
    "ProjectJoinRequest",
    "ProjectJoinResponse",
]


def _normalize_email(value: str) -> str:
    """Lowercase, trim and sanity-check a free-text email (login-page forms)."""
    normalized = value.strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise ValueError("email must be a valid address")
    return normalized


class _CamelModel(BaseModel):
    """Base for project API models: camelCase wire format, snake_case Python."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class ProjectMembershipRef(_CamelModel):
    """One membership entry exposed by ``/auth/me``."""

    project_id: str
    name: str
    role: ProjectRole


class MeResponse(_CamelModel):
    """Enriched identity payload — platform role + project memberships."""

    id: str
    display_name: str | None = None
    platform_role: PlatformRole = PlatformRole.USER
    projects: list[ProjectMembershipRef] = Field(default_factory=list)


class ProjectCreate(_CamelModel):
    """``POST /v1/projects`` body — one project per Business Application."""

    business_app_id: str
    name: str
    lz_scope: list[str] = Field(default_factory=list)
    dbx_scope: list[str] = Field(default_factory=list)


class ProjectSummary(_CamelModel):
    """Project as listed in ``GET /v1/projects``.

    Carries both scope dimensions and the member count so the administration
    table can show what a project grants without an N+1 fan-out of detail calls.

    ``lz_scope`` holds the values **as registered** — the vocabulary a scope
    mutation has to address. ``effective_lz_scope`` holds the landing-zone ids
    those grants actually resolve to, which is what a monitoring filter matches:
    a registered value may be a subscription id, and a granted workspace implies
    its landing zone. Filtering a UI selector on ``lz_scope`` intersects to
    nothing whenever the two vocabularies differ.
    """

    id: str
    name: str
    business_app_id: str
    status: ProjectStatus
    role: ProjectRole | None = None
    lz_scope: list[str] = Field(default_factory=list)
    effective_lz_scope: list[str] = Field(default_factory=list)
    dbx_scope: list[str] = Field(default_factory=list)
    member_count: int = 0


class ProjectDetail(ProjectSummary):
    """Project detail with its two scope dimensions."""

    created_by: str | None = None
    created_at: datetime | None = None
    validated_by: str | None = None
    validated_at: datetime | None = None
    decision_reason: str | None = None


class ProjectMember(_CamelModel):
    """A project member row — exposes the readable ``displayName`` (FR-017)."""

    user_id: str
    display_name: str | None = None
    role: ProjectRole
    added_at: datetime | None = None


class MemberRolePatch(_CamelModel):
    """``PATCH /v1/projects/{id}/members/{userId}`` body."""

    role: ProjectRole


class MemberAdd(_CamelModel):
    """``POST /v1/projects/{id}/members`` body — direct add by a project admin.

    The member is resolved (or provisioned) from ``email`` and their account is
    activated immediately, so an admin can grant access without a join request.
    """

    email: str
    role: ProjectRole = ProjectRole.VIEWER

    _normalize_email = field_validator("email")(_normalize_email)


class JoinRequestCreate(_CamelModel):
    """``POST /v1/projects/{id}/join-requests`` body."""

    requested_role: ProjectRole = ProjectRole.VIEWER
    justification: str | None = None


class JoinRequestItem(_CamelModel):
    """A pending/decided join request."""

    id: str
    project_id: str
    user_id: str
    display_name: str | None = None
    requested_role: ProjectRole
    status: RequestStatus
    justification: str | None = None
    requested_at: datetime | None = None


class ScopeRequestEntry(_CamelModel):
    """One landing zone / workspace asked for inside a scope request."""

    scope_type: ScopeType
    scope_ref: str


class ScopeRequestCreate(_CamelModel):
    """``POST /v1/projects/{id}/scope-requests`` body — one or many items.

    A project admin asks for everything the project is missing in a single
    request (``items``), instead of N look-alike requests a platform admin has to
    approve one by one. The single-item form (``scopeType`` + ``scopeRef``) is
    still accepted and folded into ``items``.
    """

    items: list[ScopeRequestEntry] = Field(default_factory=list)
    scope_type: ScopeType | None = None
    scope_ref: str | None = None
    justification: str | None = None

    @model_validator(mode="after")
    def collect_items(self) -> ScopeRequestCreate:
        """Fold the single-item form into ``items`` and drop blanks/duplicates."""
        entries = list(self.items)
        if self.scope_type is not None and (self.scope_ref or "").strip():
            entries.insert(
                0, ScopeRequestEntry(scope_type=self.scope_type, scope_ref=self.scope_ref)
            )

        unique: list[ScopeRequestEntry] = []
        seen: set[tuple[ScopeType, str]] = set()
        for entry in entries:
            ref = entry.scope_ref.strip()
            if not ref:
                continue
            key = (entry.scope_type, ref)
            if key in seen:
                continue
            seen.add(key)
            unique.append(ScopeRequestEntry(scope_type=entry.scope_type, scope_ref=ref))

        if not unique:
            raise ValueError("at least one scope item is required")
        self.items = unique
        return self


class ScopeRequestItem(_CamelModel):
    """A pending/decided scope-extension request."""

    id: str
    project_id: str
    scope_type: ScopeType
    scope_ref: str
    status: RequestStatus
    justification: str | None = None
    requested_by: str
    requested_at: datetime | None = None


class RequestDecision(_CamelModel):
    """Decision body for join / scope requests: ``approved`` | ``rejected``.

    ``reason`` is required when rejecting: the requester is told why instead of
    seeing their request silently disappear.
    """

    decision: RequestStatus
    reason: str | None = None

    @model_validator(mode="after")
    def require_reason_when_rejecting(self) -> RequestDecision:
        if self.decision == RequestStatus.REJECTED and not (self.reason or "").strip():
            raise ValueError("reason is required when rejecting a request")
        return self


class ProjectRejectRequest(_CamelModel):
    """``POST /v1/projects/{id}/reject`` body — the reason is mandatory.

    Rejecting also frees the Business Application, so another team can register a
    project on it (a project stuck in ``pending_validation`` would block the BA).
    """

    reason: str = Field(min_length=1)


# ─────────────────────────────────────────────────────────────────────────────
# Self-service registration / join from the login page (feature 016)
#
# The visitor is signed in with Entra but not yet a DCM user. The requester
# identity is derived server-side from the verified token, never sent in the
# body — so these requests carry no ``requesterEmail``.
# ─────────────────────────────────────────────────────────────────────────────


class ProjectRegisterMember(_CamelModel):
    """One additional member declared in the Register form (not the requester)."""

    email: str
    role: ProjectRole = ProjectRole.VIEWER

    _normalize_email = field_validator("email")(_normalize_email)


class ProjectRegisterRequest(_CamelModel):
    """``POST /v1/projects/register`` body — self-service project creation.

    The requester (derived from the auth token) becomes a project ``admin``
    automatically (FR-002); ``members`` are the *other* people. Landing-zone and
    Databricks scopes are resolved server-side from the Business Application
    referential; client-supplied ``lz_scope`` / ``dbx_scope`` are ignored.
    """

    business_app_id: str
    name: str
    members: list[ProjectRegisterMember] = Field(default_factory=list)
    lz_scope: list[str] = Field(default_factory=list)
    dbx_scope: list[str] = Field(default_factory=list)


class ProjectRegisterResponse(_CamelModel):
    """Result of a self-service registration — the created pending project."""

    id: str
    name: str
    business_app_id: str
    status: ProjectStatus
    requester_email: str
    member_count: int


class ProjectJoinRequest(_CamelModel):
    """``POST /v1/projects/join`` body — self-service join from the login page."""

    project_id: str
    justification: str | None = None


class ProjectJoinResponse(_CamelModel):
    """Accepted join request with its routing target (FR-004)."""

    request_id: str
    project_id: str
    status: RequestStatus
    routed_to: Literal["admins", "creator"]
    recipient_ids: list[str] = Field(default_factory=list)
