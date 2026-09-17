# T002 - Frontend email configuration

**Domain**: frontend
**Package**: packages/dcm-frontend
**Branch**: frontend/018-enable-email-channel-creation-and
**Jira**: DCINT-324
**Depends on**: T001 and Spec 017
**Work type**: feature

## Description

Enable email channels in the existing Notification Settings and Alert Config Dialog. Users can create a channel with recipients, test it safely by environment, and associate it with anomaly rules.

## Files to create/modify

- UPDATE pages/components under `packages/dcm-frontend/src/`
- UPDATE API client, query hooks, and route definitions as required
- CREATE tests under `packages/dcm-frontend/`

## Acceptance Criteria

- [ ] Email channel creation requires at least one valid recipient.
- [ ] Email channels can be selected in Alert Config Dialog.
- [ ] Test action uses sandbox behavior in non-production and confirmation in production.
- [ ] UI never displays raw MailJet credentials.
- [ ] Loading, empty, validation, authorization, and network-error states are covered.

## Tests

- Vitest component and mocked-network tests.
- ESLint and strict TypeScript checks.

## Out of scope

- Backend EmailChannel implementation
- Teams/Jira behavior
- New configuration page
- Production activation before MailJet verification

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside frontend package scope
- [ ] Jira Story creation deferred until dispatch is authorized

## Notes

See [email API contract](../contracts/email-channel-api.md) and [quickstart](../quickstart.md).
