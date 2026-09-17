# Feature Specification: Usage Data Product — couche curated + gold

**Feature Branch**: `019-usage-data-product-gold`
**Work Type**: feature
**Priority**: P2
**Created**: 2026-09-01

**Input**: Mettre en place la couche curated + gold du domaine Usage Data Product (adoption, consommateurs, fraîcheur, coût FinOps, gouvernance/cycle de vie) à partir des system tables Databricks (`access.audit`, `access.table_lineage`, `query.history`, `billing.usage`, `information_schema`), en remplacement de l'ancienne table `gold_data_product_usage`. Basé sur le spike `docs/spike/usage-data-product-definition/` (`usage_page.md`, `usage_datamodel.md`, `usage_datamapping.md`).

## Clarifications

### Session 2026-09-01

- Q: Seuil "data product inutilisé" (`is_unused`) — `days_since_last_read > N` ? → A: N = 90 jours (défaut spike confirmé).
- Q: Seuil "data product critique" (`is_critical`) — `downstream_fanout ≥ seuil` ? → A: seuil = 5 (défaut spike confirmé).
- Q: Règle d'attribution du coût d'une requête multi-data-products (FR-010) ? → A: pondéré par `read_bytes` par table (plus précis que le défaut "parts égales" du spike — **écart assumé vs spike**, cf. Assumptions).
- Q: Seuil de fraîcheur SLA (`is_stale_but_consumed` = `freshness_lag_hours > SLA`) ? → A: SLA = 24h.
- Q: Rétention de l'historique des tables gold `*_daily` ? → A: illimitée (pas de purge), cohérent avec le reste de DCM.

## Domain Scope

| Domaine | In scope | Ticket Story | Packages |
|---------|----------|--------------|----------|
| Frontend | ❌ | ❌ | — |
| Backend | ❌ | ❌ | — |
| DataEng | ✅ | ✅ | `packages/dcm-databricks-pipeline` |
| DevOps | ❌ | ❌ | — |
| QA | ❌ | ❌ | — |

## Ticket Plan

| Stories Jira | 4 |
| Mode | single_domain (dataeng) |
| Domaines avec ticket | dataeng |

| Ticket (preview) | Titre |
|---|---|
| T001 | Curated : registre UC (`curated_dbx_uc_tables`, `curated_dbx_uc_table_tags`, `curated_dbx_uc_table_operations`) |
| T002 | Gold fait usage : `gold_dbx_usage_table_daily`, `gold_dbx_usage_table_popularity_daily`, `gold_dbx_usage_consumer_daily`, `gold_dbx_usage_table_query_performance_daily` |
| T003 | Gold registre/état : `gold_dbx_usage_table_catalog`, `gold_dbx_usage_table_governance` (`gold_dbx_usage_dim_workspace` initialement prévue puis **retirée**, cf. Dependency Analysis) |
| T004 | Gold transverse : `gold_dbx_usage_recommendations`, `gold_dbx_usage_forecast_daily` |

## Dependency Analysis

| Besoin | Domaine | Résolution |
|---|---|---|
| Route backend `packages/dcm-backend/app/api/routes/data_product_usage.py` consomme l'ancienne table `gold_data_product_usage` (colonnes `data_product_id`/`data_product_name`/`subscription_or_account_id`) | Backend | **Hors scope de cette epic** (dataeng seul, cf. Q6 intake). La bascule vers `gold_dbx_usage_table_daily` (colonnes renommées `catalog`/`schema`/`table_name`, `subscription_or_account_id` retiré) casse la compat de cette route : à traiter dans une **epic backend future séparée** (renommage `_GOLD_TABLE` + adaptation mapping colonnes). Documenté comme dette assumée, non bloquant pour livrer le socle data. |
| Curated déjà ingérées (`curated_dbx_access_table_lineage`, `curated_dbx_access_audit`, `curated_dbx_query_history`, `curated_dbx_billing_usage`, `curated_dbx_billing_list_prices`) | DataEng | Aucune action — déjà déclarées dans `system_tables/specs.py` (cf. spike §1.1), réutilisées telles quelles. |
| Action `access.audit` filter (`ACCESS_AUDIT_ACTIONS`) à étendre aux actions d'écriture pour T001 (`curated_dbx_uc_table_operations`) | DataEng | Extension du filtre existant dans `system_tables/specs.py`, calée sur les valeurs réelles observées au gate (pas d'invention, cf. spike §1.2). |
| ~~`[NEEDS DECISION PO]` rapprochement `gold_dbx_usage_dim_workspace` avec `dim_landing_zone` existant vs LZ = workspace (cf. spike datamapping §2.4bis)~~ **RÉSOLU (2026-09-04)** | DataEng | `gold_dbx_usage_dim_workspace` **retirée du périmètre T003** : la spec 020 (livrée en parallèle) a produit `dim_dbx_workspace` (`pipelines.gold_dbx_workspace`), une résolution `workspace_id → LZ` fiable via un vrai référentiel (`dim_reference_landing_zone_dbx_workspace`, filtre `status=RUNNING`), déjà consommée par `dim_landing_zone`. Le fallback tags (`dcm_lz_id`/`Project`) de `gold_dbx_usage_dim_workspace` était redondant et moins fiable — jamais déployée en dev (0 ligne), suppression sans impact données. FR-008 s'applique désormais **sans exception** : aucune table gold usage ne porte `source_lz_id`/`subscription_or_account_id`. |

