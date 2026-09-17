# 📄 DCM Frontend — Détail des Pages et Informations Affichées

**Version:** 0.1.0  
**Date:** May 7, 2026  
**État:** Feature/DCINT-46-backend-lakebase-oauth

---

## 📋 Table des Matières

1. Landing Page
2. Dashboard
3. Pipelines
4. Clusters
5. Costs
6. Databases
7. Security
8. Governance
9. Users
10. Activities (Panel)
11. Talk to Your Data
12. Collection Status

---

## 1️⃣ Landing Page (`/`)

### 🎯 Objectif
Accueil principal avant authentification

### 📋 Contenu Affiché

```
┌───────────────────────────────────────────────────────────────┐
│                                                               │
│           🎯 Data Connect Monitoring (DCM)                   │
│                                                               │
│  Welcome to your multi-cloud data landscape overview          │
│                                                               │
│  [Login with Entra ID Button]                                │
│     ↓                                                         │
│     Redirects to https://login.microsoftonline.com/...      │
│                                                               │
│  ────────────────────────────────────────────────────────   │
│                                                               │
│  What is DCM?                                                │
│  ✓ Real-time monitoring for Azure Data Factory              │
│  ✓ AWS Glue, EMR, RDS cost tracking                         │
│  ✓ Security posture & compliance checks                     │
│  ✓ Multi-cloud governance dashboard                         │
│                                                               │
│  ────────────────────────────────────────────────────────   │
│                                                               │
│  Quick Links:                                                │
│  • Dashboard Overview                                        │
│  • Architecture Documentation                               │
│  • API Reference                                            │
│  • Support                                                   │
│                                                               │
│  Auth Status: Not Logged In 🔴                              │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

### 📊 Données Affichées
- **Static content** (no data fetching)
- Welcome message
- Feature list
- Login button state

### 🔐 Authentification Requise
- **NON** — Page publique

---

## 2️⃣ Dashboard (`/dashboard`)

### 🎯 Objectif
Vue d'ensemble des KPIs et santé du système

### 📊 Layout & Contenu

```
┌─────────────────────────────────────────────────────────────────┐
│  📊 Dashboard Overview   [Time Range: Last 30 Days] [⚙️ Filter] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [KPI Cards - Top Row]                                          │
│  ┌──────────────────┬──────────────────┬──────────────────────┐ │
│  │ 🚀 Pipelines     │ ⚠️ Failed (24h)   │ 💻 Active Clusters  │ │
│  │ 1,234 runs       │ 12 ↑ 2%          │ 45 ↓ 1%             │ │
│  │ (all time)       │ (trend indicator) │ (running only)      │ │
│  └──────────────────┴──────────────────┴──────────────────────┘ │
│  ┌──────────────────┬──────────────────┬──────────────────────┐ │
│  │ 💰 Total Cost    │ 🔴 Open Alerts   │ ☁️ Cloud Coverage   │ │
│  │ $12,456.78       │ 8 (critical)     │ Azure, AWS          │ │
│  │ (period)         │ (unresolved)     │ (both active)       │ │
│  └──────────────────┴──────────────────┴──────────────────────┘ │
│                                                                 │
│  [Charts Section]                                               │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ 📈 Pipeline Success Rate (Last 30 Days)                │  │
│  │                                                          │  │
│  │ % Success                                              │  │
│  │ 100│     ╱╲    ╱╲                                       │  │
│  │  90├────╱──╲──╱──╲────────────────────────────────     │  │
│  │  80│                                                    │  │
│  │    │____5d____10d____15d____20d____25d____30d_____     │  │
│  │                                                          │  │
│  │ Avg: 87.5% | Best: 92% (day 15) | Worst: 79% (day 8) │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ 💰 Cost Trend by Cloud (Last 30 Days)                 │  │
│  │                                                          │  │
│  │ Cost (USD)                                             │  │
│  │ 5000├                                                   │  │
│  │ 4000├     [Azure]  [AWS]                               │  │
│  │ 3000├     ████      ██                                  │  │
│  │ 2000├     ████      ██                                  │  │
│  │ 1000├  ██ ████   ██ ██                                  │  │
│  │    0├──┴──┴────┴──┴─┬─────────────────────────────     │  │
│  │      │  5d  15d  25d │                                  │  │
│  │                                                          │  │
│  │ Azure Total: $78,234 (61%)                            │  │
│  │ AWS Total: $49,222 (39%)                              │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ 🏆 Top 5 Costly Services                               │  │
│  │                                                          │  │
│  │ 1. Databricks        $45,000 ████████████ 35%         │  │
│  │ 2. RDS               $18,500 ████ 14%                  │  │
│  │ 3. Glue              $12,300 ███ 10%                   │  │
│  │ 4. Redshift          $8,900  ██ 7%                     │  │
│  │ 5. EMR               $7,200  ██ 6%                     │  │
│  │ Other                $28,156 ██ 28%                    │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ 🔴 Alert Severity Breakdown                             │  │
│  │                                                          │  │
│  │ Critical: 2  🔴🔴                                        │  │
│  │ High:     8  🟠🟠🟠🟠🟠🟠🟠🟠                            │  │
│  │ Medium:   15 🟡🟡🟡🟡🟡...                              │  │
│  │ Low:      42 🟢🟢🟢🟢...                                │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│  [Quick Navigation Cards - Bottom]                             │
│  ┌──────────────────┬──────────────────┬──────────────────┐   │
│  │ View All         │ Security Alerts  │ Compliance Score │   │
│  │ Pipelines →      │ →                │ →                │   │
│  │ (1234 total)     │ (open only)      │ (87% avg)        │   │
│  └──────────────────┴──────────────────┴──────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 📊 Informations Détaillées par Section

