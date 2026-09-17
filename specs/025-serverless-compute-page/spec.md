# feature : Page « Serverless compute » + correctifs des pages compute existantes

**Feature Branch**: `025-serverless-compute-page` — branches filles `{domain}/025-{slug}`
**Work Type**: feature
**Priority**: P2
**Created**: 2026-09-10

**Input**: Page Serverless compute : rendre visibles les 38 % de dépense DBU
(136 674 $/30 j) invisibles dans DCM, sur les 11 surfaces serverless, et corriger les
4 défauts des pages compute existantes dont ~98 k$/30 j d'économies fictives sur les
warehouses serverless. Réf. spike (révision 2026-09-10, toutes valeurs **mesurées**) :
[docs/spike/serverless-compute-page/proposition.md](../../docs/spike/serverless-compute-page/proposition.md).

## Décisions verrouillées (depuis le spike, session 2026-09-10)

L'intake a été confirmé **non interactivement** depuis le spike (consigne d'autonomie
totale) : `intake.json.intake_mode = "non_interactive"`. Les décisions qui auraient été
posées en `/speckit-clarify` sont déjà tranchées et **mesurées** dans le spike — elles sont
reprises ici parce qu'elles sont des contraintes de correction, pas de la prose :

1. **Structure = option A puis C ciblé** (§5 du spike). Une page transversale
   `/databricks/serverless` (« où part la dépense, à qui la refacturer, quels leviers »),
   **pas** une page par surface (option B rejetée : notebooks + apps + Lakebase = 13,1 % du
   serverless), **pas** un simple filtre sur les pages existantes (option C seule : les
   surfaces sans clé d'objet resteraient absentes et l'efficience resterait fausse).
2. **11 surfaces, pas 10.** `GENIE` (15 850 $, 5,6 % du serverless) est **séparé** de
   `AI_ENDPOINT` (12 733 $, 152 `endpoint_id`) : c'est la seule surface IA **sans clé
   d'objet** (0 `endpoint_id`), et elle pèse plus que `AI_ENDPOINT` entier. Les fusionner
   fabriquerait un faux grain objet.
3. **`object_id` a besoin d'une SENTINELLE `'_NO_OBJECT'`, jamais d'un NULL.** 9,3 % de la
   dépense serverless (26 533 $) n'a aucune clé d'objet (GENIE, `PLATFORM_AUTO`,
   `NETWORKING`, `OTHER`), et `NOTEBOOK`/`AI_ENDPOINT`/`LAKEBASE` en ont 1,2 %/1,1 %/13,6 %.
   `pipelines.common.writers.merge_into_table` fusionne sur `<=>` **null-safe** : une clé de
   merge NULL fusionnerait tout un workspace en **une ligne corrompue**. Même règle pour
   `serverless_surface` (branche `ELSE 'OTHER'` explicite).
4. **`identity` est un `COALESCE(run_as, owned_by, created_by)`, pas une colonne** — le champ
   porteur **change par surface** (SQL → `owned_by` 100 %, Apps → `created_by` 100 %, jobs /
   notebooks / DLT / Genie / plateforme → `run_as` 100 %, IA → mixte 60/43). Un seul champ
   donnerait la matrice fausse de la v1 du spike (Apps 0 %, SQL 40 %, IA 3 %). Une colonne
   `identity_source` (`RUN_AS | OWNED_BY | CREATED_BY | NONE`, jamais NULL) accompagne
   `identity_principal` : « propriétaire (owned_by) » et « exécutant (run_as) » ne sont pas
   la même sémantique de refacturation.
5. **`usage_policy_id` est un alias strict de `budget_policy_id`** (égalité null-safe
   vérifiée sur 2 294 408 lignes / 100 %). N'en porter **qu'un** : `budget_policy_id`.
6. **`pipeline_update_timeline` et `job_run_timeline` sont périodisées à l'heure** : une
   ligne par tranche horaire, pas par update/run. Agréger **par `update_id` / `run_id`** —
   jamais `COUNT(*)` (43 464 lignes pour 41 817 updates), jamais une durée ligne à ligne
   (`run_duration_seconds = 0` sur 95 % des lignes), jamais un taux d'échec ligne à ligne
   (`result_state` NULL sur 23 673 / 178 003 lignes).
7. **Aucune économie chiffrée sur `performance_target`** : les deux modes partagent le même
   SKU, donc le même $/DBU. Le surcoût est en **quantité de DBU**, pas en prix. Afficher la
   population et le $ exposé, pas un gain.
8. **`serverless_surface` dans le GRAIN**, pas en attribut — même raisonnement que
   `compute_kind` dans `pipeline_cost_daily` (spec 024) : 320 `dlt_pipeline_id` sont facturés
   en `SQL` **et** en `DLT`, hors du grain leur coût resterait mélangé.

## Domain Scope

Depuis `intake.json` — « In scope » = lecture autorisée, « Ticket » = reçoit une Story.

| Domaine | In scope | Ticket Story | Packages |
|---------|----------|--------------|----------|
| Frontend | ✅ | ✅ | packages/dcm-frontend |
| Backend | ✅ | ✅ | packages/dcm-backend, packages/dcm-commons |
| DataEng | ✅ | ✅ | packages/dcm-databricks-pipeline |
| DevOps | ❌ | ❌ | — |
| QA | ❌ | ❌ | — |

## Ticket Plan

| Stories Jira | 3 |
|---|---|
| Mode | one_per_domain |
| Domaines avec ticket | dataeng, backend, frontend |

## Contexte

`product_features.is_serverless` est le discriminant **officiel** (pas une heuristique de nom
de SKU). Mesuré sur le compte AWS `dbc-223d60ab-45bd` (128 workspaces), fenêtre
`usage_date` 2026-08-10 → 2026-09-09, prix de liste :

| Bucket | $ / 30 j | Part |
|---|---:|---:|
| `is_serverless = true` | 250 466 | 69,6 % |
| produit serverless-only, flag `NULL` (GENIE, MODEL_SERVING, VECTOR_SEARCH, LAKEBASE, NETWORKING, AI_*, LAKEFLOW_CONNECT, SUPERVISOR_AGENT, AGENT_EVALUATION) | 34 878 | 9,7 % |
| `is_serverless = false` (classic) | 74 687 | 20,7 % |
| **Total dépense DBU** | **360 039** | 100 % |

**Le serverless est 79,3 % de la dépense DBU**, alors que les pages Compute de DCM sont
construites sur le grain `cluster_id` — **qui n'existe pas en serverless**. Conséquence
mesurée : **136 674 $ / 30 j, soit 38,0 % de la dépense DBU totale, n'est visible nulle
part** dans l'outil, et la seule surface serverless couverte (SQL warehouse, 48,7 % du
serverless) l'est avec un diagnostic d'efficience qui produit des recommandations
**impossibles à appliquer**.

Le trou n'est pas un oubli d'IHM, il est **structurel dans le gold** :
`cluster_cost_daily` filtre `usage_metadata.cluster_id IS NOT NULL`, et
`job_cluster_cost_daily` est un rollup de cette table — un job serverless n'a **jamais** de
`cluster_id`, il est donc exclu **en amont, silencieusement** (60 021 $ / 30 j **AWS**, comme
tous les chiffres du spike — cf. Assumptions). Recontrôlé sur les deux clouds en implémentant
T001b (2026-09-10, fenêtre 2026-08-11 → 2026-09-09) : **56 841 $ AWS + 28 812 $ Azure =
85 653 $ / 30 j** exclus, sur 3 689 jobs. La table ne montrait donc que **35 %** du coût des
jobs, pas « presque tout ». L'ordre de grandeur AWS du spike est confirmé ; ce qui manquait,
c'est qu'Azure double presque l'enjeu.

« Serverless » n'est pas un type de compute : c'est **11 grains différents**, dont **trois
sans aucune clé d'objet**. Une page « clusters serverless » symétrique de la page
all-purpose n'existe pas, faute d'objet unique à lister.

