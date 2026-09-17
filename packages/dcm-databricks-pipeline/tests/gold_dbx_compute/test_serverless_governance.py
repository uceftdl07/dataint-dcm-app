"""Tests de `pipelines.gold_dbx_compute.serverless_governance`.

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`) : le builder
construit un unique `spark.sql(...)`, verifie ici via le texte SQL genere
(`FakeSpark`).

Les assertions portent sur des expressions ENTIERES et sont doublees
d'assertions NEGATIVES, parce que sur cette table chaque piege documente a une
version VOISINE ET CREDIBLE qui doit rester absente : une couverture booleenne
"au moins un tag" au lieu de cles nommees (elle vaut 100 % sur azure, ou
l'etiquette plateforme `Environment` est obligatoire), une lecture de
`serverless_cost_daily` au lieu des lignes de facturation (elle sous-estime les
orphelins), un `named_struct` dont la cle de tri n'est pas le premier champ (il
trie alors par identifiant, silencieusement), `usage_policy_id` au lieu de
`budget_policy_id`, ou une borne de fenetre publiee differente de celle
reellement filtree.
"""

from __future__ import annotations

import re
from datetime import date
from types import SimpleNamespace

from pipelines.gold_dbx_compute import specs
from pipelines.gold_dbx_compute.serverless_governance import build_serverless_governance
from pipelines.gold_dbx_compute.sql_helpers import (
    SERVERLESS_OBJECT_ID_SENTINEL,
    identity_principal_expr,
    identity_source_expr,
    serverless_object_id_expr,
    serverless_scope_predicate,
    serverless_surface_case_expr,
    tag_present_sql,
)

_WINDOW_FLOOR = date(2026, 6, 12)