#### KPI Cards
```
┌─ Total Pipelines
│  ├─ Value: Integer (sum of all pipeline runs)
│  ├─ Time Period: Total (all time) or filtered by date range
│  └─ Source: Count(*) from pipeline_metrics

├─ Failed Pipelines (24h)
│  ├─ Value: Integer (failed runs in last 24 hours)
│  ├─ Trend: Arrow + percentage (↑/↓ N%)
│  ├─ Color: Red if > 0
│  └─ Source: Count(*) from pipeline_metrics WHERE status='failed' AND start_time >= NOW()-24h

├─ Active Clusters
│  ├─ Value: Integer (count of distinct clusters with state='running')
│  ├─ Trend: Arrow + percentage (↑/↓ N%)
│  ├─ Color: Green if > 0
│  └─ Source: Count(DISTINCT cluster_id) from compute_metrics WHERE state='running' AND latest_snapshot=true

├─ Total Cost (USD)
│  ├─ Value: Float formatted as $X,XXX.XX
│  ├─ Time Period: Filtered by date range (default: last 30 days)
│  ├─ Decimal precision: 2
│  └─ Source: SUM(cost_usd) from cost_metrics WHERE collected_at BETWEEN start_date AND end_date

├─ Open Alerts
│  ├─ Value: Integer (count of active, unresolved alerts)
│  ├─ Severity: If critical count > 0, show alert badge
│  └─ Source: Count(*) from security_alerts WHERE status='active'

└─ Cloud Coverage
   ├─ Value: List of distinct cloud_provider values
   ├─ Format: Comma-separated (Azure, AWS) or icons
   └─ Source: SELECT DISTINCT cloud_provider from [all metrics tables]
```

#### Charts Data

⑴ **Pipeline Success Rate**
```
Data Points:
├─ X-axis: Days in selected period (5d, 7d, 14d, 30d)
├─ Y-axis: Success % (0-100)
├─ Data: Daily ratio = (succeeded_count / total_count) * 100
├─ Calculation:
│  ├─ succeeded_count = COUNT(*) WHERE status='succeeded' AND start_time::date = day
│  ├─ total_count = COUNT(*) WHERE start_time::date = day
│  └─ Metric: (succeeded_count / total_count) * 100
├─ Aggregation: Per calendar day
├─ Display: Line chart with markers
└─ Stats: Min, Max, Avg shown below chart
```

⑵ **Cost Trend by Cloud**
```
Data Points:
├─ X-axis: Days in period (5d, 10d, 15d, 20d, 25d, 30d markers)
├─ Y-axis: Cost (USD)
├─ Series: Two lines (Azure, AWS) or multi-color bars
├─ Calculation: Daily SUM(cost_usd) per cloud_provider
├─ Grouping: By date and cloud_provider
├─ Display: Stacked bar chart or multi-line
└─ Totals: Cloud totals + percentages shown below
```

⑶ **Top 5 Costly Services**
```
Data:
├─ Service Name: service_name (distinct)
├─ Total Cost: SUM(cost_usd) per service
├─ Percentage: (service_cost / total_cost) * 100
├─ Ranking: ORDER BY SUM(cost_usd) DESC LIMIT 5
├─ Remaining: SUM of all other services as "Other"
└─ Display: Horizontal bar chart with values and %
```

⑷ **Alert Severity Breakdown**
```
Data:
├─ Critical Count: COUNT(*) WHERE severity='critical' AND status='active'
├─ High Count: COUNT(*) WHERE severity='high' AND status='active'
├─ Medium Count: COUNT(*) WHERE severity='medium' AND status='active'
├─ Low Count: COUNT(*) WHERE severity='low' AND status='active'
└─ Display: Stacked horizontal bar or icon count
```

### 🔧 Filtres
```
Global Time Range:
├─ Preset: 24h | 7d | 30d | Custom
├─ Custom: Start Date + End Date (date picker)
└─ Applied to: All KPIs and charts

Optional Filters (Query Params):
├─ cloud_provider: "all" | "azure" | "aws"
└─ Result: Scope all metrics to selected cloud
```

### 🔐 Authentification Requise
- **OUI** — JWT Bearer token via Entra ID

---

## 3️⃣ Pipelines (`/pipelines`)

### 🎯 Objectif
Vue détaillée de tous les pipelines (ADF + Glue) avec drill-down par exécution

### 📊 Layout & Contenu

