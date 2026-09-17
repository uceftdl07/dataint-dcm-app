"""Fixtures partagees des tests de `pipelines.gold_dbx_workflow`.

Meme strategie que l'ancienne suite DLT (`tests/test_dlt_workflow.py`,
migration T002/013-workflow-sys-tables) : le runtime pyspark/JVM n'est pas
disponible en test unitaire, `pyspark.sql.functions`/`pyspark.sql.window.Window`
sont donc remplaces par un stub universel chainable (`_Any`) qui laisse
n'importe quelle expression Column/DataFrame s'executer de bout en bout sans
JVM. Les assertions portent sur les tables LUES (`spark.read.table(...)`), pas
sur des resultats de calcul concrets -- exactement ce qu'il faut verifier ici
(cf. contrainte source du domaine, `pipelines/gold_dbx_workflow/__init__.py`) :
que les builders ne lisent JAMAIS `curated_dbx_workflow_runs`/
`curated_dbx_workflow_task_runs` (collecteur JSON), uniquement
`curated_dbx_lakeflow_*` (system tables) + `dim_dbx_workspace`.

Difference cle avec l'ancienne suite DLT : les fonctions de ce plugin recoivent
`spark` en PARAMETRE explicite (pas de global de module injecte par le runtime
DLT) -- pas besoin de `mod.spark = spark_stub`, un stub est passe directement
en argument de chaque appel.
"""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace

import pytest


class _Any:
    """Mock chainable universel (DataFrame/Column) — cf. docstring module."""

    def __init__(self, tag: str = "any") -> None:
        self._tag = tag

    def __getattr__(self, _name: str):  # type: ignore[no-untyped-def]
        return lambda *a, **k: self

    def __call__(self, *a, **k):  # type: ignore[no-untyped-def]
        return self

    def __getitem__(self, _key):  # type: ignore[no-untyped-def]
        return self

    def _op(self, *_a, **_k):  # type: ignore[no-untyped-def]
        return self

    __eq__ = _op  # type: ignore[assignment]
    __ne__ = _op  # type: ignore[assignment]
    __gt__ = _op  # type: ignore[assignment]
    __lt__ = _op  # type: ignore[assignment]
    __ge__ = _op  # type: ignore[assignment]
    __le__ = _op  # type: ignore[assignment]
    __and__ = _op  # type: ignore[assignment]
    __or__ = _op  # type: ignore[assignment]
    __invert__ = _op  # type: ignore[assignment]
    __add__ = _op  # type: ignore[assignment]
    __sub__ = _op  # type: ignore[assignment]
    __mul__ = _op  # type: ignore[assignment]
    __rmul__ = _op  # type: ignore[assignment]
    __truediv__ = _op  # type: ignore[assignment]
    __rtruediv__ = _op  # type: ignore[assignment]
    __hash__ = object.__hash__


def _func_stub(*_a, **_k):  # type: ignore[no-untyped-def]
    return _Any("expr")


class _FuncModule:
    """Module-like : `from pyspark.sql.functions import x` -> `_func_stub`."""

    def __getattr__(self, _name: str):  # type: ignore[no-untyped-def]
        return _func_stub


class _WindowStub:
    @staticmethod
    def partitionBy(*_a, **_k):  # type: ignore[no-untyped-def]
        return _Any("window")


@pytest.fixture
def wf_fakes(monkeypatch: pytest.MonkeyPatch):
    """Installe les stubs pyspark et renvoie `(spark_stub, reads)`.

    `reads` accumule, dans l'ordre, chaque nom de table passe a
    `spark.read.table(...)` -- l'assertion centrale de cette suite.
    """
    functions_stub = _FuncModule()
    window_stub = SimpleNamespace(Window=_WindowStub)
    pyspark_sql_stub = SimpleNamespace(functions=functions_stub, window=window_stub)
    pyspark_stub = SimpleNamespace(sql=pyspark_sql_stub)

    monkeypatch.setitem(sys.modules, "pyspark", pyspark_stub)
    monkeypatch.setitem(sys.modules, "pyspark.sql", pyspark_sql_stub)
    monkeypatch.setitem(sys.modules, "pyspark.sql.functions", functions_stub)
    monkeypatch.setitem(sys.modules, "pyspark.sql.window", window_stub)

    reads: list[str] = []

    def _table(name: str) -> _Any:
        reads.append(name)
        return _Any(name)

    spark_stub = SimpleNamespace(read=SimpleNamespace(table=_table))

    # Force un reimport a froid : les modules du plugin font `from
    # pyspark.sql.functions import ...` au niveau module, ils doivent donc
    # etre (re)lies aux stubs installes ci-dessus, jamais au vrai pyspark
    # (qui exigerait une JVM/SparkContext actif pour `col`/`expr`/`Window`).
    for name in list(sys.modules):
        if name.startswith("pipelines.gold_dbx_workflow"):
            del sys.modules[name]

    return spark_stub, reads


