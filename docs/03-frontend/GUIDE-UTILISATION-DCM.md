# 📚 DCM Frontend — Guide d'Utilisation Complet

**Version:** 0.1.0  
**Date:** May 7, 2026  
**État:** Feature/DCINT-46-backend-lakebase-oauth

---

## 🗺️ Navigation Frontend

La navigation se fait via une **barre latérale sticky** + **header sticky** avec time range picker global.

### **Menu Principal**
```
🏠 Landing Page (/)           ← Welcome page
📊 Dashboard (/dashboard)      ← KPI overview
🚀 Pipelines (/pipelines)      ← ADF + Glue runs
💻 Clusters (/clusters)        ← Compute resources (Databricks, EMR)
💰 Costs (/costs)              ← Cost analytics
🗄️ Databases (/databases)      ← RDS, Redshift instances
🔒 Security (/security)        ← Security alerts
✅ Governance (/governance)    ← Compliance scores (Standard Checks)
👥 Users (/users)              ← User & access management
🎤 Talk to Your Data (/talk-to-data)  ← AI assistant (future)
📊 Collection Status (/status) ← Collector health
```

---

## 📊 Pages Détaillées

### **1️⃣ Landing Page** (`/`)
**Type:** Standalone (full screen, no sidebar)

#### Affichage
- Welcome message
- Link buttons to main app
- Auth status badge

#### Paramètres
- None (static page)

#### Cas d'usage
- First-time visitor
- After logout

---

### **2️⃣ Dashboard** (`/dashboard`)
**Type:** Main page with sidebar + header

#### Affichage
```
┌─────────────────────────────────────────────┐
│ 📊 Dashboard Overview                       │
├─────────────────────────────────────────────┤
│  [KPI Cards - Header]                       │
│  ├─ Total Pipelines   │ 1,234 runs          │
│  ├─ Failed (24h)      │ 12 (↑ 2%)           │
│  ├─ Active Clusters   │ 45 (↓ 1%)           │
│  ├─ Total Cost (USD)  │ $12,456             │
│  ├─ Open Alerts       │ 8                   │
│  └─ Cloud Coverage    │ Azure, AWS          │
│                                              │
│  [Charts - Body]                            │
│  ├─ Pipeline Success Rate (24h, 7d, 30d)   │
│  ├─ Cost Trend by Cloud (30d)               │
│  ├─ Top 5 Costly Services                   │
│  └─ Alert Severity Breakdown                │
│                                              │
│  [Quick Navigation Cards]                   │
│  ├─ View All Pipelines (→)                  │
│  ├─ View All Alerts (→)                     │
│  └─ View Compliance Score (→)               │
└─────────────────────────────────────────────┘
```

#### Paramètres (Time Range Context)
```
Global Time Range Selector (Header)
├─ Preset: Last 24h | Last 7d | Last 30d | Custom
├─ Start Date (YYYY-MM-DD)
└─ End Date (YYYY-MM-DD)
```

#### Filtres intra-page
```
Optional Filters (Query Params):
├─ cloud_provider: "azure" | "aws" | null (all)
└─ (Backend aggregates automatically)
```

#### Backend API
```
GET /api/v1/dashboard/overview
  Params:
    - start_date (date, optional)
    - end_date (date, optional)
    - cloud_provider (string, optional)
  Response:
    {
      total_pipelines: int,
      failed_pipelines_24h: int,
      active_clusters: int,
      total_cost_usd: float,
      open_alerts: int,
      cloud_coverage: ["azure", "aws"],
      period: { start: date, end: date }
    }
```

#### Cas d'usage
- Executive dashboard
- Quick health check
- Identify anomalies (failed runs, cost spike)

---

### **3️⃣ Pipelines** (`/pipelines`)
**Type:** Main page with sidebar + header + drill-down

