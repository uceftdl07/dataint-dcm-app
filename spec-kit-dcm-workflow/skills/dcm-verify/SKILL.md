---
name: dcm-verify
description: >-
  DCM pre-merge verification gate for AI agents. Machine-readable: gate matrix
  by package/domain, exact lint/test/build commands, exit-code rules, integration
  with dcm-review.sh. Agent MUST run gates before reporting task complete.
  Load with dcm-python and/or dcm-react during implement and review.
compatibility: "packages/dcm-frontend/, packages/dcm-backend/, packages/dcm-*-collector/, packages/dcm-commons/, packages/dcm-lambda-ingestion/, packages/dcm-databricks-pipeline/"
metadata:
  author: DCM Squad
  domain: ci,quality
---

# DCM Verify — quality gate before "c'est bon"

Machine-readable **verification skill** for AI agents.  
Canalise l'agent : **lint → types → tests → build** — exit 0 obligatoire.

**Load with** : `dcm-python` (backend/dataeng) + `dcm-react` (frontend) + **`dcm-testing`** (when writing tests)  
**Authority** : `AGENTS.md`, `spec-kit-dcm-workflow/commands/review.md`, CI workflows

## When to load

| Moment | Action |
|--------|--------|
| `/{speckit}implement` — avant de marquer task `[x]` | Run **minimal gate** for touched package |
| Checkpoint **Review** | Run full gate + `/speckit.dcm.review` |
| Avant "terminé" / "PR ready" | Run **full gate** — all touched packages |
| Après fix CI failure | Re-run failed gate only, then full gate |

## Gate matrix (by package)

| Package | Lint | Types | Tests | Build / extra |
|---------|------|-------|-------|---------------|
| `packages/dcm-frontend` | `npm run lint` | `npm run typecheck` | `npm test` | `npm run build` |
| | `npm run format:check` | | | |
| `packages/dcm-backend` | `ruff check .` | `mypy app` | `pytest` | — |
| `packages/dcm-aws-collector` | `ruff check .` | — | `pytest` | — |
| `packages/dcm-azure-collector` | `ruff check .` | — | `pytest` | — |
| `packages/dcm-lambda-ingestion` | `ruff check .` | — | `pytest` | — |
| `packages/dcm-commons` | `ruff check .` | — | `pytest` | — |
| `packages/dcm-databricks-pipeline` | `ruff check .` | — | `pytest` | — |

**Order** : lint → typecheck/mypy → tests → build (frontend only)

`mypy app` is **dcm-backend only** — `app` is that package's module and no other's
(`dcm_commons`, `aws_collector`, `azure_collector`, `lambda_ingestion`, `pipelines`).
`dcm-review.sh` derives the module from each `pyproject.toml`; do the same by hand
rather than copying `mypy app` onto another package, where it fails on a missing path.

## Decision — which gates to run?

```
Touched files under packages/dcm-frontend/**     → frontend gates
Touched files under packages/dcm-backend/**      → backend gates (only one with mypy)
Touched files under packages/dcm-*-collector/**  → python gates (ruff + pytest)
Touched files under packages/dcm-commons/**      → python gates (ruff + pytest)
Touched files under packages/dcm-lambda-ingestion/**    → python gates
Touched files under packages/dcm-databricks-pipeline/** → python gates
Both frontend + backend                          → run BOTH stacks (full-stack)
Sub-spec says "tests optional"                   → still run lint + typecheck minimum
```

## Commands — copy/paste exact

### Frontend (`packages/dcm-frontend`)

```bash
cd packages/dcm-frontend
npm run lint              # ESLint — max-warnings 0
npm run typecheck         # tsc --noEmit
npm run format:check      # Prettier
npm test                  # vitest run
npm run build             # vite build — REQUIRED before PR
```

**Minimal** (typo/copy only, no logic): `lint` + `typecheck`  
**Standard** (hooks/components): + `npm test`  
**PR-ready**: all five commands

### Backend (`packages/dcm-backend`)

