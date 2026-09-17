---
name: dp-dcm-entra-collector-sp
description: Execute MR Robot calls to create DCM collector Service Principals and assign Collector role to back ingestion SP. Agent runs MrRobotV3Client — curl is fallback only on failure.
---

# DCM Entra ID Collector SP

Create the per-LZ collector Service Principal in Microsoft Entra ID via MR Robot API.

**Agent behavior:** execute via `MrRobotV3Client` (`plugins/global/skills/mr-robot/MrRobotV3Client.py`) — do **not** output raw `export` / `curl` for the user unless execution fails.

## Auth preflight (MANDATORY — before any MR Robot call)

Verify Azure CLI session **before** `create_application`. Expired session (`AADSTS70043`) → empty token → HTTP 401.

```bash
MR_ROBOT_SCOPE="https://api-aad.pf-identity.iasp.tgscloud.net/.default"
TOKEN_LEN=$(az account get-access-token --scope "$MR_ROBOT_SCOPE" 2>/dev/null | jq -r '.accessToken | length')
```

If `TOKEN_LEN` is 0 → agent **stops** and asks user to run interactively:

```bash
az logout
az login --tenant "329e91b0-e21f-48fb-a071-456717ecc28e" \
  --scope "https://api-aad.pf-identity.iasp.tgscloud.net/.default"
```

Use `askQuestions` → wait for *"Je suis connecté, continue"* → re-run preflight → then proceed.

## Prerequisites

Credentials: `DefaultAzureCredential` (interactive `az login` or env vars). Optional `.env.local` in `plugins/global/skills/mr-robot/`:

```
AZURE_CLIENT_ID=...
AZURE_CLIENT_SECRET=...
AZURE_TENANT_ID=...
```

## Execute (preferred — agent runs this)

## Naming

`{lzName}` is **derived** during Phase 1 — never asked directly:

| Cloud | Input | `lzName` extraction |
|-------|-------|---------------------|
| Azure | `sub-iasp-lz-novadatahub` | Strip `sub-iasp-lz-` → `novadatahub` |
| AWS | `awsd-wl-DSDataEng` | Part after `-wl-` → `DSDataEng` |

| Cloud | Collector SP | Context | Back ingestion SP |
|-------|-------------|---------|-------------------|
| Azure | `AZR-IASP-LZ-{lzName}-dcm-collector` | `IAS` | `AZR-IASP-LZ-DataSquad-inj-{env}` |
| AWS | `AWS-ALZP-WL-{lzName}-dcm-collector` | `AWS` | `AWS-ALZP-WL-dcm-inj-{env}` |

Environment mapping: `d` → `d` / `PROD` for dev; `p` → `prod` / `PROD` for production.

```python
import sys
sys.path.insert(0, "plugins/global/skills/mr-robot")  # or .agents/skills path
from MrRobotV3Client import MrRobotV3Client

context = "IAS" if azure else "AWS"
client = MrRobotV3Client(context=context)

status, app = client.create_application(
    display_name=f"AZR-IASP-LZ-{lzName}-dcm-collector",  # or AWS name
    contact_email=owner_email,
)
collector_app_id = app["appId"]

status, _ = client.assign_permissions(collector_app_id, [{
    "value": "Collector",
    "type": "Application",
    "resourceName": f"AZR-IASP-LZ-DataSquad-inj-{env}",
}])

status, secret = client.add_client_secret(collector_app_id)
# secret["secretText"] → store in Key Vault immediately; never echo in chat
```

Run via `#tool:execute` from the skill directory. Report `appId` and HTTP status codes (200/201).

## Manual fallback (curl — only if MrRobotV3Client fails)

```bash
export MR_ROBOT_URL=https://api-aad.pf-identity.iasp.tgscloud.net
export TOKEN=$(az account get-access-token \
  --scope https://api-aad.pf-identity.iasp.tgscloud.net/.default | jq -r .accessToken)
```

## Azure (IAS) — Create collector SP

```bash
curl -v \
  -H "x-api-version: 3.0" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -X POST -d '{
    "displayName": "AZR-IASP-LZ-{lzName}-dcm-collector",
    "contactEmail": "{owner_email}",
    "appRoleAssignmentRequired": true,
    "environment": "PROD"
  }' "${MR_ROBOT_URL}/api/applications?context=IAS" | jq .
```

Save the returned `appId`.

## Azure (IAS) — Assign Collector permission

```bash
curl -vv -X PUT \
  "${MR_ROBOT_URL}/api/applications/{collector_appId}/permission-assignments?context=IAS" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" \
  -H "x-api-version: 3.0" \
  -H "Content-Type: application/json" \
  -d '{
    "permissions": [
      {
        "value": "Collector",
        "type": "Application",
        "resourceName": "AZR-IASP-LZ-DataSquad-inj-{env}"
      }
    ]
  }' | jq .
```

## AWS (ALZP) — Create collector SP

```bash
curl -v \
  -H "x-api-version: 3.0" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -X POST -d '{
    "displayName": "AWS-ALZP-WL-{lzName}-dcm-collector",
    "contactEmail": "{owner_email}",
    "appRoleAssignmentRequired": true,
    "environment": "prod"
  }' "${MR_ROBOT_URL}/api/applications?context=AWS" | jq .
```

## AWS (ALZP) — Assign Collector permission

```bash
curl -vv -X PUT \
  "${MR_ROBOT_URL}/api/applications/{collector_appId}/permission-assignments?context=AWS" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json" \
  -H "x-api-version: 3.0" \
  -H "Content-Type: application/json" \
  -d '{
    "permissions": [
      {
        "value": "Collector",
        "type": "Application",
        "resourceName": "AWS-ALZP-WL-dcm-inj-{env}"
      }
    ]
  }' | jq .
```

## Post-Creation Steps

1. Client secret: `add_client_secret` (agent) — **only if** not already in vault
2. **Resume check:** before create/secret, run Phase 1.6 discovery — skip if SP + Collector role already ✅
3. **409 cross-LZ:** use Microsoft Graph `appRoleAssignments` (see agent Phase 1.6) — not admin consent alone
4. Note **Tenant ID**, **Client ID** for secrets storage (Phase 3)

## Authorization Flow

```
[IAS collector SP]  →  Collector role  →  [AZR-IASP-LZ-DataSquad-inj-{env}]
[AWS collector SP]  →  Collector role  →  [AWS-ALZP-WL-dcm-inj-{env}]
```

## Rules

- **No cross-context**: IAS SP cannot call AWS back SP and vice versa
- SP is created by the **LZ team**, not DCM team (AWS SP ownership may be re-parented)
- OAuth SP is **only** for Apigee token — do not assign cloud RBAC/IAM to it
- Alternative naming `dcm-collector-agent-{lzName}` from operational guide maps to MR Robot names above

## Python Alternative (MrRobotV3Client)

**Default path for the agent** — see Execute section above. Curl blocks below are fallback only.
