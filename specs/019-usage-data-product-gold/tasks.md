# Tasks: Usage Data Product — couche curated + gold

**Input**: Design documents from `/specs/019-usage-data-product-gold/` (plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md)

**Tests**: Pytest/chispa requis par ticket (P1 constitution, non-négociable) — chaque tâche inclut ses tests miroir.

**Organization**: DCM dispatch mode = **granular au sein d'un seul domaine (DataEng)**, conforme à `intake.json.ticket_plan` (4 Stories, 1 task = 1 Jira Story = 1 branche = 1 sub-spec). Chaque tâche correspond 1:1 à une User Story de [spec.md](./spec.md). Pattern identique à l'epic précédente `012-compute-metrics-ingestion`.

## Format: `[ID] [P?] DataEng Description → sub-spec`

- **[P]**: parallélisable (fichiers différents, pas de dépendance) — aucun ici : T001 bloque {T002,T003}, qui bloquent T004 (registre partagé, cf. Dependencies).
- Toutes les tâches sont **DataEng**, package `packages/dcm-databricks-pipeline`.

## Tasks

- [X] T001 DataEng Curated : registre UC (uc_tables, uc_table_tags, uc_table_operations) → [stories/T001-curated-uc-registry.md](stories/T001-curated-uc-registry.md) · [DCINT-289](https://tdf.atlassian.net/browse/DCINT-289)
- [x] T002 DataEng Gold fait usage — table_daily, popularity_daily, consumer_daily, query_performance_daily → [stories/T002-gold-usage-fact.md](stories/T002-gold-usage-fact.md) · [DCINT-290](https://tdf.atlassian.net/browse/DCINT-290)
- [~] T003 DataEng Gold registre/état — table_catalog, table_governance (`dim_workspace` retirée, cf. stories/T003) → [stories/T003-gold-usage-catalog-governance.md](stories/T003-gold-usage-catalog-governance.md) · [DCINT-291](https://tdf.atlassian.net/browse/DCINT-291)
- [x] T004 DataEng Gold transverse — recommendations, forecast_daily → [stories/T004-gold-usage-transverse.md](stories/T004-gold-usage-transverse.md) · [DCINT-292](https://tdf.atlassian.net/browse/DCINT-292)

## Dependencies & Execution Order

- **T001** — pas de dépendance. Étend le registre existant `pipelines/system_tables/specs.py` (+3 `IngestionSpec`, aucune nouvelle mécanique). Bloque T002 et T003 (qui lisent `curated_dbx_uc_tables`/`curated_dbx_uc_table_tags`/`curated_dbx_uc_table_operations`).
- **T002** — dépend de T001. Crée le **nouveau** scaffolding `pipelines/gold_dbx_usage/` (`__init__.py`, `specs.py` registre, `entrypoint.py`, `resources/job_dcm_gold_dbx_usage.yml`) en même temps que le fait de consommation. T003 et T004 étendent ce scaffolding plutôt que de le recréer.
- **T003** — dépend de T001 et T002 (réutilise le scaffolding créé par T002 : `specs.py`, `entrypoint.py`, job resource ; `table_catalog` lit aussi `table_daily` de T002 pour `last_read_at`). Non parallèle-safe avec T002 sur ces fichiers partagés (cf. `merge-strategy.md`), même si `table_catalog.py`/`table_governance.py` sont des fichiers métier indépendants. `dim_workspace.py` livré puis **retiré** (redondant avec `dim_dbx_workspace`, spec 020, cf. stories/T003).
- **T004** — dépend de T002 et T003 (lit `table_governance`/`table_catalog`/`table_popularity_daily`/`table_query_performance_daily`/`consumer_daily` pour les recommandations ; lit `table_popularity_daily`/`consumer_daily` pour le forecast). `recommendations.py` et `forecast_daily.py` sont indépendants l'un de l'autre (pas de lecture croisée) — peuvent être livrés dans le même ticket sans ordre interne strict.

Ordre de merge recommandé : **T001 → T002 → T003 → T004** (PRs séquentielles vers `develop`, cf. `merge-strategy.md`).

## Implementation Strategy

### MVP First (Story 1 + Story 2)

1. T001 — socle curated étendu (bloquant).
2. T002 — première tranche gold (fait de consommation + agrégats) livre une valeur autonome (popularité, coût par consommateur) — checkpoint MVP naturel, remplace fonctionnellement `gold_data_product_usage`.
3. **STOP et VALIDER** : exécuter `quickstart.md` §T001-T002, confirmer SC-001/SC-002.

### Incremental Delivery

4. T003 — registre/état + gouvernance (dépend de T001+T002, valide SC-003).
5. T004 — transverse réactif + prédictif (dépend de T002+T003, valide SC-004).

Chaque ticket est mergeable indépendamment vers `develop` une fois ses tests verts et sa gate (le cas échéant) validée — pas de big-bang, cohérent avec P2 (Simplicité/Versioning) et les petites PR (cf. spec Prerequisites).
