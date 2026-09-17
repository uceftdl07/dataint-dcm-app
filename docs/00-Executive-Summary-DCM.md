# DCM - Resume global fonctionnel et technique

## Objectif

Data Connect Monitoring (DCM) est une solution de supervision data qui collecte des KPIs depuis plusieurs Landing Zones Azure et AWS, centralise ces donnees, puis les restitue dans un dashboard pour le pilotage operationnel, FinOps et la qualite de service.

## Resume fonctionnel

- Collecter automatiquement les indicateurs data/FinOps sur des environnements cloud distribues.
- Centraliser et standardiser ces KPIs dans une plateforme unique.
- Donner une vue metier consolidée via API et dashboard.
- Detecter les anomalies de performance, de cout et de disponibilite.
- Fournir des traces end-to-end pour le diagnostic et l'amelioration continue.

### Vue fonctionnelle (Mermaid)

```mermaid
flowchart LR
    U[Utilisateurs metier et IT] --> D[Dashboard DCM]
    D --> B[Backend API]
    B --> KP[KPIs consolides]
    A1[Landing Zone Azure] --> C[Collecteurs]
    A2[Landing Zone AWS] --> C
    C --> I[Ingestion centrale]
    I --> P[Pipeline data]
    P --> KP
```

## Resume technique

La solution s'appuie sur une architecture distribuee de collecte (agents/collecteurs dans chaque Landing Zone) et une architecture centrale de traitement (ingestion, pipeline, stockage, API, frontend).

- **Collecte**: agents Python/.NET selon les zones Azure/AWS.
- **Ingestion**: API centrale + bus/evenements.
- **Traitement**: pipeline data (Databricks/Lakehouse selon le flux).
- **Stockage**: base transactionnelle et tables analytiques.
- **Exposition**: backend FastAPI/.NET + frontend React.
- **Observabilite**: OpenTelemetry + Collector + backends d'observabilite.

### Vue technique cible (Mermaid)

```mermaid
flowchart TB
    subgraph LZ[Landing Zones Azure et AWS]
        AG[Agents / Collecteurs]
        SRV[Services data monitorés]
        AG --> SRV
    end

    subgraph CORE[Plateforme centrale DCM]
        API[API d'ingestion]
        BUS[Event Hubs / Bus]
        DBX[Pipeline Databricks]
        DB[(Postgres / Lakebase)]
        BE[Backend API]
        FE[Frontend React]
    end

    subgraph OBS[Observabilite]
        OTel[OTel Collector]
        MON[Azure Monitor / X-Ray / Jaeger]
    end

    AG --> API
    API --> BUS --> DBX --> DB
    BE --> DB
    FE --> BE

    AG -. OTLP .-> OTel
    API -. OTLP .-> OTel
    DBX -. OTLP .-> OTel
    BE -. OTLP .-> OTel
    FE -. OTLP .-> OTel
    OTel --> MON
```

## Flux principal (de bout en bout)

```mermaid
sequenceDiagram
    participant AG as Agent LZ
    participant API as API Ingestion
    participant BUS as Event Bus
    participant DBX as Databricks
    participant DB as Postgres/Lakebase
    participant BE as Backend API
    participant FE as Frontend

    AG->>API: Envoi KPIs
    API->>BUS: Publie evenement
    BUS->>DBX: Declenche traitement
    DBX->>DB: Ecrit KPIs consolides
    FE->>BE: Demande KPIs
    BE->>DB: Lecture KPIs
    BE-->>FE: Reponse KPI
```

## Valeur apportee

- Vision unifiee multi-cloud Azure/AWS.
- Meilleure maitrise des couts (FinOps) et des performances.
- Detection plus rapide des incidents data.
- Base solide pour la gouvernance et l'industrialisation.

## Priorites de mise en oeuvre

1. Stabiliser la collecte distribuee dans chaque Landing Zone.
2. Fiabiliser l'ingestion et le pipeline de transformation.
3. Standardiser le modele de donnees KPI.
4. Renforcer l'observabilite OpenTelemetry end-to-end.
5. Industrialiser les alertes et les tableaux de bord metier.
