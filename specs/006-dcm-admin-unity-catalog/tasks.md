# Tasks: DCM Administration Module on Unity Catalog

**Input**: Design documents from `/specs/006-dcm-admin-unity-catalog/`

**Prerequisites**: `spec.md`, `plan.md`

**Tests**: Required for auth guards, validation, audit logging and frontend admin flows where practical. Unity Catalog table creation is validated manually by `our_catalogs_spn.py`.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it touches different files and has no dependency on incomplete work.
- **[Story]**: Which user story the task maps to.

---

## Phase 1: Spec Kit Setup

**Purpose**: Make the Unity Catalog adaptation explicit before implementation.

- [x] T001 Create Spec Kit folder `specs/006-dcm-admin-unity-catalog/`.
- [x] T002 Add feature specification in `specs/006-dcm-admin-unity-catalog/spec.md`.
- [x] T003 Add implementation plan in `specs/006-dcm-admin-unity-catalog/plan.md`.
- [x] T004 Add implementation task list in `specs/006-dcm-admin-unity-catalog/tasks.md`.
- [x] T005 Update `.specify/feature.json` to point at the new feature directory.
- [x] T006 Rename branch to `006-dcm-admin-unity-catalog`.

---

## Phase 2: Unity Catalog Admin Schema (Priority: P1)

**Goal**: Create the admin tables in UC without Lakebase migrations.

**Independent Test**: Run `python our_catalogs_spn.py` and verify all `dcm_*` tables are listed.

- [x] T007 [US1] Add idempotent admin table creation to `our_catalogs_spn.py`.
- [x] T008 [US1] Add default seeds for `dcm_kpi_config`.
- [x] T009 [US1] Add default seeds for `dcm_retention_policies`.
- [x] T010 [US1] Add optional first-admin bootstrap from env vars.
- [x] T011 [US1] Print admin table verification after creation.

---

## Phase 3: Auth and Audit Prerequisites (Priority: P1)

**Goal**: Ensure every admin route has reliable identity, role checks and audit logging.

- [x] T012 [P] Add or verify auth current-user models and `require_role("admin")`.
- [x] T013 [P] Add or verify `get_allowed_lz_ids`.
- [x] T014 Add `log_action` helper writing to `dcm_audit_log`.
- [x] T015 Add or verify `GET /api/v1/auth/me`.
- [x] T016 Register auth routes in `packages/dcm-backend/app/main.py`.

---

## Phase 4: Users and Landing Zones (Priority: P1)

**Goal**: Deliver RBAC user management and LZ registry.

- [x] T017 [US2] Implement `packages/dcm-backend/app/api/routes/admin_users.py`.
- [x] T018 [US2] Add validations for roles and self-deactivation.
- [x] T019 [US2] Add atomic replace for user LZ access.
- [x] T020 [US3] Implement `packages/dcm-backend/app/api/routes/admin_lz.py`.
- [x] T021 [US3] Add `lz_id` validation and duplicate handling.
- [x] T022 Register users and LZ admin routers in backend main.
- [x] T023 Add route tests for users and LZ endpoints.

---

## Phase 5: Notifications and Alert Rules (Priority: P1)

**Goal**: Configure notification destinations before alert rules reference them.

- [x] T024 [US4] Implement `packages/dcm-backend/app/api/routes/admin_channels.py`.
- [x] T025 [US4] Add notifier helper with Teams and email test behavior.
- [x] T026 [US4] Implement `packages/dcm-backend/app/api/routes/admin_alert_rules.py`.
- [x] T027 [US4] Add alert evaluator helper for test endpoint.
- [x] T028 [US4] Validate `metric_domain` / `condition_field` combinations.
- [x] T029 Add route tests for channels and alert rules.

---

## Phase 6: Collectors, KPI, Retention, Maintenance and Audit (Priority: P1/P2)

**Goal**: Complete remaining backend modules.

