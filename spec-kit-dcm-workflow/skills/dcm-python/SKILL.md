---
name: dcm-python
description: >-
  DCM Python best practices for AI agents — FastAPI backend, collectors, lambda,
  pipeline, dcm-commons. Machine-readable: compatibility matrix, Do/Don't,
  anti-patterns, quick reference. Use when writing or reviewing Python in
  packages/dcm-backend, dcm-commons, dcm-aws-collector, dcm-azure-collector,
  dcm-lambda-ingestion, dcm-databricks-pipeline.
compatibility: DCM monorepo packages/
metadata:
  author: DCM Squad
  domain: backend,dataeng
---

# DCM Python — Best Practices for AI Agents

Machine-readable companion for AI agents working in DCM Python packages.
Same rules as constitution + backend README — structured for fast pattern matching.

**Authority**: `.specify/memory/constitution.md`, `packages/dcm-backend/README.md`

## Compatibility Matrix

Pin to these versions or newer. Examples assume DCM monorepo layout.

| Dependency        | Minimum | DCM usage                                              |
|-------------------|---------|--------------------------------------------------------|
| Python            | 3.12    | Required — `StrEnum`, `\|` union syntax                |
| FastAPI           | 0.111   | `Annotated[T, Depends(...)]` idiomatic                 |
| Pydantic          | 2.0     | v1 APIs removed — no `.dict()`, no `json_encoders`     |
| pydantic-settings | 2.0     | `app/config/` — env vars, never secrets in repo        |
| httpx             | 0.27    | Tests: `AsyncClient` + `ASGITransport`                 |
| pytest            | 8.0     | + pytest-asyncio, `asyncio_mode = auto`                |
| ruff              | 0.4     | Lint — zero warnings on main                           |
| mypy              | 1.10    | strict on `app/`                                       |
| structlog         | 24.0    | JSON structured logging — no `print()`                 |
| databricks-sql    | 3.0     | Sync driver — **must** run via `asyncio.to_thread`     |

## Project Structure (dcm-backend)

Organize by domain route, not by file type only.

```
packages/dcm-backend/app/
├── main.py                    # FastAPI app, lifespan, router mount
├── config/                    # Settings (pydantic-settings)
├── db/
│   └── connection.py          # DatabricksWarehousePool + get_db
├── auth/
│   ├── dependencies.py        # JWT, get_allowed_lz_ids, RBAC
│   └── role_permissions.py
├── api/
│   ├── routes/{domain}.py     # Thin handlers — databricks, dashboard, admin_*
│   └── services/{domain}_bundle.py  # Multi-query aggregation
├── chat/                      # Genie chat service
└── notification/
packages/dcm-backend/tests/
├── conftest.py                # client, mock_db, auth_disabled
└── test_{domain}.py
```

**Other Python packages**

| Package                  | Role                                      |
|--------------------------|-------------------------------------------|
| `dcm-commons`            | Shared models, enums, `BaseCollector`     |
| `dcm-aws-collector`      | AWS metrics → Apigee                      |
| `dcm-azure-collector`    | Azure metrics → Apigee                    |
| `dcm-lambda-ingestion`   | SQS → raw ingestion                       |
| `dcm-databricks-pipeline`| PySpark DLT, Lakebase DDL                 |

**Cross-package imports**: absolute only. Never duplicate models outside `dcm-commons`.

## Async Routes

### Decision rule (DCM)

| Route does this                              | Use                                      |
|----------------------------------------------|------------------------------------------|
| `await db.fetchall(...)` (pool wraps thread) | `async def`                              |
| Direct sync Databricks/sql call              | **Never** in route — use pool methods    |
| CPU-bound > 50 ms                            | Offload worker / batch job               |
| Blocking `time.sleep` / `open()`             | **Never** in `async def`                 |

### Do / Don't

```python
# DON'T — sync blocking inside async route freezes event loop
@router.get("/bad")
async def bad():
    time.sleep(5)
    return {"ok": True}

# DO — async route + pool (pool uses asyncio.to_thread internally)
@router.get("/workspaces")
async def list_workspaces(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
) -> list[dict[str, Any]]:
    rows = await db.fetchall("SELECT ... WHERE cloud_provider = $1", provider)
    return [dict(r) for r in rows]

# DO — thin route, heavy logic in service module
from ..services.databricks_bundle import fetch_databricks_full

@router.get("/full")
async def get_databricks_full(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    ...
) -> dict[str, Any]:
    return await fetch_databricks_full(db, ...)
```

## Database — Databricks SQL Warehouse (not SQLAlchemy)

