# Guide utilisateur — Agent DCM Collector (`dp-dcm-lz-client`)

Guide rapide pour **onboarder une Landing Zone (LZ)** dans **Data Connect Monitoring (DCM)** à l’aide de l’agent IA `dp-dcm-lz-client`.

> **Public cible :** équipe LZ (Cloud Ops / Data) qui déploie le collector pour la première fois.  
> **Durée estimée :** 30–60 min (hors déploiement infra et consentement Entra admin).

> **Guide visuel interactif :** dans l’app DCM → **http://localhost:4000/guide/lz-onboarding** (bouton **Guide** en header → **LZ onboarding guide**).  
> Copie statique : `packages/dcm-agent/docs/onboarding-guide/index.html`

---

## 1. À quoi sert cet agent ?

L’agent orchestre l’onboarding d’une LZ dans DCM en **7 phases** :

| Phase | Ce que fait l’agent | Ce que vous faites |
|-------|---------------------|-------------------|
| 1 | Collecte les paramètres LZ + choix des collectors | Répondre aux questions |
| 1.5 | Vérifie la connexion Azure (`az login`) | Se connecter si session expirée |
| 1.6 | **Découverte d'état** — saute les phases déjà faites | — |
| 2 | Crée le SP collector (ou skip si existe) | — |
| 3 | Guide le stockage des secrets (KV accessible) | PIM + secrets — peut être fait **avant** l’infra |
| **5.1** | **Guide le déploiement infra BASK** | CI Plan + CD Apply satellite `DataintDCM/ClientInfra` |
| **3b** | Secrets dans le **KV créé par le BB** (`…-dcm`) | Copier les 4 secrets après apply |
| **5.2** | Guide deploy container via workflow CI | Prérequis Builder RBAC — voir `onboarding-guide/03-phase-5-2-deploy.md` |
| 4 | Applique les rôles RBAC / IAM (MI) | Après 5.1 — valider si politique LZ bloque |
| 6 | Teste l’ingestion Apigee | — |
| 7 | Génère la fiche d’onboarding | Relire / archiver |

L’agent **exécute les commandes lui-même** (MR Robot, `az`, etc.). Vous n’avez pas à copier-coller des scripts — sauf pour `az login` (navigateur obligatoire).

---

## 2. Prérequis (à installer une seule fois)

### Outils

| Outil | Vérification | Installation |
|-------|--------------|--------------|
| **GitHub CLI** | `gh --version` | `brew install gh` puis `gh auth login` |
| **APM** | `apm --version` | `curl -sSL https://aka.ms/apm-unix \| sh` |
| **Azure CLI** | `az --version` | `brew install azure-cli` |
| **jq** (recommandé) | `jq --version` | `brew install jq` |
| **Python 3** | `python3 --version` | Déjà sur macOS / Linux |

### Droits / accès

- Accès à la **subscription LZ** (ex. `sub-iasp-lz-novadatahub`)
- Droits pour appeler **MR Robot** (token Azure avec scope identity)
- Accès **Key Vault** de la LZ (depuis un poste ayant accès réseau au vault — souvent nécessaire si le KV est en private endpoint)
- Clé **Apigee** DEV ou PROD (fournie par l’équipe DCM — une clé partagée par environnement)

### Ce qui est déjà en place (ne pas redemander)

DCM Core est **déjà déployé** par l’équipe DCM :

- Back ingestion SP (ex. DEV Azure : `AZR-IASP-LZ-DataSquad-inj-d`)
- API Apigee ingestion
- Lambda + SQS

---

## 3. Installation du plugin DCM

Depuis un clone de **dataint-dcm-app** (branche `develop`) :

```bash
git clone git@github.com:TotalEnergiesCode/dataint-dcm-app.git
cd dataint-dcm-app
git checkout develop
chmod +x packages/dcm-agent/install.sh
./packages/dcm-agent/install.sh --global
```

Installation **dans le repo seulement** (sans `--global`) :

```bash
cd dataint-dcm-app
./packages/dcm-agent/install.sh
```

Le script ajoute l’agent `@dp-dcm-lz-client` et les 7 skills.

**Réinstaller après mise à jour :**

```bash
cd dataint-dcm-app
git pull origin develop
./packages/dcm-agent/install.sh --global
```

> Ne plus utiliser `apm install TotalEnergiesCode/dp-ai-tools/plugins/dcm` — remplacé par ce script.

