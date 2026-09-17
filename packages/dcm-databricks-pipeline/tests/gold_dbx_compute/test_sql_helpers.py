"""Tests de `pipelines.gold_dbx_compute.sql_helpers` (helpers purs, sans Spark).

Perimetre : le predicat de produit de facturation (T001c) et les helpers de la
depense serverless (T001d) -- perimetre, surface, cle d'objet, identite,
histogramme du cout par execution, plus le discriminant `compute_kind` (T001g).
Les autres helpers de ce module restent verifies a travers le SQL genere par
leurs builders.

Ces helpers sont testes ICI, et pas seulement a travers le SQL des builders,
parce qu'ils portent des INVARIANTS que le texte genere ne montre pas :
l'exhaustivite des 12 surfaces, l'ORDRE des branches du `CASE` (deux produits
`SQL` sont discrimines par ce seul ordre), l'alignement des deux expressions
d'identite, le fait qu'un produit admis dans le perimetre soit bien classe, et
le REJET MESURE d'un champ source officiel au profit d'un proxy structurel.
"""

from __future__ import annotations

import re
from itertools import pairwise

import pytest

from pipelines.gold_dbx_compute.sql_helpers import (
    BILLING_PRODUCTS_CLUSTER_COMPUTE,
    BILLING_PRODUCTS_DLT_PIPELINE,
    COMPUTE_KIND_CLASSIC,
    COMPUTE_KIND_SERVERLESS,
    HISTOGRAM_COST_PER_RUN_EDGES,
    SERVERLESS_OBJECT_ID_SENTINEL,
    SERVERLESS_SCOPE_PRODUCTS,
    SERVERLESS_SURFACE_JOB,
    SERVERLESS_SURFACE_OTHER,
    SERVERLESS_SURFACES,
    billing_origin_product_predicate,
    compute_kind_case_expr,
    histogram_bucket_count,
    histogram_from_edges_sql,
    histogram_representatives,
    identity_principal_expr,
    identity_source_expr,
    serverless_object_id_expr,
    serverless_scope_predicate,
    serverless_surface_case_expr,
)


def test_billing_origin_product_predicate_formats_a_whitelist() -> None:
    assert (
        billing_origin_product_predicate(BILLING_PRODUCTS_CLUSTER_COMPUTE)
        == "billing_origin_product IN ('JOBS', 'ALL_PURPOSE', 'DLT')"
    )
    assert (
        billing_origin_product_predicate(BILLING_PRODUCTS_DLT_PIPELINE)
        == "billing_origin_product IN ('DLT')"
    )


def test_billing_origin_product_predicate_is_never_a_blacklist() -> None:
    # Une liste noire laisserait entrer silencieusement tout produit ajoute par
    # Databricks apres l'ecriture du filtre (AI_FUNCTIONS est apparu le
    # 2025-11-07 et DATABASE le 2025-09-09 dans ce compte).
    for products in (BILLING_PRODUCTS_CLUSTER_COMPUTE, BILLING_PRODUCTS_DLT_PIPELINE):
        assert "NOT IN" not in billing_origin_product_predicate(products)
    assert "MODEL_SERVING" not in BILLING_PRODUCTS_CLUSTER_COMPUTE
    assert "AI_FUNCTIONS" not in BILLING_PRODUCTS_CLUSTER_COMPUTE
    # Cote pipelines, le seul produit retenu est DLT : ni les requetes SQL, ni
    # l'ingestion managee, ni la recherche vectorielle (cf. arbitrage documente
    # avec la constante).
    assert BILLING_PRODUCTS_DLT_PIPELINE == ("DLT",)


def test_billing_origin_product_predicate_refuses_an_empty_whitelist() -> None:
    # `IN ()` est une erreur de syntaxe Spark, mais surtout une liste blanche
    # vide viderait la table gold sans rien signaler.
    with pytest.raises(ValueError, match="must not be empty"):
        billing_origin_product_predicate(())


# --- Perimetre, surface et cle d'objet serverless (T001d) --------------------


