"""Contrat d'extraction : registre des system tables Databricks vers curated.

Seule partie du plugin qui declare *quelles* tables ingerer et *comment* les
rendre idempotentes (cles de merge, watermark, partition). Instancie
l'`IngestionSpec` generique du socle : aucune mecanique ici, uniquement de la
configuration metier.

Regroupe les anciens domaines FinOps (facturation) et Usage (compute / access) :
le job execute une iteration `for_each` par entree du registre `SPECS` (une
table = une task parallele, selectionnee par le parametre `--table`).
"""

from __future__ import annotations

from pipelines.common.models import IngestionSpec

# Catalog / schema cibles par defaut, utilises UNIQUEMENT en debug local. En
# execution reelle (tache wheel), le catalog et le schema proviennent des
# `named_parameters` du job (vars bundle `catalog` / `schema`), qui varient selon
# la target (dev `__d`, prod `__p`) : la cible n'est jamais codee en dur ici.
DEFAULT_CATALOG = "it"
DEFAULT_SCHEMA = "ba_data_connect_monitoring__d"

# Fenetre de backfill du premier run des grosses tables d'evenements. Borne le
# scan initial a `now - N jours` : sans cela, le premier `SELECT *` rapatrie tout
# l'historique via le SQL connector Azure (inline fetch) et depasse le
# `spark.driver.maxResultSize` du warehouse Azure (cross-tenant, non modifiable).
# Les runs suivants sont incrementaux (watermark) et ne relisent que le recent.
INITIAL_BACKFILL_DAYS = 30

# Lots Azure (`fetchmany`) dimensionnes par LARGEUR de ligne : la memoire driver
# ~ batch_size x taille_ligne. Ancrage empirique : access.audit (~50 col + map
# `request_params`) OOM a 50k, stable a 10k. Chaque table est calee sur cet
# ancrage (ligne plus etroite => lot plus gros) pour maximiser le debit sans OOM.
# Les tables non surchargees (petit full-load, ex. list_prices) heritent du lot
# global du job.
AZURE_BATCH_WIDE = 10_000  # payload variable lourd : access.audit, query.history (statement_text)
AZURE_BATCH_NESTED = 15_000  # structs/maps de config : billing.usage, compute.clusters
AZURE_BATCH_STRING = 25_000  # colonnes texte moderees : access.table_lineage
AZURE_BATCH_NARROW = 40_000  # metriques numeriques etroites : compute.node_timeline

# --- FinOps : facturation ---------------------------------------------------
CURATED_BILLING_USAGE = "curated_dbx_billing_usage"
CURATED_BILLING_LIST_PRICES = "curated_dbx_billing_list_prices"

SOURCE_BILLING_USAGE = "system.billing.usage"
SOURCE_BILLING_LIST_PRICES = "system.billing.list_prices"

# Cles metier des MERGE idempotents. `cloud_provider` fait partie de la cle car
# les tables sont mutualisees (evite toute collision Azure/AWS).
BILLING_USAGE_MERGE_KEYS = ("cloud_provider", "record_id")
BILLING_LIST_PRICES_MERGE_KEYS = ("cloud_provider", "sku_name", "price_start_time")

# --- Usage : compute / access -----------------------------------------------
CURATED_COMPUTE_CLUSTERS = "curated_dbx_compute_clusters"
CURATED_COMPUTE_NODE_TIMELINE = "curated_dbx_compute_node_timeline"
CURATED_ACCESS_AUDIT = "curated_dbx_access_audit"

SOURCE_COMPUTE_CLUSTERS = "system.compute.clusters"
SOURCE_COMPUTE_NODE_TIMELINE = "system.compute.node_timeline"
SOURCE_ACCESS_AUDIT = "system.access.audit"

# --- Usage : lineage / query history ----------------------------------------
CURATED_ACCESS_TABLE_LINEAGE = "curated_dbx_access_table_lineage"
CURATED_QUERY_HISTORY = "curated_dbx_query_history"

SOURCE_ACCESS_TABLE_LINEAGE = "system.access.table_lineage"
SOURCE_QUERY_HISTORY = "system.query.history"

COMPUTE_CLUSTERS_MERGE_KEYS = (
    "cloud_provider",
    "account_id",
    "workspace_id",
    "cluster_id",
    "change_time",
)
COMPUTE_NODE_TIMELINE_MERGE_KEYS = (
    "cloud_provider",
    "account_id",
    "workspace_id",
    "cluster_id",
    "instance_id",
    "start_time",
)
ACCESS_AUDIT_MERGE_KEYS = ("cloud_provider", "event_id")

# system.access.audit fait ~50 colonnes et loggue TOUS les evenements du
# workspace/compte (login, clusters, jobs, notebooks, permissions...), pas
# seulement les acces table. C'est le cumul largeur (colonnes variables comme
# `request_params`/`response`) x volume (majorite d'evenements hors perimetre)
# qui sature le driver et fait timeout la table, pas la volumetrie du seul cas
# d'usage vise ici : tracker l'usage d'un data product (table ou groupe de
# tables). On projette donc uniquement les colonnes utiles a ce suivi (qui,
# quand, quelle action, sur quel objet) et on filtre aux actions d'acces table.
#
# Colonnes retenues (cf. `merge_keys`/`watermark_column`/`partition_columns`
# ci-dessus, toutes incluses) :
#   event_id       -> cle de merge
#   event_date     -> partition
#   event_time     -> watermark
#   account_id     -> compte cloud (coherent avec les autres tables usage)
#   workspace_id   -> LZ/workspace concerne
#   user_identity  -> qui (struct, email inclus)
#   service_name   -> surface d'origine de l'action (getTable/createTable/... vs
#                      clusters/create/start/delete/... ; utilise dans le filtre)
#   action_name    -> quoi (acces table, ou cycle de vie cluster)
#   request_params -> objet cible (map, contient le nom de table/schema)
#   response       -> succes/echec de l'action
# Exclues (non necessaires au tracking usage, alourdissent chaque ligne) :
#   source_ip_address, user_agent, session_id, request_id, audit_level,
#   identity_metadata, version.
ACCESS_AUDIT_SELECT_COLUMNS = (
    "event_id",
    "event_date",
    "event_time",
    "account_id",
    "workspace_id",
    "user_identity",
    "service_name",
    "action_name",
    "request_params",
    "response",
)