#### Affichage
```
┌──────────────────────────────────────────────────────┐
│ 🚀 Data Pipelines (ADF + Glue)                       │
├──────────────────────────────────────────────────────┤
│  [Filters]                                            │
│  ├─ Cloud Provider: All │ Azure │ AWS                │
│  └─ Status: All │ Succeeded │ Failed │ Running       │
│                                                       │
│  [Table]                                              │
│  │ Pipeline Name    │ Cloud  │ Status │ Duration │   │
│  │────────────────────────────────────────────────│   │
│  │ daily_etl_v2     │ Azure  │ ✓      │ 45 min   │   │
│  │ fact_dim_sync    │ AWS    │ ✗      │ —        │   │
│  │ cost_aggregator  │ AWS    │ ⏳     │ 12 min   │   │
│  │ ...                                             │   │
│                                                       │
│  [Drill-down Modal - On Pipeline Click]              │
│  ├─ Pipeline Name: "daily_etl_v2"                    │
│  ├─ Recent Runs:                                      │
│  │  ├─ Run #2026-05-07T10:00:00Z (✓ Succeeded)      │
│  │  ├─ Run #2026-05-07T09:00:00Z (✓ Succeeded)      │
│  │  └─ Run #2026-05-06T20:00:00Z (✗ Failed)         │
│  └─ Error Log: [truncated]                           │
└──────────────────────────────────────────────────────┘
```

#### Paramètres
```
[Top Filter Bar]
├─ Cloud Provider Filter: "all" | "azure" | "aws"
└─ Status Filter: "all" | "succeeded" | "failed" | "running" | "cancelled"

[Global Time Range]
└─ Applied to: start_time

[Drill-down Modal]
└─ Pipeline Name (dynamic): Opens run history for selected pipeline
```

#### Backend APIs
```
GET /api/v1/pipelines
  Params:
    - cloud_provider (string, optional)
    - status (string, optional)
    - start_date (date, optional)
    - end_date (date, optional)
  Response:
    [
      {
        pipeline_name: string,
        cloud_provider: "azure" | "aws",
        status: "succeeded" | "failed" | ...,
        start_time: datetime,
        duration_seconds: float | null,
        error_message: string | null
      },
      ...
    ]

GET /api/v1/pipelines/{pipeline_name}/runs
  Params:
    - cloud_provider (string)
    - start_date (date, optional)
    - end_date (date, optional)
  Response:
    [
      {
        run_id: string,
        status: string,
        start_time: datetime,
        end_time: datetime,
        duration_seconds: float,
        error_log: string | null
      },
      ...
    ]
```

#### Cas d'usage
- Monitor pipeline execution
- Diagnose failures
- Drill down to run history

---

### **4️⃣ Clusters** (`/clusters`)
**Type:** Main page with sidebar + header

#### Affichage
```
┌──────────────────────────────────────────────────────┐
│ 💻 Compute Resources (Databricks + EMR)              │
├──────────────────────────────────────────────────────┤
│  [Filters]                                            │
│  ├─ Cloud Provider: All │ Azure │ AWS                │
│  ├─ State: All │ Running │ Stopped │ Terminated     │
│  └─ Resource Type: All │ Databricks │ EMR            │
│                                                       │
│  [Table]                                              │
│  │ Cluster Name     │ Cloud  │ Type      │ State  │  │
│  │────────────────────────────────────────────────│  │
│  │ prod-analytics   │ Azure  │ Databricks│ Running│  │
│  │ emr-daily-batch  │ AWS    │ EMR       │ Stopped│  │
│  │ ml-training-v3   │ Azure  │ Databricks│ Running│  │
│  │ ...                                             │  │
│                                                       │
│  [Card Details - On Row Click]                       │
│  ├─ Instance Type: Standard_D8s_v3                   │
│  ├─ Cores: 64 vCPU                                   │
│  ├─ Memory: 256 GB                                   │
│  ├─ Cost/Hour: $2.45                                 │
│  ├─ Uptime: 12 days                                  │
│  └─ Last Activity: 2026-05-07 14:32 UTC              │
└──────────────────────────────────────────────────────┘
```

#### Paramètres
```
[Filters]
├─ Cloud Provider: "all" | "azure" | "aws"
├─ State: "all" | "running" | "stopped" | "terminated"
└─ Resource Type: "all" | "databricks" | "emr"

[Global Time Range]
└─ Applied to: last_activity, uptime calculation
```

