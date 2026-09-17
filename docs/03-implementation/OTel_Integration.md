***

# Guide Complet d’Intégration OpenTelemetry pour  Architecture Cloud Data KPI

> **Note 2026-05-27 :** les passages qui mentionnent Lakebase/Postgres décrivent l'ancienne cible de lecture backend. L'implémentation actuelle lit Unity Catalog via Databricks SQL Warehouse. Voir [`../MIGRATION-LAKEBASE-TO-WAREHOUSE.md`](../MIGRATION-LAKEBASE-TO-WAREHOUSE.md).

## Introduction

Ce document décrit l’intégration d’OpenTelemetry (OTel) dans votre architecture : agents Python sur landing zones Azure/AWS → API centrale → Event Hubs → Databricks/Lakebase → Postgres → backend FastAPI → dashboard React. OTel fournit traces, métriques et logs end-to-end, de manière **vendor-agnostique**, avec export possible vers Azure Monitor, AWS X-Ray, Grafana/Jaeger, Prometheus, etc.[^1][^2]

### Bénéfices principaux

- Visibilité distribuée sur les scans KPI (du call API dans la LZ jusqu’à l’affichage React).[^2]
- Détection des latences et goulots d’étranglement (par ex. API → Event Hubs, Event Hubs → Databricks, Postgres → FastAPI).[^3]
- Optimisation FinOps via des métriques sur le volume d’appels API, la latence, les erreurs, et la charge sur les services cloud.[^2]
- Alignement DevSecOps : standardisation de la télémétrie, sampling pour réduire le coût, redaction des données sensibles dans les traces.[^4]

***

## Architecture OTel – Vue d’ensemble

```mermaid
graph TD
    subgraph "Landing Zones (Azure/AWS)"
        A1[Agents Python<br/>Scan APIs Data/FinOps]
    end
    subgraph "Central App"
        API[API centrale<br/>ingestion]
        EH[Event Hubs]
        DBX[Databricks<br/>Lakebase]
        PG[Postgres]
        FAST[FastAPI Backend]
        REACT[React Dashboard]
    end
    COL[OTel Collector Central]
    BACK[Backend Observability<br/>Azure Monitor / X-Ray / Grafana / Jaeger]

    A1 -. OTLP .-> COL
    API -. OTLP .-> COL
    EH -. Receiver .-> COL
    DBX -. Native OTel .-> COL
    PG -. Instrumentation .-> FAST -. OTLP .-> COL
    REACT -. Web SDK .-> COL
    COL --> BACK

    style COL fill:#f9f
```

Principe : chaque composant émet des traces/métriques en OTLP vers un **OTel Collector** central, qui route ensuite vers les backends (Azure Monitor, X-Ray, Jaeger, etc.).[^5]

***

## 1. Prérequis

- Python 3.8+ pour les agents et la partie API si en Python.[^6]
- FastAPI (version récente, par ex. 0.100+).[^7]
- React 18+ ou équivalent pour le frontend.[^8]
- Accès réseau de tous les composants vers le Collector (port 4317/4318).
- Droits Azure (Azure Monitor, Event Hubs) et AWS (X-Ray / ADOT) selon besoins.[^9][^10]

***

## 2. OTel Collector central (priorité 1)

Le Collector est le cœur de l’architecture OTel : il reçoit OTLP des agents, API, FastAPI, React, et peut aussi se connecter à Event Hubs.[^11][^5]

### Exemple docker-compose

```yaml
version: "3"
services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    command: ["--config=/etc/otel-collector-config.yaml"]
    volumes:
      - ./otel-collector-config.yaml:/etc/otel-collector-config.yaml
    ports:
      - "4317:4317"   # OTLP gRPC
      - "4318:4318"   # OTLP HTTP
```


### Exemple `otel-collector-config.yaml` (multi-cloud, simplifié)

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

  azureeventhubs: {}  # Si vous voulez consommer de l’Event Hubs côté Collector

