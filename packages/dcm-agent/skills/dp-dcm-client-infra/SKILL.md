---
name: dp-dcm-client-infra
description: Deploy DCM collector infrastructure in the client LZ IaC repo (BASK satellite DataintDCM/ClientInfra) via azr-iac-bb-dataint-dcm or aws-iac-bb-dataint-dcm. Load during Phase 5.1 (infra) before collector package deploy and MI RBAC.
---

# DCM Client LZ Infrastructure (BASK satellite)

Deploy the **collector runtime host** in the **client Landing Zone IaC repository** — not in `BA-Data-Connect-Monitoring-infra` (DCM Core).

## Repos — roles (do not confuse)

| Repo | Role | Who uses it |
|------|------|-------------|
| **`azr-iac-bb-dataint-dcm`** | Azure **Building Block** — Terraform module (RG, KV, subnet, App Service, RBAC) | Called from LZ IaC satellite |
| **`aws-iac-bb-dataint-dcm`** | AWS **Building Block** — *template / not yet implemented* | Future — ECS + SM pattern |
| **`DataSquad-infra`** | **Exemple IaC** — pattern satellite à copier (subscription DataSquad = LZ cliente comme les autres) | Copy pattern, do not fork BB code |
| **`BA-{LZ}-Infrastructure`** | **LZ IaC** (BASK) — satellite `DataintDCM/ClientInfra` | DataSquad-infra, novadatahub, … |
| **`dataint-dcm-app`** | Collector **Python package** only | Phase 5.2 — zip/image deploy after infra |

```
BA-{LZ}-Infrastructure                    azr-iac-bb-dataint-dcm
  Project/DataintDCM/ClientInfra/  ──calls──►  (module Terraform)
         │                                        │
         └── BASK CI/CD apply                      └── creates Azure resources
```

## Agent rule — NEVER write native collector Terraform

❌ **Forbidden:** custom `dcm_collector.tf`, hand-rolled App Service, reusing core IaC Key Vault as the DCM runtime vault.

