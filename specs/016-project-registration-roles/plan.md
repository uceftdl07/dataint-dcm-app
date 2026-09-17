# Implementation Plan — Registration par projet (page login) + refonte des rôles à 3 niveaux

**Feature**: 016-project-registration-roles | **Branch base**: `develop` | **Date**: 2026-08-31
**Spec**: [spec.md](spec.md) | **Input**: bascule finale du modèle projet 015 vers la page login + réduction des rôles

> **Décision d'exécution (override)** : contrairement à la convention DCM `{domain}/016-{slug}` (une branche fille par domaine), **tout 016 est réalisé sur la branche courante `frontend/015-project-access-governance`** — Frontend (T001) + Backend (T002) dans une **PR unique** vers `develop`. Conséquence assumée : le Prerequisite « small branches / small PRs » de la spec ne s'applique pas ; le diff mêle `dcm-frontend` + `dcm-backend` et cohabite avec le travail 015 non mergé. Le gate pre-commit DCM (`/speckit.dcm.review --commit`) reste requis.

## Summary

016 finit la bascule engagée par 015 : la registration ne se fait plus **par landing zone** mais **par projet**, dès la page de login. Le bloc « Register a landing zone » devient **« Join or Register a project »** ; l'onglet « My Landing Zones » (`/my-access`) et le parcours self-service LZ (`lz_registration`) disparaissent ; le modèle de rôles passe d'un modèle plat à 6 rôles à **exactement 3 rôles exposés** : project admin / project viewer (scope projet), platform admin (`super_admin`, scope plateforme). Les rôles hérités (`data_architect`, `manager`, `admin`, `pending`) sont mappés (jamais assignables) via `platform_role`/migration 015.

## Technical Context

| Aspect | Choix |
|---|---|
| Langages | TypeScript/React 18 (frontend), Python 3.12 (backend FastAPI + asyncpg) |
| Frontend | Vite, TanStack Query 5, Vitest 4, ESLint zéro-warning ; api client central + hooks |
| Backend | FastAPI (`/api/v1`), `DatabricksWarehousePool`, pytest + pytest-asyncio, ruff + mypy zéro-warning |
| Modèles partagés | `dcm-commons` — enum rôles si un `Literal`/modèle bouge (imports absolus) |
| Socle projet consommé | Tables `dcm_project_*` + endpoints `/projects*` (015 T001 + T002) |
| Source rôles backend | `dcm-backend/app/auth/role_permissions.py` (`DCM_STORED_ROLES` / `DCM_EFFECTIVE_ROLES`) |
| Registration LZ (à retirer) | `access_requests.py` — chemin `lz_registration` (préfixe justification `[LZ REGISTRATION]`, l.95/102/125) ; garder `dcm_access` |
| Navigation / routes FE | `config/navigation.ts` (`SETTINGS_MENU` → item « My Landing Zones »), `app-routes.ts` (`/my-access` → `MyLandingZones`), `lib/role-access.ts` |
| Chooser login FE | `LandingRequestChooserModal.tsx` (kinds `dcm_access` / `lz_registration`), `LzRegistrationRequestModal.tsx` |
| Dépendance externe | 015 endpoints `/projects*` — **absents sur cette branche** ; FE tolère déjà 404 (`emptyOn404` dans `useProjectsQueries.ts`), BE (T002) ajoute register/join ici |
| Unknowns | Aucun `[NEEDS CLARIFICATION]` — levés par `/speckit.clarify` 2026-08-31 (§ Clarifications de la spec) |

## Constitution Check

| Principe | Statut | Justification |
|---|---|---|
| P1 Test-First & Code Quality (NON-NEGOTIABLE) | ✅ | Vitest : chooser « Join or Register a project », submit Register (BA + membres + scopes), submit Join, absence route `/my-access` + item nav, matrice 3 rôles. Pytest : register 201/409 (BA prise), join 202 (routage créateur si `pending_validation`), énumération rôles effectifs = 3, rôle hérité mappé jamais assignable. |
| P2 Simplicity & Versioning | ✅ | Réutilise le socle projet 015 ; pas de nouveau modèle d'autorisation générique, simple collapse de l'ensemble effectif + mapping. |
| P4 Fail Fast, Fail Loud | ✅ | 409 sur BA déjà dotée d'un projet (message « rejoindre ») ; 403 hors projet ; validation email/BA au boundary. |
| P5 Explicit Architecture & Modularity | ✅ | FE et BE restent dans leurs packages ; enum rôles centralisé (dcm-commons/backend) ; auth isolée dans `role_permissions.py`. |
| P7/P8 Secrets (NON-NEGOTIABLE) | ✅ | Aucun secret introduit ; emails saisis en clair côté login = donnée fonctionnelle, pas un secret. |
| P9 No Fake Data in Production (NON-NEGOTIABLE) | ✅ | Mock API projet **uniquement en dev** (pattern 015 T003) tant que `/projects*` absent ; jamais en prod. |
| P11 Naming Conventions | ✅ | Rôles `project admin` / `project viewer` / `platform admin` (= `super_admin`) ; pas d'anciens noms de rôles plats ré-exposés. |
| P15 API Contract Stability | ✅ | Contrat register/join figé côté BE avant consommation FE ; `dcm_access` inchangé (seul `lz_registration` retiré). |
| P16 Frontend Quality | ✅ | api client central + hooks TanStack Query, libellés rôles lisibles (name pas id), tests mockés, ESLint zéro-warning. |

