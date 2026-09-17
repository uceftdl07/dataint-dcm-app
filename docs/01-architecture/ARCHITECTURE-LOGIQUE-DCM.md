# 🧩 Architecture Logique DCM - Data Connect Monitoring

**Version** : 3.0  
**Date** : 14 Janvier 2026  
**Type** : Architecture Logique et Packages

---

## 📋 Vue d'Ensemble

Ce document décrit l'organisation logique de la solution DCM :
- **Couches logicielles** de la solution globale
- **Packages et modules** .NET et React
- **Architecture logique** des collecteurs
- **Interfaces et contrats** entre composants

---

## 🏗️ Architecture Logique Globale

```mermaid
graph TB
    subgraph PresentationLayer["🎨 Couche Présentation"]
        subgraph React["React Application (TypeScript)"]
            Pages[Pages<br/>Dashboard, MultiCloud, Costs, Analytics]
            Components[Components<br/>Charts, Tables, Filters]
            Hooks[Custom Hooks<br/>useMetrics, useCosts, useAuth]
            Services[Services<br/>API Client, Auth MSAL]
        end
    end
    
    subgraph ApplicationLayer["⚙️ Couche Application"]
        subgraph BackendAPI["Backend API .NET 8"]
            Controllers[Controllers<br/>MetricsController, CostsController]
            Services_BE[Services<br/>MetricsService, AuthorizationService]
            Repositories[Repositories<br/>DataLakeRepository, DatabricksRepository]
        end
        
        subgraph IngestionAPI["Ingestion API .NET 8"]
            FunctionApp[Azure Function<br/>IngestMetrics HTTP Trigger]
            Validation[Validation Layer<br/>Schema Validator]
            EventPublisher[Event Publisher<br/>EventHub Client]
        end
    end
    
    subgraph DataLayer["💾 Couche Données"]
        subgraph DataPlatform["Data Platform"]
            EventHub[EventHub<br/>Ingestion Buffer]
            DataLake[Data Lake Gen2<br/>Bronze/Silver/Gold]
            Databricks_Jobs[Databricks<br/>Transformation Jobs]
        end
    end
    
    subgraph CollectorLayer["📡 Couche Collecte"]
        subgraph CollectorApp["Collector .NET 8"]
            WorkerService[Worker Service<br/>Background Service]
            Orchestrator[Collection Orchestrator<br/>Scheduling Logic]
            Adapters[Cloud Adapters<br/>Azure, AWS]
            Publishers[Event Publishers<br/>HTTP Client]
        end
    end
    
    Pages -->|API Calls| Controllers
    Components -->|Use| Hooks
    Hooks -->|Use| Services
    Services -->|HTTP REST| Controllers
    
    Controllers -->|Business Logic| Services_BE
    Services_BE -->|Data Access| Repositories
    Repositories -->|Query Delta Lake| DataLake
    Repositories -->|SQL Queries| Databricks_Jobs
    
    FunctionApp -->|Validate| Validation
    Validation -->|Publish| EventPublisher
    EventPublisher -->|Send Events| EventHub
    EventHub -->|Capture| DataLake
    
    WorkerService -->|Schedule| Orchestrator
    Orchestrator -->|Collect| Adapters
    Adapters -->|Normalize| Publishers
    Publishers -->|POST HTTPS| FunctionApp
    
    Databricks_Jobs -->|Transform| DataLake
    
    classDef presentation fill:#64B5F6,stroke:#1976D2,stroke-width:3px
    classDef application fill:#81C784,stroke:#388E3C,stroke-width:3px
    classDef data fill:#BA68C8,stroke:#7B1FA2,stroke-width:3px
    classDef collector fill:#FF8A65,stroke:#D84315,stroke-width:3px
    
    class PresentationLayer,React,Pages,Components,Hooks,Services presentation
    class ApplicationLayer,BackendAPI,IngestionAPI,Controllers,Services_BE,Repositories,FunctionApp,Validation,EventPublisher application
    class DataLayer,DataPlatform,EventHub,DataLake,Databricks_Jobs data
    class CollectorLayer,CollectorApp,WorkerService,Orchestrator,Adapters,Publishers collector
```

---

## 📦 Structure des Packages - Solution Globale

### Backend API .NET 8

