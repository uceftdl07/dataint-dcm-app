# T005 — Valeurs des indicateurs au survol des graphes

**Domain**: frontend
**Package**: packages/dcm-frontend
**Branch**: (aucune — correctif demandé sur la branche courante)
**Jira**: not dispatched (dispatch non exécuté sur cette feature)
**Depends on**: T003
**Work type**: bugfix

## Description

Le montant d'un point n'était pas lisible au survol des graphes. Trois situations
distinctes :

1. `compute-trend-chart.tsx` (T003) n'exposait ses valeurs que par un `<title>` SVG : le
   navigateur ne l'affiche qu'après son propre délai, trop lent pour parcourir une série
   de ≈90 points en balayant le graphe.
2. `compute-cost-trend-chart.tsx` (tendance de coût du tiroir warehouse) et le graphe du
   `forecast-widget.tsx` étaient `aria-hidden` et **sans aucun** retour au survol.
3. La sparkline « Runs actifs » de `LakeflowOverview.tsx` n'a pas d'axes : sans `Tooltip`
   recharts, la courbe ne dit ni combien de runs ni à quelle heure.

## Files to create/modify

- CREATE `packages/dcm-frontend/src/components/domain/compute/chart-hover-tooltip.tsx`
- UPDATE `packages/dcm-frontend/src/components/domain/compute/compute-trend-chart.tsx`
  (+ `costTrendPoints`, partagé par les deux tiroirs)
- UPDATE `packages/dcm-frontend/src/components/domain/compute/compute-trend-chart.test.tsx`
- UPDATE `packages/dcm-frontend/src/components/domain/compute/forecast-widget.tsx`
- CREATE `packages/dcm-frontend/src/components/domain/compute/forecast-widget.test.tsx`
- UPDATE `packages/dcm-frontend/src/components/domain/compute/compute-cluster-drawer.tsx`
- UPDATE `packages/dcm-frontend/src/components/domain/compute/compute-warehouse-drawer.tsx`
- DELETE `packages/dcm-frontend/src/components/domain/compute/compute-cost-trend-chart.tsx`
- UPDATE `packages/dcm-frontend/src/pages/LakeflowOverview.tsx`

## Sub-tasks

- [x] `ChartHoverTooltip` : encart flottant au-dessus du point survolé, ancré au bord
      quand le point est trop près d'un côté pour être centré sans déborder de la carte.
- [x] `ComputeTrendChart` : état de survol, repère vertical pointillé, point ou barre
      accentué, encart instantané à la place du `<title>`.
- [x] Série exposée en texte (`sr-only`) à côté de l'image : le SVG est un unique
      `role="img"`, donc le balisage interne n'est jamais annoncé. L'encart est
      `aria-hidden` — une région live déclenchée à chaque bande traversée n'annoncerait
      qu'un flux de bruit.
- [x] Tiroir warehouse basculé sur `ComputeTrendChart` (`costTrendPoints`), et
      `compute-cost-trend-chart.tsx` supprimé : plus aucun appelant.
- [x] `ForecastWidget` : bandes de survol par jour, encart `date · valeur (borne basse –
      borne haute)`, graphe extrait en composant `ForecastChart` pour que le survol ne
      re-rende pas le sélecteur de métrique.
- [x] Sparkline Lakeflow : `Tooltip` recharts, libellé formaté en `HH:mm` depuis le
      `t` du point — sans axe X, le libellé par défaut serait l'**index** du point.
- [x] Tests : survol d'une bande, survol d'une bande **sans mesure**, effacement à la
      sortie du curseur, liste texte, jointure des deux séries du forecast.
- [x] Gates : `tsc`, `vitest`, `vite build`.

## Acceptance Criteria

- [x] Survoler un point d'un histogramme ou d'une courbe compute affiche immédiatement ses
      montants formatés (coût + DBU, ou lifetime + idle).
- [x] Une plage sans mesure affiche son propre libellé (« no data »), pas un zéro.
- [x] Le forecast affiche la valeur prédite **et** son intervalle de confiance au survol.
- [x] La sparkline « Runs actifs » affiche le nombre de runs et l'heure du point.
- [x] Les 7 graphes de `MonitoringReports.tsx` avaient déjà un `Tooltip` — vérifié, rien à
      y changer.

## Tests

```bash
cd packages/dcm-frontend
npx vitest run src/components/domain/compute/
npx vitest run && npx tsc --noEmit && npx vite build
```

## Out of scope

- Introduction d'une librairie de charting (les graphes compute restent en SVG inline).
- Les barres de segments Lakeflow, qui portent déjà leurs valeurs en légende ou en libellé
  adjacent.

## Notes

- Correction de fond dans `forecast-widget.tsx` : les parties historique et projetée
  étaient tracées sur **deux échelles différentes** (pas horizontal calculé sur deux
  longueurs, et `min`/`max` verticaux calculés sur deux séries). La ligne pointillée
  redémarrait donc avant la fin de la ligne pleine et les deux hauteurs n'étaient pas
  comparables. `plotForecast` place les deux sur une seule échelle — nécessaire ici, un
  encart de survol devant pointer la valeur qu'il nomme. Couvert par test.
- `compute-cost-trend-chart.tsx` était déclaré « laissé intact, hors périmètre » par T003
  parce que partagé avec le tiroir warehouse. La demande de survol portant sur *tous* les
  graphes, il est cette fois remplacé — les deux tiroirs affichent désormais le même
  histogramme et le même encart.