**Gate**: PASS — aucune violation non justifiée. P3/P6/P10/P12/P13/P14 N/A (pas de pipeline/ingestion/schéma Delta modifié dans cet Epic — la couche données est 015 T001, hors périmètre).

## Phase 0 — Research

Inconnues résolues par `/speckit.clarify` (§ Clarifications de [spec.md](spec.md)) :

- **Mapping rôles hérités** : `admin` → project admin ; `manager` & `data_architect` → project viewer ; `pending` → aucun rôle effectif.
- **Rôle du requester** (Register) : auto-ajouté **project admin** ; la liste des membres concerne les autres personnes.
- **Routage Join si `pending_validation`** : vers le **créateur/requester** tant que le projet n'est pas validé.
- **Périmètre suppression LZ** : retirer **uniquement** le chemin `lz_registration` de `access_requests.py` ; `dcm_access` conservé.
- **Email login** : saisie libre (visiteur non authentifié).

Aucune recherche technique supplémentaire : la stack, le socle projet et les patterns (mock dev, api client, `emptyOn404`) sont déjà en place.

## Phase 1 — Design & Contracts

**Backend (T002)**

- **Autorisation** : dans `role_permissions.py`, réduire `DCM_EFFECTIVE_ROLES` à l'ensemble exposé (rôle projet `{viewer, admin}` + plateforme `{super_admin}`) ; fonction de mapping des rôles hérités (voir Phase 0) appliquée en lecture, jamais en assignation. Enum `Literal` centralisé (dcm-commons si partagé FE/contrat).
- **Endpoints projet** (s'appuient sur les tables 015) :
  - `POST /api/v1/projects/register` → crée un projet `pending_validation` : BA (unique, sinon **409** « rejoindre »), requester = project admin, membres+rôles, scopes LZ + workspaces Databricks (défaut = ceux de la BA, ajout/retrait). `201`.
  - `POST /api/v1/projects/join` → `dcm_project_join_request` `pending` routée vers les admins du projet, ou le **créateur** si `pending_validation`. `202`.
  - Lecture BA + LZ/workspaces par défaut : réutiliser les données de référence LZ existantes (`ba_name`, `deriveBusinessAppOptions` côté FE).
- **Retrait LZ** : supprimer le chemin `lz_registration` (`[LZ REGISTRATION]`) de `access_requests.py` en conservant le flux `dcm_access`.

**Frontend (T001)**

- **Chooser login** : `LandingRequestChooserModal.tsx` — remplacer le kind `lz_registration` / bouton « Register a landing zone » par **« Join or Register a project »** ; `LandingRequestKind` = `'dcm_access' | 'project_register' | 'project_join'` (ou modal projet dédiée).
- **Formulaires** : Register (email libre, BA en liste, membres+rôle viewer/admin, scopes LZ+workspaces pré-remplis/éditables) ; Join (email libre + projet dans la liste DCM). Consommation via hooks TanStack Query (mock dev si `/projects*` absent).
- **Suppression « My Landing Zones »** : retirer l'item de `SETTINGS_MENU` (`config/navigation.ts`), la route `/my-access` (`app-routes.ts`), et la page `MyLandingZones.tsx` ; nettoyer `page:my-access` des permissions si nécessaire.
- **Rôles 3 valeurs** : sélecteurs et libellés (`lib/role-access.ts`) limités à project admin / project viewer / platform admin, libellés lisibles.

## Phase 2 — Work Breakdown (preview)

| ID | Domain | Branche (override single-branch) | Résumé |
|----|--------|-----------------------------------|--------|
| T001 | Frontend | `frontend/015-project-access-governance` | Chooser login « Join or Register a project » + formulaires Register/Join, suppression « My Landing Zones » (`/my-access`), UI limitée à 3 rôles |
| T002 | Backend | `frontend/015-project-access-governance` | Endpoints register/join projet (201/409/202, routage créateur si `pending_validation`), collapse rôles à 3 + mapping hérités, retrait chemin `lz_registration` |
| — | DataEng | — | ❌ hors Epic — tables projet + `platform_role` + migration livrés par 015 T001 |

Détail et découpage : `/speckit.dcm.tasks` (génère `tasks.md` + `stories/`).

## Prerequisites reminder

Override single-branch acté : les deux Stories sont réalisées sur `frontend/015-project-access-governance`, PR unique → `develop`. Malgré le regroupement, garder les commits **focalisés par préoccupation** (un commit FE, un commit BE) pour préserver la lisibilité de la revue. Sync `git merge origin/develop` avant la PR. Gate `/speckit.dcm.review --commit` obligatoire avant chaque commit (jamais `--no-verify`).