DCM uses `DatabricksWarehousePool` — sync `databricks-sql-connector` wrapped in `asyncio.to_thread`.

```python
# app/db/connection.py pattern
async def get_db(request: Request) -> DatabricksWarehousePool:
    pool = request.app.state.db_pool
    if pool is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return pool
```

### SQL rules

- **Parameterized only** — `$1`, `$2` with args tuple/list
- Never f-string user input into SQL
- LZ scoping via `_lz_filter.add_lz_filter()` + `get_allowed_lz_ids` dependency
- Prefer SQL for joins/aggregation; return dict rows to routes
- `DISTINCT ON` for latest state per entity when needed

## Dependencies

### Use Annotated

```python
from typing import Annotated
from fastapi import Depends, Query

WorkspaceIdQuery = Annotated[
    str | None,
    Query(description="Filter by workspace ID."),
]

@router.get("/items")
async def get_items(
    db: Annotated[DatabricksWarehousePool, Depends(get_db)],
    allowed_lz_ids: Annotated[list[str] | None, Depends(get_allowed_lz_ids)],
    workspace_id: WorkspaceIdQuery = None,
) -> list[dict[str, Any]]:
    ...
```

### Rules

- Dependencies cached per request — same `Depends(x)` runs once
- Auth: `get_allowed_lz_ids` on every LZ-scoped route
- Settings: `request.app.state.settings` or injected helper
- Validate in dependency when loading entity by ID

## Pydantic & Settings

```python
# app/config/__init__.py — single Settings, env_prefix DCM_
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DCM_", extra="ignore")
    auth_disabled: bool = False
    databricks_host: str = ""
    # secrets via ARN/env — never commit values
```

- Response shapes: typed `dict[str, Any]` or Pydantic models in route return
- No `Field(ge=18, default=None)` — constraint vs default conflict

## Authentication

- Prod: JWT at API Gateway; backend validates via `app/auth/dependencies.py`
- Tests: `auth_disabled_for_route_tests` fixture sets `settings.auth_disabled = True`
- Never log tokens, `Authorization` headers, or secret values
- RBAC: check `role_permissions` before admin mutations

## Logging

```python
import structlog
logger = structlog.get_logger(__name__)

logger.info("workspaces_listed", count=len(rows), cloud_provider=provider)
```

No `print()`. JSON structured logs in prod paths.

## Collectors (aws/azure)

- Extend `BaseCollector` from `dcm-commons`
- Output **MetricPayload** only — schema in commons
- Send via **Apigee** — no direct cross-LZ calls
- Secrets: Key Vault / Secrets Manager — never hardcoded

## Testing

### Async client — use project fixtures

```python
# tests/conftest.py — always use these
async def test_list_workspaces(client, mock_db):
    mock_db.fetchall.return_value = [
        {"workspace_id": "adb-123", "resource_name": "prod-eu", "display_name": "prod-eu"}
    ]
    resp = await client.get("/api/v1/databricks/workspaces")
    assert resp.status_code == 200
    assert resp.json()[0]["display_name"] == "prod-eu"
```

- `client` — httpx `AsyncClient` + `ASGITransport(app=app)`
- `mock_db` — `AsyncMock` replaces `app.state.db_pool`
- No real Databricks connection in unit tests
- New endpoint → new test file or extend existing domain tests

### Run from package dir

```bash
cd packages/dcm-backend
uv run pytest
uv run ruff check .
uv run mypy app
```

## Linting

```bash
ruff check .
ruff format .   # if configured
mypy app
```

CI + constitution: **zero warnings** on main.

---

## Anti-patterns — reject in review

| Anti-pattern | Why wrong | Fix |
|---|---|---|
| Sync I/O in `async def` route | Blocks event loop | Use pool async methods or `def` route |
| f-string SQL with user input | SQL injection | `$1` placeholders + args |
| New Pydantic model in backend only | Duplication | Add to `dcm-commons` |
| Relative import across packages | Breaks monorepo layout | Absolute imports |
| Hardcoded secret / PAT in code | Security violation | KV / Secrets Manager ARN |
| Missing test on new route | Constitution breach | pytest in `tests/` |
| `print()` debug | No observability | structlog |
| Direct cross-LZ HTTP from collector | Architecture violation | Apigee ingest only |
| Skip LZ filter on scoped data | Data leak | `get_allowed_lz_ids` + `_lz_filter` |
| Catching bare `Exception` in route | Hides bugs | Catch specific, re-raise HTTPException |

## Quick reference