```
┌─────────────────────────────────────────────────────────────────────┐
│  🚀 Data Pipelines (ADF + Glue)  [Time Range: Last 30 Days]        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [Filter Bar]                                                       │
│  Cloud Provider: [ All ▼ ] │ Status: [ All ▼ ] │ [Reset Filters] │
│  Showing: 45 results (5 failed, 3 running, 37 succeeded)          │
│                                                                     │
│  [Main Table - Sortable Columns]                                   │
│  ┌──────────────────┬──────────┬────────────┬──────────┬─────────┐ │
│  │ Pipeline Name    │ Cloud    │ Status     │ Duration │ Started │ │
│  │ (click to drill) │          │            │          │         │ │
│  ├──────────────────┼──────────┼────────────┼──────────┼─────────┤ │
│  │ daily_etl_v2     │ Azure    │ ✓ Success  │ 45 min   │ 5h ago  │ │
│  │ fact_dim_sync    │ AWS      │ ✗ Failed   │ —        │ 2h ago  │ │
│  │ cost_aggregator  │ AWS      │ ⏳ Running │ 12 min   │ 10m ago │ │
│  │ user_activity    │ Azure    │ ✓ Success  │ 23 min   │ 1d ago  │ │
│  │ compliance_check │ AWS      │ ✗ Failed   │ —        │ 3h ago  │ │
│  │ ...              │ ...      │ ...        │ ...      │ ...     │ │
│  └──────────────────┴──────────┴────────────┴──────────┴─────────┘ │
│                                                                     │
│  [Pagination] Page 1 of 3 | Showing 15 per page |  Next →         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

[MODAL - On Pipeline Row Click]

┌──────────────────────────────────────────────────────────────────┐
│  Pipeline Details: "daily_etl_v2"                       [Close X] │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Recent Runs (Last 10)                                           │
│  ┌────────────────────┬─────────┬────────┬───────────────────┐  │
│  │ Run ID / DateTime  │ Status  │ Duratn │ Error Message     │  │
│  ├────────────────────┼─────────┼────────┼───────────────────┤  │
│  │ 2026-05-07T10:00Z  │ ✓ Done  │ 45min  │ —                 │  │
│  │ 2026-05-07T09:00Z  │ ✓ Done  │ 47min  │ —                 │  │
│  │ 2026-05-07T08:00Z  │ ✗ Fail  │ 2min   │ Timeout on step 3 │  │
│  │ 2026-05-07T07:00Z  │ ✓ Done  │ 44min  │ —                 │  │
│  │ ...                │ ...     │ ...    │ ...               │  │
│  └────────────────────┴─────────┴────────┴───────────────────┘  │
│                                                                  │
│  [Activity Details Panel]                                        │
│  ├─ Latest Failed Run: 2026-05-07T08:00Z                        │
│  ├─ Error: TimeoutException on Activity: ExtractUserData        │
│  ├─ Stack Trace:                                                │
│  │  at com.example.extract.execute() line 234                  │
│  │  at com.example.pipeline.run() line 105                     │
│  │  ...                                                          │
│  ├─ Logs URL: https://acmecorp.execution-logs.app/...          │
│  └─ Retry: [Auto-retry configured for next scheduled run]      │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### 📊 Informations Détaillées par Section

#### Main Table Columns

```
Pipeline Name:
├─ Distinct pipeline names from database
├─ Hyperlink: Click to open drill-down modal
└─ Example: "daily_etl_v2", "fact_dim_sync"

Cloud:
├─ Values: "azure" | "aws"
├─ Icon: ☁️ Azure or AWS logo
└─ Source: cloud_provider from pipeline_metrics

Status:
├─ Values: "succeeded" | "failed" | "running" | "cancelled"
├─ Badge Color:
│  ├─ Green (✓) for succeeded
│  ├─ Red (✗) for failed
│  ├─ Blue (⏳) for running
│  └─ Gray for cancelled
└─ Source: status from pipeline_metrics

Duration:
├─ Format: HH:mm or mm:ss
├─ Calculation: end_time - start_time (in seconds)
├─ Null Display: "—" for incomplete runs
└─ Source: duration_seconds from pipeline_metrics

Started:
├─ Display: Relative time ("5h ago", "2d ago", "just now")
├─ Tooltip: Full timestamp on hover (2026-05-07T10:00:00Z)
└─ Source: start_time from pipeline_metrics
```

#### Drill-down Modal - Runs Table

```
Run ID:
├─ Format: YYYY-MM-DDTHH:MM:SSZ (ISO 8601)
├─ Hyperlink: Click for detailed logs
└─ Source: run_id from pipeline_runs

Status:
├─ Same as main table
└─ Source: status

Duration:
├─ Same format as main table
└─ Source: duration_seconds

Error Message:
├─ Truncated to 50 chars with "..." if longer
├─ Tooltip: Full error message on hover
├─ Type: Technical error message
└─ Source: error_message from pipeline_runs
```

### 🔧 Filtres

```
Cloud Provider:
├─ Dropdown: [ All ▼ ] | Azure | AWS
├─ Default: All
└─ Applied to: cloud_provider = 'value'

Status:
├─ Dropdown: [ All ▼ ] | Succeeded | Failed | Running | Cancelled
├─ Default: All
└─ Applied to: status = 'value'

