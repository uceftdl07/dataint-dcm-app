# DCM Review Report

**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `dataeng/DCINT-311-fix-recommendations-object-name` (base: `develop`)
**Ticket**: [DCINT-311](https://tdf.atlassian.net/browse/DCINT-311) — corriger les lignes avec `object_name IS NULL` dans `gold_dbx_compute_recommendations`
**Stack**: python (module `pipelines`)
**Verdict**: **PASS**

## Changed files

```
docs/spike/compute-metrics-definition/compute_datamodel.md
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_reliability_daily.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_reliability_rolling.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/recommendations.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/specs.py
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_cluster_reliability_daily.py
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_cluster_reliability_rolling.py
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_recommendations.py
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_specs.py
```

Nothing committed yet (working tree changes only) — `dcm-review.sh`'s `git diff
<merge-base>...HEAD` therefore shows no changed files vs `develop`. Confirmed
scope directly via `git status`/`git diff` instead (list above).

## Gates — override note

`dcm-review.sh --package packages/dcm-databricks-pipeline` reports ruff/mypy/pytest
as **FAIL** with `pyenv: <tool>: command not found` — known false positive (repo
memory `dcm-databricks-pipeline-conventions.md`): the script's shell does not set
`PYENV_VERSION`, and global pyenv is `system`. Re-ran the scoped commands by hand:

| Gate | Command | Result |
|------|---------|--------|
| ruff | `PYENV_VERSION=3.12.11 uv run ruff check <8 touched files>` | **PASS** — All checks passed! |
| mypy | `PYENV_VERSION=3.12.11 uv run mypy -p pipelines.gold_dbx_compute` | **PASS*** — 10 errors, all in `forecast.py` (untouched by this diff) |
| pytest | `PYENV_VERSION=3.12.11 uv run pytest -q` (full package) | **PASS** — 582 passed |

\* mypy is not part of this package's official gate matrix (`dcm-verify` SKILL:
`dcm-databricks-pipeline` = ruff + pytest only, no mypy config declared) — run as
extra rigor per repo convention on this package. The 10 `forecast.py` errors are
confirmed **pre-existing on `develop`** (`git stash` + re-run reproduces the exact
same 10 errors, same file, same lines) — unrelated to this change, not introduced
by it.

## Skill review (dcm-python + dcm-testing + dcm-verify)

1. **Secrets/.env**: none in diff.
2. **Anti-patterns**: none — no new imports, no relative cross-package imports,
   pure SQL-string threading of two additive columns (`cluster_name`,
   `cluster_type`) following the exact pattern already used for `cluster_type`
   elsewhere in the same files (as-of join → daily → rolling → recommendations).
3. **Acceptance** (no sub-spec — standalone hotfix, Jira DCINT-311 is the
   reference): (a) `object_name` no longer NULL for CLUSTER recommendations
   sourced from `latest_efficiency`/`latest_reliability` outside
   `gold_dbx_compute_cluster_governance`'s bounded activity window — root-caused
   and fixed by resolving the name from the same rolling table instead of an
   unreliable `LEFT JOIN governance`; (b) new `cluster_type` output column on
   `gold_dbx_compute_recommendations` (NULL for WAREHOUSE rows) — both covered
   by code + new/extended tests.
4. **Scope**: all touched files are inside `packages/dcm-databricks-pipeline`
   (+ 1 doc file, `compute_datamodel.md`, updated to keep the schema table
   truthful) — no `dcm-backend`/`dcm-frontend`/`dcm-commons` touched (explicitly
   out of scope, not requested).
5. **Tests**: extended in all 4 affected test files, asserting exact SQL text
   (repo convention: `FakeSpark` captures `spark.sql(...)` calls, no real
   `SparkSession`) — new/adjusted assertions for `e.cluster_name AS object_name`,
   `r.cluster_name AS object_name`, `cluster_type` threading through
   `_EXISTING_STATE_NULL_COLUMNS`/`merged`/final `SELECT`, and
   `CAST(NULL AS STRING) AS cluster_type` on all 5 WAREHOUSE candidates.
6. **Small PR**: 9 files, +162/-28 lines — mechanical column threading, easily
   reviewable.
7. **Schema evolution**: `merge_into_table`/`build_merge_sql` (writers.py) uses
   unconditional `MERGE ... WITH SCHEMA EVOLUTION` — new `cluster_type` column
   auto-adds on first write to `gold_dbx_compute_recommendations`, no manual
   `ALTER TABLE` needed.

Findings: none blocking.

```
(no 🔴/🟡 findings — clean diff)
```

## Verdict

Gates **PASS** (after justified override of the unscoped script's pyenv false
positive), no blockers. **PASS**.

## Next

- ○ OK → commit, then open PR `dataeng/DCINT-311-fix-recommendations-object-name` → `develop`
- ○ Fix → n/a, nothing to fix
- ○ Ignore → n/a
