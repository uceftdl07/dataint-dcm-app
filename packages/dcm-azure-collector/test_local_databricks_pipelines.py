#!/usr/bin/env python3
"""Local dev test — DatabricksPipelineCollector with mock data.

Run this script to test the collector locally without real Azure/Databricks APIs.

Usage:
    python test_local_databricks_pipelines.py
"""

import asyncio
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

# Setup environment for local dev
os.environ["DCM_LOG_LEVEL"] = "DEBUG"


async def test_collector_local() -> None:
    """Test DatabricksPipelineCollector with mock data."""
    from azure_collector.collectors.databricks_pipelines import DatabricksPipelineCollector
    from azure.identity import DefaultAzureCredential

    # Mock workspace
    mock_workspace = {
        "name": "test-workspace",
        "workspace_id": "1234567890",
        "workspace_url": "https://eastus.azuredatabricks.net",
        "resource_group": "test-rg",
    }

    # Mock job runs
    now = datetime.now(timezone.utc)
    mock_runs = [
        {
            "run_id": 1,
            "job_id": 100,
            "run_name": "etl_daily_sync",
            "state": "SUCCESS",
            "start_time": int((now - timedelta(hours=2)).timestamp() * 1000),
            "end_time": int((now - timedelta(hours=1, minutes=50)).timestamp() * 1000),
            "state_message": "",
            "tags": {"env": "prod", "team": "data"},
        },
        {
            "run_id": 2,
            "job_id": 101,
            "run_name": "data_quality_checks",
            "state": "RUNNING",
            "start_time": int((now - timedelta(minutes=30)).timestamp() * 1000),
            "end_time": None,
            "state_message": "",
            "tags": {},
        },
        {
            "run_id": 3,
            "job_id": 102,
            "run_name": "failed_job",
            "state": "FAILED",
            "start_time": int((now - timedelta(hours=4)).timestamp() * 1000),
            "end_time": int((now - timedelta(hours=3)).timestamp() * 1000),
            "state_message": "Task failed: schema validation error in step 2",
            "tags": {},
        },
    ]

    print("\n" + "=" * 80)
    print("Testing DatabricksPipelineCollector with mock data")
    print("=" * 80 + "\n")

    with patch.object(DefaultAzureCredential, "__init__", return_value=None):
        with patch(
            "azure_collector.collectors.databricks_pipelines.get_mgmt_token",
            new_callable=AsyncMock,
            return_value="test-mgmt-token",
        ):
            with patch(
                "azure_collector.collectors.databricks_pipelines.get_databricks_token",
                new_callable=AsyncMock,
                return_value="test-db-token",
            ):
                with patch(
                    "azure_collector.collectors.databricks_pipelines._list_workspaces",
                    new_callable=AsyncMock,
                    return_value=[mock_workspace],
                ):
                    with patch(
                        "azure_collector.collectors.databricks_pipelines._list_job_runs",
                        new_callable=AsyncMock,
                        return_value=mock_runs,
                    ):
                        collector = DatabricksPipelineCollector(
                            source_lz_id="azure-sub-test",
                            subscription_id="test-sub-id",
                            lookback_hours=24,
                        )

                        print(f"Collector domain: {collector.domain}\n")

                        # Collect metrics
                        result = await collector.collect()

                        print(f"Collection result:")
                        print(f"  - Status event count: {len(result.events)}")
                        print(f"  - Payload metric count: {result.payload.metric_count}")
                        print(f"  - Payload domain: {result.payload.domain}\n")

                        # Display metrics
                        if result.payload.metrics:
                            print("Collected metrics:")
                            for i, metric in enumerate(result.payload.metrics, 1):
                                print(f"\n  Metric {i}:")
                                print(f"    - run_id: {metric.get('run_id')}")
                                print(f"    - pipeline_name: {metric.get('pipeline_name')}")
                                print(f"    - status: {metric.get('status')}")
                                print(f"    - start_time: {metric.get('start_time')}")
                                print(f"    - end_time: {metric.get('end_time')}")
                                print(f"    - databricks_workspace_id: {metric.get('databricks_workspace_id')}")
                                if metric.get("error_message"):
                                    print(f"    - error_message: {metric.get('error_message')}")

                        print("\n" + "=" * 80)
                        print("✅ Test completed successfully!")
                        print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(test_collector_local())

