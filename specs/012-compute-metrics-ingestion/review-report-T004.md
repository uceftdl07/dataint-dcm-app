# DCM Review Report — T004 (clusters + warehouses, full scope)

**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `dataeng/012-gold-compute-transverse` (base: `develop`, rebased onto commit `203b873` — T003 merged)
**Stack**: dataeng (Python/PySpark)
**Scope**: `gold_dbx_compute_recommendations` (10/10 rules — 5 CLUSTER + 5 WAREHOUSE) and `gold_dbx_compute_forecast_daily` (5/5 metrics — 3 CLUSTER + 2 WAREHOUSE), superseding the earlier cluster-only partial pass
**Verdict**: **PASS**

## Automated gates note

`spec-kit-dcm-workflow/scripts/dcm-review.sh` reports FAIL because it calls bare `ruff`/`pytest`
(not `uv run ruff`/`uv run pytest`) — pre-existing, package-wide discrepancy already logged in
repo memory (`/memories/repo/dcm-databricks-pipeline.md`), not specific to this task. Gates
re-run manually below.

## Gates (manual, `uv run`)

| Gate | Command | Status |
|------|---------|--------|
| ruff | `uv run ruff check pipelines/gold_dbx_compute/ tests/gold_dbx_compute/` | **PASS** (0 warnings) |
| pytest | `uv run pytest -q tests/gold_dbx_compute/` | **PASS** (128 passed) |
| mypy | `uv run mypy pipelines/gold_dbx_compute/` | **SKIP** — pre-existing repo-wide quirk ("Source file found twice under different module names"), confirmed on `pipelines/system_tables` too, not introduced by this change. CI has mypy disabled for this package. |
| bundle validate | `databricks bundle validate -t dev` | **PASS** |

## Changed files (working tree vs `develop`, uncommitted)

```
M  pipelines/gold_dbx_compute/entrypoint.py
M  pipelines/gold_dbx_compute/specs.py
M  resources/job_dcm_gold_dbx_compute.yml
M  tests/gold_dbx_compute/test_specs.py
A  pipelines/gold_dbx_compute/forecast.py
A  pipelines/gold_dbx_compute/recommendations.py
M  tests/gold_dbx_compute/test_forecast.py
M  tests/gold_dbx_compute/test_recommendations.py
```
(+ sub-spec/tasks.md updates outside the package, tracking scope/status only)

All files are within `packages/dcm-databricks-pipeline` (intake-allowed package) — no unrelated
refactors, no files touched outside scope.

## Skill review (`dcm-python`, `dcm-testing`, `dcm-verify`)

- ✅ Absolute imports only (`from pipelines...`), no relative imports introduced.
- ✅ No hardcoded secrets — all inputs are already-qualified Unity Catalog table names, no
  credentials/connections.
- ✅ Python 3.12 syntax (`from __future__ import annotations`, `date | None` unions, matches
  existing `cluster_governance.py` style).
- ✅ Tests updated/extended with the code (`test_recommendations.py` 20 cases, `test_forecast.py`
  11 cases) — same convention as sibling builders (`test_cluster_governance.py`): no real
  `SparkSession`, `FakeSpark` captures the generated SQL text, assertions on the rendered query.
- ✅ Pre-existing `test_specs.py` tests updated (not broken) to account for the widened registry
  scope (9 `GOLD_SPECS` entries: 4 cluster + 3 warehouse + 2 transverse).
- ✅ Functions renamed `build_cluster_recommendations`/`build_cluster_forecast` →
  `build_compute_recommendations`/`build_compute_forecast` to reflect the widened clusters+
  warehouses scope — all call sites (`entrypoint.py`, tests) updated consistently.
- ✅ Dedup partition key fixed to include `object_type` (not just `object_id`) now that
  `RIGHTSIZING`/`FINOPS` combine cluster and warehouse rules in the same category.
- 🟡 **Known design tension documented, not a defect**: `research.md` R8 / `compute_datamodel.md`
  §4.1 literally specify `recommendation_id = sha2(object_type||object_id||category||generated_date)`
  using the *run* date. Implemented instead with `first_seen_date` in the hash (module docstring
  in [recommendations.py](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/recommendations.py)
  explains why: literal run-date hashing would defeat the very continuity — `first_seen_date`
  preserved across runs, `OPEN`→`RESOLVED` transitions — that those same docs require). Flagging
  for awareness in case the docs intended something else; recommend confirming with whoever owns
  `research.md`/`compute_datamodel.md`.
- 🟡 **3 warehouse thresholds are engineering defaults, not spec-mandated values**:
  `WAREHOUSE_QUEUE_TIME_P95_THRESHOLD_MS=5000`, `WAREHOUSE_FAILURE_RATE_PCT_THRESHOLD=5.0`,
  `WAREHOUSE_SPILL_QUERY_COUNT_THRESHOLD=10` (`compute_datamapping.md` §4.1 only says generic
  "seuil" with no value). Recommend product/FinOps review before these drive real alerting.
- No duplication/Sonar run requested (`--duplication`/`--sonar` not passed).

## Sub-spec acceptance criteria coverage

| Criterion | Status |
|---|---|
| `is_zombie=true` → FINOPS row, `first_seen_date`/`last_seen_date`, `status='OPEN'` | ✅ covered |
| Forecast produces projection, `method='ai_forecast'` | ✅ covered (5/5 metrics) |
| Previously-open reco with cleared condition → `RESOLVED` | ✅ covered |
| Job graph: recommendations/forecast run after cluster/warehouse tasks | ✅ covered (`depends_on` extended to warehouse tasks) |
| 4 categories (FinOps, Rightsizing, Reliability, Governance) represented | ✅ covered (RELIABILITY now sourced from the warehouse `failure_rate_pct` rule) |

## Next

- Gates are green and scope is complete (code-wise). Per the sub-spec's own "Before PR" checklist,
  the one remaining item before this can close the Epic is an actual end-to-end run of
  `quickstart.md` against seeded/real data (this review only proves the generated SQL via unit
  tests, not an executed Databricks run).
- Ready to proceed to `/speckit.dcm.publish-pr` if the team wants to open the PR now for review in
  parallel with that validation (flagged explicitly, since T004 is nominally "the task that closes
  the Epic").

