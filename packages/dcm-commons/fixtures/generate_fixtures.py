"""Generate JSON fixture files for all DCM metric domains.

Usage::

    cd dcm-commons
    uv run python fixtures/generate_fixtures.py

Each fixture is a valid ``MetricPayload`` serialised to JSON — exactly the
payload that the Lambda ingestion function receives from the APIGEE gateway.
The Databricks team can use these files to test the end-to-end ingestion
pipeline without running real collectors.

Output: one JSON file per domain/cloud combination in this same directory.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from dcm_commons.models.activity_run import ActivityRunMetric
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
    StandardCheckState,
    TriggerType,
    UserType,
)
from dcm_commons.models.payload import MetricPayload
from dcm_commons.models.pipeline import PipelineMetric
from dcm_commons.models.security import SecurityAlert
from dcm_commons.models.standard_check import StandardCheckMetric
from dcm_commons.models.user import UserMetric

FIXTURES_DIR = Path(__file__).parent


def _write(filename: str, payload: MetricPayload) -> None:
    out = FIXTURES_DIR / filename
    out.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
    print(f"  {filename}")


def pipeline_azure_failed() -> None:
    metric = PipelineMetric(
        pipeline_id="/subscriptions/fa5abbc4/resourceGroups/rg-data/providers/Microsoft.DataFactory/factories/adf-prod/pipelines/ingest_daily_raw",
        pipeline_name="ingest_daily_raw",
        run_id="adf-run-0001-failed",
        status=PipelineRunStatus.FAILED,
        trigger_type=TriggerType.SCHEDULED,
        start_time=datetime(2026, 4, 14, 2, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 4, 14, 2, 7, 43, tzinfo=timezone.utc),
        error_message="A database operation failed with the following error: 'Timeout expired. The timeout period elapsed prior to completion of the operation.'",
        factory_name="adf-prod",
        resource_group="rg-data",
        tags={"env": "prod", "team": "data-engineering"},
    )
    payload = MetricPayload(
        source_lz_id="lz-azure-prod",
        subscription_or_account_id="fa5abbc4-02eb-416f-a75f-f8f6c5cc7d8a",
        cloud_provider=CloudProvider.AZURE,
        domain=MetricDomain.PIPELINE,
        metrics=[metric.model_dump()],
        metadata={"collector_version": "1.4.0", "region": "westeurope"},
    )
    _write("pipeline_azure_failed.json", payload)


def pipeline_azure_running() -> None:
    metric = PipelineMetric(
        pipeline_id="/subscriptions/fa5abbc4/resourceGroups/rg-data/providers/Microsoft.DataFactory/factories/adf-prod/pipelines/transform_silver_compute",
        pipeline_name="transform_silver_compute",
        run_id="adf-run-0002-running",
        status=PipelineRunStatus.RUNNING,
        trigger_type=TriggerType.SCHEDULED,
        start_time=datetime(2026, 4, 14, 3, 30, 0, tzinfo=timezone.utc),
        factory_name="adf-prod",
        resource_group="rg-data",
        tags={"env": "prod", "layer": "silver"},
    )
    payload = MetricPayload(
        source_lz_id="lz-azure-prod",
        subscription_or_account_id="fa5abbc4-02eb-416f-a75f-f8f6c5cc7d8a",
        cloud_provider=CloudProvider.AZURE,
        domain=MetricDomain.PIPELINE,
        metrics=[metric.model_dump()],
        metadata={"collector_version": "1.4.0", "region": "westeurope"},
    )
    _write("pipeline_azure_running.json", payload)


def pipeline_aws_succeeded() -> None:
    metric = PipelineMetric(
        pipeline_id="glue-job-ingest-s3-to-delta",
        pipeline_name="glue-job-ingest-s3-to-delta",
        run_id="jr_abc123def456",
        status=PipelineRunStatus.SUCCEEDED,
        trigger_type=TriggerType.SCHEDULED,
        start_time=datetime(2026, 4, 14, 4, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 4, 14, 4, 12, 18, tzinfo=timezone.utc),
        glue_job_name="glue-job-ingest-s3-to-delta",
        tags={"env": "prod", "cost-center": "data-platform"},
    )
    payload = MetricPayload(
        source_lz_id="lz-aws-prod",
        subscription_or_account_id="123456789012",
        cloud_provider=CloudProvider.AWS,
        domain=MetricDomain.PIPELINE,
        metrics=[metric.model_dump()],
        metadata={"collector_version": "1.4.0", "region": "eu-west-1"},
    )
    _write("pipeline_aws_succeeded.json", payload)


def compute_azure() -> None:
    metric = ComputeMetric(
        compute_resource_id="0312-151347-reef123",
        resource_name="prod-etl-cluster",
        compute_type=ComputeType.DATABRICKS,
        state=ComputeState.RUNNING,
        num_workers=4,
        autoscale_min=2,
        autoscale_max=8,
        node_type="Standard_DS3_v2",
        spark_version="13.3.x-scala2.12",
        start_time=datetime(2026, 4, 14, 1, 0, 0, tzinfo=timezone.utc),
        creator="yahia.zerdoumi@company.com",
        estimated_hourly_cost_usd=3.84,
        workspace_id="adb-3059738143768593",
        avg_cpu_utilization_pct=Decimal("67.4"),
        avg_mem_utilization_pct=Decimal("54.1"),
        tags={"env": "prod", "team": "data-engineering", "cost-center": "dc-monitoring"},
    )
    payload = MetricPayload(
        source_lz_id="lz-azure-prod",
        subscription_or_account_id="fa5abbc4-02eb-416f-a75f-f8f6c5cc7d8a",
        cloud_provider=CloudProvider.AZURE,
        domain=MetricDomain.COMPUTE,
        metrics=[metric.model_dump()],
        metadata={"collector_version": "1.4.0", "region": "westeurope"},
    )
    _write("compute_azure.json", payload)


def compute_aws() -> None:
    metric = ComputeMetric(
        compute_resource_id="j-3ABCDEFGHIJKL",
        resource_name="emr-cluster-etl-prod",
        compute_type=ComputeType.EMR,
        state=ComputeState.RUNNING,
        num_workers=6,
        node_type="r5.2xlarge",
        start_time=datetime(2026, 4, 14, 0, 30, 0, tzinfo=timezone.utc),
        creator="arn:aws:iam::123456789012:role/emr-service-role",
        estimated_hourly_cost_usd=7.20,
        avg_cpu_utilization_pct=Decimal("78.9"),
        avg_mem_utilization_pct=Decimal("62.3"),
        tags={"env": "prod", "team": "data-platform", "Name": "emr-cluster-etl-prod"},
    )
    payload = MetricPayload(
        source_lz_id="lz-aws-prod",
        subscription_or_account_id="123456789012",
        cloud_provider=CloudProvider.AWS,
        domain=MetricDomain.COMPUTE,
        metrics=[metric.model_dump()],
        metadata={"collector_version": "1.4.0", "region": "eu-west-1"},
    )
    _write("compute_aws.json", payload)


def cost_azure() -> None:
    metrics = [
        CostMetric(
            service_name="Azure Databricks",
            resource_group="rg-data",
            subscription_or_account_id="fa5abbc4-02eb-416f-a75f-f8f6c5cc7d8a",
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 13),
            cost_usd=1842.50,
            budget_name="budget-data-platform",
            budget_limit_usd=5000.0,
            budget_consumed_pct=36.85,
            tags={"env": "prod", "service": "databricks"},
        ),
        CostMetric(
            service_name="Azure Data Factory",
            resource_group="rg-data",
            subscription_or_account_id="fa5abbc4-02eb-416f-a75f-f8f6c5cc7d8a",
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 13),
            cost_usd=312.75,
            budget_name="budget-data-platform",
            budget_limit_usd=5000.0,
            budget_consumed_pct=6.26,
            tags={"env": "prod", "service": "adf"},
        ),
    ]
    payload = MetricPayload(
        source_lz_id="lz-azure-prod",
        subscription_or_account_id="fa5abbc4-02eb-416f-a75f-f8f6c5cc7d8a",
        cloud_provider=CloudProvider.AZURE,
        domain=MetricDomain.COST,
        metrics=[m.model_dump() for m in metrics],
        metadata={"collector_version": "1.4.0", "currency": "USD"},
    )
    _write("cost_azure.json", payload)


def cost_aws() -> None:
    metrics = [
        CostMetric(
            service_name="Amazon EMR",
            subscription_or_account_id="123456789012",
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 13),
            cost_usd=2147.30,
            budget_name="aws-data-budget",
            budget_limit_usd=8000.0,
            budget_consumed_pct=26.84,
            tags={"env": "prod", "team": "data-platform"},
        ),
        CostMetric(
            service_name="AWS Glue",
            subscription_or_account_id="123456789012",
            period_start=date(2026, 4, 1),
            period_end=date(2026, 4, 13),
            cost_usd=418.60,
            tags={"env": "prod", "team": "data-platform"},
        ),
    ]
    payload = MetricPayload(
        source_lz_id="lz-aws-prod",
        subscription_or_account_id="123456789012",
        cloud_provider=CloudProvider.AWS,
        domain=MetricDomain.COST,
        metrics=[m.model_dump() for m in metrics],
        metadata={"collector_version": "1.4.0", "currency": "USD"},
    )
    _write("cost_aws.json", payload)


def database_azure() -> None:
    metric = DatabaseMetric(
        db_id="/subscriptions/fa5abbc4/resourceGroups/rg-data/providers/Microsoft.Sql/servers/sql-prod-dcm/databases/db-monitoring",
        db_name="db-monitoring",
        db_type=DatabaseType.SQLSERVER,
        server_name="sql-prod-dcm.database.windows.net",
        resource_group="rg-data",
        region="westeurope",
        cpu_percent=42.5,
        memory_percent=61.3,
        storage_used_gb=18.7,
        storage_limit_gb=250.0,
        active_connections=14,
        dtus_used=38.2,
        is_available=True,
        tags={"env": "prod", "tier": "standard"},
    )
    payload = MetricPayload(
        source_lz_id="lz-azure-prod",
        subscription_or_account_id="fa5abbc4-02eb-416f-a75f-f8f6c5cc7d8a",
        cloud_provider=CloudProvider.AZURE,
        domain=MetricDomain.DATABASE,
        metrics=[metric.model_dump()],
        metadata={"collector_version": "1.4.0", "region": "westeurope"},
    )
    _write("database_azure.json", payload)


def security_azure() -> None:
    metric = SecurityAlert(
        alert_id="2517346abc12ef34-a56b-78cd-90ef-1234567890ab",
        title="Suspicious login from unfamiliar location",
        description="A successful sign-in was detected from an IP address that has not been seen before for this user. This could indicate a compromised account.",
        severity=AlertSeverity.HIGH,
        status=AlertStatus.ACTIVE,
        detected_at=datetime(2026, 4, 14, 6, 15, 0, tzinfo=timezone.utc),
        resource_id="/subscriptions/fa5abbc4/resourceGroups/rg-data/providers/Microsoft.Sql/servers/sql-prod-dcm",
        resource_name="sql-prod-dcm",
        resource_type="Microsoft.Sql/servers",
        remediation="Review the sign-in activity in Azure Active Directory. If the sign-in is not recognized, revoke the user's session and reset credentials.",
        compromised_entity="yahia.zerdoumi@company.com",
        tags={"env": "prod", "source": "defender-for-cloud"},
    )
    payload = MetricPayload(
        source_lz_id="lz-azure-prod",
        subscription_or_account_id="fa5abbc4-02eb-416f-a75f-f8f6c5cc7d8a",
        cloud_provider=CloudProvider.AZURE,
        domain=MetricDomain.SECURITY,
        metrics=[metric.model_dump()],
        metadata={"collector_version": "1.4.0", "defender_plan": "Defender for SQL"},
    )
    _write("security_azure.json", payload)


def user_azure() -> None:
    metric = UserMetric(
        user_id="5678901234",
        user_name="jane.doe@company.com",
        user_type=UserType.DATABRICKS,
        display_name="Jane DOE",
        workspace_or_account="https://adb-3059738143768593.13.azuredatabricks.net",
        is_active=True,
        last_activity_at=datetime(2026, 4, 13, 17, 42, 0, tzinfo=timezone.utc),
        groups=["admins", "data-engineers", "ml-practitioners"],
        roles=["CAN_MANAGE", "CAN_RESTART"],
        tags={"department": "Data & Analytics", "cost-center": "dc-monitoring"},
    )
    payload = MetricPayload(
        source_lz_id="lz-azure-prod",
        subscription_or_account_id="fa5abbc4-02eb-416f-a75f-f8f6c5cc7d8a",
        cloud_provider=CloudProvider.AZURE,
        domain=MetricDomain.USER,
        metrics=[metric.model_dump()],
        metadata={"collector_version": "1.4.0", "scim_version": "2.0"},
    )
    _write("user_azure.json", payload)


def activity_run_azure() -> None:
    metrics = [
        ActivityRunMetric(
            pipeline_run_id="adf-run-0001-failed",
            pipeline_name="ingest_daily_raw",
            activity_name="CopyBlobToLake",
            activity_type=ActivityType.COPY,
            status=ActivityRunStatus.SUCCEEDED,
            start_time=datetime(2026, 4, 14, 2, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 4, 14, 2, 5, 12, tzinfo=timezone.utc),
            rows_read=2_450_000,
            rows_written=2_450_000,
            data_read_bytes=858_993_459,
            data_written_bytes=858_993_459,
        ),
        ActivityRunMetric(
            pipeline_run_id="adf-run-0001-failed",
            pipeline_name="ingest_daily_raw",
            activity_name="TransformWithDatabricks",
            activity_type=ActivityType.DATABRICKS_NOTEBOOK,
            status=ActivityRunStatus.FAILED,
            start_time=datetime(2026, 4, 14, 2, 5, 15, tzinfo=timezone.utc),
            end_time=datetime(2026, 4, 14, 2, 7, 43, tzinfo=timezone.utc),
            error_message="Timeout expired. The timeout period elapsed prior to completion of the operation.",
        ),
    ]
    payload = MetricPayload(
        source_lz_id="lz-azure-prod",
        subscription_or_account_id="fa5abbc4-02eb-416f-a75f-f8f6c5cc7d8a",
        cloud_provider=CloudProvider.AZURE,
        domain=MetricDomain.ACTIVITY_RUN,
        metrics=[m.model_dump() for m in metrics],
        metadata={"collector_version": "1.4.0", "region": "westeurope"},
    )
    _write("activity_run_azure.json", payload)


def standard_check_azure() -> None:
    metrics = [
        StandardCheckMetric(
            check_id="/subscriptions/fa5abbc4/providers/Microsoft.Authorization/policyDefinitions/a4af4a39-4135-47fb-b175-47fbdf85311d",
            check_name="Require HTTPS on Storage Accounts",
            check_state=StandardCheckState.NON_COMPLIANT,
            resource_id="/subscriptions/fa5abbc4/resourceGroups/rg-data/providers/Microsoft.Storage/storageAccounts/stdatarawprod",
            resource_name="stdatarawprod",
            resource_type="Microsoft.Storage/storageAccounts",
            check_effect=CheckEffect.AUDIT,
            non_check_reasons=["Storage account does not enforce HTTPS-only traffic."],
            evaluated_at=datetime(2026, 4, 14, 0, 0, 0, tzinfo=timezone.utc),
            tags={"scope": "non_compliant_only", "policy_initiative": "ISO-27001"},
        ),
        StandardCheckMetric(
            check_id="/subscriptions/fa5abbc4/providers/Microsoft.Authorization/policyDefinitions/c95c74d9-38fe-4f0d-af86-0c7d626a315c",
            check_name="Enable Defender for SQL on SQL Servers",
            check_state=StandardCheckState.COMPLIANT,
            resource_id="/subscriptions/fa5abbc4/resourceGroups/rg-data/providers/Microsoft.Sql/servers/sql-prod-dcm",
            resource_name="sql-prod-dcm",
            resource_type="Microsoft.Sql/servers",
            check_effect=CheckEffect.DEPLOY_IF_NOT_EXISTS,
            evaluated_at=datetime(2026, 4, 14, 0, 0, 0, tzinfo=timezone.utc),
            tags={"scope": "full_evaluation", "policy_initiative": "Defender-for-Cloud"},
        ),
    ]
    payload = MetricPayload(
        source_lz_id="lz-azure-prod",
        subscription_or_account_id="fa5abbc4-02eb-416f-a75f-f8f6c5cc7d8a",
        cloud_provider=CloudProvider.AZURE,
        domain=MetricDomain.STANDARD_CHECK,
        metrics=[m.model_dump() for m in metrics],
        metadata={"collector_version": "1.4.0", "policy_initiative": "ISO-27001"},
    )
    _write("standard_check_azure.json", payload)


if __name__ == "__main__":
    print("Generating DCM JSON fixtures...")
    pipeline_azure_failed()
    pipeline_azure_running()
    pipeline_aws_succeeded()
    compute_azure()
    compute_aws()
    cost_azure()
    cost_aws()
    database_azure()
    security_azure()
    user_azure()
    activity_run_azure()
    standard_check_azure()
    print(f"\nDone — 12 fixtures written to {FIXTURES_DIR.resolve()}")
