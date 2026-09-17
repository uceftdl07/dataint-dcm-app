# Tasks: Databricks Workflows — Observabilité des runs (domaine `workflow`)

**Feature**: `009-databricks-workflows-observability` · **PR**: #135 · **Jira**: DCINT-168
**Status**: ✅ Livré (rétro-documenté 2026-07-24)
**Inputs**: [spec.md](spec.md), [plan.md](plan.md), [data-model.md](data-model.md)

> Tasks reconstruites depuis PR #135 (merge `2fa7b3f`, 30 fichiers, +2882 lignes).
> Toutes `[x]` : livrées et mergées en `develop`.

## Légende

- `[P]` = parallélisable · préfixe domaine obligatoire (`DataEng` ici).

---

## Phase 1 — Contrat (dcm-commons)

- [x] **T001** `[DataEng]` Ajouter `MetricDomain.WORKFLOW = "workflow"` — `dcm-commons/dcm_commons/models/enums.py` (l.84)
- [x] **T002** `[DataEng][P]` Ajouter enum `WorkflowRunStatus` — `enums.py` (l.251)
- [x] **T003** `[DataEng][P]` Ajouter enum `WorkflowTriggerType` — `enums.py` (l.287)
- [x] **T004** `[DataEng]` Créer modèle `WorkflowRunMetric` (24 champs + `task_failure_rate` calculé) — `dcm-commons/dcm_commons/models/workflow.py`
- [x] **T005** `[DataEng]` Bump `schema_version` `1.1 → 1.2` (additif) — `MetricPayload`
- [x] **T006** `[DataEng][P]` Fixtures JSON runs Databricks — `dcm-commons/fixtures/`
- [x] **T007** `[DataEng][P]` Tests unitaires `WorkflowRunMetric` + `task_failure_rate` — `dcm-commons/tests/`

## Phase 2 — Collecteur (dcm-azure-collector)

- [x] **T008** `[DataEng]` Implémenter `DatabricksWorkflowCollector` (`/api/2.2/jobs/runs/list?expand_tasks=true`, 1 record/run, runs en cours inclus, zéro agrégat) — `azure_collector/collectors/databricks_workflows.py` (673 l.)
- [x] **T009** `[DataEng]` Mapping run → `WorkflowRunMetric` (FR-011 : absent ⇒ `None`)
- [x] **T010** `[DataEng]` Enregistrer le collecteur dans l'orchestration (config domaine `workflow`)
- [x] **T011** `[DataEng][P]` Tests collecteur (mock API `runs/list`, tasks expand, run en cours)

## Phase 3 — RAW (dlt_01)

- [x] **T012** `[DataEng]` Autoriser le domaine `workflow` en RAW — `pipelines/dlt_01_raw_layer.py`

## Phase 4 — CURATED (dlt_02)

- [x] **T013** `[DataEng]` Vue staging `_stg_dbx_workflow` + `_stg_dbx_workflow_valid` (DQ) — `pipelines/dlt_02_curated_layer.py` §9
- [x] **T014** `[DataEng]` Table `curated_dbx_workflow_runs` MERGE SCD1 clé `(workflow_id, run_id, source_lz_id)` (idempotence runs en cours)
- [x] **T015** `[DataEng][P]` Table `curated_dbx_workflow_runs_rejects` (DQ capture)

## Phase 5 — GOLD (dlt_03) — 5 agrégats

- [x] **T016** `[DataEng]` `gold_dbx_workflow_success_rate` (24h / 7d)
- [x] **T017** `[DataEng][P]` `gold_dbx_workflow_duration_percentiles` (p50/p95/p99)
- [x] **T018** `[DataEng][P]` `gold_dbx_workflow_duration_drift` (baseline mobile 14 j)
- [x] **T019** `[DataEng][P]` `gold_dbx_workflow_task_failure_rate`
- [x] **T020** `[DataEng]` `gold_dbx_workflow_concurrency_1min` (recouvrement d'intervalles, run en cours prolongé à `current_timestamp()`)

## Phase 5b — GOLD drill-down (addendum) — 2 tables détail

- [x] **T024** `[DataEng]` `gold_dbx_workflow_runs` (grain run, projection `curated_dbx_workflow_runs`, PK `(source_lz_id, workspace_id, workflow_id, run_id)`) — expose `run_id` pour drill-down UI
- [x] **T025** `[DataEng][P]` `gold_dbx_workflow_tasks` (grain tâche, projection `curated_dbx_workflow_task_runs`, PK `(source_lz_id, workspace_id, workflow_id, run_id, task_id)`) — expose `task_id`

## Phase 6 — Tests & qualité

- [x] **T021** `[DataEng]` Tests DLT curated (dédup MERGE, rejects)
- [x] **T022** `[DataEng][P]` Tests DLT gold (fixtures durées/statuts connus → KPI attendus)
- [x] **T023** `[DataEng]` Ruff zéro warning + non-régression domaines existants (SC-004/SC-005)

---

## Dépendances

- Phase 1 (contrat) → bloque Phases 2-5.
- T013 → T014 → T015.
- T014 → T016..T020 (GOLD lit curated).
- T024 → dépend de T014 (`curated_dbx_workflow_runs`).
- T025 → dépend de la table task-grain `curated_dbx_workflow_task_runs` (epic 009 addendum).

## Traçabilité tables ↔ tasks

| Table | Task | data-model.md |
|-------|------|---------------|
| `curated_dbx_workflow_runs` | T014 | §CURATED |
| `curated_dbx_workflow_runs_rejects` | T015 | §DQ |
| `gold_dbx_workflow_success_rate` | T016 | §GOLD |
| `gold_dbx_workflow_duration_percentiles` | T017 | §GOLD |
| `gold_dbx_workflow_duration_drift` | T018 | §GOLD |
| `gold_dbx_workflow_task_failure_rate` | T019 | §GOLD |
| `gold_dbx_workflow_concurrency_1min` | T020 | §GOLD |
| `gold_dbx_workflow_runs` | T024 | §3.6 |
| `gold_dbx_workflow_tasks` | T025 | §3.7 |