| Surface | Clé d'agrégation | $ / 30 j | Part srvls | Objets | WS | % $ keyé | Visible dans DCM |
|---|---|---:|---:|---:|---:|---:|:--|
| `SQL_WAREHOUSE` | `warehouse_id` | 138 911 | 48,7 % | 398 | 128 | 100 % | ✅ coût — ⚠️ rightsizing fictif |
| `JOB` | `job_id` (+ `job_run_id`) | 60 021 | 21,0 % | 2 701 | 80 | 100 % | ❌ **absent** |
| `NOTEBOOK` | `notebook_id` | 21 662 | 7,6 % | 4 212 | 103 | 98,8 % | ❌ absent |
| `GENIE` | **aucune** (workspace) | 15 850 | 5,6 % | — | 112 | 0 % | ❌ absent |
| `AI_ENDPOINT` | `endpoint_id` | 12 733 | 4,5 % | 152 | 29 | 98,9 % | ❌ absent |
| `APP` | `app_id` | 11 385 | 4,0 % | 55 | 22 | 100 % | ❌ absent |
| `PLATFORM_AUTO` | **aucune** (workspace) | 8 374 | 2,9 % | — | 93 | 0 % | ❌ absent |
| `DLT_PIPELINE` | `dlt_pipeline_id` | 7 796 | 2,7 % | 875 | 25 | 100 % | ✅ couvert |
| `LAKEBASE` | `endpoint_id` ∪ `dlt_pipeline_id` | 4 340 | 1,5 % | 64 | 22 | 86,4 % | ❌ absent |
| `NETWORKING` | **aucune** (workspace) | 2 304 | 0,8 % | — | 99 | 0 % | ❌ absent |
| `MV_ST_REFRESH` | `dlt_pipeline_id` | 1 970 | 0,7 % | 320 | 18 | 100 % | ⚠️ **mal attribué** |
| `OTHER` (LAKEFLOW_CONNECT) | — | 5 | 0,0 % | — | 9 | 0 % | ❌ absent |

Deux notions à tenir **séparées**, parce qu'elles appellent des actions différentes :
**sans clé d'objet = 26 533 $ (9,3 %)** — non listables objet par objet, affichables au grain
workspace, ce n'est pas un défaut à corriger mais ce que la source contient ; **sans aucun
propriétaire = 5 875 $ (2,06 %)** — ni tag, ni policy, ni identité, presque uniquement
NETWORKING (100 % orphelin) et LAKEBASE (81 %). C'est le seul vrai trou de refacturation, et
il est **petit**.

**Nuance à ne pas escamoter** : sur les deux fenêtres de 30 j consécutives, la part
serverless **baisse** (81,7 % → 79,3 %), le classic ayant crû plus vite (+23,0 %) que le
serverless (+5,2 %). La page se justifie par la **masse absolue** non couverte, pas par une
trajectoire d'explosion.

Enfin, quatre défauts des pages **existantes** ont été trouvés en mesurant, indépendants de
la nouvelle page — dont un qui affiche déjà **≈ 98 k$/30 j d'économies impossibles à
réaliser** sur les warehouses serverless (`idle_pct` médian 96,3 %, 353 des 398 warehouses
marqués `OVER`). En serverless l'utilisateur **n'est pas facturé au temps allumé** : réduire
l'idle d'un warehouse serverless ne rend aucun dollar. C'est le correctif à plus fort impact
du lot, et il ne demande **aucune donnée nouvelle**.

## Dependency Analysis

Vérification code (Q6 de l'intake) — les trois domaines étant dans le Ticket Plan, le
tableau est informatif : pas de flow de gap.

| Besoin | Domaine requis | Preuve (fichier) | Résolution |
|--------|----------------|------------------|------------|
| Tables gold au grain surface serverless | dataeng | `pipelines/gold_dbx_compute/` — aucune table `*_serverless_*` ; `cluster_cost_daily.py:129` filtre `usage_metadata.cluster_id IS NOT NULL` → exclut structurellement tout le serverless | **à créer** (T001) |
| `product_features` / `identity_metadata` lisibles en curated | dataeng | `system_tables/specs.py` — `BILLING_USAGE_SPEC` sans `select_columns` (= `SELECT *`) ; **vérifié en dev le 2026-09-10** : `curated_dbx_billing_usage` porte `billing_origin_product`, `product_features`, `usage_metadata`, `identity_metadata` | ✅ présent — **aucune ingestion nouvelle** pour T001–T006 |
| Helpers histogrammes réutilisables | dataeng | `sql_helpers.py:193-245` — `histogram_from_edges_sql` / `sum_histograms_sql` / `percentile_from_histogram_sql` | ✅ présents, à réutiliser + nouvelles bornes |
| Pattern `compute_kind` dans le grain | dataeng | `pipeline_cost_daily.py:19-23,167` — billing-direct + `compute_kind` dans le grain | ✅ présent, **à répliquer** sur les jobs |
| `system.lakeflow.pipeline_update_timeline` ingéré | dataeng | `system_tables/specs.py` — absent des inputs | **à ingérer** (T7, agrégé par `update_id`) |
| Endpoints REST `/compute-metrics/serverless/*` | backend | `app/api/routes/compute_metrics.py` — 29 routes GET (clusters/warehouses/jobs/pipelines/recommendations/forecast), aucune route serverless ; « serverless » n'apparaît qu'en commentaire l. 1248 | **à créer** (T002) |
| Page `/databricks/serverless` + composants dataviz | frontend | `src/config/navigation.ts` — groupe Compute à 5 feuilles, aucune « Serverless » ; `src/components/domain/compute/` — `ComputeKpiCard`/`ComputeDataTable`/`ComputeTrendChart`/`ComputeTabs` réutilisables, **aucune** barre empilée, **aucune** barre horizontale triée, **aucune** heatmap | **à créer** (T003) : page + nav + 3 composants |
| Pattern UI `compute_kind` | frontend | `src/pages/ComputePipelines.tsx` — pattern livré par la spec 024 (T008) | ✅ présent, à reprendre |
| `system.billing.attributed_usage` | dataeng | **vide : 0 ligne**, tout historique confondu (mesuré) | **limitation acceptée, hors scope** — cf. Prerequisites |

## Prerequisites

- **Small branches / small PRs** : 3 branches filles, une par domaine. La branche DataEng est
  elle-même séquencée en **petits PR** dans l'ordre du §11 du spike (T1 correctif warehouse →
  T2 jobs serverless → T3 correctifs §10.1/§10.4 → T4 tables socle → T6 gouvernance →
  T7 ingestion → T9 robustesse) : chaque lot est un diff revuable seul, jamais un PR unique.
- Intake + domain scope confirmés (`intake.json` / `domain-scope.json`). **Confirmés
  non interactivement depuis le spike** (`intake_mode: non_interactive`,
  `intake_source: docs/spike/serverless-compute-page/proposition.md` révision 2026-09-10) :
  les Q1–Q7 sont dérivées du document, pas d'un échange. Toute contestation de scope se règle
  par `/speckit.dcm.specify --intake-only`, pas par une édition de cette spec.
- **Dépendance externe bloquante, reportée : `system.billing.attributed_usage` est vide
  (0 ligne)** sur ce compte. C'est *la* table qui attribuerait la dépense serverless SQL à la
  requête et à l'utilisateur (`usage_metadata.dbsql_statement_id`,
  `identity_metadata.executed_by`, `granular_tags.query_tags`). Elle existe au catalogue mais
  n'est pas alimentée. **Conséquence tenue pour acquise dans cet Epic** : l'attribution des
  **48,7 % de dépense serverless SQL reste bornée au grain `warehouse_id`**, et le bloc
  Attribution restera partiel sur cette surface. C'est une **limitation acceptée, hors
  scope** — pas un blocage à résoudre avant de commencer, et surtout **rien ne doit être
  construit dessus**. Son activation est une demande à porter aux admins de compte, hors de
  cette spec. À noter que même activée, le rattachement d'une requête warehouse à sa source
  resterait borné par les **97,1 % de requêtes warehouse sans `query_source` exploitable**.