```
DataMonitoring.Solution/
│
├── DataMonitoring.Api/                      # Web API REST
│   ├── Controllers/
│   │   ├── MetricsController.cs            # GET /api/metrics
│   │   ├── CostsController.cs              # GET /api/costs
│   │   └── DatabricksController.cs         # GET /api/ml/predictions
│   ├── Middleware/
│   │   ├── AuthorizationMiddleware.cs      # RBAC par subscription
│   │   └── ExceptionHandlingMiddleware.cs
│   ├── Program.cs
│   └── appsettings.json
│
├── DataMonitoring.Application/              # Logique métier
│   ├── Services/
│   │   ├── IMetricsService.cs
│   │   ├── MetricsService.cs
│   │   ├── IAuthorizationService.cs
│   │   └── AuthorizationService.cs         # Filtrage par BU/subscription
│   ├── DTOs/
│   │   ├── MetricQueryRequest.cs
│   │   ├── MetricResponse.cs
│   │   └── CostSummaryResponse.cs
│   └── Validators/
│       └── MetricQueryValidator.cs
│
├── DataMonitoring.Domain/                   # Modèles métier
│   ├── Entities/
│   │   ├── Metric.cs
│   │   ├── Cost.cs
│   │   └── Subscription.cs
│   ├── Enums/
│   │   ├── CloudProvider.cs                # Azure, AWS
│   │   ├── ServiceType.cs
│   │   └── Environment.cs
│   └── ValueObjects/
│       ├── SubscriptionId.cs
│       └── BusinessUnit.cs
│
├── DataMonitoring.Infrastructure.DataLake/  # Accès Data Lake
│   ├── Repositories/
│   │   ├── IDataLakeRepository.cs
│   │   ├── DataLakeRepository.cs           # Queries Delta Lake
│   │   └── DatabricksRepository.cs         # SQL Warehouse queries
│   ├── Configuration/
│   │   └── DataLakeOptions.cs
│   └── Mappers/
│       └── DeltaLakeMapper.cs
│
└── DataMonitoring.Infrastructure.Auth/      # Authentification
    ├── Services/
    │   ├── ITokenValidationService.cs
    │   └── EntraIdTokenValidator.cs
    └── Models/
        └── UserClaims.cs
```

### Ingestion Function .NET 8

```
DataMonitoring.Ingestion/
│
├── Functions/
│   └── IngestMetrics.cs                     # HTTP Trigger
│
├── Services/
│   ├── IPayloadValidator.cs
│   ├── PayloadValidator.cs
│   └── IEventHubPublisher.cs
│
├── Models/
│   └── MetricBatch.cs
│
├── host.json
└── local.settings.json
```

### Frontend React TypeScript

```
dcm-dashboard/
│
├── src/
│   ├── pages/                               # Pages routes
│   │   ├── Dashboard.tsx
│   │   ├── MultiCloudView.tsx
│   │   ├── CostAnalysis.tsx
│   │   └── MLInsights.tsx
│   │
│   ├── components/                          # Composants réutilisables
│   │   ├── common/
│   │   │   ├── MetricCard.tsx
│   │   │   ├── ChartContainer.tsx
│   │   │   └── FilterBar.tsx
│   │   ├── metrics/
│   │   │   ├── MetricsTimeSeries.tsx
│   │   │   └── MetricsComparison.tsx
│   │   └── costs/
│   │       ├── CostBreakdown.tsx
│   │       └── CostTrends.tsx
│   │
│   ├── hooks/                               # Custom React Hooks
│   │   ├── useMetrics.ts
│   │   ├── useCosts.ts
│   │   ├── useAuth.ts                      # MSAL.js integration
│   │   └── useFilters.ts
│   │
│   ├── services/                            # API clients
│   │   ├── api/
│   │   │   ├── metricsApi.ts
│   │   │   ├── costsApi.ts
│   │   │   └── mlApi.ts
│   │   ├── auth/
│   │   │   └── msalConfig.ts              # EntraID config
│   │   └── httpClient.ts
│   │
│   ├── models/                              # TypeScript types
│   │   ├── Metric.ts
│   │   ├── Cost.ts
│   │   ├── CloudProvider.ts
│   │   └── User.ts
│   │
│   ├── store/                               # État global (React Query)
│   │   ├── queryClient.ts
│   │   └── cacheConfig.ts
│   │
│   └── utils/
│       ├── formatters.ts
│       ├── dateUtils.ts
│       └── chartHelpers.ts
│
├── public/
├── package.json
└── tsconfig.json
```

