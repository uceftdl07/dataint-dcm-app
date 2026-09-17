# Alerting Delivery Contract

## Message

```json
{
  "report_id": "uuid",
  "notification_type": "incident | reminder | resolution",
  "channel_id": "uuid"
}
```

## Processing

1. Validate internal M2M request and authorized project context.
2. Read report, rule, channel, and active alert configuration from Unity Catalog.
3. Resolve configured AWS Secrets Manager reference through ECS task IAM.
4. Treat `(report_id, notification_type, channel_id)` as the delivery identity.
5. Send to Teams or Jira.
6. Retry once on delivery failure.
7. Log and discard after retry fails; do not block other channels.
8. Update report delivery timestamps and `jira_ticket_url` after successful operations.

Email channel processing is deferred to Spec 018.
