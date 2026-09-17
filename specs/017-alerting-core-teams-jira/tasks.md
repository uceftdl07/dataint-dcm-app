# Tasks: Alerting Module Core - Teams and Jira

**Input**: Design documents from `specs/017-alerting-core-teams-jira/`

**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/`

**Dispatch**: Local task planning only. No Jira Stories or branches are created by this file.

## Ordered implementation tasks

- [ ] T001 DataEng implement notification tables, anomaly report alert fields, and reminder job -> [stories/T001-dataeng-alert-tables.md](stories/T001-dataeng-alert-tables.md)
- [ ] T002 Backend implement direct alert dispatch, Teams/Jira channels, and alerting API -> [stories/T002-backend-alerting-core.md](stories/T002-backend-alerting-core.md)
- [ ] T003 Frontend implement Notification Settings and Alert Config Dialog -> [stories/T003-frontend-alerting-config.md](stories/T003-frontend-alerting-config.md)

## Dependencies

- T001 provides notification/config storage and reminder-job data consumed by T002.
- T002 provides direct dispatch and project-scoped configuration APIs consumed by T003.
- T003 depends on T001 and T002 being available in the integration environment.
- Email/MailJet remains out of scope and belongs to Spec 018.
