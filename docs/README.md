# DCM — Index de la Documentation

Ce dossier contient **tous les documents de référence** du projet Data Connect Monitoring :
décisions d'architecture, modèles de données, guides d'implémentation, gestion de projet.

> **Le code source se trouve dans `/packages/`**
> **La feuille de route et le modèle de données actifs se trouvent dans `/specs/roadmap.md` et `/docs/02-data-model/`**

---

## Navigation rapide

| Dossier | Contenu | Lire en premier si… |
|---|---|---|
| [`01-architecture/`](./01-architecture/) | Documents d'architecture validés (DA, BBs, flux réseau) | Tu rejoins l'équipe ou tu veux comprendre la vision globale |
| [`02-data-model/`](./02-data-model/) | Modèle de données actif Unity Catalog / SQL Warehouse | Tu travailles sur le backend, le pipeline Databricks ou les tables DCM |
| [`03-implementation/`](./03-implementation/) | Guides techniques (OTel, alternatives ingestion, plan infra AWS, [prévision de consommation](./03-implementation/forecast-explique.md)) | Tu implémentes ou déploies un composant |
| [`04-cicd/`](./04-cicd/) | Pipelines CI/CD GitHub Actions | Tu déploies ou tu debug un workflow |
| [`05-mounir-ai/`](./05-mounir-ai/) | Agent Mounir (assistant IA DCM) | Tu travailles sur le chat Genie |
| [`06-auth/`](./06-auth/) | Authentification Entra ID + autorisation RBAC DCM | Tu configures MSAL, JWT, rôles ou l'interface admin |
| [`07-lz-onboarding/`](./07-lz-onboarding/) | **Onboarding LZ cliente** — archi collector, push/pull ECR, checklist nouvelle LZ | Tu ajoutes une LZ dans DCM ou tu déploies le collector Azure |
| [`_superseded/`](./_superseded/) | Versions intermédiaires dépassées (Multi-cloud v1, ère Event Hub) | Ne pas utiliser — archivé pour traçabilité |

---

## Documents à lire absolument

### 1. Document d'Architecture (DA) — validé Design Authority 19 Fév 2026
**[`01-architecture/DA-data-connect-monitoring.md`](./01-architecture/DA-data-connect-monitoring.md)**

C'est la **décision officielle** sur l'architecture retenue. Scénario 2 (agents distribués par LZ)
validé. Contient le contexte métier, les contraintes, les alternatives étudiées, et la
justification du choix final.

### 2. Architecture finale DCM
**[`01-architecture/ARCHITECTURE-DCM-FINALE.md`](./01-architecture/ARCHITECTURE-DCM-FINALE.md)**

Description technique complète de l'architecture cible : zones de déploiement, composants,
flux de données, sécurité.

### 3. Justification des Building Blocs
**[`01-architecture/Building-Blocks-Architecture-Justification.md`](./01-architecture/Building-Blocks-Architecture-Justification.md)**
**[`01-architecture/Justification-Building-Blocs-Architecture.md`](./01-architecture/Justification-Building-Blocs-Architecture.md)** (version FR)

Justifie les choix de Building Blocs INOX@Scale retenus pour chaque composant déployable.

### 4. Modèle de données et connexion Warehouse
**[`02-data-model/README.md`](./02-data-model/README.md)**  
**[`MIGRATION-LAKEBASE-TO-WAREHOUSE.md`](./MIGRATION-LAKEBASE-TO-WAREHOUSE.md)**

C'est la référence actuelle : le backend n'utilise plus de couche base de données PostgreSQL/Lakebase. Il se connecte directement à Databricks SQL Warehouse via Unity Catalog et consomme les tables `curated_*`, `gold_*` et `dcm_*`.

### 5. Authentification et permissions DCM
**[`06-auth/README.md`](./06-auth/README.md)**  
**[`06-auth/permissions-management.md`](./06-auth/permissions-management.md)**

Entra ID authentifie via deux App Registrations (SPA frontend + API backend). Le module `app/auth/` du backend charge ensuite le rôle et le périmètre Landing Zone depuis `dcm_app_users` et `dcm_user_lz_access`.

### 6. Onboarding LZ cliente — collector Azure
**[`07-lz-onboarding/README.md`](./07-lz-onboarding/README.md)**

Schéma archi validé : App Service dans la LZ, image Docker sur **ECR central AWS** (`551656632516`), push via `dcm-azure-collector.yml`, pull via `deploy-lz.yml`. Checklist complète pour ajouter une nouvelle LZ.

---

## Chronologie des versions

```
POC Azure (C# .NET)          → dans /_old-poc/
  ↓ 2025
Multi-cloud v1 (Event Hub)   → dans _superseded/Multi-cloud/
  ↓ fin 2025
Multi-cloud v2 (Apigee/SQS)  → dans _superseded/Multi-Cloud v2/
  ↓ DA 19 Fév 2026
DCM Cible (architecture actuelle) → 01-architecture/ + 02-data-model/ + /packages/
```