def test_serverless_scope_predicate_unions_the_managed_products() -> None:
    # `is_serverless = true` seul perdrait 11,7 % de la depense serverless
    # (44 423,98 $ sur 380 638,71 $, mesure dev 2026-09-10, fenetre de reference
    # 2026-08-10..2026-09-09, bi-cloud) : les services manages n'ont pas de
    # cluster derriere eux, donc rien a marquer serverless.
    predicate = serverless_scope_predicate()
    assert predicate.startswith("(product_features.is_serverless = true\n")
    assert predicate.endswith(")")
    for product in SERVERLESS_SCOPE_PRODUCTS:
        assert f"'{product}'" in predicate
    # LISTE BLANCHE : Databricks AJOUTE des produits, une liste noire les ferait
    # entrer sans un seul signal.
    assert "NOT IN" not in predicate
    assert "is_serverless = false" not in predicate


def test_serverless_surface_case_expr_produces_exactly_the_declared_surfaces() -> None:
    # `SERVERLESS_SURFACES` est la source de verite de l'IHM : une branche
    # ajoutee au CASE sans etre declaree la (ou l'inverse) ferait apparaitre une
    # surface qu'aucun filtre ne propose, ou proposer un filtre toujours vide.
    produced = tuple(re.findall(r"THEN '([A-Z_]+)'", serverless_surface_case_expr()))
    else_branch = re.findall(r"ELSE '([A-Z_]+)'", serverless_surface_case_expr())
    assert produced + tuple(else_branch) == SERVERLESS_SURFACES
    assert len(SERVERLESS_SURFACES) == 12
    assert SERVERLESS_SURFACE_JOB in SERVERLESS_SURFACES
    assert SERVERLESS_SURFACES[-1] == SERVERLESS_SURFACE_OTHER


def test_serverless_surface_case_expr_never_returns_null() -> None:
    # `serverless_surface` est une CLE DE MERGE et `merge_into_table` fusionne
    # sur `<=>` null-safe : une valeur NULL ne leve rien, elle fond tout un
    # workspace en une ligne corrompue.
    expression = serverless_surface_case_expr()
    assert f"ELSE '{SERVERLESS_SURFACE_OTHER}'" in expression
    assert "ELSE NULL" not in expression
    assert expression.endswith("END")


def test_serverless_surface_case_expr_discriminates_sql_by_branch_order() -> None:
    # Les deux surfaces issues du produit `SQL` ne sont separees que par l'ORDRE
    # des branches : `MV_ST_REFRESH` (presence d'un `dlt_pipeline_id`) DOIT etre
    # testee avant le `SQL_WAREHOUSE` generique, sinon tout le rafraichissement
    # de vues materialisees est compte comme du warehouse -- sans aucune erreur.
    expression = serverless_surface_case_expr()
    assert expression.index("'MV_ST_REFRESH'") < expression.index("'SQL_WAREHOUSE'")
    assert (
        "WHEN billing_origin_product = 'SQL'\n"
        "                   AND usage_metadata.dlt_pipeline_id IS NOT NULL"
        " THEN 'MV_ST_REFRESH'"
    ) in expression


def test_every_in_scope_product_is_classified_except_the_measured_one() -> None:
    # Invariant reel : un produit ADMIS dans le perimetre doit etre CLASSE,
    # sinon son cout arrive dans `OTHER`. Mesure dev 2026-09-10 sur
    # l'HISTORIQUE COMPLET (2023-08-26..2026-09-09, la fenetre que cette table
    # construit reellement) : `LAKEFLOW_CONNECT` est le seul dans ce cas,
    # 9 880,03 $ sur AWS et 0 $ sur Azure -- il n'est ni une plateforme
    # automatique ni un objet listable, donc legitimement `OTHER`. Ce test fixe
    # cet etat : le jour ou un SECOND produit du perimetre n'est plus classe, il
    # faut le classer, pas le laisser grossir dans `OTHER`.
    #
    # PORTEE de ce test, et c'est par la qu'un defaut est passe : il ne regarde
    # que les produits FORCES dans le perimetre. Les produits qui y entrent par
    # `is_serverless = true` ne sont pas dans `SERVERLESS_SCOPE_PRODUCTS`, donc
    # invisibles ici -- `SHARED_SERVERLESS_COMPUTE` (90,46 $) et
    # `BASE_ENVIRONMENTS` (0,07 $) resident aussi dans `OTHER` sans que ce test
    # ne le dise. Cf. le test suivant, qui couvre cette seconde voie.
    expression = serverless_surface_case_expr()
    unclassified = tuple(p for p in SERVERLESS_SCOPE_PRODUCTS if f"'{p}'" not in expression)
    assert unclassified == ("LAKEFLOW_CONNECT",)


