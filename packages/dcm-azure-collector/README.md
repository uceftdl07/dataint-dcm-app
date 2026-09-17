# dcm-azure-collector — Azure Collector Agent

**Phase roadmap :** Phase 2 ✅ IMPLÉMENTÉE
**Type :** Agent Python Azure
**Déploiement :** App Service WebJob (Building Block JOB_2) — processus continu
**Scheduling :** Boucle interne `asyncio` — intervalle configurable (défaut 300 s)

---

## Rôle

Collecte les métriques KPI depuis les services Azure d'une Landing Zone,
normalise chaque lot en `MetricPayload`, et envoie vers Apigee via JWT Entra ID.

Tourne comme **processus long-running** (WebJob continu) — différent du
collecteur AWS qui s'exécute en one-shot sur ECS Fargate.

---

## Sources collectées

| Collector | Service Azure | Domaine | Données | Lakebase |
|---|---|---|---|---|
| `DataFactoryCollector` | Azure Data Factory | `pipeline` | Pipeline runs, statuts, durées, erreurs, pagination | `dcm.monitoring.pipeline_runs` |
| `DatabricksCollector` | Azure Databricks | `cluster` | Clusters (état, workers, type, autoscale) | `dcm.monitoring.cluster_snapshots` |
| `CostManagementCollector` | Azure Cost Management | `cost` | Coûts 30j par service, budgets, % consommé | `dcm.monitoring.cost_daily` |
| `DatabaseCollector` | SQL / PostgreSQL / MySQL / Cosmos DB | `database` | CPU, mémoire, connexions, stockage (Azure Monitor) | `dcm.monitoring.database_snapshots` |
| `SecurityCenterCollector` | Microsoft Defender for Cloud | `security` | Alertes actives (Active + InProgress uniquement) | `dcm.monitoring.security_alerts` |

---

## Architecture d'authentification

```
App Service WebJob (Long-running)
      │
      ├── Managed Identity (System-Assigned)          ← IDENTITY_ENDPOINT présent
      │         │                                     ← ManagedIdentityCredential
      │         └── Azure Key Vault (dcm-kv-*)
      │                   ├── dcm-entra-tenant-id
      │                   ├── dcm-entra-client-id
      │                   ├── dcm-entra-client-secret
      │                   └── dcm-apigee-api-key
      │
      ├── Entra ID (MSAL — client_credentials)
      │         │
      │         └── JWT Bearer Token (scope: api://dcm-ingestion/.default)
      │
      └── Apigee → VPC Lattice → Lambda → SQS
```

**Dev local** : `IDENTITY_ENDPOINT` absent → `DefaultAzureCredential` (az login, env vars, etc.)

---

## Variables d'environnement (App Service Settings)

| Variable | Obligatoire | Description |
|---|---|---|
| `DCM_KEY_VAULT_URL` | ✅ | URL du Key Vault (ex: `https://dcm-kv-prod.vault.azure.net/`) |
| `AZURE_SUBSCRIPTION_ID` | ✅ | ID de la souscription Azure à monitorer |
| `DCM_SOURCE_LZ_ID` | ✅ | Identifiant Landing Zone (ex: `azure-sub-fa5abbc4`) |
| `DCM_APIGEE_BASE_URL` | ✅ | URL de base Apigee (ex: `https://api.corporate.com/dcm`) |
| `DCM_ENTRA_SCOPE` | — | Scope OAuth2 (défaut: `api://dcm-ingestion/.default`) |
| `DCM_COLLECTION_INTERVAL` | — | Intervalle collection en secondes (défaut: `300`, min: `60`) |
| `DCM_PIPELINE_LOOKBACK_HOURS` | — | Fenêtre historique ADF en heures (défaut: `168` = 7 jours, min: `1`) |
| `DCM_ENABLED_COLLECTORS` | — | CSV des collecteurs actifs (défaut: les 8 — voir `config.py`) |
| `DCM_LOG_LEVEL` | — | Niveau de log (défaut: `INFO`) |
| `IDENTITY_ENDPOINT` | — | Positionné auto par App Service (Managed Identity) |

---

## Structure du code

```
azure_collector/
├── __init__.py                    # version, description package
├── config.py                      # AzureCollectorConfig — env + Key Vault
├── main.py                        # Boucle asyncio, signal SIGTERM/SIGINT
├── _azure_utils.py                # run_sync(), mappers ADF/Defender, tokens
└── collectors/
    ├── __init__.py                # exports des 5 classes
    ├── datafactory.py             # DataFactoryCollector — pagination continuation_token
    ├── databricks.py              # DatabricksCollector — REST mgmt + API 2.0
    ├── cost_management.py         # CostManagementCollector — httpx REST direct
    ├── databases.py               # DatabaseCollector — 4 familles + Azure Monitor
    └── security_center.py         # SecurityCenterCollector — azure-mgmt-security
```

