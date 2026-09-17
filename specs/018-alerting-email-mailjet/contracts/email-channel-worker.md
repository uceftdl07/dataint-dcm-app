# Email Channel Worker Contract

## Processing

1. Receive the existing alert message from Spec 017.
2. Resolve MailJet credentials and sender from AWS Secrets Manager at runtime through ECS task IAM.
3. Render the incident or resolution HTML template.
4. Send to configured recipients through MailJet.
5. Retry once on failure.
6. Log and discard after the retry fails; Teams/Jira processing remains independent.

## Environment behavior

- Development/staging: sandbox/test credentials allowed.
- Production: disabled until account activation and sender-domain verification.
- Production test sends: explicit confirmation required.
