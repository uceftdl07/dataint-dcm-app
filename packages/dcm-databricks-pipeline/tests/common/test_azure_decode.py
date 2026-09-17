"""Tests de `pipelines.common.azure_decode` (reconstruction fidele des lignes)."""

from __future__ import annotations

from types import SimpleNamespace

from pyspark.sql.types import LongType, MapType, StringType, StructField, StructType

import pipelines.common.azure_decode as azure_decode


def test_rows_to_dataframe_builds_records(fakes: SimpleNamespace) -> None:
    spark = fakes.Spark()
    columns = ["sku_name", "currency_code"]
    rows = [("SKU_A", "USD"), ("SKU_B", "EUR")]

    result = azure_decode.rows_to_dataframe(spark, columns, rows)

    assert result is not None
    assert spark.created_dataframes == [
        [
            {"sku_name": "SKU_A", "currency_code": "USD"},
            {"sku_name": "SKU_B", "currency_code": "EUR"},
        ]
    ]


def test_rows_to_dataframe_uses_schema_and_coerces_complex_json(fakes: SimpleNamespace) -> None:
    """Schema explicite : lignes positionnelles + colonnes complexes JSON->natif."""
    spark = fakes.Spark()
    columns = ["sku_name", "custom_tags"]
    rows = [("SKU_A", None), ("SKU_B", '{"team": "dcm"}')]
    schema = StructType(
        [
            StructField("sku_name", StringType(), nullable=True),
            StructField("custom_tags", MapType(StringType(), StringType()), nullable=True),
        ]
    )

    result = azure_decode.rows_to_dataframe(spark, columns, rows, schema)

    assert result is not None
    assert spark.created_dataframes == [[("SKU_A", None), ("SKU_B", {"team": "dcm"})]]
    assert spark.created_schemas == [schema]


def test_rows_to_dataframe_maps_empty_complex_string_to_none(fakes: SimpleNamespace) -> None:
    """Colonne complexe renvoyee en chaine vide/blancs ⇒ None (pas d'AssertionError).

    Le SQL connector renvoie parfois un map/struct/array NULL sous forme de
    chaine vide. Le convertisseur Arrow exige un dict/list ou None : une chaine
    vide declenche `AssertionError: isinstance(value, dict)`. On verifie donc que
    `""` (et les blancs) sont normalises en None.
    """
    spark = fakes.Spark()
    columns = ["sku_name", "custom_tags"]
    rows = [("SKU_A", ""), ("SKU_B", "   "), ("SKU_C", '{"team": "dcm"}')]
    schema = StructType(
        [
            StructField("sku_name", StringType(), nullable=True),
            StructField("custom_tags", MapType(StringType(), StringType()), nullable=True),
        ]
    )

    result = azure_decode.rows_to_dataframe(spark, columns, rows, schema)

    assert result is not None
    assert spark.created_dataframes == [
        [("SKU_A", None), ("SKU_B", None), ("SKU_C", {"team": "dcm"})]
    ]


def test_rows_to_dataframe_maps_list_of_tuples_to_dict(fakes: SimpleNamespace) -> None:
    """MapType renvoye en liste de paires par le SQL connector ⇒ dict.

    Fait verifie sur `system.billing.usage` : le `databricks-sql-connector`
    renvoie les colonnes `MAP<...>` (ex. `custom_tags`) sous forme de liste de
    tuples `[(k, v), ...]`, pas de dict. Le convertisseur Arrow exige un dict
    (`convert_map` ⇒ `AssertionError` sur une liste). On verifie la conversion.
    """
    spark = fakes.Spark()
    columns = ["sku_name", "custom_tags"]
    rows = [("SKU_A", [("Environment", "NonProduction"), ("AppName", "DCM")])]
    schema = StructType(
        [
            StructField("sku_name", StringType(), nullable=True),
            StructField("custom_tags", MapType(StringType(), StringType()), nullable=True),
        ]
    )

    result = azure_decode.rows_to_dataframe(spark, columns, rows, schema)

    assert result is not None
    assert spark.created_dataframes == [
        [("SKU_A", {"Environment": "NonProduction", "AppName": "DCM"})]
    ]


