"""Construction du SQL de la vue `dim_landing_zone` (fonction pure, testable).

Isole la definition SQL de la vue de son execution (`entrypoint.py`) : la
fonction ne fait qu'assembler la requete `CREATE OR REPLACE VIEW` a partir du
`catalog`/`schema` cible (vars bundle, differentes par target), sans jamais coder
en dur la cible ni toucher a un cluster. Testable sans JVM (assertions sur la
chaine retournee).
"""

from __future__ import annotations

# Objets source de la vue (noms non qualifies ; qualifies par catalog.schema a la
# construction). `dim_dbx_workspace` (vue) est produite par
# `pipelines.gold_dbx_workspace`, `dim_landing_zone_collector` (table DLT) par le
# pipeline gold, `dim_reference_landing_zone_business_application` par
# `pipelines.reference_lz`.
DIM_DBX_WORKSPACE_VIEW = "dim_dbx_workspace"
DIM_LANDING_ZONE_COLLECTOR = "dim_landing_zone_collector"
REFERENCE_BUSINESS_APPLICATION = "dim_reference_landing_zone_business_application"
DIM_LANDING_ZONE_VIEW = "dim_landing_zone"


def build_dim_landing_zone_view_sql(catalog: str, schema: str) -> str:
    """Retourne le `CREATE OR REPLACE VIEW` de `dim_landing_zone`.

    `UNION ALL` de `dim_dbx_workspace` (colonnes metier heritees `CAST(NULL …)`)
    et `dim_landing_zone_collector` (`WHERE subscription_or_account_id IS NOT
    NULL`), enrichi par un `INNER JOIN` strict sur
    `dim_reference_landing_zone_business_application` (subscription_or_account_id) :
    une LZ sans Business Application est exclue (clarif C1). `lz_id` recalcule
    (`CONCAT('lz-', cloud_provider, '-', subscription_or_account_id)`), dedup a 1
    ligne par `subscription_or_account_id` via `QUALIFY ROW_NUMBER()` (preference
    aux lignes nommees, cote collector — clarif C4). Rejouable par construction.
    """
    return (
        f"CREATE OR REPLACE VIEW {catalog}.{schema}.dim_landing_zone AS\n"
        "SELECT\n"
        "    CONCAT('lz-', a.cloud_provider, '-', a.subscription_or_account_id) AS lz_id,\n"
        "    a.cloud_provider, a.subscription_or_account_id, a.lz_name,\n"
        "    a.environment, a.region, a.owner_team, a.onboarded_at,\n"
        "    b.business_application_id, b.business_application_name\n"
        "FROM (\n"
        "    SELECT cloud AS cloud_provider, subscription_or_account_id,\n"
        "        CAST(NULL AS STRING) AS lz_name, CAST(NULL AS STRING) AS environment,\n"
        "        CAST(NULL AS STRING) AS region, CAST(NULL AS STRING) AS owner_team,\n"
        "        CAST(NULL AS DATE) AS onboarded_at\n"
        f"    FROM {catalog}.{schema}.dim_dbx_workspace\n"
        "    UNION ALL\n"
        "    SELECT cloud_provider, subscription_or_account_id, lz_name,\n"
        "        environment, region, owner_team, onboarded_at\n"
        f"    FROM {catalog}.{schema}.dim_landing_zone_collector\n"
        "    WHERE subscription_or_account_id IS NOT NULL\n"
        ") a\n"
        f"INNER JOIN {catalog}.{schema}.dim_reference_landing_zone_business_application b\n"
        "    ON a.subscription_or_account_id = b.subscription_or_account_id\n"
        "QUALIFY ROW_NUMBER() OVER (\n"
        "    PARTITION BY a.subscription_or_account_id\n"
        "    ORDER BY CASE WHEN a.lz_name IS NOT NULL THEN 0 ELSE 1 END\n"
        ") = 1"
    )
