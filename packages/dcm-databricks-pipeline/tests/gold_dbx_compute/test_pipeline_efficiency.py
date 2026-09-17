"""Tests de `pipeline_efficiency_daily` / `pipeline_efficiency_rolling`.

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`) : chaque builder
construit un unique `spark.sql(...)`, verifie ici via le texte SQL genere
(`FakeSpark`).

Pendant PIPELINE de `test_job_efficiency.py` : memes regles de derivation, grain
stable `dlt_pipeline_id` au lieu de `job_id`. Helpers dupliques volontairement
(cf. l'en-tete de ce fichier jumeau).
"""

from __future__ import annotations

import re
from datetime import date
from types import SimpleNamespace

from pipelines.gold_dbx_compute.pipeline_efficiency_daily import build_pipeline_efficiency_daily
from pipelines.gold_dbx_compute.pipeline_efficiency_rolling import (
    build_pipeline_efficiency_rolling,
)
from pipelines.gold_dbx_compute.specs import (
    PIPELINE_EFFICIENCY_DAILY_SPEC,
    PIPELINE_EFFICIENCY_ROLLING_SPEC,
)

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
    sentinel = fakes.DataFrame("pipeline_efficiency_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_pipeline_efficiency_daily(
        spark,
        cluster_efficiency_daily_table="it.sch.gold_dbx_compute_cluster_efficiency_daily",
        billing_usage_table="it.sch.curated_dbx_billing_usage",
        lakeflow_pipelines_table="it.sch.curated_dbx_lakeflow_pipelines",
        lower_bound=lower_bound,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0]


