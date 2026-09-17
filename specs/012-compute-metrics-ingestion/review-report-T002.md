# DCM Review Report

**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `dataeng/012-gold-compute-clusters` (base: `develop`)
**Stack**: dataeng (uv-managed — generic `dcm-review.sh` doesn't invoke `uv run`, gates re-run manually below)
**Scope reviewed**: uncommitted fix for `idle_pct`/`active_hours`/`is_zombie` (query_history → job_task_run_timeline)
**Verdict**: **PASS**

## Changed files (uncommitted, working tree vs HEAD)

```
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_metrics.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/entrypoint.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/specs.py
packages/dcm-databricks-pipeline/pipelines/system_tables/specs.py
packages/dcm-databricks-pipeline/resources/job_dcm_system_tables.yml
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_cluster_metrics.py
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_specs.py
packages/dcm-databricks-pipeline/tests/system_tables/test_specs.py
specs/012-compute-metrics-ingestion/stories/T001-curated-compute-system-tables.md (Notes only)
specs/012-compute-metrics-ingestion/stories/T002-gold-compute-clusters.md (Notes only)
```

## Gates (run manually with `uv run`, scoped to touched files)

| Gate  | Status | Detail |
|-------|--------|--------|
| ruff  | PASS   | `uv run ruff check pipelines/gold_dbx_compute pipelines/system_tables/specs.py tests/gold_dbx_compute tests/system_tables/test_specs.py` — All checks passed |
| pytest | PASS  | `uv run pytest -q` (full suite) — 123 passed, 0 régression |
| mypy  | SKIP (known issue) | Pré-existant : "Source file found twice under different module names" — CI a mypy commenté pour ce package, non introduit par ce fix |
| `databricks bundle validate -t dev` | PASS | Validation OK! (sanity check YAML, lecture seule) |

Note tooling: automated `spec-kit-dcm-workflow/scripts/dcm-review.sh` reported FAIL because it calls bare `ruff`/`pytest` (not on PATH outside `uv run`) — tooling gap, not a code issue. Repo memory (`/memories/repo/dcm-databricks-pipeline.md`) already documents `uv run` as the required invocation for this package.

## Skill review (`dcm-python` domain: dataeng)

1. **Anti-patterns** — none found: no hardcoded secrets/PAT, absolute imports only (`from pipelines.system_tables.specs import ...`), no `print()` (structured logging untouched), no unrelated refactors.
2. **Grain/merge-key correctness** — `JOB_TASK_RUN_TIMELINE_MERGE_KEYS` includes `period_start_time` (required — table has multiple rows/periods per task, confirmed up to 85 rows for one `(job_id, run_id, task_key)` on continuous/streaming jobs). No naive dedup introduced.
3. **Curated-fidelity philosophy respected** — `job_task_run_timeline` ingested as-is (no `explode` of the `compute` array at curated layer); the explode/filter logic lives in gold (`cluster_metrics.py`), consistent with `NODE_TYPES_SPEC` precedent comment.
4. **Scope** — all touched files ⊆ `packages/dcm-databricks-pipeline`, plus doc-only Notes appended to the two story files (no checkbox changes) — consistent with intake/package scope for this dataeng epic.
5. **Acceptance criteria** — no formal AC changed (T001/T002 already `[x]`); this is a post-merge correctness fix documented as a "Deviations & known limitations" addendum, same convention already used elsewhere in `T002-gold-compute-clusters.md`.
6. **No unrelated changes** — diff is minimal and targeted (parameter rename `query_history_table` → `job_task_run_timeline_table`, two CTEs rewritten, one new `IngestionSpec`, matching tests).

No findings.

## Next

- Verdict PASS — safe to commit and open/update PR #188 to `develop`.
- Residual documented limitation: `compute` struct only populated by Databricks since late Nov 2025 — periods before that have no activity signal (not a regression vs. prior behavior, which had none either).
