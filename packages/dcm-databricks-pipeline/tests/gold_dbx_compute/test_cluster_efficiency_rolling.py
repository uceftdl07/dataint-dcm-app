"""Tests de `pipelines.gold_dbx_compute.cluster_efficiency_rolling` (regles de derivation).

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`) :
`build_cluster_efficiency_rolling` construit un unique `spark.sql(...)`, verifie
ici via le texte SQL genere (`FakeSpark`).
"""

from __future__ import annotations

from types import SimpleNamespace

from pipelines.gold_dbx_compute.cluster_efficiency_rolling import (
    build_cluster_efficiency_rolling,
)
from pipelines.gold_dbx_compute.specs import CLUSTER_EFFICIENCY_ROLLING_SPEC

# Moyenne ponderee par le temps allume, sans l'alias : la fenetre courante et la
# fenetre precedente DOIVENT partager cette formule au caractere pres, sinon les
# deux colonnes ne sont pas comparables terme a terme.
WEIGHTED_IDLE_PCT = (
    "SUM(d.idle_pct * d.uptime_hours)\n"
    "                / NULLIF(SUM(CASE WHEN d.idle_pct IS NOT NULL\n"
    "                                  THEN d.uptime_hours END), 0) AS "
)

# Colonnes de configuration reprises du dernier jour connu (CTE latest_attrs).
CONFIG_ATTRS = (
    "cluster_name",
    "autoscale_enabled",
    "autoscale_min_workers",
    "autoscale_max_workers",
    "configured_worker_count",
)


def _rolling_query(fakes: SimpleNamespace) -> tuple[str, object]:
    sentinel = fakes.DataFrame("cluster_efficiency_rolling_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_cluster_efficiency_rolling(
        spark,
        cluster_efficiency_daily_table="it.sch.gold_dbx_compute_cluster_efficiency_daily",
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0], result


def _cte_body(query: str, name: str) -> str:
    """Corps de la CTE `name`, jusqu'a sa parenthese fermante.

    L'espace avant le nom distingue `agg AS (` de `prev_agg AS (` tout en
    acceptant la premiere CTE, precedee de `WITH`.
    """
    after = query.split(f" {name} AS (", 1)[1]
    return after.split("\n    )", 1)[0]


