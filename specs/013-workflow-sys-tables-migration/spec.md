# Feature Specification: Migration source domaine `workflow` — collecteur → system tables `system.lakeflow`

**Feature Branch**: `spec/migrate_dcm_workflow_from_collector_to_sys_table`
**Work Type**: technique
**Priority**: P1
**Created**: 2026-08-17

**Input**: Effectuer une migration des data sources des interfaces `workflow` (observabilité des Jobs/Workflows Databricks, epic 009) depuis le collecteur `DatabricksWorkflowCollector` vers les system tables Unity Catalog `system.lakeflow.*`, puis supprimer totalement le collecteur. Basé sur le spike `docs/spike/migration_from_collector_to_sys_table/`.

## Clarifications

### Session 2026-08-17

- Q: Périmètre cloud de la migration ? → A: Multi-cloud (Azure + AWS), aligné sur les 7 system tables déjà ingérées par le socle `system_tables` ; `cloud_provider` fait partie de la clé de merge.
- Q: Résolution de `workspace_name` et `run_page_url` (non exposés par `system.lakeflow`) ? → A: résolution via `system.access.workspaces_latest.workspace_url` ; `run_page_url` reconstruit au format Databricks (`{workspace_url}/?o={workspace_id}#job/{job_id}/run/{run_id}`). Aucune donnée inventée (règle DCM).
- Q: Résolution du nom lisible de `creator_user_name` ? → A: Exposer `creator_id` (identifiant numérique) tel quel, sans lookup identité SCIM dans cet Epic.
- Q: Stratégie de bascule ? → A: En 2 temps — d'abord brancher la nouvelle source (system tables → curated → vues-pont → gold) et valider par comparaison de données, PUIS supprimer le collecteur, le domaine raw `workflow` et le modèle. Pas de big bang.
- Q: Que deviennent les champs non portés par `system.lakeflow` (queue/lag/exec/setup/cleanup durations, `workspace_name`, `error_message` complet) ? → A: Ils deviennent `NULL` ou dégradés dans le contrat GOLD **conservé** ; les colonnes restent présentes au schéma (pas de rupture API), l'UI affiche « n/d » et non `0`.
- Q: Profondeur du backfill initial des tables curated lakeflow ? → A: 30 jours, aligné sur la convention de la feature 012 ; puis rafraîchissement quotidien incrémental.
- Q: Comment éviter le conflit de producteur pendant la bascule 2-temps ? → A: Les vues-pont portent un nom distinct (`_wf_runs_bridge` / `_wf_task_runs_bridge`) et le gold est comparé ancien/nouveau en parallèle ; le collecteur et ses tables `curated_dbx_workflow_*` restent intacts jusqu'au gate.
- Q: Colonne « Attente » (queue \| lag) devenue NULL côté frontend ? → A: Masquée par défaut (retirée du tableau/sélecteur), pas d'affichage « n/d » permanent sur 100% des lignes.
- Q: Rétention des enums `MetricDomain.WORKFLOW` / `WorkflowRunStatus` / `WorkflowTriggerType` dans `dcm-commons` ? → A: Supprimés — le mapping statut/trigger vit désormais 100% en SQL (vues-pont) ; aucun consommateur Python restant.
- Q: Mécanisme d'exposition de la fraîcheur system tables ? → A: Champ `as_of` (timestamp réel, dernier `_ingested_at`) dans la réponse API ; le bandeau frontend calcule le décalage « données à ~X h ».

## Domain Scope

| Domaine | In scope | Ticket Story | Packages |
|---------|----------|--------------|----------|
| Frontend | ✅ | ✅ | packages/dcm-frontend |
| Backend | ✅ | ✅ | packages/dcm-backend, packages/dcm-commons |
| DataEng | ✅ | ✅ | packages/dcm-databricks-pipeline, packages/dcm-azure-collector, packages/dcm-commons |
| DevOps | ⚠️ | ❌ | décommission infra collecteur (App Service/ACI) — hors dispatch, suivi séparé |
| QA | ➖ | ❌ | tests inclus dans chaque ticket domaine |

## Ticket Plan

| Champ | Valeur |
|-------|--------|
| Stories Jira | 5 (estimation — arbitrée en phase tasks) |
| Mode | custom (tickets par domaine, DataEng subdivisé par étape de bascule) |
| Domaines avec ticket | DataEng, Backend, Frontend |

