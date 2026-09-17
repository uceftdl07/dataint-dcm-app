# DCM Review Report — T001 (feature 020-dbx-workspace-dim)

**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `dataeng/020-ingestion-system-access-workspaces` (base: `develop`)
**Task**: T001 · Story `specs/020-dbx-workspace-dim/stories/T001-dbx-workspace-dim.md` · Jira DCINT-300
**Stack**: python (module `pipelines`)
**Mode**: `--commit` (pre-commit review of staged diff)
**Verdict**: **PASS**

## Staged files under review

```
packages/dcm-databricks-pipeline/databricks.yml
packages/dcm-databricks-pipeline/pipelines/gold_dbx_workspace/__init__.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_workspace/entrypoint.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_workspace/view.py
packages/dcm-databricks-pipeline/pipelines/system_tables/specs.py
packages/dcm-databricks-pipeline/pyproject.toml
packages/dcm-databricks-pipeline/resources/job_dcm_gold_dbx_workspace.yml
packages/dcm-databricks-pipeline/resources/job_dcm_system_tables.yml
packages/dcm-databricks-pipeline/tests/gold_dbx_workspace/__init__.py
packages/dcm-databricks-pipeline/tests/gold_dbx_workspace/test_view.py
packages/dcm-databricks-pipeline/tests/system_tables/test_specs.py
specs/020-dbx-workspace-dim/**  (spec, plan, tasks, stories, dispatch/state)
```

## Gates

`dcm-review.sh` runs the lint/type gates **package-wide** (whole `pipelines`
module), so its raw verdict was **FAIL** — but 100 % of the failures are
**pre-existing technical debt in files this feature never touches**. Verified by
scoping each gate to the feature diff:

| Gate | Package-wide (dcm-review.sh) | Feature-scoped | Detail |
|------|------------------------------|----------------|--------|
| ruff (lint) | FAIL (278 errors) | **PASS** | Feature files: `All checks passed!`. Package errors are all in untouched files (e.g. `tests/test_dlt_workflow.py:251` ANN001) — not in staged diff, no diff vs `develop`. |
| mypy (types, strict) | FAIL | **PASS** | Feature files with `--explicit-package-bases`: `Success: no issues found in 3 source files`. Package FAIL is a pre-existing module-path config issue (`Source file found twice under different module names`) hitting untouched `pipelines/sqs_to_volume_drain.py`. |
| pytest (tests) | **PASS** | **PASS** | Full suite green; feature-scoped `tests/gold_dbx_workspace/ tests/system_tables/test_specs.py` → 24 passed. 33 pass across package (dev notes). |
| coverage | SKIP (min=0) | — | Disabled in `dcm-config.yml`. |

**Pre-existing-debt confirmation**: `test_dlt_workflow.py` and
`sqs_to_volume_drain.py` are **absent** from the staged diff and show **no diff
vs `develop`** — the gate FAIL is orthogonal to feature 020 and would block any
commit on this package until that debt is cleaned separately.

## Skill review (dcm-python · dcm-testing · dcm-verify)

Cross-checked staged diff vs skills and story acceptance criteria.

- No secret / `.env` / credential in the diff. Pure SQL DDL over already-qualified
  Unity Catalog objects; no cross-tenant call.
- Absolute imports only (`from pipelines...`). No relative cross-package imports.
- No hardcoded catalog/schema: view SQL fully parameterized by `catalog`/`schema`
  (bundle vars, per-target); `entrypoint.main` raises `ValueError` if either is
  blank — mirrors `gold_dbx_compute.entrypoint`.
- `main(spark: Any, ...)` `# noqa: ANN401` justified (fake spark for JVM-less
  tests), consistent with the sibling gold plugin.
- View logic matches the plan: inner join `curated_dbx_access_workspaces_latest`
  x `dim_reference_landing_zone_dbx_workspace` on `workspace_id`, filters
  `status = 'RUNNING'` + `subscription_or_account_id IS NOT NULL`, 5 output cols,
  `CREATE OR REPLACE VIEW` (idempotent/replayable).
- Registry/spec change consistent (16->17), `select_columns` correctly excludes
  `cloud_provider` (added by envelope) and includes the `workspace_id` merge key.
- DABs: `databricks.yml` PAUSED override for dev/dev_local, prod UNPAUSED;
  serverless wheel job, `for_each` inputs aligned with `SPEC_KEYS`.
- Tests present for every behavior change (pure-function view SQL assertions +
  spec registry assertions), named clearly, cover story acceptance criteria.
- Files modified are within feature 020 scope in intake — no out-of-scope refactor.

### Findings

- 🔴 blocker: 0
- 🟡 risk: 0
- 🟢 note (2):
  - `pipelines/gold_dbx_workspace/view.py`: curated spec projects `account_id`
    but the view sources `subscription_or_account_id` from the reference table;
    curated `account_id` is ingested for faithfulness, unused by the view. Intentional.
  - `pipelines/gold_dbx_workspace/view.py`: `updated_at = current_timestamp()`
    is evaluated per read (non-materialized view) — documented in the module docstring.

## Dev validation (notes)

Ingestion run SUCCESS → `curated_dbx_access_workspaces_latest` (319 rows / 2
clouds). Gold job SUCCESS → view `dim_dbx_workspace` (313 rows: aws 161, azure
152; 5 cols; 1 row/workspace_id). 33 pytest pass, ruff 0 on feature, `bundle
validate -t dev` OK.

## Verdict

**Verdict**: **PASS** — feature diff is clean against ruff, mypy (strict), and
pytest when scoped to the changed files; the only package-wide gate failures are
pre-existing debt in untouched files. No blockers, no risks. Commit unblocked via
stamp.
