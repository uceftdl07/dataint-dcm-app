# GitHub Environments — dev / prod

Checklist pour séparer **dev** (`dcmd`) et **prod** (`dcm`).  
Script d'aide : `scripts/github-env-setup.sh` (nécessite `gh` + droits admin sur la repo).

## URLs cibles

| | Frontend | API |
|--|----------|-----|
| **dev** | `https://dcmd.alzp.tgscloud.net` | `https://api.dcmd.alzp.tgscloud.net` |
| **prod** | `https://dcm.alzp.tgscloud.net` | `https://api.dcm.alzp.tgscloud.net` |

## Comptes AWS

| Env | Compte | Label |
|-----|--------|-------|
| dev | `551656632516` | awss-wl-dcm |
| prod | `884068385310` | awsp-dcm |
| ~~dcmd~~ | `551656632516` | **mgmt only** — ne pas utiliser pour deploy frontend/backend |

## Ce que tu as en prod aujourd'hui (capture)

Secrets présents : `AWS_ROLE_ARN`, `BACKEND_ECR_*`, `BACKEND_ECS_*`, `CLOUDFRONT_DISTRIBUTION_ID`, `FRONTEND_BUCKET`, `VITE_API_BASE_URL`, `VITE_REDIRECT_URI`, `DCM_TEAMS_WEBHOOK_URL`, `AWS_COLLECTOR_ECR_REGISTRY`.

### Problème détecté

`VITE_API_BASE_URL` et `VITE_REDIRECT_URI` sont en **Secrets**, mais le workflow lit d'abord les **Variables** (`vars.VITE_*`).  
→ Soit les déplacer en Variables, soit garder en Secrets (le workflow accepte les deux depuis le fix `vars || secrets`).

### Manquant en prod (backend deploy échouera ou SSO/CORS cassé)

| Nom | Type | Valeur prod |
|-----|------|-------------|
| `DCM_CORS_ALLOWED_ORIGINS` | Variable | `https://dcm.alzp.tgscloud.net` |
| `DCM_ENVIRONMENT` | Variable | `production` |
| `DCM_APP_NAME` | Variable | `dcm-backend` |
| `DCM_DATABRICKS_CATALOG` | Variable | `it` |
| `DCM_DATABRICKS_SCHEMA` | Variable | `ba_data_connect_monitoring__a` |
| `DCM_CHAT_PROVIDER` | Variable | `genie` |
| `DCM_GENIE_SPACE_ID` | Variable/Secret | ID espace Genie prod |
| `SQS_QUEUE_URL` | Variable | URL queue ingestion prod |
| `VITE_ENABLE_AUTH` | Variable | `true` |
| `AWS_REGION` | Variable | `eu-central-1` |
| `AWS_FRONTEND_ROLE_ARN` | Secret | rôle `GithubDeploy` compte **884068385310** |
| `AZURE_TENANT_ID` | Secret | `329e91b0-e21f-48fb-a071-456717ecc28e` |
| `APP_ID` | Secret | Client ID SPA **prod** (à créer) |
| `AZURE_SCOPE` | Secret | `api://<prod-api-app-id>/access_as_user` |
| `DCM_DATABRICKS_HOST` | Secret | host workspace Databricks prod |
| `DCM_DATABRICKS_WAREHOUSE_ID` | Secret | warehouse prod |
| `DCM_DATABRICKS_SPN_CLIENT_ID` | Secret | SPN prod |
| `DCM_DATABRICKS_SPN_CLIENT_SECRET_ARN` | Secret | ARN Secrets Manager (plaintext ou suffixe JSON key) |
| `DCM_ENTRA_TENANT_ID` | Secret | même tenant |
| `DCM_ENTRA_CLIENT_ID` | Secret | Client ID API backend **prod** |

`DCM_COLLECTOR_API_KEY` : requis par le backend (`admin_collectors.py`) mais **pas injecté par le workflow** — à ajouter sur la task definition ECS manuellement ou via prochain fix workflow.

---

## Environnement `dev` — à créer

Settings → Environments → **New environment** → `dev`  
Deployment branches : limiter à `develop`.

### Variables (non sensibles)

```text
# dcm host (prod-like / shared bucket EQ7G8LQ97M10H) — utilisé par job deploy
VITE_API_BASE_URL=https://api.dcm.alzp.tgscloud.net
VITE_REDIRECT_URI=https://dcm.alzp.tgscloud.net

# dcmd host (dev) — utilisé par job build-dcmd / deploy-dcmd (build séparé)
VITE_API_BASE_URL_DCMD=https://api.dcm.alzp.tgscloud.net
VITE_REDIRECT_URI_DCMD=https://dcmd.alzp.tgscloud.net

VITE_ENABLE_AUTH=true
DCM_ENVIRONMENT=development
DCM_APP_NAME=dcm-backend
DCM_CORS_ALLOWED_ORIGINS=https://dcmd.alzp.tgscloud.net https://dcm.alzp.tgscloud.net http://localhost:4000
DCM_DATABRICKS_CATALOG=it
DCM_DATABRICKS_SCHEMA=ba_data_connect_monitoring__a
DCM_CHAT_PROVIDER=genie
AWS_REGION=eu-central-1
SQS_QUEUE_URL=<queue dev 551656632516>
DCM_GENIE_SPACE_ID=<genie space dev>
```

