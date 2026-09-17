# T003 — Page Cluster par plage et tendances

**Domain**: frontend
**Package**: packages/dcm-frontend
**Branch**: `frontend/022-page-cluster-par-plage-et-tendances`
**Jira**: not dispatched (dispatch non exécuté sur cette feature)
**Depends on**: T002
**Work type**: feature

## Description

Sur la page Cluster, remplacer le sélecteur de période libre du header par quatre plages
statiques (`Daily`, `Last 7d`, `Last 30d`, `Last 90d`) qui pilotent `window_days`, et
afficher la période réellement couverte (`from_date → to_date`) telle que l'API la
renvoie. Étendre les colonnes des onglets Overview, Cost et Efficiency aux indicateurs
demandés, Governance restant inchangée. Enfin refondre le détail d'un cluster : conserver
son format actuel, ajouter le bloc de caractéristiques techniques, et remplacer les
visuels de tendance par un histogramme `COST TREND (≈90 DAYS)` et une courbe
`Lifetime TREND (≈90 DAYS)`, chacun suivable point par point en jour, semaine ou mois.

## Files to create/modify

- UPDATE `packages/dcm-frontend/src/pages/ComputeClusters.tsx`
- UPDATE `packages/dcm-frontend/src/pages/ComputeClusters.test.tsx`
- UPDATE `packages/dcm-frontend/src/hooks/useComputeClustersQueries.ts`
- UPDATE `packages/dcm-frontend/src/types/api.ts`
- UPDATE `packages/dcm-frontend/src/components/domain/compute/compute-cluster-drawer.tsx`
- ~~UPDATE `packages/dcm-frontend/src/components/domain/compute/compute-cost-trend-chart.tsx`~~
  → **laissé intact**, voir Notes : ce composant est partagé avec
  `compute-warehouse-drawer.tsx`, hors périmètre.
- CREATE `packages/dcm-frontend/src/components/domain/compute/compute-trend-chart.tsx`
- CREATE `packages/dcm-frontend/src/components/domain/compute/compute-trend-chart.test.tsx`
- UPDATE `packages/dcm-frontend/src/test/fixtures/compute-clusters.ts`
- UPDATE `packages/dcm-frontend/src/api/dcmApiClient.ts` (endpoint `lifetime-trend`,
  `window_days`)
- UPDATE `packages/dcm-frontend/src/hooks/query-keys.ts` (`window_days` dans les clés)
- UPDATE `packages/dcm-frontend/src/lib/compute/format.ts` (`formatDeltaPts`,
  `formatWorkerBounds`, `autoscalingLabel`)
- UPDATE `packages/dcm-frontend/src/lib/compute/field-descriptions.ts` (nouvelles colonnes)

## Sub-tasks

- [x] Tests d'abord (vitest + fixtures MSW) : les 4 plages, la persistance de la plage au
      changement d'onglet, l'affichage `from_date → to_date`, une valeur `null` de fenêtre
      précédente rendue « — » et non `0` ni `NaN`, l'état vide du détail.
- [x] Types : bloc `window`, champs ajoutés des 3 onglets, réponse `lifetime-trend`
      (cf. contrats).
- [x] Sélecteur de plage : 4 options statiques, aucune saisie de dates ; `window_days`
      dans la clé React Query pour que le changement de plage refetch.
- [x] Période couverte affichée depuis `window.from_date` / `window.to_date` de la réponse
      — jamais calculée depuis `today` (un run en retard afficherait une plage fausse).
- [x] Colonnes Overview : Workspace, Cluster, Type, $Cost, $Cost période précédente,
      Lifetime, Lifetime période précédente, Utilization (badge `utilization_status`),
      Governance (badge `severity`, `null` = conforme).
- [x] Colonnes Cost : Workspace, Cluster, Type, $Cost, $Cost période précédente, SKU,
      DBU_cost, DBU.
- [x] Colonnes Efficiency : + driver/worker node type, Autoscaling avec ses bornes
      (`autoscale_min_workers`–`autoscale_max_workers`, ou `configured_worker_count` pour
      un cluster à taille fixe), Lifetime et IDLE avec leur période précédente, CPU et
      mémoire (moyenne et p95), statut, node recommandé, économie estimée.
