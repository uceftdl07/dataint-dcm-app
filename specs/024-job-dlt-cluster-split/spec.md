# feature : Séparation compute Job cluster / DLT vs All-purpose

**Feature Branch**: `024-job-dlt-cluster-split` — branches filles `{domain}/024-{slug}`
**Work Type**: feature
**Priority**: P2
**Created**: 2026-09-09

**Input**: Je fais un spike sur la gestion job cluster dans DCM : sur la page Compute
Clusters, les job_cluster polluent la page ; les forecast et recommandations tels que
conçus ne supportent pas bien les job clusters. Séparer les compute de type job cluster
des all-purpose, agréger les métriques des job clusters à la maille `job_id`. Même chose
pour les compute DLT (maille `dlt_pipeline_id`). Réf. spike :
[docs/spike/job-dlt-cluster-separation/proposition.md](../../docs/spike/job-dlt-cluster-separation/proposition.md).

## Clarifications

### Session 2026-09-09

- Q: Périmètre nav Compute frontend (US3) ? → **3 onglets complets** (All-purpose /
  Jobs compute / Pipelines DLT). Les tables gold `job_cluster_cost_*` existent déjà mais
  **aucune page front ni endpoint backend job-compute** n'existe — la page Jobs compute est
  donc à créer de bout en bout (backend + frontend) dans cet Epic, au même titre que DLT.
- Q: Gouvernance des compute éphémères (JOB/PIPELINE) ? → **Abandonnée**. Le filtre
  `ALL_PURPOSE` sur `cluster_governance` supprime volontairement la gouvernance des grains
  éphémères (owner tag, version DBR, oversizing peu pertinents sur un cluster recréé à
  chaque run). Pas de gouvernance au grain `job_id` / `dlt_pipeline_id` dans cet Epic.
- Q: Coût des clusters `PIPELINE_MAINTENANCE` dans le rollup DLT ? → **Inclus**, rattachés
  au `dlt_pipeline_id` du pipeline parent (coût total = update + maintenance, cohérent UI).
- Q: Métriques forecast/reco pour `object_type = PIPELINE` ? → **Coût / DBU seulement**
  (`cost_usd`, `dbu_quantity`), miroir exact du grain JOB — pas d'efficacité CPU.

### Session 2026-09-09 — amendement (retour d'usage sur T003 livrée)

Les pages Jobs et Pipelines DLT livrées par T003 n'ont que 2 sous-onglets (Overview / Cost),
lignes non cliquables. Trois décisions ramènent l'itération « efficacité par famille » dans
cet Epic (elle était renvoyée à plus tard, cf. Out of scope) :

- Q: Sous-onglet **Efficiency** sur Jobs et Pipelines DLT ? → **Oui**, au grain stable
  (`job_id` / `dlt_pipeline_id`). L'« Out of scope » initial est **révisé** : l'efficacité
  entre dans cet Epic. La **reliability** par famille, elle, reste hors scope.
  Fondement : `gold_dbx_compute_cluster_efficiency_daily` porte **déjà** les clusters `JOB`
  et `PIPELINE` (le filtre `ALL_PURPOSE` de T001a ne borne que le `_rolling`) — la matière
  première existe, seul le rollup au grain stable manque.
- Q: Quelles métriques d'efficacité au grain éphémère ? → **Jeu adapté**, pas le miroir
  exact des colonnes cluster : `cpu_util_avg_pct`/`p95_pct`, `mem_util_avg_pct`/`p95_pct`,
  `idle_pct`, `uptime_hours` cumulé sur la fenêtre, workers `avg`/`max`, autoscaling,
  `recommended_node_type`,
  `estimated_savings_usd`, `utilization_status`. **Sans `is_zombie`** — un cluster JOB /
  PIPELINE se termine avec son run, « allumé longtemps sans activité » n'y a pas de sens et
  la colonne serait `false` partout. **Sans gouvernance** (C2 inchangé).
- Q: Drill-down sur les lignes Jobs / Pipelines ? → **Oui**, tiroir latéral au grain stable,
  « au même niveau de détail que l'All-purpose **dans la mesure du possible** » : identité,
  coût/DBU de la fenêtre + Δ, efficacité de la fenêtre, tendance coût ≈90 j, tendance
  uptime ≈90 j. **Sans bloc gouvernance** (inexistant à ce grain, C2). Patron réutilisé :
  `compute-cluster-drawer` / `compute-warehouse-drawer` (un tiroir par grain existe déjà).

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

