# Migration DCM : Lakebase/PostgreSQL -> Databricks SQL Warehouse

**Date de mise a jour :** 2026-05-27  
**Statut :** implemente dans le backend et le frontend DCM  
**Scope :** backend FastAPI, frontend React, tables Unity Catalog, administration DCM

## Resume

La couche Lakebase/PostgreSQL n'est plus la cible de lecture du backend DCM. Le backend se connecte maintenant directement a Databricks SQL Warehouse et lit les tables Unity Catalog du schema configure.

Avant :

```text
Backend FastAPI
  -> asyncpg / PostgreSQL wire protocol
  -> Lakebase PostgreSQL
  -> tables repliquees depuis Databricks
```

Maintenant :

```text
Backend FastAPI
  -> databricks-sql-connector
  -> Databricks SQL Warehouse
  -> Unity Catalog : <catalog>.<schema>.<table>
```

Objectifs atteints :

- Suppression de `asyncpg` et de la configuration `DCM_LAKEBASE_*` pour la lecture applicative.
- Ajout d'une connexion unique `DatabricksWarehousePool` partagee par FastAPI.
- Lecture directe des tables `curated_*`, `gold_*` et `dcm_*` dans Unity Catalog.
- Passage des requetes au dialecte Databricks SQL : placeholders `?`, `CAST(...)`, fonctions compatibles Warehouse.
- Ajout du controle d'acces DCM : roles applicatifs, scope Landing Zone, interface `/admin`, audit.

## Ce qui a change dans le code

### Backend

La connexion base de donnees est portee par `packages/dcm-backend/app/db/connection.py`.

- `DatabricksWarehousePool` ouvre une connexion SQL Warehouse au demarrage FastAPI.
- Le connecteur Databricks etant synchrone, les appels bloquants tournent via `asyncio.to_thread`.
- L'authentification utilise le SPN OAuth M2M quand `DCM_DATABRICKS_SPN_CLIENT_ID` et `DCM_DATABRICKS_SPN_CLIENT_SECRET` sont presents.
- Un PAT `DCM_DATABRICKS_TOKEN` reste possible uniquement pour le developpement local.
- Si la connexion Warehouse echoue au demarrage, l'API reste disponible, mais les routes data retournent `503` avec `database=unreachable`.

Configuration active :

```env
DCM_DATABRICKS_HOST=dbc-89e8d3b6-20ad.cloud.databricks.com
DCM_DATABRICKS_WAREHOUSE_ID=cf12d9eaa80a7ec5
DCM_DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/<warehouse-id> # optionnel
DCM_DATABRICKS_CATALOG=it
DCM_DATABRICKS_SCHEMA=ba_data_connect_monitoring__a
DCM_DATABRICKS_SPN_CLIENT_ID=<spn-client-id>
DCM_DATABRICKS_SPN_CLIENT_SECRET=<spn-client-secret>
DCM_DATABRICKS_SPN_CLIENT_SECRET_ARN=<secret-manager-arn>
```

Les variables Lakebase ne doivent plus etre utilisees pour le backend :

```text
DCM_LAKEBASE_HOST
DCM_LAKEBASE_USER
DCM_LAKEBASE_DB
DCM_LAKEBASE_PORT
DCM_LAKEBASE_MIN_POOL
DCM_LAKEBASE_MAX_POOL
DCM_LAKEBASE_PASSWORD_ARN
```

### Acces aux tables

Les routes historiques lisent les tables metriques directement dans Unity Catalog :

| Domaine | Table lue par le backend |
| --- | --- |
| Dashboard / pipelines | `curated_pipeline_metrics` |
| Activities | `curated_activity_runs` |
| Clusters / compute | `curated_compute_metrics` |
| Costs | `curated_cost_metrics` |
| Databases | `curated_database_metrics` |
| Security | `curated_security_alerts` |
| Users | `curated_user_metrics` |
| Standard Checks | `curated_standard_checks` |
| Standard Check score | `gold_standard_check_score` |
| Data Product Usage | `gold_data_product_usage` |

Les tables sont adressees sous la forme :

```text
`<DCM_DATABRICKS_CATALOG>`.`<DCM_DATABRICKS_SCHEMA>`.`<table>`
```

Le helper `qualified_table()` protege les identifiants Unity Catalog avec des backticks pour les tables dynamiques, notamment les tables admin.

### Module Administration

Le module admin a ete ajoute pour gerer DCM sans Lakebase :

- `dcm_app_users` : utilisateurs DCM, role applicatif, etat actif.
- `dcm_user_lz_access` : mapping utilisateur -> Landing Zones autorisees.
- `dcm_landing_zones` : registre admin des LZ, fallback quand `dim_landing_zone` n'est pas disponible.
- `dcm_notification_channels` : canaux email/Teams/webhook.
- `dcm_alert_rules` et `dcm_alert_firings` : regles d'alerting et historique des declenchements.
- `dcm_collector_status` : fraicheur et statut des collecteurs.
- `dcm_kpi_config` : seuils KPI administrables.
- `dcm_retention_policies` : politiques de retention.
- `dcm_maintenance_windows` : fenetres de maintenance.
- `dcm_audit_log` : audit des actions admin.

