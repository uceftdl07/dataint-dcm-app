# Feature Specification: Anomaly System (core)

**Feature Branch**: `016-anomaly-system-core`

**Created**: 2026-08-28

**Status**: Draft

**Work type**: feature

**Priority**: P1

**Domains**: DataEng, Backend, Frontend

**Input**: User description: "Anomaly detection system core: rules, reports, rule evaluator job, rules API, frontend pages"

**Source docs**: [Anomaly System design](../../docs/spike/anomaly-alerting-system/anomaly-system-dcm-design.md), [Confluence source](https://tdf.atlassian.net/wiki/spaces/TDF/pages/4816109960/Anomaly+System+DCM+Design)

**Note**: Alerting (notifications, `notification_channels`, `alert_configs`, MailJet/Teams/Jira) is **out of scope** here — it is a separate follow-up spec (Spec B) that will consume this spec's `AnomalyRule` / `AnomalyReport` contract.

## Clarifications

### Session 2026-08-28

- Q: When the Rule Evaluator detects multiple simultaneous breaches for the same rule and landing zone before the first incident resolves, should it keep exactly one active incident or allow several to coexist? → A: One active incident per `(rule_id, lz_id)` — `UNIQUE` constraint, re-breaches just extend the existing incident.
- Q: Which anomaly rules should be included in the first implementation? → A: All six domains: pipeline, compute, cost, standard_check, storage, and database.
- Q: Where should the initial company rules and thresholds come from? → A: Dynamic Unity Catalog configuration; exact source definition is finalized during planning.
- Q: Should company rules be enabled by default in every environment? → A: Activation is controlled per environment; no hard-coded default behavior.
- Q: Who can create or activate custom anomaly rules? → A: DCM administrators and users assigned to the relevant Landing Zone.
- Q: What happens when metric data cannot be read or a rule cannot be evaluated? → A: Retry evaluation; if retries fail, create an `unknown` report and raise a structured operational alert.
- Q: How are valid metrics controlled across the six domains? → A: DataEng owns Unity Catalog `anomaly_metric_fields`. A rule stores `field_id`; the backend rejects an unknown or unauthorized field reference. Product approves company-rule threshold basis.

## Prerequisites

- **P1 company rules spike**: identify target metrics/thresholds per domain (pipeline, compute, cost, standard_check, storage, database) before `/speckit.plan`. Without this, the Rule Evaluator job has no seeded company rules to evaluate — custom rules (user-created) can still function without it.
- **Metric catalog**: before backend rule CRUD and evaluator implementation, DataEng provides Unity Catalog `anomaly_metric_fields` for `pipeline`, `compute`, `cost`, `standard_check`, `storage` `usage`, and `database`. Each entry identifies `name`, `description`, `gold_table_name`, and `domain`; the evaluator configuration defines the remaining calculation, key, freshness, conversion, and threshold rules.
- **Small branches**: each of the 3 tickets (DataEng, Backend, 2x Frontend) stays scoped to its own package and checklist per the Contracts section — no cross-domain files in a single PR.

## Contracts

Shared read-only reference for all 3 tickets — keeps each domain's context scoped to its own files plus this section.

### `AnomalyRule`

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | PK |
| `name` | string | |
| `description` | string | |
| `field_id` | UUID | FK -> `anomaly_metric_fields.id`; identifies metric name, Gold table, and domain |
| `operator` | enum | `>` \| `<` \| `>=` \| `<=` \| `=` \| `!=` |
| `threshold_value` | decimal | |
| `severity` | enum | `low` \| `medium` \| `high` \| `critical` |
| `rule_type` | enum | `company` (read-only, seeded) \| `custom` (user-created) |
| `trigger_mode` | enum | `scheduled` \| `on_demand` |
| `lz_scope` | array\<string\> \| null | null = all LZ |
| `is_active` | boolean | |
| `created_by` | string | Entra OID |
| `created_at` | timestamp | |

### `AnomalyReport`

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | PK |
| `rule_id` | UUID | FK -> `anomaly_rules.id` |
| `lz_id` | string | |
| `metric_value` | decimal | observed value at detection/last check |
| `threshold_value` | decimal | snapshot of rule threshold at detection |
| `status` | enum | `active` \| `finalized` \| `unknown` |
| `start_date` | timestamp | |
| `end_date` | timestamp \| null | |
| `logs` | JSON | raw evaluation context |
| `created_at` | timestamp | |

Unique constraint: `UNIQUE (rule_id, lz_id) WHERE status = 'active'` — at most one active incident per rule/LZ (see Clarifications). Evaluation failures produce `unknown` reports and do not create active incidents.

Reserved for Spec B (not populated by this spec): `jira_ticket_url`, `alert_sent_at`, `resolution_sent_at`.

### Internal ingestion contract

`POST /internal/anomaly-reports` — called by the Databricks Rule Evaluator job, M2M JWT (Entra ID client_credentials). Body: `{ rule_id, lz_id, metric_value, threshold_value, logs }`. No notification side effect in this spec (Spec B adds that later via the same endpoint or a hook).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Detect anomalies automatically (Priority: P1)

As a DCM operator, anomalies in metric data (pipeline, compute, cost, standard_check, storage, database) are detected automatically every 15 minutes so incidents are visible without manual checking.

**Why this priority**: Core value of the feature — without detection, there is nothing to report or (later) alert on.

**Independent Test**: Seed an active `anomaly_rule`, insert a metric value breaching its threshold, wait for/trigger the Rule Evaluator job, verify an `anomaly_reports` row is created with `status=active`.

**Acceptance Scenarios**:

1. **Given** an active rule with threshold `metric_value > 100` and no existing active incident for `(rule_id, lz_id)`, **When** the Rule Evaluator runs and finds `metric_value = 120`, **Then** a new `anomaly_reports` row is inserted with `status=active`, `start_date=now`.
2. **Given** an active incident for `(rule_id, lz_id)`, **When** the Rule Evaluator runs and the metric no longer breaches the threshold, **Then** the incident is updated to `status=finalized`, `end_date=now`.
3. **Given** an active incident for `(rule_id, lz_id)`, **When** the Rule Evaluator runs and the metric still breaches the threshold, **Then** the incident's `end_date`/duration is recalculated, no duplicate row is created.

---

### User Story 2 - Manage anomaly rules (Priority: P1)

As a DCM user, I create, view, and toggle custom anomaly rules per domain so detection can be tuned without code changes.

**Why this priority**: Company rules alone aren't sufficient — teams need custom rules for their own LZ/domain thresholds.

**Independent Test**: Create a custom rule via the API/UI, verify it appears in the Rule Evaluator's active rule set on the next run, toggle it inactive, verify it's excluded.

**Acceptance Scenarios**:

1. **Given** the Anomaly Rules page, **When** a user creates a custom rule (field_id, operator, threshold, severity, trigger_mode, lz_scope), **Then** the rule is persisted with `rule_type=custom` and appears in the rules table with metric name and domain resolved from `anomaly_metric_fields`.
2. **Given** a company rule (`rule_type=company`), **When** a user views it, **Then** edit controls are disabled (read-only).
3. **Given** a custom rule, **When** a user toggles it inactive, **Then** the Rule Evaluator excludes it from the next run.

---

### User Story 3 - Review anomaly reports (Priority: P2)

As a DCM user, I view a history of detected incidents (active and finalized) with filters, so I can investigate and track resolution.

**Why this priority**: Visibility into what was detected — required for the feature to deliver value to end users, but depends on Stories 1-2 existing first.

**Independent Test**: With seeded `anomaly_reports` rows (active + finalized), open the Anomaly Reports page, filter by LZ/status/rule/period, open a report's detail view.

**Acceptance Scenarios**:

1. **Given** existing reports with mixed statuses, **When** a user filters by `status=active`, **Then** only active incidents are listed.
2. **Given** a report row, **When** a user opens its detail view, **Then** `metric_value`, `threshold_value`, and `logs` (formatted JSON) are displayed. `jira_ticket_url` link is not shown (reserved field, populated by Spec B).

### Edge Cases

- Rule Evaluator job overlaps with a still-running previous execution (cron 15min) — must not double-process or create duplicate incidents.
- A rule references a `field_id` whose catalog record cannot be read or whose Gold table no longer exposes the configured metric — evaluation should skip and log, not crash the job.
- A custom rule with `lz_scope=null` — must evaluate against all LZ the creating user has access to (not literally all LZ in the platform, unless the user is Admin).
- Company rule thresholds change (re-seeded) — existing active incidents keep their original `threshold_value` snapshot; only new evaluations use the updated threshold.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST evaluate all active `anomaly_rules` against current metric data on a 15-minute schedule (Databricks job).
- **FR-002**: System MUST open a new `anomaly_reports` incident (`status=active`) when a rule's threshold is breached and no active incident exists for `(rule_id, lz_id)`.
- **FR-003**: System MUST finalize (`status=finalized`, `end_date=now`) an active incident when its rule's metric no longer breaches the threshold.
- **FR-004**: System MUST expose CRUD for `anomaly_rules` restricted to `rule_type=custom` (company rules are read-only via API), and reject an unknown or unauthorized `field_id` from DataEng-owned Unity Catalog `anomaly_metric_fields`.
- **FR-005**: System MUST expose `GET /anomaly-reports` with filters by LZ, status, rule, and period.
- **FR-006**: System MUST expose `POST /internal/anomaly-reports` secured by M2M JWT (Entra ID client_credentials), used only by the Databricks pipeline.
- **FR-007**: Frontend MUST provide an Anomaly Rules page (list, create/edit custom rule dialog, activate/deactivate toggle).
- **FR-008**: Frontend MUST provide an Anomaly Reports page (list, filters, detail view).
- **FR-009**: System MUST NOT trigger any notification/alerting side effect from this spec (deferred to Spec B).
- **FR-010**: System MUST retry failed metric reads or rule evaluations and, after retry exhaustion, create an `unknown` report and emit a structured operational alert without stopping evaluation of other rules.

### Key Entities *(include if feature involves data)*

- **AnomalyRule**: a detection rule (company-seeded or custom), see Contracts.
- **AnomalyReport**: a detected incident (active or finalized), see Contracts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A metric breach is reflected as an `anomaly_reports` incident within one Rule Evaluator cycle (≤15 min) of the breach occurring.
- **SC-002**: Users can create a custom rule and see it evaluated within one Rule Evaluator cycle of activation.
- **SC-003**: Anomaly Reports page loads and filters incidents in under 2 seconds for a LZ with 1000+ historical reports.

## Assumptions

- Company P1 rules (metrics/thresholds) are defined via the spike in Prerequisites before implementation of the seeded rule set; custom rules are not blocked by this.
- Dedup policy resolved as part of Prerequisites before DataEng task starts.
- Existing DCM metric domains (pipeline, compute, cost, standard_check, storage, database) and their Delta tables in Unity Catalog are the data source for rule evaluation; no new metric collection is introduced by this spec.
- Alerting/notification behavior is entirely out of scope (Spec B).