def _rolling_query(fakes: SimpleNamespace) -> str:
    sentinel = fakes.DataFrame("pipeline_efficiency_rolling_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_pipeline_efficiency_rolling(
        spark,
        pipeline_efficiency_daily_table="it.sch.gold_dbx_compute_pipeline_efficiency_daily",
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

    Le SELECT final est le seul indente a 4 espaces (ceux des CTE sont a 8).
    Lignes de commentaire et lignes intermediaires de `CASE` ignorees : seul
    compte l'alias (`... AS nom`) ou la reference simple (`m.nom`).
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


def test_pipeline_efficiency_daily_reads_cluster_efficiency_daily_not_cost(
    fakes: SimpleNamespace,
) -> None:
    query = _daily_query(fakes, lower_bound=None)
    assert "it.sch.gold_dbx_compute_cluster_efficiency_daily" in query
    assert "cost_usd" not in query
    assert "dbu_quantity" not in query


def test_pipeline_efficiency_daily_keeps_only_pipeline_clusters(fakes: SimpleNamespace) -> None:
    query = _daily_query(fakes, lower_bound=None)
    assert "WHERE ce.cluster_type = 'PIPELINE'" in query
    # PIEGE : cluster_efficiency_daily ne doit JAMAIS etre filtree sur
    # ALL_PURPOSE (seule sa variante _rolling l'est, cf. SC-001).
    assert "ALL_PURPOSE" not in query


def test_pipeline_efficiency_daily_resolves_the_pipeline_from_billing_metadata(
    fakes: SimpleNamespace,
) -> None:
    # MEME resolution que pipeline_cost_daily (R7) : cout et efficacite ne
    # peuvent pas rattacher un meme cluster a deux pipelines differents.
    query = _daily_query(fakes, lower_bound=None)
    assert "u.usage_metadata.dlt_pipeline_id AS dlt_pipeline_id" in query
    assert "WHERE u.usage_metadata.dlt_pipeline_id IS NOT NULL" in query
    assert "AND u.usage_metadata.cluster_id IS NOT NULL" in query


def test_pipeline_efficiency_daily_excludes_unresolvable_clusters_with_an_inner_join(
    fakes: SimpleNamespace,
) -> None:
    # INNER JOIN DELIBERE : la cle de merge gold est null-safe (`<=>`), un
    # dlt_pipeline_id NULL ferait fusionner toutes les lignes non resolues en
    # UNE ligne corrompue (8 clusters AWS sur 5037 mesures).
    query = _daily_query(fakes, lower_bound=None)
    assert "JOIN pipeline_clusters pc" in query
    assert "LEFT JOIN pipeline_clusters" not in query


def test_pipeline_efficiency_daily_groups_on_the_stable_pipeline_grain(
    fakes: SimpleNamespace,
) -> None:
    query = _daily_query(fakes, lower_bound=None)
    assert "GROUP BY d.cloud_provider, d.workspace_id, d.dlt_pipeline_id, d.period_start" in query
    assert "COUNT(DISTINCT d.cluster_id) AS cluster_count" in query


def test_pipeline_efficiency_daily_weights_every_average_by_uptime(
    fakes: SimpleNamespace,
) -> None:
    agg = _cte_body(_daily_query(fakes, lower_bound=None), "agg")
    for column in WEIGHTED_COLUMNS:
        assert WEIGHTED_BY_UPTIME.format(col=column) in agg, column
        assert f"AVG(d.{column})" not in agg, column


def test_pipeline_efficiency_daily_recomputes_p95_from_summed_histograms(
    fakes: SimpleNamespace,
) -> None:
    query = _daily_query(fakes, lower_bound=None)
    agg = _cte_body(query, "agg")
    assert "aggregate(collect_list(d.cpu_util_hist)" in agg
    assert "aggregate(collect_list(d.mem_util_hist)" in agg
    with_metrics = _cte_body(query, "with_metrics")
    assert "g.cpu_util_hist" in with_metrics
    assert "AS cpu_util_p95_pct" in with_metrics
    assert "AS mem_util_p95_pct" in with_metrics
    # Un p95 ne se moyenne pas : le p95 quotidien de la source n'est jamais lu.
    assert "d.cpu_util_p95_pct" not in query
    assert "d.mem_util_p95_pct" not in query


def test_pipeline_efficiency_daily_sums_additive_metrics_and_maxes_worker_peak(
    fakes: SimpleNamespace,
) -> None:
    agg = _cte_body(_daily_query(fakes, lower_bound=None), "agg")
    for column in ADDITIVE_COLUMNS:
        assert f"SUM(d.{column}) AS {column}" in agg, column
    assert "MAX(d.worker_count_max) AS worker_count_max" in agg


def test_pipeline_efficiency_daily_takes_attributes_from_the_most_representative_cluster(
    fakes: SimpleNamespace,
) -> None:
    latest_attrs = _cte_body(_daily_query(fakes, lower_bound=None), "latest_attrs")
    assert (
        "PARTITION BY cloud_provider, workspace_id, dlt_pipeline_id, period_start" in latest_attrs
    )
    assert "ORDER BY uptime_hours DESC, cluster_id DESC" in latest_attrs


def test_pipeline_efficiency_daily_falls_back_to_the_id_when_the_name_is_unknown(
    fakes: SimpleNamespace,
) -> None:
    # Un pipeline dont la definition n'est pas encore ingeree reste
    # identifiable, comme dans pipeline_cost_daily.
    query = _daily_query(fakes, lower_bound=None)
    assert "COALESCE(pa.pipeline_name, g.dlt_pipeline_id) AS pipeline_name" in query


def test_pipeline_efficiency_daily_full_run_has_no_lower_bound_filter(
    fakes: SimpleNamespace,
) -> None:
    assert "DATE '" not in _daily_query(fakes, lower_bound=None)


def test_pipeline_efficiency_daily_incremental_run_buffers_only_the_mapping_read(
    fakes: SimpleNamespace,
) -> None:
    query = _daily_query(fakes, lower_bound=date(2026, 8, 14))
    # Mapping lu avec 1 jour de tampon : une mise a jour demarree avant minuit
    # peut n'avoir de ligne de facturation portant son cluster_id que la veille.
    assert "AND u.usage_date >= DATE '2026-08-13'" in query
    # La sortie reste bornee a lower_bound.
    assert "AND ce.period_start >= DATE '2026-08-14'" in query
    assert "AND ce.period_start >= DATE '2026-08-13'" not in query


def test_pipeline_efficiency_daily_outputs_exactly_the_documented_columns(
    fakes: SimpleNamespace,
) -> None:
    # Verrou builder <-> spec : `merge_into_table` emet un ALTER COLUMN COMMENT
    # par entree de `column_comments` ; une cle orpheline casse l'ecriture au
    # runtime, pas au test.
    columns = _output_columns(_daily_query(fakes, lower_bound=None))
    assert len(columns) == len(set(columns))
    assert set(columns) == set(PIPELINE_EFFICIENCY_DAILY_SPEC.column_comments)
    assert columns[:3] == ["cloud_provider", "workspace_id", "dlt_pipeline_id"]
    assert "cpu_util_hist" in columns
    assert "mem_util_hist" in columns


def test_pipeline_efficiency_daily_exposes_no_zombie_and_no_cluster_identity(
    fakes: SimpleNamespace,
) -> None:
    columns = _output_columns(_daily_query(fakes, lower_bound=None))
    for absent in ("is_zombie", "cluster_id", "cluster_name", "cluster_type"):
        assert absent not in columns, absent


# --- Fenetres glissantes -----------------------------------------------------


def test_pipeline_efficiency_rolling_reads_only_the_daily_table(fakes: SimpleNamespace) -> None:
    query = _rolling_query(fakes)
    assert "it.sch.gold_dbx_compute_pipeline_efficiency_daily" in query
    assert "curated_" not in query
    assert "cluster_type" not in query


def test_pipeline_efficiency_rolling_materializes_the_four_windows_as_of_the_last_day(
    fakes: SimpleNamespace,
) -> None:
    query = _rolling_query(fakes)
    assert "explode(array(1, 7, 30, 90)) AS window_days" in query
    assert "SELECT MAX(period_start) AS as_of_date FROM daily" in query
    assert "date_add(a.as_of_date, -(w.window_days - 1)) AS window_start" in query


def test_pipeline_efficiency_rolling_weights_averages_and_recomputes_p95(
    fakes: SimpleNamespace,
) -> None:
    query = _rolling_query(fakes)
    agg = _cte_body(query, "agg")
    for column in WEIGHTED_COLUMNS:
        assert WEIGHTED_BY_UPTIME.format(col=column) in agg, column
    assert "aggregate(collect_list(d.cpu_util_hist)" in agg
    assert "d.cpu_util_p95_pct" not in query
    with_metrics = _cte_body(query, "with_metrics")
    assert "AS cpu_util_p95_pct" in with_metrics
    assert "AS mem_util_p95_pct" in with_metrics


def test_pipeline_efficiency_rolling_sums_cluster_count_over_the_window(
    fakes: SimpleNamespace,
) -> None:
    # Exact : un cluster PIPELINE par mise a jour, jamais reutilise d'un jour a
    # l'autre - les ensembles quotidiens sont disjoints par construction.
    assert "SUM(d.cluster_count) AS cluster_count" in _cte_body(_rolling_query(fakes), "agg")


def test_pipeline_efficiency_rolling_compares_the_previous_window_with_the_same_formula(
    fakes: SimpleNamespace,
) -> None:
    prev_agg = _cte_body(_rolling_query(fakes), "prev_agg")
    expected_idle = WEIGHTED_BY_UPTIME.format(col="idle_pct").replace(
        "AS idle_pct", "AS idle_pct_prev_window"
    )
    assert expected_idle in prev_agg
    assert "d.period_start > date_add(a.as_of_date, -2 * w.window_days)" in prev_agg
    assert "d.period_start <= date_add(a.as_of_date, -w.window_days)" in prev_agg
    # NULL et jamais 0 : aucun COALESCE sur les colonnes de fenetre
    # precedente, un 0 se lisant "allume zero heure" donc une chute de 100 %.
    assert "COALESCE(p." not in _rolling_query(fakes)


def test_pipeline_efficiency_rolling_joins_the_previous_window_on_window_days(
    fakes: SimpleNamespace,
) -> None:
    # `prev_agg` porte une ligne par pipeline ET par fenetre : joindre sans
    # window_days multiplierait chaque ligne de sortie par 4.
    assert "AND p.window_days = m.window_days" in _rolling_query(fakes)


def test_pipeline_efficiency_rolling_drops_pipelines_absent_from_the_current_window(
    fakes: SimpleNamespace,
) -> None:
    assert "WHERE m.uptime_hours > 0" in _rolling_query(fakes)


def test_pipeline_efficiency_rolling_outputs_exactly_the_documented_columns(
    fakes: SimpleNamespace,
) -> None:
    columns = _output_columns(_rolling_query(fakes))
    assert len(columns) == len(set(columns))
    assert set(columns) == set(PIPELINE_EFFICIENCY_ROLLING_SPEC.column_comments)
    assert columns[:4] == ["cloud_provider", "workspace_id", "dlt_pipeline_id", "window_days"]
    # Histogrammes internes a la CTE (ils ne servent qu'au recalcul du p95).
    assert "cpu_util_hist" not in columns
    assert "mem_util_hist" not in columns
    for absent in ("is_zombie", "cluster_id", "cluster_name", "cluster_type", "period_start"):
        assert absent not in columns, absent


def test_pipeline_efficiency_uses_the_same_rightsizing_thresholds_everywhere(
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