- **Ordre de livraison imposé** : DataEng → Backend → Frontend, et **à l'intérieur** de
  DataEng, le correctif warehouse (T1) **avant tout le reste** — il retire une recommandation
  chiffrée fausse déjà visible dans l'outil.
- Le dataeng est **délégué au subagent `dp-data-databricks-engineer`** (délégation bloquante,
  `dcm-config.yml` `implement.domain_subagents`), avec **validation sur données réelles** en
  fin de task : profil OAuth **`dcm-dev`** + warehouse **`DCM-metrics`** (`fcc5098720414937`)
  via l'API Statements. **Les Personal Access Tokens sont interdits chez TotalEnergies** : le
  profil `[DEFAULT]` de `~/.databrickscfg` porte un PAT prohibé et ne doit **jamais** être
  utilisé.
- `[NEEDS CLARIFICATION]` : **0 en attente** — le spike tranche tout (cf. Décisions
  verrouillées).

## User stories

### User Story 1 — DataEng : correctifs des pages compute + socle gold serverless (Priority: P1)

Producteur du socle. Dans l'ordre du §11 du spike : (1) **neutraliser** l'efficience des
warehouses serverless, (2) rendre le **job serverless** visible en passant
`job_cluster_cost_daily` en lecture **billing-direct** avec `compute_kind` dans le grain,
(3) corriger le filtre produit de `pipeline_cost_daily` et le `sku_group` de
`cluster_cost_daily`, (4) créer `serverless_cost_daily` + `_rolling` +
`serverless_governance`, (5) ingérer `pipeline_update_timeline` agrégé par `update_id`,
(6) durcir `compute_kind_case_expr` par un test de non-régression. Le volet **forecast** du §11
du spike — projeter `SERVERLESS_SURFACE` — est **sorti du périmètre le 2026-09-10** (décision
utilisateur, avant toute implémentation) : cf. FR-016.

**Why this priority** : socle dont dépendent Backend puis Frontend ; et son premier lot
retire immédiatement **≈ 98 k$/30 j de fausses économies déjà affichées**, sans donnée
nouvelle.
**Independent Test** : requêter les tables gold — aucun jour-warehouse serverless ne porte
`estimated_savings_usd`/`utilization_status` ; `job_cluster_cost_daily` porte des lignes
`compute_kind = 'SERVERLESS'` ; `serverless_cost_daily` porte 12 valeurs de
`serverless_surface` et aucune clé de merge NULL.

**Acceptance Scenarios**

1. **Given** un warehouse serverless dans `warehouse_utilization_daily`, **When** le job gold
   s'exécute, **Then** `idle_pct`, `active_to_running_ratio`, `utilization_status`,
   `rightsizing_reco`, `estimated_savings_usd`, `auto_stop_minutes` et `has_auto_stop` sont
   **NULL** (« non applicable »), tandis que `running_hours`, `active_query_hours`,
   `peak_concurrency`, `scale_up_events`/`scale_down_events` restent renseignés.
2. **Given** de la facturation de job serverless (aucun `cluster_id`), **When** le job gold
   s'exécute, **Then** `gold_dbx_compute_job_cluster_cost_daily` porte une ligne
   `compute_kind = 'SERVERLESS'` pour ce `job_id`, et la somme des deux `compute_kind`
   redonne le coût job total.
3. **Given** de la facturation serverless sans clé d'objet (GENIE, plateforme auto,
   réseau), **When** `serverless_cost_daily` est construite, **Then** ces lignes portent
   `object_id = '_NO_OBJECT'` et `has_object_key = false`, **une ligne par workspace**, et
   aucune n'est fusionnée avec une autre par le `<=>` de `merge_into_table`.
4. **Given** `pipeline_update_timeline` périodisée à l'heure, **When** elle est ingérée,
   **Then** la table curated est au grain `update_id` (durée =
   `MAX(period_end_time) - MIN(period_start_time)`, `result_state` = `MAX` du groupe), et
   `COUNT(*)` y est un nombre d'updates.

### User Story 2 — Backend : endpoints serverless + neutralisation de l'efficience warehouse (Priority: P2)

