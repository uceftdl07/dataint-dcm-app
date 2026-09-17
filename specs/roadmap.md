# DCM - Roadmap Applicatif

> Document de référence pour l'implémentation de la solution **Data Connect Monitoring**.
> Périmètre : code applicatif uniquement — l'infrastructure AWS/Azure est gérée par une équipe dédiée.
> Auteur : Yahia ZERDOUMI (Lead Dev / Architecte Solution)
> Dernière mise à jour : 2026-03-27

---

## 1. Décisions Techniques Clés

| Décision | Choix | Justification |
|---|---|---|
| **Langage Agents** | Python (remplace .NET) | Uniformisation stack, ecosystème data Python plus riche |
| **Langage Backend API** | Python (FastAPI) | Cohérence avec agents, performance async, OpenAPI natif |
| **Langage Lambda** | Python | Standard AWS Lambda Python runtime |
| **Langage Pipeline Databricks** | Python / PySpark | Natif Databricks |
| **Base de données** | Databricks Lakebase PostgreSQL | Couche PostgreSQL-compatible → pas de changement de driver (psycopg2/asyncpg) |
| **Frontend** | React 18 + TypeScript (conservé) | Base POC réutilisable, adaptation mineure |
| **Auth** | Microsoft Entra ID (OAuth2/OIDC) | Unified IdP Azure + AWS, même App Registration |

---

## 2. Vue d'ensemble des Composants Applicatifs

