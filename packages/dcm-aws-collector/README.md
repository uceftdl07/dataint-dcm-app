# dcm-aws-collector — AWS Collector Agent

**Phase roadmap :** Phase 3
**Statut :** ✅ Implémenté
**Type :** Agent Python AWS
**Déploiement :** ECS Fargate Task (Building Block CT_2_SLESS_TASK)
**Trigger :** EventBridge Scheduler (Building Block CRON_1) — cron toutes les 5 minutes

---

## Rôle

Collecte les métriques KPI depuis les services AWS d'une Landing Zone,
normalise en `MetricPayload`, et envoie vers Apigee via JWT Entra ID.

C'est un **nouveau développement** (pas de POC équivalent côté AWS dans `/Backend/`).

**Modèle d'exécution :** One-shot — la tâche ECS démarre, collecte, envoie, et **se termine**.
Aucune boucle infinie. L'EventBridge relance toutes les 5 minutes.

---

## Sources collectées

| Collector | Service AWS | Lakebase target | Données |
|---|---|---|---|
| `GlueCollector` | AWS Glue | `dcm.monitoring.pipeline_runs` | Job runs (20 derniers/job), last-crawl crawlers |
| `EMRCollector` | Amazon EMR | `dcm.monitoring.cluster_snapshots` | État clusters, worker count, start time |
| `RDSCollector` | Amazon RDS / Aurora | `dcm.monitoring.database_snapshots` | CPU, connexions, storage (CloudWatch) |
| `CostExplorerCollector` | AWS Cost Explorer + Budgets | `dcm.monitoring.cost_daily` | Coûts mensuels par service, budget matching |
| `RedshiftCollector` | Amazon Redshift | `dcm.monitoring.database_snapshots` | CPU, disk%, connexions (CloudWatch) |

---

## Architecture d'authentification

```
ECS Fargate Task
      │
      ├── IAM Task Role (aucune credential statique)
      │         │
      │         └── AWS Secrets Manager (DCM_SECRET_NAME)
      │                   ├── entra_tenant_id
      │                   ├── entra_client_id
      │                   ├── entra_client_secret
      │                   └── apigee_api_key
      │
      └── Entra ID → client_credentials flow
                │
                └── JWT Bearer Token → Apigee → Lambda → SQS → Lakebase
```

**Dev local** : Profil `~/.aws/credentials` standard — pas besoin de Secrets Manager.
**Prod** : IAM Task Role uniquement — `boto3` résout les credentials automatiquement via l'IMDS ECS.

---

## Variables d'environnement (ECS Task Definition)

| Variable | Obligatoire | Défaut | Description |
|---|---|---|---|
| `DCM_SECRET_NAME` | ✅ | — | Nom du secret Secrets Manager |
| `DCM_SOURCE_LZ_ID` | ✅ | — | Identifiant de la Landing Zone (ex: `aws-account-551656632516`) |
| `DCM_AWS_REGION` | ✅ | — | Région AWS (ex: `eu-west-1`) |
| `DCM_APIGEE_BASE_URL` | ✅ | — | URL de base Apigee |
| `DCM_ENTRA_SCOPE` | ✅ | — | Scope OAuth2 (ex: `api://dcm-ingestion/.default`) |
| `DCM_ENABLED_COLLECTORS` | ❌ | `glue,emr,rds,cost_explorer,redshift` | Collectors à activer |
| `DCM_COST_LOOKBACK_DAYS` | ❌ | `30` | Fenêtre historique Cost Explorer (jours) |
| `DCM_LOG_LEVEL` | ❌ | `INFO` | Niveau de log (`DEBUG`/`INFO`/`WARNING`) |

---

## Structure du code

```
aws_collector/
├── __init__.py              # __version__ = "0.1.0"
├── _aws_utils.py            # run_sync(), fetch_cloudwatch_metric(), map_*()
├── config.py                # AWSCollectorConfig (Secrets Manager)
├── main.py                  # Entrypoint one-shot ECS
└── collectors/
    ├── __init__.py          # Re-exports publics
    ├── glue.py              # GlueCollector
    ├── emr.py               # EMRCollector
    ├── rds.py               # RDSCollector
    ├── cost_explorer.py     # CostExplorerCollector
    └── redshift.py          # RedshiftCollector

tests/
├── __init__.py
├── test_glue_collector.py
├── test_emr_collector.py
├── test_rds_collector.py
├── test_cost_explorer_collector.py
└── test_redshift_collector.py
```

---

## Patterns d'implémentation

### Bridge sync → async (`run_sync`)

Boto3 est une bibliothèque **synchrone**. Tous les appels SDK sont exécutés
dans un thread-pool via :

```python
async def run_sync(func: Callable[..., T], /, **kwargs: Any) -> T:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, functools.partial(func, **kwargs)
    )
```

