"""Tests de `pipelines.gold_dbx_usage.table_governance` (regles de derivation).

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`) :
`build_table_governance` construit un unique `spark.sql(...)`, verifie ici
via le texte SQL genere (`FakeSpark`), meme pattern que
`test_table_catalog.py`.
"""

from __future__ import annotations

from types import SimpleNamespace

from pipelines.gold_dbx_usage.table_governance import build_table_governance


def _table_governance_query(fakes: SimpleNamespace) -> str:
    sentinel = fakes.DataFrame("table_governance_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_table_governance(
        spark,
        table_catalog_table="it.sch.gold_dbx_usage_table_catalog",
        table_popularity_daily_table="it.sch.gold_dbx_usage_table_popularity_daily",
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0]


def test_table_governance_is_unused_is_null_safe(fakes: SimpleNamespace) -> None:
    query = _table_governance_query(fakes)
    assert "(days_since_last_read IS NULL OR days_since_last_read > 90)" in query
    assert "AS is_unused" in query


def test_table_governance_is_orphan_when_all_three_tags_are_null(
    fakes: SimpleNamespace,
) -> None:
    query = _table_governance_query(fakes)
    assert (
        "(owner IS NULL AND domain IS NULL AND cost_center IS NULL) AS is_orphan" in query
    )


def test_table_governance_is_stale_but_consumed_formula(fakes: SimpleNamespace) -> None:
    query = _table_governance_query(fakes)
    assert "freshness_lag_hours > 24 AND days_since_last_read < 7" in query
    assert "AS is_stale_but_consumed" in query


def test_table_governance_is_critical_uses_fanout_threshold(fakes: SimpleNamespace) -> None:
    query = _table_governance_query(fakes)
    assert "(downstream_fanout >= 5) AS is_critical" in query


def test_table_governance_downstream_fanout_dedup_via_qualify_row_number(
    fakes: SimpleNamespace,
) -> None:
    query = _table_governance_query(fakes)
    assert "QUALIFY ROW_NUMBER() OVER (" in query
    assert "ORDER BY period_start DESC" in query
    assert query.count("= 1") >= 1


def test_table_governance_has_no_source_lz_id_or_subscription_account_id(
    fakes: SimpleNamespace,
) -> None:
    query = _table_governance_query(fakes)
    assert "source_lz_id" not in query
    assert "subscription_or_account_id" not in query


def test_table_governance_recommended_action_and_severity_case_expressions(
    fakes: SimpleNamespace,
) -> None:
    query = _table_governance_query(fakes)
    assert "AS recommended_action" in query
    assert "WHEN is_unused THEN 'archiver'" in query
    assert "WHEN is_orphan THEN 'documenter'" in query
    assert "WHEN is_stale_but_consumed THEN 'surveiller'" in query
    assert "AS severity" in query
    assert "WHEN is_critical AND is_unused THEN 'high'" in query
    assert "WHEN is_unused OR is_orphan THEN 'medium'" in query


def test_table_governance_propagates_the_three_lifecycle_columns_from_the_catalog(
    fakes: SimpleNamespace,
) -> None:
    """Propagation par JOINTURE, jamais par copie figee : ce snapshot est
    entierement recalcule a chaque run, donc l'etat suit le registre sans decalage.
    """
    query = _table_governance_query(fakes)
    for column in ("lifecycle_state", "is_deleted", "deleted_at"):
        assert f"c.{column}" in query
        assert f"\n        {column},\n" in query


def test_table_governance_neutralises_recommended_action_and_severity_when_deleted(
    fakes: SimpleNamespace,
) -> None:
    """Aucune action n'est possible sur un objet qui n'existe plus : la branche
    passe AVANT toutes les autres, sinon `is_unused` (vrai par construction sur une
    table supprimee, jamais relue) produirait un 'archiver' sur du neant."""
    query = _table_governance_query(fakes)
    action_case = query.split("AS recommended_action")[0].rsplit("CASE", 1)[1]
    severity_case = query.split("AS severity")[0].rsplit("CASE", 1)[1]
    for case in (action_case, severity_case):
        assert case.strip().startswith("WHEN is_deleted THEN NULL")


def test_table_governance_keeps_the_raw_measures_on_a_deleted_table(
    fakes: SimpleNamespace,
) -> None:
    """Les drapeaux bruts sont des MESURES, pas des jugements : les neutraliser
    effacerait l'inventaire de ce qui a ete supprime, que la gouvernance doit
    pouvoir relire."""
    query = _table_governance_query(fakes)
    flagged = query.split("flagged AS (")[1].split("SELECT\n        cloud_provider")[0]
    assert "is_deleted" not in flagged


def test_table_governance_recommended_action_unchanged_on_an_active_table(
    fakes: SimpleNamespace,
) -> None:
    """Non-regression : l'ordre de priorite existant survit intact sous la nouvelle
    branche -- une table active continue d'etre jugee comme avant."""
    query = _table_governance_query(fakes)
    action_case = query.split("AS recommended_action")[0].rsplit("CASE", 1)[1]
    assert action_case.index("'archiver'") < action_case.index("'documenter'")
    assert action_case.index("'documenter'") < action_case.index("'surveiller'")
