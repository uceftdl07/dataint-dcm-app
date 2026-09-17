# Architecture Technique Globale - Azure Data Monitoring Platform

## [BUILD] Vue d'Ensemble de l'Architecture

Cette architecture respecte les standards INOX@Scale en utilisant les building blocs enterprise approuvés, avec une séparation claire entre zones publiques et privées.

## [CHART] Schéma d'Architecture Technique Complet

```mermaid
graph TB
    %% ===== INTERNET & USERS =====
    Users[👥 Utilisateurs Internes]
    Internet[🌐 Internet]
    
    %% ===== PUBLIC ZONE =====
    subgraph "🌍 Zone Publique - DMZ"
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
    subgraph "🔒 Zone Privée - Subnet Privé"
        subgraph "CT_1 - Backend Container"
            Backend[⚙️ Web App Container<br/>- .NET 8 API<br/>- Private Endpoints<br/>- Managed Identity]
        end
        
        subgraph "JOB_2 - Collector WebJob"
            Collector[📊 WebJob Collector<br/>- Scheduled Collection<br/>- Multi-Service Orchestration<br/>- Error Handling & Retry]
        end
        
        subgraph "DWH_1 - Databricks SQL Warehouse"
            Warehouse[🏛️ Data Warehouse<br/>- Delta Tables<br/>- SQL Analytics<br/>- Centralized Metrics]
        end

        subgraph "UC_1 - Unity Catalog"
            UnityCatalog[📚 Unity Catalog<br/>- Data Governance<br/>- Catalog/Schema/Table ACL<br/>- Central Data Access]
        end
        
        subgraph "SV_1 - Key Vault"
            KeyVault[🔑 Azure Key Vault<br/>- Databricks Credentials<br/>- API Keys<br/>- Certificates]
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
        
        subgraph "Databricks SQL & Catalog APIs"
            DB_API[🛢️ Databricks SQL/UC APIs<br/>- /api/2.0/sql/statements<br/>- /api/2.0/sql/warehouses<br/>- /api/2.1/unity-catalog/*<br/>- /api/2.0/permissions/*]
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
    Backend -->|Query Metrics| Warehouse
    Backend -->|Metadata & ACL Checks| UnityCatalog
    Backend -->|Fetch Secrets| KeyVault
    Backend -->|Application Logs| LogAnalytics
    Backend -->|Performance Metrics| AppInsights
    
    %% ===== COLLECTOR FLOWS =====
    Collector -->|Write Metrics Directly| Warehouse
    Collector -->|Resolve Catalog/Schema/Table| UnityCatalog
    Collector -->|Fetch Databricks Credentials| KeyVault
    
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
    Warehouse -->|Query & Audit Logs| LogAnalytics
    KeyVault -->|Audit Logs| LogAnalytics
    Collector -->|Job Execution Logs| LogAnalytics
    
    %% ===== STYLING =====
    classDef publicZone fill:#e3f2fd,stroke:#1976d2,stroke-width:2px
    classDef privateZone fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    classDef azureServices fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    classDef infrastructure fill:#e8f5e8,stroke:#388e3c,stroke-width:2px
    classDef security fill:#ffebee,stroke:#d32f2f,stroke-width:2px
    
    class SWA,AppGW,AAD publicZone
    class Backend,Collector,Warehouse,UnityCatalog,KeyVault privateZone
    class ADF_API,ADB_API,Monitor_API,Cost_API,DB_API,Security_API azureServices
    class LogAnalytics,AppInsights,ContainerRegistry infrastructure
    class Users,Internet security
```

## [TOOL] Description des Flux de Données

### [MOBILE] 1. Flux Utilisateur Frontend
```
Utilisateur → Internet → Static Web App (WEB_1) → Azure AD → SWA (Token)
```

### [LOCK] 2. Flux API Backend
```
SWA → Application Gateway (WAF_1) → Web App Container (CT_1) → Data Warehouse (DWH_1) via Unity Catalog (UC_1)
```

### [GEAR] 3. Flux Collector de Données
```
WebJob (JOB_2) → [6 Azure APIs] → Transformation → Direct Storage → Data Warehouse (DWH_1) via Unity Catalog (UC_1)
```

**[IMPORTANT]** Le Collector écrit **directement** dans le Data Warehouse et référence les objets via Unity Catalog. Il ne passe pas par l'API Backend pour l'ingestion des métriques. Cette approche est justifiée par :
- **Performance** : ingestion directe dans les tables analytiques
- **Gouvernance** : contrôle d'accès et traçabilité via Unity Catalog
- **Isolation** : séparation claire entre ingestion (batch) et consultation (API)

