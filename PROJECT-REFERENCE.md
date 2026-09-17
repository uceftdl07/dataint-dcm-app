# DCM — Référentiel Chef de Projet

> **À qui s'adresse ce document** : Chef de projet pilotant les développements DCM avec GitHub Copilot.
> Il centralise tous les liens vers la documentation existante, l'état d'avancement et les actions en cours.
> Ce document est le point d'entrée unique — tout le reste est accessible via les liens ci-dessous.
>
> Dernière mise à jour : 2026-04-29

---

## Comment utiliser ce document avec GitHub Copilot

GitHub Copilot lit automatiquement `.github/copilot-instructions.md` pour comprendre le contexte du projet. Pour tirer le meilleur parti de Copilot :

- **Ouvrir un fichier de spec avant de coder** : Copilot utilise le fichier ouvert comme contexte principal
- **Référencer les types existants** : les modèles Pydantic de `dcm-commons` sont la source de vérité — demandez à Copilot de les utiliser plutôt que d'en créer de nouveaux
- **Nommer les tâches précisément** : ex. "Créer un test pytest pour `DataFactoryCollector._collect_metrics()` en mockant le Azure SDK, en suivant le pattern de `test_governance.py`"
- **Pointer vers un fichier existant comme référence** : "En suivant le pattern de `packages/dcm-backend/tests/test_governance.py`..."

---

## Vue d'ensemble en 30 secondes

DCM collecte des métriques des services data Azure + AWS, les centralise via Databricks et les expose via une API + frontend React.

**Code : 100% terminé et sur GitHub.** Ce qui reste : CI/CD, tests complémentaires, docker-compose local, et après l'infra → tests E2E.

**7 composants Python/React, 66 tests backend, 10 tables Lakebase, 14 routes API, 12 pages frontend.**

---

## 1. Documentation Architecture

> Ces documents décrivent les décisions de conception validées en Design Authority. À lire avant toute décision structurante.

| Document | Description |
|---|---|
| [`docs/01-architecture/ARCHITECTURE-DCM-FINALE.md`](docs/01-architecture/ARCHITECTURE-DCM-FINALE.md) | Architecture finale validée DA — référence absolue |
| [`docs/01-architecture/ARCHITECTURE-LOGIQUE-DCM.md`](docs/01-architecture/ARCHITECTURE-LOGIQUE-DCM.md) | Vue logique des composants et leurs interactions |
| [`docs/01-architecture/Architecture-Technique-Globale.md`](docs/01-architecture/Architecture-Technique-Globale.md) | Architecture technique globale (infra + applicatif) |
| [`docs/01-architecture/Functional-Architecture.md`](docs/01-architecture/Functional-Architecture.md) | Architecture fonctionnelle — flux métier |
| [`docs/01-architecture/Building-Blocks-Architecture-Justification.md`](docs/01-architecture/Building-Blocks-Architecture-Justification.md) | Justification des choix building blocks |
| [`docs/01-architecture/Justification-Building-Blocs-Architecture.md`](docs/01-architecture/Justification-Building-Blocs-Architecture.md) | Analyse comparative scénarios architecture |
| [`docs/01-architecture/DA-data-connect-monitoring.md`](docs/01-architecture/DA-data-connect-monitoring.md) | Dossier Design Authority complet |
| [`docs/01-architecture/Network-Flow-Matrix.md`](docs/01-architecture/Network-Flow-Matrix.md) | Matrice flux réseau (ports, protocoles, endpoints) |
| [`docs/01-architecture/Global-Technical-Architecture.md`](docs/01-architecture/Global-Technical-Architecture.md) | Vue technique complète (EN) |
| [`docs/01-architecture/Logical-Architecture.md`](docs/01-architecture/Logical-Architecture.md) | Architecture logique (EN) |

---

## 2. Modèle de données

> Source de vérité pour le schéma des données. À consulter avant toute modification de table ou de modèle Pydantic.

