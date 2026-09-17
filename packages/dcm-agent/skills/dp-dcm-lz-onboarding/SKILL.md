---
name: dp-dcm-lz-onboarding
description: DCM Landing Zone onboarding process — 7 phases, responsibilities, naming conventions, and onboarding document template. Load when guiding a new LZ into Data Connect Monitoring.
---

# DCM LZ Onboarding

End-to-end process for onboarding a new Landing Zone into Data Connect Monitoring (DCM).

## When to Use

- User asks to add a new LZ to DCM
- User needs the full onboarding checklist
- User needs naming conventions for collector SPs and resources

## Architecture Reminder

DCM uses **distributed collectors** (Scenario 2): one collector per LZ sends KPIs to DCM Core via Apigee → Lambda → SQS.

| Zone | Collector runtime | Building Blocks |
|------|-------------------|-----------------|
| Azure LZ | App Service WebJob (continuous) | `JOB_2`, `SV_1` |
| AWS LZ | ECS Fargate (scheduled one-shot) | `CT_2_SLESS_TASK`, `CRON_1`, `SV_1` |

## 7-Phase LZ Onboarding (agent workflow)

DCM Core (phase 0) is **already deployed** — the LZ onboarding agent does **not** validate it.

| Phase | Name | Owner | Deliverable |
|-------|------|-------|-------------|
| 0 | DCM Core | DCM team | **Out of scope** — Apigee, Lambda, SQS, back ingestion SP (assumed live) |
| 1 | LZ scoping + collectors | LZ team | LZ id, env, account/subscription, `enabled_collectors` |
| 2 | Entra ID collector SP | LZ team + Entra admin | SP created (agent executes), `Collector` role assigned |
| 3 | Secrets runtime | LZ team | Key Vault or Secrets Manager configured |
| **5.1** | **Client LZ infra (BASK)** | Cloud Ops LZ | Satellite `DataintDCM/ClientInfra` via **`azr-iac-bb-dataint-dcm`** / **`aws-iac-bb-dataint-dcm`** |
| **3b** | **Secrets in BB vault** | LZ team | After 5.1 apply — `dcm-*` in `azr{env}kv{appcode}-dcm` (not core IaC KV) |
| **5.2** | **Collector package** | Cloud Ops LZ | Deploy **`dcm-azure-collector`** or **`dcm-aws-collector`** |
| 4 | Cloud permissions | Cloud Ops LZ | RBAC (MI) or IAM (Task Role) for **selected** collectors |
| 6 | Ingestion validation | DCM + LZ team | Token OK, POST /ingest OK |
| 7 | Documentation | DCM team | Onboarding fiche finalized |

**Infra pattern (IaC example):** `DataSquad-infra/Project/DataintDCM/ClientInfra` — subscription DataSquad is a **client LZ** like any other; skill `dp-dcm-client-infra`.

**Collector image:** central ECR AWS `551656632516` — BB creates empty App Service; CI `dcm-azure-collector-deploy-lz.yml` deploys container. No ACR in client LZ. No ACI.

## Responsibilities

| Task | LZ team | DCM team | Cloud Ops | Entra admin |
|------|---------|----------|-----------|-------------|
| Create collector SP | Lead | Support | — | Admin consent |
| Store secrets | Lead | — | Configure access | — |
| RBAC / IAM | — | Guide | Lead | — |
| Deploy collector | — | Guide | Lead | — |
| Validate ingestion | Participate | Lead | — | — |

## LZ Scoping — Azure vs AWS

**Never ask the user for `source_lz_id` or short `lzName`** — derive them from the cloud-specific identifier.

### Microsoft Azure (IAS)

- **One Landing Zone subscription for all environments** (dev and prod share the same LZ).
- Ask: `azure_lz_name` (subscription name), e.g. `sub-iasp-lz-novadatahub`
- Ask: `environment` (`d` = DEV, `p` = PROD) — which collector environment to onboard
- Ask: `subscription_id`, `owner_email`
- Derive:
  - `lzName` = strip `sub-iasp-lz-` → `novadatahub`
  - `source_lz_id` = `azr-lz-{lzName}-{dev|prod}`

### AWS (ALZP)

- **One LZ ID per environment** (separate workload per env).
- Ask: `aws_lz_id`, e.g. `awsd-wl-DSDataEng` (DEV) or `awsp-wl-MTEDSDataEngP` (PROD)
- Ask: `environment` (`d` = DEV, `p` = PROD) — must match prefix (`awsd` → DEV, `awsp` → PROD)
- Ask: `account_id`, `owner_email`
- Derive:
  - `source_lz_id` = `aws_lz_id` as provided
  - `lzName` = segment after `-wl-` (e.g. `DSDataEng`)

