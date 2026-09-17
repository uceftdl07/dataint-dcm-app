# Plan — Project membership replaces LZ scope as the access key

Feature 016 · Admin "Access Control" → manage **Projects** instead of "Landing zone scope".
Branch: `frontend/015-project-access-governance` (combined 015+016 PR, per user override).

> Decision requested at the top: this is a **feature-sized, cross-cutting change**, not a
> label rename. It removes the flat per-user LZ table (`dcm_user_lz_access`) as the access
> source and makes **project membership** (`dcm_project_members` + `dcm_project_lz_scope` /
> `dcm_project_dbx_scope`) the single source of a user's data scope. Good news: the hard
> part (project-derived scope resolution) **already exists** from 015 — this plan mostly
> *finishes the migration* and rebuilds the Admin UI on top of it.

---

## 1. Current state (what exists today)

Two access keys coexist on `CurrentUser` ([dependencies.py](../../packages/dcm-backend/app/auth/dependencies.py)):

| Key | Source | Consumed by | Status |
|-----|--------|-------------|--------|
| `lz_ids: list[str]` | flat table `dcm_user_lz_access` (per-user rows) | `get_allowed_lz_ids` → `allowed_lz_ids` in ~15 monitoring services (dashboard, alerts, compute, databricks, datafactory, governance, monitoring-reports, chat) | **legacy** |
| `scope: AllowedScope` (lz_ids + workspace_ids) | **union of active projects** via [scope.py](../../packages/dcm-backend/app/auth/scope.py) `get_allowed_scope` | `get_allowed_scope_dep` — only `clusters.py` migrated so far | **target (015)** |

- `scope` is already computed once at auth time from `dcm_project_members` JOIN
  `dcm_projects` (status=`active`) JOIN `dcm_project_lz_scope` / `dcm_project_dbx_scope`.
  `super_admin` / legacy data-admin → `unrestricted=True`.
- The Admin "Landing zone scope" editor drives the flat table through
  [admin_users.py](../../packages/dcm-backend/app/api/routes/admin_users.py) endpoints
  `PUT /admin/users/{id}/lz-access`, `POST|DELETE .../lz-access/{lz_id}`, and the
  `lz_ids` returned by `GET /admin/users`.
- Frontend Admin Access Control ([Admin.tsx](../../packages/dcm-frontend/src/pages/Admin.tsx))
  edits `AdminUser.lz_ids` via `AdminLandingZoneScopeSelector`, with drafts (`userEdits`),
  `saveUserEdit`, `approveAdminUser(lz_ids)`, a scope filter, and badges.

**Net:** the flat `lz_ids` path is still the effective access key for most screens; the
project path is built but only partially wired.

---

## 2. Target model

A user's data scope = **union of the LZ + Databricks-workspace scopes of the `active`
projects they are a member of**. Project role (viewer/admin) does not change *what data*
they see, only whether they manage the project. `super_admin` stays unrestricted.

- `dcm_user_lz_access` is **retired** as the access source (kept read-only for one release
  for rollback, then dropped).
- Admin "Access Control" manages **project membership** (which projects a user belongs to,
  and their role in each), labeled **Projects**.

### Key design lever (keeps blast radius small)

Keep exposing a **derived** `lz_ids` on `CurrentUser` and on `/auth/me`, computed from
`scope`. Then the ~15 monitoring services and the whole frontend monitoring-scope selector
(`source_lz_ids`) keep working **unchanged** — they just receive a project-derived list
instead of a flat one. We still migrate services to `scope` where the **workspace**
dimension matters (Databricks screens), but LZ-only screens need no change.

---

## 3. Decisions to confirm before coding

1. **Derive-and-keep `lz_ids`** (recommended) vs hard-remove `lz_ids` everywhere.
   Recommended: derive from `scope`, keep the field → minimal churn. Confirm.
2. **Pending projects**: today only `active` projects grant scope. A user whose only
   project is `pending_validation` has **empty** scope (sees nothing) until an admin
   validates. Confirm this is intended (it is, per 015 `_ACTIVE_PROJECT_STATUS`).
3. **Migration of existing flat access**: seed a project (or memberships) from current
   `dcm_user_lz_access` rows so no one loses access on cutover? See §6.
4. **Admin membership editing granularity**: per-user "add to / remove from project (+role)"
   — reuse existing `dcm_project_members` mutation endpoints, or add admin-scoped ones? See §4.2.
5. **Notification preferences** (`notification_lz_ids`): keep as a sub-filter of the
   derived allowed LZs (no model change). Confirm.

---

## 4. Backend changes

### 4.1 Make projects the single scope source
- [dependencies.py](../../packages/dcm-backend/app/auth/dependencies.py) (~L440-480):
  stop reading `dcm_user_lz_access` for the access decision. Set `scope` from
  `get_allowed_scope` for **all** non-super_admin roles (currently legacy `admin` is forced
  `unrestricted` — decide if legacy data-admins remain unrestricted during transition).
  Set `lz_ids = scope.lz_ids` (derived) for backward-compat consumers.
- Migrate remaining `get_allowed_lz_ids` consumers to `get_allowed_scope_dep` where the
  **workspace** dimension is needed (databricks_bundle, compute_metrics_*). LZ-only
  services can keep `allowed_lz_ids` fed by the derived list. Inventory (~15 files) in
  `app/api/services/*` and `app/api/routes/{governance,compute_metrics}.py`, `app/chat/*`.

### 4.2 Admin: manage membership instead of flat LZ
- `GET /admin/users` ([admin_users.py](../../packages/dcm-backend/app/api/routes/admin_users.py)):
  add `projects: [{id, name, role, status}]` per user (JOIN `dcm_project_members` →
  `dcm_projects`). Keep `lz_ids` as **derived, read-only** for display.
