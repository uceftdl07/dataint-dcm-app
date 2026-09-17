# Implementation Plan: Frontend Quality Hardening

**Branch**: `002-frontend-quality-hardening` | **Date**: 2026-05-25 | **Spec**: `specs/002-frontend-quality-hardening/spec.md`

**Input**: Feature specification from `/specs/002-frontend-quality-hardening/spec.md`

**Note**: Plan structuré selon Spec Kit pour transformer la review frontend en travaux incrémentaux, testables et reviewables.

## Summary

Durcir la qualité du frontend `packages/dcm-frontend` en ajoutant un socle de tests, en standardisant progressivement la gestion du server state avec TanStack Query, en simplifiant le routing protégé/lazy loading, puis en mettant à jour le tooling, les logs sécurité et la documentation. La structure de dossiers existante est conservée.

## Implementation Status

Statut au 2026-05-25 :

- Spec Kit prerequisites validés pour `specs/002-frontend-quality-hardening`.
- Socle Vitest + Testing Library ajouté et validé avec 20 tests.
- `Dashboard` migré vers TanStack Query via des hooks dédiés et query keys explicites.
- Routes protégées centralisées et lazy-loadées sans changement d'URL attendu.
- Logs client auth/token sensibles nettoyés.
- README frontend aligné avec les scripts, routes, variables d'environnement et conventions actuelles.
- Prettier, Husky et lint-staged restent différés tant que l'équipe n'a pas approuvé ces dépendances optionnelles.
- Validation finale exécutée : `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`. Le build passe avec un avertissement Vite de taille de chunks à surveiller.

## Technical Context

- **Language/Version**: TypeScript 5, React 18.3, Vite 5
- **Primary Dependencies**: React Router 6, Tailwind CSS 3, MSAL React, Recharts, Lucide React
- **Proposed Dependencies**: `@tanstack/react-query`, `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`, optional `prettier`, `husky`, `lint-staged`
- **Storage**: N/A côté frontend ; server state issu de `dcm-backend` via `packages/dcm-frontend/src/api/dcmApiClient.ts`
- **Testing**: Vitest + Testing Library, API mockée sans backend réel
- **Target Platform**: Browser SPA déployée via S3/CloudFront, dev Vite port 4000
- **Project Type**: Web application frontend
- **Performance Goals**: réduire le bundle initial en lazy-loadant les pages protégées ; conserver un fallback visible pendant chargement
- **Constraints**: URLs existantes inchangées, auth MSAL inchangée, TypeScript strict, pas de breaking change API, pas de logs sensibles
- **Scale/Scope**: 1 package frontend, environ 20 pages, client API partagé, layout protégé commun

## Constitution Check

*GATE: Must pass before implementation and re-check before merge.*

- **Test-First & Code Quality**: ajouter les tests avant ou avec chaque refactoring. Les changements ne sont complets que si `lint`, `build` et tests passent.
- **Explicit Architecture & Modularity**: préserver la séparation existante `api/`, `components/`, `contexts/`, `hooks/`, `lib/`, `pages/`, `types/`. Ajouter des hooks query dédiés plutôt que charger la logique dans les composants.
- **Security & Secrets Management**: supprimer les logs auth/token verbeux ; aucun secret ou header sensible dans le code ou la console.
- **Observability & Traceability**: conserver des erreurs utilisateur exploitables et documenter les conventions de test/query/routing.
- **Simplicity & Versioning**: migration incrémentale ; pas de refonte de design system ni routing framework.

## Project Structure

### Documentation (this feature)

```text
specs/002-frontend-quality-hardening/
├── spec.md
├── plan.md
├── tasks.md
└── checklists/
    └── requirements.md
```

### Source Code (repository root)

```text
packages/dcm-frontend/
├── package.json                         # scripts test/format/pre-commit éventuels
├── README.md                            # documentation à aligner
├── vite.config.ts                       # config test Vitest si retenue
├── src/
│   ├── App.tsx                          # route config + lazy loading
│   ├── api/
│   │   └── dcmApiClient.ts              # logs auth/token à nettoyer
│   ├── components/
│   │   ├── domain/                      # composants critiques à tester
│   │   ├── layout/
│   │   └── ui/
│   ├── hooks/                           # hooks query ou index d'exports
│   ├── pages/
│   │   └── Dashboard.tsx                # premier incrément React Query
│   └── test/                            # setup/fixtures éventuels
```

**Structure Decision**: conserver l'architecture actuelle et ajouter les artefacts manquants au plus près des usages. Pas de déplacement massif de fichiers.