---

## 🔧 Architecture Logique Collecteur

### Vue d'Ensemble Packages Collecteur

```mermaid
graph TB
    subgraph HostLayer["🎯 Host Layer"]
        Program[Program.cs<br/>Host Configuration<br/>DI Container Setup]
        Worker[CollectorWorker.cs<br/>IHostedService<br/>Lifecycle Management]
    end
    
    subgraph CoreLayer["⚙️ Core Layer"]
        Orchestrator[CollectionOrchestrator<br/>Schedule Management<br/>Error Handling]
        AdapterFactory[CloudAdapterFactory<br/>Provider Selection<br/>Adapter Creation]
        Normalizer[MetricsNormalizer<br/>Format Unification<br/>Data Enrichment]
    end
    
    subgraph AdaptersLayer["☁️ Adapters Layer"]
        IAdapter[ICloudProviderAdapter<br/>Interface]
        AzureAdapter[AzureMetricsAdapter<br/>Azure SDK Integration]
        AwsAdapter[AwsMetricsAdapter<br/>AWS SDK Integration]
    end
    
    subgraph PublishersLayer["📨 Publishers Layer"]
        IPublisher[IEventPublisher<br/>Interface]
        HttpPublisher[HttpEventPublisher<br/>HTTP Client<br/>Retry Logic Polly]
    end
    
    subgraph ModelsLayer["📦 Models Layer"]
        Config[CollectionConfig<br/>Settings]
        UnifiedMetric[UnifiedMetric<br/>Canonical Format]
        Enums[CloudProvider<br/>ServiceType<br/>MetricStatus]
    end
    
    subgraph SecretsLayer["🔐 Secrets Layer"]
        ISecretsProvider[ISecretsProvider<br/>Interface]
        AzureSecretsProvider[AzureSecretsProvider<br/>Key Vault SDK]
        AwsSecretsProvider[AwsSecretsProvider<br/>Secrets Manager SDK]
    end
    
    subgraph AuthLayer["🔑 Authentication Layer"]
        IAuthProvider[IAuthProvider<br/>Interface]
        EntraIdAuthProvider[EntraIdAuthProvider<br/>Azure.Identity SDK<br/>OAuth 2.0]
    end
    
    Program -->|Configure| Worker
    Worker -->|Execute| Orchestrator
    
    Orchestrator -->|Create Adapter| AdapterFactory
    AdapterFactory -->|Instantiate| IAdapter
    IAdapter -->|Implemented by| AzureAdapter
    IAdapter -->|Implemented by| AwsAdapter
    
    AzureAdapter -->|Collect| UnifiedMetric
    AwsAdapter -->|Collect| UnifiedMetric
    
    Orchestrator -->|Normalize| Normalizer
    Normalizer -->|Produce| UnifiedMetric
    
    Orchestrator -->|Publish| IPublisher
    IPublisher -->|Implemented by| HttpPublisher
    
    HttpPublisher -->|Use| IAuthProvider
    IAuthProvider -->|Implemented by| EntraIdAuthProvider
    
    HttpPublisher -->|Use| ISecretsProvider
    ISecretsProvider -->|Implemented by| AzureSecretsProvider
    ISecretsProvider -->|Implemented by| AwsSecretsProvider
    
    Config -.->|Configure| Orchestrator
    Config -.->|Configure| AdapterFactory
    
    classDef host fill:#E3F2FD,stroke:#1976D2,stroke-width:2px
    classDef core fill:#C8E6C9,stroke:#388E3C,stroke-width:2px
    classDef adapters fill:#FFF9C4,stroke:#F57F17,stroke-width:2px
    classDef publishers fill:#FFCCBC,stroke:#E64A19,stroke-width:2px
    classDef models fill:#F3E5F5,stroke:#7B1FA2,stroke-width:2px
    classDef secrets fill:#FFE0B2,stroke:#F57C00,stroke-width:2px
    classDef auth fill:#B2DFDB,stroke:#00796B,stroke-width:2px
    
    class HostLayer,Program,Worker host
    class CoreLayer,Orchestrator,AdapterFactory,Normalizer core
    class AdaptersLayer,IAdapter,AzureAdapter,AwsAdapter adapters
    class PublishersLayer,IPublisher,HttpPublisher publishers
    class ModelsLayer,Config,UnifiedMetric,Enums models
    class SecretsLayer,ISecretsProvider,AzureSecretsProvider,AwsSecretsProvider secrets
    class AuthLayer,IAuthProvider,EntraIdAuthProvider auth
```

