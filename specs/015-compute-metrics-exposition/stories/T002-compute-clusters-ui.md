# T002 — Frontend page Compute Clusters

**Domain**: frontend
**Package**: packages/dcm-frontend
**Branch**: frontend/015-compute-clusters-warehouses-ui
**Jira**: DCINT-268
**Depends on**: T001
**Work type**: feature

> **Branch** = git **branch name** only. Never a commit SHA.

## Description

Replace `DatabricksComingSoon` with the **Compute Clusters** page under `Databricks > Compute > Clusters` — 4 sub-views, local filters (server-driven), KPI cards, data table, detail drawer. Reference `dcm-compute-clusters.html` + `Compute_Clusters_Spec.md`.

## Files to create/modify

- CREATE `packages/dcm-frontend/src/pages/ComputeClusters.tsx` — `/databricks/cluster`
- CREATE `packages/dcm-frontend/src/components/domain/compute/` — shared primitives as needed (tabs, KPI, filter bar, drawer, trend chart, empty-state) — prefer shared helpers reusable by T003/T004
- CREATE `packages/dcm-frontend/src/hooks/useComputeClusters*.ts`
- CREATE `packages/dcm-frontend/src/lib/compute/` — types / filter mappers (shared OK)
- UPDATE `packages/dcm-frontend/src/app-routes.ts`
- UPDATE `packages/dcm-frontend/src/config/navigation.ts` — label **Clusters**
- CREATE tests + fixtures

## Sub-views (V1)

| Tab | KPI | Filters |
|-----|-----|---------|
| Overview | Coût total Δ%, Actifs, Zombies, Reco ouvertes | — |
| Cost | Coût période, DBU, Top coûteux | search, sku_group, sort |
| Efficiency | CPU/Mem p95, Zombies, Économies | utilization + Zombie pill |
| Governance | Tags, DBR, Auto-stop, Sévérité | severity + pills |

**Drawer**: identity, KPIs, cost trend 90d (default Week), linked reco + CTA to Reco page (route may land with T004).

**Excluded V1**: Reliability tab — do not grey-out (FR-010).

## Acceptance Criteria

- [ ] `/databricks/cluster` renders 4 tabs (SC-002).
- [ ] Filters call T001 API params (FR-004).
- [ ] Empty-state on zero rows (FR-008).
- [ ] Drawer + trend granularity Week default (FR-005).
- [ ] Header LZ/workspace filters apply.
- [ ] No regression on legacy `/clusters` (SC-007).
- [ ] English UI labels (NFR-004); WCAG tabs/drawer (NFR-003).

## Tests

- `cd packages/dcm-frontend && npm run test -- ComputeClusters`
- `npm run lint && npm run build`

## Out of scope

- SQL Warehouses page (T003), Reco & Forecast (T004), Backend (T001).

## Before PR

- [ ] Rebased after T001 merged
- [ ] Tests + lint + build pass
- [ ] UX sign-off vs maquette Clusters
- [ ] Jira DCINT-268 lists git branch