processors:
  batch: {}
  memory_limiter:
    limit_mib: 512
  # Exemple de processor de filtrage/redaction
  attributes/scrub:
    actions:
      - key: user.email
        action: delete
      - key: kpi.value
        action: delete

exporters:
  logging:
    verbosity: detailed

  # Azure Monitor
  azuremonitor: {}   # Config détaillée côté Azure Monitor OTel distro[web:32]

  # AWS X-Ray
  awsxray: {}        # Utilisé avec AWS Distro for OTel[web:7][web:26]

  # Traces vers Jaeger/Grafana Tempo éventuels
  otlp/jaeger:
    endpoint: jaeger:4317
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp, azureeventhubs]
      processors: [memory_limiter, batch, attributes/scrub]
      exporters: [logging, azuremonitor, awsxray, otlp/jaeger]

    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [logging]
```


***

## 3. Agents Python sur Landing Zones (Azure / AWS)

Les agents scannent des APIs data et FinOps, puis envoient les KPI à votre API centrale. On instrumente :

- Les appels sortants vers les services cloud (Azure SDK, boto3, REST).
- Le code métier de scan (spans personnalisés).
- L’envoi vers l’API centrale avec propagation du **trace context**.[^12][^13][^6]


### Dépendances typiques

```text
opentelemetry-distro
opentelemetry-exporter-otlp-proto-http
azure-monitor-opentelemetry      # pour LZ Azure[web:32]
opentelemetry-instrumentation-requests
opentelemetry-instrumentation-urllib
```


### Auto-instrumentation (zero-code)

```bash
export OTEL_SERVICE_NAME=agent-azure-lz1
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf

# Active l’auto-instrumentation
python -m opentelemetry.distro -a install

# Puis lancer l’agent
python your_agent.py
```


### Exemple de span "scan KPI" + propagation trace

```python
from opentelemetry import trace
from opentelemetry.propagate import inject
import requests

tracer = trace.get_tracer(__name__)

def send_to_central_api(payload: dict):
    headers = {}
    inject(headers)  # ajoute le header traceparent
    requests.post("https://central-api/ingest", json=payload, headers=headers)

def run_scan():
    with tracer.start_as_current_span("scan-kpi-lz"):
        # appels vers Azure/AWS (auto-tracés si libs instrumentées)
        kpis = collect_kpis_from_cloud()
        send_to_central_api({"kpis": kpis})
```


***

## 4. API centrale (ingestion des agents)

Supposons que l’API soit en FastAPI (sinon principe similaire avec Starlette/Flask).[^14][^7]

### Dépendances

```text
fastapi
uvicorn

opentelemetry-sdk
opentelemetry-exporter-otlp-proto-http
opentelemetry-instrumentation-fastapi
opentelemetry-instrumentation-requests  # pour l’envoi vers Event Hubs, si HTTP
```


### Initialisation OTel + FastAPI

```python
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPTraceExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

resource = Resource.create({"service.name": "central-api"})

provider = TracerProvider(resource=resource)
exporter = OTLPTraceExporter(endpoint="http://otel-collector:4318/v1/traces", insecure=True)
provider.add_span_processor(BatchSpanProcessor(exporter))
trace.set_tracer_provider(provider)

app = FastAPI()
FastAPIInstrumentor.instrument_app(app)
tracer = trace.get_tracer(__name__)
```


### Endpoint d’ingestion avec span métier

```python
from pydantic import BaseModel

class IngestPayload(BaseModel):
    kpis: dict

@app.post("/ingest")
async def ingest(payload: IngestPayload):
    with tracer.start_as_current_span("ingest-kpi-from-agent"):
        # Ici on peut publier dans Event Hubs
        # event_hubs_client.send(payload.json())
        return {"status": "ok"}
