# T002 — Backend : autorisation scopée projet, routes self-service et filtrage 2 dimensions

**Domain**: backend
**Package**: `packages/dcm-backend`, `packages/dcm-commons`
**Branch**: backend/015-project-access-governance
**Jira**: DCINT-260
**Depends on**: T001 (schéma + tables figés)
**Work type**: feature

> **Branch** = git **branch name** only. Never a commit SHA.

## Description

Expose l'autorisation par projet : calcul du périmètre (union des LZ + workspaces DBX des projets `active` de l'utilisateur), routes de création/adhésion/extension avec validation à deux étages (platform_admin / project admin), et bascule du filtrage des routes métriques vers les deux dimensions LZ + workspace Databricks. Porte les règles de sécurité (isolation project admin, garde dernier admin, gate `DCM-Users`, audit). Fige le contrat OpenAPI consommé par T003.

## Files to create/modify

- CREATE `packages/dcm-backend/app/auth/scope.py` — `AllowedScope`, `get_allowed_scope`, `get_allowed_scope_dep`, `add_scope_filter`, `is_project_admin`, `require_platform_admin` (portage `project_scope_prototype.py`, D2/D3)
- UPDATE `packages/dcm-backend/app/auth/` — conserver `get_allowed_lz_ids` (compat, dérivé de `get_allowed_scope`) ; enrichir `/auth/me` (`platform_role` + memberships)
- CREATE routes `/v1/projects*`, `/v1/projects/{id}/members`, join-requests, scope-requests (voir contrat)
- UPDATE routes métriques existantes — appliquer `add_scope_filter` (2 dimensions)
- CREATE `packages/dcm-commons/models/projects.py` + enums (`enums.py`)
- CREATE tests pytest (scope, gardes admin, routes)

## Acceptance Criteria

- [ ] Membre actif (LZ_A + workspace_W) ⇒ routes métriques filtrées `WHERE :unrestricted OR source_lz_id IN (…) OR workspace_id IN (…)`
- [ ] Utilisateur sans projet actif ⇒ **200 + collection vide** (pas 403) sur routes métriques (D4)
- [ ] `platform_role = super_admin` ⇒ périmètre `unrestricted`
- [ ] Création projet (BA existante) ⇒ `pending_validation` + demande routée platform_admin ; **409** si la BA a déjà un projet (FR-011a)
- [ ] Validation platform_admin ⇒ `status=active` + membres créés ; créateur auto-membre `admin` (FR-011)
- [ ] Demande d'adhésion ⇒ `dcm_project_join_requests` `pending` ; resoumission libre après rejet (FR-020b)
- [ ] Demande d'extension périmètre ⇒ `dcm_project_scope_requests` `pending`, validée par platform_admin avant application
- [ ] Retrait/rétrogradation du dernier `admin` d'un projet `active` ⇒ **409** (sauf platform_admin) (FR-014)
- [ ] Project admin agissant sur un autre projet ⇒ **403**
- [ ] Toute décision d'admin ⇒ ligne `dcm_audit_log` (FR-020)
- [ ] `ruff check` + `mypy app` zéro warning

## Tests

- `cd packages/dcm-backend && uv run pytest tests/ -k "scope or project" -q`
- `uv run ruff check . && uv run mypy app`

## Out of scope

- DDL / migration (T001)
- Écrans UI (T003)
- Retrait définitif de `get_allowed_lz_ids` (conservé compat)

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside package scope
- [ ] Diff stays reviewable (prefer fewer changed files / one concern)
- [ ] Sub-spec checkboxes reviewed
- [ ] Jira Story lists **Git branch** name (not a commit SHA)

## Notes

Contrat à figer (consommé par T003) : [contracts/projects-api.md](../contracts/projects-api.md) — toute déviation met d'abord à jour ce fichier. Modèles : [data-model.md](../data-model.md). Décisions D2/D3/D4/D7 : [research.md](../research.md). Réponses exposent `displayName` lisible (FR-017), jamais d'id brut. Aucun secret en dur (P7/P8) ; pas de données fictives (P9).
