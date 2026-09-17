"""Unit tests for `pipelines.dlt_01_raw_layer`."""

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


@pytest.fixture
def raw_module(monkeypatch: pytest.MonkeyPatch):
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
    )
    monkeypatch.setitem(sys.modules, "dlt", dlt_stub)

    sys.modules.pop("pipelines.dlt_01_raw_layer", None)
    return importlib.import_module("pipelines.dlt_01_raw_layer")


def test_ingestion_path_defaults_when_spark_unavailable(raw_module) -> None:
    assert (
        raw_module.INGESTION_VOLUME_PATH
        == "/Volumes/it/ba_data_connect_monitoring__d/ingestion_volume/"
    )


def test_raw_metrics_stream_reader_configuration(raw_module, monkeypatch: pytest.MonkeyPatch) -> None:
    read_stream = MagicMock(name="read_stream")
    loaded_df = MagicMock(name="loaded_df")
    first_select_df = MagicMock(name="first_select_df")
    final_df = MagicMock(name="final_df")

    read_stream.format.return_value = read_stream
    read_stream.option.return_value = read_stream
    read_stream.load.return_value = loaded_df
    loaded_df.select.return_value = first_select_df
    first_select_df.select.return_value = final_df

    raw_module.spark = SimpleNamespace(readStream=read_stream)

    monkeypatch.setattr(raw_module, "col", lambda name: _FakeExpr(f"col({name})"))
    monkeypatch.setattr(raw_module, "expr", lambda text: _FakeExpr(f"expr({text})"))
    monkeypatch.setattr(raw_module, "parse_json", lambda value: _FakeExpr(f"parse_json({value})"))
    monkeypatch.setattr(raw_module, "current_timestamp", lambda: _FakeExpr("current_timestamp()"))

    result = raw_module.raw_metrics()

    assert result is final_df
    read_stream.format.assert_called_once_with("cloudFiles")
    read_stream.option.assert_any_call("cloudFiles.format", "text")
    read_stream.option.assert_any_call("wholetext", "true")
    read_stream.option.assert_any_call("ignoreCorruptFiles", "true")
    read_stream.option.assert_any_call("ignoreMissingFiles", "true")
    read_stream.load.assert_called_once_with(raw_module.INGESTION_VOLUME_PATH)