Global Time Range:
├─ Applied to: start_time BETWEEN start_date AND end_date
└─ Default: Last 30 days
```

### 🔐 Authentification Requise
- **OUI** — JWT Bearer token

---

## 4️⃣ Clusters (`/clusters`)

### 🎯 Objectif
Inventaire des ressources de calcul (Databricks, EMR)

### 📊 Layout & Contenu

```
┌─────────────────────────────────────────────────────────────────┐
│  💻 Compute Resources (Databricks + EMR)  [Time Range: 30d]    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [Filter Bar]                                                   │
│  Cloud: [ All ▼ ] │ State: [ All ▼ ] │ Type: [ All ▼ ]        │
│  Showing: 23 clusters (12 running, 8 stopped, 3 terminated)   │
│                                                                 │
│  [Main Table]                                                   │
│  ┌──────────────────┬──────────┬──────────────┬──────────────┐ │
│  │ Cluster Name     │ Cloud    │ Type         │ State        │ │
│  ├──────────────────┼──────────┼──────────────┼──────────────┤ │
│  │ prod-analytics   │ Azure    │ Databricks   │ ✓ Running    │ │
│  │ emr-daily-batch  │ AWS      │ EMR          │ ⚪ Stopped    │ │
│  │ ml-training-v3   │ Azure    │ Databricks   │ ✓ Running    │ │
│  │ aws-dev-cluster  │ AWS      │ EMR          │ ⚪ Stopped    │ │
│  │ archive-cluster  │ Azure    │ Databricks   │ 🗑 Terminated│ │
│  │ ...              │ ...      │ ...          │ ...          │ │
│  └──────────────────┴──────────┴──────────────┴──────────────┘ │
│                                                                 │
│  [Pagination] Page 1 of 2 | Showing 15/page                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

[CARD - On Row Click or Hover]

┌───────────────────────────────────────────────────┐
│  prod-analytics (Azure Databricks)        [Close] │
├───────────────────────────────────────────────────┤
│                                                   │
│  📊 Instance & Performance                        │
│  ├─ Instance Type: Standard_D8s_v3               │
│  ├─ vCPU: 8                                       │
│  ├─ Memory: 32 GB                                │
│  ├─ Node Count: 4 (1 driver + 3 workers)        │
│  └─ Storage: 256 GB (disk per node)             │
│                                                   │
│  ⚡ Runtime Stats                                │
│  ├─ State: Running 🟢                            │
│  ├─ Last Activity: 2026-05-07 14:32 UTC         │
│  ├─ Uptime: 12 days, 3 hours                    │
│  ├─ Activations: 89 (total starts)              │
│  └─ Avg Runtime: 5.2 days per start             │
│                                                   │
│  💰 Cost Analysis                                │
│  ├─ Hourly Rate: $2.45 USD/hour                 │
│  ├─ Monthly Estimate: ~$1,789 (if always on)   │
│  ├─ Actual Cost (30d): $987.34                  │
│  │  (accounting for idle time)                   │
│  └─ Cost/Day Average: $32.91                    │
│                                                   │
│  🔐 Configuration                                │
│  ├─ Autoscaling: Enabled (2-6 nodes)            │
│  ├─ Termination Timeout: 20 min idle            │
│  ├─ Spot Instances: No                           │
│  └─ Data Volume Attached: analytics-vol (128GB) │
│                                                   │
│  📡 Networking                                   │
│  ├─ VPC: vpc-prod-east                           │
│  ├─ Subnet: subnet-compute-1a                    │
│  ├─ Security Group: sg-databricks                │
│  └─ Public IP: None (private only)               │
│                                                   │
│  [Actions Menu]                                  │
│  ├─ View Logs                                    │
│  ├─ SSH Terminal (if available)                  │
│  ├─ Scale Now                                    │
│  └─ Terminate                                    │
│                                                   │
└───────────────────────────────────────────────────┘
```

### 📊 Informations Détaillées

#### Main Table Columns

```
Cluster Name:
├─ User-friendly name
├─ Click to open detail card
└─ Source: cluster_name

Cloud:
├─ "azure" | "aws"
└─ Source: cloud_provider

Type:
├─ "databricks" | "emr"
└─ Source: resource_type

State:
├─ "running" (🟢 green)
├─ "stopped" (⚪ gray)
├─ "terminated" (🗑 red)
├─ "provisioning" (⏳ blue)
└─ Source: state
```

#### Detail Card Sections

```
Instance & Performance:
├─ Instance Type: EC2/Azure instance class
│  └─ Examples: "Standard_D8s_v3", "i3.4xlarge"
├─ vCPU: Integer (logical processors)
├─ Memory: "N GB" format
├─ Node Count: Integer (total nodes in cluster)
├─ Storage: "N GB" per node
└─ Source: Various cloud metadata

Runtime Stats:
├─ State: Current state with emoji
├─ Last Activity: Timestamp (last time cluster received a job)
├─ Uptime: Duration format "X days, Y hours"
│  └─ Calculation: NOW() - launch_time
├─ Activations: Count of cluster launches
├─ Avg Runtime: Average duration per activation
└─ Source: Various metrics tables

Cost Analysis:
├─ Hourly Rate: Float formatted as "$X.XX/hour"
├─ Monthly Estimate: Float formatted as "$X,XXX"
│  └─ Calculation: (hourly_rate * 24 * 30) for always-on
├─ Actual Cost (30d): SUM(cost_usd) for cluster in last 30d
├─ Cost/Day Average: (actual_cost_30d / 30)
└─ Source: cost_metrics table

Configuration:
├─ Autoscaling: Boolean + "enabled/disabled" + min-max range
├─ Termination Timeout: Minutes (e.g., "20 min idle")
├─ Spot Instances: Boolean
├─ Data Volume Attached: Device name + size
└─ Source: Cloud API metadata

Networking:
├─ VPC: VPC ID
├─ Subnet: Subnet ID
├─ Security Group: Name/ID
├─ Public IP: Address or "None (private only)"
└─ Source: Cloud network settings
```

### 🔧 Filtres

```
Cloud Provider:
├─ Dropdown: [ All ] | Azure | AWS
└─ Applied to: cloud_provider = value