```

Les traces des agents sont propagées via `traceparent` et la route FastAPI est auto-instrumentée.[^7][^14]

***

## 5. Event Hubs → Databricks / Lakebase

Deux options principales pour la télémétrie autour d’Event Hubs :

1. **Instrumentation côté producteur/consommateur** (API centrale, Databricks) — le Collector n’a pas besoin du receiver `azureeventhubs`.[^11]
2. Utiliser un receiver Event Hubs dans le Collector pour traiter certains messages.

### Databricks

Databricks supporte OTel pour exporter la télémétrie de notebooks/jobs vers un endpoint OTLP.[^15][^16]

- Configurez un endpoint OTLP (Collector) comme target d’export.
- Ajoutez des spans autour des jobs qui consomment Event Hubs et alimentent Lakebase (Delta/Lakehouse).

***

## 6. Backend FastAPI connecté à Postgres

Ce backend lit Postgres (Lakebase) et sert des KPI au dashboard React. On veut :

- Tracer les requêtes HTTP entrantes (FastAPI).
- Tracer les requêtes SQL (SQLAlchemy/psycopg/Postgres).[^17][^14]
- Propager le trace context vers React (via headers, par ex. b3 ou W3C).


### Dépendances

```text
opentelemetry-instrumentation-fastapi
opentelemetry-instrumentation-psycopg2  # ou sqlalchemy selon votre stack
opentelemetry-exporter-otlp-proto-http
```


### Exemple d’instrumentation SQLAlchemy

```python
from sqlalchemy import create_engine
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

engine = create_engine("postgresql+psycopg2://user:pass@host/db")
SQLAlchemyInstrumentor().instrument(engine=engine)
```

Les requêtes vers Postgres seront automatiquement associées aux spans FastAPI.[^17]

***

## 7. Dashboard React (frontend utilisateur)

Objectif : tracer les actions utilisateur et les appels HTTP vers le backend, puis les envoyer au Collector.[^18][^8]

### Dépendances (exemple)

```json
"@opentelemetry/api": "^1.9.0",
"@opentelemetry/sdk-trace-web": "^1.25.0",
"@opentelemetry/exporter-trace-otlp-http": "^0.52.0",
"@opentelemetry/instrumentation-fetch": "^0.52.0"
```


### Fichier `otel.js`

```js
import { WebTracerProvider } from '@opentelemetry/sdk-trace-web';
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { FetchInstrumentation } from '@opentelemetry/instrumentation-fetch';

const provider = new WebTracerProvider();
const exporter = new OTLPTraceExporter({
  url: 'http://otel-collector:4318/v1/traces'
});

provider.addSpanProcessor(new BatchSpanProcessor(exporter));
provider.register();

new FetchInstrumentation({
  propagateTraceHeaderCorsUrls: [/central-backend/],
});
```

Ensuite, importez `./otel` dans votre `index.tsx` ou `App.tsx` pour initialiser avant le rendu React.[^8][^18]

***

## 8. Diagramme de flux de traces

```mermaid
sequenceDiagram
    participant A as Agent (LZ)
    participant API as API centrale
    participant EH as Event Hubs
    participant DBX as Databricks
    participant FAST as FastAPI backend
    participant PG as Postgres
    participant R as React
    participant COL as OTel Collector

    A->>API: POST /ingest (traceparent)
    API->>EH: Publish event
    API->>COL: OTLP traces

    EH->>DBX: Event stream
    DBX->>PG: Write KPI to Lakebase
    DBX->>COL: OTLP traces

    R->>FAST: GET /kpi (trace web)
    FAST->>PG: SELECT KPI
    FAST->>COL: OTLP traces
    R->>COL: OTLP web traces
