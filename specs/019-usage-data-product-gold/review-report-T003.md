# DCM Review Report

**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `dataeng/019-usage-gold-catalog-governance` (base: `develop`)
**Task**: T003 — **complete** (`table_catalog` + `table_governance`; `dim_workspace` removed per documented decision)
**Stack**: python (module `pipelines`)

## Context note — diff scope

HEAD (`ae775ac`) is the earlier **partial** T003 commit (`dim_workspace` only,
never pushed). All T003-final work is **uncommitted working-tree changes** on
top of it (nothing staged): `dim_workspace.py`/`test_dim_workspace.py` deleted,
`table_catalog.py`/`table_governance.py` + their tests added (untracked), plus
additive changes to `specs.py`, `entrypoint.py`, `resources/job_dcm_gold_dbx_usage.yml`,
and `pipelines/system_tables/specs.py` (F001 audit-action narrowing — see
Findings). `git diff origin/develop...HEAD` is empty (0 commits ahead); the
real diff is `git diff` (working tree) — 18 files, +420/-376.

## Gates — scoped commands (per repo convention, unscoped script is known-noisy)

| Gate | Command | Status |
|---|---|---|
| ruff | `PYENV_VERSION=3.12.11 uv run ruff check pipelines/gold_dbx_usage/ tests/gold_dbx_usage/` | **PASS** — all checks passed |
| mypy | `PYENV_VERSION=3.12.11 uv run mypy -p pipelines.gold_dbx_usage` | **PASS** — no issues found in 10 source files |
| pytest | `PYENV_VERSION=3.12.11 uv run pytest tests/gold_dbx_usage/ tests/system_tables/ -q` | **PASS** — 134 passed |
| FR-008 grep | `grep -rn "source_lz_id\|subscription_or_account_id" pipelines/gold_dbx_usage/` | **PASS** — only 1 hit, a comment documenting the invariant (`specs.py:326`), no actual column |

**Verdict**: **PASS**.

## Skill review (dcm-python / dcm-verify / dcm-testing)

1. No secret/`.env`/credential in diff. ✅
2. No anti-pattern: absolute imports only, no relative cross-package import,
   French docstrings match module convention, `GoldAggregationSpec`
   dataclass reused (`watermark_column=None, initial_mode="full"` — correct
   snapshot pattern, matches `gold_dbx_compute.cluster_governance`
   precedent), no f-string SQL injection (all interpolated values are
   qualified table names / int constants from `specs.py`, never
   user input). `get(split(...), i)` used instead of `[i]` indexing to stay
   ANSI-safe on malformed values — documented and consistent with repo
   convention (`sql_helpers.split_full_name` avoided deliberately, with
   reasoning). ✅
3. Acceptance criteria coverage:
   - `table_catalog`: `last_operation` = `max_by(action_name, event_time)`,
     `freshness_lag_hours` = `(now - last_write_at)/3600` ✅ implemented as
     specified.
   - `table_governance`: `is_unused`, `is_critical`, `is_stale_but_consumed`,
     `is_orphan` — all implemented with the exact thresholds from spec.md
     Clarifications (`UNUSED_AFTER_DAYS=90`, `CRITICAL_FANOUT_THRESHOLD=5`,
     `STALE_WRITE_LAG_HOURS=24`), NULL-safety explicitly documented and
     verified by construction (NULL operand ⇒ condition NULL, never
     silently true/false). ✅
   - FR-008 (no `source_lz_id`/`subscription_or_account_id`, no exception
     left): verified via grep above. ✅
   - `table_full_name` present on `table_catalog` (`concat_ws`) and
     propagated on `table_governance`. ✅
   - Job deploy/run in dev: **confirmed**. `bundle deploy -t dev_local`
     followed by a manual `dcm_gold_dbx_usage` run; verified independently
     via `DESCRIBE HISTORY` (see Findings) — both new tables written
     (`CREATE TABLE AS SELECT`, 88 502 rows each). ✅
4. Files touched ⊆ package scope, plus spec/docs tracking files (contract,
   story, spike docs) — consistent with prior task pattern. ✅
5. Tests present for both new tables (`test_table_catalog.py`,
   `test_table_governance.py`), plus updated `test_specs.py`/
   `test_entrypoint.py`/`tests/system_tables/test_specs.py` for the
   `ACCESS_AUDIT_WRITE_ACTIONS` narrowing. 134 tests green. ✅
6. Diff stays reviewable (18 files, mostly additive + one net deletion of
   `dim_workspace`). ✅
7. `tasks.md` / Jira: not checked in this pass (out of scope for this
   review invocation) — verify before dispatch that the line still
   references a branch name, not a SHA.

## Findings

- 🟢 note: `depends_on` chaining is correct — `gold_usage_table_catalog` →
  `gold_usage_table_daily` (needs `last_read_at`), `gold_usage_table_governance`
  → both `gold_usage_table_catalog` and `gold_usage_table_popularity_daily`
  (needs `downstream_fanout`). Matches the module docstrings.
- 🟢 note: `dim_workspace` removal is well-justified and low-risk — never
  deployed in dev (0 rows, per story), redundant with `dim_dbx_workspace`
  (spec 020) which is the one actually joined by `dim_landing_zone`. Docs
  (contract, story, spec.md references) all updated in lockstep.
- 🟢 note: stale `__pycache__/dim_workspace.cpython-312.pyc` left on disk
  from the deleted module — harmless (gitignored), but worth a
  `find . -name __pycache__ -exec rm -rf {} +` before packaging/deploy to
  avoid confusion.
- 🟢 note: dev deploy/run independently verified (2026-09-07, `dev_local`)
  via `DESCRIBE HISTORY` on both new tables — `gold_dbx_usage_table_catalog`
  (`CREATE TABLE AS SELECT`, 88 502 rows, 2026-09-07T09:12:41Z) and
  `gold_dbx_usage_table_governance` (same operation, same row count,
  2026-09-07T12:04:57Z — the `LEFT JOIN` with `table_popularity_daily`
  preserves the full `table_catalog` grain as expected, no fan-out/row
  loss). Job ran manually (`triggerType: manual`) on the `dev_local` target
  (development mode — isolated job/resource names, `run_as` self);
  catalog/schema (`it.ba_data_connect_monitoring__d`) is shared with other
  dev jobs since `dev_local` isolates control resources, not data —
  expected per project convention, not a finding.

## Next

```
○ OK        → proceed to /speckit.dcm.publish-pr
○ Fix       → n/a, nothing outstanding
○ Ignorer   → n/a
```

All gates, acceptance criteria (`table_catalog`/`table_governance`, FR-008,
`depends_on` chaining, `dim_workspace` removal) and the dev deploy/run are
now confirmed. T003 is ready for PR.
