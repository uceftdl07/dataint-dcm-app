# Feature Specification: Tables référentiel `dim_reference_landing_zone_dbx_workspace` & `dim_reference_landing_zone_business_application`

**Feature Branch**: `014-reference-lz-tables`
**Work Type**: feature
**Priority**: P2
**Created**: 2026-08-20

**Input**: Créer 2 tables gold de référentiel — `dim_reference_landing_zone_dbx_workspace` (mapping workspace Databricks ↔ Landing Zone, alimentée par les tables AWS et Azure `workspace_inventory`) et `dim_reference_landing_zone_business_application` (mapping Business Application ↔ Landing Zone, alimentée par la vue Azure `ref_ba_lz`), convergeant toutes deux dans le catalog `it`, schéma `ba_data_connect_monitoring__<env>`, en suivant la même logique d'ingestion cross-tenant que les tables `system.*` (`pipelines/system_tables/`).

> **Note de re-intake (2026-08-20)** : ce dossier `specs/014-reference-lz-tables` portait un design précédent (`dim_reference_lz_workspace` / `dim_reference_lz_ba`, avec résolution `landing_zone_id` via jointure sur `dim_landing_zone`). Ce design est **abandonné** — le code correspondant (`pipelines/reference_lz/`) a été retiré du disque avant cette re-spécification. Ce document (et `data-model.md`/`research.md`/`quickstart.md`) reflète le **nouveau** design ci-dessous.

## Clarifications

### Session 2026-08-20

