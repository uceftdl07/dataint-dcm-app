# Feature Specification: Migration Lakebase → Databricks SQL Warehouse

**Feature Branch**: `001-migration-lakebase-to-warehouse`  
**Created**: 2026-05-19  
**Status**: Draft  
**Input**: `docs/migration/ANALYSE-ARCHITECTURE.md`, `docs/MIGRATION-LAKEBASE-TO-WAREHOUSE.md`, validation script `our_catalogs_spn.py`

---

## Compréhension du besoin

### Objectif métier

Supprimer la **couche intermédiaire Lakebase PostgreSQL** (réplique des tables Gold) et faire lire le **backend FastAPI** (`packages/dcm-backend`) **directement** les données SERVING dans **Unity Catalog** via le **SQL Warehouse Databricks**, avec la même surface API pour le frontend.

### Cible technique validée

| Élément | Valeur |
|--------|--------|
| Workspace | `dbc-89e8d3b6-20ad.cloud.databricks.com` |
| Warehouse ID | `cf12d9eaa80a7ec5` |
| Catalog Unity | `it` |
| Schema | `ba_data_connect_monitoring__d` |
| Auth backend | SPN OAuth M2M (`oauth_service_principal`) — même principe que `our_catalogs_spn.py` |
| Tables | 10 tables SERVING définies dans `packages/dcm-databricks-pipeline/schemas/lakebase_ddl.sql` |

### Script de pré-validation (`our_catalogs_spn.py`)

Le script prouve que le SPN peut :

1. Se connecter au SQL Warehouse avec `credentials_provider` + `catalog` / `schema` par défaut.
2. Résoudre le catalog `it` (`SHOW CATALOGS`).
3. Lister les schemas monitoring (`SHOW SCHEMAS IN it`).
4. Lister les tables (`SHOW TABLES IN it.ba_data_connect_monitoring__d`).
5. Exécuter un `SELECT * … LIMIT 5` sur une table (lecture réelle).

**Ce script est le gate Phase 0** : tant qu’il ne passe pas en environnement cible (ppd/prd), la migration backend ne doit pas être déployée.

> **Sécurité** : ne pas committer le secret SPN dans le dépôt. Utiliser `DATABRICKS_SP_CLIENT_SECRET` (Key Vault / Secrets Manager) comme en production.

---

## Architecture cible

```
Unity Catalog (Databricks)
  it.ba_data_connect_monitoring__d
    ├── pipeline_metrics
    ├── compute_metrics
    ├── cost_metrics
    ├── database_metrics
    ├── security_alerts
    ├── collection_runs
    ├── activity_runs
    ├── user_metrics
    ├── standard_checks
    └── dim_landing_zone
              │
              │  databricks-sql-connector (sync)
              │  + asyncio.to_thread (wrapper async)
              │  + OAuth SPN (credentials_provider)
              ▼
FastAPI Backend (packages/dcm-backend)
  ├── app/db/connection.py  → DatabricksWarehousePool
  ├── app/config.py         → warehouse_* settings
  └── app/api/routes/*      → SQL avec placeholders `?`
```

**Hors périmètre de cette spec** (à traiter séparément si besoin) :

- Modification des jobs PySpark pipeline (écriture Gold reste côté Databricks).
- Décommissionnement infra Lakebase (équipe plateforme).
- Changements frontend (contrat API inchangé).

---

## User Scenarios & Testing

### User Story 1 — Lecture API inchangée (Priority: P1)

En tant qu’utilisateur du portail DCM, je consulte dashboards, pipelines, coûts, etc. **sans changement visible** après la migration.

**Why this priority** : valeur métier directe ; régression = incident production.

**Independent Test** : appeler les 12 routes existantes avec JWT valide et comparer structure JSON (champs, pagination) à la baseline Lakebase.

**Acceptance Scenarios**:

1. **Given** tables peuplées dans `it.ba_data_connect_monitoring__d`, **When** `GET /api/v1/pipelines`, **Then** réponse 200 avec `items` et `total` cohérents.
2. **Given** filtres `cloud_provider`, `source_lz_id`, **When** routes filtrées, **Then** résultats filtrés correctement.
3. **Given** backend démarré sans Lakebase, **When** `GET /api/v1/health`, **Then** statut DB = OK (warehouse joignable).

---

### User Story 2 — Opérations & observabilité (Priority: P2)

En tant qu’équipe plateforme, je dois diagnostiquer échecs de connexion ou requêtes lentes sur le warehouse.

**Independent Test** : logs structurés au startup + erreur auth SPN simulée.

**Acceptance Scenarios**:

1. **Given** secret SPN invalide, **When** startup, **Then** erreur explicite (pas de hang silencieux).
2. **Given** warehouse arrêté, **When** requête API, **Then** HTTP 503 avec message actionnable.

---

### User Story 3 — Développement local (Priority: P3)

En tant que développeur, je peux tester le backend contre le warehouse ppd avec variables d’env documentées.

