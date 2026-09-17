# Migration — Étapes & champs perdus

> Étapes ordonnées pour remplacer le collecteur `DatabricksWorkflowCollector` par les
> system tables `system.lakeflow.*`, puis supprimer le collecteur. Chaque étape indique
> le(s) package(s) touché(s). Stratégie recommandée : **2 temps** (brancher la source
> system tables et valider, PUIS supprimer le collecteur) plutôt qu'un big bang.

---

## Partie A — Champs perdus / dégradés (le point d'attention n°1)

`system.lakeflow` ne porte pas tout ce que l'API REST Jobs 2.2 exposait. Impact sur le
contrat GOLD `gold_dbx_workflow_runs` / `gold_dbx_workflow_tasks` (drill-down UI) et sur
les agrégats.

### A.1 Champs PERDUS (deviennent `NULL`)

| Champ (curated/gold) | Grain | Raison | Conséquence UI / usage |
|---|---|---|---|
| `queued_duration_seconds` | run | Pas de décomposition de durée dans `job_run_timeline` (seul `period_start/end`) | Colonne « Attente » (part queue) vide |
| `setup_duration_seconds` | run | idem | — (n'était pas exposé en gold) |
| `execution_duration_seconds` | run | idem | Perte de la ventilation exec ; attribution FinOps par run dégradée |
| `cleanup_duration_seconds` | run | idem | — (n'était pas exposé en gold) |
| `schedule_lag_seconds` | run | `system.lakeflow.jobs` **ne contient pas le cron** du schedule → lag non calculable | Colonne « Attente » (part lag), filtre/tri lag inopérants |
| `workspace_name` | run/task | `lakeflow` expose `workspace_id`, pas le nom ARM | Colonnes affichent l'ID au lieu du nom (résolvable via mapping workspaces, cf. A.3) |

> Conforme à la règle DCM « **jamais de donnée fictive** » : un champ non disponible reste
> `NULL`, jamais rempli d'une valeur inventée.

### A.2 Champs DÉGRADÉS (dispo partiellement / autrement)

| Champ | Avant (collecteur) | Après (system tables) | Note |
|---|---|---|---|
| `error_message` | Message d'état complet (≤ 2000 car.) | `termination_code` + message court de `termination_details` | Diagnostic moins riche |
| `creator_user_name` | Nom du principal | `creator_id` (identifiant numérique) de `jobs` | Nom lisible = lookup identité (join `system.access` / SCIM) |
| `cluster_instance_id` | 1 cluster (`cluster_instance.cluster_id`) | `element_at(compute_ids, 1)` (tableau) | Ambigu si plusieurs computes par run/task |
| `run_page_url` | Fourni par l'API | **Reconstruit** : `https://{workspace_url}/jobs/{workflow_id}/runs/{run_id}` | Nécessite le mapping `workspace_id → workspace_url` |
| `retry_count` | `attempt_number` du run | Dérivé (comptage des lignes repair/attempt par `run_id`) | Sémantique équivalente, calcul différent |
| `trigger_type` | Enum collecteur (`_TRIGGER_MAP`) | `job_run_timeline.trigger_type` | Valeurs à re-mapper (cf. datamapping) |

### A.3 Champs CONSERVÉS (équivalent direct ou dérivable proprement)

`workflow_id`, `workflow_name`, `run_id`, `workspace_id`, `status`, `run_type`,
`start_time`, `end_time`, `duration_seconds`, `tasks_total`, `tasks_failed`,
`task_failure_rate`, `tags`, `task_id`, `task_key`, `attempt_number` (task).

> **Résolutions optionnelles** (si les tables sont activées / accessibles) :
> `workspace_name` et `run_page_url` peuvent être résolus via une table de mapping des
> workspaces (`system.access.workspaces_latest` selon activation, ou dimension DCM). À
> arbitrer ; par défaut `workspace_name = NULL`, `run_page_url` reconstruit sans le nom.

### A.4 Perte transverse : fraîcheur

- Les system tables ont une **latence de quelques heures** (vs quasi temps réel du collecteur).
- Les runs **en cours** (`running`) apparaissent avec retard ; `gold_dbx_workflow_concurrency_1min`
  et l'état « live » sont donc moins immédiats.

---

## Partie B — Étapes de migration

### Étape 0 — Prérequis (hors code)

- [ ] Activer le schéma `system.lakeflow` sur les metastores cibles (dev + prod), Azure **et** AWS.
- [ ] `GRANT SELECT ON SCHEMA system.lakeflow` au Service Principal d'ingestion (moindre privilège).
- [ ] Confirmer que le SQL Warehouse Azure cross-tenant expose bien `system.lakeflow.*`
      (même voie que `system.billing`/`system.access`, cf. spike delta-sharing).
- [ ] Décider : `workspace_name` / `run_page_url` résolus ou laissés NULL (cf. A.3).

### Étape 1 — CURATED : ajouter les 3 tables au socle `system_tables`

Package : `packages/dcm-databricks-pipeline`

- [ ] `pipelines/system_tables/specs.py` : déclarer 3 `IngestionSpec` fidèles
      (`curated_dbx_lakeflow_jobs`, `curated_dbx_lakeflow_job_run_timeline`,
      `curated_dbx_lakeflow_job_task_run_timeline`) + clés de merge + watermark
      (voir [datamodel_curated_gold.md](datamodel_curated_gold.md) §1).
- [ ] Ajouter les 3 clés au registre `SPECS` (et donc `SPEC_KEYS`).
- [ ] `resources/job_dcm_system_tables.yml` : ajouter les 3 clés à `for_each.inputs`
      (rester aligné sur `SPEC_KEYS`, sinon garde-fou entrypoint lève une erreur).
- [ ] Tests : `pipelines/system_tables` (registre + idempotence merge) — pattern existant.

### Étape 2 — GOLD : brancher les vues-pont + re-sourcer les agrégats

Package : `packages/dcm-databricks-pipeline` (`pipelines/dlt_03_gold_layer.py`)

- [ ] Créer 2 vues DLT de reshaping lisant les curated system tables via
      `spark.read.table("it.<schema>.curated_dbx_lakeflow_*")` :
  - `_wf_runs_bridge` → schéma identique à `curated_dbx_workflow_runs`
    (join `jobs` pour `workflow_name`/`creator`/`tags`, agrégats tasks depuis
    `job_task_run_timeline`, champs perdus = NULL).
  - `_wf_task_runs_bridge` → schéma identique à `curated_dbx_workflow_task_runs`.
- [ ] Remplacer dans les 8 fonctions gold :
      `dlt.read("curated_dbx_workflow_runs")` → `dlt.read("_wf_runs_bridge")` et
      `dlt.read("curated_dbx_workflow_task_runs")` → `dlt.read("_wf_task_runs_bridge")`.
- [ ] Aligner le schéma cible : la source system tables est écrite par le **job wheel**
      (schéma `system_tables`), le gold est DLT (schéma DLT). Vérifier que les deux visent
      le **même** `it.ba_data_connect_monitoring__{env}` (sinon FQN explicite dans la vue-pont).
- [ ] Tests DLT gold : adapter `test_dlt_workflow.py` (source = system tables reshaping).

### Étape 3 — Validation données (gate avant suppression)

- [ ] Exécuter le job `dcm_system_tables` en dev, vérifier le peuplement des 3 curated.
- [ ] Rafraîchir le pipeline DLT gold, comparer `gold_dbx_workflow_*` ancien vs nouveau
      (volumétrie runs/tasks, `success_rate`, `duration_percentiles`) sur une période commune.
- [ ] Confirmer avec le PO que les champs perdus (Partie A) sont acceptables pour T004.

### Étape 4 — RAW / CURATED : retirer le domaine `workflow` alimenté par le collecteur

Package : `packages/dcm-databricks-pipeline`

- [ ] `pipelines/dlt_01_raw_layer.py` : retirer `'workflow'` de `valid_domain`.
- [ ] `pipelines/dlt_02_curated_layer.py` : supprimer la section 9 (workflow runs) et la
      section tâche (`curated_dbx_workflow_runs` / `_task_runs` + vues `_stg_dbx_workflow*`
      + tables rejects).

> ⚠️ Les tables `curated_dbx_workflow_runs` / `_task_runs` sont désormais produites par
> les **vues-pont** (étape 2), plus par le collecteur. Bien vérifier qu'aucune consommation
> ne dépend de la version « raw » avant suppression.

### Étape 5 — Supprimer le collecteur (dcm-azure-collector)

Package : `packages/dcm-azure-collector`

- [ ] Supprimer `azure_collector/collectors/databricks_workflows.py`.
- [ ] `azure_collector/collectors/__init__.py` : retirer l'import + l'export `DatabricksWorkflowCollector`.
- [ ] `azure_collector/main.py` : retirer l'entrée `"databricks_workflows"` du registre + l'import.
- [ ] `azure_collector/config.py` : retirer `"databricks_workflows"` de la liste des collecteurs.
- [ ] `.github/azure-collector-deploy-targets.json` : retirer `databricks_workflows` de `enabled_collectors` (dev + prod).
- [ ] Supprimer `tests/test_databricks_workflows_collector.py`.

### Étape 6 — Supprimer le modèle (dcm-commons)

Package : `packages/dcm-commons`

- [ ] Supprimer `dcm_commons/models/workflow.py` (`WorkflowRunMetric`, `WorkflowTaskRun`).
- [ ] `dcm_commons/models/__init__.py` : retirer imports + exports `WorkflowRunMetric` / `WorkflowTaskRun`.
- [ ] Supprimer `tests/test_workflow.py`.
- [ ] `dcm_commons/models/enums.py` : conserver `MetricDomain.WORKFLOW`, `WorkflowRunStatus`,
      `WorkflowTriggerType` **uniquement** si le mapping status/trigger est réimplémenté côté
      pipeline (réutilisation des valeurs). Sinon retirer `MetricDomain.WORKFLOW`.

### Étape 7 — Backend / Frontend

Cf. [impact_back_front.md](impact_back_front.md). Principalement : gérer les colonnes
devenues NULL (queue/lag/exec, `workspace_name`, `error_message` réduit) dans l'UI et
les schémas de réponse API. **Aucune route ne disparaît** (contrat gold conservé).

### Étape 8 — Documentation & nettoyage

- [ ] Mettre à jour `Azure-Collector-End2End-Lineage.md` (retirer la chaîne collecteur `workflow`).
- [ ] Mettre à jour `specs/009-databricks-workflows-observability/` (note de migration).
- [ ] Décommissionner l'infra du collecteur (App Service / ACI) une fois le nouveau flux stable.

---

## Ordre de merge conseillé

1. PR 1 (additive, zéro risque) : Étape 1 (curated specs + job YAML).
2. PR 2 : Étape 2 (vues-pont + re-sourcing gold) + Étape 3 (validation).
3. PR 3 (destructive) : Étapes 4→6 (suppression raw/curated collecteur, collecteur, modèle).
4. PR 4 : Étape 7 (back/front) — peut être parallèle à PR 3 si les colonnes NULL sont gérées.
5. PR 5 : Étape 8 (doc + décommission infra).