```


***

## 9. Monitoring, alertes et FinOps

- **Backends possibles** : Azure Monitor, AWS X-Ray, Jaeger/Grafana Tempo, Prometheus pour les métriques.[^19][^5]
- **Métriques utiles** : latence p95/p99 des scans, taux d’erreur par LZ, nombre d’appels API par type de service (Databricks, Data Factory, EMR).[^2]
- **Dimensions FinOps** : ajoutez des attributes comme `cloud.provider`, `service.type`, `cost.estimate` dans les spans pour corréler coût et volumétrie.[^2]

***

## 10. Best practices DevSecOps

- **Sampling** : start simple avec un sampling 1–10 %, augmentez en cas d’incident ; utilisez tail-based sampling si vous déployez un collector avancé.[^2]
- **Redaction PII** : processeur `attributes` pour supprimer user IDs, emails, valeurs KPI sensibles.[^4]
- **CI/CD** : validez que l’OTEL_EXPORTER_OTLP_ENDPOINT pointe vers l’environnement correct (dev/stage/prod).
- **Tests** : script de smoke test qui exécute un scan complet et vérifie via Jaeger qu’un trace complet existe.

***
Les flux OpenTelemetry s’ajoutent à ton architecture comme des **flux techniques parallèles** : tu gardes exactement les mêmes appels métier, et tu ajoutes des appels OTLP des composants vers un ou plusieurs Collectors. L’impact principal est réseau (trafic OTLP en plus), CPU/RAM léger dans chaque service (SDK OTel) et l’ajout d’un ou plusieurs services Collector à opérer.

## Impact concret sur l'architecture actuelle

- **Agents Python LZ**
    
    - Ajout de lib OTel + envoi OTLP vers Collector (HTTP/gRPC) en plus des appels vers les APIs cloud et ton API centrale.
        
    - Overhead modéré (quelques % CPU et un peu de RAM) si tu utilises batch + sampling.
        
- **API centrale**
    
    - Instrumentation FastAPI / framework + export OTLP vers Collector.
        
    - Pas de changement dans la manière dont les agents l’appellent, seulement des spans créés autour des routes.
        
- **Event Hubs / Databricks**
    
    - Option 1 : instrumentation côté Databricks + backend (OTLP vers Collector).
        
    - Option 2 : un Collector peut aussi se connecter à Event Hubs si tu veux traiter certains messages comme signal télémétrie (moins fréquent).
        
- **Backend FastAPI + Postgres**
    
    - Auto-instrumentation FastAPI + SQL (SQLAlchemy/psycopg) et export OTLP vers Collector.
        
    - Aucune modification de ton schéma Postgres.
        
- **React dashboard**
    
    - Ajout d’un SDK OTel Web qui envoie les traces au Collector (via HTTP), en parallèle des fetch vers ton backend.
        
- **Nouvelle brique**
    
    - Un ou plusieurs **OpenTelemetry Collector(s)** (gateway central + éventuellement agents locaux) à déployer, monitorer et scaler.
        

## Nouveaux flux à ajouter (vue globale)

Voici un schéma Mermaid de ton architecture **mise à jour** avec la couche OTel (flux métier + flux télémétrie séparés) :

```mermaid
graph TD
    %% Composants métier
    subgraph "Landing Zones -Azure/AWS-"
        AG[Agents Python\nScan APIs Data/FinOps]
        AZ[Services Data/FinOps Azure]
        AW[Services Data/FinOps AWS]
    end

    subgraph "Central App"
        API[API centrale\n-ingestion KPIs-]
        EH[Event Hubs]
        DBX[Databricks\nLakebase]
        PG[Postgres]
        FAST[Backend FastAPI]
        REACT[React Dashboard]
    end

    subgraph "Observability"
        COL[OTel Collector Gateway]
        OBS[Backends Observability\nAzure Monitor / X-Ray / Jaeger]
    end

    %% Flux métier existants
    AG --> AZ
    AG --> AW
    AG --> API
    API --> EH
    EH --> DBX
    DBX --> PG
    FAST --> PG
    REACT --> FAST

    %% Flux télémétrie (OTLP / Observability)
    AG -. OTLP traces/metrics .-> COL
    API -. OTLP traces .-> COL
    DBX -. OTLP traces .-> COL
    FAST -. OTLP traces/metrics .-> COL
    REACT -. OTLP web traces .-> COL
    COL --> OBS

