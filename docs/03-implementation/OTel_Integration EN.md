# End‑to‑End OpenTelemetry Integration Guide for the Cloud Data KPI Architecture

> **2026-05-27 note:** references to Lakebase/Postgres describe the previous backend read target. The current implementation reads Unity Catalog through Databricks SQL Warehouse. See [`../MIGRATION-LAKEBASE-TO-WAREHOUSE.md`](../MIGRATION-LAKEBASE-TO-WAREHOUSE.md).

## Introduction

This document describes how to integrate OpenTelemetry (OTel) into your existing architecture: Python agents on Azure/AWS landing zones → central API → Event Hubs → Databricks/Lakebase → Postgres → FastAPI backend → React dashboard.  
OTel provides end‑to‑end **vendor‑agnostic** traces, metrics, and logs, with the ability to export to Azure Monitor, AWS X‑Ray, Grafana/Jaeger, Prometheus, and others.

### Key benefits

- Distributed visibility on KPI scans (from the API call in the landing zone all the way to the React display).  
- Detection of latency and bottlenecks (for example API → Event Hubs, Event Hubs → Databricks, Postgres → FastAPI).  
- FinOps optimization using metrics on API call volume, latency, errors, and load on cloud services.  
- DevSecOps alignment: standardized telemetry, sampling to control cost, and redaction of sensitive data in traces.  

---

## OTel architecture – high‑level view

```mermaid
graph TD
    subgraph "Landing Zones (Azure/AWS)"
        A1[Python Agents<br/>Scan Data/FinOps APIs]
    end
    subgraph "Central App"
        API[Central API<br/>ingestion]
        EH[Event Hubs]
        DBX[Databricks<br/>Lakebase]
        PG[Postgres]
        FAST[FastAPI Backend]
        REACT[React Dashboard]
    end
    COL[Central OTel Collector]
    BACK[Observability Backends<br/>Azure Monitor / X-Ray / Grafana / Jaeger]

    A1 -. OTLP .-> COL
    API -. OTLP .-> COL
    EH -. Receiver .-> COL
    DBX -. Native OTel .-> COL
    PG -. Instrumentation .-> FAST -. OTLP .-> COL
    REACT -. Web SDK .-> COL
    COL --> BACK

    style COL fill:#f9f
```
Idea: each component emits OTLP traces/metrics to a central OTel Collector, which then routes them to your backends (Azure Monitor, X‑Ray, Jaeger, etc.).

1. Prerequisites
Python 3.8+ for the agents and the API part if written in Python.

FastAPI (recent version, e.g. 0.100+).

React 18+ (or equivalent framework) for the frontend.

Network access from all components to the Collector (ports 4317/4318).

Azure permissions (Azure Monitor, Event Hubs) and AWS permissions (X‑Ray / ADOT) as needed.

2. Central OTel Collector (priority 1)
The Collector is the core of the OTel architecture: it receives OTLP data from the agents, the central API, FastAPI backend, React frontend, and can also connect to Event Hubs.

Example docker-compose
text
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
Example otel-collector-config.yaml (simplified multi‑cloud)
text
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

  azureeventhubs: {}  # If you want the Collector to consume Event Hubs

processors:
  batch: {}
  memory_limiter:
    limit_mib: 512
  # Example attribute processor for scrubbing PII/sensitive values
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
  azuremonitor: {}

  # AWS X-Ray
  awsxray: {}

  # Traces to Jaeger / Grafana Tempo
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
3. Python agents on Landing Zones (Azure / AWS)
The agents scan Data and FinOps APIs, then send KPIs to your central API.
You instrument:

Outbound calls to cloud services (Azure SDK, boto3, REST).

Business logic of the scan (custom spans).

Calls to the central API, with trace context propagation.

Typical dependencies
text
opentelemetry-distro
opentelemetry-exporter-otlp-proto-http
azure-monitor-opentelemetry      # for Azure LZs
opentelemetry-instrumentation-requests
opentelemetry-instrumentation-urllib
Auto‑instrumentation (zero‑code)
bash
export OTEL_SERVICE_NAME=agent-azure-lz1
export OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf

# Enable auto-instrumentation
python -m opentelemetry.distro -a install

# Then run the agent
python your_agent.py
Example “scan KPI” span with trace propagation
python
from opentelemetry import trace
from opentelemetry.propagate import inject
import requests

tracer = trace.get_tracer(__name__)

