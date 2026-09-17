"""Tests de `pipelines.gold_dbx_usage.recommendations` (rule engine, data products + consommateurs).

Meme convention que `tests/gold_dbx_compute/test_recommendations.py` : pas de
vraie `SparkSession`, `FakeSpark` capture le texte SQL genere par l'unique
`spark.sql(...)` et les assertions portent sur ce texte (formule du hash,
preservation de `first_seen_date`, transition de statut, priorite des
regles GOVERNANCE).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from pipelines.gold_dbx_usage.recommendations import build_usage_recommendations
from tests.conftest import strip_sql_comments

_TARGET_TABLE = "it.sch.gold_dbx_usage_recommendations"


def _recommendations_query(
    fakes: SimpleNamespace,
    *,
    existing_tables: set[str] | None = None,
    generated_date: date = date(2026, 9, 7),
) -> str:
    sentinel = fakes.DataFrame("recommendations_result")
    spark = fakes.Spark(existing_tables=existing_tables, sql_result=sentinel)
    result = build_usage_recommendations(
        spark,
        governance_table="it.sch.gold_dbx_usage_table_governance",
        catalog_table="it.sch.gold_dbx_usage_table_catalog",
        popularity_daily_table="it.sch.gold_dbx_usage_table_popularity_daily",
        query_performance_daily_table="it.sch.gold_dbx_usage_table_query_performance_daily",
        consumer_daily_table="it.sch.gold_dbx_usage_consumer_daily",
        recommendations_table=_TARGET_TABLE,
        generated_date=generated_date,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0]


def test_recommendation_id_hash_uses_first_seen_date_not_run_date(fakes: SimpleNamespace) -> None:
    # Stabilite du hash sur tout le cycle de vie de l'anomalie : `first_seen_date`
    # (pas la date du run) dans la formule, sinon un nouvel id serait genere a
    # chaque run et le MERGE ne matcherait jamais l'existant (cf. docstring
    # module -- ecart assume vs la formule litterale du spike qui utilisait
    # generated_date).
    query = _recommendations_query(fakes)
    assert (
        "concat_ws('||', cloud_provider, object_type, object_id, category,\n"
        "                CAST(first_seen_date AS STRING))"
        in query
    )
    assert "sha2(\n            concat_ws(" in query


def test_recommendation_id_stable_across_two_runs_same_day(fakes: SimpleNamespace) -> None:
    # 2 executions du meme jour (ex. retry manuel) generent EXACTEMENT la meme
    # requete (meme formule de hash, memes CTE) : idempotent par construction (P6).
    first_run_query = _recommendations_query(fakes, existing_tables={_TARGET_TABLE})
    second_run_query = _recommendations_query(fakes, existing_tables={_TARGET_TABLE})
    assert first_run_query == second_run_query


def test_first_run_uses_empty_typed_existing_stub_when_target_table_absent(
    fakes: SimpleNamespace,
) -> None:
    # 1er run (table cible pas encore creee) : `existing` ne doit JAMAIS
    # referencer la table cible reelle (elle n'existe pas), sinon
    # `TABLE_OR_VIEW_NOT_FOUND`.
    query = _recommendations_query(fakes, existing_tables=set())
    assert _TARGET_TABLE not in query
    assert "WHERE 1 = 0" in query
    assert "CAST(NULL AS DATE) AS first_seen_date" in query
    assert "CAST(NULL AS DATE) AS last_seen_date" in query


def test_existing_run_reads_the_full_target_table_both_object_types(
    fakes: SimpleNamespace,
) -> None:
    # Ce builder gere/ecrit les DEUX types d'objet (DATA_PRODUCT et CONSUMER) :
    # `existing` ne doit donc PAS filtrer par object_type.
    query = _recommendations_query(fakes, existing_tables={_TARGET_TABLE})
    assert f"SELECT * FROM {_TARGET_TABLE} WHERE status = 'OPEN'" in query
    assert f"SELECT * FROM {_TARGET_TABLE} WHERE object_type" not in query


def test_first_seen_date_preserved_from_existing_state(fakes: SimpleNamespace) -> None:
    query = _recommendations_query(fakes, existing_tables={_TARGET_TABLE})
    assert "COALESCE(ex.first_seen_date, DATE '2026-09-07') AS first_seen_date" in query


def test_status_transitions_to_resolved_when_no_longer_a_candidate(fakes: SimpleNamespace) -> None:
    query = _recommendations_query(fakes, existing_tables={_TARGET_TABLE})
    assert "CASE WHEN c.object_id IS NOT NULL THEN 'OPEN' ELSE 'RESOLVED' END AS status" in query
    assert (
        "CASE\n                WHEN c.object_id IS NOT NULL THEN DATE '2026-09-07'\n"
        "                ELSE ex.last_seen_date\n            END AS last_seen_date" in query
    )
    assert "FULL OUTER JOIN existing ex" in query


def test_lifecycle_unused_yields_medium_severity_rule(fakes: SimpleNamespace) -> None:
    query = _recommendations_query(fakes)
    assert "WHERE g.is_unused AND NOT g.is_critical" in query
    assert "'LIFECYCLE' AS category" in query
    assert "Data product inutilise" in query
    assert "Proposer depreciation / suppression" in query


def test_lifecycle_estimated_savings_reads_popularity_not_query_performance(
    fakes: SimpleNamespace,
) -> None:
    # Regression : estimated_cost_usd n'existe QUE sur table_popularity_daily
    # (grain table), pas sur table_query_performance_daily (grain requete) --
    # un join sur cette derniere leve UNRESOLVED_COLUMN en execution reelle
    # (confirme par run dev). La regle LIFECYCLE doit donc joindre
    # latest_popularity, pas latest_query_performance, pour estimated_savings_usd.
    query = _recommendations_query(fakes)
    assert "LEFT JOIN latest_popularity lp" in query
    assert "lp.estimated_cost_usd AS estimated_savings_usd" in query


def test_lifecycle_critical_and_unused_is_a_distinct_high_severity_rule(
    fakes: SimpleNamespace,
) -> None:
    # Mutuellement exclusive avec la regle "unused simple" (is_critical oppose
    # dans les deux predicats) : pas de dedoublonnage necessaire entre les deux.
    query = _recommendations_query(fakes)
    assert "WHERE g.is_critical AND g.is_unused" in query
    assert "Ne PAS deprecier ; investiguer les dependances aval" in query


def test_freshness_stale_but_consumed_yields_high_severity_rule(fakes: SimpleNamespace) -> None:
    query = _recommendations_query(fakes)
    assert "WHERE g.is_stale_but_consumed" in query
    assert "'FRESHNESS' AS category, 'HIGH' AS severity" in query


def test_governance_rules_prioritize_orphan_over_missing_classification(
    fakes: SimpleNamespace,
) -> None:
    # Ordre du tableau `usage_datamapping.md` §4.1 : is_orphan (priorite 1)
    # avant classification manquante (priorite 2), meme convention que
    # `gold_dbx_compute.recommendations` pour les categories a regles multiples.
    query = _recommendations_query(fakes)
    orphan_pos = query.index("WHERE g.is_orphan")
    classification_pos = query.index("WHERE c.is_data_product AND c.classification IS NULL")
    assert orphan_pos < classification_pos


def test_governance_rules_are_deduplicated_one_row_per_object(fakes: SimpleNamespace) -> None:
    query = _recommendations_query(fakes)
    assert (
        "PARTITION BY cloud_provider, object_type, object_id ORDER BY rule_priority"
        in query
    )


def test_reliability_failure_rate_threshold_yields_high_severity_rule(
    fakes: SimpleNamespace,
) -> None:
    query = _recommendations_query(fakes)
    assert "WHERE lp.failure_rate_pct > 5.0" in query
    assert "'RELIABILITY' AS category, 'HIGH' AS severity" in query
    assert "Investiguer les acces en echec" in query


def test_finops_high_cost_threshold_yields_consumer_object_type_rule(
    fakes: SimpleNamespace,
) -> None:
    # Seule regle au grain CONSUMER (pas DATA_PRODUCT), cf. usage_datamapping.md
    # §4.1 ligne FINOPS.
    query = _recommendations_query(fakes)
    assert "WHERE lc.estimated_cost_usd > 1.0" in query
    assert "'CONSUMER' AS object_type" in query
    assert "'FINOPS' AS category, 'MEDIUM' AS severity" in query


def test_no_data_product_rule_detects_on_a_deleted_table(fakes: SimpleNamespace) -> None:
    """Une recommandation sur une table qui n'existe plus ne mene nulle part : les
    QUATRE regles `DATA_PRODUCT` cessent de la detecter.

    Le predicat porte sur la table qui porte deja l'etat -- gouvernance pour trois
    d'entre elles, registre pour la classification -- jamais sur une copie
    denormalisee cote fait.
    """
    query = _recommendations_query(fakes)
    # LIFECYCLE (x2), FRESHNESS, GOVERNANCE-orphelin : toutes lisent la gouvernance.
    assert query.count("AND NOT g.is_deleted") == 4
    # GOVERNANCE-classification lit le registre directement.
    assert "WHERE c.is_data_product AND c.classification IS NULL AND NOT c.is_deleted" in query


def test_the_reliability_rule_joins_the_catalog_null_safely(fakes: SimpleNamespace) -> None:
    """`table_query_performance_daily` est une table de FAIT : elle ne porte pas
    l'etat et ne doit pas le porter. La jointure est donc externe, et le `COALESCE`
    obligatoire -- une cle de fait jamais resolue au registre ne doit pas etre
    filtree en silence."""
    query = _recommendations_query(fakes)
    assert "LEFT JOIN it.sch.gold_dbx_usage_table_catalog c" in query
    assert "AND NOT COALESCE(c.is_deleted, false)" in query


def test_the_finops_consumer_rule_is_left_untouched_by_the_table_lifecycle(
    fakes: SimpleNamespace,
) -> None:
    """Son grain est le CONSOMMATEUR : aucune cle table a rapprocher du registre.
    Y injecter un filtre de cycle de vie de table inventerait une jointure."""
    query = strip_sql_comments(_recommendations_query(fakes))
    finops = query.split("finops_candidates AS (")[1].split("candidates AS (")[0]
    assert "is_deleted" not in finops


def test_a_preexisting_open_recommendation_resolves_once_its_table_is_deleted(
    fakes: SimpleNamespace,
) -> None:
    """FR-014 sans code dedie : l'etat existant est relu SANS filtre de cycle de
    vie, donc la ligne `OPEN` reste dans le FULL OUTER JOIN ; plus aucune regle ne
    la produisant cote candidats, elle bascule `RESOLVED` par la mecanique en place.

    La filtrer aussi cote `existing` la ferait disparaitre du join et resterait
    `OPEN` en base pour toujours.
    """
    query = strip_sql_comments(_recommendations_query(fakes, existing_tables={_TARGET_TABLE}))
    existing = query.split("existing AS (")[1].split("),")[0]
    assert "is_deleted" not in existing
    assert "CASE WHEN c.object_id IS NOT NULL THEN 'OPEN' ELSE 'RESOLVED' END AS status" in query


def test_candidates_union_includes_all_five_category_ctes(fakes: SimpleNamespace) -> None:
    query = _recommendations_query(fakes)
    assert "SELECT * FROM lifecycle_candidates" in query
    assert "SELECT * FROM freshness_candidates" in query
    assert "SELECT * FROM governance_candidates" in query
    assert "SELECT * FROM reliability_candidates" in query
    assert "SELECT * FROM finops_candidates" in query


def test_latest_query_performance_and_consumer_dedup_to_most_recent_period(
    fakes: SimpleNamespace,
) -> None:
    # query_performance_daily/consumer_daily sont des tables *_daily (historique
    # multi-jours) : seule la derniere ligne connue par objet alimente les
    # regles RELIABILITY/FINOPS (snapshot du jour, pas une moyenne/somme).
    query = _recommendations_query(fakes)
    assert (
        "latest_query_performance AS (\n        SELECT * FROM "
        "it.sch.gold_dbx_usage_table_query_performance_daily\n        QUALIFY ROW_NUMBER() OVER (\n"
        "            PARTITION BY cloud_provider, catalog, schema, table_name "
        "ORDER BY period_start DESC\n        ) = 1\n    )"
        in query
    )
    assert (
        "latest_consumer AS (\n        SELECT * FROM it.sch.gold_dbx_usage_consumer_daily\n"
        "        QUALIFY ROW_NUMBER() OVER (\n"
        "            PARTITION BY cloud_provider, consumer_id ORDER BY period_start DESC\n"
        "        ) = 1\n    )"
        in query
    )
