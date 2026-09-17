"""Resolution du grain STABLE (`job_id` / `dlt_pipeline_id`) depuis `cluster_id`.

Les clusters `cluster_type = 'JOB'` et `'PIPELINE'` sont ephemeres : leur
`cluster_id` change a chaque execution. Toute table gold au grain job ou
pipeline doit donc rattacher ces clusters a une cle stable.

Seuls les rollups EFFICACITE (`job_efficiency_daily`,
`pipeline_efficiency_daily`) ont encore besoin de cette resolution : leur source
(`node_timeline`) ne connait que le `cluster_id`. Les rollups COUT
(`pipeline_cost_daily`, et `job_cluster_cost_daily` depuis T001b) sont
BILLING-DIRECT : la cle stable est portee par la ligne de facturation
(`usage_metadata.job_id` / `.dlt_pipeline_id`), aucune resolution par le cluster
n'y intervient -- c'est ce qui leur permet d'inclure le compute SERVERLESS, qui
n'a aucun cluster a resoudre. Les deux chemins ont ete confrontes sans desaccord
sur donnee reelle (cf. les docstrings des deux builders cout), condition pour
que cout et utilisation restent comparables au meme `job_id`.

Ce qui reste partage entre cout et efficacite, c'est la resolution du NOM :
un meme `job_id` (ou `dlt_pipeline_id`) doit porter le meme libelle dans les
deux tables, sinon l'IHM affiche deux objets pour un seul.

Ce module ne contient que des fabriques de texte SQL (aucune dependance Spark,
aucun nom de table code en dur). Chaque fabrique rend un bloc CTE COMPLET,
`nom AS ( ... )` sans virgule finale, a inserer tel quel dans le `WITH` de
l'appelant :

    WITH {job_clusters_cte_sql(...)},
    ma_cte AS (...)

Les CTE de resolution de NOM (`jobs_as_of`/`submit_run_names`,
`pipelines_as_of`) sont parametrees par la CTE de grain qui les alimente
(`grain_cte`) et par l'alias de cette CTE dans les jointures (`grain_alias`),
seuls points de variation entre les builders cout et efficacite.
"""

from __future__ import annotations


def job_clusters_cte_sql(*, job_task_run_timeline_table: str, period_filter: str) -> str:
    """CTE `job_clusters` : couples distincts `(cluster_id, job_id)`.

    `curated_dbx_lakeflow_job_task_run_timeline` logue, pour chaque execution de
    tache, la colonne `compute` (`ARRAY<STRUCT<type, cluster_id, warehouse_id>>`)
    des clusters/warehouses utilises : c'est la seule lignee
    `cluster_id -> job_id` disponible.

    A joindre en `INNER JOIN` : un cluster JOB dont le `job_id` n'est pas
    resolvable (tache pas encore ingeree, decalage de watermark) doit etre
    EXCLU, jamais rattache a `job_id = NULL` -- la cle de merge des tables gold
    etant null-safe (`<=>` dans `pipelines.common.writers.merge_into_table`),
    toutes ces lignes fusionneraient en une seule ligne corrompue.

    `period_filter` : predicat `AND t.period_start_time >= DATE '...'` deja
    formate (cf. `sql_helpers.lower_bound_predicate`), chaine vide pour une
    lecture complete.
    """
    return f"""job_clusters AS (
        SELECT DISTINCT
            t.cloud_provider,
            t.workspace_id,
            c.cluster_id,
            t.job_id
        FROM {job_task_run_timeline_table} t
        LATERAL VIEW explode(t.compute) tc AS c
        WHERE c.cluster_id IS NOT NULL
        {period_filter}
    )"""


