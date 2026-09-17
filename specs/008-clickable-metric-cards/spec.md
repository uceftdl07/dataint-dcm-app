# Feature Specification: Cartes KPI cliquables & drill-down in-page

**Feature Branch**: `008-clickable-metric-cards`  
**Created**: 2026-06-04  
**Status**: Draft  
**Input**: Retours UX `/databricks`, `/security`, `/alerts` — cartes KPI statiques peu actionnables ; pattern liste + détail déjà partiel sur Databricks (clusters).

---

## Clarification produit — Cloche (Phase 2, hors Phase 1)

> **Correction par rapport aux échanges précédents** : la cloche n’est **pas** pilotée par le scope header (`Env` / landing zone / cloud) ni par la période du header (`From` / `To` / `30d`).

| Règle | Comportement attendu |
|-------|----------------------|
| **Source de vérité** | Uniquement **Settings → Notifications** (`notification_lz_ids`, domaines, sévérité min.) + **RBAC** backend |
| **Période cloche** | Fenêtre fixe **3 mois** glissants (`start_date = today - 90j`, `end_date = today`) — indépendante du time range header |
| **Multi landing zone** | Union de toutes les LZ cochées dans Settings ; liste vide = toutes les LZ autorisées |
| **Header scope / filtres page** | **N’influencent pas** la cloche |
| **Lu / non lu** (si implémentation simple) | Alerte déjà consultée → reste dans la liste **sans** badge « non lu » ; le compteur badge = non lus uniquement |
| **Stockage lu/non lu** | `localStorage` par utilisateur (`alert_id` + `source_lz_id`) — pas de migration backend Phase 2 |
| **Deep link notif** | Phase 3 : `/alerts/:alertId?source_lz_id=...` (pas `/security` générique) |

Phase 1 **n’implémente pas** la cloche. Ces règles sont figées ici pour éviter toute régression lors de Phase 2.

---

## Compréhension du besoin

### Objectif Phase 1

Rendre les **cartes KPI (`MetricCard`) cliquables** sur les pages monitoring principales, avec un **drill-down in-page** : clic carte → focus sur la section liste correspondante (scroll + surbrillance), puis interaction ligne (panneau latéral ou accordéon selon le type de ressource).

L’utilisateur voit un chiffre (« 4 job runs », « 1 cluster ») et peut **agir** en un clic — sans nouvelle route backend Phase 1.

### Périmère Phase 1

**Inclus :**

- Pattern partagé `MetricCard` → section focus (hook + refs scroll).
- **Page pilote** : `/databricks` (12 cartes + sections existantes).
- **Extensions même pattern** (si effort restant) : `/alerts`, `/clusters`.
- Jobs Databricks : liste en **accordéon** (expand = détail run).
- Clusters : conserver panneau latéral existant ; carte « Clusters » scroll + focus table.
- Cartes filtre (Running, Errors) : comportement actuel conservé (toggle filtre) + scroll vers table clusters.
- Accessibilité : `role="button"`, `Enter` / `Espace`, `aria-pressed` sur cartes actives.

**Hors périmètre Phase 1 :**

- Refonte cloche / `useHeaderNotifications` (Phase 2).
- Route `/alerts/:id` et endpoint `GET /security/alerts/{id}` (Phase 3).
- Fix troncature `SecurityAlertsTable` (Phase 3 ou ticket séparé).
- Nouvelles routes dédiées par type (`/databricks/jobs`, etc.).
- Dashboard Home `/dashboard` (Phase 1b optionnelle — voir tasks).

### Données

Aucun changement Unity Catalog ni API. Toutes les listes utilisent les appels déjà présents sur chaque page (`listComputes`, `listPipelines`, `listActivities`, `listSecurityAlerts`, etc.) — voir `docs/03-implementation/ui-unity-catalog-interfaces-spec.md`.

---

## User Scenarios & Testing

### User Story 1 — Carte → section focus (Priority: P1)

En tant qu’utilisateur sur `/databricks`, je clique sur la carte **Job runs** pour voir immédiatement la liste des jobs sans chercher la section en bas de page.

**Independent Test** : clic « Job runs » → scroll smooth vers section jobs + carte en état `active` + section avec bordure/focus visuel.

**Acceptance Scenarios** :

1. **Given** la page Databricks est chargée, **When** je clique « Job runs », **Then** la vue scroll vers la section workloads et la carte affiche l’état actif.
2. **Given** une section est focus, **When** je re-clique la même carte, **Then** le focus se ferme (toggle) ou le filtre associé se reset selon le type de carte.
3. **Given** une carte sans liste (ex. Workspaces), **When** je clique, **Then** scroll vers le bloc « Workspace overview » existant.
4. **Given** clavier focus sur une carte, **When** j’appuie Entrée, **Then** même comportement que clic souris.

---

### User Story 2 — Détail job en accordéon (Priority: P1)

En tant qu’utilisateur, je clique un job dans la liste pour voir durée, erreur, volumes et landing zone sans quitter la page.

