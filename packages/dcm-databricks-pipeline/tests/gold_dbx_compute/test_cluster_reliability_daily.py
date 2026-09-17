"""Tests de `pipelines.gold_dbx_compute.cluster_reliability_daily` (regles de derivation).

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`) :
`build_cluster_reliability_daily` construit un unique `spark.sql(...)`,
verifie ici via le texte SQL genere (`FakeSpark`).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from pipelines.gold_dbx_compute.cluster_reliability_daily import build_cluster_reliability_daily


def _reliability_daily_query(fakes: SimpleNamespace, lower_bound: date | None) -> str:
    sentinel = fakes.DataFrame("reliability_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_cluster_reliability_daily(
        spark,
        clusters_table="it.sch.curated_dbx_compute_clusters",
        access_audit_table="it.sch.curated_dbx_access_audit",
        lower_bound=lower_bound,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0]


def test_cluster_reliability_daily_clusters_as_of_uses_end_of_day_bound(
    fakes: SimpleNamespace,
) -> None:
    # TIMESTAMP <= DATE caste a minuit et exclurait a tort les
    # clusters dont la seule version connue est datee du jour meme de
    # period_start.
    query = _reliability_daily_query(fakes, lower_bound=None)
    assert "c.change_time < k.period_start + INTERVAL 1 DAY" in query
    assert "c.change_time <= k.period_start" not in query


def test_cluster_reliability_daily_derives_cluster_type_from_cluster_source(
    fakes: SimpleNamespace,
) -> None:
    # cluster_type permet de filtrer les clusters JOB ephemeres (cf.
    # job_cluster_cost_daily) avant toute analyse agregee de fiabilite.
    query = _reliability_daily_query(fakes, lower_bound=None)
    assert "WHEN w.cluster_source = 'JOB' THEN 'JOB'" in query
    assert "ELSE 'OTHER' END AS cluster_type" in query


def test_cluster_reliability_daily_selects_cluster_name_from_clusters_join(
    fakes: SimpleNamespace,
) -> None:
    # cluster_name doit venir de la meme jointure clusters_as_of que
    # cluster_type/auto_termination_minutes, et etre expose dans la sortie
    # finale : permet a recommendations.py de resoudre object_name directement
    # depuis cette table (rolling) plutot que via cluster_governance, dont le
    # perimetre est plus etroit.
    query = _reliability_daily_query(fakes, lower_bound=None)
    assert "c.cluster_name," in query
    assert "w.cluster_name," in query


def test_cluster_reliability_daily_excludes_other_cluster_type(fakes: SimpleNamespace) -> None:
    # Clusters sans etat connu dans curated_dbx_compute_clusters
    # (cluster_type OTHER, cf. cluster_cost_daily) sont exclus de la sortie :
    # sans auto_termination_minutes ni type fiables, ils ne doivent pas
    # polluer les analyses de fiabilite.
    query = _reliability_daily_query(fakes, lower_bound=None)
    assert "WHERE CASE WHEN w.cluster_source = 'JOB' THEN 'JOB'" in query
    assert "END <> 'OTHER'" in query


def test_cluster_reliability_daily_full_run_has_no_lower_bound_filter(
    fakes: SimpleNamespace,
) -> None:
    query = _reliability_daily_query(fakes, lower_bound=None)
    assert "event_date >= DATE" not in query


def test_cluster_reliability_daily_incremental_run_filters_event_date_window(
    fakes: SimpleNamespace,
) -> None:
    query = _reliability_daily_query(fakes, lower_bound=date(2026, 8, 14))
    assert "AND event_date >= DATE '2026-08-14'" in query


def test_cluster_reliability_daily_uses_expected_termination_reasons(
    fakes: SimpleNamespace,
) -> None:
    query = _reliability_daily_query(fakes, lower_bound=None)
    # JOB_FINISHED (majorite des terminaisons observees) est une
    # auto-terminaison normale de cluster de job, pas un probleme de fiabilite
    # -> incluse dans les raisons attendues (sinon unexpected_termination_count
    # serait noye par ce bruit).
    assert "'USER_REQUEST', 'INACTIVITY', 'JOB_FINISHED'" in query
    assert "has_auto_termination" in query
    assert "auto_termination_minutes" in query


def test_cluster_reliability_daily_termination_reason_uses_delete_result(
    fakes: SimpleNamespace,
) -> None:
    # `delete` (la requete elle-meme) n'expose que `cluster_id` dans
    # request_params : la raison de terminaison n'est connue qu'a la
    # completion asynchrone `deleteResult`, sous la clef
    # `clusterTerminationReasonCode` (pas `termination_reason`, qui n'existe pas).
    query = _reliability_daily_query(fakes, lower_bound=None)
    assert "'deleteResult'" in query
    assert "request_params['clusterTerminationReasonCode']" in query
    assert "request_params['termination_reason']" not in query


def test_cluster_reliability_daily_excludes_events_without_resolvable_cluster_id(
    fakes: SimpleNamespace,
) -> None:
    # Un `create` en echec (ex. REQUEST_LIMIT_EXCEEDED) n'a jamais de
    # cluster_id assigne : ces evenements se regrouperaient sous une cle
    # cluster_id NULL et casseraient le grain per-cluster de la table.
    query = _reliability_daily_query(fakes, lower_bound=None)
    assert "WHERE cluster_id IS NOT NULL" in query


def test_cluster_reliability_daily_uses_real_audit_action_names(
    fakes: SimpleNamespace,
) -> None:
    # Noms confirmes en prod (pas ceux des endpoints REST Databricks Clusters,
    # cf. commentaire des constantes) : `create`/`start` pour le demarrage,
    # `delete`/`permanentDelete` pour la terminaison ("delete" == terminaison
    # du compute, pas une suppression de config).
    query = _reliability_daily_query(fakes, lower_bound=None)
    assert "'create', 'start'" in query
    assert "'delete', 'permanentDelete'" in query
    assert "createCluster" not in query
    assert "terminateCluster" not in query


def test_cluster_reliability_daily_cluster_id_coalesces_known_key_shapes(
    fakes: SimpleNamespace,
) -> None:
    # La clef `cluster_id` varie selon l'action : snake_case sur
    # create/start/delete/permanentDelete, camelCase sur les *Result, et
    # absente de `request_params` pour `create` (presente uniquement dans le
    # JSON de `response.result`, l'ID n'existe pas encore au moment de la
    # requete).
    query = _reliability_daily_query(fakes, lower_bound=None)
    assert "request_params['cluster_id']" in query
    assert "request_params['clusterId']" in query
    assert "get_json_object(response.result, '$.cluster_id')" in query


def test_cluster_reliability_daily_startup_latency_includes_completion_events(
    fakes: SimpleNamespace,
) -> None:
    # `avg_startup_seconds` doit voir `createResult`/`startResult` dans
    # `audit_filtered` : sans elles, le LEAD (ordonne par event_time) tombe sur
    # la PROCHAINE transition de cycle de vie (ex. la terminaison, potentiellement
    # des heures/jours plus tard) au lieu de la completion du create/start.
    query = _reliability_daily_query(fakes, lower_bound=None)
    action_filter_start = query.index("WHERE action_name IN")
    action_filter = query[action_filter_start : action_filter_start + 200]
    assert "createResult" in action_filter
    assert "startResult" in action_filter


def test_cluster_reliability_daily_startup_latency_requires_result_next_action(
    fakes: SimpleNamespace,
) -> None:
    # Le CASE de `startup_latency` doit filtrer explicitement
    # `next_action_name IN ('createResult', 'startResult')` plutot qu'un simple
    # `IS NOT NULL` : sinon un evenement quelconque intercale avant la
    # completion (ex. un `delete` avant que le `startResult` soit journalise)
    # serait pris comme "suivant" et fausserait la latence mesuree.
    query = _reliability_daily_query(fakes, lower_bound=None)
    assert (
        "WHEN action_name IN ('create', 'start')\n"
        "                     AND next_action_name IN ('createResult', 'startResult')"
        in query
    )
    assert "next_action_name IS NOT NULL" not in query
