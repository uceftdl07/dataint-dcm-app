# Feature Specification: Alerting Module — Email Channel (MailJet)

**Feature Branch**: `018-alerting-email-mailjet`

**Created**: 2026-08-28

**Status**: Draft

**Work type**: feature

**Priority**: P2

**Domains**: Backend, Frontend

**Input**: User description: "Alerting module email channel: MailJet integration, isolated due to PO blocker"

**Source docs**: [Alerting operational description §5-6](../../docs/spike/anomaly-alerting-system/alerting-module-dcm-operational-description.md), [Alerting technical architecture §3](../../docs/spike/anomaly-alerting-system/alerting-module-dcm-technical-architecture.md), [Alerting design §6](../../docs/spike/anomaly-alerting-system/alerting-module-dcm-design.md), [Alerting data model §6](../../docs/spike/anomaly-alerting-system/alerting-module-dcm-data-model.md)

**Note**: This is the smallest, last spec of the Anomaly/Alerting trilogy (A: 016-anomaly-system-core, B1: 017-alerting-core-teams-jira, **B2: this spec**). It adds exactly one channel type (`email`) to an already-shipped Alerting core — no new tables, no new orchestrator.

## Clarifications

### Session 2026-08-28

- Q: How many retries should Email/MailJet use when delivery fails? → A: One retry, then structured logging and discard, matching Spec 017.
- Q: Which sender email address should MailJet use for DCM alerts? → A: A configurable sender email resolved from AWS Secrets Manager through the backend ECS task IAM role, using `dcm-mailjet-sender-email`.
- Q: How should Email/MailJet behave before the production account and sender domain are verified? → A: Use sandbox/test credentials in development and staging; keep Email/MailJet disabled in production until verification and explicit enablement.
- Q: When a user clicks “Test” for an email channel, should it send to the configured recipients? → A: Use sandbox delivery in non-production; require explicit confirmation before sending to real recipients in production.

## Prerequisites

