# T002 — Frontend Compute UI (Clusters + SQL Warehouses + Reco & Forecast)

**Domain**: frontend
**Package**: packages/dcm-frontend
**Branch**: frontend/015-compute-clusters-warehouses-ui
**Jira**: DCINT-268
**Depends on**: T001
**Work type**: feature

> **Branch** = git **branch name** only. Never a commit SHA.

## Description

Replace `DatabricksComingSoon` placeholders and implement the full **Compute Metrics** frontend under `Databricks > Compute` :

1. **Clusters** — 4 sub-views, drawer, filters
2. **SQL Warehouses** — 4 sub-views (3 minimum if slow-queries absent), drawer, filters
3. **Recommendations & Forecast** — KPI reco, table, mini-drawer, forecast widget (5 metrics), nav badge

Reference maquettes in `maquette/compute-metrics-exposition/`.

## Files to create/modify

### Shared / nav

- CREATE `packages/dcm-frontend/src/components/domain/compute/` — shared: sub-view tabs, KPI row, filter bar, drawer, cost trend chart, empty-state
- CREATE `packages/dcm-frontend/src/lib/compute/` — types, filter mappers, query-profile URL builder
- UPDATE `packages/dcm-frontend/src/config/navigation.ts` — Compute group: **Clusters**, **SQL Warehouses**, **Recommendations & Forecast** + badge hook
- UPDATE `packages/dcm-frontend/src/app-routes.ts` — 3 routes
- UPDATE `packages/dcm-frontend/src/config/role-permissions.ts` — gate compute metrics pages if needed
- UPDATE `packages/dcm-frontend/src/components/Sidebar.tsx` (or nav renderer) — badge count if supported
- CREATE `packages/dcm-frontend/src/test/fixtures/compute-metrics.ts`

### Clusters + SQL Warehouses

- CREATE `packages/dcm-frontend/src/pages/ComputeClusters.tsx` — `/databricks/cluster`
- CREATE `packages/dcm-frontend/src/pages/ComputeSqlWarehouses.tsx` — `/databricks/sql-warehouse`
- CREATE `packages/dcm-frontend/src/hooks/useComputeClusters*.ts`
- CREATE `packages/dcm-frontend/src/hooks/useComputeWarehouses*.ts`
- CREATE `packages/dcm-frontend/src/pages/ComputeClusters.test.tsx` (and warehouses)

### Reco & Forecast

- CREATE `packages/dcm-frontend/src/pages/ComputeRecommendationsForecast.tsx` — `/databricks/compute/recommendations`
- CREATE `packages/dcm-frontend/src/components/domain/compute/recommendations-table.tsx`
- CREATE `packages/dcm-frontend/src/components/domain/compute/recommendation-mini-drawer.tsx`
- CREATE `packages/dcm-frontend/src/components/domain/compute/forecast-widget.tsx`
- CREATE `packages/dcm-frontend/src/hooks/useComputeRecommendations.ts`
- CREATE `packages/dcm-frontend/src/hooks/useComputeForecast.ts`
- CREATE `packages/dcm-frontend/src/hooks/useComputeRecommendationsOpenCount.ts`
- CREATE tests + fixtures for reco filters and forecast metric selector

## Clusters — sub-views (V1)

| Tab | KPI | Table filters | Maquette ref |
|-----|-----|---------------|--------------|
| Overview | Coût total Δ%, Actifs, Zombies, Reco ouvertes | — | §2 |
| Cost | Coût période, DBU, Top coûteux | search, sku_group, sort | §8 |
| Efficiency | CPU/Mem p95, Zombies, Économies | utilization_status pills (+ Zombie) | §8 |
| Governance | Tags, DBR, Auto-stop, Sévérité | severity + combined pills | §8 |

**Drawer** (row click): identity card, KPIs, cost trend 90d (granularity default Week), linked recommendations + link to `/databricks/compute/recommendations`.

**Excluded V1**: Reliability tab, event timeline — do not show greyed placeholder (FR-010).

## SQL Warehouses — sub-views (V1)

| Tab | KPI | Filters | Notes |
|-----|-----|---------|-------|
| Overview | Cost, actifs, queries, failures, reco | — | §2 |
| Cost | Cost Δ%, cost/query, top consumer | size, sort | §8 |
| Query performance | failure rate, p95, queue, spill | failures pill, spill pill, latency threshold | §8 |
| Slow queries | — | reason pill, warehouse select | **Hide entire tab if T001 slow-queries disabled** |

**Drawer**: size, auto-stop, KPIs, trend, linked slow queries, reco CTA.

**Sensitivity banner** on Slow queries tab: SQL text never displayed — external query profile link only (FR-006).

## Reco & Forecast — structure (V1)

1. **KPI row** (4 cards): Open reco, Potential savings, Resolved 30d, High severity — from `/recommendations/summary`.
2. **Recommendations table**: filters object_type + category + severity (AND logic, maquette §6).
3. **Mini-drawer** on row click: summary + CTA to cluster or warehouse page with object context.
4. **Forecast widget**: 5 metrics (`cost_usd`, `dbu_quantity`, `cpu_util_p95_pct`, `query_count`, `queue_time_p95_ms`); independent of table filters.
5. **Nav badge** on « Recommendations & Forecast » = open reco count from API.

## Acceptance Criteria

### Clusters & Warehouses

- [ ] `/databricks/cluster` renders 4 tabs matching maquette structure (SC-002).
- [ ] `/databricks/sql-warehouse` renders 3 or 4 tabs depending on slow-queries API availability.
- [ ] Local filters call T001 API with correct query params (FR-004).
- [ ] Empty-state when API returns zero rows (FR-008, SC-004).
- [ ] Drawer opens on row click with trend granularity control (Week default) (FR-005).
- [ ] Header workspace / LZ filters apply to all queries.
- [ ] No regression on legacy `/clusters` route (SC-007).

### Reco & Forecast

- [ ] Route `/databricks/compute/recommendations` accessible from nav (SC-001).
- [ ] KPI cards match summary API.
- [ ] Table filters combine with AND logic; empty-state when no match.
- [ ] Row click opens mini-drawer with cross-nav CTA to cluster or warehouse page (FR-009).
- [ ] Forecast widget exposes all 5 metrics (SC-006).
- [ ] Sidebar badge shows open reco count from API (FR-007, SC-005).

### Cross-cutting

- [ ] Labels UI in English (NFR-004).
- [ ] WCAG: tabs, drawer, filters keyboard accessible (NFR-003).

## Tests

- `cd packages/dcm-frontend && npm run test -- ComputeClusters ComputeSqlWarehouses ComputeRecommendations`
- `npm run lint && npm run build`

## Out of scope

- Backend API (T001).
- DataEng / gold pipelines.
- V2 Reliability / Utilization sub-views.
- 10th reco rule (warehouse UNDER) — V2.
- Editing/resolving recommendations in UI (read-only V1).

## Before PR

- [ ] Rebased/merged latest develop after T001 merged
- [ ] Tests + lint + build pass
- [ ] UX sign-off vs maquette HTML (screenshots in PR)
- [ ] Jira Story DCINT-268 lists **Git branch** name

## Notes

- Reuse existing domain components: `MetricCard`, `MetricGrid`, `Content`, shadcn `Tabs`, drawer pattern from Lakeflow pages.
- Granularity select lives **below sub-tabs**, not in global topbar (maquette §8).
- Filter state resets when switching sub-view (maquette Clusters §8).
- Badge query should be lightweight — avoid loading full reco list for nav.
- **Consolidation 2026-08-25** : un seul ticket/PR frontend (DCINT-268) — DCINT-269 / PR #215 annulés.
