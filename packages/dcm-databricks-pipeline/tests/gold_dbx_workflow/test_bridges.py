"""Tests de `pipelines.gold_dbx_workflow.bridges` (vues-pont run/tache).

Assertion CENTRALE de cette suite (demande explicite du produit, cf.
`pipelines/gold_dbx_workflow/__init__.py`) : les deux vues-pont ne lisent
JAMAIS `curated_dbx_workflow_runs`/`curated_dbx_workflow_task_runs`
(collecteur JSON), uniquement `curated_dbx_lakeflow_*` (system tables) et
`dim_dbx_workspace`.
"""

from __future__ import annotations

from types import SimpleNamespace

from .conftest import _RecordingFrame

_JOB_RUN_TIMELINE = "curated_dbx_lakeflow_job_run_timeline"
_JOB_TASK_RUN_TIMELINE = "curated_dbx_lakeflow_job_task_run_timeline"
_JOBS = "curated_dbx_lakeflow_jobs"
_DIM_WORKSPACE = "dim_dbx_workspace"

_FORBIDDEN_SOURCES = ("curated_dbx_workflow_runs", "curated_dbx_workflow_task_runs")


def test_wf_task_runs_bridge_reads_only_lakeflow_system_tables(bridges_module) -> None:
    mod, spark, reads = bridges_module
    mod.build_wf_task_runs_bridge(
        spark,
        job_task_run_timeline_table=_JOB_TASK_RUN_TIMELINE,
        jobs_table=_JOBS,
        job_run_timeline_table=_JOB_RUN_TIMELINE,
    )
    assert _JOB_TASK_RUN_TIMELINE in reads
    assert _JOBS in reads
    assert _JOB_RUN_TIMELINE in reads  # _lakeflow_submit_run_names
    for forbidden in _FORBIDDEN_SOURCES:
        assert forbidden not in reads


def test_wf_runs_bridge_reads_only_lakeflow_system_tables_and_dim_workspace(
    bridges_module,
) -> None:
    mod, spark, reads = bridges_module
    task_runs_bridge = mod.build_wf_task_runs_bridge(
        spark,
        job_task_run_timeline_table=_JOB_TASK_RUN_TIMELINE,
        jobs_table=_JOBS,
        job_run_timeline_table=_JOB_RUN_TIMELINE,
    )
    reads.clear()
    mod.build_wf_runs_bridge(
        spark,
        job_run_timeline_table=_JOB_RUN_TIMELINE,
        jobs_table=_JOBS,
        dim_dbx_workspace_table=_DIM_WORKSPACE,
        task_runs_bridge=task_runs_bridge,
    )
    assert _JOB_RUN_TIMELINE in reads
    assert _JOBS in reads
    assert _DIM_WORKSPACE in reads
    for forbidden in _FORBIDDEN_SOURCES:
        assert forbidden not in reads


def test_wf_runs_bridge_does_not_reread_task_runs_bridge(bridges_module) -> None:
    # `_wf_runs_bridge` de la version DLT appelait `dlt.read("_wf_task_runs_bridge")`
    # (lecture intra-graphe). Le portage remplace cet appel par un parametre
    # `task_runs_bridge` deja calcule par l'appelant : `build_wf_runs_bridge` ne
    # doit donc JAMAIS relire `curated_dbx_lakeflow_job_task_run_timeline`
    # lui-meme (seul `build_wf_task_runs_bridge` le fait).
    mod, spark, reads = bridges_module
    task_runs_bridge = mod.build_wf_task_runs_bridge(
        spark,
        job_task_run_timeline_table=_JOB_TASK_RUN_TIMELINE,
        jobs_table=_JOBS,
        job_run_timeline_table=_JOB_RUN_TIMELINE,
    )
    reads.clear()
    mod.build_wf_runs_bridge(
        spark,
        job_run_timeline_table=_JOB_RUN_TIMELINE,
        jobs_table=_JOBS,
        dim_dbx_workspace_table=_DIM_WORKSPACE,
        task_runs_bridge=task_runs_bridge,
    )
    assert _JOB_TASK_RUN_TIMELINE not in reads