- **Spec B1 dependency**: [017-alerting-core-teams-jira](../017-alerting-core-teams-jira/spec.md) must be merged/available — `AlertingService`, `NotificationChannel` ABC, `notification_channels`/`alert_configs` tables already exist. This spec adds one concrete channel implementation.
- **⚠️ BLOCKING — MailJet request required**: the Product Owner must request MailJet account creation or modification through the [ITSM MailJet catalog item](https://itsm.hubtotal.net/sp/?id=sc_cat_item&sys_id=b8b4a43b897e178818d4f32413c6e63e) before credentials, sender, or production validation are available.
- **Sender prerequisites**: the sender must use an existing shared mailbox on `mailing.totalenergies.com`, or `corporate.totalenergies.com` with MailJet Product Owner approval. Personal user addresses are not allowed as senders.
- **Pre-production API validation**: after the request provisions sandbox/test credentials and an approved sender, engineering validates MailJet authentication and a sandbox send before enabling the email channel in any environment. Production remains disabled until the account and sender domain are verified.
- **Small branches**: 2 tickets (Backend, Frontend), each touching only its own package.

## Contracts

References `NotificationChannel` ABC and `notification_channels.config_json` schema defined in Spec B1 — not redefined here.

### `email` channel `config_json` shape

```json
{"secret_name": "dcm-mailjet-api-key", "recipients": ["team@totalenergies.com"]}
```

### Secrets (AWS Secrets Manager, resolved at runtime through ECS task IAM — never stored in Unity Catalog)

| Secret | AWS Secrets Manager reference |
| --- | --- |
| MailJet API Key | `dcm-mailjet-api-key` |
| MailJet Secret Key | `dcm-mailjet-secret-key` |
| Sender email address | `dcm-mailjet-sender-email` |

### Email template variables

`rule_name`, `severity`, `lz_id`, `metric_value`, `threshold_value`, `start_date`, `report_url`. Subject: `[{severity}] Anomalie DCM : {rule_name} / {lz_id}`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Receive email notification on incident (Priority: P1)

As a DCM team member on an email distribution list, I receive an email when an anomaly incident opens for a rule my channel is configured on, so I have an audit trail independent of Teams/Jira access.

**Why this priority**: Core value of this spec — the only new capability it adds.

**Independent Test**: Configure an `alert_config` (rule -> email channel with test recipients), trigger an incident, verify a MailJet API call is made with the correct template variables and `alert_sent_at` is updated (same dispatch path as Spec B1, new channel implementation only).

**Acceptance Scenarios**:

1. **Given** an active `alert_config` linking a rule to an `email` channel, **When** `AlertingService.dispatch` runs (existing B1 orchestration, unchanged), **Then** `EmailChannel.send()` calls the MailJet API with the HTML template populated from the report, and `anomaly_reports.alert_sent_at` is updated.
2. **Given** a rule with Teams + Jira + Email channels all active, **When** dispatch runs, **Then** all three channels are notified in the same `asyncio.gather` fan-out (B1's existing mechanism), with email failure not blocking Teams/Jira.
3. **Given** an incident resolves, **When** the resolution dispatch runs, **Then** a "resolved" email (green template) is sent to the same recipients.

---

### User Story 2 - Configure email channel and recipients (Priority: P1)

As a DCM user, I create an email channel with a name and a list of recipients, and select it in the Alert Config Dialog, so my team gets notified via email.

**Why this priority**: Without UI to create the channel, the backend implementation is unreachable by users.

**Independent Test**: Open Notification Settings (already built in B1 with email hidden/disabled), enable the email option, create a channel with 2 recipient addresses, verify it appears and can be selected in the Alert Config Dialog.

**Acceptance Scenarios**:

1. **Given** the Notification Settings page, **When** a user creates an email channel (name + recipient list), **Then** a `notification_channels` row is created with `channel_type=email` and `config_json={"secret_name": ..., "recipients": [...]}`.
2. **Given** an existing email channel, **When** a user clicks "Test", **Then** a test email is sent to the configured recipients via MailJet.
3. **Given** the Alert Config Dialog for a rule, **When** a user toggles the Email channel (previously hidden in B1), **Then** it is now selectable and behaves identically to Teams/Jira toggles.

### Edge Cases

- MailJet API key secret not yet provisioned (PO action pending) — `EmailChannel._resolve_secret` fails; must log a critical error and skip the channel without blocking Teams/Jira dispatch (same fan-out isolation as B1).
- Recipient list is empty — channel creation should be rejected client-side/server-side (at least 1 recipient required).
- MailJet returns 5xx — retry once, then skip and log without blocking Teams/Jira delivery.
- Sender domain not yet verified in MailJet (pre-PO-action) — MailJet will reject the send; this is expected and acceptable pre-production, must not crash the dispatch loop.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST implement `EmailChannel(NotificationChannel)` using the `mailjet-rest` SDK, reusing the existing direct `AlertingService.dispatch` fan-out from Spec B1 unchanged.
- **FR-002**: System MUST resolve the MailJet API key, secret key, and sender email from AWS Secrets Manager at runtime through ECS task IAM — never store them in `notification_channels.config_json`.
- **FR-003**: System MUST send using the HTML template (`anomaly_alert.html`) with severity-based color coding matching the mapping already defined in Spec B1's design doc (low/medium/high/critical).
- **FR-004**: System MUST enable the `email` option in the existing Notification Settings page and Alert Config Dialog (built in B1 with email hidden/disabled) — UI change only, no new page.
- **FR-005**: System MUST require at least one recipient email address when creating an email channel.
- **FR-006**: System MUST NOT block Teams/Jira dispatch if the email channel fails (secret missing, MailJet error, or account not yet activated).
- **FR-007**: System MUST enable Email/MailJet only through environment configuration; sandbox/test credentials are used only after the ITSM request provisions them, while production remains disabled until account and sender verification are complete.
- **FR-008**: The email channel test action MUST use sandbox delivery in non-production and require explicit confirmation before sending to configured production recipients.

### Key Entities *(include if feature involves data)*

- **EmailChannel config**: the `email`-typed `config_json` shape on the existing `notification_channels` table (Spec B1) — no new table.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After the ITSM request provisions an approved sender and credentials, a sandbox API authentication/send validation passes; production email is delivered within the same dispatch cycle as Teams/Jira only after production account and sender verification.
- **SC-002**: Email channel failure (secret missing or MailJet down) has zero measurable impact on Teams/Jira delivery time or success rate.
- **SC-003**: Channel creation UI accepts a channel with 1-N recipients and rejects submission with 0 recipients, verified via UI test.

## Assumptions

- Spec B1 (`017-alerting-core-teams-jira`) is complete: `AlertingService`, `NotificationChannel` ABC, tables, and Notification Settings/Alert Config Dialog UI (with email hidden) already exist.
- MailJet sandbox/test credentials and an approved shared-mailbox sender are available only after the Product Owner's ITSM request is fulfilled; this blocks external API validation and production go-live, not mocked implementation tests.
- No new Databricks job or table is introduced by this spec.
