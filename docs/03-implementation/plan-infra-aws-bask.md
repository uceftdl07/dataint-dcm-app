# Plan: DCM Account Infrastructure - AWS BASK

> **Note 2026-05-27 :** ce plan contient encore l'hypothese historique LakeBase/PostgreSQL. Le code backend actuel a retire cette cible : DCM lit Unity Catalog via Databricks SQL Warehouse. Pour la cible actuelle, voir [`../MIGRATION-LAKEBASE-TO-WAREHOUSE.md`](../MIGRATION-LAKEBASE-TO-WAREHOUSE.md).

## TL;DR

Deploy the DCM Core Account infrastructure on AWS using BASK v9.2.0 Building Blocks. This is a **development-only**, **DCM Account-only** deployment covering: network foundation + VPC endpoints, SQS ingestion queue, Lambda ingestion API, ECS Fargate backend service with ALB+WAF, API Gateway (REST) with JWT auth, Databricks workspace with LakeBase PostgreSQL, S3+CloudFront static React hosting, Secrets Manager, and Entra ID App Registrations via `idp-iac-module-app-registration`. All IaC goes in `Project/IaC/` following BASK conventions.

**AWS Account**: awss-wl-dcm (551656632516)
**APP_NAME**: `dcm`
**BA_Name**: `BA-Data-Connect-Monitoring` | **BA_ID**: `9b3605c1ff1b769408f0f1108c4fd9cd`
**AS_Name**: `AS-Data-Connect-Monitoring-D` | **AS_ID**: `b3171d85ffdf769408f0f1108c4fd9ae`
**Environment**: development only (tag: `d`)
**BASK Version**: v9.2.0
**DNS Domain**: dcm.alzp.tgscloud.net
**Scope**: DCM Account only — no collectors, no datalake account, no APIGEE/VPC Lattice integration (deferred)

---

## Decisions & Assumptions

- **Scope**: DCM Account only. Collectors (AWS/Azure), Datalake Account, API Platform (APIGEE+VPC Lattice) are excluded. VPC Lattice deferred — APIGEE team will tell us what they need later.
- **Entra ID**: App Registrations created via `idp-iac-module-app-registration` + `idp-iac-module-group` (uses terraform-provider-identityrobot v0.13.0 under the hood).
- **Environment**: Development (`d`) only for now.
- **Frontend**: Deploy S3+CloudFront with a Hello World React app.
- **Backend**: Infra only — no .NET app code, no container image yet.
- **Lambda Ingestion**: Infra skeleton only — placeholder handler. Lambda is **regional** (not per-AZ).
- **LakeBase**: Available, use Databricks LakeBase PostgreSQL. **If LakeBase is unavailable at deploy time → STOP and ask the user** (no auto-fallback).
- **Network**: Use existing BASK network config. Non-routable range 100.64.0.0/16 available if needed (requires Private NAT Gateway for routing). AZ1+AZ2 only (AZ3 has no route to hub).
- **DLQ**: Included with SQS (part of BB or raw Terraform).
- **Testing**: `bask iac validate` + `bask iac plan` after each task (no apply until full plan review).
- **Monitoring**: Basic CloudWatch logging from BBs only. Full monitoring added later.
- **CI/CD**: Existing BASK workflows sufficient — no updates needed.
- **DNS**: `dcm.alzp.tgscloud.net` for API Gateway and CloudFront.

---

## Phase 0: Pre-Requisites

### Task 0.0: Update BASK, bask-cli & Merge Pending PRs
- **Status**: todo
- **Action**:
  1. Verify current BASK framework version in `version.txt` — ensure it is the latest release.
  2. If not latest, run `Scripts/update-bask.sh` (or `update-bask-for-mac.sh` on macOS) to create a `dependabask` branch, review and merge the resulting PR.
  3. Verify `bask` CLI is at the latest version: `bask --version`. Update if needed (`bask update` or reinstall).
  4. Check for any open Dependabask / BUMP PRs on the repo and merge them all before proceeding. This ensures all Building Block version bumps and framework upgrades are incorporated.
  5. After merging, pull `main` to have a clean, fully up-to-date baseline.
