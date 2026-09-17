"""Tests de `pipelines.gold_dbx_workflow.specs` (registre des 8 tables gold).

Aucun stub pyspark necessaire : `specs.py` ne fait aucun appel `pyspark.sql.
functions`, uniquement des dataclasses et des tuples de chaines.
"""

from __future__ import annotations

from pipelines.gold_dbx_workflow.specs import GOLD_SPECS, SOURCE_TABLES

_FORBIDDEN_SOURCES = ("curated_dbx_workflow_runs", "curated_dbx_workflow_task_runs")

_EXPECTED_TABLES = {
    "success_rate",
    "duration_percentiles",
    "duration_drift",
    "task_failure_rate",
    "concurrency_1min",
    "task_health",
    "runs",
    "tasks",
    "never_run",
}


def test_gold_specs_registers_exactly_the_nine_workflow_tables() -> None:
    assert set(GOLD_SPECS) == _EXPECTED_TABLES


def test_gold_specs_never_reference_collector_source_tables() -> None:
    for forbidden in _FORBIDDEN_SOURCES:
        assert forbidden not in SOURCE_TABLES
        for spec in GOLD_SPECS.values():
            assert forbidden not in spec.source_tables


def test_all_workflow_specs_are_full_recompute_snapshots() -> None:
    # Comme les `@dlt.table` d'origine (jamais de fenetre incrementale sur ce
    # domaine) : toutes les specs doivent rester `watermark_column=None`.
    for table_name, spec in GOLD_SPECS.items():
        assert spec.watermark_column is None, table_name
        assert spec.absent_row_delete_guard is not None, table_name
