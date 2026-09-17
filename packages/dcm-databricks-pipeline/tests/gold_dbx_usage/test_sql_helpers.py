"""Tests de `pipelines.gold_dbx_usage.sql_helpers` (helpers purs, sans Spark)."""

from __future__ import annotations

from datetime import date

from pipelines.gold_dbx_usage.sql_helpers import (
    CONSUMER_TYPE_UNKNOWN,
    COST_ATTRIBUTION_EQUAL_PARTS_FALLBACK,
    COST_ATTRIBUTION_WEIGHTED_BYTES,
    LIFECYCLE_STATE_ACTIVE,
    LIFECYCLE_STATE_DELETED,
    LIFECYCLE_STATE_UNKNOWN,
    decode_consumer_type_priority,
    encode_consumer_type_priority,
    equal_parts_share,
    lower_bound_predicate,
    non_null_entity_type_predicate,
    split_full_name,
    sql_string_list,
)


def test_lower_bound_predicate_none_is_empty() -> None:
    assert lower_bound_predicate("period_start", None) == ""


def test_lower_bound_predicate_formats_date_literal() -> None:
    assert (
        lower_bound_predicate("period_start", date(2026, 8, 14))
        == "AND period_start >= DATE '2026-08-14'"
    )


def test_sql_string_list_formats_literal_list() -> None:
    assert sql_string_list(("FAILED", "CANCELED")) == "'FAILED', 'CANCELED'"


def test_split_full_name_indexes_out_of_bounds_safely() -> None:
    """`get(arr, i)` et non `arr[i]` : hors bornes, le crochet leve
    `INVALID_ARRAY_INDEX` en mode ANSI et fait echouer TOUT le run, la ou `get`
    renvoie NULL sur la seule ligne concernee. Les valeurs traitees viennent de
    `request_params`, ou rien ne garantit un nom qualifie en trois parties."""
    catalog, schema, table = split_full_name("request_params['full_name_arg']")
    assert catalog == "get(split(request_params['full_name_arg'], '\\\\.'), 0)"
    assert schema == "get(split(request_params['full_name_arg'], '\\\\.'), 1)"
    assert table == "get(split(request_params['full_name_arg'], '\\\\.'), 2)"


def test_cost_attribution_constants_are_distinct() -> None:
    assert COST_ATTRIBUTION_WEIGHTED_BYTES != COST_ATTRIBUTION_EQUAL_PARTS_FALLBACK


def test_lifecycle_states_are_the_three_documented_values() -> None:
    """Domaine ferme de `lifecycle_state` : tout autre etat rendrait `is_deleted`
    inderivable, puisque le booleen se lit exactement comme `= DELETED`."""
    assert LIFECYCLE_STATE_ACTIVE == "ACTIVE"
    assert LIFECYCLE_STATE_DELETED == "DELETED"
    assert LIFECYCLE_STATE_UNKNOWN == "UNKNOWN"


def test_lifecycle_states_are_distinct() -> None:
    """Deux etats partageant une valeur confondraient « absente sans preuve » et
    « supprimee », le faux positif que la corroboration existe pour ecarter."""
    states = {LIFECYCLE_STATE_ACTIVE, LIFECYCLE_STATE_DELETED, LIFECYCLE_STATE_UNKNOWN}
    assert len(states) == 3


def test_non_null_entity_type_predicate_is_null_safe() -> None:
    """`!=` est NULL-unsafe : il ecarterait silencieusement les lignes a NULL."""
    assert (
        non_null_entity_type_predicate("entity_type", "DBSQL_QUERY")
        == "entity_type IS DISTINCT FROM 'DBSQL_QUERY'"
    )


def test_consumer_type_priority_encode_decode_roundtrip() -> None:
    """Priorite USER > SERVICE_PRINCIPAL > tout le reste, et non l'ordre alphabetique
    qu'un `MAX()` brut appliquerait."""
    encoded_user = (
        "CASE consumer_type "
        "WHEN 'USER' THEN '3_' "
        "WHEN 'SERVICE_PRINCIPAL' THEN '2_' "
        "ELSE '1_' END"
    )
    assert encode_consumer_type_priority("consumer_type") == (
        f"CONCAT({encoded_user}, consumer_type)"
    )
    assert decode_consumer_type_priority("ranked") == "SUBSTRING(ranked, 3)"
    # Le prefixe numerique trie USER (3_) apres SERVICE_PRINCIPAL (2_) apres le
    # reste (1_) dans un tri lexicographique, l'ordre que MAX() doit suivre.
    assert sorted(["1_JOB", "2_SERVICE_PRINCIPAL", "3_USER"])[-1] == "3_USER"


def test_consumer_type_unknown_is_never_sql_null_literal() -> None:
    """`consumer_type` est categorique : son absence s'ecrit avec un libelle
    explicite, jamais avec un NULL."""
    assert CONSUMER_TYPE_UNKNOWN == "UNKNOWN"


def test_equal_parts_share_reconciles_to_total_multi_data_product() -> None:
    # SUM(part) = cout total de la requete, cas synthetique a 3 data products.
    total_cost = 9.0
    n_parts = 3
    parts = [equal_parts_share(total_cost, n_parts) for _ in range(n_parts)]
    assert sum(parts) == total_cost
    assert parts == [3.0, 3.0, 3.0]


def test_equal_parts_share_reconciles_with_uneven_division() -> None:
    total_cost = 10.0
    n_parts = 3
    parts = [equal_parts_share(total_cost, n_parts) for _ in range(n_parts)]
    assert sum(parts) == total_cost


def test_equal_parts_share_zero_parts_never_divides_by_zero() -> None:
    assert equal_parts_share(10.0, 0) == 0.0
