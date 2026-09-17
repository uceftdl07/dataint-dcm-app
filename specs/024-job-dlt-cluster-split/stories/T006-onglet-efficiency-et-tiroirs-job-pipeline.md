# T006 — Sous-onglet Efficiency + lignes cliquables (Jobs & Pipelines DLT)

**Domain**: frontend
**Package**: packages/dcm-frontend
**Branch**: `frontend/024-sous-onglet-efficiency-lignes-cliquables`
**Jira**: à créer (`/speckit.dcm.dispatch`) — Epic [DCINT-325](https://tdf.atlassian.net/browse/DCINT-325)
**Depends on**: T005 (6 endpoints déployés)
**Work type**: feature

## Description

Amendement du 2026-09-09 — la demande d'origine, vue de l'IHM. Les pages livrées par T003
n'ont que 2 sous-onglets (Overview / Cost) et des lignes inertes. Deux effets :

1. **3ᵉ sous-onglet Efficiency** sur `ComputeJobs` et `ComputePipelines`, au grain stable.
2. **Lignes cliquables** sur les **3** sous-onglets → tiroir latéral de détail, « au même
   niveau de détail que l'All-purpose dans la mesure du possible » : identité, coût/DBU de la
   fenêtre + Δ, efficacité de la fenêtre, tendance coût ≈90 j, tendance uptime ≈90 j.
   **Sans bloc gouvernance** — il n'existe pas à ce grain (C2).

## Files to create/modify

- UPDATE `src/components/domain/compute/compute-cost-tabs.tsx` — `ComputeCostGrainTabKey`
  passe de `'overview' | 'cost'` à `'overview' | 'cost' | 'efficiency'`, +1 entrée `TABS`, et
  **docstring corrigé** : il affirme aujourd'hui que ces grains n'ont pas de signal
  d'utilisation en gold — faux dès que T004 est livrée
- CREATE `src/components/domain/compute/compute-job-drawer.tsx` — calqué sur
  `compute-cluster-drawer.tsx`, **sans** bloc gouvernance
- CREATE `src/components/domain/compute/compute-pipeline-drawer.tsx` — idem, grain
  `dlt_pipeline_id`
- UPDATE `src/pages/ComputeJobs.tsx` — bloc `tab === 'efficiency'` (colonnes + KPI cards),
  `onRowClick` sur les 3 `ComputeDataTable`, état du tiroir + `drawerPeriod` (90 j)
- UPDATE `src/pages/ComputePipelines.tsx` — idem
- UPDATE `src/api/dcmApiClient.ts` — 6 appels (efficiency / detail / cost-trend / uptime-trend
  × 2 familles), centralisés (pas de `fetch` inline)
- UPDATE `src/hooks/useComputeJobsQueries.ts` — `useComputeJobsEfficiencyData`,
  `useComputeJobDetail`, `useComputeJobCostTrend`, `useComputeJobUptimeTrend`
- UPDATE `src/hooks/useComputePipelinesQueries.ts` — les 4 homologues
- UPDATE `src/hooks/query-keys.ts` — clés des nouvelles requêtes (fenêtre dans la clé de cache)
- UPDATE `src/types/api.ts` — types efficiency / detail / trend des 2 familles
- UPDATE `src/test/fixtures/compute-jobs.ts`, `compute-pipelines.ts` — fixtures des 4 formes
- UPDATE `src/pages/ComputeJobs.test.tsx`, `ComputePipelines.test.tsx`

## Sub-tasks

- [x] **Tests d'abord** (Vitest + fixtures MSW), sur chaque page :
      - les sous-onglets sont **Overview / Cost / Efficiency** ;
      - l'onglet Efficiency liste au grain stable et **n'affiche aucune colonne « Zombie »** ;
      - un clic sur une ligne de **chacun des 3** onglets ouvre le tiroir renseigné ;
      - un grain **sans** ligne d'efficacité affiche « — » sur ce bloc et le tiroir reste
        utilisable (jamais d'écran cassé, jamais `0 %`) ;
      - le tiroir **n'a pas** de bloc gouvernance ;
      - fermeture au clavier (Échap) héritée du patron de tiroir.
- [x] `compute-cost-tabs.tsx` : élargir l'union + corriger le docstring. Vérifier qu'aucun
      `switch` exhaustif sur `ComputeCostGrainTabKey` ne casse ailleurs (`tsc` le dira).
- [x] Hooks + client + `query-keys.ts` + types.
- [x] Colonnes Efficiency : workspace, job/pipeline, CPU avg/p95, Mem avg/p95, idle (+ fenêtre
      précédente), uptime cumulé (+ fenêtre précédente), workers avg/max, autoscaling, node
      types, `utilization_status`, `recommended_node_type`, `estimated_savings_usd`,
      `cluster_count`. Largeurs via `COLUMN_WIDTH`, `minWidthClassName` calibré comme sur
      `ComputeClusters`.
- [x] KPI cards de l'onglet Efficiency : Avg CPU p95, Avg Mem p95, Est. savings — **pas** de
      carte « Zombies » (métrique non produite à ce grain).
- [x] Les 2 tiroirs : identité (Cloud, Workspace, id, nom), MiniKpi (CPU p95, Mem p95, Idle,
      Status), bloc nœuds, `TrendSection` « Cost trend (≈90 days) » et « Uptime trend
      (≈90 days) » avec sélecteurs de granularité.
- [x] `onRowClick` sur les 3 tables des 2 pages.
- [x] Gates : `tsc --noEmit`, `npm run lint`, `vitest run`, `npm run build` (delta 0 vs baseline).
- [ ] Vérification navigateur : les 3 onglets peuplés, clic → tiroir renseigné sur les 2 pages
      (**SC-006**), et un cas réel d'efficacité absente observé côté DLT.
      → **à faire par un humain** : aucun outil de pilotage de navigateur ici (pas de
      Playwright dans le repo). Le contrat servi a été vérifié sur la donnée dev réelle,
      voir « Vérification » ci-dessous.

## Notes

- **Un tiroir par grain** (R9), pas un tiroir générique paramétré : le patron existe déjà pour
  cluster et warehouse, et ses sections (`Fields`, `MiniKpi`, `TrendSection`) sont factorisées.
  Généraliser imposerait de réécrire 4 tiroirs livrés pour un gain nul ici.
- **`WindowChipGroup` est dupliqué** dans `ComputeJobs.tsx` et `ComputePipelines.tsx`
  (héritage T003). Si le composant est touché ici, le factoriser ; sinon ne pas élargir le
  périmètre — un refactor non demandé grossit la PR.
- **Jamais `0` pour « non mesuré »** : `idle_pct`/`p95` absents s'affichent « — ». Un `0 %` se
  lirait « cluster à 100 % occupé », l'inverse du fait.
- Pas d'onglet gouvernance ni de bloc gouvernance (C2), comme sur T003.
- Le lien KPI vers `/databricks/compute/recommendations?object_type=JOB|PIPELINE` reste tel
  quel : cette task n'ajoute pas de recommandation au grain éphémère.

## Écarts constatés

- **Sections de tiroir extraites** dans `compute-drawer-sections.tsx` (`DrawerField`,
  `DrawerMiniKpi`, `DrawerTrendSection`) et `compute-cluster-drawer.tsx` basculé dessus —
  déplacement pur, aucun changement de rendu. Sans cela les deux nouveaux tiroirs
  recopiaient trois composants au lieu de les partager. Le tiroir **warehouse** n'a pas été
  basculé : ses sections sont une vraie variante visuelle, pas un doublon.
- **Granularité par défaut des tendances alignée sur `'week'`** dans les deux nouveaux
  tiroirs, comme `ComputeClusters.tsx` : les trois tiroirs se comportent donc pareil.
- **`navigation-access.test.ts` remis au vert** : T001/T002 ont ajouté les deux feuilles
  `/databricks/job-compute` et `/databricks/pipeline-compute` au `MAIN_MENU` sans mettre à
  jour l'attendu de ce test, qui échouait donc depuis. Correction de l'attendu (2 lignes),
  hors périmètre nominal de T006 mais régression de la spec 024.
- **`PrevWindowCell` reste local à chaque page** (comme sur `ComputeClusters.tsx`) plutôt
  que factorisé : la note ci-dessus interdit d'élargir le périmètre à un composant non
  touché.

## Vérification

Portes (depuis `packages/dcm-frontend`) :

| Porte | Résultat |
|-------|----------|
| `npx tsc --noEmit` | **101** erreurs = baseline, **0** dans un fichier de T006 |
| `npx eslint` sur les 16 fichiers de T006 | **0** problème (`--max-warnings 0`) |
| `npx vitest run` | **387 passés / 4 échecs**, les 4 identiques à `origin/develop` (`App.test`, `Dashboard.test` ×2, `Databricks.test`) — vérifié en worktree détaché sur `origin/develop` |
| `npm run build` | OK (4,3 s) |
| `ComputeJobs.test.tsx` | 18/18 |
| `ComputePipelines.test.tsx` | 18/18 |

Contrat servi, sur la **donnée dev réelle** (TestClient sur l'app, entrepôt dev, six GET
en lecture seule, scope projet ouvert car l'identité dev-header a un scope vide) :

- `jobs/efficiency` : 4 846 lignes, les 33 clés lues par la page présentes ;
- `pipelines/efficiency` : 174 lignes, idem au grain `dlt_pipeline_id` ;
- `jobs/cost` : 6 759 lignes, `pipelines/cost` : 6 062 — **population facturée > population
  mesurée**, ce que l'onglet Efficiency assume (état vide explicite) ;
- détail job `904377630216362` : `efficiency` renseignée, coût 3 699,03 $ ;
- **cas réel d'efficacité absente** : pipeline `05e63a07-be8b-4500-8c5b-8cc60d25f594`,
  facturé **941,47 $** sur 30 j, `efficiency: null`, et `uptime-trend` à **0 bucket** — le
  tiroir couvre les deux (message « No utilization measured over this window » + tendance
  vide), jamais `0 %` ;
- `cost-trend` / `uptime-trend` : 5 buckets hebdo, clés conformes.

Reste à faire par un humain : cliquer `/databricks/job-compute` et
`/databricks/pipeline-compute` sur http://localhost:4000 (back dev sur `:8000`), les 3
onglets et un tiroir depuis chacun.