@pytest.fixture
def bridges_module(wf_fakes):
    spark_stub, reads = wf_fakes
    mod = importlib.import_module("pipelines.gold_dbx_workflow.bridges")
    return mod, spark_stub, reads


# ---------------------------------------------------------------------------
# Fakes "enregistreurs" (portes de `tests/test_dlt_03_gold_layer.py`,
# migration T002) : verifient les REGLES de calcul (colonnes agregees,
# jointures, coalesce, schema de sortie), pas seulement les tables lues.
# ---------------------------------------------------------------------------
def _render(arg: object) -> str:
    if isinstance(arg, str):
        return arg
    if isinstance(arg, list):
        return ", ".join(_render(item) for item in arg)
    return getattr(arg, "value", repr(arg))


class _FakeExpr:
    def __init__(self, value: str) -> None:
        self.value = value

    def alias(self, alias_name: str) -> str:
        return f"{self.value} AS {alias_name}"

    def isNull(self) -> _FakeExpr:
        return _FakeExpr(f"{self.value} IS NULL")

    def isNotNull(self) -> _FakeExpr:
        return _FakeExpr(f"{self.value} IS NOT NULL")

    def desc(self) -> _FakeExpr:
        return _FakeExpr(f"{self.value} DESC")

    def cast(self, data_type: str) -> _FakeExpr:
        return _FakeExpr(f"cast({self.value} AS {data_type})")

    def over(self, window: object) -> _FakeExpr:
        return _FakeExpr(f"{self.value} OVER {window}")

    def __gt__(self, other: object) -> _FakeExpr:
        return _FakeExpr(f"({self.value} > {other})")

    def __truediv__(self, other: object) -> _FakeExpr:
        return _FakeExpr(f"({self.value} / {other})")

    def __mul__(self, other: object) -> _FakeExpr:
        return _FakeExpr(f"({self.value} * {other})")

    def __rmul__(self, other: object) -> _FakeExpr:
        return _FakeExpr(f"({other} * {self.value})")

    def __sub__(self, other: object) -> _FakeExpr:
        return _FakeExpr(f"({self.value} - {other})")

    def __eq__(self, other: object) -> _FakeExpr:  # type: ignore[override]
        return _FakeExpr(f"({self.value} = {_render(other)})")

    def __and__(self, other: object) -> _FakeExpr:
        return _FakeExpr(f"({self.value} AND {_render(other)})")

    __hash__ = object.__hash__

    def __repr__(self) -> str:
        return self.value


class _FakeWindowSpec:
    def __init__(
        self,
        partition_by: tuple[object, ...] = (),
        order_by: tuple[object, ...] = (),
    ) -> None:
        self.partition_by = partition_by
        self.order_by = order_by

    def orderBy(self, *cols: object) -> _FakeWindowSpec:
        return _FakeWindowSpec(self.partition_by, cols)

    def rowsBetween(self, start: int, end: int) -> _FakeWindowSpec:
        return self

    def __repr__(self) -> str:
        partition = ", ".join(_render(c) for c in self.partition_by)
        order = ", ".join(_render(c) for c in self.order_by)
        return f"(PARTITION BY {partition} ORDER BY {order})"


class _FakeWindow:
    @staticmethod
    def partitionBy(*cols: object) -> _FakeWindowSpec:
        return _FakeWindowSpec(cols)


