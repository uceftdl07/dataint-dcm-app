# 🔄 Analyse des Alternatives d'Ingestion Multi-Cloud

**Date** : 14 Janvier 2026  
**Contexte** : EventHub doit être en subnet privé (contrainte entreprise)  
**Problème** : Collecteurs AWS ne peuvent pas accéder à EventHub privé  

---

## 🎯 Critères de Sélection

### Requis Fonctionnels
- ✅ Accessible depuis AWS (via internet public sécurisé)
- ✅ Accessible depuis Azure (via Private Endpoint)
- ✅ Support multi-instances : 10-50+ collecteurs
- ✅ Buffering et résilience (retry automatique)
- ✅ Scalabilité pour croissance 100x
- ✅ Monitoring et observabilité

### Contraintes Entreprise
- ✅ Backend doit être en subnet privé
- ✅ Authentification forte (OAuth, API Keys)
- ✅ Logs d'audit complets
- ✅ Coût maîtrisé (< 200€/mois pour ingestion)

---

## 📊 Option 1 : Azure API Management + Service Bus Premium ⭐ RECOMMANDÉ

### Architecture

```
Collecteurs AWS (10+)
     |
     | HTTPS Public (OAuth/API Key)
     ↓
Azure API Management (Public endpoint)
     |
     | Private Link
     ↓
Service Bus Premium (Private)
     |
     | Private Link
     ↓
Azure Function (Consumer)
     ↓
Data Lake Bronze
```

### Avantages
- ✅ **Endpoint public sécurisé** : API Management expose API publique
- ✅ **Backend privé** : Service Bus Premium avec Private Link
- ✅ **Multi-cloud natif** : Les deux providers utilisent la même API
- ✅ **Buffering robuste** : Service Bus = messaging fiable (FIFO, Dead Letter, Retry)
- ✅ **Rate limiting** : API Management gère le throttling par collecteur
- ✅ **Monitoring** : API Management + App Insights
- ✅ **Authentification flexible** : OAuth 2.0, API Keys, Certificates
- ✅ **Scalabilité** : Service Bus Premium (80 millions msg/jour)

### Inconvénients
- ⚠️ **Coût plus élevé** : ~150€/mois
- ⚠️ **Complexité** : 2 services à gérer (APIM + Service Bus)

### Configuration Détaillée

#### Service Bus Premium

```yaml
Name: sb-monitoring-premium
Tier: Premium
Messaging Units: 1 (scalable jusqu'à 8)
Features:
  - Private Link: Enabled
  - Queue: metrics-ingestion
  - Max Message Size: 1 MB
  - Max Queue Size: 80 GB
  - TTL: 7 jours

Coût: ~70€/mois (1 MU)
```

#### API Management

```yaml
Name: apim-monitoring
Tier: Developer (ou Basic pour prod)
Region: West Europe

APIs:
  - /api/v1/metrics/ingest (POST)
    - Authentication: Subscription Key + OAuth 2.0
    - Rate Limit: 1000 requests/minute par collecteur
    - Backend: Service Bus Queue
    
Policies:
  - rate-limit: 1000/minute
  - validate-jwt: Azure AD token
  - set-backend-service: Service Bus
  - retry: 3 attempts exponential backoff

Coût: 
  - Developer: ~40€/mois (non-prod)
  - Basic: ~140€/mois (prod, SLA 99.95%)
```

#### Azure Function (Consumer)

```yaml
Name: func-metrics-consumer
Plan: Premium EP1
Trigger: Service Bus Queue
Processing:
  - Batch: 100 messages
  - Write: Data Lake Bronze
  - Format: JSON gzip
  
Coût: ~70€/mois
```

### Coût Total

| Composant | Coût/Mois |
|-----------|-----------|
| Service Bus Premium (1 MU) | 70€ |
| API Management Basic | 140€ |
| Azure Function Premium EP1 | 70€ |
| Data Lake Storage | 120€ |
| **TOTAL** | **400€/mois** |

⚠️ **Plus cher qu'EventHub** mais répond aux contraintes entreprise.

### Optimisation Coût

**Option Optimisée** : APIM Developer + Service Bus Standard

| Composant | Coût/Mois |
|-----------|-----------|
| Service Bus Standard | 10€ |
| API Management Developer | 40€ |
| Azure Function Consumption | 5€ |
| Data Lake Storage | 120€ |
| **TOTAL** | **175€/mois** |

⚠️ Service Bus Standard n'a pas Private Link → Ne respecte pas contrainte subnet privé.

---

## 📊 Option 2 : Azure Function HTTP + Queue Storage

### Architecture

```
Collecteurs (AWS + Azure)
     |
     | HTTPS Public (Function Key)
     ↓
Azure Function HTTP Trigger (Public)
     |
     | Private Link
     ↓
Queue Storage (Private)
     |
     ↓
Azure Function Queue Trigger
     ↓
Data Lake Bronze
```

