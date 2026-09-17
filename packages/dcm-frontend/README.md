# dcm-frontend — React TypeScript Frontend

**Status:** Active application, with the frontend quality foundation being hardened
**Type :** Application React 18 TypeScript
**Build tool :** Vite 5
**Deployment:** S3 (Building Block WEB_2) + CloudFront
**AWS account:** awss-wl-dcm (551656632516)
**Dev port:** 4000

---

## Role

User interface for the DCM Dashboard.
Displays multi-cloud metrics (Azure + AWS) in real time.
Authenticates through Microsoft Entra ID (MSAL.js OIDC — optional in development).
Calls `dcm-backend` through AWS API Gateway.

---

## Commands

From `packages/dcm-frontend`:

```bash
npm install
npm run dev        # Vite on http://localhost:4000
npm run lint       # ESLint strict, zero warning
npm run typecheck  # TypeScript noEmit
npm run format     # Prettier write
npm run format:check # Prettier check only
npm run test       # Vitest + Testing Library
npm run build      # Production build in dist/
npm run preview    # Build preview
```

Tests are hermetic: they mock the API client and must not call the real backend.
The Husky pre-commit hook runs `lint-staged` on staged files to apply ESLint/Prettier without rerunning the full suite.

---

## Code Structure

```
src/
├── main.tsx                    # Entry point, MSAL + QueryClientProvider
├── App.tsx                     # Router, protected layout, and page lazy loading
├── app-routes.ts               # Centralized protected route configuration
├── index.css                   # Tailwind CSS
│
├── config/
│   └── authConfig.ts           # MSAL.js config (clientId, dcm-backend scope)
│
├── api/
│   └── dcmApiClient.ts         # Fetch client → dcm-backend (all routes)
│
├── types/
│   └── api.ts                  # TypeScript types (mirror of dcm-backend responses)
│
├── contexts/
│   ├── MonitoringScopeContext.tsx
│   ├── TimeRangeContext.tsx    # Global time range
│   └── ToastContext.tsx
│
├── hooks/
│   ├── query-keys.ts           # Query keys TanStack Query
│   └── useDashboardQueries.ts  # First Dashboard server-state hook
│
├── components/
│   ├── Sidebar.tsx             # Dark sidebar navigation
│   ├── Header.tsx              # Global time range selector
│   ├── domain/                 # Reusable domain components
│   ├── layout/
│   └── ui/
│
├── pages/                      # Lazy-loaded pages behind ProtectedRoute
└── test/                       # Vitest setup, wrappers, and fixtures
```

---

## Routes

| Path                  | Page                | API Data                                                                 |
| --------------------- | ------------------- | ------------------------------------------------------------------------ |
| `/`                   | Public landing      | Auth/login                                                               |
| `/dashboard`          | Overview            | `GET /api/v1/dashboard/overview`, costs, pipelines, clusters, DB, alerts |
| `/pipelines`          | Pipelines           | `GET /api/v1/pipelines` + runs                                           |
| `/datafactory`        | Data Factory        | Pipeline/activity endpoints                                              |
| `/databricks`         | Databricks          | `GET /api/v1/clusters`                                                   |
| `/costs`              | Costs               | `GET /api/v1/costs/summary` + `/by-service`                              |
| `/databases`          | Databases           | `GET /api/v1/databases`                                                  |
| `/security`           | Security            | `GET /api/v1/security/alerts`                                            |
| `/governance`         | Gouvernance         | `GET /api/v1/standard-checks`                                            |
| `/data-product-usage` | Usage data products | `GET /api/v1/data-product-usage/*`                                       |
| `/talk-to-data`       | Talk to Data        | DataIQ conversational assistant (Intelligence Quotient)                  |
| `/status`             | Collection status   | `GET /api/v1/health`                                                     |
| `/settings`           | Settings            | UI configuration                                                         |

Preserved aliases:

- `/talk-to-your-data` redirects to `/talk-to-data`.
- `/collection-status` redirects to `/status`.

Protected routes are declared in `src/app-routes.ts`, rendered through `ProtectedRoute` + `ProtectedLayout`, and loaded with `React.lazy`.

---

## API Client — Key Patterns

### Base URL

```typescript
// Dev: Vite proxy /api → http://localhost:8080 (local dcm-backend)
// Prod: VITE_API_BASE_URL/api/v1 (API Gateway endpoint)
const API_BASE = import.meta.env.VITE_API_BASE_URL
  ? `${import.meta.env.VITE_API_BASE_URL}/api/v1`
  : '/api/v1';
```

### Token injection (Entra ID)

