# DCM Review Report — T004

**Package**: `packages/dcm-backend`
**Branch**: `backend/013-backend-null-safe-freshness` (base: `develop`)
**Task**: T004 — Backend NULL-tolérance workflow + champ `as_of` + repli `/workspaces`
**Stack**: python (module `app`)
**Verdict**: **PASS**

## Scope

Diff-scoped review (DCM gate philosophy: the change, not the package's pre-existing
debt). Staged files, all within `packages/dcm-backend`:

```
app/api/services/lakeflow_jobs.py
app/api/services/lakeflow_overview.py
tests/test_databricks_workspaces.py
tests/test_lakeflow_freshness.py   (new)
```

## Gates (scoped to the T004 diff)

| Gate | Status | Detail |
|------|--------|--------|
| ruff (changed files) | PASS | Clean on the 4 changed files. Only remaining findings are **2 pre-existing** E501 in *unmodified* SQL literals `lakeflow_jobs.py:729/731` (`_query_jobs_page` CTE) — present on `develop`, not in the diff's added lines. |
| mypy (services) | PASS | No new errors. 2 pre-existing errors (`_resolve_window` `int\|None` operand; re-export `no-any-return`) present on `develop`, only line-shifted by additive edits. |
| pytest (regression scope) | PASS | 24 passed — `test_lakeflow_freshness` (new), `test_lakeflow_scope`, `test_lakeflow_overview`, `test_databricks_workspaces`. |

### Whole-package `dcm-review.sh` — FAIL (out of scope, pre-existing)

The whole-package script reports FAIL, driven **entirely by pre-existing debt on
`develop`**, none related to T004:
- ruff: `app/config.py` (`base.update(...)`) and other unmodified files.
- mypy: `app/api/routes/chat.py:63` unused `type: ignore`, `admin_entra_search.py:24`, …
- pytest: `test_connection.py::test_connect_timeout_has_actionable_message` — env-dependent
  (local `DCM_DATABRICKS_HTTP_PATH` overrides the literal the test asserts).

Confirmed pre-existing by `git stash` + rerun on the untouched tree. Fixing them is
out of scope for T004 and would violate the small/in-scope PR rule.

## Skills review (dcm-python / dcm-testing / dcm-verify)

1. Secrets/`.env`/credentials in diff — none.
2. Anti-patterns (sync handlers, relative imports, hardcoded secrets) — none. Async
   throughout; absolute imports; freshness read via parameterized SQL.
3. Acceptance criteria coverage:
   - NULL-tolerance: mappers `_row_to_run`/`_row_to_task`/`_row_to_job_list_item` use
     `row.get()` → `None` (never 0-coerced). Covered by new NULL-serialization tests.
   - `as_of` = real `MAX(collected_at)` (not a constant): `fetch_lakeflow_as_of`, wired
     into overview + all 4 jobs endpoints. Covered by `test_lakeflow_freshness`.
   - `/workspaces` NULL→tags→`workspace_id` repli: code already correct; new test
     `test_gold_null_name_falls_back_to_id`.
4. Files modified ⊆ `packages/dcm-backend` — yes.
5. Tests present for every behavior change — yes.
6. Small PR: +304/-5, reviewable.
7. RBAC invariant preserved: `fetch_lakeflow_as_of` is scoped via `_scope_where`
   (`test_lakeflow_scope` green — every lakeflow query still carries the workspace clause).

### Findings

- 🟢 note: `lakeflow_jobs.py:729/731` pre-existing E501 in SQL CTE (not in diff) — defer.
- 🟢 note: `app/config.py` startup logging prints the Teams webhook URL + SPN secret
  length to stdout (pre-existing, unrelated) — worth a separate hardening ticket.

## Verdict

**PASS** — the T004 change is lint/type/test clean and non-regressing; the only gate
failures are pre-existing package debt on `develop`, out of scope for this task.