## Proposed Design

### Testing Layer

- Ajouter Vitest + Testing Library.
- Créer un `src/test/` ou `src/__tests__/` minimal pour `setup`, wrappers providers et fixtures API.
- Tester d'abord les composants/domain states qui ont le plus de valeur : états loading, erreurs, cartes métriques, flow dashboard mocké.

### TanStack Query Layer

- Ajouter un `QueryClientProvider` au niveau racine ou autour de l'app.
- Créer des hooks query typés pour les endpoints critiques du dashboard.
- Construire des query keys explicites : `dashboard`, période, scope, cloud provider.
- Garder `dcmApiClient.ts` comme couche transport pour éviter une double migration.

### Routing Layer

- Extraire une configuration de routes protégées avec `path`, `Component`, `label` si utile.
- Remplacer les imports eager de pages protégées par `React.lazy`.
- Factoriser le wrapper `ProtectedRoute` + `ProtectedLayout`.
- Maintenir `MounirPageBubble` et les routes publiques sans changement de comportement.

### Security & Tooling

- Remplacer les logs auth/token par logs debug non sensibles ou les supprimer.
- Ajouter formatage/pre-commit uniquement si l'équipe accepte les dépendances dev.
- Mettre à jour `README.md` pour refléter le port 4000, les routes actuelles, scripts, env vars et conventions.

## Implementation Phases

### Phase 1 — Setup tests et qualité

But : rendre les changements suivants vérifiables automatiquement.

Livrables :

- Dépendances test.
- Script `test`.
- Setup Testing Library.
- Fixtures API mockées.
- Premiers tests verts.

Gate :

- `npm run test` existe et passe.
- `npm run lint` passe.

### Phase 2 — Dashboard query migration

But : prouver le pattern TanStack Query sur une page critique avant généralisation.

Livrables :

- `QueryClientProvider` intégré.
- Hooks query dashboard.
- `Dashboard.tsx` simplifié.
- Tests loading/success/error/refetch.

Gate :

- Dashboard affiche les mêmes données mockées.
- Les query keys varient selon période/scope/cloud.

### Phase 3 — Routing protégé et lazy loading

But : réduire la duplication dans `App.tsx` et améliorer le bundle initial.

Livrables :

- Route config centralisée.
- Pages protégées lazy-loaded.
- Fallback accessible.
- Tests ou validation manuelle des URLs existantes.

Gate :

- Toutes les routes existantes restent accessibles.
- Auth/protection inchangée.

### Phase 4 — Sécurité client, tooling, documentation

But : finaliser les pratiques durables.

Livrables :

- Logs token/auth nettoyés.
- README à jour.
- Prettier/husky/lint-staged si validé.
- Scripts documentés.

Gate :

- Aucun log sensible.
- `npm run lint`, `npm run build`, `npm run test` passent.

## Dependencies & Order

- Phase 1 bloque les refactorings significatifs.
- Phase 2 dépend de Phase 1.
- Phase 3 peut démarrer après Phase 1, mais doit être coordonnée avec Phase 2 car les deux touchent `App.tsx`.
- Phase 4 peut avancer en parallèle sur README et logs, mais le tooling pre-commit doit attendre la stabilisation des scripts.

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Ajout de TanStack Query trop large | PR difficile à reviewer | Migrer `Dashboard` d'abord, documenter pattern |
| Tests instables à cause de MSAL | Perte de confiance dans la suite | Utiliser wrappers/mocks et tester le mode dev sans auth réelle |
| Lazy loading casse CloudFront refresh | Routes profondes inutilisables | Vérifier config SPA existante et ne pas changer les URLs |
| Pre-commit trop lent | Développeurs contournent le hook | Utiliser lint-staged ciblé, garder les tests complets en CI |
| Nettoyage logs masque les erreurs | Debug plus difficile | Garder messages d'erreur non sensibles et actionnables |

## Validation Commands

Depuis `packages/dcm-frontend` :

```bash
npm install
npm run lint
npm run build
npm run test
```

Si un script n'existe pas encore, sa création fait partie des tâches Phase 1 ou Phase 4.

## Open Questions

- Résolu : TanStack Query a été ajouté comme dépendance frontend et utilisé pour le premier incrément `Dashboard`.
- À décider : l'équipe veut-elle rendre Prettier/husky/lint-staged obligatoires dès cette feature ou seulement documenter la recommandation ?
- À décider : les tests doivent-ils être exigés en CI dès le premier incrément ou après stabilisation de la suite minimale ?

