#!/usr/bin/env python3
"""Unity Catalog explorer for DCM (skill dcm-uc-validator) — read-only SQL Warehouse access.

Inspired by repo-root ``our_catalogs_spn.py``. Loads credentials from
``packages/dcm-backend/.env`` (``DCM_*`` vars). Use from any AI agent
(Cursor / Copilot / Claude) to inspect tables and validate UI/maquette data refs.

Examples::

    python packages/dcm-backend/scripts/uc_explorer.py --env dev ping
    python packages/dcm-backend/scripts/uc_explorer.py --env prod tables
    python packages/dcm-backend/scripts/uc_explorer.py --env dev describe dim_landing_zone
    python packages/dcm-backend/scripts/uc_explorer.py --env dev sample dim_landing_zone --limit 5
    python packages/dcm-backend/scripts/uc_explorer.py --env dev query \\
        "SELECT lz_id, cloud_provider FROM dim_landing_zone LIMIT 10"
    python packages/dcm-backend/scripts/uc_explorer.py --env dev check-tables \\
        dim_landing_zone gold_data_product_usage
    python packages/dcm-backend/scripts/uc_explorer.py --env dev extract-refs \\
        packages/dcm-frontend/src/pages/DashboardPage.tsx maquette/maquette_overview.html

Requires: databricks-sql-connector, databricks-sdk, python-dotenv
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

# scripts/ → dcm-backend/ → .env (same layout as check_databricks_spn.py / Settings)
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_ENV_PATH = _BACKEND_ROOT / ".env"

# Azure AD resource ID for Azure Databricks (same as app/db/connection.py).
_AZURE_DATABRICKS_SCOPE = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default"

SCHEMA_BY_ENV = {
    "dev": "ba_data_connect_monitoring__d",
    "prod": "ba_data_connect_monitoring__p",
}

# Read-only statement prefixes (case-insensitive, after strip).
_ALLOWED_SQL_PREFIXES = (
    "select",
    "show",
    "describe",
    "desc",
    "explain",
    "with",  # CTEs that must still be SELECT-only (checked separately)
)

# Patterns that usually mean a Unity Catalog / DCM table reference.
_TABLE_REF_RE = re.compile(
    r"""
    (?:
        # Fully qualified: catalog.schema.table or `c`.`s`.`t`
        (?:`?[a-zA-Z_][\w]*`?\.){1,2}`?([a-zA-Z_][\w]*)`?
        |
        # Bare DCM-ish table names in source / HTML
        \b(
            (?:gold|curated|dim|raw|dcm|fact|bridge)_[a-zA-Z0-9_]+
            |
            system\.[a-zA-Z0-9_.]+
        )\b
    )
    """,
    re.VERBOSE,
)

_FORBIDDEN_SQL_RE = re.compile(
    r"\b(insert|update|delete|merge|drop|create|alter|truncate|grant|revoke|"
    r"copy|vacuum|optimize|restore|msck|replace|call|execute)\b",
    re.IGNORECASE,
)

# Cap agent queries — warehouse DBU cost. SHOW/DESCRIBE/EXPLAIN are exempt.
_MAX_QUERY_LIMIT = 100
_LIMIT_RE = re.compile(r"\blimit\s+(\d+)\b", re.IGNORECASE)
# Aggregations / wide scans without an explicit escape hatch.
_EXPENSIVE_SQL_RE = re.compile(
    r"\bcount\s*\(\s*\*\s*\)"
    r"|\bsum\s*\("
    r"|\bavg\s*\("
    r"|\bgroup\s+by\b"
    r"|\bcross\s+join\b",
    re.IGNORECASE,
)
_METADATA_SQL_PREFIXES = frozenset({"show", "describe", "desc", "explain"})


@dataclass(frozen=True)
class UcSettings:
    server_hostname: str
    http_path: str
    catalog: str
    schema: str
    client_id: str
    client_secret: str
    access_token: str | None
    profile: str | None
    entra_tenant_id: str


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        print(
            "WARN: python-dotenv missing — process env only "
            "(use packages/dcm-backend/.venv)",
            file=sys.stderr,
        )
        return
    if _ENV_PATH.exists():
        load_dotenv(_ENV_PATH, override=True)
        print(f"OK  loaded {_ENV_PATH}", file=sys.stderr)
    else:
        print(f"WARN: {_ENV_PATH} not found — using process env", file=sys.stderr)


def _normalize_host(raw: str) -> str:
    return raw.replace("https://", "").replace("http://", "").rstrip("/")


def resolve_settings(*, env: str, schema_override: str | None) -> UcSettings:
    _load_dotenv()

    access_token = os.environ.get("DCM_DATABRICKS_TOKEN") or os.environ.get(
        "DATABRICKS_TOKEN"
    )
    # Avoid SPN Config silently competing with a leftover DATABRICKS_TOKEN.
    os.environ.pop("DATABRICKS_TOKEN", None)

    profile = os.environ.get("DCM_DATABRICKS_PROFILE") or os.environ.get(
        "DATABRICKS_CONFIG_PROFILE"
    )

    profile_host: str | None = None
    if profile:
        from databricks.sdk.core import Config

        cfg = Config(profile=profile)
        if cfg.host:
            profile_host = _normalize_host(cfg.host)

    server_hostname = _normalize_host(
        os.environ.get("DCM_DATABRICKS_HOST")
        or profile_host
        or "dbc-89e8d3b6-20ad.cloud.databricks.com"
    )
    warehouse_id = os.environ.get("DCM_DATABRICKS_WAREHOUSE_ID", "")
    http_path = os.environ.get("DCM_DATABRICKS_HTTP_PATH") or (
        f"/sql/1.0/warehouses/{warehouse_id}" if warehouse_id else ""
    )
    catalog = os.environ.get("DCM_DATABRICKS_CATALOG", "it")
    schema = (
        schema_override
        or SCHEMA_BY_ENV.get(env)
        or os.environ.get("DCM_DATABRICKS_SCHEMA")
        or SCHEMA_BY_ENV["dev"]
    )
    client_id = os.environ.get("DCM_DATABRICKS_SPN_CLIENT_ID", "")
    client_secret = os.environ.get("DCM_DATABRICKS_SPN_CLIENT_SECRET", "")
    entra_tenant_id = os.environ.get("DCM_ENTRA_TENANT_ID", "")

    if not http_path:
        raise SystemExit(
            "FAIL: set DCM_DATABRICKS_WAREHOUSE_ID or DCM_DATABRICKS_HTTP_PATH "
            f"in {_ENV_PATH}"
        )
    if not access_token and not client_secret and not profile:
        raise SystemExit(
            "FAIL: set DCM_DATABRICKS_TOKEN, DCM_DATABRICKS_PROFILE, or "
            f"DCM_DATABRICKS_SPN_CLIENT_SECRET in {_ENV_PATH}"
        )

    return UcSettings(
        server_hostname=server_hostname,
        http_path=http_path,
        catalog=catalog,
        schema=schema,
        client_id=client_id,
        client_secret=client_secret,
        access_token=access_token,
        profile=profile,
        entra_tenant_id=entra_tenant_id,
    )


def qualified_table(settings: UcSettings, table_name: str) -> str:
    if "." in table_name.replace("`", ""):
        # Already qualified — normalize backticks lightly.
        parts = [p.strip("`") for p in table_name.split(".")]
        return ".".join(f"`{p}`" for p in parts)
    return f"`{settings.catalog}`.`{settings.schema}`.`{table_name}`"


def _fetch_azure_aad_token(settings: UcSettings) -> str:
    """Exchange Entra SPN credentials for an Azure Databricks access token.

    Mirrors ``app/db/connection.py::_fetch_azure_aad_token`` — required when
    ``DCM_ENTRA_TENANT_ID`` is set (Azure AD app registration, not a Databricks-
    managed service principal).
    """
    import httpx

    tenant = settings.entra_tenant_id.strip()
    if not tenant:
        raise SystemExit("FAIL: DCM_ENTRA_TENANT_ID is required for Azure AD SPN auth")

    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": settings.client_id,
        "client_secret": settings.client_secret,
        "scope": _AZURE_DATABRICKS_SCOPE,
    }
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, data=data)
        if response.status_code >= 400:
            detail = response.text[:300]
            raise SystemExit(
                f"FAIL: Azure AD token request failed ({response.status_code}): {detail}"
            )
        token = response.json().get("access_token")
        if not token:
            raise SystemExit("FAIL: Azure AD token response missing access_token")
        return str(token)


def _credentials_provider(settings: UcSettings):
    """Same auth order as ``DatabricksWarehousePool`` / ``_credential_provider``."""
    from databricks.sdk.core import Config, oauth_service_principal

    def _provider():
        if settings.entra_tenant_id.strip():

            def _azure_headers() -> dict[str, str]:
                token = _fetch_azure_aad_token(settings)
                return {"Authorization": f"Bearer {token}"}

            return _azure_headers

        config = Config(
            host=f"https://{settings.server_hostname}",
            client_id=settings.client_id,
            client_secret=settings.client_secret,
        )
        return oauth_service_principal(config)

    return _provider


def connect(settings: UcSettings):
    from databricks import sql
    from databricks.sdk.core import Config

    kwargs: dict[str, object] = {
        "server_hostname": settings.server_hostname,
        "http_path": settings.http_path,
        "catalog": settings.catalog,
        "schema": settings.schema,
    }
    if settings.access_token:
        kwargs["access_token"] = settings.access_token
    elif settings.profile:
        profile_config = Config(profile=settings.profile)
        kwargs["credentials_provider"] = lambda: profile_config.authenticate
    elif settings.client_id and settings.client_secret:
        kwargs["credentials_provider"] = _credentials_provider(settings)
    else:
        raise SystemExit("FAIL: no Databricks credentials resolved from .env")
    return sql.connect(**kwargs)


def assert_readonly_sql(statement: str) -> str:
    cleaned = dedent(statement).strip().rstrip(";")
    if not cleaned:
        raise SystemExit("FAIL: empty SQL")
    if ";" in cleaned:
        raise SystemExit("FAIL: multiple statements not allowed")
    if _FORBIDDEN_SQL_RE.search(cleaned):
        raise SystemExit(
            "FAIL: only read-only SQL is allowed (SELECT/SHOW/DESCRIBE/EXPLAIN/WITH)"
        )
    head = cleaned.lstrip("(").lstrip().split(None, 1)[0].lower()
    if head not in _ALLOWED_SQL_PREFIXES:
        raise SystemExit(
            f"FAIL: statement must start with {_ALLOWED_SQL_PREFIXES}, got '{head}'"
        )
    if head == "with" and not re.search(r"\bselect\b", cleaned, re.IGNORECASE):
        raise SystemExit("FAIL: WITH must wrap a SELECT")
    return cleaned


def assert_cheap_sql(statement: str, *, allow_expensive: bool = False) -> str:
    """Block unbounded / costly SELECT patterns used by agents by mistake.

    - SHOW / DESCRIBE / EXPLAIN: allowed as-is
    - SELECT / WITH: must include ``LIMIT n`` with ``n <= 100``
    - COUNT(*)/SUM/AVG/GROUP BY/CROSS JOIN: require ``--allow-expensive``
    """
    cleaned = assert_readonly_sql(statement)
    head = cleaned.lstrip("(").lstrip().split(None, 1)[0].lower()
    if head in _METADATA_SQL_PREFIXES:
        return cleaned

    limits = [int(n) for n in _LIMIT_RE.findall(cleaned)]
    if not limits:
        raise SystemExit(
            f"FAIL: SELECT/WITH must include LIMIT ≤ {_MAX_QUERY_LIMIT} "
            "(use `sample` for previews, or pass --allow-expensive only if intentional)"
        )
    if limits[-1] > _MAX_QUERY_LIMIT:
        raise SystemExit(
            f"FAIL: LIMIT {limits[-1]} exceeds max {_MAX_QUERY_LIMIT} "
            "(raise only via sample --limit ≤ 100)"
        )

    if not allow_expensive and _EXPENSIVE_SQL_RE.search(cleaned):
        raise SystemExit(
            "FAIL: aggregation / CROSS JOIN looks expensive — prefer "
            "`sample` / `check-tables`, or re-run with --allow-expensive"
        )
    return cleaned


def assert_env_allowed(env: str, *, allow_prod: bool) -> None:
    if env == "prod" and not allow_prod:
        raise SystemExit(
            "FAIL: --env prod requires --allow-prod "
            "(prod warehouse queries can be costly)"
        )


def _print_rows(columns: list[str], rows: list[tuple], *, as_json: bool) -> None:
    if as_json:
        payload = [dict(zip(columns, row, strict=False)) for row in rows]
        print(json.dumps(payload, default=str, indent=2))
        return
    if not columns:
        print("(no columns)")
        return
    widths = [len(c) for c in columns]
    str_rows = [[("" if v is None else str(v)) for v in row] for row in rows]
    for row in str_rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], min(len(cell), 64))
    header = " | ".join(c.ljust(widths[i]) for i, c in enumerate(columns))
    sep = "-+-".join("-" * w for w in widths)
    print(header)
    print(sep)
    for row in str_rows:
        print(
            " | ".join(
                (cell if len(cell) <= 64 else cell[:61] + "...").ljust(widths[i])
                for i, cell in enumerate(row)
            )
        )
    print(f"\n({len(rows)} row(s))")


def cmd_ping(settings: UcSettings, *, as_json: bool) -> int:
    with connect(settings) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 AS ok")
        rows = cur.fetchall()
        info = {
            "ok": True,
            "host": settings.server_hostname,
            "http_path": settings.http_path,
            "catalog": settings.catalog,
            "schema": settings.schema,
            "select_1": rows[0][0] if rows else None,
        }
        if as_json:
            print(json.dumps(info, indent=2))
        else:
            print(
                f"OK — connected host={settings.server_hostname} "
                f"catalog=`{settings.catalog}` schema=`{settings.schema}`"
            )
    return 0


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def cmd_tables(settings: UcSettings, *, like: str | None, as_json: bool) -> int:
    with connect(settings) as conn, conn.cursor() as cur:
        base = f"SHOW TABLES IN `{settings.catalog}`.`{settings.schema}`"
        if like:
            cur.execute(f"{base} LIKE {_sql_literal(like)}")
        else:
            cur.execute(base)
        raw = cur.fetchall()
        # SHOW TABLES → database, tableName, isTemporary
        names = sorted(row[1] for row in raw)
        if as_json:
            print(json.dumps({"schema": settings.schema, "tables": names}, indent=2))
        else:
            print(f"Tables in `{settings.catalog}`.`{settings.schema}` ({len(names)}):")
            for name in names:
                print(f"  - {name}")
    return 0


def cmd_describe(settings: UcSettings, table: str, *, as_json: bool) -> int:
    with connect(settings) as conn, conn.cursor() as cur:
        fq = qualified_table(settings, table)
        cur.execute(f"DESCRIBE TABLE {fq}")
        rows = cur.fetchall()
        columns = [
            {"name": row[0], "type": row[1], "comment": row[2] if len(row) > 2 else None}
            for row in rows
            if row and row[0] and not str(row[0]).startswith("#")
        ]
        if as_json:
            print(json.dumps({"table": fq, "columns": columns}, indent=2, default=str))
        else:
            print(f"Columns of {fq} ({len(columns)}):")
            for col in columns:
                print(f"  - {col['name']}: {col['type']}")
    return 0


def cmd_sample(
    settings: UcSettings, table: str, *, limit: int, as_json: bool
) -> int:
    if limit < 1 or limit > 100:
        raise SystemExit("FAIL: --limit must be between 1 and 100")
    sql = f"SELECT * FROM {qualified_table(settings, table)} LIMIT {limit}"
    return cmd_query(settings, sql, as_json=as_json)


def cmd_query(
    settings: UcSettings,
    statement: str,
    *,
    as_json: bool,
    allow_expensive: bool = False,
) -> int:
    cleaned = assert_cheap_sql(statement, allow_expensive=allow_expensive)
    with connect(settings) as conn, conn.cursor() as cur:
        cur.execute(cleaned)
        rows = cur.fetchall()
        columns = [d[0] for d in (cur.description or [])]
        _print_rows(columns, rows, as_json=as_json)
    return 0


def cmd_check_tables(
    settings: UcSettings, tables: list[str], *, as_json: bool
) -> int:
    with connect(settings) as conn, conn.cursor() as cur:
        cur.execute(f"SHOW TABLES IN `{settings.catalog}`.`{settings.schema}`")
        existing = {row[1].lower() for row in cur.fetchall()}

    results = []
    missing = 0
    for raw in tables:
        name = raw.strip("`").split(".")[-1]
        present = name.lower() in existing
        if not present:
            missing += 1
        results.append({"table": name, "exists": present})

    if as_json:
        print(
            json.dumps(
                {
                    "catalog": settings.catalog,
                    "schema": settings.schema,
                    "results": results,
                    "missing_count": missing,
                },
                indent=2,
            )
        )
    else:
        print(f"Check tables in `{settings.catalog}`.`{settings.schema}`:")
        for item in results:
            mark = "OK" if item["exists"] else "MISSING"
            print(f"  [{mark}] {item['table']}")
        print(f"\n{len(results) - missing}/{len(results)} present, {missing} missing")
    return 1 if missing else 0


def extract_table_refs(text: str) -> list[str]:
    found: set[str] = set()
    for match in _TABLE_REF_RE.finditer(text):
        candidate = next((g for g in match.groups() if g), None)
        if not candidate:
            continue
        lower = candidate.lower()
        if lower.startswith("system."):
            found.add(candidate)
            continue
        bare = candidate.split(".")[-1]
        bare_l = bare.lower()
        # Keep DCM table naming conventions; drop noisy field-like tokens.
        if not bare_l.startswith(
            ("gold_", "curated_", "dim_", "raw_", "dcm_", "fact_", "bridge_")
        ):
            continue
        found.add(bare)
    return sorted(found)


def cmd_extract_refs(paths: list[str], *, as_json: bool) -> int:
    all_refs: set[str] = set()
    per_file: dict[str, list[str]] = {}
    for path_str in paths:
        path = Path(path_str)
        if not path.is_file():
            print(f"WARN: not a file: {path}", file=sys.stderr)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        refs = extract_table_refs(text)
        per_file[str(path)] = refs
        all_refs.update(refs)

    payload = {
        "files": per_file,
        "unique_refs": sorted(all_refs),
        "count": len(all_refs),
    }
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        for file_path, refs in per_file.items():
            print(f"{file_path} ({len(refs)}):")
            for ref in refs:
                print(f"  - {ref}")
        print(f"\nUnique refs: {len(all_refs)}")
        for ref in sorted(all_refs):
            print(f"  - {ref}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--env",
        choices=("dev", "prod"),
        default="dev",
        help="Target schema suffix: __d (dev) or __p (prod). Default: dev",
    )
    common.add_argument(
        "--allow-prod",
        action="store_true",
        help="Required with --env prod (explicit opt-in for prod warehouse)",
    )
    common.add_argument(
        "--schema",
        default=None,
        help="Override DCM schema (else derived from --env / .env)",
    )
    common.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON",
    )

    parser = argparse.ArgumentParser(
        description="DCM Unity Catalog explorer (read-only) for agent validation.",
        parents=[common],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ping", parents=[common], help="Verify warehouse auth + SELECT 1")

    p_tables = sub.add_parser(
        "tables", parents=[common], help="List tables in catalog.schema"
    )
    p_tables.add_argument("--like", default=None, help="SHOW TABLES LIKE pattern")

    p_desc = sub.add_parser("describe", parents=[common], help="DESCRIBE TABLE")
    p_desc.add_argument("table", help="Table name (bare or catalog.schema.table)")

    p_sample = sub.add_parser("sample", parents=[common], help="SELECT * LIMIT N")
    p_sample.add_argument("table")
    p_sample.add_argument("--limit", type=int, default=5)

    p_query = sub.add_parser(
        "query",
        parents=[common],
        help="Run a cheap read-only SQL statement (SELECT needs LIMIT ≤ 100)",
    )
    p_query.add_argument("sql", help="SELECT / SHOW / DESCRIBE / EXPLAIN / WITH…SELECT")
    p_query.add_argument(
        "--allow-expensive",
        action="store_true",
        help="Allow COUNT(*)/aggregations/CROSS JOIN (still requires LIMIT ≤ 100)",
    )

    p_check = sub.add_parser(
        "check-tables", parents=[common], help="Verify table names exist"
    )
    p_check.add_argument("tables", nargs="+", help="Table names to check")

    p_extract = sub.add_parser(
        "extract-refs",
        parents=[common],
        help="Extract likely UC table refs from source/maquette files",
    )
    p_extract.add_argument("paths", nargs="+", help="Files to scan")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "extract-refs":
        return cmd_extract_refs(args.paths, as_json=args.json)

    assert_env_allowed(args.env, allow_prod=args.allow_prod)

    # Reject unsafe / expensive SQL before loading credentials / opening a connection.
    if args.command == "query":
        assert_cheap_sql(args.sql, allow_expensive=args.allow_expensive)

    settings = resolve_settings(env=args.env, schema_override=args.schema)
    as_json = args.json

    if args.command == "ping":
        return cmd_ping(settings, as_json=as_json)
    if args.command == "tables":
        return cmd_tables(settings, like=args.like, as_json=as_json)
    if args.command == "describe":
        return cmd_describe(settings, args.table, as_json=as_json)
    if args.command == "sample":
        return cmd_sample(settings, args.table, limit=args.limit, as_json=as_json)
    if args.command == "query":
        return cmd_query(
            settings,
            args.sql,
            as_json=as_json,
            allow_expensive=args.allow_expensive,
        )
    if args.command == "check-tables":
        return cmd_check_tables(settings, args.tables, as_json=as_json)

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
