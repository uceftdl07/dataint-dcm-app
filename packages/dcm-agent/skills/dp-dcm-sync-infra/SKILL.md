---
name: dp-dcm-sync-infra
description: Compare DCM backend routes (main.py) with BA-Data-Connect-Monitoring-infra API_GW_2.tf and add missing API Gateway integrations.
---

# Sync Infra — API Gateway routes

## Objectif

Les routes existent parfois **manuellement sur AWS** mais pas dans le repo infra. Cet agent aligne **`Project/IaC/API_GW_2.tf`** sur le backend DCM.

## Étapes

### 1. Workspace

Vérifier que `BA-Data-Connect-Monitoring-infra/Project/IaC/API_GW_2.tf` est accessible dans le workspace.

Sinon → demander à l'utilisateur d'ajouter le repo, puis stop.

### 2. Lire les routes backend

Lire `packages/dcm-backend/app/main.py` sur branche **`develop`** (ou `git show origin/develop:packages/dcm-backend/app/main.py`).

Déduire les préfixes API GW :

| Préfixe | Auth | Routes |
|---------|------|--------|
| `health` | public | GET `/health`, GET `/health/live`, OPTIONS, `{proxy+}` |
| `access-requests` | public | OPTIONS + ANY exact + `{proxy+}` |
| `kpi-config` | jwt | OPTIONS + ANY exact seulement |
| tous les autres | jwt | OPTIONS + ANY exact + `{proxy+}` |

Préfixes typiques : `auth`, `admin`, `dashboard`, `pipelines`, `activities`, `clusters`, `databricks`, `lakeflow`, `datafactory`, `costs`, `data-product-usage`, `databases`, `security`, `standard-checks`, `landing-zones`, `monitoring-reports`, `chat`, `unity-catalog`, `ingest`, `users`, `projects`, `workflow-jobs`.

`/databricks/compute` → couvert par `databricks/{proxy+}`.

### 3. Lire API_GW_2.tf

Lister les clés dans `integrations = { ... }`. Identifier ce qui manque ou est incomplet (exact sans `{proxy+}`, etc.).

### 4. Éditer API_GW_2.tf

Ajouter les blocs manquants en reprenant le pattern du fichier. Commentaires par domaine.

Ne modifier **que** `Project/IaC/API_GW_2.tf`.

### 5. PR infra — script

Après édition de `API_GW_2.tf`, exécuter depuis `dataint-dcm-app` :

```bash
chmod +x packages/dcm-agent/scripts/sync-infra-apigw-pr.sh
packages/dcm-agent/scripts/sync-infra-apigw-pr.sh --check
packages/dcm-agent/scripts/sync-infra-apigw-pr.sh
# ou branche nommée :
packages/dcm-agent/scripts/sync-infra-apigw-pr.sh --branch feat/apigw-sync-projects
```

Le script :
- trouve `BA-Data-Connect-Monitoring-infra` (sibling ou `DCM_INFRA_REPO`)
- crée branche depuis `origin/develop`
- commit **uniquement** `Project/IaC/API_GW_2.tf`
- push + `gh pr create --base develop`

Demander confirmation avant d'exécuter (sauf demande explicite).