def send_to_central_api(payload: dict):
    headers = {}
    inject(headers)  # adds the traceparent header
    requests.post("https://central-api/ingest", json=payload, headers=headers)

def run_scan():
    with tracer.start_as_current_span("scan-kpi-lz"):
        # calls to Azure/AWS (auto-instrumented if libraries are instrumented)
        kpis = collect_kpis_from_cloud()
        send_to_central_api({"kpis": kpis})
4. Central API (agent ingestion)
Assume the API is implemented with FastAPI (similar principle for Starlette/Flask).

Dependencies
text
fastapi
uvicorn

opentelemetry-sdk
opentelemetry-exporter-otlp-proto-http
opentelemetry-instrumentation-fastapi
opentelemetry-instrumentation-requests  # if you send to Event Hubs over HTTP
OTel + FastAPI initialization
python
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
Ingestion endpoint with business span
python
from pydantic import BaseModel

class IngestPayload(BaseModel):
    kpis: dict

@app.post("/ingest")
async def ingest(payload: IngestPayload):
    with tracer.start_as_current_span("ingest-kpi-from-agent"):
        # Here you can publish to Event Hubs
        # event_hubs_client.send(payload.json())
        return {"status": "ok"}
The agents’ traces are propagated via the traceparent header and the FastAPI route is auto‑instrumented.

5. Event Hubs → Databricks / Lakebase
Two main options for telemetry around Event Hubs:

Producer/consumer‑side instrumentation (central API, Databricks) — the Collector does not need the azureeventhubs receiver.

Use an Event Hubs receiver in the Collector to treat some messages as telemetry signals.

Databricks
Databricks supports OTel to export telemetry from notebooks/jobs to an OTLP endpoint.

Configure the OTLP endpoint (Collector) as the export target.

Add spans around jobs that consume Event Hubs and feed Lakebase (Delta/Lakehouse).

6. FastAPI backend connected to Postgres
This backend reads Postgres (Lakebase) and serves KPIs to the React dashboard.
You want to:

Trace incoming HTTP requests (FastAPI).

Trace SQL queries (SQLAlchemy/psycopg/Postgres).

Propagate trace context to React (via headers such as W3C or b3).

Dependencies
text
opentelemetry-instrumentation-fastapi
opentelemetry-instrumentation-psycopg2  # or sqlalchemy depending on your stack
opentelemetry-exporter-otlp-proto-http
Example SQLAlchemy instrumentation
python
from sqlalchemy import create_engine
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

engine = create_engine("postgresql+psycopg2://user:pass@host/db")
SQLAlchemyInstrumentor().instrument(engine=engine)
Queries to Postgres are automatically associated with the FastAPI spans.

7. React dashboard (user frontend)
Goal: trace user actions and HTTP calls to the backend, then send them to the Collector.

Example dependencies
json
"@opentelemetry/api": "^1.9.0",
"@opentelemetry/sdk-trace-web": "^1.25.0",
"@opentelemetry/exporter-trace-otlp-http": "^0.52.0",
"@opentelemetry/instrumentation-fetch": "^0.52.0"
otel.js
js
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
Import ./otel in index.tsx or App.tsx so it initializes before React renders.

8. Trace flow diagram
```mermaid
sequenceDiagram
    participant A as Agent (LZ)
    participant API as Central API
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

    R->>FAST: GET /kpi (web trace)
    FAST->>PG: SELECT KPI
    FAST->>COL: OTLP traces
    R->>COL: OTLP web traces
```
9. Monitoring, alerting and FinOps
Backends: Azure Monitor, AWS X‑Ray, Jaeger/Grafana Tempo, Prometheus for metrics.

Useful metrics: p95/p99 latency for scans, error rate per landing zone, number of API calls per service type (Databricks, Data Factory, EMR, etc.).

FinOps dimensions: add attributes like cloud.provider, service.type, cost.estimate on spans to correlate cost and volume.

10. DevSecOps best practices
Sampling: start simple with 1–10% sampling, increase during incidents; use tail‑based sampling when you deploy a more advanced collector.

PII redaction: use the attributes processor to remove user IDs, emails, and sensitive KPI values.

CI/CD: validate that OTEL_EXPORTER_OTLP_ENDPOINT targets the correct environment (dev/stage/prod).

Tests: smoke‑test script that runs a full scan and then checks in Jaeger that a complete trace exists.

