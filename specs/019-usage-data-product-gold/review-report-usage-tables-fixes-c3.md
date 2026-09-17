# DCM Review Report

**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `dataeng/019-usage-tables-fixes` (base: `develop`)
**Stack**: python (module `pipelines`)
**Verdict**: **FAIL** (fail=2 warn=0 skip=0)

## Changed files

```
packages/dcm-databricks-pipeline/pipelines/gold_dbx_usage/entrypoint.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_usage/sql_helpers.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_usage/table_catalog.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_usage/table_popularity_daily.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_usage/table_query_performance_daily.py
packages/dcm-databricks-pipeline/tests/conftest.py
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_entrypoint.py
packages/dcm-databricks-pipeline/tests/gold_dbx_usage/test_entrypoint.py
packages/dcm-databricks-pipeline/tests/gold_dbx_usage/test_table_popularity_daily.py
packages/dcm-databricks-pipeline/tests/gold_dbx_usage/test_table_query_performance_daily.py
```

## Gates

| Gate | Status | Detail |
|------|--------|--------|
| ruff | FAIL | ANN001 Missing type annotation for function argument `gold_module`    --> tests/test_dlt_workflow.py:251:60     | 251 |  |
| mypy | FAIL | pipelines/sqs_to_volume_drain.py: error: Source file found twice under different module names: "common.models" and "pipe |
| pytest | PASS | ok |

## Next

- Agent: cross-check diff vs `dcm-python` / `dcm-react` skills + sub-spec acceptance criteria
- If PASS: open PR to integration branch
- If FAIL: fix and re-run `/speckit.dcm.review`

---

## Analyse du verdict FAIL

Meme baseline que les deux commits precedents : `ruff` et `mypy` tournent sur le
paquet entier (`dcm-review.sh:154`) et rendent sur `develop` les memes 269 + 1
erreurs, toutes dans `pipelines/dlt_0*.py`, `pipelines/sqs_to_volume_drain.py` et
`tests/test_dlt_*.py`, aucun fichier de ce commit. Aucune regression. Commit passe
avec `DCM_SKIP_PRE_COMMIT_REVIEW=1`, revue de skills ci-dessous.

`pytest` : 607 PASS. `ruff` sur les seuls fichiers du commit : clean.

## Revue de skills (`dcm-python`, `dcm-testing`, `dcm-verify`)

Perimetre staged : `table_daily.py`, `specs.py`, `sql_helpers.py` (reste),
`tests/gold_dbx_usage/test_table_daily.py`, `tests/gold_dbx_usage/test_sql_helpers.py`.

```
pipelines/gold_dbx_usage/sql_helpers.py:123: 🟡 risk: `non_null_entity_type_predicate`
  n'est plus appele par aucun builder — `table_daily` partitionne desormais sur
  `statement_id IS NULL` / `IS NOT NULL`. Seuls son propre test et un commentaire
  (ligne 47) la citent. Code mort a supprimer, ou a garder si un usage est prevu.
  NON TRAITE ici : la suppression est une decision, pas un effet de bord de ce lot.

pipelines/gold_dbx_usage/table_daily.py:423: 🟡 risk: `response['status_code'] NOT IN
  ('200', '0')` — le litteral `'0'` ne correspond a aucune valeur du domaine observe
  (`200`, `400`, `403`, `404`, `503`). Il est inerte aujourd'hui, mais suggere a tort
  qu'un `'0'` signifierait un succes. NON TRAITE ici : change le SQL, donc a decrire
  et valider comme un correctif a part.

pipelines/gold_dbx_usage/table_daily.py:1: 🟢 note: le module reste le plus dense du
  paquet (569 lignes, 8 CTE + un UNION ALL a 4 branches). Les 4 branches doivent
  garder une liste de colonnes identique — contrainte a rappeler a tout ajout.
```

1. Aucun secret, `.env` ni credential : le diff ne cite que des noms de tables UC.
2. Anti-patterns `dcm-python` : aucun. Pas de f-string sans placeholder, imports
   absolus, expressions SQL construites depuis des constantes du module.
3. Comportement couvert : chaque changement de requete a son test dans
   `test_table_daily.py`. Les assertions d'ABSENCE passent par `strip_sql_comments`
   pour ne pas dependre de la prose.
4. Perimetre : `packages/dcm-databricks-pipeline` uniquement.
5. Les `column_comments` de `specs.py` sont publies dans Unity Catalog par
   `merge_into_table` : les chiffres dates qu'ils portaient etaient visibles des
   consommateurs de la table. Retires.
6. Small PR : 863 insertions, 280 suppressions sur 5 fichiers — le lot le plus gros
   des trois, et non divisible davantage : les 4 branches du `UNION ALL` doivent
   changer ensemble (colonnes `rows_written`/`data_written_bytes`,
   `cost_attribution_method`, `existence_proven`).

**Verdict de la revue de skills** : PASS (0 🔴, 2 🟡 documentes et non traites, 1 🟢).
