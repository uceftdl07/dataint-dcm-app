"""Shared SQL helpers for RBAC and request-scoped Landing Zone filtering."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Query

__all__ = [
    "SourceLzIdQuery",
    "SourceLzIdsQuery",
    "add_cost_period_filter",
    "add_lz_filter",
    "add_scope_lz_filter",
    "normalize_requested_lz_ids",
    "resolve_effective_lz_ids",
]

SourceLzIdQuery = Annotated[
    str | None,
    Query(description="Filter by a single landing zone ID."),
]
SourceLzIdsQuery = Annotated[
    list[str] | None,
    Query(description="Filter by one or more landing zone IDs."),
]


def normalize_requested_lz_ids(
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
) -> list[str] | None:
    """Return ``None`` when the client did not request an LZ filter."""
    if source_lz_ids is not None:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in source_lz_ids:
            item = value.strip()
            if not item or item in seen:
                continue
            seen.add(item)
            normalized.append(item)
        return normalized

    if source_lz_id is not None:
        item = source_lz_id.strip()
        return [item] if item else []

    return None


def resolve_effective_lz_ids(
    allowed_lz_ids: list[str] | None,
    *,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
) -> list[str] | None:
    """Combine RBAC scope with optional request filters.

    Returns:
        ``None`` when no LZ SQL filter should be applied.
        ``[]`` when the effective scope is empty and queries must return no rows.
        ``[...]`` when results must be restricted to the given landing zones.
    """
    requested = normalize_requested_lz_ids(source_lz_id, source_lz_ids)

    if allowed_lz_ids is None:
        return requested

    if not allowed_lz_ids:
        return []

    if requested is None:
        return allowed_lz_ids

    allowed = set(allowed_lz_ids)
    return [lz_id for lz_id in requested if lz_id in allowed]


def _append_lz_in_filter(
    conditions: list[str],
    params: list[Any],
    effective_lz_ids: list[str] | None,
    *,
    column: str,
) -> None:
    if effective_lz_ids is None:
        return
    if not effective_lz_ids:
        conditions.append("1 = 0")
        return

    placeholders = ", ".join("?" for _ in effective_lz_ids)
    conditions.append(f"{column} IN ({placeholders})")
    params.extend(effective_lz_ids)


def add_lz_filter(
    conditions: list[str],
    params: list[Any],
    allowed_lz_ids: list[str] | None,
    *,
    column: str = "source_lz_id",
) -> None:
    """Append the RBAC-only LZ condition to a parameterized Databricks SQL query."""
    _append_lz_in_filter(conditions, params, resolve_effective_lz_ids(allowed_lz_ids), column=column)


def add_scope_lz_filter(
    conditions: list[str],
    params: list[Any],
    allowed_lz_ids: list[str] | None,
    *,
    source_lz_id: str | None = None,
    source_lz_ids: list[str] | None = None,
    column: str = "source_lz_id",
) -> None:
    """Append RBAC + optional request LZ filters as a single ``IN`` clause."""
    effective = resolve_effective_lz_ids(
        allowed_lz_ids,
        source_lz_id=source_lz_id,
        source_lz_ids=source_lz_ids,
    )
    _append_lz_in_filter(conditions, params, effective, column=column)


def add_cost_period_filter(
    conditions: list[str],
    params: list[Any],
    start: Any,
    end: Any,
) -> None:
    """Match cost rows whose billing period overlaps the requested window."""
    conditions.append("CAST(period_start AS DATE) <= ?")
    conditions.append("CAST(period_end AS DATE) >= ?")
    params.extend([end, start])