Cela déploie :

- Agent : `.github/agents/dp-dcm-lz-client.agent.md` (ou `~/.github/agents/` en global)
- Skills : `.agents/skills/dp-dcm-*/` (ou `~/.agents/skills/` en global)

**Copilot :** recharger VS Code si `@dp-dcm-lz-client` n’apparaît pas.

---

## 4. Connexion Azure (avant d’invoquer l’agent)

Connexion **obligatoire** avec le scope MR Robot :

```bash
az logout
az login --tenant "329e91b0-e21f-48fb-a071-456717ecc28e" \
  --scope "https://api-aad.pf-identity.iasp.tgscloud.net/.default"
```

Puis sélectionnez la **subscription de votre LZ** (ex. `sub-iasp-lz-novadatahub`).

Vérification rapide :

```bash
az account show --query "{sub:name, id:id, user:user.name}" -o table
```

---

## 5. Comment invoquer l’agent

Dans le chat **GitHub Copilot**, tapez `@` → **`dp-dcm-lz-client`**.

### Message minimal (tout fourni — recommandé)

```
@dp-dcm-lz-client Azure : sub-iasp-lz-novadatahub, env=d, subscription_id=77180ab7-ad22-4e7e-aa0b-e2f909e6d0fa, maher.lezhari@totalenergies.com
```

### Message générique (l’agent posera les questions manquantes)

```
@dp-dcm-lz-client Onboarder une nouvelle LZ dans DCM
```

### Exemple AWS

```
@dp-dcm-lz-client AWS : awsd-wl-DSDataEng, env=d, account_id=123456789012, owner@totalenergies.com
```

---

## 6. Informations à préparer avant la session

### Azure (IAS)

| Paramètre | Exemple | Obligatoire |
|-----------|---------|-------------|
| Nom subscription LZ | `sub-iasp-lz-novadatahub` | Oui |
| Environnement collector | `d` (DEV) ou `p` (PROD) | Oui |
| Subscription ID | `77180ab7-ad22-4e7e-aa0b-e2f909e6d0fa` | Oui |
| Email contact LZ | `prenom.nom@totalenergies.com` | Oui |
| Nom Key Vault LZ | ex. `azrdkvndth-01` | Pour phase secrets |
| Clé Apigee (env) | fournie par DCM | Pour phase secrets |

> **Ne pas fournir** `lzName` ni `source_lz_id` — l’agent les déduit automatiquement.  
> Ex. `novadatahub` → `source_lz_id` = `azr-lz-novadatahub-dev`

### AWS (ALZP)

| Paramètre | Exemple |
|-----------|---------|
| LZ ID | `awsd-wl-DSDataEng` (DEV) |
| Environnement | `d` ou `p` |
| Account ID | 12 chiffres |
| Email contact | `@totalenergies.com` |

---

## 7. Question que l’agent vous posera — choix des collectors

L’agent affiche un **tableau multi-sélection**. Choisissez uniquement ce que vous voulez monitorer.

### Azure — package `dcm-azure-collector`

| Clé | Surveillance |
|-----|--------------|
| `datafactory` | Azure Data Factory — pipelines |
| `activity_runs` | ADF — activity runs |
| `databricks` | Databricks — clusters |
| `databricks_pipelines` | Databricks — jobs |
| `cost_management` | Coûts & budgets |
| `databases` | SQL, PostgreSQL, MySQL, Cosmos |
| `security_center` | Defender for Cloud (optionnel) |
| `users` | Utilisateurs Entra (optionnel) |
| `standard_checks` | Checks gouvernance (optionnel) |

**Conseil :** ne cochez que les services réellement déployés dans votre LZ — cela limite les permissions RBAC.

### AWS — package `dcm-aws-collector`

| Clé | Surveillance |
|-----|--------------|
| `glue` | Glue jobs & crawlers |
| `emr` | Clusters EMR |
| `rds` | RDS / Aurora |
| `cost_explorer` | Coûts |
| `redshift` | Redshift |

---

## 8. Déroulé type d’une session

