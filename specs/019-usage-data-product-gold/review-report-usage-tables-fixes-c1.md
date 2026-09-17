# DCM Review Report

**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `dataeng/019-usage-tables-fixes` (base: `develop`)
**Stack**: python (module `pipelines`)
**Verdict**: **FAIL** (fail=2 warn=0 skip=0)

## Changed files

```
(none detected vs base)
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

Les gates `ruff` et `mypy` sont lances sur le paquet entier (`dcm-review.sh:154`,
`ruff check .`), pas sur les fichiers du diff -- `CHANGED_FILES` n'est qu'affiche
dans ce rapport. Baseline mesuree sur `develop` dans un worktree jetable :

| Gate | Ce commit | `develop` |
|------|-----------|-----------|
| ruff | 269 erreurs | 269 erreurs |
| mypy | 1 erreur | 1 erreur |
| pytest | 585 PASS | — |

Chiffres identiques : **aucune regression**. Les erreurs portent sur
`pipelines/dlt_0*.py`, `pipelines/sqs_to_volume_drain.py` et `tests/test_dlt_*.py`,
aucun n'etant modifie par ce commit. L'erreur mypy est un probleme de layout
(`pipelines/common/models.py` vu sous deux noms de module), pas un defaut de typage.

Pour ce paquet, les etapes ruff/mypy sont commentees dans
`.github/workflows/dbx_main_workflow.yml` (lignes 73-74) : ce gate local est le seul
endroit ou elles sont exigeantes, et il echoue sur `develop` depuis avant ce travail.

Commit passe avec `DCM_SKIP_PRE_COMMIT_REVIEW=1` (echappatoire documentee du skill,
et non `--no-verify` : les autres hooks tournent). La revue de skills ci-dessous a
bien eu lieu.

## Revue de skills (`dcm-python`, `dcm-testing`, `dcm-verify`)

Perimetre staged : `pipelines/gold_dbx_usage/entrypoint.py`, `tests/conftest.py`,
`tests/gold_dbx_usage/test_entrypoint.py`, `tests/gold_dbx_compute/test_entrypoint.py`.

```
pipelines/gold_dbx_usage/entrypoint.py:58: 🟡 risk: docstring de `_resolve_lower_bound`
  — retrospectif (« cette fonction retournait exactement ce dernier ») et chiffres
  dates (« 4 des 8 derniers jours faux, ~15 600 cluster-jours manquants ») → reecrit
  en enonce de comportement. CORRIGE dans ce commit.
```

1. Aucun secret, `.env` ni credential : le diff ne cite que des noms de tables UC.
2. Anti-patterns `dcm-python` : aucun. Imports absolus, pas de handler sync, logging
   par `_LOGGER` avec formatage differe (`%s`), annotations completes.
3. Comportement couvert par des tests : 4 nouveaux tests attestent l'elargissement
   au jour manquant, la reprise du dernier jour ecrit, la cible/colonnes du scan, et
   le court-circuit de `--full-refresh` avant le scan (`spark.sql_calls == []`).
4. Perimetre : `packages/dcm-databricks-pipeline` uniquement.
5. `tests/gold_dbx_compute/test_entrypoint.py` est touche pour deleguer le fake
   `gap_scan_row` a `tests/conftest.py`, desormais partage par les deux domaines gold
   qui appellent le meme helper. Pas de refacto hors sujet.
6. Small PR : 197 insertions, 40 suppressions sur 4 fichiers.

**Verdict de la revue de skills** : PASS (1 🟡 corrige, 0 🔴).
