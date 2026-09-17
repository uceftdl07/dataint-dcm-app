# Implementation Plan: DCM Navigation v2 — Sidebar Cleanup & Restructure

**Branch**: `011-nav-v2-cleanup` | **Date**: 2026-07-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/011-nav-v2-cleanup/spec.md`

## Summary

Restructure the DCM frontend sidebar from a single flat navigation list into two distinct sections (main nav + Settings), reduce visible main items to 3 (Home, Databricks, Talk to your Data), and replace the Databricks submenu with a v2 hierarchy (Lakeflow, Compute, FinOps, Usage Data Product) backed by 6 new placeholder routes. All previously visible pages remain accessible via direct URL — only nav config entries change.

**Technical approach**: Extend `ModuleMenuItem` type with a `section` discriminant; extend `MenuChild` with optional `groupHeader` flag for Lakeflow/Compute labels; split `Sidebar.tsx` `<nav>` into two sections; add 6 new placeholder routes to `app-routes.ts` before the existing `/databricks/:view` catch-all.

## Technical Context

**Language/Version**: TypeScript 5.x strict + React 18

**Primary Dependencies**: React Router v6, Lucide React, Tailwind CSS, clsx/cn, `@azure/msal-react`

**Storage**: N/A — client-side navigation config only

**Testing**: Vitest + React Testing Library (existing test suite in `packages/dcm-frontend/src/test/`)

**Target Platform**: Browser — desktop-first, responsive (existing collapsed/expanded sidebar logic unchanged)

**Project Type**: Web application — frontend only (`packages/dcm-frontend`)

**Performance Goals**: Placeholder pages are static (no API calls, no data fetching) — instant render

**Constraints**: `tsc --noEmit` exits 0; zero ESLint warnings; all existing Vitest tests pass; no `any` in committed TypeScript

**Scale/Scope**: 3 files modified (navigation.ts, Sidebar.tsx, app-routes.ts) + 1 new placeholder component + 6 new routes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

[Gates determined based on constitution file]

## Project Structure

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| P1 — Test-First & Code Quality | ✅ PASS | Vitest tests required for Sidebar two-section render + nav item count (SC-001, SC-002). Tests must be written for new behavior. |
| P2 — Simplicity & Explicitness | ✅ PASS | Minimal type extension only. No new abstractions beyond `section` discriminant + `groupHeader` flag. YAGNI respected — placeholder pages are one shared component. |
| P3 — Self-Documenting Code | ✅ PASS | Type names are explicit (`section: 'main' \| 'settings'`, `groupHeader: true`). No docstrings needed. |
| P7/P8 — No Secrets | ✅ PASS | Frontend nav only. No secrets involved. |
| P9 — No Fake Data in Production | ✅ PASS | Placeholder pages are empty-state UI scaffolding, not fake data. No test fixtures in production paths. |
| P16 — Frontend Quality | ✅ PASS | Routes declared in `app-routes.ts`. No `any`. Strict mode. TanStack Query not used (static pages). Vitest tests required. |

**No violations. No complexity justification needed.**

## Project Structure

### Documentation (this feature)

```text
specs/011-nav-v2-cleanup/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output — TypeScript type contracts
├── quickstart.md        # Phase 1 output — nav authoring guide
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (files touched)

```text
packages/dcm-frontend/src/
├── config/
│   └── navigation.ts              # MODIFY — new MODULE_MENU structure + SETTINGS_MENU
├── components/
│   └── Sidebar.tsx                # MODIFY — split nav into main + settings sections
├── app-routes.ts                  # MODIFY — add 6 new Databricks placeholder routes
└── pages/
    └── DatabricksComingSoon.tsx   # CREATE — shared placeholder page (1 component, title prop)

packages/dcm-frontend/src/test/
└── Sidebar.test.tsx               # CREATE or MODIFY — tests for two-section rendering
```

**Structure Decision**: Single frontend package. No backend changes. One new page component shared across all 6 new Databricks placeholder routes (props: `title`, `description`).

## Complexity Tracking

> No violations — no justification needed.
