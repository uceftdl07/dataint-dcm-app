# Tasks: Anomaly System Core

**Input**: Design documents from `specs/016-anomaly-system-core/`

**Prerequisites**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/`

## Ordered implementation tasks

- [ ] T001 DataEng implement anomaly rule/report Delta schema and idempotent 15-minute Rule Evaluator job -> [stories/T001-dataeng-anomaly-evaluator.md](stories/T001-dataeng-anomaly-evaluator.md)
- [ ] T002 Backend implement versioned anomaly rules/reports APIs, M2M evaluator ingress, and authorization -> [stories/T002-backend-anomaly-api.md](stories/T002-backend-anomaly-api.md)
- [ ] T003 Frontend implement Anomaly Rules page, custom-rule dialog, activation controls, and tests -> [stories/T003-frontend-anomaly-rules.md](stories/T003-frontend-anomaly-rules.md)
- [ ] T004 Frontend implement Anomaly Reports page, filters, detail view, and tests -> [stories/T004-frontend-anomaly-reports.md](stories/T004-frontend-anomaly-reports.md)

## Dependencies

- T001 provides the Delta tables and evaluator output consumed by T002.
- T002 provides API contracts consumed by T003.
- T003 and T004 depend on T001 and T002 being available in the integration environment.
- Alerting notifications remain out of scope and belong to the dependent alerting specifications.
