---
name: dp-dcm-secrets-config
description: Configure DCM collector secrets in Azure Key Vault or AWS Secrets Manager. Agent bootstraps KV network (PIM + IP whitelist), writes all 4 secrets; manual guide only as last resort.
---

# DCM Secrets Configuration

Store Entra ID and Apigee credentials for the collector runtime. Secrets are read by the **runtime identity** (Managed Identity or ECS Task Role), not by the OAuth SP directly at rest.

## Agent workflow (Azure — preferred)

1. **Phase 3.0 — PIM check** — verify active `[IASP] Landing Zone Contributor` on the LZ subscription (see below). If missing → `askQuestions`: user activates PIM in portal, confirms, agent re-checks.
2. **Phase 3.1 — KV network bootstrap** — on `ForbiddenByFirewall`: PIM active → agent auto-detects caller IP → `network-rule add ${MY_IP}/32` on BB vault `azr{env}kv{appcode}-dcm`, wait ~30s.
3. **Phase 3.2 — Write all 4 secrets** via `az keyvault secret set` or copy from `SRC_VAULT` — never echo values in chat.
4. **Phase 3.3 — Verify** `az keyvault secret list` shows all `dcm-*` names → ✅ continue to Phase 4.
5. **Phase 3.4 — Cleanup (optional)** — remove temporary IP rule; re-disable `publicNetworkAccess` if it was off before bootstrap.
6. **Fallback — guided manual mode** only if PIM unavailable or bootstrap still blocked after retry.

## Apigee key — source (not chat)

Same value as GitHub secret **`DCM_APIGEE_API_KEY`** on repo `dataint-dcm-app` (deploy collector — `.github/workflows/dcm-azure-collector.yml`). One key per environment (DEV/PROD), shared across all LZs.

Agent **never** reads key from chat. Order:

1. Copy `dcm-apigee-api-key` from source/staging vault if already present
2. Copy from another onboarded LZ vault (same env)
3. Maintainer writes from GitHub → Settings → Secrets (repo maintainer)

```bash
APIGEE_KEY=$(az keyvault secret show --vault-name "$SRC_VAULT" -n dcm-apigee-api-key --query value -o tsv)
```

## Phase 3.0 — PIM / LZ Contributor (Azure IAS)

**Portal only** — agent cannot activate PIM via CLI. User must activate before Phase 3.1 / 3b:

| PIM role | Needed for |
|----------|------------|
| `[IASP] Landing Zone Contributor` | KV network rules, enable public access, `vaults/write` |
| `[IASP] Landing Zone Owner` | `Key Vault Secrets Officer` assignment if `ForbiddenByRbac` |

After user confirms PIM active → agent re-runs check below, then **Phase 3.1 IP bootstrap** on target vault.

```bash
SUB="{subscription_id}"
USER_OID=$(az ad signed-in-user show --query id -o tsv)
LZ_CONTRIB=$(az role assignment list --assignee "$USER_OID" --scope "/subscriptions/$SUB" \
  --role "[IASP] Landing Zone Contributor" --query "[0].id" -o tsv 2>/dev/null)
echo "lz_contributor=${LZ_CONTRIB:-missing}"
```

If `missing` → `askQuestions`: *"Active PIM `[IASP] Landing Zone Contributor` (+ `LZ Owner` si RBAC KV) sur {azure_lz_name} (portal → PIM → My roles → Activate 2–8h), puis confirme"* → re-check.

## Phase 3.1 — Key Vault network bootstrap (BB vault + core vault)

**Typical error:** `ForbiddenByFirewall` / `Client address is not authorized` on BB vault `azr{env}kv{appcode}-dcm` (private endpoint + `defaultAction=Deny`).

**Agent auto-whitelists caller IP** — do not ask user to paste IP:

