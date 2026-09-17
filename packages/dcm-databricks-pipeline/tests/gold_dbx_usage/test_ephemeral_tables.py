"""Tests de `pipelines.gold_dbx_usage.ephemeral_tables` — definition unique de l'ephemere.

Les deux predicats de seuil sont EVALUES, pas seulement lus. Une assertion de
sous-chaine dit que `IS NOT NULL` et `<` sont presents ; elle ne dit pas que les deux
faces se partagent exactement les lignes. Or c'est la que l'erreur coute le plus : un
chevauchement fait ecrire puis supprimer la meme ligne a chaque run, un trou laisse une
ligne pour toujours. Les predicats sont donc executes tels qu'ils sont rendus, sur SQLite,
avec `unix_timestamp` enregistree comme fonction identite -- l'arithmetique testee est
alors celle du texte livre, sans reecriture (meme approche que les tests d'exclusion
cote backend, qui executent le SQL rendu au lieu d'y chercher une sous-chaine).
"""

from __future__ import annotations

import logging
import sqlite3
from types import SimpleNamespace

import pytest

from pipelines.gold_dbx_usage.ephemeral_tables import (
    EPHEMERAL_KEYS_CTE_NAME,
    LIVED_LONG_ENOUGH_PREDICATE,
    TABLE_KEY_COLUMNS,
    WAS_EPHEMERAL_PREDICATE,
    ephemeral_keys_cte,
    not_ephemeral_predicate,
    purge_ephemeral_rows,
)
from pipelines.gold_dbx_usage.specs import TABLE_CATALOG_MERGE_KEYS
from pipelines.gold_dbx_usage.sql_helpers import EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS

TARGET_TABLE = "it.sch.gold_dbx_usage_table_catalog"
UC_TABLES_TABLE = "it.sch.curated_dbx_uc_tables"
TABLE_OPERATIONS_TABLE = "it.sch.curated_dbx_uc_table_operations"


def _without_sql_comments(sql: str) -> str:
    """Le SQL prive de ses commentaires `--`.

    Les commentaires de ce module citent les predicats qu'ils expliquent : sans ce
    nettoyage, une assertion d'absence passerait sur une simple mention en prose.
    """
    return "\n".join(line.split("--")[0] for line in sql.splitlines())


def _purge_query(fakes: SimpleNamespace, target_table: str = TARGET_TABLE) -> str:
    spark = fakes.Spark()
    purge_ephemeral_rows(
        spark,
        target_table=target_table,
        uc_tables_table=UC_TABLES_TABLE,
        table_operations_table=TABLE_OPERATIONS_TABLE,
    )
    assert len(spark.sql_calls) == 1
    query: str = spark.sql_calls[0]
    return query


def _ephemeral_predicate_clause(purge_sql: str) -> str:
    """La seule portion du SQL de purge qui porte le predicat de duree de vie.

    Fenetre de recherche BORNEE, et c'est le point : le SQL complet contient d'autres
    `IS NOT NULL` (ceux du predicat d'entree sur `request_params`, bien plus haut), donc
    une assertion d'ordre posee sur le texte entier serait vraie quelle que soit la forme
    du predicat -- satisfaite pour la mauvaise raison.
    """
    _, _, clause = _without_sql_comments(purge_sql).partition("WHERE lo.last_operation")
    assert clause, "le predicat de suppression a change de forme"
    return clause


def _predicate_holds(
    predicate: str, *, created_event_at: int | None, last_operation_at: int
) -> bool:
    """Evalue un predicat rendu sur une ligne, en SQLite.

    `unix_timestamp` est enregistree comme identite : les colonnes portent deja des
    secondes, donc l'arithmetique evaluee est exactement celle du texte livre. Rien n'est
    reecrit -- une reformulation du predicat qui changerait son sens changerait le
    resultat, ce qu'une assertion de sous-chaine ne verrait pas.
    """
    connection = sqlite3.connect(":memory:")
    try:
        connection.create_function("unix_timestamp", 1, lambda value: value)
        connection.execute("CREATE TABLE lo (created_event_at INTEGER, last_operation_at INTEGER)")
        connection.execute(
            "INSERT INTO lo (created_event_at, last_operation_at) VALUES (?, ?)",
            (created_event_at, last_operation_at),
        )
        row = connection.execute(f"SELECT ({predicate}) FROM lo").fetchone()
    finally:
        connection.close()
    # SQLite rend NULL pour un predicat indecidable : un predicat ecrit en negatif
    # (`NOT (age >= seuil)`) tomberait ici, et `bool(None)` est faux -- ce qui masquerait
    # justement le defaut. D'ou l'assertion : les deux faces doivent TRANCHER.
    assert row[0] is not None, "predicat indecidable sur cette ligne"
    return bool(row[0])


# Age inconnu, age court, borne exacte du seuil, age long. La borne est incluse du cote
# « garder » : `>= seuil` d'un cote, `< seuil` de l'autre.
_LIFETIME_CASES = (
    (None, 5_000),
    (0, EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS - 1),
    (0, EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS),
    (0, EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS * 100),
)


