"""Shared enumerations for all DCM metric models.

All enum values are lowercase strings to ensure cross-platform consistency
when serialized to JSON, stored in Lakebase, or used in log fields.

Using ``StrEnum`` (Python 3.11+) means enum instances compare equal to their
string value, which simplifies filtering, serialization, and SQL queries::

    PipelineRunStatus.FAILED == "failed"   # True
    ComputeState.RUNNING == "running"      # True

Naming convention:

- ``*Status`` — execution outcome of a one-time operation (succeeded, failed).
- ``*State``  — current operational condition of a long-lived resource.
- ``*Severity`` — criticality level of an incident or alert.
- ``*Type``   — categorical classification with no ordering.

Backward-compatible aliases (Sprint 7 — 2026-04-13 rename)
------------------------------------------------------------
``ClusterState``, ``ClusterType``, ``ComplianceState``, ``PolicyEffect`` are
kept as module-level aliases so existing collector code continues to import
without changes until each component is updated in its own sprint.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "CloudProvider",
    "MetricDomain",
    "PipelineRunStatus",
    "TriggerType",
    # Databricks Workflows (epic 009)
    "WorkflowRunStatus",
    "WorkflowTriggerType",
    # Compute (renamed from Cluster)
    "ComputeState",
    "ComputeType",
    # Backward-compat aliases
    "ClusterState",
    "ClusterType",
    "DatabaseType",
    "AlertSeverity",
    "AlertStatus",
    "ActivityRunStatus",
    "ActivityType",
    "UserType",
    # Standard Check (renamed from Compliance)
    "StandardCheckState",
    "CheckEffect",
    # Backward-compat aliases
    "ComplianceState",
    "PolicyEffect",
    # Access governance — project model (feature 015)
    "PlatformRole",
    "ProjectStatus",
    "ProjectRole",
    "RequestStatus",
    "ScopeType",
]


class CloudProvider(StrEnum):
    """The cloud platform that hosts the monitored service."""

    AZURE = "azure"
    AWS = "aws"


class MetricDomain(StrEnum):
    """Logical grouping of metrics by monitored service category.

    The domain determines:

    - Which Lakebase table family receives the ingested records.
    - Which frontend module displays the data.
    - Which collector class(es) produce the metrics.
    """

    PIPELINE = "pipeline"                 #: ADF pipelines, AWS Glue jobs, EMR steps.
    COMPUTE = "compute"                   #: Databricks clusters, EMR clusters, HDInsight.
    COST = "cost"                         #: Azure Cost Management, AWS Cost Explorer.
    DATABASE = "database"                 #: SQL Server, PostgreSQL, MySQL, Cosmos DB, RDS.
    SECURITY = "security"                 #: Defender for Cloud alerts, AWS GuardDuty findings.
    ACTIVITY_RUN = "activity_run"         #: ADF activity-level runs, Glue job steps.
    USER = "user"                         #: Databricks SCIM users, AWS IAM identities.
    STANDARD_CHECK = "standard_check"     #: Azure Policy evaluations, AWS Config Rule results.
    WORKFLOW = "workflow"                 #: Databricks Workflows (Jobs & Pipelines) run observability (epic 009).


class PipelineRunStatus(StrEnum):
    """Execution result of a pipeline or batch job run."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RUNNING = "running"
    CANCELLED = "cancelled"
    QUEUED = "queued"
    TIMED_OUT = "timed_out"
    SKIPPED = "skipped"

    @property
    def is_terminal(self) -> bool:
        """Return ``True`` if this status represents a completed (non-running) state."""
        return self in {
            PipelineRunStatus.SUCCEEDED,
            PipelineRunStatus.FAILED,
            PipelineRunStatus.CANCELLED,
            PipelineRunStatus.TIMED_OUT,
            PipelineRunStatus.SKIPPED,
        }

    @property
    def is_failure(self) -> bool:
        """Return ``True`` if this status represents an unsuccessful outcome."""
        return self in {PipelineRunStatus.FAILED, PipelineRunStatus.TIMED_OUT}


class TriggerType(StrEnum):
    """How a pipeline or job execution was initiated."""

    SCHEDULED = "scheduled"     #: Triggered by a time-based schedule.
    MANUAL = "manual"           #: Triggered manually by a user or operator.
    EVENT = "event"             #: Triggered by an event (e.g. file arrival, message).
    DEPENDENCY = "dependency"   #: Triggered by a dependency pipeline completing.
    UNKNOWN = "unknown"         #: Trigger type could not be determined.