```bash
VAULT="{vault_name}"   # Phase 3b: phase3_dcm_vault e.g. azrmkvndth-dcm
MY_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s api.ipify.org)
KV_PNA=$(az keyvault show -n "$VAULT" --query properties.publicNetworkAccess -o tsv 2>/dev/null)
echo "caller_ip=$MY_IP publicNetworkAccess=$KV_PNA"

if [ "$KV_PNA" = "Disabled" ]; then
  az keyvault update -n "$VAULT" --public-network-access Enabled
fi
az keyvault network-rule add -n "$VAULT" --ip-address "${MY_IP}/32" 2>/dev/null || true
sleep 30
az keyvault secret list --vault-name "$VAULT" --query "[].name" -o tsv | head -3
```

Requires active `[IASP] Landing Zone Contributor` (`Microsoft.KeyVault/vaults/write`).

## Phase 3.1b — Key Vault RBAC (RBAC-enabled vaults)

If network is OK but `ForbiddenByRbac` on `setSecret` / `readMetadata`: the vault uses `enableRbacAuthorization=true`. LZ Contributor can modify vault **network** but not secrets until `Key Vault Secrets Officer` is assigned on the vault scope.

Requires `[IASP] Landing Zone Owner` (PIM) to create role assignments:

```bash
KV_SCOPE="/subscriptions/{subscription_id}/resourceGroups/{rg}/providers/Microsoft.KeyVault/vaults/{vault_name}"
USER_OID=$(az ad signed-in-user show --query id -o tsv)
az role assignment create --assignee "$USER_OID" --role "Key Vault Secrets Officer" --scope "$KV_SCOPE"
sleep 15   # RBAC propagation
```

Then continue Phase 3.2.

`collector_client_secret` must come from Phase 2 `add_client_secret` in the **same shell session** (env var `DCM_COLLECTOR_CLIENT_SECRET`) — never print it.

```bash
VAULT="{vault_name}"
TENANT_ID=$(az account show --query tenantId -o tsv)
SRC_VAULT="{staging_or_existing_kv}"
APIGEE_KEY=$(az keyvault secret show --vault-name "$SRC_VAULT" -n dcm-apigee-api-key --query value -o tsv 2>/dev/null)

az keyvault secret set --vault-name "$VAULT" -n dcm-entra-tenant-id --value "$TENANT_ID"
az keyvault secret set --vault-name "$VAULT" -n dcm-entra-client-id --value "{collector_appId}"
az keyvault secret set --vault-name "$VAULT" -n dcm-entra-client-secret --value "$DCM_COLLECTOR_CLIENT_SECRET"
az keyvault secret set --vault-name "$VAULT" -n dcm-apigee-api-key --value "$APIGEE_KEY"
```

If `DCM_COLLECTOR_CLIENT_SECRET` empty and secret not in vault → run `add_client_secret` once, capture to env var, write immediately.

## Fallback — guided manual mode

Only when Phase 3.0–3.2 still blocked after user confirmed PIM:

- Resolve `tenant_id` and `collector_appId` — show in guide table
- Placeholders only for client-secret and apigee-key
- `askQuestions`: *"J'ai stocké les 4 secrets — continuer"* → wait for **Oui**

## Apigee API key — scope (explain in Phase 3)

| Question | Answer |
|----------|--------|
| Same key for all collectors? | **Yes** — one shared key per **environment** (DEV or PROD), not per LZ |
| Where is the master? | DCM Core secret `awsd-dcm-api-keys` (owned by DCM team) |
| Where does the collector read it? | **Copy** in each LZ vault as `dcm-apigee-api-key` (Azure) or in SM JSON `apigee_api_key` (AWS) |
| User already has it? | They store it in the vault themselves — never paste in chat |

## Azure — Key Vault

### Which vault? (CRITICAL — read before Phase 3)

| Moment | Vault | Notes |
|--------|-------|-------|
| Phase 3 **early** (before infra) | Any reachable LZ vault (e.g. core `azrdkvndth-01`) | OK for Phase 6 **OAuth SP** ingest test only |
| After Phase **5.1** BB apply | **`azr{env}kv{appcode}-dcm`** (e.g. `azrdkvndth-dcm`) | **Mandatory** — BB App Settings point here |
| Phase 3b | Copy or re-write all 4 secrets into BB vault | See `dp-dcm-client-infra` post-apply step |

