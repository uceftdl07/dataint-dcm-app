# Tasks: Compute Metrics Exposition (UI)

**Input**: Design documents from `/specs/015-compute-metrics-exposition/` (spec.md, intake.json, maquette/compute-metrics-exposition/)

**Tests**: Backend pytest + frontend vitest per sub-spec. Constitution P1 — tests land with each task.

**Organization**: DCM custom ticket plan — **4 Stories** (1 Backend + 3 Frontend, **1 page = 1 ticket**), 1 task = 1 Jira Story = 1 branch = 1 sub-spec.

## Format: `[ID] [Domain] Description → sub-spec`

## Tasks

- [ ] T001 Backend API exposition gold compute (clusters, warehouses, recommendations, forecast) → [stories/T001-compute-metrics-api.md](stories/T001-compute-metrics-api.md)
- [ ] T002 Frontend page Compute Clusters → [stories/T002-compute-clusters-ui.md](stories/T002-compute-clusters-ui.md)
- [ ] T003 Frontend page Compute SQL Warehouses → [stories/T003-compute-warehouses-ui.md](stories/T003-compute-warehouses-ui.md)
- [ ] T004 Frontend page Recommendations & Forecast → [stories/T004-compute-reco-forecast-ui.md](stories/T004-compute-reco-forecast-ui.md)

## Dependencies & Execution Order

- **T001** — no dependency on frontend. **Blocks** T002/T003/T004 (API contract). Soft dependency on Epic 012 gold tables (empty-state OK if not).
- **T002 / T003 / T004** — each depends on **T001**. Independent of each other for merge/QA (page-by-page testing). Share Compute nav group + optional shared `components/domain/compute/` helpers (coordinate to avoid duplicate primitives).

Recommended merge order: **T001 → T002 → T003 → T004** (or T002/T003 parallel after T001).

## Implementation Strategy

1. T001 — backend API with empty-state + pagination for all 3 modules.
2. T002 — Clusters page only — QA sign-off page.
3. T003 — SQL Warehouses page only — QA sign-off page.
4. T004 — Reco & Forecast + nav badge — QA sign-off page.

## Notes

- Maquettes : `maquette/compute-metrics-exposition/`.
- Gold contract : `specs/012-compute-metrics-ingestion/contracts/gold-tables-contract.md`.
- Legacy `/clusters` + `GET /api/v1/compute` — **do not remove**.
- `warehouse_slow_queries` — hide tab if API disabled (T003).
- PO decision 2026-08-25 : **1 ticket frontend par page** pour tester page par page.
