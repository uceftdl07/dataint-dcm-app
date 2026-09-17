# DCM Review Report

**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `dataeng/019-usage-tables-fixes` (base: `develop`)
**Stack**: python (module `pipelines`)
**Verdict**: **FAIL** (fail=2 warn=0 skip=0)

## Changed files

```
packages/dcm-databricks-pipeline/pipelines/gold_dbx_usage/entrypoint.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_usage/specs.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_usage/sql_helpers.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_usage/table_catalog.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_usage/table_daily.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_usage/table_popularity_daily.py
packages/dcm-databricks-pipeline/pipelines/gold_dbx_usage/table_query_performance_daily.py
packages/dcm-databricks-pipeline/tests/conftest.py
packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_entrypoint.py
packages/dcm-databricks-pipeline/tests/gold_dbx_usage/test_entrypoint.py
packages/dcm-databricks-pipeline/tests/gold_dbx_usage/test_sql_helpers.py
packages/dcm-databricks-pipeline/tests/gold_dbx_usage/test_table_daily.py
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

Les gates `ruff` et `mypy` portent sur le paquet entier (`dcm-review.sh:154`,
`ruff check .`), pas sur les fichiers du diff. Baseline `develop` deja mesuree aux
commits precedents de cette branche :

| Gate | Ce commit | `develop` |
|------|-----------|-----------|
| ruff | 269 erreurs | 269 erreurs |
| mypy | 1 erreur | 1 erreur |
| pytest | 612 PASS (605 avant) | — |

Chiffres identiques : **aucune regression**. Les erreurs portent sur
`pipelines/dlt_0*.py`, `pipelines/sqs_to_volume_drain.py` et `tests/test_dlt_*.py`,
aucun n'etant touche par ce diff. L'erreur mypy est un probleme de layout
(`pipelines/common/models.py` vu sous deux noms de module), pas un defaut de typage.
`ruff check` sur les seuls fichiers modifies : PASS.

Commit passe avec `DCM_SKIP_PRE_COMMIT_REVIEW=1` (echappatoire documentee du skill,
et non `--no-verify` : les autres hooks tournent). La revue de skills ci-dessous a
bien eu lieu.

## Revue de skills (`dcm-python`, `dcm-testing`, `dcm-verify`)

Perimetre staged : `pipelines/gold_dbx_usage/{table_daily,sql_helpers,specs}.py`,
`tests/gold_dbx_usage/test_table_daily.py`.

Objet : le cout d'une requete n'etait calculable que pour un SQL warehouse. Le pont
vers la facturation reposait sur `COALESCE(compute.cluster_id, compute.warehouse_id)`,
dont le premier terme n'apporte rien : mesure dev sur 66 jours,
`query_history.compute.cluster_id` est vide sur les 90 460 458 statements (la colonne
nomme le TYPE du compute, `CLASSIC_COMPUTE`, pas la ressource), alors que
`billing_usage.usage_metadata.cluster_id` est richement rempli (9 356 230 lignes).
La facture connait donc parfaitement les clusters, mais la requete ne les nomme
jamais. Resultat : 41,9 % des statements et 54,5 % de la duree n'avaient aucun seau
rattachable, alors que la facture existe sous `usage_metadata.job_id`.

1. Aucun secret, `.env` ni credential : le diff ne cite que des noms de tables UC.
2. Anti-patterns `dcm-python` : aucun. Constantes nommees plutot que litteraux SQL
   en dur, imports absolus, annotations completes.
3. Comportement couvert par des tests : 5 nouveaux tests couvrent la disjonction des
   trois seaux (non-double-comptage), la cle de pont cote requete et sa priorite, le
   role discriminant de `cost_basis` dans les deux jointures, le libelle qui suit le
   cout et non le rattachement, et le `mixed` a l'agregation.
4. Perimetre : `packages/dcm-databricks-pipeline` uniquement.
5. Validation sur donnee reelle (lecture seule, fenetre de 3 jours, SQL rendu
   execute sur le warehouse dev) — le SQL est valide et le grain preserve :

   | | lignes | acces | acces chiffres | cout |
   |---|---|---|---|---|
   | avant | 687 413 | 19 028 371 | 2 980 112 | 1 434,61 |
   | apres | 687 413 | 19 028 371 | 3 407 729 | 1 716,90 |

   Lignes et acces INCHANGES : le correctif n'ajoute ni ne perd aucune ligne, il ne
   chiffre que ce qui ne l'etait pas. Acces chiffres +14,3 %, cout attribue +19,7 %.

   Repartition par seau sur cette meme fenetre, qui verifie sur donnee reelle deux
   affirmations du code plutot que de les supposer :

   | `cost_basis` | lignes | acces chiffres | cout |
   |---|---|---|---|
   | `warehouse_prorata` | 138 518 | 2 964 925 | 1 377,43 |
   | `serverless_job_prorata` | 86 294 | 419 998 | 248,82 |
   | `mixed` | 545 | 22 806 | 90,65 |
   | `cluster_prorata` | 0 | — | — |
   | NULL | 462 056 | 0 | — |

   `cluster_prorata` ne produit AUCUNE ligne : le seau cluster, preexistant, est
   inatteignable et le reste jusqu'a ce que la source publie l'identifiant. Le total
   du seau warehouse egale au centime le montant d'avant l'eclatement des libelles :
   ce qui etait chiffre l'etait donc a 100 % via un warehouse, et le libelle unique
   d'origine masquait ce fait au lieu de resumer deux cas.
6. Small PR : 305 insertions, 54 suppressions sur 4 fichiers.

```
pipelines/gold_dbx_usage/table_daily.py:423: 🟡 note: `response['status_code'] NOT IN
  ('200', '0')` — le litteral `'0'` est mort (aucune ligne d'audit ne le porte).
  Deja signale au commit c3, toujours non corrige : hors perimetre de ce diff.
pipelines/gold_dbx_usage/sql_helpers.py:123: 🟡 note: `non_null_entity_type_predicate`
  n'est plus appele que par son propre test. Deja signale au commit c3.
specs/019-usage-data-product-gold: 🟢 note: le gain au grain gold (+19,7 %) est
  nettement inferieur a la couverture de duree gagnee en amont (45,5 % -> 88,3 % des
  heures de `query_history`) parce que 90 % des statements serverless n'ont aucune
  ligne de lignage vers un objet nomme et n'atteignent donc jamais cette table. Trou
  de COUVERTURE DU LIGNAGE, distinct du trou de cout ferme ici.
```

**Verdict de la revue de skills** : PASS (0 🔴, 2 🟡 hors perimetre, 1 🟢).