#### Backend API
```
GET /api/v1/clusters
  Params:
    - cloud_provider (string, optional)
    - state (string, optional)
    - resource_type (string, optional)
    - start_date (date, optional)
    - end_date (date, optional)
  Response:
    [
      {
        cluster_id: string,
        cluster_name: string,
        cloud_provider: "azure" | "aws",
        resource_type: "databricks" | "emr",
        state: "running" | "stopped" | "terminated",
        instance_type: string,
        node_count: int,
        cost_per_hour_usd: float,
        last_activity: datetime,
        uptime_days: float
      },
      ...
    ]
```

#### Cas d'usage
- Monitor active clusters
- Identify idle resources
- Cost optimization

---

### **5️⃣ Costs** (`/costs`)
**Type:** Main page with sidebar + header

#### Affichage (2 Tabs)
```
┌──────────────────────────────────────────────────────┐
│ 💰 Cloud Costs                                       │
├──────────────────────────────────────────────────────┤
│  [Tabs] Summary │ By Service                         │
│                                                       │
│  TAB 1: Summary                                       │
│  ├─ Total Cost (Period): $127,456.78                │
│  ├─ Cost by Cloud:                                   │
│  │  ├─ Azure: $78,234 (61%)                         │
│  │  └─ AWS:   $49,222 (39%)                         │
│  ├─ Cost Trend Chart (30d line graph)                │
│  └─ Daily Cost Heatmap (small multiples)             │
│                                                       │
│  TAB 2: By Service                                   │
│  ├─ [Filter] Service: All │ Databricks │ RDS │ ...  │
│  └─ [Table]                                          │
│     │ Service Name   │ Cloud  │ Cost (USD) │ Trend│ │
│     │────────────────────────────────────────────│  │
│     │ Databricks     │ Azure  │ $45,000    │ ↑5% │  │
│     │ RDS            │ AWS    │ $18,500    │ ↓2% │  │
│     │ Glue           │ AWS    │ $12,300    │ ↑1% │  │
│     │ ...                                         │  │
└──────────────────────────────────────────────────────┘
```

#### Paramètres
```
[Tab Selection]
├─ Summary
└─ By Service

[Filters - By Service Tab]
├─ Cloud Provider: "all" | "azure" | "aws"
└─ Service: "all" | "databricks" | "rds" | "redshift" | "glue" | "emr" | ...

[Global Time Range]
└─ Applied to: cost aggregation period
```

#### Backend APIs
```
GET /api/v1/costs/summary
  Params:
    - cloud_provider (string, optional)
    - start_date (date, optional)
    - end_date (date, optional)
  Response:
    {
      total_cost_usd: float,
      by_cloud: {
        "azure": { total: float, percentage: float },
        "aws": { total: float, percentage: float }
      },
      trend: [
        { date: date, cost_usd: float },
        ...
      ]
    }

GET /api/v1/costs/by-service
  Params:
    - cloud_provider (string, optional)
    - service_name (string, optional)
    - start_date (date, optional)
    - end_date (date, optional)
  Response:
    [
      {
        service_name: string,
        cloud_provider: "azure" | "aws",
        total_cost_usd: float,
        daily_costs: [
          { date: date, cost_usd: float },
          ...
        ]
      },
      ...
    ]
```

#### Cas d'usage
- Cost governance
- Budget tracking
- Service cost attribution

---

### **6️⃣ Databases** (`/databases`)
**Type:** Main page with sidebar + header

