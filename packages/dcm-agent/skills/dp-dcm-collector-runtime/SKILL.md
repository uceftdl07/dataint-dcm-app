---
name: dp-dcm-collector-runtime
description: Reference the implemented DCM collector packages (dcm-azure-collector, dcm-aws-collector) — deployment model, env vars, and selectable data sources per cloud provider. Load during collector deployment (Phase 6).
---

# DCM Collector Runtime Packages

Use the **existing Python collectors** from `dataint-dcm-app` — do not invent new collector apps.

| Cloud | Package | Repo path | Runtime |
|-------|---------|-----------|---------|
| Azure | `dcm-azure-collector` | `packages/dcm-azure-collector` | App Service WebJob — **continuous** (`JOB_2` + `SV_1`) |
| AWS | `dcm-aws-collector` | `packages/dcm-aws-collector` | ECS Fargate **one-shot** + EventBridge (`CT_2_SLESS_TASK` + `CRON_1` + `SV_1`) |

Both depend on `dcm-commons` (models, `ApigeeClient`, `BaseCollector`).

## Azure — `dcm-azure-collector`

**Execution:** long-running asyncio loop (default interval 300 s). Entrypoint: `dcm-azure-collector`.

### Implemented collectors (`DCM_ENABLED_COLLECTORS` CSV)

| Key | Class | Domain | Azure service |
|-----|-------|--------|---------------|
| `datafactory` | DataFactoryCollector | pipeline | Azure Data Factory |
| `activity_runs` | (ADF activities) | pipeline | ADF activity runs |
| `databricks` | DatabricksCollector | cluster | Azure Databricks |
| `databricks_pipelines` | Databricks pipelines | pipeline | Databricks jobs |
| `cost_management` | CostManagementCollector | cost | Azure Cost Management |
| `databases` | DatabaseCollector | database | SQL / PostgreSQL / MySQL / Cosmos |
| `security_center` | SecurityCenterCollector | security | Microsoft Defender for Cloud |
| `users` | Users collector | — | Entra users (if enabled) |
| `standard_checks` | Standard checks | — | Governance checks |

Default: **none** — client must select via `enabled_collectors` in Phase 1. Never deploy all collectors without explicit client choice.

### Client selection flow (Phase 1)

1. Announce package name (`dcm-azure-collector` or `dcm-aws-collector`)
2. Display the full catalog table (keys + human-readable labels)
3. `askQuestions` multi-select — client checks only what they want
4. Confirm: **Selected** / **Excluded** lists, then continue to Entra ID
5. Phase 5 permissions and Phase 6 `DCM_ENABLED_COLLECTORS` use **selected keys only**

Example exclusion: client unchecks Databricks → `DCM_ENABLED_COLLECTORS` has no `databricks` or `databricks_pipelines`; RBAC for Databricks Reader is omitted.

### Required App Service settings

| Variable | Value source |
|----------|--------------|
| `DCM_KEY_VAULT_URL` | LZ Key Vault URL |
| `AZURE_SUBSCRIPTION_ID` | From Phase 1 `subscription_id` |
| `DCM_SOURCE_LZ_ID` | Derived `source_lz_id` |
| `DCM_APIGEE_BASE_URL` | DCM Core env URL (shared) |
| `DCM_ENTRA_SCOPE` | `api://{back_ingestion_sp_app_id}/.default` |
| `DCM_ENABLED_COLLECTORS` | Subset based on user choice |
| `DCM_COLLECTION_INTERVAL` | Optional (default 300) |

Secrets (`dcm-entra-*`, `dcm-apigee-api-key`) read from Key Vault via Managed Identity — not in app settings.

### Deployment checklist (Azure)

- [ ] Deploy `JOB_2` App Service + `SV_1` for collector WebJob
- [ ] Build/package `dcm-azure-collector` (`pip install -e . --target ./deploy_package/`)
- [ ] Enable System-Assigned Managed Identity on App Service
- [ ] Configure settings above (no secrets in plain text)
- [ ] RBAC on subscription/RG per selected collectors (see `dp-dcm-cloud-permissions`)
- [ ] WebJob mode: **continuous**

## AWS — `dcm-aws-collector`

**Execution:** one-shot — ECS task starts, collects, sends, exits. EventBridge cron (e.g. every 5 min).

### Implemented collectors (`DCM_ENABLED_COLLECTORS` CSV)

| Key | Class | Domain | AWS service |
|-----|-------|--------|-------------|
| `glue` | GlueCollector | pipeline | AWS Glue jobs + crawlers |
| `emr` | EMRCollector | cluster | Amazon EMR |
| `rds` | RDSCollector | database | RDS / Aurora |
| `cost_explorer` | CostExplorerCollector | cost | Cost Explorer + Budgets |
| `redshift` | RedshiftCollector | database | Amazon Redshift |

Default: **none** — client selects in Phase 1.

### Required ECS task env vars

| Variable | Value source |
|----------|--------------|
| `DCM_SECRET_NAME` | Secrets Manager secret (e.g. `dcm-credentials-{lzName}-{env}`) |
| `DCM_SOURCE_LZ_ID` | Derived `source_lz_id` (`aws_lz_id`) |
| `DCM_AWS_REGION` | LZ primary region |
| `DCM_APIGEE_BASE_URL` | DCM Core env URL (shared) |
| `DCM_ENTRA_SCOPE` | `api://{back_ingestion_sp_app_id}/.default` |
| `DCM_ENABLED_COLLECTORS` | Subset based on user choice |

Secret JSON keys: `entra_tenant_id`, `entra_client_id`, `entra_client_secret`, `apigee_api_key`.

### Deployment checklist (AWS)

- [ ] Deploy `CT_2_SLESS_TASK` ECS Fargate + `CRON_1` EventBridge + `SV_1` Secrets Manager
- [ ] Container image with `dcm-aws-collector` entrypoint
- [ ] Task Role IAM (not OAuth SP) — see `dp-dcm-cloud-permissions`
- [ ] Secrets Manager secret with 4 JSON keys
- [ ] Schedule: cron every 5 minutes (typical)

## Map legacy labels → collector keys (do not use in askQuestions — show keys directly)

| If user says | Azure key | AWS key |
|--------------|-----------|---------|
| cost | `cost_management` | `cost_explorer` |
| pipelines / ADF | `datafactory`, `activity_runs` | `glue` |
| databricks | `databricks`, `databricks_pipelines` | `emr` |
| databases | `databases` | `rds`, `redshift` |
| security | `security_center` | — |

## Handoffs

- **Client LZ infra (BASK satellite):** `dp-dcm-client-infra` — module `azr-iac-bb-dataint-dcm` in `BA-{LZ}-Infrastructure`
- **Azure package deploy:** after infra — zip `dcm-azure-collector` to BB App Service
- **AWS IaC:** `dgt-awslz-builder` — ECS Fargate + EventBridge + Secrets Manager (when `aws-iac-bb-dataint-dcm` is ready)

## Out of scope

- Collector application code changes (`dataint-dcm-app` — separate dev workflow)
- DCM Core ingestion pipeline
