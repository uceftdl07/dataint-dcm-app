# T003 — Teardown collecteur `workflow` (PR destructive post-gate)

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline, packages/dcm-azure-collector, packages/dcm-commons
**Branch**: dataeng/013-teardown-workflow-collector
**Jira**: [DCINT-241](https://tdf.atlassian.net/browse/DCINT-241)
**Depends on**: T002 (et passage du gate)
**Work type**: technique

## Description

Supprimer l'ancien flux `workflow` alimenté par le collecteur, **uniquement après validation du gate T002** (accord PO consigné). PR **destructive** isolée : retrait du domaine `'workflow'` de la couche raw/curated DLT collecteur, suppression du `DatabricksWorkflowCollector`, des modèles `WorkflowRunMetric`/`WorkflowTaskRun` et des enums `MetricDomain.WORKFLOW`/`WorkflowRunStatus`/`WorkflowTriggerType` (mapping désormais 100 % SQL dans les vues-pont — clarif. Q4).

## Files to create/modify

- UPDATE packages/dcm-databricks-pipeline/pipelines/dlt_01_raw_layer.py — retirer `'workflow'` de `valid_domain`
- UPDATE packages/dcm-databricks-pipeline/pipelines/dlt_02_curated_layer.py — supprimer §9 (`_stg_dbx_workflow*`, `curated_dbx_workflow_runs`/`_task_runs`, tables `_rejects`)
- DELETE packages/dcm-azure-collector/azure_collector/collectors/databricks_workflows.py
- UPDATE packages/dcm-azure-collector/azure_collector/collectors/__init__.py — retrait import/export `DatabricksWorkflowCollector`
- UPDATE packages/dcm-azure-collector/azure_collector/main.py — retrait entrée `"databricks_workflows"` + import
- UPDATE packages/dcm-azure-collector/azure_collector/config.py — retrait `"databricks_workflows"`
- UPDATE packages/dcm-azure-collector/.github/azure-collector-deploy-targets.json — retrait `databricks_workflows` de `enabled_collectors` (dev + prod)
- DELETE packages/dcm-azure-collector/tests/test_databricks_workflows_collector.py
- DELETE packages/dcm-commons/dcm_commons/models/workflow.py
- UPDATE packages/dcm-commons/dcm_commons/models/__init__.py — retrait imports/exports `WorkflowRunMetric`/`WorkflowTaskRun`
- UPDATE packages/dcm-commons/dcm_commons/models/enums.py — suppression `MetricDomain.WORKFLOW`, `WorkflowRunStatus`, `WorkflowTriggerType`
- DELETE packages/dcm-commons/tests/test_workflow.py
- UPDATE Azure-Collector-End2End-Lineage.md — retrait de la chaîne collecteur `workflow`

## Acceptance Criteria

- [ ] **Gate T002 validé** (accord PO consigné) — condition de démarrage.
- [ ] `curated_dbx_workflow_runs`/`_task_runs` sont désormais produites par les vues-pont (T002), plus par le collecteur — vérifié avant suppression §9.
- [ ] Aucune référence résiduelle à `DatabricksWorkflowCollector`, `WorkflowRunMetric`, `WorkflowTaskRun`, `MetricDomain.WORKFLOW`, `WorkflowRunStatus`, `WorkflowTriggerType` (grep clean sur tout le repo).
- [ ] `enabled_collectors` (dev+prod) ne contient plus `databricks_workflows`.
- [ ] Suites de tests des 3 packages vertes après suppression (aucun import cassé).
- [ ] ruff + mypy zéro warning.

## Tests

- `pytest packages/dcm-azure-collector/tests -q && pytest packages/dcm-commons/tests -q && pytest packages/dcm-databricks-pipeline/tests -q`
- `grep -r "DatabricksWorkflowCollector\|WorkflowRunMetric\|MetricDomain.WORKFLOW" packages/` → 0 résultat

## Out of scope

- Décommission infra collecteur (App Service / ACI) — suivi séparé (Étape 8 spike).
- NULL-safety back/front (T004/T005).

## Before PR

- [ ] Gate T002 validé (bloquant)
- [ ] Rebased/merged latest develop before PR
- [ ] Tests des 3 packages pass ; grep clean
- [ ] Diff = suppressions cohérentes (aucun code mort laissé)
- [ ] Sub-spec checkboxes reviewed
- [ ] Jira Story lists **Git branch** name

## Notes

- PR **destructive séparée** (clarif. Q2 — 2 temps) : ne jamais fusionner avec T002.
- Réf. étapes exactes : [migration_steps.md §B Étapes 4→6+8](../../../docs/spike/migration_from_collector_to_sys_table/migration_steps.md).