```
┌──────────────────────────────────────────────────────────────────────┐
│  ZONE AZURE LZ (par souscription monitorée)                         │
│  ┌──────────────────────────────────────────────┐                   │
│  │  [A] Azure Collector Agent (Python)          │                   │
│  │  App Service WebJob / Container              │                   │
│  │  - Collecte : ADF, Databricks, Monitor,      │                   │
│  │    Cost, Security Center, Databases          │                   │
│  │  - Auth : Managed Identity → Key Vault       │                   │
│  │  - Envoi : JWT → Apigee                      │                   │
│  └──────────────────────────────────────────────┘                   │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  ZONE AWS LZ (par compte AWS monitoré)                              │
│  ┌──────────────────────────────────────────────┐                   │
│  │  [B] AWS Collector Agent (Python)            │                   │
│  │  ECS Fargate Task                            │                   │
│  │  - Collecte : Glue, EMR, RDS, Cost Explorer, │                   │
│  │    Redshift, CloudWatch                      │                   │
│  │  - Auth : IAM Role → Secrets Manager         │                   │
│  │  - Envoi : JWT → Apigee                      │                   │
│  └──────────────────────────────────────────────┘                   │
└──────────────────────────────────────────────────────────────────────┘

                          │ HTTPS + JWT (via Apigee)
                          ▼

┌──────────────────────────────────────────────────────────────────────┐
│  DCM CORE (AWS Account awss-wl-dcm)                                 │
│                                                                      │
│  [C] Lambda Ingestion API (Python)                                  │
│      Réception payload → validation → SQS                           │
│                     │                                                │
│                     ▼                                                │
│  [D] Databricks Pipeline (PySpark)                                  │
│      SQS consumer → transformation → Lakebase PostgreSQL            │
│      + Analytics ML (anomalies, tendances)                          │
│                     │                                                │
│                     ▼                                                │
│  [E] DCM Backend API (Python FastAPI)                               │
│      ECS Fargate → connecté Lakebase via psycopg2                   │
│      REST API → JWT validation Entra ID                             │
│                     │                                                │
│                     ▼                                                │
│  [F] Frontend React (TypeScript)                                    │
│      S3 + CloudFront → OIDC Entra ID → API Gateway                 │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Réutilisabilité depuis le POC

| Composant POC | Réutilisable | Action |
|---|---|---|
| `AzureDataFactoryService.cs` | ✅ Logique métier | Portage Python → `collectors/azure/datafactory.py` |
| `AzureDatabricksService.cs` | ✅ Logique métier | Portage Python → `collectors/azure/databricks.py` |
| `AzureCostManagementService.cs` | ✅ Logique métier | Portage Python → `collectors/azure/cost_management.py` |
| `AzureDatabaseService.cs` | ✅ Logique métier | Portage Python → `collectors/azure/databases.py` |
| `DataCollectionService.cs` | ⚠️ Architecture change | Remplacé par scheduler (EventBridge/App Service timer) |
| **Frontend React** | ✅ Base complète | Adapter URL API, config auth OIDC |
| **Modèles de données** | ✅ Schémas | Réécrire en Pydantic models Python |
| **Redis Cache** | ❌ Supprimé | Lakebase + Databricks remplacent |
| **PostgreSQL local** | ❌ Remplacé | Lakebase PostgreSQL (même protocole) |

---

## 4. Phases d'Implémentation

### Phase 1 — Fondations & Librairies Communes
**Durée estimée** : 1-2 sprints
**Dépendances** : Aucune (peut démarrer immédiatement)
**Livrable** : Package `dcm-commons` Python partagé par tous les composants

#### 1.1 Modèle de données unifié (Pydantic)
- Schéma `MetricPayload` standard (ce que chaque agent envoie)
- Schémas par domaine : `PipelineMetric`, `ClusterMetric`, `CostMetric`, `DatabaseMetric`, `SecurityAlert`
- Versioning du payload (champ `schema_version`)

#### 1.2 Librairie d'authentification Entra ID
- Module `dcm_auth` : acquisition token OAuth2 `client_credentials`
- Support Azure Managed Identity + Secrets Manager AWS
- Refresh token automatique
- Librairie : `msal` Python

#### 1.3 Base Collector Framework
- Classe abstraite `BaseCollector`
- Interface : `collect() -> list[MetricPayload]`
- Gestion erreurs, retry, logging structuré
- Configuration via variables d'environnement

#### 1.4 Client Apigee
- Module `apigee_client` : envoi batch de payloads vers Apigee
- JWT injection, retry avec backoff exponentiel
- Gestion timeout et erreurs réseau

#### 1.5 Logging & Observabilité
- Format log structuré JSON (compatible CloudWatch + Azure Log Analytics)
- Corrélation par `collection_run_id`
- Métriques de collecte (nb métriques collectées, erreurs, durée)

---

### Phase 2 — Agent Collecteur Azure (Python)
**Durée estimée** : 2-3 sprints
**Dépendances** : Phase 1
**Livrable** : Container Python déployable en App Service WebJob
**Réutilise** : Logique collecte du POC C# (portage)

#### 2.1 Structure du projet
```
azure-collector/
├── collectors/
│   ├── base.py                  # BaseCollector (depuis Phase 1)
│   ├── datafactory.py           # Azure Data Factory
│   ├── databricks.py            # Azure Databricks
│   ├── cost_management.py       # Azure Cost Management
│   ├── databases.py             # Azure SQL, PostgreSQL, MySQL, Cosmos
│   └── security_center.py      # Azure Security Center / Defender
├── config.py                    # Configuration + Key Vault
├── scheduler.py                 # Timer trigger principal
├── main.py                      # Entrypoint
├── Dockerfile
└── requirements.txt
```

#### 2.2 Collecteurs Azure à implémenter
| Collecteur | APIs Azure | Métriques clés |
|---|---|---|
| `DataFactoryCollector` | ADF Management API | Pipeline runs, statuts, durées, erreurs |
| `DatabricksCollector` | Databricks REST API 2.0 | Clusters, jobs, runs, coûts, SCIM users |
| `CostManagementCollector` | Cost Management Query API | Coûts par service, budgets, tendances |
| `DatabaseCollector` | Azure Monitor + Resource Manager | SQL/PostgreSQL/MySQL/Cosmos métriques |
| `SecurityCenterCollector` | Security Center API | Alertes, recommandations, score sécurité |

#### 2.3 Gestion des secrets (Key Vault)
- Managed Identity → Key Vault → Client ID/Secret Entra ID
- Rotation de secrets transparente
- Fallback environnement variables (dev local)

#### 2.4 Scheduling
- Déclenchement via App Service WebJob timer (cron expression)
- Fréquence configurable par collecteur

#### 2.5 Containerisation & déploiement
- `Dockerfile` multi-stage Python
- `docker-compose` pour tests locaux
- CI/CD pipeline (GitHub Actions)

---

### Phase 3 — Agent Collecteur AWS (Python)
**Durée estimée** : 2-3 sprints
**Dépendances** : Phase 1
**Livrable** : Container Python déployable en ECS Fargate Task

#### 3.1 Structure du projet
```
aws-collector/
├── collectors/
│   ├── base.py                  # BaseCollector (depuis Phase 1)
│   ├── glue.py                  # AWS Glue
│   ├── emr.py                   # Amazon EMR
│   ├── rds.py                   # Amazon RDS / Aurora
│   ├── cost_explorer.py         # AWS Cost Explorer
│   ├── redshift.py              # Amazon Redshift
│   └── cloudwatch.py            # Amazon CloudWatch
├── config.py                    # Configuration + Secrets Manager
├── main.py                      # Entrypoint (triggered by EventBridge)
├── Dockerfile
└── requirements.txt
```

#### 3.2 Collecteurs AWS à implémenter
| Collecteur | SDK boto3 | Métriques clés |
|---|---|---|
| `GlueCollector` | `boto3.client('glue')` | Job runs, crawler status, durées, erreurs |
| `EMRCollector` | `boto3.client('emr')` | Cluster status, steps execution, coûts |
| `RDSCollector` | `boto3.client('rds')` + CloudWatch | DB state, CPU, connections, storage |
| `CostExplorerCollector` | `boto3.client('ce')` | Coûts par service, account, region |
| `RedshiftCollector` | `boto3.client('redshift')` | Cluster health, workload, queries |
| `CloudWatchCollector` | `boto3.client('cloudwatch')` | Custom metrics, log insights |

#### 3.3 Gestion des secrets (Secrets Manager)
- IAM Role → Secrets Manager → Client ID/Secret Entra ID
- VPC Endpoint (pas d'internet pour accéder aux secrets)

#### 3.4 Scheduling
- Déclenchement par EventBridge Scheduler (`CRON_1`)
- Container s'exécute, collecte, envoie, et se termine

---

### Phase 4 — Lambda Ingestion API (Python)
**Durée estimée** : 1 sprint
**Dépendances** : Phase 1 (modèles), Infrastructure Lambda déployée
**Livrable** : Fonction Lambda Python validant et routant les payloads

#### 4.1 Responsabilités
- Réception du payload depuis Apigee (via VPC Lattice)
- Validation du schéma `MetricPayload` (Pydantic)
- Enrichissement : timestamp d'ingestion, source LZ id
- Publication dans SQS

#### 4.2 Structure
```
lambda-ingestion/
├── handler.py          # Lambda entrypoint
├── validator.py        # Validation Pydantic
├── sqs_publisher.py    # Publication SQS
├── models.py           # MetricPayload models
└── requirements.txt
```

#### 4.3 Gestion d'erreurs
- Payload invalide → réponse 400 + log
- Erreur SQS → retry Lambda natif
- Dead Letter Queue pour payloads non traitables

---

### Phase 5 — Pipeline Databricks (PySpark)
**Durée estimée** : 2-3 sprints
**Dépendances** : Phase 4 (SQS), Infrastructure Databricks déployée
**Livrable** : Jobs Databricks consommant SQS et écrivant dans Lakebase

#### 5.1 Architecture pipeline
```
SQS Queue
    │
    ▼
