# Data Connect Monitoring (DCM) Constitution

<!-- SOURCE OF TRUTH — shipped by the extension. Edit here, then run
scripts/sync-dcm-extension.sh; never edit .specify/memory/constitution.md. -->

## Core Principles

Principles are grouped by theme and identified by a stable ID (`P1`..`P16`) — cite the ID
in reviews and PRs (e.g. "violates P8"). IDs are permanent; new principles append (`P17`, …)
and are never renumbered.

### Quality & Craftsmanship

#### P1. Test-First & Code Quality (NON-NEGOTIABLE)
All new features and bugfixes require associated automated tests before merge: pytest for Python (backend, collectors, pipeline, lambda, dcm-commons), Vitest for the React frontend. TDD (write tests first, validate failure, then implement) is the strongly recommended default; it is mandatory for any change to a NON-NEGOTIABLE path (secrets, no-fake-data, idempotency). Exception: `hotfix` work_type may ship the fix first, but a regression test reproducing the bug MUST land in the same PR. The enforcement details (linters, type checks, zero-warning gate) live in Technical & Compliance Constraints; this principle owns only the test requirement. "Documented" here means project docs (README, spec) are updated — see P3 for the in-code docstring rule.

#### P2. Simplicity, Explicitness & Versioning
Favor explicit, simple solutions. Avoid over-engineering (YAGNI). Versioning follows semver: breaking changes require a major bump, backward-compatible additions a minor bump. Every breaking change ships with a migration plan. Documentation must be updated with every change. (Model/schema versioning is refined in P14.)

#### P3. Self-Documenting Code — Docstrings Only Where They Ship Value
Internal code must be self-documenting: explicit file, function, and variable names over docstrings. Prefer `compute_daily_pipeline_failure_rate()` over `calc()` + docstring. Comments explain *why*, never *what*. Exceptions where docstrings/descriptions ARE allowed because they feed a public contract: FastAPI route summaries/descriptions, Pydantic `Field(description=...)` on externally exposed models, and OpenAPI-surfaced schemas.

#### P4. Fail Fast, Fail Loud
No silent failure. Uncaught exceptions must propagate and surface in logs/alerts. Never `except Exception: pass`. Partial collection failures must be logged with full context before continuing.

### Architecture & Reliability

#### P5. Explicit Architecture & Modularity
Each component (collector, backend, pipeline, frontend) is modular, with clear API contracts and separation of concerns. No cross-LZ direct calls; all data flows via Apigee and defined interfaces. Models and enums are centralized in dcm-commons.

#### P6. Idempotency by Design
All pipeline jobs, collectors, and ingestion lambdas must be idempotent. Re-running with the same `collection_run_id` must not create duplicates. Use upsert/merge semantics, never blind INSERT.

### Security & Data Integrity

#### P7. Security & Secrets Management
No hardcoded secrets. All credentials are managed via Azure Key Vault or AWS Secrets Manager. No production with mock/fake data. Access is least-privilege and all endpoints require authentication (Entra ID, JWT).

#### P8. No Hardcoded Secrets (NON-NEGOTIABLE)
Zero tolerance: no API keys, passwords, tokens, connection strings, or client secrets in source code, config files, Dockerfiles, or CI scripts. Exclusively Azure Key Vault (Azure) or AWS Secrets Manager (AWS). Detected violations block merge immediately.

#### P9. No Fake Data in Production (NON-NEGOTIABLE)
Mock/fixture data is strictly forbidden in any production environment or production code path. Fixtures live in `dcm-commons/fixtures/` for tests only and must never be imported outside `conftest.py` or test files.

### Observability

#### P10. Observability & Traceability
Structured logging (structlog, JSON) is mandatory. All API and pipeline actions are logged. Monitoring and alerting are implemented for all critical paths. Debuggability is a first-class concern.

### Data & Medallion

#### P11. Naming Conventions
Medallion Delta tables follow the pattern `{layer}_{dp_type}_{metric}` (e.g. `gold_adf_pipeline_runs`, `curated_databricks_jobs`) with a mandatory layer prefix: `raw_`, `curated_`, `gold_`. This pattern applies to the Delta lakehouse layers only; application-facing Lakebase PostgreSQL tables (e.g. `compute_metrics`, `standard_checks`) follow the backend data model and are exempt. No abbreviations beyond approved aliases in dcm-commons.

#### P12. Medallion Architecture — Aggregations on Gold Only
Business aggregations (SUM, AVG, COUNT, metric-producing window functions) are performed exclusively on the **Gold layer**. Curated layer stores cleaned, typed, deduplicated rows only — no derived metrics. Window functions used solely for deduplication or ordering (e.g. `ROW_NUMBER() OVER (...)` to keep the latest row per key) are permitted in Curated; they must not compute a business metric. Violating this rule breaks lineage guarantees.

#### P13. Immutable Raw Layer
The Raw (Bronze) layer is append-only and never mutated after write. All corrections happen in Curated or Gold transformations. Raw data is the audit trail.

### API & Contracts

#### P14. Schema Versioning
All `MetricPayload` and domain models carry a `schema_version` (semver). Breaking model changes bump the major component of `schema_version`; backward-compatible additions bump the minor. At least one prior major version stays supported for ≥1 release cycle before deprecation.

#### P15. API Contract Stability
Public API endpoints are versioned (`/v1/...`). No breaking change without a deprecation notice of ≥1 release cycle. Consumers (frontend, collectors) must not be broken by backend deploys.

### Frontend

#### P16. Frontend Quality
React/TypeScript follows the dcm-react conventions: central API client, TanStack Query hooks for data access, routes declared in `app-routes.ts`, Vitest tests with mocked network, and UI labels that surface human-readable names (not raw ids). No `any` in committed TypeScript; strict mode required.


## Technical & Compliance Constraints

These are the concrete tooling/version rules that back the principles above.
The principles are the source of truth; this section only lists enforcement details
(it must NOT restate a principle).

- Python >=3.12, FastAPI, async/await for all I/O paths
- Frontend: React 18 + TypeScript strict, ESLint + `tsc --noEmit`
- Only absolute imports between packages
- Linting: ruff, mypy (Python) and ESLint, tsc (TS) — zero warnings on the default branch (enforcement of P1)
- Python code must be type-annotated; TypeScript must compile in strict mode (no `any` committed)
- Secret scanning runs in CI (e.g. gitleaks / detect-secrets); any hit blocks merge
- CI/CD is the single gate that validates tests, lint, and type checks before merge
- Dependencies pinned via `uv` lockfile (Python) and lockfile committed (frontend)
- Contributor guidance lives in `.agents/skills/dcm-python/SKILL.md` and `.agents/skills/dcm-react/SKILL.md`


## Development Workflow & Quality Gates

- Every PR requires review by at least one qualified reviewer of the affected domain (frontend / backend / dataeng)
- Lead-developer or Design Authority review is required only for architectural or data-model changes
- PRs must pass all tests, lint, and type checks in CI
- No feature is merged without associated tests and updated docs
- Major architectural or model changes require Design Authority validation
- All breaking changes must be documented in CHANGELOG.md and communicated to all teams
- Use Spec Kit for spec-driven development and traceability


## Governance

- This constitution supersedes all other coding practices for DCM
- Amendments require documentation, team approval, and a migration plan
- All PRs and reviews must verify compliance with these principles
- Complexity must be justified and documented
- Use the dcm-python and dcm-react skills (`.agents/skills/`) for runtime and code guidance

**Version**: 1.4.0 | **Ratified**: 2026-05-19 | **Last Amended**: 2026-07-15
