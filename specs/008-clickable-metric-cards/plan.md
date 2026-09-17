# Implementation Plan: Cartes KPI cliquables (Phase 1)

**Branch**: `008-clickable-metric-cards` | **Date**: 2026-06-04 | **Spec**: `specs/008-clickable-metric-cards/spec.md`

## Summary

Introduire un pattern frontend partagé : **carte KPI cliquable → scroll + focus section → liste interactive**. Page pilote `/databricks` ; extensions `/alerts` et `/clusters` si le pattern est stable. Aucun changement backend Phase 1.

La cloche (Settings-only, 3 mois, lu/non lu) est **documentée en Phase 2** — ne pas modifier `useHeaderNotifications` dans Phase 1.

## Technical Context

- **Frontend**: React 18, TypeScript, Vite, Tailwind, `MetricCard` existant avec `onClick` / `active`.
- **Routing**: inchangé Phase 1 (tout in-page).
- **API**: réutilise les appels déjà faits au `load()` de chaque page.
- **Testing**: tests hook + accordion ; vérif manuelle `/databricks`.

## Constitution Check

- **Simplicity**: hook léger + composants domain, pas de nouveau state global.
- **Modularity**: extraire accordéon jobs réutilisable pour Data Factory / Pipelines plus tard.
- **No backend change**: Phase 1 strictement frontend.

## Project Structure

```text
specs/008-clickable-metric-cards/
├── spec.md
├── plan.md
└── tasks.md

packages/dcm-frontend/src/
├── hooks/useMetricSectionFocus.ts
├── components/domain/
│   ├── metric-section-anchor.tsx
│   └── workload-accordion.tsx
└── pages/Databricks.tsx
```

## Proposed Design

### 1. Hook `useMetricSectionFocus`

```typescript
type DatabricksSection =
  | 'clusters'
  | 'jobs'
  | 'security-alerts'
  | 'governance'
  | 'costs'
  | 'workspaces'
  | null;

// Returns: activeSection, setActiveSection, registerSectionRef(id), scrollToSection(id), clearFocus
```

- Toggle : re-clic même section → `activeSection = null`.
- `scrollToSection` : `ref.current?.scrollIntoView({ behavior, block: 'start' })`.
- Respect `prefers-reduced-motion: reduce` → `behavior: 'auto'`.

### 2. `MetricSectionAnchor`

Wrapper autour des `<Card>` sections existantes :

- `id="databricks-jobs"` (stable pour tests e2e).
- Classes conditionnelles : `ring-2 ring-primary/40` quand `activeSection` match.
- `tabIndex={-1}` pour focus programmatique après scroll (a11y).

### 3. `WorkloadAccordion`

Remplace la `<Table>` jobs sur Databricks Phase 1 (ou coexiste derrière flag — préférer remplacement direct si UX validée).

Champs expand (depuis `DatabricksWorkloadRow` existant) :

- name, id, type, source, status (header row)
- start, end, duration, sourceLzId, subscriptionOrAccountId, parentName
- rowsRead/Written, dataRead/Written bytes, errorMessage

Pattern UI : `<button>` header + `<div>` panel ; un seul open à la fois.

### 4. Wiring cartes Databricks

| Carte | Handler |
|-------|---------|
| Clusters, Avg CPU, Avg Memory, Cluster hourly | `scrollToSection('clusters')` |
| Running / Errors | filtre état existant + `scrollToSection('clusters')` |
| Job runs | `scrollToSection('jobs')` |
| Security alerts | `scrollToSection('security-alerts')` |
| Governance | `scrollToSection('governance')` |
| Databricks cost | `scrollToSection('costs')` |
| Workspaces, Landing zones | `scrollToSection('workspaces')` |

Descriptions cartes : ajouter hint « Click to view » où absent (Running/Errors l’ont déjà).

### 5. Extensions P2 (Alerts / Clusters)

- Extraire types section génériques ou dupliquer hook minimal par page.
- `/alerts` : cartes filtrent déjà — ajouter scroll vers `#alerts-list` + ring focus.
- `/clusters` : aligner sur Databricks clusters block.

### 6. Phase 2 preview (cloche — ne pas coder en Phase 1)

Fichier cible : `useHeaderNotifications.ts`

```typescript
// Pseudo — Phase 2
const end_date = today();
const start_date = subDays(today(), 90);
// NO getScopedParams, NO getApiParams from header
listSecurityAlerts({ start_date, end_date, status: 'active', limit: 50 })
  .filter(passesLandingZoneFilter(preferences, ...))
  .filter(passesNotificationFilter(preferences, ...))
  .map(alert => ({ ...item, read: isAlertRead(userId, alert) }))
unreadCount = items.filter(i => !i.read).length
```

`localStorage` key : `dcm:notif-read:{userSub}:{alert_id}:{source_lz_id}`.

---

## Risks & Mitigations

| Risque | Mitigation |
|--------|------------|
| Page Databricks déjà longue | scroll smooth + focus ring suffisent ; pas de duplicate data |
| Double comportement Running (filtre + scroll) | documenter ; carte reste `active` tant que filtre + section match |
| Pas de composant Accordion shadcn | composant domain minimal ~80 lignes |
| Régression panneau cluster | ne pas toucher logique `selectedClusterId` |

## Verification

1. `npm run lint` + `npm run test` dans `packages/dcm-frontend`.
2. Manuel : chaque carte Databricks → bonne section visible sans scroll excessif manuel.
3. Accordéon jobs : expand/collapse clavier OK.
4. Vérifier que cloche **non modifiée** Phase 1 (régression scope header).
