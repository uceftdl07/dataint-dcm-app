# dcm-backend — FastAPI Backend API

**Phase roadmap :** Phase 6
**Statut :** ✅ Implémenté
**Type :** Service API Python FastAPI (Building Block CT_2_SLESS_SERVICE)
**Déploiement :** ECS Fargate Service
**Accès :** ALB + WAF (Building Block WAF_1) → API Gateway REST (Building Block API_GW_2R)
**Compte AWS :** awss-wl-dcm (551656632516)

---

## Rôle

API REST consommée par le Frontend DCM.
Lit les métriques KPI depuis **Lakebase PostgreSQL** via `asyncpg` (protocole PostgreSQL standard).
L'authentification JWT Entra ID est validée en amont par le **Lambda Authorizer** sur l'API Gateway.

---

## Architecture

```
Browser (MSAL.js) → Entra ID → JWT Access Token
      │
      ▼
API Gateway REST (AWS)
      │
      ├── Lambda Authorizer  (valide JWT Entra ID via JWKS endpoint)
      │
      ▼
ALB → ECS Task dcm-backend (FastAPI, port 8080)
      │
      └── asyncpg connection pool → Lakebase PostgreSQL Replica (TLS)
                                           └── Tables SERVING
                                                 ├── pipeline_metrics
                                                 ├── compute_metrics
                                                 ├── cost_metrics
                                                 ├── database_metrics
                                                 ├── security_alerts
                                                 ├── activity_runs
                                                 ├── user_metrics
                                                 ├── standard_checks
                                                 ├── dim_landing_zone
                                                 └── collection_runs
```

---

## Connexion Lakebase — Zero-Copy PostgreSQL

Lakebase expose un **endpoint PostgreSQL standard** — aucun driver Databricks requis.

```python
# Connexion identique à n'importe quelle base PostgreSQL
pool = await asyncpg.create_pool(
    host="lakebase-replica.internal",
    port=5432,
    database="dcm_monitoring",
    user="dcm_backend",
    password="...",  # depuis Secrets Manager
    ssl="require",   # TLS obligatoire
    min_size=2,
    max_size=10,
)
```

---

## Structure du code

```
app/
├── __init__.py          # __version__ = "0.1.0", docstring architecture
├── main.py              # FastAPI app + lifespan (pool sur app.state.db_pool)
├── config.py            # Settings (pydantic-settings + Secrets Manager)
├── db/
│   ├── __init__.py
│   └── connection.py    # DatabasePool + get_db() FastAPI dependency
└── api/
    ├── __init__.py
    └── routes/
        ├── __init__.py
        ├── health.py       # GET /api/v1/health (+ DB probe SELECT 1)
        ├── dashboard.py    # GET /api/v1/dashboard/overview
        ├── pipelines.py    # GET /api/v1/pipelines + /{name}/runs
        ├── clusters.py     # GET /api/v1/clusters (DISTINCT ON compute_resource_id)
        ├── costs.py        # GET /api/v1/costs/summary + /by-service
        ├── databases.py    # GET /api/v1/databases (DISTINCT ON db_id)
        ├── security.py     # GET /api/v1/security/alerts
        ├── activities.py   # GET /api/v1/activities
        ├── users.py        # GET /api/v1/users
        └── governance.py   # GET /api/v1/standard-checks + /score + /landing-zones/details

tests/
├── conftest.py              # Fixtures : mock_db (AsyncMock) + client (httpx)
├── test_health.py           # 4 tests health endpoint
├── test_dashboard.py        # 4 tests dashboard overview
├── test_pipelines.py        # 8 tests list + runs
├── test_clusters.py         # 5 tests clusters
├── test_costs.py            # 8 tests summary + by-service
├── test_databases.py        # 6 tests databases
├── test_security.py         # 7 tests security alerts
└── test_governance.py       # 24 tests standard-checks + score + landing-zones
```

---

## Endpoints API

| Route | Méthode | Description |
|---|---|---|
| `/api/v1/health` | GET | Health check + DB probe (SELECT 1) |
| `/api/v1/dashboard/overview` | GET | KPIs agrégés toutes tables |
| `/api/v1/pipelines` | GET | Liste runs filtrée + paginée |
| `/api/v1/pipelines/{name}/runs` | GET | Historique d'exécution d'un pipeline |
| `/api/v1/clusters` | GET | État actuel par compute resource (DISTINCT ON) |
| `/api/v1/costs/summary` | GET | Total + by_cloud + top services |
| `/api/v1/costs/by-service` | GET | Détail par service/account/région |
| `/api/v1/databases` | GET | Santé actuelle par DB (DISTINCT ON) |
| `/api/v1/security/alerts` | GET | Alertes filtrées + paginées |
| `/api/v1/activities` | GET | Activités pipeline filtrées + paginées |
| `/api/v1/users` | GET | Utilisateurs filtrés + paginés |
| `/api/v1/standard-checks` | GET | Évaluations de conformité filtrées + paginées |
| `/api/v1/standard-checks/score` | GET | Score global (%) + breakdown par Landing Zone |
| `/api/v1/landing-zones/details` | GET | LZ actives avec ba_name, région, environnement |