[Job 1] Ingestor Stream         ← Spark Structured Streaming ou batch
    │   - Consomme SQS
    │   - Parse + valide payloads
    │   - Écrit table RAW (Delta)
    │
    ▼
[Job 2] Transformer             ← Batch scheduled (toutes les X min)
    │   - Normalise par domaine
    │   - Enrichit (tags, metadata)
    │   - Écrit tables CURATED (Delta)
    │
    ▼
[Job 3] Aggregator              ← Batch scheduled (horaire)
    │   - Calcule KPIs agrégés
    │   - Détection anomalies (statistiques simples Phase 1, ML Phase 3)
    │   - Écrit tables SERVING → Lakebase PostgreSQL
    │
    ▼
Lakebase PostgreSQL
(lu par DCM Backend API via psycopg2)
```

#### 5.2 Schéma Lakebase (tables SERVING)
| Table | Description |
|---|---|
| `pipeline_metrics` | Métriques ADF / Glue / EMR par run |
| `cluster_metrics` | Métriques clusters Databricks / EMR |
| `cost_metrics` | Coûts par service, cloud, période |
| `database_metrics` | Performance et santé des bases de données |
| `security_alerts` | Alertes Security Center / GuardDuty |
| `collection_runs` | Audit des collectes (source, statut, nb métriques) |

#### 5.3 Unity Catalog
- Namespace : `dcm.monitoring.*`
- Policies d'accès : Backend API = read-only, Admins Databricks = read-write
- Data lineage automatique

---

### Phase 6 — DCM Core Backend API (Python FastAPI)
**Durée estimée** : 2-3 sprints
**Dépendances** : Phase 5 (Lakebase prêt), Infrastructure ECS déployée
**Livrable** : API REST Python déployée sur ECS Fargate

#### 6.1 Stack technique
- **Framework** : FastAPI (async, OpenAPI auto-généré)
- **DB driver** : `asyncpg` (PostgreSQL async) → se connecte au Lakebase comme un PostgreSQL standard
- **Auth** : `python-jose` + validation JWT Entra ID
- **Container** : Python 3.12, image Docker

#### 6.2 Structure du projet
```
dcm-backend/
├── api/
│   ├── routes/
│   │   ├── dashboard.py         # Vue d'ensemble globale
│   │   ├── pipelines.py         # ADF + Glue + EMR
│   │   ├── clusters.py          # Databricks + EMR
│   │   ├── costs.py             # FinOps Azure + AWS
│   │   ├── databases.py         # Métriques bases de données
│   │   ├── security.py          # Alertes sécurité
│   │   └── health.py            # Health check
│   ├── middleware/
│   │   ├── auth.py              # JWT validation Entra ID
│   │   └── logging.py           # Logging structuré
│   └── main.py
├── db/
│   ├── connection.py            # Pool asyncpg → Lakebase
│   ├── queries/                 # SQL queries par domaine
│   └── models.py                # Pydantic response models
├── config.py                    # Settings (Secrets Manager)
├── Dockerfile
└── requirements.txt
```

#### 6.3 Endpoints REST (alignés avec le frontend existant)

| Méthode | Endpoint | Description |
|---|---|---|
| GET | `/api/v1/dashboard/overview` | Vue globale (coûts, pipelines, alertes) |
| GET | `/api/v1/pipelines` | Liste pipelines (ADF + Glue) avec statuts |
| GET | `/api/v1/pipelines/{id}/runs` | Historique runs d'un pipeline |
| GET | `/api/v1/clusters` | Clusters Databricks + EMR |
| GET | `/api/v1/costs/summary` | Résumé coûts multi-cloud |
| GET | `/api/v1/costs/by-service` | Coûts par service |
| GET | `/api/v1/databases` | Métriques bases de données |
| GET | `/api/v1/security/alerts` | Alertes sécurité |
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1/collection/runs` | Audit collectes agents |

