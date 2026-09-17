# DCM Review Report

**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `dataeng/019-usage-curated-uc-registry` (base: `develop`)
**Task**: T001 — Curated : registre UC (uc_tables, uc_table_tags, uc_table_operations)
**Stack**: python (module `pipelines`)
**Verdict**: **PASS**

## Changed files (staged, vs merge-base develop)

```
packages/dcm-databricks-pipeline/pipelines/system_tables/specs.py
packages/dcm-databricks-pipeline/resources/job_dcm_system_tables.yml
packages/dcm-databricks-pipeline/tests/system_tables/test_specs.py
specs/019-usage-data-product-gold/spec.md
specs/019-usage-data-product-gold/stories/T001-curated-uc-registry.md
specs/019-usage-data-product-gold/tasks.md
```

## Gates

| Gate   | Status | Detail |
|--------|--------|--------|
| pytest | PASS   | 283/283 (whole package, `PYENV_VERSION=3.12.11 uv run pytest -q`); 27/27 in `tests/system_tables/` |
| ruff   | WARN   | 278 pre-existing errors package-wide (`ANN001` untyped `gold_module` pytest fixture args in `tests/test_dlt_workflow.py`, untouched by this task) — scoped `ruff check pipelines/system_tables/ tests/system_tables/` = **0 errors**, 0 new violations from this diff |
| mypy   | SKIP   | Pre-existing package-wide config issue (`Source file found twice under different module names`, e.g. `common.models` / `pipelines.common.models` — same root cause across sessions, cf. `specs/013-workflow-sys-tables-migration/review-report-T002.md`), unrelated to this diff. Scoped `mypy -p pipelines.system_tables` = 1 pre-existing error in unmodified `entrypoint.py:143` (`dict` missing type args), **0 errors in the modified `specs.py`** |

Package has known pre-existing ruff/mypy debt (not a zero-warning package per repo
history, cf. T002 precedent above); no new debt category or new violation introduced
by this change (verified via file-scoped `ruff check` / `mypy -p` in addition to the
whole-package run).

## Skill review (dcm-python) — anti-patterns

- No relative imports introduced (absolute `from pipelines.common.models import IngestionSpec`). ✅
- No secrets/hardcoded credentials in the diff. ✅
- No modification of the generic ingestion socle (`pipelines/common/ingest.py`,
  `entrypoint.py`, `readers.py`) — purely declarative `IngestionSpec` configuration,
  as required by the story. ✅
- Curated stays "fidèle source" (P12, no transform/join): `curated_dbx_uc_table_operations`
  keeps `request_params` raw (MAP), matching the existing `curated_dbx_access_audit` /
  `gold_dbx_compute/cluster_reliability_daily.py` pattern (parse downstream in gold, never
  in curated). ✅
- Naming conventions respected: `curated_dbx_uc_*` prefix, new registry keys aligned with
  `SPEC_KEYS` / job YAML `for_each.inputs`. ✅ (P11)
- No legacy `Cluster`/`Compliance` naming. ✅
- New constant `ACCESS_AUDIT_WRITE_ACTIONS` is distinct from `ACCESS_AUDIT_TABLE_ACTIONS`
  (not reused/extended) — `curated_dbx_access_audit` / `ACCESS_AUDIT_SPEC` behavior
  unchanged (verified by test + no diff on `ACCESS_AUDIT_SPEC`). ✅

## Acceptance criteria coverage (story T001)

| AC | Status |
|----|--------|
| `curated_dbx_uc_tables` — full load, key `(cloud_provider, table_catalog, table_schema, table_name)` | ✅ spec + test |
| `curated_dbx_uc_table_tags` — full load, key `(cloud_provider, catalog_name, schema_name, table_name, tag_name)` | ✅ spec + test |
| `curated_dbx_uc_table_operations` — watermark `event_time`, key `(cloud_provider, event_id)`, new `ACCESS_AUDIT_WRITE_ACTIONS` | ✅ spec + test |
| Gate de validation mapping `action_name → operation` avant merge (dev) | ⬜ **manual step, not run in this session** (requires a live Databricks run — documented as a candidate list pending dev validation, cf. code comment) |
| Aucune modification du comportement de `curated_dbx_access_audit` existante | ✅ `ACCESS_AUDIT_SPEC` untouched, dedicated test asserts it |
| `table_full_name` dérivé (`concat_ws('.', ...)`) présent sur `curated_dbx_uc_tables` | ❌ **not implemented — flagged deviation** (see below) |
| Tests pytest/chispa verts, ruff/mypy sans nouvelle violation vs baseline | ✅ |
| Aucune modification hors périmètre (specs.py / job yml / tests) | ✅ (diff limited to the 3 files + `tasks.md`) |

### Flagged deviation — `table_full_name` on `curated_dbx_uc_tables`

Not implemented. `IngestionSpec.select_columns` only supports plain column names on the
native/AWS read path (`df.select(*select_columns)` — Spark cannot parse SQL expressions
there), so a `concat_ws(...)` derived column cannot be added without modifying the
generic socle (`pipelines/common/readers.py`), which is explicitly out of scope for this
task. This is consistent with the repo's "curated = fidèle source, no transform" rule
(P12) and with how `curated_dbx_access_audit` already keeps `request_params` raw
(parsed downstream in `gold_dbx_compute/cluster_reliability_daily.py`). The data model
doc itself calls this column "informatif" only on curated, since gold tables use
separate `catalog`/`schema`/`table_name` columns. Recommendation: derive `table_full_name`
in T003's gold `table_catalog` builder instead (already planned there). 🟡 risk — needs
explicit sign-off before considering T001 fully closed against the literal AC text.

**Update**: documented directly in the spec artifacts (this is no longer only a review
finding) — `spec.md` Acceptance Scenario 1/3 (User Story 1) and
`stories/T001-curated-uc-registry.md` Acceptance Criteria + Notes now state explicitly
that `table_full_name` (and the `action_name → operation` normalization) are computed in
T003's gold `table_catalog`, not in curated. Same rationale applies to `operation`:
normalizing `action_name` also requires an expression the generic `select_columns`
mechanism cannot carry on the native path, so it is deferred to gold for the same
reason.

## Scope check

- Diff limited to `packages/dcm-databricks-pipeline/pipelines/system_tables/specs.py`,
  `resources/job_dcm_system_tables.yml`, `tests/system_tables/test_specs.py`, and
  `specs/019-usage-data-product-gold/tasks.md` (task checkbox). No file outside this
  scope touched. ✅
- No modification of `curated_dbx_access_audit` / `ACCESS_AUDIT_SPEC` / other existing
  system tables specs. ✅
- No modification of `ingest.py` / `entrypoint.py` / `readers.py` (generic socle). ✅

## Findings

- 🟡 risk: `table_full_name` derived column on `curated_dbx_uc_tables` not implemented —
  see flagged deviation above; needs explicit product/tech-lead sign-off since it
  deviates from the literal acceptance criterion text (rationale: architectural
  consistency + technical infeasibility without touching the generic socle).
- 🟢 note: the mandatory dev-gate validation of `action_name → operation` mapping
  (`ACCESS_AUDIT_WRITE_ACTIONS`) still needs to run against real `system.access.audit`
  data before this can be considered production-validated — no code action possible
  here, tracked as a manual follow-up.

## Next

- Get sign-off on the `table_full_name` deviation (keep as-is / open a socle exception /
  defer fully to T003).
- Run the dev gate (`action_name → operation` mapping) before merge, per story.
- If OK to proceed: `git commit` (stamp below), then `/speckit.dcm.publish-pr --spec 019-usage-data-product-gold --task T001`.

