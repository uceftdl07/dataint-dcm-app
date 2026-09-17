"""Unit tests for the Databricks Workflows curated-layer DLT logic (epic 009).

Covers:
  * dlt_01_raw_layer  -> 'workflow' allowed in the valid_domain expectation.
  * dlt_02_curated_layer -> _stg_dbx_workflow parsing + curated_dbx_workflow_runs wiring.

Les 8 agregats gold (ex-`dlt_03_gold_layer`) ont ete migres hors DLT vers un job
PySpark standalone (`pipelines.gold_dbx_workflow`, migration T002/
013-workflow-sys-tables) : leurs tests vivent desormais dans
`tests/gold_dbx_workflow/`. Le collecteur + `curated_dbx_workflow_*` testes ici
restent INTACTS (hors scope de cette migration).

The pyspark/dlt runtime is not available in unit tests, so we install a
universal chainable stub: every DataFrame/Column operation returns the same
object, which lets each pipeline function execute end-to-end. We assert on the
source tables that were read rather than on concrete Spark results.
"""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace

import pytest


class _Any:
    """Universal chainable mock for both DataFrames and Column expressions."""

    def __init__(self, tag: str = "any") -> None:
        self._tag = tag

    # Any attribute access yields a callable that returns self.
    def __getattr__(self, _name: str):  # type: ignore[no-untyped-def]
        return lambda *a, **k: self

    # Being called (e.g. as a function result) returns self.
    def __call__(self, *a, **k):  # type: ignore[no-untyped-def]
        return self

    def __getitem__(self, _key):  # type: ignore[no-untyped-def]
        return self

    # Comparisons / boolean / arithmetic all collapse to self.
    def _op(self, *_a, **_k):  # type: ignore[no-untyped-def]
        return self

    __eq__ = _op          # type: ignore[assignment]
    __ne__ = _op          # type: ignore[assignment]
    __gt__ = _op          # type: ignore[assignment]
    __lt__ = _op          # type: ignore[assignment]
    __ge__ = _op          # type: ignore[assignment]
    __le__ = _op          # type: ignore[assignment]
    __and__ = _op         # type: ignore[assignment]
    __or__ = _op          # type: ignore[assignment]
    __invert__ = _op      # type: ignore[assignment]
    __add__ = _op         # type: ignore[assignment]
    __sub__ = _op         # type: ignore[assignment]
    __mul__ = _op         # type: ignore[assignment]
    __rmul__ = _op        # type: ignore[assignment]
    __truediv__ = _op     # type: ignore[assignment]
    __rtruediv__ = _op    # type: ignore[assignment]
    __hash__ = object.__hash__


def _func_stub(*_a, **_k):  # type: ignore[no-untyped-def]
    return _Any("expr")


class _FuncModule:
    """Module-like object: `from pyspark.sql.functions import x` -> _func_stub."""

    def __getattr__(self, _name: str):  # type: ignore[no-untyped-def]
        return _func_stub


class _WindowStub:
    @staticmethod
    def partitionBy(*_a, **_k):  # type: ignore[no-untyped-def]
        return _Any("window")


def _install_fakes(monkeypatch: pytest.MonkeyPatch, reads: list[str], tables: list[str]) -> None:
    functions_stub = _FuncModule()
    window_stub = SimpleNamespace(Window=_WindowStub)
    pyspark_sql_stub = SimpleNamespace(functions=functions_stub, window=window_stub)
    pyspark_stub = SimpleNamespace(sql=pyspark_sql_stub)

    monkeypatch.setitem(sys.modules, "pyspark", pyspark_stub)
    monkeypatch.setitem(sys.modules, "pyspark.sql", pyspark_sql_stub)
    monkeypatch.setitem(sys.modules, "pyspark.sql.functions", functions_stub)
    monkeypatch.setitem(sys.modules, "pyspark.sql.window", window_stub)

    def _decorator(*_a, **_k):  # type: ignore[no-untyped-def]
        def _wrap(func):  # type: ignore[no-untyped-def]
            return func

        return _wrap

    def _read(name: str) -> _Any:
        reads.append(name)
        return _Any(name)

    dlt_stub = SimpleNamespace(
        table=_decorator,
        view=_decorator,
        create_streaming_table=lambda *a, **k: None,
        apply_changes=lambda *a, **k: None,
        read=_read,
        read_stream=_read,
        expect_all_or_drop=_decorator,
    )
    monkeypatch.setitem(sys.modules, "dlt", dlt_stub)

    def _table(name: str) -> _Any:
        tables.append(name)
        return _Any(name)

    def _conf_get(_key: str, default: str) -> str:
        return default

    spark_stub = SimpleNamespace(
        read=SimpleNamespace(table=_table),
        conf=SimpleNamespace(get=_conf_get),
    )
    return dlt_stub, spark_stub


@pytest.fixture
def curated_module(monkeypatch: pytest.MonkeyPatch):
    reads: list[str] = []
    tables: list[str] = []
    _install_fakes(monkeypatch, reads, tables)
    sys.modules.pop("pipelines.dlt_02_curated_layer", None)
    mod = importlib.import_module("pipelines.dlt_02_curated_layer")
    mod._test_reads = reads  # type: ignore[attr-defined]
    return mod


# ---------------------------------------------------------------------------
# raw layer
# ---------------------------------------------------------------------------
def test_raw_layer_allows_workflow_domain() -> None:
    from pathlib import Path

    src = Path(__file__).resolve().parent.parent / "pipelines" / "dlt_01_raw_layer.py"
    text = src.read_text(encoding="utf-8")
    # The workflow domain must be part of the valid_domain expectation IN-list.
    marker = text.split('"valid_domain"', 1)[1].split("}", 1)[0]
    assert "'workflow'" in marker


# ---------------------------------------------------------------------------
# curated layer
# ---------------------------------------------------------------------------
def test_stg_dbx_workflow_reads_raw_metrics(curated_module) -> None:
    curated_module._test_reads.clear()
    curated_module._stg_dbx_workflow()
    assert "raw_metrics" in curated_module._test_reads


def test_stg_dbx_workflow_valid_reads_stg_dbx_workflow(curated_module) -> None:
    curated_module._test_reads.clear()
    curated_module._stg_dbx_workflow_valid()
    assert curated_module._test_reads == ["_stg_dbx_workflow"]


def test_curated_dbx_workflow_runs_rejects_reads_stg(curated_module) -> None:
    curated_module._test_reads.clear()
    curated_module.curated_dbx_workflow_runs_rejects()
    assert curated_module._test_reads == ["_stg_dbx_workflow"]


def test_stg_dbx_workflow_task_reads_raw_metrics(curated_module) -> None:
    curated_module._test_reads.clear()
    curated_module._stg_dbx_workflow_task()
    assert "raw_metrics" in curated_module._test_reads


def test_stg_dbx_workflow_task_valid_reads_stg(curated_module) -> None:
    curated_module._test_reads.clear()
    curated_module._stg_dbx_workflow_task_valid()
    assert curated_module._test_reads == ["_stg_dbx_workflow_task"]


def test_curated_dbx_workflow_task_runs_rejects_reads_stg(curated_module) -> None:
    curated_module._test_reads.clear()
    curated_module.curated_dbx_workflow_task_runs_rejects()
    assert curated_module._test_reads == ["_stg_dbx_workflow_task"]

