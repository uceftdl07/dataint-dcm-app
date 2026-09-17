# Data Connect Monitoring (DCM) - Architecture & Design Authority

> Consolidated documentation from the **Design Authority (DA)** meeting of 19 Feb 2026 and the **Architecture Design Document (ADD)** v121 (Page ID 818054930).

---

## Table of Contents

1. [DA Record](#1-da-record)
2. [Context & Objectives](#2-context--objectives)
3. [Scope & Positioning](#3-scope--positioning)
4. [Dependencies & Observability Landscape](#4-dependencies--observability-landscape)
5. [Organization & Stakeholders](#5-organization--stakeholders)
6. [Requirements](#6-requirements)
7. [Architecture Scenarios](#7-architecture-scenarios)
8. [Target Architecture - Functional](#8-target-architecture---functional)
9. [Target Architecture - Logical](#9-target-architecture---logical)
10. [Target Architecture - Technical](#10-target-architecture---technical)
11. [Flow Matrices](#11-flow-matrices)
12. [Security & Permissions](#12-security--permissions)
13. [Conformity & Standards](#13-conformity--standards)
14. [Data Governance](#14-data-governance)
15. [Roadmap & Next Steps](#15-roadmap--next-steps)
16. [DA Meeting Minutes](#16-da-meeting-minutes)
17. [Action Items](#17-action-items)

---

## 1. DA Record

| Item | Detail |
|---|---|
| **Date** | 19 Feb 2026 |
| **Type** | Design Authority (DA) |
| **DA Status** | COMPLETED |
| **ADD Page ID** | 862604863 (v114) / 818054930 (v121) |
| **Flag Archi** | VALIDATED |
| **Flag Cyber** | GREEN (13 Feb 2026) |
| **GenAI Flag** | N/A - NO |

**Cyber comment:** Go cyber sous reserve de mise a jour du PSP pour rehosting AWS DCM Core. Mettre en oeuvre les mesures listees dans le PSP actualise (PSP0003393 a mettre a jour). Le collector ayant vocation a etre deploye dans de multiples Landing Zones, il faut prevoir d'en faire un building block valide archi/cyber.

**Data classification (AICP):** 1/2 - 1/2 - 1/2

---

## 2. Context & Objectives

**Data Connect Monitoring** aims to consolidate & contextualize metrics and expose them in a simple way for data pipelines. The platform correlates performance, cloud consumption, and compliance, providing detailed information to facilitate incident analysis and resolution.

### Key Objectives

```mermaid
mindmap
  root((Data Connect Monitoring))
    Centralized Monitoring
      Data flows & usage
      Pipelines & connectors
      Status, latency, errors
    Cost Optimization
      Cloud consumption tracking
      FinOps alignment
      Budget tracking
    Performance
      Reduce downtime
      Incident analysis
      Trend detection
    Compliance
      Cybersecurity alerts
      Non-compliant access
      Governance
```

![Key Objectives Mind Map](diagrams/01-key-objectives.png)

### Business Value

- Centralized monitoring of data flows & usage
- Reduce downtime
- Performance, compliance, and cost optimization
- Enable IT and business teams to optimize costs, improve pipeline performance, and reduce security risks

---

## 3. Scope & Positioning

### Included

- Monitoring pipelines and connectors (status, latency, usage, errors)
- Cloud contextualization (resources, costs, alerting)
- Cybersecurity alerts (cyber-incident prevention, non-compliant access)
- Correlation with data, infra, usage & FinOps

### Excluded

- Data quality & lineage (covered by Sifflet)
- Infra & app monitoring (covered by Dynatrace)

### Users

- Data Engineers, Product Owners
- Cloud Ops, Cyber Champions
- Captain Run IT & Business

---

## 4. Dependencies & Observability Landscape

DCM sits within a broader data observability ecosystem alongside Dynatrace and Sifflet.

```mermaid
graph TB
    subgraph "Data Observability Landscape"
        direction TB

        subgraph DCM["Data Connect Monitoring (Build)"]
            DCM_M["Metadata: Cost, Status,<br/>Latency, Usage, Errors"]
            DCM_S["Signals: Costs, Resource Profiling,<br/>Alerting, Non-compliant Access"]
        end

        subgraph SIF["Sifflet (Buy - SaaS)"]
            SIF_M["Metadata: DQ Metrics,<br/>SQL Schemas, Lineage"]
            SIF_S["Signals: Freshness, Volume,<br/>Distribution, Schema Changes"]
        end

        subgraph DYN["Dynatrace"]
            DYN_APM["APM: Logs, Traces, Metrics,<br/>Distributed Traces, Latency"]
            DYN_INF["Infra: CPU/RAM, System Logs,<br/>Network Traffic, Cloud Tags"]
        end
    end

    DCM -->|"Pipelines, DBs,<br/>Cost Management"| ASSETS1["Azure Data Factory<br/>Databricks<br/>Databases (Azure/AWS)"]
    SIF -->|"Data Reliability &<br/>Quality"| ASSETS2["Data Warehouses<br/>Pipelines<br/>BI (Power BI)"]
    DYN -->|"Software & Infra<br/>Performance"| ASSETS3["Microservices, APIs<br/>VMs, K8s, Network<br/>Cloud Services"]

    style DCM fill:#4a90d9,color:#fff
    style SIF fill:#50b86c,color:#fff
    style DYN fill:#7b68ee,color:#fff
```

![Observability Landscape](diagrams/02-observability-landscape.png)

### Observability Coverage Matrix

| Observability Type | Solution | Metadata & Signals | Monitored Assets | Use Case | Users |
|---|---|---|---|---|---|
| **Data Observability** | **Sifflet** (Buy) | DQ metrics, SQL Schemas, Lineage, Freshness, Volume | Data Warehouses, Databricks, Pipelines (ADF), BI | Data Reliability: anomalies, root-cause, downstream impact | Business Experts, Data Hub Owner, Data Engineers |
| **Data Observability** | **DCM** (Build) | Cost, Status, Latency, Usage, Errors, Resource Profiling | Databases (Azure/AWS), Pipelines (ADF, Databricks) | Monitoring pipelines & connectors (cost, usage) | Data Engineers, Product Owners, Cloud Ops |
| **APM** | **Dynatrace** | Logs, Traces, Metrics, PurePath, Latency, Error rates | Microservices, APIs, Web/Mobile Apps, Serverless | Software Performance: code-level troubleshooting | Software Engineers, QA, UX |
| **Infrastructure** | **Dynatrace** | Logs, Metrics, CPU/RAM, Network traffic, Cloud tags | Network, Servers, VMs, K8s, Storage, Cloud Services | System Health: scaling, uptime, cost optimization | SRE, DevOps, Cloud Architects |

---

## 5. Organization & Stakeholders

| Role | Entity | Main Contact |
|---|---|---|
| Business Project Manager | TGITS/MTE/DS | Marie Helene Collyn |
| Product Owner / RIA | MTE/DS | Maher LEZHARI |
| IT Project Manager | TGITS/MTE/DS | Mikael MAUSSE |
| Cybercoach | TGITS/CRC/PRJ | Arnault GOYETTE |
| Referent Architect | DSI/STA/ADO | Sophanara DE LOPEZ |
| ACTE Architect | DSI/STA/ATE | Yahia ZERDOUMI |
| Foundation Architect | DSI/STA/AFO | Jonathan NEBIE |
| Data Architect | DSI/STA/ADO | Sophanara DE LOPEZ |
| Data Domain Lead | TGITS/PIT/OPE/DIT | Didier Cazettes |
| Operations Responsible | TGITS/MTE/DS | Mikael MAUSSE |

---

## 6. Requirements

### Service Level Information

| Criteria | Value |
|---|---|
| **RTO** | 2 to 5 Days |
| **RPO** | 2 to 5 Days |
| **Performance** | Near real-time for data pipelines monitoring |
| **Availability** | Working days only |
| **Service Availability** | 99.5% |

### Data Classification (AICP)

| Criteria | Classification |
|---|---|
| Availability | 1/2 |
| Integrity | 1/2 |
| Confidentiality | 1/2 |
| Proof | - |

### Regulatory

| Criteria | Status |
|---|---|
| SOX | No |
| GDPR | No |

---

## 7. Architecture Scenarios

Two scenarios were studied:

```mermaid
graph LR
    subgraph "Scenario 1 - Centralized Collector ❌"
        S1_JOB["Single Azure App Service<br/>Multi-cloud Collector"] --> S1_QUEUE["Queue"]
        S1_QUEUE --> S1_DB["Central Database<br/>(Azure)"]
        S1_JOB -->|"Azure Monitor API"| S1_AZ["Azure Services"]
        S1_JOB -->|"AWS CloudWatch API"| S1_AWS["AWS Services"]
    end

    style S1_JOB fill:#e74c3c,color:#fff
    style S1_DB fill:#e74c3c,color:#fff
```

![Scenario 1 - Centralized Collector](diagrams/03-scenario1-centralized.png)

```mermaid
graph LR
    subgraph "Scenario 2 - Distributed Collectors ✅"
        S2_AZ["Azure Collector<br/>(App Service WebJob)"] -->|HTTPS| APIGEE["Apigee Gateway"]
        S2_AWS["AWS Collector<br/>(ECS Fargate)"] -->|HTTPS| APIGEE
        APIGEE --> EH["Event Hub / SQS"]
        EH --> DB["Central Database"]
    end

    style S2_AZ fill:#27ae60,color:#fff
    style S2_AWS fill:#27ae60,color:#fff
    style APIGEE fill:#f39c12,color:#fff
```

![Scenario 2 - Distributed Collectors](diagrams/04-scenario2-distributed.png)

### Scenario Comparison

| Criteria | Scenario 1 - Centralized | Scenario 2 - Distributed |
|---|---|---|
| **Build Complexity** | Low | High |
| **Scalability** | Limited | Good |
| **Segmentation Rules** | Non-compliant | Compliant |
| **Cloud/AFO/ADO Rules** | Non-compliant | Fully compliant |
| **Operational Management** | Simple | More complex |
| **Architecture Recommendation** | Rejected | **Selected** |
| **Cyber Recommendation** | Rejected | **Go** |

**Decision:** Scenario 2 selected. Collectors must be qualified as **building blocks** validated archi/cyber.

---

## 8. Target Architecture - Functional

### Functional Layers Overview

```mermaid
graph TB
    subgraph "7. Governance & Identity"
        GOV["Entra ID | Unity Catalog | RBAC/IAM"]
    end

    subgraph "6. Presentation"
        PRES["Static Web App S3 (React) | Backend API (.NET)"]
    end

    subgraph "5. Analytics & ML"
        ML["Databricks | Feature Store | Model Serving"]
    end

    subgraph "4. Analytical Storage"
        ANAL["Databricks Lakehouse (on Azure ADLS2)<br/>Read-only access for ML"]
    end

    subgraph "3. Transactional Storage"
        TRANS["Databricks Lakebase<br/>ACID-compliant, low-latency"]
    end

    subgraph "2. Ingestion"
        ING["Ingestion API (Lambda) | SQS"]
    end

    subgraph "1. Collection"
        COLL_AZ["Azure Collector<br/>App Service WebJob"]
        COLL_AWS["AWS Collector<br/>ECS Fargate"]
    end

    COLL_AZ --> ING
    COLL_AWS --> ING
    ING --> TRANS
    TRANS --> ANAL
    ANAL --> ML
    TRANS --> PRES
    ML --> PRES
    GOV -.->|governs| TRANS
    GOV -.->|governs| ANAL
    GOV -.->|governs| PRES

    style GOV fill:#8e44ad,color:#fff
    style PRES fill:#2980b9,color:#fff
    style ML fill:#e67e22,color:#fff
    style ANAL fill:#27ae60,color:#fff
    style TRANS fill:#27ae60,color:#fff
    style ING fill:#f39c12,color:#fff
    style COLL_AZ fill:#3498db,color:#fff
    style COLL_AWS fill:#e74c3c,color:#fff
```

![Functional Layers Overview](diagrams/05-functional-layers.png)

### Key Functional Flows

```mermaid
sequenceDiagram
    participant AZ as Azure/AWS Services
    participant COL as Collectors (.NET)
    participant APG as Apigee Gateway
    participant API as Ingestion API (Lambda)
    participant SQS as SQS Queue
    participant LB as Lakebase Primary
    participant LBR as Lakebase Replica
    participant DBR as Databricks ML
    participant WEB as React Dashboard
    participant USR as End User

    Note over AZ,COL: A. Collection & Ingestion
    COL->>AZ: Poll KPI metrics (REST APIs)
    AZ-->>COL: Metrics (JSON)
    COL->>APG: Send normalized payload (JWT)
    APG->>API: Forward validated request
    API->>SQS: Publish message
    SQS->>LB: Consumer writes to Lakebase

    Note over LB,DBR: B. Zero-Copy Analytics
    LBR->>DBR: Read-only access (same physical storage)
    DBR->>DBR: Feature engineering & model training

    Note over USR,WEB: C. Presentation
    USR->>WEB: Navigate to dashboard
    WEB->>LB: Query KPI data
    WEB->>DBR: Request predictions (optional)
    LB-->>WEB: KPI datasets (JSON)
    WEB-->>USR: Render charts & alerts
```

![Key Functional Flows](diagrams/06-functional-flows.png)

---

## 9. Target Architecture - Logical

### Logical Architecture Overview

```mermaid
graph TB
    subgraph "Azure Monitored Landing Zones"
        AZ_COL["Azure Collector<br/>(App Service WebJob .NET)"]
        AZ_KV["Azure Key Vault"]
        AZ_MI["Managed Identity"]
        AZ_COL -->|secrets| AZ_KV
        AZ_MI -.->|authenticates| AZ_COL
    end

    subgraph "AWS Monitored Landing Zones"
        AWS_COL["AWS Collector<br/>(ECS Fargate .NET)"]
        AWS_SM["Secrets Manager"]
        AWS_EB["EventBridge Scheduler"]
        AWS_EB -->|trigger| AWS_COL
        AWS_COL -->|secrets| AWS_SM
    end

    subgraph "Corporate DMZ"
        APIGEE["Apigee API Gateway"]
    end

    subgraph "Central Monitoring Solution (AWS)"
        direction TB
        subgraph "Ingestion Layer"
            LAMBDA["Lambda - Ingestion API"]
            SQS["SQS Queue"]
            LAMBDA --> SQS
        end

        subgraph "Storage Layer (Zero-Copy)"
            LB_P["Lakebase Primary<br/>(PostgreSQL - OLTP)"]
            LB_R["Lakebase Replica<br/>(Read-only)"]
            NEON["Neon Storage Layer<br/>(Shared Physical Storage)"]
            LB_P --- NEON
            LB_R --- NEON
        end

        subgraph "Presentation Layer"
            S3["S3 + CloudFront<br/>(React Dashboard)"]
            ALB["ALB + WAF"]
            BACKEND["ECS Fargate<br/>Backend API (.NET)"]
            APIGW["API Gateway"]
            APIGW --> ALB --> BACKEND
        end

        subgraph "Analytics & ML Layer"
            DBR_WS["Databricks Workspace"]
            FS["Feature Store"]
            MS["Model Serving"]
            UC["Unity Catalog"]
        end

        SQS --> LB_P
        LB_R --> DBR_WS
        DBR_WS --> FS --> MS
        BACKEND --> LB_P
        BACKEND --> MS
        UC -.->|governs| LB_P
        UC -.->|governs| LB_R
    end

    subgraph "Identity"
        ENTRA["Microsoft Entra ID"]
    end

    AZ_COL -->|HTTPS + JWT| APIGEE
    AWS_COL -->|HTTPS + JWT| APIGEE
    APIGEE -->|VPC Lattice| LAMBDA

    AZ_COL -->|OAuth2 token| ENTRA
    AWS_COL -->|OAuth2 token| ENTRA
    APIGEE -->|validate token| ENTRA
    S3 -->|OIDC auth| ENTRA

    style APIGEE fill:#f39c12,color:#fff
    style LB_P fill:#27ae60,color:#fff
    style LB_R fill:#27ae60,color:#fff
    style NEON fill:#16a085,color:#fff
    style ENTRA fill:#8e44ad,color:#fff
    style UC fill:#8e44ad,color:#fff
```

![Logical Architecture Overview](diagrams/07-logical-architecture.png)

### Logical Blocks Summary

| Logical Block | Components | Responsibility |
|---|---|---|
| **Collection Layer** | .NET agents (Azure LZ / AWS LZ) | Collect raw KPI metrics from monitored services |
| **Ingestion Layer** | Apigee, Lambda, SQS | Expose secure endpoint, authenticate agents, buffer payloads |
| **Transactional Storage** | Lakebase Primary (PostgreSQL-compatible) | Single source of truth - ACID, low-latency OLTP |
| **Analytical & ML** | Lakebase Replica, Databricks, Unity Catalog, Feature Store | Isolated read access for analytics & ML - no data duplication |
| **Presentation** | S3 (React), API Gateway, Backend .NET API | Secure dashboard + RESTful APIs |
| **Governance & Identity** | Entra ID, Unity Catalog, Managed Identities | Authentication, authorization, data governance |

### Key Architectural Principles

- **Zero data duplication**: Lakebase's decoupled compute/storage - primary and replica share the same physical storage
- **Event-driven**: Decoupled ingestion via SQS absorbs traffic spikes
- **API-first**: All inter-zone communication through Apigee
- **Separation of concerns**: Presentation, storage, and analytics scale independently
- **Unified governance**: Unity Catalog applies consistent access policies

---

## 10. Target Architecture - Technical

The architecture is divided into three distinct zones:

### Technical Zones Overview

```mermaid
graph TB
    subgraph "Zone A: Azure Monitored Landing Zone"
        AZ_WJ["App Service WebJob (.NET)<br/>BB: JOB_2"]
        AZ_KV["Azure Key Vault<br/>BB: SV_1"]
        AZ_MI["Managed Identity"]
        AZ_WJ --> AZ_KV
        AZ_MI -.-> AZ_WJ
        AZ_WJ -->|"Azure Mgmt APIs<br/>(Cost, Monitor, ADF, Databricks)"| AZ_APIS["Azure Services"]
    end

    subgraph "Zone B: AWS Monitored Landing Zone"
        AWS_ECS["ECS Fargate Task (.NET)<br/>BB: CT_2_SLESS_TASK"]
        AWS_EB["EventBridge Scheduler<br/>BB: CRON_1"]
        AWS_SM["Secrets Manager"]
        AWS_KMS["AWS KMS"]
        AWS_EB -->|trigger| AWS_ECS
        AWS_ECS --> AWS_SM
        AWS_SM -.-> AWS_KMS
        AWS_ECS -->|"AWS APIs<br/>(Glue, EMR, RDS, Cost Explorer)"| AWS_APIS["AWS Services"]
    end

    subgraph "Corporate DMZ"
        APIGEE["Apigee (TE API Gateway)"]
    end

    subgraph "Zone C: AWS Central Monitoring Solution"
        direction TB
        subgraph "Ingestion"
            C_LAMBDA["Lambda Ingestion API<br/>BB: AWS API_1"]
            C_SQS["SQS Queue<br/>BB: AWS EVT_1"]
            C_LAMBDA --> C_SQS
        end

        subgraph "Storage (Zero-Copy)"
            C_LBP["Lakebase Primary Compute"]
            C_LBR["Lakebase Replica Compute"]
            C_NEON["Neon Storage Layer"]
            C_UC["Unity Catalog Metastore"]
        end

        subgraph "Presentation"
            C_CF["CloudFront CDN"]
            C_S3["S3 (React App)<br/>BB: AWS WEB_2"]
            C_APIGW["API Gateway (REST)<br/>BB: API_GW_2R"]
            C_ALB["ALB + WAF<br/>BB: WAF_1"]
            C_BACK["ECS Fargate Backend (.NET)<br/>BB: CT_2_SLESS_SERVICE"]
            C_CF --> C_S3
            C_APIGW --> C_ALB --> C_BACK
        end

        subgraph "Analytics & ML"
            C_DBR["Databricks Workspace<br/>BB: ML_1"]
            C_FS["Feature Store"]
            C_MS["Model Serving"]
        end

        C_SQS --> C_DBR
        C_DBR --> C_LBP
        C_LBR --> C_DBR
        C_BACK --> C_LBP
        C_BACK --> C_MS
    end

    AZ_WJ -->|"HTTPS/JWT"| APIGEE
    AWS_ECS -->|"HTTPS/JWT"| APIGEE
    APIGEE -->|"VPC Lattice"| C_LAMBDA

    ENTRA["Entra ID"] -.->|auth| AZ_WJ
    ENTRA -.->|auth| AWS_ECS
    ENTRA -.->|validate| APIGEE
    ENTRA -.->|OIDC| C_APIGW

    style APIGEE fill:#f39c12,color:#fff
    style C_LBP fill:#27ae60,color:#fff
    style C_LBR fill:#27ae60,color:#fff
    style ENTRA fill:#8e44ad,color:#fff
```

![Technical Zones Overview](diagrams/08-technical-zones.png)

### Building Blocks Used

| Zone | Building Blocks |
|---|---|
| **DCM Core (AWS)** | API_GW_2R, API_1, WAF_1, CT_2_SLESS_SERVICE, ML_1, SV_1, MQS_1 |
| **Azure Collector** | JOB_2, SV_1 |
| **AWS Collector** | NAT_1, CT_2_SLESS_TASK, CRON_1, SV_1 |

---

## 11. Flow Matrices

### Metric Ingestion Flow (Central Solution)

```mermaid
sequenceDiagram
    participant AGT as Metric Agents<br/>(Azure/AWS LZ)
    participant APG as Apigee Gateway
    participant EID as Entra ID
    participant LAM as Lambda Ingestion API
    participant SQS as SQS Queue
    participant DBR as Databricks Cluster
    participant S3B as S3 Bucket (DBFS)

    Note over AGT,APG: C0 - Agent sends payload with JWT + API Key
    AGT->>APG: HTTPS/443 (TLS 1.3) - JWT Bearer + API Key

    Note over APG,EID: C1 - Token validation
    APG->>EID: HTTPS/443 - OAuth2 Client Credentials
    EID-->>APG: Token validated

    Note over APG,LAM: C2 - Forward via VPC Lattice
    APG->>LAM: HTTPS/443 (TLS 1.3) - IAM Auth Policy

    Note over LAM,SQS: C3 - Publish to SQS
    LAM->>SQS: HTTPS/443 (TLS 1.3) - IAM Role

    Note over DBR,SQS: C4 - Consume from SQS
    DBR->>SQS: HTTPS/443 (TLS 1.3) - IAM Role

    Note over DBR,S3B: C5 - Read/Write via S3 Gateway
    DBR->>S3B: HTTPS/443 (TLS 1.3) - IAM Role
```

![Metric Ingestion Flow](diagrams/09-metric-ingestion-flow.png)

### User Access Flow

```mermaid
sequenceDiagram
    participant USR as User Browser
    participant CF as CloudFront + S3
    participant EID as Entra ID
    participant APIGW as API Gateway
    participant ALB as ALB + WAF
    participant ECS as ECS Fargate Backend
    participant LB as Lakebase (PostgreSQL)
    participant SM as Secrets Manager

    Note over USR,CF: U1 - Load React App
    USR->>CF: HTTPS/443 (TLS 1.3) - No auth (static)

    Note over USR,EID: U2 - Authenticate (OIDC)
    USR->>EID: HTTPS/443 - User Credentials + MFA

    Note over USR,APIGW: U3 - API Request with JWT
    USR->>APIGW: HTTPS/443 (TLS 1.3) - Bearer Token

    Note over APIGW,EID: U4 - Validate JWT
    APIGW->>EID: HTTPS/443 - JWT Validation

    Note over APIGW,ALB: U5 - Forward via VPC Link
    APIGW->>ALB: HTTPS/443 (TLS 1.3) - IAM/VPC Link

    Note over ALB,ECS: U6 - Route to backend (HA: AZ1+AZ2)
    ALB->>ECS: HTTPS/443 (TLS 1.3) - Internal routing

    Note over ECS,LB: U7 - Query monitoring data
    ECS->>LB: TCP/5432 (TLS 1.2) - Token from Secrets Manager

    Note over ECS,SM: U8 - Retrieve secrets
    ECS->>SM: HTTPS/443 (TLS 1.3) - IAM Role (VPC Endpoint)
```

![User Access Flow](diagrams/10-user-access-flow.png)

### Azure Collector Flow Matrix

| # | Description | Source | Destination | Protocol | Port | Encryption | Authentication |
|---|---|---|---|---|---|---|---|
| 1 | Retrieve App Registration secrets | WebJob (.NET) | Azure Key Vault | HTTPS | 443 | TLS 1.2+ | Managed Identity |
| 2 | Obtain OAuth2 token | WebJob (.NET) | Entra ID | HTTPS | 443 | TLS 1.2+ | Client ID + Secret |
| 3 | Collect KPI metrics from Azure | WebJob (.NET) | Azure Management API | HTTPS | 443 | TLS 1.2+ | Bearer token (JWT) |
| 4 | Send KPI payload to central solution | WebJob (.NET) | Apigee (TE APIM) | HTTPS | 443 | TLS 1.2+ | Bearer token (JWT) |

### AWS Collector Flow Matrix

| # | Description | Source | Destination | Protocol | Port | Encryption | Authentication |
|---|---|---|---|---|---|---|---|
| 1 | Scheduled trigger | EventBridge Scheduler | ECS Fargate Task | AWS API | 443 | TLS 1.2+ | IAM Role |
| 2 | Retrieve App Registration secrets | ECS Fargate (.NET) | Secrets Manager (VPC Endpoint) | HTTPS | 443 | TLS 1.2+ | IAM Role |
| 3 | Decrypt secrets (optional) | ECS Fargate | AWS KMS (VPC Endpoint) | HTTPS | 443 | TLS 1.2+ | IAM Role |
| 4 | Obtain OAuth2 token | ECS Fargate | Entra ID | HTTPS | 443 | TLS 1.2+ | Client ID + Secret |
| 5 | Collect KPI metrics from AWS | ECS Fargate | AWS Service APIs | HTTPS | 443 | TLS 1.2+ | IAM Role (Signature V4) |
| 6 | Send KPI payload to central solution | ECS Fargate | Apigee (TE APIM) | HTTPS | 443 | TLS 1.2+ | Bearer token (JWT) |

---

## 12. Security & Permissions

### Authentication Architecture

```mermaid
graph LR
    subgraph "Azure Collector"
        AZ_COL["WebJob (.NET)"]
        AZ_KV["Key Vault"]
        AZ_MI["Managed Identity"]
    end

    subgraph "AWS Collector"
        AWS_COL["ECS Fargate (.NET)"]
        AWS_SM["Secrets Manager"]
        AWS_IAM["IAM Role"]
    end

    subgraph "Identity Provider"
        ENTRA["Microsoft Entra ID<br/>OAuth2 / OIDC"]
    end

    subgraph "API Gateway"
        APIGEE["Apigee"]
    end

    AZ_MI -->|"1. Authenticate"| AZ_KV
    AZ_KV -->|"2. Client ID + Secret"| AZ_COL
    AZ_COL -->|"3. client_credentials"| ENTRA
    ENTRA -->|"4. JWT Bearer Token"| AZ_COL
    AZ_COL -->|"5. JWT"| APIGEE

    AWS_IAM -->|"1. Authenticate"| AWS_SM
    AWS_SM -->|"2. Client ID + Secret"| AWS_COL
    AWS_COL -->|"3. client_credentials"| ENTRA
    ENTRA -->|"4. JWT Bearer Token"| AWS_COL
    AWS_COL -->|"5. JWT"| APIGEE

    APIGEE -->|"Validate JWT"| ENTRA

    style ENTRA fill:#8e44ad,color:#fff
    style APIGEE fill:#f39c12,color:#fff
```

![Authentication Architecture](diagrams/11-authentication-architecture.png)

### Azure Collector - RBAC Least Privilege

| Monitored Service | Required RBAC Role | Scope | Justification |
|---|---|---|---|
| Azure Cost Management + Billing | Cost Management Reader | Subscription | Read usage details, reservations, budgets |
| Azure Monitor (Metrics, Logs, Alerts) | Monitoring Reader | Subscription / RG | Read monitoring data, metrics, diagnostics |
| Azure Data Factory | Reader | Data Factory instance | Read pipeline runs, activity runs, triggers |
| Azure Databricks | Reader | Databricks workspace | Read workspace metadata, job runs, cluster metrics |
| Azure SQL / PostgreSQL / MySQL | Reader | Database server | Read server state, query performance insights |
| Azure Cosmos DB | Reader | Cosmos DB account | Read account metrics, throughput, region status |
| Azure Key Vault | Key Vault Reader | Key Vault instance | Read secret metadata (no secret value access) |
| Azure Subscription | Reader | Subscription | Enumerate resource groups, resources, tags |
| Azure Reservations | Reservation Reader | Subscription / Billing | Read reservation utilization, recommendations |

### AWS Collector - IAM Least Privilege

| Monitored Service | Required Actions | Resource Scope | Justification |
|---|---|---|---|
| AWS Glue | `glue:Get*`, `glue:List*`, `glue:BatchGet*` | Specific crawlers/jobs or `*` | Read job runs, crawler metrics |
| Amazon EMR | `elasticmapreduce:List*`, `elasticmapreduce:Describe*` | Specific clusters or `*` | Read cluster status, step execution |
| Amazon RDS | `rds:Describe*`, `rds:List*` | Specific instances or `*` | Read DB instance health |
| AWS Cost Explorer | `ce:Get*`, `ce:List*` | `*` | Read cost and usage data |
| Amazon Redshift | `redshift:Describe*`, `redshift:View*` | Specific clusters or `*` | Read cluster health, workload metrics |
| AWS Secrets Manager | `secretsmanager:GetSecretValue`, `secretsmanager:DescribeSecret` | Specific secret ARNs | Retrieve Azure client secret |
| AWS KMS | `kms:Decrypt` | Specific KMS key ARN | Decrypt encrypted secrets |
| CloudWatch / CloudTrail | `logs:Describe*`, `logs:Get*`, `cloudtrail:LookupEvents` | Specific log groups or `*` | Read log data, audit events |

### Security Controls

- Client secrets are **never hardcoded** - retrieved at runtime from secure vaults
- Secrets are **rotated regularly** (automatic rotation recommended)
- All token requests over **TLS 1.2+**
- Token includes **custom claims** (subscription ID, cloud provider) for routing and tenant isolation
- All internal Azure communications use **Managed Identities** and **Private Endpoints**
- All internal AWS communications use **IAM Roles** and **VPC Endpoints**

### Cyber Flag

| Flag | Date | Comments |
|---|---|---|
| **GREEN** | 13 Feb 2026 | Go cyber subject to PSP update for AWS DCM Core rehosting. Implement measures listed in updated PSP (PSP0003393). Collectors to be qualified as archi/cyber validated building blocks. |

---

## 13. Conformity & Standards

### Architecture Principles (CR-GR-INF-001)

| Principle | Conformity | Comments |
|---|---|---|
| Strategic Alignment | Yes | - |
| Visibility | Yes | - |
| Re-use | Yes | - |
| Standard Solutions | Yes | No market solution meets all requirements; in-house build decision |
| Centralized Solutions | Yes | - |
| Mobile Devices | Yes | - |
| Resilience | Yes | - |
| Modularity | Yes | - |
| Durability | Yes | - |
| Cloud First | Yes | - |
| Shared Infrastructures | Yes | - |
| Security by Design | Yes | - |
| DevSecOps | Yes | - |
| Interoperability | Yes | - |
| Data Consistency | Yes | - |

### Architecture Framework Compliance

| Item | Status |
|---|---|
| Architecture in line with framework | **YES** |
| Temporary deviation | NO |
| Risk mitigation possible | - |
| Framework adjustment needed | - |
| Derogation required | **NO** |
| Standard patterns used | YES |
| Building blocks used | YES |
| Decision trees respected | YES |
| Non-standard components | NO |

---

## 14. Data Governance

### Data Sources (Consumed)

| Business Object | Data Source | Master Data | Comments |
|---|---|---|---|
| Pipeline execution metrics, resource utilization | Azure Data Factory | N | Investigate integration with Dynatrace/Sifflet |
| Cluster performance, job execution, Unity Catalog governance | Databricks (Azure, AWS) | N | Investigate integration with Dynatrace/Sifflet |
| Performance metrics, security alerts, cost attribution | Database Services (Azure/AWS) | N | Investigate integration with Dynatrace/Sifflet |
| Spend analysis, budget tracking, resource optimization | Cost Management APIs (Azure/AWS) | N | Check consistency with official FinOps monitoring |

### Data Exposition (Produced)

| Business Object | Exposition | Master Data | Comments |
|---|---|---|---|
| Aggregated metrics (FinOps, job status, access) | Dashboard (Dataviz) | N | Document in Collibra if relevant |
| Aggregated metrics (FinOps, job status, access) | API (via Apigee) | N | Future integration with Dynatrace, Sifflet |

### Data Management Maturity (AS-IS vs TO-BE)

```mermaid
graph LR
    subgraph "AS-IS (Maturity: 1/3)"
        A1["Data Governance: 1"]
        A2["Data Knowledge: 1"]
        A3["Referential & Master Data: 1"]
        A4["Data Access & Exposition: 1"]
        A5["Data Quality: 1"]
    end

    subgraph "TO-BE (Maturity: 2/3)"
        B1["Data Governance: 2"]
        B2["Data Knowledge: 2"]
        B3["Referential & Master Data: 2"]
        B4["Data Access & Exposition: 2"]
        B5["Data Quality: 2"]
    end

    A1 -->|improve| B1
    A2 -->|improve| B2
    A3 -->|improve| B3
    A4 -->|improve| B4
    A5 -->|improve| B5

    style A1 fill:#e74c3c,color:#fff
    style A2 fill:#e74c3c,color:#fff
    style A3 fill:#e74c3c,color:#fff
    style A4 fill:#e74c3c,color:#fff
    style A5 fill:#e74c3c,color:#fff
    style B1 fill:#f39c12,color:#fff
    style B2 fill:#f39c12,color:#fff
    style B3 fill:#f39c12,color:#fff
    style B4 fill:#f39c12,color:#fff
    style B5 fill:#f39c12,color:#fff
```

![Data Governance Maturity AS-IS vs TO-BE](diagrams/12-data-governance-maturity.png)

### User Authorization Model

| Model | Used |
|---|---|
| Authorization built in the application | YES |
| Based on Azure Entra ID Groups | NO |
| Based on Azure Entra ID AppRoles | YES |
| No authorization model | NO |

---

## 15. Roadmap & Next Steps

```mermaid
gantt
    title DCM Roadmap
    dateFormat YYYY-MM
    axisFormat %b %Y

    section Phase 1
    Validate Cyber & Industrialize POC (Data Connect scope)  :active, p1, 2026-01, 2026-04

    section Phase 2
    Extend to other Data Hubs (Surface Hub, RC)             :p2, 2026-04, 2026-08
    Qualify Collectors as Building Blocks                     :p2b, 2026-04, 2026-07

    section Phase 3
    Single Pane of Glass (synergies Sifflet + Dynatrace)    :p3, 2026-08, 2026-12

    section Future
    AI Use Cases (incident prediction via log analysis)      :p4, 2027-01, 2027-06
```

![DCM Roadmap](diagrams/13-roadmap-gantt.png)

### Phase Details

| Phase | Description | Key Activities |
|---|---|---|
| **Phase 1** | Validate & Industrialize | Cyber validation, PSP implementation, industrialize POC on Data Connect scope |
| **Phase 2** | Extend Coverage | Deploy to Surface Hub, RC; qualify Azure/AWS collectors as building blocks |
| **Phase 3** | Unified Observability | Create single pane of glass with Sifflet and Dynatrace synergies |
| **Future** | AI-Powered | Incident prediction via log analysis (not in current scope) |

---

## 16. DA Meeting Minutes

> AI-generated meeting summary from the DA session of 19 Feb 2026.

### Topics Discussed

**1. Presentation & Positioning of DCM**
- Maher, Mikael, and others presented the context, needs, and positioning of DCM
- Explained DCM's role in covering data observability needs (costs & usage)
- Distinguished DCM from Dynatrace (infra/APM) and Sifflet (data quality/pipeline health)
- Originally developed by MTE Data Squad for internal needs, now extended to other projects

**2. Functional & Technical Presentation**
- Mikael detailed DCM's operation: UI, data collection model, architecture scenarios, technical choices
- Interface provides overview of monitored elements (Databricks, ADF, databases, AWS), trend indicators, and costs
- Solution relies on collectors deployed in landing zones, centralized via API-first architecture
- Two scenarios studied: centralized (rejected) and distributed (selected, compliant with architecture rules)

**3. Organizational Aspects, Governance & Security**
- Importance of metadata valorization in coordination with data offices and project teams
- Cost monitoring must align with FinOps practices (Pascal Soudan)
- Solution complies with company architecture rules without derogation
- Collectors must be qualified as building blocks (similar to Dynatrace approach)
- PSP completed with security actions to follow

**4. Roadmap & Next Steps**
- Phase 1: Cyber validation + industrialize POC on Data Connect scope
- Phase 2: Extend to other data hubs + reflection on single pane of glass with Sifflet/Dynatrace
- Future: AI use cases for incident prediction (not in current scope)
- Sifflet SaaS validation planned to complement observability coverage

---

## 17. Action Items

| # | Action | Holder | Status |
|---|---|---|---|
| 1 | **Qualify Azure & AWS collectors as building blocks** - Define technical components and associated roles for DCM | Architecture Team | Pending |
| 2 | **Align monitored costs with FinOps tracking** - Ensure DCM costs are aligned with FinOps monitoring by Pascal Soudan's teams | Architecture Team | Pending |
| 3 | **Valorize generated metadata** - Evaluate interest with data offices for integrating DCM metadata into data management processes | Architecture Team | Pending |
| 4 | **Implement PSP cyber actions** - Execute actions defined during PSP cyber review for definitive Go cyber (PSP0003393 update) | Project Team | Pending |
| 5 | **Manage collector & API evolution** - Set up tracking for collector and API evolution to integrate new components over time | Project Team | Pending |
| 6 | **Update PSP for AWS DCM Core rehosting** - Update PSP0003393 for rehosting DCM Core on AWS | Project Team | Pending |

---

## Appendix: End-to-End Architecture Diagram

```mermaid
graph TB
    subgraph "Monitored Services"
        AZ_ADF["Azure Data Factory"]
        AZ_DBR["Azure Databricks"]
        AZ_DB["Azure Databases"]
        AZ_COST["Azure Cost Mgmt"]
        AWS_GLUE["AWS Glue"]
        AWS_EMR["AWS EMR"]
        AWS_RDS["AWS RDS"]
        AWS_CE["AWS Cost Explorer"]
    end

    subgraph "Azure Landing Zone"
        AZ_COL["Azure Collector<br/>(App Service WebJob .NET)"]
        AZ_KV["Key Vault"]
    end

    subgraph "AWS Landing Zone"
        AWS_COL["AWS Collector<br/>(ECS Fargate .NET)"]
        AWS_SM["Secrets Manager"]
        AWS_EB["EventBridge<br/>Scheduler"]
    end

    subgraph "Identity"
        ENTRA["Microsoft Entra ID"]
    end

    subgraph "DMZ"
        APIGEE["Apigee Gateway"]
    end

    subgraph "AWS Central Solution"
        subgraph "Ingestion"
            LAMBDA["Lambda API"]
            SQS["SQS"]
        end
        subgraph "Data Platform"
            DBR["Databricks"]
            LBP["Lakebase Primary"]
            LBR["Lakebase Replica"]
            UC["Unity Catalog"]
            FS["Feature Store"]
            MS["Model Serving"]
        end
        subgraph "Frontend"
            CF["CloudFront"]
            S3["S3 (React)"]
            APIGW["API Gateway"]
            WAF["ALB + WAF"]
            BACK["Backend (.NET)"]
        end
    end

    subgraph "End Users"
        USER["Data Engineers<br/>Product Owners<br/>Cloud Ops"]
    end

    %% Collection
    AZ_ADF & AZ_DBR & AZ_DB & AZ_COST --> AZ_COL
    AWS_GLUE & AWS_EMR & AWS_RDS & AWS_CE --> AWS_COL
    AZ_KV --> AZ_COL
    AWS_SM --> AWS_COL
    AWS_EB -->|schedule| AWS_COL

    %% Auth
    AZ_COL -->|OAuth2| ENTRA
    AWS_COL -->|OAuth2| ENTRA

    %% Ingestion
    AZ_COL -->|JWT| APIGEE
    AWS_COL -->|JWT| APIGEE
    APIGEE -->|validate| ENTRA
    APIGEE -->|VPC Lattice| LAMBDA
    LAMBDA --> SQS
    SQS --> DBR

    %% Storage
    DBR --> LBP
    LBR --> DBR
    UC -.-> LBP
    UC -.-> LBR
    DBR --> FS --> MS

    %% Presentation
    BACK --> LBP
    BACK --> MS
    WAF --> BACK
    APIGW --> WAF
    CF --> S3

    %% User
    USER -->|OIDC| ENTRA
    USER --> CF
    USER --> APIGW

    style ENTRA fill:#8e44ad,color:#fff
    style APIGEE fill:#f39c12,color:#fff
    style LBP fill:#27ae60,color:#fff
    style LBR fill:#27ae60,color:#fff
    style DBR fill:#e67e22,color:#fff
    style LAMBDA fill:#3498db,color:#fff
    style BACK fill:#2980b9,color:#fff
```

![End-to-End Architecture Diagram](diagrams/14-end-to-end-architecture.png)

---

*Document generated from DA meeting minutes (19 Feb 2026) and ADD v121 (Page 818054930, last updated 13 Mar 2026).*
