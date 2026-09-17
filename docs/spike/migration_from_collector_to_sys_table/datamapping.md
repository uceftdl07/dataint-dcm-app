# Data Mapping — `system.lakeflow.*` → CURATED → GOLD

> Mapping colonne par colonne du domaine `workflow` après migration sur les system tables.
> Sens de lecture : **GOLD (contrat epic 009, inchangé)** ← reconstruit par la **vue-pont** ←
> **CURATED fidèle** ← `system.lakeflow.*`.
> Légende source : `J` = `jobs`, `R` = `job_run_timeline`, `T` = `job_task_run_timeline`.
> Légende statut : ✅ direct · 🔀 dérivé/calculé · ⚠️ dégradé · ❌ perdu (NULL).

---

## 0. Reshaping préalable : N lignes timeline → 1 ligne par run

> **⚠️ Critique — à appliquer AVANT tout mapping colonne.** `job_run_timeline` (R) et
> `job_task_run_timeline` (T) contiennent **plusieurs lignes par run/tâche** : une ligne par
> transition d'état (`period_start_time` / `period_end_time` bornent chaque *période* d'état, pas
> le run entier). Garder « la dernière ligne » via un simple `qualify row_number()` donnerait un
> `start_time` **faux** (début de la dernière période, pas du run). Il faut **agréger**, pas
> dédupliquer.

**Grain de sortie** : 1 ligne par `(cloud_provider, source_lz_id, workspace_id, job_id, run_id)`
(et `+ task_run_id` pour les tâches).

**Agrégation R → 1 ligne / run** (CTE `runs_agg`) :

```sql
WITH runs_agg AS (
  SELECT
    workspace_id, job_id, run_id,
    min(period_start_time)                              AS start_time,
    -- end = fin de la dernière période SI le run est terminé, sinon NULL (en cours)
    CASE WHEN bool_and(period_end_time IS NOT NULL)
         THEN max(period_end_time) END                 AS end_time,
    -- état final = result_state de la période la plus récente (par period_start_time)
    max_by(result_state,   period_start_time)          AS final_result_state,
    max_by(termination_code, period_start_time)        AS final_termination_code,
    max_by(trigger_type,   period_start_time)          AS trigger_type,
    max_by(run_type,       period_start_time)          AS run_type,
    max_by(compute_ids,    period_start_time)          AS compute_ids
  FROM system.lakeflow.job_run_timeline
  GROUP BY workspace_id, job_id, run_id
)
```

- `start_time` = `min(period_start_time)` sur **toutes** les périodes du run (vrai début).
- `end_time` = `max(period_end_time)` **uniquement si** toutes les périodes sont clôturées
  (`bool_and(period_end_time IS NOT NULL)`), sinon `NULL` → run en cours.
- L'état final (`result_state`, `termination_code`) et les attributs quasi-constants
  (`trigger_type`, `run_type`, `compute_ids`) sont pris sur la **période la plus récente** via
  `max_by(col, period_start_time)`.
- `duration_seconds` se calcule ensuite sur `start_time`/`end_time` **agrégés**, pas ligne à ligne.

**Agrégation T → 1 ligne / tâche** (CTE `tasks_agg`) : même principe, groupé par
`(workspace_id, job_id, run_id, task_run_id, task_key)`. `attempt_number` se dérive après
agrégation (cf. §2), pas par dédup de lignes de transition.

> Dans les cellules « Source = R / T » ci-dessous, lire **`runs_agg` / `tasks_agg`** (post-§0), pas
> les tables timeline brutes.

---

## 1. Mapping RUN — `_wf_runs_bridge` (= schéma `curated_dbx_workflow_runs`)