#### 6.4 Connexion Lakebase
```python
# Pas de changement de paradigme - Lakebase = PostgreSQL standard
# Connection string : postgresql://user:pass@lakebase-host:5432/dcm_db
import asyncpg
pool = await asyncpg.create_pool(dsn=settings.LAKEBASE_DSN)
```

---

### Phase 7 — Adaptation Frontend React
**Durée estimée** : 1-2 sprints
**Dépendances** : Phase 6 (API endpoints stabilisés)
**Livrable** : Frontend adapté, déployé sur S3/CloudFront

#### 7.1 Adaptations nécessaires
- `apiClient.ts` : Mettre à jour la base URL → API Gateway AWS
- `authConfig.ts` : Conserver App Registration Entra ID, adapter redirect URI
- Adapter les types TypeScript aux nouvelles réponses API (Python FastAPI → OpenAPI)
- **Nouveau** : Section AWS dans les modules (Glue, EMR, RDS, Cost Explorer)
- **Nouveau** : Vue multi-cloud (Azure vs AWS côte à côte)
- Build deployment → S3 + invalidation CloudFront

#### 7.2 Nouveaux modules UI à créer
| Module | Données |
|---|---|
| `AWSPipelines.tsx` | Glue Jobs, EMR Steps |
| `AWSCosts.tsx` | Cost Explorer par service/compte |
| `MultiCloudDashboard.tsx` | Vue consolidée Azure + AWS |
| `CollectionStatus.tsx` | Statut des agents collecteurs |

