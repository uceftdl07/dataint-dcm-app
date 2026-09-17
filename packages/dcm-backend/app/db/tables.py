"""Helpers for addressing Unity Catalog tables safely."""

from __future__ import annotations

from ..config import Settings

__all__ = ["qualified_lz_dimension_table", "qualified_table"]

_LZ_DIMENSION_TABLE = "dim_landing_zone"


def _quote_identifier(value: str) -> str:
    return f"`{value.replace('`', '``')}`"


def qualified_table(settings: Settings, table_name: str) -> str:
    """Return a fully qualified Unity Catalog table reference."""
    return ".".join(
        (
            _quote_identifier(settings.databricks_catalog),
            _quote_identifier(settings.databricks_schema),
            _quote_identifier(table_name),
        )
    )


def qualified_lz_dimension_table(settings: Settings) -> str:
    """Return the curated landing-zone dimension table used for LZ selectors."""
    return qualified_table(settings, _LZ_DIMENSION_TABLE)