#### Affichage
```
┌──────────────────────────────────────────────────────┐
│ 🗄️ Databases (RDS + Redshift)                       │
├──────────────────────────────────────────────────────┤
│  [Filters]                                            │
│  ├─ Cloud Provider: All │ Azure │ AWS                │
│  └─ Database Type: All │ RDS │ Redshift │ Postgres  │
│                                                       │
│  [Table]                                              │
│  │ Instance Name    │ Cloud │ Type       │ Status │  │
│  │────────────────────────────────────────────────│  │
│  │ prod-rds-mysql   │ AWS   │ RDS MySQL  │ ✓      │  │
│  │ analytics-rs     │ AWS   │ Redshift   │ ✓      │  │
│  │ staging-postgres │ Azure │ PostgreSQL │ ✓      │  │
│  │ ...                                             │  │
│                                                       │
│  [Details Card - On Row Click]                       │
│  ├─ Instance Class: db.r6g.xlarge                    │
│  ├─ Engine: PostgreSQL 14.6                          │
│  ├─ Storage: 500 GB                                  │
│  ├─ Backup Status: Latest 2h ago                     │
│  ├─ Multi-AZ: Yes                                    │
│  └─ Cost/Hour: $0.85                                 │
└──────────────────────────────────────────────────────┘
```

#### Paramètres
```
[Filters]
├─ Cloud Provider: "all" | "azure" | "aws"
└─ Database Type: "all" | "rds-mysql" | "rds-postgres" | "redshift" | ...

[Global Time Range]
└─ Not applied (static resource snapshots)
```

#### Backend API
```
GET /api/v1/databases
  Params:
    - cloud_provider (string, optional)
    - database_type (string, optional)
  Response:
    [
      {
        instance_id: string,
        instance_name: string,
        cloud_provider: "azure" | "aws",
        database_type: string,
        engine: string,
        instance_class: string,
        storage_gb: float,
        status: "available" | "creating" | "deleting",
        multi_az: boolean,
        cost_per_hour_usd: float,
        last_backup_time: datetime | null
      },
      ...
    ]
```

#### Cas d'usage
- Database inventory
- Capacity planning
- Backup compliance

---

### **7️⃣ Security** (`/security`)
**Type:** Main page with sidebar + header

#### Affichage
```
┌──────────────────────────────────────────────────────┐
│ 🔒 Security Alerts                                   │
├──────────────────────────────────────────────────────┤
│  [Filters]                                            │
│  ├─ Cloud Provider: All │ Azure │ AWS                │
│  ├─ Severity: All │ Critical │ High │ Medium │ Low  │
│  └─ Status: All │ Active │ Resolved                  │
│                                                       │
│  [Status Summary Cards]                              │
│  ├─ Critical: 2 (🔴 red)                             │
│  ├─ High: 8 (🟠 orange)                              │
│  ├─ Medium: 15 (🟡 yellow)                           │
│  └─ Low: 42 (🟢 green)                               │
│                                                       │
│  [Table - Sortable]                                  │
│  │ Alert Name         │ Severity │ Status    │ Date  │  │
│  │────────────────────────────────────────────────│  │
│  │ Unencrypted RDS    │ 🔴       │ Active    │ 2d   │  │
│  │ IAM Policy Drift   │ 🟠       │ Active    │ 5h   │  │
│  │ PublicS3 Bucket    │ 🔴       │ Resolved  │ 3d   │  │
│  │ ...                                             │  │
│                                                       │
│  [Detail Drawer - On Row Click]                      │
│  ├─ Alert: Unencrypted RDS Instance                  │
│  ├─ Resource: prod-rds-mysql                         │
│  ├─ Detected: 2026-05-04 14:22 UTC                   │
│  ├─ Recommendation: Enable RDS encryption at rest    │
│  └─ Documentation: [link to remediation guide]       │
└──────────────────────────────────────────────────────┘
```

#### Paramètres
```
[Filters]
├─ Cloud Provider: "all" | "azure" | "aws"
├─ Severity: "all" | "critical" | "high" | "medium" | "low"
└─ Status: "all" | "active" | "resolved"

[Global Time Range]
└─ Applied to: alert detection date
```

#### Backend API
```
GET /api/v1/security/alerts
  Params:
    - cloud_provider (string, optional)
    - severity (string, optional)
    - status (string, optional)
    - start_date (date, optional)
    - end_date (date, optional)
    - limit (int, default=100)
    - offset (int, default=0)
  Response:
    {
      total: int,
      alerts: [
        {
          alert_id: string,
          alert_name: string,
          resource_id: string,
          resource_type: string,
          cloud_provider: "azure" | "aws",
          severity: "critical" | "high" | "medium" | "low",
          status: "active" | "resolved",
          detected_at: datetime,
          resolved_at: datetime | null,
          recommendation: string,
          documentation_url: string | null
        },
        ...
      ]
    }
```

