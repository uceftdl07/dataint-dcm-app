"""Tests de `pipelines.gold_dbx_compute.warehouse_utilization_rolling` (regles de derivation).

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`) :
`build_warehouse_utilization_rolling` construit un unique `spark.sql(...)`,
verifie ici via le texte SQL genere (`FakeSpark`).
"""

from __future__ import annotations

from types import SimpleNamespace

from pipelines.gold_dbx_compute.warehouse_utilization_rolling import (
    build_warehouse_utilization_rolling,
)


def _rolling_query(fakes: SimpleNamespace) -> tuple[str, object]:
    sentinel = fakes.DataFrame("warehouse_utilization_rolling_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_warehouse_utilization_rolling(
        spark,
        warehouse_utilization_daily_table="it.sch.gold_dbx_compute_warehouse_utilization_daily",
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0], result


def test_utilization_rolling_reads_only_daily_table_no_curated(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "it.sch.gold_dbx_compute_warehouse_utilization_daily" in query
    assert "curated_" not in query


def test_utilization_rolling_materializes_the_four_configured_windows(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "explode(array(1, 7, 30, 90)) AS window_days" in query


def test_utilization_rolling_anchors_windows_on_max_period_start(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "MAX(period_start) AS as_of_date" in query
    assert "date_add(a.as_of_date, -(w.window_days - 1)) AS window_start" in query


def test_utilization_rolling_uses_current_window_only(fakes: SimpleNamespace) -> None:
    # Pas de fenetre precedente ni de delta pour l'utilisation (aligne sur la
    # table quotidienne source qui n'en a pas).
    query, _ = _rolling_query(fakes)
    assert "d.period_start > date_add(a.as_of_date, -w.window_days)" in query
    assert "d.period_start <= a.as_of_date" in query
    assert "prev_window" not in query
    assert "2 * w.window_days" not in query


def test_utilization_rolling_sums_additive_metrics(fakes: SimpleNamespace) -> None:
    query, _ = _rolling_query(fakes)
    assert "SUM(d.running_hours) AS running_hours" in query
    assert "SUM(d.active_query_hours) AS active_query_hours" in query
    assert "SUM(d.scale_up_events) AS scale_up_events" in query
    assert "SUM(d.scale_down_events) AS scale_down_events" in query
    assert "SUM(d.estimated_savings_usd) AS estimated_savings_usd" in query


def test_utilization_rolling_recomputes_ratios_over_window(fakes: SimpleNamespace) -> None:
    # idle_pct et active_to_running_ratio recalcules a partir des sommes de la
    # fenetre, pas la moyenne des ratios quotidiens.
    query, _ = _rolling_query(fakes)
    assert (
        "(g.running_hours - g.active_query_hours) / NULLIF(g.running_hours, 0) * 100"
        in query
    )
    assert "g.active_query_hours / NULLIF(g.running_hours, 0) AS active_to_running_ratio" in query


def test_utilization_rolling_weights_avg_cluster_count_by_running_hours(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "SUM(d.avg_cluster_count * d.running_hours)" in query
    assert "SUM(CASE WHEN d.avg_cluster_count IS NOT NULL" in query


def test_utilization_rolling_takes_max_of_maxima(fakes: SimpleNamespace) -> None:
    query, _ = _rolling_query(fakes)
    assert "MAX(d.max_cluster_count) AS max_cluster_count" in query
    assert "MAX(d.peak_concurrency) AS peak_concurrency" in query


def test_utilization_rolling_recomputes_status_from_window_metrics(
    fakes: SimpleNamespace,
) -> None:
    # Diagnostic recalcule sur les metriques de la fenetre. UNDER utilise
    # max_cluster_count (max observe) comme proxy de capacite.
    query, _ = _rolling_query(fakes)
    assert "WHEN m.idle_pct > 60.0 THEN 'OVER'" in query
    assert "WHEN m.peak_concurrency >= m.max_cluster_count * 0.8" in query
    assert "AS utilization_status" in query
    assert "AS rightsizing_reco" in query


def test_utilization_rolling_keeps_latest_auto_stop_config(fakes: SimpleNamespace) -> None:
    query, _ = _rolling_query(fakes)
    assert (
        "QUALIFY ROW_NUMBER() OVER (\n"
        "            PARTITION BY cloud_provider, workspace_id, warehouse_id\n"
        "            ORDER BY period_start DESC\n"
        "        ) = 1" in query
    )
    assert "la.auto_stop_minutes" in query
    assert "la.has_auto_stop" in query


def test_utilization_rolling_keeps_latest_warehouse_name(fakes: SimpleNamespace) -> None:
    """`warehouse_name` suit la meme regle que `auto_stop_minutes` : dernier jour connu.

    Un warehouse renomme au milieu d'une fenetre de 90 jours y apparait sous son
    nom le PLUS RECENT (`latest_attrs`, `ORDER BY period_start DESC`), pas sous
    celui du premier jour : c'est le seul nom qui permette de le retrouver tel
    qu'il s'appelle aujourd'hui. Aucune relecture curated (rollup pur).
    """
    query, _ = _rolling_query(fakes)
    # Lu dans la CTE `daily` puis repris dans `latest_attrs` : 2 occurrences a
    # la maille des colonnes de CTE (indentation 12).
    assert query.count("            warehouse_name,\n") == 2
    assert (
        "QUALIFY ROW_NUMBER() OVER (\n"
        "            PARTITION BY cloud_provider, workspace_id, warehouse_id\n"
        "            ORDER BY period_start DESC\n"
        "        ) = 1" in query
    )
    assert "la.warehouse_name" in query


def test_utilization_rolling_propagates_is_serverless_as_window_max(
    fakes: SimpleNamespace,
) -> None:
    """`is_serverless` de la fenetre = au moins un jour serverless (`MAX`).

    Le discriminant n'est pas re-derive de la facturation (rollup pur, aucune
    relecture curated) : il est lu sur la table quotidienne et agrege par `MAX`.
    Des qu'une partie du temps allume de la fenetre est serverless, les ratios
    recalcules sur les sommes ne sont plus interpretables economiquement -- meme
    biais volontaire que la table quotidienne sur un jour mixte.
    """
    query, _ = _rolling_query(fakes)
    assert "            is_serverless\n" in query
    assert "MAX(CASE WHEN d.is_serverless THEN 1 ELSE 0 END) = 1 AS is_serverless" in query
    assert "        m.is_serverless,\n" in query


def test_utilization_rolling_neutralizes_efficiency_fields_on_serverless(
    fakes: SimpleNamespace,
) -> None:
    """La neutralisation serverless est REFAITE sur les metriques de la fenetre.

    Non-regression du contournement le plus tentant : neutraliser seulement la
    table quotidienne. `idle_pct`, `active_to_running_ratio`,
    `utilization_status` et `rightsizing_reco` sont RECALCULES ici a partir des
    sommes de la fenetre -- un `idle_pct` de 96 % et un verdict `OVER` non
    actionnables reapparaitraient donc a la maille fenetre, et c'est cette table
    que lit `recommendations.py` (fenetre 30 j).
    """
    query, _ = _rolling_query(fakes)
    final_select = query[query.rindex("    SELECT\n") :]
    neutralized = (
        "idle_pct",
        "active_to_running_ratio",
        "auto_stop_minutes",
        "has_auto_stop",
        "utilization_status",
        "rightsizing_reco",
        "estimated_savings_usd",
    )
    for field in neutralized:
        alias = f" AS {field},"
        assert alias in final_select, field
        expression = final_select[: final_select.index(alias)].rsplit(",\n", 1)[-1]
        assert "WHEN m.is_serverless THEN NULL" in expression, field
    # Les metriques d'activite de la fenetre restent servies telles quelles.
    for field in ("running_hours", "active_query_hours", "peak_concurrency"):
        assert f"        m.{field},\n" in final_select, field


def test_utilization_rolling_takes_the_latest_known_warehouse_type_of_the_window(
    fakes: SimpleNamespace,
) -> None:
    """`warehouse_type` de la fenetre = dernier jour RENSEIGNE, pas dernier jour.

    Une fenetre de 90 jours peut melanger des jours de types differents, ou des
    jours sans type connu du tout (warehouse absent du referentiel ce jour-la, ou
    jour ecrit avant que la colonne existe). La cle de tri de `MAX_BY` est donc
    masquee a NULL sur ces jours, ce qui les fait ignorer : verifie sur DBSQL le
    2026-09-11, `MAX_BY(wt, d)` rend NULL sur une fenetre dont le dernier jour est
    vide la ou la version masquee rend le 'PRO' de l'avant-veille. Agrege par
    fenetre plutot que repris dans `latest_attrs` : cette CTE sert le dernier jour
    tout court et propagerait justement ce NULL. Rollup pur : la valeur vient de
    la table quotidienne, aucune relecture curated.
    """
    query, _ = _rolling_query(fakes)
    # Lu dans la CTE `daily` (maille des colonnes de CTE, indentation 12).
    assert query.count("            warehouse_type,\n") == 1
    assert (
        "            MAX_BY(\n"
        "                d.warehouse_type,\n"
        "                CASE WHEN d.warehouse_type IS NOT NULL THEN d.period_start END\n"
        "            ) AS warehouse_type" in query
    )
    # Pas d'attribut de type dans `latest_attrs` : sa regle (dernier jour tout
    # court) n'est PAS celle de cette colonne.
    latest_attrs = query[query.index("latest_attrs AS (") : query.index("    agg AS (")]
    assert "warehouse_type" not in latest_attrs


def test_utilization_rolling_warehouse_type_never_contradicts_is_serverless(
    fakes: SimpleNamespace,
) -> None:
    """La subordination a `is_serverless` est REFAITE ici, pas seulement heritee.

    Meme raisonnement que la neutralisation des champs d'efficience : cette table
    ne doit pas rester coherente uniquement parce qu'une invariante est tenue dans
    la table quotidienne. `is_serverless` de la fenetre est un `MAX` (au moins un
    jour serverless), donc plus large que celui d'un jour : une fenetre mixte doit
    afficher `SERVERLESS`, sinon la ligne annoncerait « PRO » a cote d'un
    diagnostic d'efficience vide -- exactement la contradiction sur laquelle le
    backend s'appuie pour supprimer les economies non encaissables. Ce test echoue
    si les branches sont reordonnees ou si `m.warehouse_type` est servi brut.
    """
    query, _ = _rolling_query(fakes)
    assert (
        "        CASE\n"
        "            WHEN m.is_serverless THEN 'SERVERLESS'\n"
        "            WHEN m.warehouse_type = 'SERVERLESS' THEN NULL\n"
        "            ELSE m.warehouse_type\n"
        "        END AS warehouse_type,\n" in query
    )
    final_select = query[query.rindex("    SELECT\n") :]
    assert "        m.warehouse_type,\n" not in final_select
    assert "        m.is_serverless,\n" in final_select


def test_utilization_rolling_excludes_warehouses_never_running(
    fakes: SimpleNamespace,
) -> None:
    query, _ = _rolling_query(fakes)
    assert "WHERE m.running_hours > 0" in query


def test_utilization_rolling_custom_windows(fakes: SimpleNamespace) -> None:
    sentinel = fakes.DataFrame("warehouse_utilization_rolling_result")
    spark = fakes.Spark(sql_result=sentinel)
    build_warehouse_utilization_rolling(
        spark,
        warehouse_utilization_daily_table="it.sch.gold_dbx_compute_warehouse_utilization_daily",
        rolling_windows=(1, 14),
    )
    query = spark.sql_calls[0]
    assert "explode(array(1, 14)) AS window_days" in query
