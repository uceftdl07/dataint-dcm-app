"""Tests de `job_efficiency_daily` / `job_efficiency_rolling` (regles de derivation).

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`) : chaque builder
construit un unique `spark.sql(...)`, verifie ici via le texte SQL genere
(`FakeSpark`).

Le pendant PIPELINE de ces tests vit dans `test_pipeline_efficiency.py` : les
deux fichiers verifient les MEMES regles de derivation sur deux grains stables
differents. Les helpers sont volontairement dupliques entre les deux plutot que
partages par un module `tests.*` importe, pour la meme raison que les fakes de
`tests/conftest.py` (resolution ambigue du package `tests` entre les packages du
monorepo).
"""

from __future__ import annotations

import re
from datetime import date
from types import SimpleNamespace

from pipelines.gold_dbx_compute.job_efficiency_daily import build_job_efficiency_daily
from pipelines.gold_dbx_compute.job_efficiency_rolling import build_job_efficiency_rolling
from pipelines.gold_dbx_compute.specs import (
    JOB_EFFICIENCY_DAILY_SPEC,
    JOB_EFFICIENCY_ROLLING_SPEC,
)

# Moyenne ponderee par le temps allume, sans l'alias : toutes les moyennes de ces
# tables partagent cette formule (cf. cluster_efficiency_rolling). Un cluster
# allume 5 minutes ne doit pas peser autant qu'un cluster allume 5 heures.
WEIGHTED_BY_UPTIME = (
    "SUM(d.{col} * d.uptime_hours)\n"
    "                / NULLIF(SUM(CASE WHEN d.{col} IS NOT NULL\n"
    "                                  THEN d.uptime_hours END), 0) AS {col}"
)

WEIGHTED_COLUMNS = (
    "cpu_util_avg_pct",
    "mem_util_avg_pct",
    "cpu_wait_avg_pct",
    "worker_count_avg",
    "idle_pct",
)

ADDITIVE_COLUMNS = (
    "uptime_hours",
    "active_hours",
    "autoscale_oscillation",
    "estimated_savings_usd",
)

# Seuils de rightsizing, texte partage : ils DOIVENT rester identiques a ceux du
# grain cluster (cluster_efficiency_daily/_rolling) et entre le quotidien et les
# fenetres, sinon un meme calcul serait diagnostique OVER dans une table et
# OPTIMAL dans l'autre.
UTILIZATION_STATUS_CASE = """        CASE
            WHEN m.cpu_util_p95_pct < 40 AND m.mem_util_p95_pct < 50 THEN 'OVER'
            WHEN m.cpu_util_p95_pct > 85 OR m.mem_util_p95_pct > 85 THEN 'UNDER'
            ELSE 'OPTIMAL'
        END AS utilization_status"""


def _daily_query(fakes: SimpleNamespace, lower_bound: date | None) -> str:
    sentinel = fakes.DataFrame("job_efficiency_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_job_efficiency_daily(
        spark,
        cluster_efficiency_daily_table="it.sch.gold_dbx_compute_cluster_efficiency_daily",
        job_task_run_timeline_table="it.sch.curated_dbx_lakeflow_job_task_run_timeline",
        job_run_timeline_table="it.sch.curated_dbx_lakeflow_job_run_timeline",
        lakeflow_jobs_table="it.sch.curated_dbx_lakeflow_jobs",
        lower_bound=lower_bound,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0]


def _rolling_query(fakes: SimpleNamespace) -> str:
    sentinel = fakes.DataFrame("job_efficiency_rolling_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_job_efficiency_rolling(
        spark,
        job_efficiency_daily_table="it.sch.gold_dbx_compute_job_efficiency_daily",
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0]


def _cte_body(query: str, name: str) -> str:
    """Corps de la CTE `name` (cf. `test_cluster_efficiency_rolling._cte_body`)."""
    after = query.split(f" {name} AS (", 1)[1]
    return after.split("\n    )", 1)[0]


