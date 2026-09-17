# Feature Specification: Métriques Usage & FinOps Databricks (Azure + AWS) — couche curated

**Feature Branch**: `010-databricks-usage-finops-curated`
**Work Type**: feature
**Priority**: P2
**Created**: 2026-07-27
**Status**: Draft

**Input**: Mettre à disposition les métriques **FinOps** et les métriques **d'usage** (cluster, table, …) Databricks, **communes aux deux workspaces Azure et AWS**, à partir des **system tables** Databricks. La disponibilité de ces données doit être **au niveau du workspace Databricks AWS**. Extraire le **maximum** de données d'usage et de coûts dans la couche **curated**, en respectant l'**architecture médaillon** : **aucune transformation** par rapport aux données source. But final : **exposer dans l'application DCM** les données d'usage et de FinOps Databricks. (Spike Delta Sharing Azure↔AWS mené mais **approche abandonnée** — cf. Assumptions.)

---

## Domain Scope

| Domaine | In scope | Ticket Story | Packages |
|---------|----------|--------------|----------|
| Frontend | ❌ | ❌ | — |
| Backend | ❌ | ❌ | — |
| DataEng | ✅ | ✅ | `packages/dcm-databricks-pipeline` |
| DevOps | ❌ | ❌ | — |
| QA | ❌ | ❌ | — |

## Environnements & Workspaces

| Rôle | Env | Workspace URL |
|------|-----|---------------|
| Workflow d'ingestion (exécution) | AWS **dev** | `https://dbc-16a9ad66-c301.cloud.databricks.com/` |
| Workflow d'ingestion (exécution) | AWS **prod** | `https://dbc-af3acef9-c998.cloud.databricks.com/` |
| Source system tables (lecture via SP) | Azure **dev + prod** | `https://adb-3059738143768593.13.azuredatabricks.net/` |

Cible curated (dev + prod) : `it.ba_data_connect_monitoring__d`.

## Ticket Plan

| Champ | Valeur |
|-------|--------|
| Stories Jira | **2** |
| Mode | custom (split par sujet, pas par domaine) |
| Domaines avec ticket | DataEng |
| Story 1 | **Usage** — usage Databricks (compute/clusters, tables, node timeline…) |
| Story 2 | **FinOps** — coûts Databricks (`system.billing.usage` + `system.billing.list_prices`, tables fidèles source) |

## Dependency Analysis

| Besoin | Domaine | Résolution |
|--------|---------|------------|
| Accès cross-tenant aux system tables Azure depuis le workspace AWS | DataEng | **Workflow Databricks (AWS) + Service Principal** disposant de droits `SELECT` sur les schémas system Azure (`system.billing`, `system.compute`, `system.access`, `system.lakeflow`…). **Accès déjà accordé au SP** (validé). **Delta Sharing abandonné.** |
| Cible curated + naming | DataEng | Écriture dans la couche **curated** de `it.ba_data_connect_monitoring__d`, convention de nommage **`layer_source_domain_metric`** (ex. `curated_databricks_compute_usage`, `curated_dbx_billing_usage`, `curated_dbx_billing_list_prices`). |
| Corrélation multi-cloud (Azure + AWS) | DataEng | Chaque ligne curated porte `cloud_provider` (`azure`\|`aws`) + les identifiants natifs Databricks (`workspace_id` / `workspace_url`, `account_id`). **Pas de notion de Landing Zone DCM** sur ce besoin — unification par `cloud_provider` uniquement. |
| Exposition dans l'app DCM (routes API + UI) | Backend/Frontend | **Hors périmètre de cet Epic** — futur Epic Backend+Frontend qui lit les tables curated/gold produites ici via le SQL Warehouse. |

## User Scenarios & Testing

### User Story 1 — Usage Databricks commun Azure + AWS en curated (Priority: P1)

En tant qu'ingénieur data DCM, je veux disposer, **dans la couche curated du workspace AWS** (`it.ba_data_connect_monitoring__d`), des métriques **d'usage** Databricks (clusters/compute, tables, node timeline, **usage utilisateurs via `system.access.audit`**) issues des **system tables** des deux clouds (Azure via SP cross-tenant, AWS nativement), afin que ces données soient prêtes à être exposées par l'application DCM.

**Why this priority**: fondation de la vue usage unifiée multi-cloud ; sans elle, aucune donnée usage Databricks exploitable côté DCM.

