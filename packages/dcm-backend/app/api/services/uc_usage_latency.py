"""Period P95 latency rebuilt from the additive latency histogram (FR-022).

``latency_p95_ms`` is stored per (table, day) and percentiles do not add up: no
average nor maximum of daily P95s describes a multi-day period. The bucket
**counters** written by T001 do add up, so the period distribution is the
bucket-wise sum, and the P95 is interpolated inside the bucket where the
cumulative count crosses 95 %.

The interpolation is expressed in SQL, not in Python, so that ``sort=latency``
stays an ``ORDER BY`` on a paginated query. Ranking in Python would force every
in-scope table — not just the requested page — to be loaded first.

Precision is bounded by bucket width — an accepted trade-off (D10), not an
approximation to hide.
"""

from __future__ import annotations

__all__ = [
    "LATENCY_BUCKET_OVERFLOW_KEY",
    "LATENCY_BUCKET_UPPER_BOUNDS_MS",
    "LATENCY_PERCENTILE",
    "latency_p95_ctes",
]

# Contract shared with ``pipelines.gold_dbx_usage.specs`` — the keys of the MAP
# written in gold. Changing them makes already-written history non-additive.
LATENCY_BUCKET_UPPER_BOUNDS_MS: tuple[int, ...] = (
    10,
    25,
    50,
    100,
    250,
    500,
    1_000,
    2_500,
    5_000,
    10_000,
    30_000,
    60_000,
    300_000,
)
LATENCY_BUCKET_OVERFLOW_KEY = "inf"
LATENCY_PERCENTILE = 0.95


def _bucket_bounds() -> list[tuple[str, int, int | None]]:
    """``(clé du MAP, borne basse exclue, borne haute incluse)`` par bucket.

    La borne basse d'un bucket est la borne haute du précédent, qu'il porte des
    compteurs ou non : c'est l'intervalle dans lequel l'interpolation a lieu.
    """
    bounds: list[tuple[str, int, int | None]] = []
    lower = 0
    for upper in LATENCY_BUCKET_UPPER_BOUNDS_MS:
        bounds.append((str(upper), lower, upper))
        lower = upper
    bounds.append((LATENCY_BUCKET_OVERFLOW_KEY, lower, None))
    return bounds


def _case(column: str, mapping: dict[str, str]) -> str:
    # Les clés viennent des constantes du module, jamais de l'appelant.
    whens = " ".join(f"WHEN '{key}' THEN {value}" for key, value in mapping.items())
    return f"CASE {column} {whens} ELSE NULL END"


def latency_p95_ctes(query_performance_table: str, where: str) -> str:
    """CTE chain ending in ``lat(table_full_name, latency_p95_ms)``.

    ``where`` bornes the period and the catalogue scope; it carries the caller's
    placeholders, so its parameters must be appended in CTE order.

    A table whose period holds no measured statement produces **no row** here — the
    ``LEFT JOIN`` then yields ``NULL``, never a fabricated 0.
    """
    bounds = _bucket_bounds()
    lower_sql = _case("bucket", {key: str(low) for key, low, _ in bounds})
    upper_sql = _case("bucket", {key: ("NULL" if up is None else str(up)) for key, _, up in bounds})
    order_sql = _case("bucket", {key: str(index) for index, (key, _, _) in enumerate(bounds)})

    return f"""
        lat_buckets AS (
            SELECT table_full_name, bucket, SUM(bucket_count) AS bucket_count
            FROM (
                SELECT
                    table_full_name,
                    explode(latency_bucket_counts) AS (bucket, bucket_count)
                FROM {query_performance_table}
                {where}
            )
            GROUP BY table_full_name, bucket
        ),
        lat_bounded AS (
            SELECT
                table_full_name,
                bucket_count,
                {lower_sql} AS bucket_lower,
                {upper_sql} AS bucket_upper,
                {order_sql} AS bucket_order
            FROM lat_buckets
            WHERE bucket_count > 0
        ),
        lat_cumulative AS (
            SELECT
                table_full_name,
                bucket_lower,
                bucket_upper,
                bucket_count,
                bucket_order,
                SUM(bucket_count) OVER (
                    PARTITION BY table_full_name
                    ORDER BY bucket_order
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS cumulative_count,
                SUM(bucket_count) OVER (PARTITION BY table_full_name) AS total_count
            FROM lat_bounded
            WHERE bucket_order IS NOT NULL
        ),
        lat AS (
            SELECT
                table_full_name,
                ROUND(
                    MIN_BY(
                        CASE
                            WHEN bucket_upper IS NULL THEN bucket_lower
                            ELSE bucket_lower
                                 + (total_count * {LATENCY_PERCENTILE}
                                    - (cumulative_count - bucket_count))
                                   / bucket_count
                                   * (bucket_upper - bucket_lower)
                        END,
                        bucket_order
                    ),
                    1
                ) AS latency_p95_ms
            FROM lat_cumulative
            WHERE cumulative_count >= total_count * {LATENCY_PERCENTILE}
            GROUP BY table_full_name
        )
    """
