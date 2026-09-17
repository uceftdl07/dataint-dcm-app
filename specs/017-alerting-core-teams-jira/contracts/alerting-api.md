# Alerting API Contract

## Internal dispatch

### `POST /v1/internal/anomaly-reports`

Reads a report already persisted by Spec 016, then dispatches active project-authorized channels directly from the backend. Requires M2M Entra JWT from the Databricks Alert Trigger. The response confirms accepted backend dispatch; external channels fan out independently without SQS.

### `POST /v1/internal/anomaly-reports/{report_id}/resolve`

Dispatches a resolution notification for a finalized incident. Requires M2M Entra JWT from the Databricks Alert Trigger.

## User re-notify

### `POST /v1/anomaly-reports/{report_id}/notify`

Publishes a manual notification message for an authorized user. Supports all active channels for the rule or a selected channel.

## Configuration

- Versioned routes use `/v1/`.
- Channel and alert-config CRUD must enforce authorized project scope. A project may span multiple LZ IDs, workspaces, and catalogs; a channel belongs to exactly one project.
- Raw webhook URLs and API tokens are never returned in API responses.
