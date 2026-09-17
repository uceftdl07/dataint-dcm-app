# Feature Specification: Frontend Quality Hardening

**Feature Branch**: `002-frontend-quality-hardening`  
**Created**: 2026-05-25  
**Status**: Draft  
**Input**: Revue frontend externe + vérification locale de `packages/dcm-frontend`

---

## Compréhension du besoin

### Objectif

Améliorer la maintenabilité, la fiabilité et l'expérience développeur du frontend DCM sans lancer une restructuration massive inutile. Le projet possède déjà une base saine : React 18, TypeScript strict, Vite, Tailwind, MSAL, dossiers `components/`, `pages/`, `hooks/`, `contexts/`, `api/`, `lib/`, `types/`, `public/`.

Cette spec transforme la review frontend générique en plan actionnable, centré sur les écarts réels observés :

- Absence de tests frontend automatisés.
- Chargement API encore géré manuellement dans les pages (`useState`, `useEffect`, `Promise.all`).
- `App.tsx` très dense, routes protégées répétitives et pages importées eager.
- Logs client trop verbeux autour de l'auth/token.
- README frontend partiellement obsolète.
- Tooling incomplet côté formatage/pre-commit.

### Hors périmètre

- Réécrire toute l'arborescence frontend : la structure actuelle est déjà conforme aux conventions attendues.
- Migrer vers un autre design system : les composants `components/ui` et `components/domain` existants restent la base.
- Changer le contrat API backend.
- Modifier l'authentification MSAL fonctionnelle, sauf nettoyage des logs et validation des comportements.
- Introduire de l'i18n complet tant qu'aucun besoin produit immédiat n'est validé.

---

## User Scenarios & Testing

### User Story 1 — Socle de tests frontend fiable (Priority: P1)

En tant que développeur DCM, je veux disposer de tests frontend sur les composants et flows critiques afin de détecter les régressions avant merge.

**Why this priority**: c'est le plus gros écart qualité observé. Sans tests, les refactorings React Query/routing/doc risquent de casser des parcours visibles.

**Independent Test**: exécuter la commande de test frontend depuis `packages/dcm-frontend` et obtenir une suite verte couvrant au minimum le rendu layout, un composant domaine critique et un flow API mocké.

**Acceptance Scenarios**:

1. **Given** le frontend installé, **When** un développeur lance la commande de tests, **Then** les tests unitaires et d'intégration critiques passent sans accès réseau réel.
2. **Given** un composant de page reçoit une erreur API mockée, **When** le test rend la page, **Then** un état d'erreur visible et accessible est affiché.
3. **Given** un état de chargement API, **When** la page est rendue, **Then** le loader/skeleton attendu est visible et testable.

---

### User Story 2 — Server state API standardisé (Priority: P2)

En tant qu'utilisateur DCM, je veux des pages qui chargent, rafraîchissent et affichent les erreurs de façon cohérente afin d'avoir une expérience stable.

**Why this priority**: plusieurs pages gèrent directement leurs appels API avec du state local. TanStack Query apporte cache, refetch, retries contrôlés et états loading/error homogènes.

**Independent Test**: migrer une première page critique (`Dashboard`) vers des hooks de requêtes TanStack Query, avec tests mockés et comportement identique côté UI.

**Acceptance Scenarios**:

1. **Given** des réponses API valides, **When** l'utilisateur ouvre le dashboard, **Then** les mêmes métriques qu'avant sont affichées.
2. **Given** un filtre de période ou de scope change, **When** la requête est invalidée, **Then** les données sont rechargées avec les bons paramètres.
3. **Given** une erreur API, **When** la requête échoue, **Then** l'utilisateur voit une erreur actionnable et peut relancer le chargement.

---

### User Story 3 — Routing et performance initiale allégés (Priority: P3)

En tant qu'utilisateur, je veux que l'application charge plus vite et conserve les routes protégées sans duplication fragile.

**Why this priority**: `App.tsx` importe toutes les pages au démarrage et répète beaucoup de wrappers `ProtectedRoute` + `ProtectedLayout`.

**Independent Test**: remplacer la déclaration répétitive des routes par une configuration centralisée et introduire du lazy loading sur les pages protégées sans changer les URLs existantes.

**Acceptance Scenarios**:

1. **Given** une URL existante telle que `/dashboard`, `/pipelines`, `/talk-to-data`, **When** l'utilisateur navigue, **Then** la même page s'affiche derrière la protection existante.
2. **Given** une page protégée lazy-loaded, **When** elle charge, **Then** un fallback accessible est affiché pendant le chargement.
3. **Given** un utilisateur non authentifié, **When** il ouvre une route protégée, **Then** le comportement de redirection/protection reste inchangé.

---

### User Story 4 — Tooling, sécurité client et documentation à jour (Priority: P4)

En tant qu'équipe projet, je veux des conventions documentées et automatisées pour éviter les écarts qualité récurrents.

