# Feature Specification: Alerting Module (core — Teams + Jira)

**Feature Branch**: `017-alerting-core-teams-jira`

**Created**: 2026-08-28

**Status**: Draft

**Work type**: feature

**Priority**: P1

**Domains**: DataEng, Backend, Frontend

**Input**: User description: "Alerting module core: notification channels, alert configs, AlertingService fan-out, Teams and Jira channels"

**Source docs**: [Alerting overview](../../docs/spike/anomaly-alerting-system/alerting-module-dcm.md), [Operational description](../../docs/spike/anomaly-alerting-system/alerting-module-dcm-operational-description.md), [Technical architecture](../../docs/spike/anomaly-alerting-system/alerting-module-dcm-technical-architecture.md), [Design](../../docs/spike/anomaly-alerting-system/alerting-module-dcm-design.md), [Data model](../../docs/spike/anomaly-alerting-system/alerting-module-dcm-data-model.md)

**Note**: Email/MailJet channel is **out of scope** here — separate follow-up spec (Spec B2), isolated because it is blocked on a PO action (MailJet account activation + domain verification) unrelated to engineering readiness.

## Clarifications

### Session 2026-08-28

- Q: Which mechanism should deliver alert notifications? → A: No SQS. The Databricks Alert Trigger calls the backend Alerting Service directly; the backend reads alerting data from Unity Catalog through its supported SQL Warehouse access and fans out asynchronously.
- Q: How should failed Teams or Jira deliveries be retried? → A: One retry, then structured logging and discard. The retry policy is fixed for this spec.
- Q: Should Jira create one ticket for every anomaly occurrence or group repeated occurrences into one incident ticket? → A: One Jira ticket per active anomaly incident. Repeated detections reuse the existing ticket through `jira_ticket_url`.
- Q: How are repeated delivery requests handled? → A: The backend treats `(report_id, notification_type, channel_id)` as the delivery identity; Jira creation also reuses an existing `jira_ticket_url`.

## Prerequisites

- **Spec A dependency**: [016-anomaly-system-core](../016-anomaly-system-core/spec.md) must be merged/available — this spec consumes its `AnomalyRule`/`AnomalyReport` contract and `anomaly_reports` table (adds columns to it, does not redefine it).
- **Secrets naming confirmed**: AWS Secrets Manager references `dcm-teams-webhook-{name}` and `dcm-jira-api-token` — no secret value is stored in a Unity Catalog table, only its secret reference (`config_json.secret_name`). The backend ECS task role resolves it at runtime.
- **Small branches**: 3 tickets (DataEng, Backend, Frontend) stay scoped to their own package per the Contracts section below.

## Contracts

Shared read-only reference for all 3 tickets.

### `NotificationChannel` (table `notification_channels`)

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | PK |
| `name` | string | e.g. "Canal Teams DataOps" |
| `channel_type` | enum | `email` \| `teams` \| `jira` (`email` inert in this spec — no `EmailChannel` implementation until B2) |
| `project_id` | UUID | Required owner project; a project may cover multiple LZ IDs, workspaces, and catalogs |
| `config_json` | JSON | per-type shape below — **never contains a raw secret, only an AWS Secrets Manager reference** |
| `is_active` | boolean | |
| `created_by` | string | Entra OID |
| `created_at` | timestamp | |

`config_json` shape by type:
- `teams`: `{"secret_name": str}` -> resolves to the webhook URL
- `jira`: `{"project_key": str, "issue_type": str, "secret_name": str}` -> resolves to the API token

### `AlertConfig` (table `alert_configs`)

| Field | Type | Notes |
| --- | --- | --- |
| `id` | UUID | PK |
| `rule_id` | UUID | FK -> `anomaly_rules.id` (Spec A) |
| `channel_id` | UUID | FK -> `notification_channels.id` |
| `is_active` | boolean | |
| `resend_frequency` | enum | `immediate_only` (default) \| `daily` \| `weekly` \| `monthly` |
| `last_reminder_sent_at` | timestamp \| null | dedup guard for the reminder job |
| `created_by` | string | |
| `created_at` | timestamp | |

Unique constraint: `(rule_id, channel_id)`.

### `anomaly_reports` columns added by this spec

