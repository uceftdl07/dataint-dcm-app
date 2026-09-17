# T003 — Databricks v2 Sub-Navigation + Placeholder Pages

**Domain**: Frontend
**Package**: `packages/dcm-frontend`
**Branch**: `frontend/011-databricks-v2-subnav`
**Jira**: DCINT-198
**Depends on**: T001 (Databricks entry in MAIN_MENU), T002 (isGroupHeader rendering logic in Sidebar.tsx)
**Work type**: feature

## Description

Restructure the Databricks submenu in `MAIN_MENU` to the v2 hierarchy (Lakeflow group, Compute group, FinOps, Usage Data Product). Add `isGroupHeader` rendering logic to `Sidebar.tsx` children loop. Create a single shared placeholder page `DatabricksComingSoon.tsx` that derives its title from the current pathname. Register 6 new routes in `app-routes.ts` **before** the `/databricks/:view` catch-all. All existing Databricks routes remain registered.

## Files to create/modify

- UPDATE `packages/dcm-frontend/src/config/navigation.ts`
- UPDATE `packages/dcm-frontend/src/components/Sidebar.tsx`
- UPDATE `packages/dcm-frontend/src/app-routes.ts`
- CREATE `packages/dcm-frontend/src/pages/DatabricksComingSoon.tsx`

## Sub-tasks

### navigation.ts — Databricks children v2

- [ ] Replace the Databricks `children` array in `MAIN_MENU` with:
  ```typescript
  children: [
    { label: 'Lakeflow',      path: '',                              isGroupHeader: true },
    { label: 'Pipelines',     path: '/databricks/pipelines',        title: 'Lakeflow Pipelines' },
    { label: 'Workflows',     path: '/databricks/workflows',        title: 'Lakeflow Workflows' },
    { label: 'Compute',       path: '',                              isGroupHeader: true },
    { label: 'Cluster',       path: '/databricks/cluster',          title: 'Compute — Cluster' },
    { label: 'SQL Warehouse', path: '/databricks/sql-warehouse',    title: 'Compute — SQL Warehouse' },
    { label: 'FinOps',             path: '/databricks/finops-v2',          title: 'Databricks FinOps' },
    { label: 'Usage Data Product', path: '/databricks/data-product-usage', title: 'Usage Data Product' },
  ]
  ```
- [ ] Verify old Databricks children (Dashboard, Alerts, Governance, etc.) are removed from this array — their routes in `app-routes.ts` stay registered

### Sidebar.tsx — isGroupHeader rendering

- [ ] In the `item.children.map()` loop, add group header rendering before the existing `NavLink`:
  ```tsx
  if (child.isGroupHeader) {
    return (
      <p
        key={child.label}
        className="px-3 pb-1 pt-2 text-[0.65rem] font-bold uppercase tracking-widest text-muted-foreground/60"
        aria-hidden
      >
        {child.label}
      </p>
    );
  }
  ```
- [ ] Group header: not focusable, not tabbable (`aria-hidden`), no hover state, no `to` prop

### DatabricksComingSoon.tsx — placeholder page

- [ ] Create `packages/dcm-frontend/src/pages/DatabricksComingSoon.tsx`:
  - Import `useLocation` from react-router-dom
  - Define a lookup map `PAGE_META` for the 6 known pathnames → `{ title, group }`:
    ```typescript
    const PAGE_META: Record<string, { title: string; group: string }> = {
      '/databricks/pipelines':          { title: 'Pipelines',          group: 'Lakeflow' },
      '/databricks/workflows':          { title: 'Workflows',          group: 'Lakeflow' },
      '/databricks/cluster':            { title: 'Cluster',            group: 'Compute' },
      '/databricks/sql-warehouse':      { title: 'SQL Warehouse',      group: 'Compute' },
      '/databricks/finops-v2':          { title: 'FinOps',             group: 'Databricks' },
      '/databricks/data-product-usage': { title: 'Usage Data Product', group: 'Databricks' },
    };
    ```
  - Render an empty-state UI: section title, group badge, "Coming soon" message
  - No API calls, no TanStack Query, no data fetching
  - Use existing `Content`, `ContentTitle`, `ContentMain` layout components (already used by other pages)

