# Tasks: Alerting Module - Email/MailJet

**Input**: Design documents from `specs/018-alerting-email-mailjet/`

**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/`

**Dispatch**: Local task planning only. No Jira Stories or branches are created by this file.

## Ordered implementation tasks

- [ ] T001 Backend implement EmailChannel, MailJet templates, AWS Secrets Manager references, and isolated retry behavior -> [stories/T001-backend-email-mailjet.md](stories/T001-backend-email-mailjet.md)
- [ ] T002 Frontend enable email channel creation and selection in existing alerting configuration UI -> [stories/T002-frontend-email-config.md](stories/T002-frontend-email-config.md)

## Dependencies

- T001 depends on Spec 017's direct AlertingService fan-out.
- T002 depends on T001's email channel contract and Spec 017's configuration UI.
- Email production rollout depends on MailJet account activation and sender-domain verification.
- Jira dispatch is intentionally not part of this local task-generation step.
