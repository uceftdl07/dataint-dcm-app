# Implementation Plan: Marquage des tables supprimées dans le Data Product Usage

**Branch**: `027-usage-table-deleted-flag` | **Date**: 2026-09-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/027-usage-table-deleted-flag/spec.md`

## Summary

Porter l'état de cycle de vie d'une table Unity Catalog (`ACTIVE` / `DELETED` / `UNKNOWN`) dans la couche gold usage, pour que les tables supprimées cessent de polluer les écrans, les prévisions et les recommandations.

Approche technique retenue (détail et alternatives : [research.md](./research.md)) :

- **Détection par corroboration** de deux signaux déjà ingérés : absence de `curated_dbx_uc_tables` (full load avec purge) **et** dernière opération d'audit `deleteTable` dans `curated_dbx_uc_table_operations`. L'absence seule ne suffit pas — elle est majoritairement un défaut de GRANT.
- **Source de vérité unique** : trois colonnes (`lifecycle_state`, `is_deleted`, `deleted_at`) sur `gold_dbx_usage_table_catalog`, table snapshot recalculée intégralement. Le socle de lignes est étendu pour qu'une table supprimée — absente du référentiel — obtienne quand même sa ligne.
- **Aucune dénormalisation** sur les 4 tables de fait quotidiennes : leur écriture MERGE incrémentale (3 jours glissants) figerait le drapeau sur l'historique antérieur. Les consommateurs filtrent par jointure.
- **Exclusion en amont** côté forecast (filtre injecté dans l'historique observé) et côté recommandations (prédicat de détection), ce qui résout automatiquement les recommandations ouvertes préexistantes.

**Découpage décidé** : 027 livre la couche donnée (US1, US3, US4). US2 (filtre API + toggle UI) est implémentée **dans la feature 024**, dont le code applicatif est déjà écrit sur la branche `dataeng/024-usage-tracking-governance` — c'est précisément la pollution de ses résultats par les tables supprimées qui motive cette feature. Le contrat que 024 doit consommer est figé dans [contracts/api-include-deleted.md](./contracts/api-include-deleted.md) (cf. [Dependencies & Sequencing](#dependencies--sequencing)).

## Technical Context

**Language/Version**: Python 3.12 (PySpark sur Databricks) ; TypeScript / React 18 pour la partie contrat UI

**Primary Dependencies**: PySpark + Delta Lake (Unity Catalog), `ai_forecast` (SQL Warehouse Pro/Serverless) ; FastAPI + `DatabricksWarehousePool` côté contrat backend

**Storage**: Tables Delta gold du schéma DCM (`gold_dbx_usage_*`), servies via SQL Warehouse. Aucune table Lakebase PostgreSQL impactée.

**Testing**: pytest (session Spark factice, assertion sur le texte SQL généré — convention de `tests/gold_dbx_usage/`) ; Vitest pour la part frontend portée par 024

**Target Platform**: Job Databricks `job_dcm_gold_dbx_usage.yml` (tâches wheel), multi-cloud Azure + AWS

**Project Type**: Monorepo multi-packages — pipeline (implémenté ici), backend + frontend (contrat seulement)

**Performance Goals**: durée du job gold usage dégradée de ≤ 10 % (SC-007) ; `table_catalog` est déjà un recalcul intégral, l'union ajoutée porte sur un volume marginal (clés supprimées uniquement)

**Constraints**: idempotence du MERGE (P6) ; agrégations en gold uniquement (P12) ; ajout de colonnes rétro-compatible (P14) ; `render_forecast_query` doit rester une fonction pure pour rester testable sans cluster

**Scale/Scope**: registre UC à l'échelle de dizaines de milliers de tables sur 2 clouds ; 4 builders + 1 fichier de specs + 1 entrypoint modifiés, 0 table gold créée

## Constitution Check

*GATE: doit passer avant Phase 0. Re-vérifié après Phase 1.*

Référence : [constitution DCM v1.4.0](spec-kit-dcm-workflow/memory/constitution.md)

| Principe | Verdict | Justification |
|---|---|---|
| **P1** Test-First | ✅ | Chaque cas de détection (`ACTIVE`/`DELETED`/`UNKNOWN`/recréation) et chaque exclusion (forecast, recos) a un test listé dans [quickstart.md](./quickstart.md) §1, écrit avant l'implémentation |
| **P2** Simplicité / YAGNI | ✅ | Aucune table gold créée, aucun job ajouté ; 3 colonnes sur des tables existantes. Alternatives plus lourdes explicitement rejetées (research R3, R8) |
| **P3** Code auto-documenté | ✅ | Noms explicites (`lifecycle_state`, `is_deleted`) ; commentaires réservés au *pourquoi* (corroboration, rémanence du MERGE). Les `column_comments` des specs gold sont un contrat public, pas de la documentation interne |
| **P4** Fail fast | ✅ | Aucun `except` ajouté. Le choix `is_deleted` non-NULL évite précisément l'échec silencieux d'un `WHERE NOT is_deleted` sur NULL |
| **P5** Architecture explicite | ✅ | Un builder = un SELECT idempotent ; dépendances déclarées en paramètres nommés de l'entrypoint, aucun appel cross-LZ |
| **P6** Idempotence | ✅ | Écriture MERGE sur clés inchangées ; la vérification 2.7 du quickstart compare deux runs consécutifs |
| **P7/P8** Secrets | ✅ | Aucun secret manipulé |
| **P9** Pas de fausse donnée | ✅ | Détection entièrement dérivée de tables système réelles ; aucune fixture hors tests |
| **P10** Observabilité | ✅ | Compte de tables `DELETED` par cloud journalisé en structuré (FR-018), sans table de métrique dédiée |
| **P11** Nommage medallion | ✅ | Aucune table créée ni renommée ; préfixes `gold_`/`curated_` respectés |
| **P12** Agrégations en gold | ✅ | Toute la logique de cycle de vie vit en gold ; `curated_dbx_uc_table_operations` conserve `request_params` brut |
| **P13** Raw immuable | ✅ | Couche raw non touchée |
| **P14** Versioning de schéma | ✅ | Ajout de colonnes additif, rétro-compatible → bump mineur. Aucun `MetricPayload` impacté |
| **P15** Stabilité du contrat API | ✅ | 027 ne touche aucun endpoint. `include_deleted` (défaut `false`) est ajouté par 024 **avant sa première mise en production** : aucun consommateur existant n'est cassé, d'où l'intérêt de figer la règle maintenant plutôt qu'en correctif (research R7) |
| **P16** Qualité frontend | ⏸ non applicable ici | Aucun code frontend livré par 027 ; exigences (client central, hook TanStack Query, `app-routes.ts`, Vitest mocké, zéro `any`) inscrites dans [contracts/api-include-deleted.md](./contracts/api-include-deleted.md) à l'attention de 024 |

**Gate Phase 0** : PASS — aucune violation nécessitant justification.

**Gate post-Phase 1** : PASS — la conception n'a introduit ni table, ni job, ni projet supplémentaire. Section Complexity Tracking vide.

## Project Structure

### Documentation (this feature)

```text
specs/027-usage-table-deleted-flag/
├── plan.md                              # Ce fichier
├── spec.md
├── research.md                          # Phase 0 — 8 décisions, alternatives, risques
├── data-model.md                        # Phase 1 — colonnes, dérivation, transitions
├── quickstart.md                        # Phase 1 — validation unitaire + SQL de contrôle
├── contracts/
│   ├── gold-lifecycle-contract.md       # Contrat des colonnes gold (consommé par 024)
│   └── api-include-deleted.md           # Contrat API/UI figé, porté par 024
├── checklists/
│   └── requirements.md
└── tasks.md                             # Phase 2 — produit par /speckit.tasks
```

### Source Code (repository root)

```text
packages/dcm-databricks-pipeline/
├── pipelines/gold_dbx_usage/
│   ├── specs.py                         # + colonnes dans TABLE_CATALOG_COLUMN_COMMENTS
│   │                                    #   et TABLE_GOVERNANCE_COLUMN_COMMENTS
│   ├── table_catalog.py                 # socle base ∪ deleted_only, dérivation lifecycle_state
│   ├── table_governance.py              # propagation + neutralisation action/severity
│   ├── forecast_daily.py                # exclusion dans l'historique observé (+ param catalog)
│   ├── recommendations.py               # AND NOT is_deleted sur les règles DATA_PRODUCT
│   └── entrypoint.py                    # passage de table_catalog_table à write_usage_forecast
└── tests/gold_dbx_usage/
    ├── test_table_catalog.py            # 5 cas de détection
    ├── test_table_governance.py         # propagation + non-régression
    ├── test_forecast_daily.py           # exclusion en entrée + fenêtre de purge d'horizon
    ├── test_recommendations.py          # non-détection + transition RESOLVED
    └── test_specs.py                    # commentaires de colonnes