```typescript
// Registered from main.tsx after MSAL init
registerTokenGetter(async () => {
  const result = await pca.acquireTokenSilent({ scopes: dcmApiScopes, account });
  return result.accessToken;
});
```

### Typed Call

```typescript
import { getDashboardOverview } from '../api/dcmApiClient';
import type { DashboardOverview } from '../types/api';

const data: DashboardOverview = await getDashboardOverview({
  start_date: '2026-01-01',
  end_date: '2026-03-31',
});
```

### Server state Dashboard

`Dashboard.tsx` uses TanStack Query through `src/hooks/useDashboardQueries.ts`.
Query keys must include the business parameters that change the data: period, scope, and cloud provider.

### TimeRange global

```typescript
const { getApiParams } = useGlobalTimeRange();
const { start_date, end_date } = getApiParams(); // snake_case for dcm-backend
```

---

## Authentication

Entra ID MSAL.js — enabled through an environment variable.

```typescript
// .env
VITE_ENABLE_AUTH=true           // false in development
VITE_AZURE_TENANT_ID=...
VITE_AZURE_CLIENT_ID=...        // App Registration DCM Frontend
VITE_AZURE_SCOPE=api://dcm-backend/.default
```

The `VITE_ENABLE_AUTH=false` variable fully bypasses MSAL in development — no login required.

---

## Environment Variables

| Variable               | Description                                   | Default                      |
| ---------------------- | --------------------------------------------- | ---------------------------- |
| `VITE_API_BASE_URL`    | DCM API Gateway URL (empty = Vite proxy)      | —                            |
| `VITE_AZURE_TENANT_ID` | Tenant Entra ID                               | —                            |
| `VITE_AZURE_CLIENT_ID` | Client ID App Registration DCM Frontend       | —                            |
| `VITE_AZURE_SCOPE`     | JWT scope for dcm-backend                     | `api://dcm-backend/.default` |
| `VITE_REDIRECT_URI`    | Redirect URI after Entra ID login             | `window.location.origin`     |
| `VITE_ENABLE_AUTH`     | `true` = Entra ID required / `false` = bypass | `false`                      |

---

## Deployment

```bash
# Development (local dcm-backend on :8080)
cp .env.example .env
npm install
npm run dev        # → http://localhost:4000

# Local quality
npm run lint
npm run typecheck
npm run format:check
npm run test

# Build production
npm run build      # → dist/

# Deploy S3 + CloudFront
aws s3 sync dist/ s3://dcm-frontend-bucket/ --delete
aws cloudfront create-invalidation --distribution-id $CF_DIST_ID --paths "/*"
```

---

## Technical Stack

| Technology                     | Version | Usage                           |
| ------------------------------ | ------- | ------------------------------- |
| React                          | 18      | Framework UI                    |
| TypeScript                     | 5+      | Strict static typing            |
| Vite                           | 5       | Build tool (replaces CRA)       |
| Tailwind CSS                   | 3       | Utility styling                 |
| MSAL.js                        | 4       | Entra ID auth (optional)        |
| TanStack Query                 | 5       | API cache and server state      |
| Vitest + Testing Library       | 3 + 16  | Unit/integration tests          |
| Lucide React                   | latest  | Icons                           |
| React Router                   | 6       | Navigation SPA                  |
| clsx                           | 2       | Classes CSS conditionnelles     |
| Prettier + Husky + lint-staged | latest  | Formatting and pre-commit guard |

---

## Quality Conventions

- Add or update a test when a critical component, page, or query hook changes.
- Use `src/test/render.tsx` for React tests that need shared providers.
- Use `src/test/query-client.tsx` to isolate the TanStack Query cache between tests.
- Keep network calls in `src/api/dcmApiClient.ts`; pages use dedicated query hooks as they migrate to TanStack Query.
- Do not log tokens, `Authorization` headers, token lengths, or sensitive auth details on the client side.
- Keep public/protected routes in `src/app-routes.ts` when a new protected page is added.
- Run `npm run format:check` before review, or `npm run format` to fix style automatically.
- The pre-commit hook is intentionally targeted: `lint-staged` only handles files added to the commit.

---

## Dependencies

```json
"dependencies": {
  "@azure/msal-browser": "^4.0.0",
  "@azure/msal-react": "^3.0.0",
  "@tanstack/react-query": "^5.100.14",
  "clsx": "^2.0.0",
  "date-fns": "^3.0.0",
  "lucide-react": "^0.400.0",
  "react": "^18.3.0",
  "react-dom": "^18.3.0",
  "react-router-dom": "^6.24.0",
  "recharts": "^2.12.0"
}
```

The main test dependencies are `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/jest-dom`, and `@testing-library/user-event`.