- [x] T030 [US5] Implement `packages/dcm-backend/app/api/routes/admin_collectors.py`.
- [x] T031 [US5] Add `X-Collector-Key` authentication using `DCM_COLLECTOR_API_KEY`.
- [x] T032 [US6] Implement `packages/dcm-backend/app/api/routes/admin_kpi_config.py`.
- [x] T033 [US6] Implement public `GET /api/v1/kpi-config`.
- [x] T034 [US6] Implement `packages/dcm-backend/app/api/routes/admin_retention.py`.
- [x] T035 [US6] Adapt retention stats to available Unity Catalog metadata.
- [x] T036 [US6] Implement `packages/dcm-backend/app/api/routes/admin_maintenance.py`.
- [x] T037 [US6] Implement public `GET /api/v1/maintenance-windows/active`.
- [x] T038 [US7] Implement `packages/dcm-backend/app/api/routes/admin_audit.py`.
- [x] T039 [US7] Add CSV export for audit log.

---

## Phase 7: LZ Filtering in Existing Data Routes (Priority: P1)

**Goal**: Make backend data access respect admin-managed permissions.

- [x] T040 Inject allowed LZ filtering into `clusters.py`.
- [x] T041 Inject allowed LZ filtering into `pipelines.py`.
- [x] T042 Inject allowed LZ filtering into `costs.py`.
- [x] T043 Inject allowed LZ filtering into `security.py`.
- [x] T044 Inject allowed LZ filtering into `databases.py`.
- [x] T045 Inject allowed LZ filtering into `governance.py`.
- [x] T046 Inject allowed LZ filtering into `dashboard.py`.
- [x] T047 Add regression tests for unauthorized LZ filtering.

---

## Phase 8: Frontend Admin (Priority: P2)

**Goal**: Provide the admin UI requested by the tech lead.

- [x] T048 Add `packages/dcm-frontend/src/components/RequireAdmin.tsx`.
- [x] T049 Add `packages/dcm-frontend/src/hooks/useKpiConfig.ts`.
- [x] T050 Add `packages/dcm-frontend/src/pages/Admin.tsx`.
- [x] T051 Implement Users panel in `packages/dcm-frontend/src/pages/Admin.tsx`.
- [x] T052 Implement Landing Zones panel in `packages/dcm-frontend/src/pages/Admin.tsx`.
- [x] T053 Implement Notification Channels panel in `packages/dcm-frontend/src/pages/Admin.tsx`.
- [x] T054 Implement Alert Rules panel in `packages/dcm-frontend/src/pages/Admin.tsx`.
- [x] T055 Implement Collector Status panel in `packages/dcm-frontend/src/pages/Admin.tsx`.
- [x] T056 Implement KPI Config panel in `packages/dcm-frontend/src/pages/Admin.tsx`.
- [x] T057 Implement Retention panel in `packages/dcm-frontend/src/pages/Admin.tsx`.
- [x] T058 Implement Maintenance panel in `packages/dcm-frontend/src/pages/Admin.tsx`.
- [x] T059 Implement Audit Log panel in `packages/dcm-frontend/src/pages/Admin.tsx`.
- [x] T060 Add admin API methods to `packages/dcm-frontend/src/api/dcmApiClient.ts`.
- [x] T061 Add `/admin` route and admin sidebar entry.
- [x] T062 Add frontend tests for admin guard and key panels.

**Implementation note**: the first frontend delivery keeps the 9 panels inside a single `Admin.tsx` page to avoid premature file churn; extraction to `pages/admin/*Panel.tsx` can be done later if the page grows further.

---

## Phase 9: Validation

**Purpose**: Verify the feature end-to-end.

- [ ] T063 Run `python our_catalogs_spn.py` with target UC env vars.
- [ ] T064 Run backend tests.
- [x] T065 Run frontend lint/typecheck/tests.
- [ ] T066 Manually verify `/admin` with admin and non-admin users.
- [x] T067 Update task checkboxes and implementation notes if choices differ from plan.
