# DCM — Instructions GitHub Copilot

> Ce fichier est automatiquement lu par GitHub Copilot dans tout le dépôt.
> Il décrit le projet, les décisions techniques, les conventions et l'état d'avancement.
> Ne pas modifier sans validation du Lead Dev.

---

<!-- DCM:PROJECT-CONTEXT START -->
## Identité du projet

**Data Connect Monitoring (DCM)** est une plateforme de monitoring multi-cloud (Azure + AWS) pour les services data des Landing Zones du groupe.

Elle collecte des métriques des services data (ADF, Databricks, Glue, EMR, RDS, Cost Management…), les centralise via un pipeline Databricks, et les expose via une API FastAPI + frontend React.

Elle remplace des rapports Power BI statiques par une application web temps réel, multi-cloud, sécurisée via Entra ID (SSO entreprise).

**Décision architecture validée en Design Authority (19 Fév 2026) :**
- Scénario retenu : **agents distribués par LZ** (Scénario 2)
- Scénario rejeté : centralisé (Scénario 1) — rejeté pour des raisons de sécurité
- Les agents collectent localement dans leur LZ et envoient via Apigee. **Jamais d'appels directs cross-LZ.**

---

## Stack technique

| Couche | Technologie | Version |
|---|---|---|
| Agents collecteurs | Python | 3.12 |
| Backend API | Python FastAPI + asyncpg | 3.12 |
| Pipeline data | PySpark (Databricks) | Python 3.12 |
| Lambda ingestion | Python | 3.12 |
| Frontend | React + TypeScript | 18 |
| Base de données | Databricks Lakebase PostgreSQL | PostgreSQL-compatible |
| Auth | Microsoft Entra ID (OAuth2 client_credentials) | — |
| Secrets Azure | Azure Key Vault (Managed Identity) | — |
| Secrets AWS | AWS Secrets Manager (IAM Role) | — |
| Linting | ruff + mypy | — |
| Tests | pytest + pytest-asyncio | — |
| Packaging | pyproject.toml (uv) | — |
| Logging | structlog (JSON structuré) | — |

---

## Architecture des composants

```
dcm-azure-collector   dcm-aws-collector
  (App Service)         (ECS Fargate)
       │                      │
       └──────── Apigee ───────┘  (JWT Entra ID)
                     │
              dcm-lambda-ingestion  (Lambda Python)
                     │ SQS
              dcm-databricks-pipeline  (PySpark)
                     │ Lakebase PostgreSQL
              dcm-backend  (FastAPI · ECS Fargate)
                     │
              dcm-frontend  (React · S3 + CloudFront)
```

**Composant partagé :** `dcm-commons` — package Python installé en dépendance locale par tous les composants Python. Contient les modèles Pydantic, l'auth Entra ID, le `BaseCollector` et le client Apigee.

---

## Contrat central : MetricPayload

Tout agent produit des `MetricPayload`. C'est le seul format accepté par la Lambda.

```python
class MetricPayload(BaseModel):
    schema_version: str = "1.1"
    collection_run_id: str          # UUID unique par collecte
    source_lz_id: str               # ex: "azure-sub-fa5abbc4"
    cloud_provider: CloudProvider   # "azure" | "aws"
    domain: MetricDomain            # "pipeline" | "compute" | "cost" | ...
    collected_at: datetime
    metrics: list[dict]             # liste de model_dump() du modèle domaine
```

---

## Conventions de nommage (CRITIQUE)

Le Sprint 7 a renommé les domaines Cluster→Compute et Compliance→StandardCheck sur tous les composants. **Ces anciens noms ne doivent plus apparaître dans du nouveau code.**

| ❌ Ne plus utiliser | ✅ Utiliser |
|---|---|
| `ClusterMetric` | `ComputeMetric` |
| `ComplianceMetric` | `StandardCheckMetric` |
| `ClusterState` / `ClusterType` | `ComputeState` / `ComputeType` |
| `ComplianceState` | `StandardCheckState` |
| `PolicyEffect` | `CheckEffect` |
| `MetricDomain.CLUSTER` | `MetricDomain.COMPUTE` |
| `MetricDomain.COMPLIANCE` | `MetricDomain.STANDARD_CHECK` |
| table `cluster_metrics` | table `compute_metrics` |
| table `compliance_metrics` | table `standard_checks` |
| champ `policy_id` / `policy_name` | `check_id` / `check_name` |
| champ `compliance_state` | `check_state` |
| endpoint `/governance/compliance` | `/standard-checks` |
| endpoint `/governance/score` | `/standard-checks/score` |