def test_platform_auto_covers_the_renamed_monitoring_product() -> None:
    # Une liste blanche doit couvrir les noms HISTORIQUES, pas seulement les
    # noms courants. `LAKEHOUSE_MONITORING` est l'ancien nom de
    # `DATA_QUALITY_MONITORING` : les deux portent EXACTEMENT les memes SKU et se
    # relaient dans le temps (l'ancien s'arrete le 2026-02-06, le nouveau demarre
    # le 2025-11-06 sur azure / 2025-12-15 sur aws). Ne garder que le nom recent
    # faisait tomber 3 494,32 $ d'historique (AWS 2 837,39 $, Azure 656,93 $)
    # dans `OTHER` -- defaut invisible sur une fenetre de 31 jours mesuree en
    # septembre, et non couvert par le test ci-dessus puisque ce produit entre
    # dans le perimetre par `is_serverless = true`.
    expression = serverless_surface_case_expr()
    platform_auto_branch = expression[
        expression.index("'PREDICTIVE_OPTIMIZATION'") : expression.index("THEN 'PLATFORM_AUTO'")
    ]
    # Les DEUX noms dans la MEME branche : present ailleurs dans le CASE ne
    # suffirait pas, la surface resultante serait differente.
    assert "'DATA_QUALITY_MONITORING'" in platform_auto_branch
    assert "'LAKEHOUSE_MONITORING'" in platform_auto_branch


def test_serverless_object_id_expr_falls_back_to_the_sentinel() -> None:
    # Meme piege de cle de merge que la surface. Le prefixe `_` distingue la
    # sentinelle d'un id Databricks reel (aucun n'en porte).
    expression = serverless_object_id_expr()
    assert SERVERLESS_OBJECT_ID_SENTINEL.startswith("_")
    assert expression.startswith("COALESCE(")
    assert f"'{SERVERLESS_OBJECT_ID_SENTINEL}'\n            )" in expression
    # Le `ELSE NULL` interne est RATTRAPE par le COALESCE : c'est la seule raison
    # pour laquelle il est acceptable ici.
    assert expression.index("ELSE NULL") < expression.index(f"'{SERVERLESS_OBJECT_ID_SENTINEL}'")


def test_serverless_object_id_expr_only_keys_surfaces_that_have_an_object() -> None:
    # Les 4 surfaces sans objet listable restent au grain workspace. Les nommer
    # dans le CASE fabriquerait un faux grain objet dont 100 % du cout tomberait
    # de toute facon sur la sentinelle.
    expression = serverless_object_id_expr()
    keyed = tuple(re.findall(r"WHEN '([A-Z_]+)' THEN", expression))
    assert keyed == (
        "JOB",
        "DLT_PIPELINE",
        "MV_ST_REFRESH",
        "SQL_WAREHOUSE",
        "NOTEBOOK",
        "APP",
        "AI_ENDPOINT",
        "LAKEBASE",
    )
    assert set(keyed) <= set(SERVERLESS_SURFACES)
    assert set(SERVERLESS_SURFACES) - set(keyed) == {
        "GENIE",
        "NETWORKING",
        "PLATFORM_AUTO",
        SERVERLESS_SURFACE_OTHER,
    }


# --- Identite facturee (T001d) ----------------------------------------------


