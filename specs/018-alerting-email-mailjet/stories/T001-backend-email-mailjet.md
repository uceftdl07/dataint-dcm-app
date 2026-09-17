# T001 - Backend email MailJet

**Domain**: backend
**Package**: packages/dcm-backend, packages/dcm-commons
**Branch**: backend/018-implement-emailchannel-mailjet-templates
**Jira**: DCINT-323
**Depends on**: Spec 017
**Work type**: feature

## Description

Implement `EmailChannel` on the existing direct AlertingService fan-out path. Render incident, reminder, resolution, and test messages through MailJet, resolving ITSM-provisioned credentials and approved shared-mailbox sender from AWS Secrets Manager through ECS task IAM.

## Files to create/modify

- CREATE or UPDATE EmailChannel and templates under `packages/dcm-backend/`
- UPDATE shared alerting models under `packages/dcm-commons/` if required
- CREATE tests under package test directories

## Acceptance Criteria

- [ ] EmailChannel sends populated incident and resolution HTML templates.
- [ ] MailJet API key, secret key, and sender are resolved from AWS Secrets Manager through ECS task IAM; raw secrets are never persisted or logged.
- [ ] Delivery retries once, then logs and discards without blocking Teams/Jira.
- [ ] Missing credentials and MailJet failures are isolated from other channels.
- [ ] After the ITSM MailJet request is fulfilled, sandbox API authentication and a sandbox test send are validated before environment enablement.
- [ ] Test sends use sandbox credentials in non-production and require confirmation in production.

## Tests

- Pytest EmailChannel, template, secret-resolution, retry, project authorization, and fan-out isolation tests with mocked MailJet/AWS Secrets Manager.

## Out of scope

- New alerting orchestrator or queue
- Notification tables
- Frontend UI
- Production enablement before MailJet account/domain verification

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside backend/shared-model scope
- [ ] Jira Story creation deferred until dispatch is authorized

## Notes

See [email worker contract](../contracts/email-channel-worker.md) and [email API contract](../contracts/email-channel-api.md).
See the [ITSM MailJet catalog item](https://itsm.hubtotal.net/sp/?id=sc_cat_item&sys_id=b8b4a43b897e178818d4f32413c6e63e) for account and sender provisioning.
