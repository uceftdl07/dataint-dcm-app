# DCM Review Report — T001

**Package**: `packages/dcm-frontend`  
**Branch**: `frontend/011-main-nav-simplification` (rebased on `origin/develop`)  
**Story**: [DCINT-196](https://tdf.atlassian.net/browse/DCINT-196)  
**Epic**: [DCINT-195](https://tdf.atlassian.net/browse/DCINT-195)  
**Stack**: frontend  

## Verdict (scoped T001): **PASS**

Full-package `dcm-review.sh` still **FAIL** on **pre-existing develop debt** (not introduced by this PR):
- eslint: unrelated `dashboards` useMemo warning
- tsc: `MyLandingZones.tsx` typing errors already on develop
- vitest: `Databricks.tsx` crash already on develop

### Scoped gates (T001 files only)

| Gate | Status | Detail |
|------|--------|--------|
| eslint | PASS | `navigation.ts`, `Sidebar.tsx`, `Sidebar.test.tsx` — max-warnings 0 |
| typescript | PASS | no errors in T001 files |
| vitest | PASS | Sidebar.test + navigation-access — 4/4 |
| app-routes | PASS | unchanged |

## Changed files

```
packages/dcm-frontend/src/config/navigation.ts
packages/dcm-frontend/src/components/Sidebar.tsx
packages/dcm-frontend/src/components/Sidebar.test.tsx
```

## Acceptance criteria (sub-spec)

| AC | Status |
|----|--------|
| Main nav = exactly 3 items (Home, Databricks, Talk to your Data) | ✅ MAIN_MENU length 3 + Sidebar test |
| Label "Talk to your Data" | ✅ |
| Hidden routes not in nav (`/costs`, `/security`, …) | ✅ Sidebar test |
| `app-routes.ts` untouched | ✅ |
| Routes still load via URL | ✅ (no route deletions) |
| `isGroupHeader` on MenuChild | ✅ (for T003) |
| SETTINGS_MENU placeholder empty | ✅ |

## Skill check (dcm-react)

- No secrets, no unrelated refactors
- Scope ⊆ `packages/dcm-frontend`
- Tests via `renderWithProviders` + mocks (MSAL/theme/tour)
- No API / TanStack changes

## Next

- Undraft PR #151 → team review
- Then implement T002 on `frontend/011-settings-section`
