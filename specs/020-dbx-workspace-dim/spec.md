# feature : Dimension `dim_dbx_workspace` (workspaces_latest curated + vue référentiel)

**Feature Branch**: `020-dbx-workspace-dim` — branches filles `{domain}/020-dbx-workspace-dim`
**Work Type**: feature
**Priority**: P2
**Created**: 2026-09-02

**Input**: Ingérer les tables Azure et AWS `system.access.workspaces_latest` dans curated. Créer une `dim_dbx_workspace` qui est une vue issue de l'inner join entre `curated_dbx_access_workspaces_latest` et `dim_reference_landing_zone_dbx_workspace` sur la clé `workspace_id`, avec `subscription_or_account_id` NOT NULL et `status = 'RUNNING'`. Colonnes : `workspace_id` (string, Databricks workspace ID), `workspace_name` (string, display name, depuis `curated_dbx_access_workspaces_latest`), `subscription_or_account_id` (string, AWS account ID from STS role ARN), `cloud` (string, `aws` ou `azure`), `updated_at` (timestamp).

## Clarifications

### Session 2026-09-02

- Q: Où/comment matérialiser la vue `dim_dbx_workspace` (aucun précédent `CREATE VIEW` dans le pipeline) ? → A: **Nouveau module dédié** (ex. `pipelines/gold_dbx_workspace/`) + **task de job dédiée** exécutant `spark.sql("CREATE OR REPLACE VIEW …")`, ordonnancée **après** le job `system_tables` (produit le curated) **et** le job `reference_lz` (produit la dim référentiel). Cohérent avec le socle wheel (pas de DLT).
- Q: Clé de merge de l'ingestion `curated_dbx_access_workspaces_latest` ? → A: `(cloud_provider, workspace_id)` — `workspaces_latest` est un snapshot « latest » (une ligne par workspace), full load **sans** watermark.
- Q: Source de la colonne `updated_at` de la vue ? → A: `current_timestamp()` évalué à la lecture de la vue (aligné sur la convention gold `_generated_at`).

## Domain Scope

Depuis `intake.json` — « In scope » = lecture autorisée, « Ticket » = reçoit une Story.

| Domaine | In scope | Ticket Story | Packages |
|---------|----------|--------------|----------|
| Frontend | ❌ | ❌ | — |
| Backend | ❌ | ❌ | — |
| DataEng | ✅ | ✅ | packages/dcm-databricks-pipeline |
| DevOps | ❌ | ❌ | — |
| QA | ❌ | ❌ | — |

## Ticket Plan

| Stories Jira | 1 |
|---|---|
| Mode | single_domain |
| Domaines avec ticket | dataeng |

## Contexte

DCM ingère déjà plusieurs tables système Databricks (`system.access.audit`, `system.billing.*`, `system.compute.*`…) dans la couche curated via le socle `pipelines/system_tables/` (lecture AWS native + Azure cross-tenant), et dispose d'une table référentiel `dim_reference_landing_zone_dbx_workspace` (feature 014) mappant `workspace_id → subscription_or_account_id` / `cloud_provider`.

Il n'existe aujourd'hui **aucune dimension consolidée des workspaces Databricks actifs** croisant l'inventaire système (`system.access.workspaces_latest` : nom + `status`) avec le référentiel Landing Zone (compte/subscription cloud). Les consommateurs en aval (gold, backend) ne peuvent pas filtrer proprement sur « workspaces réellement `RUNNING` rattachés à une LZ connue ».

Cette feature comble ce manque en deux temps : (1) ingérer `system.access.workspaces_latest` (AWS + Azure) dans `curated_dbx_access_workspaces_latest`, (2) exposer une vue `dim_dbx_workspace` = inner join filtré entre ce curated et `dim_reference_landing_zone_dbx_workspace`.

## Dependency Analysis