def test_run_page_url_sql_builds_deep_link_from_workspace_url(bridges_module) -> None:
    mod, _spark, _reads = bridges_module
    sql = mod._run_page_url_sql()
    assert "_workspace_url" in sql
    assert "'https://', workspace_id" not in sql
    assert "'/?o=', workspace_id, '#job/', job_id, '/run/', run_id" in sql


# ---------------------------------------------------------------------------
# Tests portes de `tests/test_dlt_03_gold_layer.py` (migration T002) : verifient
# les REGLES de calcul (agregats, coalesce, jointures, schema de sortie) des
# vues-pont, pas seulement "quelle table est lue". Le fixture `wf_recording_fakes`
# fournit un `_FakeSparkSession`/`_RecordingFrame` capable de rendre en texte
# chaque expression, condition et colonne ajoutee -- exactement le style de
# l'ancienne suite DLT (memes assertions), adapte a la signature explicite
# `build_wf_runs_bridge(spark, ..., task_runs_bridge=...)` du portage (plus de
# `dlt.read("_wf_task_runs_bridge")`).
# ---------------------------------------------------------------------------


def test_wf_runs_bridge_aggregates_run_name_without_reading_the_timeline_twice(
    wf_recording_fakes: SimpleNamespace,
) -> None:
    # `runs_agg` groupe DEJA la table qui porte `run_name` au grain run : le nom
    # sort de son `.agg()`, aucune jointure ni relecture supplementaire (chemin
    # le moins couteux, contrairement a `build_wf_task_runs_bridge`).
    mod, spark = wf_recording_fakes.module, wf_recording_fakes.spark
    mod.build_wf_runs_bridge(
        spark,
        job_run_timeline_table=_JOB_RUN_TIMELINE,
        jobs_table=_JOBS,
        dim_dbx_workspace_table=_DIM_WORKSPACE,
        task_runs_bridge=_RecordingFrame("task_runs_bridge_stub"),
    )
    timeline = spark.only_read_of(_JOB_RUN_TIMELINE)
    assert any("run_name" in aggregation for aggregation in timeline.aggregations)


def test_wf_runs_bridge_workflow_name_falls_back_to_the_submitted_run_name(
    wf_recording_fakes: SimpleNamespace,
) -> None:
    mod, spark = wf_recording_fakes.module, wf_recording_fakes.spark
    runs = mod.build_wf_runs_bridge(
        spark,
        job_run_timeline_table=_JOB_RUN_TIMELINE,
        jobs_table=_JOBS,
        dim_dbx_workspace_table=_DIM_WORKSPACE,
        task_runs_bridge=_RecordingFrame("task_runs_bridge_stub"),
    )
    workflow_name = dict(runs.added_columns)["workflow_name"]
    assert workflow_name.startswith("coalesce(")
    assert "col(workflow_name)" in workflow_name
    assert "col(run_name)" in workflow_name


def test_wf_runs_bridge_does_not_leak_run_name_into_the_view_schema(
    wf_recording_fakes: SimpleNamespace,
) -> None:
    # `run_name` est un intermediaire de resolution : le laisser sortir ajouterait
    # une colonne au schema de la vue, donc aux 6 gold qui la consomment.
    mod, spark = wf_recording_fakes.module, wf_recording_fakes.spark
    runs = mod.build_wf_runs_bridge(
        spark,
        job_run_timeline_table=_JOB_RUN_TIMELINE,
        jobs_table=_JOBS,
        dim_dbx_workspace_table=_DIM_WORKSPACE,
        task_runs_bridge=_RecordingFrame("task_runs_bridge_stub"),
    )
    assert runs.selected
    assert all("run_name" not in column for column in runs.selected)