The OpenTelemetry flows plug into your architecture as parallel technical flows: you keep exactly the same business calls and add OTLP calls from the components to one or more Collectors.
The main impact is: extra network traffic (OTLP), light CPU/RAM overhead in each service (OTel SDKs), and operating one or more Collector services.

Concrete impact on the current architecture
Python LZ agents

Add OTel libraries + OTLP export to the Collector (HTTP/gRPC) in addition to cloud API calls and your central API.

Moderate overhead (a few percent CPU and some RAM) when using batch + sampling.

Central API

Instrument FastAPI (or your framework) + OTLP export to the Collector.

No change to how agents call it, only spans created around routes.

Event Hubs / Databricks

Option 1: instrument Databricks + backend (OTLP to Collector).

Option 2: Collector connects to Event Hubs to treat some messages as telemetry (less common).

FastAPI backend + Postgres

Auto‑instrument FastAPI + SQL (SQLAlchemy/psycopg) and export OTLP to the Collector.

No change to your Postgres schema.

React dashboard

Add an OTel Web SDK that sends traces to the Collector (HTTP), in parallel to fetch calls to your backend.

New building block

One or more OpenTelemetry Collector(s) (central gateway + optionally local/agent collectors) to deploy, monitor, and scale.

New flows to add (global view)
Updated architecture with business vs telemetry flows:

```mermaid
graph TD
    %% Business components
    subgraph "Landing Zones -Azure/AWS-"
        AG[Python Agents\nScan Data/FinOps APIs]
        AZ[Azure Data/FinOps Services]
        AW[AWS Data/FinOps Services]
    end

    subgraph "Central App"
        API[Central API\n-KPI ingestion-]
        EH[Event Hubs]
        DBX[Databricks\nLakebase]
        PG[Postgres]
        FAST[FastAPI Backend]
        REACT[React Dashboard]
    end

    subgraph "Observability"
        COL[OTel Collector Gateway]
        OBS[Observability Backends\nAzure Monitor / X-Ray / Jaeger]
    end

    %% Existing business flows
    AG --> AZ
    AG --> AW
    AG --> API
    API --> EH
    EH --> DBX
    DBX --> PG
    FAST --> PG
    REACT --> FAST

    %% Telemetry flows (OTLP / observability)
    AG -. OTLP traces/metrics .-> COL
    API -. OTLP traces .-> COL
    DBX -. OTLP traces .-> COL
    FAST -. OTLP traces/metrics .-> COL
    REACT -. OTLP web traces .-> COL
    COL --> OBS
```
Telemetry flows to add
Python agents → Collector

OTLP HTTP/gRPC to http://otel-collector:4318 or :4317 for traces/metrics/logs.

Central API → Collector

OTLP export of traces for endpoints like /ingest plus business spans.

Databricks → Collector

Native OTel export or job configuration → Collector OTLP endpoint.

FastAPI backend → Collector

OTLP traces (HTTP + SQL) and optionally metrics (latency, 5xx).

React → Collector

OTLP HTTP for web traces (navigation, fetch, UI events).

Collector → observability backends

OTLP or native exporters to Azure Monitor, AWS X‑Ray, Jaeger/Tempo, Prometheus, etc.

Collector deployment patterns (variants)
You can start simple with a single gateway Collector (as in the diagram).
Later, to scale and support multi‑cloud:

Deploy agent Collectors close to workloads (per node/VM or sidecar).

These agent Collectors send to a central gateway Collector that handles sampling/filtering and multi‑backend export.

Architecture: business vs telemetry flows
```mermaid
flowchart LR
    %% Components
    subgraph LZ["Landing Zones - Azure / AWS- "]
        AG["Python Agents\n- scan Data/FinOps APIs- "]
        AZ["Azure Services\n- Data, FinOps- "]
        AW["AWS Services\n- Data, FinOps- "]
    end

    subgraph CENTRAL["Central Application"]
        API["Central API\n- KPI ingestion- "]
        EH["Event Hubs"]
        DBX["Databricks\n- Lakebase / Delta- "]
        PG["Postgres\n- Lakebase DB- "]
        FAST["FastAPI Backend"]
        REACT["React Dashboard"]
    end

    subgraph OBS["Observability layer"]
        COL["OTel Collector\n- central gateway- "]
        OBSBK["Obs. backends\nAzure Monitor / X-Ray / Jaeger"]
    end

    %% BUSINESS FLOWS - solid
    AG --> AZ
    AG --> AW
    AG --> API
    API --> EH
    EH --> DBX
    DBX --> PG
    FAST --> PG
    REACT --> FAST

    %% TELEMETRY FLOWS - dotted
    AG -. "OTLP traces/metrics" .-> COL
    API -. "OTLP traces" .-> COL
    DBX -. "OTLP traces" .-> COL
    FAST -. "OTLP traces/metrics" .-> COL
    REACT -. "OTLP web traces" .-> COL
    COL --> OBSBK
```
Solid lines = existing business flows (unchanged).