---

### Phase 8 — Intégration End-to-End & Tests
**Durée estimée** : 1-2 sprints
**Dépendances** : Toutes phases précédentes
**Livrable** : Suite de tests complète, validation flux C0-C8

#### 8.1 Tests par composant
| Composant | Type tests |
|---|---|
| `dcm-commons` | Unit tests Pytest |
| `azure-collector` | Unit tests + mock Azure SDK |
| `aws-collector` | Unit tests + mock boto3 (moto) |
| `lambda-ingestion` | Unit tests + test event Lambda |
| `databricks-pipeline` | Unit tests PySpark (pyspark en local) |
| `dcm-backend` | Unit tests + integration tests (testcontainers PostgreSQL) |
| `frontend` | Unit tests Vitest + E2E Playwright |

#### 8.2 Tests d'intégration E2E
- Flux C0→C5 : Agent → Apigee → Lambda → SQS → Databricks → Lakebase
- Flux U1→U8 : Browser → CloudFront → API Gateway → Backend → Lakebase
- Tests de charge : 100 agents simultanés, 10k métriques/min

---

## 5. Dépendances entre Phases

```
Phase 1: Fondations
    │
    ├──────────────────────────────────┐
    ▼                                  ▼
Phase 2: Azure Collector          Phase 3: AWS Collector
    │                                  │
    └──────────────┬───────────────────┘
                   ▼
              Phase 4: Lambda Ingestion
                   │
                   ▼
              Phase 5: Databricks Pipeline
                   │
                   ▼
              Phase 6: Backend API
                   │
                   ▼
              Phase 7: Frontend (peut démarrer en parallèle de Phase 5+6)
                   │
                   ▼
              Phase 8: Tests E2E
```

**Phases parallélisables** :
- Phase 2 + Phase 3 (agents Azure et AWS indépendants)
- Phase 7 peut démarrer dès que les endpoints Phase 6 sont spécifiés (contrat API)

---

## 6. Organisation des dépôts

| Dépôt | Contenu |
|---|---|
| `dcm-commons` | Package Python partagé (modèles, auth, base collector) |
| `dcm-azure-collector` | Agent collecteur Azure (Python) |
| `dcm-aws-collector` | Agent collecteur AWS (Python) |
| `dcm-lambda-ingestion` | Fonction Lambda ingestion (Python) |
| `dcm-databricks-pipeline` | Jobs PySpark Databricks |
| `dcm-backend` | API FastAPI backend (Python) |
| `dcm-frontend` | Application React TypeScript (issu du POC) |

---

## 7. Standards techniques transversaux

### Python
- Version : **3.12+**
- Packaging : `pyproject.toml` (Poetry ou uv)
- Linting : `ruff` + `mypy` (typage strict)
- Tests : `pytest` + `pytest-asyncio`
- Format : `black`

### Containerisation
- Base image : `python:3.12-slim`
- Multi-stage builds (build + runtime)
- Non-root user dans le container
- Healthcheck obligatoire