- [x] Onglet Governance : **aucune modification**.
- [x] Détail cluster : bloc caractéristiques techniques (driver, worker, autoscaling,
      min/max).
- [x] `compute-trend-chart.tsx` : graphe SVG générique (variante barres et variante
      courbe), commutateur jour / semaine / mois, valeur lisible au survol de chaque point.
      Aucune librairie de charting introduite — cohérence avec l'existant.
- [x] Brancher `COST TREND` sur `cost-trend` (histogramme) et `Lifetime TREND` sur
      `lifetime-trend` (courbe), ≈90 jours.
- [x] Gates : `npm run lint`, `tsc`, `vitest`, `npm run build`.

## Acceptance Criteria

- [x] Quatre plages statiques proposées, aucune saisie de dates libre sur la page Cluster.
- [x] La période couverte est affichée sous la forme `from_date → to_date` et provient de
      la réponse API.
- [x] La plage sélectionnée est conservée au changement d'onglet.
- [x] Les 3 onglets affichent exactement les indicateurs de FR-004, FR-005 et FR-006.
- [x] Governance est identique à avant (rendu et données) — l'endpoint ne reçoit toujours
      pas `window_days`, vérifié par test.
- [x] Le détail d'un cluster conserve son format, ajoute les caractéristiques techniques,
      et présente l'histogramme `COST TREND (≈90 DAYS)` et la courbe
      `Lifetime TREND (≈90 DAYS)`, chacun avec le commutateur jour / semaine / mois.
- [x] Une donnée manquante (fenêtre précédente absente, `dbu_cost` `null`,
      `workspace_name` `null`) s'affiche comme « non disponible » — jamais `0`, `NaN` ni
      une valeur inventée (P9).
- [x] Un cluster sans donnée sur la plage choisie rend l'état vide existant, pas un graphe
      vide.
- [x] Quand **aucune** ligne n'a de fenêtre précédente pour `Lifetime` (cas de la plage
      `Last_90`, cf. R7), une note explique que la comparaison est indisponible et précise
      que le coût n'est pas concerné. Une absence sur *certaines* lignes seulement ne
      déclenche rien.

## Tests

```bash
cd packages/dcm-frontend
npm run test -- src/pages/ComputeClusters.test.tsx
npm run test
npm run lint && npx tsc --noEmit && npm run build
```

## Out of scope

- Pages Warehouses.
- Page `Clusters.tsx` héritée.
- Introduction d'une librairie de charting.
- Onglet Governance.

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside `packages/dcm-frontend`
- [ ] Diff stays reviewable
- [ ] Sub-spec checkboxes reviewed
- [ ] T002 déployée : les champs consommés existent réellement dans la réponse

## Notes

- Champs disponibles par endpoint :
  [contracts/compute-clusters-rolling.md](../contracts/compute-clusters-rolling.md).
- `idle_pct_delta_pts` est un écart en **points de pourcentage** : afficher « +10 pts »,
  pas « +50 % » ([data-model.md](../data-model.md)).
- `worker_count_max` (maximum observé par minute) et `autoscale_max_workers` (borne
  configurée) sont deux notions distinctes — ne pas les confondre dans une même colonne.
- Décision d'abandonner la période libre sur cette page : [spec.md](../spec.md)
  Clarifications, et [plan.md](../plan.md) Complexity Tracking.

### Écarts assumés par rapport au plan de fichiers

- `compute-cost-trend-chart.tsx` **n'a pas été modifié** : il est aussi consommé par
  `compute-warehouse-drawer.tsx:192`, et les pages Warehouses sont explicitement hors
  périmètre. Le nouveau `compute-trend-chart.tsx` (barres + courbe, générique) est utilisé
  côté clusters uniquement ; l'ancien composant reste la version warehouse. Fusionner les
  deux serait une refonte de la page Warehouses, à traiter dans une autre spec.
