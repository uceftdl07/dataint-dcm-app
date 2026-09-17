"""Definition UNIQUE de la table ephemere, partagee par le registre et les faits.

UNE TABLE EPHEMERE N'EST PAS UNE TABLE SUPPRIMEE. Une table dont l'audit a vu la
naissance et la mort a moins de `EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS` d'intervalle n'a
jamais ete un objet gouverne, seulement un intermediaire d'execution -- une table de
staging creee, lue et droppee par le meme run de job.

CE MODULE EXISTE POUR QUE « EPHEMERE » SOIT DEFINI A UN SEUL ENDROIT. Cinq tables gold
doivent s'accorder sur la reponse -- le registre `table_catalog`, les trois faits porteurs
de cles (`table_daily`, `table_popularity_daily`, `table_query_performance_daily`) et le
snapshot `table_governance` -- et une divergence entre deux d'entre elles ne se verrait
pas : chaque table resterait coherente avec elle-meme, seule la jointure entre elles
mentirait.

POURQUOI LES FAITS AUSSI, ET PAS SEULEMENT LE REGISTRE. L'exclusion en aval ne lit pas
l'absence d'une ligne, elle lit la PRESENCE d'une ligne `is_deleted = true` au registre
(`deleted_table_conditions` cote API, `recommendations.py` cote pipeline). Retirer la
ligne du registre sans retirer les lignes de fait rendrait donc l'ephemere VISIBLE comme
une table vivante : le seul signal qui servait a la cacher aurait disparu. Les deux vont
ensemble, sinon la task en livre l'inverse.

DEUX MECANISMES PAR TABLE, ET LES DEUX SONT NECESSAIRES :
  1. `not_ephemeral_predicate` -- ne pas ECRIRE la ligne. Pose dans le builder, sur la
     CTE rendue par `ephemeral_keys_cte`.
  2. `purge_ephemeral_rows` -- RETIRER les lignes deja ecrites. `merge_into_table` ne
     supprime jamais de ligne cible, donc aucun filtre a l'ecriture ne peut rattraper le
     stock accumule par les runs anterieurs, ni la ligne `ACTIVE` d'une table qu'un run a
     vue VIVANTE entre son `createTable` et son `deleteTable` -- celle-la est entree par
     le referentiel, aucun filtre de duree de vie ne l'a vue passer.

Le filtre sans la purge laisse le stock ; la purge sans le filtre fait ecrire puis
supprimer les memes lignes A CHAQUE RUN, les faits etant reecrits par fenetre
incrementale.

`gold_dbx_usage_consumer_daily` EST AU GRAIN CONSOMMATEUR, PAS AU GRAIN TABLE : sa cle de
merge est `(cloud_provider, consumer_id, period_start)` et elle ne porte aucune des
colonnes de `TABLE_KEY_COLUMNS`. Aucune purge n'y est donc possible -- il n'y a rien a
apparier. Elle herite du filtre par `table_daily`, dont elle agrege les lignes : ses
lignes sont donc justes des le prochain run pour la FENETRE recalculee, et gardent une
contribution d'ephemere pour les jours anterieurs a cette fenetre. Un `--full-refresh` est
le seul moyen de les corriger, et le contributeur est un compteur de requetes agrege, pas
une ligne de table visible en aval.

COUT ASSUME, ET CE QUI COUTE VRAIMENT. Chaque appel reconstruit l'agregat des operations
d'audit : 8 fois par run au total (5 purges, les 2 filtres des builders de `table_daily` et
`table_query_performance_daily`, celui du registre), la ou ce module en a ajoute 7. Ce scan-la
reste peu couteux -- `curated_dbx_uc_table_operations` est `system.access.audit` restreint
aux 3 actions DDL de `ACCESS_AUDIT_WRITE_ACTIONS`, pas la plus grosse source curated. Ce
qui domine est ailleurs : chaque purge est un MERGE qui scanne sa table CIBLE en entier,
sur des tables ecrites sans partitionnement ni liquid clustering -- sur `table_daily`,
c'est tout le fait, chaque jour.

Les cinq tables etant ecrites par cinq taches distinctes (donc cinq sessions Spark), rien
ne peut etre partage entre elles. Borner la fenetre de lecture n'est PAS une option : le
stock ecrit par les runs anterieurs sortirait de la borne et ne serait jamais purge. Si la
duree devient un probleme, la suite est de materialiser ces cles dans une table dediee, lue
par les cinq -- pas de rogner la definition. Cela fermerait du meme coup la fenetre ou
chaque purge recalcule l'ensemble a SON instant : un `deleteTable` qui atterrit en cours de
run est purge de certaines tables et pas des autres jusqu'au run suivant.

EXCLURE SUR UNE PREUVE, JAMAIS SUR UNE ABSENCE. Une cle absente du referentiel ne prouve
rien : c'est majoritairement un privilege manquant sur le principal d'ingestion (mesure
sur la warehouse de dev : des catalogues de production entiers, tres lus, sont dans ce
cas). D'ou les trois conditions cumulatives de `EPHEMERAL_KEYS_*`, aucune redondante.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pipelines.gold_dbx_usage.sql_helpers import EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pyspark.sql import SparkSession

_LOGGER = logging.getLogger(__name__)


__all__ = [
    "CREATED_EVENT_AT_EXPR",
    "DELETE_TABLE_ACTION",
    "EPHEMERAL_KEYS_CTE_NAME",
    "LAST_OPERATION_AT_EXPR",
    "LIVED_LONG_ENOUGH_PREDICATE",
    "TABLE_KEY_COLUMNS",
    "WAS_EPHEMERAL_PREDICATE",
    "ephemeral_keys_cte",
    "not_ephemeral_predicate",
    "purge_ephemeral_rows",
    "table_operations_cte",
]


# Grain commun aux cinq tables concernees : le registre et `table_governance` sont a ce
# grain exactement, les trois faits y ajoutent une date (et un consommateur pour
# `table_daily`). La purge apparie donc sur la cle de TABLE et retire toutes les lignes
# datees d'une meme cle.
TABLE_KEY_COLUMNS = ("cloud_provider", "catalog", "schema", "table_name")

EPHEMERAL_KEYS_CTE_NAME = "cles_ephemeres"

# Identifiant de table par `action_name`. `createTable` est la seule des 3 actions
# a ne pas porter `full_name_arg` ; `deleteTable` et `updateTables` le portent tous
# deux au format `catalog.schema.table`, d'ou leur regroupement en `ELSE` : la ligne
# de partage est bien « createTable vs le reste », pas les 3 actions separement.
# `get(split(...), i)` et non `[i]` : renvoie NULL sur une valeur mal formee au lieu
# de lever `INVALID_ARRAY_INDEX` en mode ANSI.
_TABLE_OPERATIONS_CATALOG_EXPR = (
    "CASE WHEN action_name = 'createTable' THEN request_params['catalog_name'] "
    "ELSE get(split(request_params['full_name_arg'], '\\\\.'), 0) END"
)
_TABLE_OPERATIONS_SCHEMA_EXPR = (
    "CASE WHEN action_name = 'createTable' THEN request_params['schema_name'] "
    "ELSE get(split(request_params['full_name_arg'], '\\\\.'), 1) END"
)
_TABLE_OPERATIONS_TABLE_NAME_EXPR = (
    "CASE WHEN action_name = 'createTable' THEN request_params['name'] "
    "ELSE get(split(request_params['full_name_arg'], '\\\\.'), 2) END"
)
# Predicat d'entree. Le `!=` est sans risque ici : `action_name` est une colonne
# d'evenement toujours peuplee, jamais NULL. Les 3 champs sont exiges pour
# `createTable`, pas seulement `name` : ils vont ensemble, et n'en exiger qu'un
# produirait un `catalog`/`schema` NULL silencieux au lieu d'une exclusion.
_TABLE_OPERATIONS_HAS_TABLE_NAME_PREDICATE = (
    "(action_name = 'createTable' AND request_params['catalog_name'] IS NOT NULL "
    "AND request_params['schema_name'] IS NOT NULL AND request_params['name'] IS NOT NULL) "
    "OR (action_name != 'createTable' AND request_params['full_name_arg'] IS NOT NULL)"
)

# Seule action d'audit qui ATTESTE une suppression. Nommee une fois : elle sert a la fois
# a fabriquer le squelette `deleted_only` du registre, a deriver `lifecycle_state` et a
# prouver l'ephemerite, et les trois doivent parler du meme evenement.
DELETE_TABLE_ACTION = "deleteTable"

# Naissance et dernier evenement vus par l'audit, ecrits UNE fois pour toutes les
# requetes : le builder du registre qui refuse d'ecrire une ephemere, les builders de
# faits qui refusent ses lignes datees, et les purges qui retirent celles deja ecrites
# doivent mesurer la MEME duree sur les MEMES bornes.
LAST_OPERATION_AT_EXPR = "MAX(event_time) AS last_operation_at"
CREATED_EVENT_AT_EXPR = (
    "MIN(CASE WHEN action_name = 'createTable' THEN event_time END) AS created_event_at"
)

# Duree de vie vue par l'AUDIT, en secondes : du premier `createTable` au dernier
# evenement connu. `MIN(createTable)` et non `MAX` : sur un nom reutilise, la duree
# obtenue couvre toute l'activite auditee, donc la plus longue des lectures possibles.
# L'erreur va toujours dans le sens « garder », jamais « supprimer a tort ».
_AUDITED_LIFETIME_SECONDS_EXPR = (
    "unix_timestamp(lo.last_operation_at) - unix_timestamp(lo.created_event_at)"
)

# Les deux faces du seuil, ecrites toutes les deux en POSITIF et strictement
# COMPLEMENTAIRES : leur reunion couvre toutes les lignes, leur intersection est vide.
#
# `LIVED_LONG_ENOUGH` decide qui obtient une ligne ; `WAS_EPHEMERAL` decide qui n'en
# obtient pas et perd celles deja ecrites. Une ligne qui satisferait les deux serait
# ecrite puis supprimee a chaque run ; une ligne qu'aucun ne satisfait serait un fantome
# definitif. D'ou l'`IS NULL` d'un cote et l'`IS NOT NULL` de l'autre, et non un simple
# `NOT (...)` : l'age INCONNU (un `createTable` sorti de la fenetre de retention d'audit)
# est garde des deux cotes, jamais d'action sur un doute.
LIVED_LONG_ENOUGH_PREDICATE = (
    "lo.created_event_at IS NULL\n"
    f"              OR {_AUDITED_LIFETIME_SECONDS_EXPR}\n"
    f"                 >= {EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS}"
)
WAS_EPHEMERAL_PREDICATE = (
    "lo.created_event_at IS NOT NULL\n"
    f"            AND {_AUDITED_LIFETIME_SECONDS_EXPR}\n"
    f"                < {EPHEMERAL_TABLE_MAX_LIFETIME_SECONDS}"
)


def table_operations_cte(
    table_operations_table: str,
    *,
    indent: str = "    ",
    extra_columns: Sequence[str] = (),
) -> str:
    """Les operations d'audit ramenees au grain `(cloud_provider, catalog, schema, table)`.

    Rendue ici plutot que recopiee : le registre en a besoin pour `last_operation` et
    `last_operation_by`, la definition de l'ephemerite pour les bornes de duree de vie.
    Une divergence d'extraction entre les deux ferait mesurer deux populations
    differentes sous le meme nom.

    Args:
        table_operations_table: nom qualifie de `curated_dbx_uc_table_operations`.
        indent: indentation des lignes produites, pour s'inserer dans un `WITH` existant.
        extra_columns: colonnes brutes a projeter en plus (le registre y ajoute
            `user_identity` pour `last_operation_by`). Elles ne participent ni au grain ni
            au predicat d'entree.
    """
    extra = "".join(f"\n{indent}    {column}," for column in extra_columns)
    return f"""{indent}SELECT
{indent}    cloud_provider,
{indent}    action_name,
{indent}    event_time,{extra}
{indent}    {_TABLE_OPERATIONS_CATALOG_EXPR} AS catalog,
{indent}    {_TABLE_OPERATIONS_SCHEMA_EXPR} AS schema,
{indent}    {_TABLE_OPERATIONS_TABLE_NAME_EXPR} AS table_name
{indent}FROM {table_operations_table}
{indent}WHERE {_TABLE_OPERATIONS_HAS_TABLE_NAME_PREDICATE}"""


def ephemeral_keys_cte(
    *,
    uc_tables_table: str,
    table_operations_table: str,
    cte_name: str = EPHEMERAL_KEYS_CTE_NAME,
) -> str:
    """La CTE des cles PROUVEES ephemeres, a inserer en tete d'un `WITH`.

    Trois conditions cumulatives, aucune redondante :

    - **absente du referentiel maintenant** (`LEFT ANTI JOIN`). Une cle presente dans
      `curated_dbx_uc_tables` (full load purge) existe au moment du run, quelle que soit
      son histoire d'audit : c'est ce qui protege un nom reutilise et une table recreee.
      La garantie vaut exactement la FRAICHEUR du miroir curated, pas plus.
    - **`deleteTable` comme derniere operation**. L'absence du referentiel vient
      majoritairement d'un privilege manquant sur le principal d'ingestion, elle ne
      prouve rien -- mesure sur la warehouse de dev : des catalogues de production
      entiers, tres lus, sont absents du referentiel sans etre supprimes pour autant.
    - **age CONNU et sous le seuil** (`WAS_EPHEMERAL_PREDICATE`). Une naissance sortie de
      la fenetre de retention d'audit ne permet pas de conclure : on garde.

    Le rendu ne se termine ni par une virgule ni par un point-virgule -- c'est a
    l'appelant de l'enchainer avec la CTE suivante.

    Args:
        uc_tables_table: nom qualifie de `curated_dbx_uc_tables` (le referentiel).
        table_operations_table: nom qualifie de `curated_dbx_uc_table_operations`.
        cte_name: nom de la CTE produite, a reprendre dans les predicats de l'appelant.
    """
    return f"""{cte_name}_referentiel AS (
        SELECT
            cloud_provider,
            table_catalog AS catalog,
            table_schema AS schema,
            table_name
        FROM {uc_tables_table}
    ),
    {cte_name}_operations AS (
{table_operations_cte(table_operations_table, indent="        ")}
    ),
    {cte_name}_derniere AS (
        SELECT
            cloud_provider,
            catalog,
            schema,
            table_name,
            MAX_BY(action_name, event_time) AS last_operation,
            {LAST_OPERATION_AT_EXPR},
            {CREATED_EVENT_AT_EXPR}
        FROM {cte_name}_operations
        GROUP BY cloud_provider, catalog, schema, table_name
    ),
    {cte_name} AS (
        SELECT lo.cloud_provider, lo.catalog, lo.schema, lo.table_name
        FROM {cte_name}_derniere lo
        LEFT ANTI JOIN {cte_name}_referentiel r
          ON r.cloud_provider = lo.cloud_provider AND r.catalog = lo.catalog
         AND r.schema = lo.schema AND r.table_name = lo.table_name
        WHERE lo.last_operation = '{DELETE_TABLE_ACTION}'
          AND (
            {WAS_EPHEMERAL_PREDICATE}
          )
    )"""


def not_ephemeral_predicate(
    alias: str,
    *,
    cte_name: str = EPHEMERAL_KEYS_CTE_NAME,
) -> str:
    """`NOT EXISTS (...)` sur la cle de table, a poser dans le `WHERE` d'un builder.

    En `NOT EXISTS` et non en `LEFT ANTI JOIN` : les builders de faits terminent sur une
    chaine de jointures deja longue, ou l'ajout d'un type de jointure supplementaire se
    lit mal et deplace la portee des alias. Spark reecrit les deux en anti-jointure.

    Comparaison par `=` colonne a colonne : un `catalog`/`schema` NULL (nom mal forme
    dans l'audit) n'apparie donc rien et la ligne est GARDEE. C'est le bon sens de
    l'erreur -- ne jamais retirer sur un doute.

    Args:
        alias: alias de la relation portant les colonnes de `TABLE_KEY_COLUMNS`.
        cte_name: nom de la CTE rendue par :func:`ephemeral_keys_cte`.
    """
    conditions = " AND ".join(f"e.{column} = {alias}.{column}" for column in TABLE_KEY_COLUMNS)
    return f"NOT EXISTS (SELECT 1 FROM {cte_name} e WHERE {conditions})"


_NUM_DELETED_ROWS_COLUMN = "num_deleted_rows"


def _deleted_row_count(merge_result: object) -> int | None:
    """Lignes supprimees rapportees par le MERGE, `None` si la metrique manque.

    La purge est la seule operation destructrice de cette couche gold : sans trace,
    personne ne saurait combien de lignes un run a retirees, ni ne verrait un pic. La
    metrique est LUE mais jamais exigee -- ce n'est pas un resultat metier, seulement une
    trace, et une session qui ne la publierait pas ne doit pas faire echouer la purge.
    D'ou la lecture par nom de colonne plutot qu'un `collect()[0][0]` positionnel : la
    liste des metriques d'un MERGE Delta depend de la version du runtime.
    """
    columns = getattr(merge_result, "columns", None)
    if not columns or _NUM_DELETED_ROWS_COLUMN not in columns:
        return None
    rows = merge_result.collect()  # type: ignore[attr-defined]
    if not rows:
        return None
    value = rows[0][columns.index(_NUM_DELETED_ROWS_COLUMN)]
    return None if value is None else int(value)


def purge_ephemeral_rows(
    spark: SparkSession,
    *,
    target_table: str,
    uc_tables_table: str,
    table_operations_table: str,
) -> None:
    """Retire de `target_table` les lignes des cles prouvees ephemeres.

    Complementaire du filtre a l'ecriture, et pas redondante avec lui : `merge_into_table`
    ne supprime JAMAIS de ligne cible, donc le filtre ne peut rien contre deux
    populations. Les lignes ecrites par les runs anterieurs au filtre, d'abord. Et
    surtout, pour le registre, la ligne `ACTIVE` d'une table qu'un run a vue VIVANTE
    entre son `createTable` et son `deleteTable` : celle-la est entree par le referentiel
    et non par la branche des supprimees, aucun filtre de duree de vie ne l'a vue passer.
    Elle resterait sinon un fantome `ACTIVE` pour une table qui n'existe plus.

    Appariement sur la cle de TABLE (`TABLE_KEY_COLUMNS`) et non sur la cle de merge de la
    cible : sur les faits, une cle ephemere doit perdre TOUTES ses lignes datees, pas
    celles d'un jour. Plusieurs lignes cible pour une ligne source est licite en MERGE ;
    c'est l'inverse qui leve `DELTA_MULTIPLE_SOURCE_ROW_MATCHING_TARGET_ROW_IN_MERGE`, et
    la source est ici un `GROUP BY` sur ces 4 memes colonnes, donc au plus une ligne par
    cle.

    Pourquoi pas l'`absent_row_delete_predicate` de `merge_into_table` : son
    `WHEN NOT MATCHED BY SOURCE ... THEN DELETE` retirerait toute cle absente de la
    source, donc AUSSI les vraies suppressions des que leur evenement d'audit quitte la
    fenetre de retention -- or leur survie est un choix explicite de la spec 027, et rien
    dans la cible ne distingue « sortie de retention » de « ephemere ». On cible une
    preuve, pas une absence.

    Idempotente et sans oscillation : le prochain run ne reecrit pas ces lignes, le filtre
    a l'ecriture les refuse (`not_ephemeral_predicate`), et les deux predicats sont
    strictement complementaires.

    Args:
        spark: session Spark.
        target_table: nom qualifie de la table gold a purger.
        uc_tables_table: nom qualifie de `curated_dbx_uc_tables`.
        table_operations_table: nom qualifie de `curated_dbx_uc_table_operations`.
    """
    keys = ephemeral_keys_cte(
        uc_tables_table=uc_tables_table,
        table_operations_table=table_operations_table,
    )
    on_clause = "\n     AND ".join(
        f"cible.{column} = ephemere.{column}" for column in TABLE_KEY_COLUMNS
    )
    projection = ", ".join(f"{EPHEMERAL_KEYS_CTE_NAME}.{column}" for column in TABLE_KEY_COLUMNS)
    query = f"""
    MERGE INTO {target_table} AS cible
    USING (
        WITH {keys}
        SELECT {projection} FROM {EPHEMERAL_KEYS_CTE_NAME}
    ) AS ephemere
      ON {on_clause}
    WHEN MATCHED THEN DELETE
    """
    deleted = _deleted_row_count(spark.sql(query))
    _LOGGER.info(
        "%s : purge des tables ephemeres -> %s ligne(s) retiree(s).",
        target_table,
        "compte non rapporte" if deleted is None else deleted,
    )