## Prerequisites

- **Small branches / small PRs** : chaque ticket (`dataeng/019-...-tXXX`) touche un sous-ensemble focalisé de `packages/dcm-databricks-pipeline` (soit `system_tables/specs.py` pour T001, soit un module `gold_dbx_usage/` dédié par ticket T002-T004) — un seul package concerné au total, mais fichiers découpés par couche/objet pour limiter la taille de chaque PR.
- Spec intake + domain scope confirmés (`intake.json` / `domain-scope.json`) — fait.
- T001 doit être mergé (ou au moins ses `IngestionSpec` disponibles) avant que T002/T003 ne puissent lire `curated_dbx_uc_tables`/`curated_dbx_uc_table_tags`/`curated_dbx_uc_table_operations` en gold — dépendance d'ordre **T001 → {T002, T003}**. T004 dépend de T002 (popularity_daily, consumer_daily) et T003 (catalog, governance).
- Gate de validation obligatoire avant merge T001 : mapping réel `action_name → operation` de `system.access.audit` vérifié en environnement (pas de valeurs inventées, cf. spike datamodel §1.2 note et datamapping §1.4).
- Pas de `[NEEDS CLARIFICATION]` bloquant identifié dans le spike (documents déjà très détaillés) — le point `[NEEDS DECISION PO]` ci-dessus est non bloquant et documenté comme tel.

## User Scenarios & Testing

### User Story 1 - Ingestion du registre Unity Catalog (T001) (Priority: P1)

En tant que pipeline DCM, je dois disposer d'un registre des tables Unity Catalog (métadonnées + tags + historique d'opérations) pour pouvoir qualifier ce qu'est un « data product » et calculer sa fraîcheur qualifiée en aval.

**Why this priority**: Bloquant — tous les autres tickets (T002-T004) dépendent de ce registre pour résoudre `(catalog, schema, table_name)`, les tags de gouvernance et le type de dernière opération.

**Independent Test**: Lancer l'ingestion `system_tables` avec les 3 nouvelles `IngestionSpec` (`curated_dbx_uc_tables`, `curated_dbx_uc_table_tags`, `curated_dbx_uc_table_operations`) sur un environnement dev ; vérifier que les 3 tables curated existent, sont peuplées (full load référentiel + watermark `event_time` pour operations), et que le grain/clé de merge documenté est respecté (pas de doublon).

**Acceptance Scenarios**:

1. **Given** le workspace Azure et AWS exposent `system.information_schema.tables`, **When** le job `dcm_system_tables` tourne, **Then** `curated_dbx_uc_tables` contient une ligne par `(cloud_provider, table_catalog, table_schema, table_name)`, fidèle source (P12 — pas de transform en curated) ; `table_full_name` (`concat_ws('.', ...)`) est calculé en aval, dans `gold_dbx_usage_table_catalog` (T003), pas en curated (déviation documentée, cf. `stories/T001-curated-uc-registry.md` §Notes).
2. **Given** des tags UC posés sur une table (`data_product`, `owner`, `domain`, `cost_center`), **When** le job tourne, **Then** `curated_dbx_uc_table_tags` contient une ligne par `(cloud_provider, catalog_name, schema_name, table_name, tag_name)`.
3. **Given** des opérations d'écriture UC (`createTable`, `mergeIntoTable`, `optimize`, ...) dans `system.access.audit`, **When** le job tourne, **Then** `curated_dbx_uc_table_operations` contient une ligne par `event_id` avec `action_name` brut (fidèle source) ; la normalisation en `operation` selon le mapping documenté (spike datamapping §1.4) est calculée en aval, dans `gold_dbx_usage_table_catalog` (T003), sans valeur inventée pour les actions non mappées.