# Actions correspondant a un acces a une table (memes actions que l'exemple
# officiel de tracking table-level access de la doc Unity Catalog). A etendre
# si le suivi des data products necessite d'autres actions (ex. `getTables`,
# `moveTable`) une fois valide sur les besoins reels du dashboard usage.
ACCESS_AUDIT_TABLE_ACTIONS = ("getTable", "createTable", "deleteTable")

# Actions de cycle de vie cluster (service_name = "clusters"), necessaires a
# `gold_dbx_compute_cluster_reliability_daily` (T002 : start_count,
# avg_startup_seconds, unexpected_termination_count). Noms confirmes en prod
# (`SELECT DISTINCT service_name, action_name FROM system.access.audit WHERE
# service_name = 'clusters'`) : PAS ceux, trompeurs, des endpoints REST
# Databricks Clusters.
#   create / start  -> demarrage.
#   delete          -> TERMINAISON du cluster (l'endpoint REST "delete" arrete
#                      le compute, la config cluster reste ; il n'existe pas
#                      d'action "terminateCluster").
#   permanentDelete -> suppression definitive de la config cluster.
# Les variantes `*Result` (createResult, deleteResult, startResult...) sont
# les evenements de completion asynchrone de l'action precedente : exclues
# du filtre de comptage (sinon double-compte start_count/
# unexpected_termination_count cote T002). Seules `createResult`/`startResult`
# sont effectivement consommees aujourd'hui par la couche gold, comme "evenement
# suivant" pour approximer `avg_startup_seconds` (cf.
# `ACCESS_AUDIT_CLUSTER_START_RESULT_ACTIONS` dans
# `pipelines.gold_dbx_compute.cluster_reliability_daily`). `deleteResult` est ingere
# ici par symetrie/completude du cycle de vie (le filtre est reste groupe au
# niveau action pour rester lisible) mais n'est pas encore consomme en aval :
# aucun consommateur actuel ne l'utilise, un futur besoin (ex. latence de
# terminaison) pourra s'en servir sans reouvrir ce filtre. L'ensemble reste
# restreint au seul service "clusters" pour ne pas elargir le filtre a toutes
# les actions create/start/delete/permanentDelete des AUTRES services (jobs,
# warehouses...), ce qui recreerait le risque de timeout/OOM que ce filtre
# etroit vise a eviter.
ACCESS_AUDIT_CLUSTER_LIFECYCLE_SERVICE = "clusters"
ACCESS_AUDIT_CLUSTER_LIFECYCLE_ACTIONS = ("create", "start", "delete", "permanentDelete")
ACCESS_AUDIT_CLUSTER_LIFECYCLE_RESULT_ACTIONS = (
    "createResult",
    "startResult",
    "deleteResult",
)

ACCESS_AUDIT_ACTIONS = (
    ACCESS_AUDIT_TABLE_ACTIONS
    + ACCESS_AUDIT_CLUSTER_LIFECYCLE_ACTIONS
    + ACCESS_AUDIT_CLUSTER_LIFECYCLE_RESULT_ACTIONS
)
ACCESS_AUDIT_ROW_FILTER = (
    "(action_name IN ({table_actions})) OR "
    "(service_name = '{service}' AND action_name IN ({cluster_actions}))"
).format(
    table_actions=", ".join(f"'{action}'" for action in ACCESS_AUDIT_TABLE_ACTIONS),
    service=ACCESS_AUDIT_CLUSTER_LIFECYCLE_SERVICE,
    cluster_actions=", ".join(
        f"'{action}'"
        for action in ACCESS_AUDIT_CLUSTER_LIFECYCLE_ACTIONS
        + ACCESS_AUDIT_CLUSTER_LIFECYCLE_RESULT_ACTIONS
    ),
)


# system.access.table_lineage est un LOG d'evenements : plusieurs lignes le meme
# jour entre le meme couple (source, target) different par entite, source_type,
# created_by, event_time. Une cle au grain jour (event_date) ecraserait ces
# evenements distincts (dernier lot gagnant) -> perte de donnees. On cle donc au
# grain evenement (event_time + entite + source/target + created_by). Colonnes
# nullables (lignage PATH, entity_run_id/created_by absents) : MERGE null-safe
# (`<=>`, cf. build_merge_sql). event_date reste watermark + partition.
ACCESS_TABLE_LINEAGE_MERGE_KEYS = (
    "cloud_provider",
    "account_id",
    "workspace_id",
    "entity_type",
    "entity_id",
    "entity_run_id",
    "source_table_full_name",
    "source_type",
    "target_table_full_name",
    "target_type",
    "created_by",
    "event_time",
)
QUERY_HISTORY_MERGE_KEYS = ("cloud_provider", "statement_id")

# --- Usage : compute (warehouses / evenements / node types) -----------------
CURATED_COMPUTE_WAREHOUSES = "curated_dbx_compute_warehouses"
CURATED_COMPUTE_WAREHOUSE_EVENTS = "curated_dbx_compute_warehouse_events"
CURATED_COMPUTE_NODE_TYPES = "curated_dbx_compute_node_types"

