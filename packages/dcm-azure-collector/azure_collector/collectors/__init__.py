"""Azure metric collector implementations — one class per monitored service.

Each collector inherits from
:class:`~dcm_commons.collectors.base.BaseCollector` and implements the
:meth:`~dcm_commons.collectors.base.BaseCollector._collect_metrics` method.

Available collectors
--------------------
:class:`DataFactoryCollector`
    Pipeline run history from all ADF instances in the subscription.
:class:`ActivityRunCollector`
    Activity-level run details (rows copied, bytes, per-activity errors) for ADF pipelines.
:class:`DatabricksCollector`
    Cluster state snapshots from all Databricks workspaces.
:class:`DatabricksPipelineCollector`
    Workflow/job execution history from all Databricks workspaces.
:class:`DatabricksWorkflowCollector`
    Databricks Workflows run observability (domain ``workflow``): status,
    durations, retry_count, task failures, cluster linkage (epic 009).
:class:`DatabricksUserCollector`
    SCIM user snapshots (groups, roles, active status) from all Databricks workspaces.
:class:`CostManagementCollector`
    Daily costs by service and budget utilisation.
:class:`DatabaseCollector`
    Health/performance metrics for SQL, PostgreSQL, MySQL, and Cosmos DB.
:class:`SecurityCenterCollector`
    Active security alerts from Microsoft Defender for Cloud.
:class:`StandardCheckCollector`
    Azure Policy evaluation results (NonCompliant by default, full scan optional).
"""

from __future__ import annotations

from azure_collector.collectors.activity_runs import ActivityRunCollector
from azure_collector.collectors.compliance import StandardCheckCollector
from azure_collector.collectors.cost_management import CostManagementCollector
from azure_collector.collectors.databases import DatabaseCollector
from azure_collector.collectors.databricks import DatabricksCollector
from azure_collector.collectors.databricks_pipelines import DatabricksPipelineCollector
from azure_collector.collectors.databricks_workflows import DatabricksWorkflowCollector
from azure_collector.collectors.datafactory import DataFactoryCollector
from azure_collector.collectors.security_center import SecurityCenterCollector
from azure_collector.collectors.users import DatabricksUserCollector

__all__ = [
    "ActivityRunCollector",
    "StandardCheckCollector",
    "CostManagementCollector",
    "DatabaseCollector",
    "DatabricksCollector",
    "DatabricksPipelineCollector",
    "DatabricksWorkflowCollector",
    "DatabricksUserCollector",
    "DataFactoryCollector",
    "SecurityCenterCollector",
]