**Independent Test**: exécuter le workflow d'ingestion usage seul ; vérifier que les tables `curated_databricks_*_usage` (Azure + AWS), **dont l'usage utilisateurs (`system.access.audit`)**, sont peuplées, avec `cloud_provider` et identifiants workspace natifs renseignés, et que les colonnes sont **fidèles à la source** (aucune agrégation/transformation dans curated).

**Acceptance Scenarios**:
1. **Given** le SP a `SELECT` sur `system.compute.*` Azure, **When** le workflow usage tourne, **Then** les lignes usage Azure atterrissent en curated AWS avec `cloud_provider = "azure"`.
2. **Given** les system tables AWS locales, **When** le workflow usage tourne, **Then** les lignes usage AWS atterrissent avec `cloud_provider = "aws"`.
3. **Given** le SP a `SELECT` sur `system.access.audit` (Azure + AWS), **When** le workflow usage tourne, **Then** les événements d'usage utilisateurs atterrissent en curated (ex. `curated_dbx_access_audit`) avec `cloud_provider` et identifiants workspace, fidèles à la source.
4. **Given** une réexécution du workflow sur la même fenêtre, **When** il rejoue, **Then** aucune ligne dupliquée (idempotence par clé métier / MERGE).
5. **Given** une métrique source absente, **When** curated est écrite, **Then** la colonne est `NULL` (jamais valeur fictive).

---

### User Story 2 — FinOps (coûts) Databricks commun Azure + AWS en curated (Priority: P1)

En tant qu'ingénieur data DCM, je veux disposer, dans la couche curated AWS, des métriques **de coût** Databricks des deux clouds issues de `system.billing.usage` et `system.billing.list_prices` (**tables fidèles à la source, sans transformation ni jointure**), afin d'exposer une vue FinOps unifiée dans DCM.

**Why this priority**: le volet FinOps est un objectif direct de la demande ; coût réel > estimation.

**Independent Test**: exécuter le workflow FinOps seul ; vérifier `curated_dbx_billing_usage` et `curated_dbx_billing_list_prices` peuplées pour Azure + AWS, colonnes **fidèles à la source** (aucune transformation/jointure), traçabilité (`collected_at`).

**Acceptance Scenarios**:
1. **Given** `system.billing.usage` + `list_prices` Azure accessibles via SP, **When** le workflow FinOps tourne, **Then** les lignes Azure sont en curated AWS avec `cloud_provider = "azure"`, colonnes fidèles source.
2. **Given** `system.billing.*` AWS locales, **When** le workflow FinOps tourne, **Then** les lignes AWS sont en curated avec `cloud_provider = "aws"`.
3. **Given** réexécution même fenêtre, **When** rejoue, **Then** pas de doublon (MERGE sur clé billing).
4. **Given** médaillon respecté, **When** on inspecte curated, **Then** les colonnes reflètent la source à la granularité `system.billing.usage` / `list_prices` — **aucune valorisation ni jointure** (reportée en gold, hors Epic).

---

## Out of scope (this Epic)

- **Backend API** : routes FastAPI exposant usage/FinOps Databricks — **futur Epic** (lecture des tables curated/gold via SQL Warehouse).
- **Frontend** : dashboards/pages DCM usage & FinOps — **futur Epic**.
- **Delta Sharing** Azure↔AWS — approche explorée (spike) puis **abandonnée** au profit du Workflow + Service Principal.
- **Feature 010 (system-tables-hybrid-migration)** — **supprimée** et remplacée par cet Epic.
- Décommissionnement collecteur/DLT des autres domaines (ADF, cost Azure collecteur, security, etc.).

## Work Breakdown (preview)

| ID | Domain | Summary | Ticket |
|----|--------|---------|--------|
| T001 | DataEng | Usage Databricks (compute/tables/node timeline) Azure+AWS → curated `it.ba_data_connect_monitoring__d` via Workflow + SP | ✅ |
| T002 | DataEng | FinOps Databricks (`system.billing.usage` + `list_prices`, tables fidèles source) Azure+AWS → curated | ✅ |
| — | Backend | Routes API usage/FinOps Databricks | ❌ hors Epic |
| — | Frontend | Pages/dashboards usage & FinOps | ❌ hors Epic |

## Requirements

### Functional Requirements

