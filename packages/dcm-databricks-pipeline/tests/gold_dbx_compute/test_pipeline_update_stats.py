"""Tests de `pipelines.gold_dbx_compute.pipeline_update_stats`.

Pas de vraie `SparkSession` (coherent avec `tests/conftest.py`) : le builder
construit un unique `spark.sql(...)`, verifie ici via le texte SQL genere
(`FakeSpark`).

Les assertions portent sur des expressions ENTIERES et sont doublees
d'assertions NEGATIVES, parce que chaque piege mesure de cette table a une
version VOISINE ET CREDIBLE qui doit rester absente : un filtre pose sur la
LECTURE curated au lieu de la sortie (il tronque `MIN(period_start_time)` des
427 updates qui changent de jour calendaire), une fenetre sur
`update_start_time` au lieu de `update_end_time` (elle fige les updates a
cheval dans leur etat partiel), un `row_number() OVER (...)` pour l'etat
terminal (inutile, `MAX()` est exact par mesure), un `coalesce(result_state,
'UNKNOWN')` (il rend un taux d'echec incalculable), un `GROUP BY` a quatre
colonnes (il fait de `workspace_id`/`pipeline_id` des cles alors qu'ils sont
des attributs), ou un rang de tentative MATERIALISE (il devient faux en
silence, 6 requetes etalant leurs tentatives sur 10 jours ou plus).
"""

from __future__ import annotations

import re
from datetime import date
from types import SimpleNamespace

from pipelines.gold_dbx_compute import specs
from pipelines.gold_dbx_compute.pipeline_update_stats import build_pipeline_update_stats

_CURATED = "it.sch.curated_dbx_lakeflow_pipeline_update_timeline"
_WINDOW_FLOOR = date(2026, 8, 31)


def _code_only(query: str) -> str:
    """Requete privee de ses commentaires SQL (`-- ...`).

    Meme raison que dans `test_serverless_governance.py` : un commentaire qui
    CITE une construction interdite ferait passer au vert une assertion
    negative portee sur le texte brut.
    """
    return re.sub(r"--[^\n]*", "", query)


def _flat(code: str) -> str:
    """Code a blancs normalises, pour asserter une expression multi-lignes."""
    return re.sub(r"\s+", " ", code).strip()


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
    return tuple(columns)


def _cte(query: str, name: str) -> str:
    """Corps de la CTE `name` seule.

    Sert aux assertions qui doivent porter sur UNE etape : « l'entree n'est pas
    filtree » est indecidable sur la requete entiere, qui porte forcement un
    filtre plus loin (celui de la sortie, justement).
    """
    marker = f"{name} AS (\n"
    start = query.index(marker) + len(marker)
    return query[start:].split("\n    )", 1)[0]


def _stats_query(fakes: SimpleNamespace, lower_bound: date | None = _WINDOW_FLOOR) -> str:
    sentinel = fakes.DataFrame("pipeline_update_stats_result")
    spark = fakes.Spark(sql_result=sentinel)
    result = build_pipeline_update_stats(
        spark,
        pipeline_update_timeline_table=_CURATED,
        lower_bound=lower_bound,
    )
    assert result is sentinel
    assert len(spark.sql_calls) == 1
    query: str = spark.sql_calls[0]
    return query


def test_stats_reads_the_curated_table_and_neither_system_nor_gold(
    fakes: SimpleNamespace,
) -> None:
    # Aucun builder gold de ce plugin ne lit `system.*` : la couche curated porte
    # `cloud_provider` (qui unifie AWS natif et Azure cross-tenant) et le backend
    # ne lit que le catalogue applicatif. Aucune table gold en entree non plus :
    # cette table n'a qu'une source, ce qui justifie l'absence de `depends_on`
    # dans le job.
    code = _code_only(_stats_query(fakes))
    assert f"FROM {_CURATED}" in code
    assert "system." not in code
    assert "gold_" not in code
    assert code.count("FROM ") == 2  # la curated + la CTE `per_update`, rien d'autre.


def test_stats_never_bounds_its_input(fakes: SimpleNamespace) -> None:
    # LE point de conception de cette table : borner la LECTURE tronquerait
    # `MIN(period_start_time)` des 427 updates (0,104 %) qui terminent un autre
    # jour calendaire que celui ou ils commencent -- 40 au-dela de 4 jours, un a
    # 19 jours (448,1 h) -- et le MERGE remplacerait une duree correcte par une
    # duree plus courte, sans lever d'erreur.
    code = _code_only(_stats_query(fakes))
    per_update = _cte(code, "per_update")
    assert f"FROM {_CURATED}" in per_update
    assert "WHERE" not in per_update
    assert "period_start_time >=" not in per_update
    assert "period_end_time >=" not in per_update