class ComputeState(StrEnum):
    """Current operational state of a compute resource (cluster, EMR, HDInsight)."""

    RUNNING = "running"
    TERMINATED = "terminated"
    TERMINATING = "terminating"
    STARTING = "starting"
    RESTARTING = "restarting"
    ERROR = "error"
    UNKNOWN = "unknown"

    @property
    def is_active(self) -> bool:
        """Return ``True`` if the resource is consuming compute/cost."""
        return self in {ComputeState.RUNNING, ComputeState.STARTING, ComputeState.RESTARTING}


class ComputeType(StrEnum):
    """The compute technology platform of the resource."""

    DATABRICKS = "databricks"   #: Azure Databricks or Databricks on AWS.
    EMR = "emr"                 #: Amazon EMR (Elastic MapReduce).
    HDI = "hdi"                 #: Azure HDInsight.


class DatabaseType(StrEnum):
    """Database engine type of the monitored database instance."""

    POSTGRESQL = "postgresql"   #: Azure Database for PostgreSQL / AWS RDS PostgreSQL.
    MYSQL = "mysql"             #: Azure Database for MySQL / AWS RDS MySQL.
    SQLSERVER = "sqlserver"     #: Azure SQL Database / AWS RDS SQL Server.
    COSMOS_DB = "cosmos_db"     #: Azure Cosmos DB (NoSQL).
    RDS_AURORA = "rds_aurora"   #: AWS Aurora (MySQL or PostgreSQL-compatible).
    REDSHIFT = "redshift"       #: AWS Redshift (data warehouse).


class AlertSeverity(StrEnum):
    """Criticality level of a security alert, ordered from highest to lowest."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"

    @property
    def requires_immediate_action(self) -> bool:
        """Return ``True`` for severities that require prompt human response."""
        return self in {AlertSeverity.HIGH, AlertSeverity.MEDIUM}


class AlertStatus(StrEnum):
    """Current disposition of a security alert."""

    ACTIVE = "active"           #: Alert is open and not yet addressed.
    IN_PROGRESS = "in_progress" #: Alert is being investigated.
    RESOLVED = "resolved"       #: Alert has been remediated.
    DISMISSED = "dismissed"     #: Alert was reviewed and dismissed as non-issue.


class ActivityRunStatus(StrEnum):
    """Execution result of a single activity within a pipeline run."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RUNNING = "running"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"

    @property
    def is_terminal(self) -> bool:
        """Return ``True`` if this status represents a completed state."""
        return self in {
            ActivityRunStatus.SUCCEEDED,
            ActivityRunStatus.FAILED,
            ActivityRunStatus.CANCELLED,
            ActivityRunStatus.SKIPPED,
        }


class ActivityType(StrEnum):
    """Type of activity within a pipeline run.

    Maps ADF activity types and Glue job step types to a unified vocabulary.
    """

    COPY = "copy"                           #: ADF Copy Activity — data movement.
    DATABRICKS_NOTEBOOK = "databricks_notebook"  #: ADF DatabricksNotebook / Glue Spark job.
    LOOKUP = "lookup"                       #: ADF Lookup Activity — read a single row.
    FOR_EACH = "for_each"                   #: ADF ForEach / iteration container.
    WAIT = "wait"                           #: ADF Wait Activity — pause execution.
    WEB_ACTIVITY = "web_activity"           #: ADF Web Activity — HTTP call.
    EXECUTE_PIPELINE = "execute_pipeline"   #: ADF Execute Pipeline — nested pipeline.
    GLUE_JOB_NODE = "glue_job_node"         #: AWS Glue workflow node.
    UNKNOWN = "unknown"                     #: Type could not be determined.


class UserType(StrEnum):
    """The identity system that manages this user account."""

    DATABRICKS = "databricks"   #: Databricks workspace user (SCIM-managed).
    AWS_IAM = "aws_iam"         #: AWS IAM user or federated identity.
    AZURE_AD = "azure_ad"       #: Microsoft Entra ID (Azure AD) user.


class StandardCheckState(StrEnum):
    """Evaluation result of a standard check / policy against a resource."""

    COMPLIANT = "compliant"           #: Resource satisfies the check.
    NON_COMPLIANT = "non_compliant"   #: Resource violates the check.
    UNKNOWN = "unknown"               #: Evaluation could not be completed.


class CheckEffect(StrEnum):
    """The action taken when a standard check is triggered.

    Azure Policy effects: https://learn.microsoft.com/azure/governance/policy/concepts/effects
    AWS Config rules use COMPLIANT / NON_COMPLIANT outcomes rather than effects.
    """

    DENY = "deny"                             #: Block the non-compliant operation.
    AUDIT = "audit"                           #: Log the violation without blocking.
    DEPLOY_IF_NOT_EXISTS = "deployifnotexists" #: Auto-remediate by deploying a resource.
    MODIFY = "modify"                         #: Auto-remediate by modifying resource properties.
    DISABLED = "disabled"                     #: Policy is defined but not enforced.


