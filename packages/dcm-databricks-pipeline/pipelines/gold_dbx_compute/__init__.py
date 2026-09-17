"""Plugin gold — agregations compute (clusters, puis warehouses/transverse en T003/T004).

Contrairement a `pipelines.system_tables` (ingestion fidele source), ce plugin
LIT des tables curated deja unifiees (`cloud_provider` deja une colonne, pas de
distinction Azure/AWS a la lecture) et calcule des agregats metier (cout,
efficience, fiabilite, gouvernance). Aucune connexion cross-tenant ici : uniquement
des lectures `spark.sql` / `spark.table` sur des tables Unity Catalog deja
materialisees par `pipelines.system_tables`.
"""

from __future__ import annotations