---

## Patterns d'implémentation

### Dependency Injection DB

Le pool est créé au démarrage (lifespan) et stocké sur `app.state.db_pool` :

```python
# app/main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = DatabasePool(settings)
    await pool.connect()
    app.state.db_pool = pool
    yield
    await pool.disconnect()

# app/db/connection.py
def get_db(request: Request) -> DatabasePool:
    return request.app.state.db_pool

# Dans une route
@router.get("/items")
async def list_items(db: Annotated[DatabasePool, Depends(get_db)]):
    rows = await db.fetchall("SELECT * FROM items WHERE ...")
    return [dict(r) for r in rows]
```

### DISTINCT ON — état actuel par entité

Pattern utilisé dans `clusters.py` et `databases.py` :

```sql
SELECT * FROM (
    SELECT DISTINCT ON (cluster_id)
           cluster_id, state, ...
    FROM cluster_metrics
    ORDER BY cluster_id, collected_at DESC  -- garde le plus récent
) latest
WHERE state = 'running'                      -- filtre après déduplication
ORDER BY cluster_name
```

### Filtres dynamiques sécurisés

Construction de la clause WHERE avec paramètres positionnels (pas d'interpolation f-string de valeurs utilisateur) :

```python
conditions: list[str] = []
args: list[Any] = []
idx = 1
if cloud_provider:
    conditions.append(f"cloud_provider = ${idx}")
    args.append(cloud_provider)
    idx += 1
where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
rows = await db.fetchall(f"SELECT ... FROM table {where}", *args)
```

### Health check avec probe DB

```python
@router.get("/health")
async def health_check(db: Annotated[DatabasePool, Depends(get_db)]):
    result = await db.fetchscalar("SELECT 1")
    if result != 1:
        raise HTTPException(503, detail={"status": "degraded", ...})
    return {"status": "ok", "database": "ok"}
```

---

## Variables d'environnement (ECS Task Definition)

| Variable | Description | Défaut |
|---|---|---|
| `DCM_SECRET_NAME` | Secret Secrets Manager (lakebase_password, entra_client_id) | — |
| `DCM_LAKEBASE_HOST` | Host Lakebase replica | `localhost` |
| `DCM_LAKEBASE_PORT` | Port | `5432` |
| `DCM_LAKEBASE_DB` | Nom de la base | `dcm_monitoring` |
| `DCM_LAKEBASE_USER` | Utilisateur DB | `dcm_backend` |
| `DCM_LAKEBASE_MIN_POOL` | Connexions min dans le pool | `2` |
| `DCM_LAKEBASE_MAX_POOL` | Connexions max dans le pool | `10` |
| `DCM_ENTRA_TENANT_ID` | Tenant Entra ID | — |
| `DCM_ALLOWED_ORIGINS` | CORS origins autorisées | `["http://localhost:4000"]` |
| `DCM_ENVIRONMENT` | `production` \| `development` | `development` |

---

## Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

| Fichier | Cas couverts |
|---|---|
| `test_health.py` | DB ok → 200, DB unreachable → 503, SELECT retourne 0 → 503, probe appelé une fois |
| `test_dashboard.py` | Zéro data, agrégats corrects, period dans réponse, filtre cloud_provider |
| `test_pipelines.py` | Réponse vide, sérialisation, pagination, filtres, start_time null, historique pipeline |
| `test_clusters.py` | Réponse vide, sérialisation, filtres cloud/state, multiple clusters |
| `test_costs.py` | Zéro data, total arrondi, by_cloud, by_service, period defaults, filtre, budget_pct null |
| `test_databases.py` | Réponse vide, sérialisation, storage_pct calculé, storage_pct null, filtres, is_available |
| `test_security.py` | Réponse vide, sérialisation, status par défaut, resolved_at, filtres, pagination, dates |
| `test_governance.py` | Standard checks (liste, filtres, pagination), score global + null, breakdown LZ, landing zones (ba_name, filtres) |

**Total : 66 tests** — couverture complète de toutes les routes.

---

## Déploiement

```bash
# Build image
docker build -t dcm-backend:latest .

# Run local (développement)
DCM_LAKEBASE_HOST=localhost DCM_LAKEBASE_PASSWORD=dev \
docker run -p 8080:8080 -e DCM_ENVIRONMENT=development dcm-backend:latest

# Swagger UI (dev uniquement — désactivé en production)
open http://localhost:8080/docs
```

---

## Dépendances

```toml
dependencies = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.30",
    "asyncpg>=0.29",      # driver PostgreSQL async (compatible Lakebase)
    "python-jose[cryptography]>=3.3",  # validation JWT Entra ID
    "pydantic-settings>=2.0",
    "boto3>=1.34",         # Secrets Manager
    "structlog>=24.0",
]
```
