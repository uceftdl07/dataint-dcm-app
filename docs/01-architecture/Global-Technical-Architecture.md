# Global Technical Architecture - Azure Data Monitoring Platform

## [BUILD] Architecture Overview

This architecture respects INOX@Scale standards using approved enterprise building blocks, with clear separation between public and private zones.

## [CHART] Complete Technical Architecture Diagram

```mermaid
graph TB
    %% ===== INTERNET & USERS =====
    Users[👥 Internal Users]
    Internet[🌐 Internet]
    
    %% ===== PUBLIC ZONE =====
    subgraph "🌍 Public Zone - DMZ"
        subgraph "WAF_1 - Application Gateway"
            AppGW[🛡️ Application Gateway<br/>- WAF Protection<br/>- SSL Termination<br/>- Load Balancing]
        end
        
        subgraph "WEB_1 - Static Web App"
            SWA[🎨 Static Web App<br/>- React Frontend<br/>- CDN Distribution<br/>- HTTPS Only]
        end
        
        subgraph "🔐 Azure AD (Entra ID)"
            AAD[Azure Active Directory<br/>- User Authentication<br/>- App Registration<br/>- Token Management]
        end
    end
    
    %% ===== PRIVATE ZONE =====
    subgraph "🔒 Private Zone - Private Subnet"
        subgraph "CT_1 - Backend Container"
            Backend[⚙️ Web App Container<br/>- .NET 8 API<br/>- Private Endpoints<br/>- Managed Identity]
        end
        
        subgraph "JOB_2 - Collector WebJob"
            Collector[📊 WebJob Collector<br/>- Scheduled Collection<br/>- Multi-Service Orchestration<br/>- Error Handling & Retry]
        end
        
        subgraph "DB_1 - PostgreSQL Database"
            PostgreSQL[🗄️ PostgreSQL Flexible<br/>- Time-series Tables<br/>- JSONB Metrics<br/>- Automated Backups]
        end
        
        subgraph "SV_1 - Key Vault"
            KeyVault[🔑 Azure Key Vault<br/>- Connection Strings<br/>- API Keys<br/>- Certificates]
        end
    end
    
    %% ===== AZURE SERVICES =====
    subgraph "☁️ Azure Management APIs"
        subgraph "Data Factory APIs"
            ADF_API[📋 Data Factory Management API<br/>- /factories<br/>- /pipelines<br/>- /pipelineruns<br/>- /metrics]
        end
        
        subgraph "Databricks APIs" 
            ADB_API[⚡ Databricks Management API<br/>- /workspaces<br/>- /clusters<br/>- /jobs<br/>- /permissions]
        end
        
        subgraph "Azure Monitor APIs"
            Monitor_API[📈 Azure Monitor API<br/>- /metrics<br/>- /logs<br/>- /activitylogs<br/>- /alerts]
        end
        
        subgraph "Cost Management APIs"
            Cost_API[💰 Cost Management API<br/>- /query (costs)<br/>- /budgets<br/>- /usagedetails<br/>- /exports]
        end
        
        subgraph "Database APIs"
            DB_API[🛢️ Azure Database APIs<br/>- SQL Database Management<br/>- PostgreSQL Management<br/>- MySQL Management<br/>- Cosmos DB Management]
        end
        
        subgraph "Security APIs"
            Security_API[🔒 Security Center API<br/>- /alerts<br/>- /assessments<br/>- /recommendations<br/>- /compliance]
        end
    end
    
    %% ===== AZURE INFRASTRUCTURE =====
    subgraph "🏗️ Azure Infrastructure Services"
        LogAnalytics[📊 Log Analytics Workspace<br/>- Application Logs<br/>- Performance Metrics<br/>- Security Events]
        
        AppInsights[📱 Application Insights<br/>- APM Monitoring<br/>- Performance Tracking<br/>- Exception Tracking]
        
        ContainerRegistry[📦 Container Registry<br/>- Backend Images<br/>- Security Scanning<br/>- Image Versioning]
    end
    
    %% ===== USER FLOWS =====
    Users -->|HTTPS| Internet
    Internet -->|DNS Resolution| SWA
    Users -->|Authentication| AAD
    AAD -->|ID Token| SWA
    SWA -->|API Calls + Bearer Token| AppGW
    AppGW -->|WAF Filtered| Backend
    
    %% ===== BACKEND FLOWS =====
    Backend -->|Read/Write Data| PostgreSQL
    Backend -->|Fetch Secrets| KeyVault
    Backend -->|Application Logs| LogAnalytics
    Backend -->|Performance Metrics| AppInsights
    
    %% ===== COLLECTOR FLOWS =====
    Collector -->|Store Metrics Directly| PostgreSQL
    Collector -->|Fetch Connection Strings| KeyVault
    
    %% ===== COLLECTOR TO AZURE APIs =====
    Collector -->|Authenticated Calls| ADF_API
    Collector -->|Authenticated Calls| ADB_API
    Collector -->|Authenticated Calls| Monitor_API
    Collector -->|Authenticated Calls| Cost_API
    Collector -->|Authenticated Calls| DB_API
    Collector -->|Authenticated Calls| Security_API
    
    %% ===== AUTHENTICATION FLOWS =====
    Collector -->|Managed Identity| AAD
    Backend -->|Managed Identity| AAD
    AAD -->|Access Tokens| ADF_API
    AAD -->|Access Tokens| ADB_API
    AAD -->|Access Tokens| Monitor_API
    AAD -->|Access Tokens| Cost_API
    AAD -->|Access Tokens| DB_API
    AAD -->|Access Tokens| Security_API
    
    %% ===== INFRASTRUCTURE FLOWS =====
    Backend -->|Pull Images| ContainerRegistry
    SWA -->|Content Delivery| Users
    
    %% ===== MONITORING FLOWS =====
    AppGW -->|WAF Logs| LogAnalytics
    PostgreSQL -->|DB Logs| LogAnalytics
    KeyVault -->|Audit Logs| LogAnalytics
    Collector -->|Job Execution Logs| LogAnalytics
    
    %% ===== STYLING =====
    classDef publicZone fill:#e3f2fd,stroke:#1976d2,stroke-width:2px
    classDef privateZone fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    classDef azureServices fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    classDef infrastructure fill:#e8f5e8,stroke:#388e3c,stroke-width:2px
    classDef security fill:#ffebee,stroke:#d32f2f,stroke-width:2px
    
    class SWA,AppGW,AAD publicZone
    class Backend,Collector,PostgreSQL,KeyVault privateZone
    class ADF_API,ADB_API,Monitor_API,Cost_API,DB_API,Security_API azureServices
    class LogAnalytics,AppInsights,ContainerRegistry infrastructure
    class Users,Internet security
```

