# Tableau de bord DCM – Navigation & Actions

## 1. Architecture
- [Architecture technique globale](dcm-docs/01-architecture/Architecture-Technique-Globale.md)
- [Architecture logique](dcm-docs/01-architecture/ARCHITECTURE-LOGIQUE-DCM.md)
- [Architecture finale](dcm-docs/01-architecture/ARCHITECTURE-DCM-FINALE.md)
- [Justification des choix](dcm-docs/01-architecture/Justification-Building-Blocs-Architecture.md)
- [Network Flow Matrix](dcm-docs/01-architecture/Network-Flow-Matrix.md)

## 2. Données & Modèles
- [Data models](dcm/solution/data-models.md)
- [Data model docs](dcm-docs/02-data-model/README.md)
- [Schemas pipeline](packages/dcm-databricks-pipeline/schemas/)

## 3. Code & Collectors
- [AWS Collector](packages/dcm-aws-collector/README.md)
- [Azure Collector](packages/dcm-azure-collector/README.md)
- [Backend API](packages/dcm-backend/README.md)
- [Commons](packages/dcm-commons/README.md)
- [Lambda ingestion](packages/dcm-lambda-ingestion/README.md)
- [Databricks pipeline](packages/dcm-databricks-pipeline/README.md)

## 4. Implémentation & Intégration
- [OTel Integration](dcm-docs/03-implementation/OTel_Integration.md)
- [OTel Integration EN](dcm-docs/03-implementation/OTel_Integration%20EN.md)
- [Analyse alternatives ingestion](dcm-docs/03-implementation/ANALYSE-ALTERNATIVES-INGESTION.md)
- [Plan infra AWS](dcm-docs/03-implementation/plan-infra-aws-bask.md)

## 5. Roadmap & Suivi
- [Roadmap applicatif](dcm/roadmap-applicatif.md)
- [Executive summary](dcm-docs/00-Executive-Summary-DCM.md)
- [État des lieux & handover (29/04/2026)](DCM-2026-04-29-etat-des-lieux-handover%201.md)

## 6. Best Practices & Guides
- [Backend best practices](claude_docs/backend_best_practices.md)

## 7. Tests & Fixturés
- [Tests backend](packages/dcm-backend/tests/)
- [Tests collectors](packages/dcm-aws-collector/tests/)
- [Fixtures](packages/dcm-commons/fixtures/)

## 8. Décisions techniques
- Voir [CHANGELOG.md](CHANGELOG.md)
- Log des décisions dans ce fichier, section dédiée

## 9. Actions & Priorités
### Actions immédiates (priorité décroissante)
1. **Stabiliser la CI/CD** : corriger les jobs, valider tous les tests (bloquant)
2. **Finaliser la migration monorepo** : harmoniser imports, conventions, doc (hautement prioritaire)
3. **Documenter l’archi cible** : compléter les schémas, justifier les choix (hautement prioritaire)
4. **Automatiser la génération des docs** : scripts, intégration CI (prioritaire)
5. **Refactoriser les collectors** : factoriser le code commun, simplifier les configs (important)
6. **Mettre à jour les specs data** : aligner les modèles, valider avec PO (important)

### Actions futures (avec dépendances infra)
1. **Déploiement cloud automatisé** (dépend infra AWS/Azure)
2. **Monitoring Databricks avancé** (dépend accès admin Databricks)
3. **Intégration SSO entreprise** (dépend IT sécurité)
4. **Alerting custom multi-cloud** (dépend infra cible)
5. **Dashboard UI unifié** (dépend frontend stable)
6. **Tests de charge bout-en-bout** (dépend env. staging)
7. **Automatisation onboarding nouveaux clients** (dépend scripts internes)

## Log des décisions techniques
- **2026-04** : Adoption du monorepo, hatchling, centralisation des docs (voir [CHANGELOG.md](CHANGELOG.md))
- **2026-04** : Correction des tests collectors pour compatibilité monorepo
- **2026-03** : Choix FastAPI pour toutes les nouvelles APIs
- **2026-02** : Factorisation des modèles dans dcm-commons

## Navigation rapide (où trouver quoi ?)
- Architecture technique → 01-architecture/
- Modèles de données → 02-data-model/
- Collectors AWS/Azure → packages/dcm-aws-collector/, packages/dcm-azure-collector/
- Backend/API → packages/dcm-backend/
- Tests → tests/ de chaque package
- Décisions techniques → CHANGELOG.md
- Roadmap → dcm/roadmap-applicatif.md
- Best practices → claude_docs/
- Specs → dcm-docs/03-implementation/
- Scripts/fixtures → packages/dcm-commons/fixtures/