| # | Slug | Domaine | Titre |
|---|------|---------|-------|
| 1 | `curated-lakeflow-system-tables` | DataEng | Ajouter les 3 tables `curated_dbx_lakeflow_*` au socle `system_tables` |
| 2 | `bridge-views-regold-workflow` | DataEng | Vues-pont DLT + re-sourcing des 8 tables gold `gold_dbx_workflow_*` (contrat inchangé) |
| 3 | `teardown-workflow-collector` | DataEng | Supprimer le domaine raw/curated `workflow`, le collecteur `DatabricksWorkflowCollector` et le modèle `WorkflowRunMetric` |
| 4 | `backend-null-tolerance-workflow` | Backend | Tolérance aux colonnes NULL + résolution `workspace_name`/`creator` dégradée |
| 5 | `frontend-null-safe-freshness` | Frontend | Colonnes NULL-safe, retrait tooltip cron, bandeau fraîcheur system tables |

## Dependency Analysis

| Vérification | Résultat | Preuve |
|--------------|----------|--------|
| Collecteur source `workflow` existe | ✅ trouvé | `packages/dcm-azure-collector/azure_collector/collectors/databricks_workflows.py` (`DatabricksWorkflowCollector`) |
| Socle `system_tables` (registre `SPECS`/`SPEC_KEYS`) réutilisable | ✅ trouvé | `packages/dcm-databricks-pipeline/pipelines/system_tables/specs.py` |
| Couche gold DLT branchable sur vues-pont | ✅ trouvé | `packages/dcm-databricks-pipeline/pipelines/dlt_03_gold_layer.py` |
| Domaine raw/curated `workflow` à retirer | ✅ trouvé | `dlt_02_curated_layer.py` (§9 workflow), `dlt_01_raw_layer.py` (`valid_domain`) |
| Modèle à supprimer (dcm-commons) | ✅ trouvé | `packages/dcm-commons/dcm_commons/models/workflow.py` (`WorkflowRunMetric`, `WorkflowTaskRun`) |
| Services backend consommateurs | ✅ trouvé | `packages/dcm-backend/app/api/services/lakeflow_jobs.py`, `lakeflow_overview.py`, `routes/databricks.py` (`/workspaces`) |
| Interface frontend consommatrice | ✅ trouvé | page `/Lakeflow/Jobs` (story T004, epic 011) |
| Gap bloquant | ❌ aucun | Le contrat GOLD reste identique ; aucune route ni schéma de réponse supprimé |

**Conclusion (dérivée du tableau)** : migration additive puis destructive, sans nouvelle API ni rupture de contrat. Le seul travail applicatif est la **tolérance au NULL** et l'ajustement de la résolution du nom de workspace.

## User Scenarios & Testing

### User Story 1 - Tables curated `system.lakeflow` disponibles (Priority: P1)

En tant qu'ingénieur data / pipeline DCM, je veux que les system tables `system.lakeflow.jobs`, `system.lakeflow.job_run_timeline` et `system.lakeflow.job_task_run_timeline` soient collectées et matérialisées dans des tables curated fidèles et idempotentes (`curated_dbx_lakeflow_jobs`, `curated_dbx_lakeflow_job_run_timeline`, `curated_dbx_lakeflow_job_task_run_timeline`), alignées sur les 7 tables déjà ingérées par le socle `system_tables`, afin que les vues-pont et la couche gold puissent s'appuyer sur une base gouvernée et multi-cloud.

**Why this priority**: C'est le socle bloquant. Sans ces 3 tables curated, ni les vues-pont ni la couche gold ne peuvent être re-sourcées, et le collecteur ne peut pas être retiré. Étape additive, sans risque sur l'existant.

**Independent Test**: Exécuter le job `dcm_system_tables` sur un environnement de test (Azure natif + Azure JDBC cross-tenant + AWS natif) ; vérifier que les 3 nouvelles tables curated existent, contiennent des lignes cohérentes avec les sources `system.lakeflow.*`, et que des runs successifs (MERGE idempotent sur la clé documentée + watermark) ne dupliquent ni ne perdent de lignes.

**Acceptance Scenarios**:

1. **Given** des définitions de jobs existent dans `system.lakeflow.jobs`, **When** le job d'ingestion s'exécute, **Then** `curated_dbx_lakeflow_jobs` contient une ligne par `(cloud_provider, account_id, workspace_id, job_id, change_time)` avec `delete_time` NULL pour les jobs actifs.
2. **Given** des runs terminés et en cours existent dans `system.lakeflow.job_run_timeline`, **When** le job d'ingestion s'exécute puis est rejoué, **Then** `curated_dbx_lakeflow_job_run_timeline` conserve toutes les périodes d'état par run sans duplication (clé incluant `period_start_time`, watermark `period_start_time`).
3. **Given** les 3 clés lakeflow sont déclarées dans le registre `SPECS`, **When** l'entrypoint du job démarre, **Then** les clés de `for_each.inputs` du job YAML sont alignées sur `SPEC_KEYS` (garde-fou entrypoint ne lève pas d'erreur).

---

### User Story 2 - Contrat GOLD `gold_dbx_workflow_*` re-sourcé sans rupture (Priority: P1)

En tant que consommateur des interfaces d'observabilité workflow (backend/frontend), je veux que les 8 tables gold `gold_dbx_workflow_*` continuent d'exister avec le même schéma et les mêmes noms, alimentées désormais par des vues-pont DLT (`_wf_runs_bridge`, `_wf_task_runs_bridge`) reconstruites depuis les curated system tables, afin que les routes API et l'UI ne subissent aucune rupture de contrat — seules les colonnes dérivées de champs non portés par `system.lakeflow` deviennent `NULL`.

**Why this priority**: C'est le cœur de la migration : garantir la continuité du contrat gold pendant la bascule. Dépend directement de la Story 1 (curated disponibles) et conditionne le gate de validation avant toute suppression.

**Independent Test**: Rafraîchir le pipeline DLT gold branché sur les vues-pont ; comparer `gold_dbx_workflow_*` ancien (collecteur) vs nouveau (system tables) sur une période commune — volumétrie runs/tasks, `success_rate`, `duration_percentiles` — et vérifier que le schéma (colonnes/types) des 8 tables est strictement identique, les champs perdus étant `NULL`.

**Acceptance Scenarios**:

1. **Given** plusieurs périodes d'état existent par run dans `job_run_timeline`, **When** la vue-pont `_wf_runs_bridge` agrège les runs, **Then** chaque run produit exactement 1 ligne au grain `(cloud_provider, workflow_id, run_id, source_lz_id)` avec `start_time = min(period_start_time)` et `end_time = max(period_end_time)` (NULL si run en cours), **et non** la dernière ligne timeline.
2. **Given** un run terminé avec `result_state = 'FAILED'`, **When** la vue-pont mappe le statut, **Then** `status = 'failed'` selon la table de mapping documentée, et `error_message = termination_code` (+ message court), sans texte complet inventé.
3. **Given** le schéma gold epic 009, **When** les 8 fonctions gold lisent `_wf_runs_bridge`/`_wf_task_runs_bridge` au lieu des curated collecteur, **Then** les colonnes non disponibles (`queued_duration_seconds`, `execution_duration_seconds`, `setup_duration_seconds`, `cleanup_duration_seconds`, `schedule_lag_seconds`, `workspace_name`) sont présentes au schéma et valent `NULL`, jamais `0` ni une valeur fictive.

---

### User Story 3 - Suppression du collecteur et du domaine `workflow` collecteur (Priority: P1)

En tant que responsable de la plateforme DCM, je veux que le collecteur `DatabricksWorkflowCollector`, le domaine raw/curated `workflow` alimenté par ce collecteur et le modèle `WorkflowRunMetric`/`WorkflowTaskRun` soient supprimés une fois la nouvelle source validée, afin de réduire le compute, les secrets et la dette, sans laisser de chemin d'ingestion mort ni de consommation orpheline.

**Why this priority**: Objectif final de la migration (moins de compute/secrets). P1 car c'est la raison d'être de l'Epic, mais **strictement conditionnée** par la validation des Stories 1 et 2 (gate données). Étape destructive à exécuter en dernier.

