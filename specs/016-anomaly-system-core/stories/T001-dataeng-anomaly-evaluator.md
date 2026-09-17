# T001 - DataEng anomaly evaluator

**Domain**: dataeng
**Package**: packages/dcm-databricks-pipeline
**Branch**: dataeng/016-implement-anomaly-rule-report-delta
**Jira**: DCINT-317
**Depends on**: none
**Work type**: feature

## Description

Create the `anomaly_metric_fields`, `anomaly_rules`, and `anomaly_reports` Delta schemas and implement the idempotent 15-minute evaluator across all six domains. The evaluator resolves each rule's `field_id` against the DataEng-owned metric-field catalog, then opens/finalizes incidents, preserves threshold snapshots, and isolates failed evaluations.

## Files to create/modify

- CREATE or UPDATE pipeline evaluator and schema files under `packages/dcm-databricks-pipeline/`
- CREATE tests under `packages/dcm-databricks-pipeline/tests/`

## Acceptance Criteria

- [ ] Active rules are evaluated on the scheduled cycle across all six domains.
- [ ] Each rule references one existing `anomaly_metric_fields` record; one metric-field record can be used by multiple rules.
- [ ] One active incident maximum exists per `(rule_id, lz_id)`.
- [ ] Continued breaches do not create duplicates; recovery finalizes the incident.
- [ ] Evaluation failures retry, then create `unknown` reports and structured operational alerts without stopping other rules.

## Tests

- Pytest evaluator unit/integration tests with test-only fixtures.
- Validate idempotent rerun and active-incident uniqueness.

## Out of scope

- Backend API routes
- Frontend pages
- Teams, Jira, or email notifications

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside package scope
- [ ] Diff stays reviewable
- [ ] Jira Story lists branch name

## Notes

See [data model](../data-model.md), [API contract](../contracts/anomaly-api.md), and [quickstart](../quickstart.md).