class WorkflowRunStatus(StrEnum):
    """Execution result of a Databricks Workflow (Job/Pipeline) run.

    Dedicated to the ``workflow`` domain (epic 009) so the Databricks-specific
    run lifecycle stays isolated from the generic :class:`PipelineRunStatus`
    used by ADF / Glue / EMR.

    Mapping from the Databricks Jobs API ``state.result_state`` /
    ``state.life_cycle_state`` (REST 2.2) is performed by the collector.
    """

    SUCCEEDED = "succeeded"     #: result_state = SUCCESS.
    FAILED = "failed"           #: result_state = FAILED / INTERNAL_ERROR / UPSTREAM_FAILED.
    RUNNING = "running"         #: life_cycle_state = RUNNING / TERMINATING.
    CANCELLED = "cancelled"     #: result_state = CANCELED / life_cycle = SKIPPED-by-cancel.
    QUEUED = "queued"           #: life_cycle_state = QUEUED / PENDING / BLOCKED.
    TIMED_OUT = "timed_out"     #: result_state = TIMEDOUT.
    SKIPPED = "skipped"         #: result_state = EXCLUDED / run skipped.

    @property
    def is_terminal(self) -> bool:
        """Return ``True`` if this status represents a completed (non-running) state."""
        return self in {
            WorkflowRunStatus.SUCCEEDED,
            WorkflowRunStatus.FAILED,
            WorkflowRunStatus.CANCELLED,
            WorkflowRunStatus.TIMED_OUT,
            WorkflowRunStatus.SKIPPED,
        }

    @property
    def is_failure(self) -> bool:
        """Return ``True`` if this status represents an unsuccessful outcome."""
        return self in {WorkflowRunStatus.FAILED, WorkflowRunStatus.TIMED_OUT}


class WorkflowTriggerType(StrEnum):
    """How a Databricks Workflow run was initiated (Databricks-native trigger types).

    Maps from the Databricks Jobs API ``trigger`` field (REST 2.2).  Kept
    separate from the generic :class:`TriggerType` because Databricks exposes
    richer, platform-specific trigger semantics.
    """

    PERIODIC = "periodic"           #: Time-based schedule (cron).
    ONE_TIME = "one_time"           #: Single manual/API-triggered run.
    RETRY = "retry"                 #: Automatic retry of a previous run.
    RUN_JOB_TASK = "run_job_task"   #: Triggered by a parent job's run-job task.
    FILE_ARRIVAL = "file_arrival"   #: Triggered by file arrival on a monitored location.
    TABLE_UPDATE = "table_update"   #: Triggered by a table/Delta update.
    CONTINUOUS = "continuous"       #: Continuous (always-on) workflow.
    MANUAL = "manual"               #: Triggered manually from the UI/API.
    UNKNOWN = "unknown"             #: Trigger type could not be determined.


# ─────────────────────────────────────────────────────────────────────────────
# Access governance — project model (feature 015-project-access-governance)
# ─────────────────────────────────────────────────────────────────────────────


class PlatformRole(StrEnum):
    """Platform-wide role above the project layer (``dcm_app_users.platform_role``).

    ``super_admin`` grants an unrestricted metric scope and validates project /
    scope requests. ``user`` is the default: authorization comes solely from
    project memberships.
    """

    USER = "user"
    SUPER_ADMIN = "super_admin"


class ProjectStatus(StrEnum):
    """Lifecycle status of a governance project (``dcm_projects.status``)."""

    PENDING_VALIDATION = "pending_validation"  #: Awaiting platform_admin approval.
    ACTIVE = "active"                          #: Grants scope to its members.
    REJECTED = "rejected"                      #: Refused by a platform_admin; frees its Business Application.
    ARCHIVED = "archived"                      #: Retired (archival flow out of scope of feature 015).


class ProjectRole(StrEnum):
    """Project-scoped role of a member (``dcm_project_members.role``)."""

    VIEWER = "viewer"  #: Reads the project scope; no administration.
    ADMIN = "admin"    #: Manages members, roles and scope-extension requests.


class RequestStatus(StrEnum):
    """Status of a join / scope request (shared by both request tables)."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ScopeType(StrEnum):
    """Dimension targeted by a project scope-extension request."""

    LZ = "lz"                        #: Landing Zone (``dcm_project_lz_scope``).
    DBX_WORKSPACE = "dbx_workspace"  #: Databricks workspace (``dcm_project_dbx_scope``).

