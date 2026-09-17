# T003 — Frontend : écrans self-service projet et matrice de rôles à deux niveaux

**Domain**: frontend
**Package**: `packages/dcm-frontend`
**Branch**: frontend/015-project-access-governance
**Jira**: DCINT-258
**Depends on**: T002 (contrat OpenAPI figé)
**Work type**: feature

> **Branch** = git **branch name** only. Never a commit SHA.

## Description

Rend la gouvernance self-service utilisable : créer un projet (BA existante, pas de texte libre), rejoindre un projet existant, gérer membres/rôles d'un projet administré, demander une extension de périmètre, et afficher un état vide navigable. La matrice d'accès combine `platform_role` (plateforme) et rôle projet (`viewer`/`admin`), avec des libellés lisibles (noms, pas d'identifiants).

## Files to create/modify

- CREATE écrans projet (créer / rejoindre / gérer membres / demander extension) + état vide
- UPDATE api client central + hooks TanStack Query (`/v1/projects*`, `/auth/me` enrichi)
- UPDATE matrice de rôles (`platform_role` + rôle projet) pilotant l'accès pages/actions
- UPDATE `app-routes.ts` pour les nouvelles routes
- CREATE tests Vitest (réseau mocké) `role-access` + `projects`

## Acceptance Criteria

- [ ] Compte `user` sans projet ⇒ application vide navigable invitant à créer/rejoindre
- [ ] Écran création : sélection **Business Application existante** (pas de texte libre) + membres + LZ/DBX ⇒ soumission `pending_validation`
- [ ] Admin projet ⇒ ajouter/retirer membres, changer rôles, demander extension — **uniquement pour ce projet**
- [ ] Retrait du dernier admin ⇒ erreur **409** restituée de façon lisible
- [ ] Matrice de rôles combine `platform_role` + rôle projet ; affiche libellés lisibles (noms, pas d'id bruts — FR-017)
- [ ] `npm run lint` + `npm run typecheck` verts

## Tests

- `cd packages/dcm-frontend && npm run test -- role-access projects`
- `npm run lint && npm run typecheck`

## Out of scope

- Endpoints backend (T002) — consommés via API mockée en dev
- DDL / migration (T001)

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside package scope
- [ ] Diff stays reviewable (prefer fewer changed files / one concern)
- [ ] Sub-spec checkboxes reviewed
- [ ] Jira Story lists **Git branch** name (not a commit SHA)

## Notes

Contrat consommé (figé par T002) : [contracts/projects-api.md](../contracts/projects-api.md). Conventions : api client central + hooks TanStack Query + labels lisibles + tests mockés (P16, skill dcm-react). Notifications in-app uniquement (FR-020a) ; resoumission libre après rejet (FR-020b).
