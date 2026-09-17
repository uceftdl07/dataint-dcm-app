# T002 — Backend : endpoints register/join projet + modèle d'autorisation réduit à 3 rôles

**Domain**: backend
**Package**: packages/dcm-backend (+ packages/dcm-commons si un enum/modèle de rôle bouge)
**Branch**: frontend/015-project-access-governance  <!-- override single-branch : pas de branche fille 016 -->
**Jira**: pending
**Depends on**: none (s'appuie sur les tables projet 015 T001, prérequis figé)
**Work type**: feature

> **Branch** = git **branch name** only. Override 016 : tout se fait sur `frontend/015-project-access-governance`.

## Description

Exposer la registration/adhésion **par projet** consommée par la page login, et **réduire le modèle de rôles à 3** : project admin, project viewer (scope projet), platform admin (`super_admin`, scope plateforme). Les rôles plats hérités sont mappés en lecture (jamais assignables). Retirer le seul chemin de self-registration LZ (`lz_registration`) en conservant le flux `dcm_access`.

## Files to create/modify

- CREATE/UPDATE packages/dcm-backend/app/api/routes/projects.py — `POST /api/v1/projects/register` (201, 409 si BA déjà dotée), `POST /api/v1/projects/join` (202)
- UPDATE packages/dcm-backend/app/auth/role_permissions.py — réduire `DCM_EFFECTIVE_ROLES` à l'ensemble exposé (projet `{viewer, admin}` + plateforme `{super_admin}`) + mapping des rôles hérités
- UPDATE packages/dcm-backend/app/api/routes/access_requests.py — retirer le chemin `lz_registration` (`[LZ REGISTRATION]`, l.95/102/125) ; garder `dcm_access`
- UPDATE packages/dcm-commons — enum/`Literal` rôle si partagé (imports absolus)
- UPDATE packages/dcm-backend/app/main.py — enregistrer le router projet si nouveau

## Acceptance Criteria

- [ ] `POST /projects/register` crée un projet `pending_validation` avec BA + membres/rôles + scopes LZ/workspaces ; requester = project admin (FR-002, FR-003)
- [ ] BA déjà dotée d'un projet → **409** avec message invitant à rejoindre (FR-003)
- [ ] `POST /projects/join` crée une `dcm_project_join_request` `pending` routée vers les admins du projet, ou le **créateur** si `pending_validation` (FR-004, clarif. routage)
- [ ] Rôles effectifs énumérés = exactement 3 ; rôles hérités mappés (`admin`→project admin ; `manager`/`data_architect`→project viewer ; `pending`→aucun) et jamais assignables (FR-006, FR-007, SC-003)
- [ ] Le chemin `lz_registration` est retiré ; `dcm_access` reste fonctionnel (FR-005)
- [ ] Gates BE verts : ruff → mypy → pytest

## Tests

- `pytest packages/dcm-backend` : register 201/409, join 202 (+ routage créateur si `pending_validation`), énumération rôles = 3, mapping rôle hérité non assignable, `dcm_access` intact après retrait `lz_registration`
- `ruff check . && mypy .`

## Out of scope

- UI login / formulaires / navigation → T001
- Tables projet + colonne `platform_role` + migration accès plats → 015 T001

## Before PR

- [ ] Merged latest develop before PR (`git merge origin/develop`)
- [ ] Tests pass
- [ ] Commit BE focalisé (séparé du commit FE T001)
- [ ] Diff reste lisible
- [ ] Sub-spec checkboxes reviewed
- [ ] `/speckit.dcm.review --commit` exécuté avant commit (jamais `--no-verify`)

## Notes

- Clarifications (spec §Clarifications, 2026-08-31) : mapping rôles hérités ; requester auto project admin ; join routé vers créateur si projet `pending_validation` ; retrait limité au chemin `lz_registration`.
- Contrat register/join à figer avant consommation par T001 (P15). Réutiliser les données de référence LZ (`ba_name`) pour la BA et les LZ/workspaces par défaut.
