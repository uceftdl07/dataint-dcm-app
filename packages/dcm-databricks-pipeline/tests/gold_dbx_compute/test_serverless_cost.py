"""Tests de `pipelines.gold_dbx_compute.serverless_cost_daily`/`_rolling`.

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`) : chaque builder
construit un unique `spark.sql(...)`, verifie ici via le texte SQL genere
(`FakeSpark`).

Les assertions portent sur des expressions ENTIERES (predicats multi-lignes
inclus) et sont doublees d'assertions NEGATIVES : sur ces deux tables, chaque
piege documente se traduit par une construction SQL qui doit etre presente ET
une construction voisine, credible, qui doit etre absente (`LAG` au lieu du
self-join, `ELSE 'PLATFORM_AUTO'` au lieu de `ELSE 'OTHER'`, `usage_policy_id`
au lieu de `budget_policy_id`, `ELSE 0` sur une fenetre precedente vide...).
"""

from __future__ import annotations

import re
from datetime import date
from types import SimpleNamespace

from pipelines.gold_dbx_compute import specs
from pipelines.gold_dbx_compute.serverless_cost_daily import build_serverless_cost_daily
from pipelines.gold_dbx_compute.serverless_cost_rolling import build_serverless_cost_rolling
from pipelines.gold_dbx_compute.sql_helpers import (
    SERVERLESS_OBJECT_ID_SENTINEL,
    SERVERLESS_SCOPE_PRODUCTS,
    SERVERLESS_SURFACES,
)


def _code_only(query: str) -> str:
    """Requete privee de ses commentaires SQL (`-- ...`).

    Les requetes generees sont abondamment commentees et ces commentaires citent
    justement les constructions interdites ("le COUNT(DISTINCT job_run_id) de la
    facturation", "un LAG() renverrait..."). Toute assertion NEGATIVE porte donc
    sur ce texte-ci : sinon elle passerait au vert le jour ou le code redevient
    faux mais garde son commentaire, ou au rouge sur une simple reformulation de
    commentaire.
    """
    return re.sub(r"--[^\n]*", "", query)


def _output_columns(query: str, from_clause: str) -> tuple[str, ...]:
    """Colonnes du SELECT final, dans l'ordre, alias resolus.

    Le SELECT final est le seul indente a 4 espaces (les CTE sont a 8).
    """
    body = query.rsplit("\n    SELECT\n", 1)[1].split(f"\n    FROM {from_clause}", 1)[0]
    columns: list[str] = []
    for raw in body.splitlines():
        line = raw.strip().rstrip(",")
        if " AS " in line:
            columns.append(line.rsplit(" AS ", 1)[1])
        elif re.fullmatch(r"\w+", line):
            columns.append(line)
        elif re.fullmatch(r"\w+\.\w+", line):
            columns.append(line.split(".", 1)[1])
    return tuple(columns)


# --- serverless_cost_daily ---------------------------------------------------


def _serverless_cost_daily_query(
    fakes: SimpleNamespace, lower_bound: date | None
) -> tuple[str, object]:
    sentinel = fakes.DataFrame("serverless_cost_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_serverless_cost_daily(
        spark,
        billing_usage_table="it.sch.curated_dbx_billing_usage",
        billing_list_prices_table="it.sch.curated_dbx_billing_list_prices",
        warehouses_table="it.sch.curated_dbx_compute_warehouses",
        lakeflow_pipelines_table="it.sch.curated_dbx_lakeflow_pipelines",
        lower_bound=lower_bound,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0], result


def test_serverless_cost_daily_full_run_has_no_lower_bound_filter(
    fakes: SimpleNamespace,
) -> None:
    code = _code_only(_serverless_cost_daily_query(fakes, lower_bound=None)[0])
    assert "usage_date >= DATE" not in code
    assert "period_start >= DATE" not in code


