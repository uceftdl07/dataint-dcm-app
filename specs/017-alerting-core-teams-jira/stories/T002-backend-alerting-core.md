# T002 - Backend alerting core

**Domain**: backend
**Package**: packages/dcm-backend, packages/dcm-commons
**Branch**: backend/017-implement-alerting-core
**Jira**: DCINT-321
**Depends on**: T001 and Spec 016
**Work type**: feature

## Description

Implement direct backend dispatch after the Databricks Alert Trigger calls the internal report endpoints, and Teams/Jira notification channels. The backend reads reports/configuration from Unity Catalog through SQL Warehouse access, fans out channels independently, and resolves AWS Secrets Manager references through ECS task IAM. Add project-scoped configuration and manual re-notify APIs.

## Files to create/modify

- CREATE or UPDATE shared alerting contracts under `packages/dcm-commons/`
- CREATE or UPDATE alerting services, channels, and API routes under `packages/dcm-backend/`
- CREATE tests under package test directories

## Acceptance Criteria

- [ ] Direct dispatch reads persisted reports and active project-authorized configuration from Unity Catalog; no SQS queue or worker is introduced.
- [ ] Backend treats `report_id + notification_type + channel_id` as delivery identity and reuses existing Jira ticket URL.
- [ ] Teams and Jira fan-out runs independently; each failed delivery gets one retry, then is logged and discarded.
- [ ] Jira creates at most one issue per active incident and stores its URL.
- [ ] Raw secrets never enter Unity Catalog rows, logs, or responses; AWS Secrets Manager references resolve through ECS task IAM.

## Tests

- Pytest API, direct-dispatch, idempotency, retry, AWS Secrets Manager, Teams, Jira, and cross-project authorization tests with mocked external services.

## Out of scope

- Frontend implementation
- Email/MailJet
- Changes outside backend and shared models

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside package scope
- [ ] Jira Story creation deferred until dispatch is authorized

## Notes

See [API contract](../contracts/alerting-api.md), [worker contract](../contracts/alerting-worker.md), and [research](../research.md).
