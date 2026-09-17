"""Tests de `pipelines.gold_dbx_usage.table_query_performance_daily`."""

from __future__ import annotations

import re
from datetime import date
from types import SimpleNamespace

from pipelines.gold_dbx_usage.ephemeral_tables import (
    EPHEMERAL_KEYS_CTE_NAME,
    not_ephemeral_predicate,
)
from pipelines.gold_dbx_usage.specs import (
    LATENCY_BUCKET_OVERFLOW_KEY,
    LATENCY_BUCKET_UPPER_BOUNDS_MS,
)
from pipelines.gold_dbx_usage.table_query_performance_daily import (
    build_table_query_performance_daily,
)
from tests.conftest import strip_sql_comments


def _perf_query(fakes: SimpleNamespace, lower_bound: date | None) -> str:
    sentinel = fakes.DataFrame("table_query_performance_daily_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_table_query_performance_daily(
        spark,
        lineage_table="it.sch.curated_dbx_access_table_lineage",
        query_history_table="it.sch.curated_dbx_query_history",
        uc_tables_table="it.sch.curated_dbx_uc_tables",
        table_operations_table="it.sch.curated_dbx_uc_table_operations",
        lower_bound=lower_bound,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0]


def _executed_sql(fakes: SimpleNamespace, lower_bound: date | None) -> str:
    """SQL rendu, prive de ses commentaires (cf. `strip_sql_comments`)."""
    return strip_sql_comments(_perf_query(fakes, lower_bound))


def test_perf_full_run_has_no_lower_bound_filter(fakes: SimpleNamespace) -> None:
    query = _perf_query(fakes, lower_bound=None)
    assert "event_date >= DATE" not in query
    assert "to_date(start_time) >= DATE" not in query


def test_perf_incremental_run_filters_lineage_and_query_history(
    fakes: SimpleNamespace,
) -> None:
    query = _perf_query(fakes, lower_bound=date(2026, 8, 14))
    assert "AND event_date >= DATE '2026-08-14'" in query
    assert "AND to_date(start_time) >= DATE '2026-08-14'" in query


def test_perf_discriminates_on_statement_id_not_entity_type(
    fakes: SimpleNamespace,
) -> None:
    """`entity_type = 'DBSQL_QUERY'` ne retient qu'une fraction du lineage : la
    latence decrite serait celle des seules requetes DBSQL interactives, sous le nom
    de tous les acces. Le critere de joignabilite a `query_history` est la presence
    d'un `statement_id`."""
    query = _executed_sql(fakes, lower_bound=None)
    assert "entity_type" not in query
    assert "AND statement_id IS NOT NULL" in query


def test_perf_source_type_covers_every_named_uc_object(fakes: SimpleNamespace) -> None:
    """Lire une vue est une lecture : `source_type = 'TABLE'` seul l'ignore.
    Seul `PATH` reste exclu (pas de nom qualifie en trois parties a resoudre)."""
    query = _executed_sql(fakes, lower_bound=None)
    assert "source_type = 'TABLE'" not in query
    for object_type in ("'TABLE'", "'VIEW'", "'MATERIALIZED_VIEW'", "'STREAMING_TABLE'"):
        assert object_type in query
    assert "'PATH'" not in query


def test_perf_lineage_is_deduplicated_before_the_join(fakes: SimpleNamespace) -> None:
    """`lineage_query` doit AGREGER au grain (statement, objet lu).

    En projection, un statement present sur N lignes de lineage (fan-out des cibles,
    `event_id` repetable, expansion de vue) compterait N fois dans `failed_count`,
    `bytes_scanned`, `rows_scanned` et dans la ponderation des percentiles, la ou
    `query_count` fait `COUNT(DISTINCT statement_id)`.
    """
    query = _perf_query(fakes, lower_bound=None)
    lineage_cte = query.split("lineage_query AS (")[1].split("query_history_filtered AS (")[0]
    assert "GROUP BY" in lineage_cte
    assert "statement_id, source_table_full_name" in lineage_cte


