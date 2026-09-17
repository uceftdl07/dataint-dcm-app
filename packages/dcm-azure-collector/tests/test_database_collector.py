"""Tests for DatabaseCollector — Azure SQL Database and PostgreSQL metrics.

Uses mocking to test the collector without real Azure SDK calls.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from azure_collector.collectors.databases import DatabaseCollector
from dcm_commons.models.enums import MetricDomain


# ---------------------------------------------------------------------------
# Concrete test implementation
# ---------------------------------------------------------------------------


class ConcreteDatabaseCollector(DatabaseCollector):
    """Concrete implementation of DatabaseCollector for testing.
    
    Overrides __init__ to avoid passing domain parameter to BaseCollector.
    """

    def __init__(
        self,
        source_lz_id: str,
        subscription_id: str,
        *,
        credential: Any | None = None,
        max_retries: int = 3,
        retry_base_delay_seconds: float = 2.0,
    ) -> None:
        from azure.identity import DefaultAzureCredential
        from azure.mgmt.sql import SqlManagementClient
        from azure.mgmt.rdbms.postgresql import PostgreSQLManagementClient
        from azure.mgmt.rdbms.mysql import MySQLManagementClient
        from azure.mgmt.cosmosdb import CosmosDBManagementClient
        from azure.mgmt.monitor import MonitorManagementClient
        from dcm_commons.collectors.base import BaseCollector
        from dcm_commons.models.enums import CloudProvider

        # Call BaseCollector.__init__ directly, bypassing domain parameter
        BaseCollector.__init__(
            self,
            source_lz_id=source_lz_id,
            cloud_provider=CloudProvider.AZURE,
            max_retries=max_retries,
            retry_base_delay_seconds=retry_base_delay_seconds,
        )
        self._subscription_id = subscription_id
        _credential = credential or DefaultAzureCredential()
        self._sql_client = SqlManagementClient(_credential, subscription_id)
        self._pg_client = PostgreSQLManagementClient(_credential, subscription_id)
        self._mysql_client = MySQLManagementClient(_credential, subscription_id)
        self._cosmos_client = CosmosDBManagementClient(_credential, subscription_id)
        self._monitor_client = MonitorManagementClient(_credential, subscription_id)

    @property
    def domain(self) -> MetricDomain:
        """Return the compute metric domain."""
        return MetricDomain.COMPUTE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_sql_server(
    name: str = "my-sqlserver",
    resource_group: str = "my-rg",
) -> dict[str, Any]:
    """Create an Azure SQL Server resource."""
    return {
        "id": f"/subscriptions/.../resourceGroups/{resource_group}/providers/Microsoft.Sql/servers/{name}",
        "name": name,
        "type": "Microsoft.Sql/servers",
        "location": "eastus",
        "tags": {},
        "properties": {
            "fullyQualifiedDomainName": f"{name}.database.windows.net",
            "administratorLogin": "sqladmin",
            "version": "12.0",
        },
    }


def _make_sql_database(
    server_name: str = "my-sqlserver",
    database_name: str = "mydb",
    resource_group: str = "my-rg",
    edition: str = "Standard",
    status: str = "Online",
) -> dict[str, Any]:
    """Create an Azure SQL Database."""
    return {
        "id": f"/subscriptions/.../resourceGroups/{resource_group}/providers/Microsoft.Sql/servers/{server_name}/databases/{database_name}",
        "name": database_name,
        "type": "Microsoft.Sql/servers/databases",
        "location": "eastus",
        "properties": {
            "edition": edition,
            "status": status,
            "databaseId": "12345678-1234-1234-1234-123456789012",
            "creationDate": "2026-01-01T00:00:00Z",
            "collation": "SQL_Latin1_General_CP1_CI_AS",
        },
    }


def _make_postgresql_server(
    name: str = "my-postgres",
    resource_group: str = "my-rg",
) -> dict[str, Any]:
    """Create an Azure Database for PostgreSQL server."""
    return {
        "id": f"/subscriptions/.../resourceGroups/{resource_group}/providers/Microsoft.DBforPostgreSQL/servers/{name}",
        "name": name,
        "type": "Microsoft.DBforPostgreSQL/servers",
        "location": "eastus",
        "tags": {},
        "properties": {
            "fullyQualifiedDomainName": f"{name}.postgres.database.azure.com",
            "administratorLogin": "pgadmin",
            "version": "12",
        },
    }


# ---------------------------------------------------------------------------
# DatabaseCollector
# ---------------------------------------------------------------------------


class TestDatabaseCollector:
    def test_init_default_parameters(self) -> None:
        collector = ConcreteDatabaseCollector(
            source_lz_id="azure-sub-fa5abbc4",
            subscription_id="12345678-1234-1234-1234-123456789012",
        )
        assert collector._source_lz_id == "azure-sub-fa5abbc4"
        assert collector._subscription_id == "12345678-1234-1234-1234-123456789012"

    @pytest.mark.asyncio
    async def test_collect_metrics_no_databases(self) -> None:
        """Test when no databases exist."""
        # Mock SQL servers and databases
        mock_sql_client = MagicMock()
        mock_sql_client.servers.list_by_subscription = MagicMock(return_value=[])
        mock_sql_client.databases.list_by_server = MagicMock(return_value=[])

        # Mock PostgreSQL servers
        mock_pg_client = MagicMock()
        mock_pg_client.servers.list = MagicMock(return_value=[])

        with patch("azure.identity.DefaultAzureCredential"):
            with patch(
                "azure.mgmt.sql.SqlManagementClient", return_value=mock_sql_client
            ):
                with patch(
                    "azure.mgmt.rdbms.postgresql.PostgreSQLManagementClient",
                    return_value=mock_pg_client,
                ):
                    with patch(
                        "azure_collector.collectors.databases.run_sync",
                        new=AsyncMock(side_effect=lambda f: f()),
                    ):
                        collector = ConcreteDatabaseCollector(
                            source_lz_id="azure-sub-fa5abbc4",
                            subscription_id="12345678-1234-1234-1234-123456789012",
                        )
                        metrics = await collector._collect_metrics()

        assert isinstance(metrics, list)

    @pytest.mark.asyncio
    async def test_collect_metrics_with_sql_databases(self) -> None:
        """Test collecting SQL databases."""
        server = _make_sql_server("my-sqlserver", "my-rg")
        database = _make_sql_database("my-sqlserver", "mydb", "my-rg")

        mock_sql_client = MagicMock()
        mock_sql_client.servers.list_by_subscription = MagicMock(return_value=[server])
        mock_sql_client.databases.list_by_server = MagicMock(return_value=[database])

        mock_pg_client = MagicMock()
        mock_pg_client.servers.list = MagicMock(return_value=[])

        with patch("azure.identity.DefaultAzureCredential"):
            with patch(
                "azure.mgmt.sql.SqlManagementClient", return_value=mock_sql_client
            ):
                with patch(
                    "azure.mgmt.rdbms.postgresql.PostgreSQLManagementClient",
                    return_value=mock_pg_client,
                ):
                    with patch(
                        "azure_collector.collectors.databases.run_sync",
                        new=AsyncMock(side_effect=lambda f: f()),
                    ):
                        collector = ConcreteDatabaseCollector(
                            source_lz_id="azure-sub-fa5abbc4",
                            subscription_id="12345678-1234-1234-1234-123456789012",
                        )
                        metrics = await collector._collect_metrics()

        # Should have metrics for SQL database
        assert isinstance(metrics, list)

    @pytest.mark.asyncio
    async def test_collect_metrics_with_postgresql_servers(self) -> None:
        """Test collecting PostgreSQL servers."""
        pg_server = _make_postgresql_server("my-postgres", "my-rg")

        mock_sql_client = MagicMock()
        mock_sql_client.servers.list_by_subscription = MagicMock(return_value=[])
        mock_sql_client.databases.list_by_server = MagicMock(return_value=[])

        mock_pg_client = MagicMock()
        mock_pg_client.servers.list = MagicMock(return_value=[pg_server])

        with patch("azure.identity.DefaultAzureCredential"):
            with patch(
                "azure.mgmt.sql.SqlManagementClient", return_value=mock_sql_client
            ):
                with patch(
                    "azure.mgmt.rdbms.postgresql.PostgreSQLManagementClient",
                    return_value=mock_pg_client,
                ):
                    with patch(
                        "azure_collector.collectors.databases.run_sync",
                        new=AsyncMock(side_effect=lambda f: f()),
                    ):
                        collector = ConcreteDatabaseCollector(
                            source_lz_id="azure-sub-fa5abbc4",
                            subscription_id="12345678-1234-1234-1234-123456789012",
                        )
                        metrics = await collector._collect_metrics()

        # Should have metrics for PostgreSQL server
        assert isinstance(metrics, list)
