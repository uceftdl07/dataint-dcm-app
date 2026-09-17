"""Tests for MetricPayload and all domain metric models.

Coverage:
    - Shared enum behaviour (StrEnum equality, computed properties).
    - BaseMetricModel configuration (frozen, str_strip_whitespace, use_enum_values).
    - MetricPayload: defaults, computed fields, UTC coercion, repr, immutability.
    - PipelineMetric: duration derivation, field constraints.
    - ComputeMetric: enum usage, optional fields, new utilisation columns.
    - CostMetric: cross-field date validation.
    - DatabaseMetric: DatabaseType enum, constraint validators.
    - SecurityAlert: AlertStatus default, enum serialisation.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from dcm_commons.models.compute import ComputeMetric
from dcm_commons.models.cost import CostMetric
from dcm_commons.models.database import DatabaseMetric
from dcm_commons.models.enums import (
    AlertSeverity,
    AlertStatus,
    ComputeState,
    ComputeType,
    DatabaseType,
    MetricDomain,
    PipelineRunStatus,
    TriggerType,
)
from dcm_commons.models.payload import MetricPayload
from dcm_commons.models.pipeline import PipelineMetric
from dcm_commons.models.security import SecurityAlert


# ==========================================================================
# Enum behaviour
# ==========================================================================


class TestEnums:
    """StrEnum equality and computed properties."""

    def test_pipeline_status_equals_string(self) -> None:
        assert PipelineRunStatus.FAILED == "failed"
        assert PipelineRunStatus.SUCCEEDED == "succeeded"

    def test_pipeline_status_is_terminal(self) -> None:
        assert PipelineRunStatus.SUCCEEDED.is_terminal is True
        assert PipelineRunStatus.FAILED.is_terminal is True
        assert PipelineRunStatus.CANCELLED.is_terminal is True
        assert PipelineRunStatus.TIMED_OUT.is_terminal is True
        assert PipelineRunStatus.SKIPPED.is_terminal is True
        assert PipelineRunStatus.RUNNING.is_terminal is False
        assert PipelineRunStatus.QUEUED.is_terminal is False

    def test_pipeline_status_is_failure(self) -> None:
        assert PipelineRunStatus.FAILED.is_failure is True
        assert PipelineRunStatus.TIMED_OUT.is_failure is True
        assert PipelineRunStatus.SUCCEEDED.is_failure is False

    def test_compute_state_is_active(self) -> None:
        assert ComputeState.RUNNING.is_active is True
        assert ComputeState.STARTING.is_active is True
        assert ComputeState.RESTARTING.is_active is True
        assert ComputeState.TERMINATED.is_active is False
        assert ComputeState.ERROR.is_active is False

    def test_alert_severity_requires_immediate_action(self) -> None:
        assert AlertSeverity.HIGH.requires_immediate_action is True
        assert AlertSeverity.MEDIUM.requires_immediate_action is True
        assert AlertSeverity.LOW.requires_immediate_action is False
        assert AlertSeverity.INFORMATIONAL.requires_immediate_action is False

    def test_trigger_type_unknown_is_default_sentinel(self) -> None:
        assert TriggerType.UNKNOWN == "unknown"


# ==========================================================================
# MetricPayload
# ==========================================================================


class TestMetricPayload:
    """Core transport envelope tests."""

    def test_defaults_are_populated(self, sample_payload: MetricPayload) -> None:
        assert sample_payload.schema_version == "1.2"
        assert len(sample_payload.collection_run_id) == 36  # UUID format
        assert sample_payload.collected_at.tzinfo is not None

    def test_metric_count_computed(self, sample_payload: MetricPayload) -> None:
        assert sample_payload.metric_count == 1

    def test_is_empty_false(self, sample_payload: MetricPayload) -> None:
        assert sample_payload.is_empty is False

    def test_is_empty_true(self, empty_payload: MetricPayload) -> None:
        assert empty_payload.is_empty is True
        assert empty_payload.metric_count == 0

    def test_naive_datetime_coerced_to_utc(self) -> None:
        naive_dt = datetime(2026, 3, 18, 10, 0, 0)  # no tzinfo
        payload = MetricPayload(
            source_lz_id="azure-sub-test",
            cloud_provider="azure",
            domain="pipeline",
            collected_at=naive_dt,
        )
        assert payload.collected_at.tzinfo is not None
        assert payload.collected_at.tzinfo == timezone.utc

    def test_tz_aware_datetime_unchanged(self) -> None:
        aware_dt = datetime(2026, 3, 18, 10, 0, 0, tzinfo=timezone.utc)
        payload = MetricPayload(
            source_lz_id="azure-sub-test",
            cloud_provider="azure",
            domain="pipeline",
            collected_at=aware_dt,
        )
        assert payload.collected_at == aware_dt

    def test_enum_values_serialised_as_strings(self, sample_payload: MetricPayload) -> None:
        dumped = json.loads(sample_payload.model_dump_json())
        assert dumped["cloud_provider"] == "azure"
        assert dumped["domain"] == "pipeline"

    def test_source_lz_id_whitespace_stripped(self) -> None:
        payload = MetricPayload(
            source_lz_id="  azure-sub-test  ",
            cloud_provider="azure",
            domain="pipeline",
        )
        assert payload.source_lz_id == "azure-sub-test"

    def test_repr_contains_key_fields(self, sample_payload: MetricPayload) -> None:
        r = repr(sample_payload)
        assert "MetricPayload(" in r
        assert "azure" in r
        assert "pipeline" in r
        assert "count=1" in r

    def test_payload_is_frozen(self, sample_payload: MetricPayload) -> None:
        with pytest.raises(Exception):  # ValidationError or TypeError (frozen)
            sample_payload.domain = "cluster"  # type: ignore[misc]

    def test_unique_run_ids_per_instance(self) -> None:
        p1 = MetricPayload(source_lz_id="x", cloud_provider="azure", domain="pipeline")
        p2 = MetricPayload(source_lz_id="x", cloud_provider="azure", domain="pipeline")
        assert p1.collection_run_id != p2.collection_run_id


# ==========================================================================
# PipelineMetric
# ==========================================================================


class TestPipelineMetric:
    """Pipeline execution metric model tests."""

    def test_minimal_construction(self) -> None:
        metric = PipelineMetric(
            pipeline_id="pipe-001",
            pipeline_name="ingest_daily",
            run_id="run-abc",
            status=PipelineRunStatus.SUCCEEDED,
            start_time=datetime(2026, 3, 18, 6, 0, 0, tzinfo=timezone.utc),
        )
        assert metric.pipeline_id == "pipe-001"
        assert metric.trigger_type == TriggerType.UNKNOWN
        assert metric.end_time is None
        assert metric.duration_seconds is None

    def test_duration_auto_derived_from_timestamps(self) -> None:
        start = datetime(2026, 3, 18, 6, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 18, 6, 0, 45, tzinfo=timezone.utc)  # 45 s later
        metric = PipelineMetric(
            pipeline_id="p",
            pipeline_name="p",
            run_id="r",
            status="succeeded",
            start_time=start,
            end_time=end,
        )
        assert metric.duration_seconds == pytest.approx(45.0)

    def test_explicit_duration_not_overridden(self) -> None:
        start = datetime(2026, 3, 18, 6, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 3, 18, 6, 1, 0, tzinfo=timezone.utc)
        metric = PipelineMetric(
            pipeline_id="p",
            pipeline_name="p",
            run_id="r",
            status="succeeded",
            start_time=start,
            end_time=end,
            duration_seconds=99.0,
        )
        assert metric.duration_seconds == pytest.approx(99.0)

    def test_status_stored_as_string_value(self) -> None:
        metric = PipelineMetric(
            pipeline_id="p",
            pipeline_name="p",
            run_id="r",
            status=PipelineRunStatus.FAILED,
            start_time=datetime(2026, 3, 18, tzinfo=timezone.utc),
        )
        dumped = metric.model_dump()
        assert dumped["status"] == "failed"

    def test_tags_default_empty(self) -> None:
        metric = PipelineMetric(
            pipeline_id="p",
            pipeline_name="p",
            run_id="r",
            status="running",
            start_time=datetime(2026, 3, 18, tzinfo=timezone.utc),
        )
        assert metric.tags == {}

    def test_frozen_model(self) -> None:
        metric = PipelineMetric(
            pipeline_id="p",
            pipeline_name="p",
            run_id="r",
            status="succeeded",
            start_time=datetime(2026, 3, 18, tzinfo=timezone.utc),
        )
        with pytest.raises(Exception):
            metric.pipeline_name = "other"  # type: ignore[misc]


# ==========================================================================
# ComputeMetric
# ==========================================================================


class TestComputeMetric:
    """Compute metric model tests."""

    def test_construction_with_required_fields(self) -> None:
        metric = ComputeMetric(
            compute_resource_id="0312-151347-reef123",
            resource_name="prod-etl",
            compute_type=ComputeType.DATABRICKS,
            state=ComputeState.RUNNING,
        )
        assert metric.compute_type == "databricks"  # use_enum_values
        assert metric.num_workers == 0
        assert metric.workspace_id is None

    def test_num_workers_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            ComputeMetric(
                compute_resource_id="c",
                resource_name="c",
                compute_type="databricks",
                state="running",
                num_workers=-1,
            )

    def test_estimated_cost_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            ComputeMetric(
                compute_resource_id="c",
                resource_name="c",
                compute_type="emr",
                state="running",
                estimated_hourly_cost_usd=-0.01,
            )

    def test_utilisation_pct_optional(self) -> None:
        metric = ComputeMetric(
            compute_resource_id="c",
            resource_name="c",
            compute_type="databricks",
            state="running",
            avg_cpu_utilization_pct=72.5,
            avg_mem_utilization_pct=58.3,
        )
        assert float(metric.avg_cpu_utilization_pct) == pytest.approx(72.5)
        assert float(metric.avg_mem_utilization_pct) == pytest.approx(58.3)

    def test_utilisation_pct_exceeds_100_raises(self) -> None:
        with pytest.raises(ValidationError):
            ComputeMetric(
                compute_resource_id="c",
                resource_name="c",
                compute_type="databricks",
                state="running",
                avg_cpu_utilization_pct=101.0,
            )


# ==========================================================================
# CostMetric
# ==========================================================================


class TestCostMetric:
    """Cost metric model tests."""

    def test_valid_cost_metric(self) -> None:
        metric = CostMetric(
            service_name="Azure Data Factory",
            subscription_or_account_id="fa5abbc4-02eb-416f-a75f-f8f6c5cc7d8a",
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
            cost_usd=142.75,
        )
        assert metric.currency == "USD"
        assert metric.tags == {}

    def test_period_end_before_start_raises(self) -> None:
        with pytest.raises(ValidationError, match="period_end"):
            CostMetric(
                service_name="ADF",
                subscription_or_account_id="sub-001",
                period_start=date(2026, 3, 31),
                period_end=date(2026, 3, 1),  # before start
                cost_usd=0.0,
            )

    def test_cost_negative_raises(self) -> None:
        with pytest.raises(ValidationError):
            CostMetric(
                service_name="ADF",
                subscription_or_account_id="sub-001",
                period_start=date(2026, 3, 1),
                period_end=date(2026, 3, 31),
                cost_usd=-1.0,
            )

    def test_budget_fields_optional(self) -> None:
        metric = CostMetric(
            service_name="Glue",
            subscription_or_account_id="aws-123",
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
            cost_usd=0.0,
        )
        assert metric.budget_name is None
        assert metric.budget_limit_usd is None
        assert metric.budget_consumed_pct is None


# ==========================================================================
# DatabaseMetric
# ==========================================================================


class TestDatabaseMetric:
    """Database metric model tests."""

    def test_construction_with_enum_type(self) -> None:
        metric = DatabaseMetric(
            db_id="/subscriptions/…/sqlServers/myserver",
            db_name="mydb",
            db_type=DatabaseType.SQLSERVER,
            server_name="myserver.database.windows.net",
        )
        assert metric.db_type == "sqlserver"  # use_enum_values

    def test_cpu_percent_bounds(self) -> None:
        with pytest.raises(ValidationError):
            DatabaseMetric(
                db_id="id",
                db_name="db",
                db_type="postgresql",
                server_name="srv",
                cpu_percent=101.0,  # exceeds 100
            )

    def test_is_available_defaults_true(self) -> None:
        metric = DatabaseMetric(
            db_id="id",
            db_name="db",
            db_type="mysql",
            server_name="srv",
        )
        assert metric.is_available is True


# ==========================================================================
# SecurityAlert
# ==========================================================================


class TestSecurityAlert:
    """Security alert model tests."""

    def test_status_defaults_to_active(self) -> None:
        alert = SecurityAlert(
            alert_id="alert-001",
            title="Suspicious login",
            severity=AlertSeverity.HIGH,
            detected_at=datetime(2026, 3, 18, 10, 0, 0, tzinfo=timezone.utc),
        )
        assert alert.status == "active"

    def test_enum_serialisation(self) -> None:
        alert = SecurityAlert(
            alert_id="a",
            title="t",
            severity=AlertSeverity.LOW,
            status=AlertStatus.RESOLVED,
            detected_at=datetime(2026, 3, 18, tzinfo=timezone.utc),
        )
        dumped = alert.model_dump()
        assert dumped["severity"] == "low"
        assert dumped["status"] == "resolved"

    def test_optional_fields_default_none(self) -> None:
        alert = SecurityAlert(
            alert_id="a",
            title="t",
            severity="medium",
            detected_at=datetime(2026, 3, 18, tzinfo=timezone.utc),
        )
        assert alert.description is None
        assert alert.resource_id is None
        assert alert.remediation is None
