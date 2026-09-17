"""Tests de `pipelines.gold_dbx_workflow.never_run` (jobs sans run observe).

Meme strategie que `test_builders.py` : le stub `wf_fakes` remplace
`pyspark.sql.functions`/`Window` et enregistre les tables lues via
`spark.read.table(...)`, sans JVM.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace

_JOB_RUN_TIMELINE = "curated_dbx_lakeflow_job_run_timeline"
_JOBS = "curated_dbx_lakeflow_jobs"
_DIM_WORKSPACE = "dim_dbx_workspace"
_JOB_TASK_RUN_TIMELINE = "curated_dbx_lakeflow_job_task_run_timeline"

_FORBIDDEN_SOURCES = ("curated_dbx_workflow_runs", "curated_dbx_workflow_task_runs")


def test_never_run_reads_only_jobs_and_job_run_timeline(
    wf_fakes: tuple[SimpleNamespace, list[str]],
) -> None:
    spark, reads = wf_fakes
    mod = importlib.import_module("pipelines.gold_dbx_workflow.never_run")
    mod.build_never_run(
        spark,
        jobs_table=_JOBS,
        job_run_timeline_table=_JOB_RUN_TIMELINE,
    )
    assert _JOBS in reads
    assert _JOB_RUN_TIMELINE in reads
    # Pas de calcul de duree/statut ici : aucune dependance sur les taches ni
    # sur le nom du workspace.
    assert _JOB_TASK_RUN_TIMELINE not in reads
    assert _DIM_WORKSPACE not in reads
    for forbidden in _FORBIDDEN_SOURCES:
        assert forbidden not in reads