- **Output**: `version.txt` reflects latest BASK version, `bask` CLI is current, no pending BUMP PRs remain, `main` is up to date.

### Task 0.1: Run Bootstrap
- **Status**: todo
- **Context**: Bootstrap creates the S3 backend bucket (`awsd-{app_name}-terraform-states-bucket`) and GitHub OIDC role for Terraform CI/CD authentication. This is a one-time setup per environment. Uses `Project/Bootstrap/` which deploys `aws-iac-bask-terraform-backend v4.0.0` + `aws-iac-bask-oidc v2.1.1`.
- **Action**:
  1. Ensure AWS credentials are configured for account `awss-wl-dcm (551656632516)`.
  2. Run Bootstrap via `Bootstrap.yaml` workflow (or `bask bootstrap plan -e development` then `bask bootstrap apply -e development`).
  3. Required inputs: `g_app_name`, `m_environment_tag = "d"`, `github_repo_name = "BA-Data-Connect-Monitoring-infra"`.
  4. First run requires AWS credentials; subsequent runs use OIDC.
- **Output**: S3 state bucket created, OIDC role created, backend ready for `bask iac init`.

### Task 0.2: Create Feature Branch
- **Status**: todo
- **Action**: Create branch `feat/dcm-core-infrastructure` from `main`.
- **Output**: Branch created, all subsequent work committed here.

### Task 0.3: BB Catalog Verification
- **Status**: todo
- **Action**: Query `bb-mcp-server` (or `gh` CLI fallback) to verify exact BB names, latest versions, and variable signatures for all BBs.

| Architecture Label | Expected BB ID | Status |
|---|---|---|
| WAF_1 | aws-iac-bb-waf-1 | ✅ Confirmed v5.1.2 |
| CT_2_SLESS_SERVICE | aws-iac-bb-ct-2-sless-service | ✅ Confirmed v3.4.0 |
| API_GW_2R | aws-iac-bb-api-gw-2r | ❓ Verify version+variables |
| JOB_1 (Lambda) | aws-iac-bb-job-1 | ❓ Verify version+variables |
| MQS_1 (SQS) | ❓ | ❓ Verify if BB exists on AWS |
| ML_1 (Databricks) | ❓ | ❓ Verify if BB exists on AWS |
| WEB_2 (S3+CloudFront) | aws-iac-bb-web-2 | ❓ Verify AWS variant exists |
| ST_O (S3 DBFS) | aws-iac-bb-st-o | ✅ In catalog, verify version |
| SV_1 (Secrets) | ❓ | ❓ Verify if BB exists on AWS |
| App Registration | idp-iac-module-app-registration | ✅ Confirmed in BASK docs |
| Group | idp-iac-module-group | ✅ Confirmed in BASK docs |

- **Output**: Full BB reference table with confirmed names, versions, required variables, and outputs.

---

## Phase 1: Foundation — Network & VPC Endpoints

**Depends on**: Phase 0
**Goal**: Ensure VPC, subnets, and all required VPC endpoints are deployed.

### Task 1.1: Verify/Update Network Foundation
- **Status**: todo
- **Context**: `Project/IaC/FOUNDATION.tf` already deploys `aws-iac-bask-network v6.0.0` with VPC, subnets, NAT GW, S3 gateway endpoint, CloudWatch + Secrets Manager interface endpoints.
- **Action**: Verify current subnet layout in `Project/Environments/development.tfvars` supports DCM: non-routable private subnets in AZ1+AZ2 for ECS (dual-AZ ALB) and Databricks. Lambda is regional — no AZ-specific subnet needed for it (but needs VPC config if VPC-deployed). The existing `/22 non-routable-private` + `/28 routable-private with NAT` should be sufficient.
- **Output**: Confirmed network config or updated `development.tfvars`.

