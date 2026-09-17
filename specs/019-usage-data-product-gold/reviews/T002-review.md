# DCM Review Report — T002 (Gold fait usage)

**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `dataeng/019-usage-gold-fact` (base: `develop`)
**Stack**: python (module `pipelines`)
**Scope**: nouveau module `pipelines/gold_dbx_usage/` + `tests/gold_dbx_usage/` + `resources/job_dcm_gold_dbx_usage.yml` + `pyproject.toml` (+1 entry point). Aucun fichier pré-existant modifié.

**Verdict**: **PASS**

## Gates (scopées au diff de cette task)

| Gate | Status | Detail |
|------|--------|--------|
| ruff (module nouveau) | PASS | `ruff check pipelines/gold_dbx_usage/ tests/gold_dbx_usage/` → 0 violation |
| pytest (suite complète) | PASS | `pytest -q` → 332 passed (dont 49 nouveaux dans `tests/gold_dbx_usage/`), 0 régression |
| mypy | SKIP (pré-existant, hors scope) | `mypy pipelines` échoue avec `Source file found twice under different module names: "common.models"` — provient de `pipelines/sqs_to_volume_drain.py` (import non qualifié), confirmé identique sur `develop` avant toute modification de cette task via `git stash -u`. Pas de nouveau fichier de T002 impliqué. |

## Note sur `ruff check .` / `mypy pipelines` non-scopés (repo entier)

`dcm-review.sh` (générique, non diff-aware pour ruff/mypy) exécute ces deux
gates sur tout le package et remonte donc aussi des violations pré-existantes
hors scope de T002 (ex. `ANN001` dans `tests/test_dlt_workflow.py`, jamais
touché ici). Ces échecs existent indépendamment de cette task — vérifié en
scope-restreignant les gates aux fichiers ajoutés/modifiés par T002
ci-dessus, qui sont tous verts.

## Déploiement dev (AC explicite du sub-spec)

Job `dcm_gold_dbx_usage` déployé (`databricks bundle deploy --target dev_local`)
et exécuté (`databricks bundle run dcm_gold_dbx_usage`) → **TERMINATED SUCCESS**.
2 bugs SQL réels détectés et corrigés pendant cette validation (non détectables
par les tests unitaires FakeSpark, qui ne valident pas la grammaire SQL réelle) :
- `table_daily.py` : `user_identity` est un STRUCT (email, subject_name), pas
  STRING → `COALESCE` corrigé pour extraire les champs du struct.
- `table_query_performance_daily.py` : CTE `query_history_filtered` sans
  `WHERE` avant le filtre incrémental `AND ...` → `PARSE_SYNTAX_ERROR`, `WHERE 1=1`
  ajouté.

## Next

- PR vers `develop`
- `/speckit.dcm.sync-status`
