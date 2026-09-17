# T003 — Frontend page Compute SQL Warehouses

**Domain**: frontend
**Package**: packages/dcm-frontend
**Branch**: frontend/015-compute-warehouses-ui
**Jira**: DCINT-269
**Depends on**: T001
**Work type**: feature

> **Branch** = git **branch name** only. Never a commit SHA.

## Description

Replace `DatabricksComingSoon` with the **SQL Warehouses** page under `Databricks > Compute > SQL Warehouses` — sub-views, filters, drawer. Reference `dcm-compute-warehouses.html` + `Compute_Warehouses_Spec.md`.

## Files to create/modify

- CREATE `packages/dcm-frontend/src/pages/ComputeSqlWarehouses.tsx` — `/databricks/sql-warehouse`
- CREATE `packages/dcm-frontend/src/hooks/useComputeWarehouses*.ts`
- REUSE / EXTEND `packages/dcm-frontend/src/components/domain/compute/` (from T002 if merged, else introduce shared primitives carefully)
- UPDATE `packages/dcm-frontend/src/app-routes.ts`
- UPDATE `packages/dcm-frontend/src/config/navigation.ts` — label **SQL Warehouses**
- CREATE tests + fixtures
- CREATE query-profile URL builder for slow-queries external link

## Sub-views (V1)

| Tab | Notes |
|-----|-------|
| Overview | Cost, actifs, queries, failures, reco |
| Cost | size filter, sort |
| Query performance | failures / spill pills + latency threshold |
| Slow queries | **Hide entire tab if T001 slow-queries disabled** |

**Drawer**: size, auto-stop, KPIs, trend, linked slow queries, reco CTA.

**Sensitivity**: never display `statement_text` — external Databricks query profile link only (FR-006).

## Acceptance Criteria

- [ ] `/databricks/sql-warehouse` renders 3 or 4 tabs depending on slow-queries API.
- [ ] Filters via T001 API (FR-004).
- [ ] Empty-state on zero rows (FR-008).
- [ ] Drawer + trend Week default (FR-005).
- [ ] Slow queries tab hidden when API unavailable (US3).
- [ ] English labels (NFR-004); WCAG (NFR-003).

## Tests

- `cd packages/dcm-frontend && npm run test -- ComputeSqlWarehouses`
- `npm run lint && npm run build`

## Out of scope

- Clusters page (T002), Reco & Forecast (T004), Backend (T001), Utilization V2.

## Before PR

- [ ] Rebased after T001 (and T002 if sharing compute components)
- [ ] Tests + lint + build pass
- [ ] UX sign-off vs maquette Warehouses
- [ ] Jira DCINT-269 lists git branch
