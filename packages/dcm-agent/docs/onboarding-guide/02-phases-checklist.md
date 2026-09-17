# Phases d’onboarding — checklist

Ordre recommandé (agent + guide Jocelyn).

| # | Phase | Qui | Action |
|---|-------|-----|--------|
| 1 | Paramètres + collectors | **Toi** | Répondre aux questions agent |
| 2 | Entra SP collector | **Agent** | MR Robot — consentement admin si besoin |
| 3 | Secrets (optionnel tôt) | **Toi + Agent** | KV accessible pour test OAuth |
| 5.1 | Infra BB | **DevOps LZ** | BASK apply satellite `DataintDCM/ClientInfra` |
| 3b | Secrets dans KV BB | **Toi** | 4 secrets `dcm-*` dans `azr{env}kv{appcode}-dcm` |
| 5.2 | Code collector | **DevOps DCM** | Deploy `dcm-azure-collector` sur App Service (voir prérequis §03) |
| 4 | RBAC MI | **Agent / DevOps** | Vérifier rôles subscription |
| 6 | Validation ingest | **Agent** | Test Apigee HTTP 202 |
| 7 | Fiche onboarding | **Agent** | Document récap |

## Légende rôles

- **Toi** — réponses, secrets manuels, confirmations
- **Agent** — commandes `az`, MR Robot, tests
- **DevOps** — BASK apply, deploy Phase 5.2, **droits Builder SP** (Contributor sub LZ + IAM ECR)

## Prérequis réseau (avant 5.1 / 5.2)

À demander à **l’équipe infra / réseau LZ** — egress HTTPS (443) depuis le subnet intégration App Service DCM.

| # | Destination | Usage |
|---|-------------|-------|
| 1 | `login.microsoftonline.com` | Auth Entra — **bloquant** |
| 2 | `management.azure.com` | APIs Azure (collectors) |
| 3 | `dev.apixnp.alzp.tgscloud.net` | Apigee ingestion |
| 4 | `551656632516.dkr.ecr.eu-central-1.amazonaws.com` | Pull image ECR central |
| 5 | `api.ecr.eu-central-1.amazonaws.com` | Token ECR |
| 6 | `prod-eu-central-1-starport-layer-bucket.s3.eu-central-1.amazonaws.com` | Layers Docker ECR |

Mécanisme : NAT Gateway, Azure Firewall FQDN, ou proxy corporate. Template mail infra : [04-network-egress.md](./04-network-egress.md).

## Avant Phase 5.2 (checklist rapide)

- [ ] Phases 2, 5.1, 3b terminées
- [ ] **Flux firewall ouverts** (6 destinations ci-dessus)
- [ ] Entrée dans `.github/azure-collector-deploy-targets.json`
- [ ] Secrets GitHub `AZURE_BUILDER_*` sur environment `dev`
- [ ] **Contributor** Builder (`AZR-IASP-LZ-{lzName}-Builder`) sur subscription LZ
- [ ] **AWS_ROLE_ARN** / `AWS_COLLECTOR_AWS_ROLE_ARN` pour push ECR
- [ ] VNet integration App Service OK

Détail deploy : [03-phase-5-2-deploy.md](./03-phase-5-2-deploy.md) · Réseau : [04-network-egress.md](./04-network-egress.md)

## Secrets Key Vault (4)

| Secret | Source |
|--------|--------|
| `dcm-entra-tenant-id` | Agent |
| `dcm-entra-client-id` | Agent (Phase 2) |
| `dcm-entra-client-secret` | Phase 2 — jamais dans le chat |
| `dcm-apigee-api-key` | Équipe DCM — **une clé par env**, partagée entre LZ |

Header Apigee : **`x-apif-apikey`** (pas `x-api-key`).

## Ce que Terraform ne fait pas

Phase **5.1** crée l’App Service **vide**.  
Phase **5.2** installe le **programme Python** — obligatoire une fois par LZ.
