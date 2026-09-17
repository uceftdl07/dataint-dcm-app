"""Compute resource metrics — Databricks (Azure/AWS), EMR (AWS), HDInsight (Azure).

Produced by:
    - ``dcm_azure_collector.collectors.databricks.DatabricksCollector``
    - ``dcm_aws_collector.collectors.emr.EmrCollector``

Stored in Lakebase under: ``dcm.monitoring.compute_metrics``

Each ``ComputeMetric`` is a point-in-time snapshot of a compute resource's state.
Collectors emit one record per resource per collection cycle.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field

from dcm_commons.models.base_metric import BaseMetricModel
from dcm_commons.models.enums import ComputeState, ComputeType

__all__ = ["ComputeMetric"]


class ComputeMetric(BaseMetricModel):
    """Point-in-time state and performance snapshot for a compute resource.

    Attributes:
        compute_resource_id:        Cloud-native resource identifier.
                                    Databricks: ``cluster_id`` (e.g. ``0312-151347-reef123``).
                                    EMR: ``j-XXXXXXXXXX``.
                                    HDInsight: ARM resource ID.
        resource_name:              Human-readable resource name.
        compute_type:               Compute technology platform.
        state:                      Current operational state at collection time.
        num_workers:                Number of active worker nodes.
                                    0 for terminated or single-node resources.
        autoscale_min:              Minimum worker count when autoscaling is enabled.
                                    ``None`` when autoscaling is disabled.
        autoscale_max:              Maximum worker count when autoscaling is enabled.
                                    ``None`` when autoscaling is disabled.
        node_type:                  Instance type / VM size of worker nodes
                                    (e.g. ``Standard_DS3_v2``, ``r5.xlarge``).
        spark_version:              Spark or Databricks Runtime version string
                                    (e.g. ``"13.3.x-scala2.12"``).
        start_time:                 UTC timestamp when the resource was last started.
                                    ``None`` for resources in ``TERMINATED`` state.
        creator:                    Username or service principal that created the resource.
        estimated_hourly_cost_usd:  Cost estimate based on instance type × worker count.
                                    Approximation only — actual billing may differ.
        workspace_id:               Databricks workspace GUID (Databricks only).
                                    ``None`` for EMR and HDInsight resources.
        avg_cpu_utilization_pct:    Average CPU utilisation percentage over the collection
                                    window. ``None`` when not available from the provider.
        avg_mem_utilization_pct:    Average memory utilisation percentage over the collection
                                    window. ``None`` when not available from the provider.
        tags:                       Provider resource tags as key/value strings.
    """

    compute_resource_id: str = Field(..., description="Cloud-native resource identifier.")
    resource_name: str = Field(..., description="Human-readable resource name.")
    compute_type: ComputeType = Field(..., description="Compute technology platform.")
    state: ComputeState
    num_workers: int = Field(
        default=0,
        ge=0,
        description="Number of active worker nodes.",
    )
    autoscale_min: int | None = Field(
        default=None,
        ge=0,
        description="Autoscale minimum worker count; None when autoscaling is disabled.",
    )
    autoscale_max: int | None = Field(
        default=None,
        ge=0,
        description="Autoscale maximum worker count; None when autoscaling is disabled.",
    )
    node_type: str | None = Field(
        default=None,
        description="Instance type / VM size of worker nodes.",
    )
    spark_version: str | None = Field(
        default=None,
        description="Spark or Databricks Runtime version string.",
    )
    start_time: datetime | None = Field(
        default=None,
        description="UTC timestamp when the resource was last started.",
    )
    creator: str | None = Field(
        default=None,
        description="Username or service principal that created the resource.",
    )
    estimated_hourly_cost_usd: float | None = Field(
        default=None,
        ge=0.0,
        description="Estimated hourly cost based on instance type and worker count.",
    )
    workspace_id: str | None = Field(
        default=None,
        description="Databricks workspace GUID (Databricks only).",
    )
    avg_cpu_utilization_pct: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Average CPU utilisation % over the collection window.",
    )
    avg_mem_utilization_pct: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Average memory utilisation % over the collection window.",
    )
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Provider resource tags.",
    )