def test_identity_expressions_share_the_same_cascade() -> None:
    # Les deux expressions DOIVENT rester alignees : `identity_source` est ce qui
    # rend `identity_principal` auditable, un decalage d'ordre rendrait la
    # matrice de refacturation fausse en attribuant un cout a un principal avec
    # le `source` d'un autre.
    fields = re.findall(r"identity_metadata\.(\w+)", identity_principal_expr())
    assert fields == ["run_as", "owned_by", "created_by"]
    assert re.findall(r"identity_metadata\.(\w+)", identity_source_expr()) == fields
    labels = re.findall(r"THEN '(\w+)'", identity_source_expr())
    assert labels == [field.upper() for field in fields]


def test_identity_source_is_never_null() -> None:
    # `NONE` et non NULL : une depense sans proprietaire est une information de
    # gouvernance (2,26 % du cout, 8 605,66 $ sur la fenetre de reference), pas
    # une absence de valeur.
    assert "ELSE 'NONE' END" in identity_source_expr()


def test_identity_cascade_excludes_run_by() -> None:
    # Exclusion MESUREE, pas un oubli : `run_by` ne recupere 0,00 $ de la
    # depense sans identite (mesure dev 2026-09-10, fenetre de reference), les
    # 364,52 $ ou il est renseigne portant deja l'un des trois autres champs.
    assert "run_by" not in identity_principal_expr()
    assert "run_by" not in identity_source_expr()


# --- Histogramme du cout par execution (T001d) ------------------------------


def test_cost_per_run_edges_are_strictly_increasing_and_cover_the_tail() -> None:
    edges = HISTOGRAM_COST_PER_RUN_EDGES
    assert len(edges) == 18
    assert list(edges) == sorted(edges)
    assert len(set(edges)) == len(edges)
    # Bornes doublantes : la resolution est fine ou la masse est (11,4 % des
    # run-jours sont <= 0,01 $) et large ou la queue est (max mesure 1 137,99 $
    # sur la fenetre de reference, sous la derniere borne).
    assert edges[0] == 0.01
    assert edges[-1] == 1310.72
    assert all(round(hi / lo, 6) == 2.0 for lo, hi in pairwise(edges))


def test_cost_per_run_histogram_has_one_overflow_bucket() -> None:
    edges = HISTOGRAM_COST_PER_RUN_EDGES
    assert histogram_bucket_count(edges) == 19
    representatives = histogram_representatives(edges)
    assert len(representatives) == 19
    assert list(representatives) == sorted(representatives)
    assert representatives[0] == 0.005
    # Le bucket overflow est represente par sa borne BASSE : estimation
    # conservatrice, une valeur non bornee ne peut pas avoir de milieu.
    assert representatives[-1] == edges[-1]
    # 19 buckets => 19 comptes dans le SQL genere.
    assert histogram_from_edges_sql("run_cost_usd", edges).count("SUM(CASE WHEN") == 19


# --- Forme de compute derriere une ligne facturee (`compute_kind`, T001g) -----
# Teste ICI, et plus seulement a travers le SQL de `job_cluster_cost_daily` et
# `pipeline_cost_daily`, parce que le discriminant retenu est une EXCEPTION a un
# champ source officiel : le SQL genere montre le `CASE`, il ne peut pas dire
# qu'un autre champ a ete essaye, mesure, et ecarte. Sans ces tests, la seule
# trace de l'arbitrage est une docstring, qu'une "amelioration" de bonne foi
# reecrit en meme temps que le code.


def test_compute_kind_case_expr_renders_the_exact_binary_case() -> None:
    # Egalite de chaine ENTIERE, pas un `in` : `compute_kind` est une CLE DE
    # MERGE du grain de ces deux tables (deja en production), donc toute
    # variation de l'expression est un changement de grain, jamais un detail de
    # forme. Les builders comparent d'ailleurs leur SQL au caractere pres.
    assert compute_kind_case_expr("usage_metadata.cluster_id") == (
        "CASE WHEN usage_metadata.cluster_id IS NOT NULL THEN 'CLASSIC' ELSE 'SERVERLESS' END"
    )