### Fetch CloudWatch (`fetch_cloudwatch_metric`)

Helper partagé pour toutes les métriques CloudWatch :

```python
await fetch_cloudwatch_metric(
    cloudwatch_client,
    namespace="AWS/RDS",
    metric_name="CPUUtilization",
    dimensions=[{"Name": "DBInstanceIdentifier", "Value": instance_id}],
    window_minutes=15,
    period_seconds=300,
)
# Retourne le float Average du dernier datapoint, ou None si aucune donnée
```

### Pagination — deux curseurs différents

| Service | Paramètre curseur | Clé réponse |
|---|---|---|
| EMR `list_clusters` | `Marker` | `Marker` |
| RDS `describe_db_instances` | `Marker` | `Marker` |
| Redshift `describe_clusters` | `Marker` | `Marker` |
| Glue `get_jobs` | `NextToken` | `NextToken` |
| Glue `get_crawlers` | `NextToken` | `NextToken` |

### Cost Explorer — région globale

Le client CE **doit** être créé en `us-east-1` (endpoint global) :

```python
self._ce = boto3.client("ce", region_name="us-east-1")
```

### Calcul storage RDS

```
AllocatedStorage (GiB, describe_db_instances)  →  storage_limit_gb
FreeStorageSpace (bytes, CloudWatch)           →  free_gb = bytes / GiB
storage_used_gb = max(0, limit_gb − free_gb)
```

### Calcul storage Redshift

```
TotalStorageCapacityInMegaBytes (describe_clusters) → limit_gb = MB / 1024
PercentageDiskSpaceUsed (CloudWatch, %)             → disk_pct
storage_used_gb = limit_gb × (disk_pct / 100)
```

### Matching budget (CostExplorer)

Comparaison insensible à la casse entre `service_name` et `BudgetName` :

```python
budget_map = {b["name"].lower(): b for b in budgets}
budget = budget_map.get(service_name.lower())
```

---

## Comportement par collector

### GlueCollector

- Liste tous les jobs via `get_jobs` (paginé `NextToken`)
- Pour chaque job : `get_job_runs(JobName, MaxResults=20)` — 20 derniers runs
- `_map_job_run` : skip si `Id` manquant ou `StartedOn` absent
- Liste tous les crawlers via `get_crawlers` (paginé `NextToken`)
- `_map_crawler` : skip si `LastCrawl` absent ou `StartTime` absent
- Crawler `run_id` = surrogate `"{name}/{start.isoformat()}"`
- Echec `get_job_runs` d'un job individuel → warning + skip (non-fatal)
- Echec listing jobs → `CollectionError` (fatal)
- Echec listing crawlers → warning + liste vide (non-fatal)

### EMRCollector

- Liste toutes les 7 états EMR via `list_clusters` (paginé `Marker`)
- Pour chaque cluster : `describe_cluster(ClusterId)` pour détails
- `num_workers` = somme `RunningInstanceCount` des groupes CORE + TASK (pas MASTER)
- `spark_version` = `ReleaseLabel` (ex: `"emr-7.0.0"`)
- `start_time` : `Status.Timeline.CreationDateTime` — boto3 renvoie `datetime` aware
- Echec `describe_cluster` individuel → warning + skip (non-fatal)
- Echec `list_clusters` → `CollectionError` (fatal)

### RDSCollector

- Pagine `describe_db_instances` (Marker)
- CloudWatch namespace `AWS/RDS`, dimension `DBInstanceIdentifier`
- 4 métriques : `CPUUtilization`, `DatabaseConnections`, `FreeStorageSpace`, `FreeableMemory`
- `FreeableMemory` capturé mais non exposé (pas de total mémoire fiable via CW)
- `is_available` : `DBInstanceStatus == "available"`
- Tags : format `[{"Key": k, "Value": v}]`
- Echec listing → `CollectionError`

### CostExplorerCollector

- `sts.get_caller_identity()` pour résoudre l'account ID
- `ce.get_cost_and_usage` avec `Granularity="MONTHLY"`, `Metrics=["UnblendedCost"]`
- `budgets.describe_budgets(AccountId=account_id)`
- Echec STS → account_id vide + budgets skippés
- Echec budgets → liste vide (non-fatal, best-effort)
- Echec CE → `CollectionError` (fatal)

### RedshiftCollector

- Pagine `describe_clusters` (Marker)
- CloudWatch namespace `AWS/Redshift`, dimension `ClusterIdentifier`
- 3 métriques : `CPUUtilization`, `PercentageDiskSpaceUsed`, `DatabaseConnections`
- `is_available` : `ClusterStatus.startswith("available")` (couvre "available, prep-for-resize")
- Tags : format Redshift `[{"TagKey": k, "TagValue": v}]` (différent de RDS)
- Echec listing → `CollectionError`

---

## Tests

