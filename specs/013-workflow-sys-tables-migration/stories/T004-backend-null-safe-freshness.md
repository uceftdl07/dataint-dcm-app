# T004 — Backend NULL-tolérance `workflow` + `as_of`

**Domain**: backend
**Package**: packages/dcm-backend
**Branch**: backend/013-backend-null-safe-freshness
**Jira**: [DCINT-239](https://tdf.atlassian.net/browse/DCINT-239)
**Depends on**: T002
**Work type**: technique

## Description

Rendre le backend Lakeflow tolérant aux colonnes devenues NULL (queue/lag/exec, `workspace_name`, `error_message` réduit, `creator_user_name`=`creator_id`), exposer un champ **`as_of`** réel (= `max(_ingested_at)` des curated lakeflow) dans les réponses overview + jobs, et ajuster la résolution `/workspaces` (repli tags/id quand `workspace_name` NULL). **Aucune route supprimée, aucun champ retiré** (P15) — évolutions additives/non-cassantes.

## Files to create/modify

- UPDATE packages/dcm-backend/app/api/services/lakeflow_jobs.py — tolérance NULL (SELECT restent valides ; modèles Pydantic `... | None`)
- UPDATE packages/dcm-backend/app/api/services/lakeflow_overview.py — calcul + exposition `as_of` (`max(_ingested_at)`) ; percentiles queue/lag → `null`
- UPDATE packages/dcm-backend/app/api/routes/databricks.py — `/workspaces` : ordre gold/curated (NULL) → tags compute (`dcm_workspace_name`/`Project`, `dbw-%`) → `workspace_id`
- UPDATE packages/dcm-backend/tests/ (test_lakeflow_overview.py, tests jobs, test_databricks_workspaces.py) — fixtures `workspace_name=NULL`, champs NULL, `as_of` présent

## Acceptance Criteria

- [ ] Tous les champs devenus NULL sont typés `... | None` dans les modèles de réponse (`queued_duration_seconds`, `execution_duration_seconds`, `schedule_lag_seconds`, `workspace_name`, `avg_queued_duration_seconds`, `avg_schedule_lag_seconds`, `max_schedule_lag_seconds`).
- [ ] Champ `as_of` (ISO 8601) présent dans les réponses overview + jobs, valeur = **vrai** `max(_ingested_at)`, jamais une constante ([contracts/api-freshness-contract.md](../contracts/api-freshness-contract.md)).
- [ ] `/workspaces` : `workspace_name` NULL en gold/curated ⇒ repli tags puis `workspace_id` (jamais un nom inventé) ; test couvre la bascule.
- [ ] Aucune route retirée, aucun champ retiré des réponses ; anciens clients désérialisent toujours.
- [ ] Sérialisation des réponses avec champs NULL sans erreur.
- [ ] ruff + mypy zéro warning ; pytest vert.

## Tests

- `pytest packages/dcm-backend/tests -q` (test_lakeflow_*, test_databricks_workspaces)

## Out of scope

- Reshaping/gold (T002).
- UI (T005).

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass (fixtures NULL + `as_of`)
- [ ] No files outside `packages/dcm-backend`
- [ ] Diff reviewable
- [ ] Sub-spec checkboxes reviewed
- [ ] Jira Story lists **Git branch** name

## Notes

- Parallélisable avec T003 (fichiers disjoints), dépend logiquement du gold re-sourcé (T002) pour `_ingested_at`/colonnes NULL.
- Réf. : [impact_back_front.md §1](../../../docs/spike/migration_from_collector_to_sys_table/impact_back_front.md).