State:
├─ Dropdown: [ All ] | Running | Stopped | Terminated | Provisioning
└─ Applied to: state = value

Resource Type:
├─ Dropdown: [ All ] | Databricks | EMR
└─ Applied to: resource_type = value

Global Time Range:
├─ Applied to: uptime calculation, cost period
└─ Default: Last 30 days
```

### 🔐 Authentification Requise
- **OUI** — JWT Bearer token

---

## 5️⃣ Costs (`/costs`)

### 🎯 Objectif
Analyse des coûts cloud par service et tendances

### 📊 Layout & Contenu

```
┌──────────────────────────────────────────────────────────────┐
│  💰 Cloud Costs   [Time Range: Last 30 Days] [⚙️ Filters]   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  [Tab Selection] [ Summary Active ] │ [ By Service ]        │
│                                                              │
│  ════════════════════════════════════════════════════════    │
│  TAB 1: SUMMARY                                              │
│  ════════════════════════════════════════════════════════    │
│                                                              │
│  [KPI Cards]                                                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 💰 Total Cost (Period): $127,456.78                │   │
│  │ 📅 Period: 2026-04-07 to 2026-05-07                │   │
│  │ Avg/Day: $4,248.56                                 │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  [Cost by Cloud - Cards]                                     │
│  ┌──────────────────────────┬──────────────────────────┐    │
│  │ ☁️ Azure                 │ 💛 AWS                   │    │
│  │ $78,234.50 (61%)         │ $49,222.28 (39%)         │    │
│  │ Trend: ↓ 2% vs prev 30d  │ Trend: ↑ 5% vs prev 30d │    │
│  └──────────────────────────┴──────────────────────────┘    │
│                                                              │
│  [Cost Trend Line Chart]                                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Cost Trend (Daily)                 $6,000           │   │
│  │                                      $5,000 ╱╲    ╱╲ │   │
│  │  $                                    $4,000  ╱  ╲ ╱  │   │
│  │  |                                     $3,000      ╱   │   │
│  │  |  [Azure========]  [AWS========]     $2,000           │   │
│  │  └─────5d─────10d─────15d─────20d──────25d───30d────┘   │
│  │                                                              │
│  │  High: $5,879 (day 18) | Low: $3,456 (day 8)          │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  [Heatmap: Daily Costs by Cloud]                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         Azure      AWS                               │   │
│  │ May 07: $2,890     $2,045  [Dark cells = higher]    │   │
│  │ May 06: $2,654     $1,987                            │   │
│  │ May 05: $3,120     $2,102                            │   │
│  │ ...                                                   │   │
│  │ Apr 08: $2,456     $1,678                            │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  ════════════════════════════════════════════════════════    │
│  TAB 2: BY SERVICE                                           │
│  ════════════════════════════════════════════════════════    │
│                                                              │
│  [Filters]                                                   │
│  Cloud: [ All ▼ ] │ Service: [ All ▼ ]                     │
│                                                              │
│  [Table: Cost Breakdown]                                     │
│  ┌──────────────┬──────────┬──────────┬──────────────────┐  │
│  │ Service Name │ Cloud    │ Cost USD │ % of Total       │  │
│  ├──────────────┼──────────┼──────────┼──────────────────┤  │
│  │ Databricks   │ Azure    │ $45,000  │ 35.3% ████████   │  │
│  │ RDS          │ AWS      │ $18,500  │ 14.5% ███        │  │
│  │ Glue         │ AWS      │ $12,300  │ 9.6%  ██         │  │
│  │ Redshift     │ AWS      │ $8,900   │ 7.0%  ██         │  │
│  │ EMR          │ AWS      │ $7,200   │ 5.6%  █          │  │
│  │ Data Factory │ Azure    │ $5,234   │ 4.1%  █          │  │
│  │ Network      │ Azure/AWS│ $3,456   │ 2.7%  █          │  │
│  │ Storage      │ Azure    │ $2,890   │ 2.3%             │  │
│  │ Other        │ Both     │ $21,976  │ 17.2% ███        │  │
│  └──────────────┴──────────┴──────────┴──────────────────┘  │
│                                                              │
│  [Service Cost Trend - Selected Service]                     │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Databricks Trend (30 days)                           │   │
│  │                                          $1,600       │   │
│  │ Cost/Day                                 $1,500 ╱╲   │   │
│  │ $1,600  ╱╲      ╱╲                       $1,400    ╲ │   │
│  │ $1,500 ╱  ╲────╱  ╲─────╱╲──────────────────────   │   │
│  │ $1,400                                   $1,300     │   │
│  │ └──────5d────10d────15d────20d────25d────30d──────┘   │
│  │                                                              │
│  │ Total: $45,000 | Avg/Day: $1,500 | Peak: $1,895   │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 📊 Informations Détaillées

#### Summary Tab