### Task 1.2: Deploy Additional VPC Endpoints
- **Status**: todo
- **Dependency**: Task 1.1
- **Context**: BASK network module already provides S3 gateway, CloudWatch, Secrets Manager endpoints. Architecture requires additional: SQS (interface), ECR (interface), KMS (interface), Databricks SCC Relay (interface), Databricks Workspace (interface).
- **Action**: Create `VPC_ENDPOINTS.tf` in `Project/IaC/` with additional VPC interface endpoints. Use `aws_vpc_endpoint` resources with proper security groups.
- **Files**: `Project/IaC/VPC_ENDPOINTS.tf` (new)
- **Output**: All VPC endpoints deployed, security groups configured.

---

## Phase 2: Security & Identity Foundation

**Depends on**: Phase 1
**Goal**: Secrets Manager, KMS keys, Entra ID App Registrations.

### Task 2.1: Deploy Secrets Manager (SV_1 BB or raw TF)
- **Status**: todo
- **Context**: DCM Core needs Secrets Manager for: Entra ID client secret, DB credentials, API keys. Verify if `SV_1` BB exists on AWS.
- **Action**: Create `SV_1.tf` with Secrets Manager secrets (placeholder values initially). Include KMS CMK for encryption.
- **Files**: `Project/IaC/SV_1.tf` (new)
- **Output**: Secrets Manager secrets + KMS key deployed.

### Task 2.2: Create Entra ID App Registrations
- **Status**: todo
- **Context**: Architecture requires App Registrations for: (1) DCM API service principal (client_credentials for collectors), (2) DCM SPA app registration (OIDC for user auth). BASK provides `idp-iac-module-app-registration` and `idp-iac-module-group` modules which use `terraform-provider-identityrobot v0.13.0` under the hood.
- **Action**:
  1. Add `identityrobot` provider to `VERSIONS.tf` (pin v0.13.0).
  2. Create `ENTRA_ID.tf` using `idp-iac-module-app-registration` for both registrations.
  3. Store generated client secrets in Secrets Manager (from Task 2.1).
- **Files**: `Project/IaC/VERSIONS.tf` (update), `Project/IaC/ENTRA_ID.tf` (new)
- **Sub-agent prompt**: "Research `idp-iac-module-app-registration` GitHub repo to find exact module source URL, variables, and outputs. Also research terraform-provider-identityrobot v0.13.0 for provider block config. Check if the module auto-creates service principals and configures OAuth2 scopes."
- **Output**: App Registration(s) created in Entra ID, client secrets stored in Secrets Manager.

---

## Phase 3: Data Layer

**Depends on**: Phase 1, Phase 2 (for secrets/KMS)
**Goal**: S3 buckets, SQS queue, Databricks workspace.

### Task 3.1: Deploy S3 DBFS Root Bucket (ST_O BB)
- **Status**: todo
- **Context**: Databricks requires an S3 bucket for DBFS root storage. Use `aws-iac-bb-st-o` BB.
- **Action**: Query bb-mcp-server for `aws-iac-bb-st-o` variables/outputs. Create `ST_O_DBFS.tf`.
- **Files**: `Project/IaC/ST_O_DBFS.tf` (new)
- **Output**: S3 bucket deployed with VPC-restricted access, KMS encryption.

### Task 3.2: Deploy SQS Queue with DLQ (MQS_1 BB or raw TF)
- **Status**: todo
- **Context**: Ingestion pipeline buffers messages in SQS. Architecture specifies `MQS_1` BB with DLQ. Need to verify if BB exists.
- **Action**: If BB exists, use it. Otherwise, create raw Terraform: `aws_sqs_queue` (main + DLQ) with KMS encryption, VPC endpoint policy, redrive policy (5 retries → DLQ).
- **Files**: `Project/IaC/MQS_1.tf` (new)
- **Output**: SQS main queue + DLQ deployed.

