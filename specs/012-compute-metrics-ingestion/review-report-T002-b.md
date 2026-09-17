# DCM Review Report

**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `dataeng/012-gold-compute-clusters` (base: `develop`)
**Stack**: dataeng (uv-managed — generic `dcm-review.sh` doesn't invoke `uv run`, gates re-run manually below)
**Scope reviewed**: uncommitted refactor — split `cluster_metrics.py` monolith (853 lines) into 4 per-table builder
modules + shared `sql_helpers.py`, and generalize `writers.merge_into_curated` → `merge_into_table` (table/column
`COMMENT` attachment, collision-safe merge source view name).
**Verdict**: **PASS**

## Changed files (uncommitted, working tree vs HEAD)

```
packages/dcm-databricks-pipeline/pipelines/common/writers.py                 (modified)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_metrics.py       (deleted)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_cost_daily.py    (new)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_efficiency_daily.py (new)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_governance.py    (new)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_reliability_daily.py (new)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/sql_helpers.py           (new)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/entrypoint.py            (modified — imports 4 builders)
packages/dcm-databricks-pipeline/pipelines/system_tables/ingest.py                   (modified — merge_into_table rename)
packages/dcm-databricks-pipeline/pipelines/system_tables/specs.py                    (modified — docstring refs only)
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_cluster_metrics.py      (deleted)
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_cluster_cost_daily.py   (new)
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_cluster_efficiency_daily.py (new)
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_cluster_governance.py   (new)
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_cluster_reliability_daily.py (new)
packages/dcm-databricks-pipeline/tests/common/test_writers.py                        (modified — comment-attachment tests)
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_specs.py                (modified)
packages/dcm-databricks-pipeline/uv.lock                                            (lockfile churn only)
```

`test_entrypoint.py` untouched and still green — confirms the public dispatch contract of
`entrypoint.main`/`_resolve_lower_bound` was preserved across the split (only internal imports changed).

## Gates (run manually with `uv run`, scoped to touched files)

| Gate  | Status | Detail |
|-------|--------|--------|
| ruff  | PASS   | `uv run ruff check pipelines/gold_dbx_compute pipelines/common/writers.py` — All checks passed |
| pytest | PASS  | `uv run pytest -q` (full suite) — **140 passed**, 0 régression (was 123 before this refactor: +17 net from the 4 new focused test files replacing the single `test_cluster_metrics.py`) |
| mypy  | SKIP (known pre-existing) | "Source file found twice under different module names" — documented repo-wide issue (`--explicit-package-bases` needed), unrelated to this change, CI has mypy non-blocking for this package |
| `databricks bundle validate -t dev` | PASS | `Validation OK!` (read-only YAML sanity check) |

Note: a `databricks bundle deploy -t dev_local` was seen failing (exit 1) in a separate terminal earlier in the
session — **not re-run here** since `deploy` mutates a workspace and this review only needs read-only `validate`
(which passes). If that failure needs diagnosing, say so explicitly and I'll investigate separately with your
confirmation before running deploy again.

## Skill review (`dcm-python` + `dcm-testing` domain: dataeng)

1. **Anti-patterns** — none found: no hardcoded secrets/PAT, absolute imports only, no `print()`, no bare
   `except Exception`, no unrelated refactors bleeding into other packages.
2. **SQL construction via f-string** — consistent with existing codebase convention (already reviewed/accepted in
   prior `cluster_metrics.py` and `system_tables/ingest.py`): interpolated values are either qualified table names
   built from bundle variables (`catalog`/`schema`, never end-user input), or code-defined constants/dates
   (`lower_bound.isoformat()`, `column_comments` dict keys from `specs.py`). No user-controlled input reaches SQL
   text — not a SQL-injection anti-pattern in this closed, config-driven context.
3. **`writers.merge_into_table`** (renamed from `merge_into_curated`) — clean generalization: `_merge_source_view_name`
   now derives a target-specific temp view name (previously a single shared `_stg_finops_merge_source` name across
   all callers — real collision-safety improvement for concurrent/interleaved merges in the same session) and
   `_apply_table_comments` correctly escapes single quotes (`_escape_sql_string`) before building
   `COMMENT ON TABLE` / `ALTER TABLE ... ALTER COLUMN ... COMMENT`. Well covered by new tests including the
   escaping case.
4. **Module split (`cluster_metrics.py` → 4 files + `sql_helpers.py`)** — reduces per-file size/cognitive load and
   isolates test blast radius (`test_cluster_metrics.py` 423 lines → 4 focused ~90-145 line test files). No logic
   drift found versus the previously-reviewed monolith: cost/efficiency/reliability/governance formulas match
   `review-report-T002.md`'s prior sign-off, plus already-merged fixes (owner tag priority, DBR LTS prefix
   matching) are preserved.