SOURCE_COMPUTE_WAREHOUSES = "system.compute.warehouses"
SOURCE_COMPUTE_WAREHOUSE_EVENTS = "system.compute.warehouse_events"
SOURCE_COMPUTE_NODE_TYPES = "system.compute.node_types"

WAREHOUSES_MERGE_KEYS = (
    "cloud_provider",
    "account_id",
    "workspace_id",
    "warehouse_id",
    "change_time",
)
WAREHOUSE_EVENTS_MERGE_KEYS = (
    "cloud_provider",
    "account_id",
    "workspace_id",
    "warehouse_id",
    "event_time",
    "event_type",
)
NODE_TYPES_MERGE_KEYS = ("cloud_provider", "account_id", "node_type")


BILLING_USAGE_SPEC = IngestionSpec(
    source_table=SOURCE_BILLING_USAGE,
    curated_table=CURATED_BILLING_USAGE,
    merge_keys=BILLING_USAGE_MERGE_KEYS,
    watermark_column="usage_end_time",
    partition_columns=("usage_date",),
    azure_fetch_batch_size=AZURE_BATCH_NESTED,
)

BILLING_LIST_PRICES_SPEC = IngestionSpec(
    source_table=SOURCE_BILLING_LIST_PRICES,
    curated_table=CURATED_BILLING_LIST_PRICES,
    merge_keys=BILLING_LIST_PRICES_MERGE_KEYS,
    # Reference full-load (miroir d'etat courant) : eligible purge (020-curated-full-load-purge).
    purge_eligible=True,
)

COMPUTE_CLUSTERS_SPEC = IngestionSpec(
    source_table=SOURCE_COMPUTE_CLUSTERS,
    curated_table=CURATED_COMPUTE_CLUSTERS,
    merge_keys=COMPUTE_CLUSTERS_MERGE_KEYS,
    watermark_column="change_time",
    initial_lookback_days=INITIAL_BACKFILL_DAYS,
    azure_fetch_batch_size=AZURE_BATCH_NESTED,
)

COMPUTE_NODE_TIMELINE_SPEC = IngestionSpec(
    source_table=SOURCE_COMPUTE_NODE_TIMELINE,
    curated_table=CURATED_COMPUTE_NODE_TIMELINE,
    merge_keys=COMPUTE_NODE_TIMELINE_MERGE_KEYS,
    watermark_column="start_time",
    initial_lookback_days=INITIAL_BACKFILL_DAYS,
    azure_fetch_batch_size=AZURE_BATCH_NARROW,
)

ACCESS_AUDIT_SPEC = IngestionSpec(
    source_table=SOURCE_ACCESS_AUDIT,
    curated_table=CURATED_ACCESS_AUDIT,
    merge_keys=ACCESS_AUDIT_MERGE_KEYS,
    watermark_column="event_time",
    partition_columns=("event_date",),
    initial_lookback_days=INITIAL_BACKFILL_DAYS,
    azure_fetch_batch_size=AZURE_BATCH_WIDE,
    select_columns=ACCESS_AUDIT_SELECT_COLUMNS,
    row_filter=ACCESS_AUDIT_ROW_FILTER,

)

ACCESS_TABLE_LINEAGE_SPEC = IngestionSpec(
    source_table=SOURCE_ACCESS_TABLE_LINEAGE,
    curated_table=CURATED_ACCESS_TABLE_LINEAGE,
    merge_keys=ACCESS_TABLE_LINEAGE_MERGE_KEYS,
    watermark_column="event_date",
    partition_columns=("event_date",),
    initial_lookback_days=INITIAL_BACKFILL_DAYS,
    azure_fetch_batch_size=AZURE_BATCH_STRING,
)

QUERY_HISTORY_SPEC = IngestionSpec(
    source_table=SOURCE_QUERY_HISTORY,
    curated_table=CURATED_QUERY_HISTORY,
    merge_keys=QUERY_HISTORY_MERGE_KEYS,
    watermark_column="start_time",
    initial_lookback_days=INITIAL_BACKFILL_DAYS,
    azure_fetch_batch_size=AZURE_BATCH_WIDE,
)

# system.compute.warehouses : historique de configuration des SQL Warehouses
# (une ligne par version). FULL LOAD, malgre la colonne temporelle `change_time` :
# c'est une DIMENSION A EVOLUTION LENTE, pas un journal d'evenements. Le
# `change_time` d'une ligne peut avoir des annees et decrire pourtant l'etat
# courant du warehouse ; un watermark n'y "retarde" donc pas la longue traine, il
# l'exclut definitivement (le watermark n'avance que vers l'avant, aucun run
# ulterieur ne rattrape). Mesure en dev le 2026-09-07, avec l'ancien watermark :
# 293 warehouses en curated pour 1429 en source (235 workspaces, historique
# depuis 2023-08-14), et 323 des 323 manquants avaient leur `change_time` le plus
# recent anterieur au demarrage de l'ingestion.
#
# NE PAS y remettre `watermark_column` / `initial_lookback_days` : cette borne
# protege les GROSSES tables d'evenements du maxResultSize du driver Azure (cf.
# INITIAL_BACKFILL_DAYS), pas celle-ci — 2583 lignes relues par run cote AWS.
# `change_time` reste dans `merge_keys` (grain = version) : le MERGE complete
# l'historique manquant sans ecraser les versions deja presentes. Lot Azure NESTED
# conserve (structs de config imbriques, ancrage compute.clusters).
WAREHOUSES_SPEC = IngestionSpec(
    source_table=SOURCE_COMPUTE_WAREHOUSES,
    curated_table=CURATED_COMPUTE_WAREHOUSES,
    merge_keys=WAREHOUSES_MERGE_KEYS,
    # Full load mais deliberement PAS `purge_eligible` (les 2 sont orthogonaux,
    # cf. docstring du champ), contrairement aux autres full-load du fichier
    # (node_types, list_prices, registres UC) qui sont des referentiels SANS
    # historique. Ici plusieurs lignes coexistent par warehouse (2583 pour 1429)
    # et le gold resout le nom via `change_time < period_start + 1 jour` (cf.
    # gold_dbx_compute/warehouse_*_daily.py) : purger vers l'etat courant
    # casserait cette resolution historique.
    azure_fetch_batch_size=AZURE_BATCH_NESTED,
)