packages/dcm-backend/    # aucun changement dans 027 — porté par la branche 024
packages/dcm-frontend/   # aucun changement dans 027 — porté par la branche 024
```

**Structure Decision**: Monorepo existant, un seul package touché (`dcm-databricks-pipeline`). Aucun répertoire créé. La feature étend la couche gold usage livrée par la feature 019 et suit sa convention « un builder = un module = un fichier de test ».

## Dependencies & Sequencing

| Dépendance | État | Impact |
|---|---|---|
| Feature 019 — tables `gold_dbx_usage_*` | ✅ livrée sur `develop` | Socle de la feature |
| Feature 020 — purge des curated full-load (`purge_eligible` sur `curated_dbx_uc_tables`) | ✅ livrée sur `develop` | **Prérequis dur** : sans purge, l'absence du référentiel n'est plus un signal et la détection tombe |
| Feature 024 — 21 endpoints `/api/v1/uc-usage/*` + pages `UsageTablesUc` / `UsageGovernance` | 🟡 écrite sur `dataeng/024-usage-tracking-governance`, **non mergée** sur `develop` | Consomme le champ livré par 027 ; porte l'implémentation d'US2 |

### Répartition du travail

| User story | Porteur | Livrable |
|---|---|---|
| US1 — signal de suppression en gold (P1) | **027** | 3 colonnes sur `table_catalog` + propagation `table_governance` |
| US3 — exclusion du forecast (P2) | **027** | filtre en entrée de `forecast_daily` |
| US4 — exclusion gouvernance / recommandations (P2) | **027** | prédicat `NOT is_deleted` sur les règles `DATA_PRODUCT` |
| US2 — filtre API + toggle UI (P1) | **024** | `include_deleted` + champs de réponse, selon [contracts/api-include-deleted.md](./contracts/api-include-deleted.md) |

### Séquencement

1. 027 livre la couche gold sur `develop` (branche `dataeng/027-usage-table-deleted-flag`).
2. La branche 024 se resynchronise (`git merge origin/develop`) et récupère la colonne.
3. 024 ajoute `include_deleted` à ses endpoints et le toggle à ses deux pages, avant sa PR.

L'ordre est contraint : 024 ne peut filtrer sur `is_deleted` qu'une fois la colonne présente en gold. Le point d'accroche existe déjà — les services 024 importent `GOLD_TABLE_CATALOG` (`app/api/services/uc_usage_common.py`), donc la jointure de filtrage se greffe sur une table qu'ils lisent déjà.

Greffer `include_deleted` sur la route héritée `/api/v1/data-product-usage` a été écarté : elle lit `gold_data_product_usage`, table que le pipeline ne produit plus (research R7).

## Complexity Tracking

> Aucune violation de la Constitution Check à justifier. Section laissée vide intentionnellement.