**Independent Test** : `our_catalogs_spn.py` + `pytest` sur routes mockées ou warehouse de dev.

---

### Edge Cases

- Warehouse en **cold start** (latence première requête).
- Requêtes avec **window functions** et **JSON** : vérifier compatibilité SQL Databricks vs PostgreSQL.
- Types `TIMESTAMPTZ` / `JSONB` Lakebase → types Delta/UC équivalents.
- **Concurrence** : une connexion partagée (pas de pool) → risque de contention ; documenter limite ou sérialiser si nécessaire.
- **Merge conflict** actuel dans `app/db/connection.py` (HEAD vs develop) → résoudre avant implémentation.

---

## Requirements

### Functional Requirements

- **FR-001** : Le backend DOIT se connecter au SQL Warehouse via `databricks-sql-connector` avec auth SPN OAuth (`credentials_provider`).
- **FR-002** : Toutes les requêtes DOIVENT cibler `it.ba_data_connect_monitoring__d.<table>` (catalog/schema configurables).
- **FR-003** : La couche DB DOIT exposer `fetchall`, `fetchone`, `fetchscalar` async (wrapper `asyncio.to_thread`).
- **FR-004** : Les placeholders PostgreSQL (`$1`, `$2`) DOIVENT être convertis en placeholders Databricks (`?`) via utilitaire centralisé.
- **FR-005** : Les résultats DOIVENT être convertis en `dict` pour les routes (colonnes nommées).
- **FR-006** : Les 12 routes API existantes DOIVENT rester fonctionnelles sans changement de contrat OpenAPI.
- **FR-007** : La config Lakebase (`lakebase_*`) DOIT être retirée ou désactivée derrière feature flag jusqu’à bascule complète.
- **FR-008** : Un script de smoke test (`our_catalogs_spn.py` ou équivalent CI) DOIT valider catalog, schema, tables et lecture avant merge.

### Key Entities (tables SERVING)

Référence : `lakebase_ddl.sql`

| Table | Usage API principal |
|-------|---------------------|
| `pipeline_metrics` | `/pipelines`, dashboard |
| `compute_metrics` | `/clusters` (compute) |
| `cost_metrics` | `/costs` |
| `database_metrics` | `/databases` |
| `security_alerts` | `/security` |
| `collection_runs` | audit collectes |
| `activity_runs` | `/activities` |
| `user_metrics` | `/users` |
| `standard_checks` | `/governance`, standard-checks |
| `dim_landing_zone` | landing zones, filtres LZ |

---

## Success Criteria

- **SC-001** : `our_catalogs_spn.py` OK en ppd — catalog, schema, ≥10 tables, lecture 5 lignes sur au moins 1 table.
- **SC-002** : 100 % des tests unitaires/intégration backend passent contre warehouse (ou mocks documentés).
- **SC-003** : Aucune dépendance runtime à `asyncpg` pour la lecture SERVING en production.
- **SC-004** : Latence p95 des routes principales ≤ baseline Lakebase + 20 % (mesure en ppd).
- **SC-005** : Checklist routes manuelle (12 endpoints) validée avant prod.

---

## Plan d’implémentation — 5 phases

### Phase 0 — Prérequis & validation accès (1–2 j)

| # | Action | Livrable |
|---|--------|----------|
| 0.1 | Exécuter `our_catalogs_spn.py` en ppd avec secret via env | Log : catalog ✅, schema ✅, N tables ✅ |
| 0.2 | Vérifier GRANT SPN : `USE CATALOG`, `USE SCHEMA`, `SELECT` sur les 10 tables | Ticket IAM/UC si échec |
| 0.3 | Confirmer que le pipeline Databricks alimente bien `it.ba_data_connect_monitoring__d` | Alignement avec équipe data |
| 0.4 | Résoudre conflit git `connection.py` | Branche propre |

**Critère de sortie** : script vert + tables non vides sur au moins un domaine (ex. `pipeline_metrics`).

---

### Phase 1 — Dépendances & configuration (1 j)

| # | Action | Fichiers |
|---|--------|----------|
| 1.1 | Ajouter `databricks-sql-connector`, `databricks-sdk` dans `pyproject.toml` | `packages/dcm-backend/pyproject.toml` |
| 1.2 | Remplacer settings Lakebase par `warehouse_server_hostname`, `warehouse_http_path`, `warehouse_id`, `warehouse_catalog`, `warehouse_schema` | `app/config.py` |
| 1.3 | Documenter variables d’env (ECS / Secrets Manager) | `docs/migration/`, README backend |
| 1.4 | Mettre à jour Dockerfile si besoin | `packages/dcm-backend/Dockerfile` |

**Critère de sortie** : app démarre avec nouvelle config (connexion peut encore échouer).

---

### Phase 2 — Couche connexion (2–3 j)