# system.compute.warehouse_events est un LOG d'evenements (start/stop/scaling...)
# par warehouse : grain evenement (pas de cle naturelle unique sans event_type,
# plusieurs evenements pouvant partager le meme `event_time`). Ligne etroite
# (peu de colonnes, essentiellement des metriques/etats) -> lot Azure NARROW,
# comme compute.node_timeline. La vraie table source n'expose AUCUNE colonne
# date (uniquement `account_id, workspace_id, warehouse_id, event_type,
# cluster_count, event_time`) : curated reste fidele source stricte (aucune
# colonne inventee/derivee), donc PAS de partitionnement ici (comme
# WAREHOUSES_SPEC / QUERY_HISTORY_SPEC) ; le pruning MERGE se fait uniquement
# via le watermark `event_time`.
WAREHOUSE_EVENTS_SPEC = IngestionSpec(
    source_table=SOURCE_COMPUTE_WAREHOUSE_EVENTS,
    curated_table=CURATED_COMPUTE_WAREHOUSE_EVENTS,
    merge_keys=WAREHOUSE_EVENTS_MERGE_KEYS,
    watermark_column="event_time",
    initial_lookback_days=INITIAL_BACKFILL_DAYS,
    azure_fetch_batch_size=AZURE_BATCH_NARROW,
)

# system.compute.node_types est une table de REFERENCE (catalogue des types de
# noeud disponibles, quelques centaines de lignes, quasi statique) : pas de
# watermark (full load a chaque run, comme billing.list_prices), aucun
# partitionnement, aucun besoin de borner le lot Azure (petite table).
# `gpu_count` est NULL pour les instances sans GPU (absence de colonne
# renseignee cote source, pas "0 GPU" explicite) : le curated reste fidele
# source stricte et conserve ce NULL tel quel. La normalisation eventuelle
# (coalesce a 0 pour l'aval FinOps/dashboard) est un traitement METIER qui
# relevera de la couche gold (pipelines/gold_dbx_compute/, a scaffolder en
# T002+), pas de ce socle d'ingestion curated.
NODE_TYPES_SPEC = IngestionSpec(
    source_table=SOURCE_COMPUTE_NODE_TYPES,
    curated_table=CURATED_COMPUTE_NODE_TYPES,
    merge_keys=NODE_TYPES_MERGE_KEYS,
    # Reference full-load (miroir d'etat courant) : eligible purge (020-curated-full-load-purge).
    purge_eligible=True,
)

# --- Workflow : Jobs/Lakeflow (system.lakeflow.*) ---------------------------
CURATED_LAKEFLOW_JOBS = "curated_dbx_lakeflow_jobs"
CURATED_LAKEFLOW_PIPELINES = "curated_dbx_lakeflow_pipelines"
CURATED_LAKEFLOW_JOB_RUN_TIMELINE = "curated_dbx_lakeflow_job_run_timeline"
CURATED_LAKEFLOW_JOB_TASK_RUN_TIMELINE = "curated_dbx_lakeflow_job_task_run_timeline"
CURATED_LAKEFLOW_PIPELINE_UPDATE_TIMELINE = "curated_dbx_lakeflow_pipeline_update_timeline"

SOURCE_LAKEFLOW_JOBS = "system.lakeflow.jobs"
SOURCE_LAKEFLOW_PIPELINES = "system.lakeflow.pipelines"
SOURCE_LAKEFLOW_JOB_RUN_TIMELINE = "system.lakeflow.job_run_timeline"
SOURCE_LAKEFLOW_JOB_TASK_RUN_TIMELINE = "system.lakeflow.job_task_run_timeline"
SOURCE_LAKEFLOW_PIPELINE_UPDATE_TIMELINE = "system.lakeflow.pipeline_update_timeline"

