# dcm-lambda-ingestion — Lambda Ingestion API

**Phase roadmap :** Phase 4
**Statut :** ✅ Implémenté
**Type :** Fonction AWS Lambda Python (Building Block API_1)
**Trigger :** API Gateway (internal) via VPC Lattice, appelé par Apigee
**Région :** eu-west-1 (DCM Core account)
**Entry point :** `lambda_ingestion.handler.handler`

---

## Rôle

Point d'entrée des payloads de métriques dans le système DCM.

1. Reçoit les `MetricPayload` JSON depuis Apigee via VPC Lattice (mTLS)
2. Valide le schéma avec Pydantic v2 (`MetricPayload.model_validate`)
3. Publie dans SQS avec attributs de message (`domain`, `cloud_provider`, `source_lz_id`)
4. Retourne `202 Accepted` avec le `collection_run_id`

---

## Architecture

```
Apigee (Corporate DMZ)
      │
      │ VPC Lattice (mTLS) — Apigee valide le JWT Entra ID ici
      ▼
API Gateway (internal) — aucune auth supplémentaire
      │
      ▼
Lambda dcm-lambda-ingestion
      │
      ├── _parse_body()      — decode JSON body (str ou dict)
      ├── validate_payload() — Pydantic MetricPayload.model_validate()
      └── SQSPublisher.publish()
                │
                ▼
          SQS Queue (dcm-metrics-queue)
                │
                └── DLQ (dcm-metrics-dlq) — messages non traités après max retries
```

---

## API

**POST** `<internal-api-gw>/v1/metrics/ingest`

### Corps de la requête

JSON conforme à `MetricPayload` (schéma défini dans `dcm-commons`) :

```json
{
  "collection_run_id": "uuid-v4",
  "source_lz_id": "aws-account-551656632516",
  "cloud_provider": "aws",
  "domain": "pipeline",
  "collected_at": "2026-03-19T10:00:00Z",
  "metrics": [...]
}
```

### Réponses

| Code | Condition | Corps |
|---|---|---|
| `202` | Payload valide, enqueué | `{"run_id": "<uuid>", "status": "accepted"}` |
| `400` | Body absent, JSON invalide, ou échec Pydantic | `{"error": "<détail>"}` |
| `500` | SQS inaccessible, env mal configuré | `{"error": "internal server error"}` |

---

## Structure du code

```
lambda_ingestion/
├── __init__.py       # __version__ = "0.1.0", docstring module
├── handler.py        # Entrypoint Lambda — parse → validate → publish → respond
├── validator.py      # validate_payload() — wrap Pydantic ValidationError → ValueError
└── sqs_publisher.py  # SQSPublisher — model_dump_json() + MessageAttributes

tests/
├── __init__.py
├── test_handler.py        # Tests complets handler (202/400/500, singleton, headers)
├── test_validator.py      # Tests validate_payload (success, ValidationError, propagation)
└── test_sqs_publisher.py  # Tests avec moto + unittest.mock
```

---

## Patterns d'implémentation

### Singleton publisher (cold-start optimisation)

```python
_publisher: SQSPublisher | None = None

def _get_publisher() -> SQSPublisher:
    global _publisher
    if _publisher is None:
        _publisher = SQSPublisher(queue_url=os.environ["SQS_QUEUE_URL"])
    return _publisher
```

Le client boto3 SQS est créé **une seule fois** par cold start.
Les invocations warm réutilisent la connexion TCP poolée.

### Parsing du body

API Gateway peut passer le body en `str` (cas standard) ou en `dict` (cas
pre-décodé par certains integrateurs VPC Lattice) :

```python
def _parse_body(event):
    raw = event.get("body")          # None → ValueError "missing"
    if isinstance(raw, dict):
        return raw                   # déjà décodé
    return json.loads(raw)           # JSONDecodeError → ValueError
```

### Validation Pydantic → ValueError propre

```python
def validate_payload(raw):
    try:
        return MetricPayload.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"Payload validation failed: {exc.error_count()} error(s)") from exc
```

Le `ValidationError` de Pydantic n'est pas renvoyé brut au client pour éviter
d'exposer des détails de schéma internes.

### MessageAttributes SQS

Chaque message est enrichi d'attributs de routage `String` pour permettre
aux filter policies SQS ou au consumer Databricks de trier sans désérialiser
le body complet :

```python
MessageAttributes={
    "domain":         {"DataType": "String", "StringValue": str(payload.domain)},
    "cloud_provider": {"DataType": "String", "StringValue": str(payload.cloud_provider)},
    "source_lz_id":   {"DataType": "String", "StringValue": payload.source_lz_id},
}
```

---

## Variables d'environnement Lambda

| Variable | Obligatoire | Description |
|---|---|---|
| `SQS_QUEUE_URL` | ✅ | URL complète de la queue SQS principale |

---

## Messages SQS publiés

| Champ | Source |
|---|---|
| **Body** | `payload.model_dump_json()` — JSON Pydantic sérialisé (dates ISO 8601, enums valeur string) |
| **domain** | `payload.domain` — `"pipeline"`, `"cluster"`, `"cost"`, `"database"` |
| **cloud_provider** | `payload.cloud_provider` — `"azure"`, `"aws"` |
| **source_lz_id** | `payload.source_lz_id` — identifiant opaque de la LZ |

---

## Tests

| Fichier | Cas couverts |
|---|---|
| `test_validator.py` | valid → MetricPayload, ValidationError → ValueError avec error count, non-ValidationError propagé |
| `test_sqs_publisher.py` | MessageId retourné, body JSON valide, MessageAttributes corrects, DataType=String, propagation exceptions SQS |
| `test_handler.py` | 202 happy path, body absent → 400, JSON invalide → 400, Pydantic failure → 400, SQS error → 500, dict body accepté, singleton créé une fois, Content-Type header |

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

---

## IAM Lambda Role (permissions minimales)

| Service | Action | Ressource |
|---|---|---|
| SQS | `sqs:SendMessage` | ARN queue `dcm-metrics-queue` |
| CloudWatch Logs | `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents` | Log group Lambda |

---

## Déploiement

```bash
# Package zip (Lambda runtime)
pip install -t package/ -r requirements.txt
cp -r lambda_ingestion/ package/
cd package && zip -r ../dcm-lambda-ingestion.zip .

# Upload via AWS CLI
aws lambda update-function-code \
  --function-name dcm-lambda-ingestion \
  --zip-file fileb://dcm-lambda-ingestion.zip
```

---

## Dépendances

```toml
dependencies = ["boto3>=1.34", "dcm-commons"]

[dev]
moto[sqs]>=5.0      # mock SQS pour tests
boto3-stubs[sqs]    # type hints boto3
pytest>=8.0
```
