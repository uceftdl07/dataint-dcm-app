# DCM Review Report — T001

**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `dataeng/027-usage-table-deleted-flag` (base: `develop`)
**Task**: T001 — DataEng usage table deleted flag ([sub-spec](stories/T001-usage-table-deleted-flag.md)) · Jira DCINT-356
**Stack**: python (module `pipelines`)
**Mode**: `--commit` (revue du diff *staged*)
**Verdict**: **PASS**

## Périmètre staged

26 fichiers, +1415 / −21.

| Catégorie | Fichiers |
|---|---|
| Pipeline | `pipelines/gold_dbx_usage/` — `sql_helpers.py`, `specs.py`, `table_catalog.py`, `table_governance.py`, `forecast_daily.py`, `recommendations.py`, `entrypoint.py` |
| Tests | `tests/gold_dbx_usage/` — 7 fichiers, +361 lignes |
| Spec | `specs/027-usage-table-deleted-flag/` (hors artefacts gitignorés) + `specs/active-epics.json` |

## Gates

> ⚠️ **`dcm-review.sh` a rendu FAIL pour une raison d'environnement, pas de code** : il invoque `ruff`/`pytest` en direct, or ce package les fournit via `uv`/`.venv` et les shims pyenv ne les exposent pas (`pyenv: ruff: command not found`). Il a aussi vu « (none detected vs base) » — normal en pre-commit, la branche n'a encore aucun commit. Les gates ont donc été rejoués via `.venv/bin/`, après `uv sync --extra dev`.

| Gate | Statut | Détail |
|------|--------|--------|
| **pytest** | **PASS** | `988 passed` — dont 22 nouveaux tests pour 027 |
| **ruff** (périmètre modifié) | **PASS** | `ruff check pipelines/gold_dbx_usage tests/gold_dbx_usage` → *All checks passed* |
| **ruff** (package entier) | **NO REGRESSION** | 242 erreurs **avec** 027, 242 erreurs **sur `develop`** — mesuré par `git stash` |
| **mypy** (périmètre modifié) | **NO REGRESSION** | 10 erreurs / 1 fichier avant et après ; mêmes erreurs dans `forecast_daily.py` (SDK Databricks, `StatementStatus | None`), seuls les numéros de ligne bougent (430 → 464) |
| **mypy** (gate requis ?) | **N/A** | `dcm-verify` réserve `mypy` à `dcm-backend` ; la matrice de ce package est **ruff + pytest** |

**Gate réellement contraignant** : la CI du package n'exécute que `pytest` — `ruff` et `mypy` sont commentés dans `.github/workflows/dbx_main_workflow.yml` (lignes 73-74).

## Checklist de revue

| # | Point | Résultat |
|---|---|---|
| 1 | Aucun secret / `.env` / credential | ✅ scan du diff staged — seule occurrence : le mot « Secrets » dans un tableau markdown du plan |
| 2 | Anti-patterns `dcm-python` | ✅ aucun `print()`, aucun import relatif, Python 3.12, constantes `LIFECYCLE_STATE_*` au lieu de littéraux SQL |
| 3 | Critères d'acceptation couverts | ✅ 16/16 — 10 par tests unitaires, 6 par la validation dev (§2.2 à §2.7 du quickstart) |
| 4 | Fichiers ⊆ périmètre de l'intake | ✅ `packages/dcm-databricks-pipeline` uniquement, conforme à `intake.json` |
| 5 | Tests pour tout changement de comportement | ✅ 22 tests ajoutés, un par cas de détection et par exclusion |
| 6 | Small PR | ✅ 14 fichiers de code, 11 de spec — pas de churn hors sujet, aucune refacto opportuniste |
| 7 | Story Jira porte un nom de branche | ✅ DCINT-356 → `dataeng/027-usage-table-deleted-flag`, jamais un SHA |

## Findings

```
🟡 risk  packages/dcm-databricks-pipeline: 242 erreurs ruff et 113 mypy préexistantes sur develop, et les
         deux gates sont commentés en CI — dette d'équipe antérieure à 027, hors périmètre de cette task.
         À traiter dans une task dédiée plutôt qu'en catimini ici.

🟢 note  pipelines/gold_dbx_usage/entrypoint.py: _log_deleted_table_count() ajoute un COUNT sur 1,44 M
         lignes après chaque écriture du registre. Coût marginal face aux 5 min du job, assumé pour FR-018.

🟢 note  gold_dbx_usage_table_governance porte 1 350 796 lignes avec recommended_action/severity à NULL.
         Par conception : mesures brutes conservées, jugement neutralisé.

🟢 note  research.md, data-model.md, quickstart.md et merge-strategy.md sont gitignorés (convention
         d'équipe, .gitignore lignes 198-203). Le relecteur de la PR n'aura donc pas le raisonnement de
         conception sous les yeux — le contexte utile a été reporté dans la sub-spec, qui est versionnée.
```

Aucun 🔴 blocker.

## Validation sur données réelles

Déploiement `dev_local` puis exécution des jobs — détail dans la [sub-spec](stories/T001-usage-table-deleted-flag.md) :

| Contrôle | Attendu | Obtenu |
|---|---|---|
| Faux positifs | 0 | **0** |
| Invariant `is_deleted`/`deleted_at` | 0 | **0** |
| Prévisions sur table supprimée | 0 | **0** (témoin : 1 682 723 lignes produites) |
| Recos `OPEN` sur table supprimée | 0 | **0** (témoin : 35 265 passées `RESOLVED`) |
| Historique d'usage préservé | > 0 | **1 395 864** |
| Idempotence | comptes identiques | **4/4** |

## Next

- Verdict **PASS** → `git commit` débloqué par le stamp
- Puis `/speckit.dcm.publish-pr --spec 027-usage-table-deleted-flag --task T001`
- Rappel cross-epic : **027 merge avant 024** (overlap sur `gold_dbx_usage/specs.py`, et 024 dépend de `is_deleted`)
