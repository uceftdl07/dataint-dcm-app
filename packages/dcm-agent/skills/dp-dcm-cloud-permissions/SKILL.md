---
name: dp-dcm-cloud-permissions
description: DCM collector cloud permissions — Azure RBAC and AWS IAM. Agent executes az role assignment create / aws iam attach-role-policy.
---

# DCM Cloud Permissions

Permissions for the **runtime identity** that executes collection. Apply to Managed Identity (Azure) or ECS Task Role (AWS) — **not** the Entra OAuth SP.

**Agent behavior:** execute `az role assignment create` via `#tool:execute` for each enabled collector. Discover MI with `az webapp identity show`.

**Prerequisite (Azure):** collector App Service must exist with System-Assigned MI (`JOB_2` + `SV_1`). If `az webapp list` returns empty → **skip Phase 4** (not blocked) and handoff Phase 5 (`dp-azlz-devops-builder`). Re-run Phase 4 after deployment.

On policy deny → report error. On missing MI before deployment → skip, not error.

## Agent execution pattern (Azure)

```bash
PRINCIPAL_ID=$(az webapp identity show -g <rg> -n <app> --query principalId -o tsv)
SCOPE="/subscriptions/<subscription_id>"
az role assignment create --assignee "$PRINCIPAL_ID" --role "Reader" --scope "$SCOPE"
# repeat per enabled_collectors from Phase 1 matrix below
```

## Permissions per collector (apply only if selected)

Filter the matrix below using `enabled_collectors` from Phase 1. **Do not assign roles for excluded collectors.**

### Azure — collector → RBAC

| Collector key | RBAC role | Scope |
|---------------|-----------|-------|
| `datafactory`, `activity_runs` | Data Factory Contributor* | Resource Group |
| `databricks`, `databricks_pipelines` | Reader | Subscription |
| `cost_management` | Cost Management Reader | Subscription |
| `databases` | Monitoring Reader + Reader | Subscription / RG |
| `security_center` | Security Reader | Subscription |
| `users`, `standard_checks` | Reader | Subscription |

\* Use Reader on ADF if Contributor is too broad.

### AWS — collector → IAM actions (subset of task role)

| Collector key | IAM actions needed |
|---------------|-------------------|
| `glue` | `glue:Get*`, `glue:List*`, `glue:BatchGet*` |
| `emr` | `elasticmapreduce:List*`, `elasticmapreduce:Describe*` |
| `rds` | `rds:Describe*`, `rds:List*` + CloudWatch read |
| `cost_explorer` | `ce:Get*`, `ce:List*` |
| `redshift` | `redshift:Describe*`, `redshift:View*` + CloudWatch read |

Build the IAM policy from the union of actions for **selected** collectors only.

## Azure — RBAC (Managed Identity) — full reference

| Role | Scope | Service collected |
|------|-------|-------------------|
| Monitoring Reader | Subscription or Resource Group | Azure Monitor (SQL, Postgres, MySQL, Cosmos) |
| Cost Management Reader | Subscription | Azure Cost Management |
| Reader | Subscription | Resource listing (Databricks, databases) |
| Security Reader | Subscription | Microsoft Defender for Cloud |
| Data Factory Contributor* | Resource Group | Azure Data Factory pipelines |

\* Use Reader on ADF if Contributor is too broad for your LZ policy.

### Key Vault access (separate from above)

| Role / Policy | Scope | Purpose |
|---------------|-------|---------|
| Key Vault Secrets User | Key Vault instance | Read collector secrets |

## AWS — IAM (ECS Task Role)

Minimum read-only policy (resource `*` often required for listing APIs):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DCMCollectorRead",
      "Effect": "Allow",
      "Action": [
        "glue:Get*",
        "glue:List*",
        "glue:BatchGet*",
        "elasticmapreduce:List*",
        "elasticmapreduce:Describe*",
        "rds:Describe*",
        "rds:List*",
        "ce:Get*",
        "ce:List*",
        "redshift:Describe*",
        "redshift:View*",
        "logs:Describe*",
        "logs:Get*",
        "cloudtrail:LookupEvents"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DCMCollectorSecrets",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "arn:aws:secretsmanager:{region}:{account_id}:secret:dcm-credentials-*"
    },
    {
      "Sid": "DCMCollectorKMS",
      "Effect": "Allow",
      "Action": ["kms:Decrypt"],
      "Resource": "arn:aws:kms:{region}:{account_id}:key/{kms-key-id}"
    }
  ]
}
```

Restrict `Resource` to specific ARNs when your LZ policy allows.

## Building Blocks

| Cloud | Runtime | BB |
|-------|---------|-----|
| Azure | App Service WebJob | `JOB_2`, `SV_1` |
| AWS | ECS Fargate + scheduler | `CT_2_SLESS_TASK`, `CRON_1`, `SV_1` |

## Network

| Cloud | Outbound to | Path |
|-------|-------------|------|
| Azure | Entra ID, Apigee, Azure Management APIs | VNET integration / private endpoints |
| AWS | Entra ID, Apigee | NAT Gateway from private routed subnet |
| AWS | AWS service APIs | Task Role via VPC endpoints where available |

## Checklist

- [ ] Permissions on **runtime identity** only
- [ ] OAuth SP has **no** cloud RBAC/IAM
- [ ] Least privilege reviewed for LZ cyber policy
- [ ] Secrets access scoped to DCM credential secret only
- [ ] Outbound connectivity to Apigee and Entra ID verified
