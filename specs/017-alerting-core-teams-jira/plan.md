# Implementation Plan: Alerting Module Core - Teams and Jira

**Branch**: `017-alerting-core-teams-jira` | **Date**: 2026-08-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/017-alerting-core-teams-jira/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Deliver Teams and Jira alerting for persisted anomaly incidents. Databricks Alert Trigger calls backend Alerting Service directly; the backend reads Unity Catalog data through SQL Warehouse access and fans out channels independently with one retry per failed delivery.

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Python 3.12; React 18 + TypeScript strict

**Primary Dependencies**: FastAPI, asyncpg, Pydantic, AWS Secrets Manager SDK, Jira REST API, Teams webhook, TanStack Query

**Storage**: Unity Catalog Delta tables for project-owned channel/config data and anomaly report alert fields; AWS Secrets Manager for secrets

**Testing**: pytest + pytest-asyncio; Vitest; mocked Unity Catalog access, AWS Secrets Manager, Teams, and Jira calls; ruff/mypy and ESLint/tsc

**Target Platform**: Backend ECS Fargate, Databricks jobs, React browser client

**Project Type**: Multi-package API, data job, and web application

**Performance Goals**: Process two-channel fan-out independently without one channel blocking the other

**Constraints**: One retry then log/discard; direct backend delivery identity; no raw secrets in storage; authenticated APIs; project-scoped channels; no cross-LZ calls; Email/MailJet deferred

**Scale/Scope**: Teams/Jira channels, per-rule configurations, incident/resolution/reminder notifications, three domain-owned Stories, two frontend configuration surfaces

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Pass. Design follows P1 (tests), P4 (visible failure), P5 (modularity), P6 (idempotency), P7/P8 (managed secrets), P10 (structured observability), P15 (versioned APIs), and P16 (React/TanStack Query). No complexity exception required.

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
├── pipelines/ or src/        # reminder/resend job and table changes
└── tests/
packages/dcm-backend/
├── dcm_backend/alerting/      # direct dispatch orchestrator and channels
├── dcm_backend/api/           # versioned config and notify routes
└── tests/
packages/dcm-commons/
└── dcm_commons/models/        # shared alerting contracts
packages/dcm-frontend/
├── src/pages/                 # Notification Settings
├── src/components/            # Alert Config Dialog
├── src/hooks/                 # TanStack Query hooks
└── tests/
```

**Structure Decision**: Keep data-job ownership in `dcm-databricks-pipeline`, delivery/API orchestration in `dcm-backend`, shared contracts in `dcm-commons`, and configuration UI in `dcm-frontend`. Each task stays within its domain package boundary.

## Complexity Tracking

No constitution violations. No complexity exception required.