### Task 3.3: Deploy Databricks Workspace (ML_1 BB or raw TF)
- **Status**: todo
- **Dependency**: Task 1.2 (VPC endpoints), Task 3.1 (S3 DBFS bucket)
- **Context**: Core analytics platform. Architecture specifies `ML_1` BB. Requires: VPC integration (Secure Cluster Connectivity), SCC relay + workspace VPC endpoints, S3 DBFS root bucket, Unity Catalog. LakeBase PostgreSQL runs inside workspace.
- **Action**: Verify if `ML_1` BB exists via bb-mcp-server. If yes, use it with SCC configuration. If no, deploy Databricks workspace via raw Terraform. Add `databricks` provider to `VERSIONS.tf`.
- **Files**: `Project/IaC/ML_1.tf` (new), `Project/IaC/VERSIONS.tf` (update)
- **Risks**: Workspace provisioning takes 15-30 min. Requires Databricks account-level credentials.
- **⚠️ BLOCKER**: If LakeBase PostgreSQL is unavailable at deploy time → **STOP and ask the user** for direction. Do NOT auto-fallback.
- **Output**: Databricks workspace + cluster + LakeBase PostgreSQL configured.

---

## Phase 4: Compute Layer

**Depends on**: Phase 1, Phase 2, Phase 3
**Goal**: Lambda ingestion, ALB+WAF, ECS Fargate backend.

### Task 4.1: Deploy ALB + WAF (WAF_1 BB) — AZ1+AZ2
- **Status**: todo
- **Dependency**: Task 1.1 (VPC/subnets in AZ1+AZ2)
- **Context**: Internal ALB with WAF protecting ECS backend. BB `aws-iac-bb-waf-1 v5.1.2` deploys: ALB across AZ1+AZ2, Security Group, ACM certificate (dcm.alzp.tgscloud.net), WAF WebACL association.
- **Action**: Create `WAF_1.tf`. Configure: non-routable private subnets **in both AZ1 and AZ2** for HA, internal ALB, private domain, services block routing to ECS backend port 8443.
- **Files**: `Project/IaC/WAF_1.tf` (new)
- **Output**: Internal ALB (dual-AZ) + WAF deployed, target groups created.

### Task 4.2: Deploy Lambda Ingestion API (JOB_1 BB) — Regional
- **Status**: todo
- **Dependency**: Task 3.2 (SQS queue ARN)
- **Context**: Lambda is **regional** (not AZ-bound). Receives KPI payloads and writes to SQS. Architecture label `API_1`. BASK catalog has `JOB_1` (aws-iac-bb-job-1). Skeleton code only.
- **Action**: Query bb-mcp-server for `aws-iac-bb-job-1` variables. Create `JOB_1.tf`. Configure: VPC deployment (connects to SQS via VPC endpoint), IAM role with `sqs:SendMessage`. Placeholder Python handler.
- **Files**: `Project/IaC/JOB_1.tf` (new), `Project/Source/LAMBDA_INGESTION/` (skeleton code)
- **Output**: Lambda function deployed (skeleton), connected to SQS.

### Task 4.3: Deploy ECS Fargate Backend (CT_2_SLESS_SERVICE BB) — AZ1+AZ2
- **Status**: todo
- **Dependency**: Task 4.1 (WAF_1 ALB target group ARN)
- **Context**: .NET backend on ECS Fargate across AZ1+AZ2 (behind ALB). BB v3.4.0 deploys: ECS cluster, service, task definition, ECR, IAM roles, CloudWatch logs. Infra only.
- **Action**: Create `CT_2_SLESS_SERVICE.tf`. Configure: non-routable private subnets in AZ1+AZ2, INFRA-FIRST mode, security groups for TCP 8443, load_balancer block pointing to WAF_1 ALB target group.
- **Files**: `Project/IaC/CT_2_SLESS_SERVICE.tf` (new)
- **Output**: ECS cluster, service (dual-AZ), task definition, ECR repo deployed.

---

## Phase 5: API & Presentation Layer

**Depends on**: Phase 4
**Goal**: API Gateway, CloudFront + S3 React hosting.

