"""Tests de `pipelines.gold_dbx_compute.cluster_cost_daily` (regles de derivation).

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`, qui n'instancie
jamais de Spark reel) : `build_cluster_cost_daily` construit un unique
`spark.sql(...)`, verifie ici via le texte SQL genere (`FakeSpark`).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from pipelines.gold_dbx_compute.cluster_cost_daily import build_cluster_cost_daily


def _cost_daily_query(fakes: SimpleNamespace, lower_bound: date | None) -> tuple[str, object]:
    sentinel = fakes.DataFrame("cost_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_cluster_cost_daily(
        spark,
        billing_usage_table="it.sch.curated_dbx_billing_usage",
        billing_list_prices_table="it.sch.curated_dbx_billing_list_prices",
        clusters_table="it.sch.curated_dbx_compute_clusters",
        lower_bound=lower_bound,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0], result


def test_cluster_cost_daily_full_run_has_no_lower_bound_filter(fakes: SimpleNamespace) -> None:
    query, _ = _cost_daily_query(fakes, lower_bound=None)
    assert "usage_date >= DATE" not in query
    assert "period_start >= DATE" not in query


def test_cluster_cost_daily_incremental_run_filters_usage_date_window(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _cost_daily_query(fakes, lower_bound=date(2026, 8, 14))
    # Lecture curated avec 1 jour tampon (J-1) pour que le self-join de
    # cost_usd_prev_day voie J-1 au bord de la fenetre incrementale.
    assert "AND usage_date >= DATE '2026-08-13'" in query
    # Mais la sortie (et donc le MERGE) reste bornee a lower_bound, le jour
    # tampon n'est jamais reecrit.
    assert "AND period_start >= DATE '2026-08-14'" in query


def test_cluster_cost_daily_clusters_as_of_uses_end_of_day_bound(
    fakes: SimpleNamespace,
) -> None:
    # TIMESTAMP <= DATE caste a minuit et exclurait a tort les
    # clusters dont la seule version connue est datee du jour meme de
    # period_start (cas de la quasi-totalite des clusters JOB ephemeres).
    query, _ = _cost_daily_query(fakes, lower_bound=None)
    assert "c.change_time < p.period_start + INTERVAL 1 DAY" in query
    assert "c.change_time <= p.period_start" not in query


def test_cluster_cost_daily_derives_owner_cost_center_and_sku_group(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _cost_daily_query(fakes, lower_bound=None)
    assert "usage_metadata.cluster_id IS NOT NULL" in query
    # Le tag explicite prime sur owned_by (souvent un UUID de service
    # principal ou un compte d'automatisation, pas une attribution metier).
    assert "COALESCE(ca.tags['owner'], ca.owned_by) AS owner" in query
    assert "ca.tags['cost_center'] AS cost_center" in query
    assert "WHEN u.sku_name LIKE '%SERVERLESS%' THEN 3" in query
    assert "WHEN u.sku_name LIKE '%PHOTON%' THEN 2" in query


def test_cluster_cost_daily_keeps_only_cluster_compute_products(fakes: SimpleNamespace) -> None:
    # `cluster_id IS NOT NULL` seul faisait entrer le cout des services manages
    # (inference, fonctions d'IA) que la facturation rattache au cluster
    # APPELANT : 791,02 $ sur 97 clusters visibles dans la table (mesure dev
    # 2026-09-10). Expression ENTIERE et non un fragment : un `IN (...)` present
    # ailleurs, ou une liste amputee d'un produit, resterait vrai sinon.
    query, _ = _cost_daily_query(fakes, lower_bound=None)
    assert (
        "WHERE usage_metadata.cluster_id IS NOT NULL\n"
        "          AND billing_origin_product IN ('JOBS', 'ALL_PURPOSE', 'DLT')"
    ) in query
    # LISTE BLANCHE : une liste noire laisserait entrer silencieusement tout
    # produit ajoute par Databricks apres l'ecriture du filtre.
    assert "NOT IN" not in query
    assert "MODEL_SERVING" not in query
    assert "AI_FUNCTIONS" not in query


def test_cluster_cost_daily_filters_products_before_aggregating(fakes: SimpleNamespace) -> None:
    # Le predicat doit rester dans `usage_filtered`, en amont du GROUP BY :
    # applique apres agregation il n'ecarterait plus des lignes mais des
    # jours-cluster entiers, dont ceux qui melangent un vrai cout de cluster et
    # un cout etranger.
    query, _ = _cost_daily_query(fakes, lower_bound=None)
    assert query.count("billing_origin_product") == 1
    assert query.index("billing_origin_product") < query.index("GROUP BY")


def test_cluster_cost_daily_keeps_the_serverless_sku_group_branch_as_a_canary(
    fakes: SimpleNamespace,
) -> None:
    # Plus atteignable depuis le filtre produit (zero ligne %SERVERLESS% dans
    # JOBS/ALL_PURPOSE/DLT sur tout l'historique, mesure dev 2026-09-10), mais
    # CONSERVEE : sa reapparition signalerait un changement de facturation
    # Databricks, pas un bug du builder.
    query, _ = _cost_daily_query(fakes, lower_bound=None)
    assert "WHEN pr.sku_priority = 3 THEN 'serverless'" in query
    assert "WHEN pr.sku_priority = 2 THEN 'photon'" in query


def test_cluster_cost_daily_computes_delta_rank_and_top_cost(fakes: SimpleNamespace) -> None:
    query, _ = _cost_daily_query(fakes, lower_bound=None)
    # Self-join exact sur le jour calendaire precedent, pas un LAG (qui
    # sauterait les jours sans usage et ramenerait un cout bien plus ancien
    # qu'hier, cf. docstring de `build_cluster_cost_daily`).
    assert "prev.period_start = e.period_start - INTERVAL 1 DAY" in query
    assert "prev.cost_usd AS cost_usd_prev_day" in query
    assert "NULLIF(cost_usd_prev_day, 0) * 100 AS cost_delta_pct" in query
    # cost_rank est global par jour (pas de decoupage par landing zone, cf.
    # commentaire de `CLUSTER_DAILY_MERGE_KEYS` : aucun mapping workspace_id ->
    # lz_id fiable n'existe aujourd'hui).
    assert (
        "RANK() OVER (PARTITION BY period_start ORDER BY cost_usd DESC) "
        "AS cost_rank" in query
    )
    assert "<= 10 AS is_top_cost" in query


def test_cluster_cost_daily_derives_cluster_type_from_cluster_source(
    fakes: SimpleNamespace,
) -> None:
    # cluster_type (ALL_PURPOSE/JOB/PIPELINE) est derive de cluster_source
    # (champ absent de system.compute.clusters) : permet de filtrer les
    # clusters JOB ephemeres (cf. job_cluster_cost_daily) des clusters
    # persistants avant toute analyse agregee.
    query, _ = _cost_daily_query(fakes, lower_bound=None)
    assert "WHEN ca.cluster_source = 'JOB' THEN 'JOB'" in query
    assert "WHEN ca.cluster_source IN ('UI', 'API') THEN 'ALL_PURPOSE'" in query
    assert (
        "WHEN ca.cluster_source IN ('PIPELINE', 'PIPELINE_MAINTENANCE') THEN 'PIPELINE'"
        in query
    )
    assert "ELSE 'OTHER' END AS cluster_type" in query
    # Colonne finale exposee = cluster_type (derive), pas le cluster_source
    # brut, dans le SELECT de sortie.
    assert "cluster_type,\n        owner," in query


def test_cluster_cost_daily_excludes_other_cluster_type(fakes: SimpleNamespace) -> None:
    # Clusters sans etat connu dans curated_dbx_compute_clusters
    # (cluster_type OTHER, ~2.8% des lignes de facturation, cf. docstring)
    # sont exclus avant le classement (cost_rank) et le delta J-1 : sans
    # identite/type fiables, ils ne doivent pas polluer les clusters
    # identifies. `cluster_type` est deja une colonne materialisee (issue de
    # `enriched`), pas besoin de repeter le CASE dans le WHERE (contrairement
    # a cluster_efficiency_daily/cluster_reliability_daily).
    query, _ = _cost_daily_query(fakes, lower_bound=None)
    assert "WHERE cluster_type <> 'OTHER'" in query


def test_cluster_cost_daily_custom_top_cost_threshold(fakes: SimpleNamespace) -> None:
    sentinel = fakes.DataFrame("cost_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    build_cluster_cost_daily(
        spark,
        billing_usage_table="it.sch.curated_dbx_billing_usage",
        billing_list_prices_table="it.sch.curated_dbx_billing_list_prices",
        clusters_table="it.sch.curated_dbx_compute_clusters",
        lower_bound=None,
        top_cost_rank_threshold=5,
    )
    assert "<= 5 AS is_top_cost" in spark.sql_calls[0]