def test_rows_to_dataframe_coerces_map_nested_in_struct(fakes: SimpleNamespace) -> None:
    """StructType contenant un MapType : map imbriquee normalisee en dict (recursion).

    Modelise `system.query.history` : la colonne `metrics` est un `StructType`
    dont les sous-champs sont des maps. Le SQL connector les renvoie en listes de
    tuples dans le dict du struct ⇒ `AssertionError: isinstance(value, dict)` dans
    `convert_map`. La recursion StructType de `_coerce_complex_value` corrige.
    """
    spark = fakes.Spark()
    columns = ["statement_id", "metrics"]
    metrics_struct = StructType(
        [
            StructField("compilation_time_ms", LongType(), nullable=True),
            StructField("task_parallelism", MapType(StringType(), LongType()), nullable=True),
        ]
    )
    schema = StructType(
        [
            StructField("statement_id", StringType(), nullable=True),
            StructField("metrics", metrics_struct, nullable=True),
        ]
    )
    # Le connecteur retourne le struct comme dict mais son sous-champ MapType
    # comme liste de tuples (comportement observé sur query_history).
    rows = [
        ("stmt-1", {"compilation_time_ms": 42, "task_parallelism": [("slot_0", 4), ("slot_1", 2)]}),
        ("stmt-2", None),
    ]

    result = azure_decode.rows_to_dataframe(spark, columns, rows, schema)

    assert result is not None
    assert spark.created_dataframes == [
        [
            ("stmt-1", {"compilation_time_ms": 42, "task_parallelism": {"slot_0": 4, "slot_1": 2}}),
            ("stmt-2", None),
        ]
    ]


def test_rows_to_dataframe_preserves_scalar_struct_subfield(fakes: SimpleNamespace) -> None:
    """Sous-champ scalaire (texte libre) d'un struct : laisse intact (pas de json.loads).

    Regression : la recursion StructType passait tous les sous-champs par
    `_coerce_complex_value`, y compris les scalaires, ce qui tentait `json.loads`
    sur du texte non-JSON (ex. un `error_message` dans un struct) et levait
    `JSONDecodeError`. Seuls les types complexes doivent etre decodes.
    """
    spark = fakes.Spark()
    columns = ["statement_id", "status"]
    status_struct = StructType(
        [
            StructField("state", StringType(), nullable=True),
            StructField("error_message", StringType(), nullable=True),
        ]
    )
    schema = StructType(
        [
            StructField("statement_id", StringType(), nullable=True),
            StructField("status", status_struct, nullable=True),
        ]
    )
    # error_message contient du texte libre non-JSON qui ne doit pas etre decode.
    rows = [("stmt-1", {"state": "FAILED", "error_message": "table not found: foo"})]

    result = azure_decode.rows_to_dataframe(spark, columns, rows, schema)

    assert result is not None
    assert spark.created_dataframes == [
        [("stmt-1", {"state": "FAILED", "error_message": "table not found: foo"})]
    ]


def test_rows_to_dataframe_returns_none_when_empty(fakes: SimpleNamespace) -> None:
    spark = fakes.Spark()

    assert azure_decode.rows_to_dataframe(spark, ["sku_name"], []) is None
    assert spark.created_dataframes == []


class _FakeNdarray:
    """Stub minimal d'un `numpy.ndarray` : expose `.tolist()` (retour arrow connector)."""

    def __init__(self, values: list[object]) -> None:
        self._values = values

    def tolist(self) -> list[object]:
        return list(self._values)