| # | Action | Fichiers |
|---|--------|----------|
| 2.1 | Implémenter `DatabricksWarehousePool` : `connect`, `close`, `fetchall/fetchone/fetchscalar` | `app/db/connection.py` |
| 2.2 | Auth : `Config` + `oauth_service_principal` (pattern `our_catalogs_spn.py` / `connect_dcm_warehouse.py`) | idem |
| 2.3 | Connexion unique partagée + `ThreadPoolExecutor` ou `asyncio.to_thread` | idem |
| 2.4 | Créer `app/db/sql.py` : `convert_placeholders(query, n_args) -> str` (`$n` → `?`) | nouveau |
| 2.5 | Créer `app/db/rows.py` : `row_to_dict(cursor, row)` | nouveau |
| 2.6 | Brancher lifespan FastAPI : `app.state.db_pool` | `app/main.py` |
| 2.7 | Health check : `SELECT 1` ou `SHOW TABLES` limité | `app/api/routes/health.py` |

**Critère de sortie** : test manuel `fetchall("SELECT COUNT(*) FROM pipeline_metrics")` OK.

---

### Phase 3 — Adaptation des routes SQL (3–5 j)

| # | Action | Fichiers |
|---|--------|----------|
| 3.1 | Préfixer tables : `` `it`.`ba_data_connect_monitoring__d`.`pipeline_metrics` `` ou config `default catalog/schema` à la connexion | toutes routes |
| 3.2 | Auditer chaque route pour placeholders `$n` → utilitaire | `app/api/routes/*.py` (11 routes métier + health) |
| 3.3 | Adapter syntaxe SQL incompatible PG → Databricks (JSON, ILIKE, casts) | par route |
| 3.4 | Vérifier window functions (`ROW_NUMBER`, partitions) sur `compute_metrics`, `user_metrics` | `clusters.py`, `users.py` |
| 3.5 | Conserver signatures `Depends(get_db)` — type `DatabricksWarehousePool` | routes |

**Ordre suggéré** : `health` → `pipelines` → `dashboard` → reste.

**Critère de sortie** : chaque route retourne 200 en ppd avec données réelles.

---

### Phase 4 — Tests, CI & bascule (2–3 j)

| # | Action | Fichiers |
|---|--------|----------|
| 4.1 | Adapter `tests/conftest.py` : mock warehouse ou connexion ppd dédiée | `packages/dcm-backend/tests/` |
| 4.2 | Tests unitaires `convert_placeholders`, `row_to_dict` | `tests/unit/test_sql.py` |
| 4.3 | Intégrer smoke `our_catalogs_spn.py` en job CI optionnel (secrets CI) | `.github/workflows/dcm-backend.yml` |
| 4.4 | Test de charge léger (concurrence 10 req/s sur 1 connexion) | doc résultats |
| 4.5 | Bascule ppd → validation métier → prd | runbook |
| 4.6 | Retirer `asyncpg` / config Lakebase après stabilisation | `pyproject.toml`, config |

**Critère de sortie** : CI verte + validation métier signée.

---

## Risques & mitigations

| Risque | Impact | Mitigation |
|--------|--------|------------|
| Driver sync bloque l’event loop | Latence API | `asyncio.to_thread` systématique |
| Pas de pool → goulot sous charge | Timeouts | Monitorer ; envisager pool de connexions si Databricks le supporte plus tard |
| Divergence SQL PG vs Spark SQL | Erreurs 400/500 | Tests par route ; revue requêtes complexes |
| Secret SPN dans scripts locaux | Fuite credentials | Env only ; `.gitignore` ; rotation |
| Tables vides en UC | API vide | Valider pipeline amont avant bascule |
| Conflit git `connection.py` | Implémentation bloquée | Résoudre en Phase 0 |

---

## Assumptions

- Le SPN `sp-dcm-metrics-reader` (app id `c92fca2d-0533-4392-8b28-c916f421f2f3`) a les droits UC nécessaires sur `it.ba_data_connect_monitoring__d`.
- Les tables UC ont un schéma **compatible** avec `lakebase_ddl.sql` (noms de colonnes alignés).
- Le contrat API REST reste inchangé pour le frontend.
- OAuth M2M existant (`DatabricksTokenManager` / SDK) peut être remplacé ou réutilisé via `oauth_service_principal` du connector.
- Lakebase reste en place jusqu’à validation complète en ppd (bascule progressive possible via feature flag).

---

## Prochaines commandes Spec Kit (Copilot)

```
/speckit.plan Détailler Phase 2–3 : DatabricksWarehousePool, sql.py, ordre migration routes, feature flag Lakebase
/speckit.tasks
/speckit.implement
```

---

## Références

- `docs/migration/ANALYSE-ARCHITECTURE.md`
- `docs/MIGRATION-LAKEBASE-TO-WAREHOUSE.md`
- `our_catalogs_spn.py` — smoke test accès UC
- `connect_dcm_warehouse.py` — pattern connexion documenté
- `packages/dcm-databricks-pipeline/schemas/lakebase_ddl.sql`