`jira_ticket_url` (string, null until a Jira channel fires), `alert_sent_at` (timestamp), `resolution_sent_at` (timestamp). These are the only changes to the Spec A table — no other column is touched.

### Dispatch contract

`AlertingService.dispatch(report_id, notification_type)` — `notification_type` is `"incident"` (initial alert / reminder) or `"resolution"`. The Databricks Alert Trigger calls the backend internal endpoint after report persistence. The backend reads the report, active configurations, and project-owned channels from Unity Catalog through its SQL Warehouse access, builds one `NotificationChannel` per configuration, fans out via `asyncio.gather`, and updates `alert_sent_at` or `resolution_sent_at`. Each channel resolves its AWS Secrets Manager reference at runtime through the ECS task IAM role.

**Explication simple / Plain-language flow:** Databricks detects or resolves an incident, then calls the backend. The backend reads the incident and its configured channels from Unity Catalog, sends notifications independently, and records successful sends. There is no SQS queue or separate worker in this design.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Notify on incident detection (Priority: P1)

As a DCM operator with a Teams and/or Jira channel configured for a rule, I receive a notification as soon as an anomaly incident opens, so I can react without checking the Reports page manually.

**Why this priority**: Core value of the module — without dispatch on detection, alerting delivers nothing.

**Independent Test**: Configure an `alert_config` (rule -> Teams channel), trigger an incident (via Spec A's Rule Evaluator or a direct `anomaly_reports` insert), verify the Teams webhook receives an Adaptive Card and `alert_sent_at` is set.

**Acceptance Scenarios**:

1. **Given** an active `alert_config` linking a rule to a Teams channel, **When** `AlertingService.dispatch(report_id, "incident")` runs for that rule's new report, **Then** a POST is sent to the Teams webhook URL and `anomaly_reports.alert_sent_at` is updated.
2. **Given** an active `alert_config` linking a rule to a Jira channel, **When** dispatch runs, **Then** a Jira issue is created in the configured project, and `anomaly_reports.jira_ticket_url` is set to the created issue URL.
3. **Given** a rule with both a Teams and a Jira `alert_config` active, **When** dispatch runs, **Then** both channels are notified in parallel (`asyncio.gather`) and a failure in one channel does not block the other.
4. **Given** `anomaly_reports.jira_ticket_url` is already set for a report, **When** dispatch runs again for the same report, **Then** no duplicate Jira issue is created (idempotence check).

---

### User Story 2 - Manage notification channels (Priority: P1)

As a DCM user, I create and manage reusable Teams/Jira notification channels so they can be attached to any rule without re-entering secrets.

**Why this priority**: Channels are the reusable building block — required before any alert config can exist.

**Independent Test**: Create a Teams channel via the Notification Settings page (name + webhook URL), verify `notification_channels` row is created with `config_json.secret_name` only (no raw URL persisted in DB), verify "Test" button sends a real test notification.

**Acceptance Scenarios**:

1. **Given** the Notification Settings page, **When** an authorized user creates a Teams channel for a project (name + webhook URL), **Then** the webhook URL is stored in AWS Secrets Manager under `dcm-teams-webhook-{name}` and the Unity Catalog row stores only `project_id` and `{"secret_name": "dcm-teams-webhook-{name}"}`.
2. **Given** an existing channel, **When** a user clicks "Test", **Then** a test notification is sent through that channel without affecting any `anomaly_reports` row.
3. **Given** an existing channel, **When** a user deactivates it, **Then** all `alert_configs` referencing it are effectively ignored by dispatch (no need to delete them).

---

### User Story 3 - Configure alerting per rule (Priority: P2)

As a DCM user, I associate a rule with one or more channels and a resend frequency, so notifications match how urgently I want to be alerted while an incident stays active.

**Why this priority**: Delivers the "who gets notified and how often" control; depends on Stories 1-2 existing (channels + dispatch) first.

**Independent Test**: Open the Alert Config Dialog for a rule, select Teams + Jira channels, set `resend_frequency=daily`, verify `alert_configs` rows created; verify the reminder job re-sends after 24h while the incident stays active and stops after resolution.

**Acceptance Scenarios**:

1. **Given** the Alert Config Dialog for a rule, **When** a user selects Teams and Jira channels with `resend_frequency=daily`, **Then** two `alert_configs` rows are created (one per channel), both `is_active=true`.
2. **Given** an active incident with `resend_frequency=daily` and `last_reminder_sent_at` more than 24h ago, **When** the reminder job runs, **Then** a reminder notification is sent and `last_reminder_sent_at` is updated.
3. **Given** an incident transitions to `finalized` (resolved in Spec A), **When** the reminder job runs, **Then** no further reminders are sent for that config, and a resolution notification (`notification_type="resolution"`) is dispatched once, updating `resolution_sent_at`.

### Edge Cases

- AWS Secrets Manager reference in `config_json.secret_name` is missing/deleted — channel must be skipped with a critical log, not crash the whole fan-out (other channels still process).
- Teams webhook or Jira API returns 5xx — retry once, then log and discard that channel delivery without blocking other channels.
- A rule has zero active `alert_configs` — dispatch is a no-op, `alert_sent_at` stays null, no error raised.
- Same channel reused by multiple rules — deleting/deactivating the channel must not silently break other rules' alerting without visibility (Notification Settings page must show usage count or the deactivation must be intentional).
- Manual re-notify (`POST /anomaly-reports/{id}/notify`, user-triggered) races with the reminder job's scheduled send — both update `alert_sent_at`; last write wins, no duplicate channel sends within the same request.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide `AlertingService.dispatch(report_id, notification_type)` invoked by the Databricks Alert Trigger after incident creation/update or resolution; it reads Unity Catalog data and performs isolated asynchronous channel fan-out without SQS.
- **FR-002**: System MUST support `teams` and `jira` channel types in this spec (`email` type is stored/selectable in schema but has no working implementation until Spec B2).
- **FR-003**: System MUST NOT persist any raw secret (webhook URL, API token) in `notification_channels.config_json` — only an AWS Secrets Manager reference, resolved at runtime through ECS task IAM.
- **FR-004**: System MUST fan out to all active channels for a rule in parallel and continue processing other channels if one fails.
- **FR-005**: System MUST be idempotent for Jira ticket creation — no duplicate issue if `anomaly_reports.jira_ticket_url` is already set.
- **FR-005a**: The backend MUST treat repeated dispatch of `report_id`, `notification_type`, and `channel_id` as the same delivery identity; Jira creation MUST reuse an existing `jira_ticket_url`.
- **FR-006**: System MUST provide a Databricks reminder job that re-sends notifications for active incidents per `alert_configs.resend_frequency`, deduplicated via `last_reminder_sent_at`.
- **FR-007**: System MUST provide a manual re-notify endpoint (`POST /anomaly-reports/{id}/notify`, JWT user) for ad-hoc re-alerting.
- **FR-008**: Frontend MUST provide a Notification Settings page (channel CRUD + test button) and an Alert Config Dialog (rule<->channel association, resend frequency), scoped to the user's authorized project. Each project manages its own channels and may contain multiple LZ IDs, workspaces, and catalogs. Email remains hidden or disabled until Spec B2.

### Key Entities *(include if feature involves data)*

- **NotificationChannel**: a reusable notification destination (Teams/Jira in this spec), see Contracts.
- **AlertConfig**: association between an `AnomalyRule` (Spec A) and a `NotificationChannel`, see Contracts.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A newly opened or finalized incident is persisted before the Databricks Alert Trigger calls the backend; backend channel fan-out is asynchronous and independent per channel.
- **SC-002**: Fan-out to 2 configured channels completes without one channel's failure delaying or blocking the other (verified via induced failure in one channel during test).
- **SC-003**: Reminder job re-sends within 1 hour of the configured `resend_frequency` window elapsing (e.g., `daily` -> sent between 24h and 25h after the previous send).

## Assumptions

- Spec A (`016-anomaly-system-core`) is complete and its `anomaly_rules`/`anomaly_reports` tables and internal ingestion endpoint exist before this spec's DataEng/Backend work starts.
- Backend ECS task IAM access to AWS Secrets Manager is available for alerting secret references.
- Email/MailJet channel is entirely out of scope; the `email` enum value exists in schema for forward compatibility but has no channel implementation in this spec.
- MCP Atlassian / Jira REST API credentials setup follows the same pattern already used elsewhere in DCM for Jira integration.
