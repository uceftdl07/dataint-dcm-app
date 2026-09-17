# T002 — Filtre dur `ALL_PURPOSE` + endpoints compute job & pipeline + forecast PIPELINE

**Domain**: backend
**Package**: packages/dcm-backend, packages/dcm-commons
**Branch**: `backend/024-filtre-dur-all-purpose-endpoints-schemas`
**Jira**: [DCINT-328](https://tdf.atlassian.net/browse/DCINT-328) (Epic [DCINT-325](https://tdf.atlassian.net/browse/DCINT-325))
**Depends on**: T001 (tables gold purgées + rollup DLT déployés et vérifiés en dev)
**Work type**: feature

## Description

Exposer les **3 familles** de compute séparément :

1. **Durcir** `cluster_type = 'ALL_PURPOSE'` en prédicat **dur** sur les services cluster
   (aujourd'hui `cluster_type` n'est qu'un `column_filter` optionnel dans
   `compute_metrics_clusters.py`, jamais appliqué par défaut — c'est la pollution résiduelle
   côté API même si le gold est purgé). Défense en profondeur au-dessus de T001a.
2. **Créer** les services / routes **compute job** (grain `job_id`, lit
   `gold_dbx_compute_job_cluster_cost_rolling` — table déjà existante mais **jamais exposée**)
   et **compute pipeline** (grain `dlt_pipeline_id`, lit `gold_dbx_compute_pipeline_cost_rolling`
   produit par T001c).
3. **Étendre** le forecast à `object_type = PIPELINE` (coût + DBU).
4. **Schémas** dcm-commons correspondants.

Contrats de réponse figés dans [contracts/compute-job-pipeline.md](../contracts/compute-job-pipeline.md).

## Files to create/modify

- UPDATE `packages/dcm-backend/app/api/services/compute_metrics_clusters.py` — prédicat dur `cluster_type = 'ALL_PURPOSE'`
- CREATE `packages/dcm-backend/app/api/services/compute_metrics_jobs.py` — service grain `job_id`
- CREATE `packages/dcm-backend/app/api/services/compute_metrics_pipelines.py` — service grain `dlt_pipeline_id`
- UPDATE `packages/dcm-backend/app/api/services/compute_metrics_common.py` — descendre les helpers fenêtre partagés (`_window_where`, `_window_block`, `_window_period`, `_bounds_sql`, `_normalize_prev_cost`, `ClusterWindowDays`) si pas déjà mutualisés
- UPDATE `packages/dcm-backend/app/api/routes/compute_metrics.py` — routes `/compute/jobs/overview` (+`/cost`), `/compute/pipelines/overview` (+`/cost`), forecast `object_type=PIPELINE`
- UPDATE `packages/dcm-commons/...` — schémas réponse job / pipeline (miroir warehouse)
- CREATE `packages/dcm-backend/tests/.../test_compute_metrics_jobs.py`
- CREATE `packages/dcm-backend/tests/.../test_compute_metrics_pipelines.py`
- UPDATE `packages/dcm-backend/tests/.../test_compute_metrics_clusters.py` — non-régression : liste ne renvoie que ALL_PURPOSE

## Sub-tasks

- [ ] **Tests d'abord** (SQL généré ou app in-process selon le patron backend existant) :
  - liste clusters → prédicat `cluster_type = 'ALL_PURPOSE'` toujours présent (SC-001) ;
  - endpoint job → grain `job_id`, `job_name` (fallback `job_id`), fenêtre 1/7/30/90 ;
  - endpoint pipeline → grain `dlt_pipeline_id`, `pipeline_name` (fallback `dlt_pipeline_id`) ;
  - `window_days` hors {1,7,30,90} → 422 (IntEnum) ;
  - `cost_usd_prev_window` ≤ 0 → `null`.
- [ ] `compute_metrics_clusters.py` : ajouter le prédicat dur, retirer la dépendance au filtre optionnel pour l'exclusion.
- [ ] `compute_metrics_jobs.py` : service lisant `gold_dbx_compute_job_cluster_cost_rolling`, pagination serveur, fenêtre glissante (patron `compute_metrics_warehouses`).
- [ ] `compute_metrics_pipelines.py` : idem sur `gold_dbx_compute_pipeline_cost_rolling`.
- [ ] `compute_metrics_common.py` : mutualiser les helpers fenêtre entre cluster / job / pipeline.
- [ ] `compute_metrics.py` : brancher les 4 routes neuves + `object_type=PIPELINE` sur le forecast.
- [ ] `dcm-commons` : schémas Pydantic partagés (job overview/cost, pipeline overview/cost).
- [ ] Gates : `ruff`, `mypy`, `pytest` (backend + commons).
- [ ] Déploiement / vérification dev : contrôles §4 de [quickstart.md](../quickstart.md) (curl SC-001, grain job, grain pipeline, forecast PIPELINE).

## Notes

- **Réutiliser** le patron `compute_metrics_warehouses` (pagination `page`/`page_size`,
  `window_days` → `from_date`/`to_date`, `cost_usd_prev_window` ≤ 0 → `null`). Ne pas
  réinventer les helpers fenêtre — les descendre dans `_common`.
- Le backend ne lit que du **gold** — ne pas franchir la frontière médaillon vers le curated.
- Pas d'endpoint gouvernance job/pipeline (hors scope : gouvernance éphémère abandonnée, C2).