@pytest.mark.parametrize(("created_event_at", "last_operation_at"), _LIFETIME_CASES)
def test_exactly_one_of_the_two_predicates_holds_on_every_row(
    created_event_at: int | None, last_operation_at: int
) -> None:
    """Complementarite STRICTE, evaluee : reunion = toutes les lignes, intersection vide.

    Les deux faces decident de sorts opposes (obtenir une ligne / la perdre). Si elles se
    chevauchaient, la ligne concernee serait ecrite puis supprimee a CHAQUE run -- le
    defaut meme que ce mecanisme doit eviter. Si elles laissaient un trou, la ligne y
    resterait sans qu'aucun run ne puisse la reprendre.
    """
    kept = _predicate_holds(
        LIVED_LONG_ENOUGH_PREDICATE,
        created_event_at=created_event_at,
        last_operation_at=last_operation_at,
    )
    purged = _predicate_holds(
        WAS_EPHEMERAL_PREDICATE,
        created_event_at=created_event_at,
        last_operation_at=last_operation_at,
    )
    assert kept != purged


def test_an_unknown_birth_is_kept_and_never_purged() -> None:
    """Le sens de l'erreur : un age inconnu ne prouve rien, donc on garde.

    Une naissance sortie de la fenetre de retention d'audit n'atteste aucune ephemerite.
    Une suppression est irreversible la ou un refus d'ecrire ne l'est pas : le doute doit
    toujours pencher du meme cote.
    """
    assert _predicate_holds(LIVED_LONG_ENOUGH_PREDICATE, created_event_at=None, last_operation_at=1)
    assert not _predicate_holds(WAS_EPHEMERAL_PREDICATE, created_event_at=None, last_operation_at=1)


def test_the_threshold_boundary_is_kept_not_purged() -> None:
    """Une vie EGALE au seuil est gardee : le seuil borne les vies « inferieures a »."""
    exact = {"created_event_at": 0, "last_operation_at": EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS}
    assert _predicate_holds(LIVED_LONG_ENOUGH_PREDICATE, **exact)  # type: ignore[arg-type]
    assert not _predicate_holds(WAS_EPHEMERAL_PREDICATE, **exact)  # type: ignore[arg-type]


def test_the_ephemeral_key_grain_is_the_registry_merge_key() -> None:
    """Meme grain que la cle de merge du registre, sinon la purge viserait a cote.

    La purge apparie sur ces colonnes ; si le registre etait ecrit a un autre grain, une
    ligne pourrait rester hors de portee sans qu'aucun test de forme ne le voie.
    """
    assert TABLE_KEY_COLUMNS == TABLE_CATALOG_MERGE_KEYS


def test_purge_deletes_and_writes_nothing(fakes: SimpleNamespace) -> None:
    """Un DELETE explicite, et rien d'autre.

    `merge_into_table` ne supprime jamais de ligne cible : les lignes deja posees restent,
    et notamment la ligne `ACTIVE` d'une table qu'un run a vue vivante entre son
    `createTable` et son `deleteTable` -- celle-la n'est passee par aucun filtre de duree
    de vie. Un `WHEN NOT MATCHED` ferait de ce MERGE une ecriture, sur une source reduite
    a 4 colonnes de cle.
    """
    query = _purge_query(fakes)
    assert f"MERGE INTO {TARGET_TABLE} AS cible" in query
    assert "WHEN MATCHED THEN DELETE" in query
    for key in TABLE_KEY_COLUMNS:
        assert f"cible.{key} = ephemere.{key}" in query
    purge_sql = _without_sql_comments(query)
    assert "WHEN NOT MATCHED" not in purge_sql
    assert "UPDATE" not in purge_sql
    assert "INSERT" not in purge_sql


def test_purge_matches_on_the_table_key_only_never_on_a_lifecycle_flag(
    fakes: SimpleNamespace,
) -> None:
    """Le `ON` ne porte AUCUN predicat d'etat, et cette absence est epinglee.

    Le critere le plus delicat de la task -- retirer aussi la ligne `ACTIVE` d'une table
    qu'un run a vue vivante -- tient a cette absence. Ajouter `AND cible.is_deleted` au
    `ON` est un reflexe defensif tout a fait plausible en relecture, et casserait le
    critere sans qu'aucune assertion de presence ne tombe.
    """
    on_clause, _, _ = _without_sql_comments(_purge_query(fakes)).partition("WHEN MATCHED")
    _, _, on_clause = on_clause.rpartition(") AS ephemere")
    assert on_clause.strip(), "la clause ON a change de forme"
    for column in ("is_deleted", "lifecycle_state", "deleted_at", "present_in_referential"):
        assert f"cible.{column}" not in on_clause
    # Et la cle appariee est la cle de TABLE, pas la cle de merge de la cible : sur un
    # fait, une cle ephemere doit perdre TOUTES ses lignes datees, pas celles d'un jour.
    assert "period_start" not in on_clause
    assert "consumer_id" not in on_clause


