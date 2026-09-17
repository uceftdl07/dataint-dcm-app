# Tasks: Frontend Quality Hardening

**Input**: Design documents from `/specs/002-frontend-quality-hardening/`

**Prerequisites**: `spec.md`, `plan.md`

**Tests**: Required. This feature is explicitly about improving frontend quality and must introduce a reliable test baseline.

**Organization**: Tasks are grouped by user story to enable independent implementation and review.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and has no dependency on incomplete work.
- **[Story]**: Which user story the task maps to.
- Each task includes exact file paths where possible.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Prepare the frontend package for testable, incremental quality work.

- [x] T001 Inspect current frontend dependency lock/package manager state in `packages/dcm-frontend/` and confirm whether to use `npm` for this package.
- [x] T002 Add frontend test dependencies in `packages/dcm-frontend/package.json`: `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`.
- [x] T003 Add a `test` script and, if useful, a `test:watch` script in `packages/dcm-frontend/package.json`.
- [x] T004 Configure Vitest jsdom environment in `packages/dcm-frontend/vite.config.ts` or a dedicated `packages/dcm-frontend/vitest.config.ts`.
- [x] T005 [P] Create Testing Library setup file in `packages/dcm-frontend/src/test/setup.ts`.
- [x] T006 [P] Create test helpers/wrappers for React Router, MSAL-safe rendering and common providers in `packages/dcm-frontend/src/test/render.tsx`.
- [x] T007 [P] Create API fixture data for dashboard/domain tests in `packages/dcm-frontend/src/test/fixtures/dashboard.ts`.

**Checkpoint**: `npm run test` can execute even if only setup smoke tests exist.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish shared patterns before user story implementation.

- [x] T008 Add `@tanstack/react-query` to `packages/dcm-frontend/package.json` after team validation.
- [x] T009 Add a Query Client provider near the app root in `packages/dcm-frontend/src/main.tsx` or `packages/dcm-frontend/src/App.tsx`.
- [x] T010 [P] Create query key helpers in `packages/dcm-frontend/src/hooks/query-keys.ts`.
- [x] T011 [P] Create a reusable query test wrapper in `packages/dcm-frontend/src/test/query-client.tsx`.
- [x] T012 Define frontend quality conventions in `packages/dcm-frontend/README.md` or a dedicated section to guide tests, query hooks and routing changes.

**Checkpoint**: Foundation ready. User story work can proceed.

---

## Phase 3: User Story 1 - Socle de tests frontend fiable (Priority: P1) MVP

**Goal**: Add a meaningful automated test baseline that protects critical UI behavior.

**Independent Test**: Run `npm run test` from `packages/dcm-frontend` and see green tests covering component rendering, loading and error states.

### Tests for User Story 1

- [x] T013 [P] [US1] Add tests for domain metric/card rendering in `packages/dcm-frontend/src/components/domain/metric-card.test.tsx`.
- [x] T014 [P] [US1] Add tests for shared error/loading states in `packages/dcm-frontend/src/components/domain/states.test.tsx`.
- [x] T015 [P] [US1] Add tests for a UI component used broadly, such as `packages/dcm-frontend/src/components/ui/button.test.tsx`.
- [x] T016 [US1] Add a dashboard page smoke test with mocked API data in `packages/dcm-frontend/src/pages/Dashboard.test.tsx`.

### Implementation for User Story 1

- [x] T017 [US1] Adjust component exports or test helpers only where necessary to make tests clean without changing runtime behavior.
- [x] T018 [US1] Ensure tests do not call real network APIs by mocking `packages/dcm-frontend/src/api/dcmApiClient.ts`.
- [x] T019 [US1] Run and fix `npm run test`, `npm run lint` and `npm run build` from `packages/dcm-frontend`.

**Checkpoint**: Frontend has a reliable minimal test suite.

---

## Phase 4: User Story 2 - Server state API standardisé (Priority: P2)

**Goal**: Prove TanStack Query on the `Dashboard` page without changing user-visible behavior.

**Independent Test**: Dashboard tests pass for success, loading, error and refetch scenarios with API mocks.

### Tests for User Story 2

- [x] T020 [P] [US2] Add tests for dashboard query key generation in `packages/dcm-frontend/src/hooks/query-keys.test.ts`.
- [x] T021 [US2] Extend `packages/dcm-frontend/src/pages/Dashboard.test.tsx` to cover success, loading, error and manual refresh behavior.

### Implementation for User Story 2

- [x] T022 [US2] Create dashboard query hook(s) in `packages/dcm-frontend/src/hooks/useDashboardQueries.ts`.
- [x] T023 [US2] Refactor `packages/dcm-frontend/src/pages/Dashboard.tsx` to use dashboard query hook(s) instead of manual `useState` + `useEffect` API orchestration.
- [x] T024 [US2] Preserve existing cloud provider, time range and monitoring scope parameter behavior in `packages/dcm-frontend/src/pages/Dashboard.tsx`.
- [x] T025 [US2] Ensure dashboard loading, error and refresh UI remains visible and accessible.
- [x] T026 [US2] Run `npm run test`, `npm run lint` and `npm run build` from `packages/dcm-frontend`.

