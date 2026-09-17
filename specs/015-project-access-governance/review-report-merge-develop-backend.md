# DCM Review Report

**Package**: `packages/dcm-backend`
**Branch**: `frontend/015-project-access-governance` (base: `develop`)
**Stack**: python (module `app`)
**Verdict**: **FAIL** (fail=2 warn=0 skip=1)

## Changed files

```
packages/dcm-backend/.env.example
packages/dcm-backend/.gitignore
packages/dcm-backend/app/api/routes/access_requests.py
packages/dcm-backend/app/api/routes/activities.py
packages/dcm-backend/app/api/routes/admin_access_requests.py
packages/dcm-backend/app/api/routes/admin_alert_rules.py
packages/dcm-backend/app/api/routes/admin_audit.py
packages/dcm-backend/app/api/routes/admin_bundle.py
packages/dcm-backend/app/api/routes/admin_channels.py
packages/dcm-backend/app/api/routes/admin_collectors.py
packages/dcm-backend/app/api/routes/admin_embedded_dashboards.py
packages/dcm-backend/app/api/routes/admin_entra_search.py
packages/dcm-backend/app/api/routes/admin_kpi_config.py
packages/dcm-backend/app/api/routes/admin_lz.py
packages/dcm-backend/app/api/routes/admin_maintenance.py
packages/dcm-backend/app/api/routes/admin_retention.py
packages/dcm-backend/app/api/routes/admin_users.py
packages/dcm-backend/app/api/routes/auth.py
packages/dcm-backend/app/api/routes/clusters.py
packages/dcm-backend/app/api/routes/compute_metrics.py
packages/dcm-backend/app/api/routes/costs.py
packages/dcm-backend/app/api/routes/data_product_usage.py
packages/dcm-backend/app/api/routes/databases.py
packages/dcm-backend/app/api/routes/databricks.py
packages/dcm-backend/app/api/routes/governance.py
packages/dcm-backend/app/api/routes/lakeflow.py
packages/dcm-backend/app/api/routes/pipelines.py
packages/dcm-backend/app/api/routes/projects.py
packages/dcm-backend/app/api/routes/security.py
packages/dcm-backend/app/api/routes/unity_catalog.py
packages/dcm-backend/app/api/routes/users.py
packages/dcm-backend/app/api/services/alerts_page.py
packages/dcm-backend/app/api/services/compute_metrics_clusters.py
packages/dcm-backend/app/api/services/compute_metrics_common.py
packages/dcm-backend/app/api/services/compute_metrics_forecast.py
packages/dcm-backend/app/api/services/compute_metrics_recommendations.py
packages/dcm-backend/app/api/services/compute_metrics_warehouses.py
packages/dcm-backend/app/api/services/dashboard_bundle.py
packages/dcm-backend/app/api/services/databricks_bundle.py
packages/dcm-backend/app/api/services/datafactory_page.py
packages/dcm-backend/app/api/services/finops_page.py
packages/dcm-backend/app/api/services/governance_page.py
packages/dcm-backend/app/api/services/lakeflow_jobs.py
packages/dcm-backend/app/api/services/lakeflow_overview.py
packages/dcm-backend/app/api/services/monitoring_reports_bundle.py
packages/dcm-backend/app/api/services/unity_catalog_bundle.py
packages/dcm-backend/app/auth/dependencies.py
packages/dcm-backend/app/auth/role_permissions.py
packages/dcm-backend/app/auth/scope.py
packages/dcm-backend/app/auth/scope_model.py
packages/dcm-backend/app/cache/response_cache.py
packages/dcm-backend/app/chat/loaders.py
packages/dcm-backend/app/config/__init__.py
packages/dcm-backend/app/db/connection.py
packages/dcm-backend/app/db/lz_scope.py
packages/dcm-backend/app/main.py
packages/dcm-backend/pyproject.toml
packages/dcm-backend/scripts/migrate_notification_lz_ids.sql
packages/dcm-backend/tests/conftest.py
packages/dcm-backend/tests/test_access_requests.py
packages/dcm-backend/tests/test_admin_auth.py
packages/dcm-backend/tests/test_compute_metrics_routes.py
packages/dcm-backend/tests/test_compute_metrics_services.py
packages/dcm-backend/tests/test_data_product_usage.py
packages/dcm-backend/tests/test_databricks_workspaces.py
packages/dcm-backend/tests/test_embedded_dashboards.py
packages/dcm-backend/tests/test_lakeflow_overview.py
packages/dcm-backend/tests/test_lakeflow_scope.py
packages/dcm-backend/tests/test_projects.py
packages/dcm-backend/tests/test_role_permissions.py
packages/dcm-backend/tests/test_scope.py
packages/dcm-backend/tests/test_unity_catalog.py
packages/dcm-backend/uv.lock
```

## Gates

| Gate | Status | Detail |
|------|--------|--------|
| ruff | FAIL | 78 |         resolved_at = datetime(2026, 3, 19, 10, 0, 0, tzinfo=timezone.utc)    |                                     |
| mypy | SKIP | mypy not installed |
| pytest | FAIL | ImportError while loading conftest '/Users/adrien.hereng/Documents/DCM/dataint-dcm-app/packages/dcm-backend/tests/confte |

## Next

- Agent: cross-check diff vs `dcm-python` / `dcm-react` skills + sub-spec acceptance criteria
- If PASS: open PR to integration branch
- If FAIL: fix and re-run `/speckit.dcm.review`
