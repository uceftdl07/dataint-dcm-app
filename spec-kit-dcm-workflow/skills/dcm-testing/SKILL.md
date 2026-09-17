---
name: dcm-testing
description: >-
  DCM testing strategy for AI agents — unit vs route/component vs regression,
  when to add which test, naming, fixtures, scoped commands. Load with
  dcm-python/dcm-react when writing tests; with dcm-verify before marking done.
compatibility: packages/dcm-frontend/, packages/dcm-backend/, packages/dcm-commons/, packages/dcm-*-collector/
metadata:
  author: DCM Squad
  domain: qa,testing
---

# DCM Testing — strategy for AI agents

Machine-readable **testing skill** for AI agents.  
Answers: **what test to add**, **where**, **how to name it**, **what to run**.

**Load with** : `dcm-python` (backend) / `dcm-react` (frontend) for code patterns  
**Execute with** : `dcm-verify` for lint + test commands before "done"

## Test pyramid (DCM reality)

```
                    ┌─────────────┐
                    │  Manual QA  │  (hors scope agent — pas prod live)
                    └──────┬──────┘
               ┌───────────┴───────────┐
               │  Route / page tests   │  ← DCM "integration" (mocked I/O)
               └───────────┬───────────┘
          ┌─────────────────┴─────────────────┐
          │  Unit — lib, hooks, pure functions   │
          └─────────────────────────────────────┘
```

| Level | DCM name | Backend | Frontend |
|-------|----------|---------|----------|
| **Unit** | Pure logic | `tests/test_lz_filter_unit.py`, helpers | `src/lib/**/*.test.ts` |
| **Route / component** | HTTP/UI integration (mocked) | `tests/test_{domain}.py` + `client` + `mock_db` | `*.test.tsx` + `renderWithProviders` |
| **Regression** | Bug must not return | New test in same file, name documents bug | Same — repro case in vitest |
| **E2E** | Not in repo today | — | — (future Playwright → section below) |

**No real Databricks / AWS / Azure** in automated tests — always mock.

## Decision tree — which test to add?

```
Change type?
│
├─ New FastAPI route / handler
│   → tests/test_{domain}.py — class Test{Feature}
│   → client + mock_db.fetchall/fetchone
│   → assert status + JSON shape
│
├─ New React hook / page / component
│   → colocate {Name}.test.ts(x) or pages/{Page}.test.tsx
│   → renderWithProviders from src/test/render.tsx
│   → mock dcmApiClient module (not global fetch)
│
├─ Pure function (filter, label, route builder)
│   → unit test only — no providers, no mock_db
│
├─ Bug fix (user report / CI red)
│   → REGRESSION test first (fails before fix, passes after)
│   → name: test_regression_{short_bug_slug} or test_{bug}_fixed
│
├─ Refactor (no behaviour change)
│   → run existing tests — do NOT delete tests
│   → add test only if coverage gap found
│
└─ Collector / lambda / pipeline
│   → packages/{pkg}/tests/ — pytest + mocks (no cloud calls)
```

## Backend — patterns

### Route test (standard)

File: `packages/dcm-backend/tests/test_{domain}.py`

```python
async def test_list_items_empty(client, mock_db):
    mock_db.fetchall.return_value = []
    resp = await client.get("/api/v1/clusters")
    assert resp.status_code == 200
    assert resp.json() == {"items": []}
```

**Fixtures** (from `tests/conftest.py` — do not duplicate):
- `client` — AsyncClient + ASGITransport
- `mock_db` — AsyncMock replacing `app.state.db_pool`
- autouse: `auth_disabled_for_route_tests`, `clear_response_cache_between_tests`

### Unit test (no HTTP)

File: `tests/test_{module}_unit.py` when logic extracted from route.

### Regression test

```python
async def test_regression_terminated_clusters_included(client, mock_db):
    """DCINT-XXX: terminated state was dropped from GET /clusters."""
    mock_db.fetchall.return_value = [_cluster_row(state="terminated")]
    resp = await client.get("/api/v1/clusters")
    assert resp.status_code == 200
    assert resp.json()["items"][0]["state"] == "terminated"
```

### Mock rules

| Do | Don't |
|----|-------|
| Mock by SQL / return value | Rely on call order with parallel routes |
| Use `$1` args in production code | Assert internal SQL string unless regression |
| Reset cache via autouse fixtures | Share mutable state between tests |

