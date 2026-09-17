# DCM Review Report — T005

**Package**: `packages/dcm-frontend`
**Branch**: `frontend/013-frontend-null-safe-freshness` (base: `develop`)
**Task**: T005 — Frontend Lakeflow/Jobs NULL-safe (« Attente » masquée, tooltip cron retiré) + bandeau fraîcheur `as_of`
**Stack**: react / typescript
**Verdict**: **PASS**

## Scope

Diff-scoped review. Changed files, all within `packages/dcm-frontend`:

```
src/lib/lakeflow/field-descriptions.ts
src/lib/lakeflow/format.ts
src/lib/lakeflow/format.test.ts        (new)
src/pages/LakeflowJobs.tsx
src/pages/LakeflowJobs.test.tsx        (new)
src/pages/LakeflowJobDetail.tsx
src/pages/LakeflowRunDetail.tsx
src/types/api.ts
```

## Gates (scoped to the T005 diff)

| Gate | Status | Detail |
|------|--------|--------|
| eslint (changed files) | PASS | `eslint <8 changed files>` → exit 0, clean. |
| vitest (new suites) | PASS | `format.test.ts` + `LakeflowJobs.test.tsx` → **11 passed**. |
| vitest (full suite) | PASS (non-regressing) | 230 passed / 234; the 4 failures are **pre-existing** on `develop` (`App.test.tsx`, `Databricks.test.tsx`, `Dashboard.test.tsx`, `Databricks.tsx:237`), proven by `git stash` + rerun (same 4 fail without the diff). None touch Lakeflow. |

### Whole-package `npm run lint` — FAIL (out of scope, pre-existing)

~39 errors / ~21 warnings, all in **unmodified** files (`DatabricksInsights.tsx`
unused vars, `PipelinesFocusPage.tsx` unused `Filter`, exhaustive-deps warnings…).
Not introduced by T005; scoped eslint on the changed files is clean.

## Acceptance criteria coverage

- [x] Colonne « Attente » (queue | lag) masquée — `wait` column + `WaitStack` + `'wait'` sort key removed from `LakeflowJobs.tsx`. Test asserts header absent.
- [x] Durées/attente `null` → « n/d »/tiret, jamais `0` — `formatDurationSeconds(null)→'—'`; removed `Number(x)||0` coercions in `DurationStack` (N2) and `SegmentBar` (N3). Unit + component tests.
- [x] Tooltip cron du Trigger supprimé ; `trigger_type` conservé — no cron/schedule tooltip exists in the frontend (verified by search); `trigger_type` rendering untouched.
- [x] Workspace / Propriétaire : fallback `workspace_id` / `creator_id` — N2 header now `workspace_name || workspace_id`; owner already carries `creator_id` from backend; N1 Job cell already `workflow_name || workflow_id` (component test).
- [x] Drill N3 : ventilation durée (queue/exec) retirée ; total `duration_seconds` affiché ; `error_message` libellé « Code de terminaison » — `SegmentBar` replaced by a single total; tasks table column renamed; `error` field description updated.
- [x] Bandeau « données à ~X h » dérivé de `as_of` (âge = now − as_of) — `formatDataFreshness()` + banner in `LakeflowJobs.tsx`; `as_of?` added to `LakeflowJobsListResponse`. Component test asserts "données à ~2 h" from a 2h-old `as_of`.
- [x] Lien `run_page_url` reconstruit — unchanged, still rendered in N2 actions + N3 header.
- [x] `app-routes.ts` inchangé ; lint + Vitest verts (scoped).

## Skills review (dcm-react / dcm-testing / dcm-verify)

1. No secrets/tokens/credentials in diff.
2. Layers respected — pages consume hooks; formatters stay pure in `lib/`; types mirror backend.
3. Readable labels over raw IDs; raw id kept as fallback only when name absent.
4. Tests hermetic (mock the hook / pure unit), use `renderWithProviders`.
5. Files modified ⊆ `packages/dcm-frontend` (+ `tasks.md` checkbox).
6. Small, reviewable diff.

### Findings

- 🟢 note: `lakeflowJobFieldDescriptions.wait` is now unused (harmless dead property) — left in place to minimize churn; can be pruned in a cleanup pass.
- 🟢 note: pre-existing frontend lint/test debt on `develop` (see above) — worth a separate hardening ticket.

## Verdict

**PASS** — all acceptance criteria met, changed files lint clean, new tests green,
full suite non-regressing (only pre-existing failures remain).