**Independent Test**: Après validation du gate (Story 2), retirer le domaine `workflow` de la couche raw/curated, supprimer le collecteur + ses tests + son enregistrement (registre, config, cibles de déploiement) et le modèle commons ; exécuter la suite de tests complète (pipeline, collecteur, commons) et vérifier qu'aucune référence morte ne subsiste et que les tables gold restent alimentées par les vues-pont.

**Acceptance Scenarios**:

1. **Given** les vues-pont alimentent désormais `curated_dbx_workflow_runs`/`_task_runs`, **When** la section workflow (§9) de `dlt_02_curated_layer.py` et `'workflow'` de `valid_domain` (`dlt_01_raw_layer.py`) sont retirés, **Then** aucune consommation ne dépend plus de la version « raw » et le pipeline gold reste vert.
2. **Given** le collecteur `DatabricksWorkflowCollector`, **When** son fichier, ses imports/exports (`collectors/__init__.py`, `main.py`, `config.py`), sa cible de déploiement (`.github/azure-collector-deploy-targets.json`) et son test sont supprimés, **Then** le collecteur Azure démarre sans l'entrée `databricks_workflows` et la CI reste verte (ruff/tests).
3. **Given** le modèle `WorkflowRunMetric`/`WorkflowTaskRun` (`dcm-commons`), **When** il est supprimé avec ses exports et son test, **Then** aucune import résiduelle ne subsiste ; les enums `MetricDomain.WORKFLOW`, `WorkflowRunStatus` et `WorkflowTriggerType` sont également supprimés (mapping statut/trigger 100% SQL côté vues-pont, aucun consommateur Python restant).

---

### User Story 4 - Backend tolérant aux champs NULL et fraîcheur system tables (Priority: P2)

En tant que consommateur des routes API Lakeflow (Jobs N1/N2/N3, Overview), je veux que les services backend tolèrent les colonnes devenues `NULL` (queue/lag/exec, `workspace_name`, `error_message` réduit) et adaptent la résolution du nom de workspace (repli tags/`workspace_id`), afin qu'aucune route ne casse et que la latence des system tables soit reflétée honnêtement.

**Why this priority**: Nécessaire pour que l'API reste correcte après bascule, mais non bloquant pour le pipeline. P2 car le contrat de réponse est déjà largement `... | None` ; le travail est d'ajustement et de tests, parallélisable avec le frontend.

**Independent Test**: Sur un jeu de données gold issu des vues-pont (avec champs NULL), interroger les routes Jobs et Overview et `/workspaces` ; vérifier que les réponses sont valides (aucune 500), que `workspace_name` retombe sur le repli tags/`workspace_id`, et que les tests backend concernés passent avec fixtures `workspace_name = NULL` en gold/curated.

**Acceptance Scenarios**:

1. **Given** des lignes gold avec `queued_duration_seconds`/`schedule_lag_seconds`/`execution_duration_seconds` NULL, **When** un client appelle les routes Jobs/Overview, **Then** la réponse est valide (200) et les champs correspondants sont `null` dans le schéma Pydantic (`... | None`), sans erreur de sérialisation.
2. **Given** `workspace_name` NULL en gold et curated, **When** la route `/workspaces` résout le nom, **Then** elle bascule sur le repli tags compute (`dcm_workspace_name`/`Project`, `dbw-%`) puis sur `workspace_id`, et ne renvoie jamais une valeur inventée.
3. **Given** la latence des system tables, **When** un endpoint Lakeflow répond, **Then** il expose un champ `as_of` (timestamp réel dérivé du dernier `_ingested_at`), sans prétendre à du quasi temps réel.

---

### User Story 5 - Frontend NULL-safe et indicateur de fraîcheur (Priority: P2)

En tant qu'utilisateur de la page `/Lakeflow/Jobs` (N1/N2/N3), je veux que les colonnes dont la donnée n'existe plus affichent « n/d » (jamais `0`), que le tooltip cron du Trigger soit retiré et qu'un bandeau signale la latence des données, afin d'avoir une information honnête et non trompeuse après la migration.

**Why this priority**: Complète la cohérence UX de la migration. P2, parallélisable avec le backend ; aucune route ni navigation retirée.

**Independent Test**: Avec des fixtures mockées reproduisant les champs NULL (queue/lag/exec, `workspace_name`, `error_message` réduit), rendre la page `/Lakeflow/Jobs` et ses drill-downs ; vérifier l'affichage « n/d » (pas `0`), l'absence de tooltip cron, le fallback `workspace_id`, l'affichage du code de terminaison, et la présence du bandeau de fraîcheur.

