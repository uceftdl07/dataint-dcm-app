---
name: dp-dcm-ingest-validation
description: Validate DCM collector ingestion — agent executes OAuth2 token test and POST /ingest via shell.
---

# DCM Ingestion Validation

Verify that a new LZ collector SP can obtain a token and push metrics through Apigee to the DCM ingestion pipeline.

**Agent behavior:** run Steps 1–3 via `#tool:execute` using secrets from Key Vault — do **not** output scripts for the user to copy.

## Prerequisites

**Assumed (DCM Core — do not ask the client):** back ingestion SP, Apigee, Lambda+SQS operational for the target env.

**This LZ session:**
- Collector SP created with `Collector` role on back ingestion SP
- Client secret created and stored in vault/SM
- Apigee API key **for the target env** received from DCM team (shared key, stored in LZ vault)
- Ingestion URL for target environment

## Ingestion URLs

| Environment | URL (example — confirm with DCM team) |
|-------------|---------------------------------------|
| Dev | `https://dev.apixnp.alzp.tgscloud.net/ingestion/v0.0.1/v1/metrics/ingest` |
| Prod | Confirm with API Platform / DCM team |

## Step 1 — Authenticate as collector SP (agent executes)

```bash
TENANT=$(az keyvault secret show --vault-name "$VAULT" -n dcm-entra-tenant-id --query value -o tsv)
CLIENT_ID=$(az keyvault secret show --vault-name "$VAULT" -n dcm-entra-client-id --query value -o tsv)
CLIENT_SECRET=$(az keyvault secret show --vault-name "$VAULT" -n dcm-entra-client-secret --query value -o tsv)

az login --service-principal -u "$CLIENT_ID" -p "$CLIENT_SECRET" --tenant "$TENANT" --allow-no-subscriptions
```

## Step 2 — Obtain token (audience = back ingestion SP)

```bash
TOKEN=$(az account get-access-token \
  --resource {back_ingestion_sp_app_id} | jq -r .accessToken)

echo "Token length: ${#TOKEN}"
```

`back_ingestion_sp_app_id` examples:
- AWS dev: appId of `AWS-ALZP-WL-dcm-inj-d`
- Azure dev: appId of `AZR-IASP-LZ-DataSquad-inj-d`

## Step 3 — POST /ingest (agent executes)

```bash
API_KEY=$(az keyvault secret show --vault-name "$VAULT" -n dcm-apigee-api-key --query value -o tsv)
API_URL="https://dev.apixnp.alzp.tgscloud.net/ingestion/v0.0.1/v1/metrics/ingest"

curl -s -w "\nHTTP %{http_code}\n" \
  -H "x-apif-apikey: $API_KEY" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -X POST "$API_URL" \
  -d '{
    "schema_version": "1.1",
    "collection_run_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "source_lz_id": "{source_lz_id}",
    "subscription_or_account_id": "{subscription_or_account_id}",
    "cloud_provider": "{azure|aws}",
    "domain": "pipeline",
    "collected_at": "2026-06-16T12:00:00Z",
    "metrics": []
  }'
```

Report HTTP status to the user. Redact API key and token in output.

## Success Criteria

| Check | Expected |
|-------|----------|
| Token acquisition | Non-empty JWT, no `az` error |
| HTTP response | 2xx from Apigee |
| Lambda logs | Ingestion request logged in DCM Core |
| SQS | Message published to ingestion queue |

## Failure Troubleshooting

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| 401 Unauthorized | Invalid/expired token or wrong audience | Verify `Collector` role assignment and back SP appId |
| 403 Forbidden | Wrong header (`x-api-key` instead of **`x-apif-apikey`**) or missing key | Use `x-apif-apikey`; same shared key per env for all LZs |
| Invalid audience | Cross-context SP (IAS vs AWS) | Recreate permission in correct context |
| 502/503 | Apigee → Lambda / VPC Lattice | Contact DCM team |
| Empty token | Wrong client secret or expired secret | Rotate secret, update vault/SM |

## Payload Schema (v1.1)

Required fields for minimal test:

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | `"1.1"` |
| `collection_run_id` | uuid | Unique run identifier |
| `source_lz_id` | string | LZ identifier in DCM |
| `subscription_or_account_id` | string | Azure sub or AWS account |
| `cloud_provider` | string | `"azure"` or `"aws"` |
| `domain` | string | e.g. `"pipeline"`, `"cost"` |
| `collected_at` | ISO8601 | Collection timestamp |
| `metrics` | array | KPI objects (empty array OK for connectivity test) |

## Validation Checklist

- [ ] Service principal login succeeds
- [ ] Token obtained for correct back ingestion audience
- [ ] POST /ingest returns 2xx
- [ ] DCM team confirms SQS/Lambda receipt
- [ ] Results recorded in onboarding fiche
