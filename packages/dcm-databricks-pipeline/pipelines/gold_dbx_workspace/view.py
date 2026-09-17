"""Construction du SQL de la vue `dim_dbx_workspace` (fonction pure, testable).

Isole la definition SQL de la vue de son execution (`entrypoint.py`) : la
fonction ne fait qu'assembler la requete `CREATE OR REPLACE VIEW` a partir du
`catalog`/`schema` cible (vars bundle, differentes par target), sans jamais coder
en dur la cible ni toucher a un cluster. Testable sans JVM (assertions sur la
chaine retournee).
"""

from __future__ import annotations

# Tables source de la vue (noms non qualifies ; qualifies par catalog.schema a la
# construction). Le curated est alimente par `pipelines.system_tables`
# (`WORKSPACES_LATEST_SPEC`), le referentiel par `pipelines.reference_lz`.
CURATED_ACCESS_WORKSPACES_LATEST = "curated_dbx_access_workspaces_latest"
REFERENCE_LANDING_ZONE_DBX_WORKSPACE = "dim_reference_landing_zone_dbx_workspace"
DIM_DBX_WORKSPACE_VIEW = "dim_dbx_workspace"


def build_dim_dbx_workspace_view_sql(catalog: str, schema: str) -> str:
    """Retourne le `CREATE OR REPLACE VIEW` de `dim_dbx_workspace`.

    Inner join strict `curated_dbx_access_workspaces_latest` (w) ⋈
    `dim_reference_landing_zone_dbx_workspace` (r) sur `workspace_id` : un
    workspace absent de l'une des deux tables est exclu. Filtres portes par la
    vue (`status = 'RUNNING'` + `subscription_or_account_id IS NOT NULL`) pour ne
    retenir que les workspaces actifs rattaches a une Landing Zone connue.
    `updated_at = current_timestamp()` est evalue a chaque lecture (vue non
    materialisee). Rejouable par construction (`CREATE OR REPLACE VIEW`).
    """
    return (
        f"CREATE OR REPLACE VIEW {catalog}.{schema}.dim_dbx_workspace AS\n"
        "SELECT\n"
        "    w.workspace_id                 AS workspace_id,\n"
        "    w.workspace_name               AS workspace_name,\n"
        "    w.workspace_url                AS workspace_url,\n"
        "    r.subscription_or_account_id   AS subscription_or_account_id,\n"
        "    r.cloud_provider               AS cloud,\n"
        "    current_timestamp()            AS updated_at\n"
        f"FROM {catalog}.{schema}.curated_dbx_access_workspaces_latest AS w\n"
        f"INNER JOIN {catalog}.{schema}.dim_reference_landing_zone_dbx_workspace AS r\n"
        "    ON w.workspace_id = r.workspace_id\n"
        "WHERE r.subscription_or_account_id IS NOT NULL\n"
        "  AND w.status = 'RUNNING';"
    )
