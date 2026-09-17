# Feature Specification: Databricks Workflows — Observabilité des runs (domaine `workflow`)

**Feature Branch**: `009-databricks-workflows-observability`
**PR**: #135 (`Feature/dcint 168`, merge `2fa7b3f`) — Jira DCINT-168
**Created**: 2026-06-22 · **Documented**: 2026-07-24 (spec rédigée a posteriori)
**Status**: Livré (code mergé en `develop`)
**Input**: `specs/009-databricks-workflows-observability/plan.md`, `data-model.md`, code PR #135

> Spec reconstruite après livraison : le code a été développé sur PR #135 avant la rédaction spec-kit.
> Le détail table-par-table / colonne-par-colonne est dans [data-model.md](data-model.md).

---

## Compréhension du besoin

### Objectif métier

Fournir aux équipes Data une **observabilité fine des Workflows Databricks** (Jobs & Pipelines) exécutés dans les Landing Zones Azure : taux de succès, durées et percentiles, dérive de performance, échecs au niveau tâche, et concurrence des runs — le tout aligné sur le contrat DCM existant (collecteur → Apigee → Lambda → SQS → Volume → DLT → tables `curated_*`/`gold_*` lues par le backend).

### Pourquoi un domaine dédié `workflow`

Le domaine `pipeline` (`PipelineMetric`) est **partagé** par ADF, Glue et EMR. Y ajouter les champs spécifiques Databricks (`tasks_total`, `tasks_failed`, `schedule_lag_seconds`, `retry_count`, `cluster_instance_id`…) polluerait le modèle et ses agrégats. Le domaine `workflow` **isole** le cycle de vie complet d'un run Databricks (convention de nommage `dbx_` sur les tables).

### Décisions structurantes

| # | Décision | Détail |
|---|---|---|
| D1 | Nouveau modèle `WorkflowRunMetric` | à côté de `PipelineMetric`, aucune modification du contrat existant |
| D2 | `schema_version` bump `1.1 → 1.2` | additif, rétrocompatible |
| D3 | Zéro agrégat côté collecteur | tous les KPI calculés en GOLD (clarification epic) |
| D4 | Préfixe `dbx_` sur les tables | distingue Databricks Workflows des pipelines ADF |
| D5 | FR-011 respectée | source absente ⇒ `None`/`NULL`, jamais `0` non daté |

---

## Périmètre

### Dans le périmètre (livré PR #135)

- **Collecteur** : `DatabricksWorkflowCollector` (`/api/2.2/jobs/runs/list?expand_tasks=true`), émet 1 record par run (dont runs en cours).
- **Contrat** : `WorkflowRunMetric` + enums `WorkflowRunStatus`, `WorkflowTriggerType`, `MetricDomain.WORKFLOW`.
- **RAW** : domaine `workflow` autorisé (dlt_01).
- **CURATED** : `curated_dbx_workflow_runs` (+ `_rejects`), MERGE SCD1.
- **GOLD** : 5 agrégats `gold_dbx_workflow_*` + 2 tables drill-down (`gold_dbx_workflow_runs` grain run, `gold_dbx_workflow_tasks` grain tâche).
- **Tests** : collecteur, commons, DLT ; fixtures JSON.

### Hors périmètre

- Collecteur AWS (Glue/EMR) — non concerné par ce domaine.
- Changement du contrat API backend / frontend.
- E2E Databricks (laissé au déploiement).
- Migration System Tables (traitée séparément — spec 010).

---

## User Scenarios & Testing

### User Story 1 — Suivi du taux de succès (Priority: P1)

En tant qu'ingénieur Data, je veux voir le taux de succès quotidien et glissant 7 j de mes Workflows par LZ/workspace.

**Independent Test** : peupler `curated_dbx_workflow_runs` avec des runs de statuts variés → `gold_dbx_workflow_success_rate` calcule `success_rate_24h_pct` et `_7d_pct` corrects.