| Colonne cible (gold/curated) | Statut | Source | Règle |
|---|---|---|---|
| `source_lz_id` | ✅ | R | Dérivé du contexte d'ingestion / `workspace_id` → LZ (mapping DCM) |
| `cloud_provider` | ✅ | R | Colonne d'enveloppe socle |
| `workspace_id` | ✅ | R.`workspace_id` | direct |
| `workspace_name` | ❌ | — | `NULL` (lakeflow n'expose pas le nom ; option: mapping workspaces) |
| `workflow_id` | ✅ | R.`job_id` | direct |
| `workflow_name` | ✅ | J.`name` | join `jobs` sur `job_id` (dernière version ≤ run, `delete_time IS NULL`) |
| `run_id` | ✅ | R.`run_id` | direct |
| `status` | 🔀 | R (agg §0) | CASE mapping (cf. §3) sur `final_result_state` / `end_time` ; `running` si `final_result_state IS NULL` et `end_time IS NULL` |
| `trigger_type` | 🔀 | R (agg §0) | re-mapping enum (cf. §4) sur `trigger_type` de la période récente |
| `start_time` | 🔀 | R (agg §0) | `min(period_start_time)` sur toutes les périodes du run (§0) — **pas** la dernière ligne |
| `end_time` | 🔀 | R (agg §0) | `max(period_end_time)` si run clôturé, sinon `NULL` (§0) |
| `duration_seconds` | 🔀 | R (agg §0) | `unix_timestamp(end_time) - unix_timestamp(start_time)` sur les valeurs **agrégées** |
| `queued_duration_seconds` | ❌ | — | `NULL` (pas de décomposition) |
| `setup_duration_seconds` | ❌ | — | `NULL` |
| `execution_duration_seconds` | ❌ | — | `NULL` |
| `cleanup_duration_seconds` | ❌ | — | `NULL` |
| `schedule_lag_seconds` | ❌ | — | `NULL` (pas de cron dans `jobs`) |
| `retry_count` | 🔀 | R/T | Nb de tentatives par `run_id` − 1 (comptage lignes repair/attempt), 0 sinon |
| `tasks_total` | 🔀 | T | `count(distinct task_key)` par `run_id` |
| `tasks_failed` | 🔀 | T | `count(distinct task_key)` où `result_state` ∈ échec, par `run_id` |
| `task_failure_rate` | 🔀 | T | `tasks_failed / nullif(tasks_total,0)` |
| `cluster_instance_id` | ⚠️ | R (agg §0) | `element_at(compute_ids, 1)` sur `compute_ids` de la période récente (ambigu si multi-compute) |
| `creator_user_name` | ⚠️ | J.`creator_id` | id numérique (nom = lookup identité optionnel) |
| `run_page_url` | 🔀 | R | `concat('https://', <workspace_url>, '/jobs/', job_id, '/runs/', run_id)` |
| `run_type` | ✅ | R.`run_type` | direct |
| `error_message` | ⚠️ | R (agg §0) | `final_termination_code` + message court (plus le texte complet) |
| `tags` | ✅ | J.`tags` | join `jobs` |

---

## 2. Mapping TASK — `_wf_task_runs_bridge` (= schéma `curated_dbx_workflow_task_runs`)

| Colonne cible | Statut | Source | Règle |
|---|---|---|---|
| `source_lz_id` | ✅ | T | contexte d'ingestion |
| `cloud_provider` | ✅ | T | enveloppe socle |
| `workspace_id` | ✅ | T.`workspace_id` | direct |
| `workspace_name` | ❌ | — | `NULL` |
| `workflow_id` | ✅ | T.`job_id` | direct |
| `workflow_name` | ✅ | J.`name` | join `jobs` |
| `run_id` | ✅ | T.`run_id` | direct |
| `task_id` | ✅ | T.`task_run_id` | direct (id unique de l'exécution de tâche) |
| `task_key` | ✅ | T.`task_key` | direct |
| `status` | 🔀 | T (agg §0) | CASE mapping (§3) sur `final_result_state` |
| `start_time` | 🔀 | T (agg §0) | `min(period_start_time)` sur toutes les périodes de la tâche — **pas** la dernière ligne |
| `end_time` | 🔀 | T (agg §0) | `max(period_end_time)` si tâche clôturée, sinon `NULL` |
| `duration_seconds` | 🔀 | T (agg §0) | `unix_timestamp(end_time) - unix_timestamp(start_time)` sur les valeurs **agrégées** |
| `attempt_number` | 🔀 | T (agg §0) | `row_number()` sur `(run_id, task_key)` ordonné par `start_time` agrégé, après reshaping (1 ligne / `task_run_id`) |
| `cluster_instance_id` | ⚠️ | T (agg §0) | `element_at(compute_ids, 1)` sur la période récente |
| `error_message` | ⚠️ | T (agg §0) | `final_termination_code` + message court |

---

## 3. Mapping statut : `result_state` → enum DCM `status`

Réutiliser la sémantique des maps du collecteur (`_RESULT_STATE_MAP`), appliquée en SQL.

| `result_state` (lakeflow) | `termination_code` | `status` DCM |
|---|---|---|
| `SUCCEEDED` | — | `succeeded` |
| `FAILED` | — | `failed` |
| `CANCELLED` / `CANCELED` | — | `cancelled` |
| `TIMED_OUT` | — | `timed_out` |
| `SKIPPED` | — | `skipped` |
| `EXCLUDED` / `UPSTREAM_FAILED` / `UPSTREAM_CANCELED` | — | `skipped` |
| `NULL` (période en cours) | `NULL` | `running` |
| `NULL` (en file) | code d'attente | `queued` |

```sql
CASE
  WHEN result_state = 'SUCCEEDED'                          THEN 'succeeded'
  WHEN result_state = 'FAILED'                             THEN 'failed'
  WHEN result_state IN ('CANCELLED','CANCELED')            THEN 'cancelled'
  WHEN result_state = 'TIMED_OUT'                          THEN 'timed_out'
  WHEN result_state IN ('SKIPPED','EXCLUDED',
                        'UPSTREAM_FAILED','UPSTREAM_CANCELED') THEN 'skipped'
  WHEN result_state IS NULL AND period_end_time IS NULL    THEN 'running'
  ELSE 'queued'
END AS status
```

> Les valeurs exactes de `result_state` sont à confirmer sur les données réelles (Étape 3
> validation). Ajuster la CASE si de nouveaux codes apparaissent — sans jamais inventer d'état.

---

## 4. Mapping `trigger_type`

| `trigger_type` (lakeflow) | `trigger_type` DCM |
|---|---|
| `PERIODIC` / `SCHEDULED` | `scheduled` |
| `ONE_TIME` / `MANUAL` | `manual` |
| `RETRY` | `retry` |
| `RUN_JOB_TASK` | `run_job_task` |
| `FILE_ARRIVAL` | `file_arrival` |
| `CONTINUOUS` | `continuous` |
| `TABLE` / `TABLE_UPDATE` | `table_update` |
| autre / NULL | `unknown` |

> À confirmer sur données réelles (Étape 3). Aligner sur `WorkflowTriggerType` si l'enum est conservé.

---

## 5. Contrôles Data Quality

Appliqués dans les vues-pont / gold (expectations DLT si en pipeline DLT).

| Contrôle | Règle | Action |
|---|---|---|
| Clé run non nulle | `workflow_id`, `run_id`, `source_lz_id` NOT NULL | drop / quarantaine |
| Cohérence temporelle | `end_time >= start_time` (si `end_time` non NULL) | warn |
| Durée positive | `duration_seconds >= 0` | warn |
| Taux ∈ [0,1] | `task_failure_rate` BETWEEN 0 AND 1 | warn |
| Statut connu | `status` ∈ enum DCM | warn (log valeurs inconnues) |
| Grain run | 1 ligne par `(cloud_provider, workflow_id, run_id, source_lz_id)` **via agrégation `GROUP BY` (§0)**, pas `qualify row_number()` sur la timeline (fausserait `start_time`) | garanti par le `GROUP BY` |
| Grain task | 1 ligne par `(cloud_provider, workflow_id, run_id, task_id, source_lz_id)` **via agrégation `GROUP BY` (§0)** | garanti par le `GROUP BY` |
| Filet dédup post-agg | si doublon résiduel après `GROUP BY`, `qualify row_number() over (partition by <clé grain> order by end_time desc nulls last, start_time desc)` | dédup de secours |

---

## 6. Traçabilité vers l'ancien contrat

| Ancien producteur (à supprimer) | Nouveau producteur |
|---|---|
| `WorkflowRunMetric` (dcm-commons) | `_wf_runs_bridge` (dlt_03) |
| `WorkflowTaskRun` (dcm-commons) | `_wf_task_runs_bridge` (dlt_03) |
| `DatabricksWorkflowCollector` → raw domaine `workflow` → `curated_dbx_workflow_runs` (dlt_02 §9) | `system.lakeflow.*` → `curated_dbx_lakeflow_*` (job wheel) → vues-pont |
| `_RESULT_STATE_MAP` / `_TERMINATION_CODE_MAP` / `_TRIGGER_MAP` (collecteur Python) | CASE SQL §3 / §4 (vue-pont) |