def _output_columns(query: str) -> list[str]:
    """Colonnes du SELECT final, dans l'ordre du texte genere.

    Le SELECT final est le seul indente a 4 espaces (ceux des CTE sont a 8), ce
    qui permet de l'isoler sans parser le SQL. Les lignes de commentaire et les
    lignes intermediaires d'un `CASE` sont ignorees : seul compte l'alias
    (`... AS nom`) ou la reference simple (`m.nom`).
    """
    tail = query.rsplit("\n    SELECT\n", 1)[1].split("\n    FROM with_metrics", 1)[0]
    columns: list[str] = []
    for raw in tail.splitlines():
        line = raw.strip().rstrip(",")
        if not line or line.startswith("--"):
            continue
        if " AS " in line:
            columns.append(line.rsplit(" AS ", 1)[1])
        elif re.fullmatch(r"\w+\.\w+", line):
            columns.append(line.split(".", 1)[1])
    return columns


# --- Table quotidienne -------------------------------------------------------


def test_job_efficiency_daily_reads_cluster_efficiency_daily_not_cost(
    fakes: SimpleNamespace,
) -> None:
    query = _daily_query(fakes, lower_bound=None)
    assert "it.sch.gold_dbx_compute_cluster_efficiency_daily" in query
    # Aucune colonne de cout : cette table repond "la taille est-elle la bonne",
    # pas "combien ca coute" (cf. gold_dbx_compute_job_cluster_cost_daily).
    assert "cost_usd" not in query
    assert "dbu_quantity" not in query


def test_job_efficiency_daily_keeps_only_job_clusters(fakes: SimpleNamespace) -> None:
    query = _daily_query(fakes, lower_bound=None)
    assert "WHERE ce.cluster_type = 'JOB'" in query
    # PIEGE : la source cluster_efficiency_daily ne doit JAMAIS etre filtree sur
    # ALL_PURPOSE (seule sa variante _rolling l'est, cf. SC-001), sinon ce
    # rollup se vide silencieusement.
    assert "ALL_PURPOSE" not in query


def test_job_efficiency_daily_excludes_unresolvable_clusters_with_an_inner_join(
    fakes: SimpleNamespace,
) -> None:
    # INNER JOIN DELIBERE : la cle de merge gold est null-safe (`<=>`), donc un
    # `job_id` NULL ne resterait pas isole - toutes les lignes non resolues
    # fusionneraient en UNE ligne corrompue.
    query = _daily_query(fakes, lower_bound=None)
    assert "JOIN job_clusters jc" in query
    assert "LEFT JOIN job_clusters" not in query
    assert "LATERAL VIEW explode(t.compute) tc AS c" in query


def test_job_efficiency_daily_groups_on_the_stable_job_grain(fakes: SimpleNamespace) -> None:
    query = _daily_query(fakes, lower_bound=None)
    assert "GROUP BY d.cloud_provider, d.workspace_id, d.job_id, d.period_start" in query
    # Le cluster ephemere disparait du grain : il ne subsiste que comme compte.
    assert "COUNT(DISTINCT d.cluster_id) AS cluster_count" in query


def test_job_efficiency_daily_weights_every_average_by_uptime(fakes: SimpleNamespace) -> None:
    agg = _cte_body(_daily_query(fakes, lower_bound=None), "agg")
    for column in WEIGHTED_COLUMNS:
        assert WEIGHTED_BY_UPTIME.format(col=column) in agg, column
    # Aucune moyenne simple ne doit subsister sur ces colonnes.
    for column in WEIGHTED_COLUMNS:
        assert f"AVG(d.{column})" not in agg, column


def test_job_efficiency_daily_recomputes_p95_from_summed_histograms(
    fakes: SimpleNamespace,
) -> None:
    query = _daily_query(fakes, lower_bound=None)
    agg = _cte_body(query, "agg")
    # Histogrammes sommes bucket par bucket dans `agg`...
    assert "aggregate(collect_list(d.cpu_util_hist)" in agg
    assert "aggregate(collect_list(d.mem_util_hist)" in agg
    # ... puis percentile recalcule dessus dans `with_metrics`. Un p95 ne se
    # moyenne pas : la source cluster_efficiency_daily expose cpu_util_p95_pct,
    # il ne doit jamais etre agrege directement.
    with_metrics = _cte_body(query, "with_metrics")
    assert "g.cpu_util_hist" in with_metrics
    assert "AS cpu_util_p95_pct" in with_metrics
    assert "AS mem_util_p95_pct" in with_metrics
    for forbidden in ("AVG(d.cpu_util_p95_pct)", "SUM(d.cpu_util_p95_pct)", "d.cpu_util_p95_pct"):
        assert forbidden not in query, forbidden


