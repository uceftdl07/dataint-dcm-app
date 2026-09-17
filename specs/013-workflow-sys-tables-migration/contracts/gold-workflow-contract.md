# Contract — GOLD `gold_dbx_workflow_*` (conservé) + colonnes NULL

> **Règle de contrat** : la migration **ne casse rien**. Les 8 tables gold gardent leur nom, leur schéma
> DDL et leurs clés/FK. Les champs perdus restent **présents** au schéma mais valorisés `NULL`
> (jamais retirés → pas de rupture DDL/API, P14/P15). Les agrégats gold sont calculés sur les vues-pont.

## Tables & clés (inchangées)

| Table | Grain (clé primaire) | FK |
|---|---|---|
| `gold_dbx_workflow_success_rate` | jour × workflow | `dim_landing_zone(lz_id)` |
| `gold_dbx_workflow_duration_percentiles` | jour × workflow | idem |
| `gold_dbx_workflow_duration_drift` | jour × workflow | idem |
| `gold_dbx_workflow_task_failure_rate` | jour × workflow | idem |
| `gold_dbx_workflow_concurrency_1min` | minute × workspace | idem |
| `gold_dbx_workflow_task_health` | jour × workflow × task_key | idem |
| `gold_dbx_workflow_runs` | `pk(source_lz_id, workspace_id, workflow_id, run_id)` | `fk_gold_wf_runs_lz` |
| `gold_dbx_workflow_tasks` | task (run_id, task_id) | idem |

## Colonnes garanties non-NULL (cœur métier conservé)

`workflow_id`, `workflow_name`, `run_id`, `workspace_id`, `status`, `run_type`, `start_time`,
`end_time` (si run clôturé), `duration_seconds` (si clôturé), `tasks_total`, `tasks_failed`,
`task_failure_rate`, `tags`, `task_id`, `task_key`, `attempt_number` (task), `retry_count`,
`success_rate` / percentiles de durée / drift (agrégats).

## Colonnes conservées au schéma mais désormais NULL

| Colonne | Table(s) | Motif (spike A.1) |
|---|---|---|
| `queued_duration_seconds` | runs | pas de décomposition dans `job_run_timeline` |
| `setup_duration_seconds` | runs | idem (n'était pas exposé) |
| `execution_duration_seconds` | runs | idem |
| `cleanup_duration_seconds` | runs | idem (n'était pas exposé) |
| `schedule_lag_seconds` | runs | `jobs` sans cron |
| `workspace_name` | runs, tasks | `lakeflow` expose `workspace_id`, pas le nom ARM |
| `avg_queued_duration_seconds`, `avg_schedule_lag_seconds`, `max_schedule_lag_seconds` | duration_percentiles | dérivés des ci-dessus |

## Colonnes dégradées (valeur présente mais moins riche)

| Colonne | Nouvelle sémantique |
|---|---|
| `error_message` | `termination_code` + message court (plus le texte complet) |
| `creator_user_name` | `creator_id` (id numérique, exposé tel quel) |
| `cluster_instance_id` | `element_at(compute_ids, 1)` |
| `run_page_url` | reconstruit `https://{workspace_url}/jobs/{job_id}/runs/{run_id}` |
| `trigger_type` | re-mappé SQL depuis `job_run_timeline.trigger_type` |

## Invariants de test (gate Étape 3)

- Volumétrie runs/tasks ancien vs nouveau cohérente sur période commune (écart expliqué par latence).
- `success_rate`, `duration_percentiles` (hors queue/lag), `task_failure_rate` : valeurs alignées.
- Aucune colonne gold retirée ; toutes les colonnes NULL ci-dessus **existent** dans le DESCRIBE.
- 0 valeur inventée : les colonnes NULL sont bien NULL, pas 0 (P9).
