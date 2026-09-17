# T001 — DataEng : tables projet, `platform_role` et migration des accès plats

**Domain**: dataeng
**Package**: `our_catalogs_spn.py` (racine), `packages/dcm-databricks-pipeline`
**Branch**: dataeng/015-project-access-governance
**Jira**: DCINT-259
**Depends on**: none
**Work type**: feature

> **Branch** = git **branch name** only. Never a commit SHA.

## Description

Crée les 6 tables du modèle « projet » dans le schéma applicatif Delta `it.ba_data_connect_monitoring__<env>` et ajoute la colonne `platform_role` à `dcm_app_users`. Fournit une migration idempotente qui regroupe les accès plats existants (`dcm_user_lz_access`) en projets par défaut, 1:1 avec une Business Application. Socle prérequis de toute la feature ; il DOIT préserver l'accès des utilisateurs existants (US1).

## Files to create/modify

- UPDATE `our_catalogs_spn.py` — DDL des 6 tables projet + `ALTER TABLE dcm_app_users ADD COLUMN IF NOT EXISTS platform_role STRING`
- CREATE fonction `migrate_flat_users_to_projects()` dans `our_catalogs_spn.py` + flags CLI `--migrate-projects` / `--apply` (dry-run par défaut)
- CREATE tests migration (idempotence, mapping rôles, auto-promotion admin, LZ non résolue)

## Acceptance Criteria

- [x] `our_catalogs_spn.py` crée `dcm_projects`, `dcm_project_lz_scope`, `dcm_project_dbx_scope`, `dcm_project_members`, `dcm_project_join_requests`, `dcm_project_scope_requests` (USING DELTA) si absentes
- [x] `dcm_app_users` possède la colonne `platform_role` après exécution (`ADD COLUMN IF NOT EXISTS`, additif — P14)
- [x] `--migrate-projects` seul = **dry-run** (imprime le plan : projets, membres, LZ non résolues) ; `--apply` exécute
- [x] 1 `dcm_projects` `active` par BA couverte (`id = business_app_id`) ; chaque non-admin = membre `viewer` ; membre le plus ancien (`added_at`) auto-promu `admin`
- [x] `super_admin`/ancien `admin` global ⇒ `platform_role='super_admin'` ; `data_architect`/`manager`/`viewer` ⇒ `user`
- [x] `lz_id` non résolvable vers une BA ⇒ listée au rapport + loggée, **sans** faire échouer la migration globale (P4)
- [x] Re-run `--apply` ⇒ 0 changement (idempotence — P6, SC-002)

## Tests

- `python our_catalogs_spn.py --migrate-projects` (dry-run) puis `--apply` ×2 sur dev — **restant à exécuter sur un vrai warehouse dev** (hors périmètre agent : pas d'accès réseau/warehouse ici)
- [x] pytest ciblé migration : mapping rôles, auto-promo admin, idempotence, LZ non résolue — `tests/test_our_catalogs_spn_migration.py` (8 tests, `python -m pytest tests/ -q` → 8 passed)

## Out of scope

- Provisioning Entra V1 / `entra_group_id` (reste NULL, point d'extension)
- Retrait de l'ancien `role` global (conservé lecture pour rollback)
- Routes API et UI (T002 / T003)

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside package scope
- [ ] Diff stays reviewable (prefer fewer changed files / one concern)
- [ ] Sub-spec checkboxes reviewed
- [ ] Jira Story lists **Git branch** name (not a commit SHA)

## Notes

Schéma détaillé et enums : [data-model.md](../data-model.md). Décisions D5 (migration 1:1 BA), D6 (`platform_role`) : [research.md](../research.md). Aucun secret en dur — SPN OAuth chargé via env (P7/P8). Contrat figé consommé par T002 : ne pas dévier du schéma sans mettre à jour data-model.md d'abord.