#### Cas d'usage
- Security posture monitoring
- Alert triage
- Compliance reporting

---

### **8️⃣ Governance** (`/governance`)
**Type:** Main page with sidebar + header + nested drill-down

#### Affichage
```
┌──────────────────────────────────────────────────────┐
│ ✅ Standard Checks (Compliance)                      │
├──────────────────────────────────────────────────────┤
│  [Views] Score │ Detailed │ By Landing Zone          │
│                                                       │
│  VIEW 1: Score Overview                              │
│  ├─ Overall Compliance: 87%                          │
│  │  ├─ Azure LZ-Prod: 92% (23/25 checks)            │
│  │  ├─ AWS Acc-Prod: 81% (18/22 checks)             │
│  │  └─ Azure LZ-Dev: 75% (12/16 checks)             │
│  ├─ Score Trend Chart (30d)                          │
│  └─ Risk Heatmap (LZ vs check category)              │
│                                                       │
│  VIEW 2: Detailed Checks                             │
│  ├─ [Filters]                                        │
│  │  ├─ Cloud: All │ Azure │ AWS                      │
│  │  ├─ State: All │ Compliant │ Non-Compliant │ N/A │
│  │  └─ Check Name: [search]                          │
│  │                                                    │
│  └─ [Table - Sortable, Paginated]                    │
│     │ Check Name            │ Cloud │ State  │ %  │  │
│     │────────────────────────────────────────────│  │
│     │ Encryption at Rest    │ Azure │ ✓      │92%│  │
│     │ MFA Enabled (Users)   │ AWS   │ ✗      │75%│  │
│     │ Logging Enabled       │ All   │ ⚠️     │87%│  │
│     │ ...                                         │  │
│                                                       │
│  VIEW 3: By Landing Zone                             │
│  ├─ [Dropdown] Select LZ: azure-lz-prod-fr           │
│  └─ [Details]                                        │
│     ├─ Overall Score: 92%                            │
│     ├─ Passing Checks: 23 ✓                          │
│     ├─ Failing Checks: 2 ✗                           │
│     └─ Non-Applicable: 1                             │
│        ├─ IAM Policy Compliance                      │
│        │  └─ 45 resources compliant, 3 non-compliant │
│        └─ [Drill-down to remediation]                │
└──────────────────────────────────────────────────────┘
```

#### Paramètres
```
[View Selection]
├─ Score Overview
├─ Detailed Checks
└─ By Landing Zone

[Filters - Detailed View]
├─ Cloud Provider: "all" | "azure" | "aws"
├─ Check State: "all" | "compliant" | "non_compliant" | "unknown"
├─ Check Name: [text search, partial match]
└─ Source LZ: [filter by landing zone]

[Nested Drill-down - By LZ View]
├─ Landing Zone selector (dropdown or tabs)
└─ Sub-resource details (IAM, encryption, etc.)

[Global Time Range]
└─ Applied to: check evaluation date
```

#### Backend APIs
```
GET /api/v1/standard-checks/score
  Params:
    - cloud_provider (string, optional)
    - source_lz_id (string, optional)
    - start_date (date, optional)
    - end_date (date, optional)
  Response:
    [
      {
        source_lz_id: string,
        cloud_provider: "azure" | "aws",
        noncompliant_count: int,
        compliant_count: int,
        unknown_count: int,
        compliance_percentage: float,
        check_categories: {
          "encryption": { compliant: int, total: int },
          "iam": { compliant: int, total: int },
          ...
        }
      },
      ...
    ]

GET /api/v1/standard-checks
  Params:
    - cloud_provider (string, optional)
    - source_lz_id (string, optional)
    - subscription_or_account_id (string, optional)
    - check_state (string, optional)
    - resource_type (string, optional)
    - check_name (string, optional)
    - start_date (date, optional)
    - end_date (date, optional)
    - limit (int, default=100)
    - offset (int, default=0)
  Response:
    {
      total: int,
      checks: [
        {
          check_id: string,
          check_name: string,
          cloud_provider: "azure" | "aws",
          source_lz_id: string,
          check_state: "compliant" | "non_compliant" | "unknown",
          resource_id: string,
          resource_type: string,
          check_effect: "allow" | "deny",
          non_check_reasons: [string],
          evaluated_at: datetime
        },
        ...
      ]
    }

GET /api/v1/landing-zones/details
  Params: none
  Response:
    [
      {
        lz_id: string,
        lz_name: string,
        ba_name: string,
        cloud_provider: "azure" | "aws",
        environment: "prod" | "staging" | "dev",
        region: string,
        valid_from: datetime
      },
      ...
    ]
```

