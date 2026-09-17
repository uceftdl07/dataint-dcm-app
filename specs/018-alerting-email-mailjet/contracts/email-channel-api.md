# Email Channel Contract

## Configuration

### `POST /v1/notification-channels`

Accepts an email channel with a name and at least one valid recipient for the caller's authorized project. The API stores the MailJet AWS Secrets Manager reference and recipients; raw credentials are never accepted as persisted configuration.

### `POST /v1/notification-channels/{channel_id}/test`

Sends a test email through sandbox credentials in non-production. Production requires explicit confirmation and environment enablement.

## Dispatch

`EmailChannel.send(report, notification_type)` supports `incident`, `reminder`, and `resolution`. It uses the existing direct-dispatch delivery identity and does not change Teams/Jira behavior.
