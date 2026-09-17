"""Unit tests for Landing Zone filter helpers."""

from __future__ import annotations

from app.api.routes._lz_filter import (
    add_scope_lz_filter,
    normalize_requested_lz_ids,
    resolve_effective_lz_ids,
)


def test_normalize_requested_lz_ids_prefers_list_param() -> None:
    assert normalize_requested_lz_ids(
        source_lz_id="lz-single",
        source_lz_ids=["lz-a", "lz-b"],
    ) == ["lz-a", "lz-b"]


def test_normalize_requested_lz_ids_single_value() -> None:
    assert normalize_requested_lz_ids(source_lz_id=" lz-aws-prod ") == ["lz-aws-prod"]


def test_resolve_effective_lz_ids_intersects_with_rbac() -> None:
    assert resolve_effective_lz_ids(
        ["lz-aws-prod", "lz-azure-prod"],
        source_lz_ids=["lz-aws-prod", "lz-other"],
    ) == ["lz-aws-prod"]


def test_resolve_effective_lz_ids_admin_without_request() -> None:
    assert resolve_effective_lz_ids(None) is None


def test_resolve_effective_lz_ids_admin_with_multi_request() -> None:
    assert resolve_effective_lz_ids(
        None,
        source_lz_ids=["lz-aws-prod", "lz-azure-prod"],
    ) == ["lz-aws-prod", "lz-azure-prod"]


def test_resolve_effective_lz_ids_empty_request_denies_rows() -> None:
    assert resolve_effective_lz_ids(None, source_lz_ids=[]) == []


def test_add_scope_lz_filter_builds_in_clause() -> None:
    conditions: list[str] = []
    params: list[str] = []

    add_scope_lz_filter(
        conditions,
        params,
        None,
        source_lz_ids=["lz-aws-prod", "lz-azure-prod"],
    )

    assert conditions == ["source_lz_id IN (?, ?)"]
    assert params == ["lz-aws-prod", "lz-azure-prod"]