---

## Patterns d'implémentation

### Async bridge — SDK synchrone dans contexte async

Tous les SDK Azure (`azure-mgmt-*`) sont synchrones. Chaque appel est wrappé via :

```python
# _azure_utils.py
async def run_sync(func: Any, *args: Any, **kwargs: Any) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))

# Usage
factories = await run_sync(lambda: list(adf_client.factories.list(subscription_id)))
```

### Fermeture de boucles Python — capturer les variables

Pattern obligatoire pour éviter les bugs de closure dans les lambdas en boucle :

```python
for server in servers:
    databases = await run_sync(
        lambda rg=resource_group, sn=server_name: list(
            sql_client.databases.list_by_server(rg, sn)
        )
    )
```

### Retry exponentiel (hérité de BaseCollector)

```
attempt 1 → délai 2 s
attempt 2 → délai 4 s
attempt 3 → exception CollectionError propagée
```

Uniquement sur `CollectionError` — les exceptions non-`CollectionError` propagent immédiatement.

### Isolation par catégorie (DatabaseCollector)

```python
for collect_fn in (sql, postgresql, mysql, cosmos):
    try:
        items = await collect_fn(...)
        metrics.extend(items)
    except CollectionError:
        raise   # auth failure = retry global
    except Exception:
        log.warning(...)  # erreur catégorie = skip, continue
```

### Boucle principale — arrêt propre sur SIGTERM

```python
loop.add_signal_handler(signal.SIGTERM, stop_event.set)
loop.add_signal_handler(signal.SIGINT, stop_event.set)

while not stop_event.is_set():
    await run_collection_cycle(...)
    await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
```

### httpx — connexion pooling Apigee

Un seul `ApigeeClient` (et donc un seul `httpx.AsyncClient`) est maintenu ouvert
pour toute la durée de vie du processus :

```python
async with ApigeeClient(...) as apigee:
    while not stop_event.is_set():
        await run_collection_cycle(config, credential, apigee)
```

---

## Comportements clés par collecteur

### DataFactoryCollector
- Pagination ADF via `continuation_token` (max 100 runs/page)
- Fenêtre temps : `now - lookback_hours` → `now` (mis à jour chaque cycle)
- Erreur par factory : log + skip, les autres factories continuent
- `duration_seconds` : converti depuis `duration_in_ms / 1000.0`

### DatabricksCollector
- Deux tokens : `management.azure.com/.default` (listing workspaces) + `2ff814a6-…/.default` (API Databricks)
- Workspace URL : préfixé `https://` si absent
- `start_time` : epoch ms → `datetime.fromtimestamp(ms/1000, tz=UTC)`
- État `RESIZING` → `RUNNING` (cluster actif pendant redimensionnement)
- Erreur par workspace : log + skip

### CostManagementCollector
- **httpx direct** (pas de SDK `azure-mgmt-costmanagement`) — contrôle total du corps de requête
- HTTP 429 → `CollectionError` → retry automatique
- Budget matching : case-insensitive sur le nom du service
- Lookback : 30 jours (configurable)

### DatabaseCollector
- **Azure Monitor** : fenêtre 15 min, granularité PT5M, agrégation Average
- Noms métriques **lowercasés** dans le dict résultat (unifie SQL lowercase et Cosmos CamelCase)
- Storage : Azure Monitor retourne des bytes → converti en GB
- `dtus_used` : **uniquement** Azure SQL Database (pas PostgreSQL/MySQL/Cosmos)
- `active_connections` : float Monitor → `int` (arrondi)
- Exclusion BDD système : `master`, `model`, `msdb`, `tempdb`
- `storage_limit_gb` : propriété SDK (`max_size_bytes` pour SQL, `storage_size_gb` pour Flexible)

### SecurityCenterCollector
- Par défaut : uniquement `Active` et `InProgress` (skip `Resolved`/`Dismissed`)
- `include_resolved=True` pour collecter toutes les alertes
- `resource_identifiers` : itéré pour extraire le premier `azure_resource_id` ARM
- `remediation_steps` : liste jointe en string avec `\n`

---

## Portage depuis le POC C#

