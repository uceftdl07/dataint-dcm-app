# T004 - Frontend anomaly reports

**Domain**: frontend
**Package**: packages/dcm-frontend
**Branch**: frontend/016-implement-anomaly-reports-page-filters
**Jira**: DCINT-316
**Depends on**: T002
**Work type**: feature

## Description

Implement the Anomaly Reports page with paginated history, filters, lifecycle status, detail view, and distinct handling for `unknown` evaluation reports.

## Files to create/modify

- CREATE or UPDATE pages/components under `packages/dcm-frontend/src/`
- CREATE or UPDATE query hooks and route definitions
- CREATE tests under `packages/dcm-frontend/`

## Acceptance Criteria

- [ ] Reports can be filtered by LZ, status, rule, and period.
- [ ] Detail view displays metric value, threshold snapshot, timestamps, and formatted logs.
- [ ] Active, finalized, and unknown reports are visually distinct.
- [ ] Loading, empty, and network-error states are covered.

## Tests

- Vitest component and mocked-network tests.
- Strict TypeScript and ESLint checks.

## Out of scope

- Anomaly Rules page
- Backend implementation
- Jira links or notification behavior from later alerting specs

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside frontend package scope
- [ ] Diff stays reviewable
- [ ] Jira Story lists branch name

## Notes

See [UI contract](../contracts/anomaly-ui.md) and [quickstart](../quickstart.md).
