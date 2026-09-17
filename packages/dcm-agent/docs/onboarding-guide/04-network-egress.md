# Prérequis réseau — ouverture flux firewall LZ

**À demander à l'équipe infra / réseau LZ avant Phase 5.1 ou 5.2** — sans ces flux, le collector ne démarre pas ou l'App Service ne pull pas l'image Docker.

## Contexte

| Élément | Valeur |
|---------|--------|
| Composant | App Service DCM — ex. `azrmfnndth-dcm` (BB DataintDCM) |
| Subscription | `sub-iasp-lz-{nom}` (ex. `sub-iasp-lz-novadatahub`) |
| Source | Subnet intégration VNet App Service — ex. `10.x.x.x/28` (subnet BB) |
| Protocole | HTTPS sortant (443) |
| Mécanisme | NAT Gateway, Azure Firewall (FQDN rules), ou route vers proxy corporate — selon archi LZ |

Le collector (`dcm-azure-collector`) :

1. s'authentifie via **Entra ID** ;
2. lit les ressources Azure via **management.azure.com** ;
3. envoie les métriques vers **Apigee** ;
4. pull son image depuis l'**ECR central DCM AWS** (pas d'ACR Azure).

Référence archi : registry central ECR DCM pour toutes les LZ Azure (Jocelyn GIBART — [installation.md](https://github.com/TotalEnergiesCode/azr-iac-bb-dataint-dcm/blob/main/installation.md)).

**Référence firewall IAS (même modèle DCM) :** issue DataSquad [#12496](https://github.com/TotalEnergiesCode/ias-firewall-rules/issues/12496) → PR [#12497](https://github.com/TotalEnergiesCode/ias-firewall-rules/pull/12497) mergée sur `settings/prod/datasquad.yml` (App Service `azrmfndsde-dcm`).

---

## Demande via GitHub `ias-firewall-rules` (recommandé)

Repo : [TotalEnergiesCode/ias-firewall-rules](https://github.com/TotalEnergiesCode/ias-firewall-rules)  
Template : **Open outbound flows** (`open-outbound-flows.yml`)

| Étape | Attendu |
|-------|---------|
| 1 | Créer issue `{lz_id} — Open outbound flows` avec bloc YAML ci-dessous |
| 2 | `github-actions` commente **YAML Parsing ✅** puis **Request Validation ✅** |
| 3 | PR auto `settings/prod/{lz_id}.yml` — label `create` (nouvelle LZ) ou `update` (fichier existant) |
| 4 | Merge PR → déploiement firewall IAS (~quelques jours selon équipe réseau) |

> Schéma repo : `protocol_port: [Https]` — **pas** `protocols` / `protocolType`. Voir [#12496](https://github.com/TotalEnergiesCode/ias-firewall-rules/issues/12496).

### YAML issue (novadatahub — copier dans le body)

```yaml
---
lz_id: novadatahub
network_rules: []
application_rules:
  - description: DCM collector Entra auth
    comment: Data Connect Monitoring - App Service azrmfnndth-dcm - Entra ID (SP collector + MI)
    target_fqdns:
      - login.microsoftonline.com
    protocol_port:
      - Https
  - description: DCM collector Azure Management APIs
    comment: Collectors ADF, Databricks, Cost Management, Security, databases
    target_fqdns:
      - management.azure.com
    protocol_port:
      - Https
  - description: DCM ingestion Apigee DEV
    comment: Metrics ingest to DCM Core - env mutualized/dev
    target_fqdns:
      - dev.apixnp.alzp.tgscloud.net
    protocol_port:
      - Https
  - description: DCM collector Docker pull ECR central
    comment: App Service pulls dcm-azure-collector from central DCM AWS ECR (551656632516)
    target_fqdns:
      - 551656632516.dkr.ecr.eu-central-1.amazonaws.com
    protocol_port:
      - Https
  - description: DCM collector ECR auth token
    comment: AWS ECR GetAuthorizationToken
    target_fqdns:
      - api.ecr.eu-central-1.amazonaws.com
    protocol_port:
      - Https
  - description: DCM collector ECR Docker layers S3
    comment: ECR Starport layer bucket
    target_fqdns:
      - prod-eu-central-1-starport-layer-bucket.s3.eu-central-1.amazonaws.com
    protocol_port:
      - Https
bundled_rules: []
```

Issue novadatahub DCM : [#12570](https://github.com/TotalEnergiesCode/ias-firewall-rules/issues/12570) — si pas de commentaire `github-actions`, éditer le body et remplacer `protocols` par `protocol_port` comme ci-dessus.

---

## Flux à autoriser (liste complète)

| # | Destination FQDN | Usage | Quand |
|---|------------------|-------|-------|
| 1 | `login.microsoftonline.com` | Auth Entra ID (SP collector + MI App Service) | Runtime — **bloquant si fermé** |
| 2 | `management.azure.com` | APIs Azure (ADF, Databricks, Cost, Security, etc.) | Runtime |
| 3 | `dev.apixnp.alzp.tgscloud.net` | Ingestion DCM via Apigee (env mutualized/dev) | Runtime |
| 4 | `551656632516.dkr.ecr.eu-central-1.amazonaws.com` | Pull image Docker collector depuis ECR central | Deploy container |
| 5 | `api.ecr.eu-central-1.amazonaws.com` | Auth token ECR (`GetAuthorizationToken`) | Deploy container |
| 6 | `prod-eu-central-1-starport-layer-bucket.s3.eu-central-1.amazonaws.com` | Layers Docker ECR | Deploy container |

**Variante Apigee (prod / autres envs) :** `*.apixnp.alzp.tgscloud.net` si règle FQDN wildcard préférée.

> Le host ECR exact peut aussi venir de `AWS_COLLECTOR_ECR_REGISTRY` (variable GitHub). Compte AWS central DCM : `551656632516` (eu-central-1).

---

## Par cas d'usage

### A — Runtime collector (obligatoire pour que le service tourne)

- `login.microsoftonline.com`
- `management.azure.com`
- `dev.apixnp.alzp.tgscloud.net` (ou `*.apixnp.alzp.tgscloud.net` selon env)

Sans ces flux : erreurs auth Entra, échec collecte Azure, ingest Apigee impossible.

### B — Pull image depuis ECR AWS (obligatoire pour déploiement container)

- `551656632516.dkr.ecr.eu-central-1.amazonaws.com`
- `api.ecr.eu-central-1.amazonaws.com`
- `prod-eu-central-1-starport-layer-bucket.s3.eu-central-1.amazonaws.com`

Sans ces flux : App Service ne pull pas l'image — Phase 5.2 bloquée.

Les flux **A** restent requis en parallèle de **B** (token Entra + restart App Service).

---

## Modèle réutilisable (toutes LZ clientes)

Même Building Block (`azr{env}fn{appcode}-dcm` + subnet BB) pour chaque LZ. Seuls changent :

- CIDR subnet source (validé par réseau LZ) ;
- URL Apigee selon env DCM (`dev`, `mutualized`, `prod`).

---

## Demande à l'équipe infra (template mail)

**Objet :** Ouverture firewall LZ — collector DCM (`azr{env}fn{appcode}-dcm`)

Bonjour,

Pour finaliser le déploiement du collector DCM sur la LZ **{nom_lz}**, merci d'autoriser les flux HTTPS (443) sortants depuis le **subnet d'intégration VNet** de l'App Service `azr{env}fn{appcode}-dcm`.

**Source :** subnet intégration App Service DCM — `{CIDR}`  
**Mécanisme :** NAT Gateway / Azure Firewall FQDN / proxy corporate — selon votre archi

| Destination | Usage |
|-------------|-------|
| `login.microsoftonline.com` | Auth Entra ID |
| `management.azure.com` | APIs Azure (collectors) |
| `dev.apixnp.alzp.tgscloud.net` | Ingestion Apigee |
| `551656632516.dkr.ecr.eu-central-1.amazonaws.com` | Pull image ECR central DCM |
| `api.ecr.eu-central-1.amazonaws.com` | Token ECR |
| `prod-eu-central-1-starport-layer-bucket.s3.eu-central-1.amazonaws.com` | Layers Docker ECR |

Merci de confirmer le CIDR exact, le mécanisme retenu et la date de mise en place.

Cordialement,

---

## Vérification après ouverture

| Test | Commande / action | Attendu |
|------|-------------------|---------|
| Pull image | Re-run workflow `dcm-azure-collector-deploy-lz.yml` | App Service démarre avec image ECR |
| Auth Entra | Logs App Service | Pas d'erreur `login.microsoftonline.com` / AAD |
| Collecte Azure | Logs App Service | Appels `management.azure.com` OK |
| Ingest | Phase 6 — test Apigee | HTTP 202 |

---

## Pièges

| Symptôme | Cause probable | Action |
|----------|----------------|--------|
| App Service ne pull pas l'image | Egress ECR/S3 bloqué | Ouvrir flux § B + re-run workflow (~12h token ECR) |
| Erreur auth au démarrage | `login.microsoftonline.com` bloqué | Ouvrir flux #1 en priorité |
| Collecte partielle | `management.azure.com` bloqué | Ouvrir flux #2 |
| Ingest 403/timeout | Apigee bloqué | Ouvrir flux #3 ou wildcard `*.apixnp.*` |

Voir aussi : [03-phase-5-2-deploy.md § E](./03-phase-5-2-deploy.md#e-infra-réseau-hors-ci)