> **Piège** : `VITE_*` sont **baked** dans le JS au build. `dcm` et `dcmd` ne peuvent pas partager le même artefact si `VITE_REDIRECT_URI` diffère. Le workflow lance **2 builds** sur `develop` : `deploy` → bucket dcm, `deploy-dcmd` → bucket dcmd.

> **Piège 2** : `FRONTEND_BUCKET` / `CLOUDFRONT_DISTRIBUTION_ID` sur env `dev` pointent aujourd'hui vers **dcm** (`EQ7G8LQ97M10H`). `dcmd.alzp` est servi par **un autre** CloudFront (hors compte 682 ou autre distro). Sans `FRONTEND_BUCKET_DCMD` + `CLOUDFRONT_DISTRIBUTION_ID_DCMD`, `dcmd` reste sur l'ancien build.

### Secrets (copier structure prod, valeurs compte dev)

| Secret | Dev (compte 551656632516) |
|--------|---------------------------|
| `AWS_FRONTEND_ROLE_ARN` | rôle deploy S3/CF dans 682… |
| `AWS_ROLE_ARN` | rôle deploy ECS dans 682… |
| `FRONTEND_BUCKET` | `awsd-dcm-awsd-dcm-webapp-files-bucket` — **alias dcm** (`EQ7G8LQ97M10H`) |
| `CLOUDFRONT_DISTRIBUTION_ID` | `EQ7G8LQ97M10H` (dcm.alzp seulement) |
| `FRONTEND_BUCKET_DCMD` | bucket S3 derrière **dcmd.alzp** (à obtenir infra) |
| `CLOUDFRONT_DISTRIBUTION_ID_DCMD` | distro CloudFront **dcmd.alzp** (≠ EQ7G8LQ97M10H) |
| `BACKEND_ECR_REPOSITORY` | repo ECR backend dev |
| `BACKEND_ECS_CLUSTER` | `awsd-ecscluster-dcm-backend` |
| `BACKEND_ECS_SERVICE` | service ECS backend dev |
| `AZURE_TENANT_ID` | `329e91b0-e21f-48fb-a071-456717ecc28e` |
| `APP_ID` | `ef49b2f7-6dea-4181-ac06-788033b361db` (SPA dev existante) |
| `AZURE_SCOPE` | `api://15817864-589d-4a33-ada4-ec40fa309a7b/access_as_user` |
| `DCM_ENTRA_CLIENT_ID` | `15817864-589d-4a33-ada4-ec40fa309a7b` |
| `DCM_DATABRICKS_*` | valeurs workspace dev |
| `DCM_TEAMS_WEBHOOK_URL` | canal Teams dev (optionnel) |

---

## Entra ID

| Action | Dev | Prod |
|--------|-----|------|
| Redirect URI SPA | `https://dcmd.alzp.tgscloud.net/` | `https://dcm.alzp.tgscloud.net/` |
| App Registration frontend | existante `-dev` | **à créer** |
| App Registration API | existante `-d` | **à créer** |
| API GW JWT audience | client ID API dev | client ID API prod |

---

## Infra (bloquant avant premier deploy dev)

Dans `BA-Data-Connect-Monitoring-infra`, compte `551656632516` :

1. Certificat ACM + alias CloudFront `dcmd.alzp.tgscloud.net`
2. Custom domain API GW `api.dcmd.alzp.tgscloud.net`
3. CORS API GW : origin `https://dcmd.alzp.tgscloud.net`, méthodes incluant `PATCH`, routes `OPTIONS` sans JWT sur `/api/v1/auth/*`, `/api/v1/admin/*`, `/api/v1/unity-catalog/*`

---

## Commandes rapides

```bash
# Audit (lecture seule)
./scripts/github-env-setup.sh audit

# Pousser les variables dev (URLs + CORS + catalog)
./scripts/github-env-setup.sh dev

# Normaliser les variables URL prod
./scripts/github-env-setup.sh prod-vars
```

## Validation post-config

```bash
# CORS preflight (après DNS + API GW)
curl -i -X OPTIONS "https://api.dcmd.alzp.tgscloud.net/api/v1/auth/me" \
  -H "Origin: https://dcmd.alzp.tgscloud.net" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"

# Health
curl -s "https://api.dcmd.alzp.tgscloud.net/api/v1/health/live"
```

Deploy test : Actions → `dcm-frontend` / `dcm-backend` → Run workflow → environment `dev`, branch `develop`.