def test_wf_task_runs_bridge_reads_run_name_from_the_run_timeline_not_the_task_one(
    wf_recording_fakes: SimpleNamespace,
) -> None:
    # `curated_dbx_lakeflow_job_task_run_timeline` NE PORTE PAS `run_name` (la
    # table systeme l'expose, le spec curated ne la selectionne pas) : le repli
    # passe donc par une lecture de `job_run_timeline`, au grain job.
    mod, spark = wf_recording_fakes.module, wf_recording_fakes.spark
    tasks = mod.build_wf_task_runs_bridge(
        spark,
        job_task_run_timeline_table=_JOB_TASK_RUN_TIMELINE,
        jobs_table=_JOBS,
        job_run_timeline_table=_JOB_RUN_TIMELINE,
    )
    assert spark.reads_of(_JOB_RUN_TIMELINE)
    joined = [name for name, _, _ in tasks.joined]
    assert any(_JOB_RUN_TIMELINE in name for name in joined)
    assert all(how == "left" for _, _, how in tasks.joined)


def test_wf_task_runs_bridge_workflow_name_falls_back_to_the_submitted_run_name(
    wf_recording_fakes: SimpleNamespace,
) -> None:
    mod, spark = wf_recording_fakes.module, wf_recording_fakes.spark
    tasks = mod.build_wf_task_runs_bridge(
        spark,
        job_task_run_timeline_table=_JOB_TASK_RUN_TIMELINE,
        jobs_table=_JOBS,
        job_run_timeline_table=_JOB_RUN_TIMELINE,
    )
    workflow_name = dict(tasks.added_columns)["workflow_name"]
    assert workflow_name.startswith("coalesce(")
    assert "col(workflow_name)" in workflow_name
    assert "col(run_name)" in workflow_name
    assert all("run_name" not in column for column in tasks.selected)


def test_lakeflow_submit_run_names_is_deduplicated_to_one_row_per_job(
    wf_recording_fakes: SimpleNamespace,
) -> None:
    # GARDE ANTI-FAN-OUT : meme famille de tables que le fan-out x43 documente
    # dans `_latest_jobs()`. La mesure donne 1 seul `run_name` par `job_id`, mais
    # 2 `job_id` portent 2 `run_id` : sans agregation au grain job, ces deux-la
    # dupliqueraient chaque tache jointe.
    mod, spark = wf_recording_fakes.module, wf_recording_fakes.spark
    names = mod._submit_run_names(spark, _JOB_RUN_TIMELINE)
    assert names.grouped_by == [
        "col(cloud_provider)",
        "col(account_id)",
        "col(workspace_id)",
        "col(job_id)",
    ]
    assert any("run_name" in aggregation for aggregation in names.aggregations)
    assert any("col(run_name) IS NOT NULL" in condition for condition in names.filters)


def test_wf_bridges_never_predicate_on_run_type(wf_recording_fakes: SimpleNamespace) -> None:
    # La disjonction mesuree rend le coalesce suffisant : un
    # `CASE WHEN run_type = 'SUBMIT_RUN'` serait une fausse precision, et se
    # perimerait au prochain type de run ajoute par Databricks. `run_type` reste
    # une colonne TRANSPORTEE (agregat + schema de sortie), jamais un predicat.
    mod, spark = wf_recording_fakes.module, wf_recording_fakes.spark
    tasks = mod.build_wf_task_runs_bridge(
        spark,
        job_task_run_timeline_table=_JOB_TASK_RUN_TIMELINE,
        jobs_table=_JOBS,
        job_run_timeline_table=_JOB_RUN_TIMELINE,
    )
    runs = mod.build_wf_runs_bridge(
        spark,
        job_run_timeline_table=_JOB_RUN_TIMELINE,
        jobs_table=_JOBS,
        dim_dbx_workspace_table=_DIM_WORKSPACE,
        task_runs_bridge=tasks,
    )
    for bridge in (runs, tasks):
        assert all("run_type" not in condition for condition in bridge.filters)
        assert all("run_type" not in value for _, value in bridge.added_columns)
