# DCM Review Report — T002 (DCINT-328)

**Package**: `packages/dcm-backend` + `packages/dcm-commons`
**Branch**: `backend/024-filtre-dur-all-purpose-endpoints-schemas` (base: `develop`)
**Task**: T002 — filtre dur ALL_PURPOSE + endpoints job/pipeline (spec `024-job-dlt-cluster-split`)
**Mode**: `--commit` (pre-commit stamp)
**Verdict**: **PASS** (fail=0 warn=0)

> Note: `dcm-review.sh` auto-run reported FAIL because global `ruff`/`pytest` are not on
> `PATH` in the review shell (`command not found`) and it diffs *committed* changes only
> (work is still uncommitted). Gates below were run manually via `uv run` per the
> `dcm-verify` skill, on the actual changed files.

## Changed files

Modified:
- packages/dcm-backend/app/api/routes/compute_metrics.py
- packages/dcm-backend/app/api/services/compute_metrics_clusters.py
- packages/dcm-backend/tests/test_compute_metrics_services.py
- packages/dcm-commons/dcm_commons/schemas/__init__.py
- packages/dcm-commons/dcm_commons/schemas/compute_metrics.py

New:
- packages/dcm-backend/app/api/services/compute_metrics_jobs.py
- packages/dcm-backend/app/api/services/compute_metrics_pipelines.py
- packages/dcm-backend/tests/test_compute_metrics_jobs.py
- packages/dcm-backend/tests/test_compute_metrics_pipelines.py

## Gates

| Gate | Package | Status | Detail |
|------|---------|--------|--------|
| ruff | dcm-backend | PASS | `uv run ruff check` on all changed files → All checks passed |
| mypy | dcm-backend | PASS | 74 baseline errors repo-wide; **0 new** — new service files clean; `compute_metrics.py` unused-ignore byte-identical to develop (line 68→77, shifted by added imports; diff of `_settings` = 0) |
| pytest | dcm-backend | PASS | `tests/test_compute_metrics_{jobs,pipelines,services}.py` → 161 passed |
| ruff | dcm-commons | PASS | 13 pre-existing baseline D101/TC003 (lines 5, 230–281, 368–410); **0 new** — added Job*/Pipeline* classes (l.287–365) carry Google docstrings |
| mypy | dcm-commons | N/A | package declares no mypy config |
| pytest | dcm-commons | PASS | `tests/` → 144 passed |

## Skills review (dcm-python / dcm-verify / dcm-testing)

1. Secrets / `.env` / credentials in diff — **none**.
2. Anti-patterns — none: async handlers, parameterized SQL (`?` placeholders), table via
   `qualified_table(...)`, column lists are module constants → no injection surface;
   soft-fail with `logger.exception`. Intra-package relative imports match the existing
   `compute_metrics_warehouses` convention.
3. Acceptance criteria — `ALL_PURPOSE` hard predicate on all 4 cluster list views
   (overview/cost/efficiency/governance); 4 new job/pipeline endpoints wired; 6 schemas
   re-exported. Covered by tests (cluster non-regression parametrized over 4 fetchers;
   job & pipeline grain/window/pagination/prev-window/route suites).
4. Scope — confined to backend + commons (task domain = backend), no refacto.
5. Tests — present for every new behavior.
6. Small PR — focused, reviewable.

## Findings

- 🟢 note: `compute_metrics.py` — 3 blank lines between `PipelineOverviewResponse` and
  `RecommendationsSummary` (cosmetic; not flagged by the configured ruff ruleset).
- 🟢 note: `specs/024-job-dlt-cluster-split/stories/T002-*.md` and
  `contracts/compute-job-pipeline.md` are not present in the repo — acceptance criteria
  cross-checked against the diff + task description rather than a written sub-spec.
- 🟢 note: pre-existing baseline mypy (74) and commons ruff (13) unchanged by T002.

## Next

- `git commit` unblocked by the PASS stamp.
- Then: `/speckit.dcm.publish-pr --spec 024-job-dlt-cluster-split --task T002`.