Discover BB vault after apply: `az keyvault list --query "[?ends_with(name,'-dcm')].name" -o tsv`

### Secret names

| Secret name | Value |
|-------------|-------|
| `dcm-entra-tenant-id` | Entra ID Tenant ID |
| `dcm-entra-client-id` | Collector SP Client ID (`appId`) |
| `dcm-entra-client-secret` | Collector SP Client Secret (regenerate if lost) |
| `dcm-apigee-api-key` | Apigee API key — **shared per env** |

### Automated (agent — one attempt)

```bash
VAULT="<key_vault_name>"
az keyvault secret set --vault-name "$VAULT" -n dcm-entra-tenant-id --value "<tenant-id>"
az keyvault secret set --vault-name "$VAULT" -n dcm-entra-client-id --value "<collector-app-id>"
az keyvault secret set --vault-name "$VAULT" -n dcm-entra-client-secret --value "<from-add_client_secret>"
az keyvault secret set --vault-name "$VAULT" -n dcm-apigee-api-key --value "<apigee-key>"
```

Discover vault: `az keyvault list --query "[?contains(name,'dcm') || contains(name,'kv')].name" -o tsv` in the LZ subscription.

### Manual guide (user — agent fills known values)

**Agent must display** (example novadatahub):

| Secret KV | Valeur | Source |
|-----------|--------|--------|
| `dcm-entra-tenant-id` | `329e91b0-e21f-48fb-a071-456717ecc28e` | Tenant TotalEnergies |
| `dcm-entra-client-id` | `c2e2404c-01af-4107-98bd-745bc53a9b01` | appId SP `AZR-IASP-LZ-novadatahub-dcm-collector` |
| `dcm-entra-client-secret` | *(utilisateur)* | MR Robot `add_client_secret` — régénérer si perdu |
| `dcm-apigee-api-key` | *(utilisateur)* | DCM Data Squad — clé partagée env DEV |

```bash
VAULT="azrdkvndth-01"
az keyvault secret set --vault-name "$VAULT" -n dcm-entra-tenant-id --value "329e91b0-e21f-48fb-a071-456717ecc28e"
az keyvault secret set --vault-name "$VAULT" -n dcm-entra-client-id --value "c2e2404c-01af-4107-98bd-745bc53a9b01"
az keyvault secret set --vault-name "$VAULT" -n dcm-entra-client-secret --value "<secret>"
az keyvault secret set --vault-name "$VAULT" -n dcm-apigee-api-key --value "<apigee-key>"
```

### Access policy (after App Service exists)

1. Enable **System-Assigned Managed Identity** on the collector App Service
2. Grant MI on Key Vault: **Get**, **List** (Access Policy or RBAC `Key Vault Secrets User`)

## AWS — Secrets Manager

### Secret name

`dcm-credentials-{lzName}-{env}`

### JSON format

```json
{
  "entra_tenant_id": "<tenant-id>",
  "entra_client_id": "<collector-client-id>",
  "entra_client_secret": "<collector-client-secret>",
  "apigee_api_key": "<apigee-key-shared-per-env>"
}
```

On VPC/network block → guide user to create/update secret manually, confirm, verify, continue.

## Security Rules

- Never commit secrets to git or paste in chat logs
- Rotate client secrets on a regular schedule
- Use placeholders in documentation: `<collector-client-secret>`
- Apigee API key is separate from Entra credentials — both required for ingestion

## Checklist

- [ ] `[IASP] Landing Zone Contributor` active (PIM) before KV bootstrap
- [ ] Caller IP whitelisted (temporary) if vault was private-endpoint only
- [ ] All four values stored in vault/SM by agent (manual only if bootstrap failed)
- [ ] Secret names verified (`dcm-entra-*`, `dcm-apigee-api-key`)
- [ ] Runtime identity has read access only (no write)
- [ ] Apigee key copied into LZ vault as `dcm-apigee-api-key` (source: GitHub secret `DCM_APIGEE_API_KEY` or existing vault)
