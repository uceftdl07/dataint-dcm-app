# Implementation Plan: Databricks Workflows — Métriques d'observabilité (Data Engineering)

**Branch**: `009-databricks-workflows-observability` | **Date**: 2026-06-22 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/009-databricks-workflows-observability/spec.md`

## Summary

Enrichir la chaîne data DCM pour produire, transporter et persister les nouvelles métriques d'observabilité des Workflows Databricks (Jobs & Pipelines) collectées depuis Azure. Approche technique :

1. **Collecteur Azure** : étendre `DatabricksPipelineCollector` (déjà branché sur `/api/2.1/jobs/runs/list`) pour appeler `/api/2.2/jobs/runs/list?expand_tasks=true`, mapper les nouveaux champs (`queued_duration_seconds`, `retry_count`, `schedule_lag_seconds`, `tasks_total`, `tasks_failed`, statut élargi avec `timed_out`), émettre les runs en cours, et regrouper les runs dans une enveloppe `MetricPayload` par cycle avec découpe au-delà d'un seuil de taille.
2. **Contrat de données** (`dcm-commons`) : créer un nouveau modèle `WorkflowRunMetric` (domaine `workflow`) à côté de `PipelineMetric`, et ajouter `MetricDomain.WORKFLOW`. Pas de modification du contrat existant (zéro régression). `schema_version` bumpé `1.1 → 1.2` (additif, rétrocompatible).
3. **Ingestion** (`dcm-lambda-ingestion`) : aucun changement de code (envelope-agnostic). Ajout du domaine `workflow` à la liste autorisée si une validation côté Lambda l'exige.
4. **Pipeline data** (`dcm-databricks-pipeline` DLT) : ajouter le domaine `workflow` à la couche RAW, créer une staging + table CURATED `curated_workflow_runs`, et en GOLD calculer les agrégats (`gold_workflow_success_rate`, `gold_workflow_duration_percentiles`, `gold_workflow_duration_drift`, `gold_workflow_task_failure_rate`, `gold_workflow_concurrency_1min`).
5. **Tests** : pytest pour collecteur (mappers, idempotence des runs en cours, batching) et `dcm-commons` (modèle, sérialisation), tests PySpark pour la transformation DLT et les agrégats sur fixtures connues.

## Technical Context

**Language/Version**: Python 3.12 strict (collecteur, commons, lambda), PySpark/Databricks Runtime 14.x+ (pipeline DLT)

**Primary Dependencies**:
- Collecteur : `httpx`, `azure-identity`, `pydantic`, `structlog`, `dcm-commons` (local)
- Commons : `pydantic` v2
- Lambda : `boto3`, `pydantic`, `dcm-commons` (local)
- Pipeline : `dlt` (Databricks), `pyspark`, `pyspark.sql.functions`, fonctions Databricks SQL (VARIANT, window)

**Storage**:
- RAW Delta : `it.ba_data_connect_monitoring__d.raw_metrics` (VARIANT)
- CURATED Delta : `it.ba_data_connect_monitoring__d.curated_workflow_runs` (nouveau)
- GOLD Delta : tables d'agrégats Workflow (nouvelles, voir Phase 1)
- Lakebase PostgreSQL : pas concerné par cet epic (restitution hors périmètre)

**Testing**: pytest + pytest-asyncio (collecteur, commons, lambda) ; tests PySpark sur fixtures JSON locales (DLT logic) ; aucun e2e Databricks dans cet epic (laissé au déploiement)

**Target Platform**: Linux x86_64 (Azure App Service / ACI pour collecteur ; AWS Lambda pour ingestion ; Databricks workspace pour pipeline)

**Project Type**: Monorepo multi-package Python (Azure collecteur · commons · Lambda · pipeline Databricks)

**Performance Goals**:
- Collecteur : un cycle complet sur une LZ (toutes workspaces, lookback 24h) reste sous 5 min ; payload découpé pour rester sous le seuil de taille de transport Apigee (généralement 10 MB).
- Pipeline : agrégats calculés en moins de 5 min sur un volume cible de 100k runs / 14 j.
- Idempotence : ré-ingestion d'une charge complète sans doublon (clé `landing_zone_id + workspace_id + workflow_id + run_id`).

**Constraints**:
- Aucune régression sur la collecte et l'ingestion des domaines existants (`pipeline`, `compute`, etc.).
- `schema_version` bump additif uniquement.
- Aucune donnée fictive : si une source ne renvoie pas un champ, marquer non disponible (jamais `0` non daté).
- Lookback collecteur fixé à 24h par défaut (FR-021).
- Le collecteur n'effectue **pas** d'agrégat ni d'échantillonnage 1-min (Q clarifications : tout est calculé côté pipeline).

**Scale/Scope**:
- ~10 Landing Zones Azure actives à terme.
- 1 à 10 workspaces Databricks par LZ.
- ~10 à 1000 runs Workflows / workspace / 24h.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Le fichier `.specify/memory/constitution.md` est encore un **template non rempli** (placeholders `[PRINCIPLE_1_NAME]` …). Aucun principe ratifié n'est donc opposable à ce plan.

**À défaut**, ce plan respecte les règles structurantes du dépôt (cf. `.github/copilot-instructions.md` → "Règles absolues") qui font office de constitution de fait :

| Règle | Respect |
|---|---|
| Jamais de données fictives / mockées en production | ✅ FR-011 ; mappers retournent `None` ou champ non disponible si la source manque |
| Jamais de secret hardcodé | ✅ Authentification existante via Managed Identity (Azure) et IAM (AWS) inchangée |
| Jamais d'appel cross-LZ direct | ✅ Le collecteur s'exécute par LZ ; aucune nouvelle communication cross-LZ |
| Python 3.12+ strict | ✅ Aligné sur la base existante |
| Ruff zéro warning | ✅ Nouveaux modules respectent `ruff` (paramétrage existant) |
| Tests obligatoires | ✅ Phase 1 inclut tests pytest pour collecteur, commons, et tests PySpark pour pipeline |
| Imports absolus uniquement | ✅ `from dcm_commons.models.workflow import WorkflowRunMetric` |

**Verdict** : ✅ **PASS** (aucune violation à justifier). À revalider en fin de Phase 1.

## Project Structure

### Documentation (this feature)

```text
specs/009-databricks-workflows-observability/
├── plan.md                              # This file
├── spec.md                              # Feature spec (already written)
├── research.md                          # Phase 0 output (this command)
├── data-model.md                        # Phase 1 output (this command)
├── quickstart.md                        # Phase 1 output (this command)
├── contracts/                           # Phase 1 output (this command)
│   ├── workflow_run_metric.schema.json  # JSON Schema du nouveau modèle
│   ├── metric_payload_workflow.example.json  # Exemple d'enveloppe
│   └── curated_workflow_runs.ddl.sql    # DDL Delta CURATED
├── checklists/
│   └── requirements.md                  # Spec quality checklist (déjà OK)
└── tasks.md                             # Phase 2 (généré par /speckit.tasks)
```

### Source Code (repository root)

Monorepo existant ; les fichiers touchés sont :

```text
packages/
├── dcm-commons/
│   └── dcm_commons/
│       └── models/
│           ├── enums.py                 # + MetricDomain.WORKFLOW, + WorkflowRunStatus, + WorkflowTriggerType
│           ├── workflow.py              # ★ NEW : WorkflowRunMetric (+ TaskOutcome enum imbriqué si utile)
│           └── payload.py               # _CURRENT_SCHEMA_VERSION 1.1 → 1.2 (additif, rétrocompat)
│   └── tests/
│       └── models/
│           └── test_workflow.py         # ★ NEW : modèle, sérialisation, idempotence
│   └── fixtures/
│       └── workflow_run_metric.json     # ★ NEW
│       └── metric_payload_workflow.json # ★ NEW
│
├── dcm-azure-collector/
│   └── azure_collector/
│       └── collectors/
│           └── databricks_workflows.py  # ★ NEW : DatabricksWorkflowCollector (API 2.2 + expand_tasks)
│       └── main.py                      # ajout du nouveau collector au runner
│   └── tests/
│       └── collectors/
│           └── test_databricks_workflows.py  # ★ NEW : mapping, running-run, batching, idempotence
│
├── dcm-lambda-ingestion/
│   └── lambda_ingestion/
│       └── validation.py                # ajouter "workflow" à la liste des domaines acceptés (si liste explicite)
│   └── tests/
│       └── test_validation.py           # ajout cas domaine workflow
│
└── dcm-databricks-pipeline/
    ├── pipelines/
    │   ├── dlt_01_raw_layer.py          # + "workflow" dans valid_domain
    │   ├── dlt_02_curated_layer.py      # + section _stg_workflow / curated_dbx_workflow_runs
    │   └── dlt_03_gold_layer.py         # + 5 agrégats workflow (success_rate, percentiles, drift, task_failure_rate, concurrency_1min)
    ├── schemas/
    │   └── lakebase_ddl.sql             # PAS modifié dans cet epic (Lakebase = restitution, hors scope)
    └── tests/
        └── test_dlt_workflow.py         # ★ NEW : tests PySpark sur fixtures