---

> Ce tableau de bord est à jour au 29/04/2026. À adapter à chaque évolution majeure.

---

## 2. Architecture de la solution

```
┌─────────────────────────────────────────────────────────────────┐
│  LANDING ZONE AZURE (une par souscription monitorée)           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Agent Azure (Python)  — App Service WebJob JOB_2      │   │
│  │  Collecte : ADF, Databricks SCIM, Cost Mgmt,           │   │
│  │             Security Center, Azure Monitor, Policy     │   │
│  │  Auth : Managed Identity → Key Vault → App Registration│   │
│  └───────────────────────────┬─────────────────────────────┘   │
└──────────────────────────────│──────────────────────────────────┘
                               │ HTTPS + JWT (Apigee)
┌─────────────────────────────────────────────────────────────────┐
│  LANDING ZONE AWS (une par compte AWS monitoré)                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Agent AWS (Python)  — ECS Fargate Task CT_2_SLESS     │   │
│  │  Collecte : Glue, EMR, RDS, Cost Explorer,             │   │
│  │             IAM, Config Rules                          │   │
│  │  Auth : IAM Role → Secrets Manager → App Registration  │   │
│  └───────────────────────────┬─────────────────────────────┘   │
└──────────────────────────────│──────────────────────────────────┘
                               │ HTTPS + JWT (Apigee)
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  DCM CORE  (compte AWS awss-wl-dcm)                            │
│                                                                 │
│  [Lambda]  Réception → Validation Pydantic → SQS              │
│      ↓                                                          │
│  [Databricks]  SQS → RAW Delta → CURATED Delta → SERVING PG   │
│      ↓                                                          │
│  [FastAPI Backend]  Lakebase PostgreSQL → REST API             │
│      ↓                                                          │
│  [Frontend React]  S3/CloudFront → Dashboard multi-cloud      │
└─────────────────────────────────────────────────────────────────┘
```

**Cloisonnement multi-LZ** : chaque métrique transporte `cloud_provider` + `source_lz_id` +
`subscription_or_account_id`. Le core ne mélange jamais les données de deux LZ différentes.

---

## 3. Organisation du dépôt

```
data-connect-monitoring/
│
├── README.md                     ← ce fichier
│
├── dcm/                          ← CODE SOURCE ET DOCS ACTIFS
│   ├── roadmap-applicatif.md     ← feuille de route 8 phases + statut
│   ├── data-models.md            ← modèle de données complet (source de vérité)
│   └── solution/                 ← code source des 7 composants
│       ├── dcm-commons/
│       ├── dcm-azure-collector/
│       ├── dcm-aws-collector/
│       ├── dcm-lambda-ingestion/
│       ├── dcm-databricks-pipeline/
│       ├── dcm-backend/
│       └── dcm-frontend/
│
├── dcm-docs/                     ← DOCUMENTATION DE RÉFÉRENCE
│   ├── README.md                 ← index de navigation
│   ├── 01-architecture/          ← DA validé, architecture finale, Building Blocs
│   ├── 02-data-model/            ← modèles de données historiques (Medallion)
│   ├── 03-implementation/        ← guides techniques (OTel, ingestion, infra AWS)
│   ├── 04-project-management/    ← périmètre, épics, user stories, Jira
│   ├── 05-reference/             ← présentations, diagrammes, images
│   └── _superseded/              ← versions intermédiaires archivées
│
└── _old-poc/                     ← ANCIEN POC C# .NET (ne plus modifier)
    ├── Backend/                   ← .NET AzureMonitoring.*
    ├── Frontend/                  ← React TS POC
    └── ...
```

---

## 4. Les 7 composants applicatifs

### `dcm-commons` — Bibliothèque Python partagée

Contrat de données entre tous les composants. Modèles Pydantic, authentification Entra ID,
classe abstraite `BaseCollector`, client Apigee avec retry.

**Règle fondamentale** : aucun composant ne dépend d'un autre composant que `dcm-commons`.
C'est la seule dépendance transversale autorisée dans toute l'architecture.

