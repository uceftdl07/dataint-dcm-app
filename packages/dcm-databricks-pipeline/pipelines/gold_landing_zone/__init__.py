"""Plugin gold — dimension unifiee des landing zones (`dim_landing_zone`).

Comme `pipelines.gold_dbx_workspace`, ce module ne calcule ni n'ecrit de table :
il declare un objet Unity Catalog `VIEW` (non materialise) via
`CREATE OR REPLACE VIEW`. La vue unifie deux perimetres de LZ — les workspaces
Databricks actifs (`dim_dbx_workspace`, vue de `pipelines.gold_dbx_workspace`) et
les LZ collectees par DCM (`dim_landing_zone_collector`, table DLT du pipeline
gold) — enrichis par le referentiel Business Application
(`dim_reference_landing_zone_business_application`, alimente par
`pipelines.reference_lz`). Aucune connexion cross-tenant : uniquement du SQL
`spark.sql` sur des tables Unity Catalog deja qualifiees.
"""

from __future__ import annotations
