# Tasks: Cartes KPI cliquables (Phase 1)

**Input**: `specs/008-clickable-metric-cards/spec.md`, `plan.md`

**Status**: Phase 1 + focus panel + URL query (2026-06-04)

---

## Phase 0: Spec Kit Setup

- [x] T001–T004 Spec folder and documents

---

## Phase 1: Fondations partagées

- [x] T005 `useMetricSectionFocus.ts`
- [x] T006 `useMetricSectionFocus.test.ts`
- [x] T007 `metric-section-anchor.tsx`
- [x] T008 Barrel exports in `components/domain/index.ts`

---

## Phase 2: Accordéon jobs

- [x] T009 `workload-accordion.tsx`
- [x] T010 `workload-accordion.test.tsx`
- [x] T011 Wired in `Databricks.tsx`

---

## Phase 3: Pilote `/databricks`

- [x] T012–T021 Metric cards wired to focus panel
- [x] **1.5** `DatabricksFocusPanel` + per-view components (`views/*`)
- [x] **1.5** URL query `?view=jobs` (+ `&state=running`, `&jobStatus=failed`)
- [x] Copy link + Close in focus panel header
- [ ] T022 Manual browser check (deploy / local QA)

---

## Phase 4: Extension `/alerts` & `/clusters`

- [x] T023 `/alerts` — `#alerts-list` + scroll from KPI cards
- [x] T024 `/clusters` — `#clusters-list` + scroll from KPI cards
- [ ] T025 Manual check `/alerts` and `/clusters`

---

## Phase 5: Qualité

- [x] T026 `npm run lint` + `npm run test` (55 tests pass)
- [ ] T027 Optional doc update in `ui-unity-catalog-interfaces-spec.md`
- [x] T028 No changes to `useHeaderNotifications.ts`

---

## Phase 6–7: Future (not started)

- [ ] T029–T036 Cloche Settings-only, 3 mois, lu/non lu
- [ ] T037–T040 Alert detail route + backend endpoint
