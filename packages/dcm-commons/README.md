# dcm-commons — Shared Library

**Phase :** Phase 1 (implémentée)
**Type :** Package Python partagé (wheel)
**Python :** ≥ 3.12
**Déploiement :** Distribué comme dépendance installée dans chaque composant DCM

---

## Rôle

`dcm-commons` est la bibliothèque partagée dont dépendent **tous** les composants DCM.
Elle fournit les blocs de construction communs afin d'éviter toute duplication de logique
entre les agents Azure, AWS, Lambda, et le backend.

Quatre responsabilités principales :

1. **Modèles de données** — contrat de transport `MetricPayload` + modèles de domaine (Pydantic v2, `frozen=True`)
2. **Authentification** — client Entra ID OAuth2 `client_credentials` avec cache thread-safe
3. **Abstraction collector** — `BaseCollector` avec retry exponentiel et logging corrélé
4. **Client Apigee** — envoi HTTP async avec retry, backoff exponentiel, et gestion d'erreurs

---

## Architecture des modules

```
dcm_commons/
├── __init__.py                    # version = "0.1.0"
├── exceptions.py                  # Hiérarchie d'exceptions DCMError
├── logging_utils.py               # structlog — configure_logging / get_logger
├── models/
│   ├── base_metric.py             # BaseMetricModel (ConfigDict partagé)
│   ├── enums.py                   # Tous les StrEnum DCM (CloudProvider, etc.)
│   ├── payload.py                 # MetricPayload — enveloppe de transport
│   ├── pipeline.py                # PipelineMetric — ADF / Glue / EMR Steps
│   ├── cluster.py                 # ClusterMetric — Databricks / EMR
│   ├── cost.py                    # CostMetric — Cost Management / Cost Explorer
│   ├── database.py                # DatabaseMetric — SQL / Cosmos / RDS / Aurora
│   └── security.py                # SecurityAlert — Defender for Cloud / GuardDuty
├── auth/
│   └── entra_id.py                # EntraIDAuthClient + TokenCredential
├── collectors/
│   └── base.py                    # BaseCollector (ABC) + CollectionResult
└── clients/
    └── apigee.py                  # ApigeeClient (async context manager)
```

---

## Hiérarchie d'exceptions

```
DCMError
├── ConfigurationError(parameter, reason)   — paramètre manquant ou invalide
├── AuthenticationError(reason)             — échec acquisition token Entra ID
├── CollectionError(collector_name, reason) — échec collecte API cloud
└── IngestionError(reason, status_code?)    — échec envoi Apigee (après retries)
```

---

## Référence API

### `MetricPayload`

Enveloppe unique sérialisée par chaque collecteur et désérialisée par l'ingestion Lambda.

| Champ | Type | Description |
|---|---|---|
| `schema_version` | `str` | Version du schéma (défaut `"1.0"`) |
| `collection_run_id` | `str` | UUID v4 auto-généré par run |
| `source_lz_id` | `str` | ID de la landing zone (`"azure-sub-fa5abbc4"`) |
| `cloud_provider` | `CloudProvider` | `azure` ou `aws` |
| `domain` | `MetricDomain` | `pipeline`, `cluster`, `cost`, `database`, `security` |
| `collected_at` | `datetime` | UTC — coercé automatiquement si naive |
| `metrics` | `list[dict]` | Sorties `model_dump()` des modèles de domaine |
| `metadata` | `dict[str,str]` | Contexte libre (région, version collecteur) |
| `metric_count` | `int` (computed) | `len(metrics)` |
| `is_empty` | `bool` (computed) | `True` si aucune métrique |

### Enumerations

| Enum | Valeurs | Propriétés calculées |
|---|---|---|
| `CloudProvider` | `azure`, `aws` | — |
| `MetricDomain` | `pipeline`, `cluster`, `cost`, `database`, `security` | — |
| `PipelineRunStatus` | `succeeded`, `failed`, `running`, `cancelled`, `queued`, `timed_out`, `skipped` | `.is_terminal`, `.is_failure` |
| `TriggerType` | `scheduled`, `manual`, `event`, `dependency`, `unknown` | — |
| `ClusterState` | `running`, `terminated`, `terminating`, `starting`, `restarting`, `error`, `unknown` | `.is_active` |
| `ClusterType` | `databricks`, `emr` | — |
| `DatabaseType` | `postgresql`, `mysql`, `sqlserver`, `cosmos_db`, `rds_aurora`, `redshift` | — |
| `AlertSeverity` | `high`, `medium`, `low`, `informational` | `.requires_immediate_action` |
| `AlertStatus` | `active`, `in_progress`, `resolved`, `dismissed` | — |

### `EntraIDAuthClient`

```python
auth = EntraIDAuthClient(
    tenant_id="329e91b0-…",
    client_id="4d96093b-…",
    client_secret=os.environ["DCM_CLIENT_SECRET"],
    scope="api://4d96093b-…/.default",
    expiry_buffer_seconds=60,   # défaut
)
token = auth.get_token()   # thread-safe, avec cache
```

- Token mis en cache jusqu'à `expires_in - buffer_seconds`
- `threading.Lock` → safe pour usage multi-thread
- `get_token()` lève `AuthenticationError` (jamais `RuntimeError`)

