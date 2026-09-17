# Implementation Plan: Mounir Live API Demo

**Branch**: `003-mounir-live-api-demo` | **Date**: 2026-05-25 | **Spec**: `specs/003-mounir-live-api-demo/spec.md`

**Input**: Feature specification from `/specs/003-mounir-live-api-demo/spec.md`

## Summary

Transformer `/talk-to-data` en demo de developpement connectee aux APIs DCM existantes. Mounir reste un assistant a intentions simples cote frontend, mais les reponses principales viennent des endpoints live deja disponibles via `dcmApiClient`.

## Technical Context

- **Language/Version**: TypeScript 5, React 18, Vite
- **Primary Dependencies**: React Router, Tailwind CSS, Lucide React, MSAL, `dcmApiClient`
- **Storage**: aucun stockage conversationnel
- **Testing**: Vitest + Testing Library, API mockee
- **Target Platform**: Browser SPA, dev Vite port 4000
- **Constraints**: pas de nouvel endpoint backend, pas de LLM, pas de secret, pas de changement de contrat API

## Constitution Check

- **Test-First & Code Quality**: couvrir la detection d'intentions ou le comportement API avec tests frontend lorsque le code le permet.
- **Explicit Architecture & Modularity**: garder `TalkToYourData.tsx` lisible en isolant la detection d'intention et la construction de reponse si necessaire.
- **Security & Secrets Management**: passer uniquement par `dcmApiClient`, ne jamais loguer token/header.
- **Observability & Traceability**: afficher les sources APIs utilisees dans la reponse utilisateur.
- **Simplicity & Versioning**: Phase 0 transitoire, facile a remplacer par `/api/v1/talk-to-data/query` plus tard.

## Project Structure

```text
specs/003-mounir-live-api-demo/
├── spec.md
├── plan.md
└── tasks.md

packages/dcm-frontend/src/
├── pages/
│   └── TalkToYourData.tsx
├── api/
│   └── dcmApiClient.ts
└── types/
    └── api.ts

docs/05-mounir-ai/
└── AGENT-MOUNIR.md
```

## Proposed Design

### Phase 0 UX

- Ajouter un message visible "version developpement".
- Conserver les suggestions, mais les aligner avec les intentions live.
- Marquer les reponses live avec `Live DCM API`.
- Garder un fallback explicite pour les questions non supportees.

### Intent Routing Frontend

- Utiliser une detection simple par mots-cles.
- Mapper les intentions vers les appels existants :
  - `costs` -> `getCostSummary`, `getCostsByService`
  - `pipelines` -> `listPipelines`
  - `security` -> `listSecurityAlerts`
  - `governance` -> `getGovernanceScore`, `listStandardChecks`
  - `data-product-usage` -> `getDataProductUsageOverview`, `getTopDataProductConsumers`
  - `overview` -> `getDashboardOverview`

### Error Handling

- Si l'API echoue, afficher un message clair et non technique.
- Si les donnees sont vides, afficher une synthese vide mais utile.

## Implementation Phases

### Phase 1 — Spec et documentation

- Creer la spec Spec Kit.
- Mettre a jour la documentation Mounir pour ajouter la Phase 0.

### Phase 2 — Frontend live demo

- Brancher `TalkToYourData.tsx` sur `dcmApiClient`.
- Ajouter detection d'intentions et formatage de syntheses.
- Mettre a jour les suggestions et les etapes de reflexion.

### Phase 3 — Validation

- Lancer lint/typecheck/tests pertinents.
- Corriger les erreurs introduites.

## Risks

- Les donnees backend locales peuvent etre absentes : prevoir des messages vides propres.
- Le composant actuel est assez gros : limiter le refactoring pour eviter une PR difficile a relire.
- La detection par mots-cles peut rater certaines formulations : documenter que c'est une Phase 0.