| Document | Description |
|---|---|
| [`docs/02-data-model/data-models.md`](docs/02-data-model/data-models.md) | **Source de vérité** — schéma complet Delta + Lakebase PostgreSQL, toutes les tables, tous les champs |
| [`docs/02-data-model/README.md`](docs/02-data-model/README.md) | Index documentation modèle de données |
| [`packages/dcm-databricks-pipeline/schemas/lakebase_ddl.sql`](packages/dcm-databricks-pipeline/schemas/lakebase_ddl.sql) | **DDL SQL complet** — script à exécuter une fois sur Lakebase PostgreSQL pour créer toutes les tables |

**Tables SERVING actuelles dans Lakebase :**

| Table | Domaine | Source |
|---|---|---|
| `pipeline_metrics` | Pipelines | ADF + Glue |
| `compute_metrics` | Compute | Databricks + EMR |
| `cost_metrics` | Coûts | Cost Management + Cost Explorer |
| `database_metrics` | Databases | SQL/PG/MySQL/Cosmos + RDS |
| `security_alerts` | Sécurité | Security Center + GuardDuty |
| `activity_runs` | Activités détaillées | ADF activities + Glue steps |
| `user_metrics` | Utilisateurs | SCIM Databricks + IAM AWS |
| `standard_checks` | Conformité | Azure Policy + AWS Config Rules |
| `dim_landing_zone` | Référentiel LZ | SCD Type 2 (`lz_id`, `lz_name`, `ba_name`, `region`, `environment`) |
| `collection_runs` | Audit collectes | Tous agents |

---

## 3. Implémentation — Code source

> Documentation par composant. Chaque README composant est le point d'entrée pour le développeur travaillant sur ce composant.

| Composant | README | Description | État |
|---|---|---|---|
| **dcm-commons** | [`packages/dcm-commons/README.md`](packages/dcm-commons/README.md) | Package Python partagé — modèles, auth, BaseCollector, ApigeeClient | ✅ |
| **dcm-azure-collector** | [`packages/dcm-azure-collector/README.md`](packages/dcm-azure-collector/README.md) | Agent Azure (App Service WebJob) — 8 collecteurs | ✅ |
| **dcm-aws-collector** | [`packages/dcm-aws-collector/README.md`](packages/dcm-aws-collector/README.md) | Agent AWS (ECS Fargate one-shot) — 8 collecteurs | ✅ |
| **dcm-lambda-ingestion** | [`packages/dcm-lambda-ingestion/README.md`](packages/dcm-lambda-ingestion/README.md) | Lambda Python — validation + publication SQS | ✅ |
| **dcm-databricks-pipeline** | [`packages/dcm-databricks-pipeline/README.md`](packages/dcm-databricks-pipeline/README.md) | PySpark — Bronze → Silver → Gold → Lakebase | ✅ |
| **dcm-backend** | [`packages/dcm-backend/README.md`](packages/dcm-backend/README.md) | FastAPI — 14 routes, 66 tests, asyncpg | ✅ |
| **dcm-frontend** | [`packages/dcm-frontend/README.md`](packages/dcm-frontend/README.md) | React 18 TS — 12 pages, Entra ID MSAL | ✅ |

**Index technique de la solution :** [`packages/`](packages/) — vue d'ensemble des composants Python/React.

---

## 4. Roadmap et état d'avancement

| Document | Description |
|---|---|
| [`specs/roadmap.md`](specs/roadmap.md) | **Roadmap de référence** — 8 phases, état sprint par sprint, domaines collectés |
| [`docs/README.md`](docs/README.md) | Index de la documentation — navigation vers tous les composants |

**État global :**

