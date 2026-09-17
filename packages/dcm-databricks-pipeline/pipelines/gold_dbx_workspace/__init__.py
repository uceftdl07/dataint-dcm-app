"""Plugin gold — dimension des workspaces Databricks actifs (`dim_dbx_workspace`).

Contrairement aux autres plugins gold (`pipelines.gold_dbx_compute`, agregats
materialises par MERGE), ce module ne calcule ni n'ecrit de table : il declare un
objet Unity Catalog `VIEW` (non materialise) via `CREATE OR REPLACE VIEW`. La vue
est un inner join filtre du curated `curated_dbx_access_workspaces_latest`
(alimente par `pipelines.system_tables`) et du referentiel
`dim_reference_landing_zone_dbx_workspace` (alimente par
`pipelines.reference_lz`). Aucune connexion cross-tenant : uniquement du SQL
`spark.sql` sur des tables Unity Catalog deja qualifiees.
"""

from __future__ import annotations
