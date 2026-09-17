"""Azure Database collector — SQL, PostgreSQL, MySQL, Cosmos DB metrics.

Discovers all Azure database resources in the monitored subscription and
collects a point-in-time health/performance snapshot for each one from
Azure Monitor.  Covers four engine families:

- **Azure SQL Database** (PaaS, DTU/vCore billing)
- **Azure Database for PostgreSQL – Flexible Server**
- **Azure Database for MySQL – Flexible Server**
- **Azure Cosmos DB** (multi-region NoSQL, serverless or provisioned)

Azure SDKs used
---------------
``azure-mgmt-sql`` (synchronous) — wrapped in :func:`run_sync`
    Enumerate Azure SQL servers and their databases.
``azure-mgmt-rdbms`` (synchronous) — wrapped in :func:`run_sync`
    Enumerate PostgreSQL and MySQL Flexible Servers.
``azure-mgmt-cosmosdb`` (synchronous) — wrapped in :func:`run_sync`
    Enumerate Cosmos DB accounts.
``azure-mgmt-monitor`` (synchronous) — wrapped in :func:`run_sync`
    Fetch per-resource time-series metrics (CPU, storage, connections,
    DTU, RU/s) from Azure Monitor.

Key API calls
-------------
``SqlManagementClient.servers.list()``
    All Azure SQL servers in the subscription.
``SqlManagementClient.databases.list_by_server(resource_group, server)``
    All user databases within a SQL server (system DBs excluded).
``PostgreSQLManagementClient.servers.list()``
    All PostgreSQL Flexible Servers in the subscription.
``MySQLManagementClient.servers.list()``
    All MySQL Flexible Servers in the subscription.
``CosmosDBManagementClient.database_accounts.list()``
    All Cosmos DB accounts in the subscription.
``MonitorManagementClient.metrics.list(resource_uri, ...)``
    Azure Monitor metrics over the last :data:`_METRICS_WINDOW_MINUTES`
    minutes, at a ``PT5M`` interval.

Ported from
-----------
``AzureDatabaseService.cs`` (POC C# backend)

Lakebase target
---------------
``dcm.monitoring.database_snapshots``
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from azure.identity import DefaultAzureCredential  # type: ignore[import-untyped]
from azure.mgmt.cosmosdb import CosmosDBManagementClient  # type: ignore[import-untyped]
from azure.mgmt.monitor import MonitorManagementClient  # type: ignore[import-untyped]
from azure.mgmt.rdbms.mysql_flexibleservers import (  # type: ignore[import-untyped]
    MySQLManagementClient,
)
from azure.mgmt.rdbms.postgresql_flexibleservers import (  # type: ignore[import-untyped]
    PostgreSQLManagementClient,
)
from azure.mgmt.sql import SqlManagementClient  # type: ignore[import-untyped]

from dcm_commons.collectors.base import BaseCollector
from dcm_commons.exceptions import CollectionError
from dcm_commons.logging_utils import get_logger
from dcm_commons.models.database import DatabaseMetric
from dcm_commons.models.enums import CloudProvider, DatabaseType, MetricDomain

from azure_collector._azure_utils import run_sync

__all__ = ["DatabaseCollector"]

_logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Look-back window fed to Azure Monitor metrics queries.
_METRICS_WINDOW_MINUTES: int = 15

# Azure Monitor metric names per database engine family.
# Names must match exactly what Azure Monitor exposes for each resource type.
_SQL_METRIC_NAMES: tuple[str, ...] = (
    "cpu_percent",
    "dtu_consumption_percent",
    "storage",               # bytes used (Azure SQL Database only)
    "connection_successful",
    "connection_failed",
)
_FLEX_METRIC_NAMES: tuple[str, ...] = (
    "cpu_percent",
    "memory_percent",
    "storage_used",          # bytes used (PostgreSQL / MySQL Flexible)
    "active_connections",
)
_COSMOS_METRIC_NAMES: tuple[str, ...] = (
    "TotalRequestUnits",
    "DocumentCount",
    "DataUsage",             # bytes (total account storage)
)

# Bytes → GiB conversion factor.
_BYTES_TO_GB: float = 1.0 / (1024.0 ** 3)

# Azure SQL system databases — never monitored.
_SQL_SYSTEM_DBS: frozenset[str] = frozenset({"master", "model", "msdb", "tempdb"})


class DatabaseCollector(BaseCollector):
    """Collects health and performance snapshots for Azure database services.

    Discovers Azure SQL databases, PostgreSQL Flexible Servers, MySQL
    Flexible Servers, and Cosmos DB accounts in the subscription.  For each
    resource, queries Azure Monitor for CPU, storage, connections, and
    engine-specific metrics (DTU, RU/s) within the last
    :data:`_METRICS_WINDOW_MINUTES` minutes.

    Per-category failures (e.g. SQL server listing fails) are logged and
    skipped — other database families continue to be collected.

    Args:
        source_lz_id:             Landing zone identifier.
        subscription_id:          Azure subscription ID.
        credential:               ``azure.identity`` credential.  Defaults to
                                  ``DefaultAzureCredential``.
        max_retries:              Retry attempts on transient failures.
        retry_base_delay_seconds: Base delay for exponential back-off.
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
        super().__init__(
            source_lz_id=source_lz_id,
            cloud_provider=CloudProvider.AZURE,
            subscription_or_account_id=subscription_id,
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
        """Return the database metric domain."""
        return MetricDomain.DATABASE

    async def _collect_metrics(self) -> list[dict[str, Any]]:
        """Enumerate all Azure database resources and collect Monitor metrics.

        Runs four sub-collectors in sequence (SQL, PostgreSQL, MySQL, Cosmos DB).
        Each sub-collector catches its own errors and logs them without
        aborting the others.

        Returns:
            List of :class:`~dcm_commons.models.database.DatabaseMetric` dicts.

        Raises:
            CollectionError: Propagated from sub-collectors when the error
                             signals a broader authentication or SDK failure
                             that warrants a full retry of the cycle.
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=_METRICS_WINDOW_MINUTES)

        _logger.info(
            "database_collect_starting",
            subscription_id=self._subscription_id,
            metrics_window_minutes=_METRICS_WINDOW_MINUTES,
        )

        metrics: list[dict[str, Any]] = []

        for collect_fn in (
            self._collect_sql_databases,
            self._collect_postgresql_servers,
            self._collect_mysql_servers,
            self._collect_cosmos_accounts,
        ):
            _logger.info(
                "database_category_starting",
                category=collect_fn.__name__,
            )
            try:
                items = await collect_fn(window_start, now)
                metrics.extend(items)
                _logger.info(
                    "database_category_done",
                    category=collect_fn.__name__,
                    metric_count=len(items),
                )
            except CollectionError:
                raise  # let base retry logic handle broad authentication failures
            except Exception as exc:
                _logger.warning(
                    "database_category_failed",
                    category=collect_fn.__name__,
                    reason=str(exc),
                )

        _logger.info("database_collection_done", metric_count=len(metrics))
        return metrics

    # ------------------------------------------------------------------
    # Per-engine-family helpers
    # ------------------------------------------------------------------

    async def _collect_sql_databases(
        self,
        window_start: datetime,
        window_end: datetime,
    ) -> list[dict[str, Any]]:
        """List all Azure SQL servers and collect per-database Monitor metrics.

        System databases (master, model, msdb, tempdb) are excluded.  If a
        single server's database listing fails, that server is skipped and
        collection continues for the remaining servers.

        Args:
            window_start: Start of the Monitor metric time window (UTC).
            window_end:   End of the Monitor metric time window (UTC).

        Returns:
            List of serialised :class:`DatabaseMetric` dicts for Azure SQL.

        Raises:
            CollectionError: If the top-level server list call fails.
        """
        _logger.info("database_sql_servers_list_starting")
        try:
            servers = await run_sync(lambda: list(self._sql_client.servers.list()))
        except Exception as exc:
            raise CollectionError(
                "DatabaseCollector",
                f"Failed to list Azure SQL servers: {exc}",
            ) from exc

        _logger.info("database_sql_servers_list_done", server_count=len(servers))
        metrics: list[dict[str, Any]] = []

        for server in servers:
            resource_group = _extract_resource_group(server.id or "")
            server_name = server.name or ""
            if not resource_group or not server_name:
                continue

            server_tags: dict[str, str] = dict(server.tags or {})

            try:
                # Capture loop variables in default args to avoid closure bugs.
                databases = await run_sync(
                    lambda rg=resource_group, sn=server_name: list(
                        self._sql_client.databases.list_by_server(rg, sn)
                    )
                )
            except Exception as exc:
                _logger.warning(
                    "sql_databases_list_failed",
                    server=server_name,
                    reason=str(exc),
                )
                continue

            for db in databases:
                db_name = db.name or ""
                resource_id = db.id or ""
                if not db_name or not resource_id or db_name.lower() in _SQL_SYSTEM_DBS:
                    continue

                monitor_data = await _fetch_monitor_metrics(
                    self._monitor_client,
                    resource_id=resource_id,
                    metric_names=list(_SQL_METRIC_NAMES),
                    window_start=window_start,
                    window_end=window_end,
                )

                # Azure Monitor returns storage in bytes — convert to GB.
                storage_bytes = monitor_data.get("storage")
                storage_used_gb = (
                    round(storage_bytes * _BYTES_TO_GB, 4)
                    if storage_bytes is not None
                    else None
                )

                # Database max size is a resource property (bytes).
                max_size_bytes: int | None = getattr(db, "max_size_bytes", None)
                storage_limit_gb = (
                    round(max_size_bytes * _BYTES_TO_GB, 4)
                    if max_size_bytes
                    else None
                )

                metric = DatabaseMetric(
                    db_id=resource_id,
                    db_name=db_name,
                    db_type=DatabaseType.SQLSERVER,
                    server_name=f"{server_name}.database.windows.net",
                    resource_group=resource_group,
                    region=getattr(db, "location", None),
                    cpu_percent=monitor_data.get("cpu_percent"),
                    storage_used_gb=storage_used_gb,
                    storage_limit_gb=storage_limit_gb,
                    dtus_used=monitor_data.get("dtu_consumption_percent"),
                    is_available=True,
                    tags={**server_tags, **dict(db.tags or {})},
                )
                metrics.append(metric.model_dump())

        return metrics

    async def _collect_postgresql_servers(
        self,
        window_start: datetime,
        window_end: datetime,
    ) -> list[dict[str, Any]]:
        """List all PostgreSQL Flexible Servers and collect Monitor metrics.

        Each Flexible Server is treated as a single monitored unit.  Metrics
        are collected at the server level, not per individual database.

        Args:
            window_start: Start of the Monitor metric time window (UTC).
            window_end:   End of the Monitor metric time window (UTC).

        Returns:
            List of serialised :class:`DatabaseMetric` dicts for PostgreSQL.
        """
        _logger.info("database_postgresql_servers_list_starting")
        try:
            servers = await run_sync(lambda: list(self._pg_client.servers.list()))
        except Exception as exc:
            _logger.warning("postgresql_servers_list_failed", reason=str(exc))
            return []

        _logger.info("database_postgresql_servers_list_done", server_count=len(servers))
        metrics: list[dict[str, Any]] = []

        for server in servers:
            resource_id = server.id or ""
            server_name = server.name or ""
            if not resource_id or not server_name:
                continue

            resource_group = _extract_resource_group(resource_id)

            monitor_data = await _fetch_monitor_metrics(
                self._monitor_client,
                resource_id=resource_id,
                metric_names=list(_FLEX_METRIC_NAMES),
                window_start=window_start,
                window_end=window_end,
            )

            storage_bytes = monitor_data.get("storage_used")
            storage_used_gb = (
                round(storage_bytes * _BYTES_TO_GB, 4)
                if storage_bytes is not None
                else None
            )

            # Storage limit is exposed in GB by the Flexible Server SKU properties.
            storage_obj = getattr(server, "storage", None)
            storage_limit_gb: float | None = None
            if storage_obj is not None:
                raw_size = getattr(storage_obj, "storage_size_gb", None)
                storage_limit_gb = float(raw_size) if raw_size is not None else None

            metric = DatabaseMetric(
                db_id=resource_id,
                db_name=server_name,
                db_type=DatabaseType.POSTGRESQL,
                server_name=f"{server_name}.postgres.database.azure.com",
                resource_group=resource_group or None,
                region=getattr(server, "location", None),
                cpu_percent=monitor_data.get("cpu_percent"),
                memory_percent=monitor_data.get("memory_percent"),
                storage_used_gb=storage_used_gb,
                storage_limit_gb=storage_limit_gb,
                active_connections=_to_int(monitor_data.get("active_connections")),
                is_available=True,
                tags=dict(server.tags or {}),
            )
            metrics.append(metric.model_dump())

        return metrics

    async def _collect_mysql_servers(
        self,
        window_start: datetime,
        window_end: datetime,
    ) -> list[dict[str, Any]]:
        """List all MySQL Flexible Servers and collect Monitor metrics.

        Mirror of :meth:`_collect_postgresql_servers` — same Monitor metric
        names are supported by both Flexible Server flavours.

        Args:
            window_start: Start of the Monitor metric time window (UTC).
            window_end:   End of the Monitor metric time window (UTC).

        Returns:
            List of serialised :class:`DatabaseMetric` dicts for MySQL.
        """
        _logger.info("database_mysql_servers_list_starting")
        try:
            servers = await run_sync(lambda: list(self._mysql_client.servers.list()))
        except Exception as exc:
            _logger.warning("mysql_servers_list_failed", reason=str(exc))
            return []

        _logger.info("database_mysql_servers_list_done", server_count=len(servers))
        metrics: list[dict[str, Any]] = []

        for server in servers:
            resource_id = server.id or ""
            server_name = server.name or ""
            if not resource_id or not server_name:
                continue

            resource_group = _extract_resource_group(resource_id)

            monitor_data = await _fetch_monitor_metrics(
                self._monitor_client,
                resource_id=resource_id,
                metric_names=list(_FLEX_METRIC_NAMES),
                window_start=window_start,
                window_end=window_end,
            )

            storage_bytes = monitor_data.get("storage_used")
            storage_used_gb = (
                round(storage_bytes * _BYTES_TO_GB, 4)
                if storage_bytes is not None
                else None
            )

            storage_obj = getattr(server, "storage", None)
            storage_limit_gb: float | None = None
            if storage_obj is not None:
                raw_size = getattr(storage_obj, "storage_size_gb", None)
                storage_limit_gb = float(raw_size) if raw_size is not None else None

            metric = DatabaseMetric(
                db_id=resource_id,
                db_name=server_name,
                db_type=DatabaseType.MYSQL,
                server_name=f"{server_name}.mysql.database.azure.com",
                resource_group=resource_group or None,
                region=getattr(server, "location", None),
                cpu_percent=monitor_data.get("cpu_percent"),
                memory_percent=monitor_data.get("memory_percent"),
                storage_used_gb=storage_used_gb,
                storage_limit_gb=storage_limit_gb,
                active_connections=_to_int(monitor_data.get("active_connections")),
                is_available=True,
                tags=dict(server.tags or {}),
            )
            metrics.append(metric.model_dump())

        return metrics

    async def _collect_cosmos_accounts(
        self,
        window_start: datetime,
        window_end: datetime,
    ) -> list[dict[str, Any]]:
        """List all Cosmos DB accounts and collect Monitor metrics.

        Metrics are account-level aggregates (not per-database or per-container).
        Storage capacity is unbounded for Cosmos DB — ``storage_limit_gb`` is
        always ``None``.

        Args:
            window_start: Start of the Monitor metric time window (UTC).
            window_end:   End of the Monitor metric time window (UTC).

        Returns:
            List of serialised :class:`DatabaseMetric` dicts for Cosmos DB.
        """
        _logger.info("database_cosmos_accounts_list_starting")
        try:
            accounts = await run_sync(
                lambda: list(self._cosmos_client.database_accounts.list())
            )
        except Exception as exc:
            _logger.warning("cosmos_accounts_list_failed", reason=str(exc))
            return []

        _logger.info("database_cosmos_accounts_list_done", account_count=len(accounts))
        metrics: list[dict[str, Any]] = []

        for account in accounts:
            resource_id = account.id or ""
            account_name = account.name or ""
            if not resource_id or not account_name:
                continue

            resource_group = _extract_resource_group(resource_id)

            monitor_data = await _fetch_monitor_metrics(
                self._monitor_client,
                resource_id=resource_id,
                metric_names=list(_COSMOS_METRIC_NAMES),
                window_start=window_start,
                window_end=window_end,
            )

            # DataUsage is reported in bytes — convert to GB.
            data_usage_bytes = monitor_data.get("datausage")
            storage_used_gb = (
                round(data_usage_bytes * _BYTES_TO_GB, 4)
                if data_usage_bytes is not None
                else None
            )

            # ``document_endpoint`` is the full HTTPS endpoint URL; use it as
            # the server_name for identification.
            endpoint: str = getattr(account, "document_endpoint", "") or ""
            server_name = endpoint or f"{account_name}.documents.azure.com"

            metric = DatabaseMetric(
                db_id=resource_id,
                db_name=account_name,
                db_type=DatabaseType.COSMOS_DB,
                server_name=server_name,
                resource_group=resource_group or None,
                region=getattr(account, "location", None),
                storage_used_gb=storage_used_gb,
                is_available=True,
                tags=dict(account.tags or {}),
            )
            metrics.append(metric.model_dump())

        return metrics


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


async def _fetch_monitor_metrics(
    monitor_client: MonitorManagementClient,
    resource_id: str,
    metric_names: list[str],
    window_start: datetime,
    window_end: datetime,
) -> dict[str, float | None]:
    """Fetch Azure Monitor metrics for a single resource over a time window.

    Queries Azure Monitor for the given metric names and returns the most
    recent non-null average value for each metric.  Returns an empty dict
    on any SDK error (non-fatal: Monitor unavailability should not stop
    resource discovery).

    Args:
        monitor_client: Authenticated :class:`MonitorManagementClient`.
        resource_id:    Full ARM resource ID of the target database resource.
        metric_names:   Metric names to query (case-sensitive, Azure Monitor
                        format, e.g. ``["cpu_percent", "storage_used"]``).
        window_start:   Start of the metric time window (tz-aware UTC).
        window_end:     End of the metric time window (tz-aware UTC).

    Returns:
        Dict mapping **lowercase** metric name → average value (``float``),
        or ``None`` if Azure Monitor returned no data for that metric.
        Empty dict on any SDK or network error.
    """
    timespan = f"{window_start.isoformat()}/{window_end.isoformat()}"
    try:
        response = await run_sync(
            monitor_client.metrics.list,
            resource_id,
            timespan=timespan,
            interval="PT5M",
            metricnames=",".join(metric_names),
            aggregation="Average",
        )
    except Exception as exc:
        _logger.debug(
            "monitor_metrics_fetch_failed",
            resource_id=resource_id,
            reason=str(exc),
        )
        return {}

    result: dict[str, float | None] = {}

    for metric_obj in response.value or []:
        name_obj = getattr(metric_obj, "name", None)
        name_raw: str = (getattr(name_obj, "value", None) or "").lower()
        if not name_raw:
            continue

        # Walk timeseries in reverse order — take the most recent non-null Average.
        value: float | None = None
        for ts in getattr(metric_obj, "timeseries", None) or []:
            for point in reversed(getattr(ts, "data", None) or []):
                avg = getattr(point, "average", None)
                if avg is not None:
                    value = float(avg)
                    break
            if value is not None:
                break

        result[name_raw] = value

    return result


def _to_int(val: float | None) -> int | None:
    """Convert a floating-point Monitor metric value to a rounded integer.

    Azure Monitor connection-count metrics arrive as floats.

    Args:
        val: Float value, or ``None`` if no data was returned.

    Returns:
        Rounded integer, or ``None`` if ``val`` is ``None``.
    """
    return int(round(val)) if val is not None else None


def _extract_resource_group(resource_id: str) -> str:
    """Extract the resource group name from an ARM resource ID.

    ARM resource ID format::

        /subscriptions/{sub}/resourceGroups/{rg}/providers/...

    Args:
        resource_id: Full ARM resource ID string.

    Returns:
        Resource group name (original casing), or empty string if the ID
        is malformed or empty.
    """
    parts = resource_id.lower().split("/")
    try:
        idx = parts.index("resourcegroups")
        return resource_id.split("/")[idx + 1]
    except (ValueError, IndexError):
        return ""