| Phase | Statut | Détail |
|---|---|---|
| Phase 1 — dcm-commons | ✅ Terminé | Modèles Pydantic, auth Entra ID, BaseCollector, ApigeeClient |
| Phase 2 — Azure Collector | ✅ Terminé | 8 collecteurs (ADF, Databricks, Cost, DB, Security, Activity, Users, StandardCheck) |
| Phase 3 — AWS Collector | ✅ Terminé | 8 collecteurs (Glue, EMR, RDS, Cost Explorer, Redshift, Glue Activity, IAM, Config) |
| Phase 4 — Lambda Ingestion | ✅ Terminé | Validation Pydantic + SQS publisher, 19 tests |
| Phase 5 — Databricks Pipeline | ✅ Terminé | 4 jobs PySpark, 10 tables DDL, 23 tests |
| Phase 6 — Backend API | ✅ Terminé | 14 routes FastAPI, 66 tests |
| Phase 7 — Frontend | ✅ Terminé | 12 pages React, MSAL Entra ID, LZ selector |
| Sprint 7 — Renommages | ✅ Terminé (2026-04-16) | Cluster→Compute, Compliance→StandardCheck, tous composants |
| **Sprint 8** | 🔵 En cours | CI/CD, tests complémentaires, docker-compose, fix bug frontend |
| Phase 8 — Tests E2E | ⏳ Après infra | Conditionnel déploiement équipe infra |

---

## 5. Implémentation — Documents de référence

