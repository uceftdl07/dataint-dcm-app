# Review report — T001a (neutralisation efficience warehouse serverless)

**Date** : 2026-09-10 · **Branche** : `spike/serverless_cluster` · **Base** : `develop`
**Task** : T001 (domaine `dataeng`), sous-tâche **T001a** sur 7
**Package** : `packages/dcm-databricks-pipeline`
**Diff staged** : **10 fichiers de code**, +607 / −94 — plus ce rapport et
`review-report-specs.md`, deux artefacts Markdown non couverts par les gates. Ils sont joints
ici plutôt que dans un commit séparé : un commit de rapports de revue exigerait son propre
rapport de revue, et cette régression n'a pas de point fixe.

## Gates — ce que `dcm-review.sh` a rendu, et pourquoi il est ici inexploitable

Sortie brute du script automatisé, conservée telle quelle :

| Gate | Status (script) | Detail (script) |
|------|--------|--------|
| ruff | FAIL | `ANN001 Missing type annotation for function argument 'gold_module' --> tests/test_dlt_workflow.py:251:60` |
| mypy | FAIL | `pipelines/common/models.py: error: Source file found twice under different module names: "common.models" and "pipelines.common.models"` |
| pytest | FAIL | `ImportError while loading conftest '…/packages/dcm-databricks-pipeline/…'` |