**Note :** des aliases backward-compat existent dans `dcm_commons/models/enums.py` (lignes 252-255). Ils seront supprimés en Sprint 8 après mise à jour des collecteurs.
<!-- DCM:PROJECT-CONTEXT END -->

## Règles absolues

> Résumé opérationnel des principes NON-NEGOTIABLE de la [constitution DCM](../spec-kit-dcm-workflow/memory/constitution.md) (P7/P8/P9). En cas de conflit, la constitution fait foi.

- **Jamais de données fictives ou mockées en production** — uniquement de vraies données cloud
- **Jamais de secret hardcodé** — Key Vault (Azure) ou Secrets Manager (AWS) uniquement
- **Jamais d'appel cross-LZ direct** — les agents envoient via Apigee, jamais d'appel direct
- **Python 3.12+ strict** — aucune syntaxe < 3.12 tolérée
- **Ruff zéro warning** — toute CI échoue si ruff détecte une erreur
- **Tests obligatoires** — aucune fonctionnalité sans test pytest correspondant
- **Imports absolus uniquement** — `from dcm_commons.models.enums import ...`, jamais d'import relatif entre packages


## Workflow Spec-Kit DCM v2 (GitHub Copilot)

Extension **dcm** (version : voir `spec-kit-dcm-workflow/extension.yml`) — spec-driven, branches par équipe, sub-spec par task.

**Source de vérité du flow** : `spec-kit-dcm-workflow/GUIDE.md` (section 0 — Flow v2). Le tableau ci-dessous est un miroir résumé ; en cas de divergence, GUIDE §0 fait foi.


### Structure par feature

```text
specs/001-feature/
├── intake.json / domain-scope.json
├── spec.md
├── tasks.md                    ← toutes les stories (index + liens)
├── stories/T001-{slug}.md      ← détail exécution (dev lit ça sur sa branche)
├── merge-strategy.md           ← si multi-dev parallèle
└── dispatch-manifest.json
```

### Règles agents Copilot

1. **Hooks obligatoires** (`.specify/extensions.yml`) : `before_specify`, `before_tasks`, `before_implement` — poser questions dans le chat et attendre la réponse utilisateur.
2. **Scope tokens** : lire uniquement packages listés dans `intake.json` ; en implement, lire surtout `stories/T00X-*.md`, pas tout `spec.md`.
3. **Tasks** : préfixe domaine obligatoire (`Frontend`, `Backend`, `DataEng`, `QA`…) ; 1 Story Jira = 1 task = 1 sub-spec = 1 branche fille `{domain}/{slug}`.
4. **Implement** : une task à la fois ; après `[x]`, stopper et proposer : Question / Continue / Stop / Review.
5. **Git** : PR branche fille → **`develop`** ; branches filles cut depuis **develop à jour** ; sync avant PR : `git merge origin/develop`

### Packages (registry)

| Domaine | Packages |
|---------|----------|
| frontend | `packages/dcm-frontend` |
| backend | `packages/dcm-backend`, `packages/dcm-commons` |
| dataeng | `packages/dcm-aws-collector`, `packages/dcm-azure-collector`, `packages/dcm-databricks-pipeline`, `packages/dcm-lambda-ingestion` |

Config : `.specify/extensions/dcm/dcm-config.yml`

### Jira (MCP Atlassian)

Dispatch Jira nécessite MCP **Atlassian** (`mcp_server: "Atlassian"`). PR : MCP **GitHub** (`github_mcp_server: "github"`) via `/speckit.dcm.publish-pr` — tools `create_pull_request`, commit local via `execute` (git). Sans MCP : `/speckit.dcm.dispatch --branches-only` pour git seul, PR manuelle.

