"""Fixtures et fakes partages des tests d'ingestion (socle + plugin FinOps).

`pyspark.sql.functions` exige une JVM active : on remplace donc le namespace `F`
des modules qui l'utilisent (`transforms`, `readers`) via la fixture
`fake_functions`, et on manipule des DataFrames/Spark factices legers exposes par
la fixture `fakes`.

Ce module est un `conftest.py` : pytest le charge PAR CHEMIN (pas par import),
il est donc visible de tous les sous-dossiers de tests (`common/`, `finops/`)
sans creer de dependance a un module `tests._fakes` partage — ce qui eviterait
l'ambiguite de resolution du package `tests` entre les differents packages du
monorepo (chaque package a son propre `tests/`).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

import pipelines.common.readers as readers
import pipelines.common.transforms as transforms


class FakeDataFrame:
    """DataFrame factice qui enregistre les appels de colonnes/union."""

    def __init__(
        self,
        name: str = "df",
        columns: list[str] | None = None,
        row_count: int = 0,
        rows: list[Any] | None = None,
    ) -> None:
        self.name = name
        self.columns = list(columns or [])
        self.row_count = row_count
        self.added_columns: list[tuple[str, Any]] = []
        self.renamed_columns: list[tuple[str, str]] = []
        self.dropped_columns: list[str] = []
        self.union_calls: list[tuple[FakeDataFrame, bool]] = []
        self.temp_views: list[str] = []
        self.saved_as: list[str] = []
        self.partitioned_by: list[str] = []
        self.write_options: dict[str, str] = {}
        self.write_modes: list[str] = []
        self.filters: list[Any] = []
        self.selected_columns: list[str] | None = None
        self.select_exprs: list[tuple[str, ...]] = []
        self.distinct_called = False
        # Lignes rendues par `collect()` : une liste de sequences indexables,
        # comme les `Row` de Spark (ex. `[[date(2026, 7, 15)]]` pour un agregat
        # d'une seule colonne). `[]` = sortie vide.
        self.rows: list[Any] = list(rows or [])

    def withColumn(self, col_name: str, value: object) -> FakeDataFrame:
        self.added_columns.append((col_name, value))
        if col_name not in self.columns:
            self.columns.append(col_name)
        return self

    def withColumnRenamed(self, existing: str, new: str) -> FakeDataFrame:
        self.renamed_columns.append((existing, new))
        self.columns = [new if c == existing else c for c in self.columns]
        return self

    def drop(self, *cols: str) -> FakeDataFrame:
        self.dropped_columns.extend(cols)
        self.columns = [c for c in self.columns if c not in cols]
        return self

    def count(self) -> int:
        return self.row_count

    def isEmpty(self) -> bool:
        """Vide au sens de Spark : ni `row_count` ni `rows` declares.

        Un test qui verifie une SUPPRESSION de lignes absentes doit donc
        declarer une sortie non vide (`row_count=1`) : la suppression est
        justement desactivee quand le builder ne produit rien (cf.
        `pipelines.gold_dbx_compute.entrypoint._absent_row_delete_predicate`).
        """
        return self.row_count == 0 and not self.rows

    def filter(self, condition: object) -> FakeDataFrame:
        self.filters.append(condition)
        return self

    def select(self, *columns: str) -> FakeDataFrame:
        self.selected_columns = list(columns)
        return self

    def selectExpr(self, *exprs: str) -> FakeDataFrame:
        self.select_exprs.append(exprs)
        return self

    def collect(self) -> list[Any]:
        return self.rows

    def distinct(self) -> FakeDataFrame:
        self.distinct_called = True
        return self

    def unionByName(self, other: FakeDataFrame, allowMissingColumns: bool = False) -> FakeDataFrame:
        self.union_calls.append((other, allowMissingColumns))
        return self

    def dropDuplicates(self, subset: list[str] | None = None) -> FakeDataFrame:
        self.deduplicated_on = subset
        return self

    def createOrReplaceTempView(self, view: str) -> None:
        self.temp_views.append(view)

    @property
    def write(self) -> FakeWriter:
        return FakeWriter(self)


class FakeColumn:
    """Colonne factice : enregistre l'expression construite, sans JVM/calcul reel.

    Chaque operation (`isNotNull`, `asc_nulls_last`, `&`, `!=`, `==`, `>=`,
    `.over`) renvoie un nouveau `FakeColumn` dont `.expr` est un tuple structure
    (ex. `("isNotNull", ("col", "workspace_id"))`), inspectable directement
    dans les tests (via `.expr`, jamais via `==` entre deux `FakeColumn` : cet
    operateur est lui-meme surcharge pour construire une expression, pas pour
    comparer -- comme la vraie API `Column` de PySpark).
    """

    def __init__(self, expr: object) -> None:
        self.expr = expr

    def _combine(self, op: str, other: object = None) -> FakeColumn:
        if other is None:
            return FakeColumn((op, self.expr))
        other_expr = other.expr if isinstance(other, FakeColumn) else other
        return FakeColumn((op, self.expr, other_expr))

    def isNotNull(self) -> FakeColumn:
        return self._combine("isNotNull")

    def asc_nulls_last(self) -> FakeColumn:
        return self._combine("asc_nulls_last")

    def over(self, window: object) -> FakeColumn:
        return self._combine("over", window)

    def __and__(self, other: object) -> FakeColumn:
        return self._combine("and", other)

    def __ne__(self, other: object) -> FakeColumn:  # type: ignore[override]
        return self._combine("ne", other)

    def __eq__(self, other: object) -> FakeColumn:  # type: ignore[override]
        return self._combine("eq", other)

    def __ge__(self, other: object) -> FakeColumn:
        return self._combine("ge", other)

    def __repr__(self) -> str:
        return f"FakeColumn({self.expr!r})"


class FakeWindowSpec:
    """Window spec factice : conserve les colonnes de partition/tri passees."""

    def __init__(
        self,
        partition_by: tuple[object, ...] = (),
        order_by: tuple[object, ...] = (),
    ) -> None:
        self.partition_by = partition_by
        self.order_by = order_by

    def partitionBy(self, *cols: object) -> FakeWindowSpec:
        return FakeWindowSpec(partition_by=cols, order_by=self.order_by)

    def orderBy(self, *cols: object) -> FakeWindowSpec:
        return FakeWindowSpec(partition_by=self.partition_by, order_by=cols)


class FakeWindow:
    """Remplace `pyspark.sql.Window` (pas d'appel JVM en test)."""

    @staticmethod
    def partitionBy(*cols: object) -> FakeWindowSpec:
        return FakeWindowSpec().partitionBy(*cols)


class FakeWriter:
    def __init__(self, df: FakeDataFrame) -> None:
        self._df = df
        self._format = ""

    def format(self, fmt: str) -> FakeWriter:
        self._format = fmt
        return self

    def option(self, key: str, value: str) -> FakeWriter:
        self._df.write_options[key] = value
        return self

    def partitionBy(self, *cols: str) -> FakeWriter:
        self._df.partitioned_by = list(cols)
        return self

    def mode(self, mode: str) -> FakeWriter:
        self._df.write_modes.append(mode)
        return self

    def saveAsTable(self, table: str) -> None:
        self._df.saved_as.append(table)


class FakeCatalog:
    def __init__(self, existing: set[str]) -> None:
        self._existing = existing

    def tableExists(self, table: str) -> bool:
        return table in self._existing


class FakeSpark:
    def __init__(
        self,
        existing_tables: set[str] | None = None,
        sql_result: object | None = None,
        local_tables: dict[str, object] | None = None,
    ) -> None:
        self.catalog = FakeCatalog(existing_tables or set())
        self.sql_calls: list[str] = []
        self.read = MagicMock()
        self.created_dataframes: list[list[dict[str, Any]]] = []
        self.created_schemas: list[object] = []
        self._sql_result = sql_result
        self._local_tables = local_tables or {}

    def sql(self, statement: str) -> object:
        """Simule `spark.sql(...)`.

        `sql_result` (passe au constructeur) : soit un objet UNIQUE renvoye a
        chaque appel (comportement historique, ex. la seule requete du MERGE
        de suppression) ; soit une LISTE consommee sequentiellement (un
        resultat different par appel, dans l'ordre — utilise par
        `purge_absent_rows` qui emet desormais 3 requetes COUNT independantes
        au lieu d'une requete combinee, pour eviter une collision d'exprId
        Catalyst, cf. `pipelines.common.purge._count_rows_to_delete_sql`).
        Liste epuisee (ex. l'appel du `MERGE ... DELETE` qui suit les 3
        comptages) : renvoie `None`, sans faire echouer le test — ces appels
        ulterieurs n'utilisent pas la valeur de retour.
        """
        self.sql_calls.append(statement)
        if isinstance(self._sql_result, list):
            return self._sql_result.pop(0) if self._sql_result else None
        return self._sql_result

    def table(self, name: str) -> object:
        """Simule `spark.table(name)` : leve `AnalysisException` si absente.

        `local_tables` (passe au constructeur) simule les tables visibles depuis
        le metastore Unity Catalog LOCAL uniquement (ex. `system.*`, presentes
        sur tous les clouds). Une table absente reproduit fidelement le
        `TABLE_OR_VIEW_NOT_FOUND` reel pour les sources Azure-only (ex.
        `reference_lz`) qui n'existent pas cote metastore local.
        """
        from pyspark.errors import AnalysisException

        if name not in self._local_tables:
            raise AnalysisException(f"[TABLE_OR_VIEW_NOT_FOUND] {name} is not found")
        return self._local_tables[name]

    def createDataFrame(self, data: list[dict[str, Any]], schema: object = None) -> FakeDataFrame:
        self.created_dataframes.append(data)
        self.created_schemas.append(schema)
        return FakeDataFrame("created")


def strip_sql_comments(query: str) -> str:
    """Retire les lignes de commentaire `--` d'un SQL rendu.

    Les builders de ce paquet sont testes sur le texte SQL genere (pas de vraie
    `SparkSession`, cf. docstring de ce module). Une assertion d'ABSENCE -- « ce
    predicat ne doit pas etre la » -- porte donc aussi sur les commentaires, ou le
    predicat cherche peut apparaitre alors qu'il ne s'execute pas. Ce helper la
    restreint au SQL.
    """
    return "\n".join(
        line for line in query.splitlines() if not line.lstrip().startswith("--")
    )


def gap_scan_row(
    *,
    last_day: object = None,
    first_missing_day: object = None,
    first_unsettled_day: object = None,
) -> SimpleNamespace:
    """Fake du resultat de `pipelines.common.incremental.gap_scan_sql` (une ligne).

    Le scan de couverture rend 3 scalaires, consommes via `.collect()[0][...]` :
    `FakeDataFrame` n'expose pas `collect`, d'ou cet objet dedie. Tous les champs
    par defaut a `None` = couverture sans trou ni jour non stabilise, et aucun
    jour ecrit -- l'appelant precise ce dont son cas a besoin.

    Partage par les deux domaines gold (`gold_dbx_compute`, `gold_dbx_usage`), qui
    appellent le meme helper et lisent donc la meme forme de ligne.
    """
    row = {
        "last_day": last_day,
        "first_missing_day": first_missing_day,
        "first_unsettled_day": first_unsettled_day,
    }
    return SimpleNamespace(collect=lambda: [row])


@pytest.fixture
def fakes() -> SimpleNamespace:
    """Expose les classes factices (Spark/DataFrame) aux tests sans import direct.

    Retourne un namespace de classes (pas d'instances) : les tests les
    instancient a la demande, ex. `fakes.Spark(existing_tables={...})`,
    `fakes.DataFrame("aws")`.
    """
    return SimpleNamespace(
        DataFrame=FakeDataFrame,
        Writer=FakeWriter,
        Catalog=FakeCatalog,
        Spark=FakeSpark,
        Column=FakeColumn,
        Window=FakeWindow,
        WindowSpec=FakeWindowSpec,
    )


@pytest.fixture
def fake_functions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remplace `F`/`Window` des modules `transforms`/`readers` (pas de JVM).

    `col` renvoie un `FakeColumn` (chainable : `.isNotNull()`, `.asc_nulls_last()`,
    `&`, `!=`, `==`, `.over(...)`) requis par `dedupe_by_key`/`filter_null_or_empty_key`.
    `lit`/`to_timestamp`/`expr`/`coalesce` restent des tuples simples (inchange,
    aucun test existant ne chaine d'appel dessus).
    """
    stub = SimpleNamespace(
        lit=lambda value: ("lit", value),
        to_timestamp=lambda value: ("to_timestamp", value),
        col=lambda value: FakeColumn(("col", value)),
        expr=lambda value: ("expr", value),
        coalesce=lambda *cols: ("coalesce", cols),
        trim=lambda column: FakeColumn(
            ("trim", column.expr if isinstance(column, FakeColumn) else column)
        ),
        row_number=lambda: FakeColumn(("row_number",)),
    )
    monkeypatch.setattr(transforms, "F", stub)
    monkeypatch.setattr(readers, "F", stub)
    monkeypatch.setattr(transforms, "Window", FakeWindow)
