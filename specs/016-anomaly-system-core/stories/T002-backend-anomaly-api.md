# T002 - Backend anomaly API

**Domain**: backend
**Package**: packages/dcm-backend, packages/dcm-commons
**Branch**: backend/016-implement-versioned-anomaly-rules
**Jira**: DCINT-319
**Depends on**: T001
**Work type**: feature

## Description

Expose versioned anomaly rule and report APIs, shared models, authorization, and the M2M evaluator ingress. Enforce company-rule read-only behavior, custom-rule LZ permissions, report filtering, and Unity Catalog metric-catalog validation.

## Files to create/modify

- CREATE or UPDATE shared models under `packages/dcm-commons/`
- CREATE or UPDATE routes/services under `packages/dcm-backend/`
- CREATE tests under package test directories

## Acceptance Criteria

- [ ] Rules CRUD supports custom rules and prevents company-rule mutation.
- [ ] Create/update requires an existing caller-authorized `field_id` from DataEng-owned Unity Catalog `anomaly_metric_fields`.
- [ ] Rules and reports are limited to authorized Landing Zones.
- [ ] Reports support LZ, status, rule, and period filters.
- [ ] Internal evaluator ingress requires M2M Entra JWT and is idempotent.
- [ ] Resolve the metric identity grain per domain (see "Open design item" in
	[data-model.md](../data-model.md)) before finalizing the `anomaly_reports`
	uniqueness constraint and API contracts; do not assume `(rule_id, lz_id)` is
	sufficient for all metric types.

## Tests

- Pytest route, authorization, contract, and idempotency tests.

## Out of scope

- Frontend pages
- Notification dispatch
- Changes outside backend and shared models

## Before PR

- [ ] Rebased/merged latest develop before PR
- [ ] Tests pass
- [ ] No files outside package scope
- [ ] Diff stays reviewable
- [ ] Jira Story lists branch name

## Notes

See [API contract](../contracts/anomaly-api.md) and [data model](../data-model.md). Shared models are permitted in `dcm-commons` as the project contract boundary.