### Sécurité
- Aucun secret hardcodé → Key Vault / Secrets Manager uniquement
- Dépendances auditées : `pip audit` dans CI
- SAST : Bandit (Python security scanner)
- TLS 1.2+ obligatoire pour toutes les connexions sortantes

### Logs
- Format JSON structuré
- Champs obligatoires : `timestamp`, `level`, `component`, `collection_run_id`, `message`
- Compatible CloudWatch Insights + Azure Log Analytics

---

## 8. État d'avancement

| Phase | Statut | Notes |
|---|---|---|
| Phase 0 - Squelette solution | ✅ Terminé (2026-03-18) | 79 fichiers — tous les composants scaffoldés |
| Phase 1 - Fondations (dcm-commons) | ✅ Terminé (2026-03-18) | Modèles Pydantic, auth Entra ID, BaseCollector, ApigeeClient, tests |
| Phase 2 - Azure Collector | ✅ Terminé (2026-03-19) | 5 collecteurs + 3 nouveaux (activity_run, users SCIM, StandardCheck Policy) |
| Phase 3 - AWS Collector | ✅ Terminé (2026-03-19) | 5 collecteurs + 3 nouveaux (Glue steps, IAM users, Config StandardCheck) |
| Phase 4 - Lambda Ingestion | ✅ Terminé (2026-03-19) | Handler, validator Pydantic, SQSPublisher, 19 tests |
| Phase 5 - Databricks Pipeline | ✅ Terminé (2026-03-26) | 3 jobs PySpark, 10 tables SERVING (incl. compute_metrics, standard_checks, dim_landing_zone), DDL complet |
| Phase 6 - Backend API | ✅ Terminé (2026-03-26) | 12 routes FastAPI incl. /activities, /users, /standard-checks, /standard-checks/score, /landing-zones/details |
| Phase 7 - Frontend | ✅ Terminé (2026-03-26) | 9 pages React incl. Standard Checks (LZ selector + ba_name), Users, drilldown 2 niveaux Pipelines→Runs→Activités |
| Sprint 7 - Renommage Cluster→Compute / Compliance→StandardCheck | ✅ Terminé (2026-04-16) | Renommage cohérent sur tous les composants : modèles, collecteurs, routes API, frontend |
| Phase 8 - Tests E2E | 🔲 À démarrer | Après déploiement infra AWS/Databricks |

### Domaines collectés (au 2026-04-16)

| Domaine | Azure | AWS | Tables SERVING |
|---|---|---|---|
| Pipelines | ADF pipeline_runs | Glue jobs, EMR steps | `pipeline_metrics` |
| Compute | Databricks clusters | EMR clusters | `compute_metrics` |
| Coûts | Cost Management | Cost Explorer | `cost_metrics` |
| Databases | SQL/PG/MySQL/Cosmos + Monitor | RDS + CloudWatch | `database_metrics` |
| Sécurité | Security Center / Defender | GuardDuty | `security_alerts` |
| Activity runs | ADF activity details | Glue job steps | `activity_runs` |
| Users | Databricks SCIM v2 | AWS IAM | `user_metrics` |
| **Standard Checks** | **Azure Policy (PolicyInsights)** | **AWS Config Rules** | **`standard_checks`** |
| **Landing Zones** | **dim_landing_zone (SCD Type 2)** | **dim_landing_zone** | **`dim_landing_zone`** |

### Prochaines actions (Phase 8)
1. Déploiement infra AWS : Lambda, SQS, ECS Fargate, ECR (équipe dédiée)
2. Déploiement Databricks Lakebase : exécution `lakebase_ddl.sql` + création jobs Databricks
3. Déploiement agents Azure : App Service WebJob par LZ
4. Déploiement agents AWS : ECS Fargate Task par compte AWS
5. Tests E2E flux complet : agent → Apigee → Lambda → SQS → Databricks → Lakebase → Backend → Frontend

---

*Dernière mise à jour : 2026-04-16 — Sprint 7 (renommages Cluster→Compute, Compliance→StandardCheck) terminé.*