**Acceptance Scenarios**:

1. **Given** `avg_queued_duration_seconds`/`avg_schedule_lag_seconds` intégralement NULL, **When** la page se rend, **Then** la colonne « Attente » est **masquée par défaut** (retirée du tableau/sélecteur) et n'affiche **jamais** `0` (fausse information).
2. **Given** `workspace_name` NULL et `creator_user_name` = `creator_id`, **When** les colonnes Workspace/Propriétaire se rendent, **Then** elles affichent respectivement le `workspace_id` en repli et l'identifiant `creator_id` (ou masqué), sans nom inventé.
3. **Given** la latence des system tables (champ `as_of` en réponse API), **When** la page se charge, **Then** un bandeau « données à ~X h » calculé depuis `as_of` est visible, particulièrement pertinent pour les runs `running` affichés avec retard ; le drill N3 n'affiche que `duration_seconds` total (ventilation queue/exec retirée) et le code de terminaison en guise de message d'erreur.

### Edge Cases

- **Run multi-période sans clôture** : toutes les périodes n'ont pas de `period_end_time` → `end_time = NULL`, `status = 'running'` (jamais une durée calculée sur une période partielle).
- **Multi-compute par run/task** : `compute_ids` contient plusieurs éléments → `cluster_instance_id = element_at(compute_ids, 1)` (ambigu, documenté), pas d'échec.
- **`result_state` inconnu** : une valeur non mappée est loggée et traitée comme telle sans inventer d'état ; la CASE de mapping est ajustée sur données réelles (gate validation).
- **Doublon résiduel après `GROUP BY`** : filet de dédup `qualify row_number()` ordonné par `end_time desc nulls last, start_time desc`.
- **Latence / run en cours** : `gold_dbx_workflow_concurrency_1min` et l'état « live » sont moins immédiats ; l'UI le signale plutôt que de masquer le décalage.
- **Schéma job wheel vs DLT** : la source curated (schéma `system_tables`, job wheel) et le gold (schéma DLT) doivent viser le même `it.ba_data_connect_monitoring__{env}` (sinon FQN explicite dans la vue-pont).

## Requirements

### Functional Requirements

