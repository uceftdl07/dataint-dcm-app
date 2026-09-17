"""Validation tests for the JSON fixture files in fixtures/.

Each fixture is a serialised ``MetricPayload`` that the Lambda ingestion
function would receive from APIGEE.  These tests ensure:

1. Every fixture round-trips through ``MetricPayload.model_validate_json()``
   without errors (schema conformance).
2. Envelope fields are coherent (schema_version, cloud_provider, domain,
   metric_count, is_empty).
3. Domain-specific spot-checks verify key field names and enum values match
   Sprint 7 renames (compute_resource_id, check_state, …).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dcm_commons.models.payload import MetricPayload

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load(filename: str) -> MetricPayload:
    """Parse a fixture file into a MetricPayload."""
    raw = (FIXTURES_DIR / filename).read_text(encoding="utf-8")
    return MetricPayload.model_validate_json(raw)


def _raw(filename: str) -> dict:
    """Return the fixture as a plain dict (for field-level assertions)."""
    return json.loads((FIXTURES_DIR / filename).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Parametrised round-trip test — all 12 fixtures must parse without error
# ---------------------------------------------------------------------------

FIXTURE_FILES = [
    "pipeline_azure_failed.json",
    "pipeline_azure_running.json",
    "pipeline_aws_succeeded.json",
    "compute_azure.json",
    "compute_aws.json",
    "cost_azure.json",
    "cost_aws.json",
    "database_azure.json",
    "security_azure.json",
    "user_azure.json",
    "activity_run_azure.json",
    "standard_check_azure.json",
]


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_fixture_parses(filename: str) -> None:
    """Every fixture must deserialise into a valid MetricPayload."""
    payload = _load(filename)
    assert payload.schema_version == "1.1"
    assert len(payload.collection_run_id) == 36  # UUID
    assert payload.collected_at.tzinfo is not None
    assert payload.metric_count == len(payload.metrics)


@pytest.mark.parametrize("filename", FIXTURE_FILES)
def test_fixture_not_empty(filename: str) -> None:
    """All fixtures must contain at least one metric."""
    payload = _load(filename)
    assert not payload.is_empty
    assert payload.metric_count >= 1


# ---------------------------------------------------------------------------
# Envelope coherence per fixture
# ---------------------------------------------------------------------------


class TestPipelineAzureFailed:
    def test_envelope(self) -> None:
        p = _load("pipeline_azure_failed.json")
        assert p.cloud_provider == "azure"
        assert p.domain == "pipeline"
        assert p.source_lz_id == "lz-azure-prod"

    def test_metric_fields(self) -> None:
        data = _raw("pipeline_azure_failed.json")
        metric = data["metrics"][0]
        assert metric["status"] == "failed"
        assert metric["trigger_type"] == "scheduled"
        assert "error_message" in metric
        assert metric["factory_name"] == "adf-prod"


class TestPipelineAzureRunning:
    def test_envelope(self) -> None:
        p = _load("pipeline_azure_running.json")
        assert p.domain == "pipeline"
        assert p.cloud_provider == "azure"

    def test_no_end_time(self) -> None:
        data = _raw("pipeline_azure_running.json")
        metric = data["metrics"][0]
        assert metric["status"] == "running"
        assert metric["end_time"] is None


class TestPipelineAwsSucceeded:
    def test_envelope(self) -> None:
        p = _load("pipeline_aws_succeeded.json")
        assert p.cloud_provider == "aws"
        assert p.domain == "pipeline"

    def test_glue_fields(self) -> None:
        data = _raw("pipeline_aws_succeeded.json")
        metric = data["metrics"][0]
        assert metric["status"] == "succeeded"
        assert "glue_job_name" in metric
        assert metric["duration_seconds"] > 0


class TestComputeAzure:
    def test_envelope(self) -> None:
        p = _load("compute_azure.json")
        assert p.domain == "compute"          # Sprint 7 rename
        assert p.cloud_provider == "azure"

    def test_sprint7_field_names(self) -> None:
        """Verify Sprint 7 renamed fields — not the old cluster_id / cluster_name."""
        data = _raw("compute_azure.json")
        metric = data["metrics"][0]
        assert "compute_resource_id" in metric   # was cluster_id
        assert "resource_name" in metric         # was cluster_name
        assert "compute_type" in metric          # was cluster_type
        assert "cluster_id" not in metric
        assert "cluster_name" not in metric

    def test_new_utilisation_columns(self) -> None:
        data = _raw("compute_azure.json")
        metric = data["metrics"][0]
        assert "avg_cpu_utilization_pct" in metric
        assert "avg_mem_utilization_pct" in metric
        assert float(metric["avg_cpu_utilization_pct"]) > 0
        assert float(metric["avg_mem_utilization_pct"]) > 0

    def test_databricks_fields(self) -> None:
        data = _raw("compute_azure.json")
        metric = data["metrics"][0]
        assert metric["compute_type"] == "databricks"
        assert metric["state"] == "running"
        assert metric["workspace_id"] is not None


class TestComputeAws:
    def test_envelope(self) -> None:
        p = _load("compute_aws.json")
        assert p.domain == "compute"
        assert p.cloud_provider == "aws"

    def test_emr_fields(self) -> None:
        data = _raw("compute_aws.json")
        metric = data["metrics"][0]
        assert metric["compute_type"] == "emr"
        assert metric["workspace_id"] is None   # EMR has no workspace


class TestCostAzure:
    def test_envelope(self) -> None:
        p = _load("cost_azure.json")
        assert p.domain == "cost"
        assert p.metric_count == 2

    def test_budget_fields_present(self) -> None:
        data = _raw("cost_azure.json")
        for metric in data["metrics"]:
            assert metric["cost_usd"] > 0
            assert "budget_consumed_pct" in metric


class TestCostAws:
    def test_envelope(self) -> None:
        p = _load("cost_aws.json")
        assert p.cloud_provider == "aws"
        assert p.domain == "cost"
        assert p.metric_count == 2


class TestDatabaseAzure:
    def test_envelope(self) -> None:
        p = _load("database_azure.json")
        assert p.domain == "database"

    def test_metrics(self) -> None:
        data = _raw("database_azure.json")
        metric = data["metrics"][0]
        assert metric["db_type"] == "sqlserver"
        assert metric["is_available"] is True
        assert metric["cpu_percent"] is not None
        assert metric["dtus_used"] is not None


class TestSecurityAzure:
    def test_envelope(self) -> None:
        p = _load("security_azure.json")
        assert p.domain == "security"
        assert p.cloud_provider == "azure"

    def test_alert_fields(self) -> None:
        data = _raw("security_azure.json")
        metric = data["metrics"][0]
        assert metric["severity"] == "high"
        assert metric["status"] == "active"
        assert metric["compromised_entity"] is not None


class TestUserAzure:
    def test_envelope(self) -> None:
        p = _load("user_azure.json")
        assert p.domain == "user"

    def test_user_fields(self) -> None:
        data = _raw("user_azure.json")
        metric = data["metrics"][0]
        assert metric["user_type"] == "databricks"
        assert metric["is_active"] is True
        assert len(metric["groups"]) > 0
        assert metric["last_activity_at"] is not None


class TestActivityRunAzure:
    def test_envelope(self) -> None:
        p = _load("activity_run_azure.json")
        assert p.domain == "activity_run"
        assert p.metric_count == 2

    def test_copy_activity_has_row_counts(self) -> None:
        data = _raw("activity_run_azure.json")
        copy_act = next(m for m in data["metrics"] if m["activity_type"] == "copy")
        assert copy_act["rows_read"] == 2_450_000
        assert copy_act["rows_written"] == 2_450_000
        assert copy_act["status"] == "succeeded"

    def test_notebook_activity_failed(self) -> None:
        data = _raw("activity_run_azure.json")
        nb_act = next(m for m in data["metrics"] if m["activity_type"] == "databricks_notebook")
        assert nb_act["status"] == "failed"
        assert nb_act["error_message"] is not None

    def test_durations_computed(self) -> None:
        data = _raw("activity_run_azure.json")
        for metric in data["metrics"]:
            assert metric["duration_seconds"] is not None
            assert metric["duration_seconds"] > 0


class TestStandardCheckAzure:
    def test_envelope(self) -> None:
        p = _load("standard_check_azure.json")
        assert p.domain == "standard_check"   # Sprint 7 rename (was compliance)
        assert p.metric_count == 2

    def test_sprint7_field_names(self) -> None:
        """Verify Sprint 7 renamed fields — not the old policy_id / compliance_state."""
        data = _raw("standard_check_azure.json")
        for metric in data["metrics"]:
            assert "check_id" in metric          # was policy_id
            assert "check_name" in metric        # was policy_name
            assert "check_state" in metric       # was compliance_state
            assert "check_effect" in metric      # was effect
            assert "non_check_reasons" in metric # was non_compliance_reasons
            assert "policy_id" not in metric
            assert "compliance_state" not in metric

    def test_both_states_present(self) -> None:
        data = _raw("standard_check_azure.json")
        states = {m["check_state"] for m in data["metrics"]}
        assert "non_compliant" in states
        assert "compliant" in states
