# Review — merge `origin/develop` dans `dataeng/019-usage-gold-fact`

**Scope** : résolution du conflit de merge pour la PR #234 (`dataeng/019-usage-gold-fact` → `develop`).
Le reste du diff provient de commits déjà mergés/revus sur `develop` (features 020,
gold_dbx_workspace, curated purge, dp-dcm-sync-infra) — aucune modification de code
métier apportée ici, uniquement la fusion.

## Conflit résolu

Un seul conflit réel (`UU`) : `packages/dcm-databricks-pipeline/pyproject.toml`,
section `[project.scripts]`. Les deux branches ajoutaient chacune un nouveau
point d'entrée wheel distinct :

- `dataeng/019-usage-gold-fact` (HEAD) : `dcm-gold-dbx-usage = "pipelines.gold_dbx_usage.entrypoint:run"`
- `origin/develop` : `dcm-gold-dbx-workspace = "pipelines.gold_dbx_workspace.entrypoint:run"`

Conflit purement additif (deux lignes indépendantes touchant la même zone du
fichier) — résolution : conserver les deux lignes, aucune perte de
fonctionnalité des deux côtés.

## Vérification post-merge

- `uv run pytest` (suite complète du package, incluant les nouveaux modules
  `gold_dbx_workspace`, `system_tables.purge_*` venus de `develop`) :
  **388 passed** (contre 348 avant merge — 40 tests supplémentaires
  apportés par `develop`, aucune régression).

**Verdict** : **PASS**
