"""Tests de `pipelines.gold_dbx_compute.job_cluster_cost_daily` (regles de derivation).

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`) :
`build_job_cluster_cost_daily` construit un unique `spark.sql(...)`, verifie
ici via le texte SQL genere (`FakeSpark`).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from pipelines.gold_dbx_compute.job_cluster_cost_daily import build_job_cluster_cost_daily
from pipelines.gold_dbx_compute.job_efficiency_daily import build_job_efficiency_daily


def _job_cluster_cost_query(fakes: SimpleNamespace, lower_bound: date | None) -> tuple[str, object]:
    sentinel = fakes.DataFrame("job_cluster_cost_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_job_cluster_cost_daily(
        spark,
        billing_usage_table="it.sch.curated_dbx_billing_usage",
        billing_list_prices_table="it.sch.curated_dbx_billing_list_prices",
        job_run_timeline_table="it.sch.curated_dbx_lakeflow_job_run_timeline",
        lakeflow_jobs_table="it.sch.curated_dbx_lakeflow_jobs",
        lower_bound=lower_bound,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0], result


def test_job_cluster_cost_daily_full_run_has_no_lower_bound_filter(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _job_cluster_cost_query(fakes, lower_bound=None)
    assert "usage_date >= DATE" not in query
    assert "period_start >= DATE" not in query


def test_job_cluster_cost_daily_incremental_run_filters_usage_and_output_windows(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _job_cluster_cost_query(fakes, lower_bound=date(2026, 8, 14))
    # 1 jour tampon (J-1) sur la lecture facturation pour que le self-join de
    # cost_usd_prev_day voie J-1 au bord de la fenetre incrementale.
    assert "AND usage_date >= DATE '2026-08-13'" in query
    # La sortie (et donc le MERGE) reste bornee a lower_bound.
    assert "AND period_start >= DATE '2026-08-14'" in query


def test_job_cluster_cost_daily_billing_direct_filters_non_null_job_id(
    fakes: SimpleNamespace,
) -> None:
    # Rollup BILLING-DIRECT (T001b) : `job_id` est porte par la ligne de
    # facturation elle-meme, aucune resolution par le cluster. Le filtre garantit
    # aussi que la cle de merge `job_id` n'est JAMAIS NULL.
    query, _ = _job_cluster_cost_query(fakes, lower_bound=None)
    assert "usage_metadata.job_id AS job_id" in query
    assert "WHERE usage_metadata.job_id IS NOT NULL" in query
    assert "it.sch.curated_dbx_billing_usage" in query


def test_job_cluster_cost_daily_does_not_inherit_the_cluster_id_not_null_filter(
    fakes: SimpleNamespace,
) -> None:
    # LE bug corrige par T001b : en agregeant `cluster_cost_daily`, ce rollup
    # heritait de son filtre `usage_metadata.cluster_id IS NOT NULL`, et un job
    # SERVERLESS n'a jamais de `cluster_id`. 56 841 $ AWS + 28 812 $ Azure sur
    # 30 jours etaient exclus silencieusement (mesure en dev le 2026-09-10).
    # `cluster_id` ne doit donc plus apparaitre dans AUCUN predicat : ni en
    # filtre de lecture, ni en condition de jointure.
    query, _ = _job_cluster_cost_query(fakes, lower_bound=None)
    assert "WHERE usage_metadata.cluster_id IS NOT NULL" not in query
    assert "cluster_id IS NOT NULL\n" not in query
    # Seule occurrence autorisee du test de presence : la derivation de
    # `compute_kind`, qui CLASSE la ligne au lieu de l'exclure.
    assert query.count("cluster_id IS NOT NULL") == 1
    assert "usage_metadata.cluster_id IS NOT NULL THEN 'CLASSIC'" in query


def test_job_cluster_cost_daily_no_longer_resolves_job_id_through_clusters(
    fakes: SimpleNamespace,
) -> None:
    # La lignee `cluster_id -> job_id` (`job_clusters` + `INNER JOIN`) disparait :
    # elle etait la source du plafond de couverture historique
    # (`job_task_run_timeline`, retention ~1 an) en plus de l'angle mort
    # serverless. Le rollup ne lit plus aucune table gold non plus.
    query, _ = _job_cluster_cost_query(fakes, lower_bound=None)
    assert "job_clusters" not in query
    assert "JOIN job_clusters jc" not in query
    assert "curated_dbx_lakeflow_job_task_run_timeline" not in query
    assert "LATERAL VIEW explode" not in query
    assert "gold_dbx_compute_cluster_cost_daily" not in query
    assert "cluster_type" not in query


def test_job_cluster_cost_daily_labels_classic_and_serverless_compute(
    fakes: SimpleNamespace,
) -> None:
    # `compute_kind` JAMAIS NULL : CASE binaire, la branche ELSE couvre tout le
    # reste. Une valeur NULL fusionnerait, via le `<=>` null-safe du MERGE, des
    # lignes de jobs differents dans une seule ligne corrompue.
    query, _ = _job_cluster_cost_query(fakes, lower_bound=None)
    assert (
        "CASE WHEN usage_metadata.cluster_id IS NOT NULL THEN 'CLASSIC' "
        "ELSE 'SERVERLESS' END AS compute_kind" in query
    )
    assert "compute_kind IS NULL" not in query


def test_job_cluster_cost_daily_carries_compute_kind_in_the_grain(
    fakes: SimpleNamespace,
) -> None:
    # `compute_kind` doit etre DANS le GROUP BY, pas un attribut agrege : les 926
    # jours-job mixtes mesures en dev (fenetre 30 j) doivent produire DEUX lignes
    # le meme jour, une par forme, sinon leur cout reste melange.
    query, _ = _job_cluster_cost_query(fakes, lower_bound=None)
    assert (
        "GROUP BY\n"
        "            u.cloud_provider, u.workspace_id, u.job_id, "
        "u.compute_kind, u.period_start" in query
    )
    # Et portee jusqu'a la sortie (colonne du SELECT final, donc du MERGE).
    assert "        job_id,\n        compute_kind,\n" in query


def test_job_cluster_cost_daily_prev_day_self_join_is_equalized_on_compute_kind(
    fakes: SimpleNamespace,
) -> None:
    # Sans cette egalite, la ligne CLASSIC de J s'apparierait AUSSI a la ligne
    # SERVERLESS de J-1 d'un job mixte : 2 lignes de sortie pour une meme cle de
    # merge, ne differant que par `cost_usd_prev_day`. Aucune erreur ne le
    # signalerait -- `merge_into_table` deduplique sur les cles de merge
    # (`dropDuplicates`) juste avant le MERGE et en garderait une au hasard :
    # `cost_delta_pct` deviendrait non deterministe, calcule contre le cout de
    # l'AUTRE forme de compute. Corruption silencieuse, pas un echec. 926
    # jours-job sont dans ce cas, contre 2 seulement cote pipeline.
    query, _ = _job_cluster_cost_query(fakes, lower_bound=None)
    assert (
        "         AND prev.job_id = e.job_id\n"
        "         AND prev.compute_kind = e.compute_kind\n"
        "         AND prev.period_start = e.period_start - INTERVAL 1 DAY" in query
    )


def test_job_cluster_cost_daily_aggregates_dbu_and_cost_by_job(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _job_cluster_cost_query(fakes, lower_bound=None)
    # `COUNT(DISTINCT)` sur la facturation : vaut 0 (et non NULL) sur une ligne
    # SERVERLESS, cardinal exact d'un ensemble vide -- la colonne reste sommable
    # telle quelle dans le rollup fenetre.
    assert "COUNT(DISTINCT u.cluster_id) AS cluster_count" in query
    assert (
        "SUM(CASE WHEN u.usage_unit = 'DBU' THEN u.usage_quantity ELSE 0 END) AS dbu_quantity"
        in query
    )
    assert "SUM(u.usage_quantity * COALESCE(lp.effective_price, 0)) AS cost_usd" in query


def test_job_cluster_cost_daily_prices_usage_on_effective_price_window(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _job_cluster_cost_query(fakes, lower_bound=None)
    assert "pricing.effective_list.default AS effective_price" in query
    assert "lp.price_start_time <= u.period_start" in query
    assert "(lp.price_end_time IS NULL OR u.period_start < lp.price_end_time)" in query


def test_job_cluster_cost_daily_resolves_job_name_as_of_period_start(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _job_cluster_cost_query(fakes, lower_bound=None)
    assert "j.name AS job_name" in query
    assert "j.change_time < a.period_start + INTERVAL 1 DAY" in query


def test_job_cluster_cost_daily_jobs_as_of_uses_end_of_day_bound(
    fakes: SimpleNamespace,
) -> None:
    # TIMESTAMP <= DATE caste a minuit et exclurait a tort les jobs
    # dont la seule version connue est datee du jour meme de period_start.
    query, _ = _job_cluster_cost_query(fakes, lower_bound=None)
    assert "j.change_time <= a.period_start" not in query


def test_job_cluster_cost_daily_computes_delta_rank_and_top_cost(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _job_cluster_cost_query(fakes, lower_bound=None)
    # Self-join exact sur le jour calendaire precedent, pas un LAG, memes
    # raisons que cluster_cost_daily.
    assert "prev.period_start = e.period_start - INTERVAL 1 DAY" in query
    assert "prev.cost_usd AS cost_usd_prev_day" in query
    assert "NULLIF(cost_usd_prev_day, 0) * 100 AS cost_delta_pct" in query
    # Rang PAR forme de compute : l'IHM affiche ce rang sur une liste filtree
    # CLASSIC ou SERVERLESS, un rang toutes formes confondues y aurait des trous.
    assert (
        "RANK() OVER (\n"
        "            PARTITION BY period_start, compute_kind ORDER BY cost_usd DESC\n"
        "        ) AS cost_rank" in query
    )
    assert (
        "RANK() OVER (PARTITION BY period_start, compute_kind ORDER BY cost_usd DESC)\n"
        "            <= 10 AS is_top_cost" in query
    )


def test_job_cluster_cost_daily_custom_top_cost_threshold(fakes: SimpleNamespace) -> None:
    sentinel = fakes.DataFrame("job_cluster_cost_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    build_job_cluster_cost_daily(
        spark,
        billing_usage_table="it.sch.curated_dbx_billing_usage",
        billing_list_prices_table="it.sch.curated_dbx_billing_list_prices",
        job_run_timeline_table="it.sch.curated_dbx_lakeflow_job_run_timeline",
        lakeflow_jobs_table="it.sch.curated_dbx_lakeflow_jobs",
        lower_bound=None,
        top_cost_rank_threshold=5,
    )
    assert "<= 5 AS is_top_cost" in spark.sql_calls[0]


def test_job_cluster_cost_daily_job_name_falls_back_to_the_submitted_run_name(
    fakes: SimpleNamespace,
) -> None:
    # Les deux sources de nom sont DISJOINTES par construction (mesure sur les 2
    # clouds) : `jobs.name` n'existe que pour les `JOB_RUN` (definition de job
    # persistee), `run_name` n'est renseigne que pour les `SUBMIT_RUN`
    # (jobs/runs/submit, aucune ligne dans system.lakeflow.jobs). Le COALESCE
    # est donc exact, et il est la seule regle : ni CASE, ni priorite a arbitrer.
    query, _ = _job_cluster_cost_query(fakes, lower_bound=None)
    assert "LEFT JOIN submit_run_names sr" in query
    assert "COALESCE(ja.job_name, sr.run_name) AS job_name" in query


def test_job_cluster_cost_daily_job_name_has_no_fallback_on_the_job_id(
    fakes: SimpleNamespace,
) -> None:
    # DIVERGENCE ASSUMEE avec `pipeline_cost_daily`, qui replie `pipeline_name`
    # sur `dlt_pipeline_id` : ici `job_name` reste vide pour un run lance depuis
    # un notebook (aucun nom dans aucune source), et c'est le consommateur qui
    # substitue l'id (`COALESCE(NULLIF(job_name, ''), job_id)` cote backend).
    # Ajouter le repli ici changerait le contenu d'une colonne documentee "reste
    # vide" et rendrait indistinguables "sans nom" et "nomme comme son id".
    query, _ = _job_cluster_cost_query(fakes, lower_bound=None)
    assert "pr.job_id) AS job_name" not in query
    assert "COALESCE(ja.job_name, sr.run_name, " not in query


def test_job_cluster_cost_daily_submit_run_names_is_deduplicated_to_one_row_per_job(
    fakes: SimpleNamespace,
) -> None:
    # GARDE ANTI-FAN-OUT : sans agregation, un job_id portant plusieurs run_id
    # (2 cas mesures en dev) dupliquerait ses lignes de cout. Meme famille de
    # tables que le fan-out x43 documente dans `_lakeflow_latest_jobs()`.
    query, _ = _job_cluster_cost_query(fakes, lower_bound=None)
    assert "MAX(r.run_name) AS run_name" in query
    assert "GROUP BY r.cloud_provider, r.workspace_id, r.job_id" in query
    assert "WHERE r.run_name IS NOT NULL" in query


def test_job_cluster_cost_daily_submit_run_names_is_not_bounded_by_the_incremental_window(
    fakes: SimpleNamespace,
) -> None:
    # Referentiel de NOM, pas une source de fait : un SUBMIT_RUN dont les lignes
    # de timeline tombent juste hors fenetre doit quand meme nommer les lignes
    # reecrites. Seules la source de fait (facturation) et la sortie sont bornees
    # -- 2 bornes et non 3 depuis T001b, la lignee `job_task_run_timeline` (qui
    # portait la troisieme) ayant disparu.
    query, _ = _job_cluster_cost_query(fakes, lower_bound=date(2026, 8, 14))
    assert "r.period_start_time >= DATE" not in query
    assert query.count(">= DATE '") == 2


def test_job_cluster_cost_daily_never_predicates_on_run_type(
    fakes: SimpleNamespace,
) -> None:
    # La disjonction mesuree rend le COALESCE suffisant : un predicat
    # `run_type = 'SUBMIT_RUN'` serait une fausse precision, et se perimerait au
    # prochain type de run que Databricks ajoute.
    query, _ = _job_cluster_cost_query(fakes, lower_bound=None)
    assert "run_type" not in query


# --- Non-regression de l'extraction dans `grain_resolution` (T004) ------------

# Texte EXACT des CTE de resolution du NOM, dont seule la CTE de grain qui les
# alimente varie d'un builder a l'autre (`priced` pour le cout billing-direct,
# `agg` pour l'efficacite). Ce bloc etait ecrit en dur dans ce builder avant son
# extraction dans `grain_resolution.job_name_ctes_sql` (T004) : l'assertion est
# volontairement byte-exacte, c'est ce qui prouve que l'extraction n'a rien
# change au SQL genere.
JOBS_AS_OF_CTE_SQL = """jobs_as_of AS (
        SELECT
            a.cloud_provider,
            a.workspace_id,
            a.job_id,
            a.period_start,
            j.name AS job_name
        FROM {grain_cte} a
        LEFT JOIN it.sch.curated_dbx_lakeflow_jobs j
          ON j.cloud_provider = a.cloud_provider
         AND j.workspace_id = a.workspace_id
         AND j.job_id = a.job_id
         AND j.change_time < a.period_start + INTERVAL 1 DAY
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY a.cloud_provider, a.workspace_id, a.job_id, a.period_start
            ORDER BY j.change_time DESC
        ) = 1
    )"""


def test_job_cluster_cost_daily_jobs_as_of_cte_text_is_unchanged(
    fakes: SimpleNamespace,
) -> None:
    # `priced` porte `compute_kind` dans son grain, mais la partition du QUALIFY
    # reste au grain `(job_id, period_start)` : `jobs_as_of` rend UNE ligne de
    # nom par job-jour, que la jointure aval consomme 1:1 pour chacune des deux
    # lignes d'un job mixte. Meme forme que cote pipeline, aucun fan-out.
    query, _ = _job_cluster_cost_query(fakes, lower_bound=None)
    assert JOBS_AS_OF_CTE_SQL.format(grain_cte="priced") in query


def test_job_efficiency_daily_names_jobs_with_the_very_same_sql(
    fakes: SimpleNamespace,
) -> None:
    # Cout et efficacite doivent nommer un job a l'identique : un ecart de
    # resolution afficherait deux noms differents pour le meme job_id dans deux
    # tables cote a cote.
    sentinel = fakes.DataFrame("job_efficiency_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    build_job_efficiency_daily(
        spark,
        cluster_efficiency_daily_table="it.sch.gold_dbx_compute_cluster_efficiency_daily",
        job_task_run_timeline_table="it.sch.curated_dbx_lakeflow_job_task_run_timeline",
        job_run_timeline_table="it.sch.curated_dbx_lakeflow_job_run_timeline",
        lakeflow_jobs_table="it.sch.curated_dbx_lakeflow_jobs",
        lower_bound=date(2026, 8, 14),
    )
    efficiency_query = spark.sql_calls[0]
    assert JOBS_AS_OF_CTE_SQL.format(grain_cte="agg") in efficiency_query
    cost_query, _ = _job_cluster_cost_query(fakes, lower_bound=date(2026, 8, 14))
    for shared in (
        "j.change_time < a.period_start + INTERVAL 1 DAY",
        "COALESCE(ja.job_name, sr.run_name) AS job_name",
        "MAX(r.run_name) AS run_name",
        "GROUP BY r.cloud_provider, r.workspace_id, r.job_id",
    ):
        assert shared in cost_query, shared
        assert shared in efficiency_query, shared


def test_job_efficiency_daily_still_resolves_the_grain_through_clusters(
    fakes: SimpleNamespace,
) -> None:
    # Ce qui n'est PLUS partage depuis T001b : la resolution du GRAIN. Le cout
    # lit `job_id` sur la facturation, l'efficacite continue de le deduire du
    # `cluster_id` faute de facturation cote `node_timeline` -- d'ou une
    # population plus petite (un job serverless n'a aucune ligne node_timeline),
    # ecart ATTENDU et documente, pas un defaut a combler. Les deux resolutions
    # ont ete confrontees sans desaccord : les 44 234 jours-job CLASSIC de la
    # table de cout precedente se retrouvent tous au meme `(job_id,
    # period_start)` en billing-direct.
    sentinel = fakes.DataFrame("job_efficiency_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    build_job_efficiency_daily(
        spark,
        cluster_efficiency_daily_table="it.sch.gold_dbx_compute_cluster_efficiency_daily",
        job_task_run_timeline_table="it.sch.curated_dbx_lakeflow_job_task_run_timeline",
        job_run_timeline_table="it.sch.curated_dbx_lakeflow_job_run_timeline",
        lakeflow_jobs_table="it.sch.curated_dbx_lakeflow_jobs",
        lower_bound=date(2026, 8, 14),
    )
    efficiency_query = spark.sql_calls[0]
    assert "job_clusters AS (" in efficiency_query
    assert "LATERAL VIEW explode(t.compute) tc AS c" in efficiency_query
    cost_query, _ = _job_cluster_cost_query(fakes, lower_bound=date(2026, 8, 14))
    assert "job_clusters AS (" not in cost_query