def test_job_efficiency_daily_sums_additive_metrics_and_maxes_worker_peak(
    fakes: SimpleNamespace,
) -> None:
    agg = _cte_body(_daily_query(fakes, lower_bound=None), "agg")
    for column in ADDITIVE_COLUMNS:
        assert f"SUM(d.{column}) AS {column}" in agg, column
    assert "MAX(d.worker_count_max) AS worker_count_max" in agg


def test_job_efficiency_daily_takes_attributes_from_the_most_representative_cluster(
    fakes: SimpleNamespace,
) -> None:
    # Un job peut avoir tourne sur plusieurs clusters le meme jour et la source
    # n'a AUCUN horodatage intra-journalier : le cluster retenu est celui reste
    # allume le plus longtemps, `cluster_id` ne servant qu'a departager.
    latest_attrs = _cte_body(_daily_query(fakes, lower_bound=None), "latest_attrs")
    assert "PARTITION BY cloud_provider, workspace_id, job_id, period_start" in latest_attrs
    assert "ORDER BY uptime_hours DESC, cluster_id DESC" in latest_attrs
    for attr in (
        "driver_node_type",
        "worker_node_type",
        "autoscale_enabled",
        "autoscale_min_workers",
        "autoscale_max_workers",
        "configured_worker_count",
        "recommended_node_type",
    ):
        assert attr in latest_attrs, attr


def test_job_efficiency_daily_full_run_has_no_lower_bound_filter(fakes: SimpleNamespace) -> None:
    query = _daily_query(fakes, lower_bound=None)
    assert "DATE '" not in query


def test_job_efficiency_daily_incremental_run_buffers_only_the_mapping_read(
    fakes: SimpleNamespace,
) -> None:
    query = _daily_query(fakes, lower_bound=date(2026, 8, 14))
    # Mapping cluster_id -> job_id lu avec 1 jour de tampon : une tache demarree
    # avant minuit peut n'avoir de ligne de timeline que la veille.
    assert "AND t.period_start_time >= DATE '2026-08-13'" in query
    # La SORTIE, elle, reste bornee a lower_bound (aucun self-join J-1 ici).
    assert "AND ce.period_start >= DATE '2026-08-14'" in query
    assert "AND ce.period_start >= DATE '2026-08-13'" not in query


def test_job_efficiency_daily_outputs_exactly_the_documented_columns(
    fakes: SimpleNamespace,
) -> None:
    # Verrou builder <-> spec : `merge_into_table` emet un ALTER COLUMN COMMENT
    # par entree de `column_comments`, donc une cle qui n'est pas une colonne de
    # sortie (ou l'inverse) casse l'ecriture au runtime, pas au test.
    columns = _output_columns(_daily_query(fakes, lower_bound=None))
    assert len(columns) == len(set(columns))
    assert set(columns) == set(JOB_EFFICIENCY_DAILY_SPEC.column_comments)
    # Les cles de merge ouvrent le SELECT (lisibilite du MERGE genere).
    assert columns[:3] == ["cloud_provider", "workspace_id", "job_id"]
    # Histogrammes EXPOSES : ils alimentent les percentiles du _rolling.
    assert "cpu_util_hist" in columns
    assert "mem_util_hist" in columns


def test_job_efficiency_daily_exposes_no_zombie_and_no_cluster_identity(
    fakes: SimpleNamespace,
) -> None:
    # `is_zombie` serait `false` partout a ce grain (un cluster JOB s'arrete
    # avec sa tache) et se lirait comme un controle qui passe.
    columns = _output_columns(_daily_query(fakes, lower_bound=None))
    for absent in ("is_zombie", "cluster_id", "cluster_name", "cluster_type"):
        assert absent not in columns, absent


# --- Fenetres glissantes -----------------------------------------------------


def test_job_efficiency_rolling_reads_only_the_daily_table(fakes: SimpleNamespace) -> None:
    query = _rolling_query(fakes)
    assert "it.sch.gold_dbx_compute_job_efficiency_daily" in query
    # Aucune relecture curated : la resolution du grain a deja eu lieu.
    assert "curated_" not in query
    # Aucun filtre de type : la source est deja restreinte aux clusters JOB.
    assert "cluster_type" not in query


def test_job_efficiency_rolling_materializes_the_four_windows_as_of_the_last_day(
    fakes: SimpleNamespace,
) -> None:
    query = _rolling_query(fakes)
    assert "explode(array(1, 7, 30, 90)) AS window_days" in query
    assert "SELECT MAX(period_start) AS as_of_date FROM daily" in query
    assert "date_add(a.as_of_date, -(w.window_days - 1)) AS window_start" in query