def pipeline_clusters_cte_sql(*, billing_usage_table: str, period_filter: str) -> str:
    """CTE `pipeline_clusters` : couples distincts `(cluster_id, dlt_pipeline_id)`.

    Mapping BILLING-DIRECT (cf. spec 024, R7, mesure en dev le 2026-09-09) : les
    lignes de facturation d'un pipeline DLT portent a la fois
    `usage_metadata.cluster_id` et `usage_metadata.dlt_pipeline_id`. Retenu
    contre deux alternatives : `system.lakeflow.pipeline_update_timeline` n'est
    lisible que cote AWS (l'efficacite DLT Azure serait perdue), et le parsing
    du nom `dlt-execution-<id>` repose sur un contrat non documente. Valide sans
    aucun desaccord (61 826 / 61 826) contre `pipeline_update_timeline`, et
    c'est la MEME source que le rollup cout (`pipeline_cost_daily`).

    Couverture mesuree : 99,84 % des clusters `PIPELINE` presents dans
    `cluster_efficiency_daily` (8 clusters AWS sur 5037 sans ligne de
    facturation portant un `cluster_id`) -> exclus par l'`INNER JOIN`, jamais
    rattaches par defaut. Les pipelines DLT SERVERLESS n'ont aucun cluster donc
    aucune ligne `node_timeline` : ils sont hors de portee de ce mapping (leur
    ligne de COUT reste produite par `pipeline_cost_daily`), ce n'est pas un
    defaut de couverture.

    Unicite : 0 violation mesuree (aucun `cluster_id` portant plusieurs
    `dlt_pipeline_id`). Si la source derivait, le `DISTINCT` ne dedoublonnerait
    pas -- un cluster partage compterait ses heures dans CHAQUE pipeline. Le
    grain de sortie resterait correct, mais la somme des `uptime_hours` sur
    plusieurs pipelines serait surestimee.
    """
    return f"""pipeline_clusters AS (
        SELECT DISTINCT
            u.cloud_provider,
            u.workspace_id,
            u.usage_metadata.cluster_id AS cluster_id,
            u.usage_metadata.dlt_pipeline_id AS dlt_pipeline_id
        FROM {billing_usage_table} u
        WHERE u.usage_metadata.dlt_pipeline_id IS NOT NULL
          AND u.usage_metadata.cluster_id IS NOT NULL
        {period_filter}
    )"""


def job_name_ctes_sql(
    *,
    grain_cte: str,
    lakeflow_jobs_table: str,
    job_run_timeline_table: str,
) -> str:
    """CTE `jobs_as_of` + `submit_run_names` : les deux sources du nom d'un job.

    `grain_cte` : CTE au grain `(cloud_provider, workspace_id, job_id,
    period_start)` qui alimente `jobs_as_of` (aliasee `a`).

    Nom au dernier etat connu (`change_time < period_start + 1 jour` : etat
    connu a un instant quelconque de `period_start`, pas seulement avant minuit
    - meme piege que `cluster_name` dans les tables gold clusters), A DEFAUT le
    nom du RUN (`job_run_timeline.run_name`, cf. `JOB_NAME_COALESCE_SQL`).

    Les deux sources sont DISJOINTES PAR CONSTRUCTION, mesure sur les deux
    clouds : un run declenche depuis une definition de job (`JOB_RUN`) a 100 %
    une ligne dans `curated_dbx_lakeflow_jobs` et `run_name` NULL ; un run
    soumis par API (`jobs/runs/submit`) n'a AUCUNE ligne dans
    `curated_dbx_lakeflow_jobs` (0 % des couples `(workspace_id, job_id)` y
    existent, par conception : il n'y a pas de definition a persister) et porte
    `run_name` a 100 %. Un `COALESCE` des deux est donc exact et SUFFIT : aucun
    predicat sur le type de run n'est necessaire (ce serait une fausse
    precision, perimee au prochain type ajoute par Databricks).
    Reste NULL apres repli : les runs lances depuis un notebook
    (`WORKFLOW_RUN`), qui n'ont de nom NULLE PART dans la source (0 sur
    192 902 lignes mesurees). C'est un plafond de la source, pas un defaut de
    resolution a corriger ici.
    """
    return f"""jobs_as_of AS (
        SELECT
            a.cloud_provider,
            a.workspace_id,
            a.job_id,
            a.period_start,
            j.name AS job_name
        FROM {grain_cte} a
        LEFT JOIN {lakeflow_jobs_table} j
          ON j.cloud_provider = a.cloud_provider
         AND j.workspace_id = a.workspace_id
         AND j.job_id = a.job_id
         AND j.change_time < a.period_start + INTERVAL 1 DAY
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY a.cloud_provider, a.workspace_id, a.job_id, a.period_start
            ORDER BY j.change_time DESC
        ) = 1
    ),
    submit_run_names AS (
        -- Nom des runs SOUMIS par API (`jobs/runs/submit`) : ils n'ont aucune
        -- ligne dans `curated_dbx_lakeflow_jobs`, leur seul nom est
        -- `run_name`. Le GROUP BY EST le dedoublonnage : sans lui, un job_id
        -- portant plusieurs run_id (2 cas mesures en dev) dupliquerait ses
        -- lignes de cout -- meme famille de tables que le fan-out x43
        -- documente dans `_lakeflow_latest_jobs()` de
        -- `pipelines/dlt_03_gold_layer.py`. Grain aligne sur `jobs_as_of` :
        -- pas d'`account_id` (absent de cette table gold, et redondant avec
        -- `workspace_id` qui n'appartient qu'a un compte).
        --
        -- VOLONTAIREMENT NON BORNEE sur la fenetre incrementale, contrairement
        -- aux CTE voisines : c'est un REFERENTIEL DE NOM, pas une source de
        -- fait. Un run soumis dont les lignes de timeline tombent juste hors
        -- fenetre doit quand meme nommer les lignes de cout reecrites ; borner
        -- ici (par mimetisme avec les CTE de fait voisines, elles bornees)
        -- laisserait `job_name` NULL sur ces jours-la.
        SELECT
            r.cloud_provider,
            r.workspace_id,
            r.job_id,
            MAX(r.run_name) AS run_name
        FROM {job_run_timeline_table} r
        WHERE r.run_name IS NOT NULL
        GROUP BY r.cloud_provider, r.workspace_id, r.job_id
    )"""


