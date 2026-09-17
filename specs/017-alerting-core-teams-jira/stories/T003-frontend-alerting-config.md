# T003 - Frontend alerting configuration

**Domain**: frontend
**Package**: packages/dcm-frontend
**Branch**: frontend/017-implement-alerting-config
**Jira**: DCINT-322
**Depends on**: T002
**Work type**: feature

## Description

Implement Notification Settings and the Alert Config Dialog. Users can manage reusable Teams/Jira channels, test channels, associate channels with rules, and configure reminder frequency. Email remains hidden until Spec 018.

## Files to create/modify

- CREATE or UPDATE pages/components under `packages/dcm-frontend/src/`
- CREATE or UPDATE API client, query hooks, and route definitions
- CREATE tests under `packages/dcm-frontend/`

## Acceptance Criteria

- [ ] Notification Settings supports Teams/Jira channel CRUD, activation, and test action.
- [ ] Alert Config Dialog supports rule/channel association and resend frequency.
- [ ] Email channel is hidden or disabled.
- [ ] Loading, empty, validation, authorization, and network-error states are covered.
- [ ] UI shows human-readable names and never exposes raw secrets.

## Tests

- Vitest component and mocked-network tests.
- ESLint and strict TypeScript checks.

## Out of scope

- Backend implementation
- Email/MailJet UI
- Dedicated alerting page deferred by the source design

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside frontend package scope
- [ ] Jira Story creation deferred until dispatch is authorized

## Notes

See [API contract](../contracts/alerting-api.md) and [quickstart](../quickstart.md).
