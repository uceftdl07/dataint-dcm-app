# Tasks: DCM Navigation v2 — Sidebar Cleanup & Restructure

**Input**: Design documents from `specs/011-nav-v2-cleanup/`

**Feature branch**: `011-nav-v2-cleanup`
**Work type**: feature | **Priority**: P2
**Domain**: Frontend | **Package**: `packages/dcm-frontend`
**Dispatch mode**: granular (1 task per User Story)

**Design artifacts**:
- [spec.md](spec.md) — 3 user stories (P1, P1, P2)
- [plan.md](plan.md) — technical context + constitution check ✅
- [research.md](research.md) — 7 decisions (R1–R7)
- [data-model.md](data-model.md) — TypeScript contracts (MAIN_MENU, SETTINGS_MENU, MenuChild)
- [quickstart.md](quickstart.md) — nav authoring guide

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared state)
- **[US1/2/3]**: User Story (1 = Main Nav, 2 = Settings Section, 3 = Databricks v2)
- Tasks are sequentially dependent (T001 → T002 → T003)

---

## Phase 1: Foundational — navigation.ts Type Contract

**Purpose**: Extend `MenuChild` type + establish `MAIN_MENU`/`SETTINGS_MENU` export structure. Unblocks all user story phases.

**⚠️ CRITICAL**: T001 modifies `navigation.ts` — T002 and T003 depend on this file being structured first.

- [x] T001 Frontend [US1] Split navigation.ts into MAIN\_MENU + SETTINGS\_MENU, extend MenuChild with isGroupHeader, implement main nav simplification → [stories/T001-main-nav-simplification.md](stories/T001-main-nav-simplification.md)

**Checkpoint**: `navigation.ts` exports `MAIN_MENU` (3 items), `SETTINGS_MENU` (2 items), `MODULE_MENU` (merged, backward compat). `Sidebar.tsx` uses `MAIN_MENU`. `tsc --noEmit` exits 0.

---

## Phase 2: User Story 2 — Settings Section in Sidebar (Priority: P1)

**Goal**: Render a distinct Settings section in `Sidebar.tsx` using `SETTINGS_MENU`. Administration hidden for non-admins.

**Independent Test**: Sidebar renders two visually separate sections. Admin user sees Administration + My Landing Zones. Non-admin user sees only My Landing Zones in Settings section.

**⚠️ Depends on**: T001 (SETTINGS_MENU must be defined in navigation.ts)

- [x] T002 Frontend [US2] Add Settings section to Sidebar.tsx (divider + SETTINGS\_MENU rendering + requiresAdmin hide logic) → [stories/T002-settings-section.md](stories/T002-settings-section.md)

**Checkpoint**: Sidebar shows Settings label + 2 items (admin) or 1 item (non-admin). Collapsed state shows icons with tooltips. No TypeScript errors.

---

## Phase 3: User Story 3 — Databricks v2 Sub-Navigation (Priority: P2)

**Goal**: Restructure Databricks children with Lakeflow/Compute group headers (non-clickable) + 6 leaf items. Create shared placeholder page. Register 6 new routes before catch-all.

**Independent Test**: Expand Databricks menu → see Lakeflow / Compute headers + 6 leaf links. Click each → placeholder page renders. Old Databricks routes still work via direct URL.

**⚠️ Depends on**: T001 (Databricks entry lives in MAIN_MENU), T002 (isGroupHeader rendering logic may be added to Sidebar.tsx)

- [x] T003 Frontend [US3] Restructure Databricks children (isGroupHeader), create DatabricksComingSoon.tsx, register 6 routes in app-routes.ts → [stories/T003-databricks-v2-subnav.md](stories/T003-databricks-v2-subnav.md)

**Checkpoint**: 6 new routes render placeholder pages. Old routes (/databricks/alerts etc.) still load. `tsc --noEmit` exits 0. All Vitest tests pass.

---

## Final Phase: Verification Gate

**Purpose**: Cross-cutting quality check — not a separate task, done as part of T003 completion.

- [ ] T003 sub-task: `npm run typecheck` exits 0 (tsc --noEmit)
- [ ] T003 sub-task: `npm run lint` exits 0 (zero ESLint warnings)
- [ ] T003 sub-task: `npm run test` — all existing Vitest tests pass + new Sidebar section tests pass

---

## Dependencies

```
T001 (navigation.ts structure + US1)
  └── T002 (Sidebar.tsx Settings section)
        └── T003 (Databricks v2 + routes + placeholder page)
```

**No parallel execution possible** — all tasks share `navigation.ts` and `Sidebar.tsx`.

---

## Implementation Strategy

**MVP** (deliver value after T001): Simplified main nav with 3 items is already clean.

**Increment 2** (T002): Settings section visible — Administration + My Landing Zones accessible from dedicated zone.

**Increment 3** (T003): Databricks v2 structure in place, ready for future sprint spec work on each section.

---

## Success Criteria Mapping

| Task | SC |
|------|----|
| T001 | SC-001 (3 main items), SC-004 (hidden routes still load), SC-005 (tsc 0), SC-006 (no regressions) |
| T002 | SC-002 (Settings section 2 items), SC-005, SC-006 |
| T003 | SC-003 (6 new routes render), SC-005, SC-006 |