### app-routes.ts — 6 new routes

- [ ] Add the 6 new routes **immediately before** the existing `{ path: '/databricks/:view', importPage: () => import('./pages/DatabricksFocusPage') }` entry:
  ```typescript
  { path: '/databricks/pipelines',          importPage: () => import('./pages/DatabricksComingSoon') },
  { path: '/databricks/workflows',          importPage: () => import('./pages/DatabricksComingSoon') },
  { path: '/databricks/cluster',            importPage: () => import('./pages/DatabricksComingSoon') },
  { path: '/databricks/sql-warehouse',      importPage: () => import('./pages/DatabricksComingSoon') },
  { path: '/databricks/finops-v2',          importPage: () => import('./pages/DatabricksComingSoon') },
  { path: '/databricks/data-product-usage', importPage: () => import('./pages/DatabricksComingSoon') },
  ```
- [ ] Verify the order: all 6 come before `/databricks/:view` (React Router v6 matches first)
- [ ] Do NOT remove any existing routes

## Acceptance Criteria

- [ ] Databricks submenu shows: Lakeflow (label), Pipelines, Workflows, Compute (label), Cluster, SQL Warehouse, FinOps, Usage Data Product
- [ ] Lakeflow and Compute labels are non-clickable, non-focusable visual separators
- [ ] Clicking each of the 6 leaf items renders `DatabricksComingSoon.tsx` with the correct section title
- [ ] `DatabricksComingSoon.tsx` renders with no console errors and no API calls
- [ ] Old routes `/databricks`, `/databricks/alerts`, `/databricks/finops`, `/databricks/governance`, `/databricks/insights`, `/unitycatalogexplorer`, `/data-product-usage`, `/monitoringreports` still load their existing pages when accessed by URL
- [ ] `tsc --noEmit` exits 0
- [ ] `npm run lint` exits 0
- [ ] All existing Vitest tests pass

## Tests

```bash
cd packages/dcm-frontend
npm run typecheck
npm run lint
npm run test -- --reporter=verbose
```

Vitest tests in `src/test/Sidebar.test.tsx` (or `DatabricksComingSoon.test.tsx`):
- Assert Databricks submenu renders 6 leaf links (not 8 old children)
- Assert Lakeflow and Compute headers are non-interactive elements (no `href`, `role=button`)
- Assert `/databricks/pipelines` link renders in the expanded Databricks menu

## Out of scope

- Functional implementation of any Databricks section (future sprint)
- Connecting placeholder pages to real APIs
- Any changes to existing Databricks pages (DatabricksFinOps.tsx, DatabricksAlerts.tsx, etc.)

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] `tsc --noEmit` exits 0
- [ ] `npm run lint` exits 0
- [ ] `npm run test` passes (no regressions + new tests)
- [ ] No files outside `packages/dcm-frontend` modified
- [ ] New routes are ordered before `/databricks/:view` catch-all in `app-routes.ts`
- [ ] Old Databricks routes NOT removed from `app-routes.ts`

## Notes

- Route conflict: `/databricks/finops` is already taken by legacy `DatabricksFinOps`. New route uses `/databricks/finops-v2` (R4 in research.md). Will be renamed to `/databricks/finops` in a future sprint when the legacy page is deprecated.
- Route `/data-product-usage` (legacy) stays hidden from nav but route remains. New route `/databricks/data-product-usage` is a separate entry pointing to the placeholder.
- `DatabricksComingSoon.tsx` is intentionally named to communicate its temporary nature. Future sprint will replace it per section with a real implementation.
- Use the existing `Content` / `ContentTitle` / `ContentMain` / `ContentDescription` layout components (same import pattern as `Dashboard.tsx`).
