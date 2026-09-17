# DCM Review Report — compute reco/forecast feedback

**Package**: `packages/dcm-backend` + `packages/dcm-frontend`
**Branch**: `feature/compute-reco-forecast-feedback` (base: `develop`)
**Stack**: backend + frontend
**Verdict**: **PASS**

## Changed files

```
packages/dcm-backend/app/api/services/compute_metrics_forecast.py
packages/dcm-backend/app/api/services/compute_metrics_recommendations.py
packages/dcm-backend/tests/test_compute_metrics_routes.py
packages/dcm-frontend/src/components/domain/compute/forecast-widget.tsx
packages/dcm-frontend/src/components/domain/compute/recommendation-mini-drawer.tsx
packages/dcm-frontend/src/components/domain/compute/recommendations-table.tsx
packages/dcm-frontend/src/lib/compute/field-descriptions.ts
packages/dcm-frontend/src/pages/ComputeRecommendationsForecast.test.tsx
packages/dcm-frontend/src/pages/ComputeRecommendationsForecast.tsx
packages/dcm-frontend/src/test/fixtures/compute-recommendations.ts
packages/dcm-frontend/src/types/api.ts
```

## Gates

| Gate | Status | Detail |
|------|--------|--------|
| ruff (touched BE) | PASS | compute_metrics_forecast + recommendations |
| pytest reco/forecast routes | PASS | 5 passed |
| secrets | PASS | no credentials |
| scope | PASS | BE+FE reco/forecast feedback only |

## Agent review

- #6 default OPEN status filter
- #2 forecast chart labels + CI band
- #3/#4 actual cost from gold `*_cost_daily` on summary + rows
- #5 historical observed series via forecast `actuals`
- #7 resolved reason not in scope (no UC column)

## Next

- Commit, push, PR → develop
- workflow_dispatch dcm-backend + dcm-frontend environment=dev deploy=true