```
Vous ──► @dp-dcm-lz-client + paramètres LZ
         │
         ▼
Agent ──► Tableau de confirmation (lzName, source_lz_id, collectors)
         │
         ▼
Agent ──► Preflight Azure (token MR Robot)
         │   └─ Si expiré : vous reconnectez az login, puis "Je suis connecté, continue"
         ▼
Agent ──► Phase 1.6 : vérifie ce qui existe déjà (SP, rôle Collector, secrets KV, App Service)
         │   └─ Affiche "Reprise à la phase N" — ne refait pas Phase 2 si déjà ✅
         ▼
Agent ──► Phase 2 : SP Entra (skip si déjà créé + rôle Collector OK)
         ▼
Agent ──► Phase 3 : secrets (optionnel tôt — ex. KV core pour test OAuth)
         ▼
Agent ──► Phase 5.1 : infra LZ via BASK + azr-iac-bb-dataint-dcm
         │   ├─ Satellite BA-{LZ}-Infrastructure / DataintDCM/ClientInfra
         │   ├─ CI Plan → merge → CD Apply
         │   └─ Modèle IaC : DataSquad-infra (exemple satellite — DataSquad = LZ cliente)
         ▼
Agent ──► Phase 3b : secrets dans KV BB (azr{env}kv{appcode}-dcm)
         ▼
Agent ──► Phase 5.2 : package dcm-azure-collector sur App Service BB
         ▼
Agent ──► Phase 4 : RBAC sur Managed Identity du collector
         │   └─ Bloqué si App Service pas encore déployé → retour 5.1
         ▼
Agent ──► Phase 6 : test POST /ingest
         ▼
Agent ──► Fiche onboarding docs/onboarding/lz-{lzName}-{env}.md
```

---

## 9. Ce que vous devez faire manuellement (checklist)

- [ ] `az login` avec le bon tenant + scope MR Robot
- [ ] Choisir les **collectors** dans le questionnaire
- [ ] **Consentement admin Entra** pour la permission `Collector` sur le back ingestion SP
- [ ] Stocker les **4 secrets** dans Key Vault **manuellement** (l’agent fournit les commandes) :
  - `dcm-entra-tenant-id`
  - `dcm-entra-client-id`
  - `dcm-entra-client-secret` (régénérer si perdu en Phase 2)
  - `dcm-apigee-api-key` (clé **partagée** pour tout l’env — voir section 10 bis)
- [ ] Confirmer à l’agent : **« J'ai stocké les 4 secrets — continuer »**
- [ ] Déployer l’**infra collector** via BASK (satellite `DataintDCM/ClientInfra` + module `azr-iac-bb-dataint-dcm`)
- [ ] Copier les **4 secrets** dans le **KV DCM** créé par le BB (`azr{env}kv{appcode}-dcm`)
- [ ] Déployer le **package** `dcm-azure-collector` sur l’App Service créé

---

## 10. Secrets Key Vault (référence)

| Secret | Contenu | Qui le fournit |
|--------|---------|----------------|
| `dcm-entra-tenant-id` | Tenant ID Entra (ex. `329e91b0-e21f-48fb-a071-456717ecc28e`) | **Agent** — valeur connue |
| `dcm-entra-client-id` | App ID du collector SP (ex. `c2e2404c-01af-4107-98bd-745bc53a9b01`) | **Agent** — Phase 1.6 / Phase 2 |
| `dcm-entra-client-secret` | Secret du collector | **Vous** — Phase 2 ou MR Robot (jamais dans le chat) |
| `dcm-apigee-api-key` | Clé Apigee partagée (même que secret GitHub `DCM_APIGEE_API_KEY`) | **Maintainer repo** / copie depuis vault existant |

> Le collector lit ces secrets via **Managed Identity** — jamais en clair dans les App Settings.

---

## 10 bis. Clé Apigee — FAQ

| Question | Réponse |
|----------|---------|
| Même clé pour tous les collecteurs ? | **Oui** — une clé par **environnement** (DEV / PROD), pas une clé par LZ |
| Où est la source ? | Secret GitHub `DCM_APIGEE_API_KEY` sur `dataint-dcm-app` (même que deploy `dcm-azure-collector`) |
| Où la mettre pour novadatahub ? | Dans le **KV DCM** `azrdkvndth-dcm` (créé par le BB) — pas le KV core seul |
| Pourquoi dans chaque vault LZ ? | Le collecteur lit ses credentials via MI depuis **son** vault au runtime — c’est une copie, pas une clé différente |

Si vous avez déjà la clé DEV : utilisez-la dans `az keyvault secret set` depuis votre poste — **jamais dans le chat**.

---

## 11. Variables d’environnement collector (Azure)

À configurer sur l’App Service après déploiement :