#### Cas d'usage
- Compliance dashboard
- Policy enforcement
- Audit trail

---

### **9️⃣ Users** (`/users`)
**Type:** Main page with sidebar + header

#### Affichage
```
┌──────────────────────────────────────────────────────┐
│ 👥 Users & Access Management                         │
├──────────────────────────────────────────────────────┤
│  [Filters]                                            │
│  ├─ Cloud Provider: All │ Azure │ AWS                │
│  ├─ Status: All │ Active │ Deprovisioned             │
│  └─ Role: [search/multiselect]                       │
│                                                       │
│  [Table - Sortable]                                  │
│  │ User Name  │ Email             │ Cloud │ Status │  │
│  │──────────────────────────────────────────────────│  │
│  │ John Doe   │ john@company.com  │ Azure │ Active │  │
│  │ Jane Smith │ jane@company.com  │ AWS   │ Active │  │
│  │ Bob Legacy │ bob@legacy.com    │ All   │ Dep.   │  │
│  │ ...                                             │  │
│                                                       │
│  [Details Panel - On Row Click]                      │
│  ├─ User: John Doe                                   │
│  ├─ Email: john@company.com                          │
│  ├─ Status: Active                                   │
│  ├─ Last Access: 2026-05-07 10:15 UTC               │
│  ├─ Roles:                                           │
│  │  ├─ Azure: "Contributor"                         │
│  │  └─ AWS: "DataAnalyst"                            │
│  ├─ Group Memberships:                               │
│  │  ├─ data-engineers (Azure)                        │
│  │  └─ analytics-team (AWS)                          │
│  └─ Membership History:                              │
│     ├─ Joined data-engineers: 2024-01-15             │
│     └─ Removed from admin: 2023-11-20                │
└──────────────────────────────────────────────────────┘
```

#### Paramètres
```
[Filters]
├─ Cloud Provider: "all" | "azure" | "aws"
├─ Status: "all" | "active" | "deprovisioned"
└─ Role: [multiselect, partial match]

[Global Time Range]
└─ Applied to: last access time
```

#### Backend API
```
GET /api/v1/users
  Params:
    - cloud_provider (string, optional)
    - status (string, optional)
    - role (string, optional)
    - start_date (date, optional)
    - end_date (date, optional)
    - limit (int, default=100)
    - offset (int, default=0)
  Response:
    {
      total: int,
      users: [
        {
          user_id: string,
          user_name: string,
          email: string,
          cloud_provider: "azure" | "aws",
          status: "active" | "deprovisioned",
          last_access: datetime | null,
          roles: [string],
          groups: [string],
          valid_from: datetime,
          valid_to: datetime | null
        },
        ...
      ]
    }
```

#### Cas d'usage
- IAM governance
- Access reviews
- Deprovisioning audit

---

### **🔟 Activities** (`/api/v1/activities`)
**Type:** Backend endpoint (not a dedicated page, integrated into flows)

#### Affichage
- **Integrated into Pipelines page** (recent activities panel)
- **Available via API** for embedded widgets

#### Backend API
```
GET /api/v1/activities
  Params:
    - cloud_provider (string, optional)
    - source_lz_id (string, optional)
    - activity_type (string, optional)
    - user_email (string, optional)
    - start_date (date, optional)
    - end_date (date, optional)
    - limit (int, default=100)
  Response:
    [
      {
        activity_id: string,
        activity_type: string,
        cloud_provider: "azure" | "aws",
        source_lz_id: string,
        user_email: string | null,
        resource_id: string,
        resource_type: string,
        action: string,
        status: "success" | "failed",
        timestamp: datetime,
        details: dict (JSON blob)
      },
      ...
    ]
```

