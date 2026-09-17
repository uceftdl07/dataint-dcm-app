"""FinOps view — cost aggregates and the 7-day forecast series.

``estimated_cost_usd`` is attributed by equal parts across every object a query
reads, views included, so a table shares its cost with the views that read it.
Every response carries ``cost_attribution_method`` / ``cost_basis`` so the UI can
say so rather than presenting the figure as an invoice (FR-009).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from ...db.connection import DatabricksWarehousePool
from .uc_usage_column_filters import COST_BY_TABLE_COLUMNS, compile_column_filters, sort_sql
from .uc_usage_common import (
    GOLD_FORECAST_DAILY,
    GOLD_TABLE_CATALOG,
    GOLD_TABLE_DAILY,
    GOLD_TABLE_POPULARITY_DAILY,
    as_float,
    date_conditions,
    deleted_table_conditions,
    guarded,
    integer,
    iso,
    lifecycle_cte,
    lifecycle_fields,
    number,
    object_filters,
    object_id_filters,
    offset_of,
    page_envelope,
    search_condition,
    where_clause,
)

__all__ = [
    "COST_BY_TABLE_SORTS",
    "FORECAST_METRICS",
    "fetch_cost_by_table",
    "fetch_finops_kpis",
    "fetch_forecast_series",
    "fetch_observed_series",
    "fetch_usage_trends",
]

FORECAST_METRICS: tuple[str, ...] = (
    "request_count",
    "distinct_consumers",
    "estimated_cost_usd",
    "data_read_bytes",
)

_COST_METRIC = "estimated_cost_usd"

# Tri de « Cost by table ». Chaque clé désigne une colonne affichée, y compris les
# deux dérivées : elles sont calculées dans la requête, donc triables comme les autres.
_COST_SORT_SQL: dict[str, str] = {
    "cost": "estimated_cost_usd",
    "cost_per_request": "cost_per_request_usd",
    "requests": "request_count",
    "read_bytes": "data_read_bytes",
    "forecast": "forecast_cost_usd_7d",
    "table_name": "table_full_name",
}
COST_BY_TABLE_SORTS: tuple[str, ...] = tuple(_COST_SORT_SQL)

# Horizon annoncé par l'UI (« +7d ») et produit par le pipeline gold
# (`FORECAST_HORIZON_DAYS`). La borne HAUTE n'est pas décorative : sans elle,
# « +7d » désigne en réalité tout ce que la table contient au-delà d'aujourd'hui.
_HORIZON_DAYS = 7

# ``forecast_daily`` est écrite en MERGE sur
# ``(cloud_provider, object_type, object_id, metric_name, horizon_date)`` : les
# horizons des exécutions précédentes ne sont jamais supprimés. Sans ces bornes,
# une « prévision » commencerait des semaines dans le passé et cumulerait, pour une
# même journée, ce que plusieurs runs avaient prédit — ce qui n'est ni une mesure
# ni une prévision.
_FUTURE_HORIZON = (
    f"horizon_date >= current_date() AND horizon_date < date_add(current_date(), {_HORIZON_DAYS})"
)


async def fetch_forecast_series(
    db: DatabricksWarehousePool,
    *,
    catalog: str | None = None,
    schema: str | None = None,
    tables: list[str] | None = None,
    metrics: list[str] | None = None,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    """Forecast series summed over the tables in scope.

    A metric with no forecast row is **absent** from the result, never present at
    zero: ``ai_forecast`` produces nothing for a table without recent activity, and
    a flat zero line would read as a prediction of no usage.

    ``distinct_consumers`` is summed across tables, so it is an upper bound — the
    same consumer reading two tables counts twice. The UI labels it as such.
    """
    wanted = [
        metric for metric in (metrics or list(FORECAST_METRICS)) if metric in FORECAST_METRICS
    ]
    if not wanted:
        return []

    conditions = [f"metric_name IN ({', '.join('?' for _ in wanted)})", _FUTURE_HORIZON]
    params: list[Any] = list(wanted)
    object_conditions, object_params = object_id_filters(catalog, schema, tables)
    conditions.extend(object_conditions)
    params.extend(object_params)
    # Gold already excludes deleted tables from the forecast; the predicate keeps
    # the API's answer consistent even if a run predates spec 027. Consumer-grain
    # rows are untouched: their ``object_id`` is not a table name.
    conditions.extend(deleted_table_conditions(db, include_deleted, column="object_id"))

    rows = await guarded(
        db,
        db.fetchall(
            f"""
            SELECT
                metric_name,
                horizon_date,
                SUM(predicted_value) AS predicted_value,
                SUM(lower_bound) AS lower_bound,
                SUM(upper_bound) AS upper_bound
            FROM {db.table(GOLD_FORECAST_DAILY)}
            {where_clause(conditions)}
            GROUP BY metric_name, horizon_date
            ORDER BY metric_name ASC, horizon_date ASC
            """,
            *params,
        ),
        tables=[GOLD_FORECAST_DAILY, GOLD_TABLE_CATALOG],
    )

    series: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        series.setdefault(row["metric_name"], []).append(
            {
                "horizon_date": iso(row["horizon_date"]),
                "predicted_value": number(row["predicted_value"], decimals=4),
                "lower_bound": number(row["lower_bound"], decimals=4),
                "upper_bound": number(row["upper_bound"], decimals=4),
            }
        )

    return [
        {"metric_name": metric, "points": series[metric]} for metric in wanted if metric in series
    ]


async def fetch_observed_series(
    db: DatabricksWarehousePool,
    *,
    start: date,
    end: date,
    catalog: str | None = None,
    schema: str | None = None,
    tables: list[str] | None = None,
    metrics: list[str] | None = None,
    include_deleted: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    """Réalisé quotidien des quatre métriques, sur la période demandée.

    Même agrégation que la prévision — somme sur les tables du périmètre —
    pour que les deux courbes soient comparables : ``distinct_consumers`` est
    donc un majorant des deux côtés, jamais un compte de consommateurs uniques.

    Le jour en cours est exclu, comme il l'est de l'entraînement du modèle : il
    n'est chargé que partiellement (mesuré en dev à la mi-journée : ~1,5 M
    requêtes contre ~5,5 M sur une journée pleine), et le tracer en fin de
    courbe donnerait à lire un effondrement là où il n'y a qu'une journée
    inachevée. La prévision reprend exactement là où il s'arrête.

    La série porte **un point par jour calendaire**, pas un point par ligne
    trouvée : ``table_popularity_daily`` n'a de ligne qu'un jour où la table est
    lue, et rendre les seuls jours présents refermerait silencieusement les
    trous — une table lue trois jours sur trente se lirait comme une activité
    continue. Un jour sans mesure vaut ``None``, jamais ``0`` (SC-005).
    """
    wanted = [
        metric for metric in (metrics or list(FORECAST_METRICS)) if metric in FORECAST_METRICS
    ]
    if not wanted:
        return {}

    conditions, params = date_conditions(start, end)
    conditions.append("period_start < current_date()")
    object_conditions, object_params = object_filters(catalog, schema, tables)
    conditions.extend(object_conditions)
    params.extend(object_params)
    conditions.extend(deleted_table_conditions(db, include_deleted))

    rows = await guarded(
        db,
        db.fetchall(
            f"""
            SELECT
                period_start,
                SUM(request_count) AS request_count,
                SUM(distinct_consumers) AS distinct_consumers,
                SUM(estimated_cost_usd) AS estimated_cost_usd,
                SUM(data_read_bytes) AS data_read_bytes
            FROM {db.table(GOLD_TABLE_POPULARITY_DAILY)}
            {where_clause(conditions)}
            GROUP BY period_start
            ORDER BY period_start ASC
            """,
            *params,
        ),
        tables=[GOLD_TABLE_POPULARITY_DAILY, GOLD_TABLE_CATALOG],
    )

    by_date = {iso(row["period_start"]): row for row in rows}
    last_day = min(end, datetime.now(UTC).date() - timedelta(days=1))
    days = [
        (start + timedelta(days=offset)).isoformat()
        for offset in range((last_day - start).days + 1)
    ]

    return {
        metric: [
            {"period_start": day, "value": number(by_date.get(day, {}).get(metric), decimals=4)}
            for day in days
        ]
        for metric in wanted
    }


async def fetch_usage_trends(
    db: DatabricksWarehousePool,
    *,
    start: date | None = None,
    end: date | None = None,
    catalog: str | None = None,
    schema: str | None = None,
    tables: list[str] | None = None,
    metrics: list[str] | None = None,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    """Réalisé puis prévision, par métrique — dans cet ordre, jamais mélangés.

    Sans période, seule la prévision est renvoyée : le réalisé n'existe qu'entre
    deux bornes, et l'API n'en invente aucune (FR-017).
    """
    forecast = {
        entry["metric_name"]: entry["points"]
        for entry in await fetch_forecast_series(
            db,
            catalog=catalog,
            schema=schema,
            tables=tables,
            metrics=metrics,
            include_deleted=include_deleted,
        )
    }
    observed: dict[str, list[dict[str, Any]]] = {}
    if start is not None and end is not None:
        observed = await fetch_observed_series(
            db,
            start=start,
            end=end,
            catalog=catalog,
            schema=schema,
            tables=tables,
            metrics=metrics,
            include_deleted=include_deleted,
        )

    wanted = [
        metric for metric in (metrics or list(FORECAST_METRICS)) if metric in FORECAST_METRICS
    ]
    return [
        {
            "metric_name": metric,
            "observed": observed.get(metric, []),
            "points": forecast.get(metric, []),
        }
        for metric in wanted
        # Une métrique sans aucune des deux séries est absente, jamais à zéro (SC-005).
        if observed.get(metric) or forecast.get(metric)
    ]


async def fetch_finops_kpis(
    db: DatabricksWarehousePool,
    *,
    start: date,
    end: date,
    catalog: str | None = None,
    schema: str | None = None,
    tables: list[str] | None = None,
    include_deleted: bool = False,
) -> dict[str, Any]:
    conditions, params = date_conditions(start, end)
    object_conditions, object_params = object_filters(catalog, schema, tables)
    conditions.extend(object_conditions)
    params.extend(object_params)
    # Applied to both queries below, so neither the total nor the most expensive
    # table can come from a table the caller asked not to see.
    conditions.extend(deleted_table_conditions(db, include_deleted))
    where = where_clause(conditions)
    popularity = db.table(GOLD_TABLE_POPULARITY_DAILY)

    summary = await guarded(
        db,
        db.fetchone(
            f"""
            SELECT
                SUM(estimated_cost_usd) AS total_cost_usd,
                COALESCE(SUM(request_count), 0) AS request_count,
                COUNT(DISTINCT table_full_name) AS costed_tables
            FROM {popularity}
            {where}
            """,
            *params,
        ),
        tables=[GOLD_TABLE_POPULARITY_DAILY, GOLD_TABLE_CATALOG],
    )

    # Sum per table first, then take the maximum: a MAX over daily rows would
    # return the most expensive day, not the most expensive table.
    top = await guarded(
        db,
        db.fetchone(
            f"""
            SELECT table_full_name, SUM(estimated_cost_usd) AS estimated_cost_usd
            FROM {popularity}
            {where}
            GROUP BY table_full_name
            HAVING SUM(estimated_cost_usd) IS NOT NULL
            ORDER BY estimated_cost_usd DESC
            LIMIT 1
            """,
            *params,
        ),
        tables=[GOLD_TABLE_POPULARITY_DAILY, GOLD_TABLE_CATALOG],
    )

    row = summary or {}
    total_cost = as_float(row.get("total_cost_usd"))
    request_count = integer(row.get("request_count"))
    avg_cost = (
        round(total_cost / request_count, 6)
        if total_cost is not None and request_count > 0
        else None
    )

    return {
        "total_cost_usd": number(total_cost, decimals=2),
        "request_count": request_count,
        "costed_tables": integer(row.get("costed_tables")),
        "avg_cost_per_request_usd": avg_cost,
        # The denominator counts every request, including those whose cost could
        # not be attributed (``costed_request_count`` is not exposed at this
        # grain), so the ratio can only understate the real cost per request.
        "is_lower_bound": True,
        "top_costly_table": (
            {
                "table_full_name": top["table_full_name"],
                "estimated_cost_usd": number(top["estimated_cost_usd"], decimals=2),
            }
            if top
            else None
        ),
        "period": {"start": start.isoformat(), "end": end.isoformat()},
    }


async def fetch_cost_by_table(
    db: DatabricksWarehousePool,
    *,
    start: date,
    end: date,
    catalog: str | None = None,
    schema: str | None = None,
    tables: list[str] | None = None,
    search: str | None = None,
    sort: str = "cost",
    direction: str = "desc",
    column_filter: list[str] | None = None,
    page: int = 1,
    page_size: int = 25,
    include_deleted: bool = False,
) -> dict[str, Any]:
    conditions, params = date_conditions(start, end)
    object_conditions, object_params = object_filters(catalog, schema, tables)
    conditions.extend(object_conditions)
    params.extend(object_params)
    search_conditions, search_params = search_condition(search, columns=["table_full_name"])
    conditions.extend(search_conditions)
    params.extend(search_params)
    conditions.extend(deleted_table_conditions(db, include_deleted))
    where = where_clause(conditions)
    popularity = db.table(GOLD_TABLE_POPULARITY_DAILY)

    # Les deux colonnes dérivées sont calculées ici, pas en Python : c'est ce qui
    # les rend triables et filtrables sur la période entière, avant la pagination.
    ctes = f"""WITH pop AS (
            SELECT
                table_full_name,
                SUM(estimated_cost_usd) AS estimated_cost_usd,
                SUM(request_count) AS request_count,
                SUM(data_read_bytes) AS data_read_bytes
            FROM {popularity}
            {where}
            GROUP BY table_full_name
        ),
        forecast AS (
            SELECT object_id, SUM(predicted_value) AS forecast_cost_usd_7d
            FROM {db.table(GOLD_FORECAST_DAILY)}
            WHERE metric_name = ? AND {_FUTURE_HORIZON}
            GROUP BY object_id
        ),
        {lifecycle_cte(db)},
        joined AS (
            SELECT
                pop.table_full_name,
                pop.estimated_cost_usd,
                pop.request_count,
                pop.data_read_bytes,
                forecast.forecast_cost_usd_7d,
                CASE
                    WHEN pop.request_count > 0
                    THEN pop.estimated_cost_usd / pop.request_count
                END AS cost_per_request_usd,
                life.is_deleted,
                life.deleted_at,
                life.lifecycle_state
            FROM pop
            LEFT JOIN forecast ON forecast.object_id = pop.table_full_name
            LEFT JOIN life ON life.table_full_name = pop.table_full_name
        )"""
    filter_where, filter_params = compile_column_filters(column_filter, COST_BY_TABLE_COLUMNS)
    order_by = sort_sql(sort, direction, _COST_SORT_SQL, "cost")

    # Compté sur ``joined`` et non sur la table de faits : le total doit décrire
    # l'ensemble filtré, faute de quoi la pagination annonce des pages vides.
    total = await guarded(
        db,
        db.fetchscalar(
            f"{ctes} SELECT COUNT(*) FROM joined {filter_where}",
            *params,
            _COST_METRIC,
            *filter_params,
        ),
        tables=[GOLD_TABLE_POPULARITY_DAILY, GOLD_FORECAST_DAILY, GOLD_TABLE_CATALOG],
    )

    rows = await guarded(
        db,
        db.fetchall(
            f"{ctes} SELECT * FROM joined {filter_where} "
            f"ORDER BY {order_by}, table_full_name ASC LIMIT ? OFFSET ?",
            *params,
            _COST_METRIC,
            *filter_params,
            page_size,
            offset_of(page, page_size),
        ),
        tables=[GOLD_TABLE_POPULARITY_DAILY, GOLD_FORECAST_DAILY, GOLD_TABLE_CATALOG],
    )

    items: list[dict[str, Any]] = [
        {
            "table_full_name": row["table_full_name"],
            "estimated_cost_usd": number(as_float(row["estimated_cost_usd"]), decimals=2),
            "request_count": number(row["request_count"]),
            "data_read_bytes": number(row["data_read_bytes"]),
            "cost_per_request_usd": number(row["cost_per_request_usd"], decimals=6),
            # NULL when the table has no forecast row — a dash in the UI, not 0.
            "forecast_cost_usd_7d": number(row["forecast_cost_usd_7d"], decimals=2),
            **lifecycle_fields(row),
        }
        for row in rows
    ]

    return page_envelope(items, integer(total), page, page_size, start, end)


async def fetch_written_bytes_series(
    db: DatabricksWarehousePool,
    *,
    start: date,
    end: date,
    catalog: str | None = None,
    schema: str | None = None,
    tables: list[str] | None = None,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    """Observed written volume per day — measured, never projected.

    ``SUM`` skips NULLs and returns NULL for an all-NULL day: that day had writes
    the model could not measure, which is not the same as a day without writes.
    """
    conditions, params = date_conditions(start, end)
    object_conditions, object_params = object_filters(catalog, schema, tables)
    conditions.extend(object_conditions)
    params.extend(object_params)
    conditions.extend(deleted_table_conditions(db, include_deleted))

    rows = await guarded(
        db,
        db.fetchall(
            f"""
            SELECT period_start, SUM(data_written_bytes) AS data_written_bytes
            FROM {db.table(GOLD_TABLE_DAILY)}
            {where_clause(conditions)}
            GROUP BY period_start
            ORDER BY period_start ASC
            """,
            *params,
        ),
        tables=[GOLD_TABLE_DAILY, GOLD_TABLE_CATALOG],
    )

    return [
        {
            "period_start": iso(row["period_start"]),
            "data_written_bytes": number(row["data_written_bytes"]),
        }
        for row in rows
    ]