LAKEFLOW_JOBS_MERGE_KEYS = (
    "cloud_provider",
    "account_id",
    "workspace_id",
    "job_id",
    "change_time",
)
LAKEFLOW_PIPELINES_MERGE_KEYS = (
    "cloud_provider",
    "account_id",
    "workspace_id",
    "pipeline_id",
    "change_time",
)
LAKEFLOW_JOB_RUN_TIMELINE_MERGE_KEYS = (
    "cloud_provider",
    "account_id",
    "workspace_id",
    "job_id",
    "run_id",
    "period_start_time",
)
LAKEFLOW_JOB_TASK_RUN_TIMELINE_MERGE_KEYS = (
    "cloud_provider",
    "account_id",
    "workspace_id",
    "job_id",
    "run_id",
    "period_start_time",
)
# Cle naturelle de system.lakeflow.pipeline_update_timeline = le grain HORAIRE de
# la source, PAS l'update. `update_id` seul est tentant (il est meme globalement
# unique : 412 350 ids distincts pour 412 350 couples (workspace_id, update_id),
# mesure dev du 2026-09-10 sur tout l'historique disponible) mais il n'est pas la
# cle de CETTE table : la source est periodisee, elle publie une ligne par tranche
# d'etat d'un update — 422 167 lignes pour 412 350 updates, jusqu'a 12 lignes pour
# un seul update. Merger sur `update_id` seul ne leverait aucune erreur et
# reduirait l'ingestion a UNE ligne arbitraire par update (`merge_into_table`
# applique `dropDuplicates(merge_keys)` avant le MERGE) : 9 817 lignes
# disparaitraient en silence, dont l'unique ligne porteuse de `result_state` pour
# certains updates. L'agregation au grain update est un traitement METIER : elle
# vit en gold (`gold_dbx_compute_pipeline_update_stats`), jamais ici (cf. le
# module `ingest`, fidele source sans transformation ni jointure).
#
# `account_id` volontairement ABSENT, contrairement aux deux specs soeurs
# ci-dessus. L'argument porteur est la REDONDANCE, et elle est mesuree
# (2026-09-10) : le 4-uplet resout deja 422 250 valeurs distinctes pour 422 250
# lignes, et `account_id` ne prend qu'UNE valeur sur les 61 workspaces de la
# source (`cloud_provider` separe deja AWS d'Azure). L'unicite est donc atteinte
# sans lui. (Le niveau differe du 422 167 cite plus haut : la source est vivante
# et grossit de quelques lignes par minute. C'est l'EGALITE des deux comptes qui
# porte l'argument, pas leur valeur.)
# Argument secondaire, et HYPOTHETIQUE — a ne pas lire comme un incident observe :
# la colonne est nullable au schema (0 NULL mesure aujourd'hui sur 422 250 lignes).
# Si un backfill source la faisait passer de NULL a une valeur, la cle etant
# NULL-SAFE (`<=>`) le MERGE INSERERAIT un doublon au lieu de mettre a jour. Une
# colonne redondante n'apporte aucun pouvoir discriminant mais garde ce mode de
# panne : d'ou son exclusion, pas l'inverse.
# Meme raisonnement que pour la cle du gold (cf.
# `gold_dbx_compute.specs`) : une cle de merge minimale a moins de modes de panne.
# Divergence assumee vis-a-vis des soeurs, tranchee AVANT le premier deploiement —
# changer une cle de merge ensuite impose de reecrire la table curated.
LAKEFLOW_PIPELINE_UPDATE_TIMELINE_MERGE_KEYS = (
    "cloud_provider",
    "workspace_id",
    "pipeline_id",
    "update_id",
    "period_start_time",
)


# system.lakeflow.jobs : historique des definitions de job (1 ligne par version).
# FULL LOAD, malgre la colonne temporelle `change_time` : meme mecanisme de perte
# que WAREHOUSES_SPEC, avec sa propre mesure. Un watermark n'y ecarte pas les
# entites ANCIENNES mais les entites DURABLES ET NON MODIFIEES dans les
# INITIAL_BACKFILL_DAYS precedant le premier run, et il n'avance que vers l'avant :
# aucun run ulterieur ne les rattrape, or une definition de job vit des annees
# sans etre touchee. Mesure en dev le 2026-09-07 : `job_name` resolu sur 70,2 %
# seulement des 68 918 lignes de `gold_dbx_compute_job_cluster_cost_daily`, dont la
# jointure est un LEFT JOIN (la perte n'est donc pas masquee par un INNER JOIN).
#
# NE PAS y remettre `watermark_column` / `initial_lookback_days`, malgre l'exemple
# de COMPUTE_CLUSTERS_SPEC : celle-ci les garde et affiche pourtant 100 % de
# `cluster_name` resolu, mais par accident de nature (un cluster de job est
# ephemere, recree a chaque execution, son `change_time` est toujours dans la
# fenetre) ; une definition de job, non. Si ce full load venait a saturer le driver
# Azure (cf. INITIAL_BACKFILL_DAYS), reduire la LARGEUR lue (`select_columns`, lot
# Azure) plutot que restaurer la borne temporelle, qui reperdrait la longue traine.
# Volume mesure en dev le 2026-09-07 : 813 516 lignes en full load contre 40 827
# dans la fenetre de 30 jours, soit ~20x de lecture par run (82 733 jobs, 194
# workspaces, historique depuis 2024-01-15). C'est un ordre de grandeur au-dessus
# des 2583 lignes de compute.warehouses, mais sans risque memoire : cote Azure
# `read_azure_batches` streame par lots de 15 000 vers un staging avant un MERGE
# unique, le driver ne detenant jamais plus d'un lot ; cote AWS c'est une lecture
# Spark d'une system table. A comparer au meme job, qui ingere `access.audit` a
# ~4,5 M lignes/jour. `change_time` reste dans `merge_keys`
# (grain = version) : le MERGE complete l'historique manquant sans ecraser les
# versions deja presentes. Lot Azure NESTED conserve (colonne `tags` MAP, largeur
# comparable a compute.clusters).
LAKEFLOW_JOBS_SPEC = IngestionSpec(
    source_table=SOURCE_LAKEFLOW_JOBS,
    curated_table=CURATED_LAKEFLOW_JOBS,
    merge_keys=LAKEFLOW_JOBS_MERGE_KEYS,
    # Full load mais deliberement PAS `purge_eligible` (les 2 sont orthogonaux,
    # cf. docstring du champ, qui reserve la purge aux miroirs d'etat courant).
    # Verifie sur CE consommateur, pas deduit des warehouses : la CTE `jobs_as_of`
    # de `gold_dbx_compute/job_cluster_cost_daily.py` resout `job_name` avec
    # `change_time < period_start + INTERVAL 1 DAY`, puis garde la version la plus
    # recente. Purger vers l'etat courant laisserait `job_name` NULL sur tout jour
    # anterieur au dernier `change_time` du job. Le repli ajoute depuis sur
    # `job_run_timeline.run_name` NE RATTRAPERAIT PAS cette perte : `run_name` est
    # renseigne a 100 % sur les runs soumis par API et a 0 % sur les runs issus
    # d'une definition de job, soit exactement les lignes que CETTE table nomme.
    azure_fetch_batch_size=AZURE_BATCH_NESTED,
)