---

### User Story 2 - Fait de consommation et agrégats popularité/consommateur (T002) (Priority: P1)

En tant que Data Product Owner / FinOps, je veux voir qui consomme quel data product, à quelle fréquence, pour quel volume et à quel coût, agrégé par jour.

**Why this priority**: Cœur métier de la feature — sans le fait de consommation, aucune des pages usage (popularité, consommateurs, coût) n'est calculable. Remplace directement `gold_data_product_usage`.

**Independent Test**: Sur un environnement dev avec des lectures réelles (`table_lineage` + `query.history` + `billing.usage`) sur au moins un data product connu, exécuter le calcul gold et vérifier que `gold_dbx_usage_table_daily` contient une ligne par `(cloud_provider, catalog, schema, table_name, consumer_id, period_start)` cohérente avec le nombre d'accès observés sur `table_lineage`.

**Acceptance Scenarios**:

1. **Given** des lectures de data product tracées dans `curated_dbx_access_table_lineage` (DP en `source_table_full_name`), **When** le calcul gold journalier tourne, **Then** `gold_dbx_usage_table_daily` agrège `request_count`, `rows_read`, `data_read_bytes`, `estimated_cost_usd` par consommateur et par jour, avec `usage_date` = alias de `period_start`.
2. **Given** `gold_dbx_usage_table_daily` peuplé sur plusieurs jours, **When** `gold_dbx_usage_table_popularity_daily` est recalculé, **Then** il expose `popularity_rank` (via `RANK() OVER (PARTITION BY period_start ORDER BY request_count DESC)`) et `request_delta_pct` (vs J-1).
3. **Given** une requête `query.history` qui échoue (`FAILED`/`CANCELED`) sur un data product, **When** `gold_dbx_usage_table_query_performance_daily` est calculé, **Then** `failure_rate_pct` reflète le taux d'échec réel et `latency_p50_ms`/`latency_p95_ms` sont calculés via `percentile_approx`.
4. **Given** un consommateur lisant plusieurs data products le même jour, **When** `gold_dbx_usage_consumer_daily` est calculé, **Then** `distinct_data_products` = `COUNT(DISTINCT (catalog, schema, table_name))` et `consumer_rank` classe par `estimated_cost_usd` décroissant.

---

### User Story 3 - Registre / état courant et gouvernance (T003) (Priority: P2)

En tant que Data Engineer / Gouvernance, je veux voir l'état courant de chaque data product (fraîcheur, dernière opération, tags de gouvernance) et un snapshot de cycle de vie (inutilisé, orphelin, critique).

**Why this priority**: Nécessaire pour les reco de gouvernance (T004) mais peut être livré après le fait de consommation (T002) — moins urgent que la mesure d'usage brute.

**Independent Test**: Sur un environnement dev, vérifier que `gold_dbx_usage_table_catalog` expose `last_write_at`/`last_operation`/`last_read_at`/`freshness_lag_hours` cohérents pour un data product connu, et que `gold_dbx_usage_table_governance` calcule correctement `is_unused`/`is_orphan`/`is_critical` sur ce même data product.

**Acceptance Scenarios**:

1. **Given** `curated_dbx_uc_tables` + `curated_dbx_uc_table_tags` + `curated_dbx_uc_table_operations` peuplés (T001), **When** `gold_dbx_usage_table_catalog` est calculé, **Then** chaque data product a `last_operation` = `MAX_BY(action_name, event_time)` (valeur brute `createTable`/`deleteTable`/`updateTables`, cf. `ACCESS_AUDIT_WRITE_ACTIONS`) et `freshness_lag_hours` = écart `now - last_write_at`.
2. **Given** `gold_dbx_usage_table_catalog` peuplé, **When** `gold_dbx_usage_table_governance` est calculé, **Then** `is_unused` = vrai si `days_since_last_read IS NULL` (jamais lu) `OR days_since_last_read > 90`, `is_orphan` = vrai si aucun tag owner/domain/cost_center, `is_critical` = vrai si `downstream_fanout ≥ 5`, `is_stale_but_consumed` = vrai si `freshness_lag_hours > 24 AND days_since_last_read < 7`.
3. ~~**Given** aucune résolution `workspace_id → LZ` fiable disponible nativement, **When** `gold_dbx_usage_dim_workspace` est calculé...~~ **Retiré (2026-09-04)** : `gold_dbx_usage_dim_workspace` a été supprimée du périmètre T003 — la résolution `workspace_id → LZ` est couverte par `dim_dbx_workspace` (spec 020), déjà jointe par `dim_landing_zone`, sans avoir besoin d'un fallback tags dédié dans ce domaine (cf. Dependency Analysis).