### Structure Packages Collecteur

```
DataMonitoring.Collector/
│
├── Program.cs                               # Entry point + DI
├── CollectorWorker.cs                       # IHostedService
│
├── Core/                                    # Logique orchestration
│   ├── CollectionOrchestrator.cs
│   ├── CloudAdapterFactory.cs
│   └── MetricsNormalizer.cs
│
├── Interfaces/                              # Contrats
│   ├── ICloudProviderAdapter.cs
│   ├── IEventPublisher.cs
│   ├── ISecretsProvider.cs
│   ├── IAuthProvider.cs
│   └── IMetricsNormalizer.cs
│
├── Adapters/                                # Implémentations cloud
│   ├── AzureMetricsAdapter.cs              # Azure SDK
│   └── AwsMetricsAdapter.cs                # AWS SDK
│
├── Publishers/                              # Publication événements
│   ├── HttpEventPublisher.cs               # HTTP + Polly retry
│   └── RetryPolicies.cs
│
├── Authentication/                          # Auth EntraID
│   ├── EntraIdAuthProvider.cs              # Azure.Identity
│   └── TokenCache.cs
│
├── Secrets/                                 # Gestion secrets
│   ├── AzureSecretsProvider.cs             # Key Vault
│   └── AwsSecretsProvider.cs               # Secrets Manager
│
├── Models/                                  # Modèles de données
│   ├── UnifiedMetric.cs                    # Format canonique
│   ├── CollectionConfig.cs
│   ├── CloudProvider.cs                    # Enum
│   ├── ServiceType.cs                      # Enum
│   └── MetricStatus.cs                     # Enum
│
├── Configuration/                           # Configuration
│   ├── CollectorOptions.cs
│   ├── ApigeeOptions.cs
│   └── SchedulingOptions.cs
│
└── appsettings.json
```

---

## 🎯 Diagramme de Classes - Collecteur

### Classes Principales