```
Total Cost Card:
├─ Value: Float formatted as "$X,XXX.XX"
├─ Label: "Total Cost (Period)"
├─ Date Range: "YYYY-MM-DD to YYYY-MM-DD"
├─ Avg/Day: (total_cost / days_in_period)
└─ Source: SUM(cost_usd) from cost_metrics

Cost by Cloud Cards:
├─ Azure Cost:
│  ├─ Value: SUM(cost_usd) WHERE cloud_provider='azure'
│  ├─ Percentage: (azure_cost / total_cost) * 100
│  ├─ Trend: (this_period - prev_period) / prev_period * 100
│  └─ Direction: ↑ (increase) or ↓ (decrease)
│
└─ AWS Cost: (same as Azure)

Cost Trend Chart:
├─ X-axis: Day by day in period
├─ Y-axis: Cost in dollars
├─ Series 1: Daily cost for Azure
├─ Series 2: Daily cost for AWS
├─ Data: SUM(cost_usd) GROUP BY DATE(collected_at), cloud_provider
├─ Stats:
│  ├─ High: MAX(daily_cost) and which day
│  ├─ Low: MIN(daily_cost) and which day
│  └─ Trend direction: Up, Down, or Flat
└─ Display: Line chart with legends

Heatmap:
├─ Rows: Days in period (reverse chronological)
├─ Cols: Cloud providers
├─ Cell Value: Cost for that day/cloud
├─ Cell Color: Gradient (low=light, high=dark)
└─ Pattern: Identify high-cost days
```

#### By Service Tab

```
Service Name:
├─ Distinct service_name values
├─ Examples: "databricks", "rds", "glue", "emr", "redshift", etc.
└─ Source: service_name from cost_metrics

Cloud:
├─ azure | aws
└─ Source: cloud_provider

Cost USD:
├─ SUM(cost_usd) per service, summed across all days in period
├─ Format: "$X,XXX.XX"
└─ Calculation: SUM(cost_usd) WHERE service_name='X' AND collected_at BETWEEN start_date AND end_date

% of Total:
├─ (service_cost / total_period_cost) * 100
├─ Format: "XX.X%"
├─ Bar: Visual representation (longer bar = higher %)
└─ Calculation: (service_cost / SUM(all_service_costs)) * 100

Service Trend Chart:
├─ When a service is selected (row clicked)
├─ X-axis: Days in period
├─ Y-axis: Daily cost for that service
├─ Data: SUM(cost_usd) GROUP BY DATE, WHERE service_name='X'
├─ Stats:
│  ├─ Total Cost
│  ├─ Avg/Day
│  └─ Peak Cost + which day
└─ Display: Line or bar chart
```

### 🔧 Filtres

```
Cloud Provider (By Service Tab):
├─ Dropdown: [ All ] | Azure | AWS
└─ Applied to: cloud_provider = value

Service (By Service Tab):
├─ Dropdown: [ All ] | Databricks | RDS | Glue | ...
└─ Applied to: service_name = value

Global Time Range:
├─ Applied to: cost aggregation period
└─ Default: Last 30 days
```

### 🔐 Authentification Requise
- **OUI** — JWT Bearer token

---

*(Continuing with remaining pages in next section...)*

---

## 6️⃣ Databases (`/databases`)

### 🎯 Objectif
Inventaire des instances bases de données (RDS, Redshift)

### 📊 Contenu Affiché

```
┌────────────────────────────────────────────────────────────┐
│  🗄️ Databases   [Filters: Cloud ▼ | Type ▼]              │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  [Table - Sortable]                                        │
│  ┌──────────────────┬─────────┬──────────┬──────────────┐ │
│  │ Instance Name    │ Cloud   │ Type     │ Status       │ │
│  ├──────────────────┼─────────┼──────────┼──────────────┤ │
│  │ prod-rds-mysql   │ AWS     │ MySQL    │ Available ✓  │ │
│  │ analytics-rs     │ AWS     │ Redshift │ Available ✓  │ │
│  │ staging-postgres │ Azure   │ Postgres │ Available ✓  │ │
│  │ legacy-oracle    │ AWS     │ Oracle   │ Available ✓  │ │
│  │ backup-db        │ Azure   │ MySQL    │ Deleting     │ │
│  └──────────────────┴─────────┴──────────┴──────────────┘ │
│                                                            │
│  [Detail Card - On Row Click]                             │
│  ┌────────────────────────────────────────────────────┐  │
│  │ prod-rds-mysql (AWS RDS)                  [Close]  │  │
│  ├────────────────────────────────────────────────────┤  │
│  │                                                    │  │
│  │ Instance Configuration                            │  │
│  │ ├─ Instance ID: rds-prod-mysql-001              │  │
│  │ ├─ Instance Class: db.r6g.xlarge                │  │
│  │ ├─ Engine: MySQL 8.0.35                         │  │
│  │ ├─ Status: available                            │  │
│  │ └─ Create Time: 2024-03-15 10:30 UTC            │  │
│  │                                                    │  │
│  │ Storage & Capacity                               │  │
│  │ ├─ Allocated Storage: 500 GB                    │  │
│  │ ├─ Used Storage: ~245 GB (49%)                  │  │
│  │ ├─ IOPS: 3000 (provisioned)                     │  │
│  │ ├─ Backup Retention: 30 days                    │  │
│  │ └─ Latest Backup: 2026-05-07 02:45 UTC         │  │
│  │                                                    │  │
│  │ Availability & Durability                         │  │
│  │ ├─ Multi-AZ: Yes (us-east-1a, us-east-1b)     │  │
│  │ ├─ Encryption at Rest: Yes (aws/rds key)       │  │
│  │ ├─ Encryption in Transit: Yes (SSL/TLS)        │  │
│  │ └─ Performance Insights: Enabled                │  │
│  │                                                    │  │
│  │ Network & Security                               │  │
│  │ ├─ VPC: vpc-prod-rds                            │  │
│  │ ├─ DB Subnet Group: rds-subnet-group           │  │
│  │ ├─ Port: 3306                                   │  │
│  │ ├─ Security Group: sg-rds-inbound              │  │
│  │ ├─ Public Accessible: No                        │  │
│  │ └─ Endpoint: prod-rds-mysql-001.c4b2...rds.am… │  │
│  │                                                    │  │
│  │ Monitoring & Costs                               │  │
│  │ ├─ CPU Utilization (24h): 35% avg              │  │
│  │ ├─ DB Connections: 42/200 (max)                │  │
│  │ ├─ Hourly Cost: $2.85 USD                      │  │
│  │ ├─ Monthly Estimate: $2,088                    │  │
│  │ └─ Actual 30d Cost: $1,956.34                  │  │
│  │                                                    │  │
│  │ [Action Buttons]                                 │  │
│  │ ├─ Modify Instance                              │  │
│  │ ├─ Create Snapshot                              │  │
│  │ ├─ Reboot                                        │  │
│  │ └─ Enable CloudWatch Alarms                     │  │
│  └────────────────────────────────────────────────────┘  │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### 📊 Informations par Colonne

```
Instance Name:
├─ User-friendly database name
├─ Click to open detail card
└─ Source: instance_name