## [TOOL] Data Flow Description

### [MOBILE] 1. Frontend User Flow
```
User → Internet → Static Web App (WEB_1) → Azure AD → SWA (Token)
```

### [LOCK] 2. Backend API Flow
```
SWA → Application Gateway (WAF_1) → Web App Container (CT_1) → PostgreSQL (DB_1)
```

### [GEAR] 3. Data Collector Flow
```
WebJob (JOB_2) → [6 Azure APIs] → Transformation → Direct Storage → PostgreSQL (DB_1)
```

**[IMPORTANT]** The Collector accesses PostgreSQL **directly** via Entity Framework Core (`IDbContextFactory<AzureMonitoringDbContext>`). It does not go through the Backend API for database operations. This approach is justified by:
- **Performance**: Avoids additional API round-trips
- **Simplicity**: Reuses existing EF Core logic
- **Isolation**: Clear separation between collection (batch) and consultation (API)

### [SHIELD] 4. Security & Secrets Flow
```
CT_1 & JOB_2 → Key Vault (SV_1) → Connection Strings & API Keys
```

## [ROCKET] Azure APIs Details

### 📋 **Data Factory Management API**
- **Base Endpoint**: `https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.DataFactory`
- **Methods Used**:
  - `GET /factories` - List Data Factories
  - `GET /factories/{factoryName}/pipelines` - Pipelines per factory
  - `GET /factories/{factoryName}/pipelineruns` - Execution history
  - `GET /factories/{factoryName}/metrics` - Performance metrics