```mermaid
classDiagram
    class ICloudProviderAdapter {
        <<interface>>
        +CloudProvider Provider
        +CollectMetricsAsync(config, cancellationToken) Task~List~UnifiedMetric~~
    }
    
    class AzureMetricsAdapter {
        -ILogger logger
        -ArmClient armClient
        +CloudProvider Provider
        +CollectMetricsAsync() Task~List~UnifiedMetric~~
        -CollectDataFactoryMetricsAsync() Task~List~UnifiedMetric~~
        -CollectDatabricksMetricsAsync() Task~List~UnifiedMetric~~
    }
    
    class AwsMetricsAdapter {
        -ILogger logger
        -IAmazonGlue glueClient
        -IAmazonCloudWatch cloudWatchClient
        +CloudProvider Provider
        +CollectMetricsAsync() Task~List~UnifiedMetric~~
        -CollectGlueMetricsAsync() Task~List~UnifiedMetric~~
        -CollectEMRMetricsAsync() Task~List~UnifiedMetric~~
    }
    
    class IEventPublisher {
        <<interface>>
        +PublishAsync(metrics, cancellationToken) Task
    }
    
    class HttpEventPublisher {
        -ILogger logger
        -HttpClient httpClient
        -IAuthProvider authProvider
        -ISecretsProvider secretsProvider
        -AsyncRetryPolicy retryPolicy
        +PublishAsync(metrics) Task
        -GetBearerTokenAsync() Task~string~
        -BuildRequestAsync(metrics, token) HttpRequestMessage
    }
    
    class IAuthProvider {
        <<interface>>
        +GetAccessTokenAsync(scope) Task~string~
    }
    
    class EntraIdAuthProvider {
        -ILogger logger
        -DefaultAzureCredential credential
        -TokenCache cache
        +GetAccessTokenAsync(scope) Task~string~
        -RequestTokenAsync(scope) Task~AccessToken~
    }
    
    class ISecretsProvider {
        <<interface>>
        +GetSecretAsync(secretName) Task~string~
    }
    
    class AzureSecretsProvider {
        -ILogger logger
        -SecretClient keyVaultClient
        +GetSecretAsync(secretName) Task~string~
    }
    
    class AwsSecretsProvider {
        -ILogger logger
        -IAmazonSecretsManager secretsManagerClient
        +GetSecretAsync(secretName) Task~string~
    }
    
    class CollectionOrchestrator {
        -ILogger logger
        -CloudAdapterFactory adapterFactory
        -IEventPublisher eventPublisher
        -IMetricsNormalizer normalizer
        +ExecuteCollectionAsync(config) Task
        -HandleCollectionErrorAsync(exception) Task
    }
    
    class CloudAdapterFactory {
        -IServiceProvider serviceProvider
        +CreateAdapter(provider) ICloudProviderAdapter
    }
    
    class UnifiedMetric {
        +string MetricId
        +DateTime Timestamp
        +CloudProvider Provider
        +string SubscriptionId
        +string SubscriptionName
        +string BusinessUnit
        +string Environment
        +ServiceType ServiceType
        +string ServiceName
        +string MetricName
        +double Value
        +string Unit
        +MetricStatus Status
        +Dictionary~string,string~ Tags
        +DateTime CollectedAt
    }
    
    ICloudProviderAdapter <|.. AzureMetricsAdapter : implements
    ICloudProviderAdapter <|.. AwsMetricsAdapter : implements
    
    IEventPublisher <|.. HttpEventPublisher : implements
    
    IAuthProvider <|.. EntraIdAuthProvider : implements
    
    ISecretsProvider <|.. AzureSecretsProvider : implements
    ISecretsProvider <|.. AwsSecretsProvider : implements
    
    HttpEventPublisher --> IAuthProvider : uses
    HttpEventPublisher --> ISecretsProvider : uses
    
    CollectionOrchestrator --> CloudAdapterFactory : uses
    CollectionOrchestrator --> IEventPublisher : uses
    
    CloudAdapterFactory --> ICloudProviderAdapter : creates
    
    AzureMetricsAdapter --> UnifiedMetric : produces
    AwsMetricsAdapter --> UnifiedMetric : produces
    HttpEventPublisher --> UnifiedMetric : publishes
```

---

## 🔄 Séquence d'Exécution Collecteur

```mermaid
sequenceDiagram
    participant W as CollectorWorker
    participant O as CollectionOrchestrator
    participant F as CloudAdapterFactory
    participant A as ICloudProviderAdapter
    participant N as MetricsNormalizer
    participant P as HttpEventPublisher
    participant Auth as EntraIdAuthProvider
    participant S as ISecretsProvider
    participant APIGEE as APIGEE Gateway
    
    Note over W: Timer déclenche toutes les 5 min
    
    W->>O: ExecuteCollectionAsync(config)
    
    O->>F: CreateAdapter(config.Provider)
    F->>A: new AzureMetricsAdapter() / AwsMetricsAdapter()
    F-->>O: adapter instance
    
    O->>A: CollectMetricsAsync(config)
    Note over A: Collecte auprès Azure/AWS APIs
    A-->>O: List<RawMetric>
    
    O->>N: NormalizeBatch(rawMetrics, provider)
    N->>N: Transform to UnifiedMetric
    N->>N: Add metadata (BU, env, subscription)
    N-->>O: List<UnifiedMetric>
    
    Note over O: Préparation publication
    
    O->>P: PublishAsync(metrics)
    
    P->>S: GetSecretAsync("apigee-endpoint")
    S-->>P: endpoint URL
    
    P->>Auth: GetAccessTokenAsync("api://dcm-ingestion/.default")
    Note over Auth: Cache check
    Auth->>Auth: Request new token if expired
    Auth-->>P: Bearer Token JWT
    
    P->>P: Build HTTP Request
    Note over P: POST with Bearer Token
    
    P->>APIGEE: POST /dcm/v1/metrics/ingest<br/>Authorization: Bearer {token}<br/>Body: JSON metrics
    
    alt Success
        APIGEE-->>P: 202 Accepted
        P-->>O: Success
        O-->>W: Collection completed
    else Retry on Error
        APIGEE-->>P: 5xx Server Error
        Note over P: Polly Retry Policy
        P->>APIGEE: Retry after backoff
    else Final Failure
        APIGEE-->>P: Error after 3 retries
        P-->>O: Throw Exception
        O->>O: Log error
        O-->>W: Collection failed (logged)
    end
```