```
dcm_commons/models/     → MetricPayload (v1.1) + 8 domaines métier
dcm_commons/auth/       → EntraIDAuthClient (OAuth2 client_credentials)
dcm_commons/collector/  → BaseCollector (ABC) + retry exponentiel + logging structuré
dcm_commons/client/     → ApigeeClient (httpx async, retry 5xx/429/réseau)
```

### `dcm-azure-collector` — Agent collecteur Azure

Tourne en continu dans chaque LZ Azure (App Service WebJob).
Collecte toutes les 5 min et envoie vers Apigee.

**Collecteurs** : DataFactory · Databricks (clusters + SCIM) · CostManagement ·
SecurityCenter · Databases · ActivityRuns · StandardCheck (Azure Policy)

### `dcm-aws-collector` — Agent collecteur AWS

Exécution one-shot déclenchée par EventBridge (ECS Fargate Task).
S'exécute, collecte, envoie, se termine.

**Collecteurs** : Glue · EMR · RDS · CostExplorer · Redshift ·
GlueActivityRuns · IAMUsers · ConfigStandardCheck (AWS Config Rules)

### `dcm-lambda-ingestion` — Point d'entrée du core

Reçoit les payloads des agents (via Apigee → VPC Lattice), valide avec Pydantic,
publie dans SQS. Première ligne de défense contre les données malformées.

### `dcm-databricks-pipeline` — Pipeline de transformation (Medallion)

```
SQS → [Ingestor]     → Delta RAW       (body opaque, at-least-once)
          → [Transformer] → Delta CURATED  (normalisé par domaine)
                  → [Aggregator] → Lakebase SERVING  (9 tables PostgreSQL)
```

Tables SERVING : `pipeline_metrics` · `compute_metrics` · `cost_metrics` ·
`database_metrics` · `security_alerts` · `activity_runs` · `user_metrics` ·
`standard_checks` · `dim_landing_zone` · `collection_runs`

### `dcm-backend` — API REST FastAPI

Expose les données Lakebase via 12 routes REST. Auth JWT Entra ID. ECS Fargate.

Routes : `/pipelines` · `/clusters` · `/costs` · `/databases` · `/security` ·
`/activities` · `/users` · `/standard-checks` · `/standard-checks/score` ·
`/landing-zones/details` · `/dashboard/overview` · `/health`

### `dcm-frontend` — Interface React TypeScript

Dashboard multi-cloud. 9 pages avec filtres, pagination, et drill-down.
Auth MSAL.js + Entra ID (optionnelle via `VITE_ENABLE_AUTH`).

Pages : Vue d'ensemble · Pipelines (drill-down Runs → Activités) · Clusters ·
Coûts · Bases de données · Sécurité · Standard Checks · Utilisateurs · Statut collecte

---

## 5. Stratégie Building Bloc — agents déployables

### Le concept

Un **Building Bloc (BB)** dans la terminologie INOX@Scale est un artifact déployable autonome :
Dockerfile + `.env` + module Terraform/Bicep d'infrastructure. Une nouvelle LZ qui adhère à DCM
reçoit un BB, le configure avec ses propres secrets, et démarre la collecte.

Les agents (`dcm-azure-collector` et `dcm-aws-collector`) sont des **Building Blocs naturels** :
conçus pour être déployés dans autant de LZ que nécessaire, de façon entièrement indépendante.

### Périmètre de responsabilité de chaque agent

| Responsabilité | Qui gère |
|---|---|
| Secrets (App Registration, IAM Role) | L'agent dans sa LZ |
| Rotation des credentials | L'équipe LZ (pas le core DCM) |
| Périmètre de collecte | La LZ (1 agent = 1 souscription/compte) |
| Fréquence de collecte | Configuration locale de l'agent |
| Expiration de secret → alerte | L'agent logge `CRITICAL` + alerte locale |

Si un secret expire dans la LZ-A, seule la LZ-A arrête de collecter.
Les LZ-B, LZ-C et le core DCM continuent de fonctionner normalement.

### Onboarding d'une nouvelle LZ Azure

```
1. Déployer le BB dcm-azure-collector (App Service WebJob JOB_2)
2. Configurer .env :
     APIGEE_ENDPOINT=https://apigee.company.com/dcm/v1/ingest
     SOURCE_LZ_ID=azure-lz-prod-fr
     SUBSCRIPTION_OR_ACCOUNT_ID=fa5abbc4-02eb-416f-a75f-f8f6c5cc7d8a
     CLIENT_ID=<app-registration-client-id>
     CLIENT_SECRET=<secret-from-key-vault>
3. Assigner les rôles RBAC sur la souscription :
     - Monitoring Reader
     - Cost Management Reader
     - Data Factory Contributor (lecture)
4. L'agent démarre → les métriques arrivent dans le core DCM
```