## Naming Conventions

### Entra ID (MR Robot — official)

| Cloud | Collector SP | Back ingestion SP |
|-------|-------------|-------------------|
| Azure (IAS) | `AZR-IASP-LZ-{lzName}-dcm-collector` | `AZR-IASP-LZ-DataSquad-inj-{env}` |
| AWS (ALZP) | `AWS-ALZP-WL-{lzName}-dcm-collector` | `AWS-ALZP-WL-dcm-inj-{env}` |

### Alternative (operational guide)

`dcm-collector-agent-{lzName}` — map to MR Robot convention when generating commands.

### Secrets

| Cloud | Location | Suggested name |
|-------|----------|----------------|
| Azure | Key Vault | `dcm-kv-prod` (shared) or LZ-specific vault |
| AWS | Secrets Manager | `dcm-credentials-{lzName}-{env}` |

## Identity Separation (CRITICAL)

```
OAuth SP (Entra App Registration)  →  JWT for Apigee only
Runtime identity (MI / Task Role) →  Secrets + cloud API access
```

Never assign Azure RBAC or AWS IAM to the OAuth SP.

## DCM Core vs LZ-Specific (CRITICAL)

Central ingestion is **shared per environment**, not provisioned per client Landing Zone:

| Component | Scope | Owner | Notes |
|-----------|-------|-------|-------|
| Back ingestion SP | Per **context + env** | DCM team | e.g. `AZR-IASP-LZ-DataSquad-inj-d` — audience for all Azure collectors on DEV |
| Apigee ingestion API | Per **env** | API Platform + DCM | Same URL for all LZ collectors (e.g. `dev.apixnp.alzp.tgscloud.net/.../ingest`) |
| Lambda `JOB_1` + SQS | Per **env** | DCM team | DCM Core infra (`BA-Data-Connect-Monitoring-infra`) — one pipeline for all LZs |
| Apigee API key | Per **env** (shared) | DCM team → LZ team stores | Secret `awsd-dcm-api-keys` in DCM Core; collectors copy value into LZ Key Vault / SM |
| Collector SP | Per **LZ** | LZ team | e.g. `AZR-IASP-LZ-{lzName}-dcm-collector` — created during onboarding |
| `source_lz_id` in payload | Per **LZ** | LZ team | Identifies which LZ sent the metrics |

## Onboarding Document Template

```markdown
# DCM Onboarding — {lzName} ({cloud_provider}, {environment})

**Date:** {date}
**Owner:** {owner_email}
**Status:** {draft|validated}

## Collector selection (Phase 1)

| enabled_collectors | {comma-separated keys} |
| excluded_collectors | {keys not selected} |
| DCM_ENABLED_COLLECTORS | {same as enabled_collectors} |

## LZ Parameters

| Parameter | Value |
|-----------|-------|
| cloud_provider | {cloud_provider} |
| azure_lz_name or aws_lz_id | {azure_lz_name or aws_lz_id} |
| environment | {environment} |
| lzName (derived) | {lzName} |
| source_lz_id (derived) | {source_lz_id} |
| subscription_or_account_id | {subscription_or_account_id} |

## Entra ID

| Item | Value |
|------|-------|
| Collector SP name | {sp_name} |
| Collector SP appId | {app_id} |
| Back ingestion SP | {back_sp_name} |
| Permission | Collector (Application) |

## Secrets

| Secret | Location |
|--------|----------|
| entra_tenant_id | {vault_or_sm} |
| entra_client_id | {vault_or_sm} |
| entra_client_secret | {vault_or_sm} |
| apigee_api_key | {vault_or_sm} |

## Cloud Permissions

{rbac_or_iam_summary}

## Collector Deployment

{deployment_summary}

## Validation

- [ ] Token client_credentials OK
- [ ] POST /ingest HTTP 2xx
- [ ] Message in SQS / Lambda logs

## References

- EntraId-Sp-To-Create.md
- dcm-lz.md (permissions guide)
```

## Out of Scope

- DCM Core infrastructure (`BA-Data-Connect-Monitoring-infra`)
- User dashboard auth OIDC/PKCE (`auth.md` — Flux A)
- Apigee product / VPC Lattice configuration
- Collector application code (`dataint-dcm-app`)
