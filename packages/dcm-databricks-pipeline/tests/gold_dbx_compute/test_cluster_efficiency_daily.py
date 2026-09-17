"""Tests de `pipelines.gold_dbx_compute.cluster_efficiency_daily` (regles de derivation).

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`) :
`build_cluster_efficiency_daily` construit un unique `spark.sql(...)`, verifie
ici via le texte SQL genere (`FakeSpark`).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from pipelines.gold_dbx_compute.cluster_efficiency_daily import build_cluster_efficiency_daily
from pipelines.gold_dbx_compute.specs import CLUSTER_EFFICIENCY_DAILY_SPEC


def _efficiency_daily_query(fakes: SimpleNamespace, lower_bound: date | None) -> str:
    sentinel = fakes.DataFrame("efficiency_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_cluster_efficiency_daily(
        spark,
        node_timeline_table="it.sch.curated_dbx_compute_node_timeline",
        clusters_table="it.sch.curated_dbx_compute_clusters",
        node_types_table="it.sch.curated_dbx_compute_node_types",
        job_task_run_timeline_table="it.sch.curated_dbx_lakeflow_job_task_run_timeline",
        cost_daily_table="it.sch.gold_dbx_compute_cluster_cost_daily",
        lower_bound=lower_bound,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0]


def test_cluster_efficiency_daily_clusters_as_of_uses_end_of_day_bound(
    fakes: SimpleNamespace,
) -> None:
    # TIMESTAMP <= DATE caste a minuit et exclurait a tort les
    # clusters dont la seule version connue est datee du jour meme de
    # period_start.
    query = _efficiency_daily_query(fakes, lower_bound=None)
    assert "c.change_time < d.period_start + INTERVAL 1 DAY" in query
    assert "c.change_time <= d.period_start" not in query


def test_cluster_efficiency_daily_reads_the_clusters_table_once(
    fakes: SimpleNamespace,
) -> None:
    # cluster_name et la configuration d'autoscaling sont reprises de la CTE
    # clusters_as_of, qui joint DEJA curated_dbx_compute_clusters au dernier etat
    # connu : une seconde jointure rescannerait toute la table de configuration
    # et pourrait resoudre un etat different de celui des types de node.
    query = _efficiency_daily_query(fakes, lower_bound=None)
    assert query.count("it.sch.curated_dbx_compute_clusters") == 1


def test_cluster_efficiency_daily_exposes_cluster_name(fakes: SimpleNamespace) -> None:
    # cluster_name manquait aux deux tables efficiency alors que les vues de
    # liste doivent l'afficher : il vient de clusters_as_of, pas d'une jointure
    # backend sur cluster_cost_rolling (qui exclut les clusters sans cout).
    query = _efficiency_daily_query(fakes, lower_bound=None)
    assert "c.cluster_name," in query
    assert "ca.cluster_name," in query


def test_cluster_efficiency_daily_derives_autoscale_config_from_both_bounds(
    fakes: SimpleNamespace,
) -> None:
    # Autoscaling actif <=> les DEUX bornes sont renseignees ; taille fixe <=>
    # worker_count renseigne et bornes NULL. Les deux modes sont mutuellement
    # exclusifs cote source, la detection est donc exacte.
    query = _efficiency_daily_query(fakes, lower_bound=None)
    assert (
        "(c.min_autoscale_workers IS NOT NULL AND c.max_autoscale_workers IS NOT NULL)" in query
    )
    assert "AS autoscale_enabled" in query
    assert "c.min_autoscale_workers AS autoscale_min_workers" in query
    assert "c.max_autoscale_workers AS autoscale_max_workers" in query
    # configured_worker_count expose a part : un COALESCE(min_autoscale_workers,
    # worker_count) afficherait une plage d'autoscaling "2-2" sur un cluster a
    # taille fixe, soit une donnee inventee.
    assert "c.worker_count AS configured_worker_count" in query
    assert "COALESCE(c.min_autoscale_workers" not in query
    for column in (
        "autoscale_enabled",
        "autoscale_min_workers",
        "autoscale_max_workers",
        "configured_worker_count",
    ):
        assert f"ca.{column}," in query


def test_cluster_efficiency_daily_new_columns_are_documented() -> None:
    # Toute colonne de sortie doit porter un commentaire Catalog Explorer (cf.
    # test_specs.test_every_gold_table_has_a_table_comment_and_documents_every_column,
    # dont la liste attendue precede cette feature).
    comments = CLUSTER_EFFICIENCY_DAILY_SPEC.column_comments
    for column in (
        "cluster_name",
        "autoscale_enabled",
        "autoscale_min_workers",
        "autoscale_max_workers",
        "configured_worker_count",
    ):
        assert comments.get(column), f"commentaire manquant pour {column}"


def test_cluster_efficiency_daily_derives_cluster_type_from_cluster_source(
    fakes: SimpleNamespace,
) -> None:
    # cluster_type permet de filtrer les clusters JOB ephemeres (cf.
    # job_cluster_cost_daily) avant toute analyse agregee d'utilisation.
    query = _efficiency_daily_query(fakes, lower_bound=None)
    assert "WHEN ca.cluster_source = 'JOB' THEN 'JOB'" in query
    assert "ELSE 'OTHER' END AS cluster_type" in query


def test_cluster_efficiency_daily_excludes_other_cluster_type(fakes: SimpleNamespace) -> None:
    # Clusters sans etat connu dans curated_dbx_compute_clusters
    # (cluster_type OTHER, cf. cluster_cost_daily) sont exclus de la sortie :
    # sans driver_node_type/worker_node_type ni type fiables, ils ne doivent
    # pas polluer les recommandations de rightsizing.
    query = _efficiency_daily_query(fakes, lower_bound=None)
    assert "WHERE CASE WHEN ca.cluster_source = 'JOB' THEN 'JOB'" in query
    assert "END <> 'OTHER'" in query


def test_cluster_efficiency_daily_full_run_has_no_lower_bound_filter(
    fakes: SimpleNamespace,
) -> None:
    query = _efficiency_daily_query(fakes, lower_bound=None)
    assert "to_date(start_time) >= DATE" not in query


def test_cluster_efficiency_daily_incremental_run_filters_period_window(
    fakes: SimpleNamespace,
) -> None:
    query = _efficiency_daily_query(fakes, lower_bound=date(2026, 8, 14))
    assert "AND to_date(start_time) >= DATE '2026-08-14'" in query


def test_cluster_efficiency_daily_over_threshold_matches_acceptance_criteria(
    fakes: SimpleNamespace,
) -> None:
    # AC: cpu_util_p95_pct < 40 AND mem_util_p95_pct < 50 => utilization_status = 'OVER'
    query = _efficiency_daily_query(fakes, lower_bound=None)
    assert "WHEN w.cpu_util_p95_pct < 40 AND w.mem_util_p95_pct < 50 THEN 'OVER'" in query
    assert "WHEN w.cpu_util_p95_pct > 85 OR w.mem_util_p95_pct > 85 THEN 'UNDER'" in query
    assert "ELSE 'OPTIMAL'" in query


def test_cluster_efficiency_daily_rightsizing_reco_and_savings_present(
    fakes: SimpleNamespace,
) -> None:
    query = _efficiency_daily_query(fakes, lower_bound=None)
    assert "AS rightsizing_reco" in query
    assert "AS estimated_savings_usd" in query
    assert "recommended_node_type" in query


def test_cluster_efficiency_daily_is_zombie_rule(fakes: SimpleNamespace) -> None:
    query = _efficiency_daily_query(fakes, lower_bound=None)
    assert "w.uptime_hours > 8" in query
    assert "AND w.cpu_util_p95_pct < 15" in query
    assert "AND (w.running_minutes - w.idle_minutes) / 60.0 < 1" in query


def test_cluster_efficiency_daily_active_hours_cannot_exceed_uptime(
    fakes: SimpleNamespace,
) -> None:
    # `active_hours` est le complement exact d'`idle_pct` sur la MEME grille par
    # minute qu'`uptime_hours` : active_hours <= uptime_hours par construction.
    # Un COUNT(DISTINCT date_trunc('HOUR', ...)) sur job_task_run_timeline
    # comptait des TRANCHES HORAIRES, une fois par tache concurrente : les
    # heures actives depassaient l'uptime (jusqu'a 60x) et `is_zombie` ne se
    # declenchait jamais.
    query = _efficiency_daily_query(fakes, lower_bound=None)
    assert "(w.running_minutes - w.idle_minutes) / 60.0 AS active_hours" in query
    assert "date_trunc('HOUR'" not in query
    assert "COUNT(DISTINCT" not in query


def test_cluster_efficiency_daily_activity_signal_uses_lakeflow_job_task_run_timeline(
    fakes: SimpleNamespace,
) -> None:
    # Signal d'activite base sur lakeflow_job_task_run_timeline (chevauchement
    # de periode + cluster_id dans l'array `compute`), pas sur query_history
    # (qui ne trace que les SQL Warehouses, cf. docstring de la fonction).
    query = _efficiency_daily_query(fakes, lower_bound=None)
    assert "it.sch.curated_dbx_lakeflow_job_task_run_timeline" in query
    assert "query_history" not in query
    assert "qh.compute" not in query
    assert "jt.period_start_time < pm.start_time + INTERVAL 1 MINUTES" in query
    assert "jt.period_end_time > pm.start_time" in query
    assert "exists(jt.compute, c -> c.cluster_id = pm.cluster_id)" in query
    assert "has_active_task" in query
