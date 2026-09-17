"""Valeurs proposables par les filtres catalogue / schéma / table.

Les listes viennent de ``gold_dbx_usage_table_catalog``, le registre du parc —
jamais des lignes déjà affichées : toutes les vues de la page paginent côté
serveur, donc une liste construite depuis la page courante ne proposerait que
25 tables sur plusieurs milliers.

``table_catalog`` est grainé par cloud : chaque liste est dédupliquée avant
d'être renvoyée, sans quoi une table présente sur les deux clouds
apparaîtrait deux fois dans le sélecteur.
"""

from __future__ import annotations

from typing import Any

from ...db.connection import DatabricksWarehousePool
from .uc_usage_common import (
    GOLD_TABLE_CATALOG,
    LIFECYCLE_AGGREGATES,
    deleted_flag_conditions,
    lifecycle_fields,
    object_filters,
    search_condition,
    where_clause,
)
from .uc_usage_common import guarded as _guarded

__all__ = ["MAX_FILTER_OPTIONS", "fetch_filter_options"]

MAX_FILTER_OPTIONS = 500


async def _values(
    db: DatabricksWarehousePool,
    column: str,
    conditions: list[str],
    params: list[Any],
    limit: int,
) -> list[str]:
    rows = await _guarded(
        db,
        db.fetchall(
            f"""
            SELECT DISTINCT {column} AS value
            FROM {db.table(GOLD_TABLE_CATALOG)}
            {where_clause([*conditions, f"{column} IS NOT NULL"])}
            ORDER BY value ASC
            LIMIT ?
            """,
            *params,
            limit,
        ),
        tables=[GOLD_TABLE_CATALOG],
    )
    return [str(row["value"]) for row in rows]


async def fetch_filter_options(
    db: DatabricksWarehousePool,
    *,
    catalog: str | None = None,
    schema: str | None = None,
    search: str | None = None,
    limit: int = MAX_FILTER_OPTIONS,
    include_deleted: bool = False,
) -> dict[str, Any]:
    """Catalogues, schémas et tables proposables dans le périmètre demandé.

    ``catalog``/``schema`` resserrent les listes situées **en dessous** d'eux :
    choisir un catalogue n'a pas à laisser proposer les schémas des autres.

    Le registre porte lui-même ``is_deleted`` : le filtre est donc un prédicat
    direct, et il s'applique aux trois listes — proposer un catalogue qui ne
    contient plus que des tables supprimées mènerait à un périmètre vide.
    """
    deleted = deleted_flag_conditions(include_deleted)
    catalogs = await _values(db, "`catalog`", [*deleted], [], limit)

    schema_conditions, schema_params = object_filters(catalog, None, None)
    schema_conditions.extend(deleted)
    schemas = await _values(db, "`schema`", schema_conditions, schema_params, limit)

    table_conditions, table_params = object_filters(catalog, schema, None)
    search_conditions, search_params = search_condition(search, columns=["table_full_name"])
    table_conditions.extend(search_conditions)
    table_params.extend(search_params)
    table_conditions.extend(deleted)

    rows = await _guarded(
        db,
        db.fetchall(
            f"""
            SELECT
                table_full_name,
                MAX(`catalog`) AS catalog,
                MAX(`schema`) AS schema,{LIFECYCLE_AGGREGATES}
            FROM {db.table(GOLD_TABLE_CATALOG)}
            {where_clause([*table_conditions, "table_full_name IS NOT NULL"])}
            GROUP BY table_full_name
            ORDER BY table_full_name ASC
            LIMIT ?
            """,
            *table_params,
            limit,
        ),
        tables=[GOLD_TABLE_CATALOG],
    )

    tables = [
        {
            "table_full_name": row["table_full_name"],
            "catalog": row["catalog"],
            "schema": row["schema"],
            **lifecycle_fields(row),
        }
        for row in rows
    ]

    return {
        "catalogs": catalogs,
        "schemas": schemas,
        "tables": tables,
        # Une liste pleine à ras bord est probablement tronquée : le sélecteur le
        # dit et invite à chercher, plutôt que de laisser croire à un parc complet.
        "truncated": len(tables) >= limit,
        "limit": limit,
    }
