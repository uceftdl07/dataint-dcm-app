# Specification Quality Checklist — `dim_dbx_workspace`

Validation standard speckit de la spec `specs/020-dbx-workspace-dim/spec.md`.

## Content Quality

- [x] Le besoin métier est décrit (dimension consolidée des workspaces actifs) sans imposer d'implémentation prématurée.
- [x] Les user stories sont testables indépendamment (Independent Test fourni).
- [x] Les critères de succès sont mesurables (SC-001..SC-003, requêtes SQL vérifiables).
- [x] Le périmètre est borné (Out of scope explicite : pas d'exposition backend/frontend, pas de SCD).

## Requirements Completeness

- [x] Chaque FR correspond à une capacité observable (ingestion curated, vue, colonnes, unicité).
- [x] Le contrat de données est nommé (`curated_dbx_access_workspaces_latest`, `dim_dbx_workspace`, colonnes `workspace_id`/`workspace_name`/`subscription_or_account_id`/`cloud`/`updated_at`).
- [x] Les dépendances externes sont identifiées (`dim_reference_landing_zone_dbx_workspace`, feature 014 ; socle `pipelines/system_tables/`).
- [x] `[NEEDS CLARIFICATION]` résolus (session 2026-09-02) : vue via module dédié `pipelines/gold_dbx_workspace/` + task, `merge_keys=(cloud_provider, workspace_id)`, `updated_at=current_timestamp()`.

## Scope & Traceability

- [x] Domain Scope aligné avec `intake.json` (DataEng-only, 1 ticket).
- [x] Work Breakdown = 1 task (T001) cohérent avec `expected_story_count`.
- [x] Aucun domaine in-scope sans ticket (pas de gap reporté).
