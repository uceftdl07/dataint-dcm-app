"""DCM Azure Collector — collects KPI metrics from Azure services.

Deployed as an Azure App Service WebJob (continuous mode) within the
monitored landing zone.  Runs a collection loop every
``DCM_COLLECTION_INTERVAL`` seconds (default: 300 s / 5 minutes).

Collected domains
-----------------
- ``pipeline``        — Azure Data Factory pipeline runs
- ``cluster``         — Azure Databricks cluster state
- ``cost``            — Azure Cost Management daily costs and budgets
- ``database``        — Azure SQL / PostgreSQL / MySQL / Cosmos DB health
- ``security``        — Microsoft Defender for Cloud alerts

Entry point
-----------
``dcm-azure-collector`` script → :func:`azure_collector.main.run`
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__: list[str] = []