def test_stats_windows_the_output_on_the_end_of_the_update(fakes: SimpleNamespace) -> None:
    # La fenetre porte sur la FIN et non sur le debut : un update commence avant
    # la borne mais termine apres resterait sinon fige dans son etat partiel
    # (2 cas mesures sur une fenetre de 10 jours au 2026-09-10). La colonne
    # filtree doit etre EXACTEMENT le `watermark_column` publie par la spec,
    # sinon `compute_gap_aware_lower_bound` inspecte un autre axe que celui que
    # le builder reecrit.
    code = _code_only(_stats_query(fakes))
    watermark = specs.PIPELINE_UPDATE_STATS_SPEC.watermark_column
    assert watermark == "update_end_time"
    assert f"AND {watermark} >= DATE '2026-08-31'" in code
    assert "AND update_start_time >=" not in code
    # Le filtre est bien sur la sortie : il suit le `FROM per_update`.
    assert code.index("FROM per_update") < code.index(f"AND {watermark} >=")


def test_stats_full_refresh_emits_no_window_at_all(fakes: SimpleNamespace) -> None:
    # `lower_bound=None` (1er run ou `--full-refresh`) : le `WHERE 1 = 1` reste,
    # le predicat disparait. Un `WHERE 1 = 1 AND` orphelin serait un SQL invalide
    # et un `>= DATE` residuel amputerait le backfill.
    code = _code_only(_stats_query(fakes, lower_bound=None))
    assert "WHERE 1 = 1" in code
    assert ">= DATE" not in code


def test_stats_group_by_is_exactly_the_merge_keys(fakes: SimpleNamespace) -> None:
    # `update_id` est globalement unique (412 350 ids pour autant de triplets
    # avec workspace/pipeline, mesure dev 2026-09-10) : grouper sur la cle de
    # merge elle-meme garantit UNE ligne de sortie par cle. Un `GROUP BY` a
    # quatre colonnes ferait des deux parents des cles de fait, et un MERGE sur
    # deux colonnes seulement fusionnerait alors plusieurs lignes en silence.
    code = _code_only(_stats_query(fakes))
    keys = specs.PIPELINE_UPDATE_STATS_MERGE_KEYS
    assert keys == ("cloud_provider", "update_id")
    assert f"GROUP BY {', '.join(keys)}" in code
    assert "GROUP BY cloud_provider, workspace_id, pipeline_id, update_id" not in code
    assert code.count("GROUP BY") == 1
    # Les deux parents sont des ATTRIBUTS : agreges, jamais groupes.
    assert "MAX(workspace_id) AS workspace_id" in code
    assert "MAX(pipeline_id) AS pipeline_id" in code


def test_stats_duration_is_the_clock_expression(fakes: SimpleNamespace) -> None:
    # Duree HORLOGE (fin la plus tardive - debut le plus precoce), verifiee
    # equivalente a la somme des tranches (ecart median 0,0 s, p95 0,0 s, 0
    # update au-dela de 60 s sur les 9 683 updates multi-tranches) : les deux
    # definitions donnent le meme chiffre, on retient celle qui s'explique en
    # une phrase. Un `datediff` rendrait des jours, pas des secondes.
    flat = _flat(_code_only(_stats_query(fakes)))
    assert (
        "unix_timestamp(MAX(period_end_time)) "
        "- unix_timestamp(MIN(period_start_time)) AS duration_sec" in flat
    )
    assert "SUM(unix_timestamp(period_end_time)" not in flat
    assert "datediff" not in flat


def test_stats_takes_the_outer_bounds_of_the_update(fakes: SimpleNamespace) -> None:
    # Bornes de l'update ENTIER, donc MIN sur les debuts et MAX sur les fins.
    # Les inverser passerait les tests de volumetrie et rendrait des durees
    # negatives sur les seuls updates multi-tranches (2,35 %).
    code = _code_only(_stats_query(fakes))
    assert "MIN(period_start_time) AS update_start_time" in code
    assert "MAX(period_end_time) AS update_end_time" in code
    assert "MAX(period_start_time) AS update_start_time" not in code
    assert "MIN(period_end_time) AS update_end_time" not in code