### Task 5.1: Deploy API Gateway REST (API_GW_2R BB)
- **Status**: todo
- **Dependency**: Task 4.1 (ALB for VPC Link), Task 2.2 (Entra ID for JWT config)
- **Context**: Public REST API with JWT validation. BB `aws-iac-bb-api-gw-2r` provides: API Gateway REST + Cognito/OIDC JWT auth. Routes via VPC Link to internal ALB. Domain: dcm.alzp.tgscloud.net.
- **Action**: Query bb-mcp-server for `aws-iac-bb-api-gw-2r`. Create `API_GW_2R.tf`. Configure: VPC Link to ALB, JWT authorizer (Entra ID), stages (dev), custom domain + ACM certificate.
- **Files**: `Project/IaC/API_GW_2R.tf` (new)
- **Output**: API Gateway deployed with JWT auth, routing to ALB.

### Task 5.2: Deploy S3 + CloudFront Static Hosting (WEB_2 BB or raw TF)
- **Status**: todo
- **Context**: React dashboard hosted on S3, served via CloudFront CDN. Deploy a Hello World React app.
- **Action**: Verify if `aws-iac-bb-web-2` supports AWS S3+CloudFront. If not, use raw Terraform: `aws_s3_bucket` + `aws_cloudfront_distribution` (OAC). Build and upload Hello World React app.
- **Files**: `Project/IaC/WEB_2.tf` (new), `Project/Source/REACT_HELLO_WORLD/` (Hello World app)
- **Output**: CloudFront distribution + S3 bucket deployed with Hello World React app.

---

## Phase 6: Wiring — Variables, Outputs, tfvars

**Depends on**: All previous phases
**Goal**: Wire everything together.

### Task 6.1: Update VARIABLES.tf
- **Status**: todo
- **Action**: Add all new variables needed by BBs.
- **Files**: `Project/IaC/VARIABLES.tf` (update)

### Task 6.2: Update OUTPUTS.tf
- **Status**: todo
- **Action**: Expose: API Gateway URL, CloudFront domain, ALB DNS, ECS cluster ARN, SQS queue URL/ARN, Lambda ARN, Databricks workspace URL, ECR repo URL.
- **Files**: `Project/IaC/OUTPUTS.tf` (update)

### Task 6.3: Update development.tfvars
- **Status**: todo
- **Action**: Add concrete values for new variables.
- **Files**: `Project/Environments/development.tfvars` (update)

### Task 6.4: Finalize VERSIONS.tf
- **Status**: todo
- **Action**: Ensure all providers pinned: `aws`, `archive`, `databricks`, `identityrobot` (v0.13.0).
- **Files**: `Project/IaC/VERSIONS.tf` (update)

---

## Phase 7: Validation & Testing

**Depends on**: Phase 6
**Goal**: Full validation before any apply.

### Task 7.1: Terraform Validate
- **Status**: todo
- **Action**: Run `bask iac validate -e development`. Fix all errors.
- **Output**: Zero validation errors.

### Task 7.2: Terraform Plan Review
- **Status**: todo
- **Action**: Run `bask iac plan -e development`. Review plan output — expect ~50-80 resources. Verify no destructive changes to existing infra.
- **Output**: Plan reviewed, resource count confirmed.

### Task 7.3: CI Pipeline Dry Run
- **Status**: todo
- **Action**: Push branch, run `Development.yaml` workflow manually with `plan` action. Verify CI plan matches local plan.
- **Output**: CI plan passes, matches local.

### Task 7.4: Security Review Checklist
- **Status**: todo
- **Action**: Verify all deployed resources against TotalEnergies cyber standards:
  - All subnets non-routable (no public IPs)
  - All VPC endpoints configured (no internet traversal)
  - KMS encryption on SQS, S3, Secrets Manager
  - WAF WebACL on ALB
  - JWT validation on API Gateway
  - IAM least-privilege roles
  - No hardcoded secrets
  - TLS 1.2+ everywhere
- **Output**: Security checklist passed.

