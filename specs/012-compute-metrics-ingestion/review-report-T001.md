# DCM Review Report

**Package**: `packages/dcm-databricks-pipeline`
**Branch**: `dataeng/012-curated-compute-system-tables` (base: `develop`)
**Stack**: backend
**Verdict**: **FAIL** (fail=2 warn=0 skip=1)

## Changed files

```
(none detected vs base)
```

## Gates

| Gate | Status | Detail |
|------|--------|--------|
| ruff | FAIL | spec-kit-dcm-workflow/scripts/dcm-review.sh: line 76: ruff: command not found  |
| mypy | SKIP | mypy not installed |
| pytest | FAIL | spec-kit-dcm-workflow/scripts/dcm-review.sh: line 76: pytest: command not found  |

## Next

- Agent: cross-check diff vs `dcm-python` / `dcm-react` skills + sub-spec acceptance criteria
- If PASS: open PR to integration branch
- If FAIL: fix and re-run `/speckit.dcm.review`
