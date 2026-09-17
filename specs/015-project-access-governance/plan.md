# Implementation Plan — Gouvernance des accès DCM (modèle projet, V2)

**Feature**: 015-project-access-governance | **Branch base**: `develop` | **Date**: 2026-08-21
**Spec**: [spec.md](spec.md) | **Input**: ADR-0001 (V2 single Entra group) + spike `docs/spike/access-group-governance`

## Summary

Remplace la stratégie d'access group / rôle actuelle de DCM par le modèle **projet** décrit dans l'ADR-0001 (V2). Entra ID est réduit à un unique groupe `DCM-Users` servant de **gate d'authentification** ; toute l'autorisation (projets, rôles, périmètres) vit dans des tables Delta DCM, source de vérité unique. Un projet = 1:1 avec une Business Application. Deux niveaux d'admin (platform_admin / project admin), périmètre à deux dimensions (Landing Zones + workspaces Databricks), et une migration idempotente des accès plats existants vers des projets par défaut.

## Technical Context

| Aspect | Choix |
|---|---|
| Langages | Python 3.12 (backend FastAPI + asyncpg, `our_catalogs_spn.py`), TypeScript/React 18 (frontend) |
| Stockage autorisation | Delta `it.ba_data_connect_monitoring__<env>` (tables `dcm_*`), lu via `DatabricksWarehousePool` |
| Auth | Microsoft Entra ID — **1 seul groupe `DCM-Users`** (gate) ; autorisation en base DCM |
| Modèles partagés | `dcm-commons/models/projects.py` + `enums.py` |
| Couche autorisation | `dcm-backend/app/auth/scope.py` (`AllowedScope`, `get_allowed_scope`, `is_project_admin`) |
| Migration | `our_catalogs_spn.py --migrate-projects [--apply]` (dry-run par défaut, idempotent) |
| Tests | pytest + pytest-asyncio (Python), Vitest (frontend) |
| Lint / types | ruff + mypy (zéro warning), ESLint + tsc |
| Prérequis externe | Feature 014 (référentiel `dim_reference_landing_zone_business_application`) déployée |
| Unknowns | Aucun `[NEEDS CLARIFICATION]` — verrouillés par ADR-0001 + `/speckit.clarify` 2026-08-21 |

## Constitution Check

| Principe | Statut | Justification |
|---|---|---|
| P1 Test-First & Code Quality (NON-NEGOTIABLE) | ✅ | Tests migration (idempotence, mapping rôles, auto-promo admin), auth (`get_allowed_scope`, garde dernier admin 409, `require_platform_admin` 403), routes, Vitest matrice rôle. |
| P2 Simplicity & Versioning | ✅ | Portage du prototype sans changement de logique (D2) ; pas de RBAC générique. |
| P4 Fail Fast, Fail Loud | ✅ | 409 duplicat BA / dernier admin ; 403 admin non autorisé ; LZ non résolue loggée + rapport. |
| P5 Explicit Architecture & Modularity | ✅ | Packages disjoints par branche ; modèles dans dcm-commons ; auth isolée. |
| P6 Idempotency by Design | ✅ | Migration `WHERE NOT EXISTS`/MERGE par clé métier ; re-run = 0 changement (SC-002). |
| P7/P8 Secrets (NON-NEGOTIABLE) | ✅ | SPN OAuth chargé via env ; aucun secret en dur. ⚠️ un `client_secret` traîne dans l'historique terminal du dev — à faire tourner (hors code). |
| P9 No Fake Data in Production (NON-NEGOTIABLE) | ✅ | Migration sur vraies tables `dcm_user_lz_access` ; pas de mock en prod. |
| P10 Observability & Traceability | ✅ | Chaque décision admin ⇒ ligne `dcm_audit_log` (FR-020). |
| P11 Naming Conventions | ✅ | `platform_role`, `dcm_project_*`, enums `Literal` ; pas d'anciens noms Cluster/Compliance. |
| P14 Schema Versioning | ✅ | `ALTER TABLE ADD COLUMN IF NOT EXISTS` (additif) ; `role` historique conservé pour rollback. |
| P15 API Contract Stability | ✅ | Contrat OpenAPI figé ([contracts/projects-api.md](contracts/projects-api.md)) avant consommation frontend ; `get_allowed_lz_ids` conservé pour limiter le blast radius (D3). |
| P16 Frontend Quality | ✅ | api client central + hooks TanStack Query + libellés lisibles (name, pas id) ; tests mockés. |

**Gate**: PASS — aucune violation non justifiée.

## Phase 0 — Research

Voir [research.md](research.md). Décisions D1–D7 verrouillées (Entra single group, portage prototype, compat `get_allowed_lz_ids`, périmètre vide ⇒ 200/403, migration 1:1 BA, colonne `platform_role`, gardes admin + audit). Toutes les inconnues résolues.

## Phase 1 — Design & Contracts

- **Data model**: [data-model.md](data-model.md) — 6 tables projet + `ALTER dcm_app_users ADD platform_role`, relations, modèles Pydantic dcm-commons, règles de validation API.
- **Contracts**: [contracts/projects-api.md](contracts/projects-api.md) — endpoints `/v1/projects*`, `/v1/projects/{id}/members`, join / scope requests, `/auth/me` enrichi, filtrage métrique 2 dimensions.
- **Quickstart**: [quickstart.md](quickstart.md) — créer tables → migrer → valider périmètre en dev.
- **Merge strategy**: [merge-strategy.md](merge-strategy.md) — 3 branches filles, ordre DataEng → Backend → Frontend sur contrats figés.

## Phase 2 — Work Breakdown (preview)

| ID | Domain | Branche | Résumé |
|----|--------|---------|--------|
| T001 | DataEng | `dataeng/015-project-access-governance` | 6 tables projet + `platform_role` + migration idempotente des accès plats |
| T002 | Backend | `backend/015-project-access-governance` | `get_allowed_scope`/`is_project_admin`, routes projet/join/scope, filtrage 2 dimensions, gardes admin + audit |
| T003 | Frontend | `frontend/015-project-access-governance` | Écrans créer/rejoindre/administrer projet, état vide, matrice rôle |

Détail et découpage : `/speckit.dcm.tasks` (génère `tasks.md` + stories).

## Prerequisites reminder

Small branches / small PRs — une branche fille par domaine, package/concern focalisé, coupée depuis `develop` à jour, PR → `develop`, sync `git merge origin/develop` avant PR.
