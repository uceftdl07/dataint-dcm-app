# Implementation Plan: Page « Serverless compute » + correctifs des pages compute existantes

**Branch**: `dataeng/025-…` → `backend/025-…` → `frontend/025-…` | **Date**: 2026-09-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/025-serverless-compute-page/spec.md`
· Spike : [docs/spike/serverless-compute-page/proposition.md](../../docs/spike/serverless-compute-page/proposition.md)
(révision 2026-09-10 — §0 « Errata » liste 9 corrections ; **seules les valeurs corrigées
font foi**, une valeur reprise d'une v1 antérieure est une erreur de lecture).

**Réf. socle réutilisé** — tous lus avant rédaction :

- [`pipelines/gold_dbx_compute/pipeline_cost_daily.py`](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/pipeline_cost_daily.py)
  — **modèle de référence** de tout ce lot : lecture **billing-direct** de
  `curated_dbx_billing_usage`, discriminant de compute **dans le grain**, jointure prix
  `(cloud_provider, sku_name, price_start_time <= period_start < price_end_time)`, tampon
  d'un jour (`lag_lookback_lower_bound`) pour que le self-join J-1 voie le bord de fenêtre,
  self-join **égalisé sur le discriminant**, `RANK() OVER (PARTITION BY period_start,
  compute_kind ...)`, et une docstring qui explique *pourquoi* les clés de merge ne sont
  jamais NULL. `serverless_cost_daily` en est la transposition à 11 surfaces.
- [`pipelines/gold_dbx_compute/job_cluster_cost_daily.py`](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/job_cluster_cost_daily.py)
  — **la table à retourner** : c'est aujourd'hui un rollup de `cluster_cost_daily`
  (`WHERE cc.cluster_type = 'JOB'`, l. 164) avec un `INNER JOIN` sur la CTE `job_clusters`
  issue de `curated_dbx_lakeflow_job_task_run_timeline`. Elle hérite donc du filtre
  `usage_metadata.cluster_id IS NOT NULL` de `cluster_cost_daily` et **exclut
  structurellement** les 60 021 $/30 j de job serverless. T2 la refait en billing-direct sur
  le modèle ci-dessus.
- [`pipelines/gold_dbx_compute/warehouse_utilization_daily.py`](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/warehouse_utilization_daily.py)
  — l. 440-562 : le `SELECT` final émet `idle_pct`, `active_to_running_ratio`,
  `utilization_status` (`CASE WHEN idle_pct > {idle_pct_over_threshold} THEN 'OVER' …`),
  `rightsizing_reco` et `estimated_savings_usd` (`cost_usd * idle_pct / 100`). **Point
  d'application exact de T1.** La CTE `with_metrics` calcule
  `idle_pct = (running_hours - active_query_hours) / NULLIF(running_hours, 0) * 100`.
- [`pipelines/gold_dbx_compute/cluster_cost_daily.py`](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_cost_daily.py)
  — l. 137 et 192 : `sku_group` dérivé de `u.sku_name LIKE '%SERVERLESS%'` sur une table dont
  le filtre d'entrée est `cluster_id IS NOT NULL`. Contresens de T3.
- [`pipelines/gold_dbx_compute/sql_helpers.py`](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/sql_helpers.py)
  — `histogram_from_edges_sql` (l. 193), `sum_histograms_sql` (l. 211),
  `percentile_from_histogram_sql` (l. 226), `histogram_bucket_count`,
  `histogram_representatives`, `HISTOGRAM_UTILIZATION_EDGES`, `HISTOGRAM_LATENCY_MS_EDGES`
  (l. 156, modèle de bornes par doublement), `rolling_windows_array_sql`,
  `lower_bound_predicate`, `compute_kind_case_expr` (l. 115). **Point d'ajout** de
  `HISTOGRAM_COST_PER_RUN_EDGES` et de `serverless_surface_case_expr` /
  `serverless_object_id_expr` / `identity_principal_expr`.
- [`pipelines/gold_dbx_compute/specs.py`](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/specs.py)
  — `GoldAggregationSpec` (`source_tables`, `target_table`, `merge_keys`,
  `watermark_column`, `initial_mode`, `incremental_lookback_days`, `column_comments`,
  `table_comment`), `ROLLING_WINDOWS = (1, 7, 30, 90)` (l. 240),
  `TOP_COST_RANK_THRESHOLD = 10` (l. 232), `WAREHOUSE_IDLE_PCT_OVER_THRESHOLD = 60.0`
  (l. 1936), `GOLD_WAREHOUSE_UTILIZATION_DAILY` (l. 1915), registre `GOLD_SPECS` en fin de
  fichier. **Jamais modifier une entrée existante autrement qu'en ajoutant** (cf.
  merge-strategy 012).
- [`pipelines/system_tables/specs.py`](../../packages/dcm-databricks-pipeline/pipelines/system_tables/specs.py)
  — `BILLING_USAGE_SPEC` **sans `select_columns`** (donc `SELECT *`) : c'est ce qui rend
  `product_features`, `identity_metadata`, `usage_metadata` et `billing_origin_product`
  disponibles en curated **sans aucune ingestion nouvelle** (vérifié en dev le 2026-09-10,
  20 colonnes). Modèle `IngestionSpec` pour T7.
- [`app/api/routes/compute_metrics.py`](../../packages/dcm-backend/app/api/routes/compute_metrics.py)
  — **29 routes `@router.get`**, zéro POST/PUT/DELETE, **zéro `response_model=`** (tous les
  handlers renvoient `dict[str, Any]`). `router = APIRouter()` sans préfixe (l. 92), monté
  dans [`app/main.py`](../../packages/dcm-backend/app/main.py) l. 214-218 sur
  `/api/v1/databricks/compute`, tag `compute-metrics`. Docstring du module (l. 3-33) =
  **liste des routes tenue à la main**, à étendre. Alias de paramètres partagés l. 99-154,
  `_common_scope_kwargs` l. 180-212.
- [`app/api/services/compute_metrics_common.py`](../../packages/dcm-backend/app/api/services/compute_metrics_common.py)
  — `RollingWindowDays` (IntEnum 1/7/30/90, l. 55-71), `_clamp_page`
  (`_DEFAULT_PAGE_SIZE = 25`, `_MAX_PAGE_SIZE = 200`), `_scope_where` / `_window_where` /
  `_empty_page`. Socle des nouveaux services.
- [`app/api/services/compute_metrics_warehouses.py`](../../packages/dcm-backend/app/api/services/compute_metrics_warehouses.py)
  — **modèle** d'un service compute branché sur une famille `*_rolling` dédiée, et **lieu du
  correctif** de neutralisation côté réponses.
- [`app/api/services/compute_metrics_pipelines.py`](../../packages/dcm-backend/app/api/services/compute_metrics_pipelines.py)
  — l. 87 `_CLASSIC_ONLY = "compute_kind = 'CLASSIC'"`, appliqué au **scope** et non au
  filtre de ligne (l. 73-86 expliquent pourquoi : sinon les cartes affichent 23 588 $
  au-dessus d'une liste qui totalise 1 903 $). Précédent exact de la façon dont un
  discriminant de compute se propage dans un service.
- [`app/api/services/compute_metrics_filters.py`](../../packages/dcm-backend/app/api/services/compute_metrics_filters.py)
  — `FILTERABLE_COLUMNS` l. 831-842 (11 vues) : une page neuve **doit** y ajouter ses vues
  pour obtenir les entonnoirs de colonne. `ColumnFilterError` → 422 global
  ([`app/main.py`](../../packages/dcm-backend/app/main.py) l. 151-165).
- [`dcm_commons/schemas/compute_metrics.py`](../../packages/dcm-commons/dcm_commons/schemas/compute_metrics.py)
  — ~590 lignes, convention `<Grain><Vue>Item` / `<Grain>OverviewKpis` / `<Grain>…Response`
  **sans préfixe `Compute`** ; `PipelineCostItem.compute_kind` (l. 417) est le précédent
  d'un champ de discriminant. À noter : **rien dans `dcm-backend` ne les importe** (seul
  `schemas/__init__.py`) — contrat documentaire, la seconde moitié réelle du contrat est
  [`src/types/api.ts`](../../packages/dcm-frontend/src/types/api.ts).
- [`src/config/navigation.ts`](../../packages/dcm-frontend/src/config/navigation.ts)
  l. 82-109 — groupe `Compute` (`collapsibleGroup: true`) à **5 feuilles** ; une feuille est
  `{ label, path, title }`, **sans icône** (l'icône vient du module de tête,
  `getPageMeta()` l. 143-167). [`src/app-routes.ts`](../../packages/dcm-frontend/src/app-routes.ts)
  l. 54-67 pour le mapping `path → importPage`, **et son piège** : le fourre-tout
  `/databricks/:view` (l. 73) doit rester **après** toute route statique neuve.
- [`src/components/domain/compute/`](../../packages/dcm-frontend/src/components/domain/compute/)
  — réutilisables tels quels : `compute-kpi-card.tsx` (97 l.), `compute-data-table.tsx`
  (452 l., `tableId` obligatoire = clé de persistance des largeurs),
  `compute-trend-chart.tsx` (202 l., **SVG inline**, pas de librairie),
  `chart-hover-tooltip.tsx`, `compute-tabs.tsx` / `compute-cost-tabs.tsx`,
  `compute-info-tip.tsx`, `compute-empty-state.tsx`, `compute-column-widths.ts`.
  **Absents, à écrire** : barre empilée, barres horizontales triées, heatmap (0 occurrence
  de `heatmap` dans tout `src`).
- [`src/pages/ComputePipelines.tsx`](../../packages/dcm-frontend/src/pages/ComputePipelines.tsx)
  — le pattern `compute_kind` de la spec 024 est **serveur uniquement** : la page n'y fait
  **aucune** référence (0 occurrence dans tout `src` hors la déclaration de type
  [`src/types/api.ts`](../../packages/dcm-frontend/src/types/api.ts) l. 2201-2207) ; le
  serverless n'y existe que comme **exclusion en prose** (l. 795, 807, 870, 990, 456). La
  page Serverless est la population complémentaire — il n'existe donc **aucun précédent
  d'IHM** de filtre/colonne/badge `compute_kind` à recopier.
- [`src/hooks/useComputePipelinesQueries.ts`](../../packages/dcm-frontend/src/hooks/useComputePipelinesQueries.ts)
  + [`src/api/dcmApiClient.ts`](../../packages/dcm-frontend/src/api/dcmApiClient.ts)
  (`ComputeMetricsScopeParams` l. 794, `ComputeMetricsPageParams` l. 805) — convention
  `useCompute<Famille>Queries.ts`, client typé central, `src/lib/compute/` pour les helpers
  de page.

## Summary

Trois branches filles, une par domaine, en cascade stricte **DataEng → Backend → Frontend**,
et **à l'intérieur de DataEng l'ordre du §11 du spike**, qui n'est pas un ordre de confort :
le premier lot retire de la production une recommandation chiffrée fausse déjà affichée.

**T001 — DataEng (7 PR séquentielles, ordre imposé).**

1. **T001a — correctif efficience warehouse serverless (§10.3, T1 du spike).** Le lot le plus
   rentable et le seul qui **ne demande aucune donnée nouvelle**. Dans
   `warehouse_utilization_daily.py`, envelopper les champs d'efficience d'un `CASE WHEN
   <serverless> THEN NULL ELSE <expression actuelle> END` : `idle_pct`,
   `active_to_running_ratio`, `utilization_status`, `rightsizing_reco`,
   `estimated_savings_usd`, `auto_stop_minutes`, `has_auto_stop`. **Garder**
   `running_hours`, `active_query_hours`, `peak_concurrency`, `scale_up_events`,
   `scale_down_events` : ils sont justes et utiles. Discriminant : `enable_serverless`
   n'existe pas, mais **`curated_dbx_compute_warehouses.warehouse_type` existe** (rectifié le
   2026-09-10 — invisible par grep, la spec curated ingère en `SELECT *`). Il n'est pourtant
   pas suffisant seul : il ne porte que le **dernier état connu**, alors qu'un jour-warehouse
   passé doit être qualifié tel qu'il était *ce jour-là*. D'où une cascade à 3 étages :
   facturation (`product_features.is_serverless` sur les lignes portant
   `usage_metadata.warehouse_id`, historisée au jour, 96,6 %) → `warehouse_type =
   'SERVERLESS'` (3,4 %) → `false` (0 %). Matérialisée dans une CTE et **portée en colonne**
   `is_serverless` de la table pour que le backend et l'IHM sachent *pourquoi* les champs
   sont NULL. Corriger au passage le commentaire périmé l. 30-33 (il justifie de préférer
   `STARTING` par un défaut de journalisation de `RUNNING` en serverless — `RUNNING` est en
   fait émis 55 886 fois sur 393 warehouses ; le choix reste bon, la raison est fausse).
2. **T001b — job serverless (T2).** Réécrire `job_cluster_cost_daily.py` en **billing-direct**
   (`usage_metadata.job_id IS NOT NULL`), grain
   `(cloud_provider, workspace_id, job_id, compute_kind, period_start)`, miroir exact de
   `pipeline_cost_daily.py`. Le `INNER JOIN` sur `job_clusters` disparaît (il n'existait que
   pour résoudre `cluster_id → job_id`, résolution inutile quand la facturation porte
   `job_id`). Conserver la résolution de `job_name` « as of » (`change_time < period_start +
   INTERVAL 1 DAY`) et le `COALESCE` de repli sur l'id. `job_cluster_cost_rolling` suit
   (`compute_kind` dans le grain). **Contrôle de sortie** : la somme des deux `compute_kind`
   redonne le coût job total de la facturation.
3. **T001c — correctifs §10.1 et §10.4 (T3).** `pipeline_cost_daily.py` : porter
   `billing_origin_product` **dans le grain** plutôt qu'ajouter `AND billing_origin_product =
   'DLT'` au filtre l. 180 — les 320 refresh MV/ST (1 970 $) ont une valeur, sur une autre
   surface, et un filtre les perdrait. `cluster_cost_daily.py` : renommer `sku_group` en
   `sku_family` (`PHOTON`/`STANDARD`) **ou** porter `is_serverless` avec `UNKNOWN` — dans les
   deux cas traiter explicitement les **6 483 lignes / 126 clusters / 897 $** où
   `product_features.is_serverless` est NULL, qu'un remplacement naïf du `LIKE` transformerait
   en NULL.
4. **T001d — `serverless_cost_daily` + `_rolling` (T4).** Le socle. Nouveaux helpers dans
   `sql_helpers.py` : `serverless_surface_case_expr` (liste de produits **fermée**, branche
   `ELSE 'OTHER'` explicite), `serverless_object_id_expr`
   (`COALESCE(<clé de surface>, '_NO_OBJECT')`), `identity_principal_expr` +
   `identity_source_expr`, `HISTOGRAM_COST_PER_RUN_EDGES`. Grain
   `(cloud_provider, workspace_id, serverless_surface, object_id, period_start)`.
   `_rolling` calqué sur les `*_rolling` existants, percentiles $/run **recalculés depuis les
   histogrammes fusionnés**.
5. **T001e — `serverless_governance` (T6).** Snapshot au grain
   `(cloud_provider, workspace_id, serverless_surface)` : parts de $ couvertes par tag /
   policy / identité, $ sans propriétaire, $ sans clé d'objet, inventaire des policies.
6. **T001f — ingestion `system.lakeflow.pipeline_update_timeline` (T7).** *Révisé le 2026-09-10 :*
   **deux artefacts**, pas un. `IngestionSpec` **fidèle au grain horaire**, calquée sur ses deux
   jumelles `job_run_timeline` / `job_task_run_timeline` (watermark `period_start_time`, pas de
   partitionnement), **plus** un builder gold `pipeline_update_stats` au grain `update_id` : durée =
   `MAX(period_end_time) - MIN(period_start_time)`, `result_state` = `MAX` du groupe, `compute_type`
   = `MAX(compute.type)`, `request_id` pour dédupliquer les reprises. La source vaut **422 143 lignes
   pour 412 328 updates**. Agréger dans l'ingestion tronquerait les 40 updates étalés au-delà du
   lookback de 3 j (jusqu'à 19 j) — cf. errata de FR-015 et `T001f-baseline-measures.md` §6.
7. **T001g — robustesse `compute_kind_case_expr` (§10.2, T9) uniquement.** Le volet
   ~~forecast `SERVERLESS_SURFACE` (T8)~~ est 🚫 **hors périmètre depuis le 2026-09-10**
   (décision utilisateur, prise avant toute ligne de code) : `ai_forecast` n'est **pas** passé
   sur `serverless_cost_daily`, `forecast.py` n'est pas touché. Reste : `compute_kind_case_expr`
   **conservé** sur `cluster_id IS NOT NULL` et **verrouillé par un test de non-régression
   d'équivalence** avec `product_features.is_serverless` (0 discordance sur 51 748 / 11 869
   lignes DLT), qui documente l'exception aws du 2026-07-31 — la seule ligne où le champ
   officiel est NULL alors que `cluster_id` tranche juste. Le test empêche un mainteneur futur
   de « corriger » l'expression vers le champ officiel et de perdre cette ligne.

**T002 — Backend.** Une famille de services neuve `compute_metrics_serverless.py` + les
routes correspondantes dans `compute_metrics.py`, **et** la neutralisation côté réponses
warehouse (un champ non applicable est **absent ou `null`, jamais `0`**). Les routes suivent
les conventions relevées : `@router.get` renvoyant `dict[str, Any]`, bloc de scope à 7
paramètres + 4 dépendances, `window_days` sur les vues instantanées et **jamais** sur les
tendances, pagination `_clamp_page`, `column_filter` → 422 sur clé inconnue, **statiques
avant `{id}`**. Nouvelles vues dans `FILTERABLE_COLUMNS`, schémas dans
`dcm_commons/schemas/compute_metrics.py`, docstring de module (liste des routes) mise à jour.

**T003 — Frontend.** Page `ComputeServerless.tsx` (`/databricks/serverless`) en 5 blocs,
entrée nav dans le groupe Compute, route déclarée **avant** le fourre-tout
`/databricks/:view`, hook `useComputeServerlessQueries.ts`, fonctions client dans
`dcmApiClient.ts`, types dans `types/api.ts`, fixtures `src/test/fixtures/compute-serverless.ts`,
et les **3 composants absents** : barre empilée, barres horizontales triées, heatmap.

## Technical Context

**Language/Version** : Python 3.12 (pipeline + backend), TypeScript 5 / React 18 (frontend).

**Primary Dependencies** : **aucune nouvelle**. Pipeline : `pyspark` + `pipelines/common/`
(`merge_into_table`, `IngestionSpec`) ; `ai_forecast` reste hors périmètre (cf. étape 7), donc
`forecast.py` et son appel Statement Execution ne sont pas touchés. Backend : FastAPI +
`DatabricksWarehousePool`. Frontend : React Query + composants `compute-*`.
**Décision explicite : les 3 composants neufs sont écrits en SVG inline**, comme
`compute-trend-chart.tsx`, et **n'introduisent pas `recharts` dans la famille compute** —
la dépendance existe bien (`package.json` l. 30) mais n'est importée que par
`LakeflowOverview.tsx` et `MonitoringReports.tsx` ; l'y faire entrer créerait deux dialectes
de graphique dans le même dossier.

**Storage** : Unity Catalog `it.ba_data_connect_monitoring__<env>` (dev `__d`, prod `__p`).

- Tables **écrites neuves** : `curated_dbx_lakeflow_pipeline_update_timeline` (fidèle, grain
  horaire), `gold_dbx_compute_pipeline_update_stats` (grain `update_id`, ajoutée le 2026-09-10 —
  errata FR-015), `gold_dbx_compute_serverless_cost_daily`,
  `gold_dbx_compute_serverless_cost_rolling`, `gold_dbx_compute_serverless_governance`.
- Tables **modifiées** : `gold_dbx_compute_warehouse_utilization_daily`/`_rolling`
  (neutralisation + colonne `is_serverless`), `gold_dbx_compute_job_cluster_cost_daily`/
  `_rolling` (source **et** grain changent), `gold_dbx_compute_pipeline_cost_daily`/`_rolling`
  (`billing_origin_product` au grain), `gold_dbx_compute_cluster_cost_daily`/`_rolling`
  (`sku_group` → `sku_family`). ~~`gold_dbx_compute_forecast_daily` (`SERVERLESS_SURFACE`)~~ →
  🚫 **retirée de cette liste le 2026-09-10** : la table reste **inchangée**, avec ses 11
  combinaisons (object_type, métrique).
- Tables **lues sans modification** : `curated_dbx_billing_usage`,
  `curated_dbx_billing_list_prices`, `curated_dbx_lakeflow_jobs`,
  `curated_dbx_lakeflow_pipelines`, `curated_dbx_compute_warehouses`, `dim_dbx_workspace`.

**Testing** : `pytest` sur le SQL généré (`packages/dcm-databricks-pipeline/tests/gold_dbx_compute/`),
`pytest` services + routes (`packages/dcm-backend/tests/test_compute_metrics_<famille>.py`),
**Vitest 4** côté frontend — tests **co-localisés** (`src/pages/<Page>.test.tsx`), configuration
dans `vite.config.ts` (`environment: 'jsdom'`, `setupFiles: './src/test/setup.ts'`), et
**pas de MSW** : la convention maison est `vi.mock('../api/dcmApiClient', …)` + `vi.mocked(fn)`
sur des fixtures typées de `src/test/fixtures/`, rendu via `renderWithProviders` de
`src/test/render.tsx`.

**Target Platform** : Databricks (jobs de bundle) + API FastAPI + SPA React.

**Project Type** : monorepo web (pipeline de données + API + SPA).

**Performance Goals** : pas d'objectif chiffré nouveau. Les tables `*_rolling` existent
précisément pour que les vues instantanées se servent d'un snapshot et non d'un `GROUP BY` sur
90 jours au moment de la requête.

**Constraints** :

- `merge_into_table` fusionne sur `<=>` **null-safe** → **aucune clé de merge NULL**, jamais.
  C'est la contrainte structurante de tout T001d/e.
- `system.billing.attributed_usage` est **vide (0 ligne)** → l'attribution SQL reste au grain
  `warehouse_id`. **Ne rien construire dessus** (Prerequisites de la spec).
- Le spike est **mono-cloud (AWS)** ; DCM est bi-cloud (Azure ajoute ≈ 103 967 $/30 j de
  serverless, mesuré). Tout contrôle comparé à un chiffre du spike **doit** porter
  `cloud_provider = 'aws'`.
- Validation sur données réelles via le profil OAuth **`dcm-dev`** + warehouse **`DCM-metrics`**
  (`fcc5098720414937`), API Statements. **PAT interdits chez TotalEnergies** : le profil
  `[DEFAULT]` de `~/.databrickscfg` en porte un et **ne doit jamais être utilisé**.

**Scale/Scope** : 4 tables gold/curated neuves, 6 familles de tables gold modifiées, ~1 famille
de services backend + ~10 routes, 1 page + 3 composants frontend. 3 branches filles, ~11 PR.

## Constitution Check

*GATE : à passer avant Phase 0. Re-vérifié après Phase 1.*

| Principe | Statut | Justification |
|---|---|---|
| P1 Test-First & Code Quality (NON-NEGOTIABLE) | ✅ PASS | Tests avant code aux 3 niveaux : SQL généré (`CASE` de surface exhaustif, sentinelle `_NO_OBJECT`, neutralisation serverless, agrégation par `update_id`, bornes d'histogramme), services + routes (ordre statique avant `{id}`, 404, 422 sur `column_filter`), rendu de page + 3 composants (Vitest, fixtures typées). Gates lint → types → tests → build par package. |
| P2 Simplicité, Explicitness & Versioning | ✅ PASS | Aucune abstraction neuve : `serverless_cost_daily` est la **transposition** de `pipeline_cost_daily`, les histogrammes réutilisent les 3 helpers existants (seules les bornes sont nouvelles), les expressions de surface/objet/identité sont **factorisées en helpers** plutôt que recopiées dans 4 builders. Les 3 composants restent en SVG inline comme le reste de la famille compute. |
| P3 Self-Documenting Code | ✅ PASS | Chaque décision contre-intuitive est documentée là où elle vit : *pourquoi* une sentinelle et pas un NULL (le `<=>`), *pourquoi* `GENIE` est séparé d'`AI_ENDPOINT`, *pourquoi* l'idle serverless est NULL et non 0, *pourquoi* `usage_policy_id` n'est pas porté, *pourquoi* `COUNT(*)` est faux sur les tables horaires. Plus la correction du commentaire périmé de `warehouse_utilization_daily.py` l. 30-33. |
| P4 Fail Fast, Fail Loud | ✅ PASS | Un produit inconnu tombe en `OTHER` et **se voit** (SC-003 exige `OTHER` non vide) au lieu de se fondre dans une catégorie existante. `column_filter` inconnu → 422. Id hors périmètre → 404. Aucune clé de merge NULL possible par construction. |
| P5 Architecture explicite & modularité | ✅ PASS | Toute l'agrégation est en gold ; le backend ne lit que du gold + `dim_dbx_workspace` ; les noms d'objet sont résolus en gold (nativement depuis `usage_metadata`, repli dimension, repli id), jamais en lecture curated depuis l'API. |
| P6 Idempotency by Design | ✅ PASS | `merge_keys` explicites sur les 3 tables neuves, `*_rolling` = snapshots complets rejouables, ingestion `update_id` idempotente. Le tampon d'un jour du self-join J-1 est **relu, jamais réécrit** (filtre de sortie sur `period_start >= lower_bound`). |
| P7/P8 Secrets Management (NON-NEGOTIABLE) | ✅ PASS | Aucun secret touché. Déploiement par bundle + OAuth (`databricks auth login`) ; validation via le profil `dcm-dev`. **PAT explicitement proscrit** (règle TTE) et le profil `[DEFAULT]` porteur d'un PAT est nommé comme interdit dans la story T001. |
| P9 No Fake Data in Production (NON-NEGOTIABLE) | ✅ PASS | Cœur du lot : on **retire** des chiffres fabriqués (≈ 98 k$/30 j d'économies non réalisables) au lieu d'en ajouter. Aucun identifiant d'objet inventé pour uniformiser les surfaces sans clé — la sentinelle `_NO_OBJECT` est explicite et accompagnée de `has_object_key`. Aucune économie chiffrée sur `performance_target` (même SKU, même $/DBU). Fixtures cantonnées à `src/test/`. |
| P10 Observability & Traceability | ⚠️ NOTE | `logging` stdlib côté pipeline/backend — écart pré-existant et uniforme, non introduit ici. |
| P11 Naming Conventions | ✅ PASS | `serverless_cost_daily`/`_rolling`/`serverless_governance`, `serverless_surface`, `object_id`/`has_object_key`, `identity_principal`/`identity_source` : mêmes conventions que les familles existantes. Le renommage `sku_group` → `sku_family` **corrige** une entorse. (~~`object_type = 'SERVERLESS_SURFACE'`~~ retiré le 2026-09-10 avec le volet forecast.) |
| P12 Medallion — Aggregations on Gold Only | ✅ PASS | Les 3 tables neuves sont des agrégations gold et l'API les lit sans recalculer. (La mention « le forecast lit du gold » est devenue sans objet le 2026-09-10 : le forecast est hors périmètre.) **T001f rectifié le 2026-09-10** : ce PASS reposait sur l'idée que l'agrégation par `update_id` était « de la dé-périodisation, pas un calcul métier », avec la réserve « à re-justifier en revue si elle glisse vers du métier ». Elle a glissé — le taux d'échec dépend du choix `update_id` vs `request_id` (§7 de la baseline), ce qui est un arbitrage métier. L'agrégation est donc passée **en gold** (`pipeline_update_stats`) et l'ingestion redevient fidèle : le principe est désormais respecté **sans réserve**. |
| P13 Immutable Raw Layer | N/A | Pas de couche Raw dans ce flux. |
| P14 Schema Versioning | N/A | Tables gold/curated hors `MetricPayload`. |
| P15 API Contract Stability | ⚠️ NOTE | **Ajouts** : routes serverless. (~~`object_type = SERVERLESS_SURFACE`~~ : hors périmètre depuis le 2026-09-10, `GET /forecast` garde donc son contrat **à l'identique** — cette valeur reste un `object_type` inconnu et doit continuer de rendre 422.) **Changements de comportement assumés et tracés** : (a) les réponses warehouse ne portent plus d'économie chiffrée pour un warehouse serverless — c'est le but ; (b) `job_cluster_cost_*` change de **grain** (`compute_kind` ajouté) et de population (le job serverless entre) : tout consommateur qui somme sans grouper voit son total changer ; (c) `sku_group` disparaît de `cluster_cost_*`. À vérifier route par route avant merge. |
| P16 Frontend Quality | ✅ PASS | Page typée calquée sur les pages compute, client central + hook TanStack Query, composants réutilisés, états vides existants, tests Vitest avec fixtures typées (pas de MSW, convention maison). Les 3 composants neufs reprennent `ChartHoverTooltip`. |

**Verdict** : PASS. Deux `⚠️ NOTE` (P10 pré-existant, P15 ruptures assumées et tracées),
aucune sur un principe NON-NEGOTIABLE.

## Project Structure

### Documentation

```text
specs/025-serverless-compute-page/
├── spec.md
├── plan.md              ← ce fichier
├── intake.json
├── domain-scope.json
├── checklists/requirements.md
├── tasks.md             ← 3 tasks (one_per_domain)
├── merge-strategy.md    ← ordre de merge des 3 branches filles
└── stories/             ← T001 (dataeng), T002 (backend), T003 (frontend)
```

Pas de `research.md` : **il n'y a pas de question ouverte à instruire**. Le spike a mesuré ce
qu'un `research.md` aurait posé — les décisions sont dans la spec (« Décisions verrouillées »)
et le tableau ci-dessous en tient le registre. Pas de `data-model.md` ni de `contracts/`
séparés : le schéma des tables est dans la spec (FR-006 à FR-017) et les formes de réponse
dans `stories/T002.md`, au plus près de qui les écrit. Les contrôles d'acceptation SQL vivent
dans `stories/T001.md` (table « Contrôles de non-régression ») plutôt que dans un
`quickstart.md`, parce que c'est le critère de sortie de cette task.

### Code — fichiers touchés

**T001 — `packages/dcm-databricks-pipeline`**

```text
pipelines/gold_dbx_compute/
├── sql_helpers.py                     UPDATE  HISTOGRAM_COST_PER_RUN_EDGES,
│                                              serverless_surface_case_expr,
│                                              serverless_object_id_expr,
│                                              identity_principal_expr / _source_expr,
│                                              compute_kind_case_expr (T9, is_serverless)
├── specs.py                           UPDATE  3 GoldAggregationSpec neuves + colonnes
│                                              ajoutées/retirées sur 4 specs existantes
├── warehouse_utilization_daily.py     UPDATE  T001a — neutralisation + is_serverless
├── warehouse_utilization_rolling.py   UPDATE  T001a — propagation
├── job_cluster_cost_daily.py          UPDATE  T001b — billing-direct + compute_kind
├── job_cluster_cost_rolling.py        UPDATE  T001b — compute_kind au grain
├── pipeline_cost_daily.py             UPDATE  T001c — billing_origin_product au grain
├── pipeline_cost_rolling.py           UPDATE  T001c — propagation
├── cluster_cost_daily.py              UPDATE  T001c — sku_group → sku_family
├── cluster_cost_rolling.py            UPDATE  T001c — propagation
├── serverless_cost_daily.py           CREATE  T001d
├── serverless_cost_rolling.py         CREATE  T001d
├── serverless_governance.py           CREATE  T001e
├── pipeline_update_stats.py           CREATE  T001f — grain update_id (errata FR-015)
├── forecast.py                        (aucun changement — 🚫 hors périmètre 2026-09-10)
├── sql_helpers.py                     UPDATE  T001g — test de non-régression compute_kind
└── entrypoint.py                      UPDATE  câblage des 4 builders neufs