def test_serverless_cost_daily_reads_one_buffer_day_before_the_output_window(
    fakes: SimpleNamespace,
) -> None:
    # 1 jour tampon (J-1) sur la lecture facturation pour que le self-join de
    # cost_usd_prev_day voie J-1 au bord de la fenetre incrementale...
    query, _ = _serverless_cost_daily_query(fakes, lower_bound=date(2026, 8, 14))
    assert "AND usage_date >= DATE '2026-08-13'" in query
    # ... mais la sortie (et donc le MERGE) reste bornee a lower_bound : sans ce
    # second filtre, le jour tampon serait ecrit avec un cout PARTIEL puisque la
    # lecture ne couvre pas sa propre veille.
    assert "AND period_start >= DATE '2026-08-14'" in query
    assert "AND period_start >= DATE '2026-08-13'" not in _code_only(query)


def test_serverless_cost_daily_scope_is_a_whitelist_of_managed_products(
    fakes: SimpleNamespace,
) -> None:
    # Expression ENTIERE, les deux lignes du WHERE : un `in query` sur la seule
    # premiere ligne resterait vrai si l'union des produits manages disparaissait,
    # et la page perdrait alors des surfaces completes (GENIE, AI_ENDPOINT,
    # LAKEBASE, NETWORKING ne portent pas is_serverless = true).
    query, _ = _serverless_cost_daily_query(fakes, lower_bound=None)
    assert (
        "WHERE (product_features.is_serverless = true\n"
        "               OR billing_origin_product IN ('GENIE', 'MODEL_SERVING', "
        "'VECTOR_SEARCH', 'LAKEBASE', 'NETWORKING', 'AI_FUNCTIONS', 'AI_GATEWAY', "
        "'LAKEFLOW_CONNECT', 'SUPERVISOR_AGENT', 'AGENT_EVALUATION'))"
    ) in query
    # LISTE BLANCHE : une liste noire laisserait entrer sans un seul signal le
    # prochain produit ajoute par Databricks.
    code = _code_only(query)
    assert "NOT IN" not in code
    assert "is_serverless = false" not in code
    for product in SERVERLESS_SCOPE_PRODUCTS:
        assert f"'{product}'" in query


def test_serverless_cost_daily_surface_is_never_null(fakes: SimpleNamespace) -> None:
    # `serverless_surface` est une CLE DE MERGE et `merge_into_table` fusionne sur
    # `<=>` null-safe : une valeur NULL ne leve rien, elle fond tout un workspace
    # en une ligne corrompue. La branche ELSE est ce qui l'interdit.
    query, _ = _serverless_cost_daily_query(fakes, lower_bound=None)
    assert "              ELSE 'OTHER'\n            END AS serverless_surface" in query
    # La v1 du spike repliait sur PLATFORM_AUTO : le cout non classe devenait
    # invisible dans une surface credible au lieu de declencher le controle.
    assert "ELSE 'PLATFORM_AUTO'" not in _code_only(query)


def test_serverless_cost_daily_maps_every_declared_surface(fakes: SimpleNamespace) -> None:
    query, _ = _serverless_cost_daily_query(fakes, lower_bound=None)
    assert len(SERVERLESS_SURFACES) == 12
    for surface in SERVERLESS_SURFACES:
        assert f"'{surface}'" in query


def test_serverless_cost_daily_object_id_falls_back_to_the_sentinel(
    fakes: SimpleNamespace,
) -> None:
    # Meme piege que la surface, meme parade : les surfaces sans objet listable
    # (GENIE, PLATFORM_AUTO, NETWORKING, OTHER) restent au grain workspace avec
    # une sentinelle EXPLICITE plutot qu'un NULL.
    query, _ = _serverless_cost_daily_query(fakes, lower_bound=None)
    assert f"              '{SERVERLESS_OBJECT_ID_SENTINEL}'\n            ) AS object_id" in query
    # has_object_key : filtre expose a l'IHM, pour ne pas lui faire comparer une
    # chaine technique.
    assert f"g.object_id <> '{SERVERLESS_OBJECT_ID_SENTINEL}' AS has_object_key" in query
    assert "object_id IS NULL" not in _code_only(query)


