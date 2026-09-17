# Feature Specification: Databricks Workflow/Jobs in DCM (no demo)

**Feature Branch**: `fullstack/011-dbx-workflow-job-metrics` (intégration / specs)  
**Hotfix park**: `hotfix/011-dbx-workflow-job-metrics` (code WIP conservé)  
**Work Type**: feature  
**Priority**: P1  
**Created**: 2026-08-04  
**Updated**: 2026-08-06  

**Input**: Exposer DBX Workflow/Jobs dans DCM sous [DCINT-173](https://tdf.atlassian.net/browse/DCINT-173) — **3 Sub-tasks**, **aucune donnée DEMO/maquette**.

**Jira parent**: DCINT-173 (Technical task) → Epic DCINT-168  
**Jira model**: Sub-tasks (pas de nouvel Epic)

---

## Domain Scope

| Domaine | In scope | Ticket | Packages |
|---------|----------|--------|----------|
| Frontend | ✅ | ✅ (via Sub-tasks) | packages/dcm-frontend |
| Backend | ✅ | ✅ (via Sub-tasks) | packages/dcm-backend |
| DataEng | ❌ lecture seule | ❌ | gold tables — hors ticket |
| DevOps | ❌ | ❌ | API GW déjà traité à part |
| QA | ❌ | ❌ | — |

## Ticket Plan

| Champ | Valeur |
|-------|--------|
| Parent | [DCINT-173](https://tdf.atlassian.net/browse/DCINT-173) |
| Mode | custom — 3 Sub-tasks |
| Sub-tasks | T001, T002, T004 |

| ID | Sub-task | Jira | Branch | PR target |
|----|----------|------|--------|-----------|
| T001 | Databricks hub, nav & workspaces | [DCINT-211](https://tdf.atlassian.net/browse/DCINT-211) | `feature/DCINT-211-databricks-hub` | develop |
| T002 | Databricks Overview | [DCINT-212](https://tdf.atlassian.net/browse/DCINT-212) | `feature/DCINT-212-databricks-overview` | develop |
| T004 | Lakeflow Jobs / Workflows | [DCINT-213](https://tdf.atlassian.net/browse/DCINT-213) | `feature/DCINT-213-lakeflow-jobs` | develop |

Merge order: **T001 → T002 → T004**.

> **Retiré** : Lakeflow Overview (`/Lakeflow/Overview`) — DCINT-214 annulé, PR #166 fermée. On garde uniquement **Databricks Overview** (T002).

## Dependency Analysis

| Besoin | Domaine | Résolution |
|--------|---------|------------|
| `gold_dbx_workflow_*` peuplées | DataEng | Soft-fail + empty-state UI/API — **pas de DEMO** |
| Noms workspace ARM | Backend | `/databricks/workspaces` propre (voir T001) |
| Routes API GW `workflow-jobs` | DevOps | Hors scope (déjà live / IaC séparé) |

---

## Navigation & IA

```
Databricks
  Overview                         → /databricks/overview          (T002)
  ▸ Lakeflow          (collapsible)
      Workflows                    → /databricks/workflows|jobs    (T004)
      Pipelines                    → /databricks/pipelines         (placeholder OK)
  ▸ Compute           (collapsible)
      Cluster                      → /databricks/cluster
      SQL Warehouse                → /databricks/sql-warehouse
  FinOps / Usage Data Product      (existant, hors scope fonctionnel 011)
```

### Règles UX nav

1. **Overview Databricks** placé **au-dessus** de Lakeflow (premier item enfant).
2. Labels : **`Lakeflow`**, **`Compute`** — jamais ALL CAPS.
3. **Lakeflow** / **Compute** : groupes **dépliables**.
4. Pages enfants : tab / secondary nav montrant l’appartenance à Lakeflow ou Compute.
5. Enfants Lakeflow : **Workflows** (Jobs), **Pipelines** — **pas** de Lakeflow Overview.

---

## Backend workspaces (T001 — obligatoire)

`GET /api/v1/databricks/workspaces` doit être **propre et correct** :

| Règle | Détail |
|-------|--------|
| Pas de colonne fantôme | Ne pas lire `workspace_name` sur `curated_compute_metrics` |
| Noms | gold/curated `workspace_name` ou tags (`dcm_workspace_name` / `Project` `dbw-%`) |
| IDs | Normaliser `adb-<id>` ↔ `<id>` |
| Soft-fail | Gold absente / ST stale → pas 500 ; fallback compute |
| Réponse | `workspace_id`, `display_name`, `source_lz_id`, `cluster_count` |
| DEMO | Interdit |

---

## Data sources

| UI | Source |
|----|--------|
| Workspace filter (header) | `GET /api/v1/databricks/workspaces` |
| Databricks Overview | dashboard / clusters APIs |
| Lakeflow Jobs N1–N3 | `GET /api/v1/lakeflow/jobs` (+ `/{id}`, `/runs`, `/tasks`) — pagination serveur |

> Détail Jobs (PO spec 2/2) + points Adrien : `stories/T004-lakeflow-jobs.md`  
> Maquettes : `maquette/Screen Recording 2026-07-02 at 14.29.37.html` (Jobs) + `maquette/maquette_overview.html` — **adapter au design DCM ; menu vertical existant uniquement** (pas le menu horizontal de la maquette).

## User Scenarios & Testing

### User Story 1 — Hub, nav & workspaces (T001 / DCINT-211) — P1

Ops ouvre Databricks : nav hiérarchique + filtre workspaces avec **noms ARM**.

**Acceptance**:
1. Header : labels `dbw-*` (ou nom gold) — pas DEMO
2. Sidebar : Lakeflow déplié → **Workflows** / **Pipelines** (pas Overview Lakeflow) ; labels Title Case
3. Page enfant : tab/indicateur appartenance Lakeflow

### User Story 2 — Databricks Overview (T002 / DCINT-212) — P1

Ops voit le résumé sur `/databricks/overview` (au-dessus de Lakeflow), data réelle.

**Acceptance**:
1. KPIs API — pas de DEMO
2. Libellés `Lakeflow`, `Compute` (pas ALL CAPS)
3. Empty/error → empty-state

### User Story 3 — Lakeflow Jobs (T004 / DCINT-213) — P1

**Spec PO 2/2** (`stories/T004-lakeflow-jobs.md`) : N1 liste → N2 workflow → N3 run/tasks  
(vocabulaire Workflow=Job, colonnes Historique 10 runs, matrice, Gantt, APIs `/api/v1/lakeflow/jobs…`).

**Acceptance**:
1. APIs paginées serveur ; Historique sans N+1 ; pas de prefetch DEMO
2. Empty/error — **interdit** `DEMO_JOBS` ; barre haute conservée
3. Contexte nav Lakeflow
4. UI conforme à la maquette Jobs (`maquette/Screen Recording 2026-07-02 at 14.29.37.html` / `maquette_jobs.html`) **adaptée au design DCM** — **pas de menu horizontal** ; **rester sur le menu vertical déjà existant**

## Out of scope

- Page **`/Lakeflow/Overview`** (retirée — DCINT-214)
- Seeds / maquettes DEMO
- Déploiement tables gold / refresh streaming curated (DataEng)
- Page Pipelines complète (placeholder OK)
- Infra API Gateway (sauf régression)

## Work Breakdown

| ID | Summary | Jira | Branch |
|----|---------|------|--------|
| T001 | Hub nav + workspaces API | DCINT-211 | feature/DCINT-211-databricks-hub |
| T002 | Databricks Overview data réelle | DCINT-212 | feature/DCINT-212-databricks-overview |
| T004 | Lakeflow Jobs liste + drill-down | DCINT-213 | feature/DCINT-213-lakeflow-jobs |

## Requirements

- **FR-001**: Aucune constante `DEMO_*` en runtime
- **FR-002**: Soft-fail backend gold manquante
- **FR-003**: `display_name` workspace dans le header
- **FR-004**: Nav : Overview DBX above Lakeflow ; groupes dépliables ; pas de Lakeflow Overview
- **FR-005**: Une PR par Sub-task vers `develop`
- **FR-006**: T004 respecte la maquette Jobs (layout / colonnes / Historique / drill-down) adaptée au design DCM ; **menu vertical existant uniquement** (interdire le menu horizontal de la maquette)

## Success Criteria

- **SC-001**: 3 Sub-tasks actives (211, 212, 213) + 3 PRs
- **SC-002**: Portal sans maquette ; nav sans `/Lakeflow/Overview`

## Assumptions

- `hotfix/011-dbx-workflow-job-metrics` = réserve code uniquement
- Parent Jira = DCINT-173
- DCINT-214 = cancelled
