# Implementation Plan: Anomaly System Core

**Branch**: `016-anomaly-system-core` | **Date**: 2026-08-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/016-anomaly-system-core/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Build the anomaly detection core across all six DCM metric domains. A scheduled Databricks evaluator loads active rules from Unity Catalog, evaluates current metrics, and persists idempotent incident state. Backend APIs expose rule/report management, while React pages provide rule and report workflows.

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Python 3.12; React 18 + TypeScript strict

**Primary Dependencies**: PySpark/Databricks, FastAPI, asyncpg, Pydantic, TanStack Query

**Storage**: Unity Catalog Delta tables for `anomaly_rules` and `anomaly_reports`; Lakebase PostgreSQL read/API projection where required by existing DCM architecture

**Testing**: pytest + pytest-asyncio for Python; Vitest for React; ruff/mypy and ESLint/tsc gates

**Target Platform**: Databricks serverless/job compute, backend ECS Fargate, frontend browser

**Project Type**: Multi-package data pipeline, API, and web application

**Performance Goals**: Breach visible within one 15-minute evaluator cycle; reports list/filter under 2 seconds for 1000+ reports per LZ

**Constraints**: No cross-LZ calls; authenticated APIs; no hardcoded secrets; idempotent evaluator; structured error logging; alerting side effects deferred to Spec 017

**Scale/Scope**: Six metric domains, scheduled evaluation, company and custom rules, active-incident uniqueness per `(rule_id, lz_id)`, two frontend pages

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Pass. Design follows P1 (tests), P4 (visible failures), P5 (modularity), P6 (idempotency), P7/P8 (managed secrets), P10 (structured observability), P15 (versioned APIs), and P16 (React/TanStack Query conventions). No complexity exception required.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
packages/dcm-databricks-pipeline/
├── pipelines/ or src/        # evaluator job and Delta transformations
├── schemas/                  # DDL extensions where applicable
└── tests/
packages/dcm-backend/
├── dcm_backend/api/          # versioned rules and reports routes
├── dcm_backend/services/     # evaluator ingress and domain services
└── tests/
packages/dcm-commons/
└── dcm_commons/models/       # shared enums and Pydantic contracts
packages/dcm-frontend/
├── src/pages/                # Anomaly Rules and Reports
├── src/hooks/                # TanStack Query hooks
└── src/components/
```

**Structure Decision**: Extend existing DCM packages by ownership boundary. Shared models remain in `dcm-commons`; evaluator logic stays in the Databricks package; API logic stays in backend; UI and mocked Vitest tests stay in frontend. Each dispatched story touches one package.

## Complexity Tracking

No constitution violations. No complexity exception required.