---

## 📋 Interfaces Clés

### ICloudProviderAdapter

```csharp
public interface ICloudProviderAdapter
{
    /// <summary>
    /// Cloud provider supporté (Azure ou AWS)
    /// </summary>
    CloudProvider Provider { get; }
    
    /// <summary>
    /// Collecte les métriques du provider
    /// </summary>
    /// <param name="config">Configuration de collecte</param>
    /// <param name="cancellationToken">Token d'annulation</param>
    /// <returns>Liste de métriques au format unifié</returns>
    Task<List<UnifiedMetric>> CollectMetricsAsync(
        CollectionConfig config,
        CancellationToken cancellationToken = default);
}
```

### IEventPublisher

```csharp
public interface IEventPublisher
{
    /// <summary>
    /// Publie un batch de métriques vers APIGEE
    /// </summary>
    /// <param name="metrics">Métriques à publier</param>
    /// <param name="cancellationToken">Token d'annulation</param>
    Task PublishAsync(
        IEnumerable<UnifiedMetric> metrics,
        CancellationToken cancellationToken = default);
}
```

### IAuthProvider

```csharp
public interface IAuthProvider
{
    /// <summary>
    /// Obtient un token d'accès EntraID
    /// </summary>
    /// <param name="scope">Scope demandé (ex: api://dcm-ingestion/.default)</param>
    /// <returns>JWT Bearer token</returns>
    Task<string> GetAccessTokenAsync(string scope);
}
```

### ISecretsProvider

```csharp
public interface ISecretsProvider
{
    /// <summary>
    /// Récupère un secret depuis Key Vault ou Secrets Manager
    /// </summary>
    /// <param name="secretName">Nom du secret</param>
    /// <returns>Valeur du secret</returns>
    Task<string> GetSecretAsync(string secretName);
}
```

---

## 🎨 Patterns de Conception Utilisés

### 1. **Adapter Pattern**
- **Usage** : `ICloudProviderAdapter`, `AzureMetricsAdapter`, `AwsMetricsAdapter`
- **Objectif** : Abstraction des différences entre Azure et AWS
- **Bénéfice** : Ajout de nouveaux providers facile

### 2. **Factory Pattern**
- **Usage** : `CloudAdapterFactory`
- **Objectif** : Création dynamique d'adapters selon config
- **Bénéfice** : Découplage et testabilité

### 3. **Repository Pattern**
- **Usage** : `DataLakeRepository`, `DatabricksRepository`
- **Objectif** : Abstraction de l'accès aux données
- **Bénéfice** : Changement de storage transparent

### 4. **Strategy Pattern**
- **Usage** : `ISecretsProvider` (Azure vs AWS)
- **Objectif** : Sélection algorithme selon contexte
- **Bénéfice** : Flexibilité multi-cloud

### 5. **Dependency Injection**
- **Usage** : Partout via .NET DI Container
- **Objectif** : Inversion de contrôle
- **Bénéfice** : Testabilité et maintenabilité

---

## 🧪 Testabilité

### Tests Unitaires

```csharp
// Example: Test AzureMetricsAdapter
public class AzureMetricsAdapterTests
{
    [Fact]
    public async Task CollectMetricsAsync_WhenDataFactoryHasRuns_ReturnsMetrics()
    {
        // Arrange
        var mockArmClient = new Mock<ArmClient>();
        var adapter = new AzureMetricsAdapter(
            Mock.Of<ILogger<AzureMetricsAdapter>>(),
            mockArmClient.Object);
        
        var config = new CollectionConfig
        {
            CloudProvider = CloudProvider.Azure,
            Services = new List<ServiceTypeConfig>
            {
                new() { Type = ServiceType.ETL_Orchestration, Enabled = true }
            }
        };
        
        // Act
        var metrics = await adapter.CollectMetricsAsync(config);
        
        // Assert
        Assert.NotEmpty(metrics);
        Assert.All(metrics, m => Assert.Equal(CloudProvider.Azure, m.Provider));
    }
}
```