### `BaseCollector`

```python
class MyCollector(BaseCollector):
    @property
    def domain(self) -> MetricDomain:
        return MetricDomain.PIPELINE

    async def _collect_metrics(self) -> list[dict[str, Any]]:
        runs = await self._client.list_runs()
        return [PipelineMetric(...).model_dump() for run in runs]

collector = MyCollector(
    source_lz_id="azure-sub-fa5abbc4",
    cloud_provider=CloudProvider.AZURE,
    max_retries=3,
    retry_base_delay_seconds=2.0,
)
result: CollectionResult = await collector.collect()
# result.payload     → MetricPayload prêt à envoyer
# result.duration_ms → temps de collecte en ms
# result.collector_name → "MyCollector"
```

- Retry exponentiel sur `CollectionError` : 2 s → 4 s → 8 s (configurable)
- Logging structuré avec `collection_run_id` bindé via `structlog.contextvars`
- `clear_contextvars()` garanti en `finally` même en cas d'erreur

### `ApigeeClient`

```python
async with ApigeeClient(
    apigee_base_url="https://api.example.com/dcm",
    auth_client=auth,
    api_key=os.environ["DCM_API_KEY"],
    timeout=30.0,
    max_retries=3,
    retry_base_delay_seconds=2.0,
) as client:
    await client.send(payload)
    stats = await client.send_batch(payloads)
    # stats = {"success": N, "failure": M}
```

- Un seul `httpx.AsyncClient` (connection pooling) pour toute la durée de vie
- Retry sur 429, 5xx, erreurs réseau — pas de retry sur 4xx (non retriable)
- `IngestionError` levée après épuisement des retries

### `configure_logging` / `get_logger`

```python
from dcm_commons.logging_utils import configure_logging, get_logger, bind_contextvars

# À l'initialisation du composant (une seule fois)
configure_logging("dcm-azure-collector", level="INFO")

# Dans chaque module
logger = get_logger(__name__)
logger.info("collection_started", domain="pipeline", lz="azure-sub-fa5abbc4")

# Corrélation async
bind_contextvars(collection_run_id="…", cloud_provider="azure")
logger.info("event")   # inclut run_id automatiquement
```

- JSON en production (`DCM_ENV=production` ou non-TTY)
- ConsoleRenderer coloré en développement (TTY)

---

## Installation

```bash
# Mode développement (éditable)
cd solution/dcm-commons
pip install -e ".[dev]"

# Comme dépendance dans un autre composant
pip install -e "../dcm-commons"   # développement local
# ou via wheel en CI/CD
pip install dcm_commons-0.1.0-py3-none-any.whl
```

---

## Tests

```bash
cd solution/dcm-commons
pip install -e ".[dev]"
pytest tests/ -v

# Avec couverture
pytest tests/ --cov=dcm_commons --cov-report=term-missing
```

| Fichier test | Couvre |
|---|---|
| `test_payload.py` | Enums, `MetricPayload`, tous les modèles de domaine |
| `test_entra_id.py` | `EntraIDAuthClient` — cache, expiry, erreurs MSAL, thread safety |
| `test_base_collector.py` | `BaseCollector` — succès, retry, backoff, propagation erreurs |
| `test_apigee_client.py` | `ApigeeClient` — HTTP 2xx/4xx/5xx, retry, send_batch, context manager |

---

## Dépendances

| Package | Version | Usage |
|---|---|---|
| `pydantic` | `>=2.7` | Modèles et validation |
| `msal` | `>=1.31` | Entra ID OAuth2 client_credentials |
| `httpx` | `>=0.27` | Client HTTP async (Apigee) |
| `structlog` | `>=24.4` | Logging structuré JSON / console |
| `tenacity` | `>=9.0` | Retry / backoff (disponible pour usage dans collecteurs) |

**Dev uniquement :**

| Package | Usage |
|---|---|
| `pytest` + `pytest-asyncio` | Tests async |
| `pytest-mock` | Mocking MSAL, services cloud |
| `respx` | Mocking appels `httpx` |
| `freezegun` | Gel du temps pour tests d'expiry token |
| `ruff` | Linter + formatter |
| `mypy` | Type-checker strict (`pydantic.mypy` plugin) |

---

## Décisions de design

| Décision | Justification |
|---|---|
| `frozen=True` sur `BaseMetricModel` | Immutabilité → hashable, safe multi-thread, pas de mutation accidentelle |
| `use_enum_values=True` | `model_dump()` produit des strings sans appels `.value` explicites |
| `StrEnum` (Python 3.11+) | `PipelineRunStatus.FAILED == "failed"` → filtres SQL et comparaisons transparents |
| `threading.Lock` dans `EntraIDAuthClient` | MSAL est synchrone — le lock serialise les refresh concurrents |
| `httpx.AsyncClient` réutilisé | Évite la création d'une session TLS à chaque appel (anti-pattern majeur) |
| Retry 4xx non retriable | Un même payload rejeté le sera toujours — pas de retry inutile |
| `clear_contextvars()` dans `finally` | Garantit la propreté des contextvars même en cas d'exception |
