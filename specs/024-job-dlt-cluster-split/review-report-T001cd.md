# DCM Review Report — T001c + T001d

**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `dataeng/024-purge-liste-all-purpose-rollup-dlt` (base: `develop`)
**Stack**: python (module `pipelines`) · toolchain `uv`
**Mode**: `--commit` (revue du diff staged)
**Verdict**: **PASS**

## Contexte

Feature `024-job-dlt-cluster-split` — PRs internes T001c (rollup DLT
`pipeline_cost` billing-direct, Option A) + T001d (passe forecast `PIPELINE`).
Jira epic DCINT-325, story DCINT-326.

## Fichiers staged (13)

```
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/entrypoint.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/forecast.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/pipeline_cost_daily.py     (NEW)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/pipeline_cost_rolling.py   (NEW)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/specs.py
packages/dcm-databricks-pipeline/resources/job_dcm_gold_dbx_compute.yml
packages/dcm-databricks-pipeline/resources/job_dcm_gold_forecast.yml
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_entrypoint.py
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_forecast.py
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_pipeline_cost.py          (NEW)
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_recommendations.py
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_specs.py
specs/024-job-dlt-cluster-split/stories/T001-purge-cluster-liste-et-rollup-dlt.md
```

`specs/024-job-dlt-cluster-split/review-report-T001b.md` (untracked, leftover
T001b) volontairement **non staged**.

## Gates

Exécutés via `uv run` (le `dcm-review.sh` standalone ne trouve pas
`ruff`/`pytest` hors venv — FAIL environnemental, pas fonctionnel).

| Gate | Status | Detail |
|------|--------|--------|
| ruff | PASS | `uv run ruff check pipelines/gold_dbx_compute/ tests/gold_dbx_compute/` — All checks passed |
| mypy | SKIP | mypy non installé dans l'env |
| pytest | PASS | `uv run pytest -q` — 614 passed |

## Revue de skills (dcm-python / dcm-testing / dcm-verify)

1. **Secrets** — aucun secret / `.env` / credential dans le diff (scan clean).
2. **Anti-patterns** — imports absolus `pipelines.*`, `from __future__ import annotations`,
   SQL généré paramétré (noms de tables issus de `specs`, seuil `int` typé),
   clé de merge `dlt_pipeline_id` garantie NON NULL (`WHERE ... IS NOT NULL`).
3. **Critères d'acceptation** couverts :
   - T001c : `pipeline_cost_daily`/`rolling` billing-direct (grain `dlt_pipeline_id`),
     specs + merge keys + tests (`test_pipeline_cost.py`, 260 l.).
   - T001d : passe `ai_forecast` `PIPELINE` (`cost_usd`/`dbu_quantity` seuls,
     pas d'efficacité), tests `test_forecast.py`.
   - Recommandations inchangées : nouveau test négatif
     `test_recommendations_never_target_pipeline_ephemeral_grain`.
4. **Périmètre** — tous les fichiers ⊆ `packages/dcm-databricks-pipeline` + la
   story 024. Pas de refacto hors sujet.
5. **Tests** — chaque changement de comportement couvert (614 pass).
6. **Bug préexistant corrigé (folded)** — retrait de la clé orpheline
   `cluster_type` de `RECOMMENDATIONS_COLUMN_COMMENTS` (leftover 3c3831e / #247
   / DCINT-311) + suppression du test obsolète
   `test_recommendations_column_comments_document_cluster_type`. Débloque
   `gold_recommendations` (`_apply_table_comments` échouait sur la colonne
   absente). Justifié, pas une régression.
7. **Small PR** — 🟡 note : ~1121 insertions, mais churn cohérent (2 PRs
   internes, code + tests + specs + YAML alignés), relisible.
8. **Dev-validated** — bundle déployé `dcm-dev` ; job `dcm_gold_forecast` run
   7453166992622 TERMINATED SUCCESS ; `gold_dbx_compute_forecast_daily`
   `object_type='PIPELINE'` (19592 lignes, 2500 pipelines) ;
   `pipeline_cost_daily/rolling` matérialisés (SC-002 PASS 0 dup ; SC-003
   résiduel documenté).

## Findings

- 🟢 note pipeline_cost_daily.py : SQL généré, noms de tables issus de la config `specs` (non user-input) — pas de risque d'injection.
- 🟢 note : diff volumineux (~1121 l.) mais cohérent (2 PRs internes couplées) et intégralement testé.

## Verdict

**PASS** — gates verts (ruff clean, 614 pytest pass), aucun blocker, aucun
risque. Commit débloqué.