def test_purge_never_removes_the_row_of_a_table_that_still_exists(
    fakes: SimpleNamespace,
) -> None:
    """Deux garde-fous, aucun redondant.

    Le `LEFT ANTI JOIN` sur le referentiel protege ce qui EXISTE : une cle presente dans
    `curated_dbx_uc_tables` (full load purge) existe au moment du run, quelle que soit son
    histoire d'audit -- c'est ce qui sauve un nom reutilise ou une table recreee. Le
    `deleteTable` exige une PREUVE de suppression : sans lui, un privilege manquant sur le
    principal d'ingestion suffirait a faire disparaitre la ligne d'une table vivante.
    """
    query = _purge_query(fakes)
    assert f"LEFT ANTI JOIN {EPHEMERAL_KEYS_CTE_NAME}_referentiel r" in query
    assert f"FROM {UC_TABLES_TABLE}" in query
    for key in TABLE_KEY_COLUMNS:
        assert f"r.{key} = lo.{key}" in query
    assert "WHERE lo.last_operation = 'deleteTable'" in query


def test_purge_predicate_states_the_known_age_before_the_arithmetic(
    fakes: SimpleNamespace,
) -> None:
    """`IS NOT NULL` d'abord, et jamais un `NOT (...)`.

    L'ordre est verifie DANS la clause de suppression, pas sur le SQL entier : ailleurs se
    trouvent les `IS NOT NULL` du predicat d'entree sur `request_params`, qui rendraient
    l'assertion vraie sans rien dire du predicat teste.
    """
    clause = _ephemeral_predicate_clause(_purge_query(fakes))
    assert "NOT (" not in clause
    assert clause.index("IS NOT NULL") < clause.index("unix_timestamp")


def test_not_ephemeral_predicate_compares_the_whole_table_key(fakes: SimpleNamespace) -> None:
    """`NOT EXISTS` sur les 4 colonnes : une seule oubliee retirerait des homonymes.

    Comparaison par `=` colonne a colonne : un `catalog`/`schema` NULL (nom mal forme dans
    l'audit) n'apparie rien et la ligne est GARDEE -- meme sens d'erreur que partout
    ailleurs ici.
    """
    predicate = not_ephemeral_predicate("a")
    assert predicate.startswith(f"NOT EXISTS (SELECT 1 FROM {EPHEMERAL_KEYS_CTE_NAME} e WHERE ")
    for column in TABLE_KEY_COLUMNS:
        assert f"e.{column} = a.{column}" in predicate
    assert predicate.count(" AND ") == len(TABLE_KEY_COLUMNS) - 1


def test_ephemeral_keys_cte_ends_without_a_separator() -> None:
    """Rendu enchainable : c'est l'appelant qui pose la virgule.

    Une virgule ou un point-virgule terminal rendrait le fragment inutilisable en tete
    d'un `WITH` existant, ou le ferait dependre de sa position.
    """
    cte = ephemeral_keys_cte(
        uc_tables_table=UC_TABLES_TABLE, table_operations_table=TABLE_OPERATIONS_TABLE
    )
    assert cte.rstrip().endswith(")")
    assert not cte.rstrip().endswith(",)")
    assert ";" not in cte
    assert cte.startswith(f"{EPHEMERAL_KEYS_CTE_NAME}_referentiel AS (")


def test_purge_logs_how_many_rows_it_removed(
    fakes: SimpleNamespace, caplog: pytest.LogCaptureFixture
) -> None:
    """La seule operation destructrice de cette couche gold laisse une trace.

    Sans elle, personne ne saurait combien de lignes un run a retirees, ni ne verrait un
    pic. La metrique est lue par NOM de colonne : la liste des metriques d'un MERGE Delta
    depend de la version du runtime.
    """
    metrics = fakes.DataFrame(
        columns=["num_affected_rows", "num_updated_rows", "num_deleted_rows"],
        rows=[[42, 0, 42]],
    )
    spark = fakes.Spark(sql_result=metrics)
    with caplog.at_level(logging.INFO):
        purge_ephemeral_rows(
            spark,
            target_table=TARGET_TABLE,
            uc_tables_table=UC_TABLES_TABLE,
            table_operations_table=TABLE_OPERATIONS_TABLE,
        )
    assert "42 ligne(s) retiree(s)" in caplog.text
    assert TARGET_TABLE in caplog.text


def test_purge_does_not_fail_when_the_session_reports_no_metric(
    fakes: SimpleNamespace, caplog: pytest.LogCaptureFixture
) -> None:
    """Une trace absente n'est pas une purge en echec.

    Le compte n'est pas un resultat metier : une session qui ne publierait pas les
    metriques du MERGE ne doit pas faire tomber la tache. Le log le dit alors plutot que
    d'annoncer zero, qui serait faux.
    """
    spark = fakes.Spark()
    with caplog.at_level(logging.INFO):
        purge_ephemeral_rows(
            spark,
            target_table=TARGET_TABLE,
            uc_tables_table=UC_TABLES_TABLE,
            table_operations_table=TABLE_OPERATIONS_TABLE,
        )
    assert "compte non rapporte" in caplog.text