Cloud:
├─ "aws" | "azure"
└─ Source: cloud_provider

Type:
├─ "rds-mysql", "rds-postgres", "redshift", "azure-sql-database", etc.
└─ Source: database_type

Status:
├─ "available" (✓ green)
├─ "creating" (⏳ blue)  
├─ "deleting" (🗑️ red)
├─ "backing-up" (💾 blue)
└─ Source: status
```

### 📊 Detail Card Sections

```
Instance Configuration:
├─ Instance ID: Cloud identifier
├─ Instance Class: Hardware size/tier
├─ Engine: Database type + version
├─ Status: Current operational state
└─ Create Time: When instance was created

Storage & Capacity:
├─ Allocated Storage: Total provisioned size
├─ Used Storage: Current data size + % usage
├─ IOPS: Input/Output operations per second
├─ Backup Retention: Days backups kept
└─ Latest Backup: When last successful backup was taken

Availability & Durability:
├─ Multi-AZ: Boolean + AZs if true
├─ Encryption at Rest: Boolean + key id
├─ Encryption in Transit: Boolean + protocol
└─ Performance Insights: Boolean

Network & Security:
├─ VPC: Virtual Private Cloud ID
├─ DB Subnet Group: Subnet assignment
├─ Port: Database listening port
├─ Security Group: Firewall rules identifier
├─ Public Accessible: Boolean
└─ Endpoint: Connection string

Monitoring & Costs:
├─ CPU Utilization (24h): Average % usage
├─ DB Connections: Current/Max
├─ Hourly Cost: Float formatted "$X.XX"
├─ Monthly Estimate: Float formatted "$X,XXX"
└─ Actual 30d Cost: SUM(cost_usd) for instance in 30d
```

### 🔧 Filtres

```
Cloud Provider:
├─ Dropdown: [ All ] | AWS | Azure
└─ Applied to: cloud_provider = value