# system.lakeflow.pipelines : historique des definitions de pipeline DLT (1 ligne
# par version, colonne `change_time`), semantiquement identique a
# system.lakeflow.jobs -> meme traitement, meme raison. FULL LOAD, deliberement
# SANS `watermark_column` ni `initial_lookback_days` : une definition de pipeline
# durable vit des mois sans etre modifiee, et un watermark sur `change_time` en
# ecarterait la longue traine (cf. la mesure et le raisonnement detailles dans la
# docstring de LAKEFLOW_JOBS_SPEC ci-dessus). `change_time` reste dans les
# `merge_keys` (grain = version) : le MERGE complete l'historique manquant sans
# ecraser les versions deja presentes. Lot Azure NESTED : colonnes larges `tags`
# (MAP), `settings` (struct) et `configuration` (MAP), comme les jobs.
LAKEFLOW_PIPELINES_SPEC = IngestionSpec(
    source_table=SOURCE_LAKEFLOW_PIPELINES,
    curated_table=CURATED_LAKEFLOW_PIPELINES,
    merge_keys=LAKEFLOW_PIPELINES_MERGE_KEYS,
    azure_fetch_batch_size=AZURE_BATCH_NESTED,
)

# system.lakeflow.job_run_timeline est un LOG immuable (1 ligne par periode
# d'etat d'un run, watermark `period_start_time`). La table source n'expose
# AUCUNE colonne DATE native (uniquement des TIMESTAMP) : comme
# WAREHOUSE_EVENTS_SPEC/QUERY_HISTORY_SPEC, curated reste fidele source stricte
# et NE PARTITIONNE PAS sur une colonne derivee (`date(period_start_time)`
# n'existe pas nativement) ; le pruning MERGE se fait uniquement via le
# watermark. Lot Azure NESTED : colonnes `job_parameters` (MAP) et `compute_ids`
# (ARRAY) de largeur comparable a compute.clusters/warehouses.
LAKEFLOW_JOB_RUN_TIMELINE_SPEC = IngestionSpec(
    source_table=SOURCE_LAKEFLOW_JOB_RUN_TIMELINE,
    curated_table=CURATED_LAKEFLOW_JOB_RUN_TIMELINE,
    merge_keys=LAKEFLOW_JOB_RUN_TIMELINE_MERGE_KEYS,
    watermark_column="period_start_time",
    initial_lookback_days=INITIAL_BACKFILL_DAYS,
    azure_fetch_batch_size=AZURE_BATCH_NESTED,
)

# system.lakeflow.job_task_run_timeline : meme nature (LOG immuable, watermark
# `period_start_time`, aucune colonne DATE native -> pas de partitionnement,
# memes raisons que ci-dessus). Cle naturelle = (workspace_id, job_id, run_id,
# period_start_time) : IMPORTANT, sur CETTE table `run_id` designe l'ID
# d'EXECUTION DE LA TACHE (pas le run parent — confirme par la doc officielle
# Databricks : "run_id: The ID of the task run"). Le run PARENT est expose via
# `job_run_id` (= `run_id` de job_run_timeline). `task_key` (nom stable de la
# tache dans le job) n'est PAS necessaire dans la cle : chaque tentative/retry
# genere deja un `run_id` distinct sur cette table, donc `run_id` seul suffit a
# identifier une execution de tache — meme structure de cle que
# LAKEFLOW_JOB_RUN_TIMELINE_MERGE_KEYS, applique au grain tache. Correctif
# suite echec reel en dev (`UNRESOLVED_COLUMN_AMONG_FIELD_NAMES: task_run_id` —
# cette colonne n'existe pas ; le premier correctif utilisait `task_key`, ici
# remplace par `run_id` qui est semantiquement plus correct). Ligne plus
# etroite que job_run_timeline (pas de `job_parameters` MAP, seulement
# `compute_ids` ARRAY) -> lot Azure NARROW, comme compute.node_timeline.
LAKEFLOW_JOB_TASK_RUN_TIMELINE_SPEC = IngestionSpec(
    source_table=SOURCE_LAKEFLOW_JOB_TASK_RUN_TIMELINE,
    curated_table=CURATED_LAKEFLOW_JOB_TASK_RUN_TIMELINE,
    merge_keys=LAKEFLOW_JOB_TASK_RUN_TIMELINE_MERGE_KEYS,
    watermark_column="period_start_time",
    initial_lookback_days=INITIAL_BACKFILL_DAYS,
    azure_fetch_batch_size=AZURE_BATCH_NARROW,
)

