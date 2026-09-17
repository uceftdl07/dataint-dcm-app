"""DCM metric domain models and shared enumerations.

This package exposes the complete public API surface for data models:

- :class:`BaseMetricModel` — Pydantic base class with shared ``ConfigDict``.
- :class:`MetricPayload` — transport envelope between collectors and the ingestion API.
- Domain models (5 original + 3 Sprint 6 + 2 Sprint 7):
  :class:`PipelineMetric`, :class:`ComputeMetric`,
  :class:`CostMetric`, :class:`DatabaseMetric`, :class:`SecurityAlert`,
  :class:`ActivityRunMetric`, :class:`UserMetric`, :class:`StandardCheckMetric`.
- Enumerations: :class:`CloudProvider`, :class:`MetricDomain`,
  :class:`PipelineRunStatus`, :class:`TriggerType`,
  :class:`ComputeState`, :class:`ComputeType`, :class:`DatabaseType`,
  :class:`AlertSeverity`, :class:`AlertStatus`,
  :class:`ActivityRunStatus`, :class:`ActivityType`,
  :class:`UserType`, :class:`StandardCheckState`, :class:`CheckEffect`.
- Backward-compatible aliases (Sprint 7):
  :class:`ClusterMetric`, :class:`ComplianceMetric`,
  :class:`ClusterState`, :class:`ClusterType`,
  :class:`ComplianceState`, :class:`PolicyEffect`.

Typical import pattern::

    from dcm_commons.models import (
        MetricPayload,
        PipelineMetric,
        ComputeMetric,
        ActivityRunMetric,
        UserMetric,
        StandardCheckMetric,
        CloudProvider,
        MetricDomain,
        PipelineRunStatus,
        ComputeState,
        StandardCheckState,
    )
"""

from __future__ import annotations

from dcm_commons.models.activity_run import ActivityRunMetric
from dcm_commons.models.base_metric import BaseMetricModel
from dcm_commons.models.compute import ComputeMetric
from dcm_commons.models.cost import CostMetric
from dcm_commons.models.database import DatabaseMetric
from dcm_commons.models.enums import (
    ActivityRunStatus,
    ActivityType,
    AlertSeverity,
    AlertStatus,
    CheckEffect,
    CloudProvider,
    ComputeState,
    ComputeType,
    DatabaseType,
    MetricDomain,
    PipelineRunStatus,
    PlatformRole,
    ProjectRole,
    ProjectStatus,
    RequestStatus,
    ScopeType,
    StandardCheckState,
    TriggerType,
    UserType,
    WorkflowRunStatus,
    WorkflowTriggerType,
)
from dcm_commons.models.payload import MetricPayload
from dcm_commons.models.pipeline import PipelineMetric
from dcm_commons.models.projects import (
    JoinRequestCreate,
    JoinRequestItem,
    MeResponse,
    MemberRolePatch,
    ProjectCreate,
    ProjectDetail,
    ProjectJoinRequest,
    ProjectJoinResponse,
    ProjectMember,
    ProjectMembershipRef,
    ProjectRegisterMember,
    ProjectRegisterRequest,
    ProjectRegisterResponse,
    ProjectSummary,
    RequestDecision,
    ScopeRequestCreate,
    ScopeRequestItem,
)
from dcm_commons.models.security import SecurityAlert
from dcm_commons.models.standard_check import StandardCheckMetric
from dcm_commons.models.user import UserMetric
from dcm_commons.models.workflow import WorkflowRunMetric, WorkflowTaskRun

__all__ = [
    # Base
    "BaseMetricModel",
    # Transport envelope
    "MetricPayload",
    # Domain models — original 5
    "PipelineMetric",
    "ComputeMetric",
    "CostMetric",
    "DatabaseMetric",
    "SecurityAlert",
    # Domain models — Sprint 6
    "ActivityRunMetric",
    "UserMetric",
    # Domain models — Sprint 7
    "StandardCheckMetric",
    # Domain models — epic 009 (Databricks Workflows)
    "WorkflowRunMetric",
    "WorkflowTaskRun",
    # Backward-compat aliases — Sprint 7
    # Enumerations — core
    "CloudProvider",
    "MetricDomain",
    "PipelineRunStatus",
    "TriggerType",
    "ComputeState",
    "ComputeType",
    "DatabaseType",
    "AlertSeverity",
    "AlertStatus",
    "ActivityRunStatus",
    "ActivityType",
    "UserType",
    "StandardCheckState",
    "CheckEffect",
    "WorkflowRunStatus",
    "WorkflowTriggerType",
    # Enumerations — access governance (feature 015)
    "PlatformRole",
    "ProjectStatus",
    "ProjectRole",
    "RequestStatus",
    "ScopeType",
    # Access governance models (feature 015)
    "ProjectMembershipRef",
    "MeResponse",
    "ProjectCreate",
    "ProjectSummary",
    "ProjectDetail",
    "ProjectMember",
    "MemberRolePatch",
    "JoinRequestCreate",
    "JoinRequestItem",
    "ScopeRequestCreate",
    "ScopeRequestItem",
    "RequestDecision",
    # Self-service registration / join (feature 016)
    "ProjectRegisterMember",
    "ProjectRegisterRequest",
    "ProjectRegisterResponse",
    "ProjectJoinRequest",
    "ProjectJoinResponse",
]
