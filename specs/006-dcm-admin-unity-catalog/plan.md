# Implementation Plan: DCM Administration Module on Unity Catalog

**Branch**: `006-dcm-admin-unity-catalog` | **Date**: 2026-05-27 | **Spec**: `specs/006-dcm-admin-unity-catalog/spec.md`

**Input**: Feature specification from `/specs/006-dcm-admin-unity-catalog/spec.md`

## Summary

Implémenter le module Administration DCM demandé par le tech lead, en corrigeant la cible data pour ce repo : les tables admin sont créées dans Unity Catalog via `our_catalogs_spn.py`, puis consommées par `packages/dcm-backend` avec `DatabricksWarehousePool`. Aucun fichier de migration Lakebase/PostgreSQL ne doit être créé.

## Technical Context

- **Backend**: Python FastAPI, Databricks SQL connector, `DatabricksWarehousePool`
- **Database**: Unity Catalog / Delta tables, catalog/schema via `DCM_DATABRICKS_CATALOG` et `DCM_DATABRICKS_SCHEMA`
- **Frontend**: React 18, TypeScript, Tailwind CSS, Lucide
- **Auth**: Entra ID JWT Bearer, `get_current_user`, `require_role("admin")`, `get_allowed_lz_ids`
- **Testing**: backend route tests where practical, frontend Vitest/Testing Library, manual UC smoke with `our_catalogs_spn.py`
- **Constraints**: no secrets in repo, no asyncpg/Lakebase migration, admin writes must audit

## Constitution Check

- **Test-First & Code Quality**: create focused tests for RBAC guards, validation, audit logging and key frontend admin flows when code is implemented.
- **Explicit Architecture & Modularity**: split backend routes by admin module and centralize audit/validation helpers.
- **Security & Secrets Management**: store only secret references for notification channels; never log JWTs, collector keys, Teams webhook URLs or email secrets.
- **Observability & Traceability**: every admin mutation writes `dcm_audit_log`; collector stale state is visible.
- **Simplicity & Versioning**: keep the first implementation close to the requested contracts and avoid unrelated dashboard refactors.

## Project Structure

```text
specs/006-dcm-admin-unity-catalog/
├── spec.md
├── plan.md
└── tasks.md

our_catalogs_spn.py

packages/dcm-backend/app/
├── auth/
│   ├── dependencies.py
│   ├── audit.py
│   ├── notifier.py
│   └── alert_evaluator.py
├── api/routes/
│   ├── admin_users.py
│   ├── admin_lz.py
│   ├── admin_channels.py
│   ├── admin_alert_rules.py
│   ├── admin_collectors.py
│   ├── admin_kpi_config.py
│   ├── admin_retention.py
│   ├── admin_maintenance.py
│   └── admin_audit.py
└── main.py

packages/dcm-frontend/src/
├── components/RequireAdmin.tsx
├── hooks/useKpiConfig.ts
├── pages/Admin.tsx
├── pages/admin/*.tsx
├── api/dcmApiClient.ts
├── App.tsx
└── components/Sidebar.tsx
```

## Proposed Design

### Phase 1 — Unity Catalog admin schema

- Extend `our_catalogs_spn.py` with idempotent `CREATE TABLE IF NOT EXISTS` statements for all `dcm_*` admin tables.
- Insert default KPI config and retention policies without duplicating rows.
- Optionally bootstrap the first admin from env vars, for example `DCM_BOOTSTRAP_ADMIN_ENTRA_OID`, `DCM_BOOTSTRAP_ADMIN_EMAIL`, `DCM_BOOTSTRAP_ADMIN_DISPLAY_NAME`.
- Print a clear post-check listing the admin tables found in the target catalog/schema.

### Phase 2 — Auth and audit prerequisites

- Ensure JWT auth, current user model, role guard and allowed LZ helper exist.
- Add `log_action` helper that writes JSON strings into `dcm_audit_log`.
- Add `GET /api/v1/auth/me` if missing.

### Phase 3 — Core admin modules

- Implement Users & Permissions first.
- Implement Landing Zones second.
- Implement Notification Channels before Alert Rules because rules reference channel IDs.
- Limit notification channel types to Teams and email in this version; Slack and generic webhook are out of scope.
- Implement Alert Rules with validation by metric domain and condition field.
- Implement Collector Status with collector API key auth for upsert.

### Phase 4 — Independent admin modules

- Implement KPI config public/admin endpoints.
- Implement Retention Policies and approximate stats adapted to Unity Catalog metadata if available.
- Implement Maintenance Windows admin/public active endpoints.
- Implement Audit Log list/export.

### Phase 5 — LZ security filters in data routes

- Inject allowed LZ filtering in existing data routes before frontend rollout.
- Keep backend as the final authority even when frontend filters are present.

### Phase 6 — Frontend admin page

- Add `/admin` route with `RequireAdmin`.
- Add sidebar entry visible only for admins.
- Implement the 9 panels requested by the spec.
- Add shared `useKpiConfig` hook and KPI color helper for dashboard cards.

## Risks

- Unity Catalog constraints differ from PostgreSQL constraints; Pydantic/API validation must enforce business rules.
- Databricks SQL DML and metadata stats differ from PostgreSQL; retention stats may require an adapted query.
- Bootstrap admin must be handled carefully to avoid locking everyone out or broadening access.
- Existing branch has unrelated uncommitted changes; implementation should avoid reverting them.

## Validation

- Run `python our_catalogs_spn.py` against the target workspace after env vars are set.
- Run backend unit tests and route tests once admin routes are implemented.
- Run frontend tests, lint and typecheck for `packages/dcm-frontend`.
- Manually verify `/admin` with admin and non-admin users.
