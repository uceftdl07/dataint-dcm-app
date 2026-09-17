# Tasks: Mounir Live API Demo

**Input**: Design documents from `/specs/003-mounir-live-api-demo/`

**Prerequisites**: `spec.md`, `plan.md`

**Tests**: Required where practical. The feature changes visible frontend behavior and API orchestration.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and has no dependency on incomplete work.
- **[Story]**: Which user story the task maps to.

---

## Phase 1: Setup and Documentation

**Purpose**: Make the Phase 0 scope explicit before implementation.

- [x] T001 Create Spec Kit folder `specs/003-mounir-live-api-demo/`.
- [x] T002 Add feature specification in `specs/003-mounir-live-api-demo/spec.md`.
- [x] T003 Add implementation plan in `specs/003-mounir-live-api-demo/plan.md`.
- [x] T004 Update `.specify/feature.json` to point at the new feature directory.
- [x] T005 Update `docs/05-mounir-ai/AGENT-MOUNIR.md` with Phase 0 live API demo before the backend agentic V1.

---

## Phase 2: User Story 1 - Transparence demo/dev (Priority: P1)

**Goal**: Make the current capability level visible and honest.

**Independent Test**: Open `/talk-to-data` and see the development mode message.

- [x] T006 [US1] Add a development mode banner/message in `packages/dcm-frontend/src/pages/TalkToYourData.tsx`.
- [x] T007 [US1] Update the welcome copy to mention APIs DCM available today and advanced conversation later.

---

## Phase 3: User Story 2 - Live API answers (Priority: P1)

**Goal**: Build useful responses from existing backend endpoints.

**Independent Test**: Trigger each suggested question and confirm the corresponding API client function is called.

- [x] T008 [US2] Import existing API client functions in `TalkToYourData.tsx`.
- [x] T009 [US2] Add a simple keyword-based intent detector for costs, pipelines, security, governance, data product usage and overview.
- [x] T010 [US2] Replace hardcoded demo responses with live response builders using `dcmApiClient`.
- [x] T011 [US2] Update suggested questions and thinking steps to match real DCM endpoints.
- [x] T012 [US2] Display sources or a `Live DCM API` indication for backend-backed responses.

---

## Phase 4: User Story 3 - Unsupported fallback (Priority: P2)

**Goal**: Keep free-form input without pretending to support everything.

**Independent Test**: Ask an out-of-scope question and receive a clear unsupported message.

- [x] T013 [US3] Add unsupported-intent response with supported domains.
- [x] T014 [US3] Ensure API errors show a user-readable message without sensitive details.

---

## Phase 5: Validation

**Purpose**: Verify frontend quality gates for the changed files.

- [x] T015 Run `npm run lint` from `packages/dcm-frontend`.
- [x] T016 Run `npm run typecheck` from `packages/dcm-frontend`.
- [x] T017 Run relevant tests from `packages/dcm-frontend`.
- [x] T018 Update task checkboxes and final notes if implementation differs from plan.