---

### **1️⃣1️⃣ Talk to Your Data** (`/talk-to-data`)
**Type:** Main page with sidebar + header

#### Affichage
```
┌──────────────────────────────────────────────────────┐
│ 🎤 Talk to Your Data (AI Assistant)                  │
├──────────────────────────────────────────────────────┤
│                                                       │
│  [Chat Interface]                                     │
│  ┌────────────────────────────────────────────────┐  │
│  │ System: I can help you analyze DCM data...    │  │
│  │                                                 │  │
│  │ User: Show me failed pipelines in last 24h    │  │
│  │                                                 │  │
│  │ Assistant: I found 3 failed pipelines...       │  │
│  │ [Table result embedded]                        │  │
│  └────────────────────────────────────────────────┘  │
│                                                       │
│  [Input]                                              │
│  └─ [Text field] + [Send button]                      │
│                                                       │
│  [Query Suggestions]                                  │
│  ├─ "What are my top 5 most expensive services?" │
│  ├─ "Show me security alerts by severity"         │
│  └─ "Which clusters are idle?"                    │
└──────────────────────────────────────────────────────┘
```

#### Paramètres
- Free-form text query
- (Backend: Parse with NLP/LLM, generate SQL, return results)

#### Status
- **NOT YET IMPLEMENTED** (Planned for future)

---

### **1️⃣2️⃣ Collection Status** (`/status`)
**Type:** Main page with sidebar + header

#### Affichage
```
┌──────────────────────────────────────────────────────┐
│ 📊 Collector Health & Data Quality                   │
├──────────────────────────────────────────────────────┤
│  [Status Cards]                                       │
│  ├─ 🟢 Azure Collector: Healthy (last run 5m ago)  │
│  ├─ 🟢 AWS Collector: Healthy (last run 2m ago)    │
│  ├─ 🟢 Databricks Pipeline: Healthy (last sync 1h) │
│  └─ 🟡 Lambda Ingestion: Degraded (25 retries)     │
│                                                       │
│  [Collection Runs Table]                             │
│  │ Run ID           │ Collector    │ Records │ Status│  │
│  │────────────────────────────────────────────────│  │
│  │ run-2026-05-07.. │ azure-col    │ 1,234  │ ✓    │  │
│  │ run-2026-05-07.. │ aws-col      │ 5,678  │ ✓    │  │
│  │ run-2026-05-06.. │ databricks   │ 12,345 │ ✓    │  │
│  │ ...                                             │  │
│                                                       │
│  [Watermark Status]                                  │
│  ├─ Azure: Last ingested at 2026-05-07T14:32 UTC    │
│  ├─ AWS: Last ingested at 2026-05-07T14:28 UTC      │
│  └─ Databricks: Last processed at 2026-05-07T14:00 │
└──────────────────────────────────────────────────────┘
```

#### Paramètres
```
[Global Time Range]
└─ Applied to: collection run history
```

#### Backend API
```
GET /api/v1/health
  Response:
    {
      status: "healthy" | "degraded" | "down",
      database: { connected: boolean, latency_ms: float },
      collectors: [
        {
          name: string,
          status: "healthy" | "degraded" | "down",
          last_run: datetime,
          last_record_count: int
        },
        ...
      ],
      watermarks: {
        azure: datetime,
        aws: datetime,
        databricks: datetime
      }
    }
```

#### Cas d'usage
- SLA monitoring
- Data freshness verification
- Troubleshooting collection issues

---

## 🎨 Global UI Elements

### **Header (Sticky)**
```
┌──────────────────────────────────────────┐
│ 📱 DCM Logo │ Page Title │ [Time Range] │ [User Menu]
│             │            │              │ ├─ My Profile
│             │            │              │ ├─ Logout
│             │            │              │ └─ ? Help
└──────────────────────────────────────────┘
```