def test_perf_grain_reads_native_lineage_columns(fakes: SimpleNamespace) -> None:
    """Le lineage publie les 3 parties du nom en colonnes natives : les reconstituer
    par `split()` n'ajoute que des facons d'avoir tort. Le GROUP BY porte sur les
    colonnes et non sur les alias, pour ne dependre d'aucune resolution d'alias
    laterale."""
    query = _executed_sql(fakes, lower_bound=None)
    assert "split(source_table_full_name" not in query
    assert "source_table_catalog AS catalog" in query
    assert (
        "GROUP BY\n"
        "            cloud_provider, workspace_id, statement_id, source_table_full_name,\n"
        "            source_table_catalog, source_table_schema, source_table_name"
    ) in query


def test_perf_failure_rate_numerator_and_denominator_count_the_same_thing(
    fakes: SimpleNamespace,
) -> None:
    """`SUM(CASE ...)` (des lignes) sur `COUNT(DISTINCT statement_id)` (des requetes)
    laisserait `failure_rate_pct` depasser 100 % des qu'une requete en echec apparait
    sur plusieurs lignes de lineage."""
    query = _executed_sql(fakes, lower_bound=None)
    assert "SUM(CASE WHEN execution_status" not in query
    assert (
        "COUNT(DISTINCT CASE WHEN execution_status IN ('FAILED', 'CANCELED')\n"
        "                            THEN statement_id END) AS failed_count"
    ) in query


def test_perf_join_does_not_require_matching_dates(fakes: SimpleNamespace) -> None:
    """`qh.period_start = lq.period_start` en condition de jointure ecarterait tout
    statement dont l'evenement de lineage et le `start_time` encadrent minuit.

    La date de perf retenue est celle de la requete. `workspace_id` fait partie de la
    cle : un `statement_id` n'est unique qu'au sein d'un workspace."""
    query = _executed_sql(fakes, lower_bound=None)
    assert "qh.period_start = lq.period_start" not in query
    assert "qh.workspace_id = lq.workspace_id" in query
    assert "lq.cloud_provider, qh.period_start," in query


def test_perf_computes_failure_rate_and_percentile_latencies(fakes: SimpleNamespace) -> None:
    query = _perf_query(fakes, lower_bound=None)
    assert "execution_status IN ('FAILED', 'CANCELED')" in query
    assert "percentile_approx(total_duration_ms, 0.50) AS latency_p50_ms" in query
    assert "percentile_approx(total_duration_ms, 0.95) AS latency_p95_ms" in query


def test_perf_query_count_is_distinct_statement_id(fakes: SimpleNamespace) -> None:
    query = _perf_query(fakes, lower_bound=None)
    assert "COUNT(DISTINCT statement_id) AS query_count" in query


# --- latency_bucket_counts (histogramme additionnable) -----------------------

_BUCKET_ENTRY_RE = re.compile(
    r"'(?P<key>[^']+)', COUNT\(DISTINCT CASE WHEN "
    r"(?P<predicate>total_duration_ms [^)]+?) THEN statement_id END\)"
)


def _bucket_entries(fakes: SimpleNamespace) -> list[tuple[str, str]]:
    """Couples (cle, predicat) du MAP `latency_bucket_counts` du SQL rendu."""
    query = _executed_sql(fakes, lower_bound=None)
    histogram_sql = query.split("map_filter(map(")[1].split("), (bucket, n) ->")[0]
    return [(m["key"], m["predicate"]) for m in _BUCKET_ENTRY_RE.finditer(histogram_sql)]


def _bucket_bounds(predicate: str) -> tuple[float, float]:
    """(borne basse EXCLUE, borne haute INCLUSE) portees par un predicat de bucket."""
    low, high = float("-inf"), float("inf")
    for clause in predicate.split(" AND "):
        _, operator, value = clause.split(" ")
        if operator == ">":
            low = float(value)
        else:
            high = float(value)
    return low, high


def test_perf_latency_bucket_keys_come_from_the_declared_bounds(
    fakes: SimpleNamespace,
) -> None:
    """Les cles du MAP sont un CONTRAT : les changer rend l'historique deja ecrit
    inadditionnable. Elles doivent donc suivre la constante, jamais un litteral
    recopie dans le SQL."""
    keys = [key for key, _ in _bucket_entries(fakes)]
    assert keys == [str(bound) for bound in LATENCY_BUCKET_UPPER_BOUNDS_MS] + [
        LATENCY_BUCKET_OVERFLOW_KEY
    ]


