# T001 — Frontend Inactive Cluster Widget on Dashboard

**Domain**: frontend  
**Package**: `packages/dcm-frontend`  
**Branch**: `frontend/009-inactive-cluster-widget`  
**Jira**: [DCINT-160](https://tdf.atlassian.net/browse/DCINT-160)  
**Depends on**: none  
**Work type**: feature  
**Priority**: P2

---

## Description

Add a "Inactive clusters" MetricCard to the Dashboard metrics row. The card shows the count of compute resources whose latest observed state is `terminated`, derived from the already-fetched `data.computes` array (no additional API request). The card uses a warning tone when count > 0, success when 0, and navigates to the Clusters inventory page filtered on `state=terminated` on click. Gated behind the existing `DASHBOARD_WIDGET_PERMISSIONS.clusters` permission.

---

## Files to create/modify

- **UPDATE** `packages/dcm-frontend/src/pages/Dashboard.tsx`  
  — import `PowerOff` from `lucide-react`  
  — import `buildClustersFocusPath` from `../lib/clusters/focus-view`  
  — compute `inactiveClusterCount` from `data.computes`  
  — add MetricCard in the metrics grid after the existing "Active clusters" card  

- **UPDATE** `packages/dcm-frontend/src/pages/Dashboard.test.tsx`  
  — add regression test: verify "Inactive clusters" card renders with correct count

---

## Sub-tasks

- [ ] Import `PowerOff` from `lucide-react` in `Dashboard.tsx` (add to existing destructuring at top)
- [ ] Import `buildClustersFocusPath` from `../lib/clusters/focus-view` in `Dashboard.tsx`
- [ ] Compute `inactiveClusterCount` inside Dashboard component (derived from `data.computes`):
  ```tsx
  const inactiveClusterCount = data ? data.computes.filter((c) => c.state === 'terminated').length : 0;
  ```
- [ ] Add MetricCard to the Dashboard metrics grid, after the existing "Active clusters" `<AccessGate>` block:
  ```tsx
  <AccessGate allowed={canAccess(DASHBOARD_WIDGET_PERMISSIONS.clusters)} resourceLabel="inactive cluster metrics" compact>
    <MetricCard
      label="Inactive clusters"
      value={inactiveClusterCount}
      description="Terminated compute"
      icon={<PowerOff />}
      tone={inactiveClusterCount > 0 ? 'warning' : 'success'}
      onClick={() => navigate(buildClustersFocusPath('inventory', { state: 'terminated' }))}
    />
  </AccessGate>
  ```
- [ ] Add test in `Dashboard.test.tsx`: when `data.computes` contains terminated items, "Inactive clusters" card appears with the correct count

---

## Acceptance Criteria

- [ ] "Inactive clusters" MetricCard visible in Dashboard metrics row for users with cluster access permission
- [ ] Count matches number of `terminated` items in `data.computes`
- [ ] Tone is `warning` when count > 0, `success` when count is 0
- [ ] Clicking navigates to `/clusters/inventory?state=terminated`
- [ ] When `data` is null/loading, the card renders in skeleton state (inherited from grid behavior — no extra code)
- [ ] No TypeScript errors, ruff/lint clean

---

## Tests

```bash
cd packages/dcm-frontend
npm run test -- --reporter=verbose src/pages/Dashboard.test.tsx
```

Test file: `packages/dcm-frontend/src/pages/Dashboard.test.tsx`

---

## Out of scope

- Backend changes (API already supports `state=terminated`)
- New TanStack Query hook (derive from existing `data.computes`)
- New dashboard bundle query field
- Workspace-filter scoping (dashboard's existing workspace filter already scopes `data.computes`)

---

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] `npm run build` passes (0 errors)
- [ ] `npm run test` passes (Dashboard.test.tsx)
- [ ] No files outside `packages/dcm-frontend` modified
- [ ] Sub-spec checkboxes above all ticked

---

## Notes

- `data.computes` comes from `useDashboardQueries` — it's the full compute list scoped by the active workspace/LZ filter. No extra API call needed.
- `buildClustersFocusPath('inventory', { state: 'terminated' })` → `/clusters/inventory?state=terminated` (existing utility, already used on Clusters.tsx line 47).
- `DASHBOARD_WIDGET_PERMISSIONS.clusters` = `'widget:dashboard:clusters'` — reuse existing gate; no new permission key needed.
- Dashboard.tsx currently imports from `lucide-react`: `AlertTriangle, BarChart3, CalendarDays, CheckCircle2, Cloud, Database, DollarSign, Factory, LayoutDashboard, RefreshCw, Server, ShieldCheck, Workflow` — add `PowerOff` to this list.
- Grid currently has 7 MetricCards (7-col grid `2xl:grid-cols-7`). Adding an 8th will shift layout to next line or require grid adjustment — check if `2xl:grid-cols-8` or accept wrapping.