---

## Phase 8: Apply to Development

**Depends on**: Phase 7 (all validation passing)
**Goal**: Deploy to `awss-wl-dcm` dev environment.

### Task 8.1: Apply Infrastructure
- **Status**: todo
- **Action**: Run `bask iac apply -e development` (or via Development.yaml workflow). Monitor for timeouts/errors, especially Databricks (15-30 min).
- **Output**: All resources deployed successfully.

### Task 8.2: Post-Apply Smoke Tests
- **Status**: todo
- **Action**:
  1. Verify VPC endpoints are `available` status
  2. Curl CloudFront URL → Hello World React page loads
  3. Curl API Gateway URL with valid JWT → reaches ALB → ECS (or 503 if no container)
  4. Invoke Lambda with test payload → message appears in SQS
  5. Login to Databricks workspace → LakeBase PostgreSQL accessible
  6. Verify ECR repository exists
  7. Verify Secrets Manager secrets exist
- **Output**: All smoke tests pass.

### Task 8.3: Validate State File
- **Status**: todo
- **Action**: Run `bask iac state-list -e development`. Confirm all expected resources in state. Verify state file in S3: `iac-application-d.tfstate`.
- **Output**: State file consistent with plan.

---

## Phase 9: Documentation & Cleanup

**Depends on**: Phase 8
**Goal**: Generate docs, clean up, prepare for PR.

### Task 9.1: Generate README
- **Status**: todo
- **Action**: Run `bash Scripts/readme-gen.sh` to regenerate README with new modules.
- **Files**: `README.md` (auto-generated)

### Task 9.2: Create Architecture Scope Diagram
- **Status**: todo
- **Action**: Create a diagram in `Docs/ai-build/` showing exactly the scope deployed: DCM Account components only, clearly marking what's included vs excluded (collectors, datalake, APIGEE).
- **Files**: `Docs/ai-build/dcm-core-scope.md` (new)

### Task 9.3: Update Plan File Status
- **Status**: todo
- **Action**: Update all task statuses in the plan file to `done`. Record any deviations or decisions made during implementation.
- **Files**: `Docs/ai-build/plan.md` (update)

---

## Phase 10: Jira Task Management

**Depends on**: Phase 0 (plan approval)
**Goal**: Create Jira issues for every task, linked to epic DPP-13.

### Task 10.1: Create Jira Issues
- **Status**: todo
- **Action**: For each task in Phases 1-9, create a Jira issue in project DPP with:
  - Summary: task title
  - Description: full task details (context, action, files, dependencies, output)
  - Parent: DPP-13 (epic link)
  - Labels: `dcm-infra`
  - Priority based on dependency (blockers = High)
- **Output**: All Jira issues created and linked to DPP-13.

---

## Phase 11: Pull Request & Review

**Depends on**: Phase 8, 9
**Goal**: PR to main, review, merge.

### Task 11.1: Create Pull Request
- **Status**: todo
- **Action**: Create PR from `feat/dcm-core-infrastructure` → `main`. Include:
  - Description with architecture scope diagram
  - Link to Jira epic DPP-13
  - Terraform plan output summary
  - Smoke test results
- **Output**: PR created, CI plan runs automatically.

### Task 11.2: Address Review Comments
- **Status**: todo
- **Action**: Address any review comments from architects/cyber team. Iterate until approved.
- **Output**: PR approved.

### Task 11.3: Merge & CD
- **Status**: todo
- **Action**: Merge PR to main. CD workflow (`CD.yaml`) triggers apply.
- **Output**: Infrastructure deployed via CD pipeline.

---

## Verification

1. `bask iac validate -e development` — zero errors after each task
2. `bask iac plan -e development` — review plan (~50-80 resources)
3. `Development.yaml` workflow on feature branch — CI plan passes
4. Post-apply: CloudFront Hello World loads via HTTPS
5. Post-apply: API Gateway returns 401 without JWT, proper response with valid JWT
6. Post-apply: Lambda test invocation writes to SQS
7. Post-apply: Databricks workspace accessible, LakeBase PostgreSQL connectable
8. Security checklist: non-routable subnets, VPC endpoints, KMS, WAF, JWT, IAM ✓