**Acceptance Scenarios**:
1. **Given** 10 runs dont 8 `succeeded`, **When** l'agrégat tourne, **Then** `success_rate_24h_pct = 80.0`.
2. **Given** 7 jours de données, **When** window 7 j, **Then** `success_rate_7d_pct` = succès/total sur la fenêtre.

### User Story 2 — Performance & dérive (Priority: P1)

En tant qu'ingénieur Data, je veux les percentiles de durée (p50/p95/p99) et la dérive vs moyenne mobile 14 j.

**Independent Test** : jeu de durées connu → `percentile_approx` et `duration_drift_pct` cohérents.

**Acceptance Scenarios**:
1. **Given** durées connues, **When** l'agrégat tourne, **Then** p50/p95/p99 correspondent.
2. **Given** baseline 14 j, **When** durée du jour > baseline, **Then** `duration_drift_pct` positif.

### User Story 3 — Fiabilité tâches & concurrence (Priority: P2)

En tant qu'exploitant, je veux le taux d'échec au niveau tâche et la concurrence des runs par minute.

**Independent Test** : runs avec `tasks_total/failed` connus → `task_failure_rate_pct` correct ; intervalles chevauchants → `concurrent_runs_active` correct.

### User Story 4 — Idempotence des runs en cours (Priority: P1)

En tant que système, un run `running` puis terminé ne doit pas créer de doublon.

**Independent Test** : ingérer le même `run_id` en `running` puis `succeeded` → MERGE SCD1 sur `(workflow_id, run_id, source_lz_id)` garde le dernier état.

---

## Functional Requirements

- **FR-001** : Le collecteur DOIT appeler `/api/2.2/jobs/runs/list?expand_tasks=true` par workspace et émettre 1 `WorkflowRunMetric` par run (y compris en cours).
- **FR-002** : Le contrat DOIT exposer un modèle `WorkflowRunMetric` distinct de `PipelineMetric`, dans le domaine `workflow`.
- **FR-003** : `schema_version` DOIT être bumpé de façon additive (`1.1 → 1.2`), sans régression sur les domaines existants.
- **FR-004** : La couche RAW DOIT accepter le domaine `workflow`.
- **FR-005** : La table `curated_dbx_workflow_runs` DOIT dédupliquer par MERGE SCD1 sur `(workflow_id, run_id, source_lz_id)`.
- **FR-006** : Les 5 agrégats GOLD DOIVENT être calculés à partir de `curated_dbx_workflow_runs` : success_rate (24h/7d), duration_percentiles (p50/p95/p99), duration_drift (14j), task_failure_rate, concurrency_1min.
- **FR-007** : La concurrence DOIT être reconstruite par recouvrement d'intervalles `[start, end]` (déterministe) ; un run en cours est prolongé à `current_timestamp()`.
- **FR-008** : Les runs invalides (DQ) DOIVENT être capturés dans `curated_dbx_workflow_runs_rejects`.
- **FR-009** : Une table drill-down `gold_dbx_workflow_runs` (grain run, PK incluant `run_id`) DOIT exposer le détail par run sans agrégation ; `run_id` NE DOIT PAS apparaître dans les 5 agrégats jour × workflow (préservation du grain).
- **FR-010** : Une table drill-down `gold_dbx_workflow_tasks` (grain tâche, PK incluant `task_id`) DOIT exposer le détail par tâche depuis `curated_dbx_workflow_task_runs`.
- **FR-011** : Toute métrique absente de la source DOIT rester `NULL`/`None` (jamais `0` non daté).

---

## Success Criteria

- **SC-001** : 1 record par run collecté, runs en cours inclus, sans agrégat côté collecteur.
- **SC-002** : `curated_dbx_workflow_runs` idempotente (double ingestion `running`→`succeeded` ⇒ 1 ligne, état terminal).
- **SC-003** : Les 5 tables GOLD produisent des valeurs conformes aux tests sur fixtures.
- **SC-004** : Aucune régression sur les domaines existants (`pipeline` ADF, `compute`, etc.).
- **SC-005** : Ruff zéro warning, tests verts (collecteur, commons, DLT).