---

### User Story 4 - Reco actionnables et prédictif (T004) (Priority: P3)

En tant que Data Product Owner / FinOps, je veux une liste unifiée de recommandations d'action (dépréciation, fraîcheur, gouvernance, coût) et une projection de tendance (adoption, coût, volume).

**Why this priority**: Valeur ajoutée transverse, dépend de T002+T003 déjà livrés — peut suivre en dernier sans bloquer l'exposition des métriques de base.

**Independent Test**: Sur un environnement dev avec au moins un data product répondant à une règle de reco (ex. `is_unused=true`), vérifier qu'une ligne apparaît dans `gold_dbx_usage_recommendations` avec la bonne `category`/`severity`. Vérifier que `gold_dbx_usage_forecast_daily` produit une projection `ai_forecast` sur au moins une métrique historisée.

**Acceptance Scenarios**:

1. **Given** un data product avec `governance.is_unused=true AND is_critical=false`, **When** les règles de reco tournent, **Then** une ligne `gold_dbx_usage_recommendations` est créée/mise à jour avec `category=LIFECYCLE`, `severity=MEDIUM`, `recommendation_id` stable (hash), `first_seen_date` préservé et `last_seen_date` mis à jour (pas de doublon).
2. **Given** un historique `gold_dbx_usage_table_popularity_daily` sur plusieurs semaines, **When** le job `ai_forecast` tourne, **Then** `gold_dbx_usage_forecast_daily` projette `request_count`/`distinct_consumers`/`estimated_cost_usd`/`data_read_bytes` avec bornes basse/haute par `horizon_date`.

---

## Out of scope (this Epic)

- **Backend** : adaptation de la route `data_product_usage.py` vers `gold_dbx_usage_table_daily` (cf. Dependency Analysis) — epic future.
- **Frontend** : consommation UI des nouvelles pages Data Products / Consommateurs (`usage_page.md` §Page 1/Page 2) — epic future, dépend de l'epic backend ci-dessus.
- **Option hors MVP explicitement notée dans le spike** : `system.access.column_lineage` (usage au grain colonne), `information_schema.table_privileges` (droits accordés vs accès réels).

## Work Breakdown (preview)

| ID | Domain | Summary | Ticket |
|----|--------|---------|--------|
| T001 | DataEng | Curated : registre UC (uc_tables, uc_table_tags, uc_table_operations) | ✅ |
| T002 | DataEng | Gold fait usage + popularité + consommateur + perf requêtes | ✅ |
| T003 | DataEng | Gold registre/état (catalog, governance ; `dim_workspace` retirée, cf. Dependency Analysis) | ✅ |
| T004 | DataEng | Gold transverse (recommendations, forecast_daily) | ✅ |
| — | Backend | Adaptation route `data_product_usage.py` vers `gold_dbx_usage_table_daily` | ❌ hors Epic |
| — | Frontend | Pages Data Products / Consommateurs | ❌ hors Epic |

## Requirements

### Functional Requirements