| POC C# | dcm-azure-collector Python |
|---|---|
| `AzureDataFactoryService.cs` + `DataFactoryApiClient.cs` | `collectors/datafactory.py` |
| `AzureDatabricksService.cs` + `DatabricksApiClient.cs` | `collectors/databricks.py` |
| `AzureCostManagementService.cs` | `collectors/cost_management.py` |
| `AzureDatabaseService.cs` | `collectors/databases.py` |
| `DatabricksPermissionsService.GetSecurityAlertsAsync()` + `DataFactoryGovernanceService.GetSecurityAlertsAsync()` | `collectors/security_center.py` |

---

## Permissions RBAC Azure requises

| Permission | Scope | Collecteur |
|---|---|---|
| `Monitoring Reader` | Resource Group | `DatabaseCollector` (Azure Monitor) |
| `Cost Management Reader` | Subscription | `CostManagementCollector` |
| `Data Factory Contributor` (lecture) | Resource Group | `DataFactoryCollector` |
| `Reader` | Subscription | `DatabricksCollector`, `DatabaseCollector` |
| `Security Reader` | Subscription | `SecurityCenterCollector` |

---

## Dépendances

```toml
[dependencies]
dcm-commons              # modèles, auth, base collector, apigee client
azure-identity>=1.17     # DefaultAzureCredential, ManagedIdentityCredential
azure-keyvault-secrets>=4.8
azure-mgmt-datafactory>=8.0
azure-mgmt-monitor>=6.0
azure-mgmt-sql>=3.0
azure-mgmt-rdbms>=10.0   # postgresql_flexibleservers + mysql_flexibleservers
azure-mgmt-cosmosdb>=9.0
azure-mgmt-security>=7.0
azure-mgmt-resource>=23.0
httpx>=0.27              # client async direct (Cost Management REST)
structlog>=24.4
```

---

## Tests

```bash
cd dcm/solution/dcm-azure-collector
pip install -e ".[dev]"
pytest tests/ -v
```

| Fichier test | Couverture |
|---|---|
| `tests/test_database_collector.py` | `_extract_resource_group`, `_to_int`, `_fetch_monitor_metrics`, SQL/PG/MySQL/Cosmos collectors, isolation failures, orchestration |

---

## Déploiement App Service WebJob

### App Service (Phase 5.2) — GitHub Actions

**CI (test + push ECR) :** `.github/workflows/dcm-azure-collector.yml`  
**Deploy App Service :** `.github/workflows/dcm-azure-collector-deploy-lz.yml`  
**Cibles :** `.github/azure-collector-deploy-targets.json`

Actions → **dcm-azure-collector - Deploy to App Service (client LZs)**

| Input | Exemple |
|-------|---------|
| `deploy_target` | `datasquad-d` ou `novadatahub-m` |
| `github_environment` | `dev` |
| `image_tag` | (vide = SHA du commit) |

Deploy **container** sur l’App Service BB — image ECR DCM : `551656632516.dkr.ecr.eu-central-1.amazonaws.com/awsd-dcm-azure-collector:<git-sha>` (pas d’ACR Azure, pas d’ACI).

### Prérequis avant le workflow

Voir guide complet : `packages/dcm-agent/docs/onboarding-guide/03-phase-5-2-deploy.md`

| # | Prérequis |
|---|-----------|
| 1 | Phases **2, 5.1, 3b** terminées |
| 2 | Entrée dans `azure-collector-deploy-targets.json` |
| 3 | GitHub `dev` : `AZURE_BUILDER_*` (Builder SP **de la LZ cible**) + `AWS_AZURE_COLLECTOR_ECR_ROLE_ARN` |
| 4 | **Contributor** `AZR-IASP-LZ-{lzName}-Builder` sur subscription **LZ** |
| 5 | **ECR push** via rôle IAM compte `551656632516` (registry central DCM AWS) |
| 6 | Egress App Service vers `*.dkr.ecr.*.amazonaws.com` + Entra + Apigee |

```bash
# Test accès Builder (comme CI) — remplacer par le Builder de la LZ cible
az login --service-principal -u <BUILDER_CLIENT_ID> \
  -p <secret> --tenant 329e91b0-e21f-48fb-a071-456717ecc28e
az account list -o table
```

### Manuel (jumpbox LZ)

```bash
# Package pour déploiement
pip install -e . --target ./deploy_package/

# Démarrer le WebJob (continu)
dcm-azure-collector
# → charge config depuis Key Vault
# → démarre la boucle asyncio
# → collecte toutes les 5 minutes
# → s'arrête proprement sur SIGTERM (App Service graceful shutdown)
```
