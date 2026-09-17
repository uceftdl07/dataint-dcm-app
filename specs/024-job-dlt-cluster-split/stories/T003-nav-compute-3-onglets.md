# T003 — Nav Compute 3 onglets (All-purpose / Jobs / Pipelines DLT)

**Domain**: frontend
**Package**: packages/dcm-frontend
**Branch**: `frontend/024-nav-compute-3-onglets-all-purpose-jobs`
**Jira**: [DCINT-327](https://tdf.atlassian.net/browse/DCINT-327) (Epic [DCINT-325](https://tdf.atlassian.net/browse/DCINT-325))
**Depends on**: T002 (endpoints compute job & pipeline déployés)
**Work type**: feature

## Description

Séparer la navigation Compute en **3 destinations** : All-purpose clusters (page existante,
désormais purgée des éphémères), **Jobs compute** (grain `job_id`) et **Pipelines DLT compute**
(grain `dlt_pipeline_id`). Les deux dernières sont **à créer de bout en bout** — aucune page
front ni onglet n'existe aujourd'hui (grep confirmé). Chaque page branchée sur son endpoint
avec forecast/reco par famille (coût + DBU pour Pipelines, C4).

## Files to create/modify

- CREATE `packages/dcm-frontend/src/pages/.../ComputeJobs.tsx` — route `/databricks/job-compute`
- CREATE `packages/dcm-frontend/src/pages/.../ComputePipelines.tsx` — route `/databricks/pipeline-compute`
- CREATE `packages/dcm-frontend/src/hooks/useComputeJobsQueries.ts`
- CREATE `packages/dcm-frontend/src/hooks/useComputePipelinesQueries.ts`
- UPDATE `packages/dcm-frontend/src/api/dcmApiClient.ts` — appels job / pipeline
- UPDATE `packages/dcm-frontend/src/hooks/query-keys.ts` — clés job / pipeline
- UPDATE `packages/dcm-frontend/src/types/api.ts` — types réponse (miroir warehouse)
- UPDATE `packages/dcm-frontend/src/config/navigation.ts` — groupe Compute → 3 entrées
- UPDATE `packages/dcm-frontend/src/config/role-permissions.ts` — `page:databricks` sur les 2 routes neuves
- UPDATE `packages/dcm-frontend/src/lib/databricks/routes.ts` — `PREDEFINED_WINDOW_ROUTES` + les 2 routes
- UPDATE `packages/dcm-frontend/src/app/app-routes.ts` — 2 routes → composants
- CREATE fixtures `packages/dcm-frontend/src/.../fixtures/compute-jobs.ts`, `compute-pipelines.ts`
- CREATE `ComputeJobs.test.tsx`, `ComputePipelines.test.tsx`
- UPDATE `focus-routes.ts` si les nouvelles routes doivent y figurer

## Sub-tasks

- [ ] **Tests d'abord** (Vitest, mocks) : la page Clusters n'affiche que du All-purpose ;
      Jobs liste au grain `job_id` (`job_name` affiché, pas l'id) ; Pipelines liste au grain
      `dlt_pipeline_id` (`pipeline_name`, fallback id) ; fenêtre glissante 1/7/30/90 ;
      forecast/reco par famille.
- [ ] `useComputeJobsQueries.ts` / `useComputePipelinesQueries.ts` : TanStack Query hooks,
      clés dans `query-keys.ts`, fenêtre dans la clé de cache.
- [ ] `dcmApiClient.ts` : appels centralisés (pas de fetch inline).
- [ ] `ComputeJobs.tsx` / `ComputePipelines.tsx` : tableaux + forecast + reco, libellés lisibles.
- [ ] `navigation.ts` : 3 entrées dans le groupe Compute (Clusters / Jobs / Pipelines DLT).
- [ ] `role-permissions.ts`, `routes.ts`, `app-routes.ts`, `focus-routes.ts` : câblage des routes.
- [ ] Fixtures + tests des 2 nouvelles pages.
- [ ] Gates : `tsc --noEmit`, `npm run lint`, `vitest run`, `npm run build` (delta 0 vs baseline).
- [ ] Vérification navigateur : page Clusters sans éphémère (SC-001 vu de l'IHM), onglets
      Jobs et Pipelines peuplés à leur grain.

## Notes

- **2 pages routées neuves**, pas des onglets internes à une page unique (C1 : « 3 onglets
  complets » = 3 destinations de nav). Réutiliser le patron `ComputeSqlWarehouses` (fenêtre
  glissante, chips, `Δ vs prev window`).
- Afficher le **nom** (`job_name` / `pipeline_name`), pas l'id, avec fallback sur l'id quand
  le nom est absent.
- Pas d'onglet gouvernance sur Jobs / Pipelines (hors scope, C2).
