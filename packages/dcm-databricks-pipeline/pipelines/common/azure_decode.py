"""Decodage fidele des lignes du SQL connector Azure en DataFrame Spark.

Reconstruit un DataFrame typé a partir des lignes renvoyees par le
`databricks-sql-connector`, en preservant les types source (schema explicite) et
en normalisant les colonnes complexes (map/struct/array) que le connector ne
renvoie pas au format attendu par Arrow. Aucune valeur n'est fabriquee : un NULL
source reste `None` (FR-011).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyspark.sql import DataFrame, SparkSession
    from pyspark.sql.types import StructType

logger = logging.getLogger(__name__)


def reference_schema(
    spark: SparkSession,
    source_table: str,
    columns: list[str],
) -> StructType:
    """Schema Spark explicite pour reconstruire les lignes Azure fidelement.

    Sans schema explicite, `createDataFrame` infere les types depuis les valeurs
    Python. Si un lot contient une colonne entierement NULL, l'inference produit
    un `NullType` non resoluble ⇒ `PySparkValueError: CANNOT_DETERMINE_TYPE`.

    On derive donc le type de chaque colonne depuis la MEME table lue localement
    cote AWS, quand elle y est visible (cas des tables `system.*` : meme schema
    Databricks sur les deux clouds). Certaines sources Azure (ex. catalogs
    cross-tenant dedies type `onedatalake-ppd-internal`.egress_firewall, utilises
    par `reference_lz`) n'existent QUE cote Azure et sont absentes du metastore
    Unity Catalog local ⇒ `spark.table(...)` leve `TABLE_OR_VIEW_NOT_FOUND`. On
    intercepte ce cas et on retombe sur un dict de types vide : chaque colonne
    utilise alors le fallback `StringType` ci-dessous (deja prevu pour une
    colonne absente du schema local), jamais de NullType, donc jamais de
    CANNOT_DETERMINE_TYPE.
    """
    from pyspark.errors import PySparkException
    from pyspark.sql.types import StringType, StructField, StructType

    try:
        source_types = {field.name: field.dataType for field in spark.table(source_table).schema}
    except PySparkException:
        logger.warning(
            "reference_schema.source_table_not_found_locally source_table=%s "
            "(source Azure sans equivalent local ⇒ fallback StringType)",
            source_table,
        )
        source_types = {}
    return StructType(
        [StructField(name, source_types.get(name, StringType()), nullable=True) for name in columns]
    )


def rows_to_dataframe(
    spark: SparkSession,
    columns: list[str],
    rows: list[Any],
    schema: StructType | None = None,
) -> DataFrame | None:
    """Convertit des lignes du SQL connector en DataFrame Spark (fidele source).

    Aucune transformation : on reconstruit une ligne par enregistrement avec les
    memes colonnes que la source. Retourne None si la source est vide (rien a
    merger).

    Quand `schema` est fourni, les lignes sont passees positionnellement (dans
    l'ordre de `columns`) avec ce schema explicite : cela evite l'inference de
    type et le `CANNOT_DETERMINE_TYPE` sur les lots ou une colonne est
    entierement NULL. Les colonnes complexes (map/struct/array) sont renvoyees
    par le SQL connector sous forme de chaine JSON ; on les redecode en objets
    Python natifs (`_coerce_complex_values`) pour qu'elles correspondent au type
    Delta cible. La coercition est recursive : les `MapType` imbriques dans un
    `StructType` (ex. `query_history.metrics`) sont normalises en `dict`. Sans
    `schema`, on retombe sur l'inference par dictionnaires.
    """
    if not rows:
        return None
    if schema is not None:
        data = _coerce_complex_values(rows, schema)
        return spark.createDataFrame(data, schema)
    records = [dict(zip(columns, row, strict=False)) for row in rows]
    return spark.createDataFrame(records)


def _coerce_complex_values(rows: list[Any], schema: StructType) -> list[tuple[Any, ...]]:
    """Normalise les colonnes complexes (map/struct/array) renvoyees par le connector.

    Le `databricks-sql-connector` (arrow) ne renvoie PAS ces colonnes dans le
    format attendu par `createDataFrame(..., schema)` (fait verifie sur
    `system.billing.usage`) :
      - `MapType`     ⇒ **liste de tuples** `[(k, v), ...]` (ex. `custom_tags`) ;
      - `StructType`  ⇒ `dict` (deja au bon format) ;
      - valeur NULL   ⇒ `None` ou chaine vide selon la colonne.

    Or le convertisseur local->Arrow exige un `dict` pour un `MapType`/`StructType`
    (sinon `AssertionError: isinstance(value, dict)` dans `convert_map`) et une
    `list` pour un `ArrayType`. On convertit donc chaque valeur selon le type
    DECLARE de la colonne (`_coerce_complex_value`), en particulier la liste de
    tuples d'un map -> `dict`. Les colonnes scalaires (datetime, Decimal, str...)
    sont laissees intactes ; un NULL reste `None` (jamais de valeur fabriquee —
    FR-011).
    """
    from pyspark.sql.types import ArrayType, MapType
    from pyspark.sql.types import StructType as _StructType

    complex_fields = [
        (index, field.dataType)
        for index, field in enumerate(schema.fields)
        if isinstance(field.dataType, (MapType, ArrayType, _StructType))
    ]
    if not complex_fields:
        return [tuple(row) for row in rows]
    coerced: list[tuple[Any, ...]] = []
    for row in rows:
        values = list(row)
        for index, data_type in complex_fields:
            values[index] = _coerce_complex_value(values[index], data_type)
        coerced.append(tuple(values))
    return coerced


def _coerce_complex_value(value: Any, data_type: Any) -> Any:  # noqa: ANN401
    """Normalise une valeur de colonne complexe selon son type Spark declare.

    Regles (alignees sur ce que renvoie reellement le SQL connector) :
      - `None` ⇒ `None` ;
      - chaine vide / blancs ⇒ `None` (complexe NULL cote source) ;
      - chaine JSON non vide ⇒ objet Python decode (`json.loads`) ;
      - `MapType` : liste de paires `[(k, v), ...]` ⇒ `dict` ;
      - `ArrayType` : `numpy.ndarray` ⇒ `list` native (`.tolist()`) ;
      - `StructType` : recursion sur chaque sous-champ du dict pour normaliser
        les maps/arrays imbriques (ex. `query_history.metrics` contient des
        sous-champs MapType renvoyes comme listes de tuples).
    Aucune valeur n'est fabriquee : un NULL source reste `None` (FR-011).
    """
    from pyspark.sql.types import ArrayType, MapType
    from pyspark.sql.types import StructType as _StructType

    # Ne toucher QUE les types complexes : un sous-champ scalaire d'un struct
    # (ex. texte libre) ne doit pas passer par json.loads (JSONDecodeError sur du
    # texte non-JSON). Les scalaires sont renvoyes intacts.
    if value is None or not isinstance(data_type, (MapType, ArrayType, _StructType)):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return None
        value = json.loads(stripped)
    if isinstance(data_type, MapType):
        if isinstance(value, list):
            value = dict(value)
        if isinstance(value, dict):
            # Descend dans les valeurs du map : valueType peut être un StructType
            # contenant des ArrayType (ex. query_history.metrics → struct → array).
            return {k: _coerce_complex_value(v, data_type.valueType) for k, v in value.items()}
        return value
    if isinstance(data_type, ArrayType):
        if not isinstance(value, list):
            value = value.tolist() if hasattr(value, "tolist") else list(value)
        # Descend dans les éléments : elementType peut être un StructType/MapType imbriqué.
        return [_coerce_complex_value(elem, data_type.elementType) for elem in value]
    if isinstance(data_type, _StructType) and isinstance(value, dict):
        for field in data_type.fields:
            if field.name in value:
                value[field.name] = _coerce_complex_value(value[field.name], field.dataType)
    return value
