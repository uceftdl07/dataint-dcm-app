# T001 — Fenêtre précédente et autoscaling en gold

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: `dataeng/022-fenetre-precedente-et-autoscaling-en`
**Jira**: not dispatched (dispatch non exécuté sur cette feature)
**Depends on**: none
**Work type**: feature

## Description

`gold_dbx_compute_cluster_efficiency_rolling` ne porte aucune colonne de fenêtre
précédente, là où `cluster_cost_rolling` expose déjà `cost_usd_prev_window` : les
indicateurs `Lifetime_previous_period` et `IDLE_previous_period` demandés par les onglets
Overview et Efficiency n'ont donc aucune source. La configuration d'autoscaling
(`Autoscaling`, `min_node`, `max_node`) est dans le même cas : seul
`curated_dbx_compute_clusters` la porte, et le service compute-metrics du backend ne lit
que du gold et des dimensions. Enfin `cluster_name` manque aux deux tables efficiency
alors que les trois onglets doivent l'afficher.

Cette task ajoute ces colonnes à `cluster_efficiency_daily` (via la CTE `clusters_as_of`,
qui joint **déjà** `curated_dbx_compute_clusters` pour les types de node) puis à
`cluster_efficiency_rolling` (propagation par `latest_attrs`, fenêtre précédente par une
nouvelle CTE `prev_agg` en `LEFT JOIN`). Les deux tables sont ensuite recréées : le commit
`b102155` fait passer `active_hours` de `bigint` à `decimal` et
`MERGE WITH SCHEMA EVOLUTION` ajoute des colonnes mais ne convertit pas un type.

## Files to create/modify

- UPDATE `packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_efficiency_daily.py`
- UPDATE `packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_efficiency_rolling.py`
- UPDATE `packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/specs.py` (commentaires de colonnes)
- UPDATE `packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_cluster_efficiency_daily.py`
- CREATE/UPDATE `packages/dcm-databricks-pipeline/tests/gold_dbx_compute/test_cluster_efficiency_rolling.py`

## Sub-tasks

- [ ] Tests d'abord : assertions sur le SQL généré (`FakeSpark`) pour les 5 colonnes de
      `cluster_efficiency_daily` et les 7 de `cluster_efficiency_rolling`, dont la borne
      exacte de la fenêtre précédente.
- [ ] `cluster_efficiency_daily` : sélectionner `cluster_name`,
      `autoscale_enabled` (`min_autoscale_workers IS NOT NULL AND max_autoscale_workers IS NOT NULL`),
      `autoscale_min_workers`, `autoscale_max_workers`, `configured_worker_count` depuis
      la CTE `clusters_as_of` — sans nouvelle jointure.
- [ ] `cluster_efficiency_rolling` : propager les 5 colonnes via `latest_attrs`.
- [ ] `cluster_efficiency_rolling` : CTE `prev_agg` sur
      `(as_of_date - 2·window_days, as_of_date - window_days]`, `LEFT JOIN` sur
      `(cloud_provider, workspace_id, cluster_id, window_days)` — `window_days` dans la
      clé, sinon chaque ligne est multipliée par 4.
- [ ] `idle_pct_prev_window` pondéré par `uptime_hours` avec le même
      `NULLIF(SUM(CASE WHEN idle_pct IS NOT NULL THEN uptime_hours END), 0)` que la fenêtre
      courante — deux définitions différentes rendraient les colonnes incomparables.
- [ ] `column_comments` des 7 nouvelles colonnes dans `specs.py`, formule incluse.
- [ ] Gates : `pytest`, `ruff check`, `mypy --explicit-package-bases`.
- [ ] Migration dev : `DROP` des 2 tables, `bundle deploy -t dev`, `bundle run --only
      gold_cluster_efficiency_daily,gold_cluster_efficiency_rolling`.
- [ ] Vérifications dev de [quickstart.md](../quickstart.md) §4.1 à §4.6.

## Acceptance Criteria

- [ ] `cluster_efficiency_daily` expose `cluster_name`, `autoscale_enabled`,
      `autoscale_min_workers`, `autoscale_max_workers`, `configured_worker_count`.
- [ ] `cluster_efficiency_rolling` expose ces 5 colonnes **plus**
      `uptime_hours_prev_window` et `idle_pct_prev_window`.
- [ ] `uptime_hours_prev_window` d'une fenêtre de N jours égale la somme des
      `uptime_hours` quotidiens sur les N jours précédant `window_start` (vérifié sur le
      dev, écart < 0,01).
- [ ] Sans jour dans la fenêtre précédente, les deux colonnes valent `NULL` — jamais `0`.
- [ ] Autoscaling actif ⇒ `autoscale_enabled = true`, bornes renseignées,
      `configured_worker_count` `NULL`. Taille fixe ⇒ l'inverse exactement.
- [ ] Les métriques existantes de la table sont inchangées : les 13 agrégats de la CTE
      `agg` ne sont pas réécrits, et `active_hours <= uptime_hours` sur toutes les lignes.
- [ ] Les 4 fenêtres (1, 7, 30, 90) sont peuplées au même `as_of_date`.

## Tests

```bash
cd packages/dcm-databricks-pipeline
.venv/bin/python -m pytest tests/gold_dbx_compute/test_cluster_efficiency_daily.py \
                           tests/gold_dbx_compute/test_cluster_efficiency_rolling.py
.venv/bin/python -m pytest
uv run ruff check pipelines tests
uv run mypy pipelines --explicit-package-bases
```

## Out of scope

- `gold_dbx_compute_cluster_reliability_rolling` — aucun indicateur demandé ne s'y rattache.
- `cluster_cost_rolling` — porte déjà sa fenêtre précédente, non touchée.
- Toute lecture backend des nouvelles colonnes → T002.
- Recalcul historique au-delà de la profondeur disponible dans `cluster_efficiency_daily`.

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside `packages/dcm-databricks-pipeline`
- [ ] Diff stays reviewable (2 builders + specs + 2 tests)
- [ ] Sub-spec checkboxes reviewed
- [ ] Migration dev exécutée et vérifiée ; migration prod planifiée

## Notes

- Décisions : [research.md](../research.md) R1 (CTE `prev_agg` plutôt que l'élargissement
  de `agg`), R2 (sémantique de l'autoscaling, distribution mesurée), R3 (migration).
- Colonnes, types et cas `NULL` : [data-model.md](../data-model.md).
- Déploiement et requêtes de vérification : [quickstart.md](../quickstart.md).
- Modèle de référence pour la fenêtre précédente : `cluster_cost_rolling.py:115-141` —
  approche différente assumée (3 agrégats additifs là-bas, 13 dont 4 pondérées ici).
- Authentification Databricks **OAuth uniquement** ; aucun PAT, aucun `DATABRICKS_TOKEN`.