class _RecordingFrame:
    """DataFrame factice qui ENREGISTRE la chaine d'appels, sans JVM ni calcul.

    Chaque operation renvoie `self` et memorise ses arguments rendus en texte :
    les vues-pont (`build_wf_runs_bridge`, `build_wf_task_runs_bridge`) sont
    ainsi verifiables sur leurs REGLES sans session Spark.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.grouped_by: list[str] = []
        self.aggregations: list[str] = []
        self.joined: list[tuple[str, str, str | None]] = []
        self.added_columns: list[tuple[str, str]] = []
        self.selected: list[str] = []
        self.filters: list[str] = []
        self.dropped: list[str] = []

    def groupBy(self, *cols: object) -> _RecordingFrame:
        self.grouped_by = [_render(c) for c in cols]
        return self

    def agg(self, *exprs: object) -> _RecordingFrame:
        self.aggregations = [_render(e) for e in exprs]
        return self

    def join(
        self,
        other: object,
        on: object = None,
        how: str | None = None,
    ) -> _RecordingFrame:
        self.joined.append((getattr(other, "name", repr(other)), _render(on), how))
        return self

    def withColumn(self, name: str, value: object) -> _RecordingFrame:
        self.added_columns.append((name, _render(value)))
        return self

    def select(self, *cols: object) -> _RecordingFrame:
        self.selected = [_render(c) for c in cols]
        return self

    def filter(self, condition: object) -> _RecordingFrame:
        self.filters.append(_render(condition))
        return self

    def drop(self, *cols: str) -> _RecordingFrame:
        self.dropped.extend(cols)
        return self


class _FakeSparkSession:
    def __init__(self) -> None:
        self.conf = SimpleNamespace(get=lambda key, default=None: default)
        self.read = SimpleNamespace(table=self._table)
        self.tables_read: list[str] = []
        self.frames: list[_RecordingFrame] = []

    def _table(self, name: str) -> _RecordingFrame:
        self.tables_read.append(name)
        frame = _RecordingFrame(name)
        self.frames.append(frame)
        return frame

    def reads_of(self, table_name: str) -> list[_RecordingFrame]:
        return [f for f in self.frames if table_name in f.name]

    def only_read_of(self, table_name: str) -> _RecordingFrame:
        frames = self.reads_of(table_name)
        assert len(frames) == 1, f"{table_name} lue {len(frames)} fois"
        return frames[0]


@pytest.fixture
def wf_recording_fakes(monkeypatch: pytest.MonkeyPatch):
    """Variante "enregistreuse" de `wf_fakes` : renvoie le module `bridges` +
    une `_FakeSparkSession` qui expose `reads_of`/`only_read_of` et des
    `_RecordingFrame` verifiables sur leurs regles de calcul.
    """
    functions_stub = SimpleNamespace(
        col=lambda name: _FakeExpr(f"col({name})"),
        max=lambda arg: _FakeExpr(f"max({_render(arg)})"),
        min=lambda arg: _FakeExpr(f"min({_render(arg)})"),
        sum=lambda arg: _FakeExpr(f"sum({_render(arg)})"),
        avg=lambda arg: _FakeExpr(f"avg({_render(arg)})"),
        count=lambda arg: _FakeExpr(f"count({_render(arg)})"),
        current_timestamp=lambda: _FakeExpr("current_timestamp()"),
        lit=lambda value: _FakeExpr(f"lit({value})"),
        when=lambda condition, value: _FakeExpr(f"when({condition},{value})"),
        expr=lambda text: _FakeExpr(f"expr({text})"),
        round=lambda value, scale: _FakeExpr(f"round({value},{scale})"),
        coalesce=lambda *args: _FakeExpr(
            "coalesce(" + ", ".join(_render(a) for a in args) + ")"
        ),
        countDistinct=lambda arg: _FakeExpr(f"countDistinct({_render(arg)})"),
        explode=lambda arg: _FakeExpr(f"explode({_render(arg)})"),
    )
    window_stub = SimpleNamespace(Window=_FakeWindow)
    pyspark_sql_stub = SimpleNamespace(functions=functions_stub, window=window_stub)
    pyspark_stub = SimpleNamespace(sql=pyspark_sql_stub)

    monkeypatch.setitem(sys.modules, "pyspark", pyspark_stub)
    monkeypatch.setitem(sys.modules, "pyspark.sql", pyspark_sql_stub)
    monkeypatch.setitem(sys.modules, "pyspark.sql.functions", functions_stub)
    monkeypatch.setitem(sys.modules, "pyspark.sql.window", window_stub)

    for name in list(sys.modules):
        if name.startswith("pipelines.gold_dbx_workflow"):
            del sys.modules[name]

    mod = importlib.import_module("pipelines.gold_dbx_workflow.bridges")
    spark = _FakeSparkSession()
    return SimpleNamespace(module=mod, spark=spark)