def _code_only(query: str) -> str:
    """Requete privee de ses commentaires SQL (`-- ...`).

    Meme raison que dans `test_serverless_cost.py` : la requete generee est
    abondamment commentee et ses commentaires CITENT les constructions
    interdites. Une assertion negative portee sur le texte brut passerait donc au
    vert le jour ou le code redevient faux mais garde son commentaire.
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


def _cte(query: str, name: str) -> str:
    """Corps de la CTE `name` seule.

    Sert aux assertions qui doivent porter sur UNE etape et pas sur la requete
    entiere : "`priced` n'agrege pas" est faux si on le verifie sur tout le
    texte, qui contient forcement des `GROUP BY` plus loin.
    """
    marker = f"{name} AS (\n"
    start = query.index(marker) + len(marker)
    return query[start:].split("\n    )", 1)[0]


def _governance_query(fakes: SimpleNamespace, floor: date = _WINDOW_FLOOR) -> str:
    sentinel = fakes.DataFrame("serverless_governance_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_serverless_governance(
        spark,
        billing_usage_table="it.sch.curated_dbx_billing_usage",
        billing_list_prices_table="it.sch.curated_dbx_billing_list_prices",
        activity_lower_bound=floor,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    query: str = spark.sql_calls[0]
    return query


def test_governance_reads_the_billing_lines_and_no_gold_table(fakes: SimpleNamespace) -> None:
    # Decision structurante de T001e, et mesuree : construire cette table sur
    # `gold_dbx_compute_serverless_cost_daily` sous-estime les dollars sans
    # proprietaire (8 605,66 $ au lieu de 8 704,20 $ sur une meme fenetre de
    # 31 jours), parce qu'au grain jour-objet les lignes sans identite fusionnent
    # avec des lignes qui en portent une. Aucune table gold en entree, donc.
    code = _code_only(_governance_query(fakes))
    assert "FROM it.sch.curated_dbx_billing_usage" in code
    assert "FROM it.sch.curated_dbx_billing_list_prices" in code
    assert "gold_" not in code


def test_governance_measures_are_computed_line_by_line(fakes: SimpleNamespace) -> None:
    # Corollaire du test precedent : relire la facturation ne sert a rien si la
    # premiere CTE la pre-agrege. `priced` doit rester au grain LIGNE.
    query = _governance_query(fakes)
    assert "GROUP BY" not in _code_only(_cte(query, "priced"))
    assert "GROUP BY" not in _code_only(_cte(query, "keyed"))
    assert "GROUP BY" not in _code_only(_cte(query, "usage_filtered"))
    # ... et la premiere agregation est celle du grain de sortie, sur les 3 cles.
    assert "GROUP BY cloud_provider, workspace_id, serverless_surface" in _cte(
        query, "surface_grain"
    )


def test_governance_scope_is_the_serverless_whitelist_bounded_by_the_window(
    fakes: SimpleNamespace,
) -> None:
    query = _governance_query(fakes)
    # Expression ENTIERE : un `in query` sur la seule premiere ligne du predicat
    # resterait vrai si l'union des produits manages disparaissait, et la table
    # perdrait des surfaces completes (GENIE, AI_ENDPOINT, LAKEBASE...).
    assert f"WHERE {serverless_scope_predicate()}" in query
    # La fenetre borne la LECTURE de la facturation, pas la sortie : un snapshot
    # non borne reevalue tout l'historique (3 687 894,38 $, part d'orphelins
    # 3 fois superieure) et ne decrit plus l'etat courant.
    assert "AND usage_date >= DATE '2026-06-12'" in _cte(query, "usage_filtered")


def test_governance_publishes_the_window_it_actually_filtered(fakes: SimpleNamespace) -> None:
    # Piege a part entiere : un `window_start` publie qui ne serait pas celui du
    # filtre rendrait chaque chiffre de la ligne faux SANS rien casser. Les deux
    # doivent bouger ensemble avec le parametre.
    query = _governance_query(fakes, floor=date(2025, 1, 3))
    assert "AND usage_date >= DATE '2025-01-03'" in query
    assert "DATE '2025-01-03' AS window_start" in query
    assert "2026-06-12" not in _code_only(query)


def test_governance_window_end_is_measured_per_cloud(fakes: SimpleNamespace) -> None:
    # `window_end` est le dernier jour REELLEMENT facture, pas la veille du run
    # (la facturation arrive avec 3 a 8 jours de retard), et il est mesure PAR
    # CLOUD : un MAX global masquerait le retard de collecte d'un cloud derriere
    # l'avance de l'autre.
    window = _cte(_governance_query(fakes), "measured_window")
    assert "MAX(usage_date) AS window_end" in window
    # Regroupement EXACT : un `in` sur "GROUP BY cloud_provider" resterait vrai si
    # une colonne s'y ajoutait (par surface, par workspace), et `window_end`
    # deviendrait la borne d'un sous-ensemble sans que la colonne change de nom.
    assert _code_only(window).rstrip().endswith("GROUP BY cloud_provider")


def test_governance_never_publishes_a_boolean_tag_coverage(fakes: SimpleNamespace) -> None:
    # LE piege de cette table, mesure : sur azure la cle plateforme `Environment`
    # est presente sur 100,0 % de la depense. Une couverture "custom_tags non
    # vide" afficherait donc 0 % de non-tague et dirait a FinOps qu'il n'y a rien
    # a faire sur azure, alors que sa meilleure cle METIER plafonne a 60,5 %
    # (`AppName`) et que `AppCode` tombe a 12,4 %.
    query = _governance_query(fakes)
    assert f"{tag_present_sql('custom_tags', specs.OWNER_TAG_KEYS)} AS has_owner_tag" in query
    assert (
        f"{tag_present_sql('custom_tags', specs.COST_CENTER_TAG_KEYS)} AS has_cost_center_tag"
        in query
    )
    code = _code_only(query)
    assert "size(custom_tags) > 0" not in code
    assert "has_custom_tags" not in code
    assert "has_any_tag" not in code


def test_governance_identity_coverage_is_the_complement_of_the_orphan_dollars(
    fakes: SimpleNamespace,
) -> None:
    # Une couverture calculee par un SUM independant du numerateur publie peut
    # deriver de lui (deux CASE a maintenir en phase). Ici elle est LA
    # soustraction, donc `identity_coverage_pct` et `cost_usd_without_identity`
    # ne peuvent pas se contredire.
    query = _governance_query(fakes)
    assert f"{identity_principal_expr()} AS identity_principal" in query
    assert f"{identity_source_expr()} AS identity_source" in query
    assert (
        "SUM(CASE WHEN identity_principal IS NULL THEN line_cost_usd ELSE 0 END)\n"
        "                AS cost_usd_without_identity," in query
    )
    assert (
        "(cost_usd - cost_usd_without_identity) / NULLIF(cost_usd, 0) * 100\n"
        "                AS identity_coverage_pct" in query
    )
    # Le champ porteur de l'identite CHANGE par surface (SQL_WAREHOUSE 100 %
    # OWNED_BY, APP 100 % CREATED_BY) : la liste des champs observes est publiee,
    # et c'est un ENSEMBLE trie -- un MAX() choisirait au hasard.
    assert "concat_ws('+', sort_array(collect_set(identity_source)))" in query


def test_governance_coverage_pct_is_null_and_not_zero_without_dollars(
    fakes: SimpleNamespace,
) -> None:
    # Cas reel : le SKU GENIE_FREE_USAGE facture des DBU GRATUITS, une surface
    # peut donc couter 0 $. Une part de dollars n'est alors pas definie, et 0 %
    # affirmerait a tort "rien n'est couvert".
    code = _code_only(_governance_query(fakes))
    assert code.count("NULLIF(cost_usd, 0) * 100") == 4
    assert "COALESCE(cost_usd_with_owner_tag" not in code
    assert "/ cost_usd * 100" not in code


def test_governance_keeps_the_surface_case_that_makes_the_merge_key_non_nullable(
    fakes: SimpleNamespace,
) -> None:
    # `serverless_surface` est une CLE DE MERGE et `merge_into_table` fusionne sur
    # `<=>` NULL-SAFE : une cle NULL ne leve rien, elle fond silencieusement tout
    # un workspace en UNE ligne corrompue. La seule garantie est la branche ELSE
    # du CASE -- d'ou l'expression entiere, et non un `in query` sur son debut.
    query = _governance_query(fakes)
    assert f"{serverless_surface_case_expr()} AS serverless_surface" in query
    assert "ELSE 'OTHER'" in _code_only(query)
    assert "ELSE 'PLATFORM_AUTO'" not in _code_only(query)
    assert set(specs.SERVERLESS_GOVERNANCE_MERGE_KEYS) <= set(_output_columns(query, "coverage c"))
    # Aucune surface n'est filtree : 12 surfaces existent cote aws et 11 cote
    # azure, "completer" la matrice par une liste blanche fabriquerait des lignes
    # sans facturation.
    assert "serverless_surface IN (" not in _code_only(query)


def test_governance_counts_the_dollars_without_object_key_on_the_sentinel(
    fakes: SimpleNamespace,
) -> None:
    query = _governance_query(fakes)
    assert f"{serverless_object_id_expr()} AS object_id" in query
    assert f"k.object_id <> '{SERVERLESS_OBJECT_ID_SENTINEL}' AS has_object_key" in query
    assert (
        "SUM(CASE WHEN has_object_key THEN 0 ELSE line_cost_usd END)\n"
        "                AS cost_usd_without_object_key," in query
    )
    # L'absence d'objet est portee par la SENTINELLE, jamais par un NULL : un
    # `object_id IS NULL` ne compterait aucun dollar.
    assert "object_id IS NULL" not in _code_only(query)


def test_governance_policy_inventory_sorts_by_cost_and_not_by_identifier(
    fakes: SimpleNamespace,
) -> None:
    query = _governance_query(fakes)
    # 1er niveau : le cout PAR POLITIQUE. Sans lui, `collect_list` rendrait une
    # entree par LIGNE DE FACTURATION (des millions), pas une par politique.
    assert "GROUP BY cloud_provider, workspace_id, serverless_surface, budget_policy_id" in _cte(
        query, "policy_grain"
    )
    assert "SUM(line_cost_usd) AS policy_cost_usd" in query
    # Le tri d'un tableau de structs compare les champs dans l'ordre de
    # DECLARATION : permuter les deux champs trierait par identifiant, sans
    # qu'aucune erreur ne soit levee et sans que le schema change de forme.
    assert "collect_list(named_struct('cost_usd', policy_cost_usd," in query
    assert "named_struct('budget_policy_id'" not in _code_only(query)
    assert "sort_array(\n" in query
    assert "                false\n            ) AS budget_policy_inventory" in query


def test_governance_policy_count_is_zero_when_measured_and_the_inventory_stays_null(
    fakes: SimpleNamespace,
) -> None:
    # 0 politique est un FAIT MESURE (c'est meme le constat de gouvernance le plus
    # lourd : SQL_WAREHOUSE, 44 % de la depense, 0 politique sur les deux clouds),
    # donc 0 et non NULL. L'inventaire reste NULL en revanche : un tableau vide
    # n'apporterait rien que `budget_policy_count = 0` ne dise deja.
    query = _governance_query(fakes)
    assert "COALESCE(p.budget_policy_count, 0) AS budget_policy_count" in query
    assert "COALESCE(p.budget_policy_inventory" not in query
    assert "COUNT(*) AS budget_policy_count" in query
    # `budget_policy_id` et non `usage_policy_id` : la colonne recente perdrait
    # silencieusement 188 744 lignes d'historique (cf. serverless_cost_daily).
    assert "usage_metadata.budget_policy_id AS budget_policy_id" in query
    assert "usage_policy_id" not in _code_only(query)


def test_governance_output_columns_match_the_published_comments(fakes: SimpleNamespace) -> None:
    # `merge_into_table` attache un `ALTER COLUMN ... COMMENT` PAR ENTREE du
    # dictionnaire : une cle orpheline echoue au RUNTIME, pas a l'import.
    columns = _output_columns(_governance_query(fakes), "coverage c")
    assert set(columns) == set(specs.SERVERLESS_GOVERNANCE_COLUMN_COMMENTS)
    assert set(specs.SERVERLESS_GOVERNANCE_MERGE_KEYS) <= set(columns)
    assert columns[-1] == "_generated_at"
    # Une seule mesure en dollars par axe, plus sa part : le complementaire se
    # soustrait de `cost_usd`. Publier les deux moities inviterait a les sommer.
    assert "cost_usd_with_identity" not in columns
    assert "cost_usd_without_owner_tag" not in columns
    assert "cost_usd_without_cost_center_tag" not in columns
