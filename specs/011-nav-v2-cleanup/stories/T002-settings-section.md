# T002 — Settings Section in Sidebar

**Domain**: Frontend
**Package**: `packages/dcm-frontend`
**Branch**: `frontend/011-settings-section`
**Jira**: DCINT-197
**Depends on**: T001 (SETTINGS_MENU export must exist in navigation.ts)
**Work type**: feature

## Description

Populate `SETTINGS_MENU` in `navigation.ts` with Administration and My Landing Zones items. Update `Sidebar.tsx` to render a visually distinct Settings section below the main nav: a divider + "Settings" label + the items from `SETTINGS_MENU`. Fix the `requiresAdmin` guard to **hide** Administration completely for non-admins (currently it dims/locks — must become `return null`).

## Files to create/modify

- UPDATE `packages/dcm-frontend/src/config/navigation.ts`
- UPDATE `packages/dcm-frontend/src/components/Sidebar.tsx`

## Sub-tasks

### navigation.ts — populate SETTINGS_MENU

- [ ] Fill `SETTINGS_MENU` with:
  ```typescript
  [
    { name: 'Administration', icon: ShieldCheck, path: '/admin', requiresAdmin: true },
    { name: 'My Landing Zones', icon: Layers, path: '/my-access' },
  ]
  ```
- [ ] Verify `MODULE_MENU = [...MAIN_MENU, ...SETTINGS_MENU]` includes both items (getPageMeta compat)

### Sidebar.tsx — Settings section render

- [ ] After the existing `<nav>` (main menu), add a Settings section block:
  ```tsx
  {/* Settings section */}
  <div className="px-2.5 pb-1">
    <hr className="border-border/50 mb-2" />
    {!isCollapsed && (
      <p className="px-2.5 pb-1 text-[0.65rem] font-bold uppercase tracking-widest text-muted-foreground/60">
        Settings
      </p>
    )}
    {settingsItems.map((item) => { /* same NavLink rendering as main nav items */ })}
  </div>
  ```
- [ ] Compute `settingsItems` via `filterModuleMenu(SETTINGS_MENU, user?.role)` (same pattern as `menuItems`)
- [ ] Add `requiresAdmin` hide guard: in the Settings section `.map()`, skip items where `item.requiresAdmin && !canAccess('page:admin')` — render `null`, no lock/dim
- [ ] Collapsed state: Settings items show as icon-only with `CollapsedTooltip` (same as main nav)
- [ ] Active state: `NavLink` isActive styling identical to main nav flat items

## Acceptance Criteria

- [ ] Sidebar renders a "Settings" section header (label + divider) below the main nav
- [ ] Admin user sees Administration + My Landing Zones in the Settings section
- [ ] Non-admin user sees only My Landing Zones (Administration completely absent from DOM)
- [ ] Clicking My Landing Zones navigates to `/my-access`
- [ ] Clicking Administration (when visible) navigates to `/admin`
- [ ] Collapsed sidebar: Settings items show icons + tooltips, no label visible
- [ ] Active route highlight works for Settings items
- [ ] `tsc --noEmit` exits 0
- [ ] `npm run lint` exits 0

## Tests

```bash
cd packages/dcm-frontend
npm run typecheck
npm run lint
npm run test -- --reporter=verbose
```

Vitest tests in `src/test/Sidebar.test.tsx`:
- Assert Settings section label renders
- Assert admin user sees 2 Settings items (Administration + My Landing Zones)
- Assert non-admin user sees 1 Settings item (My Landing Zones only, Administration absent)
- Assert My Landing Zones link href is `/my-access`

## Out of scope

- Databricks children restructure (T003)
- New placeholder pages (T003)
- Any backend permission changes

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] `tsc --noEmit` exits 0
- [ ] `npm run lint` exits 0
- [ ] `npm run test` passes
- [ ] No files outside `packages/dcm-frontend` modified
- [ ] `requiresAdmin` guard removes item from DOM (not dim/lock)

## Notes

- `requiresAdmin` guard is a Sidebar.tsx concern only — `filterModuleMenu` in `navigation-access.ts` handles `requiresSuperAdmin`, not `requiresAdmin`. Do not change `navigation-access.ts`.
- `canAccess('page:admin')` is the existing permission key for `/admin` route — verify in `ROUTE_PERMISSIONS` config (R3 in research.md).
- The "Settings" section label should not be visible when sidebar is collapsed — hide with `{!isCollapsed && ...}` guard (same pattern as user name/email in the user menu).
