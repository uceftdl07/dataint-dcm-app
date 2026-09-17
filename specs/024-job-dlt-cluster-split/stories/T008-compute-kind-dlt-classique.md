# T008 — `compute_kind` en gold + page DLT bornée au compute classique

**Domain**: dataeng (+ backend, 1 service)
**Package**: packages/dcm-databricks-pipeline, packages/dcm-commons, packages/dcm-backend
**Branch**: `frontend/024-nav-compute-3-onglets-all-purpose-jobs` — **pas de dispatch**, tasks
enchaînées sur la branche existante (consigne utilisateur du 2026-09-09)
**Jira**: aucune clé — task non dispatchée
**Depends on**: T001c (`pipeline_cost_daily`/`_rolling`), T007 (population facturée)
**Work type**: feature

## Description

Demande du 2026-09-09 : « pour la page DLT cluster, nous voulons seulement le DLT cluster
(`PIPELINE` / `PIPELINE_MAINTENANCE`). Pour rappel la page est dédiée au cluster de type DLT,
pas au DLT au global. »

La page listait les deux formes de compute DLT sans le dire. Elle est la seule des trois pages
Compute dans ce cas : « All-purpose clusters » et « Job clusters » descendent de
`cluster_cost_daily`, donc d'un `cluster_type` ; la page DLT descend d'un rollup
**billing-direct** (`usage_metadata.dlt_pipeline_id IS NOT NULL`) qui ne porte aucun
discriminant de compute. C'est cet écart que la task ferme.

**Le serverless n'est pas une anomalie** — c'est 97 % du DLT facturé en dev et 92 % du coût. Il
n'est pas supprimé, il est **étiqueté** : d'où une colonne en gold plutôt qu'un filtre dur, pour
qu'une vue serverless reste possible plus tard sans reconstruire le rollup.

## Décision — où vit le filtre (tranchée par l'utilisateur)

Trois options ont été présentées ; retenue : **colonne `compute_kind` en gold, filtre `CLASSIC`
côté app**.

- `compute_kind` ∈ `CLASSIC` / `SERVERLESS`, jamais `NULL`, dérivée de
  `usage_metadata.cluster_id IS NOT NULL` sur la ligne de facturation.
- **Le grain des 2 tables gagne `compute_kind`** : sans cela les 2 pipelines mixtes (mesurés,
  fenêtre 30 j) garderaient un coût mélangé, et l'exactitude du coût était la condition posée.
- L'app filtre `CLASSIC`. Aucune table n'est perdue pour un usage futur.

Écartées : filtrer dur en gold (le serverless deviendrait invisible partout), et filtrer côté
app par une sous-requête sur `curated_dbx_billing_usage` (une jointure de plus sur chaque route,
pour une information que gold peut porter une fois pour toutes).

## Pourquoi `cluster_id IS NOT NULL` est un proxy exact, pas une heuristique

Mesuré en dev le 2026-09-09 sur `system.billing.usage` + `curated_dbx_compute_clusters` :

| Mesure | Résultat |
|---|---|
| Clusters éphémères derrière une ligne DLT facturée | **6 375** |
| Dont `cluster_source = 'PIPELINE'` | **6 375** (100 %) |
| Absents de la dimension cluster | **0** |
| Pipelines concernés | 181 |

`cluster_source = 'PIPELINE'` est précisément ce que `cluster_type_case_expr` traduit en
`cluster_type = 'PIPELINE'` — et gold y replie déjà `PIPELINE_MAINTENANCE`. Une ligne DLT sans
`cluster_id` n'a donc pas de cluster du tout : c'est du serverless.

## Files to create/modify

- UPDATE `pipelines/gold_dbx_compute/pipeline_cost_daily.py` — colonne `compute_kind`, entrée
  dans le grain et dans la clé de merge
- UPDATE `pipelines/gold_dbx_compute/pipeline_cost_rolling.py` — idem ; `cost_rank` /
  `is_top_cost` partitionnés par `(window_days, compute_kind)`
- UPDATE `pipelines/gold_dbx_compute/forecast.py` — agrégation `SUM … GROUP BY object_key,
  period_start` sur la passe PIPELINE (voir « Écarts »)
- UPDATE `pipelines/gold_dbx_compute/specs.py`, `packages/dcm-commons/dcm_commons/schemas/compute_metrics.py`
- UPDATE `packages/dcm-databricks-pipeline/tests/gold_dbx_compute/` (`test_pipeline_cost.py`,
  `test_forecast.py`, `test_specs.py`)
- UPDATE `packages/dcm-backend/app/api/services/compute_metrics_pipelines.py` — `_CLASSIC_ONLY`
- UPDATE `packages/dcm-backend/tests/test_compute_metrics_pipelines.py`

## Sub-tasks