- Q: Nom physique de table/colonnes : garder "buisness" ou corriger en "business" ? → A: Corriger en "business" (orthographe standard) — `dim_reference_landing_zone_business_application`, colonnes `business_application_name`/`business_application_id`.
- Q: Si la source (`workspace_inventory` ou `ref_ba_lz`) contient 2 lignes avec la même clé dans un même run, que doit faire le pipeline ? → A: Dédupliquer avant MERGE (1 ligne conservée par clé, règle d'ordre déterministe à fixer en `/speckit.plan`) — le job ne doit jamais planter sur ce cas (`multiple source rows matched`).
- Q: Si une source (AWS ou Azure) est indisponible pendant un run, que doit faire le job vis-à-vis des tables/sources encore accessibles ? → A: Échec isolé par table/source — les autres tâches continuent et sont mises à jour normalement ; alerte explicite sur la tâche en échec.
- Q: Si une ligne source a une clé de fusion NULL ou vide (`workspace_id` / `subscription_or_account_id`), que doit faire le pipeline ? → A: Exclure la ligne du MERGE (filtrage avant fusion) et logguer le nombre de lignes exclues.

## Domain Scope

| Domaine | In scope | Ticket Story | Packages |
|---------|----------|--------------|----------|
| Frontend | ❌ | ❌ | — |
| Backend | ❌ | ❌ | — |
| DataEng | ✅ | ✅ | packages/dcm-databricks-pipeline |
| DevOps | ❌ | ❌ | — |
| QA | ❌ | ❌ | — |

## Ticket Plan

| Stories Jira | 1 |
| Mode | single_domain |
| Domaines avec ticket | dataeng |

## Dependency Analysis

Aucune dépendance bloquante identifiée — le socle de lecture cross-tenant Azure (connecteur SQL, credentials M2M, secret scope `dcm-secret-scope`) et le pattern job wheel-task + MERGE sont déjà en production (`pipelines/system_tables/`), réutilisés à l'identique.

| Besoin | Domaine | Résolution |
|--------|---------|------------|
| Accès cross-tenant Azure depuis compute AWS | DataEng | Réutiliser `pipelines/common/` (`read_azure_batches`, `azure_auth`) — déjà en prod |
| Table cible `it.ba_data_connect_monitoring__<env>` existante | DataEng | Schéma déjà utilisé par les tables gold système existantes |

## Prerequisites

- **Small branches / small PRs** : une seule branche fille `dataeng/014-reference-lz-tables` — les 2 tables partagent le même module d'ingestion, changement focalisé sur `packages/dcm-databricks-pipeline`.
- Spec intake + domain scope confirmés (`intake.json` / `domain-scope.json`).
- Aucune dépendance bloquante à résoudre (voir Dependency Analysis).
- Clarification retenue (intake 2026-08-20) : dans la vue source `ref_ba_lz`, la colonne `lz_id` **est déjà** la valeur `subscription_or_account_id` (renommage direct, pas de jointure de résolution).

## User Scenarios & Testing

### User Story 1 - Référentiel workspace ↔ Landing Zone et Business Application ↔ Landing Zone (Priority: P1)

En tant qu'exploitant DCM, je veux disposer de deux tables gold référentiel (`dim_reference_landing_zone_dbx_workspace`, `dim_reference_landing_zone_business_application`) alimentées automatiquement depuis les sources AWS et Azure, afin de pouvoir rattacher un workspace Databricks ou une Business Application à son identifiant de compte/subscription cloud, sans ressaisie manuelle.

**Why this priority**: Référentiel de base nécessaire à toute jointure ultérieure (dashboards, autres pipelines) entre métriques cloud et landing zone/business application — pas de valeur métier directe sans lui, mais bloquant pour les usages en aval.

**Independent Test**: Après un run du job, `SELECT * FROM it.ba_data_connect_monitoring__<env>.dim_reference_landing_zone_dbx_workspace` renvoie les workspaces AWS **et** Azure (union des deux sources) sans doublon sur `workspace_id` ; `SELECT * FROM it.ba_data_connect_monitoring__<env>.dim_reference_landing_zone_business_application` renvoie une ligne par `subscription_or_account_id` distinct de la vue `ref_ba_lz`.

**Acceptance Scenarios**:

1. **Given** une ligne existe dans `egress_firewall_aws.workspace_inventory` (AWS) et une ligne existe dans `egress_firewall.workspace_inventory` (Azure) pour deux workspaces différents, **When** le job d'ingestion s'exécute, **Then** `dim_reference_landing_zone_dbx_workspace` contient les deux lignes, avec `cloud_provider` = `aws`/`azure` respectivement et `subscription_or_account_id` peuplé depuis `aws_account_id`/`subscription_id`.
2. **Given** un workspace déjà présent dans `dim_reference_landing_zone_dbx_workspace` change de nom dans la source, **When** le job re-tourne, **Then** la ligne existante est mise à jour (MERGE par `workspace_id`) — pas de doublon.
3. **Given** une ligne existe dans la vue `ref_ba_lz` (name, ba_id, lz_id, cloud), **When** le job d'ingestion s'exécute, **Then** `dim_reference_landing_zone_business_application` contient une ligne avec `subscription_or_account_id` = `lz_id`, `business_application_name` = `name`, `business_application_id` = `ba_id`, `cloud_provider` = `cloud`.
4. **Given** un `subscription_or_account_id` déjà présent dans `dim_reference_landing_zone_business_application` réapparaît dans un run suivant de `ref_ba_lz` avec un `business_application_name`/`id` différent, **When** le job re-tourne, **Then** la ligne existante est mise à jour (MERGE par `subscription_or_account_id`) — dernier run fait foi (pas de conservation de l'historique).

---

## Out of scope (this Epic)

- Frontend/Backend : aucune exposition API/UI de ces référentiels dans cette Epic (tables gold consommables directement en SQL par d'autres pipelines/dashboards si besoin, hors périmètre ici).
- Résolution/enrichissement `landing_zone_id` via jointure (`dim_landing_zone`) — **abandonné** vs le design précédent de ce dossier ; les deux tables stockent directement `subscription_or_account_id`, sans FK vers une table `dim_landing_zone`.

## Work Breakdown (preview)

| ID | Domain | Summary | Ticket |
|----|--------|---------|--------|
| T001 | DataEng | Nouveau module d'ingestion (job wheel-task, MERGE) pour `dim_reference_landing_zone_dbx_workspace` + `dim_reference_landing_zone_business_application`, socle `pipelines/system_tables/` | ✅ |

## Requirements

### Functional Requirements

- **FR-001**: Le système DOIT créer la table gold `dim_reference_landing_zone_dbx_workspace` dans `it.ba_data_connect_monitoring__<env>` avec les colonnes `workspace_id` (STRING, NOT NULL, PK), `workspace_name` (STRING), `subscription_or_account_id` (STRING), `cloud_provider` (STRING, NOT NULL), `updated_at` (TIMESTAMP), `TBLPROPERTIES ('quality'='gold', 'delta.enableChangeDataFeed'='true')`.
- **FR-002**: Le système DOIT alimenter `dim_reference_landing_zone_dbx_workspace` par union des lignes distinctes de `` `onedatalake-ppd-internal`.egress_firewall_aws.workspace_inventory `` (colonnes `workspace_id`, `workspace_name`, `aws_account_id`→`subscription_or_account_id`, `cloud`→`cloud_provider`) et `` `onedatalake-ppd-internal`.egress_firewall.workspace_inventory `` (colonnes `workspace_id`, `workspace_name`, `subscription_id`→`subscription_or_account_id`, `cloud`→`cloud_provider`), lues respectivement en natif (AWS) et via le connecteur cross-tenant Azure (même socle que `pipelines/system_tables/`).
- **FR-003**: Le système DOIT créer la table gold `dim_reference_landing_zone_business_application` dans `it.ba_data_connect_monitoring__<env>` avec les colonnes `subscription_or_account_id` (STRING, PK), `business_application_name` (STRING), `business_application_id` (STRING), `cloud_provider` (STRING, NOT NULL), `updated_at` (TIMESTAMP), mêmes `TBLPROPERTIES` que FR-001.
- **FR-004**: Le système DOIT alimenter `dim_reference_landing_zone_business_application` depuis la vue Azure `` `catalog_badsdataeng_dev`.`ref_dcm`.`ref_ba_lz` `` (`name`→`business_application_name`, `ba_id`→`business_application_id`, `lz_id`→`subscription_or_account_id` — renommage direct, `lz_id` de la vue est déjà la valeur `subscription_or_account_id`, sans jointure de résolution — et `cloud`→`cloud_provider`).
- **FR-005**: Le système DOIT charger les deux tables en mode **full** (pas de watermark) — la source entière est relue et fusionnée (MERGE) à chaque exécution du job, upsert par clé métier (`workspace_id` pour la première table, `subscription_or_account_id` pour la seconde).
- **FR-006**: Le système DOIT renseigner `updated_at` avec le timestamp du run de chargement, identique pour toutes les lignes d'un même run.
- **FR-007**: Le système DOIT garantir l'unicité de la clé primaire déclarée sur chaque table (`workspace_id` / `subscription_or_account_id`) via MERGE — pas de duplication à travers les runs successifs.
- **FR-008**: Le système DOIT suivre le même pattern d'architecture que `pipelines/system_tables/` (module Python wheel-task, pas de matérialisation DLT ; lecture native AWS + connecteur cross-tenant Azure ; job planifié séparé).
- **FR-009**: Si la source (`workspace_inventory` AWS/Azure ou `ref_ba_lz`) contient plusieurs lignes partageant la même clé de fusion (`workspace_id` / `subscription_or_account_id`) au sein d'un même run, le système DOIT dédupliquer ces lignes (une seule ligne conservée par clé, règle de tri déterministe) **avant** le MERGE — le job ne doit jamais échouer avec une erreur de type « multiple source rows matched ».
- **FR-010**: Si une source (lecture native AWS ou connecteur cross-tenant Azure) est indisponible pendant un run, le système DOIT isoler l'échec à la tâche concernée (table/source) sans bloquer la mise à jour des autres tables/sources accessibles dans le même run, et DOIT remonter une alerte explicite sur la tâche en échec.
- **FR-011**: Le système DOIT exclure du MERGE toute ligne source dont la clé de fusion (`workspace_id` / `subscription_or_account_id`) est NULL ou vide, et DOIT logguer le nombre de lignes exclues pour ce motif.

## Success Criteria

- **SC-001**: Après un run, `SELECT workspace_id, COUNT(*) FROM dim_reference_landing_zone_dbx_workspace GROUP BY workspace_id HAVING COUNT(*) > 1` renvoie 0 ligne.
- **SC-002**: Après un run, `SELECT subscription_or_account_id, COUNT(*) FROM dim_reference_landing_zone_business_application GROUP BY subscription_or_account_id HAVING COUNT(*) > 1` renvoie 0 ligne.
- **SC-003**: `dim_reference_landing_zone_dbx_workspace` contient au moins une ligne `cloud_provider = 'aws'` et une ligne `cloud_provider = 'azure'` après un run nominal (les deux sources sont non vides en prod).
- **SC-004**: Un second run consécutif sans changement de source ne modifie pas le nombre total de lignes des deux tables (idempotence du MERGE).
- **SC-005**: Si une source contient des doublons de clé de fusion dans un même run, le job se termine sans erreur et chaque table cible ne contient qu'une seule ligne par clé (dédoublonnage effectif, FR-009).
- **SC-006**: Aucune ligne à clé de fusion NULL/vide n'est présente dans les tables cibles après un run (FR-011).

## Assumptions

- `lz_id` dans la vue `ref_ba_lz` est déjà la valeur `subscription_or_account_id` (confirmé par l'utilisateur en intake) — pas de jointure de résolution supplémentaire nécessaire.
- Catalog cible `it`, schéma `ba_data_connect_monitoring__<env>` — cohérent avec le schéma déjà utilisé par les tables gold système existantes (`pipelines/system_tables/`).
- `dim_reference_landing_zone_business_application` n'a pas de colonne `landing_zone_id`/`lz_id` distincte : le rattachement à la Landing Zone se fait via `subscription_or_account_id`, à joindre en aval avec `dim_reference_landing_zone_dbx_workspace` (ou `dim_landing_zone`) si besoin — pas de FK déclarée dans cette Epic.
- PK simple (`subscription_or_account_id`) sur `dim_reference_landing_zone_business_application` implique une seule Business Application par compte/subscription dans cette table (contrairement au design précédent qui autorisait plusieurs BA par LZ via une PK composite) — géré par la déduplication FR-009 si la source en contient plusieurs pour une même clé ; la règle de tri exacte (quelle ligne « gagne ») sera fixée en `/speckit.plan`.