### Cloisonnement au niveau du core

Chaque payload transporte ces deux champs propagés jusqu'aux tables SERVING :
- `source_lz_id` : identifiant logique de la LZ (ex: `azure-lz-prod-fr`)
- `subscription_or_account_id` : ID de souscription Azure ou compte AWS

Exemple de requête backend cloisonnée par LZ :
```sql
SELECT * FROM pipeline_metrics
WHERE source_lz_id = 'azure-lz-prod-fr'
  AND subscription_or_account_id = 'fa5abbc4-...'
ORDER BY start_time DESC;
```

---

## 6. Monorepo maintenant, multi-repo demain

### Pourquoi monorepo pendant la phase de build

Pendant la phase de développement actuel, un monorepo est la bonne décision :
- Un seul `git clone` pour travailler sur tous les composants
- Les changements cross-composants (ex: nouveau champ dans `MetricPayload`) se font en un PR
- Les tests d'intégration sont simples à exécuter localement
- Pas de gestion de versions inter-repos pendant le développement actif

### Comment le monorepo prépare la séparation future

Chaque composant est un **package Python autonome** avec son propre `pyproject.toml`.
La dépendance sur `dcm-commons` est déclarée explicitement via les sources `uv` :

```toml
# dcm-azure-collector/pyproject.toml
[project]
dependencies = ["dcm-commons>=1.1.0"]

[tool.uv.sources]
dcm-commons = { path = "../dcm-commons", editable = true }
# En production → registry privé AWS CodeArtifact
```

**Règle absolue respectée dans tout le code** : aucun import croisé entre composants
autres que `dcm-commons`. Si cette règle tient, la séparation future est :

```bash
# Extraire dcm-azure-collector en repo indépendant avec son historique git complet
git filter-repo --path dcm/solution/dcm-azure-collector/
# → Aucune réécriture de code. Seul pyproject.toml change (path → registry)
```

### Cible multi-repo (déclencheur : premier onboarding LZ externe)

| Repo GitHub | Composants | Audience |
|---|---|---|
| `dcm-core` | lambda + pipeline + backend + frontend + commons | Équipe DCM centrale |
| `dcm-azure-agent` | dcm-azure-collector + Dockerfile + Bicep | Équipes LZ Azure |
| `dcm-aws-agent` | dcm-aws-collector + Dockerfile + CloudFormation | Équipes LZ AWS |

`dcm-commons` publié dans AWS CodeArtifact, référencé comme `dcm-commons>=1.x` dans les agents.

---

## 7. Tests E2E en local

> **A venir** : les fichiers `docker-compose.yml` et `Makefile` sont prévus mais pas encore créés.

L'objectif est de valider le flux complet depuis un laptop, sans infrastructure cloud :

```
Agent Azure/AWS → Lambda (HTTP local) → SQS (LocalStack) → Pipeline local → PostgreSQL → Backend → Frontend
```

Le composant central pour les tests locaux est `dcm-databricks-pipeline/dev/local_pipeline.py` :
un script Python qui simule le comportement du pipeline Medallion sans Spark ni Databricks.
Il lit SQS (LocalStack) et écrit directement en PostgreSQL, permettant de valider la chaîne
complète depuis un laptop.

```bash
# Cible : lancer tout le stack en une commande
docker-compose up
# → LocalStack (SQS), PostgreSQL (Lakebase), agents, lambda-api, pipeline local, backend, frontend
```

---

## 8. Documentation — où trouver quoi