- New admin endpoints (super_admin only, `require_platform_admin`):
  - `PUT /admin/users/{user_id}/projects` — set the full membership list (array of
    `{project_id, role}`), diff & upsert/delete in `dcm_project_members`.
  - or reuse `POST|DELETE /projects/{project_id}/members/{user_id}` per change.
  Recommendation: one `PUT .../projects` for the inline "save" UX in the table.
- `POST /admin/users` (create) & `POST /admin/users/{id}/approve`: replace `lz_ids` input
  with an optional `projects` assignment; drop `lz_ids` write path.
- Deprecate `PUT|POST|DELETE /admin/users/{id}/lz-access*` and `admin_lz.py` writers
  (keep GET for one release, or remove behind a flag).
- Update `dcm_commons` admin models (`AdminUser`, create/approve payloads) accordingly.

### 4.3 Tests
- `test_dependencies` / scope: user scope = union of active-project scopes; pending = empty;
  super_admin = unrestricted; derived `lz_ids == scope.lz_ids`.
- `test_admin_users`: `GET /admin/users` returns `projects`; `PUT .../projects` upserts &
  removes memberships; create/approve no longer accept `lz_ids`.
- Regression: a service still filtering by `allowed_lz_ids` returns rows scoped to the
  derived list.

---

## 5. Frontend changes

- Types ([api.ts](../../packages/dcm-frontend/src/types/api.ts)): `AdminUser.projects:
  {id, name, role, status}[]`; `lz_ids` becomes display-only. Add
  `AdminUserProjectsUpdate`.
- API client + hooks: `setAdminUserProjects(userId, projects)`; drop `updateAdminUserLzAccess`.
- [Admin.tsx](../../packages/dcm-frontend/src/pages/Admin.tsx) Access Control:
  - Column header **"Landing zone scope" → "Projects"** (the requested label), plus the
    new-user form field and per-user selector.
  - Replace `AdminLandingZoneScopeSelector` with a **project membership editor**
    (multi-select projects from `useReferenceProjects` or an admin projects list, with a
    per-project role viewer/admin). Badges list project names; "Unsaved" pill unchanged.
  - `getUserDraft` / `hasUserDraftChanged` / `saveUserEdit` / `approveAdminUser` operate on
    `projects` instead of `lzScope`.
  - Scope filter → **project filter** (All / member of specific project / no project).
  - "Existing users" hint & search placeholder: drop "landing zone", say "project".
- Monitoring scope selector (`source_lz_ids`) and notification preferences: **no change** —
  they read the derived allowed LZs from `/auth/me`.
- Delete now-unused `AdminLandingZoneScopeSelector` if no other caller remains.
- Tests: rewrite `Admin.test.tsx` user-access assertions around projects; keep pre-existing
  unrelated failures out of scope.

---

## 6. Data migration (cutover safety)

Before flipping the access source, ensure no active user loses access:
- Option A (recommended): a one-off migration that, for each `dcm_user_lz_access` user with
  no project membership, creates/attaches a per-user or per-LZ "legacy access" project (or
  memberships to existing projects whose `dcm_project_lz_scope` covers their LZs).
- Option B: keep legacy `admin`/data-admin users `unrestricted` (already the case) and
  onboard normal users to projects manually before removing the flat table.
- Do **not** drop `dcm_user_lz_access` in the same release — keep it one release for rollback.

Owner: dataeng (migration script / pipeline), since it touches UC tables — delegate to
`dp-data-databricks-engineer` with the step-0 skills verdict.

---

## 7. Rollout, flags, security

- New/existing public endpoints unchanged here; admin endpoints stay `require_platform_admin`
  (super_admin). No PAT, no secret, least-privilege preserved.
- Sequence: (1) derive `lz_ids` from `scope` + keep flat table read → deploy, verify parity;
  (2) ship Admin membership UI + `PUT .../projects`; (3) migrate remaining services to
  `scope` for the workspace dimension; (4) after a soak period, remove flat `lz-access`
  writers and `dcm_user_lz_access`.
- Cyber: access decisions move to project membership — verify no route silently falls back
  to `unrestricted`. Re-run the cyber checklist before deploy.

---

## 8. Blast radius & out of scope

- **Touched**: `dependencies.py`, `scope.py` consumers (~15 service/route files),
  `admin_users.py` (+ `admin_lz.py` deprecation), `dcm_commons` admin models; frontend
  `Admin.tsx`, admin types/hooks/api, `Admin.test.tsx`; one dataeng migration.
- **Untouched (by design)**: monitoring-scope selector, notification preferences, all
  `source_lz_ids` query plumbing — they consume the derived `lz_ids`.
- **Out of scope**: changing the two-dimension scope semantics (015), the login
  register/join flow (already done in this branch), RBAC page permissions (done).

---

## 9. Suggested task breakdown

1. BE-scope: derive `lz_ids` from projects in `dependencies.py`; parity tests. *(small)*
2. BE-admin: `GET /admin/users` returns `projects`; `PUT /admin/users/{id}/projects`;
   drop `lz_ids` from create/approve; deprecate `lz-access`. *(medium)*
3. FE-admin: Projects membership editor + label rename + filters + tests. *(medium/large)*
4. BE-services: migrate workspace-sensitive services to `get_allowed_scope_dep`. *(medium)*
5. DataEng: cutover migration for existing `dcm_user_lz_access` users. *(small, delegated)*
6. Cleanup: remove flat writers + `AdminLandingZoneScopeSelector`; retire table (later release).

Estimated as a multi-PR feature. Recommend implementing 1→3 first (delivers the requested
Admin "Projects" behavior end-to-end), then 4→6 as follow-ups.