```


## Détail des flux télémétrie à ajouter

- **Agents Python → Collector**
    
    - OTLP HTTP/gRPC vers `http://otel-collector:4318` ou `:4317` pour traces/métriques/logs.
        
- **API centrale → Collector**
    
    - OTLP export des traces créées autour des endpoints `/ingest`, etc.
        
- **Databricks → Collector**
    
    - Export OTel natif ou via job config → endpoint OTLP du Collector.
        
- **Backend FastAPI → Collector**
    
    - OTLP traces (HTTP + SQL) + éventuellement métriques (latence, 5xx).
        
- **React → Collector**
    
    - OTLP HTTP pour les traces web (navigation, fetch, events).
        
- **Collector → Backends d’observabilité**
    
    - OTLP ou exporters natifs vers Azure Monitor, AWS X-Ray, Jaeger/Tempo, Prometheus, etc.
        

## Variante : patterns de déploiement Collector

Tu peux garder ça simple au début avec **un seul Collector gateway** (comme sur le schéma).  
Plus tard, pour scaler/multi-cloud :

- Collector **agent** proche des workloads (par node/VM ou sidecar).
    
- Ces collectors agents envoient vers un Collector **gateway** central multi-cloud qui fait sampling/filtrage/export multi backends.




##  Architecture avec flux métier vs télémétrie


```mermaid
flowchart LR
    %% Composants
    subgraph LZ["Landing Zones - Azure / AWS- "]
        AG["Agents Python\n- scan APIs Data/FinOps- "]
        AZ["Services Azure\n- Data, FinOps- "]
        AW["Services AWS\n- Data, FinOps- "]
    end

    subgraph CENTRAL["Application centrale"]
        API["API centrale\n- ingestion KPIs- "]
        EH["Event Hubs"]
        DBX["Databricks\n- Lakebase / Delta- "]
        PG["Postgres\n- Lakebase DB- "]
        FAST["Backend FastAPI"]
        REACT["React Dashboard"]
    end

    subgraph OBS["Observability layer"]
        COL["OTel Collector\n- gateway central- "]
        OBSBK["Backends Obs.\nAzure Monitor / X-Ray / Jaeger"]
    end

    %% FLUX METIER - plein- 
    AG --> AZ
    AG --> AW
    AG --> API
    API --> EH
    EH --> DBX
    DBX --> PG
    FAST --> PG
    REACT --> FAST

    %% FLUX TELEMETRIE - pointillés- 
    AG -. "OTLP traces/metrics" .-> COL
    API -. "OTLP traces" .-> COL
    DBX -. "OTLP traces" .-> COL
    FAST -. "OTLP traces/metrics" .-> COL
    REACT -. "OTLP web traces" .-> COL
    COL --> OBSBK

```




- **Traits pleins** = flux métier existants (tu ne touches pas).
    
- **Traits pointillés** = flux **nouveaux** liés à OpenTelemetry (OTLP).
    

---

## 2. Ce que on dois ajouter par composant

### 2.1. OTel Collector (obligatoire, 1er à mettre en place)

- **Nouveau service** (Docker, VM ou K8s) accessible depuis : agents, API, FastAPI, Databricks, React (ou via ingress).
- Ports à ouvrir :
    - 4317 (OTLP gRPC, optionnel mais conseillé).
    - 4318 (OTLP HTTP).
- Fichier `otel-collector-config.yaml` avec :
    - `receivers: otlp`
    - `processors: batch (+ éventuellement filters/redaction)`
    - `exporters` vers Azure Monitor / X‑Ray / Jaeger / Prometheus, selon ce que tu veux utiliser.

L’impact : **un nouveau flux** de chaque composant vers `http(s)://otel-collector:4317/4318`.

***

### 2.2. Agents Python (LZ Azure / AWS)

À ajouter :

- Dépendances OTel dans l’image/venv :
    - `opentelemetry-distro`
    - `opentelemetry-exporter-otlp-proto-http`
    - `azure-monitor-opentelemetry` (si tu veux envoyer aussi vers Azure direct côté LZ Azure, optionnel).