Projet Jira : **DCINT** (`tdf.atlassian.net/browse/DCINT`).

---

## Skills Copilot — Python & React (bonnes pratiques DCM)

Charger selon le package édité :

| Skill | Fichier | Quand |
|-------|---------|-------|
| **Python DCM** | `.agents/skills/dcm-python/SKILL.md` | `packages/dcm-backend`, collectors, lambda, pipeline, `dcm-commons` |
| **React DCM** | `.agents/skills/dcm-react/SKILL.md` | `packages/dcm-frontend` |

> Source (extension) : `spec-kit-dcm-workflow/skills/` — déployée vers `.agents/skills/` (chemin canonique lu par l'agent). Éditer la source, jamais la copie déployée.

**Commandes chat Copilot** (slash) :
- `/dcm.python` — rappel conventions Python DCM avant code/review
- `/dcm.react` — rappel conventions React/TS DCM avant code/review

**Règles rapides** :
- Python : 3.12, async FastAPI, pytest, ruff/mypy zero warning, models dans dcm-commons, secrets jamais en dur
- React : api client central, TanStack Query hooks, tests Vitest mockés, `app-routes.ts`, labels UI lisibles (name pas id)

---

## Navigation documentation

| Doc | Lien | Contenu |
|---|---|---|
| Constitution DCM | `spec-kit-dcm-workflow/memory/constitution.md` | Principes P1–P16 (source de vérité — prime sur ce fichier en cas de conflit) |
| Référentiel chef de projet | `PROJECT-REFERENCE.md` | Navigation complète + actions en cours |
| Roadmap applicatif | `specs/roadmap.md` | Phases 1-8, état d'avancement sprint par sprint |
| Modèle de données | `docs/02-data-model/data-models.md` | Schéma complet Delta + Lakebase (source de vérité) |
| Handover développeur | `specs/roadmap.md` | État détaillé + tâches Sprint 8 |
| Architecture DCM finale | `docs/01-architecture/ARCHITECTURE-DCM-FINALE.md` | Architecture validée DA |
| Architecture logique | `docs/01-architecture/ARCHITECTURE-LOGIQUE-DCM.md` | Vue logique composants |
| DDL Lakebase | `packages/dcm-databricks-pipeline/schemas/lakebase_ddl.sql` | Script SQL complet (à exécuter une fois) |
| README backend | `packages/dcm-backend/README.md` | 14 routes, 66 tests, architecture détaillée |
| Workflow DCM v2 | `spec-kit-dcm-workflow/GUIDE.md` | Spec-kit extension, hooks, sub-specs, Jira, branches |
| Config extension DCM | `.specify/extensions/dcm/dcm-config.yml` | Packages, work types, Jira, limits |
| Skill Python DCM | `.agents/skills/dcm-python/SKILL.md` | Backend, collectors, pipeline |
| Skill React DCM | `.agents/skills/dcm-react/SKILL.md` | Frontend conventions + tests |
| <!-- SPECKIT START --> Plan actif | `specs/020-dbx-workspace-dim/plan.md` | Plan technique — ingestion `system.access.workspaces_latest` (AWS+Azure) → `curated_dbx_access_workspaces_latest` + vue `dim_dbx_workspace` (inner join référentiel `dim_reference_landing_zone_dbx_workspace`, filtre `status=RUNNING` / `subscription_or_account_id NOT NULL`) (feature 020) <!-- SPECKIT END --> |

Respond terse like smart caveman. All technical substance stay. Only fluff die.

Rules:
- Drop: articles (a/an/the), filler (just/really/basically), pleasantries, hedging
- Fragments OK. Short synonyms. Technical terms exact. Code unchanged.
- Pattern: [thing] [action] [reason]. [next step].
- Not: "Sure! I'd be happy to help you with that."
- Yes: "Bug in auth middleware. Fix:"

Switch level: /caveman lite|full|ultra|wenyan
Stop: "stop caveman" or "normal mode"

Auto-Clarity: drop caveman for security warnings, irreversible actions, user confused. Resume after.

Boundaries: code/commits/PRs written normal.