✅ **Required:** single module call in `FOUNDATION.tf` — same pattern as [DataSquad-infra `Project/DataintDCM/ClientInfra`](https://github.com/TotalEnergiesCode/DataSquad-infra/tree/main/Project/DataintDCM/ClientInfra).

Module source (Azure):

```hcl
source = "git::https://github.com/TotalEnergiesCode/azr-iac-bb-dataint-dcm.git?ref=main"
```

- **Never** use `?ref=v1.0.0` — tag does not exist.
- **Never** use a local path to a cloned BB repo in CI — GitHub URL only.
- If CI returns `Repository not found` → LZ builder SP / `GITHUB_TOKEN` needs read access to private repo `TotalEnergiesCode/azr-iac-bb-dataint-dcm` (same as DataSquad).

## Phase ordering with `dp-dcm-lz-client`

| Order | Phase | What |
|-------|-------|------|
| 1 | 2 Entra | Collector SP + `Collector` role on back ingestion SP |
| 2 | 3 Secrets (optional early) | Can stage secrets in **any** reachable KV for Phase 6 OAuth test |
| 3 | **5.1 Infra (this skill)** | BASK satellite apply → BB creates **dedicated** DCM stack |
| 4 | **3b Secrets (mandatory)** | Copy `dcm-*` secrets into **BB Key Vault** `azr{env}kv{appcode}-dcm` |
| 5 | **5.2 Package** | Deploy `dcm-azure-collector` / `dcm-aws-collector` to the runtime |
| 6 | 4 RBAC | Verify/supplement MI roles for **selected** collectors only |
| 7 | 6 Validation | OAuth ingest test (+ runtime logs after 5.2) |

BB already assigns baseline MI RBAC (Reader, Monitoring Reader, Cost Management Reader, Data Factory Contributor, Security Reader, Log Analytics Reader, Key Vault Secrets User on **DCM KV**). Phase 4 adds collector-specific roles from `enabled_collectors`.

## Azure — satellite scaffold

Create in **`BA-{LZ}-Infrastructure`**:

```
Project/DataintDCM/ClientInfra/
  FOUNDATION.tf    ← module "dataint_dcm" { source = "...azr-iac-bb-dataint-dcm.git?ref=main" }
  VARIABLES.tf
  OUTPUTS.tf       ← re-export module.dataint_dcm.* outputs
  BACKEND.tf
  VERSIONS.tf
  PROVIDER.tf      ← azurerm + azuread

Project/Environments/DataintDCM/ClientInfra/
  development.tfvars   (or mutualized.tfvars, production.tfvars, …)
```

### `FOUNDATION.tf` — copy from DataSquad, adapt variables

Wire LZ tfvars → BB inputs: `ba_id`, `tags`, `vnet_*`, `pe_subnet_name`, `subnet_range`, Entra groups, `log_wksp_id`, `instance_number`, `collector_instance_number`.

Reference commit: [DataSquad-infra `4d8fbc5`](https://github.com/TotalEnergiesCode/DataSquad-infra/commit/4d8fbc56e907e869cc331311a74b5adce668a702).

### Resources created by BB (example novadatahub DEV)

| Resource | Pattern | Example |
|----------|---------|---------|
| Resource Group | `azr{env}rg{appcode}04-dcm` | `azrdrgndth04-dcm` |
| Key Vault | `azr{env}kv{appcode}-dcm` | `azrdkvndth-dcm` |
| App Service | `azr{env}fn{appcode}-dcm` | `azrdfnndth-dcm` |
| Integration subnet | CIDR from `subnet_range` | validate with network team |

`instance_number` for DCM RG is typically **`"04"`** (BB default).

### `development.tfvars` — minimum fields

```hcl
g_location = "West Europe"
ba_id / ba_name / as_id / as_name
tags = { LZName, AppCode, Branch, Environment }
vnet_resource_group_name / vnet_resource_name / udr_resource_name
pe_subnet_name          # existing PE subnet in LZ VNet
subnet_range            # NEW /28 — must not overlap existing subnets
owner_group_display_name / contributor_group_display_name / builder_sp_display_name
instance_number           = "04"
collector_instance_number = 1
# log_wksp_id = "..."   # optional first plan; recommended when Supervision exists
```

### Prerequisites (manual — not in BB)

- [ ] VNet + PE subnet exist (core LZ IaC)
- [ ] Entra groups + builder SP exist
- [ ] `subnet_range` approved by network team
- [ ] Firewall rules (HTTPS 443 egress from App Service integration subnet) — see [04-network-egress.md](../../docs/onboarding-guide/04-network-egress.md):
  - `login.microsoftonline.com`, `management.azure.com`, `dev.apixnp.alzp.tgscloud.net` (runtime)
  - `551656632516.dkr.ecr.eu-central-1.amazonaws.com`, `api.ecr.eu-central-1.amazonaws.com`, `prod-eu-central-1-starport-layer-bucket.s3.eu-central-1.amazonaws.com` (deploy)
- [ ] PIM `[IASP] Landing Zone Contributor` for apply

## BASK deployment steps (agent prints this checklist — user/CI executes)

### Step 1 — CI Plan

Workflow: **`CI`** (🛠️ CI)

| Input | Value |
|-------|-------|
| Deployment type | `Satellites` |
| Environments | `["development"]` (or target env) |
| Satellites | `["DataintDCM/ClientInfra"]` |
| Open firewalls | `true` |

Review Terraform plan: expect **create** RG, KV, subnet, App Service, role assignments.

### Step 2 — Merge PR

Fix plan issues (subnet overlap, missing Entra group, BB repo access) before merge.

### Step 3 — CD Apply

Workflow: **`Development`** or **`CD`**

| Input | Value |
|-------|-------|
| Deployment type | `Satellite` |
| Environment | `development` |
| Satellite | `DataintDCM/ClientInfra` |
| Plan apply | `Apply` |

Requires PIM active during apply.

### Step 4 — Post-apply verification (agent can run via `#tool:execute`)

```bash
# Replace env tag d, appcode ndth
az group show -n azrdrgndth04-dcm
az keyvault show -n azrdkvndth-dcm --query name -o tsv
az webapp list --query "[?contains(name,'dcm')].{name:name,rg:resourceGroup,mi:identity.principalId}" -o table
```

### Step 5 — Secrets into **BB Key Vault** (Phase 3b)

BB App Settings reference `module.app_keyvault.uri` — secrets **must** be in `azrdkvndth-dcm`, not the core IaC vault.

```bash
SRC_VAULT="azrdkvndth-01"          # if secrets were staged during Phase 3 early
DST_VAULT="azrdkvndth-dcm"         # BB-created vault
for s in dcm-entra-tenant-id dcm-entra-client-id dcm-entra-client-secret dcm-apigee-api-key; do
  val=$(az keyvault secret show --vault-name "$SRC_VAULT" -n "$s" --query value -o tsv)
  az keyvault secret set --vault-name "$DST_VAULT" -n "$s" --value "$val"
done
```

Or run Phase 3 agent flow targeting `DST_VAULT` directly after apply.

### Step 6 — Deploy collector package (Phase 5.2)

**Prerequisites before CI** (see `packages/dcm-agent/docs/onboarding-guide/03-phase-5-2-deploy.md`):

1. Phases 2, 5.1, 3b complete
2. Entry in `dataint-dcm-app/.github/azure-collector-deploy-targets.json`
3. GitHub env `dev`: `AZURE_BUILDER_CLIENT_ID`, `AZURE_BUILDER_CLIENT_SECRET`, `AZURE_BUILDER_TENANT_ID`, `AWS_AZURE_COLLECTOR_ECR_ROLE_ARN` (ou `AWS_COLLECTOR_AWS_ROLE_ARN`)
4. **Contributor** on LZ subscription for **that LZ's Builder SP** (`builder_sp_display_name` in tfvars, e.g. `AZR-IASP-LZ-novadatahub-Builder`)
5. **ECR push** via IAM role (central DCM registry on AWS — not Azure ACR)
6. **Egress** from App Service subnet to `*.dkr.ecr.*.amazonaws.com` + Entra + Apigee

**Workflow:** `dcm-azure-collector-deploy-lz.yml` — input `deploy_target=<key>` (container, image `:latest`).

See `dp-dcm-collector-runtime` for runtime env vars. Entrypoint: `dcm-azure-collector` / container image.

## AWS — future (aws-iac-bb-dataint-dcm)

BB is **not implemented** yet. When available:

- Satellite path: same `Project/DataintDCM/ClientInfra/`
- Module: `git::https://github.com/TotalEnergiesCode/aws-iac-bb-dataint-dcm.git?ref=main`
- Runtime: ECS Fargate + EventBridge + Secrets Manager (`dcm-aws-collector`)

Until then → handoff `dgt-awslz-builder` with explicit reference to BB README intent.

## State discovery (Phase 1.6)

Detect BB deployment:

```bash
# DCM-dedicated KV (suffix -dcm)
DCM_KV=$(az keyvault list --query "[?ends_with(name,'-dcm')].name | [0]" -o tsv)
# Collector webapp
WEBAPP=$(az webapp list --query "[?contains(name,'-dcm') || tags.BB=='JOB_2'].name | [0]" -o tsv)
```

If `DCM_KV` and `WEBAPP` present → Phase 5.1 ✅ → run Phase 3b if secrets only in old vault → Phase 5.2 → Phase 4.

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Native Terraform instead of BB | Delete custom `.tf`; use `module "dataint_dcm"` only |
| `ref=v1.0.0` | Use `ref=main` |
| Secrets only in core KV | Copy to `azr{env}kv{appcode}-dcm` after apply |
| Phase 4 before infra | Deploy satellite first (5.1) |
| Expect agent to run BASK CI | Agent guides + verifies via `az`; user triggers GitHub Actions |

## CI error: `Repository not found` on `terraform init`

**Symptom:** CI fails cloning `azr-iac-bb-dataint-dcm` with `remote: Repository not found` — while you can clone locally via SSH.

**Cause:** The repo is **private**. BASK CI uses the org **Universal GitHub App** (`UNIVERSAL_GH_APP_ID_CODE` / `UNIVERSAL_GH_APP_PRIVATE_KEY_CODE`) inside `azr-sysops-action-terraform-plan@v4` to download BB modules. GitHub returns **404** when the app has no read access (not “wrong URL”).

**This is not fixed by changing `FOUNDATION.tf`** — it is a **GitHub permissions** step.

### Fix (ask DCM BB owner or BASK / SysOps)

1. In GitHub org **TotalEnergiesCode** → **Settings** → **GitHub Apps** → find the **Universal / Organization Reader** app used by BASK (same as other `azr-iac-bb-*` modules).
2. **Repository access** → add `TotalEnergiesCode/azr-iac-bb-dataint-dcm` (or “All repositories” if org policy allows).
3. Re-run CI on `BA-{LZ}-Infrastructure`.

Reference: DataSquad-infra uses the **same** module URL and the same `azr-sysops-action-terraform-plan@v4` — it works once the app can read the BB repo.

### Verify secrets exist on LZ repo

In `BA-{LZ}-Infrastructure` → Settings → Secrets: `UNIVERSAL_GH_APP_ID_CODE` and `UNIVERSAL_GH_APP_PRIVATE_KEY_CODE` must be present (org-level secrets inherited by BASK projects).

### Message template for colleague (BB / DCM team)

> Please grant the BASK Universal GitHub App read access to `TotalEnergiesCode/azr-iac-bb-dataint-dcm` so LZ client repos (e.g. `BA-NOVADATAHUB-Infrastructure`) can run `terraform init` on satellite `DataintDCM/ClientInfra`. DataSquad-infra already consumes this BB.

## Handoffs

| Situation | Target |
|-----------|--------|
| Scaffold/edit satellite files in LZ repo | `dp-azlz-devops-builder` (Azure) |
| AWS LZ when BB ready | `dgt-awslz-builder` |
| Collector zip/container deploy | `dp-dcm-collector-runtime` skill |

## References

- [azr-iac-bb-dataint-dcm README](https://github.com/TotalEnergiesCode/azr-iac-bb-dataint-dcm)
- [DataSquad-infra DataintDCM/ClientInfra](https://github.com/TotalEnergiesCode/DataSquad-infra/tree/main/Project/DataintDCM/ClientInfra)
- [installation.md](https://github.com/TotalEnergiesCode/azr-iac-bb-dataint-dcm/blob/main/installation.md) — post-apply secrets + collector deploy