### ⚡ **Databricks Management API**
- **Base Endpoint**: `https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Databricks`
- **Methods Used**:
  - `GET /workspaces` - List workspaces
  - `GET /workspaces/{workspaceName}/clusters` - Clusters per workspace
  - `GET /workspaces/{workspaceName}/jobs` - Jobs and their status
  - `GET /workspaces/{workspaceName}/permissions` - Permissions management

### 📈 **Azure Monitor API**
- **Base Endpoint**: `https://management.azure.com/subscriptions/{subscriptionId}/providers/Microsoft.Insights`
- **Methods Used**:
  - `GET /metrics` - Resource metrics
  - `POST /logs/query` - Log Analytics queries
  - `GET /activitylog` - Azure activity logs
  - `GET /alertrules` - Configured alert rules

### 💰 **Cost Management API**
- **Base Endpoint**: `https://management.azure.com/subscriptions/{subscriptionId}/providers/Microsoft.CostManagement`
- **Methods Used**:
  - `POST /query` - Custom cost queries
  - `GET /budgets` - Configured budgets
  - `GET /exports` - Cost data exports
  - `GET /usagedetails` - Usage details per resource

### 🛢️ **Azure Database APIs**
- **SQL Database**: `Microsoft.Sql/servers/{serverName}/databases`
- **PostgreSQL**: `Microsoft.DBforPostgreSQL/flexibleServers`
- **MySQL**: `Microsoft.DBforMySQL/flexibleServers`
- **Cosmos DB**: `Microsoft.DocumentDB/databaseAccounts`

### 🔒 **Security Center API**
- **Base Endpoint**: `https://management.azure.com/subscriptions/{subscriptionId}/providers/Microsoft.Security`
- **Methods Used**:
  - `GET /alerts` - Security alerts
  - `GET /assessments` - Security assessments
  - `GET /recommendations` - Security recommendations
  - `GET /complianceResults` - Compliance results

## [BOARD] Building Blocks Used

| Building Block | Azure Service | Function | Zone |
|----------------|---------------|----------|------|
| **WEB_1** | Static Web App | React Frontend | Public |
| **WAF_1** | Application Gateway | WAF Protection + Load Balancer | DMZ |
| **CT_1** | Web App Container | .NET 8 Backend API | Private |
| **JOB_2** | App Service WebJob | Data Collector | Private |
| **DB_1** | PostgreSQL Flexible | Main Database | Private |
| **SV_1** | Azure Key Vault | Secrets Management | Private |

## [SECURITY] Implemented Security Measures

### 🔒 **Private Zone (Private Subnet)**
- **Private Endpoints** for all services
- **Network Security Groups** with restrictive rules
- **No public IP** for CT_1, JOB_2, DB_1

### 🛡️ **WAF Protection (WAF_1)**
- **OWASP Top 10** protection
- **DDoS Protection** Standard
- **SSL/TLS Termination**
- **Geographic filtering**

### 🔑 **Identity Management**
- **Managed Identity** for CT_1 and JOB_2
- **Azure AD Authentication** for users
- **Granular RBAC** on all resources

### 📊 **Monitoring and Audit**
- **Centralized Log Analytics**
- **Application Insights** for performance
- **Security Center** for compliance
- **Key Vault** audit logs

This architecture ensures **enterprise security**, **optimal performance** and **maintainability** compliant with INOX@Scale standards.