### Avantages
- ✅ **Très économique** : ~15-20€/mois
- ✅ **Simple** : Un seul service (Azure Functions)
- ✅ **Endpoint public** : Function HTTP accessible depuis AWS
- ✅ **Backend privé** : Queue Storage avec Private Endpoint
- ✅ **Scalable** : Functions scale automatiquement

### Inconvénients
- ❌ **Pas de FIFO garanti** : Queue Storage n'a pas d'ordre strict
- ❌ **Latence plus élevée** : Polling (30-60 secondes)
- ❌ **Limite message** : 64 KB (vs 1 MB EventHub/Service Bus)
- ❌ **Pas de buffering avancé** : Pas de Dead Letter sophistiqué
- ❌ **Rate limiting manuel** : À implémenter dans la Function

### Configuration

```yaml
Function App:
  Name: func-metrics-ingestion
  Plan: Consumption
  Functions:
    - IngestMetrics (HTTP Trigger)
      - Auth: Function Key
      - Write to: Queue Storage
    - ProcessMetrics (Queue Trigger)
      - Read from: Queue Storage
      - Write to: Data Lake

Queue Storage:
  Account: stmonitoring
  Queue: metrics-ingestion
  Private Endpoint: Enabled
  Max Message Size: 64 KB
  TTL: 7 jours

Coût: ~15€/mois
```

### Code Function HTTP

```csharp
[FunctionName("IngestMetrics")]
public async Task<IActionResult> IngestMetrics(
    [HttpTrigger(AuthorizationLevel.Function, "post")] HttpRequest req,
    [Queue("metrics-ingestion")] IAsyncCollector<string> queue,
    ILogger log)
{
    // Rate limiting basique
    var clientId = req.Headers["X-Client-Id"];
    if (!await _rateLimiter.AllowAsync(clientId))
    {
        return new StatusCodeResult(429); // Too Many Requests
    }
    
    // Lire et valider payload
    var body = await req.ReadAsStringAsync();
    
    // Vérifier taille (< 64 KB)
    if (Encoding.UTF8.GetByteCount(body) > 64000)
    {
        return new BadRequestObjectResult("Message too large");
    }
    
    // Enqueue
    await queue.AddAsync(body);
    
    return new OkResult();
}
```

---

## 📊 Option 3 : Azure Container Apps avec Dapr Pub/Sub

### Architecture

```
Collecteurs (AWS + Azure)
     |
     | HTTPS Public (Dapr API)
     ↓
Container App (Ingestion API)
     |
     | Dapr Pub/Sub
     ↓
Service Bus / Storage Queue (Private)
     |
     ↓
Container App (Consumer)
     ↓
Data Lake Bronze
```

### Avantages
- ✅ **Architecture moderne** : Dapr = patterns cloud-native
- ✅ **Abstraction** : Dapr abstrait le messaging backend
- ✅ **Flexible** : Changement de backend sans modifier code
- ✅ **Scaling** : Container Apps scale to zero
- ✅ **Observabilité** : Dapr telemetry intégré

### Inconvénients
- ⚠️ **Complexité** : Courbe d'apprentissage Dapr
- ⚠️ **Coût** : ~100€/mois (Container Apps Environment)
- ⚠️ **Moins mature** : Dapr relativement récent

---

## 📊 Option 4 : API Management + Data Lake Direct

### Architecture

```
Collecteurs (AWS + Azure)
     |
     | HTTPS Public (API Key)
     ↓
Azure API Management
     |
     | Backend: Azure Function
     ↓
Data Lake Bronze (Direct write)
```

### Avantages
- ✅ **Simple** : Pas de messaging intermédiaire
- ✅ **Latence minimale** : Écriture directe
- ✅ **Endpoint public** : API Management

### Inconvénients
- ❌ **Pas de buffering** : Si Data Lake down, perte de données
- ❌ **Pas de retry natif** : À implémenter côté collecteur
- ❌ **Couplage fort** : Collecteurs dépendent de Data Lake
- ❌ **Scalabilité limitée** : Data Lake peut devenir bottleneck

---

## 📊 Tableau Comparatif