def test_serverless_cost_daily_compares_to_the_previous_day_by_self_join(
    fakes: SimpleNamespace,
) -> None:
    # Self-join EXACT sur J-1, egalise sur les DEUX cles derivees. Un LAG() sur
    # une partition ordonnee par date renvoie la ligne PRECEDENTE PRESENTE, pas
    # la veille : un objet inactif 3 jours se verrait compare a J-4 et son
    # cost_delta_pct serait faux sans que rien ne leve.
    query, _ = _serverless_cost_daily_query(fakes, lower_bound=None)
    assert "LAG(" not in _code_only(query)
    assert (
        "        FROM enriched e\n"
        "        LEFT JOIN enriched prev\n"
        "          ON prev.cloud_provider = e.cloud_provider\n"
        "         AND prev.workspace_id = e.workspace_id\n"
        "         AND prev.serverless_surface = e.serverless_surface\n"
        "         AND prev.object_id = e.object_id\n"
        "         AND prev.period_start = e.period_start - INTERVAL 1 DAY"
    ) in query


def test_serverless_cost_daily_restricts_run_metrics_to_the_job_surface(
    fakes: SimpleNamespace,
) -> None:
    # `job_run_id` n'existe QUE sur la surface JOB. La restriction est ce qui rend
    # run_count NULL ailleurs, via le LEFT JOIN : un COALESCE(..., 0) affirmerait
    # "aucune execution" pour un warehouse, ce qui est faux -- la metrique n'y est
    # pas definie.
    query, _ = _serverless_cost_daily_query(fakes, lower_bound=None)
    assert "        WHERE serverless_surface = 'JOB'\n          AND job_run_id IS NOT NULL" in query
    assert "        LEFT JOIN runs_agg ra\n" in query
    code = _code_only(query)
    assert "COALESCE(ra.run_count" not in code
    assert "COALESCE(ra.cost_per_run_histogram" not in code


def test_serverless_cost_daily_aggregates_runs_before_the_histogram(
    fakes: SimpleNamespace,
) -> None:
    # Deux niveaux : `histogram_from_edges_sql` est un agregat de LIGNES, applique
    # directement a la facturation il compterait des tranches de facturation (une
    # execution de 4 min en produit plusieurs), pas des executions.
    query, _ = _serverless_cost_daily_query(fakes, lower_bound=None)
    assert query.index("    runs AS (") < query.index("    runs_agg AS (")
    assert query.index("    runs_agg AS (") < query.index("run_cost_usd <= 0.01")
    assert "SUM(line_cost_usd) AS run_cost_usd" in query
    # COUNT(*) sur `runs` EST le COUNT DISTINCT des executions du jour : le
    # recompter en distinct sur la facturation brute serait un second parcours.
    assert "COUNT(*) AS run_count" in query
    assert "COUNT(DISTINCT job_run_id)" not in _code_only(query)


def test_serverless_cost_daily_prices_lines_before_aggregating_the_grain(
    fakes: SimpleNamespace,
) -> None:
    # La CTE `priced` est VOLONTAIREMENT non agregee, contrairement a son homonyme
    # des builders voisins : le cout par execution doit relire les lignes.
    query, _ = _serverless_cost_daily_query(fakes, lower_bound=None)
    priced_block = _code_only(query).split("    priced AS (", 1)[1].split("    grain AS (", 1)[0]
    assert "GROUP BY" not in priced_block
    assert "k.usage_quantity * COALESCE(lp.effective_price, 0) AS line_cost_usd" in priced_block


