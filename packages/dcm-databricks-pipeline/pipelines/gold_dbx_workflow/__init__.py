"""Plugin gold — observabilite des Databricks Workflows (domaine `workflow`, epic 009).

Migre hors du pipeline DLT (`dlt_03_gold_layer.py`) vers un job PySpark standalone,
sur le meme modele que `pipelines.gold_dbx_compute`/`pipelines.gold_dbx_usage` :
un `python_wheel_task` par table gold, ecriture idempotente via
`pipelines.common.writers.merge_into_table`, plus de dependance a l'execution
du pipeline DLT ni au graphe `@dlt.table`/`@dlt.view`.

SOURCE DE DONNEES -- POINT CRITIQUE : ce plugin lit EXCLUSIVEMENT les tables
`curated_dbx_lakeflow_*` (produites par `pipelines.system_tables`, elles-memes
depuis `system.lakeflow.*`), JAMAIS `curated_dbx_workflow_runs`/
`curated_dbx_workflow_task_runs` (alimentees par le collecteur Azure
`DatabricksWorkflowCollector` via JSON/Apigee/Lambda/`raw_metrics`). Les deux
familles de tables ont des schemas tres proches (memes noms de colonnes) : ne
JAMAIS substituer l'une a l'autre par erreur lors d'un futur ajout/refactor.
Le decommissionnement du collecteur JSON reste hors scope de cette migration
(cf. `specs/<feature>/spec.md`) ; le fallback `curated_dbx_workflow_runs.
workspace_name` dans `dcm-backend/app/api/services/databricks_workspaces_page.py`
est une dette technique documentee separement, pas a traiter ici.
"""

from __future__ import annotations