Exposer le socle : overview (part serverless, 4 KPI, dépense par surface, trajectoire
quotidienne), attribution/gouvernance (matrice de couverture, $ sans propriétaire, $ sans clé
d'objet, budget policies), leviers (`performance_target`, distribution $/run, concentration),
et drill-down par surface — dont les surfaces au **grain workspace**. Plus la neutralisation
côté réponses warehouse : un champ non applicable est **absent ou `null`, jamais `0`**.

**Why this priority** : dépend des tables gold (US1) ; prérequis de l'UI (US3).
**Independent Test** : appeler chaque route — l'overview renvoie la part serverless et les
4 KPI ; le drill-down d'une surface sans clé d'objet renvoie des lignes au grain workspace
marquées comme telles ; la réponse warehouse d'un warehouse serverless ne porte plus
d'`estimated_savings_usd` chiffré.

**Acceptance Scenarios**

1. **Given** l'endpoint overview serverless, **When** on le requête, **Then** il renvoie la
   part serverless de la dépense DBU, le total, le Δ vs période précédente, le $ sans
   propriétaire et le **% global** couvert par une budget policy — **pas** la valeur de la
   surface JOB.
2. **Given** l'endpoint de drill-down pour `GENIE` ou `PLATFORM_AUTO` ou `NETWORKING`,
   **When** on le requête, **Then** les lignes sont au grain `workspace_id`, avec un
   indicateur `has_object_key = false` exploitable par l'IHM — **jamais** un faux identifiant
   d'objet fabriqué pour uniformiser.
3. **Given** un warehouse serverless, **When** on requête les routes d'efficience /
   recommandations warehouse, **Then** aucune économie chiffrée n'est renvoyée et le motif
   « non applicable en serverless » est exploitable côté IHM.

### User Story 3 — Frontend : page `/databricks/serverless` + 3 composants de dataviz (Priority: P3)

Créer la page transversale sous le groupe Compute, en 5 blocs (bandeau de cadrage,
attribution & chargeback, leviers actionnables, drill-down par surface en onglets, angles
morts assumés), et les **3 composants absents** : barre empilée (part d'un tout), barres
horizontales triées (classement), heatmap (matrice de couverture).

**Why this priority** : couche de présentation ; dépend des endpoints (US2). Le spike
identifie les 3 composants comme le **vrai poste d'effort** de la page, pas la donnée.
**Independent Test** : ouvrir la page — les 5 blocs sont présents, les onglets sans clé
d'objet annoncent le grain workspace dans leur en-tête, et l'encart « angles morts » explique
l'absence de CPU/mémoire/idle.

**Acceptance Scenarios**

1. **Given** la nav Compute, **When** l'utilisateur l'ouvre, **Then** une entrée
   « Serverless » existe et mène à `/databricks/serverless`.
2. **Given** le bloc « dépense par surface » à 11 catégories, **When** il s'affiche,
   **Then** c'est une **barre horizontale triée à une seule teinte séquentielle** (travail de
   magnitude), **pas** 11 couleurs catégorielles ni un camembert.
3. **Given** un onglet `Genie` / `Plateforme` / `Réseau`, **When** il s'ouvre, **Then**
   l'en-tête du tableau annonce explicitement le **grain workspace** et aucune colonne
   « objet » n'est affichée.
4. ~~**Given** la distribution du coût par run, **When** elle s'affiche, **Then** elle est en
   **buckets quasi-log** avec **p50 *et* p99 annotés** (la moyenne 0,611 $ est 4× le p95
   1,49 $ : n'afficher que p50/p95 laisserait croire à une dépense diffuse).~~ 🚫 **Retiré le
   2026-09-11** : le graphe de fenêtre a été supprimé de la page sur décision utilisateur. La
   règle de forme reste valable partout où une distribution à queue lourde est **effectivement**
   affichée — drawer par objet, colonnes `$/run p50` / `$/run p99` du bloc 4.
5. **Given** un utilisateur venant de la page cluster, **When** il cherche CPU / mémoire /
   idle / rightsizing de node, **Then** l'encart « angles morts » lui dit **pourquoi** ces
   colonnes n'existent pas — elles ne sont jamais affichées vides.

## Acceptance Criteria

1. **Given** la dépense DBU serverless, **When** un utilisateur ouvre DCM, **Then** les
   136 674 $ / 30 j aujourd'hui invisibles sont consultables — au grain objet là où une clé
   existe, au grain workspace sur les 26 533 $ qui n'en ont pas.
2. **Given** les pages compute existantes, **Then** elles n'affichent plus de recommandation
   d'économie sur un warehouse serverless, plus de pipeline non-DLT présenté comme du DLT,
   plus de `sku_group = 'serverless'` sur une table de clusters, et le job serverless y est
   visible.
3. **Given** les tables gold serverless, **Then** aucune clé de merge n'est NULL et la somme
   des `serverless_surface` redonne exactement le périmètre serverless de la facturation.
4. Gates de chaque package verts (lint → types → tests → build).

## Out of scope (cet Epic)

- **Attribution fine de la dépense serverless SQL** (à la requête / à l'utilisateur) :
  `system.billing.attributed_usage` est vide sur ce compte. L'attribution SQL reste au grain
  `warehouse_id`. Ne **rien** construire dessus. Aussi hors scope pour la même raison : un
  bloc « coût par requête SQL » (97,1 % des requêtes warehouse sans `query_source`).
- **KPI de temps de démarrage serverless** : `query.history.waiting_for_compute_duration_ms`
  est NULL sur 100 % des requêtes `SERVERLESS_COMPUTE` (0 / 4 321 082). Aucune métrique de
  cold start exploitable.
- **Attribution des notebooks serverless via `query.history`** : `notebook_id` y recouvre
  `job_info.job_id` (80,3 % et 89,9 % se chevauchent — tâche de type notebook dans un job) et
  ne désigne donc **pas** de l'interactif. Seul `billing.usage`
  (`billing_origin_product = 'INTERACTIVE'`) fait foi pour les 21 662 $.
- **Attribution des 2 304 $ de NETWORKING** à un objet : `system.access.outbound_network` est
  la seule piste, non mesurée. Reste au grain workspace.
- **Une page par surface** (option B du spike) : notebooks + apps + Lakebase = 37 387 $
  (13,1 % du serverless). Un onglet dans la page A suffit ; à rouvrir si l'usage décolle.
- **CPU / mémoire / idle actionnable / rightsizing de node** au grain serverless :
  `node_timeline` n'existe pas en serverless. Affichés comme angle mort assumé, jamais comme
  colonne vide.
- DevOps / QA : aucun ticket (pas de changement CI/infra ni de fixture transverse dédiée).

## Work Breakdown (preview)

| ID | Domain | Summary | Ticket |
|----|--------|---------|--------|
| T001 | DataEng | Correctif efficience warehouse serverless + job serverless billing-direct (`compute_kind`) + correctifs `pipeline_cost_daily`/`cluster_cost_daily` + `serverless_cost_daily`/`_rolling`/`_governance` + ingestion `pipeline_update_timeline` par `update_id` + non-régression `compute_kind_case_expr` (~~forecast `SERVERLESS_SURFACE`~~ 🚫 retiré le 2026-09-10) | ✅ |
| T002 | Backend | Endpoints serverless (overview / cost par surface / gouvernance / leviers / drill-down par surface, dont grain workspace) + neutralisation de l'efficience serverless dans les réponses warehouse + schémas `dcm-commons` | ✅ |
| T003 | Frontend | Page `/databricks/serverless` (5 blocs) + entrée nav + 3 composants absents (barre empilée, barres horizontales triées, heatmap) | ✅ |
| T004 | Frontend | Remise au vert des 4 gates de `packages/dcm-frontend` — 61 problèmes eslint, 101 erreurs `tsc`, 4 tests rouges héritées de `develop`, sans changement fonctionnel (ajoutée le 2026-09-10, cf. `amend-log.json`) | ✅ |

## Requirements & Success Criteria

### Correctifs de l'existant (priorité absolue — §10 et §11 du spike)

- **FR-001** *(T1, le plus rentable du lot)* : dans
  `gold_dbx_compute_warehouse_utilization_daily`, quand le warehouse est **serverless**,
  `idle_pct`, `active_to_running_ratio`, `utilization_status`, `rightsizing_reco`,
  `estimated_savings_usd`, `auto_stop_minutes` et `has_auto_stop` valent **NULL** (« non
  applicable »). `running_hours`, `active_query_hours`, `peak_concurrency`,
  `scale_up_events`/`scale_down_events` **restent calculés** : ils sont justes et
  intéressants. Motif : l'idle serverless **n'est pas facturé** — le calcul actuel est
  rigoureux mais fabrique ≈ 98 k$/30 j d'économies non réalisables (`idle_pct` médian
  96,3 %, > seuil sur 95,6 % des jours-warehouse, 353 des 398 warehouses marqués `OVER`).
  Le signal d'efficience serverless est le **$ par requête**, pas l'idle.
- **FR-002** *(T2)* : `gold_dbx_compute_job_cluster_cost_daily` passe en lecture
  **billing-direct** depuis `curated_dbx_billing_usage` (miroir de `pipeline_cost_daily`,
  **plus** un rollup de `cluster_cost_daily`) et porte `compute_kind`
  (`CLASSIC` / `SERVERLESS`) **dans le grain**. Motif : le rollup actuel hérite du filtre
  `usage_metadata.cluster_id IS NOT NULL` de `cluster_cost_daily` et exclut donc
  **structurellement** les 60 021 $ / 30 j de job serverless.
- **FR-003** *(T3, §10.1)* : `gold_dbx_compute_pipeline_cost_daily` ne présente plus comme
  du DLT ce qui ne l'est pas. `usage_metadata.dlt_pipeline_id` est renseigné par **4
  produits** (`DLT` 1 055 pipelines / 9 807 $ · `SQL` refresh MV/ST 320 / 1 970 $ ·
  `DATABASE` synced tables 32 / 202 $ · `VECTOR_SEARCH` 12 / 144 $) : **2 316 $ sur 364
  pipelines** sont affichés comme du DLT sans en être. Correctif retenu : **porter
  `billing_origin_product` dans le grain** plutôt que filtrer `= 'DLT'`, pour ne rien perdre
  (les 320 refresh MV/ST ont une valeur, mais sur la surface `MV_ST_REFRESH`).
- **FR-004** *(T3, §10.4)* : `gold_dbx_compute_cluster_cost_daily` n'expose plus de
  `sku_group = 'serverless'` — contresens sur une table dont le filtre d'entrée est
  `cluster_id IS NOT NULL`, donc **par construction du compute classique** (81 clusters
  étiquetés `serverless` alors qu'ils ont un `cluster_id`). Renommer en `sku_family`
  (`PHOTON` / `STANDARD`), ou porter `product_features.is_serverless` avec une **troisième
  valeur `UNKNOWN`** : le champ est **NULL sur 6 483 lignes / 897 $ / 126 clusters** de cette
  table, un remplacement naïf du `LIKE` produirait des NULL.
- **FR-005** *(T9, robustesse, priorité basse)* : `compute_kind_case_expr` porte
  `product_features.is_serverless` (champ officiel) plutôt que `cluster_id IS NULL`.
  **Aucun bug à corriger** : l'équivalence est **parfaite** sur le produit `DLT`
  (51 748 / 11 869 lignes, 0 discordance, aucun `is_serverless` NULL). Garder l'équivalence
  comme **test de non-régression**.

### Socle gold serverless

- **FR-006** : `gold_dbx_compute_serverless_cost_daily`, grain
  `(cloud_provider, workspace_id, serverless_surface, object_id, period_start)`, construite
  **billing-direct** depuis `curated_dbx_billing_usage` × `curated_dbx_billing_list_prices`.
  Périmètre : `product_features.is_serverless = true` **∪** produit dans
  `('GENIE','MODEL_SERVING','VECTOR_SEARCH','LAKEBASE','NETWORKING','AI_FUNCTIONS','AI_GATEWAY','LAKEFLOW_CONNECT','SUPERVISOR_AGENT','AGENT_EVALUATION')`.
- **FR-007** : `serverless_surface` vient d'un `CASE` **exhaustif à liste de produits
  fermée**, avec branche **`ELSE 'OTHER'` explicite** — jamais NULL (clé de merge). 12
  valeurs : `JOB`, `DLT_PIPELINE`, `MV_ST_REFRESH`, `SQL_WAREHOUSE`, `NOTEBOOK`, `APP`,
  **`GENIE`** (séparé de `AI_ENDPOINT` : seule surface IA sans `endpoint_id`), `AI_ENDPOINT`,
  `LAKEBASE`, `NETWORKING`, `PLATFORM_AUTO`, `OTHER`. Un produit **nouveau** doit tomber en
  `OTHER` et **se voir**, jamais se fondre dans une catégorie existante (la v1 du spike y
  rangeait silencieusement `LAKEFLOW_CONNECT`).
- **FR-008** : `object_id = COALESCE(<clé de la surface>, '_NO_OBJECT')`, plus un booléen
  `has_object_key`. **Une sentinelle, pas un NULL** : 9,3 % de la dépense serverless
  (26 533 $) n'a aucune clé, et `merge_into_table` fusionne sur `<=>` **null-safe** — un NULL
  en clé de merge fusionnerait tout un workspace en **une ligne corrompue**.
  `workspace_id` **reste dans le grain** : `object_id` est globalement unique **sauf pour
  `AI_ENDPOINT`** (152 `endpoint_id` pour 159 couples `(workspace_id, endpoint_id)`).
- **FR-009** : colonnes d'attribution — `budget_policy_id` (**et pas** `usage_policy_id`,
  alias strict vérifié null-safe sur 2 294 408 lignes), `identity_principal` =
  `COALESCE(identity_metadata.run_as, owned_by, created_by)`, `identity_source`
  (`RUN_AS | OWNED_BY | CREATED_BY | NONE`, **jamais NULL**), `has_custom_tags` (booléen).
- **FR-010** : colonnes de mesure — `dbu_quantity`, `cost_usd`, `cost_usd_prev_day`,
  `cost_delta_pct` (self-join exact sur J-1 **égalisé sur `serverless_surface` et
  `object_id`**, jamais un `LAG`), `run_count` =
  `COUNT(DISTINCT usage_metadata.job_run_id)` (**NULL** hors surface `JOB`), `cost_rank` /
  `is_top_cost` en `RANK() PARTITION BY (period_start, serverless_surface)`,
  `object_name`, `billing_origin_product`, `performance_target`, `_generated_at`.
- **FR-011** : `object_name` vient **nativement** de
  `usage_metadata.{job_name, notebook_path, app_name, endpoint_name}` (`job_name`
  2 305/2 701, `notebook_path` 4 342, `app_name` 52/55), **repli** sur la dimension curated,
  **repli final** sur `object_id`. Pas de join obligatoire pour ces trois surfaces.
- **FR-012** : `cost_per_run_histogram` (`array<bigint>`, buckets fixes, **sommable sur
  fenêtre**) plutôt qu'un percentile quotidien — un p95 quotidien n'est ni sommable ni
  moyennable sur 30 j. Réutiliser `histogram_from_edges_sql` / `sum_histograms_sql` /
  `percentile_from_histogram_sql` de `sql_helpers.py` avec de **nouvelles bornes
  `HISTOGRAM_COST_PER_RUN_EDGES`**, quasi-log par doublement de 0,01 $ à 1 310,72 $ (18
  bornes, 19 buckets), calquées sur `HISTOGRAM_LATENCY_MS_EDGES` :
  `0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92, 163.84, 327.68, 655.36, 1310.72`.
  **Ne pas s'arrêter à ~50 $** : 62 runs dépassent 50 $ et portent **13,8 % de la dépense
  job** — ils finiraient dans un bucket overflow non borné et le p99 (14,88 $) comme le max
  (1 345 $) deviendraient illisibles. 15,2 % des runs sont ≤ 0,01 $ : la première borne est
  bien placée.
- **FR-013** : `gold_dbx_compute_serverless_cost_rolling` = `serverless_cost_daily` +
  `window_days`, mêmes `ROLLING_WINDOWS` que les modules existants, fenêtre précédente à
  **NULL** (jamais `0`) quand elle est vide, percentiles $/run **recalculés depuis les
  histogrammes fusionnés** — jamais une moyenne de percentiles.
- **FR-014** : `gold_dbx_compute_serverless_governance`, grain
  `(cloud_provider, workspace_id, serverless_surface)` : part de $ couverte par
  `custom_tags`, par `budget_policy_id`, par `identity`, $ sans propriétaire, $ sans clé
  d'objet, inventaire des budget policies. Alimente la matrice de couverture.
- **FR-015** *(révisée le 2026-09-10 — voir errata ci-dessous)* : le grain **`update_id`** est porté
  par **`gold_dbx_compute_pipeline_update_stats`** (agrégée depuis les tranches horaires : durée =
  `MAX(period_end_time) - MIN(period_start_time)`, `result_state` = `MAX` du groupe,
  `compute_type` = `MAX(compute.type)`, plus `request_id` pour dédupliquer les reprises), et
  `curated_dbx_lakeflow_pipeline_update_timeline` reste **fidèle source au grain horaire**, comme ses
  deux jumelles `job_run_timeline` / `job_task_run_timeline`. **Jamais** une ligne par tranche dans ce
  que la page consomme : `COUNT(*)` sur la source vaut **422 143 pour 412 328 updates** (+2,38 %).

  > **Errata.** L'énoncé d'origine plaçait l'agrégation **dans l'ingestion**
  > (« `curated_dbx_lakeflow_pipeline_update_timeline` ingérée au grain `update_id` », volumes
  > 43 464 / 41 817). Trois mesures l'ont écarté (`T001f-baseline-measures.md` §6) : `IngestionSpec`
  > n'a aucun mécanisme d'agrégation et `ingest.py` se déclare « fidèle source (no transform, no
  > join) » ; avec `DEFAULT_LOOKBACK_DAYS = 3`, **40 updates s'étalent sur ≥ 4 jours (max 19 j)** et
  > un agrégat incrémental tronquerait leur `MIN(period_start_time)`, le MERGE écrasant alors une
  > ligne correcte par une plus courte ; et **le backend ne lit aucune table `curated_*`** (0 contre
  > ~30 `gold_*`). L'intention de FR-015 est conservée, sa couche d'exécution corrigée.
- 🚫 **FR-016 — HORS PÉRIMÈTRE depuis le 2026-09-10** (décision utilisateur, prise après les
  mesures de faisabilité et **avant** toute implémentation). Énoncé retiré :
  ~~`gold_dbx_compute_forecast_daily` accepte `object_type = 'SERVERLESS_SURFACE'`, projeté depuis
  `serverless_cost_daily` sur `cost_usd` et `dbu_quantity`.~~ Conséquences : `forecast.py`,
  `compute_metrics_forecast.py` et la route `GET /forecast` restent **inchangés**, et
  `forecast_daily` garde ses **11** combinaisons (object_type, métrique) au lieu de 13.
  > Les mesures qui étayaient FR-016 restent dans `T001g-baseline-measures.md` et **valent au-delà
  > de cette spec** : sur les 4 grains **déjà en production**, `ai_forecast` publie 23,4 % de
  > lignes à `predicted_value` NULL et jusqu'à **2,49 × 10³⁸⁹ $** sans lever la moindre erreur.
  > Le durcissement est donc à ouvrir comme spec distincte, et son coût est déjà chiffré : un
  > seuil de 8 points retirerait **6,39 %** des dollars projetés au grain JOB (p50 = 1 jour
  > d'historique) et **6,26 %** au grain CLUSTER — ce n'est pas un nettoyage gratuit, d'où la
  > décision de ne pas l'improviser ici.
- **FR-017** *(anti-double-comptage)* : `serverless_cost_daily` est un **rollup des mêmes
  lignes de facturation** que `cluster_cost_daily`, `job_cluster_cost_daily`,
  `pipeline_cost_daily` et `warehouse_cost_daily` — **ne jamais l'y sommer**. En revanche,
  sommer ses `serverless_surface` **entre elles est légitime** : elles partitionnent des
  lignes disjointes. Documenté dans le docstring de la table et dans son `table_comment`.

### Exposition backend

- **FR-018** : endpoint **overview serverless** — part serverless de la dépense DBU (+ valeur
  de la période précédente), total serverless, Δ vs période précédente, $ sans propriétaire,
  **% global** couvert par une budget policy. Le KPI policy est **8,4 % au global** ; 21 % est
  la valeur de la **surface JOB seule** et ne va pas dans la tuile.
- **FR-019** : endpoints **coût par surface** et **trajectoire quotidienne** (top 5 surfaces
  + « Autres »), aux fenêtres des pages compute existantes.
- **FR-020** : endpoint **gouvernance / attribution** — matrice surfaces ×
  {`custom_tags`, `budget_policy_id`, `identity`} en % de $, $ sans propriétaire (avec les
  lignes), $ sans clé d'objet, top consommateurs notebooks, inventaire des budget policies.
- **FR-021** : endpoint **leviers** — répartition `performance_target` (population + $
  exposé, **aucune économie chiffrée**), distribution $/run (p50, p95, **p99**, moyenne,
  max), concentration haute fréquence (jobs ≥ N runs), concentration du poids de run
  (runs > N $), comparatif DLT serverless vs classique.
- **FR-022** : endpoints **drill-down par surface** au grain de la clé de chaque surface,
  colonnes limitées à ce qui **existe vraiment** ; pour `GENIE`, `PLATFORM_AUTO`,
  `NETWORKING` et `OTHER`, grain **`workspace_id`** avec `has_object_key = false` exposé.
  **Jamais** de faux identifiant d'objet fabriqué pour uniformiser.
- **FR-023** : les réponses **warehouse** ne renvoient plus d'économie ni de statut de
  dimensionnement chiffrés pour un warehouse serverless — champ **absent ou `null`, jamais
  `0`** — avec le motif « non applicable en serverless » exploitable par l'IHM.
- **FR-024** : conventions des 29 routes GET existantes de `compute_metrics.py` reprises à
  l'identique (préfixe, pagination serveur, tri, recherche, `cloud_provider`, fenêtres,
  404 sur id hors périmètre), et schémas correspondants dans `dcm-commons`.

### Page frontend

- **FR-025** : entrée **« Serverless »** dans le groupe Compute de `navigation.ts` →
  page `/databricks/serverless`, en **première position** du groupe (décision du 2026-09-11) :
  la page transversale ouvre le groupe, les quatre grains classiques la suivent.
- **FR-026** : **bloc 1 — bandeau de cadrage** : hero figure « part serverless » + **barre
  empilée à 2 segments** (jamais un camembert à 2 parts), 4 tuiles KPI (`ComputeKpiCard`
  réutilisé), **barres horizontales triées** pour la dépense par surface, **colonnes empilées
  par jour** (top 5 surfaces + « Autres »).
- **FR-027** : **bloc 2 — attribution & chargeback** : **heatmap** de couverture (teinte
  séquentielle, en % de $), tuiles « $ sans propriétaire » et « $ sans clé d'objet » (celle-ci
  renvoyant vers le grain workspace), **barre horizontale top 10** des consommateurs notebooks
  + tuile « top 10 = 31 % » — **surtout pas** un Pareto à double axe — et tableau des budget
  policies.
- **FR-028** : **bloc 3 — leviers** : `performance_target` en barre empilée 2 segments +
  tableau, ~~**histogramme à buckets quasi-log** du $/run avec **p50 et p99 annotés**~~
  (🚫 retiré de la page le 2026-09-11 — décision utilisateur ; les percentiles restent servis par
  l'API et affichés par objet dans le drawer et par surface dans les colonnes du bloc 4), tableaux
  de concentration, comparatif DLT serverless/classique (dumbbell ou 2 tuiles) **présenté
  comme une corrélation, pas une promesse de gain** (les pipelines restés en classic sont les
  plus anciens et les plus lourds, pas un échantillon aléatoire).
- **FR-029** : **bloc 4 — drill-down** en onglets (`ComputeTabs` réutilisé) : Jobs · SQL ·
  Notebooks · DLT · Apps · IA · Genie · Plateforme. Les onglets **Genie**, **Plateforme** et
  **Réseau** sont au **grain workspace** et **leur en-tête le dit**. Drawer au clic avec la
  tendance 30 j (`ComputeTrendChart`) + les métriques `query.history` **uniquement pour les
  surfaces où `query_source` rattache réellement** — jobs (89,9 %) et DLT (0,7 %), **pas** les
  notebooks.
- **FR-030** : **bloc 5 — angles morts assumés** : encart explicite (pas un silence) — pas de
  CPU/mémoire, pas de rightsizing de node, pas d'idle actionnable ; mention des **97,1 % de
  requêtes warehouse sans source identifiable** et renvoi à `attributed_usage` comme condition
  d'un futur bloc « coût par requête SQL ». Une colonne sans équivalent serverless n'est
  **jamais affichée vide**.
- **FR-031** : **3 composants à créer** — barre empilée, barres horizontales triées, heatmap.
  Ils reprennent le survol des composants maison (`ComputeTrendChart`, `ChartHoverTooltip`),
  ne l'oublient pas. Règles de forme **bloquantes** : jamais de double axe ; plafond de 7–8
  séries catégorielles (au-delà → « Autres » ou petits multiples) ; **11 surfaces ≠ 11
  couleurs** → une seule teinte séquentielle triée pour un travail de magnitude ; la couleur
  suit l'entité, **jamais son rang** (filtrer une surface ne repeint pas les survivantes) ;
  palette de statut réservée aux statuts, avec icône + libellé, jamais la couleur seule ;
  légende dès 2 séries, étiquettes directes jusqu'à 4 ; distribution à queue lourde en échelle
  log ou buckets quasi-log avec p99 annoté.

### Success Criteria

Mesurés **sur données réelles** via le profil `dcm-dev` / warehouse `DCM-metrics`. Les valeurs
de référence du spike sont **AWS uniquement** : les rejouer avec
`cloud_provider = 'aws'` (cf. Assumptions).

- **SC-001** ✅ **atteint le 2026-09-10** : après FR-001, **0 jour-warehouse
  `is_serverless = true`** porte un `estimated_savings_usd`, un `utilization_status` ou un
  `rightsizing_reco` non NULL — contre 353 warehouses `OVER` et ≈ 98 k$/30 j d'économies
  annoncées avant correctif. `running_hours` et `active_query_hours` restent renseignés sur ces
  mêmes lignes. Mesuré : 0 fuite sur **15 496** jours-warehouse serverless, `is_serverless` non
  NULL sur 16 709/16 709 lignes recalculées, activité servie à 100 %, 1 213/1 213 lignes
  classic/pro intactes. Côté recommandations : « Warehouse surdimensionné » passe de 665 à 87
  OPEN dont **0 serverless**, « Auto-stop manquant » de 6 à 0, soit **−115 194 $** d'économies
  non réalisables — et **62 recos actionnables démasquées** (27 105 $) que le verdict faux
  cachait par déduplication.
  Le critère porte sur `is_serverless = true` et non sur « les warehouses serverless » : cette
  formulation sépare ce que le calcul contrôle des lignes orphelines qu'aucun run ne réécrit
  (SC-013). Les confondre ferait conclure à un échec là où il n'y en a pas.
- **SC-013** (ajouté le 2026-09-10, **reformulé le même jour** — cf. ci-dessous et T001h) :
  **aucune ligne orpheline ne survit plus de `SNAPSHOT_ABSENT_ROW_GRACE_DAYS + 1` jours** dans
  `warehouse_utilization_daily` / `_rolling`, et le MERGE du job émet bien une clause
  `WHEN NOT MATCHED BY SOURCE … THEN DELETE` **bornée à la fenêtre recalculée**, sans reculer
  l'historique et de façon idempotente.
  ✅ **Mécanisme atteint le 2026-09-10** : 43 des 75 orphelines daily supprimées par le MERGE
  du job (`DESCRIBE HISTORY` v685, `numTargetRowsDeleted = 43` — contre **0** à la v661, la
  veille, qui est la preuve directe du défaut), `MIN(period_start)` inchangé à **2026-07-15**,
  second run à `numTargetRowsDeleted = 0` (idempotence).
  🟡 **Résiduel décroissant, non nul** : 32 lignes daily et 162 rolling restent, **protégées
  par le délai de grâce**, purgeables du 2026-09-12 au 2026-09-17 (échéancier vérifié
  `_generated_at` par `_generated_at`).

  **Pourquoi la formulation initiale était fausse** — elle exigeait « **0 ligne** à
  `is_serverless` NULL » *tout en* exigeant le garde-fou de grâce de 7 jours qui protège
  précisément les orphelines récentes d'un run dégradé. Les deux demandes sont
  contradictoires : aucun mécanisme ne peut les satisfaire ensemble. Ce n'est **pas** un
  critère assoupli pour épouser un résultat décevant (SC-001 a justement été maintenu tel quel
  et atteint) — c'est un critère qui était **inatteignable par construction**, démontré par la
  mesure, et corrigé en ce qu'il voulait dire : la péremption passe de **permanente** à
  **≤ 8 jours**.

  **Sur `*_rolling`, le résiduel est un flux, pas un stock.** Chaque run crée de nouvelles
  lignes périmées (churn naturel de `window_days = 1` : un warehouse actif hier et inactif
  aujourd'hui sort de la fenêtre — 204 lignes pour le run du 2026-09-10). « 0 orpheline » n'y
  sera donc **jamais** vrai, même après l'échéancier ; le régime permanent est « ≤ 8 jours ».
  La protection du consommateur n'est pas de raccourcir la grâce (voir l'invariant ci-dessous)
  mais de **filtrer à la lecture sur `as_of_date = MAX(as_of_date)`** — ce que la couche API
  faisait déjà et ce que le moteur de règles fait depuis FR-001.

  **Invariant découvert en implémentant T001h, verrouillé par un test** :
  `SNAPSHOT_ABSENT_ROW_GRACE_DAYS` doit rester **strictement inférieur** à
  `INCREMENTAL_LOOKBACK_DAYS` (7 < 10). Sur une table à watermark, une ligne n'est supprimable
  que si elle est **à la fois** hors grâce **et** dans la fenêtre recalculée, soit
  `P + grâce < aujourd'hui ≤ P + fenêtre` : l'intervalle est **vide** dès que
  `grâce ≥ fenêtre`, et l'orpheline devient **immortelle** en régime incrémental. Monter la
  grâce « par prudence » produirait donc l'effet inverse de celui recherché.
- **SC-002** : après FR-002, la dépense job serverless apparaît dans
  `job_cluster_cost_daily` (**≈ 60 021 $ / 30 j** sur AWS), et
  `SUM(cost_usd)` toutes valeurs de `compute_kind` = dépense job totale de la facturation.
- **SC-003** : `serverless_cost_daily` porte **12** valeurs distinctes de
  `serverless_surface`, dont **`OTHER` non vide** (4,82 $, `LAKEFLOW_CONNECT`, AWS uniquement)
  — un `OTHER` vide signifierait que la liste de produits n'est plus fermée. Contrôle
  symétrique : `OTHER` doit rester **≤ ~10 $ par cloud**, sinon un produit facturé
  significatif y est tombé sans être classé (c'est ainsi qu'a été trouvé
  `DATA_CLASSIFICATION`, 107,54 $ sur Azure, désormais rangé en `PLATFORM_AUTO`).
- **SC-004** : **0 ligne** avec `serverless_surface` ou `object_id` NULL, et le nombre de
  lignes `object_id = '_NO_OBJECT'` égale le nombre de couples
  `(workspace_id, serverless_surface, period_start)` sans clé — **26 533 $ / 9,3 %** du
  serverless sur la fenêtre de référence.
- **SC-005** : la partition du §1 est **exacte** — **0 ligne** de la facturation hors des
  3 buckets (`is_serverless = true` / produit serverless-only / `is_serverless = false`).
- **SC-006** : $ sans propriétaire (ni tag, ni policy, ni identité) = **5 875 $ (2,06 %)**,
  et `identity_source` est renseigné (**jamais NULL**) sur 100 % des lignes ; la couverture
  identité est **100 % partout sauf `LAKEBASE` (5 %) et `NETWORKING` (0 %)**.
- **SC-007** : `usage_policy_id` ≠ `budget_policy_id` (comparaison null-safe) sur **0 ligne**
  — contrôle que l'alias tient toujours et qu'il reste correct de n'en porter qu'un.
- **SC-008** *(re-mesurée le 2026-09-10 sur la source, **vérifiée après déploiement** le même
  jour)* : `gold_dbx_compute_pipeline_update_stats` porte 2 valeurs distinctes de `compute_type`
  (0 NULL, 0 update ambigu), et `COUNT(*)` y égale `COUNT(DISTINCT (cloud_provider, update_id))` —
  la périodisation horaire est bien absorbée, **par le builder gold** et non par l'ingestion
  (cf. errata FR-015). La table curated en amont reste au grain horaire, où l'égalité est
  **fausse**. Mesures du premier run (backfill 30 j, les deux clouds) : **129 713 lignes curated
  pour 127 640 updates gold**, ratio 1,0162 ; `SUM(period_count)` du gold = `COUNT(*)` de la
  curated **par `cloud_provider`** (43 122 aws, 86 591 azure, écart 0). Sur la source aws en
  historique complet, la répartition est 339 941 `SERVERLESS_COMPUTE` / 72 387 `CLASSIC_COMPUTE`
  pour 422 143 lignes et 412 328 updates.
  Le taux d'échec doit nommer **son dénominateur, sa définition, sa fenêtre et son cloud** — les
  quatre. Par `request_id` (dernière tentative), l'historique complet aws donne **7,03 %
  serverless / 5,19 % classique**, mais les **30 derniers jours donnent 1,99 % serverless /
  13,31 % classique** : la direction s'inverse. Et le cloud déplace le niveau : **5,97 %
  serverless sur azure contre 1,99 % sur aws**, azure portant 67,5 % des updates. Aucun contrôle
  d'acceptation ne fixe donc un taux attendu ; ce qu'il vérifie est que **le taux servi est
  recalculé sur la fenêtre demandée**, que le libellé porte la fenêtre, et qu'il est **étiqueté
  par cloud ou déclaré agrégé** (`T001f-baseline-measures.md` §7, §10.6 et §10.8).
- **SC-008b** *(mesurée après déploiement le 2026-09-10)* : la tuile de comparaison
  serverless / classique applique un **seuil de population minimale** et n'affiche **aucun**
  pourcentage en dessous. Contre-exemple qui l'exige, et cas de test : sur azure la population
  DLT classique est de **23 updates / 6 `request_id`** (0,027 % des updates du cloud, qui est
  serverless à 99,97 %), et un « taux d'échec classique azure » de 33,33 % y sort de **deux**
  échecs. Le comparatif serverless / classique est donc structurellement **aws seulement**.
- **SC-009** : `pipeline_cost_daily` distingue les **4** `billing_origin_product` portant
  `dlt_pipeline_id` (`DLT`, `SQL`, `DATABASE`, `VECTOR_SEARCH`) ; les 364 faux pipelines DLT
  (2 316 $) ne sont plus comptés comme du DLT.
- **SC-010** : `cluster_cost_daily` ne renvoie **aucune** ligne de la valeur `serverless`
  (ancien `sku_group`), et les **6 483 lignes** à `is_serverless` NULL sont traitées
  explicitement (`UNKNOWN`), pas devenues NULL.
- **SC-011** : les percentiles $/run reconstruits depuis `cost_per_run_histogram` sur la
  fenêtre 30 j retrouvent l'ordre de grandeur mesuré — **p50 ≈ 0,125 $, p95 ≈ 1,49 $,
  p99 ≈ 14,88 $** sur 98 207 runs — à la résolution des buckets près, et **aucun run n'atterrit
  dans le bucket overflow** au-delà de 1 310,72 $ sauf le maximum mesuré (1 345 $).
- **SC-012** : la page `/databricks/serverless` affiche ses 5 blocs ; les onglets sans clé
  d'objet annoncent le grain workspace ; l'encart « angles morts » est présent — vérifié en
  test et au navigateur.

## Assumptions

- **Le spike mesure un seul cloud, DCM en couvre deux.** Toutes les valeurs du spike viennent
  du compte **AWS** `dbc-223d60ab-45bd` interrogé sur `system.billing.usage`, alors que tous
  les grains gold de DCM commencent par `cloud_provider`. **Mesuré en dev le 2026-09-10** sur
  `curated_dbx_billing_usage` (même fenêtre 2026-08-10 → 2026-09-09, prix de liste) :

  | `cloud_provider` | `is_serverless = true` | produit serverless-only | classic | part serverless |
  |---|---:|---:|---:|---:|
  | aws | 240 503 $ | 33 277 $ | 71 922 $ | **79,2 %** |
  | azure | 92 224 $ | 10 815 $ | 53 919 $ | **65,6 %** |

  Deux conséquences tenues pour acquises : (1) la part AWS en curated (**79,2 %**) reproduit
  celle du spike (**79,3 %**) — l'écart absolu de ≈ 4 % sur les montants est le décalage
  curated/système attendu (watermark, arrivées tardives), pas une erreur de périmètre ;
  (2) **Azure ajoute ≈ 103 967 $ / 30 j de serverless** que le spike n'a pas mesurés — la page
  est bi-cloud, et **les contrôles d'acceptation chiffrés doivent être rejoués avec
  `cloud_provider = 'aws'`** pour être comparables au spike. Un contrôle qui compare un total
  bi-cloud à un chiffre du spike échouera à tort.
- `curated_dbx_billing_usage` porte bien `billing_origin_product`, `product_features`,
  `usage_metadata` et `identity_metadata` (**vérifié le 2026-09-10** :
  `BILLING_USAGE_SPEC` n'a pas de `select_columns`, donc `SELECT *`). Aucune ingestion
  nouvelle n'est nécessaire pour FR-006 à FR-014 ; seule FR-015
  (`pipeline_update_timeline`) en demande une.
- `usage_metadata.serverless_compute_id` **n'est pas** une clé d'objet (80 valeurs distinctes
  pour 2 701 jobs et 80 workspaces ; 96 pour 4 212 notebooks) : c'est un identifiant de **pool
  serverless par workspace**. Aucune page ne peut être construite dessus — à démentir en revue
  si Databricks en change la sémantique.
- `job_run_timeline.compute_ids` **ne peut pas** servir de discriminant serverless : la
  serverless-ité vient de `billing.usage` puis se joint sur `job_id`, jamais l'inverse. La colonne
  s'appelle `compute_ids` (et non `compute[]`). Le **88,5 %** publié auparavant, hérité du spike
  (`proposition.md:283`, « 157 593 / 178 003 lignes »), n'est **reproductible sur aucun périmètre**
  identifiable — remesures du 2026-09-10 : **97,0 %** sur la source complète (6 465 894 / 6 668 570),
  **94 à 95 %** sur toute fenêtre de 1, 7, 30 ou 90 jours, et en curated **95,3 % aws contre
  59,3 % azure** (75,8 % bi-cloud) ; aucun de ces périmètres ne fait 178 003 lignes non plus. Le
  chiffre est donc à retirer, mais **la conclusion se renforce** : le taux est haut partout, et
  surtout il **dépend du cloud** dans un rapport de 1,6× — un taux global unique n'a aucun sens sur
  une page bi-cloud. Au grain **tâche**, `job_task_run_timeline.compute_ids` n'est vide que sur
  **16,2 %** de 23 360 757 lignes : là, ce qui interdit l'usage n'est plus l'absence mais la nature
  — la colonne rend des **identifiants**, jamais un *type*, donc une jointure de plus reste
  nécessaire. Contraste utile : côté DLT, `pipeline_update_timeline.compute.type` est renseigné à
  **100 %**, et c'est ce qui rend FR-015 possible.
- **La population DLT est majoritairement azure, et azure n'a pas de compute classique** *(mesuré
  après le premier run du 2026-09-10 — inconnu avant, la partie azure étant ingérée par JDBC
  cross-tenant et donc non interrogeable depuis les system tables locales)*. Sur la fenêtre de
  backfill de 30 jours : **86 174 updates azure sur 10 workspaces contre 41 466 aws sur 42**, soit
  **67,5 %** du périmètre côté azure, et azure est **serverless à 99,97 %** (23 updates
  classiques). Trois conséquences portées par SC-008 et SC-008b : (1) toute mesure antérieure de
  ce spike ne décrit qu'**un tiers** du périmètre, sans être fausse pour autant ; (2) le
  comparatif serverless / classique n'a de dénominateur que sur **aws** ; (3) un taux serverless
  bi-cloud (4,86 %) est une moyenne de deux régimes — 1,99 % aws, 5,97 % azure — pesée à 72 % par
  azure. Azure est aussi bien moins périodisée (1,0048 ligne par update contre 1,0399) : le piège
  du `COUNT(*)` y existe mais y est quatre fois plus faible.
- Le commentaire de `warehouse_utilization_daily.py:30-33` qui justifie de préférer `STARTING`
  parce que `RUNNING` serait mal journalisé en serverless est **périmé** : `RUNNING` est émis
  55 886 fois sur 393 warehouses. Sans conséquence — le choix reste valide — mais le
  commentaire doit être corrigé pour ne pas égarer le prochain lecteur.
- Le grain retenu pour les surfaces à clé est **l'objet** (`job_id`, `warehouse_id`,
  `notebook_id`…), pas l'exécution (`job_run_id`) : le `job_run_id` alimente `run_count` et
  l'histogramme $/run, il n'entre pas dans le grain.
- Les valeurs de référence des Success Criteria sont celles du **2026-09-09**. Si les chiffres
  bougent, la table « Contrôles de non-régression » du spike (reprise dans
  `stories/T001.md`) est le jeu à rejouer — un écart y est une mesure à re-documenter, pas
  automatiquement un échec.