#### Time Range Picker (Global Context)
```
[Preset Buttons] Last 24h | Last 7d | Last 30d | Custom
[Custom]
  Start Date: [YYYY-MM-DD picker]
  End Date:   [YYYY-MM-DD picker]
  [Apply]
```

### **Sidebar (Sticky)**
```
┌────────────────┐
│ 🏠 Dashboard   │ ← current page highlight
│ 🚀 Pipelines   │
│ 💻 Clusters    │
│ 💰 Costs       │
│ 🗄️ Databases   │
│ 🔒 Security    │
│ ✅ Governance  │
│ 👥 Users       │
│ 🎤 Talk Data   │
│ 📊 Status      │
│                │
│ [Collapse] ◄   │
└────────────────┘
```

---

## 🔐 Authentication & Authorization

### **Flow**
1. User visits `http://localhost:4000`
2. If `VITE_ENABLE_AUTH=true`:
   - MSAL.js initializes with Entra ID config
   - Redirect to `https://login.microsoftonline.com/...`
   - After login, get JWT accessToken
3. **All subsequent API calls inject:** `Authorization: Bearer {JWT}`
4. Backend validates token via Lambda Authorizer (Lambda validates audience = backend scope)

### **Environment Variables (Frontend)**
```
VITE_AZURE_CLIENT_ID=2ac61b57-9291-45d3-b735-26fc04df29b0
VITE_AZURE_TENANT_ID=329e91b0-e21f-48fb-a071-456717ecc28e
VITE_AZURE_SCOPE=api://15817864-589d-4a33-ada4-ec40fa309a7b/access_as_user
VITE_REDIRECT_URI=http://localhost:4000
VITE_ENABLE_AUTH=true | false
VITE_API_BASE_URL=http://localhost:8000
```

---

## 📱 Responsive Design

- **Desktop:** Sidebar left, main content right (full width)
- **Tablet:** Collapsible sidebar (hamburger menu)
- **Mobile:** Full-width content, sidebar drawer

---

## 🚀 Quick Start Guide for Users

### **First-Time Setup**
1. Open `http://localhost:4000`
2. Click "Login with Entra ID"
3. Enter your company credentials
4. You're redirected back to Dashboard

### **Navigate Pages**
- Use **sidebar** to switch between pages
- Use **time range picker** (top-right) to filter by date

### **Filter Data**
- Most pages have **filter cards** below the title
- Apply filters → table updates automatically

### **Drill Down**
- Click on table rows or cards to see **details/drill-down**
- Use **back** button or close modal to return

### **Export Data**
- *(Future)* Download buttons (CSV/Excel) coming soon

---

## 📋 Summary Table

| Page | Route | Purpose | Backend Calls | Filters |
|------|-------|---------|---------------|---------|
| Dashboard | `/dashboard` | KPI overview | `/overview` | Cloud, time range |
| Pipelines | `/pipelines` | Pipeline execution | `/pipelines`, `/pipelines/{name}/runs` | Cloud, status, time range |
| Clusters | `/clusters` | Compute inventory | `/clusters` | Cloud, state, type |
| Costs | `/costs` | Cost analytics | `/costs/summary`, `/costs/by-service` | Cloud, service, time range |
| Databases | `/databases` | Database inventory | `/databases` | Cloud, type |
| Security | `/security` | Alert monitoring | `/security/alerts` | Cloud, severity, status, time range |
| Governance | `/governance` | Compliance score | `/standard-checks/score`, `/standard-checks` | Cloud, state, LZ, time range |
| Users | `/users` | IAM governance | `/users` | Cloud, status, role, time range |
| Activities | `/activities` | Activity log | `/activities` | Cloud, LZ, type, time range |
| Status | `/status` | Collector health | `/health` | time range |

---

## 🔗 Related Documentation

- [Backend API Reference](../dcm-backend/README.md)
- [Data Model](../data-models.md)
- [Architecture](../01-architecture/ARCHITECTURE-DCM-FINALE.md)

---

**Last Updated:** May 7, 2026  
**Maintainer:** @agent  
**Status:** Complete (Feature/DCINT-46)
