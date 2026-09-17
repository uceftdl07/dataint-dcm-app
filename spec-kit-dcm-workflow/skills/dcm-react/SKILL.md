---
name: dcm-react
description: >-
  DCM React/TypeScript best practices for AI agents. Machine-readable:
  compatibility matrix, Do/Don't, anti-patterns, quick reference. Use when
  writing or reviewing UI in packages/dcm-frontend — components, hooks, pages,
  Vitest, TanStack Query, MSAL.
compatibility: packages/dcm-frontend/
metadata:
  author: DCM Squad
  domain: frontend
---

# DCM React — Best Practices for AI Agents

Machine-readable companion for AI agents in `packages/dcm-frontend/`.

**Authority**: `packages/dcm-frontend/README.md`, `.specify/memory/constitution.md`

## Compatibility Matrix

| Dependency           | Minimum | DCM usage                                    |
|----------------------|---------|----------------------------------------------|
| Node.js              | 20      | CI + local dev                               |
| React                | 18      | Functional components + hooks only           |
| TypeScript           | 5.4     | strict — no `any` without comment            |
| Vite                 | 8       | Dev port 4000, proxy `/api` → backend        |
| Tailwind CSS         | 3.4     | Styling — no inline styles for layout        |
| TanStack Query       | 5       | All server state                             |
| React Router         | 6       | SPA — routes in `app-routes.ts`              |
| MSAL                 | 4       | Entra ID — optional in dev                   |
| Vitest               | 4       | Unit/component tests                         |
| Testing Library      | 16      | `@testing-library/react` + user-event          |
| ESLint               | 8       | zero warnings — `npm run lint`               |

## Project Structure

Respect layers — pages never call `fetch` directly.

```
packages/dcm-frontend/src/
├── api/
│   └── dcmApiClient.ts       # ALL HTTP — single source
├── types/
│   └── api.ts                # Mirror backend response shapes
├── hooks/
│   ├── query-keys.ts         # Key factories — include all filter dims
│   └── use*Queries.ts        # TanStack Query per domain
├── contexts/                 # MonitoringScope, TimeRange, Toast, Auth
├── components/               # Reusable UI + domain folders
├── pages/                    # Lazy-loaded behind ProtectedRoute
├── lib/                      # Pure utils (e.g. workspace-label.ts)
├── app-routes.ts             # Central route config
└── test/
    ├── render.tsx            # Custom render + providers
    ├── fixtures/             # Mock API responses
    └── setup.ts
```

## Data Fetching

### Do / Don't

```typescript
// DON'T — fetch in page component
function DashboardPage() {
  useEffect(() => {
    fetch('/api/v1/dashboard/overview').then(...);
  }, []);
}

// DO — api client + query hook
// hooks/useDashboardQueries.ts
export function useDashboardOverview(params: OverviewParams) {
  return useQuery({
    queryKey: dashboardKeys.overview(params),
    queryFn: () => getDashboardOverview(params),
  });
}

// pages/DashboardPage.tsx
function DashboardPage() {
  const { data, isLoading } = useDashboardOverview(params);
}
```

### API client rules

- Dev: relative `/api` (Vite proxy → `localhost:8080`)
- Prod: `VITE_API_BASE_URL/api/v1`
- Snake_case query params for backend (`start_date`, `workspace_ids`)
- Token via `registerTokenGetter` — never log tokens or `Authorization`

### Query keys

Include **every dimension** that changes data:

```typescript
export const databricksKeys = {
  workspaces: (lzIds: string[]) => ['databricks', 'workspaces', lzIds] as const,
  full: (params: DatabricksFullParams) => ['databricks', 'full', params] as const,
};
```

## Components

```typescript
// DO — accessible, readable labels
<button aria-label="Databricks workspace filter" ...>
  {resolveWorkspaceDisplayLabel(workspace)}
</button>

// DO — clsx for conditional classes
import clsx from 'clsx';
<span className={clsx('text-sm', isActive && 'font-semibold')} />

// DO — Lucide icons
import { ChevronDown } from 'lucide-react';
```

- Prefer human-readable **names** over raw IDs in UI
- Keep raw ID in `title` tooltip when useful for support/debug
- Reuse `components/ui/` primitives before new markup
- Global filters: `MonitoringScopeContext`, `TimeRangeContext`

## Routing

```typescript
// app-routes.ts — new protected page
{
  path: '/my-page',
  element: lazy(() => import('./pages/MyPage')),
  protected: true,
}
```

- Lazy load pages
- Wrap with `ProtectedRoute`
- Never add route only in component without `app-routes.ts`

## Testing

Hermetic — mock API, no real backend.

```typescript
import { render, screen } from '../test/render';
import { Header } from './Header';

it('shows workspace name not id when one selected', () => {
  render(<Header />, {
    route: '/databricks',
    workspaceFixtures: [{ workspace_id: 'adb-123', display_name: 'prod-eu' }],
  });
  expect(screen.getByLabelText('Databricks workspace filter')).toHaveTextContent('prod-eu');
  expect(screen.queryByText('adb-123')).not.toBeInTheDocument();
});
```

- Use `src/test/render.tsx` for providers (Query, Router, contexts)
- Use `src/test/fixtures/` for response mocks
- Mock `dcmApiClient` modules — not global `fetch`
- Isolate query cache between tests

### Run

```bash
cd packages/dcm-frontend
npm run test
npm run lint
npm run typecheck
npm run format:check
```

## Display Conventions

| Context | Show | Hide in label |
|---------|------|---------------|
| Workspace filter | `display_name` | `workspace_id` (tooltip OK) |
| LZ / cloud | Human label from API | Internal UUID if alias exists |
| Errors | User-friendly message | Stack traces |

Standard product terms in English: Databricks, FinOps, Unity Catalog.

---

## Anti-patterns — reject in review

| Anti-pattern | Why wrong | Fix |
|---|---|---|
| `fetch()` in page/component | Bypasses auth, types, mocks | `dcmApiClient` + hook |
| Query key missing filter param | Stale/wrong cache | Add param to key factory |
| `any` type | Breaks strict TS | Proper type from `types/api.ts` |
| New route without `app-routes.ts` | 404 / no auth | Register lazy route |
| Raw ID as visible label | Bad UX | `display_name` / resolver util |
| Missing `aria-label` on icon-only control | a11y fail | Add label |
| Logging auth token | Security | Remove console.log token |
| Inline styles for layout | Inconsistent UI | Tailwind classes |
| Test hits real API | Flaky CI | Mock client/fixtures |
| Duplicate API types | Drift from backend | Extend `types/api.ts` |

## Quick reference

| Scenario | Solution |
|----------|----------|
| New API call | Function in `dcmApiClient.ts` |
| Server state | TanStack Query hook in `hooks/` |
| Query key | Factory in `query-keys.ts` with all params |
| New page | `pages/` + entry in `app-routes.ts` |
| Pure label/format logic | `src/lib/` — unit test separately |
| Component test | `test/render.tsx` + fixtures |
| Conditional CSS | `clsx` |
| Global LZ/time filter | Context hooks |
| Workspace display | `display_name` not `workspace_id` |
| Lint + types | `npm run lint` + `npm run typecheck` |

## Spec-kit implement

When `/{speckit}implement T00X` on frontend task:
- Read `stories/T00X-*.md` only
- Branch `frontend/{slug}` from dispatch-manifest
- Files under `packages/dcm-frontend/` unless sub-spec says otherwise
- After code: `/speckit.dcm.review --task T00X` — load **`dcm-verify`** first