- [x] Gold : `compute_kind` dans les 2 tables, dans le grain et la clé de merge, jamais `NULL`.
- [x] `cost_rank` / `is_top_cost` **par `compute_kind`** : l'IHM affiche ce rang sur une liste
      filtrée, un rang toutes formes confondues s'ouvrirait sur « 40, 57, 61… ».
- [x] ~~Recalcul complet en dev (`lower_bound=None`) puis reconstruction du rolling~~ →
      **DROP + relance des 2 tâches** : le recalcul seul ne peut pas changer le grain (voir
      « Écarts »). Exécuté en dev le 2026-09-09 (runs `967788534538711` puis
      `1008370849794262`, tous deux `SUCCESS`).
- [x] Backend : `_CLASSIC_ONLY` porté dans le **scope**, pas dans le filtre de lignes — il
      atteint ainsi les lignes, les bornes de fenêtre **et** l'agrégat des KPI d'un seul geste.
      Sans cela les cartes afficheraient 23 588 $ au-dessus d'une liste qui totalise 1 903 $.
- [x] Backend : filtre sur `overview`, `cost`, le **détail** et le **cost-trend** ; **pas** sur
      `efficiency` ni sur `uptime-trend`.
- [x] `compute_kind` servie dans le payload (liste et détail) : un lecteur doit pouvoir dire de
      quel compute il parle sans relire ce document.
- [x] Vérification sur dev : population, coût, DBU, rangs, pipeline mixte (voir « Vérification »)
      — tous les contrôles passent.

## Notes

- **Le détail et la tendance ne sont pas cosmétiques.** Le grain portant `compute_kind`, un
  pipeline mixte a deux lignes : sans filtre, `ORDER BY cost_usd DESC LIMIT 1` du détail
  renverrait la ligne serverless, et le `SUM` du cost-trend rajouterait la part serverless dans
  une série annoncée comme classique.
- **`efficiency` n'est pas filtrée et n'a pas à l'être** : `system.compute.node_timeline`
  n'échantillonne que des clusters, donc cette table ne contient déjà que du classique. La
  colonne n'y existe pas — le filtre y jetterait une `UNRESOLVED_COLUMN`.
- **Effet de bord recherché** : la colonne `Lifetime` de l'Overview DLT cessait d'être lisible
  (7 à 12 des 100 premières lignes renseignées, T007). Sur la population classique et facturée
  effectivement listée, la couverture mesurée est de **174 / 178 à 30 j, soit 98 %**. Le « — »
  massif disparaît parce que la population qui ne pouvait pas être mesurée n'est plus listée —
  pas parce qu'on a mesuré plus.
- Le filtre `_billed_only` de T007 reste appliqué **en plus** : la page liste les pipelines
  classiques **et** facturés sur la fenêtre.

## Écarts constatés

- **Le forecast PIPELINE cassait avec le changement de grain** (trouvé en relisant les lecteurs
  des 2 tables, pas remonté par les tests) : `forecast.py` passe `pipeline_cost_daily` à
  `ai_forecast` avec `object_key = (cloud_provider, workspace_id, dlt_pipeline_id)` et **sans
  `GROUP BY`** — il suppose une ligne par pipeline et par jour. Un pipeline mixte aurait produit
  deux lignes au même horodatage dans le même groupe. Corrigé par une agrégation explicite dans
  le sous-`SELECT` `observed`, ce qui **conserve** la sémantique actuelle : une prévision par
  pipeline, toutes formes de compute confondues.
- **Les autres lecteurs ont été inventoriés** : le schéma `dcm_commons` (déclaratif) et le
  service backend. Rien d'autre ne lit ces deux tables.
- **La part serverless disparaît de l'IHM sans être remplacée** : 2 789 pipelines et 43 375 DBU
  à 30 j ne sont plus visibles nulle part. C'est le périmètre demandé (« la page est dédiée au
  cluster de type DLT »), et la colonne en gold est ce qui rend une page serverless possible
  plus tard — mais aujourd'hui elle n'existe pas, et personne ne voit ce compute.
- **Les rangs changent de sens** : `cost_rank = 1` désigne désormais le pipeline classique le
  plus cher, pas le pipeline DLT le plus cher. Deux pipelines peuvent porter le rang 1 dans la
  table (un par `compute_kind`) — c'est voulu, et c'est pourquoi la partition est explicite.
