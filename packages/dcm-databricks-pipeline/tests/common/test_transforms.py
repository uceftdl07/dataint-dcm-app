"""Tests de `pipelines.common.transforms` (enveloppe fidele source)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import pipelines.common.transforms as transforms

# ---------------------------------------------------------------------------
# Enrichissement enveloppe — fidele source
# ---------------------------------------------------------------------------


def test_enrich_adds_only_envelope_columns(fake_functions: None, fakes: SimpleNamespace) -> None:
    df = fakes.DataFrame("aws_usage")

    result = transforms.enrich_with_envelope(
        df,
        cloud_provider="aws",
        collected_at="2026-07-30T00:00:00Z",
    )

    added = [name for name, _ in result.added_columns]
    assert added == list(transforms.ENVELOPE_COLUMNS)


def test_enrich_sets_expected_envelope_values(fake_functions: None, fakes: SimpleNamespace) -> None:
    df = fakes.DataFrame("azure_usage")

    result = transforms.enrich_with_envelope(
        df,
        cloud_provider="azure",
        collected_at="2026-07-30T00:00:00Z",
    )

    values = dict(result.added_columns)
    assert values["cloud_provider"] == ("lit", "azure")
    assert values["collected_at"] == ("to_timestamp", ("lit", "2026-07-30T00:00:00Z"))


# ---------------------------------------------------------------------------
# filter_null_or_empty_key (FR-011) — exclusion des cles NULL/vide + log
# ---------------------------------------------------------------------------


class _CountingDataFrame:
    """Fake minimal simulant une vraie reduction de volume par `filter()`.

    `FakeDataFrame.filter()` mute l'instance en place (memes lignes, meme
    `row_count`) : insuffisant pour verifier un nombre d'exclusions reel. Ce
    fake dedie retourne un NOUVEL objet dont `count()` reflete la baisse de
    volume attendue, sans reimplementer l'evaluation de la condition (le
    contenu de `condition` n'est pas interprete, seul le nombre de lignes
    restant apres filtrage est simule).
    """

    def __init__(self, counts: list[int]) -> None:
        self._counts = iter(counts)
        self.filters: list[object] = []

    def count(self) -> int:
        return next(self._counts)

    def filter(self, condition: object) -> _CountingDataFrame:
        self.filters.append(condition)
        return self


def test_filter_null_or_empty_key_excludes_and_logs_when_rows_removed(
    fake_functions: None, caplog: pytest.LogCaptureFixture
) -> None:
    df = _CountingDataFrame(counts=[10, 7])

    with caplog.at_level("WARNING", logger=transforms.logger.name):
        result = transforms.filter_null_or_empty_key(df, "workspace_id")

    assert result is df
    assert len(df.filters) == 1
    assert "excluded=3" in caplog.text
    assert "workspace_id" in caplog.text


def test_filter_null_or_empty_key_no_log_when_no_rows_removed(
    fake_functions: None, caplog: pytest.LogCaptureFixture
) -> None:
    df = _CountingDataFrame(counts=[10, 10])

    with caplog.at_level("WARNING", logger=transforms.logger.name):
        transforms.filter_null_or_empty_key(df, "workspace_id")

    assert caplog.text == ""


def test_filter_null_or_empty_key_combines_multiple_key_columns(
    fake_functions: None, fakes: SimpleNamespace
) -> None:
    df = fakes.DataFrame("staging", row_count=5)

    transforms.filter_null_or_empty_key(df, "workspace_id", "cloud_provider")

    # 1 seul appel `.filter()` : les conditions par cle sont combinees via `&`.
    assert len(df.filters) == 1
    condition = df.filters[0]
    assert condition.expr[0] == "and"


# ---------------------------------------------------------------------------
# dedupe_by_key (FR-009) — choix deterministe avant MERGE
# ---------------------------------------------------------------------------


def test_dedupe_by_key_orders_by_all_remaining_columns_and_drops_helper_column(
    fake_functions: None, fakes: SimpleNamespace
) -> None:
    df = fakes.DataFrame(
        "staging",
        columns=["workspace_id", "workspace_name", "subscription_or_account_id", "cloud_provider"],
    )

    result = transforms.dedupe_by_key(df, ("workspace_id",))

    # La colonne technique de rang est ajoutee puis supprimee, jamais persistee.
    added_names = [name for name, _ in df.added_columns]
    assert "_dcm_dedupe_row_number" in added_names
    assert df.dropped_columns == ["_dcm_dedupe_row_number"]
    assert "_dcm_dedupe_row_number" not in result.columns

    # Window : partition sur la cle (colonnes passees telles quelles, pas de
    # F.col ici — `Window.partitionBy` accepte des noms de colonnes bruts),
    # tri sur TOUTES les autres colonnes.
    row_number_value = dict(df.added_columns)["_dcm_dedupe_row_number"]
    window = row_number_value.expr[2]
    assert window.partition_by == ("workspace_id",)
    assert [c.expr for c in window.order_by] == [
        ("asc_nulls_last", ("col", "workspace_name")),
        ("asc_nulls_last", ("col", "subscription_or_account_id")),
        ("asc_nulls_last", ("col", "cloud_provider")),
    ]

    # Filtre final : ne garde que le rang 1 (une seule ligne par cle).
    assert len(df.filters) == 1
    assert df.filters[0].expr == ("eq", ("col", "_dcm_dedupe_row_number"), 1)


def test_dedupe_by_key_uses_constant_order_when_key_is_all_columns(
    fake_functions: None, fakes: SimpleNamespace
) -> None:
    # Cas degenere : la cle couvre toutes les colonnes -> pas de colonne restante
    # pour trier, un ordre constant (mais stable) suffit.
    df = fakes.DataFrame("staging", columns=["workspace_id"])

    transforms.dedupe_by_key(df, ("workspace_id",))

    row_number_value = dict(df.added_columns)["_dcm_dedupe_row_number"]
    window = row_number_value.expr[2]
    # `F.lit(1)` (pas de F.col ici) : element brut, pas un FakeColumn.
    assert window.order_by == (("lit", 1),)