def test_efficiency_rolling_reads_only_daily_table_no_curated(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "it.sch.gold_dbx_compute_cluster_efficiency_daily" in query
    assert "curated_" not in query


def test_efficiency_rolling_keeps_only_all_purpose_clusters(
    fakes: SimpleNamespace,
) -> None:
    # SC-001 : la liste gold ne retient que les clusters ALL_PURPOSE ; les
    # cluster_id ephemeres JOB/PIPELINE sont exclus des la CTE daily.
    query, _ = _rolling_query(fakes)
    assert (
        "FROM it.sch.gold_dbx_compute_cluster_efficiency_daily\n"
        "        WHERE cluster_type = 'ALL_PURPOSE'" in query
    )


def test_efficiency_rolling_materializes_the_four_configured_windows(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "explode(array(1, 7, 30, 90)) AS window_days" in query


def test_efficiency_rolling_anchors_windows_on_max_period_start(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "MAX(period_start) AS as_of_date" in query
    assert "date_add(a.as_of_date, -(w.window_days - 1)) AS window_start" in query


def test_efficiency_rolling_agg_still_reads_the_current_window_only(
    fakes: SimpleNamespace,
) -> None:
    # La CTE agg (13 agregats, dont 4 moyennes ponderees et 2 histogrammes)
    # n'est PAS elargie a 2 * window_days : la fenetre precedente est calculee
    # a part (prev_agg), sans conditionner un seul de ces agregats.
    query, _ = _rolling_query(fakes)
    agg = _cte_body(query, "agg")
    assert "WHERE d.period_start > date_add(a.as_of_date, -w.window_days)" in agg
    assert "AND d.period_start <= a.as_of_date" in agg
    assert "prev_window" not in agg
    assert "-2 * w.window_days" not in agg


def test_efficiency_rolling_previous_window_is_a_separate_cte(
    fakes: SimpleNamespace,
) -> None:
    # Fenetre precedente de MEME longueur = (as_of - 2*window_days,
    # as_of - window_days] : bornes exclusive/incluse symetriques de la fenetre
    # courante, donc deux periodes de window_days jours accolees.
    query, _ = _rolling_query(fakes)
    prev = _cte_body(query, "prev_agg")
    assert "SUM(d.uptime_hours) AS uptime_hours_prev_window" in prev
    assert "WHERE d.period_start > date_add(a.as_of_date, -2 * w.window_days)" in prev
    assert "AND d.period_start <= date_add(a.as_of_date, -w.window_days)" in prev
    assert (
        "GROUP BY d.cloud_provider, d.workspace_id, d.cluster_id, w.window_days" in prev
    )


def test_efficiency_rolling_previous_window_uses_the_same_weighted_idle_formula(
    fakes: SimpleNamespace,
) -> None:
    # Meme moyenne ponderee par le temps allume que la fenetre courante, au
    # caractere pres (seul l'alias change) : deux definitions differentes
    # rendraient idle_pct et idle_pct_prev_window incomparables.
    query, _ = _rolling_query(fakes)
    assert WEIGHTED_IDLE_PCT + "idle_pct," in query
    assert WEIGHTED_IDLE_PCT + "idle_pct_prev_window\n" in query


def test_efficiency_rolling_joins_previous_window_on_window_days(
    fakes: SimpleNamespace,
) -> None:
    # window_days DOIT figurer dans la cle de jointure : prev_agg porte une
    # ligne par cluster ET par fenetre, joindre sans lui multiplierait chaque
    # ligne de sortie par 4.
    query, _ = _rolling_query(fakes)
    assert (
        "LEFT JOIN prev_agg p\n"
        "      ON p.cloud_provider = m.cloud_provider\n"
        "     AND p.workspace_id = m.workspace_id\n"
        "     AND p.cluster_id = m.cluster_id\n"
        "     AND p.window_days = m.window_days" in query
    )
    assert "p.uptime_hours_prev_window," in query
    assert "p.idle_pct_prev_window," in query


def test_efficiency_rolling_previous_window_absence_stays_null(
    fakes: SimpleNamespace,
) -> None:
    # Aucun COALESCE(..., 0) sur les colonnes de fenetre precedente : un 0 se
    # lirait "allume zero heure", donc une chute de 100 %, au lieu de "pas de
    # comparaison possible". La jointure reste un LEFT JOIN (cf. test ci-dessus) :
    # un cluster sans jour dans la fenetre precedente garde ses deux colonnes NULL.
    query, _ = _rolling_query(fakes)
    assert "COALESCE" not in _cte_body(query, "prev_agg")
    assert "COALESCE(p." not in query


def test_efficiency_rolling_reads_daily_history_without_lower_bound(
    fakes: SimpleNamespace,
) -> None:
    # La fenetre precedente de la fenetre 90 jours remonte a as_of - 180 jours :
    # la lecture de la table quotidienne ne doit porter aucune borne basse de
    # date (seul le filtre de type ALL_PURPOSE est autorise, cf. SC-001).
    query, _ = _rolling_query(fakes)
    daily = _cte_body(query, "daily")
    assert "period_start >=" not in daily
    assert "DATE '" not in daily


def test_efficiency_rolling_sums_additive_metrics(fakes: SimpleNamespace) -> None:
    query, _ = _rolling_query(fakes)
    assert "SUM(d.uptime_hours) AS uptime_hours" in query
    assert "SUM(d.active_hours) AS active_hours" in query
    assert "SUM(d.autoscale_oscillation) AS autoscale_oscillation" in query
    assert "SUM(d.estimated_savings_usd) AS estimated_savings_usd" in query


def test_efficiency_rolling_takes_max_of_maxima(fakes: SimpleNamespace) -> None:
    query, _ = _rolling_query(fakes)
    assert "MAX(d.worker_count_max) AS worker_count_max" in query


def test_efficiency_rolling_weights_averages_by_uptime_hours(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "SUM(d.cpu_util_avg_pct * d.uptime_hours)" in query
    assert "SUM(d.mem_util_avg_pct * d.uptime_hours)" in query
    assert "SUM(d.idle_pct * d.uptime_hours)" in query
    assert "SUM(CASE WHEN d.cpu_util_avg_pct IS NOT NULL" in query


def test_efficiency_rolling_merges_histograms_bucketwise(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "transform(sequence(0," in query
    assert "collect_list(d.cpu_util_hist)" in query
    assert "collect_list(d.mem_util_hist)" in query
    assert "AS cpu_util_hist" in query
    assert "AS mem_util_hist" in query


def test_efficiency_rolling_recomputes_percentiles_from_histograms(
    fakes: SimpleNamespace,
) -> None:
    # Percentiles recalcules a partir des histogrammes fusionnes, pas moyennes.
    query, _ = _rolling_query(fakes)
    assert "g.cpu_util_hist" in query
    assert "g.mem_util_hist" in query
    assert "AS cpu_util_p95_pct" in query
    assert "AS mem_util_p95_pct" in query
    assert "THEN NULL" in query


def test_efficiency_rolling_recomputes_diagnostics_over_window(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "AS is_zombie" in query
    assert "AS utilization_status" in query
    assert "AS rightsizing_reco" in query


def test_efficiency_rolling_keeps_latest_descriptive_attrs(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert (
        "QUALIFY ROW_NUMBER() OVER (\n"
        "            PARTITION BY cloud_provider, workspace_id, cluster_id\n"
        "            ORDER BY period_start DESC\n"
        "        ) = 1" in query
    )
    assert "la.cluster_type" in query
    assert "la.recommended_node_type" in query


def test_efficiency_rolling_propagates_name_and_autoscale_config(
    fakes: SimpleNamespace,
) -> None:
    # Attributs de configuration repris du dernier jour connu, comme les types
    # de node : ils passent par la table quotidienne (aucune relecture curated).
    query, _ = _rolling_query(fakes)
    daily = _cte_body(query, "daily")
    latest_attrs = _cte_body(query, "latest_attrs")
    for attr in CONFIG_ATTRS:
        assert attr in daily, f"{attr} absent de la lecture quotidienne"
        assert attr in latest_attrs, f"{attr} absent de latest_attrs"
        assert f"la.{attr}," in query


def test_efficiency_rolling_new_columns_are_documented() -> None:
    # Toute colonne de sortie doit porter un commentaire Catalog Explorer (cf.
    # test_specs.test_every_gold_table_has_a_table_comment_and_documents_every_column).
    comments = CLUSTER_EFFICIENCY_ROLLING_SPEC.column_comments
    for column in (*CONFIG_ATTRS, "uptime_hours_prev_window", "idle_pct_prev_window"):
        assert comments.get(column), f"commentaire manquant pour {column}"


def test_efficiency_rolling_excludes_clusters_never_up(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "WHERE m.uptime_hours > 0" in query


def test_efficiency_rolling_custom_windows(fakes: SimpleNamespace) -> None:
    sentinel = fakes.DataFrame("cluster_efficiency_rolling_result")
    spark = fakes.Spark(sql_result=sentinel)
    build_cluster_efficiency_rolling(
        spark,
        cluster_efficiency_daily_table="it.sch.gold_dbx_compute_cluster_efficiency_daily",
        rolling_windows=(1, 14),
    )
    query = spark.sql_calls[0]
    assert "explode(array(1, 14)) AS window_days" in query
