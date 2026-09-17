# Anomaly API Contract

## Rules

### `GET /v1/anomaly-rules`

Returns paginated rules visible to the authenticated user. Supports filtering by domain, rule type, active state, and Landing Zone.

### `POST /v1/anomaly-rules`

Creates a custom rule. Requires `field_id` referencing an existing,
caller-authorized `anomaly_metric_fields` record. Rejects `rule_type=company`
and requests outside the caller's authorized Landing Zones.

### `PATCH /v1/anomaly-rules/{rule_id}`

Updates a custom rule or its activation state. A replacement `field_id` must
reference an existing, caller-authorized `anomaly_metric_fields` record. Company
rules are read-only.

### `DELETE /v1/anomaly-rules/{rule_id}`

Deletes or deactivates a custom rule according to existing DCM lifecycle conventions.

## Reports

### `GET /v1/anomaly-reports`

Returns paginated reports with filters for `lz_id`, `status`, `rule_id`, and date period.

### `GET /v1/anomaly-reports/{report_id}`

Returns metric value, threshold snapshot, status, timestamps, logs, and rule metadata.

## Internal evaluator ingress

### `POST /v1/internal/anomaly-reports`

M2M Entra JWT only. Accepts evaluator report data and persists it idempotently.

### Lifecycle ownership across specs

Spec 016 owns incident evaluation and persistence only. Spec 017 extends this
ingress with dispatch after a successful incident open/update, and adds
`POST /v1/internal/anomaly-reports/{report_id}/resolve` for a finalized
incident. The Databricks Alert Trigger added in Spec 017 owns both M2M calls;
external channel delivery remains out of scope for Spec 016.