Dotted lines = new OpenTelemetry (OTLP) flows.

2. What needs to be added per component
2.1. OTel Collector (mandatory, first to deploy)
New service (Docker, VM or K8s) reachable from: agents, central API, FastAPI backend, Databricks, React (directly or via ingress).

Ports to open:

4317 (OTLP gRPC, recommended).

4318 (OTLP HTTP).

otel-collector-config.yaml with:

receivers: otlp

processors: batch (+ optional filters/redaction)

exporters to Azure Monitor / X‑Ray / Jaeger / Prometheus, etc.

Impact: one new flow from each component to http(s)://otel-collector:4317/4318.

2.2. Python agents (Azure / AWS LZs)
Add:

OTel dependencies in the image/venv:

opentelemetry-distro

opentelemetry-exporter-otlp-proto-http

azure-monitor-opentelemetry (optional direct export to Azure from Azure LZs)

Environment variables (example):

OTEL_SERVICE_NAME=agent-azure-lz1

OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318

OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf

Startup command updated for auto‑instrumentation:

python -m opentelemetry.distro -a install

then python your_agent.py

New flow: agents → Collector via OTLP (traces/metrics), in addition to current calls to the central API.

2.3. Central API (ingestion)
Add:

Dependencies:

opentelemetry-sdk

opentelemetry-exporter-otlp-proto-http

opentelemetry-instrumentation-fastapi (or for your framework)

OTel init in the API:

TracerProvider with Resource(service.name="central-api")

BatchSpanProcessor + OTLPTraceExporter(endpoint="http://otel-collector:4318/v1/traces", insecure=True)

FastAPIInstrumentor.instrument_app(app)

New flow: central API → Collector with OTLP traces on each route + custom business spans.

2.4. Event Hubs / Databricks
Two levels:

Simple (recommended to start)

Instrument Databricks (jobs/notebooks) only, exporting OTLP to the Collector.

Traces cover: reading from Event Hubs, transforms, writing to Lakebase/Postgres.

Advanced

Add an azureeventhubs receiver in the Collector to treat some messages as telemetry (rarely needed initially).

New flow (simple case): Databricks → Collector (OTLP traces).

2.5. FastAPI backend (Postgres / Lakebase reads)
Add:

Dependencies:

opentelemetry-instrumentation-fastapi

opentelemetry-instrumentation-psycopg2 or opentelemetry-instrumentation-sqlalchemy

opentelemetry-exporter-otlp-proto-http

OTel init (similar to central API):

service.name=backend-kpi

OTLP exporter to Collector

FastAPI + SQL instrumentation (SQLAlchemyInstrumentor or psycopg)

New flow: FastAPI backend → Collector: OTLP traces (user HTTP requests + SQL queries) and optionally metrics (latency, errors).

2.6. React dashboard
Add:

npm dependencies:

@opentelemetry/api

@opentelemetry/sdk-trace-web

@opentelemetry/exporter-trace-otlp-http

@opentelemetry/instrumentation-fetch (or XHR)

otel.ts / otel.js file that:

creates WebTracerProvider,

adds a BatchSpanProcessor + OTLPTraceExporter({ url: 'http(s)://otel-collector:4318/v1/traces' }),

enables FetchInstrumentation.

Import this file before React rendering (e.g. index.tsx).

New flow: React → Collector: OTLP web traces (navigation, fetch calls to FastAPI, UI events).

3. Quick summary of new flows (vs current architecture)
Python agents → OTel Collector (OTLP)

Central API → OTel Collector (OTLP)

Databricks → OTel Collector (OTLP)

FastAPI backend → OTel Collector (OTLP)

React → OTel Collector (OTLP)

OTel Collector → Azure Monitor / X‑Ray / Jaeger / … (specific exporters)