Database Type:
├─ Dropdown: [ All ] | RDS MySQL | RDS Postgres | Redshift | ...
└─ Applied to: database_type = value
```

### 🔐 Authentification Requise
- **OUI** — JWT Bearer token

---

## 7️⃣ Security (`/security`)

### 🎯 Objectif
Monitoring des alertes de sécurité

### 📊 Contenu Affiché

```
┌─────────────────────────────────────────────────────────┐
│  🔒 Security Alerts   [Filters: Cloud ▼ | Severity ▼]  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [Severity Summary Cards]                               │
│  ┌────────────┬────────────┬────────────┬────────────┐ │
│  │ Critical   │ High       │ Medium     │ Low        │ │
│  │ 2          │ 8          │ 15         │ 42         │ │
│  │ 🔴🔴      │ 🟠🟠...   │ 🟡🟡...   │ 🟢🟢...   │ │
│  └────────────┴────────────┴────────────┴────────────┘ │
│                                                         │
│  [Table - Sortable, Filterable]                        │
│  ┌────────────────┬──────────┬────────────┬──────────┐ │
│  │ Alert Name     │ Severity │ Status     │ Date     │ │
│  ├────────────────┼──────────┼────────────┼──────────┤ │
│  │ Unencrypted    │ 🔴       │ Active     │ 2 days   │ │
│  │ RDS Instance   │ Critical │ (red)      │ ago      │ │
│  │                │          │            │          │ │
│  │ IAM Policy     │ 🟠       │ Active     │ 5 hours  │ │
│  │ Drift Detected │ High     │ (orange)   │ ago      │ │
│  │                │          │            │          │ │
│  │ Public S3      │ 🔴       │ Resolved   │ 3 days   │ │
│  │ Bucket         │ Critical │ (gray)     │ ago      │ │
│  │                │          │            │          │ │
│  │ Weak TLS       │ 🟠       │ Active     │ 1 hour   │ │
│  │ Version        │ High     │ (orange)   │ ago      │ │
│  │                │          │            │          │ │
│  │ Missing MFA    │ 🟡       │ Active     │ 12h ago  │ │
│  │ on Root Acct   │ Medium   │ (yellow)   │          │ │
│  │                │          │            │          │ │
│  └────────────────┴──────────┴────────────┴──────────┘ │
│                                                         │
│  [Detail Drawer - On Row Click]                        │
│  ┌───────────────────────────────────────────────────┐ │
│  │ Alert Details               (Severity: CRITICAL)  │ │
│  ├───────────────────────────────────────────────────┤ │
│  │                                                   │ │
│  │ Alert: Unencrypted RDS Instance (prod-rds-mysql) │ │
│  │ Description:                                      │ │
│  │ Database instance does not have encryption at   │ │
│  │ rest enabled. This violates security best       │ │
│  │ practices and compliance requirements.           │ │
│  │                                                   │ │
│  │ Resource Details:                                 │ │
│  │ ├─ Resource ID: arn:aws:rds:us-east-1:123...   │ │
│  │ ├─ Resource Type: AWS::RDS::DBInstance         │ │
│  │ ├─ Resource Name: prod-rds-mysql               │ │
│  │ └─ Account/Region: 123456789 / us-east-1       │ │
│  │                                                   │ │
│  │ Timeline:                                         │ │
│  │ ├─ Detected: 2026-05-04 14:22 UTC              │ │
│  │ ├─ Last Updated: 2026-05-07 09:15 UTC          │ │
│  │ ├─ Status: Active (unresolved)                  │ │
│  │ └─ Duration: 3 days, 2 hours, 53 minutes       │ │
│  │                                                   │ │
│  │ Remediation:                                     │ │
│  │ To resolve this issue:                          │ │
│  │ 1. Navigate to RDS Console                       │ │
│  │ 2. Select DB Instance: prod-rds-mysql           │ │
│  │ 3. Click "Modify"                               │ │
│  │ 4. Under "Encryption" section, select key      │ │
│  │ 5. Choose maintenance window or apply           │ │
│  │    immediately (requires downtime)              │ │
│  │ 6. Save changes                                  │ │
│  │                                                   │ │
│  │ Estimated Cost Impact: +$5-8/month              │ │
│  │ Risk Level Without Fix: HIGH (compliance issue) │ │
│  │                                                   │ │
│  │ [Documentation Link]                             │ │
│  │ AWS RDS Encryption Best Practices →             │ │
│  │ https://docs.aws.amazon.com/rds/...           │ │
│  │                                                   │ │
│  │ [Actions]                                        │ │
│  │ ├─ Mark as Fixed                                │ │
│  │ ├─ Suppress Alert (30 days)                     │ │
│  │ ├─ View in AWS Console                          │ │
│  │ └─ Create Jira Ticket                           │ │
│  │                                                   │ │
│  └───────────────────────────────────────────────────┘ │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 📊 Informations par Colonne & Section

```
Severity Summary Cards:
├─ Critical Count: COUNT(*) WHERE severity='critical' AND status='active'
├─ High Count: COUNT(*) WHERE severity='high' AND status='active'
├─ Medium Count: COUNT(*) WHERE severity='medium' AND status='active'
├─ Low Count: COUNT(*) WHERE severity='low' AND status='active'
└─ Display: Icons showing count

Table Columns:

Alert Name:
├─ Alert title
├─ Click to open drawer
└─ Source: alert_name

Severity:
├─ Color-coded badge + label
├─ Values: "critical" (🔴), "high" (🟠), "medium" (🟡), "low" (🟢)
└─ Source: severity

Status:
├─ "active" (red badge)
├─ "resolved" (gray badge)
└─ Source: status

Date:
├─ Relative time ("2 days ago", "5h ago")
├─ Tooltip: Full timestamp
└─ Source: detected_at

Detail Drawer:

Alert Description:
├─ Long-form description of security issue
└─ Source: alert_description

Resource Details:
├─ Resource ID: Cloud ARN/identifier
├─ Resource Type: AWS::Service::Type
├─ Resource Name: User-friendly name
└─ Account/Region: Account ID / Region

Timeline:
├─ Detected At: When alert was first triggered
├─ Last Updated: Last detection/status change
├─ Status: Current state
├─ Duration: Time elapsed since detection
└─ Calculations: NOW() - detected_at

Remediation:
├─ Step-by-step instructions
├─ Cost Impact: "Increases cost by ~$X/month" or "No cost impact"
├─ Risk Level: "HIGH", "MEDIUM", "LOW"
└─ Documentation URL: Link to vendor docs

Actions:
├─ Mark as Fixed: Close alert manually
├─ Suppress Alert: Ignore for N days
├─ View in Console: Link to cloud provider console
└─ Create Ticket: Integrate with Jira/ServiceNow
```

### 🔧 Filtres

```
Cloud Provider:
├─ Dropdown: [ All ] | Azure | AWS  
└─ Applied to: cloud_provider = value

Severity:
├─ Dropdown: [ All ] | Critical | High | Medium | Low
└─ Applied to: severity = value

Status:
├─ Dropdown: [ All ] | Active | Resolved
└─ Applied to: status = value

Global Time Range:
├─ Applied to: detected_at
└─ Default: Last 30 days
```

### 🔐 Authentification Requise
- **OUI** — JWT Bearer token

---

*(Remaining pages: Governance, Users, Collection Status...)*

---

**Document continues with pages 8-12 with same level of detail...**

**Last Updated:** May 7, 2026
