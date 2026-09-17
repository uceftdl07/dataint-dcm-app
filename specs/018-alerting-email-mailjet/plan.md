# Implementation Plan: Alerting Module - Email/MailJet

**Branch**: `018-alerting-email-mailjet` | **Date**: 2026-08-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/018-alerting-email-mailjet/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Add Email/MailJet as the third alerting channel on top of Spec 017's direct backend fan-out. Reuse AlertingService, resolve credentials from AWS Secrets Manager through ECS task IAM, send incident/resolution templates, and keep email failures isolated from Teams/Jira.

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Python 3.12; React 18 + TypeScript strict

**Primary Dependencies**: FastAPI, Pydantic, `mailjet-rest`, AWS Secrets Manager SDK, existing AlertingService, TanStack Query, Vitest

**Storage**: Existing project-owned `notification_channels` table in Unity Catalog; AWS Secrets Manager for MailJet credentials; no new table or job

**Testing**: pytest + pytest-asyncio; Vitest; mocked MailJet/AWS Secrets Manager; after ITSM provisioning, sandbox MailJet authentication and send validation; ruff/mypy and ESLint/tsc

**Target Platform**: Backend ECS Fargate, existing direct Alerting Service, React browser client

**Project Type**: Incremental multi-package API and web application capability

**Performance Goals**: Email participates in existing fan-out without delaying or blocking Teams/Jira

**Constraints**: One retry then log/discard; no raw secrets; ITSM-provisioned sandbox in non-production; production disabled until MailJet account/domain verification; sender must be an approved shared mailbox; direct fan-out only, no new queue/worker/orchestrator

**Scale/Scope**: One email channel implementation, incident/resolution/test email templates, recipient validation, existing settings/config UI extension, and post-provisioning MailJet API validation

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Pass. Design follows P1 (tests), P4 (visible failure), P5 (reuse existing orchestrator), P7/P8 (AWS Secrets Manager secrets), P10 (structured logging), P15 (versioned APIs), and P16 (React/TanStack Query). No complexity exception required.

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
packages/dcm-backend/
├── dcm_backend/alerting/      # EmailChannel and template integration
├── dcm_backend/api/           # email channel validation/config extension
└── tests/
packages/dcm-frontend/
├── src/pages/                 # existing Notification Settings extension
├── src/components/            # email channel controls
├── src/hooks/                 # existing API/query hooks
└── tests/
```

**Structure Decision**: Extend only backend and frontend packages. Reuse Spec 017's direct AlertingService fan-out, project-owned notification tables, and Alert Config Dialog; add EmailChannel, MailJet template rendering, recipient validation, and email UI enablement. No new DataEng package, queue, worker, or orchestrator.

## Complexity Tracking

No constitution violations. No complexity exception required.
