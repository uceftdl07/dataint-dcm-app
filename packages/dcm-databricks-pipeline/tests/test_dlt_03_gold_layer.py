"""Unit tests for `pipelines.dlt_03_gold_layer`.

Les tests des vues-pont workflow (`_wf_runs_bridge`/`_wf_task_runs_bridge`) ont
ete portes dans `tests/gold_dbx_workflow/test_bridges.py` lors de la migration
du domaine workflow hors DLT (migration T002/013-workflow-sys-tables) : ce
module gold ne contient plus ces fonctions (supprimees de
`pipelines/dlt_03_gold_layer.py`), seuls les autres domaines gold restent
testes ici.
"""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace

import pytest


def _render(arg: object) -> str:
    """Rend une expression factice (ou une chaine deja aliasee) en texte inspectable."""
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

    def __repr__(self) -> str:
        partition = ", ".join(_render(c) for c in self.partition_by)
        order = ", ".join(_render(c) for c in self.order_by)
        return f"(PARTITION BY {partition} ORDER BY {order})"


class _FakeWindow:
    @staticmethod
    def partitionBy(*cols: object) -> _FakeWindowSpec:
        return _FakeWindowSpec(cols)


def _install_fake_pyspark(monkeypatch: pytest.MonkeyPatch) -> None:
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


class _FakeFrame:
    def __init__(self, name: str) -> None:
        self.name = name

    def join(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self

    def groupBy(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self

    def agg(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return f"agg:{self.name}"

    def __getitem__(self, key: str) -> str:
        return f"{self.name}[{key}]"

    @property
    def source_lz_id(self) -> str:
        return f"{self.name}.source_lz_id"

    @property
    def lz_id(self) -> str:
        return f"{self.name}.lz_id"


@pytest.fixture
def gold_module(monkeypatch: pytest.MonkeyPatch):
    _install_fake_pyspark(monkeypatch)

    def _decorator(*args, **kwargs):  # type: ignore[no-untyped-def]
        def _wrap(func):  # type: ignore[no-untyped-def]
            return func

        return _wrap

    dlt_stub = SimpleNamespace(
        table=_decorator,
        view=_decorator,
        create_streaming_table=lambda *args, **kwargs: None,
        apply_changes=lambda *args, **kwargs: None,
        read=lambda name: _FakeFrame(name),
        read_stream=lambda name: _FakeFrame(name),
    )
    monkeypatch.setitem(sys.modules, "dlt", dlt_stub)

    sys.modules.pop("pipelines.dlt_03_gold_layer", None)
    return importlib.import_module("pipelines.dlt_03_gold_layer")


def test_ddl_renders_schema_string(gold_module) -> None:
    ddl = gold_module._ddl(
        ("source_lz_id", "STRING", "landing zone"),
        ("total_runs", "LONG", "run count"),
    )
    assert ddl == "source_lz_id STRING COMMENT 'landing zone', total_runs LONG COMMENT 'run count'"


def test_standard_check_score_reads_curated_standard_check_table(
    gold_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def _fake_read(name: str) -> _FakeFrame:
        calls.append(name)
        return _FakeFrame(name)

    monkeypatch.setattr(gold_module.dlt, "read", _fake_read)

    result = gold_module.gold_standard_check_score()

    assert calls == ["curated_standard_checks", "dim_landing_zone_collector"]
    assert result == "agg:curated_standard_checks"


def test_activity_performance_reads_curated_activity_runs(
    gold_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def _fake_read(name: str) -> _FakeFrame:
        calls.append(name)
        return _FakeFrame(name)

    monkeypatch.setattr(gold_module.dlt, "read", _fake_read)

    result = gold_module.gold_activity_performance()

    assert calls == ["curated_activity_runs"]
    assert result == "agg:curated_activity_runs"


def _gold_layer_source() -> str:
    from pathlib import Path

    module_path = Path(__file__).resolve().parents[1] / "pipelines" / "dlt_03_gold_layer.py"
    return module_path.read_text(encoding="utf-8")


def test_landing_zone_dimension_is_renamed_to_collector() -> None:
    # Le rename est le point pivot de la feature 021 : la table DLT devient
    # `dim_landing_zone_collector` pour liberer le nom `dim_landing_zone` au
    # profit de la vue union (pipelines.gold_landing_zone).
    source = _gold_layer_source()
    assert 'name="dim_landing_zone_collector"' in source
    assert 'target="dim_landing_zone_collector"' in source
    assert "pk_dim_landing_zone_collector" in source
    # Plus aucune reference a l'ancien nom de table (ni streaming table, ni read,
    # ni PK) — seuls docstring/commentaires peuvent le mentionner.
    assert 'name="dim_landing_zone"' not in source
    assert 'target="dim_landing_zone"' not in source
    assert 'dlt.read("dim_landing_zone")' not in source


def test_no_foreign_key_constraints_remain() -> None:
    # Les 7 FK vers dim_landing_zone sont supprimees (clarif : pas de FK sur la
    # table renommee ; l'integrite est portee par la vue via INNER JOIN).
    source = _gold_layer_source()
    assert "FOREIGN KEY" not in source
    assert "fk_gold" not in source