def test_compute_kind_case_expr_produces_only_the_two_declared_constants() -> None:
    # Invariant "cle de merge JAMAIS NULL" (discipline imposee par T001d) :
    # chaque branche rend un litteral quote, aucune ne rend NULL.
    # `merge_into_table` fusionne sur `<=>` null-safe -- un NULL ne leve rien, il
    # fond les deux formes de compute d'un meme objet en une ligne.
    expression = compute_kind_case_expr("u.cluster_id")
    produced = re.findall(r"(?:THEN|ELSE)\s+(\S+)", expression)
    assert produced == [f"'{COMPUTE_KIND_CLASSIC}'", f"'{COMPUTE_KIND_SERVERLESS}'"]
    # L'egalite ci-dessus attrape deja un `THEN NULL` ajoute (elle liste TOUTES
    # les branches). Cette seconde ligne est gardee parce qu'elle enonce
    # l'invariant lui-meme au lieu de le deduire, et parce qu'elle couvre un NULL
    # place ou la regex ne regarde pas -- autour du `CASE`, ou dans une branche
    # ecrite autrement. `.replace("IS NOT NULL", "")` neutralise le NULL du
    # PREDICAT, qui est legitime, pour ne laisser que les NULL PRODUITS.
    assert "NULL" not in expression.replace("IS NOT NULL", "")


@pytest.mark.parametrize(
    ("branch_sql", "expected_kind"),
    [
        ("WHEN u.cluster_id IS NOT NULL THEN", COMPUTE_KIND_CLASSIC),
        ("ELSE", COMPUTE_KIND_SERVERLESS),
    ],
    ids=["cluster_id renseigne", "cluster_id NULL"],
)
def test_compute_kind_case_expr_maps_cluster_id_presence_to_the_compute_form(
    branch_sql: str, expected_kind: str
) -> None:
    # Table de verite exprimee sur le SQL RENDU, et non rejouee sur des donnees :
    # ce module est fait de helpers purs, il n'y a pas de Spark dans ces tests,
    # et un test qui pretendrait evaluer le `CASE` reimplementerait la semantique
    # qu'il est cense verifier. Un `cluster_id` renseigne = un cluster reel donc
    # CLASSIC ; son absence = aucun cluster donc SERVERLESS.
    assert f"{branch_sql} '{expected_kind}'" in compute_kind_case_expr("u.cluster_id")


def test_compute_kind_case_expr_stays_on_cluster_id_not_is_serverless() -> None:
    # NON-REGRESSION : le champ officiel `product_features.is_serverless` a ete
    # envisage comme remplacant (la story le recommandait sur une equivalence
    # annoncee "parfaite") puis ecarte SUR MESURE. Ce test echoue si quelqu'un
    # bascule l'expression sur ce champ, et le message porte la mesure qui a
    # decide de ne pas le faire -- c'est la forme la plus honnete disponible ici :
    # il verrouille la STRUCTURE du discriminant, il ne rejoue pas la donnee.
    expression = compute_kind_case_expr("usage_metadata.cluster_id")
    measured_exception = (
        "Bascule vers product_features.is_serverless REJETEE SUR MESURE le 2026-09-10, sur "
        "l'historique complet et les deux clouds (2 033 499 lignes DLT, "
        "2024-02-13..2026-09-09, soit 39x le perimetre de la story) : 1 seule discordance, "
        "et c'est le champ OFFICIEL qui se trompe -- cloud aws, 2026-07-31, workspace "
        "66097812060322, sku_name ENTERPRISE_JOBS_SERVERLESS_COMPUTE_EUROPE_FRANKFURT "
        "(le nom du SKU dit lui-meme SERVERLESS_COMPUTE), cluster_id NULL donc rendu "
        "SERVERLESS par l'expression actuelle, mais is_serverless NULL. Comme compute_kind "
        "est une cle de merge ecrite avec un ELSE, la bascule n'aurait pas produit une cle "
        "NULL reperable : elle aurait etiquete CLASSIC une ligne serverless, en silence. "
        "Le montant est negligeable (0,0006839 DBU), le mecanisme ne l'est pas. Detail dans "
        "specs/025-serverless-compute-page/T001g-baseline-measures.md section 4.3."
    )
    assert "WHEN usage_metadata.cluster_id IS NOT NULL THEN" in expression, measured_exception
    assert "is_serverless" not in expression, measured_exception
    assert "product_features" not in expression, measured_exception
