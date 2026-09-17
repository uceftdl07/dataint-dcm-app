"""gold_dbx_workflow_never_run — jobs definis sans AUCUN run observe (epic 009 addendum).

Contexte (cf. echange support 2026-09-15) : aucune table gold existante ne
porte l'information "jamais execute" -- toutes derivent de
`curated_dbx_lakeflow_job_run_timeline` (le LOG des runs), un job qui n'y a
jamais aucune ligne n'y produit donc simplement AUCUNE ligne, dans AUCUNE table
`gold_dbx_workflow_*`. Ce builder comble ce trou par un ANTI-JOIN explicite
entre le REGISTRE des definitions de job (`curated_dbx_lakeflow_jobs`, full
load, historique complet depuis 2024-01-15) et les runs connus.

ATTENTION -- limite honnete, a ne pas masquer a l'IHM : `job_run_timeline` est
ingere en INCREMENTAL avec un backfill initial de `INITIAL_BACKFILL_DAYS` (30
jours, cf. `pipelines.system_tables.specs`), pas en full load comme le
registre. Un job cree avant cette fenetre et dont le DERNIER run remonte a
avant elle apparait donc ICI comme "jamais execute" alors qu'il a bel et bien
tourne un jour -- c'est en realite "aucun run observe depuis
`runs_observed_since`", pas "jamais execute depuis sa creation". D'ou la
colonne `runs_observed_since` (borne MIN reelle de la table de runs, jamais
une constante codee en dur) : elle porte cette limite explicitement plutot que
de la cacher, exactement comme `job_name_ctes_sql` documente ses propres trous
de resolution (cf. `pipelines.gold_dbx_compute.grain_resolution`).

Jobs SUPPRIMES (`delete_time IS NOT NULL`) exclus : un job supprime sans avoir
jamais tourne n'est plus un signal actionnable pour l'utilisateur.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyspark.sql.functions import col, current_timestamp, row_number
from pyspark.sql.functions import min as spark_min
from pyspark.sql.window import Window

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession

__all__ = ["build_never_run"]


def build_never_run(
    spark: SparkSession,
    *,
    jobs_table: str,
    job_run_timeline_table: str,
) -> DataFrame:
    """Jobs actifs (non supprimes) absents de `job_run_timeline` (aucun run connu).

    Ne lit QUE `jobs_table` (registre) et `job_run_timeline_table` (runs) :
    pas de `job_task_run_timeline`/`dim_dbx_workspace`, ce builder ne calcule
    ni duree ni statut, seulement une absence de run.
    """
    jobs = spark.read.table(jobs_table)
    runs = spark.read.table(job_run_timeline_table)

    # Dernier etat connu par job (le registre est un LOG de versions, cf.
    # `LAKEFLOW_JOBS_MERGE_KEYS` incluant `change_time`) : un job supprime
    # entre-temps (`delete_time` renseigne sur sa derniere version) est exclu.
    latest_version = Window.partitionBy(
        col("cloud_provider"), col("account_id"), col("workspace_id"), col("job_id")
    ).orderBy(col("change_time").desc())

    latest_jobs = (
        jobs.withColumn("_rn", row_number().over(latest_version))
        .filter((col("_rn") == 1) & col("delete_time").isNull())
        .select(
            col("cloud_provider"),
            col("account_id"),
            col("workspace_id"),
            col("job_id").alias("workflow_id"),
            col("name").alias("workflow_name"),
            col("change_time").alias("last_definition_change_time"),
        )
    )

    # Cle des jobs AYANT au moins 1 run connu -- unbounded (pas de fenetre),
    # cette table est un snapshot recalcule integralement a chaque run (comme
    # les 8 autres tables de ce domaine, `watermark_column=None`).
    runs_seen = runs.select(
        col("cloud_provider"),
        col("account_id"),
        col("workspace_id"),
        col("job_id").alias("workflow_id"),
    ).distinct()

    # Borne reelle de couverture de `job_run_timeline`, JAMAIS une constante :
    # cf. limite documentee dans le docstring module.
    observed_since = runs.select(spark_min(col("period_start_time")).alias("runs_observed_since"))

    never_run = latest_jobs.join(
        runs_seen,
        on=["cloud_provider", "account_id", "workspace_id", "workflow_id"],
        how="left_anti",
    )

    return never_run.crossJoin(observed_since).withColumn(
        "_generated_at", current_timestamp()
    )