| Je cherche… | Je regarde dans… |
|---|---|
| L'architecture validée (DA 19 Fév 2026) | [`dcm-docs/01-architecture/DA-data-connect-monitoring.md`](./dcm-docs/01-architecture/DA-data-connect-monitoring.md) |
| L'architecture finale détaillée | [`dcm-docs/01-architecture/ARCHITECTURE-DCM-FINALE.md`](./dcm-docs/01-architecture/ARCHITECTURE-DCM-FINALE.md) |
| La justification des Building Blocs | [`dcm-docs/01-architecture/Building-Blocks-Architecture-Justification.md`](./dcm-docs/01-architecture/Building-Blocks-Architecture-Justification.md) |
| Le modèle de données complet (9 tables) | [`dcm/data-models.md`](./dcm/data-models.md) |
| La feuille de route et l'avancement | [`dcm/roadmap-applicatif.md`](./dcm/roadmap-applicatif.md) |
| Les épics et user stories | [`dcm-docs/04-project-management/`](./dcm-docs/04-project-management/) |
| Le flux réseau (ports, protocoles) | [`dcm-docs/01-architecture/Network-Flow-Matrix.md`](./dcm-docs/01-architecture/Network-Flow-Matrix.md) |
| L'intégration OpenTelemetry | [`dcm-docs/03-implementation/OTel_Integration.md`](./dcm-docs/03-implementation/OTel_Integration.md) |
| Le plan infra AWS (Building Blocs BASK) | [`dcm-docs/03-implementation/plan-infra-aws-bask.md`](./dcm-docs/03-implementation/plan-infra-aws-bask.md) |
| Les présentations et diagrammes | [`dcm-docs/05-reference/`](./dcm-docs/05-reference/) |
| L'ancien POC C# .NET | [`_old-poc/`](./_old-poc/) — référence uniquement, ne plus modifier |

---

## 9. Démarrage rapide

### Pré-requis
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — gestionnaire de packages Python recommandé
- Node.js 20+ (pour le frontend)

### Installer et tester un composant

```bash
# Exemple avec dcm-commons
cd dcm/solution/dcm-commons
uv sync
uv run pytest

# Exemple avec dcm-azure-collector
cd dcm/solution/dcm-azure-collector
uv sync          # résout dcm-commons en local automatiquement
uv run pytest

# Exemple avec dcm-backend
cd dcm/solution/dcm-backend
uv sync
cp .env.example .env   # configurer LAKEBASE_DSN
uv run uvicorn app.main:app --reload --port 8080
```

### Lancer le frontend

```bash
cd dcm/solution/dcm-frontend
npm install
cp .env.example .env   # VITE_API_BASE_URL=http://localhost:8080, VITE_ENABLE_AUTH=false
npm run dev            # http://localhost:4000
```

---

## Statut d'avancement

| Composant | Code | Tests | Déploiement infra |
|---|---|---|---|
| dcm-commons | ✅ Complet | ✅ 30+ tests | ⏳ Registry CodeArtifact |
| dcm-azure-collector | ✅ Complet | ✅ Tests unitaires | ⏳ App Service WebJob JOB_2 |
| dcm-aws-collector | ✅ Complet | ✅ Tests unitaires | ⏳ ECS Fargate CT_2_SLESS |
| dcm-lambda-ingestion | ✅ Complet | ✅ 19 tests | ⏳ Lambda AWS |
| dcm-databricks-pipeline | ✅ Complet | ✅ 23 tests | ⏳ Jobs Databricks |
| dcm-backend | ✅ Complet | ✅ 66 tests | ⏳ ECS Fargate |
| dcm-frontend | ✅ Complet | — | ⏳ S3 + CloudFront |
| docker-compose E2E | 🔲 A créer | — | — |

Le code applicatif est complet. La prochaine étape est le déploiement de l'infrastructure
AWS/Databricks (équipe infra), suivi des tests E2E en conditions réelles.
=======
# Welcome to dataint-dcm-app! 🎉

Welcome to your new repository!  
This project has been automatically created for you through our CI/CD platform.

## 📚 Getting Started

To help you get started quickly, here are some useful resources:

### Documentation & Support
- **New to our platform?** Start with our [Welcome Board Link](https://digitalplatforms.totalenergies.com/documentation/platforms/cicd-platform/welcome-board-first-day-developper) - it contains everything you need for your first day as a developer
- **Need help with GitHub?** Check out our [Portal Documentation](https://digitalplatforms.totalenergies.com/documentation/platforms/cicd-platform/github/get-started-github) for comprehensive guides and best practices

## 📋 Repository Information

- **Created on:** 2026-03-31
- **Requested by:** AJ0411581@admin.hubtotal.net

## 🚀 Next Steps

1. Clone this repository to your local machine
2. Review the documentation links above
3. Start building something incredible independently with our self-services ([GitHub | Digital Platforms Portal](https://digitalplatforms.totalenergies.com/github#self-service)) and quality solutions ([Sonarqube | Digital Platforms Portal](https://digitalplatforms.totalenergies.com/cicd/sonarqube#self-service)).

---

*This README was automatically generated. Feel free to customize it for your project's specific needs.*
