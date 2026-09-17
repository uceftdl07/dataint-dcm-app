# Network Flow Matrix - Azure Data Monitoring Platform

## Flow Analysis Based on Architecture Diagram

Cette matrice décrit tous les flux réseau identifiés dans le schéma d'architecture technique de la plateforme de monitoring Azure.

| Numéro de flux | Description | Source of the Flow | Source Zone | Destination of the Flow | Destination Zone | Network Protocol | Network Port | Encryption | Authentication | Comment |
|----------------|-------------|-------------------|-------------|------------------------|-----------------|-----------------|--------------|------------|---------------|---------|
| 1 | User accesses frontend application | End User Browser | Main | Static Web App | Azure I@S | HTTPS | 443 | TLS 1.3 | None (anonymous access) | Public frontend access through CDN |
| 2 | User authentication request | Static Web App | Azure I@S | Azure AD (Entra ID) | Azure I@S | HTTPS | 443 | TLS 1.3 | OAuth2/OIDC | Authentication flow initiation |
| 3 | Frontend API calls with user token | Static Web App | Azure I@S | Application Gateway | Azure I@S | HTTPS | 443 | TLS 1.3 | JWT Bearer Token | User-authenticated API requests |
| 4 | WAF filtered requests to backend | Application Gateway | Azure I@S | Backend Container (CT_1) | Azure I@S Private | HTTPS | 443 | TLS 1.3 | JWT Bearer Token | Requests filtered by WAF rules |
| 5 | Backend database queries | Backend Container | Azure I@S Private | PostgreSQL Database | Azure I@S Private | TCP | 5432 | TLS 1.2 | Database Authentication | EF Core database operations |
| 6 | Backend fetches secrets | Backend Container | Azure I@S Private | Key Vault (SV_1) | Azure I@S Private | HTTPS | 443 | TLS 1.3 | Managed Identity | Connection strings and API keys |
| 7 | Backend application logging | Backend Container | Azure I@S Private | Log Analytics | Azure I@S | HTTPS | 443 | TLS 1.3 | Managed Identity | Application logs and telemetry |
| 8 | Collector stores metrics | WebJob Collector | Azure I@S Private | PostgreSQL Database | Azure I@S Private | TCP | 5432 | TLS 1.2 | Database Authentication | Direct database storage via EF Core |
| 9 | Collector fetches configuration | WebJob Collector | Azure I@S Private | Key Vault (SV_1) | Azure I@S Private | HTTPS | 443 | TLS 1.3 | Managed Identity | Connection strings retrieval |
| 10 | Collector to Data Factory API | WebJob Collector | Azure I@S Private | Data Factory API | Azure I@S | HTTPS | 443 | TLS 1.3 | Azure AD Token | Pipeline metrics collection |
| 11 | Collector to Databricks API | WebJob Collector | Azure I@S Private | Databricks API | Azure I@S | HTTPS | 443 | TLS 1.3 | Azure AD Token | Cluster and job metrics |
| 12 | Collector to Azure Monitor API | WebJob Collector | Azure I@S Private | Azure Monitor API | Azure I@S | HTTPS | 443 | TLS 1.3 | Azure AD Token | Performance metrics retrieval |
| 13 | Collector to Cost Management API | WebJob Collector | Azure I@S Private | Cost Management API | Azure I@S | HTTPS | 443 | TLS 1.3 | Azure AD Token | Cost and billing data |
| 14 | Collector to Security Center API | WebJob Collector | Azure I@S Private | Security Center API | Azure I@S | HTTPS | 443 | TLS 1.3 | Azure AD Token | Security alerts and assessments |
| 15 | Backend authentication requests | Backend Container | Azure I@S Private | Azure AD (Entra ID) | Azure I@S | HTTPS | 443 | TLS 1.3 | Client Credentials | Service-to-service authentication |
| 16 | Collector authentication requests | WebJob Collector | Azure I@S Private | Azure AD (Entra ID) | Azure I@S | HTTPS | 443 | TLS 1.3 | Managed Identity | Service authentication for Azure APIs |
| 17 | Container image pulls | Backend Container | Azure I@S Private | Container Registry | Azure I@S | HTTPS | 443 | TLS 1.3 | Managed Identity | Docker image deployment |
| 18 | WAF audit logging | Application Gateway | Azure I@S | Log Analytics | Azure I@S | HTTPS | 443 | TLS 1.3 | Managed Identity | Security event logging |
| 19 | Database audit logging | PostgreSQL Database | Azure I@S Private | Log Analytics | Azure I@S | HTTPS | 443 | TLS 1.3 | Managed Identity | Database operations logging |
| 20 | Collector execution logging | WebJob Collector | Azure I@S Private | Log Analytics | Azure I@S | HTTPS | 443 | TLS 1.3 | Managed Identity | Job execution and error logs |

## Zones Definition

### Network Zones
- **Main** : Réseau d'entreprise TotalEnergies (réseau interne)
- **Internet** : Zone Internet publique 
- **Azure I@S** : Zone Azure INOX@Scale (zone cloud Azure)
- **Azure I@S Private** : Sous-réseau privé Azure INOX@Scale (zone privée protégée)

### Authentication Types Used
- **OAuth2/OIDC** : Authentification utilisateur Azure AD
- **JWT Bearer Token** : Token utilisateur pour accès API
- **Managed Identity** : Identité managée Azure pour services
- **Client Credentials** : Authentification service-to-service Azure AD
- **Database Authentication** : Authentification base de données PostgreSQL

### Encryption Standards
- **TLS 1.3** : Standard de chiffrement pour HTTPS
- **TLS 1.2** : Chiffrement base de données PostgreSQL

## Security Considerations

### Private Zone Protection
- Flux 5, 6, 8, 9 : Communications internes au sous-réseau privé
- Aucun accès direct depuis Internet
- Chiffrement obligatoire pour toutes les communications

### Authentication Strategy
- Flux 1 : Accès anonyme frontend uniquement
- Flux 2-4 : Authentification utilisateur obligatoire
- Flux 10-16 : Authentification service Azure AD uniquement
- Flux 17-20 : Managed Identity pour services infrastructure

### Monitoring and Logging
- Flux 7, 18, 19, 20 : Centralisation des logs dans Log Analytics
- Audit complet de tous les accès et opérations
- Traçabilité end-to-end des flux de données