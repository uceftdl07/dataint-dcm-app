# Phase 5.2 — Déployer le code collector

## En une phrase

Installer le package **`dcm-azure-collector`** sur l’App Service créé par le Building Block (ex. `azrmfnndth-dcm`), via **container Docker** et le workflow GitHub Actions.

## Ce que dit Jocelyn

> *Infrastructure provisioning creates the runtime host, but collector package deployment must be completed by **your CI/CD process**.*

Méthode retenue équipe DCM : **container** (build Dockerfile → push **ECR DCM AWS** → App Service pull depuis ECR).

---

## Prérequis — à faire AVANT de lancer le workflow

### A. Phases onboarding terminées

| Phase | Statut requis | Pourquoi |
|-------|---------------|----------|
| **2 — Entra** | ✅ SP collector créé | Secrets `dcm-entra-*` dans le KV |
| **5.1 — Infra BB** | ✅ App Service + KV `-dcm` existent | Cible du deploy |
| **3b — Secrets** | ✅ 4 secrets `dcm-*` dans le KV BB | Runtime collector au démarrage |

Sans 5.1 + 3b, le deploy peut réussir mais l’App Service crashera au runtime.

### B. Fichier cible LZ dans le repo

Ajouter (ou vérifier) l’entrée dans :

`dataint-dcm-app/.github/azure-collector-deploy-targets.json`

Copier le template : `.github/azure-collector-deploy-targets.json.example`

Exemple clé : `novadatahub-m` → subscription, RG, webapp, KV URL, `source_lz_id`, etc.

Merger sur la branche utilisée par GitHub Actions (`develop`).

### C. Secrets GitHub (environment `dev`)

| Secret | Valeur |
|--------|--------|
| `AZURE_BUILDER_CLIENT_ID` | App ID du SP **Builder de la LZ cible** (voir § D.1) |
| `AZURE_BUILDER_CLIENT_SECRET` | Secret du SP **Builder** (pas le collector LZ) |
| `AZURE_BUILDER_TENANT_ID` | `329e91b0-e21f-48fb-a071-456717ecc28e` |
| `AWS_AZURE_COLLECTOR_ECR_ROLE_ARN` | Rôle IAM dans le compte ECR **dev** (`551656632516`) ou **prod** (`884068385310`) selon GitHub environment |

Le Builder est **propre à chaque LZ** — nom dans le tfvars satellite : `builder_sp_display_name`.

| LZ | Builder SP (`builder_sp_display_name`) |
|----|----------------------------------------|
| DataSquad | `AZR-IASP-LZ-DataSquad-Builder` |
| novadatahub | `AZR-IASP-LZ-novadatahub-Builder` |

> Si le secret est invalide → `AADSTS7000215 Invalid client secret`.

### D. Droits RBAC du Builder (obligatoire)

Le workflow se connecte avec le **Builder de la LZ déployée**, pas ton compte perso.  
Sans RBAC, Azure répond *« subscription doesn't exist »* — la sub existe, mais le SP ne la voit pas.

#### D.1 — Subscription LZ cliente

| Élément | Exemple novadatahub |
|---------|---------------------|
| Subscription | `sub-iasp-lz-novadatahub` |
| ID | `77180ab7-ad22-4e7e-aa0b-e2f909e6d0fa` |
| Builder SP | `AZR-IASP-LZ-novadatahub-Builder` |
| Rôle requis | **Contributor** sur cette subscription |

```bash
# Remplacer BUILDER_CLIENT_ID par l'appId de AZR-IASP-LZ-{lzName}-Builder
az login
az account set --subscription 77180ab7-ad22-4e7e-aa0b-e2f909e6d0fa

az role assignment create \
  --assignee "<BUILDER_CLIENT_ID>" \
  --role "Contributor" \
  --scope "/subscriptions/77180ab7-ad22-4e7e-aa0b-e2f909e6d0fa"
```

Vérification :

```bash
az role assignment list \
  --assignee "<BUILDER_CLIENT_ID>" \
  --scope "/subscriptions/77180ab7-ad22-4e7e-aa0b-e2f909e6d0fa" \
  -o table
```

#### D.2 — ECR central DCM (push + pull image)

> **Pas d’ACR Azure** — pas de registry dans la LZ cliente. Image dans l’ECR DCM (AWS), même registry que `dcm-aws-collector`.

| Élément | Valeur |
|---------|--------|
| Compte AWS | **dev** `551656632516` (awss-wl-dcm) · **prod** `884068385310` (awsp-dcm) |
| Registry | Résolu par `github_environment` dans le workflow |
| Repo | `AZURE_COLLECTOR_ECR_REPOSITORY` (défaut dev: `awsd-dcm-azure-collector`) |
| Auth CI | `AWS_AZURE_COLLECTOR_ECR_ROLE_ARN` (OIDC GitHub → IAM) |

Le workflow build + push l’image, puis configure l’App Service avec user registry `AWS` + token ECR.

### E. Infra réseau (hors CI)