def test_serverless_cost_daily_joins_prices_on_the_curated_cloud_column(
    fakes: SimpleNamespace,
) -> None:
    # `cloud_provider` (curated) et non `cloud` (nom systeme) : une jointure de
    # prix sur une colonne inexistante ne leve qu'a l'execution.
    query, _ = _serverless_cost_daily_query(fakes, lower_bound=None)
    assert "          ON lp.cloud_provider = k.cloud_provider\n" in query
    assert "         AND lp.sku_name = k.sku_name\n" in query
    assert "         AND lp.price_start_time <= k.period_start\n" in query
    assert "         AND (lp.price_end_time IS NULL OR k.period_start < lp.price_end_time)" in query
    assert re.search(r"(?<![\w.])cloud(?![\w])", _code_only(query)) is None


def test_serverless_cost_daily_gates_name_resolution_by_surface(
    fakes: SimpleNamespace,
) -> None:
    # Sans le gating, un notebook_id egal par hasard a un warehouse_id nommerait
    # un notebook avec le nom d'un warehouse (0 collision aujourd'hui, mesure sur
    # la fenetre de reference -- le gating est preventif).
    query, _ = _serverless_cost_daily_query(fakes, lower_bound=None)
    gate = "         AND g.serverless_surface IN ("
    assert f"{gate}'SQL_WAREHOUSE')\n" in query
    assert f"{gate}'DLT_PIPELINE', 'MV_ST_REFRESH', 'LAKEBASE')\n" in query
    # Etat connu a un instant QUELCONQUE de la journee agregee : un `<=` sur
    # period_start seul ne verrait que le referentiel d'avant minuit.
    assert "         AND w.change_time < g.period_start + INTERVAL 1 DAY" in query
    assert "         AND pl.change_time < g.period_start + INTERVAL 1 DAY" in query
    assert "change_time <= g.period_start" not in _code_only(query)


def test_serverless_cost_daily_name_cascade_ends_on_the_object_id(
    fakes: SimpleNamespace,
) -> None:
    # object_name JAMAIS NULL : la facturation ne nomme nativement ni les
    # warehouses ni les pipelines (0 % de leur cout), et un objet supprime du
    # referentiel n'y a plus de nom du tout -- d'ou le dernier repli.
    query, _ = _serverless_cost_daily_query(fakes, lower_bound=None)
    assert (
        "            COALESCE(\n"
        "                g.object_name_native, wa.warehouse_name, pa.pipeline_name, g.object_id\n"
        "            ) AS object_name,"
    ) in query


def test_serverless_cost_daily_ranks_within_each_surface(fakes: SimpleNamespace) -> None:
    # Rang PAR SURFACE : l'IHM affiche cette liste filtree par surface, un rang
    # toutes surfaces confondues y commencerait a 40. Douze lignes du meme jour
    # peuvent donc porter cost_rank = 1.
    query, _ = _serverless_cost_daily_query(fakes, lower_bound=None)
    code = _code_only(query)
    assert code.count("PARTITION BY period_start, serverless_surface ORDER BY cost_usd DESC") == 2
    assert "PARTITION BY period_start ORDER BY cost_usd DESC" not in code
    assert "<= 10 AS is_top_cost" in query


def test_serverless_cost_daily_keeps_the_identity_pair_on_the_same_row(
    fakes: SimpleNamespace,
) -> None:
    # identity_principal et identity_source pris sur la MEME ligne source : les
    # calculer independamment (deux MAX) les desynchroniserait sur les lignes de
    # grain portant plusieurs identites, et la matrice de refacturation
    # attribuerait un cout a un principal avec le `source` d'un autre.
    query, _ = _serverless_cost_daily_query(fakes, lower_bound=None)
    assert "ELSE max_by(identity_source, identity_principal)" in query
    assert "MAX(identity_source)" not in _code_only(query)
    # NONE et non NULL quand aucune identite n'est facturee : c'est une
    # information de gouvernance, pas une absence de valeur.
    assert "WHEN MAX(identity_principal) IS NULL THEN 'NONE'" in query