**Ces trois FAIL ne sont pas imputables au diff.** Cause racine :
[`dcm-review.sh:154,164`](../../spec-kit-dcm-workflow/scripts/dcm-review.sh#L154) invoque
`ruff check .` et `pytest` **nus**, sans `uv run` — donc avec les binaires du PATH système et
hors de l'environnement du projet géré par `uv`. Le `conftest.py` du package n'y trouve pas ses
dépendances, d'où l'`ImportError`. Ce n'est pas un détail de forme : tant que ce script
n'utilise pas `uv run`, **le gate `tests` de ce package ne teste rien** et son verdict est du
bruit.

Mesures refaites avec les invocations correctes, depuis `packages/dcm-databricks-pipeline` :

| Gate | Commande | Résultat |
|---|---|---|
| **tests** | `uv run pytest -q` | ✅ **731 passed in 0.75s** |
| **tests (ciblés)** | `uv run pytest tests/gold_dbx_compute -q` | ✅ **397 passed** |
| **lint (périmètre du diff)** | `uv run ruff check` sur les **10 fichiers touchés** | ✅ **All checks passed!** |
| **lint (dépôt)** | `uv run ruff check .` | ⚠️ **269 errors** — **identique au HEAD**, donc **0 introduite**. Le fichier incriminé par le script, `tests/test_dlt_workflow.py`, **n'est pas dans le diff** (vérifié : 0 correspondance dans `git diff --cached --name-only`) |
| **types** | `uv run mypy pipelines` | ⛔ **inexécutable**, cause préexistante : `pipelines/sqs_to_volume_drain.py` crée une ambiguïté `common.models` vs `pipelines.common.models` qui arrête mypy avant toute vérification (`errors prevented further checking`). Fichier **hors diff**. mypy n'a jamais pu tourner sur ce package |
| **format** | `ruff format --diff`, HEAD vs worktree, fichier par fichier | ✅ **aucune régression** : `specs.py` 101 → **93** lignes de diff (amélioré), les 9 autres inchangés. Aucun des 50 fichiers non concernés reformaté (critère arbitré dans `tasks.md`) |

## Checklist de revue

1. **Secrets** — PASS, et le diff en **retire** deux. `README.md` documentait
   `token = dapi...` sous `[DEFAULT]` ; `pipelines/common/runtime.py` avait
   `LOCAL_DEBUG_PROFILE = "DEFAULT"`, soit un PAT comme **défaut d'exécution** de tout debug
   local. Les deux passent à OAuth U2M `dcm-dev`. Aucun credential ajouté.
2. **Anti-patterns** (`dcm-python`) — PASS. Pas d'import relatif, pas de handler sync, SQL
   construit par f-string sur des identifiants et des seuils venant de constantes du package
   (pas d'entrée utilisateur), docstrings au niveau de densité du module de référence
   `pipeline_cost_daily.py`.
3. **Critères d'acceptation du sub-spec** — couverts :
   - 7 champs d'efficience à NULL si serverless → 3 tests, dont un portant sur le **SELECT
     final** avec les lignes de commentaire retirées, pour qu'un commentaire ne puisse pas
     faire passer l'assertion ;
   - métriques d'activité préservées → 1 test sur les 7 colonnes ;
   - `is_serverless` porté en colonne, cascade à 3 étages → 1 test ;
   - propagation au `_rolling` → 2 tests ;
   - garde serverless du rule engine → 1 test de non-régression ;
   - filtre `as_of_date` des 6 CTE `latest_*` → 2 tests, dont
     `assert "MAX(as_of_date) FROM …_rolling WHERE" not in query` qui **interdit la régression**
     vers un `MAX` par fenêtre.
4. **Périmètre** — PASS. 10 fichiers, tous sous `packages/dcm-databricks-pipeline`, périmètre
   `dataeng` de l'intake. Aucun fichier backend/frontend, aucune refacto hors sujet.
5. **Tests pour tout changement de comportement** — PASS (9 tests ajoutés, cf. point 3).
6. **Small PR** — PASS. +607/−94 sur 10 fichiers, dont ~60 % de docstrings et de commentaires
   de colonnes. Le reste des 7 sous-tâches est explicitement séquencé.
7. **Story Jira** — N/A : dispatch non exécuté (voir commit précédent).

## Validation sur données réelles (critère de sortie de la story)

Déployé `-t dev_local -p dcm-dev` (jamais `prod`), 2 runs `TERMINATED / SUCCESS`
(`326427366507454` full refresh des 2 tables utilization, `290448228844802` reconstruction de
`recommendations`), validé par Statements API sur `dcm-dev` / warehouse `fcc5098720414937`.

- **SC-001 atteint** : 0 fuite sur **15 496** jours-warehouse serverless, sur les 7 champs.
- `is_serverless` non NULL sur **16 709/16 709** lignes recalculées.
- `running_hours` / `active_query_hours` servis à **100 %** des lignes serverless.
- Lignes classic/pro **intactes** : 1 213/1 213 gardent `idle_pct` et `estimated_savings_usd`.
- Économies serverless : **225 261 $ → NULL** (dont 178 615 $ AWS + 46 646 $ Azure).
- Backlog de recos : « Warehouse surdimensionné » 665 → **87 OPEN, dont 0 serverless** ;
  « Auto-stop manquant » 6 → **0** ; **+62 recos actionnables démasquées** (27 105 $).

## Findings

```
spec-kit-dcm-workflow/scripts/dcm-review.sh:154: 🟡 risk: `ruff check .` et `pytest` invoques sans `uv run` -> le gate `tests` de ce package ne teste rien et rend un FAIL de bruit. A corriger dans un commit d'outillage dedie (pas melange a du pipeline)
packages/dcm-databricks-pipeline/pipelines/sqs_to_volume_drain.py:1: 🟡 risk: ambiguite de module qui empeche mypy de tourner sur tout le package (prealable, hors diff) -> le gate `types` est aveugle depuis toujours
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/warehouse_utilization_daily.py:627: 🟢 note: `idle_pct` est reference dans les CASE tout en etant realiase en sortie. Databricks supporte les alias lateraux, mais la garde `WHEN is_serverless THEN NULL` en PREMIERE branche rend la resolution indifferente — verifie sur donnees reelles (0 fuite)
packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/recommendations.py:408: 🟢 note: la garde serverless n'enleve pas 6 recos auto-stop, elle EMPECHE une regression de +579 : un `has_auto_stop` passe a NULL declenche la regle via son `COALESCE(..., false)`
specs/025-serverless-compute-page/tasks.md:1: 🟢 note: SC-013 ouvert — 75 + 162 lignes orphelines (0 $) non reecrites par le recalcul. `DELETE` ponctuel prepare, verifie (difference symetrique nulle vs l'anti-jointure), puis REFUSE par le classifieur de permissions et NON contourne. Correctif structurel tracé en T001h
```

0 🔴 blocker · 2 🟡 risk · 3 🟢 note

## Verdict

Gates verts **sur le périmètre du diff** (tests 731 passed, lint 0 erreur sur les 10 fichiers,
0 régression de format), 0 blocker. Les 2 🟡 sont des défauts d'outillage **préexistants et hors
diff**, tracés ici pour être corrigés séparément — ils ne portent pas sur le code livré.

**Verdict**: **PASS**
