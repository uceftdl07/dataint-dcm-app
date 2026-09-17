# DCM Review Report

**Package**: `packages/dcm-frontend`
**Branch**: `frontend/015-project-access-governance` (base: `develop`)
**Stack**: frontend
**Verdict**: **FAIL** (fail=3 warn=0 skip=0)

## Changed files

```
packages/dcm-frontend/src/api/dcmApiClient.ts
packages/dcm-frontend/src/app-routes.ts
packages/dcm-frontend/src/components/AdminProjectsTab.test.tsx
packages/dcm-frontend/src/components/AdminProjectsTab.tsx
packages/dcm-frontend/src/components/DcmGuideButton.tsx
packages/dcm-frontend/src/components/Header.test.tsx
packages/dcm-frontend/src/components/Header.tsx
packages/dcm-frontend/src/components/HeaderProjectFilter.tsx
packages/dcm-frontend/src/components/LandingRequestChooserModal.test.tsx
packages/dcm-frontend/src/components/LandingRequestChooserModal.tsx
packages/dcm-frontend/src/components/LzRegistrationRequestModal.tsx
packages/dcm-frontend/src/components/PendingApprovalMessage.tsx
packages/dcm-frontend/src/components/ProjectJoinRequestModal.test.tsx
packages/dcm-frontend/src/components/ProjectJoinRequestModal.tsx
packages/dcm-frontend/src/components/ProjectRegisterRequestModal.test.tsx
packages/dcm-frontend/src/components/ProjectRegisterRequestModal.tsx
packages/dcm-frontend/src/components/RejectWithReason.tsx
packages/dcm-frontend/src/components/RequireAdmin.test.tsx
packages/dcm-frontend/src/components/RequireAdmin.tsx
packages/dcm-frontend/src/components/Sidebar.test.tsx
packages/dcm-frontend/src/components/landing/LandingAccessCta.tsx
packages/dcm-frontend/src/components/landing/LandingAccessGuide.tsx
packages/dcm-frontend/src/components/ui/combobox.tsx
packages/dcm-frontend/src/config/navigation.ts
packages/dcm-frontend/src/config/role-permissions.ts
packages/dcm-frontend/src/contexts/MonitoringScopeContext.tsx
packages/dcm-frontend/src/contexts/monitoring-scope.ts
packages/dcm-frontend/src/hooks/query-keys.ts
packages/dcm-frontend/src/hooks/useComputeClustersQueries.ts
packages/dcm-frontend/src/hooks/useComputeWarehousesQueries.ts
packages/dcm-frontend/src/hooks/useDatabricksBundleCache.ts
packages/dcm-frontend/src/hooks/useDatabricksPageData.ts
packages/dcm-frontend/src/hooks/useLakeflowJobsData.ts
packages/dcm-frontend/src/hooks/useLakeflowOverviewData.ts
packages/dcm-frontend/src/hooks/useProjectsQueries.ts
packages/dcm-frontend/src/lib/databricks/routes.test.ts
packages/dcm-frontend/src/lib/databricks/routes.ts
packages/dcm-frontend/src/lib/databricks/workspace-label.ts
packages/dcm-frontend/src/lib/project-registration.test.ts
packages/dcm-frontend/src/lib/project-registration.ts
packages/dcm-frontend/src/lib/role-access.test.ts
packages/dcm-frontend/src/lib/role-access.ts
packages/dcm-frontend/src/pages/Admin.test.tsx
packages/dcm-frontend/src/pages/Admin.tsx
packages/dcm-frontend/src/pages/MonitoringReports.test.tsx
packages/dcm-frontend/src/pages/MonitoringReports.tsx
packages/dcm-frontend/src/pages/MyLandingZones.tsx
packages/dcm-frontend/src/pages/ProjectDetail.test.tsx
packages/dcm-frontend/src/pages/ProjectDetail.tsx
packages/dcm-frontend/src/pages/Projects.test.tsx
packages/dcm-frontend/src/pages/Projects.tsx
packages/dcm-frontend/src/pages/UnityCatalogExplorer.tsx
packages/dcm-frontend/src/tour/PageTourPrompt.tsx
packages/dcm-frontend/src/tour/resolve-tour-key.ts
packages/dcm-frontend/src/tour/tour-steps.ts
packages/dcm-frontend/src/types/api.ts
```

## Gates

| Gate | Status | Detail |
|------|--------|--------|
| eslint | FAIL |   53:9  warning  The 'dashboards' logical expression could make the dependencies of useMemo Hook (at line 66) change on  |
| typescript | FAIL | src/pages/DatabricksFocusPage.tsx(74,5): error TS6133: 'workspaces' is declared but its value is never read. src/pages/D |
| vitest | FAIL |  ❯ Databricks src/pages/Databricks.tsx:237:67   ❯ renderWithHooks node_modules/react-dom/cjs/react-dom.development.js:15 |

## Next

- Agent: cross-check diff vs `dcm-python` / `dcm-react` skills + sub-spec acceptance criteria
- If PASS: open PR to integration branch
- If FAIL: fix and re-run `/speckit.dcm.review`
