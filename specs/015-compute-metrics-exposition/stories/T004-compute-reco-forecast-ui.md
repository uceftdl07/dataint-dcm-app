# T004 — Frontend page Recommendations & Forecast

**Domain**: frontend
**Package**: packages/dcm-frontend
**Branch**: frontend/015-compute-reco-forecast-ui
**Jira**: DCINT-270
**Depends on**: T001 (T002/T003 optional for cross-links)
**Work type**: feature

> **Branch** = git **branch name** only. Never a commit SHA.

## Description

Implement **Recommendations & Forecast** under `Databricks > Compute` — KPI cards, filterable reco table, mini-drawer, forecast widget (5 metrics), nav badge (open count). Reference `dcm-compute-recommendations-forecast.html` + `Compute_Recommendations_Forecast_Spec.md`.

## Files to create/modify

- CREATE `packages/dcm-frontend/src/pages/ComputeRecommendationsForecast.tsx` — `/databricks/compute/recommendations`
- CREATE `packages/dcm-frontend/src/components/domain/compute/recommendations-table.tsx`
- CREATE `packages/dcm-frontend/src/components/domain/compute/recommendation-mini-drawer.tsx`
- CREATE `packages/dcm-frontend/src/components/domain/compute/forecast-widget.tsx`
- CREATE `packages/dcm-frontend/src/hooks/useComputeRecommendations.ts`
- CREATE `packages/dcm-frontend/src/hooks/useComputeForecast.ts`
- CREATE `packages/dcm-frontend/src/hooks/useComputeRecommendationsOpenCount.ts`
- UPDATE `packages/dcm-frontend/src/app-routes.ts`
- UPDATE `packages/dcm-frontend/src/config/navigation.ts` — **Recommendations & Forecast** + badge
- UPDATE Sidebar/nav renderer for badge if needed
- CREATE tests + fixtures

## Page structure (V1)

1. KPI row (4): Open, Potential savings, Resolved 30d, High severity
2. Recommendations table — object_type / category / severity AND filters
3. Mini-drawer + CTA to cluster|warehouse page
4. Forecast widget — 5 metrics; independent of table filters
5. Nav badge = OPEN count

## Acceptance Criteria

- [ ] Route accessible from nav (SC-001).
- [ ] KPI + AND filters + empty-state.
- [ ] Mini-drawer cross-nav CTAs (FR-009).
- [ ] Forecast 5 metrics (SC-006).
- [ ] Badge = API open count (FR-007, SC-005).
- [ ] Empty-state without data (FR-008).

## Tests

- `cd packages/dcm-frontend && npm run test -- ComputeRecommendations`
- `npm run lint && npm run build`

## Out of scope

- Clusters (T002), Warehouses (T003), Backend (T001), editing reco (read-only V1), 10th rule UNDER (V2).

## Before PR

- [ ] Rebased after T001
- [ ] Tests + lint + build pass
- [ ] Badge verified against API
- [ ] Jira DCINT-270 lists git branch