# system.lakeflow.pipeline_update_timeline : LOG immuable des executions
# (« updates ») de pipeline DLT/Lakeflow, 1 ligne par tranche d'etat, watermark
# `period_start_time`. Pendant exact de job_run_timeline pour les pipelines ->
# meme traitement, memes raisons. AUCUNE colonne DATE native (les 2 colonnes de
# periode sont TIMESTAMP, schema relu le 2026-09-10 via
# `system.information_schema.columns`) : comme ses deux soeurs, curated reste
# fidele source stricte et NE PARTITIONNE PAS sur une colonne derivee
# (`date(period_start_time)` n'existe pas a la source) ; le pruning du MERGE ne
# passe que par le watermark.
#
# `purge_eligible=False` explicite (c'est deja le defaut) : log d'evenements, pas
# un miroir d'etat courant. La source elle-meme ne conserve qu'environ un an
# glissant — la plus ancienne ligne mesuree le 2026-09-10 date du 2025-09-08,
# soit 367 jours — donc une purge vers l'etat courant detruirait un historique que
# la source ne peut PAS reproduire, et que `gold_dbx_compute_pipeline_update_stats`
# agrege.
#
# Lot Azure NESTED, comme job_run_timeline : largeur de ligne mesuree le
# 2026-09-10, ~696 octets en JSON dont seulement 84 pour les 3 colonnes ARRAY.
# PAS de `select_columns` (option evaluee puis ecartee sur mesure) : les 3
# tableaux `refresh_selection`, `full_refresh_selection` et
# `reset_checkpoint_selection` sont vides sur plus de 99,8 % des lignes (311, 494
# et 0 lignes non vides sur 422 167). Les projeter hors du curated economiserait
# une largeur negligeable en echange d'une liste de colonnes a maintenir en phase
# avec le schema source — toute colonne ajoutee par Databricks serait alors perdue
# silencieusement, ce qui est le defaut inverse de la fidelite source.
LAKEFLOW_PIPELINE_UPDATE_TIMELINE_SPEC = IngestionSpec(
    source_table=SOURCE_LAKEFLOW_PIPELINE_UPDATE_TIMELINE,
    curated_table=CURATED_LAKEFLOW_PIPELINE_UPDATE_TIMELINE,
    merge_keys=LAKEFLOW_PIPELINE_UPDATE_TIMELINE_MERGE_KEYS,
    watermark_column="period_start_time",
    initial_lookback_days=INITIAL_BACKFILL_DAYS,
    purge_eligible=False,
    azure_fetch_batch_size=AZURE_BATCH_NESTED,
)

# --- Usage Data Product : registre Unity Catalog (T001, 019-usage-data-product-gold) ---
# Fondation du socle usage : 2 tables de reference UC (metadonnees + tags,
# `information_schema.*`, full load leger comme `compute_node_types`) et 1 table
# d'evenements d'ecriture (`access.audit`, meme source que `ACCESS_AUDIT_SPEC`
# mais filtre DISTINCT -> curated separee, `curated_dbx_access_audit` inchangee).
CURATED_UC_TABLES = "curated_dbx_uc_tables"
CURATED_UC_TABLE_TAGS = "curated_dbx_uc_table_tags"
CURATED_UC_TABLE_OPERATIONS = "curated_dbx_uc_table_operations"

SOURCE_UC_TABLES = "system.information_schema.tables"
SOURCE_UC_TABLE_TAGS = "system.information_schema.table_tags"
# Meme source que ACCESS_AUDIT_SPEC (SOURCE_ACCESS_AUDIT = system.access.audit) :
# reutilisee telle quelle, seul le filtre d'action (row_filter) differe.

UC_TABLES_MERGE_KEYS = ("cloud_provider", "table_catalog", "table_schema", "table_name")
UC_TABLE_TAGS_MERGE_KEYS = (
    "cloud_provider",
    "catalog_name",
    "schema_name",
    "table_name",
    "tag_name",
)
# Meme forme que ACCESS_AUDIT_MERGE_KEYS (curated distincte, cle identique : les
# 2 tables partagent le meme grain evenement sur la meme source system.access.audit).
UC_TABLE_OPERATIONS_MERGE_KEYS = ("cloud_provider", "event_id")

# Actions system.access.audit correspondant a une ECRITURE de contenu sur une
# table UC (par opposition a ACCESS_AUDIT_TABLE_ACTIONS = acces/lecture
# getTable + cycle de vie createTable/deleteTable, deja ingere par
# ACCESS_AUDIT_SPEC). Distincte de `ACCESS_AUDIT_TABLE_ACTIONS` : ne pas
# etendre ni reutiliser cette derniere (comportement de
# `curated_dbx_access_audit` inchange). Chevauchement partiel attendu
# (createTable/deleteTable relevent des 2 notions) : ce n'est pas le meme
# objet ni construit a partir de l'autre.
#
# Ces 3 actions sont les SEULES du service `unityCatalog` documentees par
# Databricks (diagnostic log reference) et confirmees sur donnee reelle :
#   createTable/deleteTable -> cycle de vie du catalogue.
#   updateTables (nom PLURIEL cote Databricks) -> mise a jour d'une table.
#     N'EST PAS un signal d'ecriture, et la doc officielle ne le presente jamais
#     comme tel : « User makes an update to a table », et les parametres qu'elle
#     enumere sont TOUS des champs de definition (`table_type`, `columns`,
#     `row_filter`, `view_definition`, `owner`, `comment`...). L'action se declenche
#     bien a moins d'1s d'un `MERGE`/`INSERT` reel, mais par effet de bord -- un
#     commit Delta met a jour l'entree UC de la table -- et elle porte tout autant
#     les changements de metadonnee seule et les appels qui n'ecrivent rien. Une
#     « derniere ecriture » ne peut donc pas se deduire de ce service : elle se
#     calcule sur `curated_dbx_query_history.written_rows` (cf. la CTE
#     `lineage_writes` de `gold_dbx_usage/table_catalog.py`).
# ATTENTION : les ecritures de CONTENU Delta (INSERT/MERGE/COPY INTO/OPTIMIZE/
# VACUUM) s'executent au niveau moteur Spark/Delta, pas via l'API control-plane
# Unity Catalog -- elles n'ont donc PAS de `action_name` dedie sur ce service
# et ne doivent jamais etre ajoutees a cette liste (aucune valeur du type
# `commit`/`writeIntoTable`/`mergeIntoTable`/`optimize`/`vacuumEnd`/
# `setTableTags` n'existe dans le vocabulaire documente `unityCatalog`).
ACCESS_AUDIT_WRITE_ACTIONS = (
    "createTable",
    "deleteTable",
    "updateTables",
)

ACCESS_AUDIT_WRITE_ROW_FILTER = "action_name IN ({actions})".format(
    actions=", ".join(f"'{action}'" for action in ACCESS_AUDIT_WRITE_ACTIONS)
)