pipelines/system_tables/
└── specs.py                           UPDATE  T001f — IngestionSpec fidèle, grain horaire

tests/gold_dbx_compute/                CREATE/UPDATE  un fichier par builder touché
databricks.yml                         UPDATE  tâches de bundle des builders neufs
```

**T002 — `packages/dcm-backend` + `packages/dcm-commons`**

```text
app/api/routes/compute_metrics.py              UPDATE  routes serverless + docstring (liste)
app/api/services/compute_metrics_serverless.py CREATE  famille de services neuve
app/api/services/compute_metrics_warehouses.py UPDATE  neutralisation serverless
app/api/services/compute_metrics_filters.py    UPDATE  vues serverless dans FILTERABLE_COLUMNS
app/api/services/compute_metrics_common.py     UPDATE  helpers partagés si factorisation
tests/test_compute_metrics_serverless.py       CREATE
tests/test_compute_metrics_warehouses.py       UPDATE
dcm_commons/schemas/compute_metrics.py         UPDATE  Serverless*Item / *Kpis / *Response
dcm_commons/schemas/__init__.py                UPDATE  ré-export + __all__ (ordre alpha)
```

**T003 — `packages/dcm-frontend`**

```text
src/pages/ComputeServerless.tsx                      CREATE  page 5 blocs
src/pages/ComputeServerless.test.tsx                 CREATE
src/config/navigation.ts                             UPDATE  feuille « Serverless »
src/app-routes.ts                                    UPDATE  AVANT /databricks/:view
src/config/role-permissions.ts                       UPDATE  page:databricks
src/lib/databricks/routes.ts                         UPDATE  allowlist de fenêtre
src/hooks/useComputeServerlessQueries.ts             CREATE
src/hooks/query-keys.ts                              UPDATE
src/api/dcmApiClient.ts                              UPDATE  fonctions typées
src/types/api.ts                                     UPDATE  types de réponse
src/components/domain/compute/compute-stacked-bar.tsx        CREATE + test
src/components/domain/compute/compute-ranked-bars.tsx        CREATE + test
src/components/domain/compute/compute-coverage-heatmap.tsx   CREATE + test
src/test/fixtures/compute-serverless.ts              CREATE
```

**Structure Decision** : monorepo existant, aucun package neuf. Chaque domaine reste dans son
package (`dcm-databricks-pipeline` / `dcm-backend` + `dcm-commons` / `dcm-frontend`) et les 3
branches filles ne se chevauchent pas — sauf sur `dcm-commons`, touché par T002 seul.

## Phase 0 — Décisions de conception

**Pas de `research.md`** : rien n'est à mesurer, tout l'a été. Registre des décisions, chacune
adossée à une mesure du spike (les 8 premières sont reprises dans la section « Décisions
verrouillées » de la spec, qui fait foi) :

| # | Question | Décision | Ce qui la tranche |
|---|---|---|---|
| D1 | Page transversale, page par surface, ou filtre sur les pages existantes ? | **Page transversale (A) + correctifs ciblés (C)** | Les surfaces sans clé d'objet ne peuvent pas être listées objet par objet ; B éclaterait 13,1 % du serverless en 3 pages creuses |
| D2 | `GENIE` fondu dans `AI_ENDPOINT` ? | **Séparé** | 15 850 $ sans **aucun** `endpoint_id` — les fusionner fabriquerait un faux grain objet, et Genie pèse plus qu'`AI_ENDPOINT` entier |
| D3 | `object_id` NULL ou sentinelle ? | **`'_NO_OBJECT'`** | `merge_into_table` fusionne sur `<=>` null-safe → un NULL collapse un workspace entier en une ligne corrompue. Concerne 9,3 % du $ |
| D4 | Une colonne d'identité ou un `COALESCE` ? | **`COALESCE(run_as, owned_by, created_by)` + `identity_source`** | Le champ porteur change par surface (SQL `owned_by` 100 %, Apps `created_by` 100 %, jobs `run_as` 100 %) : une seule colonne donnerait la matrice fausse de la v1 |
| D5 | Porter `usage_policy_id` **et** `budget_policy_id` ? | **`budget_policy_id` seul** | Égalité null-safe vérifiée sur 2 294 408 lignes (100 %) : alias strict |
| D6 | Comment lire les tables `*_timeline` ? | **Agréger par `update_id`/`run_id`** | Périodisation horaire : 43 464 lignes pour 41 817 updates ; `run_duration_seconds = 0` sur 95 % des lignes ; `result_state` NULL sur 23 673/178 003 |
| D7 | Chiffrer une économie sur `performance_target` ? | **Non** | Les deux modes partagent le SKU, donc le $/DBU : le surcoût est en quantité, pas en prix |
| D8 | `serverless_surface` au grain ou en attribut ? | **Dans le grain** | 320 `dlt_pipeline_id` facturés en `SQL` **et** en `DLT` : hors du grain leur coût reste mélangé (même raisonnement que `compute_kind`, spec 024) |
| D9 | Comment reconnaître un **warehouse** serverless ? | Cascade **billing-first** : `product_features.is_serverless` (lignes portant `usage_metadata.warehouse_id`) → `warehouse_type = 'SERVERLESS'` → `false`, **portée en colonne** `is_serverless` | Rectifié le 2026-09-10 : `curated_dbx_compute_warehouses.warehouse_type` **existe** (l'affirmation « aucun champ dédié » était fausse — `SELECT *` en curated le rend invisible au grep). Il reste en 2ᵉ étage seulement : il ne donne que le **dernier état connu**, donc il réécrirait le passé d'un warehouse migré, là où la facturation est historisée au jour (96,6 % de couverture, contre 3,4 % de repli). Porter la colonne évite que le backend redevine le motif du NULL ; la branche `false` garantit non-NULL, donc « non applicable » ne peut pas se lire « donnée manquante » |
| D10 | §10.1 : filtrer `= 'DLT'` ou porter le produit au grain ? | **Produit au grain** | Filtrer perdrait les 320 refresh MV/ST (1 970 $), qui ont une valeur sur la surface `MV_ST_REFRESH` |
| D11 | Nouvelle famille de services backend ou extension de `compute_metrics_warehouses` ? | **Famille neuve `compute_metrics_serverless.py`** | Grain différent (surface × objet), lit des tables différentes ; l'extension mêlerait deux grains dans un module de 839 lignes |
| D12 | 3 composants dataviz : `recharts` ou SVG inline ? | **SVG inline** | `recharts` existe mais n'est importé que par 2 pages hors compute ; l'introduire ici créerait deux dialectes dans `components/domain/compute/`, où tout est fait main (`compute-trend-chart.tsx`) |
| D13 | Ordre de livraison intra-DataEng ? | **§11 du spike, T1 en premier** | T1 retire ≈ 98 k$/30 j de fausses économies **déjà affichées** et ne demande aucune donnée nouvelle : c'est le meilleur rapport valeur/risque du lot |

## Phase 1 — Design

Le design vit dans les artefacts déjà écrits, au plus près de qui l'exécute :

- **Schéma des tables** : spec FR-006 à FR-017 (grains, colonnes, formules, invariant
  anti-double-comptage, bornes d'histogramme).
- **Contrats d'API** : `stories/T002.md` — une entrée par route, avec son grain, ses
  paramètres, sa table gold source et la forme de sa réponse.
- **Contrats d'IHM** : `stories/T003.md` — un bloc par section de page, les composants
  réutilisés vs neufs, et les règles de forme bloquantes (jamais de double axe, teinte
  séquentielle, couleur liée à l'entité, p99 annoté).
- **Contrôles d'acceptation SQL** : `stories/T001.md`, table « Contrôles de non-régression »
  reprise du spike, à rejouer sur `dcm-dev` / `DCM-metrics` avec
  `cloud_provider = 'aws'`.
- **Ordre de merge** : [merge-strategy.md](./merge-strategy.md).

### Ordre d'exécution imposé

```text
DataEng (branche dataeng/025-…, 7 PR séquentielles)
  T001a neutralisation warehouse serverless  ← EN PREMIER, aucune donnée nouvelle
    └─► T001b job serverless billing-direct
          └─► T001c correctifs pipeline_cost / cluster_cost
                └─► T001d serverless_cost_daily + _rolling
                      └─► T001e serverless_governance
                            └─► T001f ingestion fidèle + pipeline_update_stats (update_id)
                                  └─► T001g robustesse compute_kind §10.2 (forecast 🚫 retiré)
  ──► déploiement dev + contrôles de non-régression (critère de sortie)
        └─► T002 (backend)
              └─► T003 (frontend)