### Commands

```bash
cd packages/dcm-backend
uv run pytest tests/test_clusters.py -q          # scoped
uv run pytest tests/test_{domain}.py -q          # one domain
uv run pytest -q                                  # full package regression
uv run pytest -k regression -q                    # regression-named only
```

## Frontend — patterns

### Component / page test

```typescript
import { renderWithProviders, screen } from '../test/render';

it('shows workspace display name', () => {
  renderWithProviders(<Header />, { route: '/databricks' });
  expect(screen.getByLabelText('Databricks workspace filter')).toBeInTheDocument();
});
```

**Use** : `src/test/render.tsx`, `src/test/fixtures/`, mock `dcmApiClient`.

### Hook test

File: `src/hooks/use{Name}.test.ts` — wrap with QueryClientTestProvider if needed.

### Regression test

```typescript
it('regression: inactive clusters visible in filter (DCINT-XXX)', () => {
  // minimal repro from bug report
});
```

### Commands

```bash
cd packages/dcm-frontend
npm test -- src/hooks/useClustersPageData.test.ts   # scoped
npm test -- src/pages/Databricks.test.tsx           # page
npm test                                             # full package regression
npm run test:perf                                    # perf hooks only (optional)
```

## Regression scope — what to run when?

| Moment | Scope | Backend | Frontend |
|--------|-------|---------|----------|
| During implement (1 file) | **Minimal** | `pytest tests/test_X.py` | `npm test -- path/to/file.test.ts` |
| Before task `[x]` | **Package** | `pytest -q` | `npm test` |
| Pre-PR / review | **Package + lint** | dcm-verify backend stack | dcm-verify frontend stack |
| Hotfix | **Regression + related** | new test + `pytest -q` | new test + `npm test` |
| Release (manual) | **All touched packages** | all packages in PR | all packages in PR |

Agent default: **minimal during edit**, **package before done**.

## Collectors / commons / lambda

| Package | Test dir | Pattern |
|---------|----------|---------|
| `dcm-commons` | `tests/` | unit + model validation |
| `dcm-aws-collector` | `tests/` | mock boto3 |
| `dcm-azure-collector` | `tests/` | mock Azure SDK |
| `dcm-lambda-ingestion` | `tests/` | event payload fixtures |
| `dcm-databricks-pipeline` | `tests/test_dlt_*.py` | DLT layer tests |

```bash
cd packages/dcm-aws-collector && uv run pytest -q
```

Never call live Apigee ingest in tests.

## Sub-spec / spec-kit

When `/{speckit}implement T00X`:

1. Read sub-spec **Tests** + **Acceptance Criteria**
2. Each criterion → ≥1 automated test (or explicit "manual only" in sub-spec)
3. New files listed in sub-spec → corresponding test file in same PR
4. Mark task `[x]` only after tests pass (`dcm-verify`)

## Anti-patterns — reject

| Anti-pattern | Fix |
|--------------|-----|
| "Manual test OK" for new API | Add `test_{domain}.py` |
| Delete failing test to green CI | Fix code or mock |
| `fetch` in component test | Mock `dcmApiClient` |
| Real Databricks in pytest | `mock_db` only |
| Test with no assert | Add behaviour assertion |
| Skip regression on bugfix | Add repro test |
| Run full monorepo pytest for 1-line frontend change | Scope to package |

## Future E2E (placeholder)

When Playwright/Cypress added:

- Location: `packages/dcm-frontend/e2e/` (TBD)
- Not required for task done today
- Smoke only on critical paths (login, dashboard load)

Update this section when e2e lands — do not invent e2e commands until then.

## Quick reference

| Scenario | Action |
|----------|--------|
| New backend endpoint | `tests/test_{domain}.py` + mock_db |
| New UI feature | `*.test.tsx` + renderWithProviders |
| Bug fix | regression test + scoped pytest/vitest |
| Before `[x]` | package-level `pytest -q` / `npm test` |
| Formal gate | `dcm-verify` + optional `dcm-review.sh` |
| How to write test code | `dcm-python` / `dcm-react` |
| CI parity | pytest blocking; eslint/tsc report-only |

## Skill stack (load order)

```
1. dcm-testing     ← strategy (this file)
2. dcm-python OR dcm-react   ← conventions
3. dcm-verify      ← run gates
```

Also load **`dcm-testing`** when implementing bugfixes or new acceptance criteria.
