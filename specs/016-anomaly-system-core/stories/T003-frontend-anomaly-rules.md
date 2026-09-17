# T003 - Frontend anomaly rules

**Domain**: frontend
**Package**: packages/dcm-frontend
**Branch**: frontend/016-implement-anomaly-rules-page-custom-rule
**Jira**: DCINT-318
**Depends on**: T002
**Work type**: feature

## Description

Implement the Anomaly Rules page and custom-rule dialog. Show human-readable rule data, enforce authorized LZ scope, keep company rules read-only, and provide environment-aware activation controls.

## Files to create/modify

- CREATE or UPDATE pages/components under `packages/dcm-frontend/src/`
- CREATE or UPDATE query hooks and route definitions
- CREATE tests under `packages/dcm-frontend/`

## Acceptance Criteria

- [ ] Rules table supports domain, type, severity, mode, status, and LZ scope visibility.
- [ ] Authorized users can create/edit custom rules and toggle activation.
- [ ] Company rules cannot be edited.
- [ ] Loading, empty, validation, authorization, and network-error states are covered.

## Tests

- Vitest component and mocked-network tests.
- Strict TypeScript and ESLint checks.

## Out of scope

- Anomaly Reports page
- Backend implementation
- Alerting configuration

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside frontend package scope
- [ ] Diff stays reviewable
- [ ] Jira Story lists branch name

## Notes

See [UI contract](../contracts/anomaly-ui.md) and [API contract](../contracts/anomaly-api.md).