### [SHIELD] 4. Flux Sécurité et Secrets
```
CT_1 & JOB_2 → Key Vault (SV_1) → Databricks Credentials, Tokens & API Keys
```

## [ROCKET] Détail des APIs Azure Appelées

### 📋 **Data Factory Management API**
- **Endpoint Base**: `https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.DataFactory`
- **Méthodes utilisées**:
  - `GET /factories` - Liste des Data Factory
  - `GET /factories/{factoryName}/pipelines` - Pipelines par factory
  - `GET /factories/{factoryName}/pipelineruns` - Historique d'exécutions
  - `GET /factories/{factoryName}/metrics` - Métriques de performance

### ⚡ **Databricks Management API**
- **Endpoint Base**: `https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Databricks`
- **Méthodes utilisées**:
  - `GET /workspaces` - Liste des workspaces
  - `GET /workspaces/{workspaceName}/clusters` - Clusters par workspace
  - `GET /workspaces/{workspaceName}/jobs` - Jobs et leurs statuts
  - `GET /workspaces/{workspaceName}/permissions` - Gestion des permissions

### 📈 **Azure Monitor API**
- **Endpoint Base**: `https://management.azure.com/subscriptions/{subscriptionId}/providers/Microsoft.Insights`
- **Méthodes utilisées**:
  - `GET /metrics` - Métriques des ressources
  - `POST /logs/query` - Requêtes Log Analytics
  - `GET /activitylog` - Logs d'activité Azure
  - `GET /alertrules` - Règles d'alertes configurées

### 💰 **Cost Management API**
- **Endpoint Base**: `https://management.azure.com/subscriptions/{subscriptionId}/providers/Microsoft.CostManagement`
- **Méthodes utilisées**:
  - `POST /query` - Requêtes de coûts personnalisées
  - `GET /budgets` - Budgets configurés
  - `GET /exports` - Exports de données de coût
  - `GET /usagedetails` - Détails d'utilisation par ressource

### 🛢️ **Databricks SQL Warehouse + Unity Catalog APIs**
- **SQL Statements API**: `POST /api/2.0/sql/statements`
- **SQL Warehouses API**: `GET /api/2.0/sql/warehouses`
- **Unity Catalog API**: `GET /api/2.1/unity-catalog/catalogs|schemas|tables`
- **Permissions API**: `GET/PUT /api/2.0/permissions/{securable_type}/{full_name}`

### 🔒 **Security Center API**
- **Endpoint Base**: `https://management.azure.com/subscriptions/{subscriptionId}/providers/Microsoft.Security`
- **Méthodes utilisées**:
  - `GET /alerts` - Alertes de sécurité
  - `GET /assessments` - Évaluations de sécurité
  - `GET /recommendations` - Recommandations sécurité
  - `GET /complianceResults` - Résultats de conformité

## [BOARD] Building Blocs Utilisés

| Building Bloc | Service Azure | Fonction | Zone |
|---------------|---------------|----------|------|
| **WEB_1** | Static Web App | Frontend React | Publique |
| **WAF_1** | Application Gateway | Protection WAF + Load Balancer | DMZ |
| **CT_1** | Web App Container | Backend API .NET 8 | Privée |
| **JOB_2** | App Service WebJob | Collector de données | Privée |
| **DWH_1** | Databricks SQL Warehouse | Stockage analytique des métriques | Privée |
| **UC_1** | Unity Catalog | Gouvernance et contrôle d'accès des données | Privée |
| **SV_1** | Azure Key Vault | Gestion des secrets | Privée |

## [SECURITY] Mesures de Sécurité Implémentées

### 🔒 **Zone Privée (Subnet Privé)**
- **Private Endpoints** pour tous les services
- **Network Security Groups** avec règles restrictives
- **No public IP** pour CT_1, JOB_2, DWH_1

### 🛡️ **Protection WAF (WAF_1)**
- **OWASP Top 10** protection
- **DDoS Protection** Standard
- **SSL/TLS Termination**
- **Geographic filtering**

### 🔑 **Gestion des Identités**
- **Managed Identity** pour CT_1 et JOB_2
- **Azure AD Authentication** pour utilisateurs
- **RBAC** granulaire sur toutes les ressources

### 📊 **Monitoring et Audit**
- **Log Analytics** centralisé
- **Application Insights** pour performance
- **Security Center** pour compliance
- **Key Vault** audit logs

Cette architecture garantit une **sécurité enterprise**, une **performance optimale** et une **maintenabilité** conforme aux standards INOX@Scale.