- **FR-001**: Le système DOIT ingérer 3 nouvelles system tables (`information_schema.tables`, `information_schema.table_tags`, `access.audit` filtré actions d'écriture) en curated, sans transformation (fidèle source), avec `cloud_provider` dans chaque clé de merge (mutualisation Azure/AWS).
- **FR-002**: Le système DOIT produire un fait de consommation gold (`gold_dbx_usage_table_daily`) au grain `(cloud_provider, catalog, schema, table_name, consumer_id, period_start)`, agrégeant lectures/volumes/coût/erreurs.
- **FR-003**: Le système DOIT dériver des agrégats par data product (`popularity_daily`, `query_performance_daily`) et par consommateur (`consumer_daily`) depuis le fait de consommation.
- **FR-004**: Le système DOIT maintenir un registre d'état courant par data product (`gold_dbx_usage_table_catalog`) exposant fraîcheur, dernière opération qualifiée (type d'opération, pas seulement horodatage) et tags de gouvernance.
- **FR-005**: Le système DOIT calculer un snapshot de gouvernance/cycle de vie (`gold_dbx_usage_table_governance`) avec des règles explicites (`is_unused`, `is_orphan`, `is_stale_but_consumed`, `is_critical`).
- **FR-006**: Le système DOIT centraliser les recommandations d'action dans `gold_dbx_usage_recommendations` avec une clé stable (`recommendation_id` = hash), sans doublon, en préservant `first_seen_date`.
- **FR-007**: Le système DOIT produire des projections prédictives (`gold_dbx_usage_forecast_daily`) via `ai_forecast` sur l'historique gold journalier, pour les métriques marquées `P`/`R+P` dans le spike.
- **FR-008**: Le système NE DOIT PAS exposer `source_lz_id` ni `subscription_or_account_id` dans les tables gold usage (`*_daily`, `*_catalog`, `*_governance`, `recommendations`, `forecast_daily`) — sans exception (la table `gold_dbx_usage_dim_workspace`, initialement prévue comme seule exception documentée, a été retirée du périmètre T003 ; la résolution `workspace_id → LZ` vit désormais uniquement dans `dim_dbx_workspace`, spec 020, cf. Dependency Analysis).
- **FR-009**: Toute donnée non disponible en source DOIT rester `NULL` (jamais `0` ni inventée) — notamment le mapping `action_name → operation` non couvert par les valeurs observées au gate.
- **FR-010**: L'attribution du coût d'une requête multi-data-products DOIT être **pondérée par `read_bytes` par table** (part proportionnelle au volume lu de chaque data product dans la requête, cf. Clarifications), avec contrôle de réconciliation `SUM(parts) = coût requête`. **Écart assumé vs défaut du spike** (qui proposait des parts égales) — la pondération par `read_bytes` nécessite que le lineage colonne/table de la requête expose `read_bytes` par table source ; à défaut de cette donnée pour une requête donnée, repli sur parts égales pour cette requête uniquement (documenté, pas une valeur inventée).

## Success Criteria

- **SC-001**: Les 3 nouvelles tables curated (T001) sont peuplées en environnement dev sans erreur de schéma, avec 0 doublon sur la clé de merge documentée.
- **SC-002**: `gold_dbx_usage_table_daily` (T002) reproduit fonctionnellement le périmètre de l'ancienne `gold_data_product_usage` (mêmes métriques de service, colonnes renommées) sur un jeu de données de test.
- **SC-003**: `gold_dbx_usage_table_catalog` (T003) résout `last_operation` pour au moins 95 % des data products ayant eu une opération d'écriture observable dans la fenêtre de test (le reste documenté comme `NULL` légitime, pas un bug).
- **SC-004**: Au moins une recommandation de chaque catégorie (`LIFECYCLE`, `FRESHNESS`, `GOVERNANCE`, `RELIABILITY`, `FINOPS`) est générée sur un jeu de données de test couvrant les règles du spike (T004).
- **SC-005**: Suites de tests pytest/chispa vertes pour les 4 tickets, ruff/mypy sans nouvelle violation vs baseline.

## Assumptions

- Les system tables `access.audit`, `access.table_lineage`, `query.history`, `billing.usage`, `billing.list_prices` sont déjà accessibles en lecture (Azure via SP Entra + AWS natif) — infrastructure posée par l'epic 010.
- Le registre "data product" (`is_data_product`) se limite au MVP à la présence du tag `data_product` OU l'appartenance à un schéma/catalogue publié — pas de déclaratif supplémentaire.
- Seuils numériques confirmés en clarification : `days_since_last_read > 90` (inutilisé), `downstream_fanout ≥ 5` (critique), `freshness_lag_hours > 24` (SLA fraîcheur/stale-but-consumed).
- Rétention illimitée sur les tables gold `*_daily` (pas de purge programmée dans cette epic).
- Le mapping `action_name → operation` sera calé sur les valeurs réellement observées en gate de validation dev, pas sur une liste théorique exhaustive.
- Pas de nouveau secret/scope requis — réutilise l'authentification Azure SP existante (`dcm-secret-scope`).
