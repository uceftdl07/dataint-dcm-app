"""Tests des 8 builders `pipelines.gold_dbx_workflow.*` (dispatch des sources).

Chaque builder doit lire les tables `curated_dbx_lakeflow_*`/`dim_dbx_workspace`
transmises (via les vues-pont) et JAMAIS `curated_dbx_workflow_runs`/
`curated_dbx_workflow_task_runs` (collecteur JSON, hors scope) -- meme
assertion centrale que `test_bridges.py`, verifiee ici bout-en-bout depuis
l'entree publique de chaque table gold.
"""

from __future__ import annotations

import importlib

import pytest

_JOB_RUN_TIMELINE = "curated_dbx_lakeflow_job_run_timeline"
_JOB_TASK_RUN_TIMELINE = "curated_dbx_lakeflow_job_task_run_timeline"
_JOBS = "curated_dbx_lakeflow_jobs"
_DIM_WORKSPACE = "dim_dbx_workspace"

_FORBIDDEN_SOURCES = ("curated_dbx_workflow_runs", "curated_dbx_workflow_task_runs")

# (module, build_fn_name, needs_dim_workspace)
_RUN_GRAIN_BUILDERS = [
    ("pipelines.gold_dbx_workflow.success_rate", "build_success_rate"),
    ("pipelines.gold_dbx_workflow.duration_percentiles", "build_duration_percentiles"),
    ("pipelines.gold_dbx_workflow.duration_drift", "build_duration_drift"),
    ("pipelines.gold_dbx_workflow.task_failure_rate", "build_task_failure_rate"),
    ("pipelines.gold_dbx_workflow.concurrency_1min", "build_concurrency_1min"),
    ("pipelines.gold_dbx_workflow.runs", "build_runs"),
]

_TASK_GRAIN_BUILDERS = [
    ("pipelines.gold_dbx_workflow.task_health", "build_task_health"),
    ("pipelines.gold_dbx_workflow.tasks", "build_tasks"),
]


@pytest.mark.parametrize("module_name, fn_name", _RUN_GRAIN_BUILDERS)
def test_run_grain_builder_reads_only_lakeflow_and_dim_workspace(
    wf_fakes, module_name: str, fn_name: str
) -> None:
    spark, reads = wf_fakes
    mod = importlib.import_module(module_name)
    build_fn = getattr(mod, fn_name)
    build_fn(
        spark,
        job_run_timeline_table=_JOB_RUN_TIMELINE,
        job_task_run_timeline_table=_JOB_TASK_RUN_TIMELINE,
        jobs_table=_JOBS,
        dim_dbx_workspace_table=_DIM_WORKSPACE,
    )
    assert _JOB_RUN_TIMELINE in reads
    assert _JOB_TASK_RUN_TIMELINE in reads
    assert _JOBS in reads
    assert _DIM_WORKSPACE in reads
    for forbidden in _FORBIDDEN_SOURCES:
        assert forbidden not in reads


@pytest.mark.parametrize("module_name, fn_name", _TASK_GRAIN_BUILDERS)
def test_task_grain_builder_reads_only_lakeflow_tables(
    wf_fakes, module_name: str, fn_name: str
) -> None:
    spark, reads = wf_fakes
    mod = importlib.import_module(module_name)
    build_fn = getattr(mod, fn_name)
    build_fn(
        spark,
        job_run_timeline_table=_JOB_RUN_TIMELINE,
        job_task_run_timeline_table=_JOB_TASK_RUN_TIMELINE,
        jobs_table=_JOBS,
    )
    assert _JOB_TASK_RUN_TIMELINE in reads
    assert _JOBS in reads
    assert _JOB_RUN_TIMELINE in reads  # _lakeflow_submit_run_names
    assert _DIM_WORKSPACE not in reads  # pas de jointure workspace au grain tache
    for forbidden in _FORBIDDEN_SOURCES:
        assert forbidden not in reads
