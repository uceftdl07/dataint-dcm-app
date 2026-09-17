# Tasks — Gouvernance des accès DCM (modèle projet, V2)

**Feature**: 015-project-access-governance | **Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)
**Mode**: one_per_domain (1 task = 1 domaine = 1 story = 1 branche fille) | **Base**: `develop`
**Merge order**: T001 → T002 → T003 ([merge-strategy.md](merge-strategy.md))

Contrats figés permettant le parallélisme : schéma 6 tables ([data-model.md](data-model.md)) figé par T001 ; OpenAPI ([contracts/projects-api.md](contracts/projects-api.md)) figé par T002.

## Tasks

- [x] T001 DataEng — Tables projet + `platform_role` + migration idempotente des accès plats — [DCINT-259](https://tdf.atlassian.net/browse/DCINT-259) → [stories/T001-dataeng-project-tables-migration.md](stories/T001-dataeng-project-tables-migration.md)
- [ ] T002 Backend — `get_allowed_scope`/`is_project_admin`, routes projet/join/scope, filtrage 2 dimensions, gardes admin + audit — [DCINT-260](https://tdf.atlassian.net/browse/DCINT-260) → [stories/T002-backend-project-authz-routes.md](stories/T002-backend-project-authz-routes.md)
- [ ] T003 Frontend — Écrans créer/rejoindre/administrer projet, état vide, matrice rôle — [DCINT-258](https://tdf.atlassian.net/browse/DCINT-258) → [stories/T003-frontend-project-self-service.md](stories/T003-frontend-project-self-service.md)

## Dependencies

```text
T001 (schéma + migration)  ──►  T002 (backend, contre schéma figé)  ──►  T003 (frontend, contre OpenAPI figé)
```

T002 démarrable en parallèle contre schéma + modèles figés (bouchons DB) ; T003 démarrable en parallèle contre OpenAPI + API mockée.
