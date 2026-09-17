"""Unit tests for `pipelines.dlt_02_curated_layer`."""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


class _FakeExpr:
    def __init__(self, value: str) -> None:
        self.value = value

    def alias(self, alias_name: str) -> str:
        return f"{self.value} AS {alias_name}"

    def cast(self, target_type: str) -> str:
        return f"CAST({self.value} AS {target_type})"

    def __invert__(self) -> "_FakeExpr":
        return _FakeExpr(f"NOT({self.value})")


def _install_fake_pyspark(monkeypatch: pytest.MonkeyPatch) -> None:
    functions_stub = SimpleNamespace(
        col=lambda name: _FakeExpr(f"col({name})"),
        expr=lambda text: _FakeExpr(f"expr({text})"),
        when=lambda condition, value: _FakeExpr(f"when({condition},{value})"),
        concat_ws=lambda sep, *parts: _FakeExpr(f"concat_ws({sep},{len(parts)})"),
        lit=lambda value: _FakeExpr(f"lit({value})"),
        explode=lambda value: _FakeExpr(f"explode({value})"),
    )
    pyspark_sql_stub = SimpleNamespace(functions=functions_stub)
    pyspark_stub = SimpleNamespace(sql=pyspark_sql_stub)

    monkeypatch.setitem(sys.modules, "pyspark", pyspark_stub)
    monkeypatch.setitem(sys.modules, "pyspark.sql", pyspark_sql_stub)
    monkeypatch.setitem(sys.modules, "pyspark.sql.functions", functions_stub)


@pytest.fixture
def curated_module(monkeypatch: pytest.MonkeyPatch):
    _install_fake_pyspark(monkeypatch)

    def _decorator(*args, **kwargs):  # type: ignore[no-untyped-def]
        def _wrap(func):  # type: ignore[no-untyped-def]
            return func

        return _wrap

    dlt_stub = SimpleNamespace(
        table=_decorator,
        view=_decorator,
        expect_all_or_drop=lambda *_a, **_k: _decorator(),
        create_streaming_table=lambda *args, **kwargs: None,
        apply_changes=lambda *args, **kwargs: None,
        read_stream=lambda name: MagicMock(name=f"stream_{name}"),
    )
    monkeypatch.setitem(sys.modules, "dlt", dlt_stub)

    sys.modules.pop("pipelines.dlt_02_curated_layer", None)
    return importlib.import_module("pipelines.dlt_02_curated_layer")


def test_ddl_renders_schema_string(curated_module) -> None:
    ddl = curated_module._ddl(
        ("id", "STRING", "identifier"),
        ("cost_usd", "DOUBLE", "cost in usd"),
    )
    assert ddl == "id STRING COMMENT 'identifier', cost_usd DOUBLE COMMENT 'cost in usd'"


def test_parse_metrics_and_dq_builds_expected_valid_expression(
    curated_module,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expr_spy = MagicMock(side_effect=lambda text: _FakeExpr(text))

    monkeypatch.setattr(curated_module, "expr", expr_spy)
    monkeypatch.setattr(curated_module, "col", lambda name: _FakeExpr(name))
    monkeypatch.setattr(curated_module, "explode", lambda value: _FakeExpr(f"explode({value})"))
    monkeypatch.setattr(curated_module, "lit", lambda value: _FakeExpr(str(value)))
    monkeypatch.setattr(
        curated_module,
        "when",
        lambda condition, value: _FakeExpr(f"WHEN({condition.value},{value.value})"),
    )
    monkeypatch.setattr(curated_module, "concat_ws", lambda sep, *parts: f"{sep}:{len(parts)}")

    df = MagicMock(name="raw_df")
    exploded = MagicMock(name="exploded")
    parsed = MagicMock(name="parsed")
    after_first = MagicMock(name="after_first")
    final_df = MagicMock(name="final_df")

    df.select.return_value = exploded
    exploded.select.return_value = parsed
    parsed.withColumn.return_value = after_first
    after_first.withColumn.return_value = final_df

    dq_rules = {
        "valid_id": "id IS NOT NULL",
        "valid_cost": "cost_usd >= 0",
    }

    result = curated_module.parse_metrics_and_dq(df, [_FakeExpr("metric:id")], dq_rules)

    assert result is final_df

    expected_valid_expr = (
        "COALESCE((id IS NOT NULL), false) AND COALESCE((cost_usd >= 0), false)"
    )
    expr_spy.assert_any_call(expected_valid_expr)


def test_staging_views_use_renamed_domains(curated_module, monkeypatch: pytest.MonkeyPatch) -> None:
    class _DomainCol:
        def __init__(self, name: str) -> None:
            self.name = name

        def __eq__(self, other: object) -> str:  # type: ignore[override]
            return f"{self.name}=={other}"

    raw_stream = MagicMock(name="raw_stream")
    filtered_stream = MagicMock(name="filtered_stream")
    raw_stream.filter.return_value = filtered_stream

    monkeypatch.setattr(curated_module, "col", lambda name: _DomainCol(name))
    monkeypatch.setattr(curated_module.dlt, "read_stream", lambda name: raw_stream)

    parse_spy = MagicMock(return_value="parsed")
    monkeypatch.setattr(curated_module, "parse_metrics_and_dq", parse_spy)

    curated_module._stg_compute()
    raw_stream.filter.assert_any_call("domain==compute")

    curated_module._stg_standard_check()
    raw_stream.filter.assert_any_call("domain==standard_check")

    assert parse_spy.call_count == 2