- **FR-001**: Le système DOIT ingérer `system.lakeflow.jobs`, `system.lakeflow.job_run_timeline` et `system.lakeflow.job_task_run_timeline` dans 3 tables curated fidèles et idempotentes via le socle `system_tables` existant (MERGE idempotent + watermark), déclarées dans le registre `SPECS`/`SPEC_KEYS` et alignées avec `for_each.inputs` du job YAML.
- **FR-002**: Les tables curated lakeflow DOIVENT utiliser les clés de merge documentées incluant `cloud_provider` (multi-cloud Azure+AWS) et le watermark approprié (`change_time` pour jobs, `period_start_time` pour les timelines), avec partition `date(period_start_time)` pour les tables d'événements volumineuses et un **backfill initial de 30 jours** (aligné feature 012) avant bascule en rafraîchissement quotidien incrémental.
- **FR-003**: Le système DOIT reconstruire les runs et tâches par **agrégation** (`GROUP BY` au grain run/tâche) des lignes timeline, et non par déduplication `qualify row_number()` : `start_time = min(period_start_time)`, `end_time = max(period_end_time)` uniquement si toutes les périodes sont clôturées (sinon `NULL`), état final via `max_by(col, period_start_time)`.
- **FR-004**: Le système DOIT exposer 2 vues-pont DLT (`_wf_runs_bridge`, `_wf_task_runs_bridge`) reproduisant **exactement** le schéma des anciennes tables `curated_dbx_workflow_runs`/`curated_dbx_workflow_task_runs`, alimentées depuis les curated lakeflow, afin que les 8 fonctions gold restent inchangées.
- **FR-005**: Le contrat GOLD (`gold_dbx_workflow_*`, 8 tables) DOIT rester identique en noms et en schéma ; seule la source change (vues-pont). Les colonnes dérivées de champs non portés par `system.lakeflow` DOIVENT valoir `NULL`, jamais une valeur fictive ni `0`.
- **FR-006**: Le système DOIT mapper `result_state`/`termination_code` vers l'enum de statut DCM et `trigger_type` vers l'enum de déclenchement DCM via des règles SQL documentées, réutilisant la sémantique des maps du collecteur ; toute valeur source inconnue est loggée sans invention d'état.
- **FR-007**: Le système DOIT dériver proprement les champs conservés/recalculés : `retry_count` (comptage tentatives par `run_id`), `tasks_total`/`tasks_failed`/`task_failure_rate` (depuis le task timeline), `attempt_number` (task, via `row_number` post-agrégation), `run_page_url` (reconstruit `{workspace_url}/?o={workspace_id}#job/{job_id}/run/{run_id}`), `creator_user_name = creator_id`.
- **FR-008**: Le système DOIT appliquer des contrôles Data Quality dans les vues-pont/gold : clés run/task non nulles (drop/quarantaine), cohérence temporelle `end_time >= start_time`, `duration_seconds >= 0`, `task_failure_rate ∈ [0,1]`, statut ∈ enum DCM, unicité de grain garantie par le `GROUP BY` (+ filet de dédup).
- **FR-009**: La bascule DOIT être réalisée en 2 temps : (a) brancher la nouvelle source et **valider par comparaison de données** (volumétrie, `success_rate`, percentiles) sur une période commune avec confirmation PO ; (b) seulement après ce gate, retirer le domaine raw/curated `workflow`, le collecteur et le modèle. Pendant la phase (a), les vues-pont `_wf_runs_bridge`/`_wf_task_runs_bridge` portent un **nom distinct** des tables du collecteur, la comparaison ancien/nouveau s'exécute **en parallèle**, et le collecteur ainsi que ses tables `curated_dbx_workflow_*` restent **intacts jusqu'au gate** (rollback trivial).
- **FR-010**: Après le gate, le système DOIT retirer le domaine `workflow` de la couche raw (`valid_domain`) et de la couche curated (§9 workflow, vues staging, tables rejects), en vérifiant qu'aucune consommation ne dépend plus de la version « raw » (les curated `_runs`/`_task_runs` étant produites par les vues-pont).
- **FR-011**: Après le gate, le système DOIT supprimer le collecteur `DatabricksWorkflowCollector` (fichier, imports/exports, registre `main.py`, `config.py`, cibles de déploiement dev+prod, test) sans laisser de référence morte et sans casser la CI du collecteur Azure.
- **FR-012**: Après le gate, le système DOIT supprimer le modèle `WorkflowRunMetric`/`WorkflowTaskRun` (`dcm-commons`) et ses exports/tests, **ainsi que les enums `MetricDomain.WORKFLOW`, `WorkflowRunStatus` et `WorkflowTriggerType`** : le mapping statut/trigger vit désormais 100% en SQL (vues-pont), sans consommateur Python restant. La suppression DOIT être vérifiée sans référence morte (imports/exports/tests).
- **FR-013**: Les services backend Lakeflow (Jobs N1/N2/N3, Overview) et les modèles de réponse DOIVENT tolérer les colonnes `NULL` (types `... | None`) sans rupture de contrat ; aucune route n'est retirée.
- **FR-014**: La route `/workspaces` DOIT résoudre `workspace_name` par repli tags compute (`dcm_workspace_name`/`Project`, `dbw-%`) puis `workspace_id` lorsque les sources gold/curated renvoient `NULL`, sans jamais renvoyer une valeur inventée.
- **FR-015**: Les endpoints Lakeflow DOIVENT exposer un champ `as_of` (timestamp réel dérivé du dernier `_ingested_at`) reflétant la latence des system tables (quelques heures), sans prétendre à une fraîcheur quasi temps réel.
- **FR-016**: Le frontend `/Lakeflow/Jobs` (N1/N2/N3) DOIT rendre NULL-safe les colonnes dépendant de champs perdus (afficher « n/d », jamais `0`), **masquer par défaut la colonne « Attente »** (queue \| lag) devenue intégralement NULL, retirer le tooltip cron du Trigger, appliquer le fallback `workspace_id`, afficher `creator_id` et le code de terminaison, et afficher un bandeau de fraîcheur alimenté par le champ `as_of` (« données à ~X h »).
- **FR-017**: Aucune route backend, aucun schéma de réponse et aucune route de navigation frontend (`app-routes.ts`) NE DOIT être supprimé par cette migration ; la hiérarchie 3 niveaux de la page Jobs reste inchangée.
- **FR-018**: Toutes les données produites DOIVENT provenir exclusivement des vraies system tables Databricks (aucune donnée mockée en production) ; un champ non disponible en source reste `NULL`, conformément aux règles absolues DCM.
- **FR-019**: Les tests DOIVENT être mis à jour/ajoutés pour chaque couche : registre + idempotence merge (curated lakeflow), vues-pont/gold (source system tables), backend (fixtures `workspace_name = NULL`, tolérance NULL), frontend (fixtures NULL, rendu « n/d »).
- **FR-020**: La documentation de lineage et l'epic 009 DOIVENT être mis à jour (retrait de la chaîne collecteur `workflow`, note de migration), et l'infrastructure du collecteur (App Service/ACI) décommissionnée une fois le nouveau flux stable (suivi DevOps hors dispatch).