def test_rows_to_dataframe_coerces_array_ndarray_to_list(fakes: SimpleNamespace) -> None:
    """ArrayType renvoye en ndarray par le connector (arrow) ⇒ list native.

    Verifie sur `system.compute.clusters` : le `databricks-sql-connector` renvoie
    les colonnes `ARRAY<...>` (ex. `init_scripts`, `ssh_public_keys`) sous forme
    de `numpy.ndarray`, pas de `list`. Le convertisseur Arrow exige une `list`
    (`convert_array` ⇒ `AssertionError` sur un ndarray). On verifie la conversion
    via `.tolist()` ; une liste deja decodee (JSON) reste intacte ; NULL -> None.
    """
    from pyspark.sql.types import ArrayType

    spark = fakes.Spark()
    columns = ["cluster_id", "ssh_public_keys"]
    rows = [
        ("c-1", _FakeNdarray(["key-a", "key-b"])),
        ("c-2", '["key-c"]'),
        ("c-3", None),
    ]
    schema = StructType(
        [
            StructField("cluster_id", StringType(), nullable=True),
            StructField("ssh_public_keys", ArrayType(StringType()), nullable=True),
        ]
    )

    result = azure_decode.rows_to_dataframe(spark, columns, rows, schema)

    assert result is not None
    assert spark.created_dataframes == [
        [("c-1", ["key-a", "key-b"]), ("c-2", ["key-c"]), ("c-3", None)]
    ]


def test_rows_to_dataframe_recurses_into_map_value_struct_array(fakes: SimpleNamespace) -> None:
    """MapType(str, StructType(ArrayType)) : le connector renvoie les valeurs du map
    sous forme de dict dont les champs ArrayType sont des tuples (non-list).
    Sans récursion dans valueType, Arrow lève AssertionError dans convert_array.
    Réplique le pattern query_history.metrics → struct → map → struct → array.
    """
    from pyspark.sql.types import ArrayType

    spark = fakes.Spark()
    columns = ["query_id", "metrics"]
    inner_struct = StructType(
        [StructField("items", ArrayType(StringType()), nullable=True)]
    )
    schema = StructType(
        [
            StructField("query_id", StringType(), nullable=True),
            StructField("metrics", MapType(StringType(), inner_struct), nullable=True),
        ]
    )
    # Le SQL connector renvoie les valeurs du map comme liste de paires ;
    # le champ ArrayType interne est renvoyé en tuple (non-list) par le connector.
    rows = [("q-1", [("k1", {"items": ("a", "b")})])]

    result = azure_decode.rows_to_dataframe(spark, columns, rows, schema)

    assert result is not None
    assert spark.created_dataframes == [
        [("q-1", {"k1": {"items": ["a", "b"]}})]
    ]


def test_reference_schema_uses_local_table_types_when_table_mirrored(
    fakes: SimpleNamespace,
) -> None:
    """Table source visible localement (ex. `system.*`) : types repris tels quels."""
    local_schema = StructType(
        [
            StructField("sku_name", StringType(), nullable=True),
            StructField("list_price", LongType(), nullable=True),
        ]
    )
    spark = fakes.Spark(
        local_tables={"system.billing.list_prices": SimpleNamespace(schema=local_schema)}
    )

    result = azure_decode.reference_schema(
        spark, "system.billing.list_prices", ["sku_name", "list_price"]
    )

    assert result == local_schema


def test_reference_schema_falls_back_to_string_when_source_table_not_found_locally(
    fakes: SimpleNamespace,
) -> None:
    """Source Azure-only (ex. `reference_lz`) absente du metastore local :

    `spark.table(...)` leve `AnalysisException` (`TABLE_OR_VIEW_NOT_FOUND`) au
    lieu de crasher, `reference_schema` doit retomber sur `StringType` pour
    toutes les colonnes (regression du bug production T014 : le catalog
    cross-tenant `onedatalake-ppd-internal`.egress_firewall n'existe que cote
    Azure, contrairement aux tables `system.*`).
    """
    spark = fakes.Spark(local_tables={})  # aucune table visible localement

    result = azure_decode.reference_schema(
        spark,
        "`onedatalake-ppd-internal`.`egress_firewall`.`workspace_inventory`",
        ["workspace_id", "workspace_name"],
    )

    assert result == StructType(
        [
            StructField("workspace_id", StringType(), nullable=True),
            StructField("workspace_name", StringType(), nullable=True),
        ]
    )