- Variables d’environnement (exemple) :
    - `OTEL_SERVICE_NAME=agent-azure-lz1`
    - `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318`
    - `OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf`
- Commande de lancement modifiée (auto‑instrumentation) :
    - `python -m opentelemetry.distro -a install` (dans l’image ou au démarrage)
    - puis `python your_agent.py`

**Flux ajouté** :

- Agents → Collector : OTLP (traces/métriques) en plus des appels actuels vers ton API centrale.

***

### 2.3. API centrale (ingestion)

À ajouter :

- Dépendances :
    - `opentelemetry-sdk`
    - `opentelemetry-exporter-otlp-proto-http`
    - `opentelemetry-instrumentation-fastapi` (ou équivalent pour ton framework).
- Init OTel dans l’API :
    - Création d’un `TracerProvider` avec `Resource(service.name="central-api")`.
    - `BatchSpanProcessor` + `OTLPTraceExporter(endpoint="http://otel-collector:4318/v1/traces", insecure=True)`.
    - `FastAPIInstrumentor.instrument_app(app)`.

**Flux ajouté** :

- API → Collector : OTLP traces pour chaque requête / route + spans custom métier.

***

### 2.4. Event Hubs / Databricks

Tu as deux niveaux possibles :

1. **Simple (suffisant au début)**
    - Tu instrumentes uniquement Databricks (jobs / notebooks) avec un exporter OTLP vers le Collector.
    - Les traces couvrent : lecture Event Hubs, transformations, écriture Lakebase/Postgres.
2. **Évolué**
    - Tu ajoutes un receiver `azureeventhubs` dans le Collector pour traiter certains messages comme télémétrie (rarement nécessaire au début).

**Flux ajouté (cas simple)** :

- Databricks → Collector : OTLP traces.

***

### 2.5. Backend FastAPI (lecture Postgres / Lakebase)

À ajouter :

- Dépendances :
    - `opentelemetry-instrumentation-fastapi`
    - `opentelemetry-instrumentation-psycopg2` ou `opentelemetry-instrumentation-sqlalchemy`
    - `opentelemetry-exporter-otlp-proto-http`.
- Init OTel (similaire à l’API centrale) :
    - `service.name=backend-kpi`
    - exporter OTLP vers Collector.
    - Instrumentation FastAPI + SQL (SQLAlchemyInstrumentor ou psycopg).

**Flux ajouté** :

- FastAPI → Collector : OTLP traces (requêtes HTTP utilisateurs + requêtes SQL) + éventuellement métriques (latence, erreurs).

***

### 2.6. React Dashboard

À ajouter :

- Dépendances npm :
    - `@opentelemetry/api`
    - `@opentelemetry/sdk-trace-web`
    - `@opentelemetry/exporter-trace-otlp-http`
    - `@opentelemetry/instrumentation-fetch` (ou XHR).
- Fichier `otel.ts` / `otel.js` qui :
    - crée un `WebTracerProvider`,
    - ajoute un `BatchSpanProcessor` + `OTLPTraceExporter({ url: 'http(s)://otel-collector:4318/v1/traces' })`,
    - active `FetchInstrumentation`.
- Import de ce fichier **avant** le rendu React (ex : dans `index.tsx`).

**Flux ajouté** :

- React → Collector : OTLP web traces (navigation, appels fetch vers FastAPI, events UI).

***

## 3. Résumé rapide des flux nouveaux (à comparer à ton existant)

- **Agents Python → OTel Collector** (OTLP)
- **API centrale → OTel Collector** (OTLP)
- **Databricks → OTel Collector** (OTLP)
- **Backend FastAPI → OTel Collector** (OTLP)
- **React → OTel Collector** (OTLP)
- **OTel Collector → Azure Monitor / X‑Ray / Jaeger / …** (exporters spécifiques)