- **Le plan de migration prévu (« recalcul complet ») ne fonctionne pas**, mesuré sur le run
  dev `541099072303791` du 2026-09-09 : `MERGE WITH SCHEMA EVOLUTION` n'applique l'évolution de
  schéma qu'à l'**écriture**, la condition `ON` étant résolue contre le schéma **courant** de la
  cible. Ajouter `compute_kind` aux clés de merge fait donc échouer le MERGE à l'analyse
  (`DELTA_MERGE_UNRESOLVED_EXPRESSION: Cannot resolve t.compute_kind in search condition`), et
  `full_refresh` n'y change rien — le MERGE ne démarre pas. Le grain ne se change pas par
  recalcul : il se change en **supprimant la table cible** puis en relançant la tâche (branche
  `saveAsTable` de `merge_into_table`). Limite désormais documentée dans
  `pipelines/common/writers.py`. Un `ALTER TABLE ADD COLUMN` débloquerait le MERGE mais
  laisserait les 552 835 lignes historiques à `compute_kind = NULL`, jamais appariées par le
  `<=>` null-safe, donc en doublons à purger — d'où le choix du DROP.
- **Le DROP + rebuild dev est fait** (autorisé explicitement par l'utilisateur le 2026-09-09),
  et il **reste une porte manuelle pour la prod** : le même code déployé sur des tables au
  grain ancien fait échouer la tâche `gold_pipeline_cost_daily` à chaque run nocturne avec
  `DELTA_MERGE_UNRESOLVED_EXPRESSION`. Le DROP prod doit précéder — ou accompagner — la mise
  en production, il ne peut pas être joué après.
- **Les pipelines « mixtes » sont 8 à 30 j, pas 2** — et les deux chiffres sont justes : 8 ont
  une ligne dans chaque `compute_kind`, mais seulement **2** facturent un montant non nul des
  deux côtés (`2449b18c…`, `59c2bbbd…`). Les 6 autres portent une ligne à 0 $ d'un côté, que
  le filtre `_billed_only` de T007 écarte de toute façon. Un cas mérite d'être connu :
  `d6ef89f6…` facture 9,11 $ en serverless et 0 $ en classique — il **disparaît** de la page,
  alors qu'il a bien tourné sur un cluster DLT sur la fenêtre. C'est le comportement voulu
  (la page liste ce qui coûte du classique), pas un oubli.

## Vérification

### Séquence de migration — **jouée en dev le 2026-09-09**, à rejouer en prod

Bundle déployé (`databricks bundle deploy -t dev -p dcm-dev`, wheel
`dcm_databricks_pipeline-0.1.1`), puis :

```sql
DROP TABLE it.ba_data_connect_monitoring__d.gold_dbx_compute_pipeline_cost_daily;
DROP TABLE it.ba_data_connect_monitoring__d.gold_dbx_compute_pipeline_cost_rolling;
```

```bash
# depuis packages/dcm-databricks-pipeline — 2 tâches ciblées, pas les 23 du job
databricks bundle run dcm_gold_dbx_compute --only gold_pipeline_cost_daily \
  --params full_refresh=true -t dev -p dcm-dev
databricks bundle run dcm_gold_dbx_compute --only gold_pipeline_cost_rolling -t dev -p dcm-dev
```

Sans risque de perte : l'historique curated (`curated_dbx_billing_usage` filtré DLT) remonte au
**2024-02-13**, soit exactement le `MIN(period_start)` de la table quotidienne ; les 2 tables
sont `MANAGED` / `DELTA`, `UNDROP` disponible 7 jours ; **aucun grant au niveau table** (tous
héritent du schéma / catalogue), donc rien à réattribuer. Même séquence requise en **prod**.

Contrôlé après coup : l'historique est revenu **à l'identique**, 2024-02-13 → 2026-09-09.

### Baseline capturée avant migration (2026-09-09, dev)

Sert d'invariant de conservation : ces totaux doivent être retrouvés à l'identique en sommant
les **deux** `compute_kind` après rebuild.

| Table | Lignes | Pipelines | DBU | USD |
|---|---|---|---|---|
| `pipeline_cost_daily` (2024-02-13 → 2026-09-09) | 552 835 | 20 265 | 991 603,0 | 384 364,7983 |
| `pipeline_cost_rolling` 1 j | 2 028 | 2 028 | 744,9 | 358,6040 |
| `pipeline_cost_rolling` 7 j | 2 501 | 2 501 | 10 938,1 | 5 182,9062 |
| `pipeline_cost_rolling` 30 j | 6 062 | 6 062 | 49 591,1 | 23 588,7254 |
| `pipeline_cost_rolling` 90 j | 12 983 | 12 983 | 124 764,1 | 59 112,1405 |

Attendu, mesuré sur `system.billing.usage` **avant** écriture (fenêtre 30 j glissante depuis
`current_date()`, dev) :

| Mesure | CLASSIC | SERVERLESS |
|---|---|---|
| Pipelines | **181** | 2 793 |
| DBU | **6 467,9** | 44 981,1 |

Écart avec les 178 / 6 216 annoncés au cadrage : la fenêtre. Ces chiffres-ci partent de
`current_date() - INTERVAL 30 DAYS`, la table `_rolling` ancre la sienne sur
`MAX(period_start)`. Les 181 recoupent la mesure de population classique déjà notée. Pipelines
mixtes **facturant les deux formes** : **2** sur 2 972, conforme au cadrage — 8 ont une ligne
dans chaque forme, dont 6 à 0 $ d'un côté (voir « Écarts »).

### Conservation après rebuild — mesurée le 2026-09-09

Σ des deux `compute_kind` **contre la baseline ci-dessus**. Le coût et les DBU sont conservés au
centime ; seul le **nombre de lignes** monte, du nombre exact de grains qui facturent les deux
formes — c'est l'éclatement de grain demandé, pas une duplication.

| Table / fenêtre | Lignes | Δ lignes | DBU | USD | Verdict |
|---|---|---|---|---|---|
| `pipeline_cost_daily` | 552 968 | +133 | 991 603,0 | 384 364,7983 | conservé (20 265 pipelines, 2024-02-13 → 2026-09-09) |
| `_rolling` 1 j | 2 028 | 0 | 744,9 | 358,6040 | conservé, aucun mixte |
| `_rolling` 7 j | 2 501 | 0 | 10 938,1 | 5 182,9062 | conservé, aucun mixte |
| `_rolling` 30 j | 6 070 | +8 | 49 591,1 | 23 588,7254 | conservé, 8 mixtes |
| `_rolling` 90 j | 13 010 | +27 | 124 764,1 | 59 112,1405 | conservé, 27 mixtes |

Contrôles :

| Contrôle | Attendu | Mesuré |
|---|---|---|
| `compute_kind IS NULL` dans les 2 tables | 0 | **0 / 0** |
| Σ(CLASSIC) + Σ(SERVERLESS) vs baseline | coût et DBU identiques | **identiques** (voir tableau ci-dessus) |
| Population servie par `overview` / `cost` (1/7/30/90 j) | 93 / 162 / 178 / 237 | **93 / 162 / 178 / 237** |
| `overview.total` = `cost.total` = KPI `active_pipelines` | égalité aux 4 fenêtres | **égalité aux 4** |
| KPI coût total vs Σ gold `CLASSIC` | égalité aux 4 fenêtres | **22,655 / 466,233 / 1 901,396 / 5 251,630 $** — égal au centime |
| Lignes `SERVERLESS` servies | 0 | **0** aux 4 fenêtres |
| Lignes à 0 $ servies (`_billed_only`, T007) | 0 | **0** aux 4 fenêtres |
| Rangs de la 1re page de Cost | 1, 2, 3… | **1, 2, 3, 4, 5** aux 4 fenêtres |
| Pipeline mixte : détail et cost-trend | part classique seule | `a6c534ba…` détail **7,0346 $** `compute_kind=CLASSIC`, cost-trend **Σ 7,0346 $** sur 26 points |
| Efficiency non filtrée (population propre) | 90 / 158 / 174 / 202 | **90 / 158 / 174 / 202** |

Couverture d'efficacité sur la population classique — la raison d'être de la task côté IHM :
**174 / 178 à 30 j, soit 98 %** (contre 7 à 12 lignes renseignées sur les 100 premières avant le
filtre). La colonne `Lifetime` de l'Overview DLT redevient lisible. À 90 j la couverture
retombe à 202 / 237 (85 %) : `node_timeline` a une rétention plus courte que la facturation.

Portes :

| Porte | Résultat |
|-------|----------|
| `uv run pytest tests/test_compute_metrics_pipelines.py` (backend) | **82 passés** |
| `uv run ruff check` sur les 2 fichiers backend | propre |
| `uv run pytest` (dcm-databricks-pipeline) | **723 passés** |
| `uv run pytest` (dcm-commons) | **144 passés** |
| `uv run ruff check` sur les fichiers touchés | propre (`writers.py`, `gold_dbx_compute/`, tests) |
| `databricks bundle validate --strict -t dev` | **Validation OK** |
| `databricks bundle deploy -t dev` | **fait** (wheel 0.1.1 uploadée) |
| Rebuild dev des 2 tables | **fait** — DROP autorisé par l'utilisateur, runs `967788534538711` et `1008370849794262` `SUCCESS` |
| Vérification des invariants sur dev | **tous passés** (voir « Contrôles ») |
| Vérification navigateur (`localhost:4000`) | **à faire par l'utilisateur**, avec T006 et T007 |

Notes de portes : `ruff check` sur l'ensemble du package remonte 269 erreurs et `dcm-commons`
13 `D101`, toutes préexistantes et hors fichiers touchés — le workflow CI a d'ailleurs
`ruff` et `mypy` **commentés** pour ce package, seule `pytest tests` y est bloquante. `mypy`
n'est pas une porte utilisable ici (collision de chemins de modules préexistante sur
`pipelines/`).
