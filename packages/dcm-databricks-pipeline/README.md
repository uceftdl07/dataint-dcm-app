# DCM Databricks Pipeline

Databricks pipeline for **Data Connect Monitoring (DCM)**.

It ingests multi-cloud metric payloads, applies quality rules, builds curated domain tables, and exposes business-ready aggregates using a Medallion design:

- **RAW (Bronze)**: immutable JSON payload archive
- **CURATED (Silver)**: parsed domain metrics with DQ + dedup
- **GOLD**: dimensions and aggregate views for analytics

## Table of Contents

- [Scope](#scope)
- [Architecture](#architecture)
- [Domain Coverage](#domain-coverage)
- [Data Model by Layer](#data-model-by-layer)
- [Data Quality](#data-quality)
- [Design Pattern (Framework + Plugin)](#design-pattern-framework--plugin)
- [Project Structure](#project-structure)
- [Local Development](#local-development)
- [Run Tests](#run-tests)
- [Debug with Databricks Connect](#debug-with-databricks-connect)
- [Key Conventions](#key-conventions)
- [Troubleshooting](#troubleshooting)

## Scope

- **Component**: `dcm-databricks-pipeline`
- **Catalog/Schema target**: `it.ba_data_connect_monitoring__d`
- **Language**: Python 3.12+
- **Main dependencies**: PySpark, Delta, boto3, dcm-commons

This package contains DLT notebooks/modules for:

1. RAW ingestion and archiving
2. CURATED parsing/validation/upsert
3. GOLD dimensions and KPI aggregates

## Architecture

```text
Cloud Sources (AWS + Azure)
        |
        v
Landing Volume
/Volumes/it/ba_data_connect_monitoring__d/ingestion_volume/
        |
        v
RAW (raw_metrics)
- full envelope stored as VARIANT body
- ingestion metadata
        |
        v
CURATED (8 domain tables + rejects)
- explode body:metrics[]
- domain mapping + DQ checks
- apply_changes (SCD1)
        |
        v
GOLD
- dim_landing_zone (SCD1)
- dim_users (SCD2)
- 7 aggregate business tables
```

## Domain Coverage

| JSON Domain | Curated Table | Gold Output |
|---|---|---|
| `pipeline` | `curated_pipeline_metrics` | `gold_pipeline_summary` |
| `compute` | `curated_compute_metrics` | `gold_compute_utilization` |
| `cost` | `curated_cost_metrics` | `gold_cost_summary` |
| `database` | `curated_database_metrics` | `gold_database_capacity_alerts` |
| `security` | `curated_security_alerts` | `gold_security_summary` |
| `activity_run` | `curated_activity_runs` | `gold_activity_performance` |
| `user` | `curated_user_metrics` | `dim_users` (SCD2 dimension) |
| `standard_check` | `curated_standard_checks` | `gold_standard_check_score` |

## Data Model by Layer

### RAW (Bronze)

Main table: `raw_metrics`

Core columns:

- `body` (VARIANT): full JSON envelope including `metrics[]`
- `collection_run_id`, `domain`, `cloud_provider`, `source_lz_id`
- `schema_version`, `_sqs_message_id`, `_ingested_at`

Partitioning:

- `domain`
- `cloud_provider`

### CURATED (Silver)

Pattern applied per domain:

1. `_stg_<domain>`: parse + DQ computation
2. `_stg_<domain>_valid`: `_dq_is_valid = true`
3. `curated_<domain>`: `dlt.apply_changes(..., stored_as_scd_type=1)`
4. `curated_<domain>_rejects`: invalid rows for analysis

Shared envelope columns include:

- `row_id`, `collection_run_id`, `source_lz_id`, `cloud_provider`
- `subscription_or_account_id`, `collected_at`, `_ingested_at`

### GOLD

Dimensions:

- `dim_landing_zone` (SCD1)
- `dim_users` (SCD2 with history tracking)

Aggregates:

- `gold_pipeline_summary`
- `gold_compute_utilization`
- `gold_cost_summary`
- `gold_database_capacity_alerts`
- `gold_security_summary`
- `gold_activity_performance`
- `gold_standard_check_score`

## Data Quality

### RAW expectations

Drop records when:

- `collection_run_id` is null
- `domain` is outside supported list
- `cloud_provider` is outside `aws|azure|gcp`

### CURATED DQ

Each domain has explicit rules (examples):

- pipeline status allowed values
- utilization ranges (`0..100`)
- storage consistency (`used <= limit`)
- standard check state whitelist

Invalid records are routed to `curated_*_rejects` tables.

## Design Pattern (Framework + Plugin)

The system-tables ingestion (`pipelines/common/` + `pipelines/system_tables/`)
follows a **Framework + Plugin** pattern: a **reusable, domain-agnostic socle**
(`common`) provides the generic ingestion primitives, and a **thin, business-specific
plugin** (`system_tables`) only declares *what* to ingest and wires the socle together.

> This is the recommended Databricks layout for wheel-based jobs: production code
> lives in versioned, unit-testable `.py` modules (no notebooks), business logic is
> separated from orchestration/IO, and the entry point does wiring only.

### Why

The original ingestion was a single 900-line monolith. Splitting it into a socle +
plugin makes each concern independently testable. The plugin mutualises **all five
`system.*` tables** (billing + compute/access) behind a single spec registry: the
job runs one `for_each` task that fans out one parallel iteration per table
(`--table {{input}}`, bounded by `concurrency`). Adding a table = one entry in the
registry + one string in the job's `inputs`, without touching the ingestion engine.

### The socle — `pipelines/common/` (reusable, no business notion)

Everything is driven by an `IngestionSpec` (source table -> curated table, merge
keys, optional watermark/partition strategy). No module here knows about billing.

| Module | Responsibility |
|---|---|
| `models.py` | `IngestionSpec` (frozen dataclass) + `AzureConnectionConfig` |
| `transforms.py` | Pure transforms: envelope enrichment, multi-cloud union (source-faithful) |
| `writers.py` | Idempotent Delta writes: `MERGE WITH SCHEMA EVOLUTION`, staging append |
| `incremental.py` | Watermark lower-bound + partition-pruning predicate |
| `readers.py` | Native UC read + batched Azure cross-tenant read (bounded driver memory) |
| `azure_auth.py` | Entra M2M client-credentials token for the Databricks resource |
| `azure_decode.py` | Faithful rebuild of SQL-connector rows into a typed DataFrame |
| `runtime.py` | Named-parameter parsing, cluster detection, local-debug bootstrap |

### The plugin — `pipelines/system_tables/` (business-specific, thin)

| Module | Responsibility |
|---|---|
| `specs.py` | Declares the 5 `IngestionSpec`s (billing + compute/access) + the `SPECS` registry keyed by `--table` input |
| `ingest.py` | Orchestration: read (native AWS / batched Azure) -> envelope -> idempotent MERGE per cloud |
| `entrypoint.py` | Wheel entry point (`run`/`main`): resolves Spark, secrets, params; selects table(s); wiring only |

### Design rules enforced

- **Thin entry point** — `entrypoint.py` does wiring only; no business rule lives there.
- **Pure, testable transforms** — logic functions take/return DataFrames and run
  without a cluster (fakes + monkeypatch, see [Run Tests](#run-tests)).
- **One responsibility per module** — a single reason to change each file.
- **Parameterised, never hardcoded** — catalog/schema/dates come from bundle
  variables / widgets; secrets from a secret scope (constitution P8), never in code.
- **Absolute imports only** — each consuming module holds its own reference to a
  socle function, which keeps it monkeypatchable at the consumer boundary.

The test tree **mirrors** the source tree (`tests/common/`, `tests/system_tables/`),
with shared fakes/fixtures in `tests/conftest.py`.

## Project Structure

```text
packages/dcm-databricks-pipeline/
  pipelines/
    __init__.py
    dlt_01_raw_layer.py            # DLT medallion (RAW)
    dlt_02_curated_layer.py        # DLT medallion (CURATED)
    dlt_03_gold_layer.py           # DLT medallion (GOLD)
    sqs_to_volume_drain.py         # SQS -> landing volume drain
    common/                        # reusable ingestion socle (Framework)
      models.py                    # IngestionSpec, AzureConnectionConfig
      transforms.py                # envelope + multi-cloud union
      writers.py                   # idempotent MERGE + staging
      incremental.py               # watermark + partition pruning
      readers.py                   # native + batched Azure read
      azure_auth.py                # Entra M2M token
      azure_decode.py              # SQL-connector rows -> typed DataFrame
      runtime.py                   # params + local-debug bootstrap
    system_tables/                 # system tables plugin (Plugin)
      specs.py                     # 5 IngestionSpecs + SPECS registry
      ingest.py                    # orchestration
      entrypoint.py                # wheel entry point (run/main)
  tests/
    conftest.py                    # shared fakes (Spark/DataFrame) + fixtures
    common/                        # mirrors pipelines/common/
      test_transforms.py
      test_writers.py
      test_incremental.py
      test_readers.py
      test_azure_decode.py
    system_tables/                 # mirrors pipelines/system_tables/
      test_specs.py
      test_ingest.py
      test_entrypoint.py
    test_dlt_01_raw_layer.py
    test_dlt_02_curated_layer.py
    test_dlt_03_gold_layer.py
    test_dlt_workflow.py
  resources/                       # Databricks Asset Bundle resources (jobs)
  pyproject.toml
```

## Local Development

From `packages/dcm-databricks-pipeline`:

```zsh
uv python install 3.12
uv sync --extra dev --python 3.12
```

## Run Tests

```zsh
uv run pytest -q
```

Targeted DLT tests:

```zsh
uv run pytest -q tests/test_dlt_01_raw_layer.py tests/test_dlt_02_curated_layer.py tests/test_dlt_03_gold_layer.py
```

## Debug with Databricks Connect

The system-tables job (`pipelines/system_tables/entrypoint.py`) runs on
**serverless** in the AWS workspace and reads Azure cross-tenant via the SQL
connector. You can step through it locally with breakpoints using
[Databricks Connect](https://docs.databricks.com/dev-tools/databricks-connect):
your Python runs on your machine while Spark executes on serverless.

The module's `run()` entry point auto-detects the environment:

- **On a Databricks cluster** (wheel task) — resolves `SparkSession` +
  `dbutils.secrets`, reads the job's `named_parameters`. Production path,
  unchanged.
- **Locally** (no `DATABRICKS_RUNTIME_VERSION`) — builds a serverless Databricks
  Connect session and a `dbutils.secrets`-compatible accessor, and reads
  parameters from `DBG_*` environment variables.

### 1. Prerequisites

**Isolated debug venv (required).** `databricks-connect` ships its own PySpark
and refuses to run if `pyspark` (a runtime dep of the wheel, present in `.venv`)
is installed in the same environment. Create a separate `.venv-debug`:

```zsh
cd packages/dcm-databricks-pipeline
./scripts/setup_debug_env.sh
```

**Databricks auth.** Debug runs under **your own identity** via an **OAuth**
profile (U2M). Personal access tokens are **prohibited** at TotalEnergies — never
put a `token = dapi...` in `~/.databrickscfg`, and do **not** use the `DEFAULT`
profile if it still holds one. Create/refresh the `dcm-dev` profile:

```zsh
databricks auth login \
  --host https://dbc-223d60ab-45bd.cloud.databricks.com \
  --profile dcm-dev
```

This writes a token-less profile (`auth_type = databricks-cli`); the browser
sign-in refreshes it, nothing durable is stored in the file.

Verify: `databricks auth describe -p dcm-dev` should print
`Authenticated with: databricks-cli` and your user — a profile printing a
`pat`/`token` auth type must be fixed, not used.

**Azure SP secrets** (only if debugging the Azure read). Either grant your user
read access on the `dcm-secret-scope` secret scope, or override the three secrets
with environment variables (never commit them):

```zsh
export DBX_AZ_TENANT_ID="<entra-tenant-id>"
export DBX_AZ_CLIENT_ID="<entra-client-id>"
export DBX_AZ_CLIENT_SECRET="<entra-client-secret>"
```

### 2. Run the debugger

**VS Code (recommended):** press <kbd>F5</kbd> and pick
**"Debug System Tables local (Databricks Connect)"** (see `.vscode/launch.json`). Set
breakpoints in `main` (`pipelines/system_tables/entrypoint.py`), `read_azure_batches`, or
`rows_to_dataframe` (`pipelines/common/`).

**Terminal:**

```zsh
cd packages/dcm-databricks-pipeline
DATABRICKS_CONFIG_PROFILE=dcm-dev .venv-debug/bin/python -m pipelines.system_tables.entrypoint
```

### 3. Parameters

Job parameters are read from `DBG_*` env vars (defaults live in
`.vscode/launch.json`, aligned with `databricks.yml` target `dev`):

| Env var | Purpose |
|---|---|
| `DBG_AWS_ACCOUNT_ID` | AWS account for the `cloud_provider=aws` envelope |
| `DBG_AZURE_WORKSPACE_ID` | Azure workspace id (`cloud_provider=azure`) |
| `DBG_AZURE_HOST` | Azure SQL Warehouse host (**empty = AWS-only**, skips Azure) |
| `DBG_AZURE_HTTP_PATH` | Azure SQL Warehouse HTTP path |
| `DBG_AZURE_SECRET_SCOPE` | Secret scope holding the Entra SP creds |
| `DBG_LOOKBACK_DAYS` | Incremental lookback window (days) |

`collection_run_id` / `collected_at` are auto-generated locally when unset.

> ⚠️ Debug runs the **real** ingestion: it writes to the dev curated tables
> (`it.ba_data_connect_monitoring__d`) via idempotent `MERGE`, under your
> identity. Use it only against a dev environment. `.venv-debug/` is
> git-ignored; keep every credential out of version control (and out of
> `~/.databrickscfg`: OAuth only, no PAT).

## Key Conventions

Sprint 7 renaming is mandatory in new code:

- use `compute` (not `cluster`)
- use `standard_check` (not `compliance`)
- use check vocabulary (`check_id`, `check_name`, `check_state`, `check_effect`)

## Troubleshooting

### `uv sync` fails with hatch editable build error

If hatch cannot infer files to include, ensure:

- `pipelines/__init__.py` exists
- `pyproject.toml` contains:

```toml
[tool.hatch.build.targets.wheel]
packages = ["pipelines"]
```

### Pytest warns about `asyncio_mode`

This usually means the wrong pytest environment is used (system Python instead of project env).
Use:

```zsh
uv run pytest -q
```

---

If you update table names, domain names, or DQ logic in `pipelines/dlt_*`, update this README in the same PR.
