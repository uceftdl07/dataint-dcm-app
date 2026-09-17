# Tasks: Frontend UX Improvements

**Input**: Design documents from `/specs/007-frontend-ux-improvements/`

**Prerequisites**: `spec.md`, `plan.md`

**Tests**: Required for shared components when practical. Manual browser verification is required for responsive and visual UX changes.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and has no dependency on incomplete work.
- **[Story]**: Which user story the task maps to.

---

## Phase 1: Spec Kit Setup

**Purpose**: Capture the UX improvement scope before implementation.

- [x] T001 Create Spec Kit folder `specs/007-frontend-ux-improvements/`.
- [x] T002 Add feature specification in `specs/007-frontend-ux-improvements/spec.md`.
- [x] T003 Add implementation plan in `specs/007-frontend-ux-improvements/plan.md`.
- [x] T004 Add implementation task list in `specs/007-frontend-ux-improvements/tasks.md`.
- [x] T005 Update `.specify/feature.json` to point at the new feature directory.

---

## Phase 2: Frontend UX Audit (Priority: P1)

**Goal**: Identify the exact shared components before editing.

**Independent Test**: Document the frontend files responsible for layout, header filters, sidebar, `Mounir AI`, empty states and page actions.

- [x] T006 [P] Locate the protected layout and global page header components.
- [x] T007 [P] Locate the monitoring scope/date range filter components.
- [x] T008 [P] Locate the sidebar/navigation components and `navigation.ts`.
- [x] T009 [P] Locate the `Mounir AI` floating button component.
- [x] T010 [P] Locate current empty state and KPI/card components.
- [x] T011 Capture current viewport issues on `/dashboard`, `/databricks`, `/databricksalerts` and `/databricksfinops`.

**Audit notes**:

- Protected layout and floating assistant: `packages/dcm-frontend/src/App.tsx` (`ProtectedLayout`, `renderProtectedPage`, `MounirPageBubble`).
- Global header and filters: `packages/dcm-frontend/src/components/Header.tsx` (`Header`, `dateRangePresets`, `compactScopeLabel`).
- Scope and time range state: `packages/dcm-frontend/src/contexts/MonitoringScopeContext.tsx`, `packages/dcm-frontend/src/contexts/monitoring-scope.ts`, `packages/dcm-frontend/src/contexts/TimeRangeContext.tsx`, `packages/dcm-frontend/src/contexts/time-range.ts`.
- Sidebar and navigation: `packages/dcm-frontend/src/components/Sidebar.tsx`, `packages/dcm-frontend/src/config/navigation.ts`.
- KPI/cards and empty states: `packages/dcm-frontend/src/components/domain/metric-card.tsx`, `packages/dcm-frontend/src/components/domain/states.tsx`, `packages/dcm-frontend/src/components/domain/filter-panel.tsx`, plus shared cards in `packages/dcm-frontend/src/components/ui/card.tsx`.
- Representative pages: `packages/dcm-frontend/src/pages/Dashboard.tsx`, `packages/dcm-frontend/src/pages/Databricks.tsx`, `packages/dcm-frontend/src/pages/Alerts.tsx`, `packages/dcm-frontend/src/pages/Costs.tsx`, `packages/dcm-frontend/src/pages/DatabricksAlerts.tsx`, `packages/dcm-frontend/src/pages/DatabricksFinOps.tsx`.
- Observed issues to address first: the global header consumes too much vertical space, reduced sidebar relies heavily on icons, `MounirPageBubble` is fixed at `bottom-6 right-6 z-50`, and empty states mix shared components with inline messages.

---

## Phase 3: Compact Header and Filters (Priority: P1)

**Goal**: Show meaningful page data earlier without removing filter capabilities.

**Independent Test**: On representative pages, first KPI/verdict content appears higher and filters remain usable.

- [x] T012 [US1] Reduce visual height of global filter inputs.
- [x] T013 [US1] Make date fields and range shortcuts use a compact layout on desktop.
- [x] T014 [US1] Add or expose a compact active-scope summary.
- [x] T015 [US1] Ensure filters remain editable in compact or responsive mode.
- [ ] T016 [US1] Verify `/dashboard`, `/databricks`, `/databricksalerts`, `/databricksfinops` and `/monitoringreports`.

**Implementation notes**:

- `packages/dcm-frontend/src/components/Header.tsx` now renders the global filters in a compact horizontal row with smaller controls and no horizontal scrollbar.
- Browser check completed on `/databricksalerts`; remaining representative pages still need visual verification.

---

## Phase 4: Sidebar Reduced Mode (Priority: P1)

**Goal**: Make the reduced sidebar understandable and clickable.

**Independent Test**: With sidebar reduced, every icon has a comprehensible label and active page state.

- [x] T017 [US2] Add tooltips or equivalent hover labels for reduced sidebar items.
- [x] T018 [US2] Fix duplicated accessible names such as `HomeHome` if present.
- [x] T019 [US2] Improve active-state styling in reduced mode.
- [ ] T020 [US2] Verify click targets for Home, Databricks, Global FinOps, Global Alerts, Cloud security and Settings.
- [ ] T021 [US2] Add a targeted test for accessible nav labels if the project test setup supports it.

**Implementation notes**:

- `packages/dcm-frontend/src/components/Sidebar.tsx` keeps reduced-mode tooltips and now exposes explicit accessible labels for primary nav items and the user menu.
- Active nav items get a stronger ring/shadow treatment in reduced mode.