### Key Entities

- **curated_dbx_lakeflow_jobs**: Définitions SCD des jobs (`job_id`, `name`, `creator_id`, `run_as`, `tags`, `change_time`, `delete_time`) — clé `(cloud_provider, account_id, workspace_id, job_id, change_time)`.
- **curated_dbx_lakeflow_job_run_timeline**: Historique des périodes d'état des runs (`run_id`, `period_start_time`, `period_end_time`, `trigger_type`, `run_type`, `compute_ids`, `result_state`, `termination_code`) — clé incluant `run_id, period_start_time`.
- **curated_dbx_lakeflow_job_task_run_timeline**: Historique des périodes d'état des tâches (`task_run_id`, `task_key`, `period_start_time`, `period_end_time`, `compute_ids`, `result_state`, `termination_code`) — clé incluant `task_run_id, period_start_time`.
- **_wf_runs_bridge / _wf_task_runs_bridge**: Vues-pont DLT reshaping (schéma identique aux anciens `curated_dbx_workflow_runs`/`_task_runs`), champs perdus = `NULL`.
- **gold_dbx_workflow_\*** (8 tables): Contrat inchangé (success_rate, duration_percentiles, duration_drift, task_failure_rate, concurrency_1min, task_health, runs, tasks) — re-sourcées via les vues-pont.

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% des 3 system tables `system.lakeflow` ciblées (jobs, job_run_timeline, job_task_run_timeline) sont disponibles en tables curated interrogeables, multi-cloud (Azure + AWS), en plus des 7 déjà ingérées par le socle.
- **SC-002**: Sur une période commune de validation, la volumétrie runs/tasks et les métriques `success_rate`/`duration_percentiles` issues de la nouvelle source ne divergent pas de la source collecteur au-delà d'un écart documenté attribuable uniquement aux champs perdus et à la fraîcheur (validé avec le PO).
- **SC-003**: Le schéma des 8 tables `gold_dbx_workflow_*` (noms + colonnes + types) est strictement identique avant/après migration ; les champs perdus sont `NULL` et aucune valeur fictive n'est produite (vérifié par diff de schéma + contrôle des colonnes).
- **SC-004**: Les jobs d'ingestion curated et le pipeline gold peuvent être rejoués sur une même période sans duplication de lignes ni perte d'historique (jeu de test rejoué 2 fois, grain run/task unitaire garanti par le `GROUP BY`).
- **SC-005**: Après suppression, aucune référence à `DatabricksWorkflowCollector`, `WorkflowRunMetric`/`WorkflowTaskRun`, ni au domaine raw `workflow` ne subsiste dans le code de production, et l'ensemble des suites de tests (pipeline, collecteur, commons, backend, frontend) est vert.
- **SC-006**: 100% des routes backend Lakeflow et de la navigation frontend `/Lakeflow/Jobs` restent fonctionnelles après migration (aucune 500, aucune route/navigation supprimée), avec les champs perdus rendus « n/d » côté UI (jamais `0`) et la colonne « Attente » masquée par défaut.
- **SC-007**: La page `/Lakeflow/Jobs` affiche un bandeau de fraîcheur calculé depuis le champ `as_of` de l'API (« données à ~X h »), et les runs `running` restent visibles malgré le décalage.
- **SC-008**: Les données produites proviennent exclusivement de vraies system tables Databricks (aucune donnée fictive), conformément aux règles absolues du projet.

