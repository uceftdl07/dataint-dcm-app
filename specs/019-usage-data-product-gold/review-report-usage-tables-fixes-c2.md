# DCM Review Report

**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `dataeng/019-usage-tables-fixes` (base: `develop`)
**Stack**: python (module `pipelines`)
**Verdict**: **FAIL** (fail=2 warn=0 skip=0)

## Changed files

```
packages/dcm-databricks-pipeline/pipelines/gold_dbx_usage/entrypoint.py
packages/dcm-databricks-pipeline/tests/conftest.py
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_entrypoint.py
packages/dcm-databricks-pipeline/tests/gold_dbx_usage/test_entrypoint.py
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

Meme baseline que le commit precedent : `ruff` et `mypy` tournent sur le paquet
entier (`dcm-review.sh:154`) et rendent sur `develop` les memes 269 + 1 erreurs,
toutes dans `pipelines/dlt_0*.py`, `pipelines/sqs_to_volume_drain.py` et
`tests/test_dlt_*.py`, aucun fichier de ce commit. Aucune regression. Commit passe
avec `DCM_SKIP_PRE_COMMIT_REVIEW=1`, revue de skills ci-dessous.

`pytest` : 592 PASS avec ce seul lot applique.

## Revue de skills (`dcm-python`, `dcm-testing`, `dcm-verify`)

Perimetre staged : `table_query_performance_daily.py`, `table_popularity_daily.py`,
`table_catalog.py`, `sql_helpers.py` (ajout de `LINEAGE_NAMED_OBJECT_TYPES`),
`tests/conftest.py` (ajout de `strip_sql_comments`) et les deux fichiers de tests
correspondants.

```
pipelines/gold_dbx_usage/table_catalog.py:1: 🟢 note: aucun changement de code dans
  ce fichier — uniquement docstring et commentaires. Verse dans ce lot par cohesion
  de sujet (les builders satellites), pas parce qu'il corrige un comportement.
```

1. Aucun secret, `.env` ni credential : le diff ne cite que des noms de tables UC.
2. Anti-patterns `dcm-python` : aucun. Le seul symbole nouveau de `sql_helpers`
   consomme ici est `LINEAGE_NAMED_OBJECT_TYPES` ; `split_full_name` disparait des
   deux builders au profit des colonnes natives du lineage.
3. Comportement couvert : chaque changement de requete a son test — agregation au
   grain avant jointure, discriminant `statement_id`, elargissement de `source_type`,
   colonnes natives au GROUP BY, numerateur et denominateur de `failure_rate_pct`
   comptant la meme chose, jointure sans egalite de dates, partition de `RANK()` par
   `cloud_provider`, `downstream_fanout` cote CIBLE.
4. Perimetre : `packages/dcm-databricks-pipeline` uniquement.
5. `strip_sql_comments` dans `conftest.py` sert les assertions d'ABSENCE : sur un
   builder teste via son texte SQL, « ce predicat ne doit pas etre la » porterait
   sinon aussi sur les commentaires.
6. Small PR : 288 insertions, 117 suppressions sur 7 fichiers.

**Verdict de la revue de skills** : PASS (0 🔴, 0 🟡, 1 🟢).