**Checkpoint**: Dashboard server state pattern is ready to replicate on other pages later.

---

## Phase 5: User Story 3 - Routing et performance initiale allégés (Priority: P3)

**Goal**: Simplify protected route declarations and lazy-load protected pages.

**Independent Test**: Existing routes still render the same pages and unauthenticated users remain protected.

### Tests for User Story 3

- [x] T027 [US3] Add route configuration tests or app smoke tests for representative public/protected routes in `packages/dcm-frontend/src/App.test.tsx`.

### Implementation for User Story 3

- [x] T028 [US3] Extract protected route metadata into a route config inside `packages/dcm-frontend/src/App.tsx` or `packages/dcm-frontend/src/routes.tsx`.
- [x] T029 [US3] Replace eager protected page imports with `React.lazy` in `packages/dcm-frontend/src/App.tsx` or `packages/dcm-frontend/src/routes.tsx`.
- [x] T030 [US3] Add `Suspense` fallback using existing loading UI in `packages/dcm-frontend/src/App.tsx`.
- [x] T031 [US3] Preserve `MounirPageBubble`, `ProtectedRoute`, `ProtectedLayout` and all existing route paths.
- [x] T032 [US3] Run `npm run test`, `npm run lint` and `npm run build` from `packages/dcm-frontend`.

**Checkpoint**: Routing is easier to maintain and initial loading is lighter.

---

## Phase 6: User Story 4 - Tooling, sécurité client et documentation à jour (Priority: P4)

**Goal**: Finalize durable project quality practices.

**Independent Test**: Documentation matches scripts and sensitive auth logs are absent.

### Tests for User Story 4

- [x] T033 [US4] Add or update tests around API client error handling where practical in `packages/dcm-frontend/src/api/dcmApiClient.test.ts`.

### Implementation for User Story 4

- [x] T034 [US4] Remove or guard verbose token/auth console logs in `packages/dcm-frontend/src/api/dcmApiClient.ts`.
- [x] T035 [US4] Add a typecheck script to `packages/dcm-frontend/package.json` if missing.
- [x] T036 [US4] Add Prettier configuration and scripts in `packages/dcm-frontend/package.json` if approved by the team.
- [x] T037 [US4] Add Husky/lint-staged pre-commit workflow if approved by the team.
- [x] T038 [US4] Update `packages/dcm-frontend/README.md` with accurate setup, scripts, routes, env vars, testing and conventions.
- [x] T039 [US4] Run final `npm run lint`, `npm run build`, `npm run test` and typecheck script from `packages/dcm-frontend`.

**Checkpoint**: Quality gates and docs are aligned with the actual frontend.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final consistency checks before implementation is considered complete.

- [x] T040 [P] Update `specs/002-frontend-quality-hardening/plan.md` if implementation choices differ from the original plan.
- [x] T041 [P] Update `specs/002-frontend-quality-hardening/tasks.md` by checking completed tasks as work is implemented.
- [x] T042 Verify no unrelated large refactor or file movement was introduced outside `packages/dcm-frontend`. Tracked implementation diff is scoped to `packages/dcm-frontend`; existing untracked non-frontend files were left untouched.
- [x] T043 Verify no frontend code logs secrets, bearer tokens, auth headers or token lengths.
- [x] T044 Prepare a short PR summary linking user stories to completed tasks and validation commands.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Phase 1.
- **US1 Tests (Phase 3)**: depends on Phase 1.
- **US2 Query migration (Phase 4)**: depends on Phase 2 and benefits from US1 test helpers.
- **US3 Routing/lazy loading (Phase 5)**: depends on Phase 1 and should coordinate with Phase 2 because both can touch app root files.
- **US4 Tooling/docs/security (Phase 6)**: can partially run after Phase 1, but final scripts depend on completed test/build setup.
- **Polish (Phase 7)**: depends on selected user stories being complete.

### Parallel Opportunities

- T005, T006 and T007 can run in parallel.
- T010, T011 and T012 can run in parallel.
- T013, T014 and T015 can run in parallel.
- T034 and T038 can run in parallel after test setup is available.
- Documentation/spec updates in T040 and T041 can run in parallel with final validation.

## Implementation Strategy

### MVP First

1. Complete Phase 1.
2. Complete Phase 3 (US1).
3. Stop and validate tests, lint and build.

### Incremental Delivery

1. Deliver test baseline.
2. Deliver dashboard TanStack Query migration.
3. Deliver route config/lazy loading.
4. Deliver security/tooling/docs.

### Recommended PR Split

- PR 1: Test infrastructure + first tests.
- PR 2: TanStack Query provider + dashboard migration.
- PR 3: Route config + lazy loading.
- PR 4: API log cleanup + README/tooling.

