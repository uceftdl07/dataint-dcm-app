# Tasks: Migration domaine `workflow` — collecteur → `system.lakeflow.*`

**Input**: Design documents from `/specs/013-workflow-sys-tables-migration/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: Non demandés en TDD explicite, mais P1 (constitution) impose que les tests (pytest/chispa côté pipeline, pytest côté backend, Vitest côté frontend) atterrissent avec chaque tâche — inclus dans chaque sub-spec.

**Organization**: DCM dispatch mode = **custom** (`intake.json.ticket_plan`, 5 Stories → `dataeng ×3`, `backend ×1`, `frontend ×1`). 1 task = 1 Jira Story = 1 branche = 1 sub-spec. Détail d'exécution dans `stories/T00X-*.md` (ce fichier = index).

## Format: `[ID] [P?] Domain Description → sub-spec`

- **[P]** : parallélisable (fichiers disjoints, pas de dépendance sur une tâche incomplète).
- Domaines : dataeng, backend, frontend.

## Tasks

- [ ] T001 DataEng Curated fidèle `system.lakeflow.*` — 3 `IngestionSpec` (`curated_dbx_lakeflow_jobs`, `_job_run_timeline`, `_job_task_run_timeline`) + registre + job YAML → [stories/T001-curated-lakeflow-system-tables.md](stories/T001-curated-lakeflow-system-tables.md)
- [~] T002 DataEng Vues-pont DLT (`_wf_runs_bridge`, `_wf_task_runs_bridge`) + re-sourcing des 8 gold `gold_dbx_workflow_*` + gate de validation → [stories/T002-bridge-views-regold-workflow.md](stories/T002-bridge-views-regold-workflow.md) (code fait, tests OK ; **gate quickstart §3 + validation PO restants**)
- [ ] T003 DataEng Teardown collecteur `workflow` (raw/curated DLT §9, `DatabricksWorkflowCollector`, modèles + enums `dcm-commons`) — **PR destructive post-gate** → [stories/T003-teardown-workflow-collector.md](stories/T003-teardown-workflow-collector.md)
- [ ] T004 [P] Backend NULL-tolérance domaine `workflow` + champ `as_of` + repli `/workspaces` → [stories/T004-backend-null-safe-freshness.md](stories/T004-backend-null-safe-freshness.md)
- [x] T005 Frontend Lakeflow/Jobs NULL-safe (colonne « Attente » masquée, tooltip cron retiré) + bandeau fraîcheur `as_of` → [stories/T005-frontend-null-safe-freshness.md](stories/T005-frontend-null-safe-freshness.md)

## Dependencies & Execution Order

- **T001** — aucune dépendance. Étend le plugin `pipelines/system_tables/` (3 `IngestionSpec` + `SPECS`/`SPEC_KEYS` + `job_dcm_system_tables.yml`). Bloque T002 (les vues-pont lisent `curated_dbx_lakeflow_*`). PR **additive, zéro risque**.
- **T002** — dépend de T001. Crée les 2 vues-pont dans `dlt_03_gold_layer.py` et re-source les 8 fonctions gold. Inclut le **gate de validation** (quickstart §3, comparaison ancien vs nouveau, accord PO). Collecteur + `curated_dbx_workflow_*` DLT laissés **intacts**.
- **T003** — dépend de T002 **et du passage du gate** (accord PO). PR **destructive séparée** : retrait `'workflow'` de `valid_domain`, suppression §9 DLT curated, collecteur, modèles/enums. Ne jamais lancer avant validation T002.
- **T004** [P] — dépend de T002 (le gold re-sourcé expose les colonnes NULL + `_ingested_at` pour `as_of`). Parallélisable avec T003 (fichiers backend disjoints du teardown pipeline), tant que les colonnes NULL sont tolérées.
- **T005** — dépend de T004 (consomme le champ `as_of` et les réponses NULL-safe de l'API).

Ordre de merge conseillé : **T001 → T002 (+ gate) → {T003 ∥ T004} → T005**.

## Implementation Strategy

### MVP (T001 + T002)

1. T001 — curated lakeflow (bloquant).
2. T002 — vues-pont + re-sourcing gold : le contrat GOLD est servi par les system tables. **STOP & VALIDATE** via quickstart §1-3 (gate) avant tout teardown.

### Incrémental

1. Après gate ✅ : T003 (teardown) et T004 (backend NULL-safe) en parallèle, puis T005 (frontend).
2. Chaque tâche est indépendamment testable via les Acceptance Criteria de sa sub-spec + `quickstart.md`.

## Notes

- Pas de phase Setup/Foundational dédiée : l'Epic étend des packages déjà scaffoldés.
- Polish/cross-cutting (ruff/mypy zéro-warning, run complet `quickstart.md`, docs `Azure-Collector-End2End-Lineage.md`) est plié dans le « Before PR » de chaque story (surtout T003), pas une phase séparée.
- **Garde-fou destructif** : T003 ne démarre qu'après validation explicite du gate T002 (clarif. Q2 — 2 temps).
- Voir [merge-strategy.md](merge-strategy.md) pour les fichiers partagés et l'ordre de coexistence des noms (`_wf_*_bridge` distincts des anciennes `curated_dbx_workflow_*`).