```bash
cd packages/dcm-backend
uv run ruff check .       # or: ruff check .
uv run mypy app           # skip if mypy unavailable — report SKIP
uv run pytest -q          # or: .venv/bin/python -m pytest -q
```

Prefer `uv run` if `uv` installed; else activate `.venv`.

### Collectors / lambda / commons / databricks-pipeline

```bash
cd packages/dcm-aws-collector   # or azure-collector, lambda-ingestion,
                                # dcm-commons, dcm-databricks-pipeline
uv run ruff check .
uv run pytest -q
```

No `mypy` on these: none of them declares a `mypy` config, and `mypy app` — the
dcm-backend command — targets a directory they do not have.

## Full-stack change (default DCM feature)

```bash
cd packages/dcm-backend && uv run ruff check . && uv run mypy app && uv run pytest -q
cd packages/dcm-frontend && npm run lint && npm run typecheck && npm test && npm run build
```

Run from repo root. **Do not** skip backend if both packages touched.

## Automated script (review / CI parity)

From repo root — same gates as `/speckit.dcm.review`:

```bash
chmod +x spec-kit-dcm-workflow/scripts/dcm-review.sh
./spec-kit-dcm-workflow/scripts/dcm-review.sh --package packages/dcm-frontend
./spec-kit-dcm-workflow/scripts/dcm-review.sh --package packages/dcm-backend
```

Optional: `--duplication`, `--sonar`, `--report specs/NNN-*/review-T001.md`

## Agent rules (MANDATORY)

1. **Run gates yourself** — use Shell/bash, do not ask user to run unless blocked (no node, no uv)
2. **Exit 0 required** — capture stderr on failure, fix, re-run
3. **Never say "c'est bon" / "done"** if any gate failed or was skipped without reason
4. **Report format** after verify:

```
DCM Verify — {package}
  lint       ✅ | ❌
  types      ✅ | ❌ | ⏭ skip
  tests      ✅ | ❌
  build      ✅ | ❌ | n/a
```

5. **New route / API** : backend pytest + frontend typecheck if client added
6. **Implement checkpoint** : run minimal gate before marking `[x]` in tasks.md

## Integration with spec-kit

| Command | Verify role |
|---------|-------------|
| `/{speckit}implement T00X` | Load this skill + domain skill; verify before `[x]` |
| `/speckit.dcm.review --task T00X` | `dcm-review.sh` + skill checklist |
| `/speckit.dcm.sync-status` | Only after verify pass + PR merged |

## Common failures

| Symptom | Cause | Fix |
|---------|-------|-----|
| `MISSING_EXPORT` on `npm run build` | import exists, export missing | export in module + re-build |
| ESLint `--max-warnings 0` | unused import, hook deps | fix lint, re-run |
| pytest `response_cache` stale | cache between tests | `clear_response_cache()` in conftest |
| page-bundle KeyError in pytest | parallel mock order | mock by SQL string not call order |
| mypy SKIP | not installed locally | `uv pip install -e ".[dev]"` or report SKIP |
| ruff F401 / E501 | style | `ruff check --fix .` then manual |

## Anti-patterns — reject

| Anti-pattern | Fix |
|--------------|-----|
| "Tests should pass" without running | Run pytest/vitest |
| Skip build on frontend PR | Always `npm run build` |
| Fix lint only in edited file when CI lints whole package | `npm run lint` full package |
| Mark task `[x]` before verify | Verify first |
| User asked verify, agent summarizes only | Execute commands |

## Quick reference

| Scenario | Commands |
|----------|----------|
| Frontend task done | `lint` → `typecheck` → `test` → `build` |
| Backend route done | `ruff` → `mypy` → `pytest` |
| Collector change | `ruff` → `pytest` |
| Full-stack feature | backend stack + frontend stack |
| Pre-PR formal review | `dcm-review.sh --package ...` |
| Domain conventions | Load `dcm-python` / `dcm-react` |
| What test to write | Load **`dcm-testing`** |
| Blocked (no npm) | Report exact blocker + partial verify |