UC_TABLES_SPEC = IngestionSpec(
    source_table=SOURCE_UC_TABLES,
    curated_table=CURATED_UC_TABLES,
    merge_keys=UC_TABLES_MERGE_KEYS,
    # Registre UC full-load (miroir d'etat courant) : eligible purge (020-curated-full-load-purge).
    purge_eligible=True,
)

UC_TABLE_TAGS_SPEC = IngestionSpec(
    source_table=SOURCE_UC_TABLE_TAGS,
    curated_table=CURATED_UC_TABLE_TAGS,
    merge_keys=UC_TABLE_TAGS_MERGE_KEYS,
    # Registre UC full-load (miroir d'etat courant) : eligible purge (020-curated-full-load-purge).
    purge_eligible=True,
)

# select_columns reutilise ACCESS_AUDIT_SELECT_COLUMNS (memes colonnes utiles :
# qui/quand/quelle action/quel objet/succes-echec) -- seul row_filter differe
# (actions d'ECRITURE au lieu d'acces table). `request_params` (MAP) reste BRUT
# ici : l'extraction de `table_full_name`/`operation` normalisee est un
# traitement metier qui vit en GOLD (T003 `table_catalog`), pas en curated
# (P12 -- meme convention que `request_params['cluster_id']` extrait en gold
# dans `gold_dbx_compute/cluster_reliability_daily.py`, jamais en curated).
UC_TABLE_OPERATIONS_SPEC = IngestionSpec(
    source_table=SOURCE_ACCESS_AUDIT,
    curated_table=CURATED_UC_TABLE_OPERATIONS,
    merge_keys=UC_TABLE_OPERATIONS_MERGE_KEYS,
    watermark_column="event_time",
    partition_columns=("event_date",),
    initial_lookback_days=INITIAL_BACKFILL_DAYS,
    azure_fetch_batch_size=AZURE_BATCH_WIDE,
    select_columns=ACCESS_AUDIT_SELECT_COLUMNS,
    row_filter=ACCESS_AUDIT_WRITE_ROW_FILTER,
)

# --- Access : inventaire des workspaces (system.access.workspaces_latest) ----
# Snapshot « latest » des workspaces Databricks (AWS natif + Azure cross-tenant),
# alimente la dimension `dim_dbx_workspace` (feature 020). Table de reference
# petite et stable : full load a chaque run (aucun watermark, comme
# `compute.node_types` / `billing.list_prices`), aucune partition. `cloud_provider`
# fait partie de la cle de merge (table mutualisee Azure/AWS) et est ajoute par
# l'enveloppe, donc ABSENT de `select_columns` (comme toutes les autres specs).
CURATED_ACCESS_WORKSPACES_LATEST = "curated_dbx_access_workspaces_latest"
SOURCE_ACCESS_WORKSPACES_LATEST = "system.access.workspaces_latest"
WORKSPACES_LATEST_MERGE_KEYS = ("cloud_provider", "workspace_id")

# `account_id` projete sous reserve de presence a la source (schema confirme au
# premier run reel) : conserve tel que decide en clarify. `select_columns` DOIT
# inclure toutes les `merge_keys` sauf `cloud_provider` (ajoute par l'enveloppe) :
# `workspace_id` y figure bien.
WORKSPACES_LATEST_SPEC = IngestionSpec(
    source_table=SOURCE_ACCESS_WORKSPACES_LATEST,
    curated_table=CURATED_ACCESS_WORKSPACES_LATEST,
    merge_keys=WORKSPACES_LATEST_MERGE_KEYS,
    select_columns=("workspace_id", "workspace_name", "workspace_url", "status", "account_id"),
)


# Registre des tables ingerees, keye par un identifiant court et stable. Cet
# identifiant est la valeur `{{input}}` d'une iteration `for_each` du job : le
# job liste ces cles dans `inputs` et passe chacune via `--table`, ce qui
# selectionne UNE spec a ingerer par task parallele. L'ordre du dict est
# conserve (full load leger d'abord, grosses tables d'evenements ensuite).
SPECS: dict[str, IngestionSpec] = {
    "billing_usage": BILLING_USAGE_SPEC,
    "billing_list_prices": BILLING_LIST_PRICES_SPEC,
    "compute_clusters": COMPUTE_CLUSTERS_SPEC,
    "compute_node_timeline": COMPUTE_NODE_TIMELINE_SPEC,
    "access_audit": ACCESS_AUDIT_SPEC,
    "access_table_lineage": ACCESS_TABLE_LINEAGE_SPEC,
    "query_history": QUERY_HISTORY_SPEC,
    "compute_warehouses": WAREHOUSES_SPEC,
    "compute_warehouse_events": WAREHOUSE_EVENTS_SPEC,
    "compute_node_types": NODE_TYPES_SPEC,
    "lakeflow_jobs": LAKEFLOW_JOBS_SPEC,
    "lakeflow_pipelines": LAKEFLOW_PIPELINES_SPEC,
    "lakeflow_job_run_timeline": LAKEFLOW_JOB_RUN_TIMELINE_SPEC,
    "lakeflow_job_task_run_timeline": LAKEFLOW_JOB_TASK_RUN_TIMELINE_SPEC,
    "uc_tables": UC_TABLES_SPEC,
    "uc_table_tags": UC_TABLE_TAGS_SPEC,
    "uc_table_operations": UC_TABLE_OPERATIONS_SPEC,
    "access_workspaces_latest": WORKSPACES_LATEST_SPEC,
    "lakeflow_pipeline_update_timeline": LAKEFLOW_PIPELINE_UPDATE_TIMELINE_SPEC,
}

# Identifiants de tables, dans l'ordre : source de verite de la liste `inputs`
# du `for_each` cote job (garde le YAML et le code alignes).
SPEC_KEYS = tuple(SPECS)