```

Le fil n'est **pas** parallélisable entre domaines : T002 lit les tables que T001 produit,
T003 consomme les endpoints de T002. Le critère de sortie de T001 et T002 est
« **déployée et vérifiée en dev** », pas « implémentée ».

À l'intérieur de T001, seules T001a, T001b, T001c sont mutuellement indépendantes sur le plan
technique — elles sont quand même séquencées, pour que le correctif à plus fort impact partage
en revue le moins de diff possible avec le reste. T001d dépend des helpers factorisés en
T001a-c ; T001e lit `serverless_cost_daily`. T001g, réduite au §10.2, **ne dépend plus de T001d**
depuis le retrait du forecast le 2026-09-10 : elle ne touche que `compute_kind_case_expr` et son
test, donc elle pourrait même précéder T001d — l'ordre est conservé pour ne pas rouvrir la
séquence de PR déjà en cours. T001f est
la seule à demander une **ingestion** et peut glisser sans bloquer la page (elle n'alimente que
le comparatif DLT serverless/classique).

## Complexity Tracking

| Écart | Pourquoi c'est nécessaire | Alternative rejetée |
|---|---|---|
| Une table gold neuve au grain `(surface, object_id)` plutôt que d'étendre les tables existantes | Les 11 surfaces n'ont pas la même clé, et 3 n'en ont aucune : aucune table au grain `cluster_id`/`job_id`/`warehouse_id` ne peut les accueillir | Ajouter une colonne `is_serverless` aux tables existantes : ne rend visible que ce qui a déjà une clé, soit ~62 % du serverless — les 38 % invisibles le resteraient |
| Une **sentinelle** `'_NO_OBJECT'` plutôt qu'un NULL, contre l'intuition SQL | `merge_into_table` fusionne sur `<=>` : un NULL en clé de merge n'échoue pas, il **fusionne silencieusement** tout un workspace en une ligne. 9,3 % du $ serverless est concerné | Laisser NULL et « faire attention » : le mode d'échec est une donnée corrompue sans erreur levée, détectable seulement en recomptant les $ |
| `serverless_surface` **dans le grain** (ligne par surface) plutôt qu'en attribut | 320 `dlt_pipeline_id` sont facturés sur deux produits : hors du grain, leurs coûts restent mélangés et le self-join J-1 apparie des lignes de surfaces différentes | Surface en attribut avec `MAX()` : perd la décomposition et fabrique un `cost_delta_pct` calculé contre l'autre surface (piège déjà documenté dans `pipeline_cost_daily.py`) |
| Réécriture de `job_cluster_cost_daily` (source **et** grain) plutôt qu'ajout d'une table job serverless séparée | Deux tables pour un même grain métier `job_id` obligeraient chaque lecteur à savoir laquelle interroger, et l'IHM à faire l'union — exactement ce que `compute_kind` dans le grain a résolu pour le DLT | Table `job_serverless_cost_daily` distincte : duplication du builder, du service et du composant, avec un risque permanent de somme des deux |
| Colonne `is_serverless` ajoutée à `warehouse_utilization_daily` en plus de la neutralisation | Sans elle, le backend et l'IHM voient des NULL sans savoir *pourquoi* et ne peuvent pas afficher « non applicable en serverless » — un NULL muet se lit comme une donnée manquante | Ne mettre que des NULL : l'utilisateur conclut à un bug de collecte, ce qui est pire que le faux chiffre qu'on retire |
| Un histogramme $/run (`array<bigint>`, 19 buckets) plutôt qu'un percentile quotidien | Un p95 quotidien n'est ni sommable ni moyennable sur 30 jours ; les helpers de fusion existent déjà et sont utilisés par 2 familles | `percentile_approx` par jour : impossible de servir la fenêtre 30 j de l'IHM sans mentir sur l'agrégat |
| Bornes jusqu'à 1 310,72 $ alors que le p99 est à 14,88 $ | 62 runs dépassent 50 $ et portent **13,8 % de la dépense job** ; s'arrêter tôt les empile dans un bucket overflow non borné, rendant p99 et max illisibles | S'arrêter à ~50 $ « puisque c'est la queue » : c'est précisément la queue qui porte le budget |
| 3 composants dataviz neufs plutôt qu'une réutilisation de `compute-trend-chart` | Il ne sait faire qu'une série temporelle (barres ou ligne) ; part-d'un-tout, classement et matrice sont trois grammaires différentes | Détourner le trend chart : produirait des barres empilées fausses (pas de notion de segment) ou une heatmap simulée en lignes |
| `serverless_governance` en table dédiée plutôt qu'un `GROUP BY` de `serverless_cost_daily` à la volée | P12 : les agrégations vivent en gold ; la matrice de couverture agrège des ratios de $ sur toutes les surfaces × 3 dimensions, recalculé à chaque requête sur 90 jours | Calculer côté API : hors frontière médaillon et lent, pour une matrice qui ne change qu'une fois par jour |
| ~~Agrégation par `update_id` **à l'ingestion** curated (T001f) plutôt qu'en gold~~ → **inversé le 2026-09-10** : ingestion **fidèle** + agrégation dans `gold_dbx_compute_pipeline_update_stats` | Trois mesures, aucune disponible à l'écriture du plan : `IngestionSpec` n'a **aucun** mécanisme d'agrégation et `ingest.py` se déclare « fidèle source (no transform, no join) » ; avec `DEFAULT_LOOKBACK_DAYS = 3`, **40 updates s'étalent sur ≥ 4 j (max 19 j)** et un agrégat incrémental tronquerait leur durée, le MERGE écrasant une ligne correcte par une plus courte ; **le backend ne lit aucune table `curated_*`** (0 contre ~30 `gold_*`), donc le « futur lecteur » était hypothétique là où la troncature est mesurée | Garder l'agrégation à l'ingestion. **L'argument d'origine reste bon mais ne suffit pas** : oui, un lecteur de la table curated fera un `COUNT(*)` faux. Deux réponses — le piège est nommé dans le `table_comment`, et il existe **déjà** à l'identique sur les deux jumelles `job_run_timeline` / `job_task_run_timeline`, elles aussi fidèles au grain horaire. Faire de `pipeline_update_timeline` la seule des trois qui soit agrégée serait le piège le plus surprenant, pas le moins |

## Progress Tracking

- [x] Constitution Check initial — PASS (2 `⚠️ NOTE`, aucune sur un NON-NEGOTIABLE)
- [x] Phase 0 — décisions consignées (D1…D13, **aucune question ouverte**)
- [x] Phase 1 — design réparti (spec pour le schéma, stories pour API/IHM/contrôles,
      merge-strategy pour l'ordre)
- [x] Constitution Check après design — PASS (inchangé)
- [x] Tasks générées (T001 DataEng, T002 Backend, T003 Frontend)
- [ ] Stories Jira créées (`/speckit.dcm.dispatch`) — **hors périmètre de cette session**
- [ ] T001a neutralisation warehouse serverless implémentée + vérifiée en dev (SC-001)
- [ ] T001b job serverless billing-direct implémenté + vérifié en dev (SC-002)
- [ ] T001c correctifs `pipeline_cost_daily` / `cluster_cost_daily` (SC-009, SC-010)
- [ ] T001d `serverless_cost_daily` + `_rolling` (SC-003 à SC-007, SC-011)
- [ ] T001e `serverless_governance` (SC-006)
- [ ] T001f ingestion `pipeline_update_timeline` fidèle + `pipeline_update_stats` au grain
      `update_id` (SC-008)
- [ ] T001g robustesse `compute_kind_case_expr` §10.2 (~~forecast `SERVERLESS_SURFACE`~~ 🚫 hors
      périmètre depuis le 2026-09-10)
- [ ] T002 implémentée + vérifiée en dev
- [ ] T003 implémentée (SC-012)
