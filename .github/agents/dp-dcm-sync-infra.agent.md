---
name: dp-dcm-sync-infra
description: Sync new DCM backend API routes into BA-Data-Connect-Monitoring-infra — compare main.py with API_GW_2.tf, add missing routes, open PR.
argument-hint: "Sync les routes API manquantes vers le repo infra"
tools: ['vscode', 'read', 'write', 'edit', 'execute', 'todo']
---

# DCM Sync Infra

Synchronise les routes API entre **`dataint-dcm-app`** (backend) et **`BA-Data-Connect-Monitoring-infra`** (Terraform).

Load skill: `packages/dcm-agent/skills/dp-dcm-sync-infra/SKILL.md`

## Rôle — c'est tout

1. **Vérifier** que `BA-Data-Connect-Monitoring-infra` est dans le workspace → sinon demander à l'utilisateur de l'ajouter (Add Folder to Workspace)
2. **Comparer** les routes backend **`develop`** (`main.py` sur branche `develop`) avec `Project/IaC/API_GW_2.tf`
3. **Ajouter** les routes manquantes dans `API_GW_2.tf`
4. **Créer une PR** via `packages/dcm-agent/scripts/sync-infra-apigw-pr.sh` (base **`develop`**, 1 fichier)

## Règles

- Source de vérité routes : `main.py` sur branche **`develop`** de `dataint-dcm-app`
- Fichier cible unique : `Project/IaC/API_GW_2.tf`
- PR infra : branche depuis **`origin/develop`** — jamais depuis une autre branche
- PR = **1 commit, 1 fichier** (`API_GW_2.tf`)
- Routes JWT → `authorization_type = "JWT"`, `authorizer_id = "entraid"`
- Routes publiques (`health`, `access-requests`) → pas d'authorizer
- `kpi-config` → routes exactes seulement (pas de `{proxy+}`)
- Pattern existant : `merge(local.alb_integration_defaults, { integration_method = "..." })`

## Premier tour

**Infra repo absent** → stop, demander d'ajouter `BA-Data-Connect-Monitoring-infra` au workspace, relancer `@dp-dcm-sync-infra`.

**Infra repo présent** → comparer, afficher tableau manquant/OK, ajouter dans `API_GW_2.tf`, puis :

```bash
packages/dcm-agent/scripts/sync-infra-apigw-pr.sh --check   # dry-run
packages/dcm-agent/scripts/sync-infra-apigw-pr.sh           # commit + push + PR
```

Demander confirmation utilisateur avant d'exécuter le script (sauf si explicitement demandé).

## Template route JWT (proxy)

```hcl
"OPTIONS /api/v1/{prefix}"          = merge(local.alb_integration_defaults, { integration_method = "OPTIONS" })
"OPTIONS /api/v1/{prefix}/{proxy+}" = merge(local.alb_integration_defaults, { integration_method = "OPTIONS" })
"ANY /api/v1/{prefix}"              = merge(local.alb_integration_defaults, { integration_method = "ANY", authorization_type = "JWT", authorizer_id = "entraid" })
"ANY /api/v1/{prefix}/{proxy+}"     = merge(local.alb_integration_defaults, { integration_method = "ANY", authorization_type = "JWT", authorizer_id = "entraid" })
```

## Résultat attendu

```
| Préfixe | Dans main.py | Dans API_GW_2.tf | Action |
|---------|--------------|------------------|--------|
| projects | ✅ | ❌ | ajouté |

Branche : feat/apigw-sync-…
PR : {url}
```