```

**Structure Decision** : extension du **monorepo Python existant**. Aucun nouveau package, aucune nouvelle frontière de service. Les changements sont :
- **`dcm-commons`** : 1 nouveau module modèle + 3 nouveaux enums + bump `schema_version` 1.1→1.2 (additif).
- **`dcm-azure-collector`** : 1 nouveau collector dédié (préserve l'existant `DatabricksPipelineCollector` qui continue d'alimenter le domaine `pipeline`).
- **`dcm-lambda-ingestion`** : ajout du domaine `workflow` à la liste acceptée (1 ligne si liste explicite).
- **`dcm-databricks-pipeline`** : 1 nouvelle table CURATED + 5 nouvelles tables GOLD, branchées sur le même `raw_metrics` (un seul ajout dans `valid_domain`).

Rationale du choix d'un **nouveau modèle `WorkflowRunMetric`** plutôt que d'étendre `PipelineMetric` :
- `PipelineMetric` est aussi utilisé par ADF, Glue, EMR (`docs/02-data-model/data-models.md`). Lui ajouter des champs Databricks-spécifiques (`tasks_total`, `tasks_failed`, `schedule_lag_seconds`, `attempt_number`) le pollue.
- Un nouveau domaine `workflow` permet d'isoler les agrégats (success_rate 24h/7j, percentiles, drift…) sans déformer les agrégats actuels du domaine `pipeline`.
- La table CURATED dédiée évite des colonnes massivement nulles dans `curated_pipelines`.
- Migration : le collecteur Pipeline existant peut être déprécié sur Databricks dans un epic ultérieur (hors scope), sans casser la rétrocompatibilité.

## Complexity Tracking

> Aucune violation de constitution à justifier — la table reste vide.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |

---

## Addendum — Détail tâches Databricks (`task_id`) — 2026-07-26

**Contexte** : le PR #135 modélise le domaine `workflow` au **grain run** (`WorkflowRunMetric`, un enregistrement par run de Job/Pipeline). Les tâches (`tasks[]`) n'étaient exploitées qu'en agrégat (`tasks_total`, `tasks_failed`). Cet addendum ajoute le **grain tâche** afin d'exposer, tracer et agréger chaque tâche individuellement via un identifiant `task_id`.

### Décision de modélisation — étoile à 2 faits (additif, zéro régression)

Un run Databricks contient N tâches. Ajouter un `task_id` **unique par ligne** impose un grain tâche. Pour ne pas corrompre les 5 KPIs GOLD run-grain existants (success_rate, percentiles, drift, task_failure_rate, concurrency — qui comptent des **runs** et portent des durées **run-level**), on n'aplatit **pas** `task_id` dans le fait run. On introduit un **second fait au grain tâche** :

| Champ | Type | Sémantique | Source API Databricks |
|---|---|---|---|
| `task_id` | STRING | **Identifiant unique du run de tâche** (globalement unique). Clé de dédup au grain tâche. | `tasks[].run_id` |
| `task_key` | STRING | Nom stable de la tâche dans le job (dimension pour agrégats). | `tasks[].task_key` |
| `status` | STRING (`WorkflowRunStatus`) | Résultat de la tâche. | `tasks[].state.result_state` / `status.termination_details.code` |
| `start_time` / `end_time` | TIMESTAMP | Fenêtre d'exécution de la tâche (NULL si en cours). | `tasks[].start_time` / `end_time` (epoch ms) |
| `duration_seconds` | DOUBLE | Durée de la tâche (s). | `tasks[].execution_duration` \|\| (`end`−`start`) |
| `attempt_number` | INT | Numéro de tentative de la tâche. | `tasks[].attempt_number` |
| `cluster_instance_id` | STRING | Cluster ayant exécuté la tâche (join FinOps). | `tasks[].cluster_instance.cluster_id` |
| `error_message` | STRING | Message d'erreur/état de la tâche (max 2000 char). | `tasks[].state.state_message` |

`task_id`/`task_key` sont **NULL-safe** : un run sans `tasks[]` étendu (single-task ad-hoc, `expand_tasks` off) ne produit **aucune** ligne au grain tâche (les compteurs `tasks_total`/`tasks_failed` du fait run restent la source de vérité pour ces runs).

### Impacts par couche

- **`dcm-commons`** :
  - Nouveau modèle imbriqué `WorkflowTaskRun` (`workflow.py`).
  - `WorkflowRunMetric` gagne un champ **additif** `tasks: list[WorkflowTaskRun] = []` (rétrocompatible ; `schema_version` reste `1.2`).
  - Export `WorkflowTaskRun` dans `models/__init__.py`.
- **`dcm-azure-collector`** (`databricks_workflows.py`) : `_map_run_to_metric` peuple `tasks` depuis `run["tasks"]` (mapping `task_id`=`run_id` tâche, `task_key`, status via `_parse_run_state` réutilisé, timings via `_ms_to_seconds`/`_epoch_ms_to_dt`).
- **`dcm-databricks-pipeline`** :
  - **RAW** : inchangé (domaine `workflow`).
  - **CURATED** : `curated_dbx_workflow_runs` **inchangée** (grain run). **NOUVELLE** table `curated_dbx_workflow_task_runs` (grain tâche) via `explode(body:metrics[].tasks[])`, PK `(workflow_id, run_id, task_id, source_lz_id)`, table de rejets associée.
  - **GOLD** : les 5 tables run-grain **inchangées**. **NOUVELLE** table `gold_dbx_workflow_task_health` — grain `(source_lz_id, workspace_id, workflow_id, task_key, execution_date)`, mesures : `total_task_runs`, `failed_task_runs`, `task_failure_rate_pct`, `avg_task_duration_seconds`, `p95_task_duration_seconds`. FK `source_lz_id → dim_landing_zone`. (`task_id` reste au grain curated : non agrégeable en clé GOLD ; la dimension GOLD est `task_key`.)
- **Lakebase** (`lakebase_ddl.sql`) : nouvelle table `gold_dbx_workflow_task_health_sync` (miroir PostgreSQL).
- **Tests** : `test_workflow.py` (modèle + parsing tasks), `test_databricks_workflows_collector.py` (mapping tasks), `test_dlt_workflow.py` (explode task grain + agrégat task_health).

### Rationale

- **Pas de duplication** : durées/status run-level restent au grain run ; durées/status tâche au grain tâche → chaque mesure vit à son grain naturel (conforme au modèle Databricks `system.lakeflow.job_task_run_timeline`).
- **Zéro régression** : aucune modification des tables/KPIs run-grain existants ni du contrat run.
- **`task_id` exposé en CURATED** (drill-down « quelle tâche a échoué / durée par tâche ») ; **`task_key` exposé en GOLD** (KPIs de santé par tâche dans le temps).