---

## Phase 5: Mounir AI Floating Entry Point (Priority: P1)

**Goal**: Keep assistant access visible without blocking page actions.

**Independent Test**: The floating assistant button does not cover `Refresh`, `Export`, `Reset` or KPI content on tested viewports.

- [x] T022 [US3] Reduce or adjust the default `Mounir AI` button footprint.
- [x] T023 [US3] Reposition the button with safe margins from page actions.
- [x] T024 [US3] Add a compact behavior for constrained viewports if needed.
- [ ] T025 [US3] Verify assistant open/close behavior on dashboard and Databricks pages.

**Implementation notes**:

- `packages/dcm-frontend/src/App.tsx` now hides `MounirPageBubble` on constrained and medium viewports; users still reach the assistant from the `Talk to Data` sidebar item, and the floating button remains available on `xl` screens.
- `packages/dcm-frontend/src/components/GlobalLoadingSpinner.tsx` no longer renders a centered full-screen logo overlay. Global API loading is shown as a thin top progress bar so page skeletons and actions remain readable.

---

## Phase 6: Page Hierarchy and Actions (Priority: P2)

**Goal**: Make pages more decision-oriented.

**Independent Test**: Pages show verdict/KPI/actions before long explanatory text where data is available.

- [x] T026 [US4] Identify pages that need a top-level verdict.
- [x] T027 [US4] Add or standardize verdict display for monitoring pages.
- [x] T028 [US4] Move or emphasize the 3-4 primary KPI cards above long descriptions.
- [x] T029 [US7] Clarify action grouping for `Refresh`, `Export`, `Reset` where applicable.
- [ ] T030 [US4] Verify no page loses important explanatory context.

**Implementation notes**:

- Added shared `PageVerdict` and `EmptyState` action support in `packages/dcm-frontend/src/components/domain/states.tsx`.
- Dashboard, shared security alert pages and shared FinOps pages now expose a short operational verdict before KPI details.
- Primary page actions remain grouped in the header action area; empty-state actions are local to the affected table or card.

---

## Phase 7: Empty States (Priority: P2)

**Goal**: Explain empty data states clearly.

**Independent Test**: Empty Alerts, FinOps and Jobs states tell the user what the absence of data means and what to do next.

- [x] T031 [US5] Replace generic Alerts empty messages with clearer user guidance.
- [x] T032 [US5] Replace generic FinOps empty messages with collection/scope guidance.
- [x] T033 [US5] Improve empty Jobs/Pipelines messages where applicable.
- [x] T034 [US5] Add links or action hints to change period, change scope or check collection status when relevant.
- [x] T035 [US5] Ensure empty states do not imply "healthy" when data collection is unknown.

**Implementation notes**:

- Shared Alerts and FinOps tables now distinguish "no detected signal" from possible collection/scope issues.
- Pipelines and drilldown empty states now explain filters, period and collection status before implying a healthy state.

---

## Phase 8: Labels and Landing Page (Priority: P3)

**Goal**: Improve finish and first-use clarity.

**Independent Test**: Main labels are consistent and the unauthenticated landing page has an obvious primary CTA.

- [x] T036 [US6] Decide the target language convention for primary UI labels.
- [x] T037 [US6] Harmonize `Start`, `End`, `Refresh`, `Reset`, `No alert`, `To handle` and related labels.
- [x] T038 [US6] Keep technical product terms stable where expected: `Databricks`, `FinOps`, `Unity Catalog`, `Landing Zone`.
- [x] T039 [US7] Make the landing page primary CTA more visually dominant.
- [x] T040 [US7] Clarify the difference between `Sign in` and `Initialize the cockpit` if both remain.
- [x] T041 [US7] Verify the decorative landing background does not compete with the CTA.

**Implementation notes**:

- Primary UI convention kept in English because the frontend already uses English for navigation, actions and technical terms.
- Frequent labels were harmonized (`30 days`, `Needs attention`, `Controlled`, `Increasing`, `Decreasing`, plural alert empty states).
- Landing page now has a dominant `Sign in to cockpit` CTA, a secondary documentation action and a less competing decorative background.

---

## Phase 9: Validation

**Purpose**: Verify the UX improvement end-to-end.

- [x] T042 Run frontend lint in `packages/dcm-frontend`.
- [x] T043 Run frontend build in `packages/dcm-frontend`.
- [ ] T044 Run frontend tests if available.
- [x] T045 Manually verify `/` unauthenticated.
- [x] T046 Manually verify `/dashboard`.
- [x] T047 Manually verify `/databricks`.
- [x] T048 Manually verify `/databricksalerts`.
- [x] T049 Manually verify `/databricksfinops`.
- [ ] T050 Manually verify menu opened and reduced.
- [x] T051 Manually verify `Mounir AI` on desktop and medium viewport.
- [x] T052 Update this task list with completed checkboxes and implementation notes.

**Validation notes**:

- `npm run lint` passed.
- `npm run build` passed.
- `npm run test` was executed but currently fails on `src/pages/Admin.test.tsx` because the test renders `Administration access required` for role `admin` instead of the expected super-admin page.
- Browser snapshots verified `/`, `/dashboard`, `/databricks`, `/databricksalerts` and `/databricksfinops`.
- Follow-up feedback adjusted the global header spacing and centered the compact filter row on `/dashboard`.