## Prerequisites

> Requis avant `/speckit.plan` (validés par le hook `before_plan`).

- **Small branches / small PRs** : découper le travail par domaine et par étape de bascule (curated → vues-pont/gold → teardown → backend → frontend) pour que chaque branche fille (`{domain}/013-{slug}`) touche un ensemble de fichiers **focalisé** (idéalement un package / une préoccupation). Objectif : moins de fichiers modifiés par PR pour faciliter la revue humaine ; l'étape destructive (teardown) reste une PR séparée après le gate.
- **Accès system tables** : schéma `system.lakeflow` activé sur les metastores cibles (dev + prod), Azure **et** AWS ; `GRANT SELECT ON SCHEMA system.lakeflow` au Service Principal d'ingestion (moindre privilège) ; le SQL Warehouse Azure cross-tenant expose bien `system.lakeflow.*` (même voie que `system.billing`/`system.access`).
- **Socle `system_tables`** : pattern d'ingestion existant (`IngestionSpec`, registre `SPECS`/`SPEC_KEYS`, MERGE idempotent, watermark) réutilisable tel quel — confirmé (`packages/dcm-databricks-pipeline/pipelines/system_tables/specs.py`).
- **Contrat gold epic 009** : 8 tables `gold_dbx_workflow_*` et fonctions gold existantes — confirmé (`dlt_03_gold_layer.py`).
- **Décisions archi tranchées** : `workspace_name = NULL` + repli tags/id ; `run_page_url` reconstruit sans le nom ; `creator_user_name = creator_id` (pas de lookup identité SCIM dans cet Epic) ; **backfill initial 30 jours** ; **enums `MetricDomain.WORKFLOW`/`WorkflowRunStatus`/`WorkflowTriggerType` supprimés** (mapping 100% SQL) ; **fraîcheur exposée via champ `as_of`**.
- **Gate de validation** : accord de principe du PO pour valider les champs perdus/dégradés (Partie A du spike) avant toute suppression.
- **Alignement schéma** : job wheel (schéma `system_tables`) et pipeline DLT gold (schéma DLT) visent le même `it.ba_data_connect_monitoring__{env}` (vars bundle, jamais codé en dur).

## Out of scope (this Epic)

- **Récupération des champs perdus** (`queued/setup/execution/cleanup_duration_seconds`, `schedule_lag_seconds`) — non portés par `system.lakeflow`, restent `NULL` (pas de source alternative dans cet Epic).
- **Lookup identité SCIM** pour convertir `creator_id` en nom lisible — reporté (option, non retenue).
- **Résolution de `workspace_name` via une dimension workspaces DCM dédiée** — reporté ; repli tags/`workspace_id` retenu.
- **Restauration d'une fraîcheur quasi temps réel** — la latence system tables (quelques heures) est acceptée et signalée, pas compensée.
- **Décommission effective de l'infrastructure du collecteur** (App Service/ACI) — suivi DevOps séparé, exécuté une fois le nouveau flux stable (hors dispatch de cet Epic).

## Assumptions

- Les system tables `system.lakeflow.*` conservent nativement un historique suffisant pour reconstruire les runs/tasks et couvrir le besoin d'observabilité de l'epic 009, avec la latence documentée (quelques heures).
- Les valeurs exactes de `result_state` et `trigger_type` observées en production seront confirmées lors du gate de validation (Étape 3 du spike) et le mapping SQL ajusté sans jamais inventer d'état.
- Les modèles de réponse Pydantic backend exposent déjà majoritairement des types `... | None` pour les champs concernés ; le travail restant est de garantir/compléter cette tolérance et d'adapter les fixtures de test.
- Le référentiel `dim_landing_zone (lz_id)` et le mapping `workspace_id → LZ`/`workspace_url` existent et sont réutilisables pour dériver `source_lz_id` et reconstruire `run_page_url`.
- Les 8 tables gold et les routes backend/navigation frontend n'exigent aucune évolution de schéma structurelle ; l'impact se limite aux colonnes devenues `NULL` et à la résolution du nom de workspace.
- La bascule en 2 temps (additive puis destructive) permet un rollback simple avant suppression (le collecteur reste opérationnel tant que le gate n'est pas validé).
