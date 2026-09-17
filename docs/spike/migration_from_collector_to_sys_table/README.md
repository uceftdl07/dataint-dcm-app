# Migration — Collecteur Databricks Workflows → System Tables `system.lakeflow`

> Spike : remplacer la source du domaine `workflow` (observabilité des Jobs/Workflows
> Databricks, epic 009) par les **system tables Unity Catalog** `system.lakeflow.*`,
> et **supprimer totalement** le collecteur `DatabricksWorkflowCollector`.
> Catalog / schéma cibles : `it.ba_data_connect_monitoring__{env}` (`__d` dev, `__p` prod).

---

## Pourquoi cette migration

| Aujourd'hui (collecteur) | Cible (system tables) |
|---|---|
| `DatabricksWorkflowCollector` (Azure REST Jobs 2.2, `runs/list?expand_tasks=true`) | `system.lakeflow.jobs` + `job_run_timeline` + `job_task_run_timeline` |
| 1 App Service / ACI par LZ, token Databricks par workspace, pagination bornée (`_MAX_PAGES`, `lookback_hours=24`) | Ingestion serverless incrémentale via le socle `system_tables` (job wheel existant, MERGE idempotent) |
| Azure-only | Multi-cloud (AWS natif ⊎ Azure JDBC cross-tenant, comme les 7 tables déjà ingérées) |
| Quasi temps réel | Latence system tables (quelques heures) |
| Modèle `WorkflowRunMetric` + domaine raw `workflow` | Faits fidèles system tables → reshaping en GOLD |

Bénéfices : moins de compute, moins de secrets, historique complet et rétroactif,
source gouvernée UC. Contrepartie : perte de certains champs (voir plus bas) et de la
fraîcheur temps réel.

---

## Contenu du dossier

| Doc | Objet |
|---|---|
| [migration_steps.md](migration_steps.md) | Étapes de migration (ordre, packages touchés) + **liste des champs perdus/dégradés** |
| [datamodel_curated_gold.md](datamodel_curated_gold.md) | Modèle de données CURATED + GOLD après migration |
| [datamapping.md](datamapping.md) | Mapping `system.lakeflow.*` → curated → gold (colonne par colonne) |
| [impact_back_front.md](impact_back_front.md) | Anticipation des modifications backend + frontend |

---

## Principe directeur

Le **contrat GOLD reste identique** (mêmes 8 tables `gold_dbx_workflow_*`, mêmes colonnes) :
le backend et le frontend ne changent **de structure** que sur les colonnes devenues NULL.
Les 2 tables curated intermédiaires (`curated_dbx_workflow_runs`, `curated_dbx_workflow_task_runs`)
sont **reconstruites** depuis les system tables via 2 vues-pont DLT, au lieu d'être
alimentées par le collecteur via la couche raw.

```text
system.lakeflow.jobs ─────────────┐
system.lakeflow.job_run_timeline ─┼─►  CURATED fidèle (curated_dbx_lakeflow_*)
system.lakeflow.job_task_run_timeline ┘        (socle system_tables, MERGE idempotent)
                                                      │
                                                      ▼
                                       Vues-pont DLT (reshaping → contrat epic 009)
                                                      │
                                                      ▼
                                   GOLD inchangé (gold_dbx_workflow_* × 8)
                                                      │
                                                      ▼
                                            Backend / Frontend
```