Constats de la vérification code (Q6 de l'intake) — tout est DataEng, aucun ticket cross-domaine requis.

| Besoin | Domaine requis | Preuve (fichier) | Résolution |
|--------|----------------|------------------|------------|
| Ingestion `system.access.*` → `curated_dbx_access_*` (dual-cloud) | dataeng | `pipelines/system_tables/specs.py` — `SOURCE_ACCESS_AUDIT` → `curated_dbx_access_audit` via registre `SPECS` | pattern existant réutilisé |
| Full-load sans watermark (petite table) | dataeng | `pipelines/common/models.py` — `watermark_column=None ⇒ full load` (ex. `list_prices`) | pattern existant réutilisé |
| Table référentiel jointe (`workspace_id`) | dataeng | `pipelines/reference_lz/specs.py` — `dim_reference_landing_zone_dbx_workspace` (cols `subscription_or_account_id`, `cloud_provider`) | déjà déployée (feature 014) |
| Pattern `CREATE VIEW` dans le pipeline | dataeng | aucun `CREATE OR REPLACE VIEW` trouvé — tout est table DLT / Delta MERGE | nouveau module dédié `pipelines/gold_dbx_workspace/` (cf. `## Clarifications`) |

## Prerequisites

- **Small branches / small PRs** : la feature tient sur une seule branche fille `dataeng/020-dbx-workspace-dim` touchant uniquement `packages/dcm-databricks-pipeline` (ajout d'une `IngestionSpec` + module/vue + tests). Périmètre fichiers restreint.
- Intake + domain scope confirmés (`intake.json` / `domain-scope.json`).
- Aucune dépendance bloquante cross-domaine (DataEng-only).
- `dim_reference_landing_zone_dbx_workspace` (feature 014) déployée dans `it.ba_data_connect_monitoring__<env>` — prérequis de la jointure.
- Clarifications levées (session 2026-09-02) : matérialisation de la vue, `merge_keys`, source `updated_at` — voir `## Clarifications`.

## User stories

### User Story 1 — Dimension des workspaces Databricks actifs (Priority: P1)

En tant qu'exploitant DCM, je veux une dimension `dim_dbx_workspace` listant chaque workspace Databricks **actif** (`status = 'RUNNING'`) rattaché à une Landing Zone connue (`subscription_or_account_id` non nul), avec son nom d'affichage et son cloud, afin que les couches gold et le backend puissent joindre proprement leurs métriques au bon workspace/compte sans ressaisie.

**Why this priority** : sans cette dimension, aucun consommateur ne dispose d'une liste fiable et filtrée des workspaces actifs croisant l'inventaire système et le référentiel LZ.
**Independent Test** : après un run du job d'ingestion, `SELECT * FROM it.ba_data_connect_monitoring__<env>.curated_dbx_access_workspaces_latest` renvoie des lignes AWS **et** Azure ; puis `SELECT * FROM …dim_dbx_workspace` ne renvoie que les workspaces `RUNNING` avec `subscription_or_account_id` non nul, une ligne par `workspace_id`, avec les 5 colonnes attendues.

**Acceptance Scenarios**

1. **Given** `system.access.workspaces_latest` contient des workspaces AWS et Azure, **When** le job d'ingestion s'exécute, **Then** `curated_dbx_access_workspaces_latest` contient les lignes des deux clouds avec `cloud_provider` peuplé.
2. **Given** un `workspace_id` présent dans `curated_dbx_access_workspaces_latest` (`status='RUNNING'`) **et** dans `dim_reference_landing_zone_dbx_workspace` (`subscription_or_account_id` non nul), **When** on interroge `dim_dbx_workspace`, **Then** il renvoie une ligne avec `workspace_id`, `workspace_name` (depuis le curated), `subscription_or_account_id` + `cloud` (depuis le référentiel) et `updated_at`.
3. **Given** un `workspace_id` avec `status != 'RUNNING'` **ou** `subscription_or_account_id` nul, **When** on interroge `dim_dbx_workspace`, **Then** ce workspace est **absent** de la vue.
4. **Given** un `workspace_id` présent dans le curated mais **absent** du référentiel (ou l'inverse), **When** on interroge `dim_dbx_workspace`, **Then** il est absent (inner join strict).

## Acceptance Criteria

1. **Given** un run du job, **When** `curated_dbx_access_workspaces_latest` est peuplée, **Then** elle contient les colonnes fidèles de `system.access.workspaces_latest` nécessaires à la vue (au minimum `workspace_id`, `workspace_name`, `status`, `cloud_provider`) sans doublon sur la clé de merge.
2. **Given** la vue `dim_dbx_workspace` créée, **When** on la requête, **Then** elle expose exactement `workspace_id`, `workspace_name`, `subscription_or_account_id`, `cloud`, `updated_at`, filtrée `status='RUNNING'` et `subscription_or_account_id IS NOT NULL`, une ligne par `workspace_id`.
3. Gates du package verts (ruff → mypy scoped → pytest).

## Out of scope (cet Epic)

- Exposition backend / frontend de `dim_dbx_workspace` (aucun ticket Backend/Frontend dans cet Epic — consommation en aval traitée séparément).
- Historisation SCD (la vue reflète l'état courant `workspaces_latest` + référentiel, pas d'historique).
- Toute colonne de `system.access.workspaces_latest` non nécessaire à la vue (projection fidèle mais restreinte).

## Work Breakdown (preview)

| ID | Domain | Summary | Ticket |
|----|--------|---------|--------|
| T001 | DataEng | Ajouter l'`IngestionSpec` `workspaces_latest` (AWS+Azure) au registre `pipelines/system_tables/specs.py` → `curated_dbx_access_workspaces_latest`, puis créer la vue `dim_dbx_workspace` (inner join filtré avec `dim_reference_landing_zone_dbx_workspace`) + tests | ✅ |

## Requirements & Success Criteria

- **FR-001** : Le système DOIT ingérer `system.access.workspaces_latest` (AWS lecture native + Azure connecteur cross-tenant) dans `curated_dbx_access_workspaces_latest` (`it.ba_data_connect_monitoring__<env>`), via une `IngestionSpec` ajoutée au registre `SPECS` de `pipelines/system_tables/specs.py`, en **full load** (sans watermark, petite table snapshot) avec `merge_keys = (cloud_provider, workspace_id)`.
- **FR-002** : `curated_dbx_access_workspaces_latest` DOIT projeter au minimum les colonnes nécessaires à la vue : `workspace_id`, `workspace_name`, `status`, et `cloud_provider` (colonne discriminante Azure/AWS ajoutée par le socle).
- **FR-003** : Le système DOIT créer une vue `dim_dbx_workspace` = **inner join** entre `curated_dbx_access_workspaces_latest` et `dim_reference_landing_zone_dbx_workspace` sur `workspace_id`, filtrée `subscription_or_account_id IS NOT NULL` **et** `status = 'RUNNING'`, matérialisée via `spark.sql("CREATE OR REPLACE VIEW …")` depuis un **module dédié** (`pipelines/gold_dbx_workspace/`) + task de job ordonnancée après `system_tables` et `reference_lz`.
- **FR-004** : La vue `dim_dbx_workspace` DOIT exposer exactement : `workspace_id` (STRING), `workspace_name` (STRING, depuis `curated_dbx_access_workspaces_latest`), `subscription_or_account_id` (STRING, depuis `dim_reference_landing_zone_dbx_workspace`), `cloud` (STRING, `aws`/`azure`, depuis le référentiel), `updated_at` (TIMESTAMP = `current_timestamp()` évalué à la lecture).
- **FR-005** : La vue DOIT renvoyer une seule ligne par `workspace_id` (pas de doublon issu de la jointure).
- **SC-001** : Après un run, `SELECT workspace_id, COUNT(*) FROM dim_dbx_workspace GROUP BY workspace_id HAVING COUNT(*) > 1` renvoie 0 ligne.
- **SC-002** : `dim_dbx_workspace` ne contient aucune ligne avec `status != 'RUNNING'` ni `subscription_or_account_id` nul (garanti par les filtres de la vue).
- **SC-003** : `curated_dbx_access_workspaces_latest` contient au moins une ligne `cloud_provider='aws'` et une ligne `cloud_provider='azure'` après un run nominal (les deux sources sont non vides en prod) — **non vérifiable en local**, à valider après déploiement dev.

## Assumptions

- `system.access.workspaces_latest` expose bien `workspace_id`, `workspace_name` et `status` (valeur `RUNNING` pour un workspace actif), dans les deux clouds — à confirmer contre le schéma réel au run.
- `cloud` de la vue provient de `dim_reference_landing_zone_dbx_workspace.cloud_provider` (référentiel faisant foi pour le rattachement LZ), aligné avec `cloud_provider` du curated.
- La jointure inner est le comportement voulu : un workspace non référencé dans `dim_reference_landing_zone_dbx_workspace` (ou inversement absent du curated) est volontairement exclu de la dimension.
