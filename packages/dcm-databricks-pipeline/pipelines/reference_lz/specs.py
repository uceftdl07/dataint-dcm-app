"""Contrat d'extraction : tables referentiel Landing Zone (workspace / BA).

Contrairement a `pipelines.system_tables.specs`, ce module n'expose PAS un
registre generique d'`IngestionSpec` consomme par `ingest_system_table()` : les
2 tables ci-dessous ont des sources trop divergentes pour l'abstraction
generique (cf. `research.md` §3) :

- `dim_reference_landing_zone_dbx_workspace` : 2 sources (AWS + Azure) qui ne
  partagent PAS le meme nom de colonne d'identifiant de compte
  (`aws_account_id` vs `subscription_id`).
- `dim_reference_landing_zone_business_application` : source Azure UNIQUE
  (`ref_ba_lz`), pas d'equivalent AWS.

`IngestionSpec` reste reutilise ici comme simple porteur de configuration
(table source, colonnes projetees) pour les primitives bas niveau du socle
(`read_native_source`, `read_azure_batches`) -- l'orchestration (renommage par
cloud, filtre, dedup, MERGE) est ecrite a la main dans `ingest.py`.
"""

from __future__ import annotations

from pipelines.common.models import IngestionSpec

# Catalog / schema cibles par defaut, utilises UNIQUEMENT en debug local (cf.
# `pipelines.system_tables.specs` : meme convention). En execution reelle
# (tache wheel), le catalog et le schema proviennent des `named_parameters` du
# job (vars bundle `catalog` / `schema`), jamais codes en dur ici.
DEFAULT_CATALOG = "it"
DEFAULT_SCHEMA = "ba_data_connect_monitoring__d"

# --- dim_reference_landing_zone_dbx_workspace -------------------------------
CURATED_DBX_WORKSPACE = "dim_reference_landing_zone_dbx_workspace"

# Segment catalog avec tiret : backticks obligatoires en identifiant SQL
# 3-parties (cf. research.md §2 -- Spark SQL rejette un tiret non quote).
SOURCE_WORKSPACE_INVENTORY_AWS = (
    "`onedatalake-ppd-internal`.egress_firewall_aws.workspace_inventory"
)
SOURCE_WORKSPACE_INVENTORY_AZURE = "`onedatalake-ppd-internal`.egress_firewall.workspace_inventory"

DBX_WORKSPACE_MERGE_KEYS = ("workspace_id",)

# Colonne d'identifiant de compte/subscription : nom source different par cloud,
# renommee vers la meme colonne cible avant fusion (seule divergence de schema
# entre les 2 sources `workspace_inventory`).
WORKSPACE_ACCOUNT_COLUMN_AWS = "aws_account_id"
WORKSPACE_ACCOUNT_COLUMN_AZURE = "subscription_id"
WORKSPACE_ACCOUNT_COLUMN_TARGET = "subscription_or_account_id"
WORKSPACE_CLOUD_COLUMN_SOURCE = "cloud"
WORKSPACE_CLOUD_COLUMN_TARGET = "cloud_provider"

# `select_columns` projette uniquement les colonnes necessaires (fidele source,
# pas de transformation autre que le renommage applique ensuite dans `ingest.py`).
WORKSPACE_AWS_SPEC = IngestionSpec(
    source_table=SOURCE_WORKSPACE_INVENTORY_AWS,
    curated_table=CURATED_DBX_WORKSPACE,
    merge_keys=DBX_WORKSPACE_MERGE_KEYS,
    select_columns=(
        "workspace_id",
        "workspace_name",
        WORKSPACE_ACCOUNT_COLUMN_AWS,
        WORKSPACE_CLOUD_COLUMN_SOURCE,
    ),
)

WORKSPACE_AZURE_SPEC = IngestionSpec(
    source_table=SOURCE_WORKSPACE_INVENTORY_AZURE,
    curated_table=CURATED_DBX_WORKSPACE,
    merge_keys=DBX_WORKSPACE_MERGE_KEYS,
    select_columns=(
        "workspace_id",
        "workspace_name",
        WORKSPACE_ACCOUNT_COLUMN_AZURE,
        WORKSPACE_CLOUD_COLUMN_SOURCE,
    ),
)

# --- dim_reference_landing_zone_business_application ------------------------
CURATED_BUSINESS_APPLICATION = "dim_reference_landing_zone_business_application"

# Vue Azure unique (tenant Azure) -- aucun equivalent AWS (cf. research.md §3).
SOURCE_BA_LZ = "`catalog_badsdataeng_dev`.`ref_dcm`.`ref_ba_lz`"

BUSINESS_APPLICATION_MERGE_KEYS = (WORKSPACE_ACCOUNT_COLUMN_TARGET,)

BA_LZ_SPEC = IngestionSpec(
    source_table=SOURCE_BA_LZ,
    curated_table=CURATED_BUSINESS_APPLICATION,
    merge_keys=BUSINESS_APPLICATION_MERGE_KEYS,
    select_columns=("name", "ba_id", "lz_id", WORKSPACE_CLOUD_COLUMN_SOURCE),
)

# --- dim_business_application -----------------------------------------------
# Catalogue distinct des Business Applications (1 ligne par `business_application_id`),
# derive de la MEME source Azure `ref_ba_lz` mais projete sur (name, ba_id) puis
# dedup par `business_application_id` -- une BA couvre plusieurs subscriptions dans
# `ref_ba_lz`, cette table n'en garde qu'un representant. Remplace la materialized
# view creee a la main. Consomme par l'API (`/reference/business-applications`).
CURATED_BUSINESS_APPLICATION_DIM = "dim_business_application"

BUSINESS_APPLICATION_DIM_MERGE_KEYS = ("business_application_id",)

BA_DIM_SPEC = IngestionSpec(
    source_table=SOURCE_BA_LZ,
    curated_table=CURATED_BUSINESS_APPLICATION_DIM,
    merge_keys=BUSINESS_APPLICATION_DIM_MERGE_KEYS,
    select_columns=("name", "ba_id"),
)

# Identifiants courts (valeur `{{input}}` d'une iteration `for_each` du job,
# cf. `resources/job_dcm_reference_lz.yml`) -- une table = une task parallele
# (isolation d'echec par table/source, FR-010).
TABLE_DBX_WORKSPACE = "dbx_workspace"
TABLE_BUSINESS_APPLICATION = "business_application"
TABLE_BUSINESS_APPLICATION_DIM = "business_application_dim"

TABLE_KEYS = (
    TABLE_DBX_WORKSPACE,
    TABLE_BUSINESS_APPLICATION,
    TABLE_BUSINESS_APPLICATION_DIM,
)

# Registre cle courte -> nom de table curated (non qualifie) -- meme role que
# `pipelines.system_tables.specs.SPECS`, mais pointant vers un NOM de table
# (pas une `IngestionSpec`) : l'ingestion est dispatchee explicitement dans
# `entrypoint.main` vers l'une des 2 fonctions bespoke `ingest.py`, pas via un
# appel generique unique.
CURATED_TABLES: dict[str, str] = {
    TABLE_DBX_WORKSPACE: CURATED_DBX_WORKSPACE,
    TABLE_BUSINESS_APPLICATION: CURATED_BUSINESS_APPLICATION,
    TABLE_BUSINESS_APPLICATION_DIM: CURATED_BUSINESS_APPLICATION_DIM,
}