### Tests d'Intégration

```csharp
// Example: Test HttpEventPublisher avec APIGEE
public class HttpEventPublisherIntegrationTests : IClassFixture<WebApplicationFactory>
{
    [Fact]
    public async Task PublishAsync_WithValidToken_Returns202Accepted()
    {
        // Arrange
        var publisher = new HttpEventPublisher(
            logger, httpClient, authProvider, secretsProvider);
        
        var metrics = new List<UnifiedMetric>
        {
            new() { /* ... */ }
        };
        
        // Act
        await publisher.PublishAsync(metrics);
        
        // Assert - No exception thrown = success
    }
}
```

---

## 📦 Dépendances NuGet Principales

### Collecteur

```xml
<ItemGroup>
  <!-- Host & DI -->
  <PackageReference Include="Microsoft.Extensions.Hosting" Version="8.0.0" />
  
  <!-- Azure SDK -->
  <PackageReference Include="Azure.Identity" Version="1.10.4" />
  <PackageReference Include="Azure.ResourceManager" Version="1.9.0" />
  <PackageReference Include="Azure.ResourceManager.DataFactory" Version="1.0.0" />
  <PackageReference Include="Azure.Security.KeyVault.Secrets" Version="4.5.0" />
  
  <!-- AWS SDK -->
  <PackageReference Include="AWSSDK.Core" Version="3.7.300" />
  <PackageReference Include="AWSSDK.Glue" Version="3.7.300" />
  <PackageReference Include="AWSSDK.SecretsManager" Version="3.7.300" />
  
  <!-- Scheduling -->
  <PackageReference Include="Quartz" Version="3.8.0" />
  <PackageReference Include="Quartz.Extensions.Hosting" Version="3.8.0" />
  
  <!-- Resilience -->
  <PackageReference Include="Polly" Version="8.2.0" />
  
  <!-- Logging -->
  <PackageReference Include="Serilog.Extensions.Hosting" Version="8.0.0" />
  <PackageReference Include="Serilog.Sinks.ApplicationInsights" Version="4.0.0" />
</ItemGroup>
```

### Backend API

```xml
<ItemGroup>
  <!-- Web API -->
  <PackageReference Include="Microsoft.AspNetCore.OpenApi" Version="8.0.0" />
  <PackageReference Include="Swashbuckle.AspNetCore" Version="6.5.0" />
  
  <!-- Auth -->
  <PackageReference Include="Microsoft.Identity.Web" Version="2.15.0" />
  
  <!-- Data Access -->
  <PackageReference Include="Azure.Storage.Blobs" Version="12.19.0" />
  <PackageReference Include="Microsoft.Data.Analysis" Version="0.21.0" />
</ItemGroup>
```

### Frontend React

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "typescript": "^5.3.0",
    "@azure/msal-react": "^2.0.0",
    "@azure/msal-browser": "^3.0.0",
    "@tanstack/react-query": "^5.0.0",
    "axios": "^1.6.0",
    "recharts": "^2.10.0",
    "react-router-dom": "^6.20.0"
  }
}
```

---

## 🎯 Points Clés Architecture Logique

### Principes Appliqués

1. **Separation of Concerns** : Couches distinctes (Presentation, Application, Data, Collection)
2. **Dependency Inversion** : Dépendances vers abstractions (interfaces)
3. **Single Responsibility** : Chaque classe a une responsabilité unique
4. **Open/Closed** : Extensions faciles (nouveaux adapters) sans modification code existant
5. **Interface Segregation** : Interfaces spécifiques et ciblées

### Extensibilité

**Ajout d'un nouveau Cloud Provider** (si besoin futur) :
1. Créer `NewCloudAdapter : ICloudProviderAdapter`
2. Implémenter `CollectMetricsAsync()`
3. Enregistrer dans `CloudAdapterFactory`
4. Ajouter enum value dans `CloudProvider`

**Ajout d'un nouveau type de service** :
1. Ajouter enum value dans `ServiceType`
2. Implémenter collecte dans adapter existant
3. Aucun changement dans orchestration

---

**Document d'Architecture Logique**  
**Version** : 3.0  
**Date** : 14 Janvier 2026  
**Statut** : **ARCHITECTURE VALIDÉE**