| Critère | APIM + Service Bus ⭐ | Function + Queue | Container Apps + Dapr | APIM + Data Lake Direct |
|---------|---------------------|------------------|---------------------|------------------------|
| **Coût/mois** | 400€ (optimisé 175€) | 15€ | 100€ | 210€ |
| **Endpoint Public** | ✅ APIM | ✅ Function | ✅ Container App | ✅ APIM |
| **Backend Privé** | ✅ Private Link | ✅ Private Endpoint | ✅ Private Endpoint | ✅ Private Endpoint |
| **Buffering** | ✅✅ Excellent | ⚠️ Basique | ✅ Bon | ❌ Aucun |
| **FIFO** | ✅ Oui | ❌ Non | ✅ Oui (si Service Bus) | N/A |
| **Retry** | ✅ Natif | ⚠️ Manuel | ✅ Dapr retry | ❌ Côté client |
| **Rate Limiting** | ✅✅ APIM | ⚠️ Manuel | ⚠️ Manuel | ✅✅ APIM |
| **Scalabilité** | ✅✅ Excellent | ✅ Bon | ✅✅ Excellent | ⚠️ Limité |
| **Complexité** | ⚠️ Moyenne | ✅ Faible | ⚠️⚠️ Élevée | ✅ Faible |
| **Monitoring** | ✅✅ Excellent | ✅ Bon | ✅✅ Excellent | ✅ Bon |
| **SLA** | ✅ 99.95% | ⚠️ 99.5% | ✅ 99.95% | ⚠️ 99.5% |

---

## 🎯 Recommandation Finale

### Pour votre contexte (10-50+ collecteurs, dashboard entreprise)

**Option Recommandée : Azure API Management + Service Bus Premium**

**Justification :**

1. **Contrainte Subnet Privé** : ✅ Respectée
   - API Management = endpoint public sécurisé
   - Service Bus Premium = Private Link natif
   
2. **Multi-instances** : ✅ Idéal
   - API Management gère facilement 50+ collecteurs
   - Rate limiting par subscription key (un par collecteur)
   - Monitoring détaillé par collecteur
   
3. **Résilience Entreprise** : ✅ Production-ready
   - Service Bus = messaging robuste (Dead Letter, Retry)
   - SLA 99.95%
   - Buffering 7 jours
   
4. **Sécurité** : ✅ Conforme
   - OAuth 2.0 + API Keys
   - Logs d'audit complets
   - Intégration Azure AD
   
5. **Coût** : ⚠️ Plus élevé mais justifié
   - 400€/mois pour architecture complète
   - Économies potentielles avec Developer tier (175€/mois en dev)

### Alternative Économique

**Si budget contraint : Azure Function HTTP + Service Bus Standard**

| Composant | Coût/Mois |
|-----------|-----------|
| Service Bus Standard | 10€ |
| Azure Function Consumption | 5€ |
| Data Lake Storage | 120€ |
| **TOTAL** | **135€/mois** |

⚠️ **Compromis** : Service Bus Standard n'a pas Private Link
- Solution : Firewall Service Bus avec IP whitelisting
- Acceptable si collecteurs Azure passent par NAT Gateway (IP fixe)

---

## 📋 Plan de Migration EventHub → Solution Choisie

### Phase 1 : POC (Semaine 1-2)

1. **Déployer Service Bus Premium**
2. **Configurer API Management (Developer tier)**
3. **Créer Azure Function consumer**
4. **Tester avec 1 collecteur Azure**
5. **Tester avec 1 collecteur AWS**

### Phase 2 : Validation (Semaine 3-4)

1. **Tests de charge** : 10 collecteurs simultanés
2. **Validation buffering** : Simuler Data Lake down
3. **Validation retry** : Tester Dead Letter Queue
4. **Monitoring** : Configurer alertes

### Phase 3 : Migration (Semaine 5-6)

1. **Migrer tous les collecteurs**
2. **Désactiver EventHub**
3. **Formation équipes**

---

## 💰 Estimation Coûts Multi-Instances

### Scénario : 30 collecteurs (20 Azure + 10 AWS)

**Architecture : APIM + Service Bus Premium**

| Composant | Configuration | Coût/Mois |
|-----------|---------------|-----------|
| Service Bus Premium | 2 MU (pour 30 collecteurs) | 140€ |
| API Management Basic | SLA 99.95% | 140€ |
| Azure Function Premium | EP2 (processing) | 140€ |
| Data Lake Storage | 5 TB (30 collecteurs) | 300€ |
| Application Insights | 100 GB logs | 80€ |
| **TOTAL** | | **800€/mois** |

**Coût par collecteur** : 800€ / 30 = **27€/mois/collecteur**

**Acceptable pour solution entreprise** ✅

---

## 🔧 Configuration Exemple API Management

```yaml
API: /api/v1/metrics/ingest

Method: POST
Authentication: 
  - Primary: Subscription Key (un par collecteur)
  - Secondary: OAuth 2.0 (Azure AD)
  
Rate Limiting:
  - Global: 10,000 requests/minute
  - Per Subscription: 500 requests/minute
  
Policies:
  - validate-jwt (Azure AD)
  - rate-limit-by-key
  - set-backend-service (Service Bus)
  - log-to-eventhub (audit)
  
Backend:
  - Service Bus Queue: metrics-ingestion
  - Write via Azure SDK

Response:
  - 202 Accepted (async processing)
  - 429 Too Many Requests (rate limit)
  - 401 Unauthorized
```

---

**Document de Travail** - Version 1.0  
**Date** : 14 Janvier 2026