| Document | Description |
|---|---|
| [`specs/roadmap.md`](specs/roadmap.md) | **Handover développeur** — état détaillé composant par composant + toutes les tâches Sprint 8 avec code exact |
| [`docs/03-implementation/ANALYSE-ALTERNATIVES-INGESTION.md`](docs/03-implementation/ANALYSE-ALTERNATIVES-INGESTION.md) | Analyse des alternatives d'ingestion (SQS vs EventBridge vs Kafka) |
| [`docs/03-implementation/plan-infra-aws-bask.md`](docs/03-implementation/plan-infra-aws-bask.md) | Plan infrastructure AWS (pour l'équipe infra) |
| [`docs/03-implementation/OTel_Integration.md`](docs/03-implementation/OTel_Integration.md) | Guide intégration OpenTelemetry (FR) |
| [`docs/03-implementation/OTel_Integration EN.md`](docs/03-implementation/OTel_Integration%20EN.md) | Guide intégration OpenTelemetry (EN) |
| [`docs/aws-resources-inventory.md`](docs/aws-resources-inventory.md) | Inventaire ressources AWS déployées (compte 551656632516, 17 avril 2026) |

---

## 6. Actions en cours — Sprint 8

> Ces actions sont détaillées avec le code exact dans [`specs/roadmap.md`](specs/roadmap.md) sections 4.1 à 4.6.

| # | Action | Composant | Priorité | Détail |
|---|---|---|---|---|
| S8-1 | Nettoyage imports backward-compat | azure-collector + aws-collector | 🔴 Haute | Remplacer `ClusterState` → `ComputeState`, `ComplianceState` → `StandardCheckState` dans tous les collecteurs. Ensuite supprimer les 4 alias dans `dcm_commons/models/enums.py` lignes 252-255. |
| S8-2 | Générer 12 fixtures JSON | dcm-commons | 🔴 Haute | Compléter `fixtures/generate_fixtures.py`. Générer : `pipeline_metric.json`, `compute_metric.json`, `cost_metric.json`, `database_metric.json`, `security_alert.json`, `activity_run_metric.json`, `user_metric.json`, `standard_check_metric.json`, `metric_payload_pipeline.json`, `metric_payload_compute.json`, `metric_payload_standard_check.json`, `lambda_event.json`. |
| S8-3 | Tests collecteurs manquants | azure-collector + aws-collector | 🟠 Moyenne | Azure : `test_datafactory_collector.py`, `test_databricks_collector.py`, `test_cost_management_collector.py`, `test_security_center_collector.py`, `test_activity_runs_collector.py`. AWS : `test_iam_users_collector.py`, `test_config_compliance_collector.py`, `test_glue_activity_runs_collector.py`. |
| S8-4 | CI/CD GitHub Actions | `.github/workflows/` | 🟠 Moyenne | 7 workflows : `ci-commons.yml`, `ci-backend.yml`, `ci-azure-collector.yml`, `ci-aws-collector.yml`, `ci-lambda-ingestion.yml`, `ci-databricks-pipeline.yml`, `ci-frontend.yml`. Plus `security-scan.yml`. |
| S8-5 | docker-compose local dev | racine `packages/` | 🟡 Basse | PostgreSQL + LocalStack SQS + dcm-backend. Plus `Makefile` avec `make up`, `make test`. |
| S8-6 | Fix bug TypeScript | dcm-frontend | 🟡 Basse | `LandingPage.tsx` ligne ~122 : `JSX element type 'node.icon' does not have any construct or call signatures`. Typer `Icon` comme `React.ComponentType<React.SVGProps<SVGSVGElement>>`. |

---

## 7. Actions futures — Post Sprint 8

| Action | Priorité | Dépendance | Description |
|---|---|---|---|
| Restructuration dépôt `packages/` | Planifié Sprint 9/10 | CI/CD stable | Renommer `dcm/solution/` → `packages/`, `dcm-docs/` → `docs/`, créer `specs/` pour spec-kit Copilot, créer `infra/` pour IaC. Validé en équipe. |
| Tests E2E flux complet | Après infra | Équipe infra | Flux agent → Apigee → Lambda → SQS → Databricks → Lakebase → Backend → Frontend. |
| Déploiement ECS Service dcm-backend | Après infra | Équipe infra | ECS Service manquant (cluster ECS existe mais service vide). |
| ECR repositories | Après infra | Équipe infra | Créer registres ECR pour dcm-backend, dcm-aws-collector, dcm-frontend (images Docker). |
| Databricks workspace + DDL | Après infra | Équipe infra | Exécuter `lakebase_ddl.sql` sur le Lakebase PostgreSQL. Créer les 4 jobs Databricks. |
| EventBridge Scheduler AWS collector | Après infra | Équipe infra | Déclencher dcm-aws-collector toutes les 5 minutes (ECS Fargate Task). |
| ALB (Application Load Balancer) | Après infra | Équipe infra | Confirmer existence ALB devant dcm-backend (SG existe mais ALB non listé dans inventaire). |


---

## 8. Décisions techniques clés (log)

> Ces décisions sont définitives et ne doivent pas être remises en question sans passage en Design Authority.

| Date | Décision | Justification |
|---|---|---|
| 19 Fév 2026 | **Agents distribués par LZ** (Scénario 2) | Scénario 1 centralisé rejeté pour raisons de sécurité cyber |
| 19 Fév 2026 | **Python** pour tous les composants (remplace .NET) | Uniformisation stack, ecosystème data Python plus riche |
| 19 Fév 2026 | **FastAPI** pour le backend | Async natif, OpenAPI auto-généré, cohérence Python |
| 19 Fév 2026 | **Databricks Lakebase PostgreSQL** | Protocole PostgreSQL standard, driver asyncpg sans changement |
| 2026-04-16 | **Renommage Cluster→Compute, Compliance→StandardCheck** | Alignement terminologie métier : Compute = générique Databricks+EMR, StandardCheck = terme correct contrôles Policy/Config |
| 2026-04-29 | **Migration `packages/` différée à Sprint 9/10** | CI/CD doit être stable avant migration — pas de double écriture des paths |
| 2026-04-29 | **BaseCollector dans dcm-commons** (building block validé) | Évite duplication de 40% du code collecteur — retry, corrélation ID, CollectionResult partagés |
| 2026-04-29 | **Pas de fusion `main.py` Azure+AWS** | Patterns incompatibles : Azure = boucle infinie (WebJob), AWS = one-shot (ECS Fargate) |



---

## 9. Navigation rapide

```
Comprendre l'architecture     → docs/01-architecture/ARCHITECTURE-DCM-FINALE.md
Comprendre le schéma données  → docs/02-data-model/data-models.md
Reprendre le code d'un composant → packages/{composant}/README.md
Savoir ce qui reste à faire   → specs/roadmap.md
Suivre la roadmap             → specs/roadmap.md
Voir l'inventaire AWS         → docs/aws-resources-inventory.md
Exécuter le DDL Lakebase      → packages/dcm-databricks-pipeline/schemas/lakebase_ddl.sql
Comprendre les conventions    → .github/copilot-instructions.md
```