5. **Scope** — all touched files ⊆ `packages/dcm-databricks-pipeline`; no frontend/backend files touched.
6. **Acceptance criteria (T002 story)** — all previously-checked criteria remain satisfied (idempotent merge, full
   vs. incremental window, naming convention, bundle validate); this refactor changes internal file layout only, no
   behavior/AC regression — confirmed via the untouched `test_entrypoint.py` passing unmodified.
7. **Stale documentation** — `specs/012-compute-metrics-ingestion/stories/T002-gold-compute-clusters.md` still
   references the old single-file `cluster_metrics.py` / `test_cluster_metrics.py` in its "Description", "Files to
   create/modify" and "Tests" sections. Not a code defect, but should get a short "Deviations & known limitations"
   addendum (same convention already used repeatedly in that file) documenting the split into
   `cluster_cost_daily.py` / `cluster_efficiency_daily.py` / `cluster_reliability_daily.py` /
   `cluster_governance.py` / `sql_helpers.py`, so T003/T004 owners aren't confused when rebasing. **Non-blocking.**

## Cyber verification

| Rule | Status | Evidence |
|------|--------|----------|
| No hardcoded secret/PAT | PASS | Plugin only reads Unity Catalog tables via qualified names from bundle vars; no credentials anywhere in diff |
| Least privilege / UC as source of truth | PASS | All reads/writes go through UC-qualified `catalog.schema.table`; no direct cloud/API calls |
| No DBFS | PASS | No `dbfs:/` paths introduced |
| No cross-tenant / cross-LZ call | PASS | Docstring explicitly states "jamais de connexion cross-tenant"; only same-workspace UC tables read |
| GDPR (prod→non-prod) | N/A | No data export/copy between environments in this diff |
| Lakebase / ML / Apps / Vector Search / MCP / Genie | N/A | Not touched by this change |

No blockers.

## Impact coûts & fiabilité

- **Coûts** : aucun changement de coût runtime (même fenêtre incrémentale 3 jours, mêmes tables sources) ; l'ajout
  de `COMMENT ON TABLE`/`ALTER COLUMN` est une opération de métadonnées pure, négligeable, exécutée à chaque run
  (créé ou existant) mais sans scan de données.
- **Fiabilité** : la correction du nom de vue temporaire de merge (`_merge_source_view_name` dérivé de la table
  cible, au lieu d'un nom fixe partagé) élimine un risque réel de collision si deux `merge_into_table` s'exécutaient
  dans la même session Spark (ex. futurs jobs `for_each_task` parallèles au sein d'un même run) — amélioration de
  fiabilité, pas seulement cosmétique. Découpage en 4 modules réduit le rayon d'impact d'une régression future (un
  bug dans `cluster_governance.py` ne peut plus casser silencieusement un test partagé de 423 lignes).

## Next

- Verdict **PASS** — safe to commit and push to PR #188.
- Optional (non-blocking) follow-up: add a short deviations note to
  `stories/T002-gold-compute-clusters.md` documenting the file split for T003/T004 rebase clarity.
- Separate item: the earlier `databricks bundle deploy -t dev_local` failure (exit 1) was not investigated as part
  of this review — flag if you want it diagnosed next.
