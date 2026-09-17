# T001 - DataEng alert tables

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: dataeng/017-implement-alert-tables-reminder-job
**Jira**: DCINT-320
**Depends on**: Spec 016
**Work type**: feature

## Description

Create notification channel and alert configuration tables, add alert delivery fields to anomaly reports, implement the reminder/resend job, and add the Alert Trigger integration. The Alert Trigger calls the Spec 017 internal ingress after an evaluator opens/updates an incident and calls the resolution ingress after finalization. Store only managed-secret references and preserve idempotent reminder processing.

## Files to create/modify

- CREATE or UPDATE schema, Alert Trigger, and reminder-job files under `packages/dcm-databricks-pipeline/`
- CREATE tests under `packages/dcm-databricks-pipeline/tests/`

## Acceptance Criteria

- [ ] Tables and anomaly report alert fields match the Spec B data model.
- [ ] The schema permits `email`, `teams`, and `jira` channel types; email delivery remains disabled until Spec 018.
- [ ] Alert Trigger calls the internal report ingress after incident open/update and the resolution ingress after incident finalization, using the dedicated M2M identity.
- [ ] Active configurations are selected by resend frequency and inactive configurations are ignored.
- [ ] Reminder processing updates `last_reminder_sent_at` idempotently.
- [ ] No raw Teams webhook or Jira token is persisted.

## Tests

- Pytest schema, Alert Trigger, and reminder-job tests with test-only fixtures, including incident and resolution lifecycle calls.

## Out of scope

- Backend worker and channel clients
- Frontend configuration UI
- Email/MailJet

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside package scope
- [ ] Jira Story creation deferred until dispatch is authorized

## Notes

See [data model](../data-model.md) and [worker contract](../contracts/alerting-worker.md).