- `compute-trend-chart.test.tsx` ajouté : les invariants du graphe (un `null` coupe la
  courbe et n'est pas un `0`, série entièrement à zéro sans division par zéro, chaque
  bucket survolable même vide) se testent au niveau du composant, pas au travers de la page.
- Les 4 échecs de `npm run test` (`App.test.tsx`, `Dashboard.test.tsx` ×2,
  `Databricks.test.tsx`) préexistent sur `fix/dcm_compute` : vérifié en rejouant ces trois
  fichiers avec les modifications frontend remisées — mêmes 4 échecs. Idem pour les
  39 erreurs `npm run lint` et les erreurs `tsc`, toutes hors fichiers touchés (aucune
  ligne de lint ni de `tsc` ne pointe un fichier de cette story).
- Comparaison à la fenêtre précédente : disponible pour 197/249 clusters `ALL_PURPOSE`,
  mais seulement 70/47 483 `JOB` et 0/1 058 `PIPELINE` — les `cluster_id` éphémères n'ont
  aucun prédécesseur. Les cellules « période précédente » afficheront donc « — » sur la
  quasi-totalité des lignes JOB et PIPELINE : c'est le comportement attendu, pas un bug de
  jointure.

### Confirmé et chiffré par la vérification dev de T002 ([research.md](../research.md) R8)

La cause est mesurée : **99,1 % des `cluster_id` n'apparaissent qu'un seul jour**. Le taux
de comparabilité global est donc dérisoire (0,03 % à `w=90`), mais le tri par défaut est
`cost_usd DESC` et les clusters persistants sont aussi les plus coûteux — **la page 1 est
comparable à 88–92 %**. L'écran que l'utilisateur regarde est donc renseigné ; le « — » se
concentre dans la longue traîne. Rien à changer côté rendu.

Deux points, dont un seul reste ouvert :

1. **Les lignes à coût nul — déjà correctement traitées, ne rien changer.** `cost_rolling`
   conserve délibérément les clusters retombés à zéro : 55 % des lignes à `w=90` ont
   `cost_usd = 0`. Vérifié que la page est juste malgré cela : la carte KPI lit
   `kpis.active_clusters` (le décompte honnête, 622 553 à `w=90`) et le `total` ne sert
   qu'à la pagination, où il doit bien compter toutes les lignes paginables. Noté ici parce
   que l'écart entre les deux nombres (1 378 333 contre 622 553) ressemble à une incohérence
   et pourrait être « corrigé » à tort.
2. **Tranché et implémenté — sur la plage `Last_90`, `Lifetime_previous_period` et
   `IDLE_previous_period` sont vides pour *toutes* les lignes** (0 sur 420 748), jusqu'à
   ~2027-01-01, le temps que `system.compute.node_timeline` accumule 180 jours (R7). Le
   rendu « — » est correct au sens de P9, mais une colonne uniformément vide se lit comme
   une panne.

   Arbitrage du demandeur : **garder les 2 colonnes et afficher une note explicative**,
   plutôt que les masquer sur `Last_90` — la table garde ainsi la même forme sur les
   4 plages.

   Implémentation : `lifetimeComparisonUnavailable` dans `ComputeClusters.tsx`, déduite des
   **lignes réellement reçues** (« aucune ligne ne porte de `uptime_hours_prev_window` »), et
   non d'un test `window_days === 90`. Trois conséquences voulues :

   - le jour où l'historique amont devient suffisant, des valeurs précédentes apparaissent et
     la note cesse de s'afficher d'elle-même — **aucun code à revisiter en janvier 2027** ;
   - la note ne se déclenche pas sur un filtre qui n'a légitimement rien retourné (`every`
     sur un tableau non vide) ;
   - elle ne s'affiche pas sur l'onglet Cost, dont l'historique est bien plus profond et la
     comparaison intacte — le texte le dit explicitement plutôt que de laisser croire que
     toute comparaison est cassée.

   La note porte `role="note"` et est couverte par un test à deux volets : silencieuse sur la
   fixture par défaut (qui mélange un cluster comparable et un cluster éphémère — un « — »
   sur *certaines* lignes est normal), affichée quand toutes les lignes sont vides.