---

## Relevant Files

### Existing (modify)
- `Project/IaC/FOUNDATION.tf` — verify subnet config supports all components
- `Project/IaC/VARIABLES.tf` — add new BB variables
- `Project/IaC/OUTPUTS.tf` — expose new BB outputs
- `Project/IaC/VERSIONS.tf` — add databricks + identityrobot providers
- `Project/Environments/development.tfvars` — add new variable values

### New (create)
- `Project/IaC/VPC_ENDPOINTS.tf` — additional VPC endpoints (SQS, ECR, KMS, Databricks)
- `Project/IaC/SV_1.tf` — Secrets Manager + KMS
- `Project/IaC/ENTRA_ID.tf` — App Registrations via idp-iac-module-app-registration
- `Project/IaC/ST_O_DBFS.tf` — S3 DBFS root bucket
- `Project/IaC/MQS_1.tf` — SQS queue + DLQ
- `Project/IaC/ML_1.tf` — Databricks workspace + LakeBase
- `Project/IaC/JOB_1.tf` — Lambda ingestion API
- `Project/IaC/WAF_1.tf` — ALB + WAF (internal, AZ1+AZ2)
- `Project/IaC/CT_2_SLESS_SERVICE.tf` — ECS Fargate backend (AZ1+AZ2)
- `Project/IaC/API_GW_2R.tf` — API Gateway REST + JWT auth
- `Project/IaC/WEB_2.tf` — CloudFront + S3 React hosting
- `Docs/ai-build/plan.md` — this plan file committed to repo
- `Docs/ai-build/dcm-core-scope.md` — architecture scope diagram

---

## Dependency Graph

```
Phase 0: Pre-requisites (no dependencies)
  Task 0.0: Update BASK, bask-cli & merge pending PRs
  Task 0.1: Run Bootstrap
  Task 0.2: Create branch
  Task 0.3: BB Catalog Verification

Phase 1 (after Phase 0):
  Task 1.1: Verify Network Foundation
  Task 1.2: Deploy VPC Endpoints (depends on 1.1)

Phase 2 (parallel with Phase 1):
  Task 2.1: Secrets Manager + KMS
  Task 2.2: Entra ID App Registrations (via idp-iac-module-app-registration)

Phase 3 (after Phase 1+2):
  Task 3.1: S3 DBFS Root Bucket (parallel with 3.2)
  Task 3.2: SQS Queue + DLQ (parallel with 3.1)
  Task 3.3: Databricks Workspace (depends on 1.2, 3.1) ⚠️ BLOCKER if LakeBase unavailable

Phase 4 (after Phase 3):
  Task 4.1: WAF_1 ALB — AZ1+AZ2 (depends on 1.1)
  Task 4.2: Lambda Ingestion — regional (depends on 3.2)
  Task 4.3: ECS Fargate Backend — AZ1+AZ2 (depends on 4.1)

Phase 5 (after Phase 4):
  Task 5.1: API Gateway (depends on 4.1, 2.2)
  Task 5.2: CloudFront + S3 React (parallel with 5.1)

Phase 6 (after Phase 5):
  Tasks 6.1-6.4: Variables, Outputs, tfvars, Versions

Phase 7 (after Phase 6):
  Tasks 7.1-7.4: Validate, Plan, CI dry run, Security review

Phase 8 (after Phase 7):
  Tasks 8.1-8.3: Apply, Smoke tests, State validation

Phase 9 (after Phase 8):
  Tasks 9.1-9.3: README, Architecture scope doc, Plan status update

Phase 10 (parallel — can start after Phase 0 approval):
  Task 10.1: Create Jira issues linked to DPP-13

Phase 11 (after Phase 8+9):
  Tasks 11.1-11.3: PR, Review, Merge + CD
```