def test_serverless_cost_daily_reads_budget_policy_id_not_usage_policy_id(
    fakes: SimpleNamespace,
) -> None:
    # budget_policy_id est un SUR-ENSEMBLE STRICT d'usage_policy_id (188 744
    # lignes sur 33 879 602 le portent seul, 0 l'inverse, 0 desaccord) : retenir
    # la colonne recente perdrait silencieusement ces attributions.
    query, _ = _serverless_cost_daily_query(fakes, lower_bound=None)
    assert "usage_metadata.budget_policy_id AS budget_policy_id" in query
    assert "usage_policy_id" not in _code_only(query)


def test_serverless_cost_daily_counts_dbu_only_on_dbu_lines(fakes: SimpleNamespace) -> None:
    # La depense serverless est aussi facturee en GB, HOUR et DSU : un
    # SUM(usage_quantity) global additionnerait des gigaoctets a des DBU.
    query, _ = _serverless_cost_daily_query(fakes, lower_bound=None)
    assert "SUM(CASE WHEN usage_unit = 'DBU' THEN usage_quantity ELSE 0 END) AS dbu_quantity" in (
        query
    )
    assert "SUM(usage_quantity) AS dbu_quantity" not in _code_only(query)
    # cost_usd, lui, couvre TOUTES les unites.
    assert "SUM(line_cost_usd) AS cost_usd" in query


def test_serverless_cost_daily_output_matches_its_documented_columns(
    fakes: SimpleNamespace,
) -> None:
    # Un commentaire orphelin fait echouer merge_into_table a l'EXECUTION (un
    # ALTER COLUMN par entree), pas au test : la parite est verifiee ici.
    query, _ = _serverless_cost_daily_query(fakes, lower_bound=None)
    columns = _output_columns(query, "with_prev_day")
    assert columns == (
        "cloud_provider",
        "workspace_id",
        "serverless_surface",
        "object_id",
        "period_start",
        "object_name",
        "billing_origin_product",
        "performance_target",
        "budget_policy_id",
        "identity_principal",
        "identity_source",
        "has_custom_tags",
        "has_object_key",
        "dbu_quantity",
        "cost_usd",
        "cost_usd_prev_day",
        "cost_delta_pct",
        "run_count",
        "cost_per_run_histogram",
        "cost_rank",
        "is_top_cost",
        "_generated_at",
    )
    assert set(columns) == set(specs.SERVERLESS_COST_DAILY_COLUMN_COMMENTS)
    # Les cles de merge sont bien produites par la requete.
    assert set(specs.SERVERLESS_COST_DAILY_MERGE_KEYS) <= set(columns)


# --- serverless_cost_rolling -------------------------------------------------


def _serverless_cost_rolling_query(fakes: SimpleNamespace) -> tuple[str, object]:
    sentinel = fakes.DataFrame("serverless_cost_rolling_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_serverless_cost_rolling(
        spark,
        serverless_cost_daily_table="it.sch.gold_dbx_compute_serverless_cost_daily",
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0], result


def test_serverless_cost_rolling_reads_only_the_daily_table(fakes: SimpleNamespace) -> None:
    query, _ = _serverless_cost_rolling_query(fakes)
    assert "it.sch.gold_dbx_compute_serverless_cost_daily" in query
    # Un rollup de la table gold, jamais une seconde lecture de la facturation :
    # deux chemins de calcul divergeraient sur le meme cout.
    assert "curated_" not in _code_only(query)


