# DCM Review Report

**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `dataeng/012-gold-warehouses` (base: `develop`)
**Task**: T003 — Gold SQL Warehouses (cost, utilization/rightsizing, query performance)
**Stack**: dataeng (Python / PySpark)
**Verdict**: **PASS** — both findings from the previous pass are resolved.

## Note on `dcm-review.sh` automated run

The script's own run reports **FAIL** (`ruff: command not found`, `pytest: command not found`) — known repo discrepancy: the script calls bare `ruff`/`pytest` instead of `uv run ruff`/`uv run pytest`. Not a real regression. Gates re-run manually below with `uv run`.

## Changed files (uncommitted, working tree vs `develop` — no commits yet on this branch)

```
 pipelines/gold_dbx_compute/entrypoint.py                          |  52 +++-
 pipelines/gold_dbx_compute/specs.py                                | 316 +++++++++++++-
 pipelines/gold_dbx_compute/warehouse_cost_daily.py                 | 263 ++++++++++++++++ (new)
 pipelines/gold_dbx_compute/warehouse_query_performance_daily.py    | 160 ++++++++++ (new)
 pipelines/gold_dbx_compute/warehouse_utilization_daily.py          | 476 +++++++++++++++++++++++++++ (new)
 resources/job_dcm_gold_dbx_compute.yml                             |  62 +++-
 tests/gold_dbx_compute/test_entrypoint.py                          |  45 +++
 tests/gold_dbx_compute/test_specs.py                                | 146 ++++++-
 tests/gold_dbx_compute/test_warehouse_cost_daily.py                 |  90 ++++++ (new)
 tests/gold_dbx_compute/test_warehouse_query_performance_daily.py    |  83 +++++ (new)
 tests/gold_dbx_compute/test_warehouse_utilization_daily.py          | 271 ++++++++++++ (new, was 100 in prior pass)
 specs/.../stories/T003-gold-warehouses.md                           |  44 +-
 specs/.../tasks.md                                                  |   2 +-
```
13 files changed, 1985 insertions(+), 25 deletions(-). All code within `packages/dcm-databricks-pipeline` (in-scope per `intake.json`). No cluster-related entries in shared files (`specs.py`/`entrypoint.py`/job YAML) modified — append-only, per `merge-strategy.md`.

**Note**: this is a re-review of the same task — `warehouse_utilization_daily.py`/its test file grew significantly (340→476 lines, 100→271 test lines) since the previous pass, reflecting post-delivery fixes to `running_hours`/`active_query_hours`/`peak_concurrency` (see Finding below).

## Gates (manual, `uv run`)

| Gate | Status | Detail |
|------|--------|--------|
| ruff | PASS | `uv run ruff check pipelines/gold_dbx_compute/ tests/gold_dbx_compute/` — all checks passed |
| mypy | KNOWN FAIL (pre-existing) | `uv run mypy pipelines/gold_dbx_compute` — "Source file found twice under different module names": repo-wide quirk, confirmed pre-existing on `system_tables`/T002, CI has mypy commented out for this package. Not a regression from T003. |
| pytest (package scope) | PASS | `uv run pytest -q tests/gold_dbx_compute/` — 95 passed |
| pytest (full suite) | PASS | `uv run pytest -q` — 205 passed, 0 regression (was 198 in prior pass, 120 after T002) |
| bundle validate | PASS | `databricks bundle validate -t dev` — Validation OK |

## Skill review (`dcm-python` + `dcm-testing` + `dcm-verify`)

- Absolute imports only (`from pipelines.gold_dbx_compute...`, `from pipelines.system_tables.specs import ...`) — no relative imports between packages. ✅
- No secrets/hardcoded credentials — plugin only reads already-qualified Unity Catalog tables (`catalog`/`schema` params required, guarded in `entrypoint.main`). ✅
- Tests follow existing `FakeSpark`/`fakes` fixture pattern (`tests/conftest.py`), asserting on generated SQL text — consistent with T002, no real `SparkSession` instantiated. ✅
- No unrelated refactors: cluster-related code (`cluster_*.py`, cluster entries in `specs.py`/`entrypoint.py`/job YAML) untouched — diff confirms append-only. ✅
- Naming convention `gold_dbx_compute_warehouse_*` respected (FR-015). ✅
- No `source_lz_id`/`cost_rank` on warehouse tables — consistent with `data-model.md` and documented as a deliberate deviation in the sub-spec. ✅
- `running_hours` now correctly splits sessions across calendar-day boundaries (`LATERAL VIEW explode(sequence(...))` + `GREATEST`/`LEAST`), and `active_query_hours`/`peak_concurrency` share a single sweep-line CTE (`concurrency_events`/`concurrency_running`) instead of an `O(n²)` self-join — both changes are well covered by new non-regression tests with clear rationale docstrings. ✅

### Findings

- ✅ **Resolved** — `specs/012-compute-metrics-ingestion/stories/T003-gold-warehouses.md` now has a `### Fix cible post-livraison T003 : running_hours / active_query_hours / peak_concurrency` section (mirroring the T002 pattern), documenting the negative-`idle_pct` and self-join-timeout root causes and their fixes (day-splitting, sweep-line, stale-null-`end_time` exclusion). The stale "Deviations" bullet about `LEAD`-only pairing without day-splitting was also corrected.
- ✅ **Resolved** — `resources/job_dcm_gold_dbx_compute.yml:16`: job `name` renamed from `"... DCM Gold Compute (Clusters)"` to `"... DCM Gold Compute"` (job now covers clusters + warehouses). Cosmetic display-name only, no `task_key`/dependency/logic impact — re-validated via `databricks bundle validate -t dev` (PASS below).
- No other blocking or functional findings.

## Acceptance Criteria coverage (sub-spec `stories/T003-gold-warehouses.md`)

All 7 acceptance criteria + test/gate checkboxes still hold and are further reinforced by the additional non-regression tests:
- cost_daily: `query_count`, `cost_usd`, `cost_per_query_usd` — covered (`test_warehouse_cost_daily.py`).
- utilization_daily: idle detection → `OVER` + `estimated_savings_usd`, plus now cross-midnight-safe `running_hours` and sweep-line `active_query_hours`/`peak_concurrency` — covered (`test_warehouse_utilization_daily.py`, 18 tests).
- query_performance_daily: `failure_rate_pct`/`spill_query_count`/percentiles — covered (`test_warehouse_query_performance_daily.py`).
- Idempotency via generic `merge_into_table` (unchanged, already tested at socle level).
- Full-run / incremental-window behavior — covered via `_resolve_lower_bound` (reused from T002) + SQL-predicate assertions in each test file.

## Next

- **Verdict: PASS** — safe to open PR to `develop`.
- Reminder: nothing committed yet on this branch (`git log origin/develop..HEAD` is empty, all changes in working tree) — commit before running `/speckit.dcm.publish-pr`.