**Prérequis à demander à l’équipe infra LZ avant deploy** — détail complet : [04-network-egress.md](./04-network-egress.md)

| Prérequis | Détail |
|-----------|--------|
| VNet integration | App Service intégrée au subnet BB (ex. `/28`) |
| `vnetImagePullEnabled` | Configuré par le workflow |
| Egress HTTPS runtime | Entra + Azure Management + Apigee |
| Egress HTTPS deploy | ECR central DCM (AWS) + S3 layers |

**Flux HTTPS (443) sortants depuis le subnet intégration App Service :**

| # | Destination | Usage |
|---|-------------|-------|
| 1 | `login.microsoftonline.com` | Auth Entra ID — **bloquant si fermé** |
| 2 | `management.azure.com` | APIs Azure (collectors) |
| 3 | `dev.apixnp.alzp.tgscloud.net` | Ingestion Apigee (env dev/m) |
| 4 | `551656632516.dkr.ecr…` (dev) ou `884068385310.dkr.ecr…` (prod) | Pull image Docker ECR central |
| 5 | `api.ecr.eu-central-1.amazonaws.com` | Token ECR |
| 6 | `prod-eu-central-1-starport-layer-bucket.s3.eu-central-1.amazonaws.com` | Layers Docker ECR |

Variante Apigee prod : `*.apixnp.alzp.tgscloud.net`. Mécanisme : NAT Gateway, Azure Firewall FQDN, ou proxy corporate.

Sans egress ECR : l’App Service ne pull pas l’image. Sans Entra/Apigee : collector bloqué au démarrage.

### F. Check rapide avant Run workflow

Test comme GitHub Actions (attendre 2–5 min après RBAC) :

```bash
az login --service-principal \
  -u "<BUILDER_CLIENT_ID>" \
  -p "<AZURE_BUILDER_CLIENT_SECRET>" \
  --tenant "329e91b0-e21f-48fb-a071-456717ecc28e"

az account list -o table
# doit contenir 77180ab7-... (LZ)

az account set --subscription 77180ab7-ad22-4e7e-aa0b-e2f909e6d0fa
az webapp show -g azrmrgndth04 -n azrmfnndth-dcm \
  --query "{name:name,state:state}" -o table
```

---

## Lancer le workflow

**Fichier :** `dataint-dcm-app/.github/workflows/dcm-azure-collector-deploy-lz.yml`

**Actions →** `dcm-azure-collector - Deploy to App Service (client LZs)` → **Run workflow**

| Input | Valeur novadatahub |
|-------|-------------------|
| `deploy_target` | `novadatahub-m` |
| `github_environment` | `dev` |

C’est tout. Le reste est dans le JSON + constantes workflow (container, ECR `dcm-azure-collector`).

![GitHub workflow](./assets/06-github-deploy-lz-workflow.png)

### Ce que fait le workflow

1. Charge la cible depuis `azure-collector-deploy-targets.json`
2. Build image Docker → push ECR DCM (`dcm-azure-collector:<sha>` + `:latest`)
3. Récupère un token ECR pour l’App Service
4. Vérifie que le Builder voit la subscription LZ
5. Configure App Service (`DCM_*`, `vnetImagePullEnabled`)
6. `az webapp config container set` (image ECR + user `AWS`) + restart

---

## Validation Phase 5.2 terminée

```bash
az account set --subscription 77180ab7-ad22-4e7e-aa0b-e2f909e6d0fa
az webapp show -g azrmrgndth04 -n azrmfnndth-dcm \
  --query "{name:name,state:state,image:siteConfig.linuxFxVersion}" -o table
az webapp log tail -g azrmrgndth04 -n azrmfnndth-dcm
```

Attendu dans les logs :

- Config chargée depuis Key Vault
- Cycle de collecte démarré
- Pas d’erreur auth en boucle

![Log stream](./assets/07-app-service-logs.png)

---

## Pièges connus

| Symptôme | Cause | Action |
|----------|-------|--------|
| `subscription doesn't exist` | Builder sans RBAC sur sub LZ | § D.1 — Contributor sur sub cliente |
| ECR push 403 | Rôle IAM CI insuffisant | Vérifier `AWS_COLLECTOR_AWS_ROLE_ARN` |
| App Service ne pull pas l’image | Egress ECR bloqué ou token expiré | § E — firewall + re-run workflow (~12h token) |
| `Invalid client secret` | Mauvais secret GitHub | Secret du **Builder**, pas collector |
| Compte perso ne peut pas deploy | Normal — pas `publishxml` | Utiliser le workflow CI, pas `az webapp deploy` local |

---

## Ne pas confondre

| Workflow | Cible |
|----------|-------|
| `dcm-azure-collector.yml` | ECR DCM — build/push image |
| `dcm-azure-collector-deploy-lz.yml` | App Service **LZ cliente** (DataSquad, novadatahub, …) — **Phase 5.2** |

Handoff détaillé : `BA-Data-Connect-Monitoring-infra/DCM-client-LZ-onboarding-handoff.md`