def test_serverless_cost_rolling_materializes_the_four_configured_windows(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _serverless_cost_rolling_query(fakes)
    assert specs.ROLLING_WINDOWS == (1, 7, 30, 90)
    assert "explode(array(1, 7, 30, 90)) AS window_days" in query
    assert "SELECT MAX(period_start) AS as_of_date FROM daily" in query


def test_serverless_cost_rolling_reads_twice_the_window_for_the_comparison(
    fakes: SimpleNamespace,
) -> None:
    # 2 x window_days lus pour calculer la fenetre precedente dans le meme
    # GROUP BY, borne haute incluse a as_of_date.
    query, _ = _serverless_cost_rolling_query(fakes)
    assert (
        "        WHERE d.period_start > date_add(a.as_of_date, -2 * w.window_days)\n"
        "          AND d.period_start <= a.as_of_date"
    ) in query


def test_serverless_cost_rolling_leaves_an_empty_previous_window_null(
    fakes: SimpleNamespace,
) -> None:
    # Pas d'`ELSE 0` sur la fenetre precedente : 0 affirmerait "cet objet existait
    # et n'a rien coute", faux d'un objet cree pendant la fenetre courante (son
    # cost_delta_pct passerait de NULL a +infini).
    query, _ = _serverless_cost_rolling_query(fakes)
    assert (
        "            SUM(CASE\n"
        "                    WHEN d.period_start <= date_add(a.as_of_date, -w.window_days)\n"
        "                    THEN d.cost_usd\n"
        "                END) AS cost_usd_prev_window,"
    ) in query
    # La fenetre COURANTE, elle, garde ELSE 0 : un objet present sur la fenetre
    # sans cout ce jour-la a bien coute 0.
    assert (
        "            SUM(CASE\n"
        "                    WHEN d.period_start > date_add(a.as_of_date, -w.window_days)\n"
        "                    THEN d.cost_usd ELSE 0\n"
        "                END) AS cost_usd,"
    ) in query
    # ... et le filtre final doit COALESCE ce NULL, sinon `NULL <> 0` vaut NULL et
    # exclurait l'objet disparu au lieu de le garder a -100 %.
    assert "WHERE m.cost_usd <> 0 OR COALESCE(m.cost_usd_prev_window, 0) <> 0" in query


def test_serverless_cost_rolling_propagates_a_null_run_count(fakes: SimpleNamespace) -> None:
    # run_count quotidien est NULL hors surface JOB : un SUM sans ELSE propage le
    # NULL au lieu de fabriquer un 0 qui affirmerait "aucune execution".
    query, _ = _serverless_cost_rolling_query(fakes)
    assert (
        "            SUM(CASE\n"
        "                    WHEN d.period_start > date_add(a.as_of_date, -w.window_days)\n"
        "                    THEN d.run_count\n"
        "                END) AS run_count,"
    ) in query
    assert "THEN d.run_count ELSE 0" not in _code_only(query)


def test_serverless_cost_rolling_recomputes_percentiles_from_the_merged_histogram(
    fakes: SimpleNamespace,
) -> None:
    # Un percentile n'est ni sommable ni moyennable : une moyenne de p95
    # quotidiens n'a aucune signification statistique. Les percentiles de la
    # fenetre sont RELUS de l'histogramme fusionne.
    query, _ = _serverless_cost_rolling_query(fakes)
    code = _code_only(query)
    # Chaque percentile est verifie DANS SA PROPRE expression : un `in query`
    # global resterait vrai si un seul des trois etait recalcule correctement.
    for column in ("cost_per_run_p50_usd", "cost_per_run_p95_usd", "cost_per_run_p99_usd"):
        expression = code.split(f" END AS {column}", 1)[0].rsplit(
            "CASE WHEN g.run_count IS NULL THEN NULL ELSE ", 1
        )[1]
        assert "g.cost_per_run_histogram_raw" in expression
        assert "d.cost_per_run_p" not in expression
    assert "AVG(" not in code
    assert "percentile(" not in code
    assert "approx_percentile" not in code


def test_serverless_cost_rolling_masks_the_histogram_to_the_current_window(
    fakes: SimpleNamespace,
) -> None:
    # `collect_list` ignore les NULL : sans ce masquage, la fusion melangerait les
    # histogrammes des DEUX fenetres lues (2 x window_days).
    query, _ = _serverless_cost_rolling_query(fakes)
    assert (
        "collect_list(CASE WHEN d.period_start > date_add(a.as_of_date, -w.window_days)"
        " THEN d.cost_per_run_histogram END)"
    ) in query


def test_serverless_cost_rolling_nulls_run_metrics_when_no_run_occurred(
    fakes: SimpleNamespace,
) -> None:
    # `aggregate` sur une liste vide renvoie 0 : l'histogramme fusionne vaut 19
    # zeros, pas NULL. Sans ce masquage, la page afficherait un p50 de 0,005 $
    # (le representant du premier bucket) pour un objet qui n'a rien execute.
    query, _ = _serverless_cost_rolling_query(fakes)
    assert (
        "            CASE\n"
        "                WHEN g.run_count IS NULL THEN NULL\n"
        "                ELSE g.cost_per_run_histogram_raw\n"
        "            END AS cost_per_run_histogram,"
    ) in query
    # Le meme masque protege les TROIS percentiles.
    assert _code_only(query).count("CASE WHEN g.run_count IS NULL THEN NULL ELSE ") == 3


def test_serverless_cost_rolling_takes_attributes_at_the_full_object_grain(
    fakes: SimpleNamespace,
) -> None:
    # Partition INCLUANT serverless_surface : contrairement au compute_kind de
    # pipeline_cost_rolling, la surface fait partie de l'identite de l'objet et
    # ses attributs en dependent (le nom d'un dlt_pipeline_id vu en
    # MV_ST_REFRESH n'est pas celui du meme id vu en DLT_PIPELINE).
    query, _ = _serverless_cost_rolling_query(fakes)
    assert (
        "        QUALIFY ROW_NUMBER() OVER (\n"
        "            PARTITION BY cloud_provider, workspace_id, serverless_surface, object_id\n"
        "            ORDER BY period_start DESC\n"
        "        ) = 1"
    ) in query


def test_serverless_cost_rolling_ranks_within_window_and_surface(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _serverless_cost_rolling_query(fakes)
    code = _code_only(query)
    assert (
        code.count("PARTITION BY m.window_days, m.serverless_surface ORDER BY m.cost_usd DESC") == 2
    )
    assert "PARTITION BY m.window_days ORDER BY m.cost_usd DESC" not in code
    assert "<= 10 AS is_top_cost" in query


def test_serverless_cost_rolling_inherits_the_sentinel_from_the_daily_table(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _serverless_cost_rolling_query(fakes)
    assert f"m.object_id <> '{SERVERLESS_OBJECT_ID_SENTINEL}' AS has_object_key" in query
    code = _code_only(query)
    assert "object_id IS NULL" not in code
    assert "LAG(" not in code


def test_serverless_cost_rolling_output_matches_its_documented_columns(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _serverless_cost_rolling_query(fakes)
    columns = _output_columns(query, "with_metrics m")
    assert columns == (
        "cloud_provider",
        "workspace_id",
        "serverless_surface",
        "object_id",
        "window_days",
        "as_of_date",
        "window_start",
        "object_name",
        "billing_origin_product",
        "performance_target",
        "budget_policy_id",
        "identity_principal",
        "identity_source",
        "has_custom_tags",
        "has_object_key",
        "dbu_quantity",
        "cost_usd",
        "cost_usd_prev_window",
        "cost_delta_pct",
        "run_count",
        "cost_per_run_histogram",
        "cost_per_run_p50_usd",
        "cost_per_run_p95_usd",
        "cost_per_run_p99_usd",
        "cost_rank",
        "is_top_cost",
        "_generated_at",
    )
    assert set(columns) == set(specs.SERVERLESS_COST_ROLLING_COLUMN_COMMENTS)
    assert set(specs.SERVERLESS_COST_ROLLING_MERGE_KEYS) <= set(columns)