def test_job_efficiency_rolling_weights_averages_and_recomputes_p95(
    fakes: SimpleNamespace,
) -> None:
    query = _rolling_query(fakes)
    agg = _cte_body(query, "agg")
    for column in WEIGHTED_COLUMNS:
        assert WEIGHTED_BY_UPTIME.format(col=column) in agg, column
    # Percentiles de la fenetre : histogrammes quotidiens sommes, jamais des
    # percentiles quotidiens moyennes.
    assert "aggregate(collect_list(d.cpu_util_hist)" in agg
    assert "d.cpu_util_p95_pct" not in query
    with_metrics = _cte_body(query, "with_metrics")
    assert "AS cpu_util_p95_pct" in with_metrics
    assert "AS mem_util_p95_pct" in with_metrics


def test_job_efficiency_rolling_sums_cluster_count_over_the_window(
    fakes: SimpleNamespace,
) -> None:
    # Exact (et non surestime) parce que les clusters JOB sont ephemeres : un
    # cluster_id distinct par execution, jamais reutilise d'un jour a l'autre.
    assert "SUM(d.cluster_count) AS cluster_count" in _cte_body(_rolling_query(fakes), "agg")


def test_job_efficiency_rolling_compares_the_previous_window_with_the_same_formula(
    fakes: SimpleNamespace,
) -> None:
    query = _rolling_query(fakes)
    prev_agg = _cte_body(query, "prev_agg")
    # Fenetre precedente de MEME longueur, formule d'idle_pct identique a `agg`
    # (au caractere pres) : sinon les deux colonnes ne sont pas comparables.
    expected_idle = WEIGHTED_BY_UPTIME.format(col="idle_pct").replace(
        "AS idle_pct", "AS idle_pct_prev_window"
    )
    assert expected_idle in prev_agg
    assert "d.period_start > date_add(a.as_of_date, -2 * w.window_days)" in prev_agg
    assert "d.period_start <= date_add(a.as_of_date, -w.window_days)" in prev_agg
    # NULL et jamais 0 : aucun COALESCE sur les colonnes de fenetre
    # precedente, un 0 se lisant "allume zero heure" donc une chute de 100 %.
    assert "COALESCE(p." not in _rolling_query(fakes)


def test_job_efficiency_rolling_joins_the_previous_window_on_window_days(
    fakes: SimpleNamespace,
) -> None:
    # `prev_agg` porte une ligne par job ET par fenetre : joindre sans
    # window_days multiplierait chaque ligne de sortie par 4.
    query = _rolling_query(fakes)
    assert "AND p.window_days = m.window_days" in query


def test_job_efficiency_rolling_drops_jobs_absent_from_the_current_window(
    fakes: SimpleNamespace,
) -> None:
    # Sans ce filtre, un job actif seulement dans la fenetre PRECEDENTE
    # apparaitrait avec 0 h courante et ses seules colonnes _prev_window.
    assert "WHERE m.uptime_hours > 0" in _rolling_query(fakes)


def test_job_efficiency_rolling_outputs_exactly_the_documented_columns(
    fakes: SimpleNamespace,
) -> None:
    columns = _output_columns(_rolling_query(fakes))
    assert len(columns) == len(set(columns))
    assert set(columns) == set(JOB_EFFICIENCY_ROLLING_SPEC.column_comments)
    assert columns[:4] == ["cloud_provider", "workspace_id", "job_id", "window_days"]
    # Les histogrammes restent INTERNES a la CTE (ils ne servent qu'au p95).
    assert "cpu_util_hist" not in columns
    assert "mem_util_hist" not in columns
    for absent in ("is_zombie", "cluster_id", "cluster_name", "cluster_type", "period_start"):
        assert absent not in columns, absent


def test_job_efficiency_uses_the_same_rightsizing_thresholds_everywhere(
    fakes: SimpleNamespace,
) -> None:
    daily = _daily_query(fakes, lower_bound=None)
    rolling = _rolling_query(fakes)
    for query in (daily, rolling):
        assert UTILIZATION_STATUS_CASE in query
        # Recommandation lisible derivee du MEME diagnostic, avec le repli
        # explicite quand aucun node type plus petit n'existe.
        assert "THEN concat('Reduire vers ', la.recommended_node_type)" in query
        assert "aucun node type plus petit disponible" in query