| Fichier | Classe/Groupe | Cas couverts |
|---|---|---|
| `test_glue_collector.py` | `TestMapJobRun` | succeeded, failed+error, missing id, missing start, naive tz, None exec_time |
| | `TestMapCrawler` | correct mapping, failed+error, missing name, missing last_crawl, missing start, naive tz |
| | `TestPaginateGlueJobs` | single page, multi-page Marker |
| | `TestGlueCollectorCollectMetrics` | both sources, job listing failure, crawler listing failure (partial), skip run sans StartedOn |
| `test_emr_collector.py` | `TestMapEmrState` | 8 states paramétrés |
| | `TestMapCluster` | full mapping, MASTER excluded, missing id, name fallback, start_time, naive tz, no timeline, tags, terminated |
| | `TestPaginateClusters` | single page, multi-page Marker |
| | `TestEMRCollectorCollectMetrics` | normal, listing failure, describe failure skip, empty id skip |
| `test_rds_collector.py` | `TestMapRdsEngine` | 10 engines paramétrés |
| | `TestPaginateDbInstances` | single page, multi-page |
| | `TestCollectInstanceMetric` | full, missing id, no free storage, zero allocated, storage clamped, unavailable, aurora engine, tags |
| | `TestRDSCollectorCollectMetrics` | collects all, listing failure, |
| `test_cost_explorer_collector.py` | `TestGetAccountId` | success, STS failure |
| | `TestQueryCosts` | parse costs, invalid amount→0, empty keys skipped |
| | `TestQueryBudgets` | parse budgets, empty account_id, API failure, missing name skipped |
| | `TestBuildCostMetrics` | case-insensitive match, no match→None, zero limit ignored, negative cost clamped, account_id embedded, pct calc |
| | `TestCostExplorerCollectorCollectMetrics` | full collection, CE failure→CollectionError |
| `test_redshift_collector.py` | `TestPaginateClusters` | single page, multi-page |
| | `TestCollectClusterMetric` | full, missing id, no storage, no disk pct, prep-for-resize=available, modifying=unavailable, tags Redshift format, tag without key skipped, endpoint→server_name, connections rounded |
| | `TestRedshiftCollectorCollectMetrics` | collects all, listing failure, None metric skipped |

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

---

## Déploiement

```bash
# Build image Docker
docker build -f packages/dcm-aws-collector/Dockerfile -t dcm-aws-collector:latest .

# Push vers ECR
aws ecr get-login-password --region eu-west-1 | \
  docker login --username AWS --password-stdin $ECR_URL
docker push $ECR_URL/dcm-aws-collector:latest

# Enregistrer la task definition ECS
aws ecs register-task-definition --cli-input-json file://task-definition.json
```

---

## Dépendances

```toml
[project.dependencies]
boto3 = ">=1.34"
dcm-commons = { path = "../dcm-commons" }

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "moto[glue,emr,rds,ce,budgets,cloudwatch,secretsmanager,sts]>=5.0",
    "boto3-stubs[glue,emr,rds,ce,budgets,cloudwatch,secretsmanager,sts]",
]
```

---

## RBAC AWS (IAM Task Role)

| Service | Action requise | Portée |
|---|---|---|
| Secrets Manager | `secretsmanager:GetSecretValue` | Secret `DCM_SECRET_NAME` |
| Glue | `glue:GetJobs`, `glue:GetJobRuns`, `glue:GetCrawlers` | Compte |
| EMR | `elasticmapreduce:ListClusters`, `elasticmapreduce:DescribeCluster` | Compte |
| RDS | `rds:DescribeDBInstances`, `rds:ListTagsForResource` | Compte |
| CloudWatch | `cloudwatch:GetMetricStatistics` | Compte |
| Cost Explorer | `ce:GetCostAndUsage` | Compte |
| Budgets | `budgets:ViewBudget` | Compte |
| STS | `sts:GetCallerIdentity` | Compte |
| Redshift | `redshift:DescribeClusters` | Compte |

---

## URL AWS a Whitelister (Client Landing Zone)

Les URL suivantes doivent etre autorisees en sortie depuis la landing zone cliente pour permettre la collecte DCM.

| Service | URL HTTPS a autoriser |
|---|---|
| Glue | `https://glue.eu-central-1.amazonaws.com` |
| EMR | `https://elasticmapreduce.eu-central-1.amazonaws.com` |
| RDS | `https://rds.eu-central-1.amazonaws.com` |
| CloudWatch Metrics | `https://monitoring.eu-central-1.amazonaws.com` |
| Cost Explorer | `https://ce.us-east-1.amazonaws.com` |
| AWS Budgets | `https://budgets.amazonaws.com` |
| STS regional | `https://sts.eu-central-1.amazonaws.com` |
| STS global (fallback SDK) | `https://sts.amazonaws.com` |
| Redshift | `https://redshift.eu-central-1.amazonaws.com` |