def test_perf_latency_buckets_partition_every_possible_duration(
    fakes: SimpleNamespace,
) -> None:
    """Conservation : chaque duree tombe dans EXACTEMENT un bucket.

    C'est ce qui garantit `SUM(map_values(latency_bucket_counts)) = query_count` :
    des bornes qui se chevauchent compteraient un statement deux fois, un trou
    entre deux bornes en perdrait. Teste sur les bornes elles-memes (`d = b`, qui
    doit tomber dans le bucket `b` et pas dans le suivant) et sur leurs voisines
    immediates, la ou un `>=` a la place d'un `>` se voit.
    """
    buckets = [_bucket_bounds(predicate) for _, predicate in _bucket_entries(fakes)]
    samples = [0.0, 0.5, 1e12]
    for bound in LATENCY_BUCKET_UPPER_BOUNDS_MS:
        samples.extend((bound - 1, float(bound), bound + 1))
    for duration in samples:
        matched = [(low, high) for low, high in buckets if low < duration <= high]
        assert len(matched) == 1, f"duree {duration} ms dans {len(matched)} buckets"


def test_perf_latency_buckets_count_distinct_statements(fakes: SimpleNamespace) -> None:
    """`COUNT(*)` compterait des LIGNES du grain quand `query_count` compte des
    statements distincts : la somme des buckets depasserait alors `query_count`
    des qu'une table est lue depuis deux workspaces par le meme statement."""
    entries = _bucket_entries(fakes)
    assert len(entries) == len(LATENCY_BUCKET_UPPER_BOUNDS_MS) + 1
    histogram_sql = _executed_sql(fakes, lower_bound=None).split("map_filter(map(")[1]
    assert "COUNT(*)" not in histogram_sql.split("), (bucket, n) ->")[0]


def test_perf_latency_buckets_omit_empty_buckets(fakes: SimpleNamespace) -> None:
    """Une tranche sans requete n'a pas de compteur a zero, elle n'a pas de cle."""
    query = _executed_sql(fakes, lower_bound=None)
    assert "), (bucket, n) -> n > 0) AS latency_bucket_counts" in query


def test_perf_keeps_the_daily_percentile_alongside_the_histogram(
    fakes: SimpleNamespace,
) -> None:
    """L'histogramme s'ajoute, il ne remplace pas : un lecteur de `latency_p95_ms`
    ne doit pas casser."""
    query = _executed_sql(fakes, lower_bound=None)
    assert "percentile_approx(total_duration_ms, 0.95) AS latency_p95_ms" in query
    assert "AS latency_bucket_counts" in query


def test_perf_carries_its_own_ephemeral_filter(fakes: SimpleNamespace) -> None:
    """Cette table n'herite d'aucun filtre : elle lit le lineage et `query_history`.

    `table_popularity_daily` et `consumer_daily` derivent de `gold_dbx_usage_table_daily`
    et heritent du filtre pose la ; celle-ci ne lit aucune table gold, donc sans son propre
    filtre une table de staging creee, lue et droppee par un meme run garderait ses lignes
    de perf -- et l'exclusion en aval ne pourrait plus les cacher, puisqu'elle lit la
    PRESENCE d'une ligne `is_deleted` au registre, que la purge retire.
    """
    query = _perf_query(fakes, lower_bound=None)
    assert f"WITH {EPHEMERAL_KEYS_CTE_NAME}_referentiel AS (" in query
    assert "it.sch.curated_dbx_uc_tables" in query
    assert "it.sch.curated_dbx_uc_table_operations" in query
    assert not_ephemeral_predicate("lq") in query


def test_perf_ephemeral_filter_applies_to_the_lineage_side_of_the_join(
    fakes: SimpleNamespace,
) -> None:
    """Filtre pose sur `lq`, la relation qui porte la cle de table.

    `qh` (l'historique de requetes) n'a ni catalogue ni nom de table : un filtre pose de ce
    cote ne compilerait pas, et un filtre pose apres l'agregat finale arriverait apres que
    les compteurs ont deja ete calcules sur la population non filtree.
    """
    query = _perf_query(fakes, lower_bound=None)
    joined = query.partition("joined AS (")[2].partition("\n    )")[0]
    assert joined, "la CTE `joined` a change de forme"
    assert not_ephemeral_predicate("lq") in joined