Ces tables sont creees dans Unity Catalog par `our_catalogs_spn.py` via le SQL Warehouse, pas via une migration PostgreSQL.

### Authentification et autorisation

Entra ID authentifie l'utilisateur, puis DCM autorise via Unity Catalog :

```text
Bearer token Entra
  -> backend decode oid/sub + email
  -> lookup dcm_app_users
  -> role DCM
  -> dcm_user_lz_access pour les roles non admin
  -> filtre SQL source_lz_id IN (...)
```

Roles actuels :

| Role | Acces donnees | Acces admin UI |
| --- | --- | --- |
| `viewer` | Landing Zones assignees | Non |
| `data_architect` | Landing Zones assignees | Non |
| `manager` | Landing Zones assignees | Non |
| `admin` | Toutes les Landing Zones | Non |
| `super_admin` | Toutes les Landing Zones | Oui |

Le filtre Landing Zone est applique cote backend avec `add_lz_filter()`. Les admins et super admins recoivent `allowed_lz_ids = None`, ce qui signifie acces donnees complet.

### Frontend

Le frontend a ete aligne sur ce modele :

- Ajout de la page `/admin`, protegee par `RequireAdmin`.
- Seul `super_admin` peut ouvrir l'interface Administration.
- Ajout d'appels API admin dans `dcmApiClient.ts`.
- Ajout du chargement de l'utilisateur courant via `GET /api/v1/me`.
- Les pages data affichent un message explicite quand l'API est disponible mais que la connexion Warehouse n'est pas initialisee.
- Le selecteur Landing Zone consomme `GET /api/v1/landing-zones/details`, avec fallback backend vers `dcm_landing_zones`.

## Datamodel actif

Le datamodel actif n'utilise plus une couche SERVING PostgreSQL separee pour le backend. Les tables consommees par l'API sont des tables Unity Catalog interrogees via SQL Warehouse.

```text
Agents Azure/AWS
  -> ingestion centrale
  -> raw_metrics
  -> curated_* par domaine
  -> gold_* pour les aggregats metier
  -> backend FastAPI via Databricks SQL Warehouse
  -> frontend React
```

Le terme "SERVING" reste utile fonctionnellement, mais il designe maintenant les tables Unity Catalog pretes pour l'API, pas une base Lakebase/PostgreSQL.

### Couches conservees

| Couche | Role | Exemples |
| --- | --- | --- |
| RAW | Archive opaque des payloads collectes | `raw_metrics` |
| CURATED | Donnees normalisees par domaine, lues par l'API | `curated_pipeline_metrics`, `curated_cost_metrics` |
| GOLD | Aggregats metier et vues optimisees | `gold_standard_check_score`, `gold_data_product_usage` |
| ADMIN | Configuration applicative DCM | `dcm_app_users`, `dcm_alert_rules`, `dcm_kpi_config` |

### Impacts SQL

Les requetes backend doivent respecter le dialecte Databricks SQL :

| Ancien pattern PostgreSQL | Nouveau pattern Databricks SQL |
| --- | --- |
| `$1`, `$2` | `?` |
| `timestamp::date` | `CAST(timestamp AS DATE)` |
| `NOW()` | `current_timestamp()` |
| Tables non qualifiees | Tables qualifiees Unity Catalog |
| Contraintes PostgreSQL comme source de verite | Validation applicative et tables Delta |

Exemple :

```sql
SELECT run_id, pipeline_name, status, start_time
FROM it.ba_data_connect_monitoring__a.curated_pipeline_metrics
WHERE cloud_provider = ?
  AND source_lz_id IN (?, ?)
ORDER BY start_time DESC
LIMIT ? OFFSET ?
```

## Validation

Tests ajoutes ou adaptes :

- Backend : fixtures mockees sur `DatabricksWarehousePool`, pas de connexion Databricks reelle en test unitaire.
- Tests admin : utilisateurs, auth, operations admin, alerting.
- Tests LZ filtering : validation des scopes Landing Zone.
- Frontend : client API, admin guard, header/navigation, dashboard et pages dependantes.

Smoke test manuel :

```bash
python our_catalogs_spn.py
```

Ce script verifie l'acces SPN au SQL Warehouse, cree les tables admin Unity Catalog si besoin, seed les seuils KPI/retention et bootstrap les premiers admins.

## Points de vigilance

- Ne pas recreer de migration Lakebase/PostgreSQL pour les nouvelles fonctionnalites DCM.
- Ne pas reintroduire `asyncpg` dans le backend applicatif.
- Toute nouvelle table consommee par l'API doit etre dans Unity Catalog et accessible via le Warehouse configure.
- Les requetes multi-LZ doivent appeler `add_lz_filter()` ou appliquer une restriction equivalente cote backend.
- Les tables admin Delta ne remplacent pas les checks metier applicatifs : unicite, roles et transitions doivent rester controles par l'API.