# Expression de nom a placer dans le SELECT qui porte `job_name_joins_sql`.
JOB_NAME_COALESCE_SQL = "COALESCE(ja.job_name, sr.run_name) AS job_name"


def job_name_joins_sql(grain_alias: str) -> str:
    """`LEFT JOIN` de `jobs_as_of` + `submit_run_names`, indentation a 8 espaces.

    `grain_alias` : alias, dans le SELECT appelant, de la CTE au grain job.
    Les deux jointures sont des `LEFT JOIN` : un job sans nom resolvable garde
    son `job_id` et sa mesure, il n'est jamais supprime.
    """
    return f"""LEFT JOIN jobs_as_of ja
          ON ja.cloud_provider = {grain_alias}.cloud_provider
         AND ja.workspace_id = {grain_alias}.workspace_id
         AND ja.job_id = {grain_alias}.job_id
         AND ja.period_start = {grain_alias}.period_start
        LEFT JOIN submit_run_names sr
          ON sr.cloud_provider = {grain_alias}.cloud_provider
         AND sr.workspace_id = {grain_alias}.workspace_id
         AND sr.job_id = {grain_alias}.job_id"""


def pipeline_name_cte_sql(*, grain_cte: str, lakeflow_pipelines_table: str) -> str:
    """CTE `pipelines_as_of` : nom du pipeline DLT au dernier etat connu.

    `grain_cte` : CTE au grain `(cloud_provider, workspace_id, dlt_pipeline_id,
    period_start)` qui l'alimente (aliasee `p`). `change_time < period_start +
    1 jour` : etat connu a un instant quelconque de `period_start`, pas
    seulement avant minuit.
    """
    return f"""pipelines_as_of AS (
        SELECT
            p.cloud_provider,
            p.workspace_id,
            p.dlt_pipeline_id,
            p.period_start,
            pl.name AS pipeline_name
        FROM {grain_cte} p
        LEFT JOIN {lakeflow_pipelines_table} pl
          ON pl.cloud_provider = p.cloud_provider
         AND pl.workspace_id = p.workspace_id
         AND pl.pipeline_id = p.dlt_pipeline_id
         AND pl.change_time < p.period_start + INTERVAL 1 DAY
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY p.cloud_provider, p.workspace_id, p.dlt_pipeline_id, p.period_start
            ORDER BY pl.change_time DESC
        ) = 1
    )"""


def pipeline_name_coalesce_sql(grain_alias: str) -> str:
    """Nom du pipeline, A DEFAUT son id (jamais NULL).

    Un pipeline dont aucune definition n'est encore ingeree dans
    `curated_dbx_lakeflow_pipelines` (retard de watermark) reste identifiable
    par son id plutot que d'apparaitre sans nom.
    """
    return f"COALESCE(pa.pipeline_name, {grain_alias}.dlt_pipeline_id) AS pipeline_name"


def pipeline_name_join_sql(grain_alias: str) -> str:
    """`LEFT JOIN pipelines_as_of`, indentation a 8 espaces (cf. `job_name_joins_sql`)."""
    return f"""LEFT JOIN pipelines_as_of pa
          ON pa.cloud_provider = {grain_alias}.cloud_provider
         AND pa.workspace_id = {grain_alias}.workspace_id
         AND pa.dlt_pipeline_id = {grain_alias}.dlt_pipeline_id
         AND pa.period_start = {grain_alias}.period_start"""