| Scenario | Solution |
|----------|----------|
| List/filter DB rows | `async def` + `await db.fetchall(sql, *args)` |
| LZ-scoped query | `add_lz_filter(sql, allowed_lz_ids)` |
| Inject DB | `Annotated[DatabricksWarehousePool, Depends(get_db)]` |
| Inject auth scope | `Depends(get_allowed_lz_ids)` |
| Multi-query page data | `api/services/{domain}_bundle.py` |
| Unit test route | `client` + `mock_db` fixtures |
| Disable auth in test | autouse `auth_disabled_for_route_tests` |
| Shared enum/model | `dcm-commons` |
| Collector metric | `BaseCollector` → Apigee |
| Lint + types | `ruff check .` + `mypy app` |

## Spec-kit implement

When `/{speckit}implement` on backend task:
- Read `stories/T00X-*.md` only — not full epic spec
- Touch files in sub-spec ## Files only
- Package scope from `intake.json`
- After code: `/speckit.dcm.review --task T00X` — load **`dcm-verify`** first

## New Backend API — full checklist

When adding a **new API prefix** (new router mounted in `main.py`), agent MUST complete code **and** verify API Gateway — or **AskQuestion** for user to run AWS steps.

### Step 1 — Code (agent)

| # | File | Action |
|---|------|--------|
| 1 | `app/api/routes/{domain}.py` | New router + handlers |
| 2 | `app/main.py` | `include_router(..., prefix="/api/v1/{prefix}")` |
| 3 | `tests/test_{domain}.py` | pytest with `client` + `mock_db` |
| 4 | `scripts/sync-api-gateway-routes.sh` | Add line to `ROUTE_SPECS` (see below) |
| 5 | `packages/dcm-frontend/src/api/dcmApiClient.ts` | Client function if UI needs it |
| 6 | `packages/dcm-frontend/src/types/api.ts` | Response types |

Derive **API Gateway prefix** from mount path — first segment after `/api/v1/`:
- `prefix="/api/v1/databricks"` → `"databricks:jwt"`
- `prefix="/api/v1"` + route `/access-requests` → `"access-requests:none"` (public)

`ROUTE_SPECS` format in `scripts/sync-api-gateway-routes.sh`:

```bash
"my-prefix:jwt"              # proxy ANY + OPTIONS (default)
"my-prefix:none"             # public — no JWT at gateway
"my-prefix:jwt:exact"        # single path only (no /{proxy+})
"health:none:health"         # special health routes
```

### Step 2 — AWS SSO (agent tries, user completes if blocked)

```bash
aws sso login --profile dcm-sso
aws sts get-caller-identity --profile dcm-sso
```

| Result | Action |
|--------|--------|
| Login OK + identity returned | Continue Step 3 |
| Browser / device code required | **AskQuestion**: "Connecte-toi via navigateur SSO, puis dis Continue" |
| No AWS CLI / no profile | **AskQuestion**: user runs SSO manually or infra team |

Defaults (override via env): `AWS_PROFILE=dcm-sso`, `AWS_REGION=eu-central-1`, `DCM_APIGW_ID=h4b8ee6xja`.

### Step 3 — Check API Gateway routes (agent CAN run)

```bash
./scripts/sync-api-gateway-routes.sh --check
```

Lists missing `ANY` / `OPTIONS` routes vs `ROUTE_SPECS`. **Read-only** — safe to run.

### Step 4 — Apply routes (AskQuestion BEFORE write)

```bash
AWS_PROFILE=dcm-sso AWS_REGION=eu-central-1 ./scripts/sync-api-gateway-routes.sh
```

**Never run apply without user confirm** — modifies production API Gateway.

AskQuestion:

```
Nouvelle API {prefix} — routes Gateway manquantes: {N}

○ Oui — lancer sync-api-gateway-routes.sh (prod)
○ Non — je le fais moi-même / ticket infra
○ Dev local seulement — skip Gateway (Vite proxy)
```

### Step 5 — Verify

```bash
curl -i https://api.dcm.alzp.tgscloud.net/api/v1/health/live
# New route with JWT:
curl -i -H "Authorization: Bearer $TOKEN" https://api.dcm.alzp.tgscloud.net/api/v1/{prefix}/...
```

Local dev: Vite proxy `/api` → `localhost:8080` — **no Gateway sync needed** for coding.

### Agent rules summary

| Step | Agent auto | User required |
|------|------------|---------------|
| FastAPI route + tests + main.py | yes | — |
| Add `ROUTE_SPECS` entry | yes | — |
| `aws sso login` | try | if browser SSO |
| `--check` Gateway | yes | — |
| `sync-api-gateway-routes.sh` apply | **no** | confirm first |
| Frontend client | yes if spec says frontend | — |
