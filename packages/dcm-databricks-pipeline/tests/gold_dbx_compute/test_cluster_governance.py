"""Tests de `pipelines.gold_dbx_compute.cluster_governance` (regles de derivation).

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`) :
`build_cluster_governance` construit un unique `spark.sql(...)`, verifie ici
via le texte SQL genere (`FakeSpark`). `dbr_lts_versions_supported_as_of` est
une fonction Python pure, testee independamment (pas de Spark).
"""

from __future__ import annotations

import re
from datetime import date
from types import SimpleNamespace

import pytest

from pipelines.gold_dbx_compute.cluster_governance import (
    build_cluster_governance,
    dbr_lts_versions_supported_as_of,
)

_GOVERNANCE_TEST_DBR_LTS_VERSIONS = frozenset({"14.3.x-lts", "15.4.x-lts"})
_ACTIVITY_LOWER_BOUND = date(2026, 5, 19)


def _governance_query(
    fakes: SimpleNamespace,
    dbr_lts_versions: frozenset[str] = _GOVERNANCE_TEST_DBR_LTS_VERSIONS,
) -> str:
    sentinel = fakes.DataFrame("governance_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_cluster_governance(
        spark,
        clusters_table="it.sch.curated_dbx_compute_clusters",
        efficiency_daily_table="it.sch.gold_dbx_compute_cluster_efficiency_daily",
        dbr_lts_versions=dbr_lts_versions,
        activity_lower_bound=_ACTIVITY_LOWER_BOUND,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    return spark.sql_calls[0]


def test_cluster_governance_derives_cluster_type_from_cluster_source(
    fakes: SimpleNamespace,
) -> None:
    # cluster_source deja inclus via `SELECT c.*` de latest_clusters ; verifie
    # que le SELECT final expose cluster_type (derive), pas le brut.
    query = _governance_query(fakes)
    assert "WHEN t.cluster_source = 'JOB' THEN 'JOB'" in query
    assert "ELSE 'OTHER' END AS cluster_type" in query


def test_cluster_governance_snapshot_is_bounded_to_all_purpose(
    fakes: SimpleNamespace,
) -> None:
    # SC-001 : le snapshot materialise ne contient que les clusters ALL_PURPOSE
    # (les JOB/PIPELINE/OTHER ephemeres disparaissent de la page Clusters). Les
    # regles de gouvernance (tags/DBR) restent gated par governance_applies.
    query = _governance_query(fakes)
    assert "END = 'ALL_PURPOSE'" in query
    assert "END <> 'OTHER'" not in query


def test_cluster_governance_missing_tags_yields_low_severity(fakes: SimpleNamespace) -> None:
    query = _governance_query(fakes)
    assert "AS has_owner_tag" in query
    assert "AS has_cost_center_tag" in query
    assert "NOT t.has_owner_tag OR NOT t.has_cost_center_tag" in query


def test_cluster_governance_tag_lookup_is_case_insensitive_on_the_key(
    fakes: SimpleNamespace,
) -> None:
    # Un acces exact `lc.tags['owner']` ne reconnait PAS les cles reelles du parc
    # (`Owner`, `OWNER`) : la conformite au tagging apparaitrait fausse a ~100 %
    # alors que le tag est pose. Les cles sont donc normalisees en minuscules.
    query = _governance_query(fakes)
    assert "lc.tags['owner']" not in query
    assert "lc.tags['cost_center']" not in query
    assert "map_filter(lc.tags, (k, v) -> lower(trim(k)) IN ('owner')" in query
    # Orthographes acceptees du centre de cout (cf. COST_CENTER_TAG_KEYS) : les
    # tags d'affectation du parc (BU, Project) valent centre de cout.
    assert "'cost_center', 'costcenter', 'cost-center', 'bu', 'project'" in query


def test_cluster_governance_priority_order_is_tag_then_dbr_then_oversize(
    fakes: SimpleNamespace,
) -> None:
    # Priorite (la plus haute en premier) : tag manquant > DBR obsolete > oversize.
    query = _governance_query(fakes)
    action_case_start = query.index("CASE", query.index("AS recommended_action") - 400)
    tag_pos = query.index("NOT t.has_owner_tag OR NOT t.has_cost_center_tag", action_case_start)
    dbr_pos = query.index("t.dbr_lts_key NOT IN", action_case_start)
    oversize_pos = query.index("node_oversized_flag", action_case_start)
    assert tag_pos < dbr_pos < oversize_pos


def test_cluster_governance_tag_and_dbr_rules_target_all_purpose_clusters_only(
    fakes: SimpleNamespace,
) -> None:
    # Les tags et le runtime d'un cluster JOB/PIPELINE viennent de la definition
    # du job/pipeline : une non-conformite par execution ephemere n'aurait aucun
    # destinataire. Seul `node_oversized` (propriete observee du cluster) reste
    # evalue pour tous les types.
    query = _governance_query(fakes)
    assert "= 'ALL_PURPOSE') AS governance_applies" in query
    assert (
        "WHEN t.governance_applies AND (NOT t.has_owner_tag OR NOT t.has_cost_center_tag)" in query
    )
    assert "WHEN t.governance_applies AND t.dbr_lts_key NOT IN" in query
    oversize_clause = "WHEN COALESCE(re.node_oversized_flag, 0) = 1"
    assert oversize_clause in query
    assert f"t.governance_applies AND {oversize_clause}" not in query


def test_cluster_governance_scope_is_bounded_by_the_activity_window(
    fakes: SimpleNamespace,
) -> None:
    # Sans borne temporelle, le snapshot reevalue tout cluster jamais apparu en
    # curated (clusters JOB/PIPELINE ephemeres : un cluster_id par execution) et
    # croit indefiniment. Perimetre = actif sur la fenetre OU reconfigure depuis.
    query = _governance_query(fakes)
    floor = f"DATE '{_ACTIVITY_LOWER_BOUND.isoformat()}'"
    assert f"WHERE period_start >= {floor}" in query
    assert f"OR lc.change_time >= {floor}" in query
    assert "FROM in_scope_clusters lc" in query


def test_cluster_governance_severity_values_match_priority(fakes: SimpleNamespace) -> None:
    query = _governance_query(fakes)
    assert "THEN 'LOW'" in query
    assert "THEN 'HIGH'" in query
    assert "THEN 'MEDIUM'" in query


def test_cluster_governance_is_snapshot_using_latest_change_time(
    fakes: SimpleNamespace,
) -> None:
    query = _governance_query(fakes)
    assert "ORDER BY c.change_time DESC" in query
    assert "QUALIFY ROW_NUMBER()" in query


def test_cluster_governance_dbr_lts_lookup_uses_provided_versions(
    fakes: SimpleNamespace,
) -> None:
    query = _governance_query(fakes)
    for version in _GOVERNANCE_TEST_DBR_LTS_VERSIONS:
        assert version in query


def test_cluster_governance_dbr_version_matching_extracts_major_minor_prefix(
    fakes: SimpleNamespace,
) -> None:
    # `dbr_version` reel n'est jamais litteralement '16.4.x-lts' : c'est
    # '16.4.x-scala2.12', '-aarch64-', '-photon-', '-cpu-ml-' selon le flavor
    # -> extraction du prefixe major.minor.x avant de comparer au referentiel
    # (format lisible officiel Databricks).
    query = _governance_query(fakes)
    assert "regexp_extract(lc.dbr_version, '^([0-9]+(?:\\.[0-9]+)?\\.x)', 1)" in query
    assert "AS dbr_lts_key" in query
    assert "t.dbr_lts_key IN" in query
    assert "t.dbr_version IN" not in query


@pytest.mark.parametrize(
    ("dbr_version", "expected_prefix"),
    [
        ("16.4.x-scala2.12", "16.4.x"),
        ("14.3.x-photon-scala2.12", "14.3.x"),
        ("15.4.x-aarch64-photon-scala2.12", "15.4.x"),
        ("13.3.x-cpu-ml-scala2.12", "13.3.x"),
    ],
)
def test_dbr_lts_key_regex_extracts_major_minor_prefix_from_real_flavors(
    dbr_version: str, expected_prefix: str
) -> None:
    # Rejoue en Python le pattern SQL genere (regexp_extract Spark = re.match
    # ancre en tete, meme semantique POSIX pour ce pattern simple) : confirme
    # que le prefixe 'major.minor.x' est bien extrait des formats reels de
    # dbr_version (flavors scala/photon/aarch64/cpu-ml), pas seulement du
    # format lisible officiel '16.4.x-lts' utilise par le referentiel.
    match = re.match(r"^([0-9]+(?:\.[0-9]+)?\.x)", dbr_version)
    assert match is not None
    assert match.group(1) == expected_prefix


def test_dbr_lts_key_regex_does_not_match_dlt_cluster_format() -> None:
    # Cas DLT documente dans le docstring de `build_cluster_governance` :
    # `dbr_version` du type 'dlt:...' n'a pas de prefixe numerique en tete ->
    # pas de correspondance. Spark `regexp_extract` renvoie alors '' (chaine
    # vide, PAS NULL) : concatene a '-lts', `dbr_lts_key` devient '-lts', une
    # valeur qui ne correspond jamais a une entree de `DBR_LTS_RELEASE_DATES`
    # (toujours prefixees d'un numero de version) -> `dbr_is_lts_current`
    # reste `false` pour ces clusters, comme attendu (pas un bug).
    match = re.match(r"^([0-9]+(?:\.[0-9]+)?\.x)", "dlt:12345-abcdef")
    assert match is None


def test_dbr_lts_versions_supported_as_of_keeps_versions_within_support_window() -> None:
    release_dates = {"14.3.x-lts": date(2024, 2, 1), "15.4.x-lts": date(2024, 8, 19)}
    supported = dbr_lts_versions_supported_as_of(
        date(2026, 1, 1), release_dates=release_dates, window_years=3
    )
    assert supported == {"14.3.x-lts", "15.4.x-lts"}


def test_dbr_lts_versions_supported_as_of_drops_expired_versions() -> None:
    release_dates = {"11.3.x-lts": date(2023, 2, 1), "14.3.x-lts": date(2024, 2, 1)}
    supported = dbr_lts_versions_supported_as_of(
        date(2026, 8, 17), release_dates=release_dates, window_years=3
    )
    assert supported == {"14.3.x-lts"}
