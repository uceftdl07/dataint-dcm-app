"""Database health and performance metrics — Azure SQL / Cosmos DB and AWS RDS / Aurora.

Produced by:
    - ``dcm_azure_collector.collectors.database.AzureDatabaseCollector``
    - ``dcm_aws_collector.collectors.rds.RdsCollector``

Stored in Lakebase under: ``dcm.monitoring.database_snapshots``

Each ``DatabaseMetric`` is a point-in-time health snapshot for one database
instance, collected from Azure Monitor metrics or AWS CloudWatch.

Note on ``dtus_used``:
    DTUs (Database Transaction Units) are an Azure-specific capacity metric
    exclusive to Azure SQL Database (not Elastic Pool or Managed Instance).
    This field is ``None`` for all non-Azure-SQL databases.
"""

from __future__ import annotations

from pydantic import Field

from dcm_commons.models.base_metric import BaseMetricModel
from dcm_commons.models.enums import DatabaseType

__all__ = ["DatabaseMetric"]


class DatabaseMetric(BaseMetricModel):
    """Point-in-time health and performance snapshot for a database instance.

    Attributes:
        db_id:              Cloud-native database resource identifier
                            (ARM resource ID or AWS ARN).
        db_name:            Database name within the server / instance.
        db_type:            Database engine type.
        server_name:        Hostname or server resource name
                            (e.g. ``"myserver.database.windows.net"``
                            or ``"my-rds-instance.xxxx.rds.amazonaws.com"``).
        resource_group:     Azure resource group name (Azure only).
        region:             Cloud region where the database is hosted
                            (e.g. ``"westeurope"``, ``"eu-west-1"``).
        cpu_percent:        CPU utilisation percentage (0–100).
        memory_percent:     Memory utilisation percentage (0–100).
        storage_used_gb:    Storage space currently in use (GB).
        storage_limit_gb:   Provisioned storage capacity (GB).
        active_connections: Number of active client connections at collection time.
        dtus_used:          DTU consumption percentage (Azure SQL Database only).
        is_available:       ``True`` if the database responded to health probes.
        tags:               Provider resource tags as key/value strings.
    """

    db_id: str = Field(
        ...,
        description="Cloud-native database resource identifier (ARM resource ID or ARN).",
    )
    db_name: str = Field(..., description="Database name within the server or instance.")
    db_type: DatabaseType = Field(..., description="Database engine type.")
    server_name: str = Field(
        ...,
        description="Hostname or server resource name.",
    )
    resource_group: str | None = Field(
        default=None,
        description="Azure resource group name (Azure only).",
    )
    region: str | None = Field(
        default=None,
        description="Cloud region where the database is hosted.",
    )
    cpu_percent: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="CPU utilisation percentage (0–100).",
    )
    memory_percent: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Memory utilisation percentage (0–100).",
    )
    storage_used_gb: float | None = Field(
        default=None,
        ge=0.0,
        description="Storage space currently in use (GB).",
    )
    storage_limit_gb: float | None = Field(
        default=None,
        ge=0.0,
        description="Provisioned storage capacity (GB).",
    )
    active_connections: int | None = Field(
        default=None,
        ge=0,
        description="Number of active client connections at collection time.",
    )
    dtus_used: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="DTU consumption percentage (Azure SQL Database only).",
    )
    is_available: bool = Field(
        default=True,
        description="True if the database responded to health probes at collection time.",
    )
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Provider resource tags.",
    )