- **FR-001**: Le système DOIT extraire les métriques **d'usage** Databricks depuis les system tables (`system.compute.clusters`, `system.compute.node_timeline`, tables d'usage/tables, et **`system.access.audit`** pour l'usage utilisateurs) pour **Azure et AWS**.
- **FR-002**: Le système DOIT extraire les métriques **de coût** Databricks depuis `system.billing.usage` et `system.billing.list_prices`, ingérées **fidèlement (telles quelles, sans transformation ni jointure)** dans des tables curated distinctes, pour **Azure et AWS**. La valorisation `usage × list_prices` est **reportée en gold** (hors Epic).
- **FR-003**: L'accès aux system tables **Azure** depuis le workspace **AWS** DOIT se faire via un **Workflow Databricks exécuté par un Service Principal** disposant de droits `SELECT` sur les schémas system Azure. Aucun Delta Sharing.
- **FR-004**: Les données DOIVENT atterrir dans la couche **curated** de `it.ba_data_connect_monitoring__d`.
- **FR-005**: Les tables curated DOIVENT respecter la convention de nommage **`layer_source_domain_metric`** (ex. `curated_databricks_compute_usage`, `curated_dbx_billing_usage`, `curated_dbx_billing_list_prices`).
- **FR-006**: La couche curated DOIT être **fidèle à la source** (médaillon) : **aucune transformation métier, agrégation ni jointure** par rapport aux system tables ; renommage/typage/cast technique tolérés, agrégats et valorisations réservés à une éventuelle couche gold.
- **FR-007**: Le système DOIT extraire le **maximum** de colonnes disponibles d'usage et de coût des system tables (pas de projection restrictive).
- **FR-008**: Chaque ligne curated DOIT porter `cloud_provider` (`azure` | `aws`) et les identifiants natifs Databricks (`workspace_id` / `workspace_url`, `account_id`) issus de la source. **Aucune notion de Landing Zone DCM** — l'unification multi-cloud se fait sur `cloud_provider`.
- **FR-009**: Les écritures DOIVENT être **idempotentes** (MERGE sur clé métier), rejouables sans doublon ni trou.
- **FR-010**: Le système DOIT renseigner traçabilité par ligne (`collection_run_id`, `collected_at` / `_ingested_at`).
- **FR-011**: Aucune donnée fictive : métrique source absente ⇒ colonne `NULL` (jamais `0` non daté).
- **FR-012**: Le déploiement DOIT se faire via le Databricks Asset Bundle du package (`resources/`), cohérent avec l'existant.
- **FR-013**: Le Service Principal DOIT avoir `SELECT` sur les schémas system requis (`system.billing`, `system.compute`, `system.access` (dont `system.access.audit`), et selon usage `system.lakeflow`) côté Azure et AWS.

## Success Criteria

- **SC-001**: Tables curated usage + FinOps peuplées pour **Azure ET AWS** dans `it.ba_data_connect_monitoring__d`.
- **SC-002**: Nommage `layer_source_domain_metric` respecté sur toutes les tables produites.
- **SC-003**: Curated fidèle à la source — audit colonnes = pas de transformation métier vs system tables.
- **SC-004**: Workflow idempotent — 2 exécutions consécutives ⇒ 0 doublon.
- **SC-005**: Chaque ligne porte `cloud_provider` + identifiants workspace natifs (`workspace_id`/`workspace_url`) corrects.
- **SC-006**: Ruff zéro warning, tests verts (transformations + mapping).

## Assumptions

- **A1 — Portée cross-tenant (résolu).** Les system tables Azure ne sont pas visibles nativement dans le compte/metastore AWS ; l'accès passe **uniquement** par le Workflow + Service Principal cross-tenant. **Droits SP accordés côté Azure — validé.**
- **A2 — Corrélation multi-cloud sans LZ.** Unification par `cloud_provider` (`azure`|`aws`) + identifiants Databricks natifs (`workspace_id`/`workspace_url`, `account_id`). **Aucune table de mapping LZ** requise pour ce besoin.
- **A3 — Valorisation coût (révisé).** **Archi médaillon pure** : `system.billing.usage` et `system.billing.list_prices` sont ingérées **telles quelles** dans deux tables curated distinctes, **sans jointure ni valorisation**. Le calcul `coût = usage × list_prices` est **reporté en couche gold** (futur Epic).
- **A4 — Fréquence & fenêtre.** Planification du Workflow (horaire ? 15 min ?) et lookback incrémental à définir selon fraîcheur DCM.
- **A5 — Feature 010 (system-tables-hybrid-migration) supprimée** ; cet Epic la remplace (compute/workflow inclus dans le périmètre usage cross-cloud).
- **A6 — Workspaces cibles.** Exécution AWS dev `dbc-16a9ad66-c301`, AWS prod `dbc-af3acef9-c998` ; source Azure dev+prod `adb-3059738143768593.13`.