def test_stats_flattens_the_compute_struct_and_drops_the_cluster_id(
    fakes: SimpleNamespace,
) -> None:
    # L'ingestion etant fidele source, le struct `compute` arrive tel quel en
    # curated (`select_columns` ne peut pas aliaser, cf. `readers.py`) : le
    # flatten `compute.type -> compute_type` vit donc ici. `compute.cluster_id`
    # est volontairement laisse de cote (NULL sur 81,7 % des lignes : le
    # serverless n'a pas de cluster).
    code = _code_only(_stats_query(fakes))
    assert "MAX(compute.type) AS compute_type" in code
    assert "compute.cluster_id" not in code


def test_stats_keeps_the_terminal_state_without_a_window_function(
    fakes: SimpleNamespace,
) -> None:
    # `MAX(result_state)` est exact par MESURE : 9 817 des 422 167 lignes portent
    # `result_state IS NULL` (tranches intermediaires), l'etat terminal n'est
    # porte que par UNE ligne, et 0 update sur 412 362 expose deux etats
    # non-NULL. Un `row_number() OVER (ORDER BY period_start_time DESC)`
    # coutrait un shuffle pour le meme resultat. Et le NULL doit RESTER NULL :
    # un `'UNKNOWN'` rend le denominateur d'un taux d'echec inexcluable.
    code = _code_only(_stats_query(fakes))
    assert "MAX(result_state) AS result_state" in code
    assert "row_number()" not in code
    assert "OVER (" not in code
    assert "UNKNOWN" not in code
    assert "coalesce(result_state" not in code


def test_stats_publishes_request_id_but_not_a_materialized_attempt_rank(
    fakes: SimpleNamespace,
) -> None:
    # `request_id` est la cle de deduplication des retentatives (412 350 updates
    # pour 347 683 requetes, 14 056 requetes retentees, jusqu'a 14 tentatives) :
    # sans elle un taux d'echec par update sur-estime l'ecart
    # serverless/classique de 1,49x. Le RANG de tentative n'est en revanche pas
    # materialise : 6 requetes etalent leurs tentatives sur 10 jours ou plus
    # (jusqu'a 49), une colonne figee deviendrait fausse en silence des que la
    # retentative arriverait apres la sortie de la precedente de la fenetre.
    code = _code_only(_stats_query(fakes))
    assert "MAX(request_id) AS request_id" in code
    assert "request_id" in _output_columns(code, "per_update")
    assert "attempt_number" not in code
    assert "is_last_attempt" not in code


def test_stats_counts_the_source_slices_once_as_an_audit_column(
    fakes: SimpleNamespace,
) -> None:
    # `period_count` rend l'agregation auditable sans relire la curated :
    # `SUM(period_count)` doit egaler le `COUNT(*)` curated. C'est aussi le seul
    # `COUNT(*)` legitime sur cette source -- compter les lignes curated pour
    # compter des executions sur-compte de 9 817 unites.
    code = _code_only(_stats_query(fakes))
    assert "COUNT(*) AS period_count" in code
    assert code.count("COUNT(*)") == 1
    assert "COUNT(DISTINCT" not in code


def test_stats_omits_the_empty_array_columns(fakes: SimpleNamespace) -> None:
    # Les 3 colonnes ARRAY de la source sont vides sur plus de 99,8 % des lignes
    # (311 / 494 / 0 lignes non vides sur 422 167, mesure dev 2026-09-10) et
    # sans usage produit : les agreger couterait un shuffle par rien.
    code = _code_only(_stats_query(fakes))
    assert "refresh_selection" not in code
    assert "full_refresh_selection" not in code
    assert "reset_checkpoint_selection" not in code


def test_stats_output_columns_match_the_published_comments(fakes: SimpleNamespace) -> None:
    # `merge_into_table` emet un `ALTER COLUMN ... COMMENT` par entree de
    # `column_comments` : une cle orpheline echoue au RUNTIME, pas en test. Et
    # une colonne sans commentaire arrive nue dans Catalog Explorer -- sur cette
    # table c'est le piege du taux d'echec par update qui disparaitrait.
    columns = _output_columns(_code_only(_stats_query(fakes)), "per_update")
    assert set(columns) == set(specs.PIPELINE_UPDATE_STATS_COLUMN_COMMENTS)
    assert columns[-1] == "_generated_at"
    assert len(columns) == len(set(columns))
    for key in specs.PIPELINE_UPDATE_STATS_MERGE_KEYS:
        assert key in columns