| Stories Jira | 6 (3 initiales + 3 de l'amendement 2026-09-09) |
|---|---|
| Mode | one_per_domain (l'amendement ajoute une 2ᵉ Story par domaine) |
| Domaines avec ticket | frontend, backend, dataeng |

## Contexte

Le compute Databricks est présenté dans DCM sur une page **Clusters** unique alimentée par
les tables gold `gold_dbx_compute_cluster_*_rolling` / `_governance`. Ces tables listent
**tous** les `cluster_type` (`ALL_PURPOSE`, `JOB`, `PIPELINE`, `OTHER`).

Or seuls les clusters **All-purpose** (`cluster_source` = UI/API) sont persistants : leur
`cluster_id` est stable dans le temps. Les clusters **JOB** (éphémères, recréés à chaque
run) et **PIPELINE / DLT** (recréés à chaque update) portent un `cluster_id` neuf à chaque
exécution. Conséquences observées :

- **Pollution** de la page Clusters par des centaines de `cluster_id` éphémères à vie
  courte, non actionnables (le cluster n'existe plus au run suivant).
- **Forecast** (`ai_forecast`) inexploitable sur ces clusters : la série d'entraînement se
  réduit à 0–1 point par `cluster_id` éphémère.
- **Recommandations** produites au grain cluster éphémère, sans valeur (rightsizing d'un
  cluster qui n'existe plus).

Le pipeline traite **déjà partiellement** le cas JOB : `gold_dbx_compute_job_cluster_cost_daily`
+ `_rolling` agrègent le coût à la maille stable `job_id`, et le forecast **exclut déjà**
`cluster_type = 'JOB'` du grain CLUSTER. Mais (1) les tables **liste** ne filtrent pas
`cluster_type` (d'où la pollution résiduelle), et (2) le cas **DLT** n'a **aucun** rollup
équivalent — les clusters PIPELINE polluent comme les JOB avant leur rollup.

État cible : **3 familles de compute, 3 grains** — `ALL_PURPOSE` au grain `cluster_id`
(page Clusters purgée), `JOB` au grain `job_id` (existant), `PIPELINE` au grain
`dlt_pipeline_id` (nouveau rollup, miroir du module job). La clé DLT `dlt_pipeline_id` est
portée nativement par `billing_usage.usage_metadata.dlt_pipeline_id` (aucun lineage requis,
contrairement au JOB).

## Dependency Analysis

Vérification code (Q6 de l'intake). Backend étant déjà dans le Ticket Plan, le tableau est
informatif — pas de flow de gap.

| Besoin | Domaine requis | Preuve (fichier) | Résolution |
|--------|----------------|------------------|------------|
| `cluster_type` dérivé en gold | dataeng | `pipelines/gold_dbx_compute/sql_helpers.py` — `cluster_type_case_expr` (JOB/ALL_PURPOSE/PIPELINE/OTHER) | déjà présent, réutilisé |
| Rollup coût maille `job_id` | dataeng | `pipelines/gold_dbx_compute/job_cluster_cost_daily.py` + `_rolling` | déjà présent, modèle du rollup DLT |
| Forecast exclut JOB du grain cluster | dataeng | `pipelines/gold_dbx_compute/forecast.py` — `WHERE cluster_type != 'JOB'` | à généraliser (exclure PIPELINE + purge liste) |
| Tables liste filtrent `cluster_type` | dataeng | `cluster_cost_rolling` / `_efficiency_rolling` / `governance` — aucun filtre | **à ajouter** (filtre `ALL_PURPOSE`) |
| Backend applique `cluster_type` par défaut | backend | `app/api/services/compute_metrics_clusters.py` — `cluster_type` en column_filter optionnel seulement | **à durcir** + nouveaux services pipeline |
| Rollup DLT (grain `dlt_pipeline_id`) | dataeng | aucun `pipeline_cost_*` dans `gold_dbx_compute` | **à créer** |
| `system.lakeflow.pipelines` ingéré | dataeng | `pipelines/system_tables/specs.py` inputs — pas de `pipelines` | **à ingérer** (prérequis nom lisible DLT) |

## Prerequisites

- **Small branches / small PRs** : 3 branches filles, une par domaine. La branche DataEng
  est elle-même séquencée (purge liste → ingestion `pipelines` → rollup DLT → forecast/reco)
  pour rester en petits diffs ; découper en plusieurs PR si nécessaire.
- Intake + domain scope confirmés (`intake.json` / `domain-scope.json`).
- Dépendances bloquantes de Dependency Analysis : aucune externe. La branche Backend
  dépend des tables gold DataEng (purge + rollup DLT) ; la branche Frontend dépend des
  endpoints Backend. Ordre de livraison : **DataEng → Backend → Frontend**, répété à
  l'identique sur le second lot de l'amendement (**T004 → T005 → T006**).
- `[NEEDS CLARIFICATION]` levés (recommandé avant l'étape `plan`).

## User stories

### User Story 1 — DataEng : purge des pages cluster + rollup DLT (Priority: P1)

Producteur du socle gold. Filtrer les tables liste sur `ALL_PURPOSE`, créer le rollup DLT
`gold_dbx_compute_pipeline_cost_daily` + `_rolling` au grain `dlt_pipeline_id`, ingérer
`system.lakeflow.pipelines` pour le nom lisible, et étendre forecast/reco au type PIPELINE.

**Why this priority** : socle dont dépendent Backend puis Frontend ; débloque aussi
immédiatement la purge visuelle des pages.
**Independent Test** : requêter les tables gold — `cluster_*_rolling` ne contient plus que
`ALL_PURPOSE` ; `pipeline_cost_rolling` contient une ligne par `dlt_pipeline_id` × fenêtre.

**Acceptance Scenarios**

1. **Given** des clusters JOB et PIPELINE dans `cluster_cost_daily`, **When** on lit
   `gold_dbx_compute_cluster_cost_rolling` / `_efficiency_rolling` / `governance`,
   **Then** aucune ligne `cluster_type` ≠ `ALL_PURPOSE`.
2. **Given** de la facturation `billing_usage` avec `usage_metadata.dlt_pipeline_id` non
   nul, **When** le job gold s'exécute, **Then** `gold_dbx_compute_pipeline_cost_daily`
   agrège `cost_usd` / `dbu_quantity` par `(cloud_provider, workspace_id, dlt_pipeline_id,
   period_start)` sans double-comptage avec `cluster_cost_daily`.
3. **Given** `gold_dbx_compute_forecast_daily`, **Then** `object_type = 'PIPELINE'` est
   projeté depuis le rollup DLT et le grain CLUSTER exclut JOB **et** PIPELINE.

### User Story 2 — Backend : filtre dur ALL_PURPOSE + endpoints job & pipeline (Priority: P2)

Exposer les 3 familles séparément : durcir `cluster_type = 'ALL_PURPOSE'` sur les services
cluster, ajouter les services / routes **compute job** (grain `job_id`, tables gold déjà
existantes mais non exposées) **et compute pipeline** (grain `dlt_pipeline_id`), étendre
forecast/reco à `object_type = PIPELINE`, et les schémas dcm-commons associés.

**Why this priority** : dépend des tables gold (US1) ; prérequis de l'UI (US3).
**Independent Test** : appeler les endpoints — la liste clusters ne renvoie que
`ALL_PURPOSE` ; l'endpoint job renvoie le grain `job_id`, l'endpoint pipeline le grain
`dlt_pipeline_id`.

**Acceptance Scenarios**

1. **Given** l'API `/api/v1/databricks/compute/clusters`, **When** on liste sans filtre,
   **Then** aucun élément `cluster_type` ≠ `ALL_PURPOSE`.
2. **Given** les nouveaux endpoints compute job et compute pipelines, **When** on les
   requête, **Then** ils renvoient coût / DBU par `job_id` (avec `job_name`) resp. par
   `dlt_pipeline_id` (avec `pipeline_name`, ou l'id à défaut).
3. **Given** `/compute/forecast?object_type=PIPELINE`, **Then** la série DLT est renvoyée.

### User Story 3 — Frontend : nav Compute à 3 onglets (Priority: P3)

Séparer la navigation Compute en **All-purpose clusters** / **Jobs compute** /
**Pipelines (DLT) compute**, chacun branché sur son endpoint, avec forecast/reco par
famille.

**Why this priority** : couche de présentation ; dépend des endpoints Backend (US2).
**Independent Test** : la page Clusters n'affiche plus de compute éphémère ; les onglets
Jobs et Pipelines listent leur grain respectif.

**Acceptance Scenarios**

1. **Given** la nav Compute, **When** l'utilisateur ouvre l'onglet Clusters, **Then**
   seuls des clusters All-purpose sont listés.
2. **Given** l'onglet Pipelines (DLT), **When** il s'ouvre, **Then** les pipelines DLT sont
   listés au grain `dlt_pipeline_id` avec leur coût.

### User Story 4 — DataEng : rollup efficacité au grain job / pipeline (Priority: P4)

Amendement. Produire l'efficacité (CPU/mémoire, idle, uptime, rightsizing) aux grains stables
`job_id` et `dlt_pipeline_id`, par agrégation de `gold_dbx_compute_cluster_efficiency_daily`
restreint aux clusters `JOB` resp. `PIPELINE`, avec la résolution
`cluster_id → job_id` / `cluster_id → dlt_pipeline_id`.

**Why this priority** : socle des deux tasks suivantes ; sans table au grain stable, ni
l'onglet Efficiency ni le bloc efficacité du tiroir n'ont de source.
**Independent Test** : requêter les tables gold — `job_efficiency_rolling` porte une ligne par
`(job_id, window_days)`, `pipeline_efficiency_rolling` une ligne par
`(dlt_pipeline_id, window_days)`, avec des p95 dans `[0, 100]`.

**Acceptance Scenarios**

1. **Given** des clusters `JOB` dans `cluster_efficiency_daily`, **When** le job gold
   s'exécute, **Then** `gold_dbx_compute_job_efficiency_daily` agrège CPU/mémoire, idle et
   uptime par `(cloud_provider, workspace_id, job_id, period_start)`, les p95 étant
   **recalculés depuis les histogrammes** fusionnés (jamais une moyenne de percentiles).
2. **Given** des clusters `PIPELINE`, **Then** `gold_dbx_compute_pipeline_efficiency_daily`
   fait de même par `(cloud_provider, workspace_id, dlt_pipeline_id, period_start)`.
3. **Given** les `_rolling` correspondants, **Then** ils exposent une ligne par grain ×
   fenêtre (`ROLLING_WINDOWS`), fenêtre précédente en `NULL` (jamais `0`) quand elle est vide.
4. **Given** un pipeline **serverless** (aucune ligne `node_timeline`), **Then** il est
   absent de la table efficacité — sans perdre sa ligne de coût.

### User Story 5 — Backend : endpoints efficiency + détail/tendances job & pipeline (Priority: P5)

Amendement. Exposer l'efficacité et le drill-down des deux familles : `/compute/jobs/efficiency`,
`/compute/pipelines/efficiency`, plus les routes détail (`/compute/jobs/{job_id}`,
`/compute/pipelines/{dlt_pipeline_id}`) et tendances (`/cost-trend`, `/uptime-trend`),
calquées sur les routes cluster homologues.

**Why this priority** : dépend de US4 pour l'efficacité ; prérequis de US6.
**Independent Test** : appeler chaque route — l'efficacité renvoie le grain stable ; le détail
renvoie les blocs `cost` / `efficiency` (`governance` absent) ; les tendances renvoient une
série ≈90 j au grain de granularité demandé.

**Acceptance Scenarios**

1. **Given** `/compute/jobs/efficiency`, **When** on la requête, **Then** elle renvoie le grain
   `job_id` avec `job_name`, sans champ `is_zombie`.
2. **Given** `/compute/jobs/{job_id}` sur un id inconnu du périmètre, **Then** 404 (pas un
   corps vide à 200), aligné sur `/clusters/{cluster_id}`.
3. **Given** `/compute/pipelines/{dlt_pipeline_id}/cost-trend`, **Then** la série vient de
   `pipeline_cost_daily` sur ≈90 j, granularité `day`/`week`/`month`.

### User Story 6 — Frontend : onglet Efficiency + lignes cliquables sur Jobs & Pipelines (Priority: P6)

Amendement. Ajouter le 3ᵉ sous-onglet **Efficiency** aux pages `ComputeJobs` et
`ComputePipelines`, et rendre les lignes des trois sous-onglets cliquables vers un tiroir de
détail au grain stable.

**Why this priority** : couche de présentation ; dépend de US5.
**Independent Test** : sur chaque page, les 3 sous-onglets sont présents ; un clic sur une
ligne ouvre le tiroir renseigné, fermable au clavier.

**Acceptance Scenarios**

1. **Given** la page Job clusters, **When** elle s'ouvre, **Then** les sous-onglets sont
   Overview / Cost / **Efficiency**.
2. **Given** une ligne de n'importe lequel des 3 sous-onglets, **When** l'utilisateur clique,
   **Then** un tiroir s'ouvre avec identité, coût/DBU de la fenêtre, efficacité, tendance coût
   et tendance uptime — **sans** bloc gouvernance.
3. **Given** un job dont aucune ligne d'efficacité n'existe (couverture `node_timeline`),
   **Then** le tiroir affiche « — » sur ce bloc et reste utilisable (jamais d'écran cassé).

## Acceptance Criteria

1. **Given** les 3 familles de compute, **When** un utilisateur navigue, **Then** JOB et
   PIPELINE n'apparaissent plus dans la vue Clusters et disposent chacun de leur vue
   agrégée à la maille stable.
2. **Given** forecast et recommandations, **Then** ils ne sont plus produits au grain
   cluster éphémère (JOB/PIPELINE exclus du grain CLUSTER, PIPELINE projeté à son grain).
3. **Given** les pages Jobs et Pipelines DLT, **Then** elles offrent le même parcours
   d'analyse que la page All-purpose — liste, coût, **efficacité**, **détail au clic** —
   moins la gouvernance, inexistante au grain éphémère.
4. Gates de chaque package verts (lint → types → tests → build).

## Out of scope (cet Epic)

- Rollup **reliability** (taux d'échec, durée des runs) au grain `job_id` / `dlt_pipeline_id`
  — itération ultérieure. ~~Efficacité~~ : **révisé par l'amendement du 2026-09-09**,
  l'efficacité (CPU/mémoire/idle/rightsizing) entre dans cet Epic via T004–T006.
- Serverless compute (SQL serverless, jobs serverless) — traité hors de ce découpage
  cluster_source, malgré le nom de la branche de travail.
- **Gouvernance au grain éphémère** (JOB / PIPELINE) : abandonnée. Le filtre `ALL_PURPOSE`
  sur `cluster_governance` retire volontairement owner tag / version DBR / oversizing des
  grains éphémères. Pas de rollup gouvernance au grain `job_id` / `dlt_pipeline_id`.
- DevOps / QA : aucun ticket (pas de changement CI/infra ni de fixture transverse dédiée).

## Work Breakdown (preview)

| ID | Domain | Summary | Ticket |
|----|--------|---------|--------|
| T001 | DataEng | Purge liste (`ALL_PURPOSE`) + rollup DLT `pipeline_cost_daily`/`_rolling` (grain `dlt_pipeline_id`) + ingest `system.lakeflow.pipelines` + forecast/reco `PIPELINE` | ✅ |
| T002 | Backend | Filtre dur `ALL_PURPOSE` sur services cluster + endpoints/schemas compute **job** (grain `job_id`) **et** compute pipeline (grain `dlt_pipeline_id`) + forecast/reco `object_type=PIPELINE` | ✅ |
| T003 | Frontend | Nav Compute 3 onglets (All-purpose / Jobs / Pipelines DLT) + forecast/reco par famille | ✅ |
| T004 | DataEng | Rollup **efficacité** `job_efficiency_daily`/`_rolling` (grain `job_id`) + `pipeline_efficiency_daily`/`_rolling` (grain `dlt_pipeline_id`) depuis `cluster_efficiency_daily` | ⏳ |
| T005 | Backend | Endpoints `jobs/efficiency`, `pipelines/efficiency`, détail `jobs/{job_id}` / `pipelines/{dlt_pipeline_id}` + tendances coût & uptime (≈90 j) | ⏳ |
| T006 | Frontend | Sous-onglet **Efficiency** sur Jobs & Pipelines + lignes cliquables → tiroir de détail au grain stable | ⏳ |

## Requirements & Success Criteria

- **FR-001** : Les tables gold liste (`cluster_cost_rolling`, `cluster_efficiency_rolling`,
  `cluster_governance`) ne contiennent que `cluster_type = 'ALL_PURPOSE'`.
- **FR-002** : `gold_dbx_compute_pipeline_cost_daily` agrège coût / DBU par
  `(cloud_provider, workspace_id, dlt_pipeline_id, period_start)` depuis
  `curated_dbx_billing_usage` filtré `usage_metadata.dlt_pipeline_id IS NOT NULL`, sans
  double-comptage avec `cluster_cost_daily`. Le coût des clusters `PIPELINE_MAINTENANCE`
  est **inclus**, rattaché au `dlt_pipeline_id` du pipeline parent (coût total du pipeline).
- **FR-003** : `gold_dbx_compute_pipeline_cost_rolling` matérialise une ligne par
  `dlt_pipeline_id` × fenêtre (mêmes `ROLLING_WINDOWS` que le module job).
- **FR-004** : `system.lakeflow.pipelines` est ingéré en `curated_dbx_lakeflow_pipelines`
  pour fournir `pipeline_name` (fallback : `dlt_pipeline_id`).
- **FR-005** : `gold_dbx_compute_forecast_daily` exclut JOB **et** PIPELINE du grain
  CLUSTER et ajoute `object_type = 'PIPELINE'` depuis le rollup DLT, sur les seules
  métriques **`cost_usd` et `dbu_quantity`** (miroir du grain JOB, pas d'efficacité CPU).
- **FR-006** : `gold_dbx_compute_recommendations` ne produit plus de reco au grain cluster
  éphémère (JOB/PIPELINE exclus du grain CLUSTER).
- **FR-007** : Les services / routes backend cluster appliquent `cluster_type = 'ALL_PURPOSE'`
  en prédicat dur (plus seulement en filtre optionnel).
- **FR-008** : Deux endpoints sont exposés — compute **job** (grain `job_id`, tables gold
  `job_cluster_cost_*` existantes mais non encore branchées) et compute **pipeline** (grain
  `dlt_pipeline_id`) — avec les schémas dcm-commons correspondants.
- **FR-009** : Le forecast backend accepte `object_type = PIPELINE`.
- **FR-010** : La nav Compute frontend expose 3 onglets (All-purpose clusters / Jobs
  compute / Pipelines DLT compute), chacun branché sur son endpoint.

Amendement 2026-09-09 (T004–T006) :

- **FR-011** : `gold_dbx_compute_job_efficiency_daily` agrège
  `gold_dbx_compute_cluster_efficiency_daily` restreint `cluster_type = 'JOB'` au grain
  `(cloud_provider, workspace_id, job_id, period_start)`, via la résolution
  `cluster_id → job_id` de `curated_dbx_job_task_run_timeline` (même CTE que
  `job_cluster_cost_daily`).
- **FR-012** : `gold_dbx_compute_pipeline_efficiency_daily` fait de même pour
  `cluster_type = 'PIPELINE'` au grain
  `(cloud_provider, workspace_id, dlt_pipeline_id, period_start)`. La résolution
  `cluster_id → dlt_pipeline_id` se fait par couples distincts issus de
  `curated_dbx_billing_usage` (**R7 tranchée le 2026-09-09** : 99,84 % de couverture, unicité
  vérifiée, 0 désaccord sur 61 826 clusters contre `system.lakeflow.pipeline_update_timeline`) ;
  les pipelines serverless, sans `node_timeline`, restent absents de l'efficacité.
- **FR-013** : Les moyennes (`cpu_util_avg_pct`, `mem_util_avg_pct`, `idle_pct`) sont
  **pondérées par `uptime_hours`** ; les p95 (`cpu_util_p95_pct`, `mem_util_p95_pct`) sont
  **recalculés depuis les histogrammes fusionnés** (`cpu_util_hist` / `mem_util_hist`) —
  jamais une moyenne de percentiles. `uptime_hours` est **cumulé** sur tous les runs du grain
  dans la fenêtre.
- **FR-014** : Les `_rolling` correspondants matérialisent une ligne par grain × fenêtre
  (`ROLLING_WINDOWS`), avec fenêtre précédente à `NULL` (jamais `0`) quand elle est vide.
- **FR-015** : Les tables efficacité au grain éphémère n'exposent **pas** `is_zombie`
  (signal sans sens sur un cluster qui se termine avec son run) et **aucun** champ de
  gouvernance (C2 inchangé).
- **FR-016** : Le backend expose `/compute/jobs/efficiency` et `/compute/pipelines/efficiency`
  (pagination serveur, recherche, tri — miroir des routes `cost` existantes).
- **FR-017** : Le backend expose `/compute/jobs/{job_id}` et
  `/compute/pipelines/{dlt_pipeline_id}` renvoyant les blocs `cost` + `efficiency` de la
  fenêtre (**sans** bloc `governance`), plus les tendances `cost-trend` et `uptime-trend`
  sur ≈90 j aux granularités `day` / `week` / `month`. Un id hors périmètre → **404**.
- **FR-018** : Les pages `ComputeJobs` et `ComputePipelines` exposent un 3ᵉ sous-onglet
  **Efficiency** et rendent les lignes des 3 sous-onglets cliquables vers un tiroir de détail
  au grain stable, réutilisant le patron `compute-cluster-drawer`.
- **SC-001** : 0 ligne `cluster_type` ≠ `ALL_PURPOSE` renvoyée par l'endpoint liste
  clusters (mesuré sur données réelles AWS + Azure).
- **SC-002** : Chaque `dlt_pipeline_id` facturé sur la période apparaît exactement une fois
  par fenêtre dans `pipeline_cost_rolling`.
- **SC-003** : Somme `cost_usd` de `pipeline_cost_daily` = somme `cost_usd` de
  `cluster_cost_daily` restreint `cluster_type = 'PIPELINE'` (contrôle anti-écart du rollup).
- **SC-004** : `job_efficiency_rolling` et `pipeline_efficiency_rolling` renvoient exactement
  une ligne par grain × `window_days`, avec `cpu_util_p95_pct` / `mem_util_p95_pct` dans
  `[0, 100]` et `uptime_hours > 0` (mesuré sur données réelles AWS + Azure).
- **SC-005** : Le taux de couverture efficacité est **mesuré et documenté** par famille
  (part des `job_id` / `dlt_pipeline_id` facturés qui portent une ligne d'efficacité) ; un
  résidu non couvert est un fait attendu à documenter, pas un échec.
- **SC-006** : Sur chaque page (Jobs, Pipelines), les 3 sous-onglets sont présents et un clic
  sur une ligne de chacun ouvre un tiroir renseigné — vérifié en test et au navigateur.

## Assumptions

- `billing_usage.usage_metadata.dlt_pipeline_id` est présent et fiable pour les deux clouds
  (déjà utilisé implicitement par la facturation Databricks) — à démentir en revue sinon.
- Le mapping `cluster_source` → `cluster_type` de `cluster_type_case_expr` reste la source
  de vérité de la classification (UI/API=ALL_PURPOSE, JOB=JOB, PIPELINE(_MAINTENANCE)=PIPELINE).
- Le grain DLT retenu est `dlt_pipeline_id` (le pipeline), pas `dlt_update_id` (l'update) —
  symétrique au choix `job_id` (le job) plutôt que `job_run_id`.
- **(Amendement)** `gold_dbx_compute_cluster_efficiency_daily` conserve les clusters `JOB` et
  `PIPELINE` : le filtre `ALL_PURPOSE` de T001a ne borne que le `_rolling`. Vérifié dans le
  code ; si un futur changement filtrait aussi le `daily`, T004 perdrait sa source.
- **(Amendement, vérifié)** La résolution `cluster_id → dlt_pipeline_id` n'existait pas (le
  coût DLT vient directement de `usage_metadata.dlt_pipeline_id`), mais `usage_metadata` porte
  aussi `cluster_id` dans la même table curated : le mapping en est dérivé. **Mesuré en dev le
  2026-09-09** (R7) — 99,84 % des clusters `PIPELINE` de l'efficacité sont résolus, unicité à 0
  violation, et accord sans divergence avec la source documentée
  `system.lakeflow.pipeline_update_timeline`. Les pipelines serverless n'auront jamais
  d'efficacité (pas de `node_timeline`) ; 8 clusters AWS non résolus sont exclus, pas rattachés.