**Why this priority**: ces améliorations réduisent les frictions et les erreurs, mais elles doivent suivre le socle tests/refactoring.

**Independent Test**: lancer lint, typecheck, tests et vérifier que le README décrit les commandes, l'architecture réelle, les variables d'environnement et les conventions actuelles.

**Acceptance Scenarios**:

1. **Given** un développeur clone le projet, **When** il lit le README frontend, **Then** il trouve les commandes correctes et les routes à jour.
2. **Given** le client API en production, **When** une requête authentifiée est faite, **Then** aucun log token/auth verbeux n'est imprimé en console.
3. **Given** un commit local, **When** le hook pre-commit est activé, **Then** lint/format/tests ciblés protègent les fichiers modifiés.

---

## Edge Cases

- Auth activée vs désactivée (`VITE_ENABLE_AUTH`) : les tests doivent couvrir au moins le mode dev sans authentification réelle.
- Requêtes concurrentes : l'indicateur global de loading ne doit pas rester bloqué si une requête échoue.
- Cache TanStack Query : les clés doivent inclure période, scope, cloud provider et filtres pour éviter d'afficher des données obsolètes.
- Lazy loading : les routes profondes doivent rester compatibles avec le déploiement SPA CloudFront/S3.
- Logs sécurité : aucun secret, token, header `Authorization` ou longueur de token ne doit être loggé en production.
- Pre-commit : ne doit pas imposer une suite trop lente à chaque commit.

## Requirements

### Functional Requirements

- **FR-001**: Le frontend MUST disposer d'une commande de test automatisée documentée dans `packages/dcm-frontend/package.json` et le README.
- **FR-002**: Les tests MUST couvrir au minimum un composant UI/domain, un flow de page avec API mockée et un état d'erreur utilisateur.
- **FR-003**: Les appels API des pages critiques SHOULD être migrés progressivement vers TanStack Query avec des query keys explicites.
- **FR-004**: Le premier incrément MUST migrer `Dashboard` sans changer son comportement utilisateur ni ses paramètres API.
- **FR-005**: Les routes protégées MUST conserver les URLs existantes et le comportement `ProtectedRoute`.
- **FR-006**: Les pages protégées SHOULD être chargées paresseusement avec un fallback accessible.
- **FR-007**: Les logs du client API MUST éviter les détails sensibles liés au token/auth en production.
- **FR-008**: Le README frontend MUST refléter les commandes, routes, variables d'environnement et conventions réelles.
- **FR-009**: Le tooling SHOULD inclure formatage et hooks pre-commit si l'équipe accepte l'ajout de dépendances dev.
- **FR-010**: Toute modification MUST respecter TypeScript strict et le lint existant.

### Non-Functional Requirements

- **NFR-001**: La migration doit être incrémentale et reviewable par petits PRs.
- **NFR-002**: Aucune dépendance frontend lourde ne doit être ajoutée sans justification.
- **NFR-003**: Les tests doivent être hermétiques et ne pas appeler le backend réel.
- **NFR-004**: Les refactorings ne doivent pas modifier les contrats API backend.
- **NFR-005**: Les changements de tooling doivent rester compatibles avec Vite 5, React 18 et TypeScript 5.

### Key Entities

- **Frontend Route**: URL, composant page, protection auth, stratégie lazy/eager.
- **Query Key**: identifiant TanStack Query construit depuis endpoint, scope, période, cloud provider et filtres.
- **API Query Hook**: hook typé qui encapsule un appel `dcmApiClient` et expose loading/error/data/refetch.
- **Test Fixture**: jeu de données mocké représentant les réponses API critiques.

## Success Criteria

### Measurable Outcomes

- **SC-001**: `npm run test` ou équivalent existe et passe dans `packages/dcm-frontend`.
- **SC-002**: Au moins 5 tests frontend couvrent composants, hooks/query et page critique.
- **SC-003**: `Dashboard` utilise TanStack Query ou une couche query équivalente, sans régression UI visible.
- **SC-004**: `App.tsx` réduit la duplication de routes protégées via une configuration centralisée.
- **SC-005**: Les routes existantes listées dans `App.tsx` continuent de fonctionner.
- **SC-006**: Aucun log sensible lié au token n'est présent dans le client API.
- **SC-007**: README frontend mis à jour et aligné avec `package.json`.
- **SC-008**: `npm run lint`, `npm run build` et les tests passent.

## Assumptions

- Le package manager actuel du dossier `packages/dcm-frontend` reste `npm` tant qu'aucun fichier lock ou règle de monorepo n'impose autre chose.
- TanStack Query peut être ajouté comme dépendance frontend si validé par l'équipe.
- Vitest + Testing Library sont préférés pour rester cohérents avec Vite.
- La première livraison vise la qualité du socle, pas une migration complète de toutes les pages en une seule PR.
- Les règles Spec Kit du repo s'appliquent : traçabilité, tests, documentation et gates de qualité.

