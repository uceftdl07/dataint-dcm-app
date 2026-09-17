"""Database layer — Databricks SQL Warehouse connection and FastAPI dependency."""

from __future__ import annotations

from .connection import DatabricksWarehousePool, get_db

# Legacy alias for backward compatibility during migration
DatabasePool = DatabricksWarehousePool

__all__ = ["DatabricksWarehousePool", "DatabasePool", "get_db"]