| Variable | Exemple |
|----------|---------|
| `DCM_KEY_VAULT_URL` | `https://azrdkvndth-dcm.vault.azure.net/` (KV créé par le BB) |
| `AZURE_SUBSCRIPTION_ID` | UUID subscription LZ |
| `DCM_SOURCE_LZ_ID` | `azr-lz-novadatahub-dev` |
| `DCM_APIGEE_BASE_URL` | URL ingestion DEV DCM |
| `DCM_ENABLED_COLLECTORS` | `datafactory,activity_runs,databricks,...` |
| `DCM_COLLECTION_INTERVAL` | `300` (optionnel) |

---

## 12. Problèmes fréquents

| Symptôme | Cause | Action |
|----------|-------|--------|
| `token_length=0` | Session Azure expirée | Relancer `az login` (section 4) |
| HTTP 409 sur assignation Collector | Consentement admin manquant | Demander à l’admin Entra |
| `ForbiddenByConnection` sur Key Vault | KV en private endpoint | Stocker les secrets manuellement depuis un poste avec accès réseau au KV |
| RBAC impossible | App Service pas déployé | Phase 5.1 — satellite BASK `DataintDCM/ClientInfra` |
| CI `subscription doesn't exist` | Builder sans droits sur sub LZ | **Contributor** sur sub LZ pour `AZR-IASP-LZ-{lzName}-Builder` — voir `03-phase-5-2-deploy.md` |
| ECR push 403 (CI) | Rôle IAM insuffisant | Vérifier `AWS_COLLECTOR_AWS_ROLE_ARN` sur env GitHub `dev` |
| Pas de clé Apigee | Secret DCM Core non copié | Contacter l’équipe DCM |

---

## 13. Handoffs vers d’autres agents

| Besoin | Agent / doc |
|--------|-------------|
| Scaffold satellite DCM dans `BA-{LZ}-Infrastructure` | `dp-azlz-devops-builder` + skill `dp-dcm-client-infra` |
| Modèle satellite IaC | [DataSquad-infra DataintDCM/ClientInfra](https://github.com/TotalEnergiesCode/DataSquad-infra/tree/main/Project/DataintDCM/ClientInfra) |
| Module Terraform Azure | [azr-iac-bb-dataint-dcm](https://github.com/TotalEnergiesCode/azr-iac-bb-dataint-dcm) |
| AWS (futur) | `aws-iac-bb-dataint-dcm` + `dgt-awslz-builder` |

Copilot : `@dp-azlz-devops-builder Déployer le collector DCM pour novadatahub (env=d)`.

---

## 14. Exemple complet — novadatahub (DEV)

**1. Prérequis**

```bash
gh auth login
./packages/dcm-agent/install.sh
az login --tenant "329e91b0-e21f-48fb-a071-456717ecc28e" \
  --scope "https://api-aad.pf-identity.iasp.tgscloud.net/.default"
# Choisir subscription [15] sub-iasp-lz-novadatahub
```

**2. Chat**

```
@dp-dcm-lz-client Azure : sub-iasp-lz-novadatahub, env=d, subscription_id=77180ab7-ad22-4e7e-aa0b-e2f909e6d0fa, maher.lezhari@totalenergies.com
```

**3. Réponses agent**

- Collectors : cocher ADF, Databricks, cost, databases (selon besoin)
- Si KV privé : confirmer le nom `azrdkvndth-01`, stocker les secrets manuellement, puis confirmer à l'agent
- Consentement Entra : oui, fait par l’admin

**4. Résultat attendu**

- SP : `AZR-IASP-LZ-novadatahub-dcm-collector`
- `DCM_ENABLED_COLLECTORS=datafactory,activity_runs,databricks,databricks_pipelines,cost_management,databases`
- Fiche : `docs/onboarding/lz-novadatahub-d.md`

---

## 15. Liens utiles

| Ressource | URL / chemin |
|-----------|--------------|
| Plugin DCM | `dataint-dcm-app/packages/dcm-agent/` |
| Agent | `packages/dcm-agent/agents/dp-dcm-lz-client.agent.md` |
| Infra DCM Core | `BA-Data-Connect-Monitoring-infra` |
| Package collector Azure | `dataint-dcm-app/packages/dcm-azure-collector` |
| MR Robot (Entra) | `plugins/global/skills/mr-robot/` |

---

*Dernière mise à jour : juin 2026 — agent `dp-dcm-lz-client` v7 phases.*
