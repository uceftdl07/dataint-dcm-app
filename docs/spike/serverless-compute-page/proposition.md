# Spike — Page « Serverless compute » dans DCM

> **Question posée** : le serverless est aujourd'hui majoritaire. Qu'est-ce qu'on peut
> *réellement* afficher de pertinent, et sous quelle forme ?
>
> **Toutes les valeurs de ce document sont mesurées**, pas estimées : compte Databricks
> AWS `dbc-223d60ab-45bd` (128 workspaces), `system.billing.usage` ×
> `system.billing.list_prices`, fenêtre **`usage_date` du 2026-08-10 au 2026-09-09 inclus
> (31 jours, notée « 30 j »)**. Coûts en $ **prix de liste**
> (`pricing.effective_list.default`), hors remise contractuelle — donc comparables entre
> eux, pas au montant facturé. Requêtes reproductibles en [annexe](#annexe--requêtes-de-mesure).
>
> **Révision du 2026-09-10** : toutes les mesures de la v1 ont été rejouées. Neuf d'entre
> elles étaient fausses ou construites sur un prédicat invalide, et sont corrigées ici —
> le détail est en [§0](#0-errata-de-la-v1). Les conclusions de structure (§5) et le
> séquencement tiennent ; les chiffres de la matrice d'attribution (§6 bloc 2), du
> contraste DLT (§3) et de la correction warehouse (§10.3) changent significativement.
> Ajout d'un [périmètre bi-cloud](#️-périmètre-de-mesure--tout-ce-document-est-mono-cloud-aws) :
> ce document ne mesure qu'AWS, alors que DCM est bi-cloud — Azure ajoute ≈ 104 k$ / 30 j
> de serverless, avec un mix nettement plus « jobs » et « apps ».
>
> **Corrections d'implémentation (spec [025](../../../specs/025-serverless-compute-page/), même
> date)** : §10.1 et §10.4 ont été **rejoués sur tout l'historique du gold déployé** au moment
> de les corriger dans le code, et deux affirmations de cette révision se sont révélées fausses
> — dont une qui recommandait un renommage à ne pas faire. §10.4 a dû être corrigé **deux
> fois** : la première réécriture posait un diagnostic tout aussi faux, démenti par la mesure au
> grain de la table cible. Détail en
> [§0 bis](#0-bis--errata-de-la-v2-relevés-en-implémentant). Le reste du document n'est pas
> remesuré : ses chiffres restent ceux de la fenêtre de 30 j annoncée ci-dessus.
>
> Références code : [gold_dbx_compute](../../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/) ·
> [sql_helpers.py](../../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/sql_helpers.py) ·
> [navigation.ts](../../../packages/dcm-frontend/src/config/navigation.ts) ·
> spikes voisins : [job-dlt-cluster-separation](../job-dlt-cluster-separation/proposition.md) ·
> [compute-metrics-definition](../compute-metrics-definition/compute_page.md)

---

## 0. Errata de la v1

À lire avant le reste si la v1 a déjà servi de base à une décision.

| # | Affirmation v1 | Réalité mesurée | Impact |
|---|---|---|---|
| 1 | « 10 grains », `Endpoint IA` keyé sur `endpoint_id`, 1 035 objets, 112 WS | **11 surfaces.** GENIE (15 850 $, 5,6 % du serverless) n'a **aucune clé d'objet** — 0 `endpoint_id`. La surface `AI_ENDPOINT` réelle = 12 733 $, **152** `endpoint_id`, **29** WS | §2 restructuré ; GENIE rejoint les surfaces sans clé |
| 2 | « $ non attribuables : 10 672 $ (3,7 %) » = NETWORKING + plateforme auto | Confusion de deux notions. **Sans clé d'objet : 26 533 $ (9,3 %)**. **Sans aucun propriétaire : 5 875 $ (2,06 %)**. La plateforme auto est attribuée à 100 % (`run_as`) et taguée à 95 % | KPI du bloc 1 et bloc 2 refaits |
| 3 | Matrice d'attribution sur `{custom_tags, budget_policy_id, run_as}` → Apps 0 %, SQL 40 %, IA 3 % | `run_as` n'est pas le bon champ partout : **SQL → `owned_by` (100 %)**, **Apps → `created_by` (100 %)**, IA → mixte. Avec `COALESCE(run_as, owned_by, created_by)` : **100 % partout sauf LAKEBASE (5 %) et NETWORKING (0 %)** | conclusion du bloc 2 inversée |
| 4 | « 21 % couvert par une budget policy » présenté en KPI global | 21 % est la valeur **de la surface JOB**. Global serverless = **8,4 %** | KPI du bandeau corrigé |
| 5 | DLT : « srvls 37 810 updates, 7,0 %, médiane 94 s ; classic 7 187, 24,3 %, 798 s » | `pipeline_update_timeline` est **périodisée à l'heure**, pas une ligne par update. Par `update_id` : **srvls 35 572 updates / 7,2 % / p50 90 s / p95 461 s ; classic 6 245 / 27,2 % / p50 832 s / p95 3 284 s** | §3 et §4 ; contrainte d'implémentation (agréger par `update_id`) |
| 6 | `query.history` : « attribution 90 % job, 2 % notebook, 8 % non attribué » | `query_source.job_info IS NOT NULL` est **toujours vrai** (struct non-NULL à champs NULL). Sur les feuilles : `job_info.job_id` **89,9 %**, `notebook_id` **80,3 %** — les deux **se recouvrent** (tâche de type notebook dans un job). `notebook_id` ne désigne donc **pas** de l'interactif | §4 ; interdit d'attribuer le notebook serverless via `query.history` seul |
| 7 | Jobs : « 379 en `STANDARD` (2 235 $) » sur 2 701 | **345 en `STANDARD` (2 025 $)** + 34 panachés (408 $) + 2 322 `PERFORMANCE_OPTIMIZED` (57 589 $) = 2 701. La v1 comptait les panachés deux fois | §3, §6 bloc 3 |
| 8 | $/run : « p50 0,158 $, p95 1,98 $ » | **p50 0,125 $ · p95 1,49 $ · p99 14,88 $ · moyenne 0,611 $ · max 1 345 $.** La moyenne est 4× le p95 : la queue porte l'essentiel. **62 runs > 50 $ = 13,8 % de la dépense job** | §6 bloc 3 ; bornes d'histogramme (§9) |
| 9 | Warehouses : « l'efficience est fausse pour 93 % de la dépense SQL, `warehouse_events` n'est pas journalisé en serverless » | **Faux : les événements sont là** — 53 615 sessions `STARTING`→`STOPPED` / 30 j sur 380 des 398 warehouses serverless, et `RUNNING` est émis 55 886 fois. Le défaut réel est ailleurs et bien plus grave : `idle_pct` **est** calculable (médiane **96,3 %**), il dépasse le seuil de 60 % sur **95,6 % des jours-warehouse**, et `estimated_savings_usd` fabrique donc **≈ 49 100 $ d'économies sur 15 j** (353 warehouses marqués `OVER`) qui **ne peuvent pas être réalisées** — en serverless l'idle n'est pas facturé | §10.3 réécrit |

Deux ajouts qui n'étaient pas dans la v1 et qui changent l'implémentation :

- **`object_id` est NULL sur 9,3 % de la dépense serverless** (GENIE, plateforme auto,
  NETWORKING). La v1 le met en clé de merge sans le dire : le `<=>` null-safe de
  `merge_into_table` fusionnerait ces lignes en une. Sentinelle obligatoire — cf. §9.
- **Les noms sont déjà dans `billing.usage`** (`usage_metadata.job_name` 2 305/2 701,
  `notebook_path` 4 342, `app_name` 52/55) : la résolution de `object_name` n'a pas
  besoin d'un join pour ces trois surfaces, seulement d'un repli.

### 0 bis — Errata de la v2, relevés en implémentant

Corrections apportées pendant l'implémentation de T3 (lot §10.1 + §10.4), mesurées sur
**tout l'historique du gold déployé** et non plus sur la fenêtre de 30 j. Elles ne changent
ni le séquencement ni les conclusions de structure, mais l'une d'elles **invalide un
correctif recommandé**. L'entrée 11 a dû être corrigée **deux fois** : la v3 avait remplacé le
diagnostic faux de la v2 par un autre diagnostic faux — la ligne 11 bis est la mesure retenue.

| # | Affirmation antérieure | Réalité mesurée le 2026-09-10 | Impact |
|---|---|---|---|
| 10 | §10.1 (v2) : « 4 produits renseignent `dlt_pipeline_id` ; 2 316 $ / 30 j sur 364 pipelines » | **6 produits.** `LAKEFLOW_CONNECT` (9 873,47 $, 3ᵉ poste) et `AI_FUNCTIONS` manquaient. Sur l'historique : **113 085 lignes / 37 100,15 $** de faux DLT à supprimer — et surtout **`SQL` porte 10 499 identifiants de pipelines contre 9 298 pour `DLT`**, donc plus de la moitié de la population de la page DLT n'est pas du DLT | §10.1 réécrit ; l'argument devient la **population**, pas le montant |
| 11 | §10.4 (v2) : « `sku_group = 'serverless'` est un contresens, piège de nommage de SKU appliqué dans le code → renommer en `sku_family` » | **Diagnostic faux.** Les SKU en cause sont `*_SERVERLESS_REAL_TIME_INFERENCE_*` : le libellé dit **vrai**, ces lignes *sont* du serverless | Renommage `sku_family` **abandonné** : `sku_group` est un contrat plein-stack (URL, filtres, 3 packages), et le filtre produit rend la valeur improductible sans rien casser |
| 11 bis | §10.4 (v3) : « la table **ingère des endpoints de serving** comme des clusters ; **1 286,28 $** sur 129 lignes, qui seront **retirées** » | **Les trois affirmations sont fausses.** Les 3 963 `cluster_id` d'endpoints sont absents de `curated_dbx_compute_clusters`, donc **déjà** écartés par le `WHERE cluster_type <> 'OTHER'` — ce garde-fou masquait le défaut. Le vrai défaut : **791,01 $** de facturation serving / IA rattachée à **97 clusters réels** sur **134 jours-cluster mixtes**. **0 ligne retirée**, 134 corrigées en valeur (les 129 étiquetées `serverless` deviennent 104 `classic` + 25 `photon`) | §10.4 réécrit une 2ᵉ fois. `cluster_cost_daily` n'a **aucune orpheline** (vérifié sur les 5 389 217 lignes) : `full_refresh` suffit, pas de purge — au contraire de §10.1. `sku_group = 'serverless'` n'est **pas** un marqueur du défaut, `MAX(CASE …)` l'agrégeant sur le jour-cluster |

Les deux défauts n'en sont qu'**un seul, appliqué deux fois** : une population définie par un
identifiant de `usage_metadata` sans prédicat de `billing_origin_product`. Mais **leur
remédiation diffère**, et c'est le piège de ce lot : côté pipelines le filtre laisse
113 085 lignes que le recalcul ne produit plus — l'upsert ne les supprime pas, il faut une
purge explicite ; côté clusters il n'en laisse **aucune**, les jours-cluster touchés étant
mixtes, et un `full_refresh` suffit à en corriger la valeur. Appliquer la même recette aux deux
donnerait dans un cas une table encore fausse, dans l'autre un mécanisme de suppression armé
pour rien.

---

## 1. Le constat qui justifie la page

`product_features.is_serverless` est le discriminant **officiel et exact** (pas une
heuristique de nom de SKU — cf. §4) :

| Bucket | $ / 30 j | Part |
|---|---:|---:|
| `is_serverless = true` | 250 466 | **69,6 %** |
| produit serverless-only, flag `NULL` (GENIE, MODEL_SERVING, VECTOR_SEARCH, LAKEBASE, NETWORKING, AI_*, LAKEFLOW_CONNECT, SUPERVISOR_AGENT, AGENT_EVALUATION) | 34 878 | **9,7 %** |
| `is_serverless = false` (classic) | 74 687 | 20,7 % |
| **Total dépense DBU** | **360 039** | 100 % |

Les trois buckets **partitionnent exactement** `system.billing.usage` : aucune ligne ne
tombe hors des trois (vérifié — cf. contrôle §annexe). « Total dépense DBU » et pas
« total compute » : `system.billing.usage` ne contient que des produits facturés en DBU,
pas le stockage ni les egress hors NETWORKING.

**Le serverless représente 79,3 % de la dépense DBU**, alors que les pages Compute de
DCM sont construites sur le grain `cluster_id` — qui n'existe pas en serverless.
Conséquence mesurée au §2 : **136 674 $ / 30 j, soit 38,0 % de la dépense totale, n'est
visible nulle part** dans l'outil, et la seule surface serverless réellement couverte
(SQL warehouse, 48,7 % du serverless) l'est avec un diagnostic d'efficience qui produit
des recommandations impossibles à appliquer (§10.3).

**Nuance à ne pas escamoter** : sur les deux fenêtres de 30 j consécutives, la part
serverless **baisse** — 271 269 / 331 996 = **81,7 %** (30 j au 2026-08-09) contre
**79,3 %** (30 j au 2026-09-09), le classic ayant crû plus vite (+23,0 %) que le
serverless (+5,2 %). La page se justifie par la **masse absolue** non couverte, pas par
une trajectoire d'explosion. Ne pas vendre l'inverse.

### ⚠️ Périmètre de mesure : tout ce document est mono-cloud (AWS)

`system.billing.usage` est **scopé à un compte Databricks**. Les mesures ci-dessus
viennent du compte AWS `dbc-223d60ab-45bd` ; le compte Azure est un **autre** compte
Databricks, invisible depuis ses tables système. DCM, lui, est **bi-cloud** : ses tables
curated unionnent les deux (`cloud_provider`). Rejoué sur
`it.ba_data_connect_monitoring__d.curated_dbx_billing_usage`, même fenêtre :

| `cloud_provider` | serverless $ | total $ | part srvls | WS |
|---|---:|---:|---:|---:|
| `aws` | 276 672 | 349 372 | **79,2 %** | 156 |
| `azure` | **103 967** | 158 544 | **65,6 %** | 143 |
| **les deux** | **380 639** | **507 916** | **74,9 %** | 299 |

Trois conséquences, toutes à porter dans l'implémentation :

1. **Azure ajoute ≈ 104 k$ / 30 j de serverless** que ce document ne mesure pas. Le
   dimensionnement réel de la page est donc ~1,4× celui annoncé ici.
2. **Le `CASE` à 11 surfaces tient à l'identique sur Azure** (vérifié : mêmes 12 buckets,
   aucun produit inattendu au-delà de 108 $), mais **le mix diffère fortement** — Azure est
   beaucoup plus « jobs » et « apps », beaucoup moins « SQL warehouse » :

   | Surface | part AWS | part Azure |
   |---|---:|---:|
   | `SQL_WAREHOUSE` | 48,7 % | **29,9 %** |
   | `JOB` | 21,0 % | **28,5 %** |
   | `DLT_PIPELINE` | 2,7 % | **11,6 %** |
   | `APP` | 4,0 % | **11,2 %** |
   | `NOTEBOOK` | 7,6 % | 5,1 % |
   | `AI_ENDPOINT` | 4,5 % | 4,8 % |
   | `GENIE` | 5,6 % | 3,4 % |
   | `PLATFORM_AUTO` | 2,9 % | 2,7 % |
   | `LAKEBASE` | 1,5 % | 2,0 % |
   | `MV_ST_REFRESH` | 0,7 % | 0,4 % |
   | `NETWORKING` | 0,8 % | 0,3 % |

   Le correctif « job serverless » (T2) est donc encore **plus** rentable qu'annoncé, et le
   correctif warehouse (T1) un peu moins. L'ordre du §11 ne change pas.
3. **Tous les contrôles chiffrés de l'annexe se rejouent avec `cloud_provider = 'aws'`**,
   sinon ils échouent sur une base bi-cloud. `cloud_provider` est déjà dans le grain des
   tables gold : le modèle du §9 n'a rien à changer, seuls les seuils de contrôle sont
   mono-cloud.

Le piège de nommage à connaître avant tout : un pipeline DLT serverless est facturé sous
le SKU `ENTERPRISE_JOBS_SERVERLESS_COMPUTE_*`, exactement comme un job serverless.
**Filtrer sur `sku_name LIKE '%SERVERLESS%'` ne dit pas de quel produit il s'agit**, et
`sku_name LIKE '%DLT%'` ne ramène que le DLT *classique* (SKU `ENTERPRISE_DLT_CORE/ADVANCED`).
Le couple `(billing_origin_product, product_features.is_serverless)` est la seule clé fiable.
Ce piège est déjà présent dans le code — cf. §10.4, où sa conséquence n'est pas un libellé
faux (le SKU dit vrai) mais une **population** dont personne n'a vu qu'elle laissait entrer,
sur des clusters bien réels, du coût qui n'est pas du coût de cluster.

---

## 2. « Serverless » n'est pas un type de compute : c'est 11 grains différents

C'est le point structurant du spike. Une page « clusters serverless » symétrique de la
page « all-purpose clusters » **n'existe pas**, parce qu'il n'y a pas d'objet unique à
lister. Chaque surface serverless a sa propre clé métier — et **trois n'en ont aucune**.

| Surface | Clé d'agrégation | $ / 30 j | Part srvls | Objets | WS | % $ keyé | $ tagué | policy | identité | Visible dans DCM |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|:--|
| `SQL_WAREHOUSE` | `usage_metadata.warehouse_id` | 138 911 | 48,7 % | 398 | 128 | 100 % | 34 % | 0 % | 100 % (`owned_by`) | ✅ coût — ⚠️ rightsizing fictif (§10.3) |
| `JOB` | `job_id` (+ `job_run_id`) | 60 021 | 21,0 % | 2 701 | 80 | 100 % | 67 % | 21 % | 100 % (`run_as`) | ❌ **absent** |
| `NOTEBOOK` | `notebook_id` | 21 662 | 7,6 % | 4 212 | 103 | 98,8 % | 26 % | 26 % | 100 % (`run_as`) | ❌ absent |
| `GENIE` | **aucune** (workspace) | 15 850 | 5,6 % | — | 112 | 0 % | 100 % | 0 % | 100 % (`run_as`) | ❌ absent |
| `AI_ENDPOINT` (serving, vector search, AI functions, agents) | `endpoint_id` | 12 733 | 4,5 % | 152 | 29 | 98,9 % | 55 % | 2 % | 100 % (`created_by`/`run_as`) | ❌ absent |
| `APP` | `app_id` | 11 385 | 4,0 % | 55 | 22 | 100 % | 11 % | 11 % | 100 % (`created_by`) | ❌ absent |
| `PLATFORM_AUTO` (predictive optimization, DQ monitoring, FGAC) | **aucune** (workspace) | 8 374 | 2,9 % | — | 93 | 0 % | 95 % | 0 % | 100 % (`run_as`) | ❌ absent |
| `DLT_PIPELINE` | `dlt_pipeline_id` | 7 796 | 2,7 % | 875 | 25 | 100 % | 38 % | 39 % | 100 % (`run_as`) | ✅ couvert |
| `LAKEBASE` / synced tables | `endpoint_id` ∪ `dlt_pipeline_id` | 4 340 | 1,5 % | 64 | 22 | 86,4 % | 14 % | 14 % | **5 %** | ❌ absent |
| `NETWORKING` (egress / NAT) | **aucune** (workspace) | 2 304 | 0,8 % | — | 99 | 0 % | 0 % | 0 % | **0 %** | ❌ absent |
| `MV_ST_REFRESH` (refresh MV / streaming table DBSQL) | `dlt_pipeline_id` | 1 970 | 0,7 % | 320 | 18 | 100 % | 29 % | 22 % | 100 % (`run_as`) | ⚠️ **mal attribué** (§10.1) |
| `OTHER` (LAKEFLOW_CONNECT) | — | 5 | 0,0 % | — | 9 | 0 % | 0 % | 0 % | 0 % | ❌ absent |

**Invisible aujourd'hui : 136 674 $ / 30 j, soit 38,0 % de la dépense DBU totale.**

Deux notions que la v1 confondait, et qu'il faut tenir séparées parce qu'elles appellent
des actions différentes :

- **Sans clé d'objet — 26 533 $ (9,3 % du serverless)** : `GENIE` + `PLATFORM_AUTO` +
  `NETWORKING` + `OTHER`. Ces surfaces ne peuvent **pas** être listées objet par objet.
  Elles s'affichent au grain workspace, et c'est tout ce qu'on peut en dire. Ce n'est
  pas un défaut à corriger : c'est ce que la source contient.
- **Sans aucun propriétaire — 5 875 $ (2,06 % du serverless)** : ni tag, ni budget
  policy, ni identité. Presque uniquement `NETWORKING` (2 304 $, 100 % orphelin) et
  `LAKEBASE` (81 % orphelin ≈ 3 515 $). C'est le seul vrai trou de refacturation, et il
  est **petit** — la v1 le surestimait de 82 %.

Le plus gros trou actionnable reste le **job serverless (60 021 $)** : il n'apparaît pas
parce que [`cluster_cost_daily`](../../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_cost_daily.py#L129)
filtre `usage_metadata.cluster_id IS NOT NULL`, et que
[`job_cluster_cost_daily`](../../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/job_cluster_cost_daily.py#L159-L165)
est un rollup de cette table. Un job serverless n'a **jamais** de `cluster_id` → il est
exclu en amont, silencieusement.

`object_id` est **globalement unique sauf pour `AI_ENDPOINT`** (152 `endpoint_id` pour
159 couples `(workspace_id, endpoint_id)` : un même endpoint existe dans plusieurs
workspaces). `workspace_id` doit donc rester dans le grain.

---

## 3. Ce que le serverless retire — et par quoi le remplacer

La moitié des colonnes des pages Compute actuelles n'a **aucun équivalent** serverless.
Les afficher vides serait pire que ne pas les afficher : c'est la table de traduction à
tenir.

| Métrique page Cluster | Source classique | Serverless | Substitut proposé |
|---|---|:--|---|
| CPU / mem util avg & p95 | `node_timeline` | ❌ n'existe pas | **aucun.** Ne pas afficher de colonne vide |
| `idle_pct` | `node_timeline` + `query.history` | ⚠️ calculable mais **non facturé** | **aucun.** Le gaspillage serverless n'est pas l'idle mais le *coût par unité de travail* — cf. §10.3 |
| `uptime_hours` | `node_timeline` | ❌ | durée cumulée des runs (`job_run_timeline`, ⚠️ périodisée à l'heure — §4) |
| `worker_count` avg/max, `node_type` | `clusters` | ❌ | `product_features.performance_target`, `product_features.apps.compute_size` |
| `auto_termination_minutes` | `clusters` | ❌ sans objet (arrêt automatique par design) | **aucun** |
| `recommended_node_type` (rightsizing) | reco | ❌ | reco `performance_target = STANDARD`, reco budget policy |
| tags `owner` / `cost_center` | `usage.custom_tags` | ⚠️ 0 → 100 % selon surface | `usage_metadata.budget_policy_id` + `COALESCE(identity_metadata.run_as, owned_by, created_by)` |
| temps de démarrage | `clusters` / audit | ⚠️ partiel | `setup_duration_seconds` (`job_run_timeline`) |
| DBU / coût $ | `billing.usage` | ✅ | ✅ identique, **à un grain plus fin** (`job_run_id`) |
| nom de l'objet | join sur `clusters` | ✅ **natif** | `usage_metadata.{job_name, notebook_path, app_name, endpoint_name}` — join seulement en repli |

Et ce que le serverless **ajoute**, qui n'existe pas côté classique — c'est là que la
page prend sa valeur propre plutôt que de mimer la page cluster :

1. **`product_features.performance_target`** (`STANDARD` / `PERFORMANCE_OPTIMIZED`) : le
   seul levier de rightsizing du serverless. Mesuré sur les 2 701 jobs serverless :
   **2 322 en `PERFORMANCE_OPTIMIZED` (57 589 $, 88 579 runs)**, **345 en `STANDARD`
   (2 025 $, 9 124 runs)**, **34 panachés** (408 $, 504 runs). Même constat DLT :
   `PERFORMANCE_OPTIMIZED` domine. Le champ existe aussi côté DLT dans
   `pipeline_update_timeline.trigger_details.job_task.performance_target`.
2. **`usage_metadata.budget_policy_id`** : le mécanisme de tagging *propre au serverless*
   (les tags de cluster n'existent pas). Policies distinctes par produit : **27 JOBS,
   32 INTERACTIVE, 6 LAKEBASE, 5 APPS, 5 SQL, 3 DLT, 2 VECTOR_SEARCH / DQ / DATABASE /
   FGAC**. Mais **8,4 % seulement de la dépense serverless** y est rattachée (21 % sur
   les jobs, 26 % sur les notebooks, 0,3 % sur SQL). C'est le chantier chargeback n°1.
   ⚠️ `usage_metadata.usage_policy_id` est **strictement identique** à
   `budget_policy_id` (égalité null-safe vérifiée sur 2 294 408 lignes / 100 %) : c'est
   un alias, pas une seconde dimension. N'en porter qu'un.
3. **`usage_metadata.job_run_id` renseigné sur 100 %** de la dépense job serverless →
   coût par exécution nativement calculable. C'est la bonne unité serverless : sans idle,
   « cher » ne veut plus dire « allumé trop longtemps » mais « trop de runs » ou « run
   trop lourd ».
4. **`system.lakeflow.pipeline_update_timeline.compute.type`** : discriminant DLT
   serverless/classique **autoritatif**, avec un contraste net à afficher — mesuré
   **par `update_id`** (la table est périodisée à l'heure, cf. §4) :

   | | updates | pipelines | % échec | p50 durée | p95 durée |
   |---|---:|---:|---:|---:|---:|
   | `SERVERLESS_COMPUTE` | 35 572 | 1 238 | **7,2 %** | **90 s** | 461 s |
   | `CLASSIC_COMPUTE` | 6 245 | 179 | **27,2 %** | **832 s** | 3 284 s |

   ⚠️ Corrélation, pas causalité : les pipelines restés en classic ne sont pas un
   échantillon aléatoire (souvent les plus anciens et les plus lourds). Afficher le
   contraste, pas une promesse de gain.

---

## 4. Sources disponibles, avec leur couverture mesurée

| Source | Ce qu'elle donne pour le serverless | Couverture mesurée | Verdict |
|---|---|---|:--|
| `system.billing.usage` (déjà ingérée) | coût, DBU, `product_features.*`, `usage_metadata.*` (56 champs), `identity_metadata.{run_as, owned_by, created_by}`, `custom_tags` | 100 % de la dépense | ✅ **socle unique de la page** |
| `system.query.history` (déjà ingérée) | `compute.type = 'SERVERLESS_COMPUTE'` : durée, `read_bytes`, `written_bytes`, spill, statut, `query_source.*` | **4,32 M requêtes / 7 j sur 90 WS** (vs 4,69 M warehouse, 0,005 M classic) → **47,9 %** des requêtes | ✅ substitut du `node_timeline` absent : le « travail fait » |
| `system.lakeflow.pipeline_update_timeline` | `compute.type`, `result_state`, `trigger_type`, `trigger_details.job_task.performance_target`, `run_as_user_name` | 43 464 lignes / 41 817 updates / 30 j ; `compute.type` toujours renseigné | ✅ **à ingérer** (non ingérée aujourd'hui) |
| `system.lakeflow.job_run_timeline` (déjà ingérée) | `setup/queue/run_duration_seconds`, `termination_code`, `compute_ids` | ⚠️ `compute_ids` vide sur ~~157 593 / 178 003 lignes (88,5 %)~~ → **6 465 894 / 6 668 570 (97,0 %)**, errata du 2026-09-10 : le périmètre de 178 003 lignes n'a pas pu être reconstitué, et le taux dépend du cloud (95,3 % aws / 59,3 % azure) ; `run_duration_seconds = 0` sur **95 %** des lignes (périodisation horaire) | ⚠️ utilisable pour la fiabilité **après agrégation par `run_id`**, **jamais** comme discriminant serverless |
| `system.serving.endpoint_usage` / `served_entities` | détail des endpoints de serving | **40 076 requêtes / 30 j sur 62 served entities** ; 648 `served_entities` / 299 endpoints au catalogue | ✅ **alimentée** — mais 62 entités actives contre 82 `endpoint_id` facturés : couverture partielle, à croiser |
| `system.access.outbound_network` | `destination`, `access_type` par workspace | non mesuré | 🔍 seule piste pour attribuer les 2 304 $ de NETWORKING |

### Le piège qui a faussé la v1 : un struct non-NULL à champs NULL

`query_source.job_info IS NOT NULL` est **vrai sur 100 % des lignes** de
`system.query.history` : le struct est instancié même quand tous ses champs sont NULL.
Tout comptage d'attribution doit porter sur la **feuille** (`query_source.job_info.job_id`).
Mesuré correctement sur 7 j :

| `compute.type` | requêtes | `job_info.job_id` | `notebook_id` | `pipeline_info.pipeline_id` | `dashboard_id` | non attribué |
|---|---:|---:|---:|---:|---:|---:|
| `SERVERLESS_COMPUTE` | 4 321 082 | 89,9 % | **80,3 %** | 0,7 % | 0 % | **8,0 %** |
| `WAREHOUSE` | 4 685 173 | 0,1 % | 0,1 % | 0 % | 2,2 % | **97,1 %** |
| `CLASSIC_COMPUTE` | 5 318 | 99,8 % | 0 % | 100 % | 0 % | 0 % |

Les 89,9 % et 80,3 % **se recouvrent** : une tâche de job dont le type est « notebook »
porte les deux. **`notebook_id` dans `query.history` ne désigne donc pas de l'interactif**
et ne peut pas servir à attribuer les 21 662 $ de la surface `NOTEBOOK` — pour ça, seul
`billing.usage` fait foi (`billing_origin_product = 'INTERACTIVE'`).

Corollaire sur les warehouses : **97,1 % des requêtes warehouse n'ont aucune source
identifiable**. Un bloc « coût par requête SQL » est donc hors de portée aujourd'hui,
indépendamment de `attributed_usage`.

### Quatre impasses — mesurées, à ne pas retenter

- **`system.billing.attributed_usage` est vide : 0 ligne, tout historique confondu.**
  C'est *la* table qui attribuerait la dépense serverless SQL à la requête et à
  l'utilisateur (`usage_metadata.dbsql_statement_id`, `identity_metadata.executed_by`,
  `granular_tags.query_tags`). Elle existe au catalogue mais n'est pas alimentée sur ce
  compte. **Décision à remonter** : demander son activation aux admins de compte
  débloquerait l'attribution fine des 48,7 % de la dépense serverless (SQL warehouse).
  D'ici là, ne rien construire dessus.
- **`query.history.waiting_for_compute_duration_ms` est NULL sur `SERVERLESS_COMPUTE`**
  (0 / 4 321 082), alors qu'il est renseigné sur 99,8 % des requêtes warehouse. Il n'y a
  donc **pas de métrique de cold start** exploitable côté requête serverless. Ne pas
  promettre de KPI « temps de démarrage serverless » sur cette base.
- **`job_run_timeline.compute[]` ne peut pas servir de discriminant** (88,5 % de tableaux
  vides). La serverless-ité d'un job doit venir de `billing.usage` puis être jointe sur
  `job_id`, jamais l'inverse.
  > **Errata du 2026-09-10 — conclusion confirmée, chiffre et nom de colonne à corriger.** La
  > colonne s'appelle **`compute_ids`** (un `array<string>` d'identifiants), pas `compute[]`, et le
  > **88,5 %** n'est reproductible sur aucun périmètre : **97,0 %** sur la source complète
  > (6 465 894 / 6 668 570), **94–95 %** sur toute fenêtre de 1, 7, 30 ou 90 jours, et en curated
  > **95,3 % aws contre 59,3 % azure** — aucun de ces périmètres ne compte 178 003 lignes (le
  > dénominateur du tableau §« sources »). Deux enseignements que le spike n'avait pas : le taux
  > **dépend du cloud** dans un rapport de 1,6×, donc aucun chiffre global n'est publiable sur une
  > page bi-cloud ; et au grain **tâche** (`job_task_run_timeline.compute_ids`) le vide tombe à
  > **16,2 %** de 23 360 757 lignes — là, ce qui interdit l'usage n'est plus l'absence mais la
  > nature : un identifiant n'est pas un *type*, il faut encore une jointure.
- **`usage_metadata.serverless_compute_id` n'est pas une clé d'objet.** 80 valeurs
  distinctes pour 2 701 jobs serverless (et 80 workspaces), 96 pour 4 212 notebooks :
  c'est un identifiant de **pool serverless par workspace**, pas un « cluster serverless »
  à lister. Renseigné sur 88 % de la dépense job, 83 % notebook, 99 % DLT, ~0 % SQL.
  Aucune page ne peut être construite dessus.

### Deux tables périodisées à l'heure — contrainte d'implémentation

`system.lakeflow.pipeline_update_timeline` et `system.lakeflow.job_run_timeline` émettent
**une ligne par tranche horaire** d'un update / d'un run, pas une ligne par update / run
(le commentaire de colonne le dit : *« The start time for the pipeline update **or for
the hour** »*). Conséquences non négociables :

- `COUNT(*)` **n'est pas** un nombre d'updates : 43 464 lignes pour 41 817 updates.
- La durée d'un update est `MAX(period_end_time) - MIN(period_start_time)` **groupé par
  `update_id`**, jamais `period_end_time - period_start_time` sur une ligne.
- `run_duration_seconds = 0` sur 95 % des lignes de `job_run_timeline` n'est pas une
  anomalie : c'est la valeur des tranches non terminales. Prendre le `MAX` par `run_id`.
- `result_state` est NULL sur 23 673 / 178 003 lignes (tranches non terminales) : un taux
  d'échec calculé ligne à ligne est faux.

---

## 5. Trois options de structure — et la recommandation

| | Option A — page transversale « Serverless » | Option B — une page par surface | Option C — filtre `compute_kind` sur les pages existantes |
|---|---|---|---|
| Forme | 1 nouvelle page, entrée « Serverless » sous Compute | 4–5 pages (jobs / notebooks / apps / IA) | 0 nouvelle page, un toggle |
| Répond à « où part l'argent serverless » | ✅ | ❌ éclaté | ❌ |
| Rend visible les 136,7 k$ absents | ✅ intégralement | ⚠️ non : les 26,5 k$ sans clé d'objet n'ont pas de page possible | ❌ les surfaces sans page restent absentes |
| Grain unique ? | ⚠️ non : agrège 11 clés → grain « surface » | ✅ un grain par page | ✅ |
| Coût | 1 table gold + 1 page | 4 tables + 4 pages | filtre + colonnes, mais faux sur l'efficience |
| Piège | ne pas y refaire un drill-down complet par objet | duplique la nav pour 4 % de la dépense | affiche des colonnes vides (§3) |

**Recommandé : A d'abord, puis C ciblé.**

- **A** — une page **`/databricks/serverless`** transversale, dont le sujet n'est pas
  « lister des objets » mais **« où part la dépense serverless, à qui la refacturer, quels
  leviers »**. C'est le seul cadrage qui absorbe 11 grains hétérogènes sans mentir, et le
  seul qui puisse afficher les 26 533 $ sans clé d'objet (au grain workspace).
- **C ciblé** — sur les pages **Job clusters** et **DLT pipeline clusters**, ajouter la
  dimension serverless là où elle a un vrai grain d'objet (`job_id`, `dlt_pipeline_id`).
  Le DLT le fait déjà via `compute_kind`
  ([`pipeline_cost_daily`](../../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/pipeline_cost_daily.py#L19-L23)) :
  **répliquer ce pattern sur les jobs** est le correctif le plus rentable du lot
  (60 021 $ rendus visibles à l'endroit où l'utilisateur les cherche).
- **B rejeté** pour l'instant : notebooks + apps + Lakebase = 37 387 $ (13,1 % du
  serverless). Un onglet dans la page A suffit ; une page dédiée n'est justifiée que si
  l'usage décolle.

---

## 6. Contenu proposé de la page, bloc par bloc

Colonne « Forme » choisie par le *job* de la donnée (magnitude / identité / part d'un
tout / série temporelle), pas par goût — cf. §8. « Réutilise » indique si le composant
frontend existe déjà.

### Bloc 1 — Bandeau de cadrage : où part l'argent

| Widget | Question | Forme | Source | Valeur mesurée | Réutilise |
|---|---|---|---|---|:--|
| Part serverless de la dépense DBU | « suis-je encore en train de piloter le bon périmètre ? » | **hero figure + barre empilée à 2 segments** (part d'un tout, 2 classes) — jamais un camembert | `is_serverless` | **79,3 %** (81,7 % sur les 30 j précédents) | ⚠️ nouveau (barre empilée) |
| 4 tuiles KPI | total serverless $, Δ vs période précédente, $ sans propriétaire, % couvert par une budget policy | **KPI row** (valeur + delta + sparkline) | `usage` | 285 352 $ · **+5,2 %** · 5 875 $ (**2,1 %**) · **8,4 %** sous policy | ✅ `ComputeKpiCard` |
| Dépense par surface | « quelles surfaces pèsent ? » | **barre horizontale triée, teinte séquentielle unique** (11 catégories à noms longs = magnitude, pas identité) | table §2 | SQL 48,7 % / jobs 21,0 % | ⚠️ nouveau |
| Trajectoire quotidienne | « ça dérive ? » | **colonnes empilées par jour, top 5 surfaces + « Autres »** ; en mode filtré → **emphase** (1 teinte + gris) | `usage_date` | — | ⚠️ nouveau (multi-séries) |

> ⚠️ Le KPI « % sous budget policy » est **8,4 % au global**, pas 21 % : 21 % est la
> valeur de la surface JOB seule. Afficher le global dans la tuile et le détail par
> surface dans le bloc 2 — pas l'inverse.

### Bloc 2 — Attribution & chargeback (le bloc à plus forte valeur)

C'est ici que le serverless diffère le plus du classique : pas de tag de cluster, donc
l'attribution passe par d'autres champs — et **le bon champ d'identité change selon la
surface**. C'est le point que la v1 avait manqué et qui inverse la conclusion du bloc.

| Widget | Question | Forme | Valeur mesurée |
|---|---|---|---|
| Matrice de couverture | « quelle surface est refacturable ? » | **heatmap** surfaces × {`custom_tags`, `budget_policy_id`, `identity`}, teinte séquentielle, en % de $ | identité = **100 % partout sauf LAKEBASE 5 % et NETWORKING 0 %** |
| $ sans propriétaire | « combien je ne peux imputer à personne ? » | **tuile KPI + tableau des lignes** | **5 875 $ (2,1 %)** : NETWORKING 2 304 $ (100 % orphelin) + LAKEBASE ≈ 3 515 $ (81 %) |
| $ sans clé d'objet | « combien je ne peux pas descendre à l'objet ? » | **tuile KPI + renvoi vers le grain workspace** | **26 533 $ (9,3 %)** : GENIE 15 850 + plateforme auto 8 374 + NETWORKING 2 304 + autres 5 |
| Top consommateurs notebooks | « qui dépense en interactif ? » | **barre horizontale top 10 + tuile « top 10 = 31 % »** — surtout **pas** un Pareto à double axe (§8) | 461 users, médiane **7,1 $**, max **1 400 $**, top 10 = **31 %** |
| Budget policies | « quelles policies existent, que couvrent-elles ? » | **tableau** (policy, $, surfaces, workspaces) | 27 jobs / 32 notebooks / 6 lakebase / 5 apps / 5 SQL / 3 DLT |

**`identity` est un `COALESCE`, pas une colonne.** Le champ porteur diffère par surface —
un seul champ donnerait la matrice fausse de la v1 :

| Surface | `run_as` | `owned_by` | `created_by` | → `identity` |
|---|---:|---:|---:|---:|
| `SQL_WAREHOUSE` | 0 % | **100 %** | 0 % | 100 % |
| `JOB` / `NOTEBOOK` / `DLT_PIPELINE` / `MV_ST_REFRESH` / `PLATFORM_AUTO` / `GENIE` | **100 %** | 0 % | 0 % | 100 % |
| `APP` | 0 % | 0 % | **100 %** | 100 % |
| `AI_ENDPOINT` | 60 % | 0 % | 43 % | 100 % |
| `LAKEBASE` | 5 % | 0 % | 0 % | **5 %** |
| `NETWORKING` | 0 % | 0 % | 0 % | **0 %** |

### Bloc 3 — Leviers actionnables (ce qui remplace le rightsizing)

| Widget | Question | Forme | Valeur mesurée |
|---|---|---|---|
| `performance_target` | « combien je paie le mode rapide ? » | **barre empilée 2 segments + tableau des jobs concernés** | **2 322 jobs / 57 589 $** en `PERFORMANCE_OPTIMIZED` vs **345 / 2 025 $** en `STANDARD` (+ 34 panachés / 408 $) |
| Distribution du coût par run | « le coût vient du volume de runs ou du poids des runs ? » | **histogramme à buckets fixes** (bornes quasi-log, réutilise la machinerie existante — §9) | 98 207 runs · p50 **0,125 $** · p95 **1,49 $** · p99 **14,88 $** · moyenne **0,611 $** · max **1 345 $** |
| Concentration haute fréquence | « quels jobs paient l'overhead de run ? » | **tableau trié** (runs, $, $/run) | **43 jobs ≥ 300 runs = 24 543 $**, soit 41 % de la dépense job serverless pour 1,6 % des jobs |
| Concentration du poids de run | « et la queue ? » | **tuile + tableau des runs concernés** | **62 runs > 50 $ = 13,8 % de la dépense job** ; 2 runs > 200 $ = 2,7 % |
| Serverless vs classique, à iso-objet | « migrer vaut-il le coup ? » | **dumbbell** (avant → après par pipeline) ou **2 tuiles comparées** | DLT : 7,2 % échec / p50 90 s (srvls) vs 27,2 % / 832 s (classic) — cf. la mise en garde §3.4 |

> ⚠️ Sur `performance_target`, **ne pas afficher d'économie chiffrée** : les deux modes
> partagent le même SKU (`ENTERPRISE_JOBS_SERVERLESS_COMPUTE_*`), donc le même $/DBU. Le
> surcoût se matérialise en **quantité de DBU**, pas en prix, et ne peut être chiffré que
> par comparaison A/B sur un job donné. Afficher la population et le $ exposé ; laisser
> l'arbitrage à l'utilisateur.
>
> ⚠️ Sur la distribution du coût par run, **afficher p50 *et* p99** : la moyenne (0,611 $)
> est 4× le p95 (1,49 $). Un widget qui n'affiche que p50/p95 laisse croire que la
> dépense est diffuse alors que 0,06 % des runs en portent 13,8 %.

### Bloc 4 — Drill-down par surface

Onglets **Jobs · SQL · Notebooks · DLT · Apps · IA · Genie · Plateforme**, chacun un
tableau au grain de sa clé, colonnes limitées à ce qui existe vraiment (§3) : `$`, `DBU`,
`Δ vs J-1`, `runs`, `$/run`, `perf_target`, `budget_policy`, `identity`, `% tagué`.

Les onglets **Genie**, **Plateforme** et **Réseau** sont au **grain workspace** (aucune
clé d'objet — §2), pas au grain objet : le tableau y liste des workspaces, et l'en-tête
doit le dire. Ne pas fabriquer un faux identifiant d'objet pour uniformiser.

Drawer au clic avec la tendance 30 j (`ComputeTrendChart`) + les métriques `query.history`
de l'objet (durée p95, spill, taux d'échec) **uniquement pour les surfaces où
`query_source` rattache réellement** — jobs (89,9 %) et DLT (0,7 %), **pas** les
notebooks (§4).

### Bloc 5 — Angles morts assumés, affichés comme tels

Un encart explicite, pas un silence : **pas de CPU/mémoire, pas de rightsizing de node,
et pas d'idle actionnable** sur le serverless — avec le renvoi vers `attributed_usage`
(§4) comme condition d'un futur bloc « coût par requête SQL ». Un utilisateur qui vient
de la page cluster cherchera ces colonnes ; mieux vaut lui dire pourquoi elles n'existent
pas. Mentionner aussi que **97,1 % des requêtes warehouse n'ont aucune source
identifiable** : c'est la vraie raison pour laquelle « qui a lancé cette requête SQL »
n'est pas affichable, avant même la question `attributed_usage`.

---

## 7. Maquette

```
Compute — Serverless                                    [ 1j | 7j | 30j | 90j ]  ⟳
────────────────────────────────────────────────────────────────────────────────
  79,3 %          ███████████████████████████████████░░░░░░░░  srvls 79,3 / classic 20,7
  de la dépense DBU est serverless          (81,7 % sur les 30 j précédents ▼)

  ┌ Total srvls ─┐ ┌ Δ vs 30j-1 ─┐ ┌ Sans propriétaire ┐ ┌ Sous budget policy ┐
  │  285 352 $   │ │   + 5,2 %   │ │     5 875 $       │ │       8,4 %         │
  │  ▁▂▃▅▄▆▇     │ │   ▁▂▂▃▃▄▅   │ │     (2,1 %)       │ │  ▁▁▂▂▃▃▃            │
  └──────────────┘ └─────────────┘ └───────────────────┘ └─────────────────────┘

  Dépense par surface (30 j)              Trajectoire quotidienne
  SQL warehouse    ████████████ 138 911    $ ┤        ▂▃▅▆▅▇▆   ■ SQL  ■ Jobs
  Job serverless   █████ 60 021              ┤   ▂▃▄▅▆███████   ■ Notebooks
  Notebook         ██ 21 662                 ┤▂▃▄▅▆██████████   ■ Genie  ■ Autres
  Genie            █▌ 15 850                 └────────────────
  Endpoint IA      █ 12 733
  App              █ 11 385                ⓘ 26 533 $ (9,3 %) sans clé d'objet :
  Plateforme auto  ▊ 8 374                    Genie, plateforme auto, réseau →
  DLT pipeline     ▊ 7 796                    consultables au grain workspace
  Lakebase         ▍ 4 340
  Réseau           ▎ 2 304
  MV / ST refresh  ▏ 1 970

  Attribution — % de $ rattachable          Leviers
        tags  policy  identité              perf_target   ████████████▏ 96 % PERF_OPT
  SQL    34%    0%     100% (owned_by)                    ▍ 4 % STANDARD
  Jobs   67%   21%     100% (run_as)        $ / run       ▁▃▆█▅▂▁
  Noteb  26%   26%     100% (run_as)                      p50 0,13 $ · p99 14,88 $
  Genie 100%    0%     100% (run_as)        43 jobs ≥ 300 runs → 24 543 $ (41 %)
  IA     55%    2%     100% (créé./run_as)  62 runs > 50 $  → 13,8 % de la dépense job
  Apps   11%   11%     100% (created_by)    DLT srvls 7,2 % échec / 90 s
  Lakeb  14%   14%       5%  ⚠                  vs classic 27,2 % / 832 s
  Réseau  0%    0%       0%  ⚠

  [ Jobs ] [ SQL ] [ Notebooks ] [ DLT ] [ Apps ] [ IA ] [ Genie ] [ Plateforme ]
  ┌──────────────────────────────────────────────────────────────────────────┐
  │ Job                WS      $        runs   $/run  perf_target  policy    │
  │ ingest_sap_delta   lz-fin  4 218    1 440  2,93   PERF_OPT     finops-1  │
  │ …                                                                        │
  └──────────────────────────────────────────────────────────────────────────┘
  ⓘ Pas de CPU/mémoire, pas de rightsizing de node, pas d'idle actionnable — pourquoi ›
```

---

## 8. Règles de forme à respecter à l'implémentation

Contraintes de dataviz applicables aux widgets ci-dessus, à trancher **avant** d'écrire le
composant :

- **Jamais de double axe.** Le réflexe « coût en barres + nombre de runs en ligne sur un
  2ᵉ axe » est l'erreur n°1 : deux graphiques, ou une indexation base 100.
- **11 surfaces ≠ 11 couleurs.** Plafond de 7–8 séries catégorielles ; au-delà, replier la
  queue en « Autres » ou passer en petits multiples. Pour la répartition par surface, la
  donnée fait un travail de **magnitude** (comparer des montants), pas d'**identité** →
  **une seule teinte séquentielle**, triée. Les 11 couleurs seraient illisibles en
  daltonisme et n'ajouteraient rien.
- **La couleur suit l'entité, jamais son rang** : filtrer une surface ne doit pas
  repeindre les survivantes.
- **Part d'un tout à 2 classes** (serverless/classic, perf_target) → barre empilée ou
  jauge, pas un camembert à 2 parts.
- **Statuts réservés** (échec de run, dérive de coût) : palette de statut + icône +
  libellé, jamais la couleur seule, et jamais recyclée en « série 4 ».
- **Légende dès 2 séries**, étiquettes directes jusqu'à 4, jamais un nombre sur chaque
  point.
- **Distribution à queue lourde → échelle log ou buckets quasi-log**, avec le p99
  annoté. Une échelle linéaire sur le $/run écrase 99,9 % de la population contre l'axe.
- **Survol par défaut** : les composants maison
  [`ComputeTrendChart`](../../../packages/dcm-frontend/src/components/domain/compute/compute-trend-chart.tsx)
  (SVG inline, mono-série, barres ou ligne) et
  [`ChartHoverTooltip`](../../../packages/dcm-frontend/src/components/domain/compute/chart-hover-tooltip.tsx)
  le font déjà — les nouvelles formes (empilé, barres horizontales, heatmap) doivent le
  reprendre, pas l'oublier.

**Coût frontend à prévoir** : `ComputeKpiCard`, `ComputeDataTable`, `ComputeTrendChart`,
`ComputeTabs`/`ComputeCostTabs` et les drawers se réutilisent tels quels. Manquent
**3 composants** : barre empilée (part d'un tout), barres horizontales triées
(classement), heatmap (matrice de couverture). C'est le vrai poste d'effort de la page,
pas la donnée.

---

## 9. Data model cible

⭐ = nouvelle · ✅ = existe · 🔧 = à corriger

| Table | Grain | Statut | Usage |
|---|---|:--|---|
| `gold_dbx_compute_serverless_cost_daily` | `(cloud_provider, workspace_id, serverless_surface, object_id, period_start)` | ⭐ | socle de la page |
| `gold_dbx_compute_serverless_cost_rolling` | + `window_days` | ⭐ | KPI + tableaux fenêtrés |
| `gold_dbx_compute_serverless_governance` | `(cloud_provider, workspace_id, serverless_surface)` | ⭐ | matrice d'attribution (bloc 2) |
| `gold_dbx_compute_job_cluster_cost_daily` | `job_id` + `compute_kind` | 🔧 | rendre le job serverless visible (option C) |
| `gold_dbx_compute_pipeline_cost_daily` | `dlt_pipeline_id` + `compute_kind` | 🔧 filtrer `billing_origin_product = 'DLT'` | §10.1 |
| `gold_dbx_compute_warehouse_utilization_daily` | `warehouse_id` | 🔧 neutraliser l'efficience serverless | §10.3 |
| `gold_dbx_compute_cluster_cost_daily` | `cluster_id` | 🔧 liste blanche `billing_origin_product IN ('JOBS', 'ALL_PURPOSE', 'DLT')` — **pas** de renommage de `sku_group`, et **0 ligne retirée** (134 corrigées en valeur) | §10.4 |
| `curated_dbx_lakeflow_pipeline_update_timeline` | **`update_id`** (agrégé depuis les tranches horaires) | ⭐ ingestion | fiabilité / durée DLT serverless |
| `gold_dbx_compute_forecast_daily` | `(object_type, object_id, metric)` | 🔧 + `SERVERLESS_SURFACE` | forecast |

Schéma `gold_dbx_compute_serverless_cost_daily` :

```
cloud_provider, workspace_id, serverless_surface, object_id, period_start  -- PK / merge key
object_name              -- usage_metadata.{job_name,notebook_path,app_name,endpoint_name},
                         -- repli sur la dim curated, repli final sur object_id
billing_origin_product   -- produit brut, conservé pour l'audit
performance_target       -- STANDARD | PERFORMANCE_OPTIMIZED | MIXED | NULL selon surface
budget_policy_id         -- attribution serverless (ne PAS porter usage_policy_id : alias)
identity_principal       -- COALESCE(run_as, owned_by, created_by)
identity_source          -- RUN_AS | OWNED_BY | CREATED_BY | NONE, jamais NULL
has_custom_tags          -- boolean, alimente la matrice de couverture
dbu_quantity, cost_usd, cost_usd_prev_day, cost_delta_pct
run_count                -- COUNT(DISTINCT usage_metadata.job_run_id), NULL hors surface JOB
cost_per_run_histogram   -- array<bigint>, buckets fixes, sommable sur fenêtre
cost_rank, is_top_cost   -- RANK() PARTITION BY (period_start, serverless_surface)
_generated_at
```

Quatre choix, dont deux qui suivent les conventions déjà en place dans le domaine :

- **`serverless_surface` dans le GRAIN, pas en attribut** — même raisonnement que
  `compute_kind` dans [`pipeline_cost_daily`](../../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/pipeline_cost_daily.py#L19-L23) :
  un même `object_id` peut être facturé sur deux surfaces (320 `dlt_pipeline_id` sont
  facturés en SQL *et* en DLT), et hors du grain leur coût resterait mélangé.
  Le `CASE` doit être **exhaustif avec branche `ELSE` explicite** (jamais de NULL en clé
  de merge : `merge_into_table` utilise un `<=>` null-safe qui fusionnerait toutes ces
  lignes en une).
- **⚠️ `object_id` a besoin d'une SENTINELLE, pas d'un NULL.** C'est le piège que la v1
  ne voyait pas : **9,3 % de la dépense serverless (26 533 $) n'a aucune clé d'objet**
  (GENIE, `PLATFORM_AUTO`, `NETWORKING`, `OTHER`), et `NOTEBOOK` / `AI_ENDPOINT` /
  `LAKEBASE` ont eux aussi 1,2 % / 1,1 % / 13,6 % de leur coût sans clé. Un `object_id`
  NULL en clé de merge fusionnerait **tout un workspace en une ligne corrompue** via le
  `<=>`. Écrire `COALESCE(<clé de la surface>, '_NO_OBJECT')` et porter un booléen
  `has_object_key` pour que l'IHM sache afficher un grain workspace (§6 bloc 4) au lieu
  d'un faux objet.
- **`cost_per_run_histogram` plutôt qu'un percentile quotidien** — un p95 quotidien n'est
  ni sommable ni moyennable sur 30 j. Réutiliser
  [`histogram_from_edges_sql` / `percentile_from_histogram_sql`](../../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/sql_helpers.py#L193-L245)
  avec de nouvelles bornes `HISTOGRAM_COST_PER_RUN_EDGES`, **quasi-log par doublement de
  0,01 $ à 1 310,72 $** (18 bornes, 19 buckets), calquées sur
  `HISTOGRAM_LATENCY_MS_EDGES` :
  `0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96, 81.92, 163.84, 327.68, 655.36, 1310.72`.
  **Ne pas s'arrêter à ~50 $** comme le proposait la v1 : 62 runs dépassent 50 $ et
  portent **13,8 % de la dépense job**, qui finiraient tous dans un bucket overflow non
  borné — le p99 (14,88 $) et le max (1 345 $) deviendraient illisibles. 15,2 % des runs
  sont ≤ 0,01 $ : la première borne est bien placée.
- **`identity_source` en colonne à côté de `identity_principal`** — l'IHM doit pouvoir
  écrire « propriétaire (owned_by) » sur un warehouse et « exécutant (run_as) » sur un
  job : ce n'est pas la même sémantique de refacturation, et les fondre sans dire lequel
  est affiché ferait passer un créateur d'app pour son utilisateur.

> **Anti-double-comptage** : cette table est un **rollup des mêmes lignes de facturation**
> que `cluster_cost_daily`, `job_cluster_cost_daily`, `pipeline_cost_daily` et
> `warehouse_cost_daily`. Ne jamais la sommer avec elles. En revanche, sommer ses
> `serverless_surface` entre elles est légitime : elles partitionnent des lignes disjointes.

---

## 10. Corrections à porter sur l'existant (trouvées en mesurant)

Quatre défauts constatés sur les pages actuelles, indépendants de la nouvelle page. §10.1 et
§10.4 sont en réalité **le même défaut appliqué deux fois** — une population définie par un
identifiant de `usage_metadata` sans prédicat de `billing_origin_product` — et se corrigent
ensemble (lot T3).

### 10.1 — `pipeline_cost_daily` : plus de la moitié de la population n'est pas du DLT

Le filtre est `usage_metadata.dlt_pipeline_id IS NOT NULL`
([ligne 180](../../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/pipeline_cost_daily.py#L180))
**sans prédicat de produit**. Or ce champ est renseigné par **6** produits, pas 4.

> **Correction de la v2, mesurée le 2026-09-10** sur **tout l'historique** du gold déployé
> (`it.ba_data_connect_monitoring__d`, 552 968 lignes, 20 265 `dlt_pipeline_id`) et non plus
> sur une fenêtre de 30 j. La v2 annonçait **3** produits non-DLT et **2 316 $ / 30 j** ; il y
> en a **5**, dont le 3ᵉ poste de dépense du lot, et le chiffre qui compte n'est pas le montant.

| `billing_origin_product` | lignes gold | pipelines | $ (historique) | couverture | vrai DLT ? |
|---|---:|---:|---:|---|:--|
| `DLT` | 439 896 | 9 298 | 347 266,53 | 2024-02-13 → 2026-09-09 | ✅ |
| `SQL` (refresh MV / streaming table DBSQL) | 106 936 | **10 499** | 22 674,95 | 2024-08-26 → 2026-09-09 | ❌ |
| `LAKEFLOW_CONNECT` | 2 043 | 49 | 9 873,47 | 2025-02-12 → 2026-03-18 | ❌ |
| `DATABASE` (synced tables Lakebase) | 3 186 | 293 | 2 614,01 | 2025-09-09 → 2026-09-09 | ❌ |
| `VECTOR_SEARCH` (sync d'index) | 924 | 130 | 1 938,16 | 2024-12-16 → 2026-09-08 | ❌ |
| `AI_FUNCTIONS` | 2 | 1 | 1,14 | 2026-06-04 | ❌ |

**Plus de 113 000 lignes et 37 100 $ sont affichés comme du DLT sans en être.** Mais le montant
n'est pas le vrai enjeu : **`SQL` porte 10 499 identifiants de pipelines contre 9 298 pour
`DLT`**, donc **plus de la moitié de la population listée sur la page DLT n'est pas du DLT**,
avec un coût par pipeline **17 × plus faible** (2,16 $ contre 37,35 $) qui écrase les moyennes
et remplit les pages de pagination. Un utilisateur qui cherche ses pipelines DLT en trouve
majoritairement d'autres.

Trois chiffres voisins circulent ici, et ce ne sont **pas** les mêmes populations — précisé
parce que la v3 les avait mélangés :

| Quantité | Valeur | Définition |
|---|---:|---|
| lignes gold que le correctif ne produit plus | **113 085** / 37 100,15 $ | jointure sur le grain **complet**, `compute_kind` compris. C'est ce que la purge supprime |
| contamination côté `curated` | 629 379 lignes / 10 972 pids / **37 100,58 $** | lignes de facturation portant un `dlt_pipeline_id` sur un produit ≠ `DLT` |
| somme des sous-totaux du tableau ci-dessus | 113 072 / 37 101,73 $ | attribution **par produit**, qui compte deux fois les 19 lignes d'éventail et ignore `compute_kind` |

Fiabilité de la mesure : **5** `dlt_pipeline_id` sur 20 265 portent 2 produits, soit **19**
lignes d'éventail sur 552 968 (0,003 %) — la somme des lignes par produit dépasse donc le
total de 19 exactement. L'attribution par produit est nette.

Correctif : ajouter `billing_origin_product = 'DLT'`. Porter le produit dans le grain pour
« ne rien perdre » **est écarté** : ce serait le troisième élargissement de grain de la table
après `compute_kind`, et la valeur des refresh MV/ST est sur la page SQL, pas ici. À traiter
comme une entrée de backlog séparée si le besoin se confirme.

⚠️ **Les lignes historiques ne disparaissent pas toutes seules.** `merge_into_table` est un
upsert : une clé cible que le recalcul ne produit plus n'est jamais supprimée, et
`PIPELINE_COST_DAILY_SPEC` ne déclare **pas** d'`absent_row_delete_guard` (aucune spec
`*_daily` n'en déclare, sauf `WAREHOUSE_UTILIZATION_DAILY_SPEC` depuis le correctif §10.3).
Le filtre seul assainit les jours **futurs** et laisse 2 ans et demi d'historique faux. Le
correctif doit donc livrer **aussi** une purge ponctuelle des lignes devenues orphelines.

Comment, sans changer le régime permanent de la table : par un **paramètre de run**
`one_off_purge`, qui injecte le garde-fou pour un run et ne persiste rien (le run suivant est
de nouveau en upsert pur). Poser l'`absent_row_delete_guard` dans la spec reviendrait à
accepter *définitivement*, pour une réparation ponctuelle, que cette table perde un jour déjà
écrit dès qu'un run est dégradé — ce que le commentaire de `WAREHOUSE_UTILIZATION_DAILY_SPEC`
interdit précisément d'étendre aux `*_daily` qui agrègent la facturation. Deux détails qui
décident du résultat : le paramètre exige `full_refresh` (sans lui la suppression serait bornée
à la fenêtre incrémentale de 10 j et nettoierait une fraction de l'historique **en rapportant
un succès**), et le seuil est le **début du run** et non la grâce volumétrique de 7 j — mesuré,
`pipeline_cost_daily` n'a qu'**une seule** valeur de `_generated_at`, donc `current_date() - 7`
y supprimerait **0 ligne** sans le dire. Bornes conservées : la suppression reste limitée au
`MIN(period_start)` réellement produit (2024-02-13, antérieur à la première orpheline du
2024-08-26 — les 113 085 sont donc bien toutes couvertes), et une sortie vide l'annule au lieu
de vider la table.

### 10.2 — `compute_kind_case_expr` : proxy exact aujourd'hui, à remplacer par le champ officiel

Nuance par rapport à la v1, qui parlait d'« heuristique ». Le
[docstring du code](../../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/sql_helpers.py#L115-L138)
revendique un proxy **exact** (`cluster_id IS NULL` → `SERVERLESS`), mesuré. **Il a
raison** : sur les lignes DLT de la fenêtre, l'équivalence est parfaite —

| `cluster_id IS NULL` | `is_serverless` | lignes |
|---|---|---:|
| `true` | `true` | 51 748 |
| `false` | `false` | 11 869 |

Aucune ligne discordante, aucun `is_serverless` NULL sur le produit `DLT`. Il n'y a donc
**aucun bug à corriger ici** — mais il reste préférable de porter
`product_features.is_serverless` (champ officiel, robuste au jour où Databricks facturera
un cluster DLT sans renseigner `cluster_id`) et de **garder l'équivalence ci-dessus comme
test de non-régression**. Priorité basse : c'est une amélioration de robustesse, pas un
correctif de données.

### 10.3 — L'efficience des SQL warehouses serverless produit des économies imaginaires

Correction complète de la v1, qui affirmait que `warehouse_events` « n'est pas journalisé
de façon fiable en serverless ». **C'est faux.** Sur 30 j, les warehouses serverless
émettent :

| event_type | serverless (n / warehouses) | classic-pro (n / warehouses) |
|---|---:|---:|
| `STARTING` | 55 880 / 380 | 161 / 16 |
| `RUNNING` | 55 886 / 393 | 157 / 16 |
| `STOPPED` | 53 665 / 393 | 161 / 16 |
| `SCALED_UP` / `SCALED_DOWN` | 58 777 / 58 771 | 218 / 218 |

Les événements sont là, et `RUNNING` aussi (le
[commentaire du code](../../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/warehouse_utilization_daily.py#L30-L33)
qui justifie de préférer `STARTING` parce que `RUNNING` serait mal journalisé en
serverless est **périmé** — sans conséquence, le choix reste valide).

**Le défaut réel est plus grave.** `running_hours` et `idle_pct` sont parfaitement
calculables sur serverless, et l'implémentation existante est rigoureuse (sessions
`STARTING`→`STOPPED` découpées par jour, `active_query_hours` par balayage sweep-line qui
ne double-compte pas la concurrence). Rejoué à l'identique sur 15 j (2026-08-25 →
2026-09-08) :

| | jours-warehouse | `running_hours` | `active_query_hours` | `idle_pct` global | `idle_pct` médian | jours > seuil 60 % |
|---|---:|---:|---:|---:|---:|---:|
| serverless | 3 131 | 7 962 | 919 | **88,5 %** | **96,3 %** | **95,6 %** |
| classic / pro | 70 | 93 | 6 | 93,1 % | 91,9 % | 95,7 % |

Conséquence directe, avec `WAREHOUSE_IDLE_PCT_OVER_THRESHOLD = 60.0` et
`estimated_savings_usd = cost_usd * idle_pct / 100` :

- **353 des 398 warehouses serverless sont marqués `utilization_status = 'OVER'`** ;
- la page annonce **≈ 49 100 $ d'économies sur 15 j** (≈ 98 k$ / 30 j, sur 57 729 $ de
  coût serverless apparié) **qui ne peuvent pas être réalisées** : en serverless
  l'utilisateur n'est **pas facturé au temps allumé** mais au compute consommé par les
  requêtes. Réduire l'idle d'un warehouse serverless ne rend aucun dollar.
- Ce n'est pas un artefact : un warehouse serverless démarre à l'arrivée d'une requête et
  s'arrête quelques minutes après — 53 615 sessions sur 30 j. Un ratio actif/allumé
  structurellement bas est le **comportement attendu**, pas un gaspillage.

**Correctif** : quand le warehouse est serverless, mettre à NULL (« non applicable »)
`idle_pct`, `active_to_running_ratio`, `utilization_status`, `rightsizing_reco`,
`estimated_savings_usd`, `auto_stop_minutes`/`has_auto_stop`, et l'afficher comme tel côté
IHM (§3, bloc 5). `running_hours`, `active_query_hours`, `peak_concurrency`,
`scale_up_events`/`scale_down_events` restent justes et intéressants — les garder. Le
signal d'efficience serverless est le **$ par requête** et le temps de file, depuis
`query.history`, pas l'idle.

C'est de loin le correctif à plus fort impact du lot : il retire une recommandation
chiffrée fausse de ~98 k$/30 j déjà visible dans l'outil.

### 10.4 — `cluster_cost_daily` compte du coût de service managé comme du coût de cluster

Nouveau, absent de la v1. [`cluster_cost_daily`](../../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/cluster_cost_daily.py#L136-L192)
dérive `sku_group ∈ {serverless, photon, classic}` d'un `sku_name LIKE '%SERVERLESS%'`,
sur une table dont le filtre d'entrée est `usage_metadata.cluster_id IS NOT NULL` — donc
supposée **par construction du compute classique**. Sur tout l'historique du gold déployé
(5 389 217 lignes) :

| `sku_group` dérivé | lignes | clusters | $ (historique) |
|---|---:|---:|---:|
| `classic` | 5 186 818 | 5 027 848 | 2 562 759,86 |
| `photon` | 202 270 | 182 043 | 647 884,22 |
| **`serverless`** | **129** | **97** | **1 286,28** |

> **Correction de fond de la v2, mesurée le 2026-09-10.** La v2 concluait « 81 clusters sont
> étiquetés `serverless` alors qu'ils ont un `cluster_id` — c'est le piège de nommage de SKU
> du §1 appliqué dans le code » et proposait de renommer `sku_group` en `sku_family`.
> **Ce diagnostic est faux, et le correctif qui en découle l'est aussi.**
>
> **Deuxième correction, du 2026-09-10 également, en implémentant le correctif.** La v3 de
> cette section — écrite quelques heures plus tôt — annonçait que la table « ingère des
> endpoints de serving comme s'ils étaient des clusters », pour **1 286,28 $**, et que les
> 129 lignes seraient **retirées**. Les trois affirmations sont fausses, et c'est le tableau
> `sku_group` ci-dessus qui a induit en erreur : il compte des lignes ÉTIQUETÉES, pas des
> lignes fausses. Ce que la mesure exhaustive donne, elle, est écrit ci-dessous.

Population `cluster_id IS NOT NULL` de `curated_dbx_billing_usage`, par produit :

| `billing_origin_product` | lignes | `cluster_id` distincts | DBU | SKU `%SERVERLESS%` ? |
|---|---:|---:|---:|:--|
| `JOBS` | 6 872 307 | 5 058 358 | 5 472 121,45 | non |
| `ALL_PURPOSE` | 1 735 927 | 6 631 | 4 468 993,76 | non |
| `DLT` | 696 693 | 275 731 | 625 861,71 | non |
| `MODEL_SERVING` | 47 341 | 3 628 | 47 558,18 | **oui** |
| `AI_FUNCTIONS` | 3 962 | 432 | 15 444,84 | **oui** |

```
-- Lignes portant un cluster_id ET un sku_name %SERVERLESS%,
-- sur un produit autre que MODEL_SERVING / AI_FUNCTIONS :
--   → 0 ligne.
```

Les SKU en cause sont `ENTERPRISE_SERVERLESS_REAL_TIME_INFERENCE_*` et
`PREMIUM_SERVERLESS_REAL_TIME_INFERENCE_*` : des **endpoints d'inférence temps réel**. Donc

1. le libellé de SKU est **exact** — ces lignes *sont* du serverless, ce n'est pas un piège
   de nommage ;
2. le vrai défaut est **en amont** : `MODEL_SERVING` et `AI_FUNCTIONS` rattachent leur
   facturation au cluster **appelant** via `usage_metadata.cluster_id`. Le coût de l'inférence
   est alors compté comme du coût de ce cluster ;
3. `sku_group = 'serverless'` **n'est pas** un marqueur utilisable du défaut — ni exhaustif,
   ni précis, cf. ci-dessous. C'est ce que la v3 avait supposé.

#### Ce que le défaut est réellement, mesuré exhaustivement

Sur les 3 963 + 432 `cluster_id` que portent `MODEL_SERVING` et `AI_FUNCTIONS`, **3 963
n'existent pas** dans `curated_dbx_compute_clusters` : ils sont donc déjà écartés par le
`WHERE cluster_type <> 'OTHER'` en fin de builder. Ce garde-fou, posé pour ne pas exposer un
cluster sans identité, **masquait le défaut** — et fait que l'énoncé « la table ingère des
endpoints » est faux : les endpoints n'y entrent pas.

Ce qui fuit est le reste : de la facturation de serving / IA rattachée à **97 clusters bien
réels et connus**. Mesure sur tout l'historique, jointure de prix identique à celle du builder :

| | Valeur |
|---|---|
| jours-cluster contaminés | **134** (97 clusters distincts) |
| coût étranger effectivement retiré | **791,01 $** — `AI_FUNCTIONS` 567,34 $ (55 clusters, 2026-03-04 → 2026-09-09), `MODEL_SERVING` 223,68 $ (42 clusters, 2025-10-28 → 2026-09-07) |
| coût affiché aujourd'hui sur ces 134 lignes | 1 557,64 $ → **766,63 $** après correctif |
| lignes **supprimées** | **0** |
| lignes **corrigées en valeur** | **134** |

**Aucune ligne ne disparaît**, parce que ces 134 jours-cluster portent aussi du vrai coût de
compute : ce sont des jours *mixtes*. Vérifié indépendamment de `sku_group`, sur les
5 389 217 lignes du gold : **0 jour-cluster n'est intégralement du serving**, et **0** ligne
gold n'a pas de correspondance curated. `cluster_cost_daily` n'a donc **aucune orpheline**, et
n'a besoin que d'un `full_refresh` — pas d'une purge (contrairement à §10.1).

Pourquoi `sku_group = 'serverless'` ne peut pas servir de marqueur : `sku_group` est dérivé
d'un `MAX(CASE WHEN sku_name LIKE '%SERVERLESS%' THEN 3 …)` **agrégé sur le jour-cluster**.
Une seule ligne étrangère suffit donc à réétiqueter la journée entière. D'où l'écart dans les
deux sens : 129 lignes étiquetées pour 134 contaminées (5 échappent, leur coût étranger étant
sur un SKU non-`%SERVERLESS%` — elles sont déjà `classic`), et sur les 129, **104 afficheront
`classic` et 25 `photon`** après le correctif, aucune ne disparaissant.

**Correctif : ne retenir que les produits de compute cluster** —
`billing_origin_product IN ('JOBS', 'ALL_PURPOSE', 'DLT')`, une **liste blanche** et non
l'exclusion de `MODEL_SERVING` / `AI_FUNCTIONS` que proposait la v3 : `AI_FUNCTIONS` est
apparu le 2025-11-07 et `DATABASE` le 2025-09-09 dans ce compte, une liste noire écrite en
2025-08 les aurait admis en silence. Effet de bord acquis : la valeur `'serverless'` devient
structurellement improductible (zéro ligne `%SERVERLESS%` dans les 3 produits retenus sur tout
l'historique) — le but affiché par la v2, atteint sans renommer quoi que ce soit. La branche
`CASE` correspondante est **conservée comme témoin** : sa réapparition signalerait un
changement de facturation Databricks, pas un bug du builder.

**Ne pas renommer `sku_group`.** Vérifié : c'est un contrat plein-stack — paramètre d'URL
`?sku_group=` ([`routes/compute_metrics.py`](../../../packages/dcm-backend/app/api/routes/compute_metrics.py)),
filtre à valeurs distinctes ([`compute_metrics_filters.py:369-375`](../../../packages/dcm-backend/app/api/services/compute_metrics_filters.py#L369-L375)),
`ClusterCostItem.sku_group` ([`schemas/compute_metrics.py:78`](../../../packages/dcm-commons/dcm_commons/schemas/compute_metrics.py#L78)),
type TS ([`api.ts:1744`](../../../packages/dcm-frontend/src/types/api.ts#L1744)), champ « SKU
group » du drawer, clés de cache React Query. Casser 3 packages et une API d'URL pour **791 $**
de coût mal attribué n'est pas un arbitrage défendable ; le renommage reste une piste de
lisibilité **séparée**.

Reste vrai de la v2, et à traiter par qui portera §10.2 : `product_features.is_serverless` est
**NULL** sur une partie des lignes de cette table, donc un remplacement naïf du `LIKE` par le
champ officiel doit traiter le NULL explicitement — ce qui n'est **pas** le cas du produit
`DLT`, où le champ est toujours renseigné (cf. §10.2).

⚠️ **Piège de méthode, et la v3 y est tombée.** Une requête attribuant un produit **par
cluster** avait sorti 36 lignes / 240 $ de `serverless` sur `ALL_PURPOSE`/`JOBS` ; une seconde,
**par ligne de facturation**, en trouvait zéro. La v3 en a conclu que la première était
l'artefact. C'est l'inverse : le grain du gold est le **jour-cluster**, pas la ligne de
facturation. La requête par ligne répondait donc à une question que la table ne pose pas
(« existe-t-il une ligne à la fois `%SERVERLESS%` et `ALL_PURPOSE` ? » — non), et la première
touchait le vrai phénomène (des jours-cluster mixtes), même si sa méthode — « le produit le
plus fréquent » — restait fausse. **Mesurer au grain de la table cible**, ni au-dessus ni
en-dessous : c'est ce qui a fait passer le diagnostic de « 1 286 $ à retirer » à « 791 $ à
corriger sur 134 lignes conservées ».

---

## 11. Séquencement

| # | Lot | Contenu | Débloque |
|---|---|---|---|
| **T1** | Correctif §10.3 (warehouses serverless) | neutraliser `idle_pct`/`utilization_status`/`estimated_savings_usd` quand serverless | **retire ≈ 98 k$/30 j de fausses économies déjà affichées.** Le plus rentable du lot, aucune donnée nouvelle |
| **T2** | Job serverless dans la page Jobs | `compute_kind` sur `job_cluster_cost_daily` en lecture **billing-direct** (miroir de `pipeline_cost_daily`, pas un rollup de `cluster_cost_daily`) | 60 021 $ / 30 j visibles, là où l'utilisateur les cherche. Quick win, aucune page nouvelle |
| **T3** | Correctifs §10.1 et §10.4 — **un seul défaut, deux fois** : une population filtrée sur un id de `usage_metadata` sans prédicat de produit | liste blanche de produits sur `pipeline_cost_daily` **et** sur `cluster_cost_daily` ; purge des orphelines pour la première (paramètre de run `one_off_purge`), `full_refresh` seul pour la seconde | fiabilise les pages DLT et clusters existantes : **retire 113 085 lignes / 37 100 $** de faux DLT ; côté clusters **aucune ligne retirée**, mais **134 jours-cluster** débarrassés de **791 $** de coût étranger sur 97 clusters réels |
| **T4** | `serverless_cost_daily` + `_rolling` | table socle, `serverless_surface` dans le grain, sentinelle `object_id` | données de la page A |
| **T5** | Page A, blocs 1 & 3 | bandeau + leviers ; 3 composants à créer (§8) | la page devient utile |
| **T6** | `serverless_governance` + bloc 2 | matrice d'attribution (`identity` coalescée), budget policies | chargeback serverless |
| **T7** | Ingestion `pipeline_update_timeline` (agrégée par `update_id`) | fiabilité / durée DLT serverless | comparatif serverless vs classic |
| **T8** | Bloc 4 (onglets) + forecast `SERVERLESS_SURFACE` | drill-down par surface, dont onglets au grain workspace | parité avec les pages existantes |
| **T9** | §10.2 (robustesse `compute_kind`) | `is_serverless` officiel + test de non-régression sur l'équivalence | dette technique, priorité basse |

**Décision à trancher avant T6** : activation de `system.billing.attributed_usage`
(§4). Sans elle, l'attribution des 48,7 % de dépense serverless SQL reste bloquée au grain
warehouse, et le bloc 2 restera partiel — ce n'est pas un problème de code. À noter que
même avec `attributed_usage`, le rattachement d'une requête warehouse à sa source restera
limité par les **97,1 % de requêtes sans `query_source` exploitable** (§4).

---

## Annexe — requêtes de mesure

### Discriminant de surface, à porter tel quel dans le builder gold

`ELSE` explicite et **liste de produits fermée** : la v1 renvoyait tout inconnu vers
`PLATFORM_AUTO`, ce qui y a silencieusement rangé `LAKEFLOW_CONNECT`. Un produit nouveau
doit apparaître en `OTHER` et se voir, pas se fondre dans une catégorie existante.

```sql
CASE
  WHEN billing_origin_product = 'JOBS'                                        THEN 'JOB'
  WHEN billing_origin_product = 'DLT'                                         THEN 'DLT_PIPELINE'
  WHEN billing_origin_product = 'SQL'
       AND usage_metadata.dlt_pipeline_id IS NOT NULL                         THEN 'MV_ST_REFRESH'
  WHEN billing_origin_product = 'SQL'                                         THEN 'SQL_WAREHOUSE'
  WHEN billing_origin_product = 'INTERACTIVE'                                 THEN 'NOTEBOOK'
  WHEN billing_origin_product = 'APPS'                                        THEN 'APP'
  WHEN billing_origin_product = 'GENIE'                                       THEN 'GENIE'
  WHEN billing_origin_product IN ('MODEL_SERVING','VECTOR_SEARCH','AI_GATEWAY',
                                  'SUPERVISOR_AGENT','AI_FUNCTIONS',
                                  'AGENT_EVALUATION')                         THEN 'AI_ENDPOINT'
  WHEN billing_origin_product IN ('DATABASE','LAKEBASE')                      THEN 'LAKEBASE'
  WHEN billing_origin_product = 'NETWORKING'                                  THEN 'NETWORKING'
  WHEN billing_origin_product IN ('PREDICTIVE_OPTIMIZATION',
                                  'DATA_QUALITY_MONITORING',
                                  'FINE_GRAINED_ACCESS_CONTROL',
                                  'DATA_CLASSIFICATION')                      THEN 'PLATFORM_AUTO'
  ELSE 'OTHER'   -- jamais NULL : clé de merge
END AS serverless_surface
```

`GENIE` est **séparé de `AI_ENDPOINT`** : c'est la seule surface IA sans `endpoint_id`
(0 sur 15 850 $), donc sans clé d'objet, et elle pèse plus que `AI_ENDPOINT` entier.

`DATA_CLASSIFICATION` n'apparaît **que sur Azure** (107,54 $, 1 workspace) : il n'existe
pas dans les mesures AWS de ce document et serait resté invisible sans la vérification
bi-cloud. C'est précisément l'intérêt du `ELSE 'OTHER'` : le seul reliquat après cet ajout
est `LAKEFLOW_CONNECT` (4,82 $, AWS), qui n'est ni de la plateforme auto ni un objet
listable et reste donc légitimement en `OTHER`. **Contrôle à garder** : `OTHER` doit rester
sous ~10 $ par cloud ; au-delà, un produit nouveau est apparu et il faut le classer, pas
l'ignorer.

### Clé d'objet par surface, avec sentinelle

```sql
COALESCE(
  CASE serverless_surface
    WHEN 'JOB'           THEN usage_metadata.job_id
    WHEN 'DLT_PIPELINE'  THEN usage_metadata.dlt_pipeline_id
    WHEN 'MV_ST_REFRESH' THEN usage_metadata.dlt_pipeline_id
    WHEN 'SQL_WAREHOUSE' THEN usage_metadata.warehouse_id
    WHEN 'NOTEBOOK'      THEN usage_metadata.notebook_id
    WHEN 'APP'           THEN usage_metadata.app_id
    WHEN 'AI_ENDPOINT'   THEN COALESCE(usage_metadata.endpoint_id,
                                       usage_metadata.ai_gateway.endpoint_id)
    WHEN 'LAKEBASE'      THEN COALESCE(usage_metadata.endpoint_id,
                                       usage_metadata.dlt_pipeline_id)
    ELSE NULL   -- GENIE, PLATFORM_AUTO, NETWORKING, OTHER : grain workspace
  END,
  '_NO_OBJECT'
) AS object_id
```

### Périmètre serverless (§1)

`product_features.is_serverless = true` **∪** produit dans
`('GENIE','MODEL_SERVING','VECTOR_SEARCH','LAKEBASE','NETWORKING','AI_FUNCTIONS','AI_GATEWAY','LAKEFLOW_CONNECT','SUPERVISOR_AGENT','AGENT_EVALUATION')`.

### Jointure prix

⚠️ Le nom de la colonne cloud **diffère entre les tables système et la couche curated** :
`system.billing.usage`/`list_prices` exposent `cloud`, `curated_dbx_billing_*` exposent
`cloud_provider`. Les requêtes de mesure de ce document utilisent la première forme, les
builders gold la seconde (cf.
[`pipeline_cost_daily`](../../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/pipeline_cost_daily.py#L193-L205)) :

```sql
-- mesure, sur system.*
LEFT JOIN system.billing.list_prices lp
  ON lp.sku_name = u.sku_name AND lp.cloud = u.cloud
 AND lp.price_start_time <= u.usage_start_time
 AND (lp.price_end_time IS NULL OR u.usage_start_time < lp.price_end_time)
```

### Agrégation obligatoire des tables périodisées à l'heure

```sql
-- pipeline_update_timeline : une ligne par TRANCHE HORAIRE, pas par update
SELECT workspace_id, pipeline_id, update_id,
       MAX(compute.type)  AS compute_type,
       MAX(result_state)  AS result_state,   -- NULL sur les tranches non terminales
       unix_timestamp(MAX(period_end_time))
         - unix_timestamp(MIN(period_start_time)) AS duration_sec
FROM system.lakeflow.pipeline_update_timeline
GROUP BY workspace_id, pipeline_id, update_id
```

### Contrôles de non-régression à rejouer si les chiffres bougent

⚠️ **Tous ces contrôles sont mono-cloud** : ajouter `cloud_provider = 'aws'` (ou `cloud =
'AWS'` sur `system.*`) sur une base bi-cloud, sinon ils échouent tous. Les deux contrôles
bi-cloud sont en fin de tableau.

| Contrôle | Attendu au 2026-09-09 (fenêtre 08-10 → 09-09) |
|---|---|
| part serverless de la dépense DBU | **79,3 %** (250 466 + 34 878 sur 360 039 $) |
| lignes hors des 3 buckets du §1 | **0** (partition exacte) |
| surfaces distinctes du `CASE` ci-dessus | **12** dont `OTHER` non vide (4,82 $, LAKEFLOW_CONNECT) |
| $ sans clé d'objet | **26 533 $** (9,3 % du serverless) |
| $ sans propriétaire (ni tag, ni policy, ni identité) | **5 875 $** (2,06 % du serverless) |
| `billing_origin_product` distincts avec `dlt_pipeline_id` | **4** (DLT, SQL, DATABASE, VECTOR_SEARCH) |
| `compute.type` distincts dans `pipeline_update_timeline` | **2** (SERVERLESS_COMPUTE, CLASSIC_COMPUTE) |
| updates DLT par `update_id` (srvls / classic) | **35 572 / 6 245** |
| lignes dans `system.billing.attributed_usage` | **0** |
| `query.history` : part de `SERVERLESS_COMPUTE` | **47,9 %** des requêtes / 7 j |
| `query.history` : `waiting_for_compute_duration_ms` non NULL sur `SERVERLESS_COMPUTE` | **0** |
| `usage_policy_id` ≠ `budget_policy_id` (null-safe) | **0 ligne** sur 2 294 408 |
| `job_run_timeline.compute_ids` vide | ~~**88,5 %**~~ → **97,0 %** (errata 2026-09-10, non reproductible ; 95,3 % aws / 59,3 % azure) |
| équivalence `cluster_id IS NULL` ⟺ `is_serverless` sur produit `DLT` | **parfaite** (51 748 / 11 869, 0 discordance) |
| warehouses serverless avec ≥ 1 `STARTING` | **380 / 398** |
| jours-warehouse serverless à `idle_pct > 60 %` | **95,6 %** |
| **bi-cloud** — serverless Azure (curated) | **103 967 $** / 158 544 $ = **65,6 %**, 143 WS |
| **bi-cloud** — `OTHER` par cloud | ≤ **10 $** (aws 4,82 $ ; azure 0 $ après ajout de `DATA_CLASSIFICATION`) |
