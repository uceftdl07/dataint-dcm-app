# T001 — Frontend : registration/join projet sur la page login + suppression « My Landing Zones » + UI 3 rôles

**Domain**: frontend
**Package**: packages/dcm-frontend
**Branch**: frontend/015-project-access-governance  <!-- override single-branch : pas de branche fille 016 -->
**Jira**: pending
**Depends on**: T002 (contrat endpoints register/join ; mock dev tant que `/projects*` absent)
**Work type**: feature

> **Branch** = git **branch name** only. Override 016 : tout se fait sur `frontend/015-project-access-governance`.

## Description

Sur la page de login/inscription, remplacer le bloc « Register a landing zone » par une entrée **« Join or Register a project »** avec deux formulaires (Register / Join). Supprimer l'onglet **« My Landing Zones »** (route `/my-access`, item de nav, page). Limiter tous les sélecteurs et libellés de rôles à **3 valeurs** : project admin, project viewer (scope projet), platform admin (scope plateforme). Consommer l'API projet via hooks TanStack Query, avec **mock dev** tant que les endpoints 015/T002 ne sont pas disponibles.

## Files to create/modify

- UPDATE packages/dcm-frontend/src/components/LandingRequestChooserModal.tsx — remplacer le kind `lz_registration` / bouton « Register a landing zone » par « Join or Register a project » (kinds `project_register` / `project_join`)
- CREATE packages/dcm-frontend/src/components/ProjectRegisterRequestModal.tsx — formulaire Register (email libre, BA en liste, membres+rôle viewer/admin, scopes LZ+workspaces pré-remplis/éditables)
- CREATE packages/dcm-frontend/src/components/ProjectJoinRequestModal.tsx — formulaire Join (email libre + projet dans la liste DCM)
- UPDATE packages/dcm-frontend/src/config/navigation.ts — retirer l'item « My Landing Zones » de `SETTINGS_MENU`
- UPDATE packages/dcm-frontend/src/app-routes.ts — retirer la route `/my-access` (`MyLandingZones`)
- DELETE packages/dcm-frontend/src/pages/MyLandingZones.tsx (+ tests associés)
- UPDATE packages/dcm-frontend/src/lib/role-access.ts — limiter les rôles exposés/libellés à project admin / project viewer / platform admin
- UPDATE packages/dcm-frontend/src/hooks/useProjectsQueries.ts (+ api client) — mutations register/join + mock dev
- UPDATE/REMOVE packages/dcm-frontend/src/components/LzRegistrationRequestModal.tsx — supprimer si plus référencé après retrait du parcours LZ

## Acceptance Criteria

- [ ] Le chooser d'inscription affiche « Join or Register a project » et plus « Register a landing zone » (SC-001, FR-001)
- [ ] Register : BA choisie dans une liste (pas de texte libre), email libre, membres avec rôle viewer/admin, LZ+workspaces de la BA pré-sélectionnés et éditables ; le requester est présenté comme project admin (FR-002, clarif. requester)
- [ ] Join : email libre + projet choisi dans la liste des projets DCM, soumission d'une demande d'adhésion (FR-004)
- [ ] La route `/my-access` et l'item « My Landing Zones » sont absents pour tous les rôles (SC-002, FR-005)
- [ ] Les sélecteurs de rôles n'exposent que 3 valeurs avec libellés lisibles (SC-003, FR-006, FR-008)
- [ ] Gates FE verts : lint → types → tests → build

## Tests

- `npm run test` (Vitest, réseau mocké) : chooser, submit Register (payload BA+membres+scopes), submit Join, absence route `/my-access` + nav, matrice 3 rôles
- `npm run lint && npm run build`

## Out of scope

- Endpoints backend register/join et modèle d'autorisation serveur → T002
- Refonte des écrans projet existants (Projects.tsx / ProjectDetail.tsx) au-delà de l'alignement 3 rôles
- Tables projet / migration (015 T001)

## Before PR

- [ ] Merged latest develop before PR (`git merge origin/develop`)
- [ ] Tests pass
- [ ] Commit FE focalisé (séparé du commit BE T002)
- [ ] Diff reste lisible
- [ ] Sub-spec checkboxes reviewed
- [ ] `/speckit.dcm.review --commit` exécuté avant commit (jamais `--no-verify`)

## Notes

- Clarifications (spec §Clarifications, 2026-08-31) : email login = saisie libre ; requester auto project admin ; rôles hérités mappés côté backend (non exposés en création).
- Dépendance T002 : consommer le contrat register/join défini par le backend. Pattern mock dev = 015 T003 ; `emptyOn404` déjà en place dans `useProjectsQueries.ts` pour les collections.
