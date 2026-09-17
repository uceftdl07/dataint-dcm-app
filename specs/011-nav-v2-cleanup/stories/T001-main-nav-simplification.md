# T001 — Main Nav Simplification

**Domain**: Frontend
**Package**: `packages/dcm-frontend`
**Branch**: `frontend/011-main-nav-simplification`
**Jira**: DCINT-196
**Depends on**: none
**Work type**: feature

## Description

Restructure `navigation.ts` to establish the v2 navigation contract: introduce `MAIN_MENU` (3 items: Home, Databricks, Talk to your Data) and `SETTINGS_MENU` (2 items) as separate exports. Keep `MODULE_MENU` as merged array for backward compat with `getPageMeta`. Update `Sidebar.tsx` to render from `MAIN_MENU`. All previously visible items not in `MAIN_MENU` are removed from the config array — their routes in `app-routes.ts` are untouched.

Extend `MenuChild` with the `isGroupHeader?: true` flag (needed by T003, defined here as the type contract owner).

## Files to create/modify

- UPDATE `packages/dcm-frontend/src/config/navigation.ts`
- UPDATE `packages/dcm-frontend/src/components/Sidebar.tsx`

## Sub-tasks

### navigation.ts

- [ ] Add `isGroupHeader?: true` to `MenuChild` interface
- [ ] Define `MAIN_MENU: ModuleMenuItem[]` with exactly 3 items:
  - `Home` → `/dashboard` (LayoutDashboard icon)
  - `Databricks` → children array (keep existing structure for now, T003 restructures it)
  - `Talk to your Data` → `/talk-to-data` (Bot icon) — label update from "Talk to Data"
- [ ] Define `SETTINGS_MENU: ModuleMenuItem[]` placeholder (content filled by T002, define empty array here)
- [ ] Redefine `MODULE_MENU = [...MAIN_MENU, ...SETTINGS_MENU]` — keeps `getPageMeta` working
- [ ] Remove all other items (Data Factory, Databases, Clusters, Global FinOps, Global Alerts, Cloud Security, Standard Checks, Users, My Landing Zones, Administration, Collection Status, Settings, Talk to Data old entry) from `MAIN_MENU`
- [ ] Keep removed items' routes in `app-routes.ts` untouched

### Sidebar.tsx

- [ ] Import `MAIN_MENU` and `SETTINGS_MENU` (instead of `MODULE_MENU`)
- [ ] Change `menuItems` useMemo to use `filterModuleMenu(MAIN_MENU, user?.role)`
- [ ] Verify collapsed sidebar still shows correct icons + tooltips for 3 items

## Acceptance Criteria

- [ ] Sidebar main nav section shows exactly 3 items: Home, Databricks, Talk to your Data
- [ ] "Talk to your Data" label (updated from "Talk to Data") displays correctly
- [ ] Navigating directly to `/costs`, `/security`, `/datafactory`, `/clusters`, `/databases`, `/governance`, `/users`, `/status` loads the correct page (no 404)
- [ ] `tsc --noEmit` exits 0
- [ ] `npm run lint` exits 0

## Tests

```bash
cd packages/dcm-frontend
npm run typecheck
npm run lint
npm run test -- --reporter=verbose
```

Write Vitest test in `src/test/Sidebar.test.tsx` (or update if it exists):
- Assert sidebar main nav renders exactly 3 top-level items
- Assert hidden routes (`/costs`, `/security`) are NOT in rendered nav

## Out of scope

- Settings section rendering (T002)
- Databricks children restructure (T003)
- New placeholder pages (T003)
- `SETTINGS_MENU` content — defined empty here, populated in T002

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] `tsc --noEmit` exits 0
- [ ] `npm run lint` exits 0
- [ ] `npm run test` passes (no regressions)
- [ ] No files outside `packages/dcm-frontend` modified
- [ ] `app-routes.ts` unchanged (no routes deleted)

## Notes

- `getPageMeta` in `navigation.ts` iterates `MODULE_MENU` — backward compat preserved via merged array (R7)
- `filterModuleMenu` in `navigation-access.ts` handles `requiresSuperAdmin` filtering — no changes needed there for T001
- The "Talk to your Data" label fix: current nav config has `name: 'Talk to Data'` — update to `'Talk to your Data'` (matches spec FR-001 + LandingPage DataIQ label)
- Existing Databricks children are kept as-is for T001 — T003 will restructure them
