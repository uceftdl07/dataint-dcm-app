"""Ecritures Delta idempotentes (MERGE, staging) — socle reutilisable.

Regroupe les primitives d'ecriture generiques, reutilisees par les couches
curated (`pipelines.system_tables.ingest`) et gold
(`pipelines.gold_dbx_compute.entrypoint`) : construction du `MERGE INTO`,
ecriture idempotente (creation puis upsert), append vers une table de staging
ephemere, et attachement de commentaires de table/colonnes. Aucune notion
metier ni de couche : le comportement est pilote par les cles de merge, les
colonnes de partition et les commentaires fournis par l'appelant.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pyspark.sql import DataFrame, SparkSession


def _escape_sql_string(value: str) -> str:
    """Echappe une chaine pour un litteral SQL (`'` -> `''`)."""
    return value.replace("'", "''")


def _sanitize_identifier(value: str) -> str:
    """Assainit une chaine pour en faire un fragment d'identifiant SQL valide.

    Remplace toute sequence de caracteres non alphanumeriques par `_` (les noms
    qualifies `catalog.schema.table` contiennent des points, les identifiants
    de run peuvent contenir `-`/`/`, tous invalides tels quels dans un nom de
    vue/table). Peut renvoyer une chaine vide (ex. `value` entierement fait de
    symboles) : a l'appelant de choisir un repli le cas echeant. Reutilise par
    `_merge_source_view_name` et `staging_table_name` pour ne jamais dupliquer
    cette regle.
    """
    return re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_")


def _merge_source_view_name(target_table: str) -> str:
    """Nom de la vue temporaire source du `MERGE INTO`, unique par table cible.

    Derive de `target_table` (au lieu d'un nom fixe partage par tous les
    appelants) : evite toute collision si deux `merge_into_table` sur des
    tables differentes s'executaient dans la meme session Spark.
    """
    return f"_stg_merge_source__{_sanitize_identifier(target_table) or 'table'}"


def build_merge_sql(
    target_table: str,
    source_view: str,
    merge_keys: tuple[str, ...],
    partition_predicate: str | None = None,
    absent_row_delete_predicate: str | None = None,
) -> str:
    """Construit un `MERGE INTO` idempotent sur les cles metier.

    2 executions consecutives ⇒ 0 doublon (SC-004) : les lignes deja presentes
    sont mises a jour (UPDATE), les nouvelles inserees (INSERT).

    `MERGE WITH SCHEMA EVOLUTION` : absorbe la divergence de schema Azure/AWS
    (colonnes source manquantes ⇒ NULL, nouvelles colonnes ⇒ ajoutees a la cible).
    On passe par la clause SQL car la conf globale
    `spark.databricks.delta.schema.autoMerge.enabled` est INTERDITE en serverless
    (`CONFIG_NOT_AVAILABLE.SERVERLESS_...`). Remplace l'ancien
    `unionByName(allowMissingColumns=True)`.

    `partition_predicate` (optionnel) restreint le scan de la table cible aux
    partitions concernees (pruning) — crucial pour les grosses tables comme
    `usage`, ex. `t.usage_date >= DATE '2026-07-01'`.

    `absent_row_delete_predicate` (optionnel) ajoute une clause
    `WHEN NOT MATCHED BY SOURCE AND <predicat> THEN DELETE`, utile pour un
    SNAPSHOT d'etat courant (sans lui le MERGE est un upsert qui accumule les
    objets disparus). Le predicat porte sur l'alias cible `t` et sert de
    GARDE-FOU : en ne supprimant que des lignes anciennes (ex.
    `t._generated_at < date_add(current_date(), -7)`), un run degrade (source
    vide/partielle) ne peut pas vider la table.
    """
    if not merge_keys:
        raise ValueError("merge_keys must not be empty")
    # `<=>` (null-safe) et non `=` : certaines cles metier sont nullables (ex.
    # lignage vers un PATH -> *_table_full_name NULL ; entity_run_id / created_by
    # absents). Avec `=`, NULL = NULL vaut NULL ⇒ jamais MATCHED ⇒ doublons au
    # re-run sur la fenetre de lookback. Identique a `=` pour les cles non-nulles.
    condition = " AND ".join(f"t.{key} <=> s.{key}" for key in merge_keys)
    if partition_predicate:
        condition = f"{condition} AND {partition_predicate}"
    clauses = [
        "WHEN MATCHED THEN UPDATE SET *",
        "WHEN NOT MATCHED THEN INSERT *",
    ]
    if absent_row_delete_predicate:
        clauses.append(
            f"WHEN NOT MATCHED BY SOURCE AND ({absent_row_delete_predicate}) THEN DELETE"
        )
    return (
        f"MERGE WITH SCHEMA EVOLUTION INTO {target_table} AS t\n"
        f"USING {source_view} AS s\n"
        f"ON {condition}\n" + "\n".join(clauses)
    )


def merge_into_table(
    spark: SparkSession,
    df: DataFrame,
    *,
    target_table: str,
    merge_keys: tuple[str, ...],
    partition_columns: tuple[str, ...] = (),
    partition_predicate: str | None = None,
    absent_row_delete_predicate: str | None = None,
    column_comments: Mapping[str, str] | None = None,
    table_comment: str | None = None,
) -> None:
    """Ecrit `df` dans `target_table` de facon idempotente.

    Premiere execution (table absente) : creation par `saveAsTable`
    (partitionnee si `partition_columns`). Executions suivantes : `MERGE INTO`
    sur les cles metier, avec pruning de partition optionnel
    (`partition_predicate`) pour borner le scan cible. Dans les deux cas, si
    fournis, `table_comment` et `column_comments` sont attaches a la table
    juste apres l'ecriture (cf. `_apply_table_comments`).

    `absent_row_delete_predicate` (optionnel) transmis a `build_merge_sql` :
    supprime les lignes cible absentes de `df` qui satisfont ce predicat
    (snapshots d'etat courant, cf. la docstring de `build_merge_sql`). Sans lui,
    l'ecriture est un upsert pur : aucune ligne n'est jamais supprimee.

    `mergeSchema` / `MERGE WITH SCHEMA EVOLUTION` gerent l'evolution de schema au
    niveau de l'ecriture (option serverless-compatible, la conf globale
    `delta.schema.autoMerge.enabled` etant interdite en serverless).

    LIMITE, et elle mord des qu'on CHANGE UN GRAIN : l'evolution de schema ne
    couvre que l'ECRITURE (`UPDATE SET *` / `INSERT *`). La condition `ON` est
    resolue contre le schema COURANT de la cible, donc ajouter a `merge_keys`
    une colonne que la table n'a pas encore echoue a l'analyse
    (`DELTA_MERGE_UNRESOLVED_EXPRESSION: Cannot resolve t.<col> in search
    condition`, constate en dev le 2026-09-09 en ajoutant `compute_kind` au
    grain de `gold_dbx_compute_pipeline_cost_daily`), et aucun `full_refresh`
    n'y change rien : le MERGE ne demarre pas. Un changement de grain se
    deploie donc en DEUX temps : supprimer la table cible (`DROP TABLE`, les
    tables gold sont recalculables depuis curated et `UNDROP` reste disponible
    7 jours sur une table UC MANAGED), puis relancer la tache — l'absence de
    cible fait passer par la branche `saveAsTable` ci-dessous, qui recree le bon
    schema. Un `ALTER TABLE ... ADD COLUMN` prealable debloquerait aussi le
    MERGE, mais laisserait toutes les lignes historiques avec la nouvelle cle a
    `NULL` : jamais appariees (le `<=>` null-safe ne rapproche pas `NULL` de
    `'CLASSIC'`), elles subsisteraient en doublons a purger a la main.
    """
    # Déduplique sur les clés de merge : Delta refuse si plusieurs lignes source
    # correspondent à la même ligne cible (DELTA_MULTIPLE_SOURCE_ROW_MATCHING_TARGET_ROW).
    df = df.dropDuplicates(list(merge_keys))
    if not spark.catalog.tableExists(target_table):
        writer = df.write.format("delta").option("mergeSchema", "true")
        if partition_columns:
            writer = writer.partitionBy(*partition_columns)
        writer.saveAsTable(target_table)
    else:
        source_view = _merge_source_view_name(target_table)
        df.createOrReplaceTempView(source_view)
        spark.sql(
            build_merge_sql(
                target_table,
                source_view,
                merge_keys,
                partition_predicate,
                absent_row_delete_predicate,
            )
        )
    _apply_table_comments(
        spark, target_table, column_comments=column_comments, table_comment=table_comment
    )


def _apply_table_comments(
    spark: SparkSession,
    target_table: str,
    *,
    column_comments: Mapping[str, str] | None,
    table_comment: str | None,
) -> None:
    """Attache un commentaire de table et des commentaires de colonnes.

    Execute `COMMENT ON TABLE ... IS ...` (si `table_comment` fourni) puis
    `ALTER TABLE ... ALTER COLUMN ... COMMENT ...` pour chaque entree de
    `column_comments`. Operation de metadonnees pure (aucun scan de donnees) ;
    appelee a chaque `merge_into_table`, table nouvellement creee ou deja
    existante.
    """
    if table_comment:
        spark.sql(f"COMMENT ON TABLE {target_table} IS '{_escape_sql_string(table_comment)}'")
    for column, comment in (column_comments or {}).items():
        spark.sql(
            f"ALTER TABLE {target_table} ALTER COLUMN {column} "
            f"COMMENT '{_escape_sql_string(comment)}'"
        )


def staging_table_name(curated_table: str, collection_run_id: str) -> str:
    """Nom de la table de staging ephemere, unique par run.

    Derive du nom curated qualifie (`catalog.schema.table`) + un suffixe issu du
    `collection_run_id` (assaini via `_sanitize_identifier` : seuls
    `[0-9A-Za-z_]`, sinon un identifiant SQL invalide). L'unicite par run evite
    toute collision si deux runs coexistaient.
    """
    suffix = _sanitize_identifier(collection_run_id) or "run"
    return f"{curated_table}__stg_{suffix}"


def append_to_staging(
    spark: SparkSession,
    df: DataFrame,
    staging_table: str,
    *,
    first_batch: bool,
) -> None:
    """Append d'un lot vers la table de staging (creation/reset au 1er lot).

    Insert pur (aucun scan de la cible curated), donc bien moins couteux qu'un
    MERGE par lot. `overwrite` au 1er lot (reset d'un eventuel staging orphelin
    d'un run precedent interrompu), `append` ensuite. `mergeSchema` absorbe une
    divergence de colonnes entre lots. La memoire du driver reste bornee : un
    seul lot est materialise a la fois (`createDataFrame`), l'ecriture etant
    ensuite distribuee par Spark.
    """
    mode = "overwrite" if first_batch else "append"
    (df.write.format("delta").option("mergeSchema", "true").mode(mode).saveAsTable(staging_table))


def non_cloud_merge_keys(merge_keys: tuple[str, ...]) -> tuple[str, ...]:
    """Cles de merge metier, sans `cloud_provider`.

    `cloud_provider` est une colonne d'ENVELOPPE (ajoutee par
    `transforms.enrich_with_envelope` a l'ingestion), absente de toute lecture
    BRUTE de la source (`read_native_source`/`read_azure_batches`). Les
    primitives de purge (`build_purge_merge_sql`, et le calcul des lignes
    absentes cote `pipelines.common.purge`) comparent donc la cible curated a
    une lecture source fraiche sur les seules cles METIER, `cloud_provider`
    etant impose separement via un predicat explicite (chaque run de purge
    traite un seul cloud a la fois, comme l'ingestion).
    """
    return tuple(key for key in merge_keys if key != "cloud_provider")


def build_purge_merge_sql(
    target_table: str,
    source_view: str,
    merge_keys: tuple[str, ...],
    cloud_provider: str,
) -> str:
    """Construit un `MERGE` de suppression pure (aucun UPDATE/INSERT).

    Supprime de `target_table` les lignes du `cloud_provider` traite qui n'ont
    PAS de correspondance dans `source_view` sur les cles metier
    (`WHEN NOT MATCHED BY SOURCE`) : c'est le mecanisme de purge, symetrique de
    `build_merge_sql` qui ne fait qu'upserter. Le filtre `cloud_provider` est
    applique a la fois dans la condition `ON` (evite qu'une ligne d'un AUTRE
    cloud avec la meme cle metier soit consideree a tort comme "matched") et
    dans la clause `WHEN NOT MATCHED BY SOURCE` (ne supprime jamais les lignes
    des clouds non traites par ce run) : les MERGE de purge sont SEPARES par
    cloud, meme convention que `ingest_system_table` (un run Azure ne doit
    jamais supprimer des lignes AWS, et reciproquement).
    """
    business_keys = non_cloud_merge_keys(merge_keys)
    if not business_keys:
        raise ValueError("merge_keys must contain at least one non-cloud_provider key")
    cloud_literal = _escape_sql_string(cloud_provider)
    condition = " AND ".join(f"t.{key} <=> s.{key}" for key in business_keys)
    condition = f"{condition} AND t.cloud_provider = '{cloud_literal}'"
    return (
        f"MERGE INTO {target_table} AS t\n"
        f"USING {source_view} AS s\n"
        f"ON {condition}\n"
        f"WHEN NOT MATCHED BY SOURCE AND t.cloud_provider = '{cloud_literal}' THEN DELETE"
    )


def purge_rows_not_in_source(
    spark: SparkSession,
    df_source: DataFrame,
    *,
    target_table: str,
    merge_keys: tuple[str, ...],
    cloud_provider: str,
) -> None:
    """Supprime de `target_table` les lignes absentes de `df_source` (un cloud).

    `df_source` doit porter une lecture FRAICHE et COMPLETE de la table source
    pour ce cloud (jamais un lot partiel) : toute ligne curated de ce cloud sans
    correspondance sur les cles metier est supprimee. Aucun garde-fou
    volumetrique ici (primitive d'ecriture generique, comme `merge_into_table`) :
    l'appelant (`pipelines.common.purge.purge_absent_rows`) est responsable de
    verifier le seuil AVANT d'appeler cette fonction.
    """
    source_view = f"{_merge_source_view_name(target_table)}__purge"
    df_source.createOrReplaceTempView(source_view)
    spark.sql(build_purge_merge_sql(target_table, source_view, merge_keys, cloud_provider))