**Independent Test** : section jobs en accordéon — une seule ligne ouverte à la fois (optionnel), champs tronqués en fermé.

**Acceptance Scenarios** :

1. **Given** la section jobs est visible, **When** je clique une ligne, **Then** le panneau expand affiche start/end, duration, status, LZ, parent pipeline, rows/bytes, error message.
2. **Given** une ligne est ouverte, **When** je clique une autre ligne, **Then** la précédente se ferme (comportement accordion single-open).
3. **Given** un job sans erreur, **When** expand, **Then** le champ error affiche « — ».

---

### User Story 3 — Clusters inchangés mais reliés aux cartes (Priority: P1)

En tant qu’utilisateur, je clique « Clusters » ou « Running » pour atteindre la table clusters avec le panneau détail latéral déjà en place.

**Acceptance Scenarios** :

1. **Given** cartes Clusters / Running / Errors, **When** clic, **Then** scroll vers table clusters ; Running/Errors appliquent aussi le filtre état existant.
2. **Given** une ligne cluster sélectionnée, **When** panneau droit, **Then** comportement identique à l’existant (pas de régression).

---

### User Story 4 — Alertes & gouvernance depuis cartes (Priority: P2)

En tant qu’utilisateur, je clique « Security alerts » ou « Governance score » pour voir les listes compactes en bas de page.

**Acceptance Scenarios** :

1. **Given** cartes Security alerts / Governance, **When** clic, **Then** scroll vers les cards list en bas de page Databricks.
2. **Given** une alerte dans la liste, **When** clic (Phase 1), **Then** expand inline ou highlight — deep link `/alerts/:id` reporté Phase 3.

---

### User Story 5 — Extension Alerts / Clusters (Priority: P2)

En tant qu’utilisateur sur `/alerts` ou `/clusters`, les cartes KPI du haut filtrent ou scrollent vers la table comme sur Databricks.

**Acceptance Scenarios** :

1. **Given** `/alerts`, **When** clic Critical / Active, **Then** filtre table + état actif carte (déjà partiel — harmoniser avec pattern focus).
2. **Given** `/clusters`, **When** clic Running / Errors, **Then** scroll table + filtre (aligné sur comportement Databricks).

---

## Mapping cartes → sections (`/databricks`)

| Carte | Action Phase 1 | Section cible (`id`) | Interaction liste |
|-------|----------------|----------------------|-------------------|
| Workspaces | Scroll focus | `#databricks-workspaces` | Liste workspace overview |
| Landing zones | Scroll focus | `#databricks-workspaces` | Idem (LZ dérivées clusters) |
| Clusters | Scroll focus | `#databricks-clusters` | Table + panneau latéral |
| Running | Filtre + scroll | `#databricks-clusters` | Filtre `state=running` |
| Errors | Filtre + scroll | `#databricks-clusters` | Filtre `state=error` |
| Job runs | Scroll focus | `#databricks-jobs` | **Accordéon** |
| Security alerts | Scroll focus | `#databricks-security-alerts` | Liste compacte (expand optionnel P2) |
| Governance score | Scroll focus | `#databricks-governance` | Liste checks |
| Average CPU / Memory | Scroll focus | `#databricks-clusters` | Table clusters |
| Databricks cost | Scroll focus | `#databricks-costs` | Table coûts |
| Cluster hourly | Scroll focus | `#databricks-clusters` | Table clusters |

---

## Composants proposés

```text
packages/dcm-frontend/src/
├── hooks/
│   └── useMetricSectionFocus.ts      # activeSection, scrollToSection, toggle
├── components/domain/
│   ├── metric-section-anchor.tsx     # wrapper section + id + ring focus
│   ├── workload-accordion.tsx        # jobs Databricks expand/collapse
│   └── metric-card.tsx               # (existant) onClick + active déjà supportés
└── pages/
    └── Databricks.tsx                # pilote Phase 1
```

---

## Non-functional

- Pas de requête API supplémentaire au clic carte (données déjà en state page).
- Scroll `behavior: 'smooth'` avec fallback si `prefers-reduced-motion`.
- Tests unitaires : hook focus + accordion ; test manuel navigateur `/databricks`.

---

## Phases roadmap feature

| Phase | Contenu | Backend |
|-------|---------|---------|
| **1** (cette spec) | Cartes cliquables + drill-down in-page | Aucun |
| **2** | Cloche Settings-only, 3 mois, lu/non lu localStorage | Aucun |
| **3** | `/alerts/:id`, `SecurityAlertDetail`, troncature tables, endpoint détail | `GET /security/alerts/{id}` |

---

## Références

- `packages/dcm-frontend/src/pages/Databricks.tsx` — implémentation partielle (Running/Errors onClick)
- `packages/dcm-frontend/src/components/domain/metric-card.tsx`
- `packages/dcm-frontend/src/hooks/useHeaderNotifications.ts` — à modifier Phase 2 uniquement
- `docs/03-implementation/ui-unity-catalog-interfaces-spec.md`
- `docs/03-frontend/notification.md`
