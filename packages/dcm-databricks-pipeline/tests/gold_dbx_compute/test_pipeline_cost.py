"""Tests de `pipelines.gold_dbx_compute.pipeline_cost_daily`/`_rolling` (regles de derivation).

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`) : chaque builder
construit un unique `spark.sql(...)`, verifie ici via le texte SQL genere
(`FakeSpark`).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from pipelines.gold_dbx_compute.pipeline_cost_daily import build_pipeline_cost_daily
from pipelines.gold_dbx_compute.pipeline_cost_rolling import build_pipeline_cost_rolling
from pipelines.gold_dbx_compute.pipeline_efficiency_daily import build_pipeline_efficiency_daily


def _pipeline_cost_daily_query(
    fakes: SimpleNamespace, lower_bound: date | None
) -> tuple[str, object]:
    sentinel = fakes.DataFrame("pipeline_cost_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_pipeline_cost_daily(
        spark,
        billing_usage_table="it.sch.curated_dbx_billing_usage",
        billing_list_prices_table="it.sch.curated_dbx_billing_list_prices",
        lakeflow_pipelines_table="it.sch.curated_dbx_lakeflow_pipelines",
        lower_bound=lower_bound,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0], result


def test_pipeline_cost_daily_full_run_has_no_lower_bound_filter(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _pipeline_cost_daily_query(fakes, lower_bound=None)
    assert "usage_date >= DATE" not in query
    assert "period_start >= DATE" not in query


def test_pipeline_cost_daily_incremental_run_filters_usage_and_output_windows(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _pipeline_cost_daily_query(fakes, lower_bound=date(2026, 8, 14))
    # 1 jour tampon (J-1) sur la lecture facturation pour que le self-join de
    # cost_usd_prev_day voie J-1 au bord de la fenetre incrementale.
    assert "AND usage_date >= DATE '2026-08-13'" in query
    # La sortie (et donc le MERGE) reste bornee a lower_bound.
    assert "AND period_start >= DATE '2026-08-14'" in query


def test_pipeline_cost_daily_billing_direct_filters_non_null_pipeline_id(
    fakes: SimpleNamespace,
) -> None:
    # Rollup BILLING-DIRECT : lit la facturation restreinte aux lignes portant
    # un dlt_pipeline_id (execution ET maintenance du pipeline), sans passer par
    # les clusters. Le filtre garantit aussi que la cle de merge dlt_pipeline_id
    # n'est JAMAIS NULL.
    query, _ = _pipeline_cost_daily_query(fakes, lower_bound=None)
    assert "usage_metadata.dlt_pipeline_id AS dlt_pipeline_id" in query
    # Expression ENTIERE, les deux lignes du WHERE : un `in query` sur la seule
    # premiere ligne restait vrai alors que le predicat produit manquait.
    assert (
        "WHERE usage_metadata.dlt_pipeline_id IS NOT NULL\n"
        "          AND billing_origin_product IN ('DLT')"
    ) in query


def test_pipeline_cost_daily_keeps_only_the_dlt_product(fakes: SimpleNamespace) -> None:
    # `dlt_pipeline_id` n'est PAS reserve aux pipelines DLT : 10 972 ids non-DLT
    # pour 37 100,58 $ le portent sur l'historique complet (mesure dev
    # 2026-09-10), dont 10 499 requetes SQL -- 10 435 d'entre elles ayant une
    # ligne dans curated_dbx_lakeflow_pipelines, donc affichees avec un NOM de
    # pipeline, indistinguables d'un vrai pipeline.
    query, _ = _pipeline_cost_daily_query(fakes, lower_bound=None)
    assert "AND billing_origin_product IN ('DLT')" in query
    # LISTE BLANCHE : ni liste noire, ni enumeration des produits ecartes (qui
    # laisserait entrer le prochain produit ajoute par Databricks).
    assert "NOT IN" not in query
    assert "'SQL'" not in query
    assert "LAKEFLOW_CONNECT" not in query
    assert "VECTOR_SEARCH" not in query


def test_pipeline_cost_daily_filters_products_before_aggregating(
    fakes: SimpleNamespace,
) -> None:
    # En amont du GROUP BY : applique apres agregation, le predicat ecarterait
    # des jours-pipeline entiers au lieu des seules lignes etrangeres.
    query, _ = _pipeline_cost_daily_query(fakes, lower_bound=None)
    assert query.count("billing_origin_product") == 1
    assert query.index("billing_origin_product") < query.index("GROUP BY")


def test_pipeline_cost_daily_does_not_resolve_via_clusters(
    fakes: SimpleNamespace,
) -> None:
    # Aucune resolution cluster_id -> dlt_pipeline_id (ce serait l'option B,
    # rejetee) : le builder ne lit ni cluster_cost_daily ni la table clusters,
    # et ne joint aucune dimension cluster.
    query, _ = _pipeline_cost_daily_query(fakes, lower_bound=None)
    assert "cluster_cost_daily" not in query
    assert "curated_dbx_compute_clusters" not in query
    assert "cluster_type" not in query
    # La SEULE mention d'un cluster est le test de presence qui derive
    # `compute_kind` sur la ligne de facturation elle-meme : lire un champ de
    # `usage_metadata` n'est pas resoudre un cluster (aucune jointure).
    assert query.count("cluster_id") == 1
    assert "usage_metadata.cluster_id IS NOT NULL THEN 'CLASSIC'" in query


def test_pipeline_cost_daily_labels_classic_and_serverless_compute(
    fakes: SimpleNamespace,
) -> None:
    # `compute_kind` JAMAIS NULL : CASE binaire, la branche ELSE couvre tout le
    # reste. Une valeur NULL fusionnerait, via le `<=>` null-safe du MERGE, des
    # lignes de pipelines differents dans une seule ligne corrompue.
    query, _ = _pipeline_cost_daily_query(fakes, lower_bound=None)
    assert (
        "CASE WHEN usage_metadata.cluster_id IS NOT NULL THEN 'CLASSIC' "
        "ELSE 'SERVERLESS' END AS compute_kind" in query
    )
    assert "compute_kind IS NULL" not in query


def test_pipeline_cost_daily_carries_compute_kind_in_the_grain(
    fakes: SimpleNamespace,
) -> None:
    # `compute_kind` doit etre DANS le GROUP BY, pas un attribut agrege : les 2
    # pipelines mixtes mesures en dev (fenetre 30 j) doivent produire DEUX lignes
    # le meme jour, une par forme, sinon leur cout reste melange.
    query, _ = _pipeline_cost_daily_query(fakes, lower_bound=None)
    assert (
        "GROUP BY\n"
        "            u.cloud_provider, u.workspace_id, u.dlt_pipeline_id, "
        "u.compute_kind, u.period_start" in query
    )
    # Et portee jusqu'a la sortie (colonne du SELECT final, donc du MERGE).
    assert "        dlt_pipeline_id,\n        compute_kind,\n" in query


def test_pipeline_cost_daily_prev_day_self_join_is_equalized_on_compute_kind(
    fakes: SimpleNamespace,
) -> None:
    # Sans cette egalite, la ligne CLASSIC de J s'apparierait AUSSI a la ligne
    # SERVERLESS de J-1 d'un pipeline mixte : 2 lignes de sortie pour une meme
    # cle de merge, ne differant que par `cost_usd_prev_day`. Aucune erreur ne
    # le signalerait -- `merge_into_table` deduplique sur les cles de merge
    # (`dropDuplicates`) juste avant le MERGE et en garderait une au hasard :
    # `cost_delta_pct` deviendrait non deterministe, calcule contre le cout de
    # l'AUTRE forme de compute. Corruption silencieuse, pas un echec.
    query, _ = _pipeline_cost_daily_query(fakes, lower_bound=None)
    assert (
        "         AND prev.dlt_pipeline_id = e.dlt_pipeline_id\n"
        "         AND prev.compute_kind = e.compute_kind\n"
        "         AND prev.period_start = e.period_start - INTERVAL 1 DAY" in query
    )


def test_pipeline_cost_daily_aggregates_dbu_and_cost_by_pipeline(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _pipeline_cost_daily_query(fakes, lower_bound=None)
    assert (
        "SUM(CASE WHEN u.usage_unit = 'DBU' THEN u.usage_quantity ELSE 0 END) AS dbu_quantity"
        in query
    )
    assert "SUM(u.usage_quantity * COALESCE(lp.effective_price, 0)) AS cost_usd" in query
    assert (
        "GROUP BY\n"
        "            u.cloud_provider, u.workspace_id, u.dlt_pipeline_id, "
        "u.compute_kind, u.period_start" in query
    )


def test_pipeline_cost_daily_prices_usage_on_effective_price_window(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _pipeline_cost_daily_query(fakes, lower_bound=None)
    assert "pricing.effective_list.default AS effective_price" in query
    assert "lp.price_start_time <= u.period_start" in query
    assert "(lp.price_end_time IS NULL OR u.period_start < lp.price_end_time)" in query


def test_pipeline_cost_daily_resolves_pipeline_name_as_of_period_start(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _pipeline_cost_daily_query(fakes, lower_bound=None)
    assert "pl.name AS pipeline_name" in query
    assert "pl.change_time < p.period_start + INTERVAL 1 DAY" in query


def test_pipeline_cost_daily_name_falls_back_to_pipeline_id(
    fakes: SimpleNamespace,
) -> None:
    # Un pipeline dont aucune definition n'est encore ingeree dans
    # curated_dbx_lakeflow_pipelines reste identifiable par son id.
    query, _ = _pipeline_cost_daily_query(fakes, lower_bound=None)
    assert "COALESCE(pa.pipeline_name, pr.dlt_pipeline_id) AS pipeline_name" in query


def test_pipeline_cost_daily_pipelines_as_of_uses_end_of_day_bound(
    fakes: SimpleNamespace,
) -> None:
    # TIMESTAMP <= DATE caste a minuit et exclurait a tort les pipelines dont la
    # seule version connue est datee du jour meme de period_start.
    query, _ = _pipeline_cost_daily_query(fakes, lower_bound=None)
    assert "pl.change_time <= p.period_start" not in query


def test_pipeline_cost_daily_computes_delta_rank_and_top_cost(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _pipeline_cost_daily_query(fakes, lower_bound=None)
    # Self-join exact sur le jour calendaire precedent, pas un LAG.
    assert "prev.period_start = e.period_start - INTERVAL 1 DAY" in query
    assert "prev.cost_usd AS cost_usd_prev_day" in query
    assert "NULLIF(cost_usd_prev_day, 0) * 100 AS cost_delta_pct" in query
    # Rang PAR forme de compute : l'IHM affiche ce rang sur une liste filtree
    # CLASSIC, un rang toutes formes confondues s'y ouvrirait sur "40, 57, 61...".
    assert (
        "RANK() OVER (\n"
        "            PARTITION BY period_start, compute_kind ORDER BY cost_usd DESC\n"
        "        ) AS cost_rank" in query
    )
    assert (
        "RANK() OVER (PARTITION BY period_start, compute_kind ORDER BY cost_usd DESC)\n"
        "            <= 10 AS is_top_cost" in query
    )


def test_pipeline_cost_daily_custom_top_cost_threshold(fakes: SimpleNamespace) -> None:
    sentinel = fakes.DataFrame("pipeline_cost_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    build_pipeline_cost_daily(
        spark,
        billing_usage_table="it.sch.curated_dbx_billing_usage",
        billing_list_prices_table="it.sch.curated_dbx_billing_list_prices",
        lakeflow_pipelines_table="it.sch.curated_dbx_lakeflow_pipelines",
        lower_bound=None,
        top_cost_rank_threshold=5,
    )
    assert "<= 5 AS is_top_cost" in spark.sql_calls[0]


def _pipeline_cost_rolling_query(fakes: SimpleNamespace) -> tuple[str, object]:
    sentinel = fakes.DataFrame("pipeline_cost_rolling_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_pipeline_cost_rolling(
        spark,
        pipeline_cost_daily_table="it.sch.gold_dbx_compute_pipeline_cost_daily",
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0], result


def test_pipeline_cost_rolling_reads_only_daily_table_no_curated(
    fakes: SimpleNamespace,
) -> None:
    # Rollup pur : lit UNIQUEMENT la table quotidienne gold, jamais une table
    # curated.
    query, _ = _pipeline_cost_rolling_query(fakes)
    assert "it.sch.gold_dbx_compute_pipeline_cost_daily" in query
    assert "curated_" not in query


def test_pipeline_cost_rolling_materializes_the_four_configured_windows(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _pipeline_cost_rolling_query(fakes)
    assert "explode(array(1, 7, 30, 90)) AS window_days" in query


def test_pipeline_cost_rolling_anchors_windows_on_max_period_start(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _pipeline_cost_rolling_query(fakes)
    assert "MAX(period_start) AS as_of_date" in query
    assert "date_add(a.as_of_date, -(w.window_days - 1)) AS window_start" in query


def test_pipeline_cost_rolling_sums_additive_metrics_over_window(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _pipeline_cost_rolling_query(fakes)
    assert "WHEN d.period_start > date_add(a.as_of_date, -w.window_days)" in query
    assert "THEN d.dbu_quantity ELSE 0" in query
    assert "THEN d.cost_usd ELSE 0" in query


def test_pipeline_cost_rolling_has_no_cluster_count_column(
    fakes: SimpleNamespace,
) -> None:
    # Grain pipeline (pas cluster) : cluster_count est sans objet, contrairement
    # au rollup job_cluster.
    query, _ = _pipeline_cost_rolling_query(fakes)
    assert "cluster_count" not in query


def test_pipeline_cost_rolling_computes_previous_equal_length_window(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _pipeline_cost_rolling_query(fakes)
    assert "WHEN d.period_start <= date_add(a.as_of_date, -w.window_days)" in query
    assert "AS cost_usd_prev_window" in query
    assert "d.period_start > date_add(a.as_of_date, -2 * w.window_days)" in query
    assert (
        "(g.cost_usd - g.cost_usd_prev_window)\n"
        "            / NULLIF(g.cost_usd_prev_window, 0) * 100 AS cost_delta_pct" in query
    )


def test_pipeline_cost_rolling_ranks_within_each_window_and_compute_kind(
    fakes: SimpleNamespace,
) -> None:
    # `(window_days, compute_kind)` et non `window_days` seule : la page DLT
    # n'affiche que le classique, un rang toutes formes confondues y commencerait
    # a 40 avec des trous. Deux lignes d'une meme fenetre peuvent donc porter le
    # rang 1, une par forme -- c'est voulu.
    query, _ = _pipeline_cost_rolling_query(fakes)
    assert (
        "RANK() OVER (\n"
        "            PARTITION BY g.window_days, g.compute_kind ORDER BY g.cost_usd DESC\n"
        "        ) AS cost_rank" in query
    )
    assert (
        "RANK() OVER (PARTITION BY g.window_days, g.compute_kind ORDER BY g.cost_usd DESC)\n"
        "            <= 10 AS is_top_cost" in query
    )


def test_pipeline_cost_rolling_keeps_compute_kind_in_the_grain(
    fakes: SimpleNamespace,
) -> None:
    # Repris du daily et agrege PAR forme : sans `compute_kind` dans le GROUP BY,
    # la fenetre re-melangerait ce que le grain quotidien vient de separer.
    query, _ = _pipeline_cost_rolling_query(fakes)
    assert (
        "GROUP BY\n"
        "            d.cloud_provider,\n"
        "            d.workspace_id,\n"
        "            d.dlt_pipeline_id,\n"
        "            d.compute_kind,\n"
        "            w.window_days,\n"
        "            a.as_of_date" in query
    )
    assert "        g.dlt_pipeline_id,\n        g.compute_kind,\n" in query


def test_pipeline_cost_rolling_keeps_latest_pipeline_name(fakes: SimpleNamespace) -> None:
    query, _ = _pipeline_cost_rolling_query(fakes)
    assert (
        "QUALIFY ROW_NUMBER() OVER (\n"
        "            PARTITION BY cloud_provider, workspace_id, dlt_pipeline_id\n"
        "            ORDER BY period_start DESC\n"
        "        ) = 1" in query
    )
    assert "la.pipeline_name" in query
    # Partition VOLONTAIREMENT sans `compute_kind` : le nom d'un pipeline ne
    # depend pas de la forme de compute, les deux lignes d'un pipeline mixte
    # portent le meme. La jointure reste 1:1 dans les deux cas.
    assert (
        "            PARTITION BY cloud_provider, workspace_id, dlt_pipeline_id, compute_kind"
        not in query
    )


def test_pipeline_cost_rolling_drops_day_over_day_columns(fakes: SimpleNamespace) -> None:
    query, _ = _pipeline_cost_rolling_query(fakes)
    assert "cost_usd_prev_day" not in query


def test_pipeline_cost_rolling_excludes_objects_inactive_in_both_windows(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _pipeline_cost_rolling_query(fakes)
    assert "WHERE g.cost_usd <> 0 OR g.cost_usd_prev_window <> 0" in query


def test_pipeline_cost_rolling_custom_windows_and_threshold(fakes: SimpleNamespace) -> None:
    sentinel = fakes.DataFrame("pipeline_cost_rolling_result")
    spark = fakes.Spark(sql_result=sentinel)
    build_pipeline_cost_rolling(
        spark,
        pipeline_cost_daily_table="it.sch.gold_dbx_compute_pipeline_cost_daily",
        rolling_windows=(1, 14),
        top_cost_rank_threshold=5,
    )
    query = spark.sql_calls[0]
    assert "explode(array(1, 14)) AS window_days" in query
    assert "<= 5 AS is_top_cost" in query


# --- Non-regression de l'extraction dans `grain_resolution` (T004) ------------

# Texte EXACT de la CTE de nom du pipeline, dont seule la CTE de grain qui
# l'alimente varie d'un builder a l'autre (`priced` pour le cout, `agg` pour
# l'efficacite). Ce bloc etait ecrit en dur dans ce builder avant son extraction
# dans `grain_resolution.pipeline_name_cte_sql` : assertion byte-exacte, c'est
# ce qui prouve que l'extraction n'a rien change au SQL genere.
PIPELINES_AS_OF_CTE_SQL = """pipelines_as_of AS (
        SELECT
            p.cloud_provider,
            p.workspace_id,
            p.dlt_pipeline_id,
            p.period_start,
            pl.name AS pipeline_name
        FROM {grain_cte} p
        LEFT JOIN it.sch.curated_dbx_lakeflow_pipelines pl
          ON pl.cloud_provider = p.cloud_provider
         AND pl.workspace_id = p.workspace_id
         AND pl.pipeline_id = p.dlt_pipeline_id
         AND pl.change_time < p.period_start + INTERVAL 1 DAY
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY p.cloud_provider, p.workspace_id, p.dlt_pipeline_id, p.period_start
            ORDER BY pl.change_time DESC
        ) = 1
    )"""


def test_pipeline_cost_daily_pipelines_as_of_cte_text_is_unchanged(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _pipeline_cost_daily_query(fakes, lower_bound=None)
    assert PIPELINES_AS_OF_CTE_SQL.format(grain_cte="priced") in query


def test_pipeline_efficiency_daily_names_pipelines_with_the_very_same_sql(
    fakes: SimpleNamespace,
) -> None:
    # Cout et efficacite doivent nommer un pipeline a l'identique : un ecart de
    # resolution afficherait deux noms differents pour le meme dlt_pipeline_id
    # dans deux tables cote a cote.
    sentinel = fakes.DataFrame("pipeline_efficiency_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    build_pipeline_efficiency_daily(
        spark,
        cluster_efficiency_daily_table="it.sch.gold_dbx_compute_cluster_efficiency_daily",
        billing_usage_table="it.sch.curated_dbx_billing_usage",
        lakeflow_pipelines_table="it.sch.curated_dbx_lakeflow_pipelines",
        lower_bound=None,
    )
    assert PIPELINES_AS_OF_CTE_SQL.format(grain_cte="agg") in spark.sql_calls[0]
